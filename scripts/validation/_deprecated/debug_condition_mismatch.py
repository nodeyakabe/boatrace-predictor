#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
条件不一致のデバッグスクリプト

Tier 2（SQL）で抽出されるがTier 3（Python）で除外される条件を特定
"""
import sqlite3
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from config.bet_conditions import STANDARD_BET_CONDITIONS


def analyze_condition_coverage():
    """Tier 2とTier 3の条件カバレッジを比較"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=== 条件カバレッジ分析 ===\n")

    # config/bet_conditions.py の条件を確認
    print(f"config/bet_conditions.py の条件数: {len(STANDARD_BET_CONDITIONS)}\n")

    for i, cond in enumerate(STANDARD_BET_CONDITIONS):
        print(f"【条件{i+1}】{cond['name']}")
        print(f"  信頼度: {cond.get('confidence', 'None')}")
        print(f"  級別: {cond['c1_rank']}")
        print(f"  オッズ範囲: {cond['odds_min']}-{cond['odds_max']}")
        print(f"  パターンH: {cond.get('use_pattern_h', False)}")
        print(f"  会場フィルター: {cond.get('venue_filter', 'なし')}")
        print(f"  その他条件: ", end='')
        optional_keys = ['month_exclude', 'escape_rate_min', 'predicted_course',
                        'bias_max', 'c1_second_rate_min', 'c1_second_rate_max',
                        'predicted_rank_has_class', 'predicted_rank_range']
        other_conds = [k for k in optional_keys if cond.get(k) is not None]
        print(', '.join(other_conds) if other_conds else 'なし')
        print()

    # Tier 2で抽出される信頼度×級別の組み合わせを集計
    print("=== Tier 2で抽出される信頼度×級別の分布 ===\n")

    query = '''
    SELECT
        rp1.confidence,
        e1.racer_rank as c1_rank,
        COUNT(*) as count
    FROM races r
    JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
    WHERE rp1.confidence IN ('A', 'B', 'C', 'D')
      AND e1.racer_rank IN ('A1', 'A2', 'B1', 'B2')
      AND r.race_date >= '2024-01-01'
      AND r.race_date < '2026-01-01'
    GROUP BY rp1.confidence, e1.racer_rank
    ORDER BY rp1.confidence, count DESC
    '''

    cursor.execute(query)
    rows = cursor.fetchall()

    print("信頼度 | 級別 | 件数")
    print("-" * 30)
    for row in rows:
        print(f"{row['confidence']:>6} | {row['c1_rank']:>4} | {row['count']:>6}")

    print("\n=== config/bet_conditions.py でカバーされている組み合わせ ===\n")

    # 信頼度×級別の組み合わせを抽出
    covered_combinations = set()
    for cond in STANDARD_BET_CONDITIONS:
        confidence = cond.get('confidence')
        c1_ranks = cond.get('c1_rank', [])

        if confidence is None:
            # B2条件（全信頼度に適用）
            for conf in ['A', 'B', 'C', 'D', 'E']:
                for rank in c1_ranks:
                    covered_combinations.add((conf, rank))
        else:
            for rank in c1_ranks:
                covered_combinations.add((confidence, rank))

    print("カバー済み組み合わせ:")
    for conf in ['A', 'B', 'C', 'D']:
        for rank in ['A1', 'A2', 'B1', 'B2']:
            if (conf, rank) in covered_combinations:
                print(f"  {conf} × {rank:>2} ✅")
            else:
                print(f"  {conf} × {rank:>2} ❌ 未カバー")

    # サンプルレースで詳細チェック
    print("\n=== サンプルレースでのオッズ範囲チェック ===\n")

    # Tier 2で抽出されるレースのオッズ分布
    query = '''
    SELECT
        rp1.confidence,
        e1.racer_rank as c1_rank,
        COALESCE(
            (SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
             AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)),
            0
        ) as odds_123,
        COUNT(*) as count
    FROM races r
    JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
    JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
    WHERE rp1.confidence IN ('A', 'B', 'C', 'D')
      AND e1.racer_rank IN ('A1', 'A2', 'B1')
      AND r.race_date >= '2024-01-01'
      AND r.race_date < '2026-01-01'
      AND odds_123 > 0
    GROUP BY rp1.confidence, e1.racer_rank,
             CASE
                WHEN odds_123 < 10 THEN '<10'
                WHEN odds_123 < 30 THEN '10-30'
                WHEN odds_123 < 50 THEN '30-50'
                WHEN odds_123 < 100 THEN '50-100'
                ELSE '100+'
             END
    ORDER BY rp1.confidence, e1.racer_rank,
             CASE
                WHEN odds_123 < 10 THEN 1
                WHEN odds_123 < 30 THEN 2
                WHEN odds_123 < 50 THEN 3
                WHEN odds_123 < 100 THEN 4
                ELSE 5
             END
    LIMIT 50
    '''

    cursor.execute(query)
    rows = cursor.fetchall()

    print("信頼度 | 級別 | オッズ範囲 | 件数")
    print("-" * 40)
    for row in rows:
        odds = row['odds_123']
        if odds < 10:
            odds_range = '<10'
        elif odds < 30:
            odds_range = '10-30'
        elif odds < 50:
            odds_range = '30-50'
        elif odds < 100:
            odds_range = '50-100'
        else:
            odds_range = '100+'
        print(f"{row['confidence']:>6} | {row['c1_rank']:>4} | {odds_range:>10} | {row['count']:>6}")

    conn.close()


if __name__ == '__main__':
    analyze_condition_coverage()
