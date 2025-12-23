# -*- coding: utf-8 -*-
"""
複数月バックテスト - 新戦略の安定性検証

1月〜11月の11ヶ月間で戦略の安定性を検証
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import DATABASE_PATH


def run_monthly_backtest(year: int, month: int):
    """指定月のバックテストを実行"""

    # 月の開始・終了日
    start_date = f'{year}-{month:02d}-01'
    if month == 12:
        end_date = f'{year}-12-31'
    else:
        end_date = f'{year}-{month+1:02d}-01'

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # レース情報、予測を取得
    query = """
    SELECT
        r.id as race_id,
        r.race_date,
        r.venue_code,
        r.race_number,
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
    ORDER BY r.race_date, r.venue_code, r.race_number
    """

    cursor.execute(query, (start_date, end_date))
    rows = cursor.fetchall()

    # 結果データを取得
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

    # レースごとにデータを整理
    races = {}
    for row in rows:
        race_id, race_date, venue_code, race_number, confidence, pred_type, c1_rank, predictions = row

        result_data = race_results_map.get(race_id, {})
        first = result_data.get('1')
        second = result_data.get('2')
        third = result_data.get('3')

        if race_id not in races:
            races[race_id] = {
                'race_date': race_date,
                'venue_code': venue_code,
                'race_number': race_number,
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

    # オッズデータを取得
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

    # 結果集計
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

        if confidence == 'A':
            continue
        if c1_rank not in ['A1', 'A2']:
            continue
        if odds == 0:
            continue

        is_hit = (combo == actual_result)
        bet_amount = 0

        # 新戦略の条件判定
        if confidence == 'B':
            if odds >= 50 and c1_rank in ['A1', 'A2']:
                bet_amount = 200
        elif confidence == 'C':
            if 30 <= odds < 60 and c1_rank == 'A1':
                bet_amount = 500
            elif 20 <= odds < 40 and c1_rank == 'A1':
                bet_amount = 400
            elif odds >= 50 and c1_rank in ['A1', 'A2']:
                bet_amount = 400
            elif 15 <= odds < 30 and c1_rank == 'A1':
                bet_amount = 300
        elif confidence == 'D':
            if 25 <= odds < 50 and c1_rank == 'A1':
                bet_amount = 300
            elif 20 <= odds < 50 and c1_rank == 'A1':
                bet_amount = 300
            elif odds >= 30 and c1_rank in ['A1', 'A2']:
                bet_amount = 200

        if bet_amount > 0:
            total_bet += bet_amount
            total_count += 1
            if is_hit:
                total_hits += 1
                total_win += actual_odds * bet_amount

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
    }


def main():
    """メイン処理"""
    print("=" * 100)
    print("複数月バックテスト - 新戦略の安定性検証")
    print("=" * 100)
    print()

    year = 2025
    monthly_results = []

    for month in range(1, 12):  # 1月〜11月
        result = run_monthly_backtest(year, month)
        if result:
            monthly_results.append(result)

    if not monthly_results:
        print("データがありませんでした")
        return

    # 結果表示
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
    print("=" * 100)
    print("【安定性評価】")
    print("=" * 100)
    print()
    print(f"  黒字月: {positive_months}/{len(monthly_results)}ヶ月 ({positive_months/len(monthly_results)*100:.1f}%)")
    print(f"  年間レース数: {total_count}件")
    print(f"  年間的中数: {total_hits}件")
    print(f"  年間的中率: {total_hit_rate:.2f}%")
    print()
    print(f"  年間投資額: {total_bet:,}円")
    print(f"  年間回収額: {total_win:,.0f}円")
    print(f"  年間収支: {total_profit:+,.0f}円")
    print(f"  年間回収率: {total_roi:.1f}%")
    print()

    if positive_months >= len(monthly_results) * 0.5:
        print(f"  [OK] 安定性: {positive_months}/{len(monthly_results)}月が黒字 - 比較的安定")
    else:
        print(f"  [NG] 安定性: {positive_months}/{len(monthly_results)}月が黒字 - 改善が必要")


if __name__ == "__main__":
    main()
