"""
オリジナル展示収集ワーカー（バックグラウンド実行用）

このスクリプトはジョブマネージャーから呼び出され、
進捗をファイルに書き込みながら処理を行う
"""
import os
import sys
import argparse
from datetime import datetime, timedelta

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.utils.job_manager import update_job_progress, complete_job

JOB_NAME = 'tenji_collection'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('days_offset', type=int, default=0, nargs='?',
                        help='日数オフセット（0=今日, -1=昨日）')
    args = parser.parse_args()

    days_offset = args.days_offset
    target_date = datetime.now().date() + timedelta(days=days_offset)

    try:
        update_job_progress(JOB_NAME, {
            'status': 'running',
            'progress': 10,
            'message': f'{target_date} のオリジナル展示データを収集開始',
            'target_date': str(target_date)
        })

        # 実際の収集処理を呼び出し（最適化版）
        script_path = os.path.join(PROJECT_ROOT, 'fetch_original_tenji_daily.py')

        if not os.path.exists(script_path):
            complete_job(JOB_NAME, success=False, message='収集スクリプトが見つかりません')
            return

        import subprocess
        import tempfile

        # 出力をファイルにリダイレクト（バッファブロック防止）
        log_dir = os.path.join(PROJECT_ROOT, 'temp', 'jobs')
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f'{JOB_NAME}_output.log')

        # 日付引数を準備
        if days_offset == 0:
            date_args = ['--today']
        else:
            target_date_str = (datetime.now().date() + timedelta(days=days_offset)).strftime('%Y-%m-%d')
            date_args = ['--date', target_date_str]

        with open(log_file, 'w', encoding='utf-8') as f:
            result = subprocess.run(
                [sys.executable, script_path] + date_args,
                stdout=f,
                stderr=subprocess.STDOUT,
                timeout=600,
                cwd=PROJECT_ROOT
            )

        # ログファイルから結果を読み取り
        output = ''
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                output = f.read()
        except:
            pass

        if result.returncode == 0:
            # 成功件数を抽出
            success_line = ''
            if "成功:" in output:
                for line in output.split('\n'):
                    if '成功:' in line:
                        success_line = line
                        break

            complete_job(JOB_NAME, success=True,
                        message=f'{target_date} の収集完了 {success_line}')
        else:
            # エラー内容をログから抽出
            error_msg = output[-500:] if output else '不明なエラー'
            complete_job(JOB_NAME, success=False,
                        message=f'収集エラー: {error_msg[:200]}')

    except subprocess.TimeoutExpired:
        complete_job(JOB_NAME, success=False, message='タイムアウト（10分経過）')
    except Exception as e:
        complete_job(JOB_NAME, success=False, message=f'エラー: {str(e)[:200]}')


if __name__ == '__main__':
    main()
