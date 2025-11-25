"""
レース結果スクレイピング - 改善版 V4
STタイム取得の完全修正版（スタート情報テーブルから正確に取得）
"""

import re
from .result_scraper import ResultScraper


class ImprovedResultScraperV4(ResultScraper):
    """
    改善版レース結果スクレイパー V4

    変更点:
    - スタート情報テーブル（is-w495の2番目）から正確にST時間を取得
    - 決まり手などの余分なテキストを完全に除去
    - F/L（フライング・出遅れ）の対応
    """

    def get_race_result_complete(self, venue_code, race_date, race_number):
        """
        完全な結果を取得（STタイム抽出の完全修正版）
        """
        from config.settings import BOATRACE_OFFICIAL_URL

        url = f"{BOATRACE_OFFICIAL_URL}/raceresult"
        params = {
            "rno": race_number,
            "jcd": venue_code,
            "hd": race_date
        }

        soup = self.fetch_page(url, params)
        if not soup:
            return None

        # 親クラスのメソッドで基本データを取得
        result = super().get_race_result_complete(venue_code, race_date, race_number)

        if not result:
            return None

        # STタイムを正しいテーブルから取得
        st_times = {}
        st_status = {}

        # is-w495 クラスのテーブルを全て取得
        tables = soup.find_all('table', class_='is-w495')

        # 2番目のテーブルがスタート情報テーブル
        if len(tables) >= 2:
            start_table = tables[1]
            rows = start_table.find_all('tr')

            # 最初の行はヘッダーなのでスキップ
            for row in rows[1:]:
                cells = row.find_all(['td', 'th'])
                if len(cells) > 0:
                    # セルのテキストを取得（例: "1 .21" または "4 .11 まくり差し"）
                    cell_text = cells[0].get_text(strip=False)  # strip=False で全テキスト取得

                    # pit番号とST時間をパース
                    pit_number, st_time, status = self._parse_start_info_cell(cell_text)

                    if pit_number is not None and st_time is not None:
                        st_times[pit_number] = st_time
                        st_status[pit_number] = status

        # 結果を更新
        result['st_times'] = st_times
        result['st_status'] = st_status

        return result

    def _parse_start_info_cell(self, cell_text):
        """
        スタート情報セルをパース

        Args:
            cell_text: セルのテキスト（例: "1.21", "4.11 まくり差し", "1.F"）

        Returns:
            (pit_number: int|None, st_time: float|None, status: str)

        Examples:
            "1.21" -> (1, 0.21, 'normal')
            "4.11 まくり差し" -> (4, 0.11, 'normal')
            "1.F" -> (1, -0.01, 'flying')
            "2.L" -> (2, -0.02, 'late')
        """
        # 改行や余分な空白を除去
        cell_text = ' '.join(cell_text.split())

        # pit番号とST時間を抽出するパターン
        # パターン1: "1.21" (pit番号.ST時間)
        # パターン2: "4.11 まくり差し" (pit番号.ST時間 決まり手)
        # パターン3: "1.F" (pit番号.F)
        # パターン4: "2.L" (pit番号.L)

        # まずpit番号を抽出（最初の数字）
        pit_match = re.match(r'^(\d+)', cell_text)
        if not pit_match:
            return (None, None, 'unknown')

        pit_number = int(pit_match.group(1))

        # pit番号の後の空白とドット、そしてその後の部分を抽出
        # パターン: ピット番号 .STタイム[余分なテキスト]
        rest_text = cell_text[len(pit_match.group(1)):].strip()

        # ドットをスキップ
        if rest_text.startswith('.'):
            rest_text = rest_text[1:]
        else:
            return (pit_number, None, 'unknown')

        # フライングのチェック
        if rest_text.strip().upper().startswith('F'):
            return (pit_number, -0.01, 'flying')

        # 出遅れのチェック
        if rest_text.strip().upper().startswith('L'):
            return (pit_number, -0.02, 'late')

        # ST時間を抽出（数値部分のみ）
        # rest_textには既にドットが削除されているので、数字のみを抽出
        # パターン: 数字のみ（例: "21", "11"）
        st_match = re.match(r'^(\d+)', rest_text)

        if st_match:
            num_text = st_match.group(1)

            try:
                # 数値を小数点として解釈（例: "21" -> 0.21）
                st_time = float('0.' + num_text)
                return (pit_number, st_time, 'normal')
            except ValueError:
                pass

        # パースできない場合
        return (pit_number, None, 'unknown')
