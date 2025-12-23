# -*- coding: utf-8 -*-
"""
2連単のみ戦略の最適化バックテスト

信頼度・級別・オッズ条件を組み合わせて最適な2連単戦略を探る
"""

import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import DATABASE_PATH


def run_exacta_only_backtest():
    """2連単のみ戦略のバックテスト"""

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("=" * 80)
    print("Exacta Only Strategy Optimization Backtest")
    print("=" * 80)

    # 条件別の月別結果
    conditions_results = {}

    # テストする条件
    test_conditions = [
        {'name': 'D x A1', 'conf': ['D'], 'c1_rank': ['A1']},
        {'name': 'D x A1/A2', 'conf': ['D'], 'c1_rank': ['A1', 'A2']},
        {'name': 'C x A1', 'conf': ['C'], 'c1_rank': ['A1']},
        {'name': 'C x A1/A2', 'conf': ['C'], 'c1_rank': ['A1', 'A2']},
        {'name': 'C/D x A1', 'conf': ['C', 'D'], 'c1_rank': ['A1']},
        {'name': 'C/D x A1/A2', 'conf': ['C', 'D'], 'c1_rank': ['A1', 'A2']},
    ]

    for cond in test_conditions:
        conditions_results[cond['name']] = defaultdict(lambda: {'bet': 0, 'win': 0, 'hits': 0, 'count': 0})

    # レースデータ取得
    cursor.execute('''
        SELECT DISTINCT r.id, r.race_date
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id
        WHERE r.race_date >= '2025-01-01' AND r.race_date < '2025-12-01'
          AND rp.prediction_type = 'advance'
          AND rp.rank_prediction = 1
    ''')
    races = cursor.fetchall()

    for race_id, race_date in races:
        month = race_date[:7]

        # 予測取得
        cursor.execute('''
            SELECT pit_number, confidence FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'advance'
            ORDER BY rank_prediction LIMIT 2
        ''', (race_id,))
        preds = cursor.fetchall()
        if len(preds) < 2:
            continue

        pred_1st, confidence = preds[0]
        pred_2nd = preds[1][0]
        pred_exacta = f"{pred_1st}-{pred_2nd}"

        # 1コース級別
        cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
        c1_row = cursor.fetchone()
        c1_rank = c1_row[0] if c1_row else 'B1'

        # 結果取得
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND rank IN ('1', '2')
            ORDER BY CAST(rank AS INTEGER)
        ''', (race_id,))
        results = [row[0] for row in cursor.fetchall()]
        if len(results) < 2:
            continue

        actual_exacta = f"{results[0]}-{results[1]}"

        # 払戻取得
        cursor.execute('SELECT bet_type, amount FROM payouts WHERE race_id = ?', (race_id,))
        payouts = {row[0]: row[1] for row in cursor.fetchall()}
        exacta_payout = payouts.get('exacta', 0)

        is_hit = (pred_exacta == actual_exacta)

        # 各条件でチェック
        for cond in test_conditions:
            if confidence in cond['conf'] and c1_rank in cond['c1_rank']:
                stats = conditions_results[cond['name']]
                stats[month]['count'] += 1
                stats[month]['bet'] += 200
                if is_hit:
                    stats[month]['hits'] += 1
                    stats[month]['win'] += exacta_payout * 200 / 100

    conn.close()

    # 結果表示
    print("\n" + "=" * 80)
    print("[Condition Comparison - Annual Summary]")
    print("=" * 80)
    print(f"{'Condition':>15} {'Count':>7} {'Hits':>6} {'HitRate':>8} {'Bet':>12} {'Return':>12} {'Profit':>12} {'ROI':>8} {'ProfitMo':>10}")
    print("-" * 100)

    condition_summaries = []

    for cond_name, monthly_stats in conditions_results.items():
        total = {'bet': 0, 'win': 0, 'hits': 0, 'count': 0}
        pos_months = 0

        for month, s in monthly_stats.items():
            total['bet'] += s['bet']
            total['win'] += s['win']
            total['hits'] += s['hits']
            total['count'] += s['count']
            if s['win'] - s['bet'] >= 0:
                pos_months += 1

        if total['count'] == 0:
            continue

        hit_rate = total['hits'] / total['count'] * 100
        profit = total['win'] - total['bet']
        roi = total['win'] / total['bet'] * 100 if total['bet'] > 0 else 0
        months_count = len([m for m in monthly_stats.values() if m['count'] > 0])

        condition_summaries.append({
            'name': cond_name,
            'count': total['count'],
            'hits': total['hits'],
            'hit_rate': hit_rate,
            'bet': total['bet'],
            'win': total['win'],
            'profit': profit,
            'roi': roi,
            'pos_months': pos_months,
            'total_months': months_count,
            'monthly_stats': monthly_stats,
        })

        mark = " *" if roi >= 100 else ""
        print(f"{cond_name:>15} {total['count']:>7} {total['hits']:>6} {hit_rate:>7.1f}% {total['bet']:>11,} {total['win']:>11,.0f} {profit:>+11,.0f} {roi:>7.1f}%{mark} {pos_months:>4}/{months_count}")

    # 最良条件の詳細
    best_by_roi = max(condition_summaries, key=lambda x: x['roi'])
    best_by_profit = max(condition_summaries, key=lambda x: x['profit'])
    best_by_stability = max(condition_summaries, key=lambda x: x['pos_months'] / x['total_months'] if x['total_months'] > 0 else 0)

    print("\n" + "=" * 80)
    print("[Best Conditions]")
    print("=" * 80)
    print(f"Best by ROI:       {best_by_roi['name']} (ROI {best_by_roi['roi']:.1f}%)")
    print(f"Best by Profit:    {best_by_profit['name']} (Profit +{best_by_profit['profit']:,.0f}Y)")
    print(f"Best by Stability: {best_by_stability['name']} ({best_by_stability['pos_months']}/{best_by_stability['total_months']} months)")

    # 最良条件の月別詳細
    print("\n" + "=" * 80)
    print(f"[Monthly Detail - {best_by_roi['name']}]")
    print("=" * 80)
    print(f"{'Month':>8} {'Count':>6} {'Hits':>5} {'HitRate':>8} {'Bet':>10} {'Return':>12} {'Profit':>12} {'ROI':>8}")
    print("-" * 80)

    for month in sorted(best_by_roi['monthly_stats'].keys()):
        s = best_by_roi['monthly_stats'][month]
        if s['count'] == 0:
            continue
        hit_rate = s['hits'] / s['count'] * 100
        profit = s['win'] - s['bet']
        roi = s['win'] / s['bet'] * 100 if s['bet'] > 0 else 0
        mark = ' [+]' if profit >= 0 else ' [-]'
        print(f"{month:>8} {s['count']:>6} {s['hits']:>5} {hit_rate:>7.1f}% {s['bet']:>9,} {s['win']:>11,.0f} {profit:>+11,.0f} {roi:>7.1f}%{mark}")

    # 3連単との比較
    print("\n" + "=" * 80)
    print("[Comparison with Trifecta MODERATE]")
    print("=" * 80)
    print(f"""
Trifecta MODERATE (Current):
  - Annual Profit: +92,020Y
  - ROI: 122.9%
  - Profitable Months: 7/11 (63.6%)
  - Monthly Hits: 2.9

{best_by_roi['name']} Exacta Only:
  - Annual Profit: {best_by_roi['profit']:+,.0f}Y
  - ROI: {best_by_roi['roi']:.1f}%
  - Profitable Months: {best_by_roi['pos_months']}/{best_by_roi['total_months']} ({best_by_roi['pos_months']/best_by_roi['total_months']*100:.1f}%)
  - Monthly Hits: {best_by_roi['hits']/best_by_roi['total_months']:.1f}

Combined (Trifecta + Exacta):
  - Annual Profit: +104,260Y
  - ROI: 117.9%
  - Profitable Months: 6/11 (54.5%)
  - Monthly Hits: 14.9
""")


if __name__ == "__main__":
    run_exacta_only_backtest()
