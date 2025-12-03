"""
レース結果の手動入力・管理モジュール
"""

import sqlite3
from typing import Dict, List, Tuple
from datetime import datetime
from src.utils.db_connection_pool import get_connection


class ResultManager:
    """レース結果の管理クラス"""

    def __init__(self, db_path: str = "data/boatrace.db"):
        self.db_path = db_path

    def _connect(self):
        """データベース接続（接続プールから取得）"""
        return get_connection(self.db_path)

    def add_manual_result(self, race_id: int, pit_number: int, rank: int) -> bool:
        """
        手動でレース結果を追加

        Args:
            race_id: レースID
            pit_number: 艇番（1-6）
            rank: 着順（1-6）

        Returns:
            成功: True, 失敗: False
        """
        try:
            conn = self._connect()
            cursor = conn.cursor()

            # 既存データを確認
            cursor.execute("""
                SELECT id FROM results
                WHERE race_id = ? AND pit_number = ?
            """, (race_id, pit_number))

            existing = cursor.fetchone()

            if existing:
                # 既存データを更新
                cursor.execute("""
                    UPDATE results
                    SET rank = ?, is_invalid = 0
                    WHERE race_id = ? AND pit_number = ?
                """, (rank, race_id, pit_number))
            else:
                # 新規追加
                cursor.execute("""
                    INSERT INTO results (race_id, pit_number, rank, is_invalid)
                    VALUES (?, ?, ?, 0)
                """, (race_id, pit_number, rank))

            conn.commit()
            cursor.close()
            return True

        except Exception as e:
            print(f"Error adding result: {e}")
            return False

    def delete_result(self, race_id: int, pit_number: int) -> bool:
        """
        レース結果を削除

        Args:
            race_id: レースID
            pit_number: 艇番

        Returns:
            成功: True, 失敗: False
        """
        try:
            conn = self._connect()
            cursor = conn.cursor()

            cursor.execute("""
                DELETE FROM results
                WHERE race_id = ? AND pit_number = ?
            """, (race_id, pit_number))

            conn.commit()
            affected = cursor.rowcount
            cursor.close()

            return affected > 0

        except Exception as e:
            print(f"Error deleting result: {e}")
            return False

    def mark_as_invalid(self, race_id: int, pit_number: int) -> bool:
        """
        レース結果を無効としてマーク

        Args:
            race_id: レースID
            pit_number: 艇番

        Returns:
            成功: True, 失敗: False
        """
        try:
            conn = self._connect()
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE results
                SET is_invalid = 1
                WHERE race_id = ? AND pit_number = ?
            """, (race_id, pit_number))

            conn.commit()
            affected = cursor.rowcount
            cursor.close()

            return affected > 0

        except Exception as e:
            print(f"Error marking invalid: {e}")
            return False

    def get_race_results(self, race_id: int) -> List[Dict]:
        """
        レースの全結果を取得

        Args:
            race_id: レースID

        Returns:
            [{pit_number: 1, rank: 1, racer_name: '山田太郎', is_invalid: 0}, ...]
        """
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = """
            SELECT
                r.pit_number,
                r.rank,
                r.is_invalid,
                e.racer_name
            FROM results r
            LEFT JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            WHERE r.race_id = ?
            ORDER BY r.rank
        """

        cursor.execute(query, (race_id,))
        rows = cursor.fetchall()
        cursor.close()

        return [
            {
                'pit_number': row['pit_number'],
                'rank': row['rank'],
                'is_invalid': row['is_invalid'],
                'racer_name': row['racer_name'] if row['racer_name'] else '不明'
            }
            for row in rows
        ]

    def import_from_csv(self, csv_path: str) -> Tuple[int, int]:
        """
        CSVファイルから一括インポート

        CSV形式: race_id,pit_number,rank
        例: 12345,1,1

        Args:
            csv_path: CSVファイルパス

        Returns:
            (成功件数, 失敗件数)
        """
        import csv

        success_count = 0
        fail_count = 0

        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)

                for row in reader:
                    try:
                        race_id = int(row['race_id'])
                        pit_number = int(row['pit_number'])
                        rank = int(row['rank'])

                        if self.add_manual_result(race_id, pit_number, rank):
                            success_count += 1
                        else:
                            fail_count += 1

                    except (ValueError, KeyError) as e:
                        print(f"Invalid row: {row}, error: {e}")
                        fail_count += 1

        except FileNotFoundError:
            print(f"File not found: {csv_path}")
            return (0, 0)
        except Exception as e:
            print(f"Import error: {e}")
            return (success_count, fail_count)

        return (success_count, fail_count)

    def export_to_csv(self, start_date: str, end_date: str, output_path: str) -> int:
        """
        指定期間のレース結果をCSV出力

        Args:
            start_date: 開始日（YYYY-MM-DD）
            end_date: 終了日（YYYY-MM-DD）
            output_path: 出力ファイルパス

        Returns:
            出力件数
        """
        import csv

        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = """
            SELECT
                r.race_id,
                ra.race_date,
                ra.venue_code,
                ra.race_number,
                r.pit_number,
                r.rank,
                e.racer_name
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            LEFT JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            WHERE ra.race_date BETWEEN ? AND ?
              AND r.is_invalid = 0
            ORDER BY ra.race_date, ra.venue_code, ra.race_number, r.rank
        """

        cursor.execute(query, (start_date, end_date))
        rows = cursor.fetchall()
        cursor.close()

        count = 0

        try:
            with open(output_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)

                # ヘッダー
                writer.writerow(['race_id', 'race_date', 'venue_code', 'race_number', 'pit_number', 'rank', 'racer_name'])

                # データ
                for row in rows:
                    writer.writerow([
                        row['race_id'],
                        row['race_date'],
                        row['venue_code'],
                        row['race_number'],
                        row['pit_number'],
                        row['rank'],
                        row['racer_name']
                    ])
                    count += 1

        except Exception as e:
            print(f"Export error: {e}")
            return 0

        return count


if __name__ == "__main__":
    # テスト
    manager = ResultManager()

    print("=== ResultManager Test ===")
    print("\nテスト用レースID: 1")

    # 現在の結果を取得
    results = manager.get_race_results(1)
    print(f"\n現在の結果: {len(results)}件")
    for r in results:
        print(f"  {r['pit_number']}号艇: {r['rank']}着 ({r['racer_name']})")
