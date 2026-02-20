#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
予測結果の構造を確認するデバッグスクリプト
"""
import sys
import os
import io
import json

# Windows環境でのstdout/stderrエンコーディングをUTF-8に設定
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.analysis.race_predictor import RacePredictor
from config.settings import DATABASE_PATH
import sqlite3


# 2025-01-01の1レースを取得
conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()

cursor.execute("""
    SELECT id, race_date, venue_code, race_number
    FROM races
    WHERE race_date = '2025-01-01'
    ORDER BY venue_code, race_number
    LIMIT 1
""")

race_row = cursor.fetchone()
conn.close()

if not race_row:
    print("レースが見つかりませんでした")
    sys.exit(1)

race_id, race_date, venue_code, race_number = race_row
print(f"テストレース: {race_date} {venue_code} {race_number}R (race_id={race_id})")
print()

# 予測を生成
predictor = RacePredictor(use_cache=True)
predictions = predictor.predict_race(race_id, use_beforeinfo=True)

print(f"予測結果のタイプ: {type(predictions)}")
print(f"予測結果の件数: {len(predictions) if predictions else 0}")
print()

if predictions and len(predictions) > 0:
    # 1艇目の構造を詳細に表示
    first_pred = predictions[0]
    print("=" * 80)
    print("1艇目の予測結果構造:")
    print("=" * 80)

    for key, value in first_pred.items():
        value_type = type(value).__name__

        if isinstance(value, dict):
            print(f"\n{key} (dict):")
            for sub_key, sub_value in value.items():
                print(f"  {sub_key}: {sub_value} ({type(sub_value).__name__})")
        elif isinstance(value, (list, tuple)):
            print(f"\n{key} ({value_type}, length={len(value)}):")
            if len(value) > 0:
                print(f"  [0]: {value[0]}")
        else:
            # 値が長すぎる場合は省略
            str_value = str(value)
            if len(str_value) > 100:
                str_value = str_value[:100] + "..."
            print(f"{key}: {str_value} ({value_type})")

    # extended_scoreの詳細確認
    print("\n" + "=" * 80)
    print("extended_score の詳細:")
    print("=" * 80)

    ext_score = first_pred.get('extended_score')
    print(f"extended_score のタイプ: {type(ext_score)}")

    if isinstance(ext_score, dict):
        print("\nextended_score の内容:")
        for key, value in ext_score.items():
            if isinstance(value, dict):
                print(f"\n  {key} (dict):")
                for sub_key, sub_value in value.items():
                    print(f"    {sub_key}: {sub_value}")
            else:
                print(f"  {key}: {value} ({type(value).__name__})")
    else:
        print(f"extended_score は辞書ではありません: {ext_score}")

    # JSONに整形して保存
    output_file = os.path.join(PROJECT_ROOT, 'temp', 'prediction_structure_sample.json')
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        # JSONシリアライズ可能な形式に変換
        json_data = []
        for pred in predictions:
            json_pred = {}
            for key, value in pred.items():
                try:
                    json.dumps(value)  # シリアライズ可能かテスト
                    json_pred[key] = value
                except:
                    json_pred[key] = str(value)
            json_data.append(json_pred)

        json.dump(json_data, f, ensure_ascii=False, indent=2)

    print(f"\n予測結果をJSONに保存: {output_file}")

else:
    print("予測結果が空です")
