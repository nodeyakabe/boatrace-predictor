#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ユニーク版標準バックテスト（実運用シミュレーション用）

目的:
    重複レースを除外し、Tier 3の実運用ロジックと同じ動作でバックテストを実行

使用方法:
    # 6年間全体テスト（ユニーク版）
    python scripts/backtest/standard_backtest_unique.py --full

    # 2024年テスト（ユニーク版）
    python scripts/backtest/standard_backtest_unique.py --year 2024

    # JSON保存（Tier 3との比較用）
    python scripts/backtest/standard_backtest_unique.py --full --save-json data/tier2_unique_results.json

出力:
    - 全体サマリー（ユニークレース数、ROI、収支）
    - 条件別パフォーマンス（重複除外版）
    - 年度別パフォーマンス
"""
import sqlite3
import sys
import os
import json
import argparse
from datetime import datetime
from typing import Dict, List

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from config.bet_conditions import STANDARD_BET_CONDITIONS, get_active_conditions
from scripts.backtest.backtest_helpers import get_race_ids_for_condition

VENUE_NAMES = {
    '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島', '05': '多摩川',
    '06': '浜名湖', '07': '蒲郡', '08': '常滑', '09': '津', '10': '三国',
    '11': 'びわこ', '12': '住之江', '13': '尼崎', '14': '鳴門', '15': '丸亀',
    '16': '児島', '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
    '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村',
}

def assign_races_to_conditions(
    cursor: sqlite3.Cursor,
    conditions: List[Dict],
    start_date: str,
    end_date: str,
    enable_wind_filter: bool = True
) -> Dict[str, List[int]]:
    """
    全レースを優先度順に条件に割り当て

    Args:
        cursor: DBカーソル
        conditions: 条件リスト（STANDARD_BET_CONDITIONS）
        start_date: 開始日（'YYYY-MM-DD'形式）
        end_date: 終了日（'YYYY-MM-DD'形式）

    Returns:
        {condition_id: [race_id, ...]}
    """
    all_race_ids = set()
    race_to_condition = {}  # {race_id: condition_id}

    # 優先度順にソート（priorityが同じ場合はリスト順）
    sorted_conditions = sorted(
        conditions,
        key=lambda x: (x.get('priority', 999), conditions.index(x))
    )

    print("\n[Duplicate Race Assignment]")
    print("-" * 80)
    print(f"{'Condition ID':<20} {'Priority':<8} {'Candidates':<10} {'Assigned':<10} {'Duplicates':<10}")
    print("-" * 80)

    for cond in sorted_conditions:
        race_ids = get_race_ids_for_condition(cursor, cond, start_date, end_date, enable_wind_filter=enable_wind_filter)
        new_assignments = 0
        duplicate_count = 0

        for race_id in race_ids:
            if race_id not in all_race_ids:
                all_race_ids.add(race_id)
                race_to_condition[race_id] = cond['id']
                new_assignments += 1
            else:
                duplicate_count += 1

        print(f"{cond['id']:<20} {cond.get('priority', 1):<8} {len(race_ids):<10} {new_assignments:<10} {duplicate_count:<10}")

    print("-" * 80)
    total_candidates = sum(len(get_race_ids_for_condition(cursor, c, start_date, end_date, enable_wind_filter=enable_wind_filter)) for c in conditions)
    print(f"Total candidates (with duplicates): {total_candidates:,}")
    print(f"Unique races: {len(all_race_ids):,}")
    print(f"Duplicates excluded: {total_candidates - len(all_race_ids):,}")
    print()

    # 条件別にレースIDをまとめる
    condition_to_races = {}
    for race_id, cond_id in race_to_condition.items():
        if cond_id not in condition_to_races:
            condition_to_races[cond_id] = []
        condition_to_races[cond_id].append(race_id)

    return condition_to_races

def analyze_assigned_races(
    cursor: sqlite3.Cursor,
    cond: Dict,
    race_ids: List[int]
) -> Dict:
    """
    指定されたレースIDのみで条件の成績を計算

    Args:
        cursor: DBカーソル
        cond: 条件定義
        race_ids: レースIDのリスト

    Returns:
        {bets, hits, hit_rate, investment, payout, roi, profit}
    """
    if not race_ids:
        return {
            'name': cond['name'],
            'bets': 0, 'hits': 0, 'hit_rate': 0,
            'investment': 0, 'payout': 0, 'roi': 0, 'profit': 0,
        }

    # パターンHか1点買いかで投資額・払戻を計算
    use_pattern_h = cond.get('use_pattern_h', False)
    pattern_h_require_p123 = cond.get('pattern_h_require_p123', False)
    use_pattern_p142 = cond.get('use_pattern_p142', False)
    use_pattern_p143 = cond.get('use_pattern_p143', False)
    use_pattern_p132 = cond.get('use_pattern_p132', False)
    use_pattern_p124 = cond.get('use_pattern_p124', False)
    use_market_diverge = cond.get('use_market_diverge', False)
    # 市場乖離条件: 予測買い目 != 市場本命（最小オッズ組み合わせ）
    if use_market_diverge:
        md_extra = """
        AND CAST(p1 AS TEXT)||'-'||CAST(p2 AS TEXT)||'-'||CAST(p3 AS TEXT) !=
            COALESCE((SELECT combination FROM trifecta_odds t WHERE t.race_id = race_bets.race_id AND t.odds > 0 ORDER BY t.odds ASC LIMIT 1), '')"""
    else:
        md_extra = ""
    placeholders = ','.join(['?'] * len(race_ids))

    if use_pattern_p143:
        # p1-p4-p3 パターン: 予測1位-予測4位-予測3位の三連単 100円（2026-04-17追加）
        query = f"""
        WITH race_bets AS (
            SELECT
                r.id as race_id,
                rp1.pit_number as p1,
                rp3.pit_number as p3,
                rp4.pit_number as p4,
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
                 AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp4.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)), 0) as odds_143,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') as actual_1st,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') as actual_2nd,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') as actual_3rd
            FROM races r
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
            WHERE r.id IN ({placeholders})
        ),
        race_payouts AS (
            SELECT
                *,
                CASE WHEN odds_143 >= {cond['odds_min']} AND odds_143 < {cond['odds_max']} THEN 100 ELSE 0 END as bet_amount,
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p4 AND actual_3rd = p3
                         AND odds_143 >= {cond['odds_min']} AND odds_143 < {cond['odds_max']}
                    THEN odds_143 * 100 ELSE 0
                END as payout,
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p4 AND actual_3rd = p3
                         AND odds_143 >= {cond['odds_min']} AND odds_143 < {cond['odds_max']}
                    THEN 1 ELSE 0
                END as is_hit
            FROM race_bets
        )
        SELECT
            SUM(CASE WHEN bet_amount > 0 THEN 1 ELSE 0 END) as bets,
            SUM(is_hit) as hits,
            SUM(bet_amount) as investment,
            SUM(payout) as payout
        FROM race_payouts
        WHERE bet_amount > 0
        """
    elif use_pattern_p132:
        # p1-p3-p2 パターン: 予測1位-予測3位-予測2位の三連単 100円（2026-04-17追加）
        query = f"""
        WITH race_bets AS (
            SELECT
                r.id as race_id,
                rp1.pit_number as p1,
                rp2.pit_number as p2,
                rp3.pit_number as p3,
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
                 AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT)), 0) as odds_132,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') as actual_1st,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') as actual_2nd,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') as actual_3rd
            FROM races r
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            WHERE r.id IN ({placeholders})
        ),
        race_payouts AS (
            SELECT
                *,
                CASE WHEN odds_132 >= {cond['odds_min']} AND odds_132 < {cond['odds_max']} THEN 100 ELSE 0 END as bet_amount,
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p3 AND actual_3rd = p2
                         AND odds_132 >= {cond['odds_min']} AND odds_132 < {cond['odds_max']}
                    THEN odds_132 * 100 ELSE 0
                END as payout,
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p3 AND actual_3rd = p2
                         AND odds_132 >= {cond['odds_min']} AND odds_132 < {cond['odds_max']}
                    THEN 1 ELSE 0
                END as is_hit
            FROM race_bets
        )
        SELECT
            SUM(CASE WHEN bet_amount > 0 THEN 1 ELSE 0 END) as bets,
            SUM(is_hit) as hits,
            SUM(bet_amount) as investment,
            SUM(payout) as payout
        FROM race_payouts
        WHERE bet_amount > 0
        """
    elif use_pattern_p142:
        # p1-p4-p2 パターン: 予測1位-予測4位-予測2位の三連単 100円（2026-04-17追加）
        query = f"""
        WITH race_bets AS (
            SELECT
                r.id as race_id,
                rp1.pit_number as p1,
                rp2.pit_number as p2,
                rp4.pit_number as p4,
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
                 AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp4.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT)), 0) as odds_142,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') as actual_1st,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') as actual_2nd,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') as actual_3rd
            FROM races r
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
            WHERE r.id IN ({placeholders})
        ),
        race_payouts AS (
            SELECT
                *,
                CASE WHEN odds_142 >= {cond['odds_min']} AND odds_142 < {cond['odds_max']} THEN 100 ELSE 0 END as bet_amount,
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p4 AND actual_3rd = p2
                         AND odds_142 >= {cond['odds_min']} AND odds_142 < {cond['odds_max']}
                    THEN odds_142 * 100 ELSE 0
                END as payout,
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p4 AND actual_3rd = p2
                         AND odds_142 >= {cond['odds_min']} AND odds_142 < {cond['odds_max']}
                    THEN 1 ELSE 0
                END as is_hit
            FROM race_bets
        )
        SELECT
            SUM(CASE WHEN bet_amount > 0 THEN 1 ELSE 0 END) as bets,
            SUM(is_hit) as hits,
            SUM(bet_amount) as investment,
            SUM(payout) as payout
        FROM race_payouts
        WHERE bet_amount > 0
        """
    elif use_pattern_p124:
        # p1-p2-p4 パターン: 予測1位-予測2位-予測4位の三連単 100円（2026-04-20追加）
        query = f"""
        WITH race_bets AS (
            SELECT
                r.id as race_id,
                rp1.pit_number as p1,
                rp2.pit_number as p2,
                rp4.pit_number as p4,
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
                 AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp4.pit_number AS TEXT)), 0) as odds_124,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') as actual_1st,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') as actual_2nd,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') as actual_3rd
            FROM races r
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
            WHERE r.id IN ({placeholders})
        ),
        race_payouts AS (
            SELECT
                *,
                CASE WHEN odds_124 >= {cond['odds_min']} AND odds_124 < {cond['odds_max']} THEN 100 ELSE 0 END as bet_amount,
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4
                         AND odds_124 >= {cond['odds_min']} AND odds_124 < {cond['odds_max']}
                    THEN odds_124 * 100 ELSE 0
                END as payout,
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4
                         AND odds_124 >= {cond['odds_min']} AND odds_124 < {cond['odds_max']}
                    THEN 1 ELSE 0
                END as is_hit
            FROM race_bets
        )
        SELECT
            SUM(CASE WHEN bet_amount > 0 THEN 1 ELSE 0 END) as bets,
            SUM(is_hit) as hits,
            SUM(bet_amount) as investment,
            SUM(payout) as payout
        FROM race_payouts
        WHERE bet_amount > 0
        """
    elif use_pattern_h:
        # パターンH: 3点買い（200円/100円/100円）
        query = f"""
        WITH race_bets AS (
            SELECT
                r.id as race_id,
                rp1.pit_number as p1,
                rp2.pit_number as p2,
                rp3.pit_number as p3,
                rp4.pit_number as p4,
                rp5.pit_number as p5,
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
                 AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)), 0) as odds_123,
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
                 AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp4.pit_number AS TEXT)), 0) as odds_124,
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
                 AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp5.pit_number AS TEXT)), 0) as odds_125,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') as actual_1st,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') as actual_2nd,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') as actual_3rd
            FROM races r
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
            JOIN race_predictions rp5 ON r.id = rp5.race_id AND rp5.prediction_type = 'before' AND rp5.rank_prediction = 5
            WHERE r.id IN ({placeholders})
        ),
        race_payouts AS (
            SELECT
                *,
                CASE WHEN odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']} THEN 200 ELSE 0 END as bet_123,
                CASE WHEN odds_124 >= {cond['odds_min']} AND odds_124 < {cond['odds_max']} THEN 100 ELSE 0 END as bet_124,
                {'0' if cond.get('pattern_h_exclude_p5') else f"CASE WHEN odds_125 >= {cond['odds_min']} AND odds_125 < {cond['odds_max']} THEN 100 ELSE 0 END"} as bet_125,
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3
                         AND odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']}
                    THEN odds_123 * 200 ELSE 0
                END as payout_123,
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4
                         AND odds_124 >= {cond['odds_min']} AND odds_124 < {cond['odds_max']}
                    THEN odds_124 * 100 ELSE 0
                END as payout_124,
                {'0' if cond.get('pattern_h_exclude_p5') else f"""CASE
                    WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p5
                         AND odds_125 >= {cond['odds_min']} AND odds_125 < {cond['odds_max']}
                    THEN odds_125 * 100 ELSE 0
                END"""} as payout_125,
                CASE
                    WHEN (actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3 AND odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']})
                      OR (actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4 AND odds_124 >= {cond['odds_min']} AND odds_124 < {cond['odds_max']})
                      {''.join(['', f'OR (actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p5 AND odds_125 >= {cond["odds_min"]} AND odds_125 < {cond["odds_max"]})']) if not cond.get('pattern_h_exclude_p5') else ''}
                    THEN 1 ELSE 0
                END as is_hit
            FROM race_bets
        )
        SELECT
            SUM(CASE WHEN {'bet_123 > 0' if pattern_h_require_p123 else 'bet_123 > 0 OR bet_124 > 0 OR bet_125 > 0'} THEN 1 ELSE 0 END) as bets,
            SUM(is_hit) as hits,
            SUM(bet_123 + bet_124 + bet_125) as investment,
            SUM(payout_123 + payout_124 + payout_125) as payout
        FROM race_payouts
        WHERE {'bet_123 > 0' if pattern_h_require_p123 else 'bet_123 > 0 OR bet_124 > 0 OR bet_125 > 0'}
        """
    else:
        # 1点買い: 100円
        query = f"""
        WITH race_bets AS (
            SELECT
                r.id as race_id,
                rp1.pit_number as p1,
                rp2.pit_number as p2,
                rp3.pit_number as p3,
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
                 AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)), 0) as odds_123,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') as actual_1st,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') as actual_2nd,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') as actual_3rd
            FROM races r
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            WHERE r.id IN ({placeholders})
        ),
        race_payouts AS (
            SELECT
                *,
                CASE WHEN odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']}{md_extra}
                     THEN 100 ELSE 0 END as bet_amount,
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3
                         AND odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']}{md_extra}
                    THEN odds_123 * 100 ELSE 0
                END as payout,
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3
                         AND odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']}{md_extra}
                    THEN 1 ELSE 0
                END as is_hit
            FROM race_bets
        )
        SELECT
            SUM(CASE WHEN bet_amount > 0 THEN 1 ELSE 0 END) as bets,
            SUM(is_hit) as hits,
            SUM(bet_amount) as investment,
            SUM(payout) as payout
        FROM race_payouts
        WHERE bet_amount > 0
        """

    # SQLite variable limit対策: 大量race_idsをバッチ処理（上限約900）
    BATCH_SIZE = 900
    race_ids_list = list(race_ids)
    total_bets_sum = 0
    total_hits_sum = 0
    total_investment_sum = 0
    total_payout_sum = 0

    for batch_start in range(0, len(race_ids_list), BATCH_SIZE):
        batch = race_ids_list[batch_start:batch_start + BATCH_SIZE]
        batch_placeholders = ','.join(['?'] * len(batch))
        # クエリ内のplaceholdersを実際のバッチサイズに置換
        batch_query = query.replace(f'({placeholders})', f'({batch_placeholders})')
        cursor.execute(batch_query, batch)
        row = cursor.fetchone()
        if row and row[0]:
            total_bets_sum += row[0] or 0
            total_hits_sum += row[1] or 0
            total_investment_sum += row[2] or 0
            total_payout_sum += row[3] or 0

    if total_bets_sum > 0:
        bets, hits, investment, payout = total_bets_sum, total_hits_sum, total_investment_sum, total_payout_sum
        hits = hits or 0
        payout = payout or 0
        roi = 100.0 * payout / investment if investment > 0 else 0
        profit = payout - investment
        hit_rate = 100.0 * hits / bets if bets > 0 else 0
        return {
            'name': cond['name'],
            'bets': bets,
            'hits': hits,
            'hit_rate': hit_rate,
            'investment': investment,
            'payout': payout,
            'roi': roi,
            'profit': profit,
        }

    return {
        'name': cond['name'],
        'bets': 0, 'hits': 0, 'hit_rate': 0,
        'investment': 0, 'payout': 0, 'roi': 0, 'profit': 0,
    }

def get_hit_details(
    cursor: sqlite3.Cursor,
    cond: Dict,
    race_ids: List[int]
) -> List[Dict]:
    """的中レースの詳細情報を返す（analyze_assigned_racesと同じSQLを使用）"""
    if not race_ids:
        return []

    use_pattern_p143 = cond.get('use_pattern_p143', False)
    use_pattern_p132 = cond.get('use_pattern_p132', False)
    use_pattern_p142 = cond.get('use_pattern_p142', False)
    use_pattern_p124 = cond.get('use_pattern_p124', False)
    use_pattern_h = cond.get('use_pattern_h', False)
    odds_min = cond.get('odds_min', 0)
    odds_max = cond.get('odds_max', 9999)
    placeholders = ','.join(['?'] * len(race_ids))

    if use_pattern_p143:
        query = f"""
        WITH race_bets AS (
            SELECT r.id as race_id, r.race_date, r.venue_code, r.race_number,
                   rp1.pit_number as p1, rp3.pit_number as p3, rp4.pit_number as p4,
                   COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
                    AND o.combination = CAST(rp1.pit_number AS TEXT)||'-'||CAST(rp4.pit_number AS TEXT)||'-'||CAST(rp3.pit_number AS TEXT)), 0) as odds_val,
                   (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') as actual_1st,
                   (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') as actual_2nd,
                   (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') as actual_3rd
            FROM races r
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
            WHERE r.id IN ({placeholders})
        )
        SELECT race_date, venue_code, race_number,
               CAST(p1 AS TEXT)||'-'||CAST(p4 AS TEXT)||'-'||CAST(p3 AS TEXT) as buy,
               CAST(actual_1st AS TEXT)||'-'||CAST(actual_2nd AS TEXT)||'-'||CAST(actual_3rd AS TEXT) as actual,
               odds_val
        FROM race_bets
        WHERE actual_1st = p1 AND actual_2nd = p4 AND actual_3rd = p3
          AND odds_val >= {odds_min} AND odds_val < {odds_max}
        ORDER BY race_date"""
    elif use_pattern_p132:
        query = f"""
        WITH race_bets AS (
            SELECT r.id as race_id, r.race_date, r.venue_code, r.race_number,
                   rp1.pit_number as p1, rp2.pit_number as p2, rp3.pit_number as p3,
                   COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
                    AND o.combination = CAST(rp1.pit_number AS TEXT)||'-'||CAST(rp3.pit_number AS TEXT)||'-'||CAST(rp2.pit_number AS TEXT)), 0) as odds_val,
                   (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') as actual_1st,
                   (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') as actual_2nd,
                   (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') as actual_3rd
            FROM races r
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            WHERE r.id IN ({placeholders})
        )
        SELECT race_date, venue_code, race_number,
               CAST(p1 AS TEXT)||'-'||CAST(p3 AS TEXT)||'-'||CAST(p2 AS TEXT) as buy,
               CAST(actual_1st AS TEXT)||'-'||CAST(actual_2nd AS TEXT)||'-'||CAST(actual_3rd AS TEXT) as actual,
               odds_val
        FROM race_bets
        WHERE actual_1st = p1 AND actual_2nd = p3 AND actual_3rd = p2
          AND odds_val >= {odds_min} AND odds_val < {odds_max}
        ORDER BY race_date"""
    elif use_pattern_p142:
        query = f"""
        WITH race_bets AS (
            SELECT r.id as race_id, r.race_date, r.venue_code, r.race_number,
                   rp1.pit_number as p1, rp2.pit_number as p2, rp4.pit_number as p4,
                   COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
                    AND o.combination = CAST(rp1.pit_number AS TEXT)||'-'||CAST(rp4.pit_number AS TEXT)||'-'||CAST(rp2.pit_number AS TEXT)), 0) as odds_val,
                   (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') as actual_1st,
                   (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') as actual_2nd,
                   (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') as actual_3rd
            FROM races r
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
            WHERE r.id IN ({placeholders})
        )
        SELECT race_date, venue_code, race_number,
               CAST(p1 AS TEXT)||'-'||CAST(p4 AS TEXT)||'-'||CAST(p2 AS TEXT) as buy,
               CAST(actual_1st AS TEXT)||'-'||CAST(actual_2nd AS TEXT)||'-'||CAST(actual_3rd AS TEXT) as actual,
               odds_val
        FROM race_bets
        WHERE actual_1st = p1 AND actual_2nd = p4 AND actual_3rd = p2
          AND odds_val >= {odds_min} AND odds_val < {odds_max}
        ORDER BY race_date"""
    elif use_pattern_p124:
        query = f"""
        WITH race_bets AS (
            SELECT r.id as race_id, r.race_date, r.venue_code, r.race_number,
                   rp1.pit_number as p1, rp2.pit_number as p2, rp4.pit_number as p4,
                   COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
                    AND o.combination = CAST(rp1.pit_number AS TEXT)||'-'||CAST(rp2.pit_number AS TEXT)||'-'||CAST(rp4.pit_number AS TEXT)), 0) as odds_val,
                   (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') as actual_1st,
                   (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') as actual_2nd,
                   (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') as actual_3rd
            FROM races r
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
            WHERE r.id IN ({placeholders})
        )
        SELECT race_date, venue_code, race_number,
               CAST(p1 AS TEXT)||'-'||CAST(p2 AS TEXT)||'-'||CAST(p4 AS TEXT) as buy,
               CAST(actual_1st AS TEXT)||'-'||CAST(actual_2nd AS TEXT)||'-'||CAST(actual_3rd AS TEXT) as actual,
               odds_val
        FROM race_bets
        WHERE actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4
          AND odds_val >= {odds_min} AND odds_val < {odds_max}
        ORDER BY race_date"""
    elif use_pattern_h:
        query = f"""
        WITH race_bets AS (
            SELECT r.id as race_id, r.race_date, r.venue_code, r.race_number,
                   rp1.pit_number as p1, rp2.pit_number as p2,
                   rp3.pit_number as p3, rp4.pit_number as p4, rp5.pit_number as p5,
                   COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
                    AND o.combination = CAST(rp1.pit_number AS TEXT)||'-'||CAST(rp2.pit_number AS TEXT)||'-'||CAST(rp3.pit_number AS TEXT)), 0) as odds_123,
                   COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
                    AND o.combination = CAST(rp1.pit_number AS TEXT)||'-'||CAST(rp2.pit_number AS TEXT)||'-'||CAST(rp4.pit_number AS TEXT)), 0) as odds_124,
                   COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
                    AND o.combination = CAST(rp1.pit_number AS TEXT)||'-'||CAST(rp2.pit_number AS TEXT)||'-'||CAST(rp5.pit_number AS TEXT)), 0) as odds_125,
                   (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') as actual_1st,
                   (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') as actual_2nd,
                   (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') as actual_3rd
            FROM races r
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
            JOIN race_predictions rp5 ON r.id = rp5.race_id AND rp5.prediction_type = 'before' AND rp5.rank_prediction = 5
            WHERE r.id IN ({placeholders})
        )
        SELECT race_date, venue_code, race_number,
               CASE
                 WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3 AND odds_123 >= {odds_min} AND odds_123 < {odds_max}
                   THEN CAST(p1 AS TEXT)||'-'||CAST(p2 AS TEXT)||'-'||CAST(p3 AS TEXT)
                 WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4 AND odds_124 >= {odds_min} AND odds_124 < {odds_max}
                   THEN CAST(p1 AS TEXT)||'-'||CAST(p2 AS TEXT)||'-'||CAST(p4 AS TEXT)
                 ELSE CAST(p1 AS TEXT)||'-'||CAST(p2 AS TEXT)||'-'||CAST(p5 AS TEXT)
               END as buy,
               CAST(actual_1st AS TEXT)||'-'||CAST(actual_2nd AS TEXT)||'-'||CAST(actual_3rd AS TEXT) as actual,
               CASE
                 WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3 AND odds_123 >= {odds_min} AND odds_123 < {odds_max} THEN odds_123
                 WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4 AND odds_124 >= {odds_min} AND odds_124 < {odds_max} THEN odds_124
                 ELSE odds_125
               END as odds_val
        FROM race_bets
        WHERE (
            (actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3 AND odds_123 >= {odds_min} AND odds_123 < {odds_max})
            OR (actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4 AND odds_124 >= {odds_min} AND odds_124 < {odds_max})
            {'OR (actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p5 AND odds_125 >= ' + str(odds_min) + ' AND odds_125 < ' + str(odds_max) + ')' if not cond.get('pattern_h_exclude_p5') else ''}
        )
        ORDER BY race_date"""
    else:
        query = f"""
        WITH race_bets AS (
            SELECT r.id as race_id, r.race_date, r.venue_code, r.race_number,
                   rp1.pit_number as p1, rp2.pit_number as p2, rp3.pit_number as p3,
                   COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
                    AND o.combination = CAST(rp1.pit_number AS TEXT)||'-'||CAST(rp2.pit_number AS TEXT)||'-'||CAST(rp3.pit_number AS TEXT)), 0) as odds_val,
                   (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') as actual_1st,
                   (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') as actual_2nd,
                   (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') as actual_3rd
            FROM races r
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            WHERE r.id IN ({placeholders})
        )
        SELECT race_date, venue_code, race_number,
               CAST(p1 AS TEXT)||'-'||CAST(p2 AS TEXT)||'-'||CAST(p3 AS TEXT) as buy,
               CAST(actual_1st AS TEXT)||'-'||CAST(actual_2nd AS TEXT)||'-'||CAST(actual_3rd AS TEXT) as actual,
               odds_val
        FROM race_bets
        WHERE actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3
          AND odds_val >= {odds_min} AND odds_val < {odds_max}
        ORDER BY race_date"""

    BATCH_SIZE = 900
    hits = []
    for batch_start in range(0, len(race_ids), BATCH_SIZE):
        batch = race_ids[batch_start:batch_start + BATCH_SIZE]
        batch_ph = ','.join(['?'] * len(batch))
        batch_query = query.replace(f'({placeholders})', f'({batch_ph})')
        cursor.execute(batch_query, batch)
        for row in cursor.fetchall():
            date, vc, rn, buy, actual, odds = row
            venue = VENUE_NAMES.get(str(vc).zfill(2), str(vc))
            payout = int(odds * 100)
            hits.append({
                'date': date,
                'venue': venue,
                'race_number': rn,
                'buy': buy,
                'actual': actual,
                'odds': odds,
                'payout': payout,
                'profit': payout - 100,
            })
    return hits


def analyze_grade_breakdown(
    cursor: sqlite3.Cursor,
    condition_to_races: Dict[str, List[int]],
    conditions: List[Dict]
) -> Dict:
    """全assigned race_idをrace_grade別に集計して返す"""
    all_ids = [rid for ids in condition_to_races.values() for rid in ids]
    if not all_ids:
        return {}

    # race_grade を一括取得
    BATCH = 900
    grade_map: Dict[int, str] = {}
    for i in range(0, len(all_ids), BATCH):
        batch = all_ids[i:i + BATCH]
        ph = ','.join(['?'] * len(batch))
        cursor.execute(f'SELECT id, race_grade FROM races WHERE id IN ({ph})', batch)
        for row in cursor.fetchall():
            grade_map[row[0]] = row[1] or '一般'

    # grade × condition_id ごとに race_ids を振り分け
    grade_cond_races: Dict[str, Dict[str, List[int]]] = {}
    for cond_id, race_ids in condition_to_races.items():
        for rid in race_ids:
            grade = grade_map.get(rid, '一般')
            grade_cond_races.setdefault(grade, {}).setdefault(cond_id, []).append(rid)

    cond_map = {c['id']: c for c in conditions}
    grade_totals: Dict[str, Dict] = {}
    for grade, cond_to_ids in grade_cond_races.items():
        total = {'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0.0}
        for cond_id, race_ids in cond_to_ids.items():
            r = analyze_assigned_races(cursor, cond_map[cond_id], race_ids)
            total['bets'] += r['bets']
            total['hits'] += r['hits']
            total['investment'] += r['investment']
            total['payout'] += r['payout']
        grade_totals[grade] = total
    return grade_totals


def run_unique_backtest(year: int = 2025, full_test: bool = False, enable_wind_filter: bool = True, grade_breakdown: bool = False, show_hits: bool = False) -> Dict:
    """ユニーク版バックテストを実行"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 期間設定
    if full_test:
        years = [2020, 2021, 2022, 2023, 2024, 2025]
        year_start = f"{years[0]}-01-01"
        year_end = f"{years[-1] + 1}-01-01"
    else:
        year_start = f"{year}-01-01"
        year_end = f"{year + 1}-01-01"

    # STEP 1: 全レースを優先度順に条件に割り当て（active=Falseは除外）
    active_conditions = get_active_conditions()
    condition_to_races = assign_races_to_conditions(
        cursor,
        active_conditions,
        year_start,
        year_end,
        enable_wind_filter=enable_wind_filter
    )

    # STEP 2: 各条件の成績を再集計
    results = {
        'test_type': 'unique',
        'date': datetime.now().isoformat(),
        'param_desc': f"standard_backtest_unique {'full(2020-2025)' if full_test else str(year)}",
        'conditions': [],
        'total': {},
    }

    total_bets = 0
    total_hits = 0
    total_investment = 0
    total_payout = 0

    print("\n[Condition Performance - Unique Races]")
    print("-" * 90)
    print(f"{'Condition':<30} {'Bets':>6} {'Hits':>4} {'Hit%':>7} {'ROI':>8} {'Profit':>14}")
    print("-" * 90)

    all_hit_details = []
    for cond in active_conditions:
        assigned_races = condition_to_races.get(cond['id'], [])
        cond_result = analyze_assigned_races(cursor, cond, assigned_races)
        results['conditions'].append(cond_result)

        total_bets += cond_result['bets']
        total_hits += cond_result['hits']
        total_investment += cond_result['investment']
        total_payout += cond_result['payout']

        print(f"{cond_result['name']:<30} {cond_result['bets']:>6} {cond_result['hits']:>4} "
              f"{cond_result['hit_rate']:>6.1f}% {cond_result['roi']:>7.1f}% {cond_result['profit']:>+14,.0f}")

        if show_hits and cond_result['hits'] > 0:
            for h in get_hit_details(cursor, cond, assigned_races):
                all_hit_details.append({'cond_id': cond['id'], **h})

    # STEP 3: 全体サマリー
    results['total'] = {
        'bets': total_bets,
        'hits': total_hits,
        'hit_rate': 100.0 * total_hits / total_bets if total_bets > 0 else 0,
        'investment': total_investment,
        'payout': total_payout,
        'roi': 100.0 * total_payout / total_investment if total_investment > 0 else 0,
        'profit': total_payout - total_investment,
    }

    print("-" * 90)
    print(f"{'Total':<30} {total_bets:>6} {total_hits:>4} "
          f"{results['total']['hit_rate']:>6.1f}% {results['total']['roi']:>7.1f}% {results['total']['profit']:>+14,.0f}")
    print()

    # STEP 4: 的中詳細表示（--show-hits 時のみ）
    if show_hits and all_hit_details:
        print("\n[Hit Details]")
        print("-" * 80)
        print(f"{'日付':<12} {'会場':<6} {'R':>3}  {'買い目':<8} {'実結果':<8} {'オッズ':>8} {'払戻':>10} {'収支':>10}  条件")
        print("-" * 80)
        for h in sorted(all_hit_details, key=lambda x: x['date']):
            print(f"{h['date']:<12} {h['venue']:<6} {h['race_number']:>3}R  "
                  f"{h['buy']:<8} {h['actual']:<8} {h['odds']:>7.1f}倍 "
                  f"{h['payout']:>9,d}円 {h['profit']:>+9,d}円  {h['cond_id']}")
        print("-" * 80)
        print(f"  合計: {len(all_hit_details)}的中 / 払戻計: {sum(h['payout'] for h in all_hit_details):,d}円")
        print()

    # STEP 5: race_grade別集計（--grade-breakdown 時のみ）
    if grade_breakdown:
        print("\n[Grade Breakdown (Unique Races)]")
        print("-" * 72)
        print(f"{'Grade':<20} {'Bets':>6} {'Hits':>5} {'Hit%':>7} {'ROI':>8} {'Profit':>14}")
        print("-" * 72)
        grade_totals = analyze_grade_breakdown(cursor, condition_to_races, active_conditions)
        ORDER = ['一般', 'G1', 'G2', 'G3', 'SG', 'オールレディース', 'ヴィーナスシリーズ', 'ルーキーシリーズ']
        all_grades = ORDER + [g for g in sorted(grade_totals) if g not in ORDER]
        gb_total = {'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0.0}
        for grade in all_grades:
            if grade not in grade_totals:
                continue
            t = grade_totals[grade]
            if t['bets'] == 0:
                continue
            hit_rate = 100.0 * t['hits'] / t['bets']
            roi = 100.0 * t['payout'] / t['investment'] if t['investment'] > 0 else 0.0
            profit = t['payout'] - t['investment']
            print(f"{grade:<20} {t['bets']:>6} {t['hits']:>5} {hit_rate:>6.1f}% {roi:>7.1f}% {profit:>+14,.0f}")
            for k in gb_total:
                gb_total[k] += t[k]
        print("-" * 72)
        gb_hit = 100.0 * gb_total['hits'] / gb_total['bets'] if gb_total['bets'] > 0 else 0
        gb_roi = 100.0 * gb_total['payout'] / gb_total['investment'] if gb_total['investment'] > 0 else 0
        gb_profit = gb_total['payout'] - gb_total['investment']
        print(f"{'Total':<20} {gb_total['bets']:>6} {gb_total['hits']:>5} {gb_hit:>6.1f}% {gb_roi:>7.1f}% {gb_profit:>+14,.0f}")
        print()
        results['grade_breakdown'] = grade_totals

    conn.close()
    return results

def main():
    parser = argparse.ArgumentParser(description='Unique Standard Backtest')
    parser.add_argument('--year', type=int, default=2025, help='Target year (default: 2025)')
    parser.add_argument('--full', action='store_true', help='Run 6-year full test')
    parser.add_argument('--save-json', type=str, help='Save results to JSON (for Tier 3 comparison)')
    parser.add_argument('--no-wind-filter', action='store_true', help='風速フィルター無効化（デフォルト: 有効）')
    parser.add_argument('--grade-breakdown', action='store_true', help='race_grade別パフォーマンスを追加表示')
    parser.add_argument('--show-hits', action='store_true', help='的中レースの詳細（日付・会場・買い目・オッズ）を表示')
    args = parser.parse_args()

    enable_wind_filter = not args.no_wind_filter

    print("=" * 90)
    print("Unique Standard Backtest (Production Simulation)")
    print(f"  [風速フィルター: {'無効' if args.no_wind_filter else '有効（デフォルト）'}]")
    if args.grade_breakdown:
        print("  [race_grade別集計: 有効]")
    if args.show_hits:
        print("  [的中詳細: 有効]")
    print("=" * 90)
    print()

    results = run_unique_backtest(args.year, args.full, enable_wind_filter=enable_wind_filter, grade_breakdown=args.grade_breakdown, show_hits=args.show_hits)

    print("\n[Overall Summary]")
    print("-" * 60)
    print(f"Total bets: {results['total']['bets']:,} (unique)")
    print(f"Hits: {results['total']['hits']:,}")
    print(f"Hit rate: {results['total']['hit_rate']:.2f}%")
    print(f"Total investment: {results['total']['investment']:,} yen")
    print(f"Total payout: {results['total']['payout']:,.0f} yen")
    print(f"ROI: {results['total']['roi']:.1f}%")
    print(f"Profit: {results['total']['profit']:+,.0f} yen")
    print()

    if args.save_json:
        os.makedirs(os.path.dirname(args.save_json), exist_ok=True)
        with open(args.save_json, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"[OK] Results saved: {args.save_json}")

if __name__ == '__main__':
    main()
