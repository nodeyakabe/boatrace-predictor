# -*- coding: utf-8 -*-
"""
データ収集スクリプト テンプレート

このテンプレートは以下のベストプラクティスを実装しています:
1. 開催スケジュール確認 - 無駄なリクエストを削減
2. 既存データチェック - 重複取得を回避
3. エラー種別分類 - データなし vs エラーを明確に区別
4. リトライ機能 - 一時的なエラーからの回復
5. UPSERT実装 - データ整合性の維持
6. バッチ処理 - DB負荷軽減と一貫性確保
7. 進捗表示 - 長時間処理の状態把握
8. ログ出力 - トラブルシューティング支援

使用方法:
    python scripts/data_collection/your_script.py --start 2024-01-01 --end 2024-12-31

作成時の注意:
    - このテンプレートをコピーして必要な部分を修正
    - fetch_single_item() と save_batch() を実際のロジックに置き換え
    - 適切なテーブル名とカラムに変更
"""

import sys
import os
import io
import argparse
import sqlite3
import time
import logging
import signal
import threading
from pathlib import Path
from datetime import datetime, timedelta
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue

# Windows文字コード対策
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# プロジェクト固有のインポート（必要に応じて変更）
from src.scraper.schedule_scraper import ScheduleScraper
# from src.scraper.your_scraper import YourScraper  # 実際のスクレイパー


# =============================================================================
# 設定
# =============================================================================

DB_PATH = PROJECT_ROOT / 'data' / 'boatrace.db'
LOG_DIR = PROJECT_ROOT / 'logs'
LOG_DIR.mkdir(exist_ok=True)

# 並列処理設定
DEFAULT_WORKERS = 8
DEFAULT_BATCH_SIZE = 100
DEFAULT_DELAY = 0.3

# リトライ設定
MAX_RETRIES = 3
RETRY_BASE_WAIT = 1.0  # 秒


# =============================================================================
# エラー分類
# =============================================================================

class FetchResult(Enum):
    """取得結果の分類"""
    SUCCESS = "success"           # 成功
    NO_DATA = "no_data"           # データなし（開催なし等、正常）
    NETWORK_ERROR = "network"     # ネットワークエラー（要リトライ）
    TIMEOUT = "timeout"           # タイムアウト（要リトライ）
    SERVER_ERROR = "server"       # サーバーエラー（要リトライ）
    PARSE_ERROR = "parse"         # パースエラー（データ形式問題）


# =============================================================================
# ロガー設定
# =============================================================================

def setup_logger(name: str) -> logging.Logger:
    """ロガーを設定"""
    log_file = LOG_DIR / f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # ファイルハンドラー
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))

    # コンソールハンドラー
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


# =============================================================================
# スレッドローカルストレージ
# =============================================================================

thread_local = threading.local()


def get_session():
    """スレッドローカルなセッションを取得（HTTPリクエスト用）"""
    import requests
    if not hasattr(thread_local, "session"):
        thread_local.session = requests.Session()
        thread_local.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    return thread_local.session


# =============================================================================
# 1. 開催スケジュール取得
# =============================================================================

def get_schedule_for_period(start_date: str, end_date: str, logger: logging.Logger) -> dict:
    """
    期間内の開催スケジュールを取得

    Args:
        start_date: 開始日 (YYYY-MM-DD)
        end_date: 終了日 (YYYY-MM-DD)
        logger: ロガー

    Returns:
        dict: {
            '20240101': ['01', '05', '10', ...],  # その日に開催している会場リスト
            '20240102': ['02', '06', '12', ...],
            ...
        }
    """
    logger.info("開催スケジュールを取得中...")

    scraper = ScheduleScraper()
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')

    venue_schedule = scraper.get_schedule_for_period(start_dt, end_dt)
    scraper.close()

    # 会場→日付 を 日付→会場 に変換
    date_schedule = {}
    for venue_code, dates in venue_schedule.items():
        for date_str in dates:
            if date_str not in date_schedule:
                date_schedule[date_str] = []
            date_schedule[date_str].append(venue_code)

    # 各日付の会場リストをソート
    for date_str in date_schedule:
        date_schedule[date_str].sort()

    # 統計表示
    total_venue_days = sum(len(venues) for venues in date_schedule.values())
    days_count = len(date_schedule)
    avg_venues = total_venue_days / days_count if days_count > 0 else 0

    logger.info(f"  期間: {start_date} - {end_date}")
    logger.info(f"  開催日数: {days_count}日")
    logger.info(f"  総会場日数: {total_venue_days} (平均 {avg_venues:.1f}会場/日)")

    return date_schedule


