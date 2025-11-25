"""会場ページのHTML構造を確認"""
import requests
from bs4 import BeautifulSoup

url = "https://www.boatrace.jp/owpc/pc/data/stadium?jcd=01"

print("URL:", url)
print("\nHTMLを取得中...")

try:
    response = requests.get(url, timeout=30, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    response.raise_for_status()
    response.encoding = response.apparent_encoding

    print("[OK] 取得成功")
    print(f"Status: {response.status_code}")
    print(f"Encoding: {response.encoding}")

    soup = BeautifulSoup(response.content, 'html.parser')

    # CSSクラスを探す
    print("\n" + "="*70)
    print("table1クラスの要素:")
    print("="*70)
    table1_divs = soup.find_all('div', class_='table1')
    print(f"Found {len(table1_divs)} elements")
    for i, div in enumerate(table1_divs[:2]):
        print(f"\n[{i}] {div.get_text(strip=True)[:200]}")

    print("\n" + "="*70)
    print("is-w495クラスのテーブル:")
    print("="*70)
    tables = soup.find_all('table', class_='is-w495')
    print(f"Found {len(tables)} tables")
    for i, table in enumerate(tables[:2]):
        print(f"\n[{i}] {table.get_text(strip=True)[:200]}")

    # 全てのCSSクラスをリストアップ
    print("\n" + "="*70)
    print("ページ内の全クラス（上位30件）:")
    print("="*70)
    all_classes = set()
    for tag in soup.find_all(True):
        if tag.has_attr('class'):
            for cls in tag['class']:
                all_classes.add(cls)

    for cls in sorted(list(all_classes))[:30]:
        print(f"  - {cls}")

    # HTMLを保存
    with open('venue_page_debug.html', 'w', encoding='utf-8') as f:
        f.write(str(soup))

    print("\n[OK] HTMLをvenue_page_debug.htmlに保存しました")

except Exception as e:
    print(f"\n[ERROR] {e}")
    import traceback
    traceback.print_exc()
