#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2024年全体のデータを収集するスクリプト
月ごとに分割して実行し、進捗を表示
"""
import sys
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

# 2024年の月別期間
MONTHS_2024 = [
    ('2024-01-01', '2024-01-31', '1月'),
    ('2024-02-01', '2024-02-29', '2月'),
    ('2024-03-01', '2024-03-31', '3月'),
    ('2024-04-01', '2024-04-30', '4月'),
    ('2024-05-01', '2024-05-31', '5月'),
    ('2024-06-01', '2024-06-30', '6月'),
    ('2024-07-01', '2024-07-31', '7月'),
    ('2024-08-01', '2024-08-31', '8月'),
    ('2024-09-01', '2024-09-30', '9月'),
    ('2024-10-01', '2024-10-31', '10月'),
    ('2024-11-01', '2024-11-30', '11月'),
    ('2024-12-01', '2024-12-31', '12月'),
]

def main():
    print("=" * 70)
    print("2024年全体のデータ収集")
    print("=" * 70)
    print(f"総月数: {len(MONTHS_2024)}ヶ月")
    print()

    start_time = datetime.now()

    for i, (start, end, month_name) in enumerate(MONTHS_2024, 1):
        print(f"\n[{i}/{len(MONTHS_2024)}] 2024年{month_name} ({start} ~ {end}) を収集中...")

        # fetch_historical_data.pyを呼び出し（予測生成なし）
        cmd = [
            sys.executable,
            str(ROOT_DIR / 'scripts' / 'fetch_historical_data.py'),
            '--start', start,
            '--end', end,
            '--no-predict'
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=1800  # 30分タイムアウト
            )

            # 結果の最後の20行を表示
            output_lines = result.stdout.split('\n')
            for line in output_lines[-20:]:
                if line.strip():
                    print(f"  {line}")

            if result.returncode != 0:
                print(f"  [!] エラーが発生しました（終了コード: {result.returncode}）")
                if result.stderr:
                    print(f"  エラー: {result.stderr[-500:]}")

        except subprocess.TimeoutExpired:
            print(f"  [!] タイムアウト（30分超過）")
        except Exception as e:
            print(f"  [!] エラー: {e}")

        # 進捗表示
        elapsed = (datetime.now() - start_time).total_seconds()
        avg_time = elapsed / i
        remaining = avg_time * (len(MONTHS_2024) - i)
        print(f"\n  進捗: {i}/{len(MONTHS_2024)} ({i/len(MONTHS_2024)*100:.1f}%)")
        print(f"  経過時間: {elapsed/60:.1f}分, 残り推定: {remaining/60:.1f}分")

    print("\n" + "=" * 70)
    print("完了")
    print("=" * 70)
    print(f"総処理時間: {(datetime.now() - start_time).total_seconds()/60:.1f}分")
    print("=" * 70)

if __name__ == '__main__':
    main()
