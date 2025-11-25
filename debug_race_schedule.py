"""レーススケジュールのHTML構造を確認"""
import requests
from bs4 import BeautifulSoup
from datetime import datetime

today = datetime.now().strftime('%Y%m%d')
url = f"https://www.boatrace.jp/owpc/pc/race/index?hd={today}"

print(f"URL: {url}")
print(f"日付: {today}\n")

try:
    response = requests.get(url, timeout=10)
    response.raise_for_status()

    print(f"[OK] Status: {response.status_code}\n")

    soup = BeautifulSoup(response.content, 'html.parser')

    # table1クラスを探す
    print("="*70)
    print("table1クラスのテーブル:")
    print("="*70)
    table1_divs = soup.find_all('div', class_='table1')
    print(f"Found {len(table1_divs)} table1 divs")

    # tbody tr要素を探す
    print("\n" + "="*70)
    print("tbody tr要素:")
    print("="*70)
    venue_elements = soup.select('.table1 tbody tr')
    print(f"Found {len(venue_elements)} tbody tr elements")

    for i, elem in enumerate(venue_elements[:5]):
        jyo_code = elem.get('jyo')
        print(f"  [{i}] jyo={jyo_code}, classes={elem.get('class')}")
        print(f"       text: {elem.get_text(strip=True)[:100]}")

    # is-w495テーブルを探す
    print("\n" + "="*70)
    print("is-w495テーブル:")
    print("="*70)
    tables = soup.find_all('table', class_='is-w495')
    print(f"Found {len(tables)} tables")

    # bodyTableクラスを探す
    print("\n" + "="*70)
    print("bodyTableクラス:")
    print("="*70)
    body_tables = soup.find_all('table', class_='bodyTable')
    print(f"Found {len(body_tables)} bodyTable")

    if body_tables:
        for i, table in enumerate(body_tables[:2]):
            print(f"\n[{i}] bodyTable:")
            trs = table.find_all('tr')
            print(f"  rows: {len(trs)}")
            for j, tr in enumerate(trs[:3]):
                jyo = tr.get('jyo')
                print(f"    [{j}] jyo={jyo}, text={tr.get_text(strip=True)[:80]}")

    # 全てのjyo属性を持つ要素を探す
    print("\n" + "="*70)
    print("jyo属性を持つ全要素:")
    print("="*70)
    jyo_elements = soup.find_all(attrs={'jyo': True})
    print(f"Found {len(jyo_elements)} elements with jyo attribute")

    for i, elem in enumerate(jyo_elements[:10]):
        jyo = elem.get('jyo')
        print(f"  [{i}] tag={elem.name}, jyo={jyo}, class={elem.get('class')}")

except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