# =============================================================================
# 2. 既存データチェック
# =============================================================================

def get_existing_data(db_path: Path, start_date: str, end_date: str) -> set:
    """
    既に収集済みのデータを取得

    Args:
        db_path: データベースパス
        start_date: 開始日 (YYYY-MM-DD)
        end_date: 終了日 (YYYY-MM-DD)

    Returns:
        set: 収集済みの識別子セット（例: race_id, (venue_code, date)等）
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 例: race_idベースでのチェック
    # 実際のテーブル・カラムに合わせて変更してください
    cursor.execute("""
        SELECT id FROM races
        WHERE race_date BETWEEN ? AND ?
    """, (start_date, end_date))

    existing = set(row[0] for row in cursor.fetchall())
    conn.close()

    return existing


def get_uncollected_items(db_path: Path, start_date: str, end_date: str, logger: logging.Logger) -> list:
    """
    未収集のアイテムを取得

    Args:
        db_path: データベースパス
        start_date: 開始日
        end_date: 終了日
        logger: ロガー

    Returns:
        list: 収集対象のアイテムリスト
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 例: 特定カラムがNULLのレースを取得
    # 実際の条件に合わせて変更してください
    cursor.execute("""
        SELECT DISTINCT r.id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date BETWEEN ? AND ?
          AND NOT EXISTS (
              SELECT 1 FROM your_table t WHERE t.race_id = r.id
          )
        ORDER BY r.race_date, r.venue_code, r.race_number
    """, (start_date, end_date))

    items = cursor.fetchall()
    conn.close()

    logger.info(f"未収集アイテム: {len(items)}件")
    return items


# =============================================================================
# 3. データ取得（エラー分類・リトライ付き）
# =============================================================================

def fetch_single_item(args: tuple, retry: int = MAX_RETRIES) -> tuple:
    """
    1アイテムのデータを取得（リトライ機能付き）

    Args:
        args: (race_id, venue_code, race_date, race_number) などの識別情報
        retry: リトライ回数

    Returns:
        tuple: (FetchResult, data_or_none)
    """
    race_id, venue_code, race_date, race_number = args

    # 日付形式変換（YYYY-MM-DD → YYYYMMDD）
    date_str = race_date.replace('-', '')

    for attempt in range(retry):
        try:
            # 実際のデータ取得処理をここに実装
            # 例: スクレイパーでデータ取得
            session = get_session()

            # URL構築（実際のURLに変更）
            url = f"https://example.com/api?venue={venue_code}&date={date_str}&race={race_number}"

            response = session.get(url, timeout=15)

            # 404 = データなし（正常）
            if response.status_code == 404:
                return (FetchResult.NO_DATA, None)

            # サーバーエラー
            if response.status_code >= 500:
                if attempt < retry - 1:
                    time.sleep(RETRY_BASE_WAIT * (2 ** attempt))
                    continue
                return (FetchResult.SERVER_ERROR, None)

            response.raise_for_status()

            # データパース
            data = parse_response(response, race_id)

            if data is None:
                return (FetchResult.NO_DATA, None)

            return (FetchResult.SUCCESS, data)

        except TimeoutError:
            if attempt < retry - 1:
                time.sleep(RETRY_BASE_WAIT * (2 ** attempt))
                continue
            return (FetchResult.TIMEOUT, None)

        except ConnectionError:
            if attempt < retry - 1:
                time.sleep(RETRY_BASE_WAIT * (2 ** attempt))
                continue
            return (FetchResult.NETWORK_ERROR, None)

        except Exception as e:
            if attempt < retry - 1:
                time.sleep(RETRY_BASE_WAIT * (2 ** attempt))
                continue
            return (FetchResult.PARSE_ERROR, None)

    return (FetchResult.NETWORK_ERROR, None)


def parse_response(response, race_id) -> dict:
    """
    レスポンスをパースしてデータを抽出

    実際のパースロジックに置き換えてください
    """
    # 例: JSONレスポンスのパース
    try:
        json_data = response.json()

        if not json_data or not json_data.get('data'):
            return None

        return {
            'race_id': race_id,
            'field1': json_data.get('field1'),
            'field2': json_data.get('field2'),
            # ... 必要なフィールドを追加
        }

    except Exception:
        return None


