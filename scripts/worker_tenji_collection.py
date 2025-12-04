"""
オリジナル展示収集ワーカー（バックグラウンド実行用）

共通ワークフロークラスを使用し、進捗をジョブマネージャーに記録
"""
import os
import sys
import argparse
from datetime import datetime, timedelta

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.utils.job_manager import update_job_progress, complete_job
from src.workflow.tenji_collection import TenjiCollectionWorkflow
import subprocess

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
            # 展示データ収集成功時、予測を再生成
            target_date = (datetime.now() + timedelta(days=args.days_offset)).strftime('%Y-%m-%d')

            update_job_progress(JOB_NAME, {
                'status': 'running',
                'step': '予測再生成',
                'message': f'{target_date} の予測を再生成中...',
                'progress': 95
            })
            print(f"\n予測を再生成中: {target_date}")

            try:
                # fast_prediction_generator.pyを実行
                generator_path = os.path.join(PROJECT_ROOT, 'scripts', 'fast_prediction_generator.py')
                cmd = [sys.executable, generator_path, '--date', target_date]

                result_gen = subprocess.run(
                    cmd,
                    cwd=PROJECT_ROOT,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    timeout=300
                )

                if result_gen.returncode == 0:
                    # 成功時のメッセージをパース
                    output_lines = result_gen.stdout.strip().split('\n')
                    prediction_count = 0
                    for line in output_lines:
                        if '予測生成完了' in line or '件' in line:
                            print(line)
                            # 件数を抽出
                            import re
                            match = re.search(r'(\d+)件', line)
                            if match:
                                prediction_count = int(match.group(1))

                    final_message = f"収集完了: {result['races_collected']}件 / 予測更新: {prediction_count}件"
                    print(f"予測再生成完了: {prediction_count}件")
                else:
                    print(f"予測再生成エラー (code={result_gen.returncode})")
                    print(result_gen.stderr)
                    final_message = f"収集完了: {result['races_collected']}件 (予測更新失敗)"

            except subprocess.TimeoutExpired:
                print("予測再生成タイムアウト (5分)")
                final_message = f"収集完了: {result['races_collected']}件 (予測更新タイムアウト)"
            except Exception as e:
                print(f"予測再生成エラー: {e}")
                final_message = f"収集完了: {result['races_collected']}件 (予測更新失敗)"

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
        else:
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
