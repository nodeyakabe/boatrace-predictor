"""
不足データ一括取得スクリプト（12時間バッチ処理用）

戦略的優先順位:
1. 決まり手・払戻金（必須 - 予測精度に直結）
2. 結果データ（必須 - 全データの基礎）
3. レース詳細（重要 - ST/コース情報）
4. 直前情報（重要だが古いデータは優先度低）

12時間で最大限のデータを取得します
"""
import os
import sys
import argparse
import json
from datetime import datetime, timedelta

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.workflow.missing_data_fetch import MissingDataFetchWorkflow
from src.utils.job_manager import update_job_progress, complete_job

# 進捗保存ファイル
PROGRESS_FILE = os.path.join(PROJECT_ROOT, 'temp/batch_progress_12h.json')


def save_progress(phase: str, completed: bool, stats: dict):
    """進捗を保存（中断・再開用）"""
    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)

    progress = {
        'timestamp': datetime.now().isoformat(),
        'phase': phase,
        'completed': completed,
        'stats': stats
    }

    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def load_progress():
    """保存済み進捗を読み込み"""
    if not os.path.exists(PROGRESS_FILE):
        return None

    try:
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None


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
    parser = argparse.ArgumentParser(description='不足データ一括取得（12時間バッチ用）')
    parser.add_argument('--resume', action='store_true', help='前回の続きから再開')
    parser.add_argument('--recent-only', action='store_true', help='直前情報は2024年以降のみ')
    parser.add_argument('--start-date', type=str, help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='終了日 (YYYY-MM-DD)')
    args = parser.parse_args()

    print("=" * 80)
    print("不足データ一括取得 - 12時間バッチ処理")
    print("=" * 80)
    print()

    start_time = datetime.now()

    # 再開チェック
    prev_progress = None
    if args.resume:
        prev_progress = load_progress()
        if prev_progress:
            print(f"📂 前回の進捗を検出: {prev_progress['phase']}")
            print(f"   実行時刻: {prev_progress['timestamp']}")
            print(f"   前回の統計: {prev_progress['stats']}")
            print()

    # 全体統計
    total_stats = {
        'phase1_processed': 0,
        'phase1_errors': 0,
        'phase2_processed': 0,
        'phase2_errors': 0,
        'phase3_processed': 0,
        'phase3_errors': 0
    }

    # ========== フェーズ1: 決まり手・払戻金の完全補完 ==========
    if not prev_progress or prev_progress['phase'] == 'phase1':
        print("=" * 80)
        print("フェーズ1: 決まり手・払戻金の完全補完（全期間）")
        print("=" * 80)
        print("  優先度: [最高]")
        print("  対象: 決まり手、払戻金")
        print("  期間: 全期間（期間制限なし）")
        print("  推定時間: 30-60分")
        print()

        workflow1 = MissingDataFetchWorkflow(
            db_path=os.path.join(PROJECT_ROOT, 'data/boatrace.db'),
            project_root=PROJECT_ROOT,
            progress_callback=progress_callback
        )

        # 期間制限なし（全期間対象）
        workflow1.start_date = None
        workflow1.end_date = None

        result1 = workflow1.run(check_types=['当日確定情報'])

        total_stats['phase1_processed'] = result1.get('processed', 0)
        total_stats['phase1_errors'] = result1.get('errors', 0)

        save_progress('phase1', result1['success'], total_stats)

        print()
        print("=" * 80)
        print("フェーズ1 完了")
        print("=" * 80)
        if result1['success']:
            print(f"[OK] 成功: {result1.get('message', '処理完了')}")
            print(f"   処理数: {result1.get('processed', 0)}件")
            print(f"   エラー: {result1.get('errors', 0)}件")
        else:
            print(f"[NG] 失敗: {result1.get('message', 'エラー')}")
            print("   [!] 次のフェーズに進みます")
        print()

    # ========== フェーズ2: 結果データとレース詳細（全期間） ==========
    if not prev_progress or prev_progress['phase'] in ['phase1', 'phase2']:
        print("=" * 80)
        print("フェーズ2: 結果データとレース詳細の補完（全期間）")
        print("=" * 80)
        print("  優先度: [高]")
        print("  対象: 結果データ、レース詳細（ST/コース）")
        print("  期間: 全期間（期間制限なし）")
        print("  推定時間: 1-2時間")
        print()

        workflow2 = MissingDataFetchWorkflow(
            db_path=os.path.join(PROJECT_ROOT, 'data/boatrace.db'),
            project_root=PROJECT_ROOT,
            progress_callback=progress_callback
        )

        # 期間制限なし
        workflow2.start_date = None
        workflow2.end_date = None

        result2 = workflow2.run(check_types=['当日確定情報'])

        total_stats['phase2_processed'] = result2.get('processed', 0)
        total_stats['phase2_errors'] = result2.get('errors', 0)

        save_progress('phase2', result2['success'], total_stats)

        print()
        print("=" * 80)
        print("フェーズ2 完了")
        print("=" * 80)
        if result2['success']:
            print(f"[OK] 成功: {result2.get('message', '処理完了')}")
            print(f"   処理数: {result2.get('processed', 0)}件")
            print(f"   エラー: {result2.get('errors', 0)}件")
        else:
            print(f"[NG] 失敗: {result2.get('message', 'エラー')}")
            print("   [!] 次のフェーズに進みます")
        print()

    # ========== フェーズ3: 直前情報（2024年以降または全期間） ==========
    print("=" * 80)
    print("フェーズ3: 直前情報の補完")
    print("=" * 80)

    if args.recent_only:
        start_date = '2024-01-01'
        end_date = datetime.now().strftime('%Y-%m-%d')
        print("  優先度: [中]（2024年以降のみ）")
        print(f"  期間: {start_date} ～ {end_date}")
        print("  推定時間: 2-4時間")
    elif args.start_date and args.end_date:
        start_date = args.start_date
        end_date = args.end_date
        print("  優先度: [中]（指定期間）")
        print(f"  期間: {start_date} ～ {end_date}")
    else:
        start_date = None
        end_date = None
        print("  優先度: [中]（全期間）")
        print("  期間: 全期間（期間制限なし）")
        print("  推定時間: 8-10時間（大量）")

    print("  対象: 展示タイム、チルト、調整重量、天候、潮位")
    print()

    workflow3 = MissingDataFetchWorkflow(
        db_path=os.path.join(PROJECT_ROOT, 'data/boatrace.db'),
        project_root=PROJECT_ROOT,
        progress_callback=progress_callback
    )

    # 期間設定
    workflow3.start_date = start_date
    workflow3.end_date = end_date

    result3 = workflow3.run(check_types=['直前情報取得'])

    total_stats['phase3_processed'] = result3.get('processed', 0)
    total_stats['phase3_errors'] = result3.get('errors', 0)

    save_progress('phase3', result3['success'], total_stats)

    print()
    print("=" * 80)
    print("フェーズ3 完了")
    print("=" * 80)
    if result3['success']:
        print(f"[OK] 成功: {result3.get('message', '処理完了')}")
        print(f"   処理数: {result3.get('processed', 0)}件")
        print(f"   エラー: {result3.get('errors', 0)}件")
    else:
        print(f"[NG] 失敗: {result3.get('message', 'エラー')}")
    print()

    # ========== 最終サマリー ==========
    end_time = datetime.now()
    elapsed_time = end_time - start_time

    print("=" * 80)
    print("最終サマリー")
    print("=" * 80)
    print(f"実行時間: {elapsed_time}")
    print()
    print(f"フェーズ1（決まり手・払戻金）:")
    print(f"  処理数: {total_stats['phase1_processed']}件")
    print(f"  エラー: {total_stats['phase1_errors']}件")
    print()
    print(f"フェーズ2（結果・レース詳細）:")
    print(f"  処理数: {total_stats['phase2_processed']}件")
    print(f"  エラー: {total_stats['phase2_errors']}件")
    print()
    print(f"フェーズ3（直前情報）:")
    print(f"  処理数: {total_stats['phase3_processed']}件")
    print(f"  エラー: {total_stats['phase3_errors']}件")
    print()

    total_processed = sum([
        total_stats['phase1_processed'],
        total_stats['phase2_processed'],
        total_stats['phase3_processed']
    ])
    total_errors = sum([
        total_stats['phase1_errors'],
        total_stats['phase2_errors'],
        total_stats['phase3_errors']
    ])

    print(f"合計処理数: {total_processed}件")
    print(f"合計エラー: {total_errors}件")
    print("=" * 80)

    # ジョブマネージャーに完了を通知
    try:
        success = total_errors == 0
        complete_job(
            'missing_data_fetch',
            success=success,
            message=f"完了: 処理数 {total_processed}件, エラー {total_errors}件"
        )
    except Exception:
        pass

    # 進捗ファイルを削除（完了したため）
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)

    sys.exit(0)


if __name__ == '__main__':
    main()
