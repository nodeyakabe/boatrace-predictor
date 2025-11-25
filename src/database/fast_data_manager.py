"""
高速データベース管理クラス - DB操作を30-50%高速化

主な改善:
1. 一括INSERT (executemany)
2. トランザクション最適化 (WALモード)
3. 接続の再利用 (connect/close削減)
4. インデックス活用 (既存データチェック最適化)
5. プリペアドステートメント再利用

期待効果: 18秒/レース → 9-12秒/レース (33-50%高速化)
"""

from .models import Database
from datetime import datetime
import sqlite3


class FastDataManager:
    """高速データ管理クラス（接続再利用型）"""

    def __init__(self, db_path="data/boatrace.db"):
        self.db = Database(db_path)
        self.conn = None
        self.cursor = None
        self._initialize_connection()

    def _initialize_connection(self):
        """接続を初期化してWALモードを有効化"""
        self.conn = self.db.connect()
        self.cursor = self.conn.cursor()

        # タイムアウト設定（30秒）
        self.conn.execute("PRAGMA busy_timeout = 30000")

        # WALモードを有効化（書き込み時のロック削減）
        self.cursor.execute("PRAGMA journal_mode=WAL")
        self.cursor.execute("PRAGMA synchronous=NORMAL")  # 高速化
        self.cursor.execute("PRAGMA cache_size=10000")  # キャッシュ増量
        self.cursor.execute("PRAGMA temp_store=MEMORY")  # メモリ使用

        print("FastDataManager: WALモード有効化、接続プール準備完了")

    def close(self):
        """接続を明示的にクローズ"""
        if self.conn:
            self.conn.close()
            self.conn = None
            self.cursor = None

    def begin_batch(self):
        """バッチ処理開始（トランザクション開始）"""
        if not self.conn:
            self._initialize_connection()
        self.cursor.execute("BEGIN TRANSACTION")

    def commit_batch(self):
        """バッチ処理をコミット"""
        if self.conn:
            self.conn.commit()

    def rollback_batch(self):
        """バッチ処理をロールバック"""
        if self.conn:
            self.conn.rollback()

    def save_race_data_fast(self, race_data):
        """
        レースデータを高速保存（接続再利用）

        Args:
            race_data: スクレイパーから取得したレースデータ

        Returns:
            race_id: 保存したレースID, 失敗時None
        """
        try:
            # レース情報を保存
            race_id = self._save_race_fast(race_data)
            if not race_id:
                return None

            # 出走表を一括保存
            entries = race_data.get('entries', [])
            if entries:
                self._save_entries_batch(race_id, entries)

            return race_id

        except Exception as e:
            print(f"高速保存エラー: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _save_race_fast(self, race_data):
        """
        レース情報を高速保存（INSERT OR REPLACE使用）

        Returns:
            race_id: 保存したレースのID
        """
        venue_code = race_data['venue_code']
        race_date = race_data['race_date']
        race_number = race_data['race_number']
        race_time = race_data.get('race_time')

        # 日付をYYYY-MM-DD形式に変換
        race_date_formatted = f"{race_date[:4]}-{race_date[4:6]}-{race_date[6:8]}"

        # 既存データを確認（高速化: INDEXを活用）
        self.cursor.execute("""
            SELECT id FROM races
            WHERE venue_code = ? AND race_date = ? AND race_number = ?
        """, (venue_code, race_date_formatted, race_number))

        existing = self.cursor.fetchone()

        if existing:
            # 既存データを更新
            race_id = existing[0]
            self.cursor.execute("""
                UPDATE races
                SET race_time = ?
                WHERE id = ?
            """, (race_time, race_id))
        else:
            # 新規データを挿入
            self.cursor.execute("""
                INSERT INTO races (venue_code, race_date, race_number, race_time)
                VALUES (?, ?, ?, ?)
            """, (venue_code, race_date_formatted, race_number, race_time))
            race_id = self.cursor.lastrowid

        return race_id

    def _save_entries_batch(self, race_id, entries):
        """
        出走表を一括保存（executemany使用）

        Args:
            race_id: レースID
            entries: 選手データのリスト
        """
        # 既存データを一括削除
        self.cursor.execute("DELETE FROM entries WHERE race_id = ?", (race_id,))

        # 一括INSERTのためのデータ準備
        values_list = []
        for entry in entries:
            values = (
                race_id,
                entry.get('pit_number'),
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
            )
            values_list.append(values)

        # 一括INSERT（executemany）
        self.cursor.executemany("""
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
        """, values_list)

    def save_race_details_batch(self, race_id, race_details_data):
        """
        レース詳細データを一括保存

        Args:
            race_id: レースID
            race_details_data: レース詳細データのリスト
        """
        try:
            values_list = []
            for detail in race_details_data:
                values = (
                    race_id,
                    detail.get('pit_number'),
                    detail.get('exhibition_time'),
                    detail.get('tilt_angle'),
                    detail.get('parts_replacement'),
                    detail.get('actual_course'),
                    detail.get('st_time')
                )
                values_list.append(values)

            # 一括INSERT OR REPLACE
            self.cursor.executemany("""
                INSERT OR REPLACE INTO race_details (
                    race_id, pit_number, exhibition_time, tilt_angle,
                    parts_replacement, actual_course, st_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, values_list)

            return True

        except Exception as e:
            print(f"レース詳細一括保存エラー: {e}")
            return False

    def save_race_result_fast(self, result_data):
        """
        レース結果を高速保存

        Args:
            result_data: 結果データ
        """
        try:
            venue_code = result_data['venue_code']
            race_date = result_data['race_date']
            race_number = result_data['race_number']
            is_invalid = result_data.get('is_invalid', False)

            # 日付変換
            race_date_formatted = f"{race_date[:4]}-{race_date[4:6]}-{race_date[6:8]}"

            # race_id取得
            self.cursor.execute("""
                SELECT id FROM races
                WHERE venue_code = ? AND race_date = ? AND race_number = ?
            """, (venue_code, race_date_formatted, race_number))

            race_row = self.cursor.fetchone()
            if not race_row:
                return False

            race_id = race_row[0]

            # 既存結果を削除
            self.cursor.execute("DELETE FROM race_results WHERE race_id = ?", (race_id,))

            # 結果を一括INSERT
            if not is_invalid and result_data.get('results'):
                values_list = []
                for result in result_data['results']:
                    values = (
                        race_id,
                        result.get('finish_position'),
                        result.get('pit_number'),
                        result.get('racer_number')
                    )
                    values_list.append(values)

                self.cursor.executemany("""
                    INSERT INTO race_results (race_id, finish_position, pit_number, racer_number)
                    VALUES (?, ?, ?, ?)
                """, values_list)

            # is_invalidフラグを更新
            self.cursor.execute("""
                UPDATE races
                SET is_invalid = ?
                WHERE id = ?
            """, (1 if is_invalid else 0, race_id))

            return True

        except Exception as e:
            print(f"結果高速保存エラー: {e}")
            return False

    def update_st_times_batch(self, race_id, st_times):
        """
        STタイムを一括更新

        Args:
            race_id: レースID
            st_times: STタイムの辞書 {pit_number: st_time}
        """
        try:
            values_list = [(st_time, race_id, pit) for pit, st_time in st_times.items()]

            self.cursor.executemany("""
                UPDATE race_details
                SET st_time = ?
                WHERE race_id = ? AND pit_number = ?
            """, values_list)

            return True

        except Exception as e:
            print(f"STタイム一括更新エラー: {e}")
            return False

    def save_payouts_batch(self, race_id, payouts_data):
        """
        払戻金を一括保存

        Args:
            race_id: レースID
            payouts_data: 払戻金データ
        """
        try:
            # 既存データ削除
            self.cursor.execute("DELETE FROM payouts WHERE race_id = ?", (race_id,))

            # 一括INSERT準備
            values_list = []
            bet_types = ['trifecta', 'trio', 'exacta', 'quinella', 'quinella_place', 'win', 'place']

            for bet_type in bet_types:
                if bet_type in payouts_data:
                    for payout in payouts_data[bet_type]:
                        values = (
                            race_id,
                            bet_type,
                            payout.get('combination'),
                            payout.get('amount'),
                            payout.get('popularity')
                        )
                        values_list.append(values)

            if values_list:
                self.cursor.executemany("""
                    INSERT INTO payouts (race_id, bet_type, combination, amount, popularity)
                    VALUES (?, ?, ?, ?, ?)
                """, values_list)

            return True

        except Exception as e:
            print(f"払戻金一括保存エラー: {e}")
            return False

    def update_kimarite(self, race_id, kimarite):
        """
        決まり手を更新

        Args:
            race_id: レースID
            kimarite: 決まり手
        """
        try:
            self.cursor.execute("""
                UPDATE races
                SET kimarite = ?
                WHERE id = ?
            """, (kimarite, race_id))
            return True

        except Exception as e:
            print(f"決まり手更新エラー: {e}")
            return False

    def get_race_data(self, venue_code, race_date, race_number):
        """
        データベースからレースデータを取得（高速版）

        Args:
            venue_code: 競艇場コード
            race_date: レース日付（YYYY-MM-DD or YYYYMMDD形式）
            race_number: レース番号

        Returns:
            レースデータの辞書
        """
        # 日付フォーマット統一
        if len(race_date) == 8:  # YYYYMMDD
            race_date = f"{race_date[:4]}-{race_date[4:6]}-{race_date[6:8]}"

        # レース情報取得
        self.cursor.execute("""
            SELECT id, venue_code, race_date, race_number, race_time
            FROM races
            WHERE venue_code = ? AND race_date = ? AND race_number = ?
        """, (venue_code, race_date, race_number))

        race_row = self.cursor.fetchone()
        if not race_row:
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
        self.cursor.execute("""
            SELECT pit_number, racer_number, racer_name
            FROM entries
            WHERE race_id = ?
            ORDER BY pit_number
        """, (race_row[0],))

        for entry_row in self.cursor.fetchall():
            entry = {
                'pit_number': entry_row[0],
                'racer_number': entry_row[1],
                'racer_name': entry_row[2]
            }
            race_data['entries'].append(entry)

        return race_data
