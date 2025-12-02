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
                'exhibition_times': {1: 6.79, 2: 6.75, ...},     # 枠番 -> 展示タイム
                'tilt_angles': {1: 0.0, 2: -0.5, ...},           # 枠番 -> チルト角度
                'parts_replacements': {1: 'R', 2: '', ...},      # 枠番 -> 部品交換情報
                'adjusted_weights': {1: 0.0, 2: 0.5, ...},       # 枠番 -> 調整重量 (NEW)
                'start_timings': {1: 0.09, 2: 0.15, ...},        # 枠番 -> ST (NEW)
                'exhibition_courses': {1: 1, 2: 2, ...},         # 枠番 -> 展示進入コース (NEW)
                'is_published': True/False                        # データ公開状態 (NEW)
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

            # データ公開状態を確認
            is_published = self._check_data_published(soup)

            # 展示タイムを取得
            exhibition_times = self._extract_exhibition_times(soup)

            # チルト角度、部品交換、調整重量、前走成績を取得
            tilt_angles, parts_replacements, adjusted_weights, previous_race = self._extract_table_data(soup)

            # スタート展示データ（ST、進入コース）を取得
            start_timings, exhibition_courses = self._extract_start_exhibition(soup)

            # 気象データを取得
            weather_data = self._extract_weather_data(soup)

            return {
                'exhibition_times': exhibition_times,
                'tilt_angles': tilt_angles,
                'parts_replacements': parts_replacements,
                'adjusted_weights': adjusted_weights,
                'start_timings': start_timings,
                'exhibition_courses': exhibition_courses,
                'is_published': is_published,
                'weather': weather_data,  # NEW: 気象データ
                'previous_race': previous_race  # NEW: 前走成績
            }

        except Exception as e:
            print(f"事前情報取得エラー ({venue_code}, {date_str}, R{race_number}): {e}")
            return None

    def _check_data_published(self, soup):
        """
        データが公開されているかチェック

        Args:
            soup: BeautifulSoupオブジェクト

        Returns:
            bool: 公開されていればTrue、未公開ならFalse
        """
        # 未公開の場合、エラーメッセージや特定のクラスが表示される
        error_msg = soup.find('p', class_='is-fs14')
        if error_msg and '情報はありません' in error_msg.get_text():
            return False

        # スタート展示テーブルがあるか確認
        tables = soup.find_all('table')
        if len(tables) < 3:
            return False

        # テーブル3（スタート展示）にデータがあるか
        table3 = tables[2]
        tbody = table3.find('tbody')
        if not tbody or not tbody.find('td'):
            return False

        return True

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
        テーブルからチルト角度、部品交換、調整重量、前走成績を抽出

        Args:
            soup: BeautifulSoupオブジェクト

        Returns:
            tuple: (tilt_angles dict, parts_replacements dict, adjusted_weights dict, previous_race dict)
        """
        tilt_angles = {}
        parts_replacements = {}
        adjusted_weights = {}
        previous_race = {}  # {pit_number: {'course': 4, 'st': 5.17, 'rank': 5}}

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

                        # 調整重量を探す（Row 0, Col 9に格納されている）
                        # ※注意: 前走成績がある場合、Row 0のCol 9に調整重量が入る
                        if len(cols) > 9:
                            weight_col = cols[9]
                            weight_text = weight_col.get_text(strip=True)

                            # 空欄の場合は0.0kg
                            if not weight_text:
                                adjusted_weights[pit_number] = 0.0
                            else:
                                try:
                                    weight_value = float(weight_text.replace('kg', ''))
                                    # 妥当な範囲チェック（0〜5kg程度）
                                    if 0.0 <= weight_value <= 5.0:
                                        adjusted_weights[pit_number] = weight_value
                                except ValueError:
                                    # 数値変換できない場合は0.0とする
                                    adjusted_weights[pit_number] = 0.0
                        else:
                            # 列数が足りない場合は0.0kg
                            adjusted_weights[pit_number] = 0.0

                        # 前走成績を取得（Row 1, Row 2, Row 3から）
                        prev_race_data = {}

                        # Row 1: 進入コース
                        if len(rows) > 1:
                            row1 = rows[1]
                            row1_cols = row1.find_all(['td', 'th'], recursive=False)
                            if len(row1_cols) > 1:
                                course_text = row1_cols[1].get_text(strip=True)
                                try:
                                    prev_race_data['course'] = int(course_text)
                                except ValueError:
                                    pass

                        # Row 2: ST
                        if len(rows) > 2:
                            row2 = rows[2]
                            row2_cols = row2.find_all(['td', 'th'], recursive=False)
                            if len(row2_cols) > 2:
                                st_text = row2_cols[2].get_text(strip=True)
                                try:
                                    # ".17" → "5.17" (pit_numberを付加)
                                    if st_text.startswith('.'):
                                        full_st = f"{pit_number}{st_text}"
                                        prev_race_data['st'] = float(full_st)
                                    else:
                                        prev_race_data['st'] = float(st_text)
                                except ValueError:
                                    pass

                        # Row 3: 艇順（着順）
                        if len(rows) > 3:
                            row3 = rows[3]
                            row3_cols = row3.find_all(['td', 'th'], recursive=False)
                            if len(row3_cols) > 1:
                                rank_text = row3_cols[1].get_text(strip=True)
                                try:
                                    prev_race_data['rank'] = int(rank_text)
                                except ValueError:
                                    pass

                        # 前走成績データがあれば記録
                        if prev_race_data:
                            previous_race[pit_number] = prev_race_data

                    break  # 該当テーブルを見つけたら終了

        except Exception as e:
            print(f"テーブルデータ抽出エラー: {e}")
            import traceback
            traceback.print_exc()

        return tilt_angles, parts_replacements, adjusted_weights, previous_race

    def _extract_start_exhibition(self, soup):
        """
        スタート展示データ（ST、進入コース）を抽出

        Args:
            soup: BeautifulSoupオブジェクト

        Returns:
            tuple: (start_timings dict, exhibition_courses dict)
        """
        start_timings = {}
        exhibition_courses = {}

        try:
            # テーブル3がスタート展示テーブル
            tables = soup.find_all('table')
            if len(tables) < 3:
                return start_timings, exhibition_courses

            table3 = tables[2]
            tbody = table3.find('tbody')
            if not tbody:
                return start_timings, exhibition_courses

            # 各TRが1コース、2コース...の順に並んでいる
            # TR内のTDから艇番とSTを取得
            rows = tbody.find_all('tr')

            for course, tr in enumerate(rows, 1):
                # TD要素を取得
                td = tr.find('td')
                if not td:
                    continue

                # 艇番を取得
                number_span = td.find('span', class_='table1_boatImage1Number')
                if not number_span:
                    continue

                pit_number_text = number_span.get_text(strip=True)
                try:
                    pit_number = int(pit_number_text)
                except ValueError:
                    continue

                # このTRの順番 = コース番号
                exhibition_courses[pit_number] = course

                # STタイムを取得
                time_span = td.find('span', class_='table1_boatImage1Time')
                if time_span:
                    st_text = time_span.get_text(strip=True)
                    # ".09"のような形式なので、艇番と結合して"1.09"にする
                    try:
                        # "F"マーク（フライング）の処理
                        if 'F' in st_text:
                            # "F.03" のような形式 → フライングなので負の値で記録
                            # "F.03" → "-0.03"
                            num_part = st_text.replace('F', '').replace('.', '')
                            if num_part:
                                st_value = -float(f"0.{num_part.zfill(2)}")
                                start_timings[pit_number] = st_value
                        elif 'L' in st_text:
                            # "L"マーク（出遅れ）の処理
                            # 通常のSTとして処理（正の値）
                            num_part = st_text.replace('L', '')
                            if num_part:
                                full_st = f"{pit_number}{num_part}"
                                st_value = float(full_st)
                                if 0.0 <= st_value <= 9.99:
                                    start_timings[pit_number] = st_value
                        else:
                            # 正常なST: ".09" → "1.09"
                            full_st = f"{pit_number}{st_text}"
                            st_value = float(full_st)
                            # STは通常0.00〜2.00の範囲
                            if 0.0 <= st_value <= 9.99:
                                start_timings[pit_number] = st_value
                    except ValueError:
                        pass

        except Exception as e:
            print(f"スタート展示データ抽出エラー: {e}")
            import traceback
            traceback.print_exc()

        return start_timings, exhibition_courses

    def _extract_weather_data(self, soup):
        """
        気象データを抽出

        Args:
            soup: BeautifulSoupオブジェクト

        Returns:
            dict: {
                'temperature': 13.0,      # 気温（℃）
                'water_temp': 13.0,       # 水温（℃）
                'wind_speed': 1,          # 風速（m）
                'wave_height': 1,         # 波高（cm）
                'weather_code': 1,        # 天候コード（1=晴, 2=曇, 3=雨など）
                'wind_dir_code': 1        # 風向コード
            }
        """
        weather_data = {
            'temperature': None,
            'water_temp': None,
            'wind_speed': None,
            'wave_height': None,
            'weather_code': None,
            'wind_dir_code': None
        }

        try:
            # 水面気象情報セクションを探す
            weather_section = soup.find('div', class_='weather1')
            if not weather_section:
                return weather_data

            # 全ての数値データを取得
            data_elements = weather_section.find_all('span', class_='weather1_bodyUnitLabelData')

            for elem in data_elements:
                title_elem = elem.find_previous_sibling('span', class_='weather1_bodyUnitLabelTitle')
                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)
                value_text = elem.get_text(strip=True)

                try:
                    # 気温
                    if '気温' in title:
                        weather_data['temperature'] = float(value_text.replace('℃', '').replace('度', ''))
                    # 水温
                    elif '水温' in title:
                        weather_data['water_temp'] = float(value_text.replace('℃', '').replace('度', ''))
                    # 風速
                    elif '風速' in title:
                        weather_data['wind_speed'] = int(value_text.replace('m', '').replace('メートル', ''))
                    # 波高
                    elif '波高' in title:
                        weather_data['wave_height'] = int(value_text.replace('cm', '').replace('センチ', ''))
                except (ValueError, AttributeError):
                    pass

            # 天候コードを取得（アイコンクラスから）
            weather_icon = weather_section.find('p', class_=lambda x: x and 'is-weather' in x)
            if weather_icon:
                classes = weather_icon.get('class', [])
                for cls in classes:
                    if cls.startswith('is-weather') and cls != 'is-weather':
                        try:
                            weather_data['weather_code'] = int(cls.replace('is-weather', ''))
                        except ValueError:
                            pass

            # 風向コードを取得（アイコンクラスから）
            wind_icon = weather_section.find('p', class_=lambda x: x and 'is-wind' in x and 'is-windDirection' not in str(x))
            if wind_icon:
                classes = wind_icon.get('class', [])
                for cls in classes:
                    if cls.startswith('is-wind') and cls != 'is-wind' and not cls.startswith('is-windDirection'):
                        try:
                            weather_data['wind_dir_code'] = int(cls.replace('is-wind', ''))
                        except ValueError:
                            pass

        except Exception as e:
            print(f"気象データ抽出エラー: {e}")
            import traceback
            traceback.print_exc()

        return weather_data

    def to_ui_format(self, beforeinfo_data):
        """
        UIコンポーネント用のデータ形式に変換

        Args:
            beforeinfo_data: get_race_beforeinfo() の戻り値

        Returns:
            dict: UI用フォーマット {
                'racers': [{
                    'pit_number': int,
                    'exhibition_time': float,
                    'start_timing': float,
                    'tilt': float,
                    'parts_replacement': str,
                    'adjusted_weight': float,
                    'exhibition_course': int,
                    'prev_race_course': int,
                    'prev_race_st': float,
                    'prev_race_rank': int
                }, ...],
                'weather': {
                    'temperature': float,
                    'water_temp': float,
                    'wind_speed': int,
                    'wave_height': int,
                    'weather_code': int,
                    'wind_dir_code': int
                }
            }
        """
        if not beforeinfo_data or not beforeinfo_data.get('is_published'):
            return None

        # 選手データを統合
        racers = []
        for pit in range(1, 7):
            racer_data = {'pit_number': pit}

            # 展示タイム
            if pit in beforeinfo_data.get('exhibition_times', {}):
                racer_data['exhibition_time'] = beforeinfo_data['exhibition_times'][pit]

            # ST
            if pit in beforeinfo_data.get('start_timings', {}):
                racer_data['start_timing'] = beforeinfo_data['start_timings'][pit]

            # チルト
            if pit in beforeinfo_data.get('tilt_angles', {}):
                racer_data['tilt'] = beforeinfo_data['tilt_angles'][pit]

            # 部品交換
            if pit in beforeinfo_data.get('parts_replacements', {}):
                racer_data['parts_replacement'] = beforeinfo_data['parts_replacements'][pit]

            # 調整重量
            if pit in beforeinfo_data.get('adjusted_weights', {}):
                racer_data['adjusted_weight'] = beforeinfo_data['adjusted_weights'][pit]

            # 展示進入コース
            if pit in beforeinfo_data.get('exhibition_courses', {}):
                racer_data['exhibition_course'] = beforeinfo_data['exhibition_courses'][pit]

            # 前走データ
            if pit in beforeinfo_data.get('previous_race', {}):
                prev = beforeinfo_data['previous_race'][pit]
                if 'course' in prev:
                    racer_data['prev_race_course'] = prev['course']
                if 'st' in prev:
                    racer_data['prev_race_st'] = prev['st']
                if 'rank' in prev:
                    racer_data['prev_race_rank'] = prev['rank']

            racers.append(racer_data)

        # 気象データ
        weather = beforeinfo_data.get('weather', {})

        return {
            'racers': racers,
            'weather': weather
        }

    def save_to_db(self, race_id: int, beforeinfo_data: dict, db_path: str = None):
        """
        直前情報をDBに保存

        Args:
            race_id: レースID
            beforeinfo_data: get_race_beforeinfo()の戻り値
            db_path: データベースパス（Noneの場合はデフォルトパス使用）

        Returns:
            bool: 保存成功したかどうか
        """
        if not beforeinfo_data or not beforeinfo_data.get('is_published'):
            return False

        import sqlite3
        import os

        if db_path is None:
            # デフォルトパスを使用
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
            db_path = os.path.join(project_root, 'data/boatrace.db')

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # race_detailsテーブルに選手ごとのデータを保存
            for pit in range(1, 7):
                ex_time = beforeinfo_data.get('exhibition_times', {}).get(pit)
                tilt = beforeinfo_data.get('tilt_angles', {}).get(pit)
                parts = beforeinfo_data.get('parts_replacements', {}).get(pit)
                adj_weight = beforeinfo_data.get('adjusted_weights', {}).get(pit)
                ex_course = beforeinfo_data.get('exhibition_courses', {}).get(pit)
                st = beforeinfo_data.get('start_timings', {}).get(pit)

                # 前走成績
                prev_race = beforeinfo_data.get('previous_race', {}).get(pit, {})
                prev_course = prev_race.get('course')
                prev_st = prev_race.get('st')
                prev_rank = prev_race.get('rank')

                # データが1つでもあればUPSERT
                if any([ex_time, tilt, parts, adj_weight, ex_course, st, prev_course, prev_st, prev_rank]):
                    cursor.execute("""
                        SELECT id FROM race_details WHERE race_id = ? AND pit_number = ?
                    """, (race_id, pit))
                    existing = cursor.fetchone()

                    if existing:
                        # 既存レコードを更新（NULLでない値のみ上書き）
                        cursor.execute("""
                            UPDATE race_details
                            SET exhibition_time = COALESCE(?, exhibition_time),
                                tilt_angle = COALESCE(?, tilt_angle),
                                parts_replacement = COALESCE(?, parts_replacement),
                                adjusted_weight = COALESCE(?, adjusted_weight),
                                exhibition_course = COALESCE(?, exhibition_course),
                                st_time = COALESCE(?, st_time),
                                prev_race_course = COALESCE(?, prev_race_course),
                                prev_race_st = COALESCE(?, prev_race_st),
                                prev_race_rank = COALESCE(?, prev_race_rank)
                            WHERE race_id = ? AND pit_number = ?
                        """, (ex_time, tilt, parts, adj_weight, ex_course, st,
                              prev_course, prev_st, prev_rank, race_id, pit))
                    else:
                        # 新規挿入
                        cursor.execute("""
                            INSERT INTO race_details (
                                race_id, pit_number, exhibition_time, tilt_angle,
                                parts_replacement, adjusted_weight, exhibition_course,
                                st_time, prev_race_course, prev_race_st, prev_race_rank
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (race_id, pit, ex_time, tilt, parts, adj_weight,
                              ex_course, st, prev_course, prev_st, prev_rank))

            # race_conditionsテーブルに気象データを保存
            weather = beforeinfo_data.get('weather', {})
            if weather:
                temp = weather.get('temperature')
                water_temp = weather.get('water_temp')
                wind_speed = weather.get('wind_speed')
                wave_height = weather.get('wave_height')
                weather_code = weather.get('weather_code')
                wind_dir_code = weather.get('wind_dir_code')

                # 天候コード・風向コードをテキストに変換
                weather_text = self._weather_code_to_text(weather_code) if weather_code else None
                wind_dir_text = self._wind_dir_code_to_text(wind_dir_code) if wind_dir_code else None

                # データがあればUPSERT
                if any([temp, water_temp, wind_speed, wave_height, weather_text, wind_dir_text]):
                    cursor.execute("""
                        SELECT id FROM race_conditions WHERE race_id = ?
                    """, (race_id,))
                    existing = cursor.fetchone()

                    if existing:
                        # 既存レコードを更新
                        cursor.execute("""
                            UPDATE race_conditions
                            SET temperature = COALESCE(?, temperature),
                                water_temperature = COALESCE(?, water_temperature),
                                wind_speed = COALESCE(?, wind_speed),
                                wave_height = COALESCE(?, wave_height),
                                weather = COALESCE(?, weather),
                                wind_direction = COALESCE(?, wind_direction)
                            WHERE race_id = ?
                        """, (temp, water_temp, wind_speed, wave_height,
                              weather_text, wind_dir_text, race_id))
                    else:
                        # 新規挿入
                        cursor.execute("""
                            INSERT INTO race_conditions (
                                race_id, temperature, water_temperature,
                                wind_speed, wave_height, weather, wind_direction
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (race_id, temp, water_temp, wind_speed, wave_height,
                              weather_text, wind_dir_text))

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            print(f"DB保存エラー (race_id={race_id}): {e}")
            import traceback
            traceback.print_exc()
            return False

    def _weather_code_to_text(self, code: int) -> str:
        """天候コードをテキストに変換"""
        weather_map = {
            1: '晴',
            2: '曇',
            3: '雨',
            4: '雪',
            5: '霧',
            6: '台風'
        }
        return weather_map.get(code, '不明')

    def _wind_dir_code_to_text(self, code: int) -> str:
        """風向コードをテキストに変換"""
        wind_dir_map = {
            1: '無風',
            2: '北',
            3: '北北東',
            4: '北東',
            5: '東北東',
            6: '東',
            7: '東南東',
            8: '南東',
            9: '南南東',
            10: '南',
            11: '南南西',
            12: '南西',
            13: '西南西',
            14: '西',
            15: '西北西',
            16: '北西',
            17: '北北西'
        }
        return wind_dir_map.get(code, '不明')

    def close(self):
        """セッションを閉じる"""
        self.session.close()


if __name__ == "__main__":
    # テスト実行
    scraper = BeforeInfoScraper()

    print("="*70)
    print("事前情報スクレイパーテスト")
    print("="*70)

    # テスト1: 公開レース（芦屋 12/2 5R）
    print("\n【テスト1: 公開レース】")
    print("URL: https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno=5&jcd=21&hd=20251202")
    result = scraper.get_race_beforeinfo("21", "20251202", 5)

    if result:
        print(f"\nデータ公開状態: {'公開' if result['is_published'] else '未公開'}")

        print("\n【展示タイム】")
        for pit, time_val in sorted(result['exhibition_times'].items()):
            print(f"  {pit}号艇: {time_val}秒")

        print("\n【チルト角度】")
        for pit, tilt in sorted(result['tilt_angles'].items()):
            print(f"  {pit}号艇: {tilt}")

        print("\n【部品交換】")
        for pit, parts in sorted(result['parts_replacements'].items()):
            print(f"  {pit}号艇: {parts}")

        print("\n【調整重量】")
        if result['adjusted_weights']:
            for pit, weight in sorted(result['adjusted_weights'].items()):
                print(f"  {pit}号艇: {weight}kg")
        else:
            print("  データなし")

        print("\n【スタートタイミング（ST）】")
        for pit, st in sorted(result['start_timings'].items()):
            print(f"  {pit}号艇: {st}")

        print("\n【展示進入コース】")
        for pit, course in sorted(result['exhibition_courses'].items()):
            print(f"  {pit}号艇 → {course}コース")

    # テスト2: 未公開レース（芦屋 12/2 7R）
    print("\n" + "="*70)
    print("【テスト2: 未公開レース】")
    print("URL: https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno=7&jcd=21&hd=20251202")
    result2 = scraper.get_race_beforeinfo("21", "20251202", 7)

    if result2:
        print(f"\nデータ公開状態: {'公開' if result2['is_published'] else '未公開'}")
        if not result2['is_published']:
            print("→ まだ直前情報が公開されていません")

    scraper.close()
