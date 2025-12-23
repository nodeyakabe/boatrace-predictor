# -*- coding: utf-8 -*-
"""
最適化戦略v2 バックテスト

厳選条件のみに絞った安定性重視の戦略
- 月間安定性の高い条件のみを採用
- 回収率と的中率のバランスを重視
"""

import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import DATABASE_PATH


def run_monthly_backtest_v2(year: int, month: int, strategy: str = 'strict'):
    """最適化v2バックテスト"""

    start_date = f'{year}-{month:02d}-01'
    if month == 12:
        end_date = f'{year}-12-31'
    else:
        end_date = f'{year}-{month+1:02d}-01'

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    query = """
    SELECT
        r.id as race_id,
        r.race_date,
        rp.confidence,
        rp.prediction_type,
        e.racer_rank as c1_rank,
        GROUP_CONCAT(rp.pit_number || ':' || rp.rank_prediction, '|') as predictions
    FROM races r
    JOIN race_predictions rp ON r.id = rp.race_id
    JOIN entries e ON r.id = e.race_id AND e.pit_number = 1
    WHERE r.race_date >= ? AND r.race_date < ?
      AND rp.rank_prediction <= 6
    GROUP BY r.id, rp.prediction_type
    """

    cursor.execute(query, (start_date, end_date))
    rows = cursor.fetchall()

    results_query = """
    SELECT race_id, pit_number, rank
    FROM results
    WHERE rank IN ('1', '2', '3')
    """
    cursor.execute(results_query)
    results_rows = cursor.fetchall()

    race_results_map = {}
    for race_id, pit_number, rank in results_rows:
        if race_id not in race_results_map:
            race_results_map[race_id] = {}
        race_results_map[race_id][rank] = pit_number

    if not rows:
        conn.close()
        return None

    races = {}
    for row in rows:
        race_id, race_date, confidence, pred_type, c1_rank, predictions = row

        result_data = race_results_map.get(race_id, {})
        first = result_data.get('1')
        second = result_data.get('2')
        third = result_data.get('3')

        if race_id not in races:
            races[race_id] = {
                'race_date': race_date,
                'c1_rank': c1_rank,
                'result': f"{first}-{second}-{third}" if first and second and third else None,
                'initial': None,
                'before': None,
            }

        pred_list = []
        for p in predictions.split('|'):
            parts = p.split(':')
            if len(parts) == 2:
                pred_list.append({'pit': int(parts[0]), 'rank': int(parts[1])})
        pred_list.sort(key=lambda x: x['rank'])

        combo = f"{pred_list[0]['pit']}-{pred_list[1]['pit']}-{pred_list[2]['pit']}" if len(pred_list) >= 3 else None

        if pred_type == 'before':
            races[race_id]['before'] = {'confidence': confidence, 'combo': combo}
        else:
            races[race_id]['initial'] = {'confidence': confidence, 'combo': combo}

    race_ids = list(races.keys())
    if race_ids:
        placeholders = ','.join('?' * len(race_ids))
        cursor.execute(f"""
            SELECT race_id, combination, odds
            FROM trifecta_odds
            WHERE race_id IN ({placeholders})
        """, race_ids)

        odds_data = {}
        for race_id, combo, odds in cursor.fetchall():
            if race_id not in odds_data:
                odds_data[race_id] = {}
            odds_data[race_id][combo] = odds
    else:
        odds_data = {}

    conn.close()

    # 条件別結果
    condition_results = defaultdict(lambda: {'bet': 0, 'win': 0, 'hits': 0, 'count': 0})
    total_bet = 0
    total_win = 0
    total_hits = 0
    total_count = 0

    for race_id, race in races.items():
        if not race['result']:
            continue

        pred = race['before'] if race['before'] else race['initial']
        if not pred or not pred['combo']:
            continue

        confidence = pred['confidence']
        c1_rank = race['c1_rank']
        combo = pred['combo']
        actual_result = race['result']
        race_odds = odds_data.get(race_id, {})
        odds = race_odds.get(combo, 0)
        actual_odds = race_odds.get(actual_result, 0)

        if odds == 0:
            continue

        is_hit = (combo == actual_result)
        bet_amount = 0
        condition_key = None

        # ============================================================
        # 戦略選択
        # ============================================================
        if strategy == 'strict':
            # 最も厳選された条件のみ（月間安定性重視）
            if confidence == 'C' and 30 <= odds < 60 and c1_rank == 'A1':
                bet_amount = 500
                condition_key = 'C_30-60_A1'
            elif confidence == 'D' and 25 <= odds < 50 and c1_rank == 'A1':
                bet_amount = 300
                condition_key = 'D_25-50_A1'

        elif strategy == 'moderate':
            # 中程度の厳選（回収率重視）
            if confidence == 'C':
                if 30 <= odds < 60 and c1_rank == 'A1':
                    bet_amount = 500
                    condition_key = 'C_30-60_A1'
                elif 20 <= odds < 40 and c1_rank == 'A1':
                    bet_amount = 400
                    condition_key = 'C_20-40_A1'
            elif confidence == 'D':
                if 25 <= odds < 50 and c1_rank == 'A1':
                    bet_amount = 300
                    condition_key = 'D_25-50_A1'
                elif 20 <= odds < 50 and c1_rank == 'A1':
                    bet_amount = 300
                    condition_key = 'D_20-50_A1'

        elif strategy == 'balanced':
            # バランス型（安定性と回収率のバランス）
            if confidence == 'C':
                if 30 <= odds < 60 and c1_rank == 'A1':
                    bet_amount = 500
                    condition_key = 'C_30-60_A1'
                elif 20 <= odds < 40 and c1_rank == 'A1':
                    bet_amount = 400
                    condition_key = 'C_20-40_A1'
                elif odds >= 50 and c1_rank in ['A1', 'A2']:
                    bet_amount = 300
                    condition_key = 'C_50+_A'
            elif confidence == 'D':
                if 25 <= odds < 50 and c1_rank == 'A1':
                    bet_amount = 300
                    condition_key = 'D_25-50_A1'
                elif odds >= 30 and c1_rank in ['A1', 'A2']:
                    bet_amount = 200
                    condition_key = 'D_30+_A'

        if bet_amount > 0 and condition_key:
            total_bet += bet_amount
            total_count += 1
            condition_results[condition_key]['bet'] += bet_amount
            condition_results[condition_key]['count'] += 1
            if is_hit:
                total_hits += 1
                total_win += actual_odds * bet_amount
                condition_results[condition_key]['hits'] += 1
                condition_results[condition_key]['win'] += actual_odds * bet_amount

    if total_bet == 0:
        return None

    hit_rate = total_hits / total_count * 100 if total_count > 0 else 0
    roi = total_win / total_bet * 100
    profit = total_win - total_bet

    return {
        'month': month,
        'count': total_count,
        'hits': total_hits,
        'hit_rate': hit_rate,
        'bet': total_bet,
        'win': total_win,
        'profit': profit,
        'roi': roi,
        'conditions': dict(condition_results),
    }


