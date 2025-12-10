# -*- coding: utf-8 -*-
"""
1. 新戦略での年間月別収支
2. 信頼度Bの活用方法分析
"""

import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import DATABASE_PATH


def get_race_data():
    """レースデータを取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 結果データ
    cursor.execute("""
        SELECT race_id, pit_number, rank
        FROM results WHERE rank IN ('1', '2', '3')
    """)
    race_results = {}
    for race_id, pit, rank in cursor.fetchall():
        if race_id not in race_results:
            race_results[race_id] = {}
        race_results[race_id][rank] = pit

    # 予測・レース情報
    cursor.execute("""
        SELECT r.id, r.race_date, r.venue_code, rp.confidence, rp.prediction_type,
               e.racer_rank as c1_rank,
               GROUP_CONCAT(rp.pit_number || ':' || rp.rank_prediction, '|') as preds
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id
        JOIN entries e ON r.id = e.race_id AND e.pit_number = 1
        WHERE r.race_date >= '2025-01-01' AND r.race_date < '2025-12-01'
          AND rp.rank_prediction <= 6
        GROUP BY r.id, rp.prediction_type
    """)
    races_raw = cursor.fetchall()

    races = {}
    for row in races_raw:
        race_id, race_date, venue, conf, pred_type, c1_rank, preds = row
        result = race_results.get(race_id, {})
        first, second, third = result.get('1'), result.get('2'), result.get('3')

        if race_id not in races:
            races[race_id] = {
                'race_date': race_date,
                'month': int(race_date.split('-')[1]),
                'c1_rank': c1_rank,
                'result': f"{first}-{second}-{third}" if first and second and third else None,
                'initial': None, 'before': None
            }

        pred_list = []
        for p in preds.split('|'):
            parts = p.split(':')
            if len(parts) == 2:
                pred_list.append({'pit': int(parts[0]), 'rank': int(parts[1])})
        pred_list.sort(key=lambda x: x['rank'])
        combo = f"{pred_list[0]['pit']}-{pred_list[1]['pit']}-{pred_list[2]['pit']}" if len(pred_list) >= 3 else None

        if pred_type == 'before':
            races[race_id]['before'] = {'confidence': conf, 'combo': combo}
        else:
            races[race_id]['initial'] = {'confidence': conf, 'combo': combo}

    # オッズ
    race_ids = list(races.keys())
    if race_ids:
        placeholders = ','.join('?' * len(race_ids))
        cursor.execute(f"""
            SELECT race_id, combination, odds FROM trifecta_odds
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
    return races, odds_data


def analyze_monthly_pnl():
    """新戦略(MODERATE)での月別収支"""
    print("=" * 100)
    print("【1】新戦略（MODERATE）での年間月別収支")
    print("=" * 100)
    print()

    races, odds_data = get_race_data()

    monthly = defaultdict(lambda: {'bet': 0, 'win': 0, 'hits': 0, 'count': 0})

    for race_id, race in races.items():
        if not race['result']:
            continue

        pred = race['before'] if race['before'] else race['initial']
        if not pred or not pred['combo']:
            continue

        conf = pred['confidence']
        c1_rank = race['c1_rank']
        combo = pred['combo']
        actual = race['result']
        odds = odds_data.get(race_id, {}).get(combo, 0)
        actual_odds = odds_data.get(race_id, {}).get(actual, 0)
        month = race['month']

        if odds == 0:
            continue

        bet_amount = 0
        # MODERATE戦略
        if conf == 'C':
            if 30 <= odds < 60 and c1_rank == 'A1':
                bet_amount = 500
            elif 20 <= odds < 40 and c1_rank == 'A1':
                bet_amount = 400
        elif conf == 'D':
            if 25 <= odds < 50 and c1_rank == 'A1':
                bet_amount = 300
            elif 20 <= odds < 50 and c1_rank == 'A1':
                bet_amount = 300

        if bet_amount > 0:
            is_hit = (combo == actual)
            monthly[month]['bet'] += bet_amount
            monthly[month]['count'] += 1
            if is_hit:
                monthly[month]['hits'] += 1
                monthly[month]['win'] += actual_odds * bet_amount

    print(f"{'月':>4} {'レース数':>8} {'的中':>6} {'的中率':>8} {'投資額':>12} {'回収額':>12} {'収支':>12} {'回収率':>8}")
    print("-" * 90)

    total_bet, total_win, total_hits, total_count = 0, 0, 0, 0
    positive_months = 0

    for month in range(1, 12):
        m = monthly[month]
        if m['bet'] == 0:
            continue
        profit = m['win'] - m['bet']
        roi = m['win'] / m['bet'] * 100
        hit_rate = m['hits'] / m['count'] * 100 if m['count'] > 0 else 0
        status = "[+]" if profit >= 0 else "[-]"

        print(f"{month:>3}月 {m['count']:>8} {m['hits']:>6} {hit_rate:>7.1f}% {m['bet']:>11,}円 {m['win']:>11,.0f}円 {profit:>+11,.0f}円 {roi:>7.1f}% {status}")

        total_bet += m['bet']
        total_win += m['win']
        total_hits += m['hits']
        total_count += m['count']
        if profit >= 0:
            positive_months += 1

    print("-" * 90)
    total_profit = total_win - total_bet
    total_roi = total_win / total_bet * 100 if total_bet > 0 else 0
    total_hit_rate = total_hits / total_count * 100 if total_count > 0 else 0

    print(f"{'合計':>4} {total_count:>8} {total_hits:>6} {total_hit_rate:>7.1f}% {total_bet:>11,}円 {total_win:>11,.0f}円 {total_profit:>+11,.0f}円 {total_roi:>7.1f}%")
    print()
    print(f"  黒字月: {positive_months}/11ヶ月 ({positive_months/11*100:.1f}%)")
    print(f"  年間収支: {total_profit:+,.0f}円")
    print(f"  年間回収率: {total_roi:.1f}%")


