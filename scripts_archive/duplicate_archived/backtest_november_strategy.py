# -*- coding: utf-8 -*-
"""
11月バックテスト - 最終運用戦略の実証実験

総合タブの購入条件に基づいて、2025年11月1日〜30日の
1ヶ月間買い続けた場合の収支をシミュレーション
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import DATABASE_PATH


def run_november_backtest():
    """11月のバックテストを実行"""

    print("=" * 80)
    print("11月バックテスト - 最終運用戦略の実証実験")
    print("=" * 80)
    print()

    # 購入条件定義（BetTargetEvaluator 2025年12月最適化版と同じ）
    BET_CONDITIONS = {
        'B': [
            # B × 新方式 × 50+倍 × A級: 回収率121.7%
            {
                'method': '新方式',
                'odds_min': 50, 'odds_max': 9999,
                'c1_rank': ['A1', 'A2'],
                'expected_roi': 121.7,
                'bet_amount': 200,
            },
        ],
        'C': [
            # C × 従来 × 30-60倍 × A1級: 回収率127.2%
            {
                'method': '従来',
                'odds_min': 30, 'odds_max': 60,
                'c1_rank': ['A1'],
                'expected_roi': 127.2,
                'bet_amount': 500,
            },
            # C × 従来 × 20-40倍 × A1級: 回収率122.8%
            {
                'method': '従来',
                'odds_min': 20, 'odds_max': 40,
                'c1_rank': ['A1'],
                'expected_roi': 122.8,
                'bet_amount': 400,
            },
            # C × 従来 × 50+倍 × A級: 回収率121.0%
            {
                'method': '従来',
                'odds_min': 50, 'odds_max': 9999,
                'c1_rank': ['A1', 'A2'],
                'expected_roi': 121.0,
                'bet_amount': 400,
            },
            # C × 新方式 × 15-30倍 × A1級: 回収率107.5%
            {
                'method': '新方式',
                'odds_min': 15, 'odds_max': 30,
                'c1_rank': ['A1'],
                'expected_roi': 107.5,
                'bet_amount': 300,
            },
        ],
        'D': [
            # D × 新方式 × 25-50倍 × A1級: 回収率251.5%
            {
                'method': '新方式',
                'odds_min': 25, 'odds_max': 50,
                'c1_rank': ['A1'],
                'expected_roi': 251.5,
                'bet_amount': 300,
            },
            # D × 従来 × 20-50倍 × A1級: 回収率215.7%
            {
                'method': '従来',
                'odds_min': 20, 'odds_max': 50,
                'c1_rank': ['A1'],
                'expected_roi': 215.7,
                'bet_amount': 300,
            },
            # D × 新方式 × 20-40倍 × A1級: 回収率168.7%
            {
                'method': '新方式',
                'odds_min': 20, 'odds_max': 40,
                'c1_rank': ['A1'],
                'expected_roi': 168.7,
                'bet_amount': 300,
            },
            # D × 新方式 × 30+倍 × A級: 回収率209.1%
            {
                'method': '新方式',
                'odds_min': 30, 'odds_max': 9999,
                'c1_rank': ['A1', 'A2'],
                'expected_roi': 209.1,
                'bet_amount': 200,
            },
        ],
    }

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 11月のレースデータを取得
    start_date = '2025-11-01'
    end_date = '2025-11-30'

    print(f"対象期間: {start_date} 〜 {end_date}")
    print()

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
    WHERE r.race_date BETWEEN ? AND ?
      AND rp.rank_prediction <= 6
    GROUP BY r.id, rp.prediction_type
    ORDER BY r.race_date, r.venue_code, r.race_number
    """

    cursor.execute(query, (start_date, end_date))
    rows = cursor.fetchall()

    # 結果データを取得（1着〜3着）
    results_query = """
    SELECT race_id, pit_number, rank
    FROM results
    WHERE rank IN ('1', '2', '3')
    """
    cursor.execute(results_query)
    results_rows = cursor.fetchall()

    # 結果をレースごとにまとめる
    race_results_map = {}
    for race_id, pit_number, rank in results_rows:
        if race_id not in race_results_map:
            race_results_map[race_id] = {}
        race_results_map[race_id][rank] = pit_number

    if not rows:
        print("11月のデータが見つかりませんでした")
        conn.close()
        return

    # レースごとにデータを整理
    races = {}
    for row in rows:
        race_id, race_date, venue_code, race_number, confidence, pred_type, c1_rank, predictions = row

        # 結果を取得
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

        # 予測をパース
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

    # 結果集計用（新戦略）
    results = {
        # 信頼度B
        'B_50+_A_new': {'bet': 0, 'hits': 0, 'win': 0, 'races': []},
        # 信頼度C
        'C_30-60_A1_old': {'bet': 0, 'hits': 0, 'win': 0, 'races': []},
        'C_20-40_A1_old': {'bet': 0, 'hits': 0, 'win': 0, 'races': []},
        'C_50+_A_old': {'bet': 0, 'hits': 0, 'win': 0, 'races': []},
        'C_15-30_A1_new': {'bet': 0, 'hits': 0, 'win': 0, 'races': []},
        # 信頼度D
        'D_25-50_A1_new': {'bet': 0, 'hits': 0, 'win': 0, 'races': []},
        'D_20-50_A1_old': {'bet': 0, 'hits': 0, 'win': 0, 'races': []},
        'D_20-40_A1_new': {'bet': 0, 'hits': 0, 'win': 0, 'races': []},
        'D_30+_A_new': {'bet': 0, 'hits': 0, 'win': 0, 'races': []},
    }

    daily_results = defaultdict(lambda: {'bet': 0, 'win': 0, 'hits': 0, 'races': 0})

    # 各レースを評価
    total_races = 0
    skipped_no_odds = 0
    skipped_no_result = 0

    for race_id, race in races.items():
        # 結果がないレースはスキップ
        if not race['result']:
            skipped_no_result += 1
            continue

        total_races += 1

        # 直前情報があれば使う（なければ事前）
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

        # 信頼度Aは除外（Bは条件付きで採用）
        if confidence == 'A':
            continue

        # 1コースB級以下は除外
        if c1_rank not in ['A1', 'A2']:
            continue

        # オッズがない場合はスキップ
        if odds == 0:
            skipped_no_odds += 1
            continue

        is_hit = (combo == actual_result)
        matched = False

        # ============ 信頼度B の条件 ============
        if confidence == 'B':
            # B × 新方式 × 50+倍 × A級
            if odds >= 50 and c1_rank in ['A1', 'A2']:
                bet_amount = 200
                key = 'B_50+_A_new'
                results[key]['bet'] += bet_amount
                results[key]['races'].append(race_id)
                if is_hit:
                    results[key]['hits'] += 1
                    results[key]['win'] += actual_odds * bet_amount
                daily_results[race['race_date']]['bet'] += bet_amount
                daily_results[race['race_date']]['races'] += 1
                if is_hit:
                    daily_results[race['race_date']]['hits'] += 1
                    daily_results[race['race_date']]['win'] += actual_odds * bet_amount
                matched = True

        # ============ 信頼度C の条件 ============
        elif confidence == 'C':
            # C × 従来 × 30-60倍 × A1級（最優先）
            if 30 <= odds < 60 and c1_rank == 'A1':
                bet_amount = 500
                key = 'C_30-60_A1_old'
                results[key]['bet'] += bet_amount
                results[key]['races'].append(race_id)
                if is_hit:
                    results[key]['hits'] += 1
                    results[key]['win'] += actual_odds * bet_amount
                daily_results[race['race_date']]['bet'] += bet_amount
                daily_results[race['race_date']]['races'] += 1
                if is_hit:
                    daily_results[race['race_date']]['hits'] += 1
                    daily_results[race['race_date']]['win'] += actual_odds * bet_amount
                matched = True
            # C × 従来 × 20-40倍 × A1級
            elif 20 <= odds < 40 and c1_rank == 'A1':
                bet_amount = 400
                key = 'C_20-40_A1_old'
                results[key]['bet'] += bet_amount
                results[key]['races'].append(race_id)
                if is_hit:
                    results[key]['hits'] += 1
                    results[key]['win'] += actual_odds * bet_amount
                daily_results[race['race_date']]['bet'] += bet_amount
                daily_results[race['race_date']]['races'] += 1
                if is_hit:
                    daily_results[race['race_date']]['hits'] += 1
                    daily_results[race['race_date']]['win'] += actual_odds * bet_amount
                matched = True
            # C × 従来 × 50+倍 × A級
            elif odds >= 50 and c1_rank in ['A1', 'A2']:
                bet_amount = 400
                key = 'C_50+_A_old'
                results[key]['bet'] += bet_amount
                results[key]['races'].append(race_id)
                if is_hit:
                    results[key]['hits'] += 1
                    results[key]['win'] += actual_odds * bet_amount
                daily_results[race['race_date']]['bet'] += bet_amount
                daily_results[race['race_date']]['races'] += 1
                if is_hit:
                    daily_results[race['race_date']]['hits'] += 1
                    daily_results[race['race_date']]['win'] += actual_odds * bet_amount
                matched = True
            # C × 新方式 × 15-30倍 × A1級（ここでは従来方式で代用）
            elif 15 <= odds < 30 and c1_rank == 'A1':
                bet_amount = 300
                key = 'C_15-30_A1_new'
                results[key]['bet'] += bet_amount
                results[key]['races'].append(race_id)
                if is_hit:
                    results[key]['hits'] += 1
                    results[key]['win'] += actual_odds * bet_amount
                daily_results[race['race_date']]['bet'] += bet_amount
                daily_results[race['race_date']]['races'] += 1
                if is_hit:
                    daily_results[race['race_date']]['hits'] += 1
                    daily_results[race['race_date']]['win'] += actual_odds * bet_amount
                matched = True

        # ============ 信頼度D の条件 ============
        elif confidence == 'D':
            # D × 新方式 × 25-50倍 × A1級（最優先）
            if 25 <= odds < 50 and c1_rank == 'A1':
                bet_amount = 300
                key = 'D_25-50_A1_new'
                results[key]['bet'] += bet_amount
                results[key]['races'].append(race_id)
                if is_hit:
                    results[key]['hits'] += 1
                    results[key]['win'] += actual_odds * bet_amount
                daily_results[race['race_date']]['bet'] += bet_amount
                daily_results[race['race_date']]['races'] += 1
                if is_hit:
                    daily_results[race['race_date']]['hits'] += 1
                    daily_results[race['race_date']]['win'] += actual_odds * bet_amount
                matched = True
            # D × 従来 × 20-50倍 × A1級
            elif 20 <= odds < 50 and c1_rank == 'A1':
                bet_amount = 300
                key = 'D_20-50_A1_old'
                results[key]['bet'] += bet_amount
                results[key]['races'].append(race_id)
                if is_hit:
                    results[key]['hits'] += 1
                    results[key]['win'] += actual_odds * bet_amount
                daily_results[race['race_date']]['bet'] += bet_amount
                daily_results[race['race_date']]['races'] += 1
                if is_hit:
                    daily_results[race['race_date']]['hits'] += 1
                    daily_results[race['race_date']]['win'] += actual_odds * bet_amount
                matched = True
            # D × 新方式 × 30+倍 × A級
            elif odds >= 30 and c1_rank in ['A1', 'A2']:
                bet_amount = 200
                key = 'D_30+_A_new'
                results[key]['bet'] += bet_amount
                results[key]['races'].append(race_id)
                if is_hit:
                    results[key]['hits'] += 1
                    results[key]['win'] += actual_odds * bet_amount
                daily_results[race['race_date']]['bet'] += bet_amount
                daily_results[race['race_date']]['races'] += 1
                if is_hit:
                    daily_results[race['race_date']]['hits'] += 1
                    daily_results[race['race_date']]['win'] += actual_odds * bet_amount
                matched = True

    # ============ 結果表示 ============
    print(f"総レース数: {total_races}")
    print(f"オッズなしでスキップ: {skipped_no_odds}")
    print(f"結果なしでスキップ: {skipped_no_result}")
    print()

    print("=" * 80)
    print("【条件別結果】")
    print("=" * 80)
    print()
    print(f"{'条件':<20} {'レース数':>8} {'的中':>6} {'的中率':>8} {'投資額':>12} {'回収額':>12} {'収支':>12} {'回収率':>8}")
    print("-" * 100)

    total_bet = 0
    total_win = 0
    total_hits = 0
    total_count = 0

    for key, data in results.items():
        if data['bet'] > 0:
            count = len(data['races'])
            hit_rate = data['hits'] / count * 100 if count > 0 else 0
            roi = data['win'] / data['bet'] * 100 if data['bet'] > 0 else 0
            profit = data['win'] - data['bet']

            print(f"{key:<20} {count:>8} {data['hits']:>6} {hit_rate:>7.1f}% {data['bet']:>11,}円 {data['win']:>11,.0f}円 {profit:>+11,.0f}円 {roi:>7.1f}%")

            total_bet += data['bet']
            total_win += data['win']
            total_hits += data['hits']
            total_count += count

    print("-" * 100)

    if total_bet > 0:
        total_hit_rate = total_hits / total_count * 100 if total_count > 0 else 0
        total_roi = total_win / total_bet * 100
        total_profit = total_win - total_bet

        print(f"{'【合計】':<20} {total_count:>8} {total_hits:>6} {total_hit_rate:>7.1f}% {total_bet:>11,}円 {total_win:>11,.0f}円 {total_profit:>+11,.0f}円 {total_roi:>7.1f}%")

    print()
    print("=" * 80)
    print("【日別収支】")
    print("=" * 80)
    print()
    print(f"{'日付':<12} {'レース数':>8} {'的中':>6} {'投資額':>12} {'回収額':>12} {'収支':>12} {'累計収支':>12}")
    print("-" * 90)

    cumulative_profit = 0
    sorted_dates = sorted(daily_results.keys())

    for date in sorted_dates:
        data = daily_results[date]
        profit = data['win'] - data['bet']
        cumulative_profit += profit

        print(f"{date:<12} {data['races']:>8} {data['hits']:>6} {data['bet']:>11,}円 {data['win']:>11,.0f}円 {profit:>+11,.0f}円 {cumulative_profit:>+11,.0f}円")

    print("-" * 90)
    print(f"{'月間合計':<12} {total_count:>8} {total_hits:>6} {total_bet:>11,}円 {total_win:>11,.0f}円 {total_profit:>+11,.0f}円")

    print()
    print("=" * 80)
    print("【サマリー】")
    print("=" * 80)
    print()
    print(f"  購入レース数: {total_count}件")
    print(f"  的中数: {total_hits}件")
    print(f"  的中率: {total_hit_rate:.2f}%")
    print()
    print(f"  総投資額: {total_bet:,}円")
    print(f"  総回収額: {total_win:,.0f}円")
    print(f"  収支: {total_profit:+,.0f}円")
    print(f"  回収率: {total_roi:.1f}%")
    print()

    if total_profit > 0:
        print(f"  [OK] 11月は +{total_profit:,.0f}円 の利益！")
    else:
        print(f"  [NG] 11月は {abs(total_profit):,.0f}円 の損失")


if __name__ == "__main__":
    run_november_backtest()
