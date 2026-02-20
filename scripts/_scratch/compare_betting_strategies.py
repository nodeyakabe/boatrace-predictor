#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
買い目パターン比較分析スクリプト
1. ユーザー提案の買い目（1位軸、2着3着分散）
2. 投資配分の比較（本命厚め vs 均等 vs 4点買い）
"""
import sqlite3
import sys
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DATABASE_PATH = 'data/boatrace.db'

def analyze_user_suggested_pattern():
    """ユーザー提案の買い目パターンを分析"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("="*80)
    print("【調査1】ユーザー提案の買い目パターン")
    print("="*80)
    print()
    print("買い目:")
    print("  ① 予測1着-予測2着-予測3着 (133円)")
    print("  ② 予測1着-予測3着-予測2着 (133円) ← 2着と3着を入れ替え")
    print("  ③ 予測1着-予測2着-予測4着 (134円)")
    print("  合計投資額: 400円")
    print()
    print("戦略: 「1位軸」で2着・3着を分散")
    print("-"*80)
    print()

    # 信頼度ごとに分析
    confidences = ['A', 'B', 'C', 'D', 'E', 'ALL']

    for conf in confidences:
        if conf == 'ALL':
            print(f"{'='*80}")
            print(f"【全信頼度 合計】")
            print(f"{'='*80}")
            conf_filter = ""
        else:
            print(f"{'='*80}")
            print(f"【信頼度 {conf}】")
            print(f"{'='*80}")
            conf_filter = f"AND rp1.confidence = '{conf}'"

        cursor.execute(f'''
            WITH predictions AS (
                SELECT
                    rp1.race_id,
                    rp1.pit_number as p1,
                    rp2.pit_number as p2,
                    rp3.pit_number as p3,
                    rp4.pit_number as p4
                FROM race_predictions rp1
                LEFT JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
                    AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
                LEFT JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
                    AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
                LEFT JOIN race_predictions rp4 ON rp1.race_id = rp4.race_id
                    AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
                WHERE rp1.prediction_type = 'before'
                AND rp1.rank_prediction = 1
                {conf_filter}
            ),
            results_agg AS (
                SELECT
                    race_id,
                    CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
                    CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
                    CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
                FROM results
                WHERE rank IN ('1', '2', '3')
                GROUP BY race_id
            )
            SELECT
                COUNT(*) as races,
                -- 買い目① 1-2-3の的中
                SUM(CASE WHEN combo_123 = r.actual_combo THEN 1 ELSE 0 END) as hits_123,
                -- 買い目② 1-3-2の的中（2着と3着入れ替え）
                SUM(CASE WHEN combo_132 = r.actual_combo THEN 1 ELSE 0 END) as hits_132,
                -- 買い目③ 1-2-4の的中
                SUM(CASE WHEN combo_124 = r.actual_combo THEN 1 ELSE 0 END) as hits_124,
                -- いずれか的中
                SUM(CASE WHEN combo_123 = r.actual_combo OR combo_132 = r.actual_combo OR combo_124 = r.actual_combo
                    THEN 1 ELSE 0 END) as hits_total,
                -- 払戻（133円、133円、134円）
                SUM(CASE WHEN combo_123 = r.actual_combo THEN o123.odds * 133
                         WHEN combo_132 = r.actual_combo THEN o132.odds * 133
                         WHEN combo_124 = r.actual_combo THEN o124.odds * 134
                         ELSE 0 END) as returns,
                SUM(400) as investment,
                -- 平均オッズ
                AVG(CASE WHEN combo_123 = r.actual_combo THEN o123.odds
                         WHEN combo_132 = r.actual_combo THEN o132.odds
                         WHEN combo_124 = r.actual_combo THEN o124.odds END) as avg_hit_odds
            FROM (
                SELECT
                    p.race_id,
                    CAST(p.p1 AS TEXT) || '-' || CAST(p.p2 AS TEXT) || '-' || CAST(p.p3 AS TEXT) as combo_123,
                    CAST(p.p1 AS TEXT) || '-' || CAST(p.p3 AS TEXT) || '-' || CAST(p.p2 AS TEXT) as combo_132,
                    CAST(p.p1 AS TEXT) || '-' || CAST(p.p2 AS TEXT) || '-' || CAST(p.p4 AS TEXT) as combo_124
                FROM predictions p
            ) pred
            LEFT JOIN trifecta_odds o123 ON pred.race_id = o123.race_id AND o123.combination = pred.combo_123
            LEFT JOIN trifecta_odds o132 ON pred.race_id = o132.race_id AND o132.combination = pred.combo_132
            LEFT JOIN trifecta_odds o124 ON pred.race_id = o124.race_id AND o124.combination = pred.combo_124
            LEFT JOIN results_agg r ON pred.race_id = r.race_id
        ''')

        row = cursor.fetchone()
        races, hits_123, hits_132, hits_124, hits_total, returns, investment, avg_odds = row

        if races and investment:
            profit = returns - investment
            roi = 100.0 * returns / investment
            hit_rate = 100.0 * hits_total / races

            print(f"  レース数:       {races:>6,}件")
            print(f"  的中内訳:")
            print(f"    ① 1-2-3:      {hits_123:>6,}件")
            print(f"    ② 1-3-2:      {hits_132:>6,}件  ← 2着と3着入れ替え")
            print(f"    ③ 1-2-4:      {hits_124:>6,}件")
            print(f"    合計的中:     {hits_total:>6,}件 ({hit_rate:.1f}%)")
            print()
            print(f"  投資額:         {investment:>9,.0f}円")
            print(f"  払戻額:         {returns:>9,.0f}円")
            print(f"  収支:           {profit:>+9,.0f}円")
            print(f"  ROI:            {roi:>7.1f}%")
            if avg_odds:
                print(f"  平均配当:       {avg_odds:>7.1f}倍")
        else:
            print(f"  データなし")

        print()

    conn.close()


