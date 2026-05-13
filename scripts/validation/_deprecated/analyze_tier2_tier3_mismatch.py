#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tier 2とTier 3の不一致レース詳細調査

目的:
    - 32%の不一致レースの原因を全数調査
    - SQLとPythonのロジック差異を特定
    - データ取得の違いを検証
"""
import sqlite3
import sys
import io
import os
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from src.betting.evaluator_helpers import create_custom_evaluator
from src.betting.bet_target_evaluator import BetStatus
from config.bet_conditions import STANDARD_BET_CONDITIONS

def get_tier2_purchase_races() -> List[str]:
    """Tier 2（標準バックテスト）で購入対象となったレースIDを全件取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    all_races = set()

    for cond in STANDARD_BET_CONDITIONS:
        # standard_backtest.pyのSQLを再現
        c1_rank_str = "','".join(cond['c1_rank'])
        use_pattern_h = cond.get('use_pattern_h', True)

        # 会場フィルター
        venue_clause = ""
        if cond.get('venue_filter'):
            venue_codes = []
            for v in cond['venue_filter']:
                if isinstance(v, int):
                    venue_codes.append(f"'{v:02d}'")
                else:
                    venue_codes.append(f"'{v}'")
            venue_clause = f"AND r.venue_code IN ({','.join(venue_codes)})"

        # 月除外フィルター
        month_exclude_clause = ""
        if cond.get('month_exclude'):
            months = ','.join(map(str, cond['month_exclude']))
            month_exclude_clause = f"AND CAST(strftime('%m', r.race_date) AS INTEGER) NOT IN ({months})"

        # 逃げ率フィルター
        escape_rate_join = ""
        escape_rate_clause = ""
        if cond.get('escape_rate_min') is not None:
            escape_rate_join = """
            LEFT JOIN entries e_pred ON r.id = e_pred.race_id AND e_pred.pit_number = rp1.pit_number
            LEFT JOIN player_escape_stats pes ON e_pred.racer_number = pes.player_id AND pes.stadium_id IS NULL
            """
            escape_rate_clause = f"AND pes.escape_rate IS NOT NULL AND pes.escape_rate >= {cond['escape_rate_min']} "

        # バイアス指数フィルター
        bias_join = ""
        bias_clause = ""
        if cond.get('bias_max') is not None:
            bias_join = """
            LEFT JOIN entries e_bias ON r.id = e_bias.race_id AND e_bias.pit_number = rp1.pit_number
            LEFT JOIN player_bias_stats pbs ON e_bias.racer_number = pbs.player_id AND pbs.stadium_id IS NULL
            """
            bias_clause = f"AND pbs.bias_index IS NOT NULL AND pbs.bias_index < {cond['bias_max']} "

        # 予測コース
        predicted_course_clause = ""
        if cond.get('predicted_course'):
            predicted_course_clause = f"AND rp1.pit_number = {cond['predicted_course']}"

        # 2連率フィルター
        c1_second_rate_clause = ""
        if cond.get('c1_second_rate_min') is not None:
            c1_second_rate_clause += f"AND e1.second_rate >= {cond['c1_second_rate_min']} "
        if cond.get('c1_second_rate_max') is not None:
            c1_second_rate_clause += f"AND e1.second_rate < {cond['c1_second_rate_max']} "

        if use_pattern_h:
            # パターンH: 3点のいずれかがオッズ範囲内
            query = f"""
            WITH race_base AS (
                SELECT
                    r.id as race_id,
                    rp1.pit_number as p1,
                    rp2.pit_number as p2,
                    rp3.pit_number as p3,
                    rp4.pit_number as p4,
                    rp5.pit_number as p5
                FROM races r
                JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
                JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
                JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
                JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
                JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
                JOIN race_predictions rp5 ON r.id = rp5.race_id AND rp5.prediction_type = 'before' AND rp5.rank_prediction = 5
                JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
                {escape_rate_join}
                {bias_join}
                WHERE rp.rank_prediction = 1
                AND rp.confidence = '{cond['confidence']}'
                AND e1.racer_rank IN ('{c1_rank_str}')
                AND r.race_date >= '2020-01-01'
                AND r.race_date < '2026-01-01'
                {venue_clause}
                {month_exclude_clause}
                {predicted_course_clause}
                {c1_second_rate_clause}
                {escape_rate_clause}
                {bias_clause}
            ),
            race_with_odds AS (
                SELECT
                    rb.race_id,
                    COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                              AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)), 0) as odds_123,
                    COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                              AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p4 AS TEXT)), 0) as odds_124,
                    COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                              AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p5 AS TEXT)), 0) as odds_125
                FROM race_base rb
            )
            SELECT race_id
            FROM race_with_odds
            WHERE (odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']})
               OR (odds_124 >= {cond['odds_min']} AND odds_124 < {cond['odds_max']})
               OR (odds_125 >= {cond['odds_min']} AND odds_125 < {cond['odds_max']})
            """
        else:
            # 1点買い
            query = f"""
            WITH race_base AS (
                SELECT
                    r.id as race_id,
                    rp1.pit_number as p1,
                    rp2.pit_number as p2,
                    rp3.pit_number as p3
                FROM races r
                JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
                JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
                JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
                JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
                JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
                {escape_rate_join}
                {bias_join}
                WHERE rp.rank_prediction = 1
                AND rp.confidence = '{cond['confidence']}'
                AND e1.racer_rank IN ('{c1_rank_str}')
                AND r.race_date >= '2020-01-01'
                AND r.race_date < '2026-01-01'
                {venue_clause}
                {month_exclude_clause}
                {predicted_course_clause}
                {c1_second_rate_clause}
                {escape_rate_clause}
                {bias_clause}
            ),
            race_with_odds AS (
                SELECT
                    rb.race_id,
                    COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                              AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)), 0) as odds_123
                FROM race_base rb
            )
            SELECT race_id
            FROM race_with_odds
            WHERE odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']}
            """

        cursor.execute(query)
        race_ids = [row[0] for row in cursor.fetchall()]
        all_races.update(race_ids)
        print(f"  {cond['name']}: {len(race_ids)}件")

    conn.close()
    return list(all_races)


