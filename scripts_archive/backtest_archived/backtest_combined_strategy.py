# -*- coding: utf-8 -*-
"""
複合戦略バックテスト - 3連単 + 2連単の組み合わせ

戦略:
1. 現行MODERATE戦略（3連単: C/D × A1 × 20-60倍）
2. 追加: 2連単（D × A1 × 5-20倍払戻レンジ）
"""

import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import DATABASE_PATH


def run_combined_backtest():
    """複合戦略のバックテスト"""

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("=" * 80)
    print("複合戦略バックテスト: 3連単 MODERATE + 2連単")
    print("=" * 80)

    # 月別結果
    monthly_trifecta = defaultdict(lambda: {'bet': 0, 'win': 0, 'hits': 0, 'count': 0})
    monthly_exacta = defaultdict(lambda: {'bet': 0, 'win': 0, 'hits': 0, 'count': 0})
    monthly_combined = defaultdict(lambda: {'bet': 0, 'win': 0, 'hits': 0, 'count': 0})

    # レースデータ取得
    cursor.execute('''
        SELECT DISTINCT r.id, r.race_date
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id
        WHERE r.race_date >= '2025-01-01' AND r.race_date < '2025-12-01'
          AND rp.confidence IN ('C', 'D')
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

        if c1_rank not in ['A1', 'A2']:
            continue

        # 結果取得
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND rank IN ('1', '2', '3')
            ORDER BY CAST(rank AS INTEGER)
        ''', (race_id,))
        results = [row[0] for row in cursor.fetchall()]
        if len(results) < 3:
            continue

        actual_1st, actual_2nd, actual_3rd = results[0], results[1], results[2]
        actual_trifecta = f"{actual_1st}-{actual_2nd}-{actual_3rd}"
        actual_exacta = f"{actual_1st}-{actual_2nd}"

        # オッズ・払戻取得
        cursor.execute('SELECT combination, odds FROM trifecta_odds WHERE race_id = ?', (race_id,))
        trifecta_odds = {row[0]: row[1] for row in cursor.fetchall()}

        cursor.execute('SELECT bet_type, amount FROM payouts WHERE race_id = ?', (race_id,))
        payouts = {row[0]: row[1] for row in cursor.fetchall()}

        pred_tri_odds = trifecta_odds.get(pred_trifecta, 0)
        exacta_payout = payouts.get('exacta', 0)

        # ============ 3連単 MODERATE戦略 ============
        trifecta_bet = 0
        if confidence == 'C' and c1_rank == 'A1':
            if 30 <= pred_tri_odds < 60:
                trifecta_bet = 500
            elif 20 <= pred_tri_odds < 40:
                trifecta_bet = 400
        elif confidence == 'D' and c1_rank == 'A1':
            if 25 <= pred_tri_odds < 50:
                trifecta_bet = 300
            elif 20 <= pred_tri_odds < 50:
                trifecta_bet = 300

        if trifecta_bet > 0:
            monthly_trifecta[month]['count'] += 1
            monthly_trifecta[month]['bet'] += trifecta_bet
            if pred_trifecta == actual_trifecta:
                monthly_trifecta[month]['hits'] += 1
                monthly_trifecta[month]['win'] += payouts.get('trifecta', 0) * trifecta_bet / 100

        # ============ 2連単 追加戦略 ============
        # D × A1 × 払戻5-20倍（実際の払戻金で判定）
        exacta_bet = 0
        if confidence == 'D' and c1_rank == 'A1':
            # 2連単は払戻金で条件判定（事前にオッズがないため）
            # バックテストでは的中時の払戻金で条件を判定
            if pred_exacta == actual_exacta:
                # 的中時、払戻が5-20倍（500-2000円）の範囲だったかチェック
                if 500 <= exacta_payout <= 2000:
                    exacta_bet = 200

        # 実際の運用では、2連単オッズがないため常に購入して事後判定
        # ここではシンプルに D × A1 で全購入としてシミュレート
        if confidence == 'D' and c1_rank == 'A1':
            monthly_exacta[month]['count'] += 1
            monthly_exacta[month]['bet'] += 200
            if pred_exacta == actual_exacta:
                monthly_exacta[month]['hits'] += 1
                monthly_exacta[month]['win'] += exacta_payout * 200 / 100

    conn.close()

    # 結果表示
    print("\n" + "=" * 80)
    print("【3連単 MODERATE戦略のみ】")
    print("=" * 80)
    print(f"{'月':>8} {'件数':>6} {'的中':>5} {'的中率':>8} {'投資':>10} {'回収':>12} {'収支':>12} {'ROI':>8}")
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
        print(f"{'合計':>8} {total_tri['count']:>6} {total_tri['hits']:>5} {total_tri['hits']/total_tri['count']*100:>7.1f}% {total_tri['bet']:>9,} {total_tri['win']:>11,.0f} {total_tri['win']-total_tri['bet']:>+11,.0f} {total_tri['win']/total_tri['bet']*100:>7.1f}%")
        print(f"\n黒字月: {pos_months_tri}/{len(monthly_trifecta)} ({pos_months_tri/len(monthly_trifecta)*100:.1f}%)")

    print("\n" + "=" * 80)
    print("【2連単 追加戦略のみ (D × A1)】")
    print("=" * 80)
    print(f"{'月':>8} {'件数':>6} {'的中':>5} {'的中率':>8} {'投資':>10} {'回収':>12} {'収支':>12} {'ROI':>8}")
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
        print(f"{'合計':>8} {total_exa['count']:>6} {total_exa['hits']:>5} {total_exa['hits']/total_exa['count']*100:>7.1f}% {total_exa['bet']:>9,} {total_exa['win']:>11,.0f} {total_exa['win']-total_exa['bet']:>+11,.0f} {total_exa['win']/total_exa['bet']*100:>7.1f}%")
        print(f"\n黒字月: {pos_months_exa}/{len(monthly_exacta)} ({pos_months_exa/len(monthly_exacta)*100:.1f}%)")

    # 複合戦略
    print("\n" + "=" * 80)
    print("【複合戦略 (3連単 + 2連単)】")
    print("=" * 80)
    print(f"{'月':>8} {'件数':>6} {'的中':>5} {'的中率':>8} {'投資':>10} {'回収':>12} {'収支':>12} {'ROI':>8}")
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
        print(f"{'合計':>8} {total_combined['count']:>6} {total_combined['hits']:>5} {total_combined['hits']/total_combined['count']*100:>7.1f}% {total_combined['bet']:>9,} {total_combined['win']:>11,.0f} {total_combined['win']-total_combined['bet']:>+11,.0f} {total_combined['win']/total_combined['bet']*100:>7.1f}%")
        print(f"\n黒字月: {pos_months_combined}/{len(all_months)} ({pos_months_combined/len(all_months)*100:.1f}%)")

    # 比較サマリー
    print("\n" + "=" * 80)
    print("【戦略比較サマリー】")
    print("=" * 80)

    print(f"\n{'戦略':>20} {'年間収支':>15} {'年間ROI':>10} {'黒字月':>12} {'月間的中数':>12}")
    print("-" * 70)

    if total_tri['bet'] > 0:
        tri_profit = total_tri['win'] - total_tri['bet']
        tri_roi = total_tri['win'] / total_tri['bet'] * 100
        tri_monthly_hits = total_tri['hits'] / len(monthly_trifecta)
        print(f"{'3連単のみ':>20} {tri_profit:>+14,.0f}円 {tri_roi:>9.1f}% {pos_months_tri:>5}/{len(monthly_trifecta)}月 {tri_monthly_hits:>11.1f}件")

    if total_exa['bet'] > 0:
        exa_profit = total_exa['win'] - total_exa['bet']
        exa_roi = total_exa['win'] / total_exa['bet'] * 100
        exa_monthly_hits = total_exa['hits'] / len(monthly_exacta)
        print(f"{'2連単のみ':>20} {exa_profit:>+14,.0f}円 {exa_roi:>9.1f}% {pos_months_exa:>5}/{len(monthly_exacta)}月 {exa_monthly_hits:>11.1f}件")

    if total_combined['bet'] > 0:
        comb_profit = total_combined['win'] - total_combined['bet']
        comb_roi = total_combined['win'] / total_combined['bet'] * 100
        comb_monthly_hits = total_combined['hits'] / len(all_months)
        print(f"{'複合 (3連単+2連単)':>20} {comb_profit:>+14,.0f}円 {comb_roi:>9.1f}% {pos_months_combined:>5}/{len(all_months)}月 {comb_monthly_hits:>11.1f}件")


if __name__ == "__main__":
    run_combined_backtest()
