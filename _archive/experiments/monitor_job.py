"""
ジョブ監視スクリプト
"""
import sys
import json
import time
from datetime import datetime

sys.path.insert(0, 'src')

print('不足データ取得ジョブを監視中...')
print('=' * 70)
print()

last_progress = -1
last_message = ''
start_time = time.time()

for i in range(180):  # 最大15分間監視
    try:
        with open('temp/jobs/missing_data_fetch.json', 'r', encoding='utf-8') as f:
            job = json.load(f)

        status = job.get('status')
        progress = job.get('progress', 0)
        message = job.get('message', '')
        phase = job.get('phase', 0)
        total_steps = job.get('total_steps', 2)
        processed = job.get('processed', 0)
        total = job.get('total', 0)
        errors = job.get('errors', 0)

        # 進捗が変わったときだけ表示
        if progress != last_progress or message != last_message:
            elapsed = time.time() - start_time
            elapsed_min = int(elapsed // 60)
            elapsed_sec = int(elapsed % 60)

            print(f'[{elapsed_min:02d}:{elapsed_sec:02d}] フェーズ{phase}/{total_steps} | {progress}% | {message}')
            print(f'        処理: {processed}/{total} | エラー: {errors}')

            last_progress = progress
            last_message = message

        # 終了チェック
        if status in ['completed', 'failed', 'cancelled']:
            print()
            print('=' * 70)
            print(f'ジョブ終了: {status}')
            print(f'最終メッセージ: {message}')
            print(f'処理件数: {processed}/{total}')
            print(f'エラー: {errors}件')

            elapsed = time.time() - start_time
            print(f'実行時間: {int(elapsed//60)}分{int(elapsed%60)}秒')
            print('=' * 70)
            break

        time.sleep(5)

    except FileNotFoundError:
        print('ジョブファイルが見つかりません')
        break
    except Exception as e:
        print(f'エラー: {e}')
        time.sleep(5)
else:
    print()
    print('タイムアウト（15分経過）- ジョブはまだ実行中です')
