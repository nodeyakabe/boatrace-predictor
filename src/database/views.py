"""
データベースビュー管理モジュール

アプリケーション用のSQLビューを作成・管理します。
元のテーブル構造を変更せず、UI層で使いやすい仮想テーブルを提供します。
"""

import sqlite3
from typing import Optional


class DatabaseViewManager:
    """データベースビュー管理クラス"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def create_all_views(self):
        """すべてのアプリケーション用ビューを作成"""
        conn = sqlite3.connect(self.db_path)
        try:
            self._create_race_details_extended(conn)
            self._create_racer_performance_summary(conn)
            self._create_venue_statistics_view(conn)
            conn.commit()
            print("[OK] All database views created successfully")
        except Exception as e:
            print(f"[ERROR] Error creating views: {e}")
            conn.rollback()
        finally:
            conn.close()

    def drop_all_views(self):
        """すべてのビューを削除"""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("DROP VIEW IF EXISTS race_details_extended")
            conn.execute("DROP VIEW IF EXISTS racer_performance_summary")
            conn.execute("DROP VIEW IF EXISTS venue_statistics_view")
            conn.commit()
            print("[OK] All views dropped successfully")
        except Exception as e:
            print(f"[ERROR] Error dropping views: {e}")
            conn.rollback()
        finally:
            conn.close()

    def _create_race_details_extended(self, conn: sqlite3.Connection):
        """
        race_details_extended ビュー

        race_details + results を結合し、UIで使いやすい拡張ビューを作成。
        kimarite（決まり手）や rank（着順）なども含めて一つのビューで取得可能。
        """
        conn.execute("""
            CREATE VIEW IF NOT EXISTS race_details_extended AS
            SELECT
                rd.id as detail_id,
                rd.race_id,
                rd.pit_number,
                rd.exhibition_time,
                rd.tilt_angle,
                rd.parts_replacement,
                rd.actual_course,
                rd.st_time,
                res.rank,
                res.kimarite,
                res.is_invalid,
                res.trifecta_odds,
                r.race_date,
                r.venue_code,
                r.race_number,
                r.title,
                r.grade,
                e.racer_number,
                e.racer_name,
                e.motor_number,
                e.boat_number
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            LEFT JOIN entries e ON rd.race_id = e.race_id AND rd.pit_number = e.pit_number
        """)
        print("  [+] race_details_extended view created")

    def _create_racer_performance_summary(self, conn: sqlite3.Connection):
        """
        racer_performance_summary ビュー

        選手ごとの成績サマリーを集計したビュー。
        総レース数、勝利数、連対数、3連対数などを事前計算。
        """
        conn.execute("""
            CREATE VIEW IF NOT EXISTS racer_performance_summary AS
            SELECT
                e.racer_number,
                e.racer_name,
                COUNT(DISTINCT r.id) as total_races,
                SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN CAST(res.rank AS INTEGER) <= 2 THEN 1 ELSE 0 END) as top2,
                SUM(CASE WHEN CAST(res.rank AS INTEGER) <= 3 THEN 1 ELSE 0 END) as top3,
                AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) as win_rate,
                AVG(CASE WHEN CAST(res.rank AS INTEGER) <= 2 THEN 1.0 ELSE 0.0 END) as place_rate_2,
                AVG(CASE WHEN CAST(res.rank AS INTEGER) <= 3 THEN 1.0 ELSE 0.0 END) as place_rate_3,
                AVG(rd.st_time) as avg_st_time,
                MIN(r.race_date) as first_race_date,
                MAX(r.race_date) as last_race_date
            FROM entries e
            JOIN races r ON e.race_id = r.id
            LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
            LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
            WHERE res.rank IS NOT NULL
            GROUP BY e.racer_number, e.racer_name
        """)
        print("  [+] racer_performance_summary view created")

    def _create_venue_statistics_view(self, conn: sqlite3.Connection):
        """
        venue_statistics_view ビュー

        競艇場ごとの統計情報を集計したビュー。
        コース別勝率、決まり手分布、平均配当などを事前計算。
        """
        conn.execute("""
            CREATE VIEW IF NOT EXISTS venue_statistics_view AS
            SELECT
                r.venue_code,
                COUNT(DISTINCT r.id) as total_races,
                -- 1号艇逃げ率
                AVG(CASE WHEN rd.actual_course = 1 AND res.rank = '1' THEN 1.0 ELSE 0.0 END) as course1_win_rate,
                -- イン勝率（1-3コース）
                AVG(CASE WHEN rd.actual_course IN (1, 2, 3) AND res.rank = '1' THEN 1.0 ELSE 0.0 END) as inside_win_rate,
                -- 平均配当
                AVG(res.trifecta_odds) as avg_trifecta_odds,
                -- 万舟率
                AVG(CASE WHEN res.trifecta_odds >= 10000 THEN 1.0 ELSE 0.0 END) as high_payout_rate,
                -- 最も多い決まり手（サブクエリで取得）
                (
                    SELECT res2.kimarite
                    FROM results res2
                    JOIN races r2 ON res2.race_id = r2.id
                    WHERE r2.venue_code = r.venue_code
                      AND res2.rank = '1'
                      AND res2.kimarite IS NOT NULL
                    GROUP BY res2.kimarite
                    ORDER BY COUNT(*) DESC
                    LIMIT 1
                ) as most_common_kimarite,
                MIN(r.race_date) as first_race_date,
                MAX(r.race_date) as last_race_date
            FROM races r
            LEFT JOIN race_details rd ON r.id = rd.race_id
            LEFT JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
            WHERE res.rank = '1'
            GROUP BY r.venue_code
        """)
        print("  [+] venue_statistics_view view created")


def initialize_views(db_path: str):
    """
    データベースビューを初期化

    アプリケーション起動時に呼び出して、必要なビューを作成します。

    Args:
        db_path: データベースファイルのパス
    """
    manager = DatabaseViewManager(db_path)
    manager.create_all_views()


def refresh_views(db_path: str):
    """
    ビューをリフレッシュ（削除してから再作成）

    Args:
        db_path: データベースファイルのパス
    """
    manager = DatabaseViewManager(db_path)
    manager.drop_all_views()
    manager.create_all_views()


if __name__ == "__main__":
    # テスト実行
    import sys
    import os

    # プロジェクトルートをパスに追加
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

    from config.settings import DATABASE_PATH

    print(f"Initializing views for database: {DATABASE_PATH}")
    initialize_views(DATABASE_PATH)
