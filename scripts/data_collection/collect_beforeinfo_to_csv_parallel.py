"""
直前情報CSV保存スクリプト（並列処理版）

prev_race_rank等の直前情報をCSV方式で収集します。
DB競合を避けるため、CSV形式で保存します。

使用例:
    python scripts/data_collection/collect_beforeinfo_to_csv_parallel.py --start 2020-01-01 --end 2023-12-31 --output data/csv/beforeinfo/2020-2023

    # 並列数を指定
    python scripts/data_collection/collect_beforeinfo_to_csv_parallel.py --start 2024-01-01 --end 2025-12-31 --workers 12 --output data/csv/beforeinfo/2024-2025

特徴:
- CSV方式でDB競合を回避
- 欠損チェックで未取得レースのみ対象
- シグナルハンドラで優雅な終了
- バッチコミットで高速化
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import os
import csv
import sqlite3
import argparse
from datetime import datetime
import time
import logging
import signal
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, Event
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.scraper.beforeinfo_scraper import BeforeInfoScraper

# スレッドローカルストレージ
thread_local = threading.local()

def get_scraper():
    """スレッドローカルなScraperインスタンスを取得"""
    if not hasattr(thread_local, 'scraper'):
        thread_local.scraper = BeforeInfoScraper(delay=0.3)
    return thread_local.scraper


class ParallelBeforeinfoCsvFetcher:
    """CSV出力方式の並列直前情報取得クラス"""

    def __init__(self, db_path, output_dir, delay=0.3, max_workers=12, batch_size=50):
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
        self.csv_path = self.output_dir / 'beforeinfo.csv'

        # 統計情報
        self.success_count = 0
        self.error_count = 0
        self.unpublished_count = 0
        self.lock = Lock()

        # バッチバッファ
        self.batch_buffer = []
        self.buffer_lock = Lock()

        # ロガー
        self.logger = None

        # 終了フラグ
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
        """シグナルハンドラ設定"""
        def signal_handler(signum, frame):
            if not self.is_shutting_down:
                self.logger.warning("\n" + "=" * 80)
                self.logger.warning("終了シグナル受信。優雅にシャットダウンしています...")
                self.logger.warning("データを保存中です。強制終了しないでください。")
                self.logger.warning("=" * 80)
                self.is_shutting_down = True
                self.shutdown_event.set()

        signal.signal(signal.SIGINT, signal_handler)
        try:
            signal.signal(signal.SIGTERM, signal_handler)
        except:
            pass  # Windows環境ではSIGTERMが使えない場合がある
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
                  SELECT 1 FROM race_details rd
                  WHERE rd.race_id = r.id AND rd.prev_race_rank IS NOT NULL
                  LIMIT 1
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

        write_header = not self.csv_path.exists()

        try:
            with open(self.csv_path, 'a', newline='', encoding='utf-8') as f:
                fieldnames = [
                    'race_id', 'pit_number',
                    'exhibition_time', 'tilt_angle', 'parts_replacement',
                    'adjusted_weight', 'st_time', 'exhibition_course',
                    'prev_race_course', 'prev_race_st', 'prev_race_rank',
                    'fetched_at'
                ]
                writer = csv.DictWriter(f, fieldnames=fieldnames)

                if write_header:
                    writer.writeheader()

                for race_id, beforeinfo_data in batch_data:
                    fetched_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                    exhibition_times = beforeinfo_data.get('exhibition_times', {})
                    tilt_angles = beforeinfo_data.get('tilt_angles', {})
                    parts = beforeinfo_data.get('parts_replacements', {})
                    weights = beforeinfo_data.get('adjusted_weights', {})
                    st_times = beforeinfo_data.get('start_timings', {})
                    courses = beforeinfo_data.get('exhibition_courses', {})
                    prev_race = beforeinfo_data.get('previous_race', {})

                    for pit in range(1, 7):
                        prev_data = prev_race.get(pit, {})

                        writer.writerow({
                            'race_id': race_id,
                            'pit_number': pit,
                            'exhibition_time': exhibition_times.get(pit),
                            'tilt_angle': tilt_angles.get(pit),
                            'parts_replacement': parts.get(pit),
                            'adjusted_weight': weights.get(pit),
                            'st_time': st_times.get(pit),
                            'exhibition_course': courses.get(pit),
                            'prev_race_course': prev_data.get('course'),
                            'prev_race_st': prev_data.get('st'),
                            'prev_race_rank': prev_data.get('rank'),
                            'fetched_at': fetched_at
                        })

            self.logger.info(f"✅ バッチ保存完了: {len(batch_data)}レース")

        except Exception as e:
            self.logger.error(f"❌ CSV保存エラー: {e}")

    def fetch_one_race(self, race_info):
        """1レース分の直前情報を取得"""
        race_id, venue_code, race_date, race_number = race_info

        if self.shutdown_event.is_set():
            return None

        scraper = get_scraper()

        try:
            date_str = race_date.replace('-', '')
            beforeinfo = scraper.get_race_beforeinfo(
                venue_code=f"{int(venue_code):02d}",
                date_str=date_str,
                race_number=race_number
            )

            if beforeinfo and beforeinfo.get('is_published'):
                with self.lock:
                    self.success_count += 1
                return (race_id, beforeinfo)
            else:
                with self.lock:
                    self.unpublished_count += 1
                return None

        except Exception as e:
            with self.lock:
                self.error_count += 1
            self.logger.debug(f"エラー race_id={race_id}: {str(e)[:100]}")
            return None

    def run(self, start_date, end_date):
        """メイン実行"""
        # ログ設定
        log_file = self.output_dir / f'collect_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
        self.setup_logging(log_file)
        self.setup_signal_handlers()

        self.logger.info("=" * 80)
        self.logger.info("直前情報CSV収集（並列処理版）")
        self.logger.info("=" * 80)
        self.logger.info(f"対象期間: {start_date} ～ {end_date}")
        self.logger.info(f"出力先: {self.csv_path}")
        self.logger.info(f"並列数: {self.max_workers}")
        self.logger.info("=" * 80)

        # 未取得レース取得
        self.logger.info("未取得レースを確認中...")
        races = self.get_races_to_fetch(start_date, end_date)
        self.logger.info(f"対象レース数: {len(races):,}件")

        if not races:
            self.logger.info("処理対象がありません")
            return True

        # 確認
        try:
            if sys.stdin.isatty():
                response = input("\n収集を開始しますか？ (y/N): ")
                if response.lower() != 'y':
                    self.logger.info("キャンセルしました")
                    return False
        except (EOFError, OSError):
            self.logger.info("（バックグラウンド実行: 自動開始）")

        # 並列収集開始
        self.logger.info("\n収集開始...")
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(self.fetch_one_race, race): race for race in races}

            for i, future in enumerate(as_completed(futures), 1):
                if self.shutdown_event.is_set():
                    self.logger.warning("シャットダウン中...")
                    break

                result = future.result()

                if result:
                    with self.buffer_lock:
                        self.batch_buffer.append(result)

                        if len(self.batch_buffer) >= self.batch_size:
                            self.save_batch_to_csv(self.batch_buffer)
                            self.batch_buffer = []

                # 進捗表示
                if i % 100 == 0 or i == len(races):
                    elapsed = time.time() - start_time
                    speed = i / elapsed if elapsed > 0 else 0
                    eta = (len(races) - i) / speed if speed > 0 else 0

                    self.logger.info(
                        f"進捗: {i:,}/{len(races):,} ({i/len(races)*100:.1f}%) | "
                        f"成功: {self.success_count:,} | エラー: {self.error_count:,} | "
                        f"速度: {speed:.1f}件/秒 | 残り: {eta/60:.0f}分"
                    )

        # 残りのバッチを保存
        if self.batch_buffer:
            self.save_batch_to_csv(self.batch_buffer)

        # 最終レポート
        elapsed = time.time() - start_time
        self.logger.info("\n" + "=" * 80)
        self.logger.info("収集完了")
        self.logger.info("=" * 80)
        self.logger.info(f"処理時間: {elapsed/60:.1f}分")
        self.logger.info(f"成功: {self.success_count:,}件")
        self.logger.info(f"エラー: {self.error_count:,}件")
        self.logger.info(f"未公開: {self.unpublished_count:,}件")
        self.logger.info(f"処理速度: {len(races)/elapsed:.2f}件/秒")
        self.logger.info(f"\n出力ファイル: {self.csv_path}")
        self.logger.info("=" * 80)

        return True


def main():
    parser = argparse.ArgumentParser(description='直前情報CSV収集（並列処理版）')
    parser.add_argument('--start', type=str, required=True, help='開始日（YYYY-MM-DD）')
    parser.add_argument('--end', type=str, required=True, help='終了日（YYYY-MM-DD）')
    parser.add_argument('--output', type=str, required=True, help='出力ディレクトリ')
    parser.add_argument('--workers', type=int, default=12, help='並列ワーカー数')
    parser.add_argument('--batch-size', type=int, default=50, help='バッチサイズ')

    args = parser.parse_args()

    db_path = PROJECT_ROOT / "data" / "boatrace.db"

    fetcher = ParallelBeforeinfoCsvFetcher(
        db_path=db_path,
        output_dir=args.output,
        max_workers=args.workers,
        batch_size=args.batch_size
    )

    success = fetcher.run(args.start, args.end)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