def compare_strategies():
    """戦略比較"""
    print("=" * 120)
    print("最適化戦略v2 - 戦略比較分析")
    print("=" * 120)
    print()

    strategies = ['strict', 'moderate', 'balanced']
    year = 2025

    for strategy in strategies:
        print(f"\n{'='*40} 戦略: {strategy.upper()} {'='*40}")
        print()

        monthly_results = []
        for month in range(1, 12):
            result = run_monthly_backtest_v2(year, month, strategy)
            if result:
                monthly_results.append(result)

        if not monthly_results:
            print("データなし")
            continue

        print(f"{'月':>4} {'レース数':>8} {'的中':>6} {'的中率':>8} {'投資額':>12} {'回収額':>12} {'収支':>12} {'回収率':>8}")
        print("-" * 90)

        total_bet = 0
        total_win = 0
        total_hits = 0
        total_count = 0
        positive_months = 0

        for r in monthly_results:
            status = "[+]" if r['profit'] >= 0 else "[-]"
            print(f"{r['month']:>3}月 {r['count']:>8} {r['hits']:>6} {r['hit_rate']:>7.1f}% {r['bet']:>11,}円 {r['win']:>11,.0f}円 {r['profit']:>+11,.0f}円 {r['roi']:>7.1f}% {status}")

            total_bet += r['bet']
            total_win += r['win']
            total_hits += r['hits']
            total_count += r['count']
            if r['profit'] >= 0:
                positive_months += 1

        print("-" * 90)

        if total_bet > 0:
            total_hit_rate = total_hits / total_count * 100
            total_roi = total_win / total_bet * 100
            total_profit = total_win - total_bet

            print(f"{'合計':>4} {total_count:>8} {total_hits:>6} {total_hit_rate:>7.1f}% {total_bet:>11,}円 {total_win:>11,.0f}円 {total_profit:>+11,.0f}円 {total_roi:>7.1f}%")
            print()
            print(f"  黒字月: {positive_months}/{len(monthly_results)}ヶ月 ({positive_months/len(monthly_results)*100:.1f}%)")
            print(f"  年間収支: {total_profit:+,.0f}円")
            print(f"  年間回収率: {total_roi:.1f}%")


if __name__ == "__main__":
    compare_strategies()
