"""
オッズデータCSV保存スクリプト（並列処理版）

大量データ向けにCSV方式でオッズを収集します。
DBで欠損しているレースのみを対象に、CSV形式で保存します。

使用例:
    python scripts/data_collection/fetch_odds_to_csv_parallel.py --start-date 2023-01-01 --end-date 2023-12-31 --output data/csv/odds/2023

    # 並列数を指定
    python scripts/data_collection/fetch_odds_to_csv_parallel.py --start-date 2020-01-01 --end-date 2020-12-31 --workers 10 --output data/csv/odds/2020

改善内容:
- CSV方式で大量データに対応
- DBチェックで欠損レースのみ取得
- スクレイパープーリングで高速化
- シグナルハンドラで優雅な終了
"""
import os
import sys
import csv
import sqlite3
import argparse
from datetime import datetime
import time
import logging
import signal
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, Event
import queue
from pathlib import Path

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.scraper.odds_scraper import OddsScraper


class ParallelOddsCsvFetcher:
    """CSV出力方式の並列オッズ取得クラス"""

    def __init__(self, db_path, output_dir, delay=0.3, max_workers=10, batch_size=100):
        """
        初期化

        Args:
            db_path: データベースパス（欠損チェック用）
            output_dir: CSV出力ディレクトリ
            delay: 各スレッドのリクエスト間隔（秒）
            max_workers: 並列スレッド数
            batch_size: バッチ保存サイズ
        """
        self.db_path = db_path
        self.output_dir = Path(output_dir)
        self.delay = delay
        self.max_workers = max_workers
        self.batch_size = batch_size

        # 出力ディレクトリ作成
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # CSVファイルパス
        self.csv_path = self.output_dir / 'trifecta_odds.csv'

        # 統計情報
        self.success_count = 0
        self.error_count = 0
        self.lock = Lock()

        # バッチバッファ
        self.batch_buffer = []
        self.buffer_lock = Lock()

        # ロガー
        self.logger = None

        # 終了フラグ（シグナルハンドラ用）
        self.shutdown_event = Event()
        self.is_shutting_down = False

    def setup_logging(self, log_file):
        """ロギング設定"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8', mode='a'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
        return self.logger

    def setup_signal_handlers(self):
        """シグナルハンドラ設定（優雅な終了）"""
        def signal_handler(signum, frame):
            if not self.is_shutting_down:
                self.logger.warning("\n" + "=" * 80)
                self.logger.warning("終了シグナル受信。優雅にシャットダウンしています...")
                self.logger.warning("データを保存中です。強制終了しないでください。")
                self.logger.warning("=" * 80)
                self.is_shutting_down = True
                self.shutdown_event.set()

        # Ctrl+C (SIGINT) および SIGTERM をキャッチ
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        self.logger.info("シグナルハンドラ設定完了（Ctrl+Cで優雅に終了）")

    def get_races_to_fetch(self, start_date, end_date):
        """未取得レースを取得（DBチェック）"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
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

    def save_batch_to_csv(self, batch_data):
        """バッチデータをCSVに保存"""
        if not batch_data:
            return

        # ファイルが存在しない場合はヘッダーを書き込む
        write_header = not self.csv_path.exists()

        try:
            with open(self.csv_path, 'a', newline='', encoding='utf-8') as f:
                fieldnames = ['race_id', 'combination', 'odds', 'fetched_at']
                writer = csv.DictWriter(f, fieldnames=fieldnames)

                if write_header:
                    writer.writeheader()

                for race_id, odds_data in batch_data:
                    fetched_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    for combination, odds_value in odds_data.items():
                        writer.writerow({
                            'race_id': race_id,
                            'combination': combination,
                            'odds': odds_value,
                            'fetched_at': fetched_at
                        })

        except Exception as e:
            self.logger.error(f"CSV保存エラー: {e}")

    def fetch_single_race(self, race_info, scraper):
        """単一レースのオッズを取得"""
        # 終了フラグチェック
        if self.shutdown_event.is_set():
            return False, "シャットダウン中"

        race_id, venue_code, race_date, race_number = race_info
        date_str = race_date.replace('-', '')

        try:
            # オッズ取得
            odds_data = scraper.get_trifecta_odds(venue_code, date_str, race_number)

            if odds_data:
                # バッファに追加
                with self.buffer_lock:
                    self.batch_buffer.append((race_id, odds_data))

                    # バッチサイズに達したら保存
                    if len(self.batch_buffer) >= self.batch_size:
                        batch_to_save = self.batch_buffer.copy()
                        self.batch_buffer.clear()
                        self.save_batch_to_csv(batch_to_save)

                with self.lock:
                    self.success_count += 1

                return True, None
            else:
                with self.lock:
                    self.error_count += 1
                return False, f"オッズ取得失敗: {race_date} {venue_code.zfill(2)}R{race_number}"

        except Exception as e:
            with self.lock:
                self.error_count += 1
            return False, f"エラー: {race_date} {venue_code.zfill(2)}R{race_number} - {str(e)}"

    def run(self, start_date, end_date, log_file, progress_interval=100):
        """並列処理実行"""
        self.logger = self.setup_logging(log_file)

        # シグナルハンドラ設定
        self.setup_signal_handlers()

        self.logger.info("=" * 80)
        self.logger.info("オッズデータCSV保存（並列処理版）")
        self.logger.info(f"期間: {start_date} ～ {end_date}")
        self.logger.info(f"出力先: {self.csv_path}")
        self.logger.info(f"並列スレッド数: {self.max_workers}")
        self.logger.info(f"リクエスト間隔: {self.delay}秒/スレッド")
        self.logger.info(f"バッチサイズ: {self.batch_size}")
        self.logger.info(f"ログファイル: {log_file}")
        self.logger.info("=" * 80)

        # 未取得レースを取得
        self.logger.info("DBチェック: 欠損レースを検索中...")
        races = self.get_races_to_fetch(start_date, end_date)
        total = len(races)

        self.logger.info(f"対象レース数: {total:,}件（DBに存在しないレースのみ）")
        if total == 0:
            self.logger.info("取得対象なし。終了します。")
            return

        # 推定時間を計算（並列処理考慮）
        estimated_hours = (total * self.delay) / (3600 * self.max_workers)
        self.logger.info(f"推定処理時間: {estimated_hours:.1f}時間（並列処理{self.max_workers}スレッド）")
        self.logger.info("並列処理を開始します...")

        start_time = time.time()
        processed = 0

        try:
            self.logger.info("スクレイパーインスタンスを作成中...")
            # 並列処理実行
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # 各スレッドに専用のスクレイパーを作成
                scrapers = {i: OddsScraper(delay=self.delay, max_retries=2) for i in range(self.max_workers)}
                self.logger.info(f"{len(scrapers)}個のスクレイパーインスタンス作成完了")
                scraper_queue = queue.Queue()
                for scraper in scrapers.values():
                    scraper_queue.put(scraper)

                # タスクを投入
                self.logger.info("タスクを投入中...")
                futures = []
                for race_info in races:
                    # 終了フラグチェック
                    if self.shutdown_event.is_set():
                        self.logger.warning("新規タスクの投入を停止します")
                        break

                    scraper = scraper_queue.get()
                    future = executor.submit(self.fetch_single_race, race_info, scraper)
                    future.add_done_callback(lambda f, s=scraper: scraper_queue.put(s))
                    futures.append(future)

                self.logger.info(f"{len(futures)}件のタスク投入完了。処理を開始します...")

                # 進捗監視
                for future in as_completed(futures):
                    processed += 1

                    try:
                        success, error_msg = future.result()
                        if not success and error_msg:
                            self.logger.warning(error_msg)
                    except Exception as e:
                        self.logger.error(f"タスク実行エラー: {e}")

                    # 進捗表示
                    if processed % progress_interval == 0 or processed == total or processed == 1:
                        elapsed = time.time() - start_time
                        rate = processed / elapsed if elapsed > 0 else 0
                        remaining = (total - processed) / rate if rate > 0 else 0
                        progress_pct = (processed / total) * 100

                        self.logger.info(
                            f"進捗: {processed:,}/{total:,} ({progress_pct:.1f}%) | "
                            f"成功: {self.success_count:,}, エラー: {self.error_count:,} | "
                            f"速度: {rate:.2f}件/秒 ({rate*60:.1f}件/分) | 残り: {remaining/3600:.1f}時間"
                        )

                    # 終了フラグチェック
                    if self.shutdown_event.is_set():
                        self.logger.warning("シャットダウン処理を開始します")
                        break

        except Exception as e:
            self.logger.error(f"実行エラー: {e}")
            import traceback
            traceback.print_exc()

        finally:
            # 残りのバッファを保存
            self.logger.info("残りのバッファデータをCSV保存中...")
            if self.batch_buffer:
                with self.buffer_lock:
                    batch_to_save = self.batch_buffer.copy()
                    self.batch_buffer.clear()
                self.save_batch_to_csv(batch_to_save)

            elapsed = time.time() - start_time
            self.logger.info("\n" + "=" * 80)
            if self.shutdown_event.is_set():
                self.logger.info("中断完了（データは安全に保存されました）")
            else:
                self.logger.info("処理完了")
            self.logger.info(f"  成功: {self.success_count:,}レース")
            self.logger.info(f"  エラー: {self.error_count:,}レース")
            self.logger.info(f"  処理時間: {elapsed/60:.1f}分 ({elapsed/3600:.2f}時間)")
            if processed > 0:
                self.logger.info(f"  平均速度: {processed/elapsed:.2f}件/秒 ({processed/(elapsed/60):.1f}件/分)")
            self.logger.info(f"  出力ファイル: {self.csv_path.absolute()}")
            self.logger.info("=" * 80)


