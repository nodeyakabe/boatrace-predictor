"""決まり手取得テスト"""
import requests
from bs4 import BeautifulSoup

# レース情報
venue_code = 6
race_date = '2026-01-01'
race_number = 1

# URLを構築
date_str = race_date.replace('-', '')
url = f'https://www.boatrace.jp/owpc/pc/race/raceresult?rno={race_number}&jcd={int(venue_code):02d}&hd={date_str}'

print(f'URL: {url}')
print()

try:
    # HTTPリクエスト
    response = requests.get(url, timeout=10)
    response.encoding = response.apparent_encoding

    print(f'ステータスコード: {response.status_code}')
    print(f'レスポンス長: {len(response.text)}')
    print()

    # BeautifulSoupでパース
    soup = BeautifulSoup(response.text, 'lxml')

    # 決まり手テーブルを探す
    tables = soup.find_all('table')
    print(f'テーブル数: {len(tables)}')
    print()

    for i, table in enumerate(tables):
        thead = table.find('thead')
        if not thead:
            continue

        headers = [th.get_text(strip=True) for th in thead.find_all('th')]

        if '決まり手' in headers:
            print(f'テーブル#{i}: 決まり手テーブル発見！')
            print(f'ヘッダー: {headers}')

            tbody = table.find('tbody')
            if tbody:
                tds = tbody.find_all('td')
                print(f'TD数: {len(tds)}')
                for j, td in enumerate(tds[:10]):  # 最初の10個
                    print(f'  TD[{j}]: [{td.get_text(strip=True)}]')
            else:
                print('  tbody not found')
            break
    else:
        print('決まり手テーブルが見つかりませんでした')

except Exception as e:
    print(f'エラー: {type(e).__name__}: {e}')
