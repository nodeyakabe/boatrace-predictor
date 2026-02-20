#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""2020年のbefore予想を月別に生成するシンプルスクリプト"""
import sys
import io
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).parent
SCRIPT = PROJECT_ROOT / "scripts" / "prediction" / "fast_prediction_generator.py"
LOG_FILE = PROJECT_ROOT / "logs" / f"gen2020before_{datetime.now().strftime('%H%M%S')}.log"


def log(msg):
    """コンソールとログファイルの両方に出力"""
    print(msg, flush=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')


# 2020年の各月の代表日
dates_2020 = [
    "2020-01-05", "2020-02-02", "2020-03-01", "2020-04-01",
    "2020-05-01", "2020-06-01", "2020-07-01", "2020-08-01",
    "2020-09-01", "2020-10-01", "2020-11-01", "2020-12-01"
]

log("="*70)
log("2020年 before予想生成（月別実行）")
log("="*70)
log(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
log(f"ログ: {LOG_FILE}")
log(f"対象月数: {len(dates_2020)}ヶ月")
log("")

success_count = 0
failed_count = 0
start_time = datetime.now()

for i, date in enumerate(dates_2020, 1):
    log(f"\n[{i}/{len(dates_2020)}] {date[:7]} 処理中...")

    cmd = [
        sys.executable,
        str(SCRIPT),
        "--date", date,
        "--type", "before"
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=600
        )

        if result.returncode == 0:
            success_count += 1
            # 簡潔な成功メッセージ
            lines = result.stdout.split('\n')
            for line in lines:
                if '既存スキップ:' in line or '生成完了:' in line or '更新完了:' in line:
                    log(f"  ✅ {line.strip()}")
                    break
            else:
                log(f"  ✅ 完了")
        else:
            failed_count += 1
            log(f"  ❌ 失敗（終了コード: {result.returncode}）")
            if result.stderr:
                log(f"     エラー: {result.stderr[:200]}")

    except subprocess.TimeoutExpired:
        failed_count += 1
        log(f"  ❌ タイムアウト")
    except Exception as e:
        failed_count += 1
        log(f"  ❌ エラー: {e}")

    # 進捗サマリー
    if i % 3 == 0 or i == len(dates_2020):
        elapsed = (datetime.now() - start_time).total_seconds()
        rate = i / elapsed if elapsed > 0 else 0
        remaining_months = len(dates_2020) - i
        eta_seconds = remaining_months / rate if rate > 0 else 0
        eta = datetime.now().replace(microsecond=0) + timedelta(seconds=eta_seconds)
        log(f"\n  📊 進捗: {i}/{len(dates_2020)}ヶ月 ({100*i/len(dates_2020):.1f}%) "
            f"成功={success_count} 失敗={failed_count}")
        if remaining_months > 0:
            log(f"  完了予定: {eta.strftime('%H:%M')}")

elapsed = (datetime.now() - start_time).total_seconds()

log("\n" + "="*70)
log("完了サマリー")
log("="*70)
log(f"対象月数: {len(dates_2020)}ヶ月")
log(f"成功: {success_count}ヶ月 ✅")
log(f"失敗: {failed_count}ヶ月 ❌")
log(f"処理時間: {elapsed/60:.1f}分")
log(f"完了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
log("="*70)

sys.exit(0 if failed_count == 0 else 1)
