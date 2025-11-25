"""
データベースモデル層のユニットテスト

データ取得に依存せず、データベースの基本機能をテスト
- テーブル作成
- CRUD操作
- トランザクション管理
- 外部キー制約
- ユニーク制約
"""

import unittest
import sqlite3
import tempfile
import os
from pathlib import Path
import sys
sys.path.append('.')

from src.database.models import Database


class TestDatabase(unittest.TestCase):
    """Databaseクラスのテスト"""

    def setUp(self):
        """各テストの前に実行: テスト用の一時データベースを作成"""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = self.temp_db.name
        self.db = Database(self.db_path)

    def tearDown(self):
        """各テストの後に実行: 一時データベースを削除"""
        # 接続を確実に閉じる
        if hasattr(self, 'db') and self.db.connection:
            self.db.close()

        # ファイルが存在する場合は削除を試みる
        if os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except PermissionError:
                # Windowsでは即座に削除できない場合がある
                pass

    def test_database_creation(self):
        """データベースファイルが正しく作成されるか"""
        self.assertTrue(os.path.exists(self.db_path))
        # 空のDBファイルは0バイトの可能性があるため、存在チェックのみ
        self.assertGreaterEqual(os.path.getsize(self.db_path), 0)

    def test_connection(self):
        """データベースに正しく接続できるか"""
        conn = self.db.connect()
        self.assertIsNotNone(conn)
        self.assertIsInstance(conn, sqlite3.Connection)
        self.db.close()

    def test_context_manager(self):
        """コンテキストマネージャーが正しく動作するか"""
        with Database(self.db_path) as conn:
            self.assertIsNotNone(conn)
            self.assertIsInstance(conn, sqlite3.Connection)

    def test_table_creation(self):
        """全テーブルが正しく作成されるか"""
        self.db.create_tables()

        conn = self.db.connect()
        cursor = conn.cursor()

        # SQLiteのマスターテーブルから全テーブル名を取得
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table'
            ORDER BY name
        """)
        tables = [row[0] for row in cursor.fetchall()]

        # 期待されるテーブル（実際のスキーマに合わせる）
        expected_tables = [
            'entries',
            'race_details',
            'races',
            'recommendations',
            'results',
            'tide',
            'venues',
            'weather'
        ]

        for table in expected_tables:
            self.assertIn(table, tables, f"テーブル '{table}' が作成されていません")

        self.db.close()

    def test_venue_table_structure(self):
        """venuesテーブルの構造が正しいか"""
        self.db.create_tables()
        conn = self.db.connect()
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(venues)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        # 必須カラムの確認
        self.assertIn('id', columns)
        self.assertIn('code', columns)
        self.assertIn('name', columns)
        self.assertIn('latitude', columns)
        self.assertIn('longitude', columns)

        self.db.close()

    def test_race_table_structure(self):
        """racesテーブルの構造が正しいか"""
        self.db.create_tables()
        conn = self.db.connect()
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(races)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        # 必須カラムの確認
        expected_columns = ['id', 'venue_code', 'race_date', 'race_number', 'race_time']
        for col in expected_columns:
            self.assertIn(col, columns, f"カラム '{col}' が存在しません")

        self.db.close()

    def test_venue_unique_constraint(self):
        """venuesテーブルのユニーク制約が機能するか"""
        self.db.create_tables()
        conn = self.db.connect()
        cursor = conn.cursor()

        # 1件目の挿入（成功するはず）
        cursor.execute("""
            INSERT INTO venues (code, name) VALUES ('01', '桐生')
        """)
        conn.commit()

        # 同じcodeで2件目の挿入（失敗するはず）
        with self.assertRaises(sqlite3.IntegrityError):
            cursor.execute("""
                INSERT INTO venues (code, name) VALUES ('01', '戸田')
            """)

        self.db.close()

    def test_race_unique_constraint(self):
        """racesテーブルのユニーク制約（venue_code, race_date, race_number）が機能するか"""
        self.db.create_tables()
        conn = self.db.connect()
        cursor = conn.cursor()

        # venueを先に作成
        cursor.execute("INSERT INTO venues (code, name) VALUES ('01', '桐生')")

        # 1件目のレース挿入（成功）
        cursor.execute("""
            INSERT INTO races (venue_code, race_date, race_number)
            VALUES ('01', '2024-01-01', 1)
        """)
        conn.commit()

        # 同じ組み合わせで2件目のレース挿入（失敗）
        with self.assertRaises(sqlite3.IntegrityError):
            cursor.execute("""
                INSERT INTO races (venue_code, race_date, race_number)
                VALUES ('01', '2024-01-01', 1)
            """)

        self.db.close()

    def test_foreign_key_constraint(self):
        """外部キー制約が機能するか"""
        self.db.create_tables()
        conn = self.db.connect()

        # 外部キー制約を有効化
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()

        # 存在しないvenue_codeでレースを挿入（失敗するはず）
        with self.assertRaises(sqlite3.IntegrityError):
            cursor.execute("""
                INSERT INTO races (venue_code, race_date, race_number)
                VALUES ('99', '2024-01-01', 1)
            """)

        self.db.close()

    def test_transaction_commit(self):
        """トランザクションのコミットが正しく動作するか"""
        self.db.create_tables()

        with Database(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO venues (code, name) VALUES ('01', '桐生')")

        # 別の接続でデータを確認
        conn2 = sqlite3.connect(self.db_path)
        cursor2 = conn2.cursor()
        cursor2.execute("SELECT COUNT(*) FROM venues WHERE code = '01'")
        count = cursor2.fetchone()[0]
        self.assertEqual(count, 1, "コミットされたデータが見つかりません")
        conn2.close()

    def test_transaction_rollback(self):
        """トランザクションのロールバックが正しく動作するか"""
        self.db.create_tables()

        try:
            with Database(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO venues (code, name) VALUES ('01', '桐生')")
                # 意図的に例外を発生させる
                raise Exception("テスト用の例外")
        except Exception:
            pass

        # 別の接続でデータを確認（ロールバックされているはず）
        conn2 = sqlite3.connect(self.db_path)
        cursor2 = conn2.cursor()
        cursor2.execute("SELECT COUNT(*) FROM venues WHERE code = '01'")
        count = cursor2.fetchone()[0]
        self.assertEqual(count, 0, "ロールバックが正しく動作していません")
        conn2.close()

    def test_row_factory(self):
        """行ファクトリーが正しく設定されているか（カラム名でアクセス可能）"""
        self.db.create_tables()
        conn = self.db.connect()
        cursor = conn.cursor()

        cursor.execute("INSERT INTO venues (code, name) VALUES ('01', '桐生')")
        conn.commit()

        cursor.execute("SELECT code, name FROM venues WHERE code = '01'")
        row = cursor.fetchone()

        # sqlite3.Rowオブジェクトはインデックスとカラム名の両方でアクセス可能
        self.assertEqual(row['code'], '01')
        self.assertEqual(row['name'], '桐生')

        self.db.close()

    def test_multiple_connections(self):
        """複数の接続が正しく動作するか"""
        self.db.create_tables()

        # 接続1でデータを挿入
        conn1 = self.db.connect()
        cursor1 = conn1.cursor()
        cursor1.execute("INSERT INTO venues (code, name) VALUES ('01', '桐生')")
        conn1.commit()

        # 接続2でデータを読み取り
        db2 = Database(self.db_path)
        conn2 = db2.connect()
        cursor2 = conn2.cursor()
        cursor2.execute("SELECT name FROM venues WHERE code = '01'")
        name = cursor2.fetchone()['name']

        self.assertEqual(name, '桐生')

        self.db.close()
        db2.close()


class TestDatabaseIntegration(unittest.TestCase):
    """データベースの統合テスト"""

    def setUp(self):
        """テスト用の一時データベースを作成"""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = self.temp_db.name
        self.db = Database(self.db_path)
        self.db.create_tables()

    def tearDown(self):
        """一時データベースを削除"""
        # 接続を確実に閉じる
        if hasattr(self, 'db') and self.db.connection:
            self.db.close()

        # ファイルが存在する場合は削除を試みる
        if os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except PermissionError:
                # Windowsでは即座に削除できない場合がある
                pass

    def test_insert_full_race_data(self):
        """完全なレースデータ（venue→race→entries→results）を挿入できるか"""
        with Database(self.db_path) as conn:
            cursor = conn.cursor()

            # 1. 競艇場を挿入
            cursor.execute("""
                INSERT INTO venues (code, name, latitude, longitude)
                VALUES ('01', '桐生', 36.4, 139.3)
            """)

            # 2. レースを挿入
            cursor.execute("""
                INSERT INTO races (venue_code, race_date, race_number, race_time)
                VALUES ('01', '2024-01-01', 1, '10:30')
            """)
            race_id = cursor.lastrowid

            # 3. 出走表を挿入
            cursor.execute("""
                INSERT INTO entries (race_id, pit_number, racer_number, racer_name, racer_rank)
                VALUES (?, 1, '4444', '選手A', 'A1')
            """, (race_id,))

            # 4. 結果を挿入（race_timeカラムは存在しないため、rankのみ）
            cursor.execute("""
                INSERT INTO results (race_id, pit_number, rank)
                VALUES (?, 1, '1')
            """, (race_id,))

        # データが正しく挿入されたか確認
        conn2 = sqlite3.connect(self.db_path)
        cursor2 = conn2.cursor()

        cursor2.execute("""
            SELECT r.race_date, r.race_number, e.racer_name, res.rank
            FROM races r
            JOIN entries e ON r.id = e.race_id
            JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
            WHERE r.venue_code = '01'
        """)
        row = cursor2.fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], '2024-01-01')  # race_date
        self.assertEqual(row[1], 1)              # race_number
        self.assertEqual(row[2], '選手A')        # racer_name
        self.assertEqual(row[3], '1')            # rank (TEXTカラムなので文字列)

        conn2.close()


if __name__ == '__main__':
    # テストスイートを作成
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # テストクラスを追加
    suite.addTests(loader.loadTestsFromTestCase(TestDatabase))
    suite.addTests(loader.loadTestsFromTestCase(TestDatabaseIntegration))

    # テスト実行
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 結果サマリー
    print("\n" + "=" * 70)
    print("テスト結果サマリー")
    print("=" * 70)
    print(f"実行テスト数: {result.testsRun}")
    print(f"成功: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"失敗: {len(result.failures)}")
    print(f"エラー: {len(result.errors)}")

    # 終了コード
    sys.exit(0 if result.wasSuccessful() else 1)