def main():
    parser = argparse.ArgumentParser(description='オッズデータCSV保存（並列処理版）')
    parser.add_argument('--db', default='data/boatrace.db', help='データベースパス（欠損チェック用）')
    parser.add_argument('--start-date', required=True, help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end-date', required=True, help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--output', required=True, help='CSV出力ディレクトリ')
    parser.add_argument('--delay', type=float, default=0.3, help='リクエスト間隔（秒/スレッド）')
    parser.add_argument('--workers', type=int, default=10, help='並列スレッド数')
    parser.add_argument('--batch-size', type=int, default=100, help='バッチ保存サイズ')
    parser.add_argument('--log-file', default='logs/odds_csv_fetch.log', help='ログファイルパス')
    parser.add_argument('--progress-interval', type=int, default=100, help='進捗表示間隔')

    args = parser.parse_args()

    # ログディレクトリ作成
    log_dir = os.path.dirname(args.log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)

    db_path = os.path.join(PROJECT_ROOT, args.db)
    if not os.path.exists(db_path):
        print(f"DB not found: {db_path}")
        return

    # 並列処理実行
    fetcher = ParallelOddsCsvFetcher(
        db_path=db_path,
        output_dir=args.output,
        delay=args.delay,
        max_workers=args.workers,
        batch_size=args.batch_size
    )

    fetcher.run(
        start_date=args.start_date,
        end_date=args.end_date,
        log_file=args.log_file,
        progress_interval=args.progress_interval
    )


if __name__ == '__main__':
    main()
