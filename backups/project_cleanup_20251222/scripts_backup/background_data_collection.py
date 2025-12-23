"""
データ収集 - バックグラウンド実行スクリプト

コマンドライン引数:
  --type: 収集タイプ (today, week, period)
  --start: 開始日 (YYYY-MM-DD)
  --end: 終了日 (YYYY-MM-DD)
  --venues: 会場コード (カンマ区切り、省略時は全会場)
  --skip-existing: 既存データをスキップ（デフォルトON）
  --no-skip: 既存データもすべて再取得
"""
import os
import sys
import argparse
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.utils.job_manager import update_job_progress, complete_job

JOB_NAME = 'data_collection'


def update_progress(step: str, message: str, progress: int):
    """進捗を更新"""
    update_job_progress(JOB_NAME, {
        'status': 'running',
        'step': step,
        'message': message,
        'progress': progress
    })
    print(f"[{progress}%] {step}: {message}")


def collect_today(skip_existing: bool = True):
    """今日のデータを収集"""
    mode_str = "（スキップモード）" if skip_existing else "（全件取得）"
    update_progress("データ収集", f"今日のデータを収集中...{mode_str}", 5)

    from src.scraper.bulk_scraper import BulkScraper

    scraper = BulkScraper()
    today = datetime.now().strftime('%Y-%m-%d')

    # スケジュールスクレイパー経由で今日のスケジュールを取得
    schedule = scraper.schedule_scraper.get_today_schedule()

    if not schedule:
        update_progress("データ収集", "本日開催のレースがありません", 100)
        return 0

    # スケジュールは {venue_code: race_date} の辞書形式
    venue_codes = list(schedule.keys())
    total = len(venue_codes)
    total_races = 0

    for i, venue_code in enumerate(venue_codes, 1):
        pct = 5 + int((i / total) * 90)
        update_progress("データ収集", f"会場 {venue_code} を収集中... ({i}/{total})", pct)

        try:
            result = scraper.fetch_multiple_venues(
                venue_codes=[venue_code],
                race_date=today,
                race_count=12,
                skip_existing=skip_existing
            )
            if venue_code in result:
                total_races += len(result[venue_code])
        except Exception as e:
            print(f"会場 {venue_code} エラー: {e}")

    update_progress("データ収集", f"完了: {total_races}レース取得", 100)
    return total_races


def collect_week(skip_existing: bool = True):
    """今週のデータを収集"""
    mode_str = "（スキップモード）" if skip_existing else "（全件取得）"
    update_progress("データ収集", f"今週のデータを収集中...{mode_str}", 5)

    from src.scraper.bulk_scraper import BulkScraper

    scraper = BulkScraper()
    today = datetime.now().date()
    start_date = today - timedelta(days=7)

    total_races = 0
    skipped_total = 0
    date_range = []
    current = start_date
    while current <= today:
        date_range.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)

    total_days = len(date_range)

    for day_idx, date_str in enumerate(date_range, 1):
        pct = 5 + int((day_idx / total_days) * 90)
        update_progress("データ収集", f"{date_str} を収集中... ({day_idx}/{total_days})", pct)

        # 全会場を収集
        try:
            result = scraper.fetch_multiple_venues(
                venue_codes=[f"{i:02d}" for i in range(1, 25)],
                race_date=date_str,
                race_count=12,
                skip_existing=skip_existing
            )
            for venue_code, races in result.items():
                total_races += len(races)
        except Exception as e:
            print(f"{date_str} エラー: {e}")

    update_progress("データ収集", f"完了: {total_races}レース取得", 100)
    return total_races


def collect_period(start_date: str, end_date: str, venue_codes: list = None, skip_existing: bool = True):
    """期間指定でデータを収集"""
    mode_str = "（スキップモード）" if skip_existing else "（全件取得）"
    update_progress("データ収集", f"{start_date}〜{end_date}を収集中...{mode_str}", 5)

    from src.scraper.bulk_scraper import BulkScraper

    scraper = BulkScraper()

    if not venue_codes:
        venue_codes = [f"{i:02d}" for i in range(1, 25)]

    # 日付リストを作成
    start = datetime.strptime(start_date, '%Y-%m-%d').date()
    end = datetime.strptime(end_date, '%Y-%m-%d').date()

    date_range = []
    current = start
    while current <= end:
        date_range.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)

    total_tasks = len(date_range) * len(venue_codes)
    completed = 0
    total_races = 0

    for date_str in date_range:
        for venue_code in venue_codes:
            pct = 5 + int((completed / total_tasks) * 90)
            update_progress("データ収集", f"{date_str} 会場{venue_code} ({completed}/{total_tasks})", pct)

            try:
                result = scraper.fetch_multiple_venues(
                    venue_codes=[venue_code],
                    race_date=date_str,
                    race_count=12,
                    skip_existing=skip_existing
                )
                if venue_code in result:
                    total_races += len(result[venue_code])
            except Exception as e:
                print(f"{date_str} {venue_code} エラー: {e}")

            completed += 1

    update_progress("データ収集", f"完了: {total_races}レース取得", 100)
    return total_races


def main():
    parser = argparse.ArgumentParser(description='バックグラウンドデータ収集')
    parser.add_argument('--type', choices=['today', 'week', 'period'], default='today',
                       help='収集タイプ')
    parser.add_argument('--start', help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--venues', help='会場コード (カンマ区切り)')
    parser.add_argument('--no-skip', action='store_true', dest='no_skip',
                       help='既存データもすべて再取得（デフォルトはスキップ）')

    args = parser.parse_args()

    # スキップモードの判定（デフォルトはスキップON）
    skip_existing = not args.no_skip

    print("=" * 60)
    print(f"データ収集 - バックグラウンド処理 ({args.type})")
    print(f"スキップモード: {'OFF（全件取得）' if args.no_skip else 'ON（既存スキップ）'}")
    print("=" * 60)

    try:
        if args.type == 'today':
            total_races = collect_today(skip_existing=skip_existing)
        elif args.type == 'week':
            total_races = collect_week(skip_existing=skip_existing)
        elif args.type == 'period':
            if not args.start or not args.end:
                raise ValueError("期間指定には --start と --end が必要です")
            venue_codes = args.venues.split(',') if args.venues else None
            total_races = collect_period(args.start, args.end, venue_codes, skip_existing=skip_existing)
        else:
            raise ValueError(f"不明な収集タイプ: {args.type}")

        complete_job(JOB_NAME, success=True, message=f'データ収集完了: {total_races}レース')
        print("=" * 60)
        print(f"処理完了: {total_races}レース")
        print("=" * 60)

    except Exception as e:
        complete_job(JOB_NAME, success=False, message=f'エラー: {str(e)}')
        print(f"エラー発生: {e}")
        raise


if __name__ == '__main__':
    main()
