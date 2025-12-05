"""
不足データ一括取得スクリプト（夜間バッチ処理用）

過去30日の全不足データを順次取得します
"""
import os
import sys
import argparse
from datetime import datetime, timedelta

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.workflow.missing_data_fetch import MissingDataFetchWorkflow
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
        pass  # エラーは無視（ジョブマネージャー経由でない実行もある）


def main():
    parser = argparse.ArgumentParser(description='不足データ一括取得（夜間バッチ用）')
    parser.add_argument('--days', type=int, default=30, help='対象日数（デフォルト: 30日）')
    parser.add_argument('--start-date', type=str, help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='終了日 (YYYY-MM-DD)')
    args = parser.parse_args()

    print("=" * 80)
    print("不足データ一括取得 - 夜間バッチ処理")
    print("=" * 80)
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
    print("フェーズ1: 当日確定情報の取得")
    print("=" * 80)
    print("  - 結果データ")
    print("  - レース詳細（ST/コース）")
    print("  - 決まり手")
    print("  - 払戻金")
    print()

    workflow1 = MissingDataFetchWorkflow(
        db_path=os.path.join(PROJECT_ROOT, 'data/boatrace.db'),
        project_root=PROJECT_ROOT,
        progress_callback=progress_callback
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
    print("フェーズ2: 直前情報の取得")
    print("=" * 80)
    print("  - 展示タイム")
    print("  - チルト")
    print("  - 調整重量")
    print("  - 天候・風向")
    print("  - オリジナル展示")
    print("  - 潮位データ")
    print()

    workflow2 = MissingDataFetchWorkflow(
        db_path=os.path.join(PROJECT_ROOT, 'data/boatrace.db'),
        project_root=PROJECT_ROOT,
        progress_callback=progress_callback
    )

    # 期間を設定
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

    # 最終サマリー
    print("=" * 80)
    print("最終サマリー")
    print("=" * 80)
    print(f"対象期間: {start_date} ～ {end_date}")
    print()
    print(f"フェーズ1（当日確定情報）:")
    print(f"  ステータス: {'[OK] 成功' if result1['success'] else '[NG] 失敗'}")
    print(f"  処理数: {result1.get('processed', 0)}件")
    print(f"  エラー: {result1.get('errors', 0)}件")
    print()
    print(f"フェーズ2（直前情報）:")
    print(f"  ステータス: {'[OK] 成功' if result2['success'] else '[NG] 失敗'}")
    print(f"  処理数: {result2.get('processed', 0)}件")
    print(f"  エラー: {result2.get('errors', 0)}件")
    print()

    total_processed = result1.get('processed', 0) + result2.get('processed', 0)
    total_errors = result1.get('errors', 0) + result2.get('errors', 0)

    print(f"合計処理数: {total_processed}件")
    print(f"合計エラー: {total_errors}件")
    print("=" * 80)

    # ジョブマネージャーに完了を通知
    try:
        success = result1['success'] and result2['success']
        complete_job(
            'missing_data_fetch',
            success=success,
            message=f"完了: 処理数 {total_processed}件, エラー {total_errors}件"
        )
    except Exception:
        pass

    # 終了コード
    if result1['success'] and result2['success']:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
