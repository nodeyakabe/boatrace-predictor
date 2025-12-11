# -*- coding: utf-8 -*-
"""12月購入シミュレーション

12月1日から今日までの戦略Aでの購入をシミュレート
"""

import sys
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


# 戦略A条件（残タスク一覧.mdより）
STRATEGY_A_CONDITIONS = {
    'Tier1': [
        {'name': 'D-B1-200-300倍', 'confidence': 'D', 'c1_rank': 'B1', 'odds_min': 200, 'odds_max': 300, 'bet': 300},
        {'name': 'D-A1-100-150倍', 'confidence': 'D', 'c1_rank': 'A1', 'odds_min': 100, 'odds_max': 150, 'bet': 300},
        {'name': 'D-A1-200-300倍', 'confidence': 'D', 'c1_rank': 'A1', 'odds_min': 200, 'odds_max': 300, 'bet': 300},
        {'name': 'C-B1-150-200倍', 'confidence': 'C', 'c1_rank': 'B1', 'odds_min': 150, 'odds_max': 200, 'bet': 300},
    ],
    'Tier2': [
        {'name': 'D-A2-30-40倍', 'confidence': 'D', 'c1_rank': 'A2', 'odds_min': 30, 'odds_max': 40, 'bet': 300},
        {'name': 'D-A1-40-50倍', 'confidence': 'D', 'c1_rank': 'A1', 'odds_min': 40, 'odds_max': 50, 'bet': 300},
        {'name': 'D-A1-20-25倍', 'confidence': 'D', 'c1_rank': 'A1', 'odds_min': 20, 'odds_max': 25, 'bet': 300},
    ],
    'Tier3': [
        {'name': 'D-B1-5-10倍', 'confidence': 'D', 'c1_rank': 'B1', 'odds_min': 5, 'odds_max': 10, 'bet': 300},
    ],
}