def analyze_confidence_b():
    """信頼度Bの詳細分析"""
    print()
    print("=" * 100)
    print("【2】信頼度Bの活用方法分析")
    print("=" * 100)
    print()

    races, odds_data = get_race_data()

    # 条件別に集計
    conditions = defaultdict(lambda: {'bet': 0, 'win': 0, 'hits': 0, 'count': 0})

    for race_id, race in races.items():
        if not race['result']:
            continue

        pred = race['before'] if race['before'] else race['initial']
        if not pred or not pred['combo']:
            continue

        conf = pred['confidence']
        if conf != 'B':
            continue

        c1_rank = race['c1_rank']
        combo = pred['combo']
        actual = race['result']
        odds = odds_data.get(race_id, {}).get(combo, 0)
        actual_odds = odds_data.get(race_id, {}).get(actual, 0)

        if odds == 0:
            continue

        is_hit = (combo == actual)

        # オッズ範囲を決定
        if odds < 10:
            odds_range = '0-10'
        elif odds < 20:
            odds_range = '10-20'
        elif odds < 30:
            odds_range = '20-30'
        elif odds < 50:
            odds_range = '30-50'
        elif odds < 100:
            odds_range = '50-100'
        else:
            odds_range = '100+'

        # 級別を決定
        if c1_rank == 'A1':
            rank_cat = 'A1'
        elif c1_rank == 'A2':
            rank_cat = 'A2'
        elif c1_rank in ['B1', 'B2']:
            rank_cat = 'B級'
        else:
            rank_cat = 'その他'

        key = f"B × {rank_cat} × {odds_range}倍"
        conditions[key]['count'] += 1
        conditions[key]['bet'] += 100  # 標準100円計算
        if is_hit:
            conditions[key]['hits'] += 1
            conditions[key]['win'] += actual_odds * 100

    print("【信頼度B: 条件別分析】")
    print()
    print(f"{'条件':<30} {'件数':>8} {'的中':>6} {'的中率':>8} {'回収率':>10}")
    print("-" * 70)

    # 回収率順にソート
    sorted_conds = sorted(conditions.items(), key=lambda x: x[1]['win']/x[1]['bet']*100 if x[1]['bet']>0 else 0, reverse=True)

    profitable_conditions = []
    for key, data in sorted_conds:
        if data['count'] < 20:  # サンプル数20以上
            continue
        roi = data['win'] / data['bet'] * 100 if data['bet'] > 0 else 0
        hit_rate = data['hits'] / data['count'] * 100 if data['count'] > 0 else 0
        status = "★" if roi >= 100 else ""

        print(f"{key:<30} {data['count']:>8} {data['hits']:>6} {hit_rate:>7.1f}% {roi:>9.1f}% {status}")

        if roi >= 100:
            profitable_conditions.append((key, data, roi, hit_rate))

    print()
    print("=" * 100)
    print("【信頼度B: 採用推奨条件】")
    print("=" * 100)
    print()

    if profitable_conditions:
        for key, data, roi, hit_rate in profitable_conditions:
            print(f"  ✓ {key}")
            print(f"    - サンプル数: {data['count']}件")
            print(f"    - 的中率: {hit_rate:.1f}%")
            print(f"    - 回収率: {roi:.1f}%")
            print()
    else:
        print("  回収率100%以上の条件は見つかりませんでした")

    # 月別安定性も確認
    print()
    print("【信頼度B: 有望条件の月別安定性】")
    print()

    # B × A1 × 高オッズの月別
    monthly_b = defaultdict(lambda: {'bet': 0, 'win': 0, 'hits': 0, 'count': 0})

    for race_id, race in races.items():
        if not race['result']:
            continue

        pred = race['before'] if race['before'] else race['initial']
        if not pred or not pred['combo']:
            continue

        conf = pred['confidence']
        if conf != 'B':
            continue

        c1_rank = race['c1_rank']
        combo = pred['combo']
        actual = race['result']
        odds = odds_data.get(race_id, {}).get(combo, 0)
        actual_odds = odds_data.get(race_id, {}).get(actual, 0)
        month = race['month']

        if odds == 0:
            continue

        # 有望条件: B × A級 × 50倍以上
        if c1_rank in ['A1', 'A2'] and odds >= 50:
            is_hit = (combo == actual)
            monthly_b[month]['bet'] += 200
            monthly_b[month]['count'] += 1
            if is_hit:
                monthly_b[month]['hits'] += 1
                monthly_b[month]['win'] += actual_odds * 200

    print("B × A級 × 50倍+ の月別:")
    print(f"{'月':>4} {'件数':>6} {'的中':>4} {'投資額':>10} {'回収額':>10} {'収支':>10} {'回収率':>8}")
    print("-" * 70)

    positive = 0
    total_b_bet, total_b_win = 0, 0
    for month in range(1, 12):
        m = monthly_b[month]
        if m['bet'] == 0:
            print(f"{month:>3}月 {0:>6} {0:>4} {0:>10}円 {0:>10}円 {0:>+10}円 {0:>7.1f}%")
            continue
        profit = m['win'] - m['bet']
        roi = m['win'] / m['bet'] * 100
        status = "[+]" if profit >= 0 else "[-]"
        print(f"{month:>3}月 {m['count']:>6} {m['hits']:>4} {m['bet']:>9,}円 {m['win']:>9,.0f}円 {profit:>+9,.0f}円 {roi:>7.1f}% {status}")
        total_b_bet += m['bet']
        total_b_win += m['win']
        if profit >= 0:
            positive += 1

    print("-" * 70)
    if total_b_bet > 0:
        print(f"合計  黒字月: {positive}/11, 年間回収率: {total_b_win/total_b_bet*100:.1f}%")


