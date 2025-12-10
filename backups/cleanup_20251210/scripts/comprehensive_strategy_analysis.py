# -*- coding: utf-8 -*-
"""
包括的買い目戦略分析

年間データを多角的に分析し、安定した収益を得られる戦略を探索する
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import json

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import DATABASE_PATH


def run_comprehensive_analysis():
    """包括的な戦略分析を実行"""

    print("=" * 100)
    print("包括的買い目戦略分析")
    print("=" * 100)
    print()

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 全期間のデータを取得
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
    WHERE rp.rank_prediction <= 6
    GROUP BY r.id, rp.prediction_type
    ORDER BY r.race_date, r.venue_code, r.race_number
    """
    cursor.execute(query)
    rows = cursor.fetchall()

    # 結果データを取得
    cursor.execute("""
        SELECT race_id, pit_number, rank
        FROM results
        WHERE rank IN ('1', '2', '3')
    """)
    results_rows = cursor.fetchall()

    race_results_map = {}
    for race_id, pit_number, rank in results_rows:
        if race_id not in race_results_map:
            race_results_map[race_id] = {}
        race_results_map[race_id][rank] = pit_number

    # オッズデータを取得
    cursor.execute("""
        SELECT race_id, combination, odds
        FROM trifecta_odds
    """)
    odds_rows = cursor.fetchall()

    odds_map = {}
    for race_id, combo, odds in odds_rows:
        if race_id not in odds_map:
            odds_map[race_id] = {}
        odds_map[race_id][combo] = odds

    conn.close()

    # レースデータを整理
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

    print(f"総レース数: {len(races)}")
    print(f"結果あり: {sum(1 for r in races.values() if r['result'])}")
    print(f"オッズあり: {len(odds_map)}")
    print()

    # ============================================================
    # 分析1: 信頼度 × 1コース級別 × オッズ帯の全組み合わせ分析
    # ============================================================
    print("=" * 100)
    print("【分析1】信頼度 × 1コース級別 × オッズ帯 の組み合わせ分析")
    print("=" * 100)
    print()

    # オッズ帯の定義
    odds_ranges = [
        (5, 10, "5-10倍"),
        (10, 20, "10-20倍"),
        (20, 30, "20-30倍"),
        (30, 50, "30-50倍"),
        (50, 100, "50-100倍"),
        (100, 200, "100-200倍"),
        (200, 9999, "200倍+"),
    ]

    results_matrix = defaultdict(lambda: {'count': 0, 'hits': 0, 'bet': 0, 'win': 0})

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
        race_odds = odds_map.get(race_id, {})
        odds = race_odds.get(combo, 0)
        actual_odds = race_odds.get(actual_result, 0)

        if odds == 0:
            continue

        is_hit = (combo == actual_result)

        for odds_min, odds_max, odds_label in odds_ranges:
            if odds_min <= odds < odds_max:
                key = (confidence, c1_rank, odds_label)
                results_matrix[key]['count'] += 1
                results_matrix[key]['bet'] += 100
                if is_hit:
                    results_matrix[key]['hits'] += 1
                    results_matrix[key]['win'] += actual_odds * 100
                break

    # 結果を表示（回収率順）
    sorted_results = sorted(results_matrix.items(), key=lambda x: x[1]['win'] / x[1]['bet'] * 100 if x[1]['bet'] > 0 else 0, reverse=True)

    print(f"{'信頼度':<6} {'1コース':<6} {'オッズ帯':<12} {'件数':>8} {'的中':>6} {'的中率':>8} {'投資':>12} {'回収':>12} {'収支':>12} {'回収率':>8}")
    print("-" * 110)

    profitable_conditions = []
    for key, data in sorted_results:
        if data['count'] >= 30:  # サンプル30件以上
            confidence, c1_rank, odds_label = key
            hit_rate = data['hits'] / data['count'] * 100 if data['count'] > 0 else 0
            roi = data['win'] / data['bet'] * 100 if data['bet'] > 0 else 0
            profit = data['win'] - data['bet']

            if roi >= 100:
                profitable_conditions.append({
                    'confidence': confidence,
                    'c1_rank': c1_rank,
                    'odds_range': odds_label,
                    'count': data['count'],
                    'hits': data['hits'],
                    'hit_rate': hit_rate,
                    'roi': roi,
                    'profit': profit
                })

            marker = "***" if roi >= 120 else "**" if roi >= 100 else ""
            print(f"{confidence:<6} {c1_rank:<6} {odds_label:<12} {data['count']:>8} {data['hits']:>6} {hit_rate:>7.1f}% {data['bet']:>11,}円 {data['win']:>11,.0f}円 {profit:>+11,.0f}円 {roi:>7.1f}% {marker}")

    print()
    print(f"回収率100%以上の条件: {len(profitable_conditions)}件")
    print()

    # ============================================================
    # 分析2: 月別安定性分析
    # ============================================================
    print("=" * 100)
    print("【分析2】月別安定性分析（各条件が毎月プラスかどうか）")
    print("=" * 100)
    print()

    # 有望条件の月別成績
    for cond in profitable_conditions[:10]:  # 上位10条件
        monthly_results = defaultdict(lambda: {'bet': 0, 'win': 0, 'hits': 0, 'count': 0})

        for race_id, race in races.items():
            if not race['result']:
                continue

            pred = race['before'] if race['before'] else race['initial']
            if not pred or not pred['combo']:
                continue

            confidence = pred['confidence']
            c1_rank = race['c1_rank']

            if confidence != cond['confidence'] or c1_rank != cond['c1_rank']:
                continue

            combo = pred['combo']
            actual_result = race['result']
            race_odds = odds_map.get(race_id, {})
            odds = race_odds.get(combo, 0)
            actual_odds = race_odds.get(actual_result, 0)

            if odds == 0:
                continue

            # オッズ帯チェック
            odds_label = cond['odds_range']
            odds_min, odds_max = None, None
            for om, ox, ol in odds_ranges:
                if ol == odds_label:
                    odds_min, odds_max = om, ox
                    break

            if odds_min is None or not (odds_min <= odds < odds_max):
                continue

            month = race['race_date'][:7]  # YYYY-MM
            monthly_results[month]['count'] += 1
            monthly_results[month]['bet'] += 100
            if combo == actual_result:
                monthly_results[month]['hits'] += 1
                monthly_results[month]['win'] += actual_odds * 100

        # 月別結果表示
        print(f"\n【{cond['confidence']} × {cond['c1_rank']} × {cond['odds_range']}】")
        print(f"  年間: 件数{cond['count']} / 的中{cond['hits']} / 回収率{cond['roi']:.1f}%")

        plus_months = 0
        minus_months = 0
        sorted_months = sorted(monthly_results.keys())

        for month in sorted_months:
            data = monthly_results[month]
            if data['bet'] > 0:
                roi = data['win'] / data['bet'] * 100
                profit = data['win'] - data['bet']
                if profit > 0:
                    plus_months += 1
                else:
                    minus_months += 1
                print(f"  {month}: {data['count']:>3}件 / {data['hits']:>2}的中 / 収支{profit:>+8,.0f}円 / 回収率{roi:>6.1f}%")

        stability = plus_months / (plus_months + minus_months) * 100 if (plus_months + minus_months) > 0 else 0
        print(f"  → 安定性: {plus_months}勝{minus_months}敗 ({stability:.0f}%)")

    # ============================================================
    # 分析3: 的中率と回収率のバランス分析
    # ============================================================
    print()
    print("=" * 100)
    print("【分析3】的中率と回収率のバランス分析")
    print("=" * 100)
    print()

    # 的中率が高い条件を優先的に選ぶ
    high_hitrate_conditions = []
    for key, data in results_matrix.items():
        if data['count'] >= 50:  # サンプル50件以上
            confidence, c1_rank, odds_label = key
            hit_rate = data['hits'] / data['count'] * 100 if data['count'] > 0 else 0
            roi = data['win'] / data['bet'] * 100 if data['bet'] > 0 else 0

            if hit_rate >= 3.0:  # 的中率3%以上
                high_hitrate_conditions.append({
                    'confidence': confidence,
                    'c1_rank': c1_rank,
                    'odds_range': odds_label,
                    'count': data['count'],
                    'hits': data['hits'],
                    'hit_rate': hit_rate,
                    'roi': roi,
                    'profit': data['win'] - data['bet']
                })

    # 的中率順にソート
    high_hitrate_conditions.sort(key=lambda x: x['hit_rate'], reverse=True)

    print("【的中率3%以上の条件（サンプル50件以上）】")
    print(f"{'信頼度':<6} {'1コース':<6} {'オッズ帯':<12} {'件数':>8} {'的中':>6} {'的中率':>8} {'回収率':>8} {'収支':>12}")
    print("-" * 90)

    for cond in high_hitrate_conditions:
        marker = "***" if cond['roi'] >= 120 else "**" if cond['roi'] >= 100 else ""
        print(f"{cond['confidence']:<6} {cond['c1_rank']:<6} {cond['odds_range']:<12} {cond['count']:>8} {cond['hits']:>6} {cond['hit_rate']:>7.1f}% {cond['roi']:>7.1f}% {cond['profit']:>+11,.0f}円 {marker}")

    # ============================================================
    # 分析4: 複合条件の探索
    # ============================================================
    print()
    print("=" * 100)
    print("【分析4】複合条件探索（より緩い条件での集計）")
    print("=" * 100)
    print()

    # 信頼度別 × 1コースA級以上 × オッズ20倍以上
    composite_results = defaultdict(lambda: {'count': 0, 'hits': 0, 'bet': 0, 'win': 0})

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
        race_odds = odds_map.get(race_id, {})
        odds = race_odds.get(combo, 0)
        actual_odds = race_odds.get(actual_result, 0)

        if odds == 0:
            continue

        is_hit = (combo == actual_result)

        # 1コースA級以上のみ
        is_a_rank = c1_rank in ['A1', 'A2']

        # オッズ帯別
        for odds_min in [10, 15, 20, 25, 30, 40, 50]:
            if odds >= odds_min:
                key = (confidence, 'A級' if is_a_rank else 'B級', f'{odds_min}倍+')
                composite_results[key]['count'] += 1
                composite_results[key]['bet'] += 100
                if is_hit:
                    composite_results[key]['hits'] += 1
                    composite_results[key]['win'] += actual_odds * 100

    print(f"{'信頼度':<6} {'1コース':<6} {'オッズ条件':<12} {'件数':>8} {'的中':>6} {'的中率':>8} {'回収率':>8} {'収支':>12}")
    print("-" * 90)

    sorted_composite = sorted(composite_results.items(), key=lambda x: x[1]['win'] / x[1]['bet'] * 100 if x[1]['bet'] > 0 else 0, reverse=True)

    for key, data in sorted_composite:
        if data['count'] >= 100:
            confidence, rank_label, odds_label = key
            hit_rate = data['hits'] / data['count'] * 100 if data['count'] > 0 else 0
            roi = data['win'] / data['bet'] * 100 if data['bet'] > 0 else 0
            profit = data['win'] - data['bet']

            marker = "***" if roi >= 120 else "**" if roi >= 100 else ""
            print(f"{confidence:<6} {rank_label:<6} {odds_label:<12} {data['count']:>8} {data['hits']:>6} {hit_rate:>7.1f}% {roi:>7.1f}% {profit:>+11,.0f}円 {marker}")

    # ============================================================
    # 最終提案
    # ============================================================
    print()
    print("=" * 100)
    print("【最終分析結果と推奨戦略】")
    print("=" * 100)
    print()

    # 回収率100%以上 かつ サンプル100件以上 かつ 月別安定性50%以上
    final_recommendations = []

    for key, data in results_matrix.items():
        if data['count'] >= 100 and data['bet'] > 0:
            confidence, c1_rank, odds_label = key
            roi = data['win'] / data['bet'] * 100
            hit_rate = data['hits'] / data['count'] * 100

            if roi >= 100:
                # 月別安定性を計算
                monthly = defaultdict(lambda: {'bet': 0, 'win': 0})
                for race_id, race in races.items():
                    if not race['result']:
                        continue
                    pred = race['before'] if race['before'] else race['initial']
                    if not pred or not pred['combo']:
                        continue
                    if pred['confidence'] != confidence or race['c1_rank'] != c1_rank:
                        continue

                    combo = pred['combo']
                    race_odds = odds_map.get(race_id, {})
                    odds = race_odds.get(combo, 0)

                    if odds == 0:
                        continue

                    for om, ox, ol in odds_ranges:
                        if ol == odds_label and om <= odds < ox:
                            month = race['race_date'][:7]
                            monthly[month]['bet'] += 100
                            if combo == race['result']:
                                actual_odds = race_odds.get(race['result'], 0)
                                monthly[month]['win'] += actual_odds * 100
                            break

                plus = sum(1 for m in monthly.values() if m['win'] > m['bet'])
                total = len([m for m in monthly.values() if m['bet'] > 0])
                stability = plus / total * 100 if total > 0 else 0

                final_recommendations.append({
                    'confidence': confidence,
                    'c1_rank': c1_rank,
                    'odds_range': odds_label,
                    'count': data['count'],
                    'hits': data['hits'],
                    'hit_rate': hit_rate,
                    'roi': roi,
                    'profit': data['win'] - data['bet'],
                    'stability': stability,
                    'plus_months': plus,
                    'total_months': total
                })

    # 安定性と回収率のバランスでソート
    final_recommendations.sort(key=lambda x: (x['stability'], x['roi']), reverse=True)

    print("【推奨条件】回収率100%以上 & サンプル100件以上")
    print(f"{'信頼度':<6} {'1コース':<6} {'オッズ帯':<12} {'件数':>6} {'的中率':>8} {'回収率':>8} {'安定性':>10} {'収支':>12}")
    print("-" * 90)

    for rec in final_recommendations:
        stability_str = f"{rec['plus_months']}/{rec['total_months']}月"
        print(f"{rec['confidence']:<6} {rec['c1_rank']:<6} {rec['odds_range']:<12} {rec['count']:>6} {rec['hit_rate']:>7.1f}% {rec['roi']:>7.1f}% {stability_str:>10} {rec['profit']:>+11,.0f}円")

    print()
    print("=" * 100)
    print("分析完了")
    print("=" * 100)

    return final_recommendations


if __name__ == "__main__":
    run_comprehensive_analysis()