# =============================================================================
# 4. バッチ保存（UPSERT使用）
# =============================================================================

def save_batch(conn: sqlite3.Connection, batch: list, logger: logging.Logger) -> int:
    """
    バッチデータをDBに保存（UPSERT使用）

    Args:
        conn: DB接続
        batch: 保存するデータのリスト
        logger: ロガー

    Returns:
        int: 保存件数
    """
    cursor = conn.cursor()
    saved = 0

    try:
        # トランザクション開始
        cursor.execute("BEGIN IMMEDIATE")

        for data in batch:
            try:
                # UPSERT（INSERT OR REPLACE）
                # 実際のテーブル・カラムに合わせて変更
                cursor.execute("""
                    INSERT OR REPLACE INTO your_table (
                        race_id, field1, field2, updated_at
                    ) VALUES (?, ?, ?, datetime('now'))
                """, (
                    data['race_id'],
                    data['field1'],
                    data['field2'],
                ))
                saved += 1

            except Exception as e:
                logger.warning(f"レコード保存エラー: {data.get('race_id')} - {e}")

        # コミット
        conn.commit()

    except Exception as e:
        logger.error(f"バッチ保存エラー: {e}")
        conn.rollback()
        raise

    return saved


# =============================================================================
# 5. メイン処理
# =============================================================================

