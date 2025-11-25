"""
レース結果スクレイピング - 改善版
STタイムのF(フライング)とL(出遅れ)に対応
"""

from .result_scraper import ResultScraper as BaseResultScraper
from config.settings import BOATRACE_OFFICIAL_URL


class ImprovedResultScraper(BaseResultScraper):
    """改善版レース結果スクレイパー - F/L対応"""

    def get_race_result_complete(self, venue_code, race_date, race_number):
        """
        指定レースの完全な結果を取得 (F/L対応版)

        STタイムで以下の特殊ケースに対応:
        - F: フライング (-0.01として保存)
        - L: 出遅れ (-0.02として保存)
        - .F: フライング (0.01秒未満)

        Args:
            venue_code: 競艇場コード
            race_date: レース日付（YYYYMMDD形式）
            race_number: レース番号（1-12）

        Returns:
            {
                'venue_code': str,
                'race_date': str,
                'race_number': int,
                'results': [着順データ],
                'trifecta_odds': float,
                'is_invalid': 返還フラグ,
                'weather_data': 天気情報,
                'actual_courses': {枠番: コース番号},
                'st_times': {枠番: STタイム (F=-0.01, L=-0.02)},
                'st_status': {枠番: 'normal'|'flying'|'late'}, # 追加
                'payouts': {舟券種別: [払戻金データ]},
                'kimarite': '決まり手'
            } or None
        """
        url = f"{BOATRACE_OFFICIAL_URL}/raceresult"
        params = {
            "rno": race_number,
            "jcd": venue_code,
            "hd": race_date
        }

        soup = self.fetch_page(url, params)
        if not soup:
            return None

        # ページタイトルでレース存在確認
        title = soup.find('title')
        if title and 'エラー' in title.text:
            print(f"レース不存在: {venue_code} {race_date} {race_number}R")
            return None

        result = {
            "venue_code": venue_code,
            "race_date": race_date,
            "race_number": race_number,
            "results": [],
            "trifecta_odds": None,
            "is_invalid": False,
            "weather_data": None,
            "actual_courses": {},
            "st_times": {},
            "st_status": {},  # 新規追加: STタイムのステータス
            "payouts": {},
            "kimarite": None
        }

        try:
            # 1. 天気情報を取得
            weather_data = self._extract_weather_data(soup)
            if weather_data:
                result["weather_data"] = weather_data

            # 2. 着順情報を解析
            result_table = soup.find('table', class_=lambda x: x and 'is-w495' in str(x))
            if result_table:
                tbodies = result_table.find_all('tbody')

                for tbody in tbodies:
                    row = tbody.find('tr')
                    if not row:
                        continue

                    tds = row.find_all('td')
                    if len(tds) < 2:
                        continue

                    # 着順
                    rank_td = tds[0]
                    rank = self._parse_japanese_rank(rank_td.text.strip())

                    # 艇番
                    pit_td = tds[1]
                    pit_number = self._extract_pit_number(pit_td)

                    if pit_number and rank:
                        result["results"].append({
                            'pit_number': pit_number,
                            'rank': rank
                        })

            # 3. 三連単オッズを取得
            payoff_table = soup.find('table', class_=lambda x: x and 'is-w243' in str(x))
            if payoff_table:
                tbody = payoff_table.find('tbody')
                if tbody:
                    first_row = tbody.find('tr')
                    if first_row:
                        tds = first_row.find_all('td')
                        for td in tds:
                            odds_value = self._parse_odds(td.text)
                            if odds_value:
                                result["trifecta_odds"] = odds_value
                                break

            # 4. 返還・不成立の判定
            invalid_indicators = soup.find_all(string=lambda x: x and ('返還レース' in str(x) or '不成立' in str(x) or 'レース不成立' in str(x)))
            if invalid_indicators:
                result["is_invalid"] = True

            # 5. 実際の進入コースを取得
            tables = soup.find_all('table')
            for table in tables:
                table_text = table.get_text()

                if 'スタート情報' in table_text:
                    tbody = table.find('tbody')

                    if tbody:
                        rows = tbody.find_all('tr', recursive=False)

                        if len(rows) == 6:
                            for course, row in enumerate(rows, start=1):
                                number_elem = row.find(class_='table1_boatImage1Number')

                                if number_elem:
                                    pit_text = number_elem.get_text(strip=True)
                                    try:
                                        pit_number = int(pit_text)
                                        if 1 <= pit_number <= 6:
                                            result["actual_courses"][pit_number] = course
                                    except ValueError:
                                        pass

                            if len(result["actual_courses"]) == 6:
                                break

            # 6. STタイムを取得 (改善版: F/L対応)
            time_elements = soup.find_all(class_='table1_boatImage1TimeInner')

            for time_elem in time_elements:
                time_text = time_elem.get_text(strip=True)

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

                # STタイムのパース (F/L対応)
                st_time, status = self._parse_st_time(time_text)

                if st_time is not None:
                    result["st_times"][pit_number] = st_time
                    result["st_status"][pit_number] = status

            # 7. 払戻金と決まり手を取得
            for table in tables:
                thead = table.find('thead')
                if not thead:
                    continue

                headers = [th.get_text(strip=True) for th in thead.find_all('th')]

                # 払戻金テーブル
                if '勝式' in headers and '払戻金' in headers:
                    tbodies = table.find_all('tbody')

                    for tbody in tbodies:
                        rows = tbody.find_all('tr')
                        if not rows:
                            continue

                        first_row = rows[0]
                        tds = first_row.find_all('td')

                        if len(tds) < 2:
                            continue

                        # 舟券種別取得
                        bet_type = None
                        for td in tds:
                            if td.get('rowspan'):
                                bet_type = td.get_text(strip=True)
                                break

                        if not bet_type:
                            continue

                        bet_type_map = {
                            '3連単': 'trifecta',
                            '3連複': 'trio',
                            '2連単': 'exacta',
                            '2連複': 'quinella',
                            '拡連複': 'quinella_place',
                            '単勝': 'win',
                            '複勝': 'place'
                        }

                        bet_key = bet_type_map.get(bet_type)
                        if not bet_key:
                            continue

                        payouts_list = []

                        for row in rows:
                            tds = row.find_all('td')

                            combination = None
                            payout = None

                            for i, td in enumerate(tds):
                                if td.get('rowspan'):
                                    continue

                                cell_text = td.get_text(strip=True)

                                if '-' in cell_text or '=' in cell_text:
                                    combination = cell_text
                                elif '円' in cell_text or cell_text.replace(',', '').replace('.', '').isdigit():
                                    payout_value = self._parse_payout(cell_text)
                                    if payout_value:
                                        payout = payout_value

                            if combination and payout:
                                payouts_list.append({
                                    'combination': combination,
                                    'payout': payout
                                })

                        if payouts_list:
                            result["payouts"][bet_key] = payouts_list

                # 決まり手テーブル
                if '決まり手' in headers:
                    tbody = table.find('tbody')
                    if tbody:
                        kimarite_td = tbody.find('td')
                        if kimarite_td:
                            result["kimarite"] = kimarite_td.get_text(strip=True)

        except Exception as e:
            # print(f"結果取得エラー: {venue_code} {race_date} {race_number}R - {e}")
            # import traceback
            # traceback.print_exc()
            return None

        return result

    def _parse_st_time(self, time_text):
        """
        STタイムをパース (F/L対応)

        Args:
            time_text: STタイムのテキスト

        Returns:
            (st_time: float|None, status: str)
            - normal: 正常なSTタイム
            - flying: フライング (F)
            - late: 出遅れ (L)
        """
        time_text = time_text.strip()

        # フライングのチェック
        if time_text == 'F' or time_text.upper() == 'F':
            return (-0.01, 'flying')

        # .Fのパターン (0.01秒未満のフライング)
        if '.F' in time_text.upper():
            return (-0.01, 'flying')

        # 出遅れのチェック
        if time_text == 'L' or time_text.upper() == 'L':
            return (-0.02, 'late')

        # .Lのパターン
        if '.L' in time_text.upper():
            return (-0.02, 'late')

        # 数値のパース
        if time_text.startswith('.'):
            time_text = '0' + time_text

        try:
            st_time = float(time_text)
            return (st_time, 'normal')
        except ValueError:
            # パースできない場合はNoneを返す
            # print(f"STタイムパース失敗: '{time_text}'")
            return (None, 'unknown')
