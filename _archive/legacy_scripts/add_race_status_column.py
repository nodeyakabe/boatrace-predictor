"""
レースステータスカラムを追加するマイグレーション

開催中止、フライング、事故などのレース状態を記録するため
racesテーブルにrace_statusカラムを追加する
"""

import sqlite3
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db_path = 'C:/Users/seizo/Desktop/BoatRace/data/boatrace.db'

def add_race_status_column():
    """racesテーブルにrace_statusカラムを追加"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # race_statusカラムが存在するか確認
        cursor.execute("PRAGMA table_info(races)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'race_status' in columns:
            logger.info("race_statusカラムは既に存在します")
        else:
            logger.info("race_statusカラムを追加中...")
            cursor.execute('''
                ALTER TABLE races
                ADD COLUMN race_status TEXT DEFAULT 'unknown'
            ''')
            conn.commit()
            logger.info("race_statusカラムを追加しました")

        # 既存データの更新：結果があるレースは'completed'に設定
        logger.info("既存データのステータスを更新中...")
        cursor.execute('''
            UPDATE races
            SET race_status = 'completed'
            WHERE id IN (
                SELECT DISTINCT race_id FROM results
            )
        ''')
        completed_count = cursor.rowcount
        conn.commit()
        logger.info(f"{completed_count}件のレースを'completed'に更新しました")

        # 結果がないレースは'cancelled'と仮定（後で詳細を調査）
        cursor.execute('''
            UPDATE races
            SET race_status = 'cancelled'
            WHERE race_status = 'unknown'
            AND id NOT IN (
                SELECT DISTINCT race_id FROM results
            )
        ''')
        cancelled_count = cursor.rowcount
        conn.commit()
        logger.info(f"{cancelled_count}件のレースを'cancelled'（要確認）に更新しました")

        # 統計を表示
        cursor.execute('''
            SELECT race_status, COUNT(*) as count
            FROM races
            GROUP BY race_status
        ''')
        stats = cursor.fetchall()
        logger.info("\nレースステータス統計:")
        for status, count in stats:
            logger.info(f"  {status}: {count:,}件")

    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    logger.info("レースステータスカラム追加スクリプト開始")
    add_race_status_column()
    logger.info("完了")
