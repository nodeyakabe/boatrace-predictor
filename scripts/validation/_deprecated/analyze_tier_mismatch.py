#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tier 2（SQL）とTier 3（Python）のミスマッチ詳細分析

目的:
    68.82%のマッチ率の原因を特定し、95%以上への改善策を提示する

使用方法:
    python scripts/validation/analyze_tier_mismatch.py --start 2020-01-01 --end 2025-12-31

作成日: 2026-02-16
"""
import sqlite3
import sys
import os
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from config.bet_conditions import STANDARD_BET_CONDITIONS
from src.betting.evaluator_helpers import create_custom_evaluator
from src.betting.bet_target_evaluator import BetStatus


def get_tier2_bets_by_condition(cursor, cond: Dict, start_date: str, end_date: str) -> List[Tuple]:
    """Tier 2（SQL）で購入対象となるレースを条件別に取得

    Args:
        cursor: DBカーソル
        cond: 購入条件
        start_date: 開始日
        end_date: 終了日

    Returns:
        (race_id, venue_code, confidence, c1_rank, odds, combination) のリスト
    """
    from scripts.backtest.standard_backtest import build_condition_query

    # SQLクエリを構築（詳細情報を取得するように修正）
    c1_rank_str = "','".join(cond['c1_rank'])
    use_pattern_h = cond.get('use_pattern_h', True)

    # 信頼度フィルター
    confidence_clause = ""
    if cond.get('confidence') is not None:
        confidence_clause = f"AND rp.confidence = '{cond['confidence']}'"

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

    # モーターフィルター
    motor_clause = ""
    if cond.get('motor_min'):
        motor_clause = f"AND e1.motor_second_rate >= {cond['motor_min']}"

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

    # 月除外フィルター
    month_exclude_clause = ""
    if cond.get('month_exclude'):
        months = ','.join(map(str, cond['month_exclude']))
        month_exclude_clause = f"AND CAST(strftime('%m', r.race_date) AS INTEGER) NOT IN ({months})"

    # 予測コースフィルター
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
        # パターンH: 3点買い
        query = f'''
        WITH race_base AS (
            SELECT
                r.id as race_id,
                r.venue_code,
                rp.confidence,
                e1.racer_rank as c1_rank,
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
            {confidence_clause}
            AND e1.racer_rank IN ('{c1_rank_str}')
            AND r.race_date >= '{start_date}'
            AND r.race_date < '{end_date}'
            {venue_clause}
            {motor_clause}
            {predicted_course_clause}
            {c1_second_rate_clause}
            {month_exclude_clause}
            {escape_rate_clause}
            {bias_clause}
        ),
        race_with_odds AS (
            SELECT
                rb.*,
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                          AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)), 0) as odds_123,
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                          AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p4 AS TEXT)), 0) as odds_124,
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                          AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p5 AS TEXT)), 0) as odds_125
            FROM race_base rb
        )
        SELECT DISTINCT
            race_id,
            venue_code,
            confidence,
            c1_rank,
            CASE
                WHEN odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']} THEN odds_123
                WHEN odds_124 >= {cond['odds_min']} AND odds_124 < {cond['odds_max']} THEN odds_124
                WHEN odds_125 >= {cond['odds_min']} AND odds_125 < {cond['odds_max']} THEN odds_125
                ELSE 0
            END as odds,
            CASE
                WHEN odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']} THEN CAST(p1 AS TEXT) || '-' || CAST(p2 AS TEXT) || '-' || CAST(p3 AS TEXT)
                WHEN odds_124 >= {cond['odds_min']} AND odds_124 < {cond['odds_max']} THEN CAST(p1 AS TEXT) || '-' || CAST(p2 AS TEXT) || '-' || CAST(p4 AS TEXT)
                WHEN odds_125 >= {cond['odds_min']} AND odds_125 < {cond['odds_max']} THEN CAST(p1 AS TEXT) || '-' || CAST(p2 AS TEXT) || '-' || CAST(p5 AS TEXT)
                ELSE NULL
            END as combination
        FROM race_with_odds
        WHERE (odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']})
           OR (odds_124 >= {cond['odds_min']} AND odds_124 < {cond['odds_max']})
           OR (odds_125 >= {cond['odds_min']} AND odds_125 < {cond['odds_max']})
        '''
    else:
        # 1点買い
        query = f'''
        WITH race_base AS (
            SELECT
                r.id as race_id,
                r.venue_code,
                rp.confidence,
                e1.racer_rank as c1_rank,
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
            {confidence_clause}
            AND e1.racer_rank IN ('{c1_rank_str}')
            AND r.race_date >= '{start_date}'
            AND r.race_date < '{end_date}'
            {venue_clause}
            {motor_clause}
            {predicted_course_clause}
            {c1_second_rate_clause}
            {month_exclude_clause}
            {escape_rate_clause}
            {bias_clause}
        )
        SELECT
            rb.race_id,
            rb.venue_code,
            rb.confidence,
            rb.c1_rank,
            COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                      AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)), 0) as odds,
            CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT) as combination
        FROM race_base rb
        WHERE odds >= {cond['odds_min']} AND odds < {cond['odds_max']}
        '''

    cursor.execute(query)
    return cursor.fetchall()


def get_tier3_bets(cursor, race_ids: List[str]) -> Dict[str, Dict]:
    """Tier 3（Python）で購入対象となるレースを判定

    Args:
        cursor: DBカーソル
        race_ids: 評価対象のrace_idリスト

    Returns:
        {race_id: {'is_bet': True/False, 'reason': str, ...}}
    """
    from src.betting.evaluator_helpers import create_custom_evaluator

    evaluator = create_custom_evaluator(
        enable_venue_wind_filter=False,
        db_path=DATABASE_PATH
    )

    results = {}

    for race_id in race_ids:
        # レースデータを取得
        cursor.execute("""
            SELECT r.id, r.venue_code, r.race_number, r.race_date, r.race_time
            FROM races r WHERE r.id = ?
        """, (race_id,))
        race_row = cursor.fetchone()
        if not race_row:
            continue

        race_data = {
            'id': race_row[0],
            'venue_code': race_row[1],
            'race_number': race_row[2],
            'race_date': race_row[3],
            'race_time': race_row[4],
            'wind_speed': 0.0,
            'entries': []
        }

        # エントリー情報を取得
        cursor.execute("""
            SELECT pit_number, racer_number, racer_name, racer_rank, motor_second_rate, second_rate
            FROM entries WHERE race_id = ? ORDER BY pit_number
        """, (race_id,))
        race_data['entries'] = [
            {
                'pit_number': row[0],
                'racer_number': row[1],
                'racer_name': row[2],
                'racer_rank': row[3],
                'motor_second_rate': row[4],
                'second_rate': row[5],
            }
            for row in cursor.fetchall()
        ]

        # 予測データを取得
        cursor.execute("""
            SELECT pit_number, rank_prediction, confidence, racer_number
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'before'
            ORDER BY rank_prediction
        """, (race_id,))
        predictions_rows = cursor.fetchall()

        if len(predictions_rows) < 3:
            continue

        old_pred = [row[0] for row in predictions_rows]
        predictions = {
            'confidence': predictions_rows[0][2],
            'old_prediction': old_pred,
            'new_prediction': old_pred,
            'first_racer_number': predictions_rows[0][3],
        }

        # オッズデータを取得（パターンH対応：3点分）
        combinations = []
        if len(old_pred) >= 3:
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

        fetched_odds = {row[0]: row[1] for row in cursor.fetchall()}
        odds_data = {}
        for combo in combinations:
            odds_data[combo] = fetched_odds.get(combo, 0)

        # BetTargetEvaluatorで購入判定
        try:
            bet_target = evaluator.evaluate_race(
                race_data=race_data,
                predictions=predictions,
                odds_data=odds_data,
                has_beforeinfo=True
            )

            is_bet = bet_target.status in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]

            results[race_id] = {
                'is_bet': is_bet,
                'status': bet_target.status.value,
                'reason': bet_target.reason,
                'confidence': predictions['confidence'],
                'c1_rank': race_data['entries'][0].get('racer_rank') if race_data['entries'] else 'N/A',
                'venue_code': race_data['venue_code'],
                'odds': bet_target.odds,
                'combination': bet_target.combination,
            }

        except Exception as e:
            results[race_id] = {
                'is_bet': False,
                'error': str(e),
            }

    return results


def analyze_mismatch_patterns(tier2_bets: List[Tuple], tier3_results: Dict[str, Dict],
                              cond: Dict) -> Dict:
    """ミスマッチパターンを分析

    Args:
        tier2_bets: Tier 2の購入対象リスト
        tier3_results: Tier 3の判定結果
        cond: 購入条件

    Returns:
        分析結果
    """
    tier2_race_ids = {row[0] for row in tier2_bets}
    tier3_race_ids = {race_id for race_id, result in tier3_results.items() if result.get('is_bet')}

    matched = tier2_race_ids & tier3_race_ids
    tier2_only = tier2_race_ids - tier3_race_ids
    tier3_only = tier3_race_ids - tier2_race_ids

    # パターン分類
    mismatch_patterns = defaultdict(int)

    # Tier 2のみのパターン分析
    for race_id in list(tier2_only)[:50]:  # 最大50件
        tier3_result = tier3_results.get(race_id, {})
        reason = tier3_result.get('reason', '不明')

        # 理由からパターンを抽出
        if 'オッズ範囲外' in reason:
            mismatch_patterns['オッズ範囲外（Tier 3）'] += 1
        elif '条件不一致' in reason:
            mismatch_patterns['条件不一致（Tier 3）'] += 1
        elif 'error' in tier3_result:
            mismatch_patterns['評価エラー（Tier 3）'] += 1
        else:
            mismatch_patterns['その他（Tier 2のみ）'] += 1

    # Tier 3のみのパターン分析
    for race_id in list(tier3_only)[:50]:  # 最大50件
        # Tier 2で見逃している理由を推測（SQLの条件でフィルターされた）
        mismatch_patterns['Tier 2でフィルター除外'] += 1

    return {
        'condition_id': cond['id'],
        'condition_name': cond['name'],
        'tier2_count': len(tier2_race_ids),
        'tier3_count': len(tier3_race_ids),
        'matched_count': len(matched),
        'tier2_only_count': len(tier2_only),
        'tier3_only_count': len(tier3_only),
        'match_rate': 100.0 * len(matched) / len(tier2_race_ids) if tier2_race_ids else 0,
        'mismatch_patterns': dict(mismatch_patterns),
    }


def main():
    parser = argparse.ArgumentParser(
        description='Tier 2（SQL）とTier 3（Python）のミスマッチ詳細分析'
    )
    parser.add_argument('--start', type=str, default='2020-01-01', help='開始日（YYYY-MM-DD）')
    parser.add_argument('--end', type=str, default='2026-01-01', help='終了日（YYYY-MM-DD）')
    parser.add_argument('--condition-id', type=str, help='特定条件のみ分析（例: A_A1_10_12）')
    args = parser.parse_args()

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("=" * 90)
    print("Tier 2（SQL）とTier 3（Python）のミスマッチ詳細分析")
    print("=" * 90)
    print(f"検証期間: {args.start} ~ {args.end}")
    print()

    # 分析対象条件
    conditions = STANDARD_BET_CONDITIONS
    if args.condition_id:
        conditions = [c for c in conditions if c['id'] == args.condition_id]
        if not conditions:
            print(f"エラー: 条件ID '{args.condition_id}' が見つかりません")
            return

    all_results = []

    for cond in conditions:
        print(f"分析中: {cond['name']}...")

        # Tier 2の購入対象を取得
        tier2_bets = get_tier2_bets_by_condition(cursor, cond, args.start, args.end)
        tier2_race_ids = [row[0] for row in tier2_bets]

        if not tier2_race_ids:
            print(f"  Tier 2購入対象: 0件 → スキップ")
            continue

        # Tier 3の判定を取得
        tier3_results = get_tier3_bets(cursor, tier2_race_ids[:500])  # 最大500件に制限

        # ミスマッチ分析
        analysis = analyze_mismatch_patterns(tier2_bets[:500], tier3_results, cond)
        all_results.append(analysis)

        print(f"  Tier 2購入対象: {analysis['tier2_count']}件")
        print(f"  Tier 3購入対象: {analysis['tier3_count']}件")
        print(f"  一致率: {analysis['match_rate']:.2f}%")
        print()

    # 結果サマリー
    print()
    print("=" * 90)
    print("条件別ミスマッチサマリー")
    print("=" * 90)
    print(f"{'条件ID':<20} {'条件名':<30} {'Tier2':<8} {'Tier3':<8} {'一致率':<8} {'T2のみ':<8} {'T3のみ':<8}")
    print("-" * 90)

    for result in all_results:
        print(f"{result['condition_id']:<20} {result['condition_name']:<30} "
              f"{result['tier2_count']:<8} {result['tier3_count']:<8} "
              f"{result['match_rate']:<7.1f}% {result['tier2_only_count']:<8} {result['tier3_only_count']:<8}")

    print()

    conn.close()


if __name__ == '__main__':
    main()
