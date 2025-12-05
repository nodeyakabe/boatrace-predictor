"""
本日開催されている競艇場を確認
"""
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import warnings
from bs4 import XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

date = datetime.now().strftime('%Y%m%d')
venues = [
    ('01', '桐生'), ('02', '戸田'), ('03', '江戸川'), ('04', '平和島'),
    ('05', '多摩川'), ('06', '浜名湖'), ('07', '蒲郡'), ('08', '常滑'),
    ('09', '津'), ('10', '三国'), ('11', 'びわこ'), ('12', '住之江'),
    ('13', '尼崎'), ('14', '鳴門'), ('15', '丸亀'), ('16', '児島'),
    ('17', '宮島'), ('18', '徳山'), ('19', '下関'), ('20', '若松'),
    ('21', '芦屋'), ('22', '福岡'), ('23', '唐津'), ('24', '大村')
]

print(f"=== {date} 本日のレース開催状況 ===\n")

for code, name in venues:
    try:
        url = "https://www.boatrace.jp/owpc/pc/race/racelist"
        params = {'rno': 1, 'jcd': code, 'hd': date}
        headers = {'User-Agent': 'Mozilla/5.0'}

        response = requests.get(url, params=params, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'lxml')

        # データがあるか確認
        no_data = soup.find_all(string=lambda x: x and 'データがありません' in str(x))
        has_table = soup.find('table', class_=lambda x: x and 'is-w495' in str(x))

        if not no_data and has_table:
            print(f"{name}({code}): 開催中")
        else:
            print(f"{name}({code}): 休催")

    except Exception as e:
        print(f"{name}({code}): エラー - {str(e)[:30]}")