def get_tier3_purchase_races() -> List[str]:
    """Tier 3（BetTargetEvaluator）で購入対象となったレースIDを全件取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 風速フィルター無効化（Tier 2と合わせる）
    evaluator = create_custom_evaluator(
        enable_venue_wind_filter=False,
        db_path=DATABASE_PATH
    )

    # 期間内の全レースを取得
    cursor.execute("""
        SELECT id
        FROM races
        WHERE race_date >= '2020-01-01' AND race_date < '2026-01-01'
        ORDER BY race_date, race_time
    """)

    race_ids = [row['id'] for row in cursor.fetchall()]
    print(f"総レース数: {len(race_ids)}")

    bet_races = []

    for i, race_id in enumerate(race_ids):
        if (i + 1) % 10000 == 0:
            print(f"  処理中: {i+1}/{len(race_ids)}")

        # レースデータを取得
        cursor.execute("""
            SELECT id, venue_code, race_number, race_date, race_time
            FROM races WHERE id = ?
        """, (race_id,))
        row = cursor.fetchone()
        if not row:
            continue

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

        race_data = {
            'id': row['id'],
            'venue_code': row['venue_code'],
            'race_number': row['race_number'],
            'race_date': row['race_date'],
            'race_time': row['race_time'],
            'wind_speed': wind_speed,
            'entries': entries
        }

        # 予測データを取得
        cursor.execute("""
            SELECT pit_number, rank_prediction, confidence, racer_number
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'before'
            ORDER BY rank_prediction
        """, (race_id,))
        predictions = [dict(row) for row in cursor.fetchall()]
        if len(predictions) < 3:
            continue

        old_pred = [p['pit_number'] for p in predictions]
        first_racer_number = predictions[0]['racer_number']

        predictions_dict = {
            'confidence': predictions[0]['confidence'],
            'old_prediction': old_pred,
            'new_prediction': old_pred,
            'first_racer_number': first_racer_number
        }

        # オッズデータを取得（パターンH対応：3点分）
        combinations = []
        combinations.append(f"{old_pred[0]}-{old_pred[1]}-{old_pred[2]}")
        if len(old_pred) >= 4:
            combinations.append(f"{old_pred[0]}-{old_pred[1]}-{old_pred[3]}")
        if len(old_pred) >= 5:
            combinations.append(f"{old_pred[0]}-{old_pred[1]}-{old_pred[4]}")

        placeholders = ','.join(['?'] * len(combinations))
        cursor.execute(f"""
            SELECT combination, odds
            FROM trifecta_odds
            WHERE race_id = ? AND combination IN ({placeholders})
        """, (race_id, *combinations))

        odds_data = {row['combination']: row['odds'] for row in cursor.fetchall()}

        if not odds_data:
            continue

        # BetTargetEvaluatorで購入判定
        try:
            bet_target = evaluator.evaluate_race(
                race_data=race_data,
                predictions=predictions_dict,
                odds_data=odds_data,
                has_beforeinfo=True
            )

            if bet_target.status in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
                bet_races.append(race_id)

        except Exception as e:
            continue

    conn.close()
    print(f"Tier 3購入対象: {len(bet_races)}件")
    return bet_races


def analyze_mismatch_races(tier2_races: List[str], tier3_races: List[str]):
    """不一致レースを詳細分析"""
    tier2_set = set(tier2_races)
    tier3_set = set(tier3_races)

    # 一致・不一致の分類
    matched = tier2_set & tier3_set
    tier2_only = tier2_set - tier3_set
    tier3_only = tier3_set - tier2_set

    print("\n" + "=" * 80)
    print("不一致レース分析")
    print("=" * 80)
    print(f"Tier 2購入対象: {len(tier2_set):,}件")
    print(f"Tier 3購入対象: {len(tier3_set):,}件")
    print(f"一致: {len(matched):,}件 ({100*len(matched)/len(tier2_set):.2f}%)")
    print(f"Tier 2のみ: {len(tier2_only):,}件 ({100*len(tier2_only)/len(tier2_set):.2f}%)")
    print(f"Tier 3のみ: {len(tier3_only):,}件 ({100*len(tier3_only)/len(tier2_set):.2f}%)")

    # 不一致レースのサンプルを詳細調査
    print("\n" + "=" * 80)
    print("Tier 2のみ購入対象（Tier 3で除外）のサンプル調査")
    print("=" * 80)

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 条件別に不一致を集計
    condition_mismatch = defaultdict(lambda: {'tier2_only': 0, 'tier3_only': 0, 'matched': 0})

    for race_id in list(tier2_only)[:20]:
        cursor.execute("""
            SELECT r.id, r.venue_code, r.race_date, r.race_number,
                   rp.confidence,
                   e1.racer_rank as c1_rank,
                   rp1.pit_number as p1, rp2.pit_number as p2, rp3.pit_number as p3
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
            WHERE r.id = ?
        """, (race_id,))

        row = cursor.fetchone()
        if not row:
            continue

        combo = f"{row['p1']}-{row['p2']}-{row['p3']}"
        cursor.execute("SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?", (race_id, combo))
        odds_row = cursor.fetchone()
        odds = odds_row['odds'] if odds_row else 0

        print(f"\nレースID: {race_id}")
        print(f"  日付: {row['race_date']}, 会場: {row['venue_code']}, {row['race_number']}R")
        print(f"  信頼度: {row['confidence']}, 1コース級別: {row['c1_rank']}")
        print(f"  買い目: {combo}, オッズ: {odds:.1f}倍")
        print(f"  → Tier 2で購入対象、Tier 3で除外")

    conn.close()


def main():
    print("Tier 2とTier 3の不一致レース詳細調査")
    print("=" * 80)

    print("\n[STEP 1] Tier 2購入対象レースを抽出中...")
    tier2_races = get_tier2_purchase_races()
    print(f"Tier 2購入対象: {len(tier2_races)}件\n")

    print("[STEP 2] Tier 3購入対象レースを抽出中...")
    tier3_races = get_tier3_purchase_races()
    print()

    print("[STEP 3] 不一致レースを分析中...")
    analyze_mismatch_races(tier2_races, tier3_races)


if __name__ == '__main__':
    main()