def analyze_combined_strategy():
    """MODERATE + 信頼度Bの統合戦略"""
    print()
    print("=" * 100)
    print("【3】統合戦略シミュレーション（MODERATE + 信頼度B）")
    print("=" * 100)
    print()

    races, odds_data = get_race_data()

    monthly = defaultdict(lambda: {'bet': 0, 'win': 0, 'hits': 0, 'count': 0})

    for race_id, race in races.items():
        if not race['result']:
            continue

        pred = race['before'] if race['before'] else race['initial']
        if not pred or not pred['combo']:
            continue

        conf = pred['confidence']
        c1_rank = race['c1_rank']
        combo = pred['combo']
        actual = race['result']
        odds = odds_data.get(race_id, {}).get(combo, 0)
        actual_odds = odds_data.get(race_id, {}).get(actual, 0)
        month = race['month']

        if odds == 0:
            continue

        bet_amount = 0

        # MODERATE戦略 + 信頼度B追加
        if conf == 'B':
            # B × A級 × 50倍以上
            if c1_rank in ['A1', 'A2'] and odds >= 50:
                bet_amount = 200
        elif conf == 'C':
            if 30 <= odds < 60 and c1_rank == 'A1':
                bet_amount = 500
            elif 20 <= odds < 40 and c1_rank == 'A1':
                bet_amount = 400
        elif conf == 'D':
            if 25 <= odds < 50 and c1_rank == 'A1':
                bet_amount = 300
            elif 20 <= odds < 50 and c1_rank == 'A1':
                bet_amount = 300

        if bet_amount > 0:
            is_hit = (combo == actual)
            monthly[month]['bet'] += bet_amount
            monthly[month]['count'] += 1
            if is_hit:
                monthly[month]['hits'] += 1
                monthly[month]['win'] += actual_odds * bet_amount

    print(f"{'月':>4} {'レース数':>8} {'的中':>6} {'的中率':>8} {'投資額':>12} {'回収額':>12} {'収支':>12} {'回収率':>8}")
    print("-" * 90)

    total_bet, total_win, total_hits, total_count = 0, 0, 0, 0
    positive_months = 0

    for month in range(1, 12):
        m = monthly[month]
        if m['bet'] == 0:
            continue
        profit = m['win'] - m['bet']
        roi = m['win'] / m['bet'] * 100
        hit_rate = m['hits'] / m['count'] * 100 if m['count'] > 0 else 0
        status = "[+]" if profit >= 0 else "[-]"

        print(f"{month:>3}月 {m['count']:>8} {m['hits']:>6} {hit_rate:>7.1f}% {m['bet']:>11,}円 {m['win']:>11,.0f}円 {profit:>+11,.0f}円 {roi:>7.1f}% {status}")

        total_bet += m['bet']
        total_win += m['win']
        total_hits += m['hits']
        total_count += m['count']
        if profit >= 0:
            positive_months += 1

    print("-" * 90)
    total_profit = total_win - total_bet
    total_roi = total_win / total_bet * 100 if total_bet > 0 else 0
    total_hit_rate = total_hits / total_count * 100 if total_count > 0 else 0

    print(f"{'合計':>4} {total_count:>8} {total_hits:>6} {total_hit_rate:>7.1f}% {total_bet:>11,}円 {total_win:>11,.0f}円 {total_profit:>+11,.0f}円 {total_roi:>7.1f}%")
    print()
    print(f"  黒字月: {positive_months}/11ヶ月 ({positive_months/11*100:.1f}%)")
    print(f"  年間収支: {total_profit:+,.0f}円")
    print(f"  年間回収率: {total_roi:.1f}%")


if __name__ == "__main__":
    analyze_monthly_pnl()
    analyze_confidence_b()
    analyze_combined_strategy()
