#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
バッチ処理エラーの完全なデバッグ

エラーメッセージを切り詰めずに完全なスタックトレースを取得
"""
import sys
import os
import traceback

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

from scripts.fast_prediction_generator import FastPredictionGenerator

print("="*80)
print("バッチ処理エラー完全デバッグ")
print("="*80)

# advance予測を生成
gen = FastPredictionGenerator('advance')

# 2024-01-01の最初の5レースのみテスト
import sqlite3
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

cursor.execute("""
    SELECT id, venue_code, race_number
    FROM races
    WHERE race_date = '2024-01-01'
    ORDER BY venue_code, race_number
    LIMIT 5
""")

test_races = []
for row in cursor.fetchall():
    test_races.append({
        'race_id': row[0],
        'venue_code': row[1],
        'race_number': row[2],
        'venue_name': '桐生',  # 仮
        'race_date': '2024-01-01',
        'race_time': '10:00:00',
        'race_grade': '一般',
        'wind_speed': None,
        'wave_height': None,
        'wind_direction': None
    })

# エントリー情報を取得
race_ids = [r['race_id'] for r in test_races]
placeholders = ','.join(['?'] * len(race_ids))
cursor.execute(f"""
    SELECT race_id, pit_number, racer_number
    FROM entries
    WHERE race_id IN ({placeholders})
    ORDER BY race_id, pit_number
""", race_ids)

entries_by_race = {}
for row in cursor.fetchall():
    race_id = row[0]
    if race_id not in entries_by_race:
        entries_by_race[race_id] = []
    entries_by_race[race_id].append({
        'pit_number': row[1],
        'racer_number': row[2]
    })

conn.close()

print(f"\nテスト対象: {len(test_races)}レース")
print("="*80)

# データロード
if gen.predictor.batch_loader:
    print("\n日次データロード中...")
    gen.predictor.batch_loader.load_daily_data('2024-01-01')
    print("データロード完了")

# 各レースで予測実行
for idx, race in enumerate(test_races, 1):
    race_id = race['race_id']
    entries = entries_by_race.get(race_id, [])

    print(f"\n[{idx}/{len(test_races)}] race_id={race_id}, エントリー={len(entries)}艇")
    print("-"*80)

    try:
        # predict_race_fastの中身を直接実行してエラー箇所を特定
        try:
            predictions = gen.predictor.predict_race(race_id, use_beforeinfo=gen.use_beforeinfo)

            if predictions:
                print(f"✅ 成功: {len(predictions)}件の予測")
            else:
                print("⚠️ 予測結果が空")

        except Exception as inner_e:
            print(f"\n❌ predict_race内でエラー発生!")
            print(f"エラー型: {type(inner_e).__name__}")
            print(f"エラーメッセージ: {inner_e}")
            print("\n完全なスタックトレース:")
            print("="*80)

            # トレースバックをファイルに保存
            with open('error_traceback.txt', 'w', encoding='utf-8') as f:
                f.write(f"race_id: {race_id}\n")
                f.write(f"エラー型: {type(inner_e).__name__}\n")
                f.write(f"エラーメッセージ: {inner_e}\n\n")
                f.write("完全なスタックトレース:\n")
                traceback.print_exc(file=f)

            # コンソールにも出力
            import sys
            traceback.print_exc(file=sys.stdout)
            print("="*80)

            print("\nエラー詳細を error_traceback.txt に保存しました")

            # 最初のエラーで停止
            break

    except Exception as e:
        print(f"\n❌ 外側でエラー発生!")
        print(f"エラー型: {type(e).__name__}")
        print(f"エラーメッセージ: {e}")
        print("\n完全なスタックトレース:")
        print("="*80)
        traceback.print_exc()
        print("="*80)

        # 最初のエラーで停止
        break

print("\n" + "="*80)
print("デバッグ完了")
print("="*80)
