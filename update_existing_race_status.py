"""
既存レースのrace_statusを更新

現在'completed'とマークされている30,330件のレースに対して、
resultsテーブルのデータから正確なrace_statusを判定・更新する
"""

import sqlite3
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

db_path = 'C:/Users/seizo/Desktop/BoatRace/data/boatrace.db'

def update_existing_race_status():
    """既存レースのrace_statusを更新"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 全レースを取得
        cursor.execute('''
            SELECT r.id, r.venue_code, r.race_date, r.race_number, r.race_status, COUNT(res.id) as result_count
            FROM races r
            LEFT JOIN results res ON r.id = res.race_id
            GROUP BY r.id
        ''')

        all_races = cursor.fetchall()
        logger.info(f"総レース数: {len(all_races):,}件")

        # ステータスごとの更新カウント
        status_updates = {
            'completed': 0,
            'cancelled': 0,
            'already_correct': 0
        }

        for race_id, venue_code, race_date, race_number, current_status, result_count in all_races:
            new_status = None

            if result_count >= 6:
                # 完全な結果データがある → completed
                new_status = 'completed'
            elif result_count >= 3:
                # 部分的な結果（3-5艇） → フライングや事故の可能性があるがcompletedとする
                new_status = 'completed'
            elif result_count > 0:
                # 1-2艇のみ → 異常だがとりあえずcompletedにしておく
                new_status = 'completed'
            else:
                # 結果が0件 → cancelled（開催中止と推定）
                new_status = 'cancelled'

            # ステータスが変わる場合のみ更新
            if new_status != current_status:
                cursor.execute('''
                    UPDATE races
                    SET race_status = ?
                    WHERE id = ?
                ''', (new_status, race_id))

                status_updates[new_status] += 1

                if status_updates[new_status] % 100 == 0:
                    logger.info(f"進捗: {new_status}へ更新 = {status_updates[new_status]}件")
            else:
                status_updates['already_correct'] += 1

        conn.commit()

        # 最終統計
        logger.info("\n=== 更新完了 ===")
        logger.info(f"completedへ更新: {status_updates['completed']:,}件")
        logger.info(f"cancelledへ更新: {status_updates['cancelled']:,}件")
        logger.info(f"既に正しい: {status_updates['already_correct']:,}件")

        # 最終的なrace_status分布を表示
        cursor.execute('''
            SELECT race_status, COUNT(*) as count
            FROM races
            GROUP BY race_status
            ORDER BY count DESC
        ''')

        logger.info("\n=== 最終的なrace_status分布 ===")
        for status, count in cursor.fetchall():
            logger.info(f"  {status}: {count:,}件")

    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    logger.info("既存レースのrace_status更新開始\n")
    logger.info("=" * 60)
    update_existing_race_status()
    logger.info("=" * 60)
    logger.info("\n更新完了")
