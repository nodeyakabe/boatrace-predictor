"""
Playwrightベース オッズスクレイパー
JavaScriptで動的にレンダリングされる3連単オッズデータを取得
"""

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import re
import time


class PlaywrightOddsScraper:
    """Playwrightを使った3連単オッズ取得クラス"""

    def __init__(self, headless: bool = True, timeout: int = 30000):
        """
        初期化

        Args:
            headless: ヘッドレスモードで実行するか
            timeout: ページ読み込みタイムアウト（ミリ秒）
        """
        self.headless = headless
        self.timeout = timeout
        self.base_url = "https://www.boatrace.jp/owpc/pc/race/odds3t"

    def get_trifecta_odds(self, venue_code: str, race_date: str, race_number: int) -> dict:
        """
        3連単オッズを取得

        Args:
            venue_code: 競艇場コード（2桁の文字列、例: '01'）
            race_date: レース日付（YYYYMMDD形式）
            race_number: レース番号

        Returns:
            {'1-2-3': 12.5, '1-2-4': 25.3, ...} or None
        """
        url = f"{self.base_url}?rno={race_number}&jcd={venue_code.zfill(2)}&hd={race_date.replace('-', '')}"
        print(f"[INFO] アクセス中: {url}")

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080},
                    locale='ja-JP'
                )
                page = context.new_page()

                # ページ読み込み（domcontentloadedで十分）
                page.goto(url, timeout=self.timeout, wait_until='domcontentloaded')

                # JavaScriptの実行を待つ
                page.wait_for_timeout(5000)

                # ページタイトルを確認
                title = page.title()
                print(f"[INFO] ページタイトル: {title}")

                # HTMLを取得
                html_content = page.content()
                print(f"[INFO] HTML長さ: {len(html_content)}")

                # オッズデータを解析
                odds_data = self._parse_trifecta_odds(html_content)

                browser.close()

                if odds_data:
                    print(f"[OK] 3連単オッズ取得成功: {len(odds_data)}通り")
                else:
                    print("[WARNING] オッズデータが見つかりませんでした")

                return odds_data

        except PlaywrightTimeout:
            print("[ERROR] ページ読み込みタイムアウト")
            return None
        except Exception as e:
            print(f"[ERROR] オッズ取得エラー: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _parse_trifecta_odds(self, html: str) -> dict:
        """
        HTMLから3連単オッズを解析

        Args:
            html: ページのHTMLソース

        Returns:
            オッズ辞書 or None
        """
        from bs4 import BeautifulSoup

        odds_data = {}
        soup = BeautifulSoup(html, 'html.parser')

        try:
            # 競艇公式サイトの3連単オッズテーブル構造:
            # - 各列が1着（1号艇〜6号艇）
            # - 行1,5,9,13,17 (18セル): [2着, 3着, オッズ] × 6 - 新しい2着の開始
            # - 行2-4,6-8,... (12セル): [3着, オッズ] × 6 - 同じ2着の続き
            # - 4行で1つの2着が完了（1行目 + 3行の残り3着）

            tables = soup.find_all('table')
            print(f"[DEBUG] テーブル数: {len(tables)}")

            # 3連単オッズテーブルを探す（20行以上あるテーブル）
            for table_idx, table in enumerate(tables):
                rows = table.find_all('tr')
                if len(rows) < 20:
                    continue

                print(f"[DEBUG] 3連単テーブル候補: テーブル{table_idx} ({len(rows)}行)")

                # 各1着に対する現在の2着を管理
                current_second = {}

                for row_idx, row in enumerate(rows[1:], 1):
                    cells = row.find_all('td')
                    cell_texts = [c.get_text(strip=True) for c in cells]

                    if len(cell_texts) < 12:
                        continue

                    # 18セルの行 = 新しい2着の開始
                    if len(cell_texts) >= 18:
                        for first in range(1, 7):
                            offset = (first - 1) * 3
                            if offset + 2 >= len(cell_texts):
                                break

                            second_text = cell_texts[offset]
                            third_text = cell_texts[offset + 1]
                            odds_text = cell_texts[offset + 2]

                            if second_text.isdigit() and third_text.isdigit():
                                second = int(second_text)
                                third = int(third_text)
                                current_second[first] = second

                                if len(set([first, second, third])) == 3:
                                    try:
                                        odds_val = float(odds_text.replace(',', ''))
                                        if 1.0 <= odds_val <= 99999.0:
                                            odds_data[f"{first}-{second}-{third}"] = odds_val
                                    except ValueError:
                                        pass
                    else:
                        # 12セルの行 = 同じ2着の残りの3着
                        for first in range(1, 7):
                            offset = (first - 1) * 2
                            if offset + 1 >= len(cell_texts):
                                break

                            third_text = cell_texts[offset]
                            odds_text = cell_texts[offset + 1]

                            if third_text.isdigit():
                                third = int(third_text)
                                second = current_second.get(first, 0)

                                if second > 0 and len(set([first, second, third])) == 3:
                                    try:
                                        odds_val = float(odds_text.replace(',', ''))
                                        if 1.0 <= odds_val <= 99999.0:
                                            odds_data[f"{first}-{second}-{third}"] = odds_val
                                    except ValueError:
                                        pass

                # データが取得できたら終了
                if len(odds_data) >= 110:
                    break

            print(f"[DEBUG] テーブルから{len(odds_data)}通り取得")

            # 不足分の確認
            if len(odds_data) < 120:
                all_combos = set()
                for f in range(1, 7):
                    for s in range(1, 7):
                        if s != f:
                            for t in range(1, 7):
                                if t != f and t != s:
                                    all_combos.add(f"{f}-{s}-{t}")
                missing = all_combos - set(odds_data.keys())
                if missing:
                    print(f"[DEBUG] 不足: {len(missing)}通り")

        except Exception as e:
            print(f"[ERROR] HTMLパース失敗: {e}")
            import traceback
            traceback.print_exc()

        return odds_data if odds_data else None

    def get_multiple_races(self, venue_code: str, race_date: str, race_numbers: list) -> dict:
        """
        複数レースのオッズを一括取得

        Args:
            venue_code: 競艇場コード
            race_date: レース日付
            race_numbers: レース番号のリスト

        Returns:
            {race_number: {'1-2-3': odds, ...}, ...}
        """
        results = {}
        for race_num in race_numbers:
            odds = self.get_trifecta_odds(venue_code, race_date, race_num)
            results[race_num] = odds
            time.sleep(1)  # サーバー負荷軽減
        return results


def test_scraper():
    """スクレイパーのテスト"""
    print("=" * 60)
    print("Playwright オッズスクレイパー テスト")
    print("=" * 60)

    scraper = PlaywrightOddsScraper(headless=True)

    # 今日の日付を使用
    from datetime import datetime
    today = datetime.now().strftime('%Y%m%d')

    # 戸田競艇場でテスト
    print(f"\n--- 戸田競艇場 1R ({today}) ---")
    odds = scraper.get_trifecta_odds('02', today, 1)

    if odds:
        # 人気上位10通りを表示
        sorted_odds = sorted(odds.items(), key=lambda x: x[1])[:10]
        print("\n人気上位10通り:")
        for combo, o in sorted_odds:
            print(f"  {combo}: {o:.1f}倍")
        print(f"\n合計: {len(odds)}通り")
    else:
        print("データ取得失敗")

    print("\n" + "=" * 60)
    print("テスト完了")
    print("=" * 60)


if __name__ == "__main__":
    test_scraper()