def analyze_investment_distribution():
    """投資配分の比較分析"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print()
    print("="*80)
    print("【調査2】投資配分の比較（信頼度B限定）")
    print("="*80)
    print()
    print("比較パターン:")
    print("  A. 現行（本命厚め）:  1-2-3(200円), 1-2-4(100円), 1-2-5(100円)")
    print("  B. 均等3点買い:      1-2-3(133円), 1-2-4(133円), 1-2-5(134円)")
    print("  C. 4点買い:          1-2-3(100円), 1-2-4(100円), 1-2-5(100円), 1-2-6(100円)")
    print()
    print("※ 信頼度Bで比較（高オッズ帯、パターンH使用条件）")
    print("-"*80)
    print()

    patterns = [
        {
            'name': 'A. 現行（本命厚め）',
            'bets': [
                {'combo': '123', 'amount': 200},
                {'combo': '124', 'amount': 100},
                {'combo': '125', 'amount': 100},
            ],
            'total': 400,
        },
        {
            'name': 'B. 均等3点買い',
            'bets': [
                {'combo': '123', 'amount': 133},
                {'combo': '124', 'amount': 133},
                {'combo': '125', 'amount': 134},
            ],
            'total': 400,
        },
        {
            'name': 'C. 4点買い',
            'bets': [
                {'combo': '123', 'amount': 100},
                {'combo': '124', 'amount': 100},
                {'combo': '125', 'amount': 100},
                {'combo': '126', 'amount': 100},
            ],
            'total': 400,
        },
    ]

    results_summary = []

    for pattern in patterns:
        print(f"{'='*80}")
        print(f"{pattern['name']}")
        print(f"{'='*80}")
        print("買い目:")
        for bet in pattern['bets']:
            print(f"  1-2-{bet['combo'][-1]}: {bet['amount']:>3}円")
        print(f"  合計: {pattern['total']}円")
        print()

        # SQLクエリを動的に構築
        combo_cases = []
        odds_joins = []
        hit_conditions = []

        for i, bet in enumerate(pattern['bets']):
            combo_num = bet['combo']
            p3 = combo_num[-1]
            combo_cases.append(f"CAST(p.p1 AS TEXT) || '-' || CAST(p.p2 AS TEXT) || '-' || CAST(p.p{p3} AS TEXT) as combo_{combo_num}")
            odds_joins.append(f"LEFT JOIN trifecta_odds o{combo_num} ON pred.race_id = o{combo_num}.race_id AND o{combo_num}.combination = pred.combo_{combo_num}")
            hit_conditions.append(f"WHEN combo_{combo_num} = r.actual_combo THEN o{combo_num}.odds * {bet['amount']}")

        combo_cases_str = ',\n                    '.join(combo_cases)
        odds_joins_str = '\n            '.join(odds_joins)
        hit_conditions_str = '\n                         '.join(hit_conditions)

        # 的中判定条件
        hit_check_conditions = ' OR '.join([f"combo_{bet['combo']} = r.actual_combo" for bet in pattern['bets']])
        avg_odds_conditions = '\n                         '.join([f"WHEN combo_{bet['combo']} = r.actual_combo THEN o{bet['combo']}.odds" for bet in pattern['bets']])

        query = f'''
            WITH predictions AS (
                SELECT
                    rp1.race_id,
                    rp1.pit_number as p1,
                    rp2.pit_number as p2,
                    rp3.pit_number as p3,
                    rp4.pit_number as p4,
                    rp5.pit_number as p5,
                    rp6.pit_number as p6
                FROM race_predictions rp1
                LEFT JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
                    AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
                LEFT JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
                    AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
                LEFT JOIN race_predictions rp4 ON rp1.race_id = rp4.race_id
                    AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
                LEFT JOIN race_predictions rp5 ON rp1.race_id = rp5.race_id
                    AND rp5.prediction_type = 'before' AND rp5.rank_prediction = 5
                LEFT JOIN race_predictions rp6 ON rp1.race_id = rp6.race_id
                    AND rp6.prediction_type = 'before' AND rp6.rank_prediction = 6
                WHERE rp1.prediction_type = 'before'
                AND rp1.rank_prediction = 1
                AND rp1.confidence = 'B'
            ),
            results_agg AS (
                SELECT
                    race_id,
                    CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
                    CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
                    CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
                FROM results
                WHERE rank IN ('1', '2', '3')
                GROUP BY race_id
            )
            SELECT
                COUNT(*) as races,
                SUM(CASE WHEN {hit_check_conditions}
                    THEN 1 ELSE 0 END) as hits,
                SUM(CASE {hit_conditions_str}
                         ELSE 0 END) as returns,
                SUM({pattern['total']}) as investment,
                AVG(CASE {avg_odds_conditions} END) as avg_hit_odds
            FROM (
                SELECT
                    p.race_id,
                    {combo_cases_str}
                FROM predictions p
            ) pred
            {odds_joins_str}
            LEFT JOIN results_agg r ON pred.race_id = r.race_id
        '''

        cursor.execute(query)
        row = cursor.fetchone()
        races, hits, returns, investment, avg_odds = row

        if races and investment:
            profit = returns - investment
            roi = 100.0 * returns / investment
            hit_rate = 100.0 * hits / races

            print(f"  レース数:       {races:>6,}件")
            print(f"  的中数:         {hits:>6,}件 ({hit_rate:.1f}%)")
            print(f"  投資額:         {investment:>9,.0f}円")
            print(f"  払戻額:         {returns:>9,.0f}円")
            print(f"  収支:           {profit:>+9,.0f}円")
            print(f"  ROI:            {roi:>7.1f}%")
            if avg_odds:
                print(f"  平均配当:       {avg_odds:>7.1f}倍")

            results_summary.append({
                'name': pattern['name'],
                'races': races,
                'hits': hits,
                'hit_rate': hit_rate,
                'investment': investment,
                'returns': returns,
                'profit': profit,
                'roi': roi,
                'avg_odds': avg_odds or 0,
            })
        else:
            print(f"  データなし")

        print()

    # 比較サマリー
    print("="*80)
    print("【比較サマリー】")
    print("="*80)
    print()
    print(f"{'パターン':<24} {'的中率':<10} {'ROI':<10} {'収支':<15} {'平均配当':<10}")
    print("-"*80)
    for r in results_summary:
        print(f"{r['name']:<24} {r['hit_rate']:>6.1f}%  {r['roi']:>7.1f}%  {r['profit']:>+12,.0f}円  {r['avg_odds']:>7.1f}倍")

    print()
    if len(results_summary) >= 2:
        best_profit = max(results_summary, key=lambda x: x['profit'])
        best_roi = max(results_summary, key=lambda x: x['roi'])
        print(f"収支最大:   {best_profit['name']} ({best_profit['profit']:+,.0f}円)")
        print(f"ROI最大:    {best_roi['name']} ({best_roi['roi']:.1f}%)")

    conn.close()


if __name__ == '__main__':
    import time
    start = time.time()

    # 調査1: ユーザー提案の買い目
    analyze_user_suggested_pattern()

    # 調査2: 投資配分の比較
    analyze_investment_distribution()

    elapsed = time.time() - start
    print()
    print("="*80)
    print("分析完了")
    print("="*80)
    print(f"\n実行時間: {elapsed:.1f}秒")