def simulate_period(cursor, start_date, end_date):
    """指定期間のシミュレーション"""

    # 期間のレース取得
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= ? AND r.race_date <= ?
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''', (start_date, end_date))
    races = cursor.fetchall()

    print(f"対象期間: {start_date} ~ {end_date}")
    print(f"対象レース数: {len(races)}")
    print()

    # 日別・条件別の結果を記録
    daily_results = defaultdict(lambda: {'bet': 0, 'payout': 0, 'hit': 0, 'count': 0})
    condition_results = defaultdict(lambda: {'bet': 0, 'payout': 0, 'hit': 0, 'count': 0})
    purchases = []  # 購入明細

    for race in races:
        race_id = race['race_id']
        race_date = race['race_date']
        venue_code = race['venue_code']
        race_number = race['race_number']

        # 1コース級別取得
        cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
        c1 = cursor.fetchone()
        c1_rank = c1['racer_rank'] if c1 else 'B1'

        # 予測情報取得
        cursor.execute('''
            SELECT pit_number, confidence
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'advance'
            ORDER BY rank_prediction
        ''', (race_id,))
        preds = cursor.fetchall()

        if len(preds) < 3:
            continue

        confidence = preds[0]['confidence']
        pred_combo = f"{preds[0]['pit_number']}-{preds[1]['pit_number']}-{preds[2]['pit_number']}"

        # オッズ取得
        cursor.execute('SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?', (race_id, pred_combo))
        odds_row = cursor.fetchone()
        odds = odds_row['odds'] if odds_row else 0

        # 実結果取得
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        results = cursor.fetchall()

        if len(results) < 3:
            continue

        actual_combo = f"{results[0]['pit_number']}-{results[1]['pit_number']}-{results[2]['pit_number']}"

        # 各Tierの条件をチェック
        for tier_name, conditions in STRATEGY_A_CONDITIONS.items():
            for cond in conditions:
                if (confidence == cond['confidence'] and
                    c1_rank == cond['c1_rank'] and
                    cond['odds_min'] <= odds < cond['odds_max']):

                    bet_amount = cond['bet']
                    is_hit = (pred_combo == actual_combo)

                    # 払戻金取得
                    payout = 0
                    if is_hit:
                        cursor.execute('''
                            SELECT amount FROM payouts
                            WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                        ''', (race_id, actual_combo))
                        payout_row = cursor.fetchone()
                        if payout_row:
                            payout = (bet_amount / 100) * payout_row['amount']

                    # 記録
                    key = f"{tier_name}-{cond['name']}"
                    daily_results[race_date]['bet'] += bet_amount
                    daily_results[race_date]['payout'] += payout
                    daily_results[race_date]['hit'] += 1 if is_hit else 0
                    daily_results[race_date]['count'] += 1

                    condition_results[key]['bet'] += bet_amount
                    condition_results[key]['payout'] += payout
                    condition_results[key]['hit'] += 1 if is_hit else 0
                    condition_results[key]['count'] += 1

                    purchases.append({
                        'date': race_date,
                        'venue': venue_code,
                        'race': race_number,
                        'combo': pred_combo,
                        'odds': odds,
                        'bet': bet_amount,
                        'hit': is_hit,
                        'payout': payout,
                        'tier': tier_name,
                        'condition': cond['name'],
                    })

    return daily_results, condition_results, purchases


def print_results(daily_results, condition_results, purchases):
    """結果を表示"""

    # 日別結果
    print("=" * 80)
    print("【日別結果】")
    print("=" * 80)
    print(f"{'日付':<12} {'購入数':>6} {'的中':>4} {'投資':>8} {'払戻':>10} {'収支':>10} {'ROI':>8}")
    print("-" * 80)

    total_bet = 0
    total_payout = 0
    total_hit = 0
    total_count = 0

    for date in sorted(daily_results.keys()):
        d = daily_results[date]
        profit = d['payout'] - d['bet']
        roi = (d['payout'] / d['bet'] * 100) if d['bet'] > 0 else 0

        print(f"{date:<12} {d['count']:>6} {d['hit']:>4} {d['bet']:>7,}円 {d['payout']:>9,.0f}円 {profit:>+9,.0f}円 {roi:>7.1f}%")

        total_bet += d['bet']
        total_payout += d['payout']
        total_hit += d['hit']
        total_count += d['count']

    print("-" * 80)
    total_profit = total_payout - total_bet
    total_roi = (total_payout / total_bet * 100) if total_bet > 0 else 0
    print(f"{'合計':<12} {total_count:>6} {total_hit:>4} {total_bet:>7,}円 {total_payout:>9,.0f}円 {total_profit:>+9,.0f}円 {total_roi:>7.1f}%")
    print()

    # 条件別結果
    print("=" * 80)
    print("【条件別結果】")
    print("=" * 80)
    print(f"{'条件':<25} {'購入':>5} {'的中':>4} {'投資':>8} {'払戻':>10} {'収支':>10} {'ROI':>8}")
    print("-" * 80)

    for key in sorted(condition_results.keys()):
        d = condition_results[key]
        if d['count'] > 0:
            profit = d['payout'] - d['bet']
            roi = (d['payout'] / d['bet'] * 100) if d['bet'] > 0 else 0
            print(f"{key:<25} {d['count']:>5} {d['hit']:>4} {d['bet']:>7,}円 {d['payout']:>9,.0f}円 {profit:>+9,.0f}円 {roi:>7.1f}%")

    print()

    # 的中明細
    hits = [p for p in purchases if p['hit']]
    if hits:
        print("=" * 80)
        print("【的中明細】")
        print("=" * 80)
        for h in hits:
            print(f"  {h['date']} {h['venue']}場{h['race']:>2}R: {h['combo']} ({h['odds']:.1f}倍) -> 払戻 {h['payout']:,.0f}円")

    print()
    print("=" * 80)
    print("【サマリー】")
    print("=" * 80)
    print(f"購入レース数: {total_count}")
    print(f"的中レース数: {total_hit}")
    print(f"的中率: {(total_hit / total_count * 100) if total_count > 0 else 0:.1f}%")
    print(f"総投資額: {total_bet:,}円")
    print(f"総払戻額: {total_payout:,.0f}円")
    print(f"総収支: {total_profit:+,.0f}円")
    print(f"ROI: {total_roi:.1f}%")


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=" * 80)
    print("12月購入シミュレーション（戦略A）")
    print("=" * 80)
    print()

    # 12月1日から今日まで
    start_date = "2025-12-01"
    end_date = datetime.now().strftime("%Y-%m-%d")

    daily_results, condition_results, purchases = simulate_period(cursor, start_date, end_date)
    print_results(daily_results, condition_results, purchases)

    conn.close()


if __name__ == '__main__':
    main()