class DataCollector:
    """データ収集クラス"""

    def __init__(self, db_path: Path, workers: int = DEFAULT_WORKERS,
                 batch_size: int = DEFAULT_BATCH_SIZE, delay: float = DEFAULT_DELAY):
        self.db_path = db_path
        self.workers = workers
        self.batch_size = batch_size
        self.delay = delay

        self.logger = setup_logger('data_collection')
        self.shutdown_event = threading.Event()

        # 統計
        self.stats = {
            'total': 0,
            'success': 0,
            'no_data': 0,
            'network_error': 0,
            'timeout': 0,
            'server_error': 0,
            'parse_error': 0,
        }

        # シグナルハンドラ設定
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """シグナルハンドラ設定（優雅な終了）"""
        def handler(signum, frame):
            self.logger.warning("\n終了シグナル受信。優雅にシャットダウン中...")
            self.shutdown_event.set()

        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

    def run(self, start_date: str, end_date: str, use_schedule: bool = True):
        """
        データ収集を実行

        Args:
            start_date: 開始日 (YYYY-MM-DD)
            end_date: 終了日 (YYYY-MM-DD)
            use_schedule: 開催スケジュールを使用するか
        """
        self.logger.info("=" * 80)
        self.logger.info("データ収集開始")
        self.logger.info("=" * 80)
        self.logger.info(f"期間: {start_date} - {end_date}")
        self.logger.info(f"並列数: {self.workers}")
        self.logger.info(f"バッチサイズ: {self.batch_size}")

        # 1. 開催スケジュール取得（オプション）
        if use_schedule:
            schedule = get_schedule_for_period(start_date, end_date, self.logger)
            # スケジュールからタスクを生成
            tasks = self._create_tasks_from_schedule(schedule)
        else:
            # 全対象を取得
            tasks = get_uncollected_items(self.db_path, start_date, end_date, self.logger)

        self.stats['total'] = len(tasks)
        self.logger.info(f"総タスク数: {self.stats['total']}")

        if not tasks:
            self.logger.info("処理対象がありません")
            return

        # DB接続（WALモード有効化）
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")

        # 2. 並列処理
        start_time = time.time()
        batch = []
        processed = 0

        try:
            with ThreadPoolExecutor(max_workers=self.workers) as executor:
                futures = {executor.submit(fetch_single_item, task): task for task in tasks}

                for future in as_completed(futures):
                    if self.shutdown_event.is_set():
                        self.logger.warning("シャットダウン中...")
                        break

                    processed += 1
                    result, data = future.result()

                    # 統計更新
                    if result == FetchResult.SUCCESS:
                        self.stats['success'] += 1
                        batch.append(data)
                    elif result == FetchResult.NO_DATA:
                        self.stats['no_data'] += 1
                    elif result == FetchResult.NETWORK_ERROR:
                        self.stats['network_error'] += 1
                    elif result == FetchResult.TIMEOUT:
                        self.stats['timeout'] += 1
                    elif result == FetchResult.SERVER_ERROR:
                        self.stats['server_error'] += 1
                    else:
                        self.stats['parse_error'] += 1

                    # 3. バッチ保存
                    if len(batch) >= self.batch_size:
                        saved = save_batch(conn, batch, self.logger)
                        self.logger.info(f"バッチ保存完了: {saved}件")
                        batch = []

                    # 4. 進捗表示
                    if processed % 100 == 0 or processed == self.stats['total']:
                        self._show_progress(processed, start_time)

                    # 待機
                    time.sleep(self.delay)

            # 残りのバッチを保存
            if batch:
                saved = save_batch(conn, batch, self.logger)
                self.logger.info(f"最終バッチ保存完了: {saved}件")

        finally:
            conn.close()

        # 5. 最終レポート
        self._show_final_report(start_time)

    def _create_tasks_from_schedule(self, schedule: dict) -> list:
        """
        開催スケジュールからタスクを生成

        Args:
            schedule: {date_str: [venue_codes]}

        Returns:
            list: タスクリスト
        """
        # 既存データを取得
        existing = get_existing_data(self.db_path, min(schedule.keys()), max(schedule.keys()))

        tasks = []
        for date_str, venue_codes in schedule.items():
            date_formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            for venue_code in venue_codes:
                for race_number in range(1, 13):
                    # 実際の識別子生成ロジックに合わせて変更
                    task_id = (None, venue_code, date_formatted, race_number)
                    # if task_id not in existing:  # 既存チェック
                    tasks.append(task_id)

        return tasks

    def _show_progress(self, processed: int, start_time: float):
        """進捗表示"""
        elapsed = time.time() - start_time
        rate = processed / elapsed if elapsed > 0 else 0
        remaining = (self.stats['total'] - processed) / rate if rate > 0 else 0
        progress_pct = processed / self.stats['total'] * 100 if self.stats['total'] > 0 else 0

        self.logger.info(
            f"進捗: {processed}/{self.stats['total']} ({progress_pct:.1f}%) | "
            f"成功: {self.stats['success']} | "
            f"データなし: {self.stats['no_data']} | "
            f"エラー: {self.stats['network_error'] + self.stats['timeout'] + self.stats['server_error']} | "
            f"速度: {rate:.1f}件/秒 | 残り: {remaining/60:.1f}分"
        )

    def _show_final_report(self, start_time: float):
        """最終レポート表示"""
        elapsed = time.time() - start_time

        self.logger.info("")
        self.logger.info("=" * 80)
        self.logger.info("処理完了")
        self.logger.info("=" * 80)
        self.logger.info(f"総タスク数: {self.stats['total']}")
        self.logger.info(f"成功: {self.stats['success']}")
        self.logger.info(f"データなし: {self.stats['no_data']}")
        self.logger.info(f"ネットワークエラー: {self.stats['network_error']}")
        self.logger.info(f"タイムアウト: {self.stats['timeout']}")
        self.logger.info(f"サーバーエラー: {self.stats['server_error']}")
        self.logger.info(f"パースエラー: {self.stats['parse_error']}")
        self.logger.info(f"所要時間: {elapsed/60:.1f}分")

        if self.stats['total'] > 0:
            success_rate = self.stats['success'] / self.stats['total'] * 100
            self.logger.info(f"成功率: {success_rate:.1f}%")

        self.logger.info("=" * 80)


# =============================================================================
# エントリポイント
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='データ収集スクリプト')
    parser.add_argument('--start', type=str, required=True, help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, required=True, help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--workers', type=int, default=DEFAULT_WORKERS, help=f'並列数 (デフォルト: {DEFAULT_WORKERS})')
    parser.add_argument('--batch-size', type=int, default=DEFAULT_BATCH_SIZE, help=f'バッチサイズ (デフォルト: {DEFAULT_BATCH_SIZE})')
    parser.add_argument('--delay', type=float, default=DEFAULT_DELAY, help=f'リクエスト間隔 (デフォルト: {DEFAULT_DELAY}秒)')
    parser.add_argument('--no-schedule', action='store_true', help='開催スケジュールを使用しない')
    parser.add_argument('--dry-run', action='store_true', help='ドライラン（実際の保存なし）')

    args = parser.parse_args()

    collector = DataCollector(
        db_path=DB_PATH,
        workers=args.workers,
        batch_size=args.batch_size,
        delay=args.delay
    )

    collector.run(
        start_date=args.start,
        end_date=args.end,
        use_schedule=not args.no_schedule
    )


if __name__ == '__main__':
    main()
