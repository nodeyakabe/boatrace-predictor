"""
2020～2024年オッズデータ取得スクリプト（バックグラウンド実行対応）

特徴:
- バックグラウンドで安全に実行可能
- 進捗をログファイルに保存
- 中断しても再開可能（未取得のみ処理）
- 定期的にDB保存してデータ損失を防止
"""
import os
import sys
import sqlite3
import argparse
from datetime import datetime
import time
import logging

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from src.scraper.odds_scraper import OddsScraper


def setup_logging(log_file):
    """ロギング設定"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)


def get_races_to_fetch(db_path, start_date, end_date):
    """未取得レースを取得"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    query = """
        SELECT r.id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date BETWEEN ? AND ?
          AND NOT EXISTS (
              SELECT 1 FROM trifecta_odds t WHERE t.race_id = r.id
          )
        ORDER BY r.race_date, r.venue_code, r.race_number
    """
    cursor.execute(query, (start_date, end_date))
    races = cursor.fetchall()
    conn.close()
    return races


def save_odds_to_db(db_path, race_id, odds_data):
    """オッズをDBに保存"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for combination, odds_value in odds_data.items():
        cursor.execute("""
            INSERT OR REPLACE INTO trifecta_odds (race_id, combination, odds, fetched_at)
            VALUES (?, ?, ?, datetime('now'))
        """, (race_id, combination, odds_value))

    conn.commit()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description='2020～2024年オッズ取得（バックグラウンド実行）')
    parser.add_argument('--db', default='data/boatrace.db')
    parser.add_argument('--start-date', default='2020-01-01', help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end-date', default='2024-12-31', help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--delay', type=float, default=0.5, help='リクエスト間隔（秒）')
    parser.add_argument('--log-file', default='logs/odds_fetch_2020_2024.log', help='ログファイルパス')
    parser.add_argument('--progress-interval', type=int, default=100, help='進捗表示間隔')

    args = parser.parse_args()

    # ログディレクトリ作成
    log_dir = os.path.dirname(args.log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)

    logger = setup_logging(args.log_file)

    db_path = os.path.join(PROJECT_ROOT, args.db)
    if not os.path.exists(db_path):
        logger.error(f"DB not found: {db_path}")
        return

    logger.info("=" * 80)
    logger.info("2020～2024年オッズデータ取得開始")
    logger.info(f"期間: {args.start_date} ～ {args.end_date}")
    logger.info(f"リクエスト間隔: {args.delay}秒")
    logger.info(f"ログファイル: {args.log_file}")
    logger.info("=" * 80)

    # 未取得レースを取得
    logger.info("未取得レースを検索中...")
    races = get_races_to_fetch(db_path, args.start_date, args.end_date)
    total = len(races)

    logger.info(f"対象レース数: {total:,}件")
    if total == 0:
        logger.info("取得対象なし。終了します。")
        return

    # 推定時間を計算
    estimated_hours = (total * args.delay) / 3600
    logger.info(f"推定処理時間: {estimated_hours:.1f}時間")

    # スクレイパー初期化
    scraper = OddsScraper(delay=args.delay, max_retries=3)

    success_count = 0
    error_count = 0
    start_time = time.time()
    last_log_time = start_time

    # 逐次処理
    for i, (race_id, venue_code, race_date, race_number) in enumerate(races):
        date_str = race_date.replace('-', '')

        try:
            # オッズ取得
            odds_data = scraper.get_trifecta_odds(venue_code, date_str, race_number)

            if odds_data:
                # DB保存
                save_odds_to_db(db_path, race_id, odds_data)
                success_count += 1
            else:
                error_count += 1
                logger.warning(f"取得失敗: {race_date} {venue_code.zfill(2)}R{race_number}")

        except Exception as e:
            error_count += 1
            logger.error(f"エラー発生: {race_date} {venue_code.zfill(2)}R{race_number} - {str(e)}")

        # 進捗表示
        current_time = time.time()
        if (i + 1) % args.progress_interval == 0 or (i + 1) == total:
            elapsed = current_time - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            remaining = (total - i - 1) / rate if rate > 0 else 0

            progress_pct = ((i + 1) / total) * 100
            logger.info(
                f"進捗: {i+1:,}/{total:,} ({progress_pct:.1f}%) | "
                f"成功: {success_count:,}, エラー: {error_count:,} | "
                f"速度: {rate:.2f}件/秒 | 残り: {remaining/3600:.1f}時間"
            )
            last_log_time = current_time

        # 1時間ごとに詳細ログ
        if current_time - last_log_time >= 3600:
            logger.info(f"[定期報告] 経過時間: {elapsed/3600:.1f}時間, 処理済み: {i+1:,}/{total:,}")
            last_log_time = current_time

    elapsed = time.time() - start_time
    logger.info("\n" + "=" * 80)
    logger.info("処理完了")
    logger.info(f"  成功: {success_count:,}レース")
    logger.info(f"  エラー: {error_count:,}レース")
    logger.info(f"  処理時間: {elapsed/60:.1f}分 ({elapsed/3600:.1f}時間)")
    logger.info(f"  平均速度: {total/elapsed:.2f}件/秒")
    logger.info("=" * 80)


if __name__ == '__main__':
    main()
