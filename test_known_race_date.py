"""過去の開催日でテスト（2025-11-04）"""
import requests
from bs4 import BeautifulSoup

# DBに存在する最新の日付でテスト
date_str = "20251104"
url = f"https://www.boatrace.jp/owpc/pc/race/index?hd={date_str}"

print(f"URL: {url}")
print(f"日付: {date_str}\n")

try:
    response = requests.get(url, timeout=10)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, 'html.parser')

    # jyo属性を持つ要素を探す
    jyo_elements = soup.find_all(attrs={'jyo': True})
    print(f"jyo属性を持つ要素: {len(jyo_elements)}件\n")

    if jyo_elements:
        print("開催会場:")
        for i, elem in enumerate(jyo_elements[:10]):
            jyo = elem.get('jyo')
            print(f"  [{i}] jyo={jyo}, tag={elem.name}, class={elem.get('class')}")
    else:
        print("[INFO] jyo属性を持つ要素が見つかりませんでした")

        # 別の方法で開催情報を探す
        print("\n代替方法で検索中...")

        # is-arrow1クラスのリンクを探す
        arrow_links = soup.find_all('a', class_='is-arrow1')
        print(f"is-arrow1リンク: {len(arrow_links)}件")

        if arrow_links:
            print("\nリンク情報:")
            for i, link in enumerate(arrow_links[:5]):
                href = link.get('href')
                text = link.get_text(strip=True)
                print(f"  [{i}] href={href}, text={text}")

                # 会場コードを抽出
                if href and 'jcd=' in href:
                    jcd = href.split('jcd=')[1].split('&')[0]
                    print(f"       -> 会場コード: {jcd}")

except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
