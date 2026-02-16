#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tier 2とTier 3の不一致原因を特定する分析スクリプト

目的:
    - Tier 2（SQLバックテスト）で購入対象となったレース
    - Tier 3（実コード）で除外されたレース
    上記の差分を詳細に分析し、除外理由を特定

使用方法:
    python scripts/analysis/analyze_tier2_tier3_gap.py
"""
import sqlite3
import sys
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from config.bet_conditions import STANDARD_BET_CONDITIONS
from src.betting.evaluator_helpers import create_custom_evaluator
from src.betting.bet_target_evaluator import BetStatus

# ============================================================
# Tier 2の購入対象レースを取得するSQLクエリ
# ============================================================
def build_tier2_race_query(cond: Dict, date_start: str, date_end: str) -> str:
    """Tier 2の購入対象レースを取得するクエリを構築（standard_backtest.pyと同じロジック）"""
    c1_rank_str = "','".join(cond['c1_rank'])
    use_pattern_h = cond.get('use_pattern_h', True)

    # 信頼度フィルター
    confidence_clause = ""
    if cond.get('confidence') is not None:
        confidence_clause = f"AND rp.confidence = '{cond['confidence']}'"

    # 各種フィルター条件（standard_backtest.pyと同じ）
    venue_clause = ""
    if cond.get('venue_filter'):
        venue_codes = []
        for v in cond['venue_filter']:
            if isinstance(v, int):
                venue_codes.append(f"'{v:02d}'")
            else:
                venue_codes.append(f"'{v}'")
        venue_clause = f"AND r.venue_code IN ({','.join(venue_codes)})"

    motor_clause = ""
    if cond.get('motor_min'):
        motor_clause = f"AND e1.motor_second_rate >= {cond['motor_min']}"

    race_exclude_clause = ""
    if cond.get('race_exclude'):
        race_exclude_clause = f"AND r.race_number NOT IN ({','.join(map(str, cond['race_exclude']))})"

    venue_exclude_clause = ""
    if cond.get('venue_exclude'):
        venue_codes = []
        for v in cond['venue_exclude']:
            if isinstance(v, int):
                venue_codes.append(f"'{v:02d}'")
            else:
                venue_codes.append(f"'{v}'")
        venue_exclude_clause = f"AND r.venue_code NOT IN ({','.join(venue_codes)})"

    predicted_course_clause = ""
    if cond.get('predicted_course'):
        predicted_course_clause = f"AND rp1.pit_number = {cond['predicted_course']}"

    c1_second_rate_clause = ""
    if cond.get('c1_second_rate_min') is not None:
        c1_second_rate_clause += f"AND e1.second_rate >= {cond['c1_second_rate_min']} "
    if cond.get('c1_second_rate_max') is not None:
        c1_second_rate_clause += f"AND e1.second_rate < {cond['c1_second_rate_max']} "

    month_exclude_clause = ""
    if cond.get('month_exclude'):
        months = ','.join(map(str, cond['month_exclude']))
        month_exclude_clause = f"AND CAST(strftime('%m', r.race_date) AS INTEGER) NOT IN ({months})"

    escape_rate_join = ""
    escape_rate_clause = ""
    if cond.get('escape_rate_min') is not None:
        escape_rate_join = """
        LEFT JOIN entries e_pred ON r.id = e_pred.race_id AND e_pred.pit_number = rp1.pit_number
        LEFT JOIN player_escape_stats pes ON e_pred.racer_number = pes.player_id AND pes.stadium_id IS NULL
        """
        escape_rate_clause = f"AND pes.escape_rate >= {cond['escape_rate_min']} "

    bias_join = ""
    bias_clause = ""
    if cond.get('bias_max') is not None:
        bias_join = """
        LEFT JOIN entries e_bias ON r.id = e_bias.race_id AND e_bias.pit_number = rp1.pit_number
        LEFT JOIN player_bias_stats pbs ON e_bias.racer_number = pbs.player_id AND pbs.stadium_id IS NULL
        """
        bias_clause = f"AND pbs.bias_index IS NOT NULL AND pbs.bias_index < {cond['bias_max']} "

    motor_rate_join = ""
    motor_rate_clause = ""
    if cond.get('p1_motor_second_rate_min') is not None:
        motor_rate_join = """
        LEFT JOIN entries e_motor ON r.id = e_motor.race_id AND e_motor.pit_number = rp1.pit_number
        """
        motor_rate_clause = f"AND e_motor.motor_second_rate >= {cond['p1_motor_second_rate_min']} "

    predicted_rank_class_clause = ""
    if cond.get('predicted_rank_has_class') and cond.get('predicted_rank_range'):
        class_list = "','".join(cond['predicted_rank_has_class'])
        rank_min, rank_max = cond['predicted_rank_range']
        predicted_rank_class_clause = f"""
        AND EXISTS (
            SELECT 1
            FROM race_predictions rp_class
            LEFT JOIN racers r_class ON rp_class.racer_number = r_class.racer_number
            WHERE rp_class.race_id = r.id
            AND rp_class.prediction_type = 'before'
            AND rp_class.rank_prediction BETWEEN {rank_min} AND {rank_max}
            AND r_class.rank IN ('{class_list}')
        )
        """

    # レースIDリストを取得するクエリ
    if use_pattern_h:
        # パターンH: 3点のいずれかがオッズ範囲内
        query = f'''
        WITH race_base AS (
            SELECT
                r.id as race_id,
                r.race_date,
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
            {motor_rate_join}
            WHERE rp.rank_prediction = 1
            {confidence_clause}
            AND e1.racer_rank IN ('{c1_rank_str}')
            AND r.race_date >= '{date_start}'
            AND r.race_date < '{date_end}'
            {venue_clause}
            {motor_clause}
            {race_exclude_clause}
            {venue_exclude_clause}
            {predicted_course_clause}
            {c1_second_rate_clause}
            {month_exclude_clause}
            {escape_rate_clause}
            {bias_clause}
            {motor_rate_clause}
            {predicted_rank_class_clause}
        ),
        race_with_odds AS (
            SELECT
                rb.race_id,
                rb.race_date,
                rb.venue_code,
                rb.confidence,
                rb.c1_rank,
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                          AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)), 0) as odds_123,
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                          AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p4 AS TEXT)), 0) as odds_124,
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                          AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p5 AS TEXT)), 0) as odds_125
            FROM race_base rb
        )
        SELECT race_id, race_date, venue_code, confidence, c1_rank, odds_123, odds_124, odds_125
        FROM race_with_odds
        WHERE (odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']})
           OR (odds_124 >= {cond['odds_min']} AND odds_124 < {cond['odds_max']})
           OR (odds_125 >= {cond['odds_min']} AND odds_125 < {cond['odds_max']})
        '''
    else:
        # 1点買い: 1-2-3のみがオッズ範囲内
        query = f'''
        WITH race_base AS (
            SELECT
                r.id as race_id,
                r.race_date,
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
            {motor_rate_join}
            WHERE rp.rank_prediction = 1
            {confidence_clause}
            AND e1.racer_rank IN ('{c1_rank_str}')
            AND r.race_date >= '{date_start}'
            AND r.race_date < '{date_end}'
            {venue_clause}
            {motor_clause}
            {race_exclude_clause}
            {venue_exclude_clause}
            {predicted_course_clause}
            {c1_second_rate_clause}
            {month_exclude_clause}
            {escape_rate_clause}
            {bias_clause}
            {motor_rate_clause}
            {predicted_rank_class_clause}
        ),
        race_with_odds AS (
            SELECT
                rb.race_id,
                rb.race_date,
                rb.venue_code,
                rb.confidence,
                rb.c1_rank,
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                          AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)), 0) as odds_123
            FROM race_base rb
        )
        SELECT race_id, race_date, venue_code, confidence, c1_rank, odds_123
        FROM race_with_odds
        WHERE odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']}
        '''
    return query


def get_race_data_for_tier3(cursor, race_id: str) -> Optional[Dict]:
    """Tier 3用のレースデータを取得"""
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
    wind_speed = conditions_row[0] if conditions_row and conditions_row[0] else 0.0

    # エントリー情報
    cursor.execute("""
        SELECT pit_number, racer_number, racer_name, racer_rank, motor_second_rate, second_rate
        FROM entries WHERE race_id = ? ORDER BY pit_number
    """, (race_id,))
    entries = [dict(zip(['pit_number', 'racer_number', 'racer_name', 'racer_rank', 'motor_second_rate', 'second_rate'], row)) for row in cursor.fetchall()]

    return {
        'id': row[0],
        'venue_code': row[1],
        'race_number': row[2],
        'race_date': row[3],
        'race_time': row[4],
        'wind_speed': wind_speed,
        'entries': entries
    }


def get_predictions_for_tier3(cursor, race_id: str) -> Optional[Dict]:
    """Tier 3用の予測データを取得"""
    cursor.execute("""
        SELECT pit_number, rank_prediction, confidence, racer_number
        FROM race_predictions
        WHERE race_id = ? AND prediction_type = 'before'
        ORDER BY rank_prediction
    """, (race_id,))

    predictions = [dict(zip(['pit_number', 'rank_prediction', 'confidence', 'racer_number'], row)) for row in cursor.fetchall()]
    if len(predictions) < 3:
        return None

    old_pred = [p['pit_number'] for p in predictions[:6]]  # 6位まで取得
    return {
        'confidence': predictions[0]['confidence'],
        'old_prediction': old_pred,
        'new_prediction': old_pred,
        'full_prediction': old_pred,
        'first_racer_number': predictions[0]['racer_number']
    }


def get_odds_data_for_tier3(cursor, race_id: str, predictions: Dict) -> Dict:
    """Tier 3用のオッズデータを取得（パターンH対応：3点分）"""
    old_pred = predictions['old_prediction']

    # パターンH用の3点（1-2-3, 1-2-4, 1-2-5）を取得
    combinations = []
    if len(old_pred) >= 3:
        combinations.append(f"{old_pred[0]}-{old_pred[1]}-{old_pred[2]}")  # 1-2-3
    if len(old_pred) >= 4:
        combinations.append(f"{old_pred[0]}-{old_pred[1]}-{old_pred[3]}")  # 1-2-4
    if len(old_pred) >= 5:
        combinations.append(f"{old_pred[0]}-{old_pred[1]}-{old_pred[4]}")  # 1-2-5

    if not combinations:
        return {}

    # 3点分のオッズを一度に取得
    placeholders = ','.join(['?' for _ in combinations])
    cursor.execute(f"""
        SELECT combination, odds
        FROM trifecta_odds
        WHERE race_id = ? AND combination IN ({placeholders})
    """, (race_id, *combinations))

    # 辞書形式で返す
    return {row[0]: row[1] for row in cursor.fetchall()}


def classify_exclusion_reason(cond: Dict, race_data: Dict, predictions: Dict, odds_data: Dict, bet_target) -> str:
    """
    除外理由を詳細に分類

    Tier 2では購入対象だがTier 3で除外された理由を特定
    """
    # 1コース選手の級別を取得
    entries = race_data.get('entries', [])
    c1_entry = next((e for e in entries if e.get('pit_number') == 1), None)
    c1_rank = c1_entry.get('racer_rank', 'B1') if c1_entry else 'B1'

    # 条件の級別と比較
    if c1_rank not in cond['c1_rank']:
        return f"1コース級別不一致（条件:{cond['c1_rank']}, 実際:{c1_rank}）"

    # オッズを取得
    old_pred = predictions['old_prediction']
    old_combo = f"{old_pred[0]}-{old_pred[1]}-{old_pred[2]}"
    odds = odds_data.get(old_combo, 0)

    # オッズ範囲チェック
    if odds < cond['odds_min']:
        return f"オッズ不足（{odds:.1f}倍 < {cond['odds_min']}倍）"
    if odds >= cond['odds_max']:
        return f"オッズ超過（{odds:.1f}倍 >= {cond['odds_max']}倍）"

    # 会場フィルター
    venue_code = race_data.get('venue_code')
    if venue_code and isinstance(venue_code, str):
        venue_code = int(venue_code)

    if cond.get('venue_filter'):
        if venue_code not in cond['venue_filter']:
            return f"会場フィルター不一致（会場:{venue_code}, 条件:{cond['venue_filter']}）"

    if cond.get('venue_exclude'):
        if venue_code in cond['venue_exclude']:
            return f"会場除外（会場:{venue_code}）"

    # 月除外フィルター
    race_date = race_data.get('race_date')
    if race_date and cond.get('month_exclude'):
        race_month = int(race_date.split('-')[1])
        if race_month in cond['month_exclude']:
            return f"月除外（{race_month}月）"

    # モーター連帯率
    motor_second_rate = c1_entry.get('motor_second_rate') if c1_entry else None
    if cond.get('motor_min'):
        if motor_second_rate is None:
            return f"モーター連帯率データなし"
        if motor_second_rate < cond['motor_min']:
            return f"モーター連帯率不足（{motor_second_rate:.1f}% < {cond['motor_min']}%）"

    # 1コース選手の全国2連率
    c1_second_rate = c1_entry.get('second_rate') if c1_entry else None
    if cond.get('c1_second_rate_min'):
        if c1_second_rate is None:
            return f"1コース2連率データなし"
        if c1_second_rate < cond['c1_second_rate_min']:
            return f"1コース2連率不足（{c1_second_rate:.1f}% < {cond['c1_second_rate_min']}%）"
    if cond.get('c1_second_rate_max'):
        if c1_second_rate is None:
            return f"1コース2連率データなし"
        if c1_second_rate >= cond['c1_second_rate_max']:
            return f"1コース2連率超過（{c1_second_rate:.1f}% >= {cond['c1_second_rate_max']}%）"

    # 予測コース
    if cond.get('predicted_course'):
        if old_pred[0] != cond['predicted_course']:
            return f"予測コース不一致（予測:{old_pred[0]}, 条件:{cond['predicted_course']}）"

    # レース番号除外
    race_number = race_data.get('race_number')
    if cond.get('race_exclude'):
        if race_number in cond['race_exclude']:
            return f"レース番号除外（{race_number}R）"

    # 逃げ率フィルター（データ不足の可能性）
    if cond.get('escape_rate_min'):
        return f"逃げ率データ不足またはフィルター不一致（閾値:{cond['escape_rate_min']}）"

    # バイアス指数フィルター（データ不足の可能性）
    if cond.get('bias_max'):
        return f"バイアス指数データ不足またはフィルター不一致（閾値:{cond['bias_max']}）"

    # 予測順位の級別フィルター（B2条件）
    if cond.get('predicted_rank_has_class') and cond.get('predicted_rank_range'):
        return f"予測順位級別フィルター不一致（B2条件）"

    # パターンH適用の違い
    if cond.get('use_pattern_h', True):
        # パターンHの場合、3点のいずれかがオッズ範囲内であればTier 2では購入対象
        # Tier 3でも同じはずだが、multi_bet_generatorの生成失敗の可能性
        combo_123 = f"{old_pred[0]}-{old_pred[1]}-{old_pred[2]}"
        combo_124 = f"{old_pred[0]}-{old_pred[1]}-{old_pred[3]}" if len(old_pred) >= 4 else None
        combo_125 = f"{old_pred[0]}-{old_pred[1]}-{old_pred[4]}" if len(old_pred) >= 5 else None

        odds_123 = odds_data.get(combo_123, 0)
        odds_124 = odds_data.get(combo_124, 0) if combo_124 else 0
        odds_125 = odds_data.get(combo_125, 0) if combo_125 else 0

        in_range_123 = cond['odds_min'] <= odds_123 < cond['odds_max']
        in_range_124 = cond['odds_min'] <= odds_124 < cond['odds_max']
        in_range_125 = cond['odds_min'] <= odds_125 < cond['odds_max']

        if not (in_range_123 or in_range_124 or in_range_125):
            return f"パターンH全オッズ範囲外（1-2-3:{odds_123:.1f}, 1-2-4:{odds_124:.1f}, 1-2-5:{odds_125:.1f}）"

    # その他（bet_targetの理由を参照）
    return f"その他: {bet_target.reason}"


def analyze_tier2_tier3_gap():
    """Tier 2とTier 3の不一致原因を分析"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # Tier 3用のevaluatorを作成（風速フィルター無効化）
    from src.betting.evaluator_helpers import create_custom_evaluator
    evaluator = create_custom_evaluator(
        enable_venue_wind_filter=False,
        db_path=DATABASE_PATH
    )

    print("=" * 90)
    print("Tier 2とTier 3の不一致原因分析")
    print("=" * 90)
    print()

    # 期間設定
    start_date = '2020-01-01'
    end_date = '2026-01-01'

    # 不一致原因の集計
    exclusion_reasons = {}
    condition_mismatch = {}
    tier2_only_races = []

    # 各条件ごとにTier 2の購入対象レースを取得し、Tier 3で判定
    for cond in STANDARD_BET_CONDITIONS:
        print(f"条件分析中: {cond['name']} ...", end=' ')

        # Tier 2の購入対象レースを取得
        query = build_tier2_race_query(cond, start_date, end_date)
        cursor.execute(query)
        tier2_races = cursor.fetchall()

        print(f"Tier 2購入件数: {len(tier2_races)}")

        tier2_excluded_count = 0

        for race_row in tier2_races:
            race_id = race_row[0]

            # Tier 3で判定
            race_data = get_race_data_for_tier3(cursor, race_id)
            if not race_data:
                continue

            predictions = get_predictions_for_tier3(cursor, race_id)
            if not predictions:
                continue

            odds_data = get_odds_data_for_tier3(cursor, race_id, predictions)
            if not odds_data:
                tier2_excluded_count += 1
                reason = "オッズデータなし"
                exclusion_reasons[reason] = exclusion_reasons.get(reason, 0) + 1
                tier2_only_races.append({
                    'race_id': race_id,
                    'condition': cond['name'],
                    'reason': reason,
                    'race_data': race_data,
                })
                continue

            # BetTargetEvaluatorで購入判定
            try:
                bet_target = evaluator.evaluate_race(
                    race_data=race_data,
                    predictions=predictions,
                    odds_data=odds_data,
                    has_beforeinfo=True
                )

                # TARGET_ADVANCEまたはTARGET_CONFIRMEDでなければ除外
                if bet_target.status not in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
                    tier2_excluded_count += 1

                    # より詳細な除外理由を特定
                    detailed_reason = classify_exclusion_reason(cond, race_data, predictions, odds_data, bet_target)

                    reason = detailed_reason
                    exclusion_reasons[reason] = exclusion_reasons.get(reason, 0) + 1
                    condition_mismatch[cond['name']] = condition_mismatch.get(cond['name'], 0) + 1

                    tier2_only_races.append({
                        'race_id': race_id,
                        'condition': cond['name'],
                        'reason': reason,
                        'race_data': race_data,
                        'predictions': predictions,
                        'odds_data': odds_data,
                        'bet_target': bet_target,
                    })
            except Exception as e:
                tier2_excluded_count += 1
                reason = f"エラー: {str(e)}"
                exclusion_reasons[reason] = exclusion_reasons.get(reason, 0) + 1
                tier2_only_races.append({
                    'race_id': race_id,
                    'condition': cond['name'],
                    'reason': reason,
                    'race_data': race_data,
                })

        if tier2_excluded_count > 0:
            print(f"  → Tier 3で除外: {tier2_excluded_count}件")

    conn.close()

    # 結果サマリー
    print()
    print("=" * 90)
    print("不一致原因のサマリー（上位20件）")
    print("=" * 90)
    sorted_reasons = sorted(exclusion_reasons.items(), key=lambda x: x[1], reverse=True)
    total_mismatch = sum(count for _, count in sorted_reasons)
    for i, (reason, count) in enumerate(sorted_reasons[:20], 1):
        pct = 100.0 * count / total_mismatch if total_mismatch > 0 else 0
        print(f"{i:2d}. {reason:<70} {count:>6}件 ({pct:5.1f}%)")

    print()
    print("=" * 90)
    print("条件別の不一致件数（全条件）")
    print("=" * 90)
    sorted_conditions = sorted(condition_mismatch.items(), key=lambda x: x[1], reverse=True)
    for i, (condition, count) in enumerate(sorted_conditions, 1):
        print(f"{i:2d}. {condition:<60} {count:>6}件")

    # カテゴリ別集計
    print()
    print("=" * 90)
    print("不一致原因のカテゴリ別集計")
    print("=" * 90)
    category_stats = {}
    for reason, count in exclusion_reasons.items():
        if "逃げ率" in reason:
            category = "逃げ率データ不足"
        elif "バイアス指数" in reason:
            category = "バイアス指数データ不足"
        elif "オッズ不足（0.0倍" in reason:
            category = "オッズデータなし"
        elif "オッズ不足" in reason:
            category = "オッズ範囲外（下限未満）"
        elif "オッズ超過" in reason:
            category = "オッズ範囲外（上限以上）"
        elif "パターンH全オッズ範囲外" in reason:
            category = "パターンH全オッズ範囲外"
        elif "会場フィルター" in reason:
            category = "会場フィルター不一致"
        elif "月除外" in reason:
            category = "月除外フィルター不一致"
        elif "モーター" in reason:
            category = "モーター条件不一致"
        elif "1コース2連率" in reason:
            category = "1コース2連率不一致"
        elif "予測コース" in reason:
            category = "予測コース不一致"
        elif "級別" in reason:
            category = "級別不一致"
        else:
            category = "その他"

        category_stats[category] = category_stats.get(category, 0) + count

    sorted_categories = sorted(category_stats.items(), key=lambda x: x[1], reverse=True)
    for i, (category, count) in enumerate(sorted_categories, 1):
        pct = 100.0 * count / total_mismatch if total_mismatch > 0 else 0
        print(f"{i:2d}. {category:<40} {count:>6}件 ({pct:5.1f}%)")

    print()
    print(f"総不一致件数: {total_mismatch}件")

    # サンプルレースの詳細出力（最初の10件）
    print()
    print("=" * 90)
    print("不一致サンプルレース（最初の10件）")
    print("=" * 90)
    for i, race_info in enumerate(tier2_only_races[:10], 1):
        print(f"\n[{i}] レースID: {race_info['race_id']}")
        print(f"    条件: {race_info['condition']}")
        print(f"    除外理由: {race_info['reason']}")
        if 'race_data' in race_info:
            rd = race_info['race_data']
            print(f"    会場: {rd['venue_code']}, 日付: {rd['race_date']}, レース: {rd['race_number']}R")
        if 'predictions' in race_info:
            pred = race_info['predictions']
            print(f"    予測: {pred['old_prediction'][:3]}, 信頼度: {pred['confidence']}")
        if 'odds_data' in race_info:
            print(f"    オッズ: {race_info['odds_data']}")


if __name__ == '__main__':
    analyze_tier2_tier3_gap()
