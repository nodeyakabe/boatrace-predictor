#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
不一致原因のデバッグスクリプト

Tier 2で購入対象となるレースがTier 3で除外される理由を特定する
"""
import sqlite3
import sys
import os
from collections import Counter

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from src.betting.evaluator_helpers import create_custom_evaluator
from src.betting.bet_target_evaluator import BetStatus


def get_race_data(cursor, race_id: str):
    """レースデータを取得"""
    cursor.execute("""
        SELECT id, venue_code, race_number, race_date, race_time
        FROM races WHERE id = ?
    """, (race_id,))

    row = cursor.fetchone()
    if not row:
        return None

    # 気象情報
    cursor.execute("SELECT wind_speed FROM race_conditions WHERE race_id = ?", (race_id,))
    conditions_row = cursor.fetchone()
    wind_speed = conditions_row['wind_speed'] if conditions_row and conditions_row['wind_speed'] else 0.0

    # エントリー情報
    cursor.execute("""
        SELECT pit_number, racer_number, racer_name, racer_rank, motor_second_rate, second_rate
        FROM entries WHERE race_id = ? ORDER BY pit_number
    """, (race_id,))
    entries = [dict(row) for row in cursor.fetchall()]

    return {
        'id': row['id'],
        'venue_code': row['venue_code'],
        'race_number': row['race_number'],
        'race_date': row['race_date'],
        'race_time': row['race_time'],
        'wind_speed': wind_speed,
        'entries': entries
    }


def get_predictions(cursor, race_id: str):
    """予測データを取得"""
    cursor.execute("""
        SELECT pit_number, rank_prediction, confidence
        FROM race_predictions
        WHERE race_id = ? AND prediction_type = 'before'
        ORDER BY rank_prediction
    """, (race_id,))

    predictions = [dict(row) for row in cursor.fetchall()]
    if len(predictions) < 3:
        return None

    old_pred = [p['pit_number'] for p in predictions]
    return {
        'confidence': predictions[0]['confidence'],
        'old_prediction': old_pred,
        'new_prediction': old_pred,
        'full_prediction': old_pred[:6] if len(old_pred) >= 6 else old_pred
    }


def get_odds_data(cursor, race_id: str, predictions):
    """オッズデータを取得（パターンH対応：3点分）"""
    old_pred = predictions['old_prediction']

    if len(old_pred) < 3:
        return {}

    # パターンH用の3点（1-2-3, 1-2-4, 1-2-5）を取得
    combinations = []
    combinations.append(f"{old_pred[0]}-{old_pred[1]}-{old_pred[2]}")  # 1-2-3
    if len(old_pred) >= 4:
        combinations.append(f"{old_pred[0]}-{old_pred[1]}-{old_pred[3]}")  # 1-2-4
    if len(old_pred) >= 5:
        combinations.append(f"{old_pred[0]}-{old_pred[1]}-{old_pred[4]}")  # 1-2-5

    # 3点分のオッズを一度に取得
    placeholders = ','.join(['?'] * len(combinations))
    cursor.execute(f"""
        SELECT combination, odds
        FROM trifecta_odds
        WHERE race_id = ? AND combination IN ({placeholders})
    """, (race_id, *combinations))

    return {row['combination']: row['odds'] for row in cursor.fetchall()}


def analyze_sample_races():
    """サンプルレースの不一致原因を分析"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Tier 3と同じ設定でevaluatorを作成（風速フィルター無効化）
    from src.betting.evaluator_helpers import create_custom_evaluator
    evaluator = create_custom_evaluator(
        enable_venue_wind_filter=False,
        db_path=DATABASE_PATH
    )

    # サンプルレースを取得（Tier 2で購入対象となるレース）
    query = '''
    SELECT DISTINCT
        r.id,
        r.race_date,
        r.venue_code,
        r.race_number,
        rp1.confidence,
        e1.racer_rank as c1_rank,
        rp1.pit_number as p1,
        rp2.pit_number as p2,
        rp3.pit_number as p3
    FROM races r
    JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
    JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
    WHERE rp1.confidence IN ('A', 'B', 'C', 'D')
      AND e1.racer_rank IN ('A1', 'A2', 'B1')
      AND r.race_date >= '2024-01-01'
      AND r.race_date < '2026-01-01'
    ORDER BY RANDOM()
    LIMIT 100
    '''

    cursor.execute(query)
    sample_races = cursor.fetchall()

    print(f"=== 不一致原因分析（サンプル{len(sample_races)}件）===\n")

    # 除外理由カウンター
    exclusion_reasons = Counter()
    tier3_bet_count = 0
    tier3_excluded_count = 0

    excluded_samples = []

    for race_row in sample_races:
        race_id = race_row['id']

        # レースデータを取得
        race_data = get_race_data(cursor, race_id)
        if not race_data:
            continue

        # 予測データを取得
        predictions = get_predictions(cursor, race_id)
        if not predictions:
            continue

        # オッズデータを取得
        odds_data = get_odds_data(cursor, race_id, predictions)
        if not odds_data:
            exclusion_reasons['オッズデータなし'] += 1
            tier3_excluded_count += 1
            excluded_samples.append({
                'race_id': race_id,
                'date': race_row['race_date'],
                'venue': race_row['venue_code'],
                'race_num': race_row['race_number'],
                'confidence': race_row['confidence'],
                'c1_rank': race_row['c1_rank'],
                'reason': 'オッズデータなし'
            })
            continue

        # Tier 3で購入判定
        try:
            bet_target = evaluator.evaluate_race(
                race_data=race_data,
                predictions=predictions,
                odds_data=odds_data,
                has_beforeinfo=True
            )

            if bet_target.status in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
                tier3_bet_count += 1
            else:
                tier3_excluded_count += 1
                reason = bet_target.reason
                exclusion_reasons[reason] += 1

                # 最初の30件のみ詳細を保存
                if len(excluded_samples) < 30:
                    excluded_samples.append({
                        'race_id': race_id,
                        'date': race_row['race_date'],
                        'venue': race_row['venue_code'],
                        'race_num': race_row['race_number'],
                        'confidence': race_row['confidence'],
                        'c1_rank': race_row['c1_rank'],
                        'reason': reason
                    })

        except Exception as e:
            exclusion_reasons[f'エラー: {str(e)[:50]}'] += 1
            tier3_excluded_count += 1
            continue

    # 結果サマリー
    print(f"サンプルレース数: {len(sample_races)}")
    print(f"Tier 3購入対象: {tier3_bet_count}件")
    print(f"Tier 3除外: {tier3_excluded_count}件")
    print(f"一致率（サンプル内）: {100.0 * tier3_bet_count / len(sample_races):.2f}%\n")

    # 除外理由TOP10
    print("=== 除外理由TOP10 ===")
    for reason, count in exclusion_reasons.most_common(10):
        pct = 100.0 * count / tier3_excluded_count if tier3_excluded_count > 0 else 0
        print(f"{count:3}件 ({pct:5.1f}%) - {reason}")

    print("\n=== 除外サンプル詳細（最大30件）===")
    print("race_id | date       | venue | R  | conf | c1 | reason")
    print("-" * 90)
    for sample in excluded_samples[:30]:
        print(f"{sample['race_id']:<7} | {sample['date']} | {sample['venue']:>5} | {sample['race_num']:>2} | {sample['confidence']} | {sample['c1_rank']:>2} | {sample['reason'][:60]}")

    conn.close()


if __name__ == '__main__':
    analyze_sample_races()
