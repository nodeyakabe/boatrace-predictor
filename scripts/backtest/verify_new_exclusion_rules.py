#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
新視点除外ルールの6年間検証

発見した除外ルール候補:
1. D×後半(9-12R) → -22,100円
2. D×0-2m×横風 → -11,700円
3. A×後半(9-12R) → -10,910円
4. D×7m+×横風 → -8,100円
5. D×5-6m×向かい風 → -7,500円
"""
import sqlite3
import sys
import io
import os

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()

# 現在の購入条件
CONDITIONS = {
    'A': [
        {'name': 'A×A1×10-12', 'c1_rank': ['A1'], 'odds_min': 10, 'odds_max': 12, 'venue_filter': None, 'motor_min': None},
        {'name': 'A×A1×14-16', 'c1_rank': ['A1'], 'odds_min': 14, 'odds_max': 16, 'venue_filter': None, 'motor_min': None},
        {'name': 'A×B1×Motor40%+', 'c1_rank': ['B1'], 'odds_min': 10, 'odds_max': 100, 'venue_filter': None, 'motor_min': 40},
    ],
    'B': [
        {'name': 'B×50-100', 'c1_rank': ['A1', 'B1'], 'odds_min': 50, 'odds_max': 100, 'venue_filter': None, 'motor_min': None},
        {'name': 'B×30-50×B1+会場', 'c1_rank': ['B1'], 'odds_min': 30, 'odds_max': 50,
         'venue_filter': [10, 6, 16, 21, 9, 13, 20, 24, 7, 8], 'motor_min': None},
    ],
    'C': [
        {'name': 'C×20-30×B1+会場', 'c1_rank': ['B1'], 'odds_min': 20, 'odds_max': 30,
         'venue_filter': [23, 18, 5, 4, 9, 15, 8, 24, 20, 17], 'motor_min': None},
        {'name': '鳴門×C×A2×30-80', 'c1_rank': ['A2'], 'odds_min': 30, 'odds_max': 80,
         'venue_filter': [14], 'motor_min': None},
    ],
    'D': [
        {'name': 'D×40-50×B1', 'c1_rank': ['B1'], 'odds_min': 40, 'odds_max': 50, 'venue_filter': None, 'motor_min': None},
        {'name': 'D×35-60', 'c1_rank': ['A1', 'A2', 'B1'], 'odds_min': 35, 'odds_max': 60, 'venue_filter': None, 'motor_min': None,
         'race_exclude': [9], 'venue_exclude': [10]},
    ],
}


def analyze_exclusion_rule(confidence, rule_type, rule_value, years=[2020, 2021, 2022, 2023, 2024, 2025]):
    """除外ルールの年別効果を分析"""
    results = []

    for year in years:
        conditions = CONDITIONS.get(confidence, [])
        base_profit = 0
        base_bets = 0
        excluded_profit = 0
        excluded_bets = 0

        for cond in conditions:
            c1_rank_str = "','".join(cond['c1_rank'])
            venue_clause = ""
            if cond.get('venue_filter'):
                venue_clause = f"AND r.venue_code IN ({','.join(map(str, cond['venue_filter']))})"
            motor_clause = ""
            if cond.get('motor_min'):
                motor_clause = f"AND e1.motor_second_rate >= {cond['motor_min']}"
            race_exclude_clause = ""
            if cond.get('race_exclude'):
                race_exclude_clause = f"AND r.race_number NOT IN ({','.join(map(str, cond['race_exclude']))})"
            venue_exclude_clause = ""
            if cond.get('venue_exclude'):
                venue_exclude_clause = f"AND r.venue_code NOT IN ({','.join(map(str, cond['venue_exclude']))})"

            # 除外条件を構築
            if rule_type == 'schedule':
                if rule_value == '後半(9-12R)':
                    exclusion_clause = "AND r.race_number >= 9"
                elif rule_value == '前半(1-4R)':
                    exclusion_clause = "AND r.race_number <= 4"
                else:
                    exclusion_clause = "AND r.race_number BETWEEN 5 AND 8"
            elif rule_type == 'wind_combo':
                # 風速×風向の組み合わせ
                wind_band, wind_dir = rule_value.split('×')
                if wind_band == '0-2m':
                    wind_clause = "AND rc.wind_speed <= 2"
                elif wind_band == '3-4m':
                    wind_clause = "AND rc.wind_speed > 2 AND rc.wind_speed <= 4"
                elif wind_band == '5-6m':
                    wind_clause = "AND rc.wind_speed > 4 AND rc.wind_speed <= 6"
                else:  # 7m+
                    wind_clause = "AND rc.wind_speed > 6"

                if wind_dir == '追い風':
                    dir_clause = "AND rc.wind_direction IN ('北', '北東', '北西')"
                elif wind_dir == '向かい風':
                    dir_clause = "AND rc.wind_direction IN ('南', '南東', '南西')"
                else:  # 横風
                    dir_clause = "AND rc.wind_direction IN ('東', '西')"

                exclusion_clause = f"{wind_clause} {dir_clause}"
            else:
                exclusion_clause = ""

            # ベースクエリ（全体）
            query_base = f'''
            SELECT
                COUNT(*) as bets,
                SUM(CASE
                    WHEN (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') = rp1.pit_number
                     AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') = rp2.pit_number
                     AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') = rp3.pit_number
                    THEN COALESCE(
                        (SELECT o.odds FROM trifecta_odds o
                         WHERE o.race_id = r.id
                         AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
                        ), 0
                    ) * 100
                    ELSE 0
                END) as payout
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
            LEFT JOIN race_conditions rc ON r.id = rc.race_id
            WHERE rp.rank_prediction = 1
            AND rp.confidence = '{confidence}'
            AND e1.racer_rank IN ('{c1_rank_str}')
            AND r.race_date >= '{year}-01-01'
            AND r.race_date < '{year}-12-01'
            {venue_clause}
            {motor_clause}
            {race_exclude_clause}
            {venue_exclude_clause}
            AND COALESCE(
                (SELECT o.odds FROM trifecta_odds o
                 WHERE o.race_id = r.id
                 AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
                ), 0
            ) >= {cond['odds_min']}
            AND COALESCE(
                (SELECT o.odds FROM trifecta_odds o
                 WHERE o.race_id = r.id
                 AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
                ), 0
            ) < {cond['odds_max']}
            '''
            cursor.execute(query_base)
            row = cursor.fetchone()
            if row[0]:
                base_bets += row[0]
                base_profit += (row[1] or 0) - row[0] * 100

            # 除外対象クエリ
            query_excluded = f'''
            SELECT
                COUNT(*) as bets,
                SUM(CASE
                    WHEN (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') = rp1.pit_number
                     AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') = rp2.pit_number
                     AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') = rp3.pit_number
                    THEN COALESCE(
                        (SELECT o.odds FROM trifecta_odds o
                         WHERE o.race_id = r.id
                         AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
                        ), 0
                    ) * 100
                    ELSE 0
                END) as payout
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
            LEFT JOIN race_conditions rc ON r.id = rc.race_id
            WHERE rp.rank_prediction = 1
            AND rp.confidence = '{confidence}'
            AND e1.racer_rank IN ('{c1_rank_str}')
            AND r.race_date >= '{year}-01-01'
            AND r.race_date < '{year}-12-01'
            {venue_clause}
            {motor_clause}
            {race_exclude_clause}
            {venue_exclude_clause}
            {exclusion_clause}
            AND COALESCE(
                (SELECT o.odds FROM trifecta_odds o
                 WHERE o.race_id = r.id
                 AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
                ), 0
            ) >= {cond['odds_min']}
            AND COALESCE(
                (SELECT o.odds FROM trifecta_odds o
                 WHERE o.race_id = r.id
                 AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
                ), 0
            ) < {cond['odds_max']}
            '''
            cursor.execute(query_excluded)
            row = cursor.fetchone()
            if row[0]:
                excluded_bets += row[0]
                excluded_profit += (row[1] or 0) - row[0] * 100

        # 除外による改善
        improvement = -excluded_profit if excluded_profit < 0 else -excluded_profit

        results.append({
            'year': year,
            'base_bets': base_bets,
            'base_profit': base_profit,
            'excluded_bets': excluded_bets,
            'excluded_profit': excluded_profit,
            'improvement': improvement,
        })

    return results


def main():
    print("=" * 100)
    print("新視点除外ルールの6年間検証")
    print("=" * 100)

    # 検証する除外ルール
    rules = [
        {'confidence': 'D', 'type': 'schedule', 'value': '後半(9-12R)', 'desc': 'D×後半(9-12R)'},
        {'confidence': 'A', 'type': 'schedule', 'value': '後半(9-12R)', 'desc': 'A×後半(9-12R)'},
        {'confidence': 'D', 'type': 'wind_combo', 'value': '0-2m×横風', 'desc': 'D×0-2m×横風'},
        {'confidence': 'D', 'type': 'wind_combo', 'value': '7m+×横風', 'desc': 'D×7m+×横風'},
        {'confidence': 'D', 'type': 'wind_combo', 'value': '5-6m×向かい風', 'desc': 'D×5-6m×向かい風'},
        {'confidence': 'D', 'type': 'wind_combo', 'value': '3-4m×追い風', 'desc': 'D×3-4m×追い風'},
        {'confidence': 'A', 'type': 'wind_combo', 'value': '0-2m×向かい風', 'desc': 'A×0-2m×向かい風'},
        {'confidence': 'A', 'type': 'wind_combo', 'value': '3-4m×追い風', 'desc': 'A×3-4m×追い風'},
    ]

    valid_rules = []

    for rule in rules:
        print(f"\n【{rule['desc']}】")
        print("-" * 80)

        results = analyze_exclusion_rule(rule['confidence'], rule['type'], rule['value'])

        total_improvement = 0
        positive_years = 0

        for r in results:
            status = "+" if r['excluded_profit'] < 0 else "-"
            improvement = -r['excluded_profit']
            total_improvement += improvement
            if improvement > 0:
                positive_years += 1
            print(f"  {r['year']}年: 除外{r['excluded_bets']:>4}件, 除外部分収支{r['excluded_profit']:>+8,.0f}円 → 改善{improvement:>+8,.0f}円")

        print(f"  ─────────────────────────────")
        print(f"  6年合計改善: {total_improvement:+,.0f}円 | 効果あり: {positive_years}/6年")

        # 採用基準: 6年合計で改善 AND 4年以上効果あり
        if total_improvement > 0 and positive_years >= 4:
            print(f"  → ★ 採用候補（安定性あり）")
            valid_rules.append({
                **rule,
                'total_improvement': total_improvement,
                'positive_years': positive_years,
            })
        elif total_improvement > 0 and positive_years >= 3:
            print(f"  → △ 要検討（やや不安定）")
        else:
            print(f"  → × 不採用（不安定）")

    # 結果サマリー
    print("\n" + "=" * 100)
    print("【採用候補の除外ルール】")
    print("=" * 100)

    if valid_rules:
        print(f"\n{'ルール':<30} {'6年改善':>15} {'安定性':>10}")
        print("-" * 60)
        for r in sorted(valid_rules, key=lambda x: x['total_improvement'], reverse=True):
            print(f"{r['desc']:<30} {r['total_improvement']:>+14,.0f} {r['positive_years']}/6年")

        total = sum(r['total_improvement'] for r in valid_rules)
        print("-" * 60)
        print(f"{'累積改善額':<30} {total:>+14,.0f}円")
    else:
        print("\n安定性のある除外ルールは見つかりませんでした。")

    conn.close()


if __name__ == '__main__':
    main()
