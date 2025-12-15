#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
信頼度別の的中率分析

予測タイプ: before（直前情報あり）
対象期間: 2025年全期間
"""
import sqlite3
from pathlib import Path
from collections import defaultdict

db_path = Path('data/boatrace.db')
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("=" * 100)
print("信頼度別 的中率分析（2025年全期間）")
print("=" * 100)
print("予測タイプ: before（直前情報あり）")
print("対象期間: 2025-01-01 ~ 2025-12-31")
print()

# 2025年全期間のレースを取得
cursor.execute("""
    SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
    FROM races r
    WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
    ORDER BY r.race_date, r.venue_code, r.race_number
""")
races = cursor.fetchall()

stats = {
    'A': {'total': 0, 'hit_1st': 0, 'hit_2nd': 0, 'hit_3rd': 0, 'hit_trifecta': 0},
    'B': {'total': 0, 'hit_1st': 0, 'hit_2nd': 0, 'hit_3rd': 0, 'hit_trifecta': 0},
    'C': {'total': 0, 'hit_1st': 0, 'hit_2nd': 0, 'hit_3rd': 0, 'hit_trifecta': 0},
    'D': {'total': 0, 'hit_1st': 0, 'hit_2nd': 0, 'hit_3rd': 0, 'hit_trifecta': 0},
    'E': {'total': 0, 'hit_1st': 0, 'hit_2nd': 0, 'hit_3rd': 0, 'hit_trifecta': 0},
}

for race in races:
    race_id = race['race_id']

    # 予測情報を取得（直前情報 = before）
    cursor.execute('''
        SELECT pit_number, confidence, rank_prediction
        FROM race_predictions
        WHERE race_id = ? AND prediction_type = 'before'
        ORDER BY rank_prediction
    ''', (race_id,))
    preds = cursor.fetchall()

    if len(preds) < 6:
        continue

    confidence = preds[0]['confidence']
    if confidence not in stats:
        continue

    # 予測
    pred_1st = preds[0]['pit_number']
    pred_2nd = preds[1]['pit_number']
    pred_3rd = preds[2]['pit_number']

    stats[confidence]['total'] += 1

    # 結果を取得
    cursor.execute('''
        SELECT pit_number, rank
        FROM results
        WHERE race_id = ? AND is_invalid = 0
        ORDER BY CAST(rank AS INTEGER)
        LIMIT 3
    ''', (race_id,))
    results = cursor.fetchall()

    if len(results) < 3:
        continue

    actual_1st = results[0]['pit_number']
    actual_2nd = results[1]['pit_number']
    actual_3rd = results[2]['pit_number']

    # 的中判定
    if pred_1st == actual_1st:
        stats[confidence]['hit_1st'] += 1

    if pred_2nd == actual_2nd:
        stats[confidence]['hit_2nd'] += 1

    if pred_3rd == actual_3rd:
        stats[confidence]['hit_3rd'] += 1

    if (pred_1st == actual_1st and pred_2nd == actual_2nd and pred_3rd == actual_3rd):
        stats[confidence]['hit_trifecta'] += 1

# 結果表示
print("=" * 100)
print("信頼度別 的中率")
print("=" * 100)
print(f"{'信頼度':>6} {'レース数':>10} {'1着的中':>10} {'1着率':>10} {'2着的中':>10} {'2着率':>10} {'3着的中':>10} {'3着率':>10} {'3連単':>10} {'3連単率':>10}")
print("-" * 100)

total_stats = {'total': 0, 'hit_1st': 0, 'hit_2nd': 0, 'hit_3rd': 0, 'hit_trifecta': 0}

for confidence in ['A', 'B', 'C', 'D', 'E']:
    s = stats[confidence]
    if s['total'] == 0:
        continue

    total_stats['total'] += s['total']
    total_stats['hit_1st'] += s['hit_1st']
    total_stats['hit_2nd'] += s['hit_2nd']
    total_stats['hit_3rd'] += s['hit_3rd']
    total_stats['hit_trifecta'] += s['hit_trifecta']

    rate_1st = s['hit_1st'] / s['total'] * 100
    rate_2nd = s['hit_2nd'] / s['total'] * 100
    rate_3rd = s['hit_3rd'] / s['total'] * 100
    rate_trifecta = s['hit_trifecta'] / s['total'] * 100

    print(f"{confidence:>6} {s['total']:>10,} {s['hit_1st']:>10,} {rate_1st:>9.2f}% {s['hit_2nd']:>10,} {rate_2nd:>9.2f}% {s['hit_3rd']:>10,} {rate_3rd:>9.2f}% {s['hit_trifecta']:>10,} {rate_trifecta:>9.2f}%")

print("-" * 100)
# 合計
if total_stats['total'] > 0:
    rate_1st_total = total_stats['hit_1st'] / total_stats['total'] * 100
    rate_2nd_total = total_stats['hit_2nd'] / total_stats['total'] * 100
    rate_3rd_total = total_stats['hit_3rd'] / total_stats['total'] * 100
    rate_trifecta_total = total_stats['hit_trifecta'] / total_stats['total'] * 100

    print(f"{'合計':>6} {total_stats['total']:>10,} {total_stats['hit_1st']:>10,} {rate_1st_total:>9.2f}% {total_stats['hit_2nd']:>10,} {rate_2nd_total:>9.2f}% {total_stats['hit_3rd']:>10,} {rate_3rd_total:>9.2f}% {total_stats['hit_trifecta']:>10,} {rate_trifecta_total:>9.2f}%")

print()
print("=" * 100)
print("信頼度別 詳細分析")
print("=" * 100)

for confidence in ['A', 'B', 'C', 'D', 'E']:
    s = stats[confidence]
    if s['total'] == 0:
        continue

    print(f"\n【信頼度{confidence}】")
    print(f"  総レース数: {s['total']:,}")
    print(f"  1着的中: {s['hit_1st']:,}回 ({s['hit_1st']/s['total']*100:.2f}%)")
    print(f"  2着的中: {s['hit_2nd']:,}回 ({s['hit_2nd']/s['total']*100:.2f}%)")
    print(f"  3着的中: {s['hit_3rd']:,}回 ({s['hit_3rd']/s['total']*100:.2f}%)")
    print(f"  3連単的中: {s['hit_trifecta']:,}回 ({s['hit_trifecta']/s['total']*100:.2f}%)")

    # 1着が当たった時の2着・3着的中率
    if s['hit_1st'] > 0:
        # 1着が当たったレースのみを抽出して2着・3着の的中率を計算
        cursor.execute('''
            SELECT COUNT(*) as count
            FROM race_predictions rp1
            INNER JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id AND rp2.rank_prediction = 2
            INNER JOIN results res1 ON rp1.race_id = res1.race_id AND res1.rank = '1'
            INNER JOIN results res2 ON rp1.race_id = res2.race_id AND res2.rank = '2'
            INNER JOIN races r ON rp1.race_id = r.id
            WHERE rp1.prediction_type = 'before'
              AND rp1.rank_prediction = 1
              AND rp1.confidence = ?
              AND rp1.pit_number = res1.pit_number
              AND rp2.pit_number = res2.pit_number
              AND r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        ''', (confidence,))
        hit_2nd_when_1st = cursor.fetchone()['count']

        cursor.execute('''
            SELECT COUNT(*) as count
            FROM race_predictions rp1
            INNER JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id AND rp3.rank_prediction = 3
            INNER JOIN results res1 ON rp1.race_id = res1.race_id AND res1.rank = '1'
            INNER JOIN results res3 ON rp1.race_id = res3.race_id AND res3.rank = '3'
            INNER JOIN races r ON rp1.race_id = r.id
            WHERE rp1.prediction_type = 'before'
              AND rp1.rank_prediction = 1
              AND rp1.confidence = ?
              AND rp1.pit_number = res1.pit_number
              AND rp3.pit_number = res3.pit_number
              AND r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        ''', (confidence,))
        hit_3rd_when_1st = cursor.fetchone()['count']

        print(f"  【1着的中時】")
        print(f"    2着も的中: {hit_2nd_when_1st:,}回 ({hit_2nd_when_1st/s['hit_1st']*100:.2f}%)")
        print(f"    3着も的中: {hit_3rd_when_1st:,}回 ({hit_3rd_when_1st/s['hit_1st']*100:.2f}%)")

conn.close()
print("\n分析完了")
