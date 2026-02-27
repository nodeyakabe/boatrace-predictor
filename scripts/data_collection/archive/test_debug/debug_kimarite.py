"""決まり手デバッグ"""
import requests
from bs4 import BeautifulSoup
import warnings
from bs4 import XMLParsedAsHTMLWarning
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# Test レース: venue=23, race=6, date=2026-01-01
url = 'https://www.boatrace.jp/owpc/pc/race/raceresult?rno=6&jcd=23&hd=20260101'

print(f"URL: {url}")

response = requests.get(url, timeout=10)
response.encoding = response.apparent_encoding
soup = BeautifulSoup(response.text, 'lxml')

tables = soup.find_all('table')
print(f"\\nTotal tables: {len(tables)}")

for i, table in enumerate(tables):
    thead = table.find('thead')
    if not thead:
        print(f"Table #{i}: No thead")
        continue

    headers = [th.get_text(strip=True) for th in thead.find_all('th')]
    print(f"\\nTable #{i}: {headers}")

    if any('決まり手' in h for h in headers):
        print(f"  -> FOUND kimarite table!")
        tbody = table.find('tbody')
        if tbody:
            tds = tbody.find_all('td')
            print(f"  -> TD count: {len(tds)}")
            for j, td in enumerate(tds[:5]):
                try:
                    print(f"     TD[{j}]: [{td.get_text(strip=True)}]")
                except:
                    print(f"     TD[{j}]: [encoding error]")
        else:
            print(f"  -> No tbody")
