"""
データベース管理・データ保存機能
スクレイピングしたデータをDBに保存
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from .models import Database
from datetime import datetime
from ..utils.date_utils import to_iso_format

logger = logging.getLogger(__name__)


# データ検証用の定数
REQUIRED_RACE_FIELDS = ['venue_code', 'race_date', 'race_number']
REQUIRED_ENTRY_FIELDS = ['pit_number', 'racer_number', 'racer_name']
REQUIRED_RESULT_FIELDS = ['pit_number', 'rank']


class DataManager:
    """データ管理クラス"""

    def __init__(self, db_path: str = "data/boatrace.db") -> None:
        self.db = Database(db_path)

    def _validate_race_data(self, race_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        レースデータの検証

        Args:
            race_data: レースデータ

        Returns:
            (検証結果, エラーメッセージのリスト)
        """
        errors = []

        # 必須フィールドのチェック
        for field in REQUIRED_RACE_FIELDS:
            if field not in race_data or race_data[field] is None:
                errors.append(f"必須フィールドがありません: {field}")

        if errors:
            return False, errors

        # venue_codeの検証（2桁の数字）
        venue_code = race_data['venue_code']
        if not isinstance(venue_code, str) or len(venue_code) != 2 or not venue_code.isdigit():
            errors.append(f"無効なvenue_code: {venue_code}")

        # race_dateの検証（8桁のYYYYMMDD形式）
        race_date = race_data['race_date']
        if not isinstance(race_date, str) or len(race_date) != 8 or not race_date.isdigit():
            errors.append(f"無効なrace_date: {race_date}")

        # race_numberの検証（1-12）
        race_number = race_data['race_number']
        if not isinstance(race_number, int) or not 1 <= race_number <= 12:
            errors.append(f"無効なrace_number: {race_number}")

        return len(errors) == 0, errors

    def _validate_entry_data(self, entry: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        選手エントリーデータの検証

        Args:
            entry: 選手データ

        Returns:
            (検証結果, エラーメッセージのリスト)
        """
        errors = []

        # 必須フィールドのチェック
        for field in REQUIRED_ENTRY_FIELDS:
            if field not in entry or entry[field] is None or entry[field] == '':
                errors.append(f"必須フィールドがありません: {field}")

        if errors:
            return False, errors

        # pit_numberの検証（1-6）
        pit_number = entry.get('pit_number')
        if not isinstance(pit_number, int) or not 1 <= pit_number <= 6:
            errors.append(f"無効なpit_number: {pit_number}")

        return len(errors) == 0, errors

    def _validate_result_data(self, result_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        レース結果データの検証

        Args:
            result_data: レース結果データ

        Returns:
            (検証結果, エラーメッセージのリスト)
        """
        errors = []

        # 必須フィールドのチェック
        if 'results' not in result_data or not result_data['results']:
            errors.append("resultsフィールドがありません")
            return False, errors

        # 結果数の検証（欠場・失格等で6艇未満もあり得る）
        results = result_data['results']
        if not (1 <= len(results) <= 6):
            errors.append(f"結果数が不正: {len(results)}艇（1-6艇であるべき）")

        # 各結果の検証
        seen_pits = set()
        seen_ranks = set()

        for idx, result in enumerate(results):
            # 必須フィールドのチェック
            for field in REQUIRED_RESULT_FIELDS:
                if field not in result or result[field] is None:
                    errors.append(f"results[{idx}]: 必須フィールドがありません: {field}")

            pit_number = result.get('pit_number')
            rank = result.get('rank')

            # pit_numberの検証（1-6）
            if not isinstance(pit_number, int) or not 1 <= pit_number <= 6:
                errors.append(f"results[{idx}]: 無効なpit_number: {pit_number}")
            elif pit_number in seen_pits:
                errors.append(f"results[{idx}]: 重複したpit_number: {pit_number}")
            else:
                seen_pits.add(pit_number)

            # rankの検証（実際の艇数に応じて）
            max_rank = len(results)
            if not isinstance(rank, int) or not 1 <= rank <= max_rank:
                errors.append(f"results[{idx}]: 無効なrank: {rank} (最大: {max_rank})")
            elif rank in seen_ranks:
                errors.append(f"results[{idx}]: 重複したrank: {rank}")
            else:
                seen_ranks.add(rank)

        return len(errors) == 0, errors

    def save_race_data(self, race_data: Dict[str, Any]) -> bool:
        """
        レースデータをデータベースに保存

        Args:
            race_data: スクレイパーから取得したレースデータ

        Returns:
            保存成功: True, 失敗: False
        """
        # データ検証
        is_valid, errors = self._validate_race_data(race_data)
        if not is_valid:
            logger.error(f"レースデータ検証エラー: {', '.join(errors)}")
            return False

        conn = None
        try:
            conn = self.db.connect()
            cursor = conn.cursor()

            # レース情報を保存
            race_id = self._save_race(cursor, race_data)
            if not race_id:
                conn.rollback()
                return False

            # 出走表（選手情報）を保存
            for entry in race_data.get('entries', []):
                # 各エントリーの検証
                is_valid, entry_errors = self._validate_entry_data(entry)
                if not is_valid:
                    logger.warning(f"エントリーデータ検証エラー（スキップ）: {', '.join(entry_errors)}")
                    continue
                self._save_entry(cursor, race_id, entry)

            conn.commit()
            logger.info(f"データベース保存完了: race_id={race_id}")
            return True

        except Exception as e:
            logger.error(f"データベース保存エラー: {e}", exc_info=True)
            if conn:
                conn.rollback()
            return False

        finally:
            if conn:
                conn.close()

    def _save_race(self, cursor, race_data):
        """
        レース情報を保存

        Args:
            cursor: DBカーソル
            race_data: レースデータ

        Returns:
            race_id: 保存したレースのID
        """
        venue_code = race_data['venue_code']
        race_date = race_data['race_date']
        race_number = race_data['race_number']
        race_time = race_data.get('race_time')
        race_grade = race_data.get('race_grade', '')
        race_distance = race_data.get('race_distance')

        # 新しいカラム（レースタイプ判定用）
        grade = race_data.get('grade', race_grade or '')  # gradeを優先、なければrace_grade
        is_nighter = 1 if race_data.get('is_nighter', False) else 0
        is_ladies = 1 if race_data.get('is_ladies', False) else 0
        is_rookie = 1 if race_data.get('is_rookie', False) else 0
        is_shinnyuu_kotei = 1 if race_data.get('is_shinnyuu_kotei', False) else 0

        # 日付をYYYY-MM-DD形式に変換（安全なユーティリティ使用）
        race_date_formatted = to_iso_format(race_date)

        # 既存データを確認
        cursor.execute("""
            SELECT id FROM races
            WHERE venue_code = ? AND race_date = ? AND race_number = ?
        """, (venue_code, race_date_formatted, race_number))

        existing = cursor.fetchone()

        if existing:
            # 既存データを更新
            race_id = existing[0]
            cursor.execute("""
                UPDATE races
                SET race_time = ?,
                    grade = ?,
                    is_nighter = ?,
                    is_ladies = ?,
                    is_rookie = ?,
                    is_shinnyuu_kotei = ?
                WHERE id = ?
            """, (race_time, grade, is_nighter, is_ladies, is_rookie, is_shinnyuu_kotei, race_id))
            logger.info(f"レース情報を更新: race_id={race_id}")
        else:
            # 新規データを挿入
            cursor.execute("""
                INSERT INTO races (venue_code, race_date, race_number, race_time, grade, is_nighter, is_ladies, is_rookie, is_shinnyuu_kotei)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (venue_code, race_date_formatted, race_number, race_time, grade, is_nighter, is_ladies, is_rookie, is_shinnyuu_kotei))
            race_id = cursor.lastrowid
            logger.info(f"レース情報を新規登録: race_id={race_id}")

        return race_id

    def _save_entry(self, cursor, race_id, entry):
        """
        出走表（選手情報）を保存

        Args:
            cursor: DBカーソル
            race_id: レースID
            entry: 選手データ
        """
        pit_number = entry['pit_number']

        # 既存データを削除（更新の場合）
        cursor.execute("""
            DELETE FROM entries
            WHERE race_id = ? AND pit_number = ?
        """, (race_id, pit_number))

        # 新規データを挿入
        cursor.execute("""
            INSERT INTO entries (
                race_id, pit_number, racer_number, racer_name,
                racer_rank, racer_home, racer_age, racer_weight,
                motor_number, boat_number,
                win_rate, second_rate, third_rate,
                f_count, l_count, avg_st,
                local_win_rate, local_second_rate, local_third_rate,
                motor_second_rate, motor_third_rate,
                boat_second_rate, boat_third_rate
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            race_id,
            pit_number,
            entry.get('racer_number'),
            entry.get('racer_name'),
            entry.get('racer_rank'),
            entry.get('racer_home'),
            entry.get('racer_age'),
            entry.get('racer_weight'),
            entry.get('motor_number'),
            entry.get('boat_number'),
            entry.get('win_rate'),
            entry.get('second_rate'),
            entry.get('third_rate'),
            entry.get('f_count'),
            entry.get('l_count'),
            entry.get('avg_st'),
            entry.get('local_win_rate'),
            entry.get('local_second_rate'),
            entry.get('local_third_rate'),
            entry.get('motor_second_rate'),
            entry.get('motor_third_rate'),
            entry.get('boat_second_rate'),
            entry.get('boat_third_rate')
        ))

    def get_race_data(self, venue_code, race_date, race_number):
        """
        データベースからレースデータを取得

        Args:
            venue_code: 競艇場コード
            race_date: レース日付（YYYYMMDD形式 または YYYY-MM-DD形式）
            race_number: レース番号

        Returns:
            レースデータの辞書
        """
        conn = self.db.connect()
        cursor = conn.cursor()

        # 日付をYYYY-MM-DD形式に変換
        race_date_formatted = to_iso_format(race_date)

        # レース情報取得
        cursor.execute("""
            SELECT id, venue_code, race_date, race_number, race_time
            FROM races
            WHERE venue_code = ? AND race_date = ? AND race_number = ?
        """, (venue_code, race_date_formatted, race_number))

        race_row = cursor.fetchone()
        if not race_row:
            self.db.close()
            return None

        race_data = {
            'id': race_row[0],
            'venue_code': race_row[1],
            'race_date': race_row[2],
            'race_number': race_row[3],
            'race_time': race_row[4],
            'entries': []
        }

        # 出走表取得
        cursor.execute("""
            SELECT pit_number, racer_number, racer_name, racer_rank,
                   racer_home, racer_age, racer_weight,
                   motor_number, boat_number,
                   win_rate, second_rate, third_rate,
                   f_count, l_count, avg_st,
                   local_win_rate, local_second_rate, local_third_rate,
                   motor_second_rate, motor_third_rate,
                   boat_second_rate, boat_third_rate
            FROM entries
            WHERE race_id = ?
            ORDER BY pit_number
        """, (race_row[0],))

        for entry_row in cursor.fetchall():
            entry = {
                'pit_number': entry_row[0],
                'racer_number': entry_row[1],
                'racer_name': entry_row[2],
                'racer_rank': entry_row[3],
                'racer_home': entry_row[4],
                'racer_age': entry_row[5],
                'racer_weight': entry_row[6],
                'motor_number': entry_row[7],
                'boat_number': entry_row[8],
                'win_rate': entry_row[9],
                'second_rate': entry_row[10],
                'third_rate': entry_row[11],
                'f_count': entry_row[12],
                'l_count': entry_row[13],
                'avg_st': entry_row[14],
                'local_win_rate': entry_row[15],
                'local_second_rate': entry_row[16],
                'local_third_rate': entry_row[17],
                'motor_second_rate': entry_row[18],
                'motor_third_rate': entry_row[19],
                'boat_second_rate': entry_row[20],
                'boat_third_rate': entry_row[21]
            }
            race_data['entries'].append(entry)

        self.db.close()
        return race_data

    def get_today_races(self, venue_code, race_date):
        """
        指定日・指定場の全レース一覧を取得

        Args:
            venue_code: 競艇場コード
            race_date: レース日付（YYYYMMDD形式 または YYYY-MM-DD形式）

        Returns:
            レース一覧のリスト
        """
        conn = self.db.connect()
        cursor = conn.cursor()

        # 日付をYYYY-MM-DD形式に変換
        race_date_formatted = to_iso_format(race_date)

        cursor.execute("""
            SELECT id, race_number, race_time
            FROM races
            WHERE venue_code = ? AND race_date = ?
            ORDER BY race_number
        """, (venue_code, race_date_formatted))

        races = []
        for row in cursor.fetchall():
            races.append({
                'id': row[0],
                'race_number': row[1],
                'race_time': row[2]
            })

        self.db.close()
        return races

    def save_multiple_races(self, races_data_list):
        """
        複数レースのデータを一括保存

        Args:
            races_data_list: レースデータのリスト

        Returns:
            保存成功数、失敗数のタプル
        """
        success_count = 0
        error_count = 0

        for race_data in races_data_list:
            try:
                if self.save_race_data(race_data):
                    success_count += 1
                else:
                    error_count += 1
            except Exception as e:
                logger.error(f"保存エラー (R{race_data.get('race_number')}): {e}")
                error_count += 1

        logger.info(f"一括保存完了: 成功={success_count}件, 失敗={error_count}件")
        return success_count, error_count


    def get_weather_data(self, venue_code, weather_date):
        """
        データベースから天気データを取得

        Args:
            venue_code: 競艇場コード
            weather_date: 日付（YYYY-MM-DD形式）

        Returns:
            天気データの辞書
        """
        conn = self.db.connect()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT temperature, weather_condition, wind_speed, wind_direction, humidity
            FROM weather
            WHERE venue_code = ? AND weather_date = ?
        """, (venue_code, weather_date))

        row = cursor.fetchone()
        self.db.close()

        if row:
            return {
                'temperature': row[0],
                'weather_condition': row[1],
                'wind_speed': row[2],
                'wind_direction': row[3],
                'humidity': row[4]
            }
        return None

    def save_race_result(self, result_data):
        """
        レース結果をデータベースに保存（新構造：各艇の着順を記録）

        Args:
            result_data: レース結果データの辞書
                {
                    'venue_code': '10',
                    'race_date': '20251029',
                    'race_number': 1,
                    'results': [
                        {'pit_number': 1, 'rank': 3},
                        {'pit_number': 2, 'rank': 1},
                        {'pit_number': 3, 'rank': 5},
                        ...
                    ],
                    'trifecta_odds': 1234.5,
                    'is_invalid': False
                }

        Returns:
            保存成功: True, 失敗: False
        """
        # データ検証
        is_valid, errors = self._validate_result_data(result_data)
        if not is_valid:
            logger.error(f"レース結果データ検証エラー: {', '.join(errors)}")
            return False

        conn = None
        try:
            conn = self.db.connect()
            cursor = conn.cursor()

            # race_idを取得
            venue_code = result_data['venue_code']
            race_date = result_data['race_date']
            race_number = result_data['race_number']

            # 日付をYYYY-MM-DD形式に変換（安全なユーティリティ使用）
            race_date_formatted = to_iso_format(race_date)

            cursor.execute("""
                SELECT id FROM races
                WHERE venue_code = ? AND race_date = ? AND race_number = ?
            """, (venue_code, race_date_formatted, race_number))

            race_row = cursor.fetchone()
            if not race_row:
                logger.warning(f"レースが見つかりません: {venue_code} {race_date_formatted} {race_number}R")
                return False

            race_id = race_row[0]

            # race_statusを更新（result_dataにrace_statusが含まれている場合）
            race_status = result_data.get('race_status')
            if race_status:
                cursor.execute("""
                    UPDATE races
                    SET race_status = ?
                    WHERE id = ?
                """, (race_status, race_id))

            # 既存データを削除
            cursor.execute("DELETE FROM results WHERE race_id = ?", (race_id,))

            # 各艇の結果を保存
            trifecta_odds = result_data.get('trifecta_odds')
            is_invalid = 1 if result_data.get('is_invalid', False) else 0
            winning_technique = result_data.get('winning_technique')
            kimarite_text = result_data.get('kimarite')  # テキスト形式の決まり手

            for result in result_data.get('results', []):
                pit_number = result.get('pit_number')
                rank = result.get('rank')

                # 1着の艇にだけオッズと決まり手を記録
                odds = trifecta_odds if rank == 1 else None
                technique = winning_technique if rank == 1 else None
                kimarite = kimarite_text if rank == 1 else None

                cursor.execute("""
                    INSERT INTO results (
                        race_id, pit_number, rank, is_invalid, trifecta_odds, winning_technique, kimarite
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (race_id, pit_number, rank, is_invalid, odds, technique, kimarite))

            conn.commit()
            return True

        except Exception as e:
            logger.error(f"結果保存エラー: {e}", exc_info=True)
            if conn:
                conn.rollback()
            return False

        finally:
            if conn:
                conn.close()

    def save_weather_data(self, venue_code, weather_date, weather_data):
        """
        天気情報をデータベースに保存

        Args:
            venue_code: 競艇場コード
            weather_date: 日付（YYYY-MM-DD形式）
            weather_data: 天気データの辞書
                {
                    'temperature': 17.0,
                    'weather_condition': '晴れ',
                    'wind_speed': 5.0,
                    'wind_direction': '北',
                    'water_temperature': 20.0,
                    'wave_height': 5.0
                }

        Returns:
            保存成功: True, 失敗: False
        """
        if not weather_data:
            return False

        conn = None
        try:
            conn = self.db.connect()
            cursor = conn.cursor()

            # 既存データがあれば更新、なければ挿入
            cursor.execute("""
                INSERT OR REPLACE INTO weather (
                    venue_code, weather_date, temperature, weather_condition,
                    wind_speed, wind_direction, water_temperature, wave_height
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                venue_code,
                weather_date,
                weather_data.get('temperature'),
                weather_data.get('weather_condition'),
                weather_data.get('wind_speed'),
                weather_data.get('wind_direction'),
                weather_data.get('water_temperature'),
                weather_data.get('wave_height')
            ))

            conn.commit()
            return True

        except Exception as e:
            logger.error(f"天気情報保存エラー: {e}", exc_info=True)
            if conn:
                conn.rollback()
            return False

        finally:
            if conn:
                conn.close()

    def save_race_details(self, race_id, race_details_data):
        """
        レース詳細データ（展示タイム、チルト、進入コース等）を保存

        Args:
            race_id: レースID
            race_details_data: レース詳細データのリスト
                [{'pit_number': 1, 'exhibition_time': 6.79, 'tilt_angle': 0.0,
                  'parts_replacement': '', 'actual_course': 1, 'st_time': 0.14}, ...]

        Returns:
            保存成功: True, 失敗: False
        """
        conn = None
        try:
            conn = self.db.connect()
            cursor = conn.cursor()

            for detail in race_details_data:
                pit_number = detail.get('pit_number')
                exhibition_time = detail.get('exhibition_time')
                tilt_angle = detail.get('tilt_angle')
                parts_replacement = detail.get('parts_replacement')
                actual_course = detail.get('actual_course')
                st_time = detail.get('st_time')

                # INSERTを試み、競合時はNULLでない値のみUPDATE
                cursor.execute("""
                    INSERT INTO race_details (
                        race_id, pit_number, exhibition_time, tilt_angle,
                        parts_replacement, actual_course, st_time
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(race_id, pit_number) DO UPDATE SET
                        exhibition_time = COALESCE(excluded.exhibition_time, race_details.exhibition_time),
                        tilt_angle = COALESCE(excluded.tilt_angle, race_details.tilt_angle),
                        parts_replacement = COALESCE(excluded.parts_replacement, race_details.parts_replacement),
                        actual_course = COALESCE(excluded.actual_course, race_details.actual_course),
                        st_time = COALESCE(excluded.st_time, race_details.st_time)
                """, (
                    race_id, pit_number, exhibition_time, tilt_angle,
                    parts_replacement, actual_course, st_time
                ))

            conn.commit()
            logger.info(f"レース詳細データ保存完了: race_id={race_id}, {len(race_details_data)}艇分")
            return True

        except Exception as e:
            logger.error(f"レース詳細保存エラー: {e}", exc_info=True)
            if conn:
                conn.rollback()
            return False

        finally:
            if conn:
                conn.close()

    def save_payouts(self, race_id, payouts_data):
        """
        払戻金データを保存

        Args:
            race_id: レースID
            payouts_data: 払戻金データの辞書
                {'trifecta': [{'combination': '1-4-6', 'amount': 12300, 'popularity': 1}, ...],
                 'trio': [...], ...}

        Returns:
            保存成功: True, 失敗: False
        """
        conn = None
        try:
            conn = self.db.connect()
            cursor = conn.cursor()

            # 既存データを削除（更新の場合）
            cursor.execute("DELETE FROM payouts WHERE race_id = ?", (race_id,))

            # N+1問題を回避：一括挿入用のデータを準備
            insert_data = []
            for bet_type, payout_list in payouts_data.items():
                if not payout_list:
                    continue

                for payout in payout_list:
                    combination = payout.get('combination')
                    amount = payout.get('amount')
                    popularity = payout.get('popularity')

                    if combination and amount:
                        insert_data.append((race_id, bet_type, combination, amount, popularity))

            # executemanyで一括挿入
            if insert_data:
                cursor.executemany("""
                    INSERT INTO payouts (race_id, bet_type, combination, amount, popularity)
                    VALUES (?, ?, ?, ?, ?)
                """, insert_data)

            conn.commit()
            logger.info(f"払戻金データ保存完了: race_id={race_id}")
            return True

        except Exception as e:
            logger.error(f"払戻金保存エラー: {e}", exc_info=True)
            if conn:
                conn.rollback()
            return False

        finally:
            if conn:
                conn.close()

    def update_kimarite(self, race_id, kimarite):
        """
        レース結果に決まり手を更新

        Args:
            race_id: レースID
            kimarite: 決まり手（逃げ、差し、まくり、まくり差し、抜き、恵まれ）

        Returns:
            保存成功: True, 失敗: False
        """
        try:
            conn = self.db.connect()
            cursor = conn.cursor()

            # resultsテーブルのkirmarite列を更新
            cursor.execute("""
                UPDATE results
                SET kimarite = ?
                WHERE race_id = ? AND rank = 1
            """, (kimarite, race_id))

            conn.commit()
            self.db.close()
            logger.info(f"決まり手更新完了: race_id={race_id}, kimarite={kimarite}")
            return True

        except Exception as e:
            logger.error(f"決まり手更新エラー: {e}")
            if conn:
                conn.rollback()
            self.db.close()
            return False

    def update_st_times(self, race_id, st_times_dict):
        """
        STタイムを更新

        Args:
            race_id: レースID
            st_times_dict: {枠番: STタイム} の辞書

        Returns:
            保存成功: True, 失敗: False
        """
        try:
            conn = self.db.connect()
            cursor = conn.cursor()

            # N+1問題を回避：executemanyを使用して一括更新
            update_data = [(st_time, race_id, pit_number)
                          for pit_number, st_time in st_times_dict.items()]

            cursor.executemany("""
                UPDATE race_details
                SET st_time = ?
                WHERE race_id = ? AND pit_number = ?
            """, update_data)

            conn.commit()
            self.db.close()
            logger.info(f"STタイム更新完了: race_id={race_id}, {len(st_times_dict)}艇分")
            return True

        except Exception as e:
            logger.error(f"STタイム更新エラー: {e}")
            if conn:
                conn.rollback()
            self.db.close()
            return False

    def update_race_status(self, race_id: int, race_status: str) -> bool:
        """
        レースのステータスを更新
        
        Args:
            race_id: レースID
            race_status: レースステータス（'completed', 'cancelled', 'flying', 'accident', 'returned'）
        
        Returns:
            更新成功: True, 失敗: False
        """
        conn = None
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE races
                SET race_status = ?
                WHERE id = ?
            """, (race_status, race_id))
            
            conn.commit()
            logger.info(f"レースステータス更新: race_id={race_id}, status={race_status}")
            return True
            
        except Exception as e:
            logger.error(f"レースステータス更新エラー: {e}", exc_info=True)
            if conn:
                conn.rollback()
            return False
            
        finally:
            if conn:
                conn.close()
    
    def update_race_status_by_info(self, venue_code: str, race_date: str, race_number: int, race_status: str) -> bool:
        """
        レース情報からステータスを更新

        Args:
            venue_code: 競艇場コード
            race_date: レース日付（YYYYMMDD or YYYY-MM-DD）
            race_number: レース番号
            race_status: レースステータス

        Returns:
            更新成功: True, 失敗: False
        """
        conn = None
        try:
            conn = self.db.connect()
            cursor = conn.cursor()

            # 日付をYYYY-MM-DD形式に変換
            race_date_formatted = to_iso_format(race_date)

            cursor.execute("""
                SELECT id FROM races
                WHERE venue_code = ? AND race_date = ? AND race_number = ?
            """, (venue_code, race_date_formatted, race_number))

            race_row = cursor.fetchone()
            if not race_row:
                logger.warning(f"レースが見つかりません: {venue_code} {race_date_formatted} {race_number}R")
                return False

            race_id = race_row[0]

            cursor.execute("""
                UPDATE races
                SET race_status = ?
                WHERE id = ?
            """, (race_status, race_id))

            conn.commit()
            logger.info(f"レースステータス更新: {venue_code} {race_date_formatted} {race_number}R -> {race_status}")
            return True

        except Exception as e:
            logger.error(f"レースステータス更新エラー: {e}", exc_info=True)
            if conn:
                conn.rollback()
            return False

        finally:
            if conn:
                conn.close()

    def _get_race_environment(self, race_id: int) -> Dict:
        """
        レースの環境情報を取得

        Args:
            race_id: レースID

        Returns:
            環境情報の辞書
        """
        conn = None
        try:
            conn = self.db.connect()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    r.venue_code,
                    r.race_time,
                    rc.wind_direction,
                    rc.wind_speed,
                    rc.wave_height,
                    rc.weather
                FROM races r
                LEFT JOIN race_conditions rc ON r.id = rc.race_id
                WHERE r.id = ?
            """, (race_id,))

            row = cursor.fetchone()
            if row:
                return {
                    'venue_code': row[0],
                    'race_time': row[1],
                    'wind_direction': row[2],
                    'wind_speed': row[3],
                    'wave_height': row[4],
                    'weather': row[5]
                }
            else:
                return {
                    'venue_code': None,
                    'race_time': None,
                    'wind_direction': None,
                    'wind_speed': None,
                    'wave_height': None,
                    'weather': None
                }

        except Exception as e:
            logger.error(f"環境情報取得エラー: {e}", exc_info=True)
            return {
                'venue_code': None,
                'race_time': None,
                'wind_direction': None,
                'wind_speed': None,
                'wave_height': None,
                'weather': None
            }

        finally:
            if conn:
                conn.close()

    def save_race_predictions(self, race_id: int, predictions: List[Dict], prediction_type: str = 'advance') -> bool:
        """
        レースの予想結果をデータベースに保存

        Args:
            race_id: レースID
            predictions: 予想結果のリスト
                [
                    {
                        'pit_number': 1,
                        'rank_prediction': 1,
                        'total_score': 85.5,
                        'confidence': 'high',
                        'racer_name': '選手名',
                        'racer_number': '1234',
                        'applied_rules': 'rule1,rule2,rule3'
                    },
                    ...
                ]
            prediction_type: 予想タイプ ('advance': 事前予想, 'before': 直前予想)

        Returns:
            保存成功: True, 失敗: False
        """
        conn = None
        try:
            conn = self.db.connect()
            cursor = conn.cursor()

            # 既存の同タイプの予想データを削除（再生成の場合）
            cursor.execute(
                "DELETE FROM race_predictions WHERE race_id = ? AND prediction_type = ?",
                (race_id, prediction_type)
            )

            # BEFORE予想の場合、環境要因減点システムを適用
            env_info = None
            penalty_system = None
            if prediction_type == 'before':
                try:
                    from ..analysis.environmental_penalty import EnvironmentalPenaltySystem
                    env_info = self._get_race_environment(race_id)
                    penalty_system = EnvironmentalPenaltySystem()
                    logger.info(f"環境要因減点システム準備完了: race_id={race_id}")
                except Exception as e:
                    logger.warning(f"環境要因減点システム初期化エラー（スキップ）: {e}")

            # 予想データを保存
            from datetime import datetime
            generated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            for pred in predictions:
                # 信頼度Bの予想に環境要因減点を適用（BEFORE予想のみ）
                original_confidence = pred.get('confidence')
                if (prediction_type == 'before' and
                    original_confidence == 'B' and
                    penalty_system is not None and
                    env_info.get('venue_code') is not None):

                    try:
                        # 環境要因減点を計算
                        result = penalty_system.should_accept_bet(
                            venue_code=env_info['venue_code'],
                            race_time=env_info['race_time'] or '12:00',
                            wind_direction=env_info['wind_direction'],
                            wind_speed=env_info['wind_speed'],
                            wave_height=env_info['wave_height'],
                            weather=env_info['weather'],
                            original_score=pred.get('total_score', 100),
                            min_threshold=0  # 閾値チェックはしない（信頼度のみ調整）
                        )

                        # 調整後の信頼度を適用
                        adjusted_confidence = result['adjusted_confidence']
                        if adjusted_confidence != original_confidence:
                            pred['confidence'] = adjusted_confidence
                            logger.info(
                                f"環境要因減点適用: race_id={race_id}, "
                                f"pit={pred.get('pit_number')}, "
                                f"元信頼度=B, 調整後={adjusted_confidence}, "
                                f"減点={result['penalty']}pt, "
                                f"元スコア={pred.get('total_score', 100):.1f}, "
                                f"調整後スコア={result['adjusted_score']:.1f}"
                            )
                    except Exception as e:
                        logger.warning(f"環境要因減点適用エラー（スキップ）: {e}")

                cursor.execute("""
                    INSERT INTO race_predictions (
                        race_id, pit_number, rank_prediction, total_score,
                        confidence, racer_name, racer_number, applied_rules,
                        course_score, racer_score, motor_score, kimarite_score, grade_score,
                        prediction_type, generated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    race_id,
                    pred.get('pit_number'),
                    pred.get('rank_prediction'),
                    pred.get('total_score'),
                    pred.get('confidence'),
                    pred.get('racer_name'),
                    pred.get('racer_number'),
                    pred.get('applied_rules'),
                    pred.get('course_score', 0),
                    pred.get('racer_score', 0),
                    pred.get('motor_score', 0),
                    pred.get('kimarite_score', 0),
                    pred.get('grade_score', 0),
                    prediction_type,
                    generated_at
                ))

            conn.commit()
            logger.info(f"予想データ保存完了: race_id={race_id}, type={prediction_type}, {len(predictions)}件")
            return True

        except Exception as e:
            logger.error(f"予想データ保存エラー: {e}", exc_info=True)
            if conn:
                conn.rollback()
            return False

        finally:
            if conn:
                conn.close()

    def get_race_predictions(self, race_id: int, prediction_type: str = 'before') -> Optional[List[Dict]]:
        """
        保存された予想データを取得

        Args:
            race_id: レースID
            prediction_type: 予想タイプ ('advance': 事前予想, 'before': 直前予想)
                            デフォルトは'before'（直前予想を優先）

        Returns:
            予想データのリスト、またはNone
        """
        conn = None
        try:
            conn = self.db.connect()
            cursor = conn.cursor()

            # まず指定されたタイプの予想を検索
            cursor.execute("""
                SELECT pit_number, rank_prediction, total_score, confidence,
                       racer_name, racer_number, applied_rules, prediction_type, generated_at
                FROM race_predictions
                WHERE race_id = ? AND prediction_type = ?
                ORDER BY rank_prediction
            """, (race_id, prediction_type))

            rows = cursor.fetchall()

            # 指定されたタイプが見つからない場合、他のタイプを検索（後方互換性）
            if not rows:
                cursor.execute("""
                    SELECT pit_number, rank_prediction, total_score, confidence,
                           racer_name, racer_number, applied_rules, prediction_type, generated_at
                    FROM race_predictions
                    WHERE race_id = ?
                    ORDER BY rank_prediction
                """, (race_id,))
                rows = cursor.fetchall()

            if not rows:
                return None

            predictions = []
            for row in rows:
                predictions.append({
                    'pit_number': row[0],
                    'rank_prediction': row[1],
                    'total_score': row[2],
                    'confidence': row[3],
                    'racer_name': row[4],
                    'racer_number': row[5],
                    'applied_rules': row[6],
                    'prediction_type': row[7] if len(row) > 7 else 'advance',
                    'generated_at': row[8] if len(row) > 8 else None
                })

            return predictions

        except Exception as e:
            logger.error(f"予想データ取得エラー: {e}", exc_info=True)
            return None

        finally:
            if conn:
                conn.close()
