# -*- coding: utf-8 -*-
"""
統合戦略バックテスト

BetTargetEvaluatorを使用して、3連単+2連単の複合戦略を検証する
"""

import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import DATABASE_PATH
from src.betting import BetTargetEvaluator, BetStatus


def run_integrated_backtest():
    """統合戦略のバックテスト"""

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    evaluator = BetTargetEvaluator()

    print("=" * 80)
    print("Integrated Strategy Backtest: Trifecta MODERATE + Exacta")
    print("=" * 80)

    # 月別結果
    monthly_trifecta = defaultdict(lambda: {'bet': 0, 'win': 0, 'hits': 0, 'count': 0})
    monthly_exacta = defaultdict(lambda: {'bet': 0, 'win': 0, 'hits': 0, 'count': 0})

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
            ORDER BY rank_prediction LIMIT 3
        ''', (race_id,))
        preds = cursor.fetchall()
        if len(preds) < 3:
            continue

        pred_1st, confidence = preds[0]
        pred_2nd = preds[1][0]
        pred_3rd = preds[2][0]
        pred_trifecta = f"{pred_1st}-{pred_2nd}-{pred_3rd}"
        pred_exacta = f"{pred_1st}-{pred_2nd}"

        # 1コース級別
        cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
        c1_row = cursor.fetchone()
        c1_rank = c1_row[0] if c1_row else 'B1'

        # 結果取得
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND rank IN ('1', '2', '3')
            ORDER BY CAST(rank AS INTEGER)
        ''', (race_id,))
        results = [row[0] for row in cursor.fetchall()]
        if len(results) < 3:
            continue

        actual_trifecta = f"{results[0]}-{results[1]}-{results[2]}"
        actual_exacta = f"{results[0]}-{results[1]}"

        # オッズ・払戻取得
        cursor.execute('SELECT combination, odds FROM trifecta_odds WHERE race_id = ?', (race_id,))
        trifecta_odds = {row[0]: row[1] for row in cursor.fetchall()}

        cursor.execute('SELECT bet_type, amount FROM payouts WHERE race_id = ?', (race_id,))
        payouts = {row[0]: row[1] for row in cursor.fetchall()}

        pred_tri_odds = trifecta_odds.get(pred_trifecta, 0)

        # BetTargetEvaluatorで判定
        trifecta_target = evaluator.evaluate(
            confidence=confidence,
            c1_rank=c1_rank,
            old_combo=pred_trifecta,
            new_combo=pred_trifecta,
            old_odds=pred_tri_odds,
            new_odds=pred_tri_odds,
            has_beforeinfo=True
        )

        exacta_target = evaluator.evaluate_exacta(
            confidence=confidence,
            c1_rank=c1_rank,
            pred_1st=pred_1st,
            pred_2nd=pred_2nd,
        )

        # 3連単
        if trifecta_target.status in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
            monthly_trifecta[month]['count'] += 1
            monthly_trifecta[month]['bet'] += trifecta_target.bet_amount
            if pred_trifecta == actual_trifecta:
                monthly_trifecta[month]['hits'] += 1
                monthly_trifecta[month]['win'] += payouts.get('trifecta', 0) * trifecta_target.bet_amount / 100

        # 2連単
        if exacta_target.status == BetStatus.TARGET_ADVANCE:
            monthly_exacta[month]['count'] += 1
            monthly_exacta[month]['bet'] += exacta_target.bet_amount
            if pred_exacta == actual_exacta:
                monthly_exacta[month]['hits'] += 1
                monthly_exacta[month]['win'] += payouts.get('exacta', 0) * exacta_target.bet_amount / 100

    conn.close()

    # 結果表示
    print("\n" + "=" * 80)
    print("[Trifecta MODERATE Strategy]")
    print("=" * 80)
    print(f"{'Month':>8} {'Count':>6} {'Hits':>5} {'HitRate':>8} {'Bet':>10} {'Return':>12} {'Profit':>12} {'ROI':>8}")
    print("-" * 80)

    total_tri = {'bet': 0, 'win': 0, 'hits': 0, 'count': 0}
    pos_months_tri = 0

    for month in sorted(monthly_trifecta.keys()):
        s = monthly_trifecta[month]
        if s['count'] == 0:
            continue
        hit_rate = s['hits'] / s['count'] * 100
        profit = s['win'] - s['bet']
        roi = s['win'] / s['bet'] * 100 if s['bet'] > 0 else 0
        mark = ' [+]' if profit >= 0 else ' [-]'
        print(f"{month:>8} {s['count']:>6} {s['hits']:>5} {hit_rate:>7.1f}% {s['bet']:>9,} {s['win']:>11,.0f} {profit:>+11,.0f} {roi:>7.1f}%{mark}")

        total_tri['bet'] += s['bet']
        total_tri['win'] += s['win']
        total_tri['hits'] += s['hits']
        total_tri['count'] += s['count']
        if profit >= 0:
            pos_months_tri += 1

    print("-" * 80)
    if total_tri['bet'] > 0:
        print(f"{'Total':>8} {total_tri['count']:>6} {total_tri['hits']:>5} {total_tri['hits']/total_tri['count']*100:>7.1f}% {total_tri['bet']:>9,} {total_tri['win']:>11,.0f} {total_tri['win']-total_tri['bet']:>+11,.0f} {total_tri['win']/total_tri['bet']*100:>7.1f}%")
        print(f"\nProfitable months: {pos_months_tri}/{len(monthly_trifecta)} ({pos_months_tri/len(monthly_trifecta)*100:.1f}%)")

    print("\n" + "=" * 80)
    print("[Exacta Strategy (D x A1)]")
    print("=" * 80)
    print(f"{'Month':>8} {'Count':>6} {'Hits':>5} {'HitRate':>8} {'Bet':>10} {'Return':>12} {'Profit':>12} {'ROI':>8}")
    print("-" * 80)

    total_exa = {'bet': 0, 'win': 0, 'hits': 0, 'count': 0}
    pos_months_exa = 0

    for month in sorted(monthly_exacta.keys()):
        s = monthly_exacta[month]
        if s['count'] == 0:
            continue
        hit_rate = s['hits'] / s['count'] * 100
        profit = s['win'] - s['bet']
        roi = s['win'] / s['bet'] * 100 if s['bet'] > 0 else 0
        mark = ' [+]' if profit >= 0 else ' [-]'
        print(f"{month:>8} {s['count']:>6} {s['hits']:>5} {hit_rate:>7.1f}% {s['bet']:>9,} {s['win']:>11,.0f} {profit:>+11,.0f} {roi:>7.1f}%{mark}")

        total_exa['bet'] += s['bet']
        total_exa['win'] += s['win']
        total_exa['hits'] += s['hits']
        total_exa['count'] += s['count']
        if profit >= 0:
            pos_months_exa += 1

    print("-" * 80)
    if total_exa['bet'] > 0:
        print(f"{'Total':>8} {total_exa['count']:>6} {total_exa['hits']:>5} {total_exa['hits']/total_exa['count']*100:>7.1f}% {total_exa['bet']:>9,} {total_exa['win']:>11,.0f} {total_exa['win']-total_exa['bet']:>+11,.0f} {total_exa['win']/total_exa['bet']*100:>7.1f}%")
        print(f"\nProfitable months: {pos_months_exa}/{len(monthly_exacta)} ({pos_months_exa/len(monthly_exacta)*100:.1f}%)")

    # 複合戦略
    print("\n" + "=" * 80)
    print("[Combined Strategy (Trifecta + Exacta)]")
    print("=" * 80)
    print(f"{'Month':>8} {'Count':>6} {'Hits':>5} {'HitRate':>8} {'Bet':>10} {'Return':>12} {'Profit':>12} {'ROI':>8}")
    print("-" * 80)

    all_months = sorted(set(monthly_trifecta.keys()) | set(monthly_exacta.keys()))
    total_combined = {'bet': 0, 'win': 0, 'hits': 0, 'count': 0}
    pos_months_combined = 0

    for month in all_months:
        tri = monthly_trifecta.get(month, {'bet': 0, 'win': 0, 'hits': 0, 'count': 0})
        exa = monthly_exacta.get(month, {'bet': 0, 'win': 0, 'hits': 0, 'count': 0})

        combined_bet = tri['bet'] + exa['bet']
        combined_win = tri['win'] + exa['win']
        combined_hits = tri['hits'] + exa['hits']
        combined_count = tri['count'] + exa['count']

        if combined_count == 0:
            continue

        hit_rate = combined_hits / combined_count * 100
        profit = combined_win - combined_bet
        roi = combined_win / combined_bet * 100 if combined_bet > 0 else 0
        mark = ' [+]' if profit >= 0 else ' [-]'
        print(f"{month:>8} {combined_count:>6} {combined_hits:>5} {hit_rate:>7.1f}% {combined_bet:>9,} {combined_win:>11,.0f} {profit:>+11,.0f} {roi:>7.1f}%{mark}")

        total_combined['bet'] += combined_bet
        total_combined['win'] += combined_win
        total_combined['hits'] += combined_hits
        total_combined['count'] += combined_count
        if profit >= 0:
            pos_months_combined += 1

    print("-" * 80)
    if total_combined['bet'] > 0:
        print(f"{'Total':>8} {total_combined['count']:>6} {total_combined['hits']:>5} {total_combined['hits']/total_combined['count']*100:>7.1f}% {total_combined['bet']:>9,} {total_combined['win']:>11,.0f} {total_combined['win']-total_combined['bet']:>+11,.0f} {total_combined['win']/total_combined['bet']*100:>7.1f}%")
        print(f"\nProfitable months: {pos_months_combined}/{len(all_months)} ({pos_months_combined/len(all_months)*100:.1f}%)")

    # 比較サマリー
    print("\n" + "=" * 80)
    print("[Strategy Comparison Summary]")
    print("=" * 80)

    print(f"\n{'Strategy':>25} {'Annual Profit':>15} {'Annual ROI':>10} {'Profitable':>12} {'Monthly Hits':>12}")
    print("-" * 75)

    if total_tri['bet'] > 0:
        tri_profit = total_tri['win'] - total_tri['bet']
        tri_roi = total_tri['win'] / total_tri['bet'] * 100
        tri_monthly_hits = total_tri['hits'] / len(monthly_trifecta)
        print(f"{'Trifecta Only':>25} {tri_profit:>+14,.0f}Y {tri_roi:>9.1f}% {pos_months_tri:>5}/{len(monthly_trifecta)}mo {tri_monthly_hits:>11.1f}")

    if total_exa['bet'] > 0:
        exa_profit = total_exa['win'] - total_exa['bet']
        exa_roi = total_exa['win'] / total_exa['bet'] * 100
        exa_monthly_hits = total_exa['hits'] / len(monthly_exacta)
        print(f"{'Exacta Only':>25} {exa_profit:>+14,.0f}Y {exa_roi:>9.1f}% {pos_months_exa:>5}/{len(monthly_exacta)}mo {exa_monthly_hits:>11.1f}")

    if total_combined['bet'] > 0:
        comb_profit = total_combined['win'] - total_combined['bet']
        comb_roi = total_combined['win'] / total_combined['bet'] * 100
        comb_monthly_hits = total_combined['hits'] / len(all_months)
        print(f"{'Combined (Tri+Exa)':>25} {comb_profit:>+14,.0f}Y {comb_roi:>9.1f}% {pos_months_combined:>5}/{len(all_months)}mo {comb_monthly_hits:>11.1f}")


if __name__ == "__main__":
    run_integrated_backtest()
