"""
事前情報（beforeinfo）スクレイパー
展示タイム、チルト角度、部品交換情報を取得
"""

import requests
from bs4 import BeautifulSoup
import time
import re


class BeforeInfoScraper:
    """事前情報ページのスクレイパー"""

    def __init__(self, delay=1.0):
        """
        初期化

        Args:
            delay: リクエスト間の待機時間（秒）
        """
        self.base_url = "https://www.boatrace.jp/owpc/pc/race/beforeinfo"
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

    def get_race_beforeinfo(self, venue_code, date_str, race_number):
        """
        レースの事前情報を取得

        Args:
            venue_code: 競艇場コード（例: "01"）
            date_str: 日付文字列（例: "20251004"）
            race_number: レース番号（1-12）

        Returns:
            dict: {
                'exhibition_times': {1: 6.79, 2: 6.75, ...},  # 枠番 -> 展示タイム
                'tilt_angles': {1: 0.0, 2: -0.5, ...},         # 枠番 -> チルト角度
                'parts_replacements': {1: 'R', 2: '', ...}     # 枠番 -> 部品交換情報
            }
            エラー時はNone
        """
        params = {
            "jcd": venue_code,
            "hd": date_str,
            "rno": race_number
        }

        try:
            response = self.session.get(
                self.base_url,
                params=params,
                timeout=15
            )
            response.raise_for_status()
            time.sleep(self.delay)

            soup = BeautifulSoup(response.text, 'html.parser')

            # 展示タイムを取得
            exhibition_times = self._extract_exhibition_times(soup)

            # チルト角度と部品交換を取得
            tilt_angles, parts_replacements = self._extract_table_data(soup)

            return {
                'exhibition_times': exhibition_times,
                'tilt_angles': tilt_angles,
                'parts_replacements': parts_replacements
            }

        except Exception as e:
            print(f"事前情報取得エラー ({venue_code}, {date_str}, R{race_number}): {e}")
            return None

    def _extract_exhibition_times(self, soup):
        """
        展示タイムを抽出

        Args:
            soup: BeautifulSoupオブジェクト

        Returns:
            dict: {枠番: 展示タイム}
        """
        exhibition_times = {}

        try:
            # is-w748 テーブルから展示タイムを取得
            table = soup.find('table', class_='is-w748')
            if not table:
                return exhibition_times

            # 全tbodyを取得（各艇ごとに1つのtbody）
            # ヘッダーは空なので、固定列インデックスを使用
            all_tbodies = table.find_all('tbody')

            for tbody in all_tbodies:
                rows = tbody.find_all('tr', recursive=False)
                if not rows:
                    continue

                # 最初の行からデータを取得
                first_row = rows[0]
                cols = first_row.find_all(['td', 'th'], recursive=False)

                if len(cols) < 5:  # 最低限Col 0-4が必要
                    continue

                # Col 0: 枠番を取得（is-boatColorクラス）
                pit_number = None
                pit_col = cols[0]
                classes = ' '.join(pit_col.get('class', []))
                if 'is-boatColor' in classes:
                    try:
                        pit_number = int(pit_col.get_text(strip=True))
                    except ValueError:
                        continue

                if not pit_number:
                    continue

                # Col 4: 展示タイム（固定位置）
                time_text = cols[4].get_text(strip=True)
                if time_text:
                    try:
                        time_value = float(time_text)
                        # 妥当な範囲チェック（6.0秒〜8.0秒程度）
                        if 5.0 <= time_value <= 10.0:
                            exhibition_times[pit_number] = time_value
                    except ValueError:
                        # 非数値の場合はスキップ
                        pass

        except Exception as e:
            print(f"展示タイム抽出エラー: {e}")

        return exhibition_times

    def _extract_table_data(self, soup):
        """
        テーブルからチルト角度と部品交換を抽出

        Args:
            soup: BeautifulSoupオブジェクト

        Returns:
            tuple: (tilt_angles dict, parts_replacements dict)
        """
        tilt_angles = {}
        parts_replacements = {}

        try:
            # メインテーブルを探す（「チルト」「部品交換」を含むテーブル）
            tables = soup.find_all('table')

            for table in tables:
                thead = table.find('thead')
                if not thead:
                    continue

                # ヘッダー行を取得
                headers = [th.get_text(strip=True) for th in thead.find_all('th')]

                # 「チルト」と「部品交換」の列インデックスを探す
                tilt_idx = None
                parts_idx = None

                for idx, header in enumerate(headers):
                    if 'チルト' in header:
                        tilt_idx = idx
                    elif '部品交換' in header:
                        parts_idx = idx

                # 両方の列が見つかった場合
                if tilt_idx is not None or parts_idx is not None:
                    # ★重要: 各艇のデータが別々のtbodyに格納されている
                    # 全てのtbodyを取得して処理
                    all_tbodies = table.find_all('tbody')

                    for tbody in all_tbodies:
                        rows = tbody.find_all('tr', recursive=False)

                        # 枠番を探す
                        pit_number = None
                        for row in rows:
                            cols = row.find_all(['td', 'th'], recursive=False)

                            if len(cols) == 0:
                                continue

                            # 枠番を取得（is-boatColorクラスを持つセル）
                            for col in cols:
                                classes = ' '.join(col.get('class', []))
                                if 'is-boatColor' in classes:
                                    pit_number_text = col.get_text(strip=True)
                                    try:
                                        pit_number = int(pit_number_text)
                                        break
                                    except ValueError:
                                        pass

                            if pit_number:
                                break

                        if not pit_number:
                            continue

                        # この艇のチルト角度と部品交換を最初の行から取得
                        first_row = rows[0] if rows else None
                        if not first_row:
                            continue

                        cols = first_row.find_all(['td', 'th'], recursive=False)

                        # チルト角度を探す（-0.5 ~ +3.0 の範囲の数値）
                        for col in cols:
                            text = col.get_text(strip=True)
                            if text and re.match(r'^[+-]?\d+\.\d+$', text):
                                try:
                                    value = float(text)
                                    # チルト角度の範囲チェック
                                    if -0.5 <= value <= 3.0:
                                        tilt_angles[pit_number] = value
                                        break
                                except ValueError:
                                    pass

                        # 部品交換を探す（"R", "E", "C" などの1文字または数文字）
                        # 部品交換は「前検」列（インデックス8）にある
                        if len(cols) > 8:
                            parts_col = cols[8]  # インデックス8が部品交換列
                            parts_text = parts_col.get_text(strip=True)
                            # "R"（交換済み）などのマーク（1〜3文字）
                            if parts_text and 1 <= len(parts_text) <= 3:
                                parts_replacements[pit_number] = parts_text

                    break  # 該当テーブルを見つけたら終了

        except Exception as e:
            print(f"テーブルデータ抽出エラー: {e}")
            import traceback
            traceback.print_exc()

        return tilt_angles, parts_replacements

    def close(self):
        """セッションを閉じる"""
        self.session.close()


if __name__ == "__main__":
    # テスト実行
    scraper = BeforeInfoScraper()

    print("="*70)
    print("事前情報スクレイパーテスト")
    print("="*70)

    # 芦屋 10/23 1R（過去のレース）
    result = scraper.get_race_beforeinfo("21", "20251023", 1)

    if result:
        print("\n【展示タイム】")
        for pit, time_val in sorted(result['exhibition_times'].items()):
            print(f"  {pit}号艇: {time_val}秒")

        print("\n【チルト角度】")
        for pit, tilt in sorted(result['tilt_angles'].items()):
            print(f"  {pit}号艇: {tilt}")

        print("\n【部品交換】")
        for pit, parts in sorted(result['parts_replacements'].items()):
            print(f"  {pit}号艇: {parts}")

    scraper.close()
