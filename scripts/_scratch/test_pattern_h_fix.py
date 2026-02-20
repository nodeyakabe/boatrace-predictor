#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""パターンH判定ロジックの修正テスト"""
import sqlite3
from config.settings import DATABASE_PATH
from src.betting.evaluator_helpers import create_standard_evaluator

# Evaluator作成
evaluator = create_standard_evaluator()

# DB接続
conn = sqlite3.connect(DATABASE_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# パターンH条件でテストするレースを探す（B×50-100条件）
cursor.execute("""
    SELECT
        r.id,
        r.race_date,
        r.venue_code,
        r.race_number
    FROM races r
    JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
    WHERE rp.confidence = 'B'
      AND r.venue_code IN ('01', '04', '07', '08', '09', '11', '19', '21', '22')  -- B×50-100の会場
      AND r.race_date >= '2024-01-01'
    GROUP BY r.id
    HAVING COUNT(rp.pit_number) >= 5
    LIMIT 5
""")

test_races = cursor.fetchall()

print("=" * 80)
print("パターンH判定ロジック修正テスト")
print("=" * 80)
print()

for race_row in test_races:
    race_id = race_row['id']

    # レースデータ取得
    cursor.execute("SELECT * FROM races WHERE id = ?", (race_id,))
    race_data_row = cursor.fetchone()

    # 気象データ
    cursor.execute("SELECT wind_speed FROM race_conditions WHERE race_id = ?", (race_id,))
    cond_row = cursor.fetchone()
    wind_speed = cond_row['wind_speed'] if cond_row else 0.0

    # エントリー取得
    cursor.execute("""
        SELECT pit_number, racer_number, racer_name, racer_rank, motor_second_rate, second_rate
        FROM entries WHERE race_id = ? ORDER BY pit_number
    """, (race_id,))
    entries = [dict(row) for row in cursor.fetchall()]

    # 予測取得
    cursor.execute("""
        SELECT pit_number, rank_prediction, confidence
        FROM race_predictions
        WHERE race_id = ? AND prediction_type = 'before'
        ORDER BY rank_prediction
    """, (race_id,))
    pred_rows = [dict(row) for row in cursor.fetchall()]

    if len(pred_rows) < 5:
        continue

    old_pred = [p['pit_number'] for p in pred_rows]
    confidence = pred_rows[0]['confidence']

    # オッズ取得（3点分）
    combo_123 = f"{old_pred[0]}-{old_pred[1]}-{old_pred[2]}"
    combo_124 = f"{old_pred[0]}-{old_pred[1]}-{old_pred[3]}"
    combo_125 = f"{old_pred[0]}-{old_pred[1]}-{old_pred[4]}"

    cursor.execute("""
        SELECT combination, odds
        FROM trifecta_odds
        WHERE race_id = ? AND combination IN (?, ?, ?)
    """, (race_id, combo_123, combo_124, combo_125))

    odds_data = {row['combination']: row['odds'] for row in cursor.fetchall()}

    # レースデータ構築
    race_data = {
        'id': race_id,
        'venue_code': race_data_row['venue_code'],
        'race_number': race_data_row['race_number'],
        'race_date': race_data_row['race_date'],
        'race_time': race_data_row['race_time'],
        'wind_speed': wind_speed,
        'entries': entries
    }

    predictions = {
        'confidence': confidence,
        'old_prediction': old_pred,
        'new_prediction': old_pred
    }

    # BetTargetEvaluator評価
    try:
        bet_target = evaluator.evaluate_race(
            race_data=race_data,
            predictions=predictions,
            odds_data=odds_data,
            has_beforeinfo=True
        )

        print(f"レースID: {race_id}")
        print(f"  日付: {race_data_row['race_date']}, 会場: {race_data_row['venue_code']}, R{race_data_row['race_number']}")
        print(f"  信頼度: {confidence}")
        print(f"  予測順位: {old_pred}")
        print(f"  オッズ: {combo_123}={odds_data.get(combo_123, 'なし')}, {combo_124}={odds_data.get(combo_124, 'なし')}, {combo_125}={odds_data.get(combo_125, 'なし')}")
        print(f"  判定結果: {bet_target.status.value}")
        print(f"  買い目: {bet_target.combination}")
        print(f"  オッズ: {bet_target.odds}")
        print(f"  理由: {bet_target.reason}")
        print(f"  パターンH: {bet_target.use_pattern_h}")
        print()
    except Exception as e:
        print(f"レースID: {race_id} - エラー: {e}")
        import traceback
        traceback.print_exc()
        print()

conn.close()

print("テスト完了")
