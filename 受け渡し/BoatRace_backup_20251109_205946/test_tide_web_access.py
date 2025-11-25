"""
気象庁潮位表のWebインターフェース経由でのデータ取得テスト
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

def test_web_tide_access():
    """Webインターフェース経由で潮位データにアクセス"""

    print("="*80)
    print("気象庁潮位表 Webアクセステスト")
    print("="*80)

    # テスト: 2024年10月1日から7日間（博多）
    url = 'https://www.data.jma.go.jp/kaiyou/db/tide/suisan/suisan.php'

    test_cases = [
        {'year': '2024', 'month': '10', 'station': '61', 'station_name': '博多'},
        {'year': '2015', 'month': '11', 'station': '61', 'station_name': '博多'},
    ]

    for test in test_cases:
        print(f"\n{test['station_name']} {test['year']}年{test['month']}月:")
        print("-" * 40)

        params = {
            'stn': test['station'],
            'yy': test['year'],
            'mm': test['month'],
            'dd': '1',
            'rg': '7',  # 7日間
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            print(f"  Status: {response.status_code}")

            if response.status_code == 200:
                # Shift_JISでデコード
                response.encoding = 'shift_jis'
                html = response.text

                # エラーメッセージチェック
                if '地点、年の設定に誤りがあります' in html:
                    print(f"  [ERROR] 地点・年の設定エラー")
                    print(f"  この年月のデータは提供されていません")
                    continue

                # BeautifulSoupでパース
                soup = BeautifulSoup(html, 'html.parser')

                # テーブルを探す
                tables = soup.find_all('table')
                print(f"  テーブル数: {len(tables)}")

                # 潮位データが含まれそうなテーブルを探す
                for i, table in enumerate(tables):
                    # テーブルの最初の数行を表示
                    rows = table.find_all('tr')
                    if rows and len(rows) > 2:
                        print(f"\n  テーブル {i+1} (行数: {len(rows)}):")
                        for j, row in enumerate(rows[:5]):
                            cells = row.find_all(['th', 'td'])
                            cell_text = [cell.get_text(strip=True) for cell in cells]
                            if cell_text:
                                print(f"    行{j+1}: {cell_text}")

                        # 「満潮」「干潮」が含まれるかチェック
                        table_text = table.get_text()
                        if '満潮' in table_text or '干潮' in table_text:
                            print(f"    [OK] 潮位データを含むテーブル発見")

        except Exception as e:
            print(f"  [ERROR] {e}")

    print("\n" + "="*80)
    print("テスト完了")
    print("="*80)

if __name__ == '__main__':
    test_web_tide_access()
