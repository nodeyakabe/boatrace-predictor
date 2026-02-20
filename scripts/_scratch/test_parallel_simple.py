# -*- coding: utf-8 -*-
"""シンプルな並列処理テスト"""
import sys
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

print("="*80)
print("並列処理テスト開始")
print("="*80)

# DB接続テスト
print("\nDB接続中...")
conn = sqlite3.connect('data/boatrace.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
    SELECT DISTINCT venue_code, race_date
    FROM races
    WHERE race_date BETWEEN ? AND ?
    ORDER BY race_date, venue_code
    LIMIT 5
""", ('2020-01-01', '2020-01-31'))

tasks = cursor.fetchall()
conn.close()

print(f"タスク数: {len(tasks)}")
print("タスク一覧:", tasks)

# タスク準備
print("\nタスク準備中...")
task_list = list(tasks)
task_count = len(task_list)
print(f"準備完了: {task_count}件")

# シンプルな処理関数
def simple_task(args):
    venue_code, race_date = args
    time.sleep(0.1)  # 処理のシミュレーション
    return {'venue_code': venue_code, 'race_date': race_date, 'status': 'ok'}

# 並列処理開始
print("\nThreadPoolExecutor起動...")
sys.stdout.flush()

with ThreadPoolExecutor(max_workers=2) as executor:
    print("ThreadPoolExecutor起動成功")
    sys.stdout.flush()

    futures = {executor.submit(simple_task, task): task for task in task_list}
    print(f"タスク投入完了: {len(futures)}件")
    sys.stdout.flush()

    for i, future in enumerate(as_completed(futures), 1):
        result = future.result()
        print(f"[{i}/{task_count}] 完了: {result['venue_code']} {result['race_date']}")
        sys.stdout.flush()

print("\n完了")
