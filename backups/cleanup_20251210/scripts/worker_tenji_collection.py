"""
オリジナル展示収集ワーカー（バックグラウンド実行用）

共通ワークフロークラスを使用し、進捗をジョブマネージャーに記録
"""
import os
import sys
import argparse

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.utils.job_manager import update_job_progress, complete_job
from src.workflow.tenji_collection import TenjiCollectionWorkflow

JOB_NAME = 'tenji_collection'


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
    parser.add_argument('days_offset', type=int, default=0, nargs='?',
                        help='日数オフセット（0=今日, -1=昨日）')
    args = parser.parse_args()

    print("=" * 60)
    print("オリジナル展示データ収集 - バックグラウンド処理")
    print("=" * 60)

    try:
        # 共通ワークフローを使用
        workflow = TenjiCollectionWorkflow(
            db_path=os.path.join(PROJECT_ROOT, 'data/boatrace.db'),
            project_root=PROJECT_ROOT,
            progress_callback=progress_callback
        )

        result = workflow.run(days_offset=args.days_offset)

        if result['success'] and result['races_collected'] > 0:
            final_message = f"収集完了: {result['races_collected']}件"
            complete_job(
                JOB_NAME,
                success=True,
                message=final_message
            )
            print("=" * 60)
            print("処理完了")
            print(f"  収集数: {result['races_collected']}")
            print(f"  会場: {result['venues_success']}/{result['venues_total']}")
            print("=" * 60)
        elif result['success']:
            # 成功だが収集件数が0（開催なし等）
            complete_job(
                JOB_NAME,
                success=True,
                message=result.get('message', '対象レースなし')
            )
        else:
            # 失敗
            complete_job(
                JOB_NAME,
                success=False,
                message=result.get('message', 'エラー発生')
            )

    except Exception as e:
        complete_job(JOB_NAME, success=False, message=f'エラー: {str(e)}')
        print(f"エラー発生: {e}")
        raise


if __name__ == '__main__':
    main()
