"""
不足データ一括取得スクリプト（並列化版）

並列化改善:
- 結果データ取得: 16スレッド並列
- 直前情報取得: 8スレッド並列
- オッズ取得: 4スレッド並列

期待速度:
- 改善前: 1634レース × 12秒 = 5.4時間
- 改善後: 16並列 → 約20-40分（10-15倍高速化）
"""
import os
import sys
import argparse
from datetime import datetime, timedelta

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.workflow.missing_data_fetch_parallel import MissingDataFetchWorkflowParallel
from src.utils.job_manager import update_job_progress, complete_job


def progress_callback(step: str, message: str, progress: int):
    """進捗を表示してジョブマネージャーに通知"""
    timestamp = datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] [{progress}%] {step}: {message}")

    # ジョブマネージャーに進捗を通知
    try:
        update_job_progress('missing_data_fetch', {
            'status': 'running',
            'progress': progress,
            'message': message,
            'step': step
        })
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description='不足データ一括取得（並列化版）')
    parser.add_argument('--days', type=int, default=30, help='対象日数（デフォルト: 30日）')
    parser.add_argument('--start-date', type=str, help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--workers-results', type=int, default=16, help='結果取得の並列数（デフォルト: 16）')
    parser.add_argument('--workers-beforeinfo', type=int, default=8, help='直前情報取得の並列数（デフォルト: 8）')
    parser.add_argument('--workers-odds', type=int, default=4, help='オッズ取得の並列数（デフォルト: 4）')
    args = parser.parse_args()

    print("=" * 80)
    print("不足データ一括取得 - 並列化版")
    print("=" * 80)
    print(f"並列設定: 結果={args.workers_results}スレッド, 直前情報={args.workers_beforeinfo}スレッド, オッズ={args.workers_odds}スレッド")
    print()

    # 期間を決定
    if args.start_date and args.end_date:
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(args.end_date, '%Y-%m-%d').date()
    else:
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=args.days)

    print(f"対象期間: {start_date} ～ {end_date}")
    print(f"   ({(end_date - start_date).days + 1}日分)")
    print()

    # フェーズ1: 当日確定情報の取得
    print("=" * 80)
    print("フェーズ1: 当日確定情報の取得（並列処理）")
    print("=" * 80)
    print("  - 結果データ")
    print("  - レース詳細（ST/コース）")
    print("  - 決まり手")
    print("  - 払戻金")
    print()

    workflow1 = MissingDataFetchWorkflowParallel(
        db_path=os.path.join(PROJECT_ROOT, 'data/boatrace.db'),
        project_root=PROJECT_ROOT,
        progress_callback=progress_callback,
        max_workers_results=args.workers_results,
        max_workers_beforeinfo=args.workers_beforeinfo,
        max_workers_odds=args.workers_odds
    )

    # 期間を設定
    workflow1.start_date = str(start_date)
    workflow1.end_date = str(end_date)

    result1 = workflow1.run(check_types=['当日確定情報'])

    print()
    print("=" * 80)
    print("フェーズ1 完了")
    print("=" * 80)
    if result1['success']:
        print(f"[OK] 成功: {result1.get('message', '処理完了')}")
        print(f"   処理数: {result1.get('processed', 0)}件")
        if result1.get('errors', 0) > 0:
            print(f"   エラー: {result1['errors']}件")
    else:
        print(f"[NG] 失敗: {result1.get('message', 'エラー')}")
    print()

    # フェーズ2: 直前情報の取得
    print("=" * 80)
    print("フェーズ2: 直前情報の取得（並列処理）")
    print("=" * 80)
    print("  - 展示タイム")
    print("  - チルト")
    print("  - 体重")
    print("  - ST予想")
    print("  - 気象データ")
    print()

    workflow2 = MissingDataFetchWorkflowParallel(
        db_path=os.path.join(PROJECT_ROOT, 'data/boatrace.db'),
        project_root=PROJECT_ROOT,
        progress_callback=progress_callback,
        max_workers_results=args.workers_results,
        max_workers_beforeinfo=args.workers_beforeinfo,
        max_workers_odds=args.workers_odds
    )

    workflow2.start_date = str(start_date)
    workflow2.end_date = str(end_date)

    result2 = workflow2.run(check_types=['直前情報取得'])

    print()
    print("=" * 80)
    print("フェーズ2 完了")
    print("=" * 80)
    if result2['success']:
        print(f"[OK] 成功: {result2.get('message', '処理完了')}")
        print(f"   処理数: {result2.get('processed', 0)}件")
        if result2.get('errors', 0) > 0:
            print(f"   エラー: {result2['errors']}件")
    else:
        print(f"[NG] 失敗: {result2.get('message', 'エラー')}")
    print()

    # 最終結果
    print("=" * 80)
    print("全処理完了")
    print("=" * 80)

    total_processed = result1.get('processed', 0) + result2.get('processed', 0)
    total_errors = result1.get('errors', 0) + result2.get('errors', 0)

    print(f"総処理数: {total_processed}件")
    print(f"総エラー: {total_errors}件")

    # ジョブマネージャーに完了を通知
    if result1['success'] and result2['success']:
        complete_job(
            'missing_data_fetch',
            success=True,
            message=f'不足データ取得完了（処理: {total_processed}件, エラー: {total_errors}件）'
        )
    else:
        complete_job(
            'missing_data_fetch',
            success=False,
            message='一部のフェーズでエラーが発生しました'
        )


if __name__ == '__main__':
    main()
