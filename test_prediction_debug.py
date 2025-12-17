#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
予測生成デバッグスクリプト
"""
import sys
import os
import traceback

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

from scripts.fast_prediction_generator import FastPredictionGenerator

# advance予測を生成
gen = FastPredictionGenerator('advance')

print("2024-01-01の最初の失敗レースでデバッグテスト")
print("="*70)

# 失敗したrace_id=134178でテスト
race_info = {
    'race_id': 134178,
    'venue_name': '鳴門',
    'race_number': 12
}

# エントリー情報を実際のDBから取得
import sqlite3
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()
cursor.execute('SELECT pit_number, racer_number FROM entries WHERE race_id = 134178 ORDER BY pit_number')
entries = [{'pit_number': row[0], 'racer_number': row[1]} for row in cursor.fetchall()]
conn.close()

print(f"race_id: {race_info['race_id']}")
print(f"エントリー数: {len(entries)}")

try:
    # 予測生成
    predictions = gen.predict_race_fast(race_info, entries)
    print(f"\n✅ 予測生成成功: {len(predictions)}件")

    # データベースに保存
    if predictions:
        print("\nデータベース保存テスト...")
        success = gen.data_manager.save_race_predictions(
            race_info['race_id'],
            predictions,
            prediction_type='advance'
        )
        if success:
            print("✅ DB保存成功")
        else:
            print("❌ DB保存失敗")

except Exception as e:
    print(f"\n❌ エラー発生:")
    print(f"エラー型: {type(e).__name__}")
    print(f"エラーメッセージ: {e}")
    print("\n完全なスタックトレース:")
    traceback.print_exc()

print("\n" + "="*70)
