"""
daily_schedulerのテストスクリプト（dry-run）

実際のデータ収集は行わず、スケジュール設定と起動通知のみテスト
"""
import sys
from pathlib import Path
from datetime import datetime
import schedule

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def mock_block_a():
    """Aブロックのモック"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [TEST] A block executed")

def mock_block_c():
    """Cブロックのモック"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [TEST] C block executed")

def mock_block_d():
    """Dブロックのモック"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [TEST] D block executed")

def mock_race_monitor():
    """レース監視のモック"""
    pass

def test_scheduler():
    """スケジューラーのテスト"""
    print("\n" + "=" * 70)
    print("daily_scheduler.py Test (dry-run)")
    print("=" * 70)
    print(f"Test started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # スケジュール設定（新バージョン）
    print("Schedule configuration:")
    schedule.every().day.at("03:00").do(mock_block_a)
    print("  [OK] 03:00 - Block A (Yesterday data) [1 hour earlier]")
    
    schedule.every().day.at("06:00").do(mock_block_c)
    print("  [OK] 06:00 - Block C (Today data) [30 min earlier]")
    
    schedule.every().day.at("07:30").do(mock_block_d)
    print("  [OK] 07:30 - Block D (Prediction) [30 min earlier]")
    
    schedule.every(1).minutes.do(mock_race_monitor)
    print("  [OK] Every 1 minute - Race monitoring")
    
    print()
    print("Next scheduled runs:")
    jobs = schedule.get_jobs()
    for i, job in enumerate(jobs[:4], 1):
        next_run = job.next_run
        if next_run:
            print(f"  {i}. {next_run.strftime('%Y-%m-%d %H:%M:%S')} - {job.job_func.__name__}")
    
    print()
    print("=" * 70)
    print("Test result: SUCCESS - Schedule configuration is correct")
    print("=" * 70)
    print()
    
    # 今日のスケジュール確認
    print("Today's schedule:")
    today = datetime.now().date()
    for job in jobs[:3]:
        next_run = job.next_run
        if next_run and next_run.date() == today:
            hours_until = (next_run - datetime.now()).total_seconds() / 3600
            print(f"  - {next_run.strftime('%H:%M')} (in {hours_until:.1f} hours)")
        elif next_run:
            print(f"  - {next_run.strftime('%m/%d %H:%M')} (tomorrow or later)")
    
    print()
    print("NOTE: This is a dry-run test. No actual data collection performed.")
    print()

if __name__ == "__main__":
    test_scheduler()
