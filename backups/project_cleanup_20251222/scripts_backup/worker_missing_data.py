"""
不足データ取得ワーカー（バックグラウンド実行用）

共通ワークフロークラスを使用し、進捗をジョブマネージャーに記録
"""
import os
import sys
import argparse
import json

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.utils.job_manager import update_job_progress, complete_job
from src.workflow.missing_data_fetch import MissingDataFetchWorkflow

JOB_NAME = 'missing_data_fetch'


def progress_callback(step: str, message: str, progress: int):
    """ジョブマネージャーに進捗を記録"""
    update_job_progress(JOB_NAME, {
        'status': 'running',
        'step': step,
        'message': message,
        'progress': progress
    })
    print(f"[{progress}%] {step}: {message}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=str, required=True,
                        help='設定ファイルパス（JSON）')
    args = parser.parse_args()

    print("=" * 60)
    print("不足データ取得 - バックグラウンド処理")
    print("=" * 60)

    try:
        # 設定ファイルを読み込み
        with open(args.config, 'r', encoding='utf-8') as f:
            config = json.load(f)

        missing_dates = config.get('missing_dates', [])
        check_types = config.get('check_types', [])

        # 共通ワークフローを使用
        workflow = MissingDataFetchWorkflow(
            db_path=os.path.join(PROJECT_ROOT, 'data/boatrace.db'),
            project_root=PROJECT_ROOT,
            progress_callback=progress_callback
        )

        result = workflow.run(
            missing_dates=missing_dates,
            check_types=check_types
        )

        if result['success']:
            complete_job(
                JOB_NAME,
                success=True,
                message=result.get('message', '処理完了')
            )
            print("=" * 60)
            print("処理完了")
            print(f"  処理数: {result['processed']}")
            print(f"  エラー: {result['errors']}")
            print("=" * 60)
        else:
            complete_job(
                JOB_NAME,
                success=False,
                message=result.get('message', 'エラー発生')
            )

        # 設定ファイルを削除
        try:
            os.remove(args.config)
        except:
            pass

    except Exception as e:
        complete_job(JOB_NAME, success=False, message=f'エラー: {str(e)}')
        print(f"エラー発生: {e}")
        raise


if __name__ == '__main__':
    main()
