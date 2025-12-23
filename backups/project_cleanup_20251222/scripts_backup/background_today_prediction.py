"""
今日の予測生成 - バックグラウンド実行スクリプト

共通ワークフロークラスを使用し、進捗をジョブマネージャーに記録
"""
import os
import sys
import warnings
warnings.filterwarnings('ignore')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.utils.job_manager import update_job_progress, complete_job
from src.workflow.today_prediction import TodayPredictionWorkflow

JOB_NAME = 'today_prediction'


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
    """メイン処理"""
    print("=" * 60)
    print("今日の予測生成 - バックグラウンド処理")
    print("=" * 60)

    try:
        # 共通ワークフローを使用
        workflow = TodayPredictionWorkflow(
            db_path=os.path.join(PROJECT_ROOT, 'data/boatrace.db'),
            project_root=PROJECT_ROOT,
            progress_callback=progress_callback
        )

        result = workflow.run()

        if result['success']:
            complete_job(
                JOB_NAME,
                success=True,
                message=f"今日の予測生成が完了しました（{result['predictions_generated']}レース）"
            )
            print("=" * 60)
            print("処理完了")
            print(f"  取得レース: {result['races_fetched']}")
            print(f"  予測生成: {result['predictions_generated']}")
            print(f"  オッズ取得: {result['odds_fetched']}")
            print("=" * 60)
        else:
            complete_job(
                JOB_NAME,
                success=False,
                message=f"エラー: {', '.join(result['errors'])}"
            )

    except Exception as e:
        complete_job(JOB_NAME, success=False, message=f'エラー: {str(e)}')
        print(f"エラー発生: {e}")
        raise


if __name__ == '__main__':
    main()
