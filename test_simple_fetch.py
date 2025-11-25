"""
簡易テスト: 最終保存日確認のみ
"""
import sys
import sqlite3
from datetime import datetime, timedelta

DB_PATH = "data/boatrace.db"

# 出力バッファリング無効化
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

print("=" * 80, flush=True)
print("過去データ取得 - 最終保存日確認テスト", flush=True)
print("=" * 80, flush=True)

try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT MAX(race_date) FROM races")
    result = cursor.fetchone()

    if result and result[0]:
        last_date_str = result[0]
        last_date = datetime.strptime(last_date_str, '%Y-%m-%d')

        print(f"\n[OK] 最終保存日: {last_date_str}", flush=True)

        # 次の取得日
        next_date = last_date + timedelta(days=1)
        today = datetime.now()

        print(f"[INFO] 次の取得日: {next_date.strftime('%Y-%m-%d')}", flush=True)
        print(f"[INFO] 今日: {today.strftime('%Y-%m-%d')}", flush=True)

        days_to_fetch = (today - next_date).days + 1

        if days_to_fetch > 0:
            print(f"\n[INFO] 取得が必要な日数: {days_to_fetch}日", flush=True)
            print(f"[INFO] 期間: {next_date.strftime('%Y-%m-%d')} ~ {today.strftime('%Y-%m-%d')}", flush=True)
        else:
            print(f"\n[OK] データは最新です！", flush=True)

    else:
        print("\n[WARN] データがありません", flush=True)

    cursor.execute("SELECT COUNT(*) FROM races")
    total = cursor.fetchone()[0]
    print(f"\n[INFO] 総レース数: {total:,}件", flush=True)

    conn.close()

    print("\n" + "=" * 80, flush=True)
    print("[OK] テスト完了", flush=True)
    print("=" * 80, flush=True)

except Exception as e:
    print(f"\n[ERROR] {e}", flush=True)
    import traceback
    traceback.print_exc()
