"""
レース結果スクレイピング - 改善版 V3
STタイム取得のバグ修正版（決まり手が混入している問題を解決）
"""

import re
from .result_scraper import ResultScraper


class ImprovedResultScraperV3(ResultScraper):
    """
    改善版レース結果スクレイパー V3

    変更点:
    - STタイムに決まり手などの余分なテキストが含まれる問題を修正
    - F/L（フライング・出遅れ）の対応
    - 数値部分のみを正確に抽出
    """

    def get_race_result_complete(self, venue_code, race_date, race_number):
        """
        完全な結果を取得（STタイム抽出の改善版）
        """
        # まず親クラスのメソッドを実行して基本データを取得
        # ただし、STタイムの取得をやり直す必要があるため、
        # ページ取得からやり直す

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

        # STタイムを再取得（改善版のロジックで）
        st_times = {}
        st_status = {}

        time_elements = soup.find_all(class_='table1_boatImage1TimeInner')

        for time_elem in time_elements:
            # 全テキストを取得
            time_text = time_elem.get_text(strip=True)

            # 親のtrからpit番号を取得
            parent_tr = time_elem.find_parent('tr')
            if not parent_tr:
                continue

            number_elem = parent_tr.find(class_='table1_boatImage1Number')
            if not number_elem:
                continue

            pit_text = number_elem.get_text(strip=True)
            try:
                pit_number = int(pit_text)
            except ValueError:
                continue

            # STタイムをパース（改善版）
            st_time, status = self._parse_st_time_improved(time_text)

            if st_time is not None:
                st_times[pit_number] = st_time
                st_status[pit_number] = status

        # 結果を更新
        result['st_times'] = st_times
        result['st_status'] = st_status

        return result

    def _parse_st_time_improved(self, time_text):
        """
        STタイムをパース（改善版）

        Args:
            time_text: STタイムのテキスト（決まり手などが混入している可能性あり）

        Returns:
            (st_time: float|None, status: str)

        Examples:
            ".14" -> (0.14, 'normal')
            ".14まくり差し" -> (0.14, 'normal')  # 余分なテキストを除去
            "F" -> (-0.01, 'flying')
            ".F" -> (-0.01, 'flying')
            "L" -> (-0.02, 'late')
            ".L" -> (-0.02, 'late')
        """
        time_text = time_text.strip()

        # フライングのチェック
        if 'F' in time_text.upper():
            return (-0.01, 'flying')

        # 出遅れのチェック
        if 'L' in time_text.upper():
            return (-0.02, 'late')

        # 数値部分を正規表現で抽出
        # パターン: .数字 または 0.数字 または 数字.数字
        match = re.search(r'(\.?\d+\.?\d*)', time_text)

        if match:
            num_text = match.group(1)

            # .で始まる場合は0を追加
            if num_text.startswith('.'):
                num_text = '0' + num_text

            try:
                st_time = float(num_text)
                return (st_time, 'normal')
            except ValueError:
                pass

        # パースできない場合
        return (None, 'unknown')
