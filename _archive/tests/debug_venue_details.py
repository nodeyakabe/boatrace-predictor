"""会場詳細データの抽出をデバッグ"""
import requests
from bs4 import BeautifulSoup
import re

url = "https://www.boatrace.jp/owpc/pc/data/stadium?jcd=01"

print("URL:", url)
print("\nHTMLを取得中...")

response = requests.get(url, timeout=30, headers={
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
})
response.raise_for_status()
response.encoding = response.apparent_encoding

soup = BeautifulSoup(response.content, 'html.parser')

print("[OK] 取得成功\n")

# table1クラスの要素を詳細に確認
print("="*70)
print("table1クラスの要素（詳細）:")
print("="*70)

table1_divs = soup.find_all('div', class_='table1')
for i, div in enumerate(table1_divs):
    print(f"\n[{i}] table1要素:")

    # dl/dt/ddタグを探す
    dl_items = div.find_all('dl')
    print(f"  dl要素数: {len(dl_items)}")

    for j, dl in enumerate(dl_items):
        dt = dl.find('dt')
        dd = dl.find('dd')
        if dt and dd:
            print(f"    [{j}] {dt.get_text(strip=True)}: {dd.get_text(strip=True)}")

    # レコード情報を探す
    print("\n  レコード関連テキスト:")
    text_content = div.get_text()
    if '秒' in text_content:
        lines = [line.strip() for line in text_content.split('\n') if line.strip() and '秒' in line]
        for line in lines[:5]:
            print(f"    - {line}")

# 水質・干満差などの情報を探す
print("\n" + "="*70)
print("水質・干満差・モーター情報:")
print("="*70)

# すべてのdl要素を確認
all_dls = soup.find_all('dl')
for dl in all_dls:
    dt = dl.find('dt')
    dd = dl.find('dd')
    if dt and dd:
        key = dt.get_text(strip=True)
        value = dd.get_text(strip=True)
        if any(keyword in key for keyword in ['水質', '干満', 'モーター', '干満差', '水面']):
            print(f"  {key}: {value}")

# h3見出しとそれに続くコンテンツを確認
print("\n" + "="*70)
print("h3見出しとコンテンツ:")
print("="*70)

h3_tags = soup.find_all('h3', class_='is-fs18')
for h3 in h3_tags[:5]:
    print(f"\n見出し: {h3.get_text(strip=True)}")
    next_elem = h3.find_next_sibling()
    if next_elem:
        print(f"  次の要素: {next_elem.name} class={next_elem.get('class')}")
        print(f"  内容: {next_elem.get_text(strip=True)[:150]}")

print("\n" + "="*70)
print("完了")
print("="*70)
