#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
収益集中リスク分析
"""
import sqlite3
import sys
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import os
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()

print('=' * 80)
print('収益集中リスク分析')
print('=' * 80)
print()

# 全ての的中データを取得して条件ごとに集計
cursor.execute("""
SELECT
    r.id,
    r.race_date,
    r.venue_code,
    rp.confidence,
    e1.racer_rank,
    o.odds,
    rp1.pit_number,
    e1.second_rate,
    CAST(strftime('%m', r.race_date) AS INTEGER) as month
FROM races r
JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
JOIN trifecta_odds o ON r.id = o.race_id
    AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
JOIN results res1 ON r.id = res1.race_id AND res1.rank = '1'
JOIN results res2 ON r.id = res2.race_id AND res2.rank = '2'
JOIN results res3 ON r.id = res3.race_id AND res3.rank = '3'
WHERE rp.rank_prediction = 1
AND r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
AND res1.pit_number = rp1.pit_number
AND res2.pit_number = rp2.pit_number
AND res3.pit_number = rp3.pit_number
""")

# 条件に該当するか判定
conditions = [
    {'name': 'A-A1-10-12', 'confidence': 'A', 'c1_rank': ['A1'], 'odds_min': 10, 'odds_max': 12, 'venue_filter': ['10', '14', '21', '18', '08', '19', '12']},
    {'name': 'B-50-100-冬除外', 'confidence': 'B', 'c1_rank': ['A1', 'B1'], 'odds_min': 50, 'odds_max': 100, 'month_exclude': [12, 1, 2]},
    {'name': 'B-30-50-B1-会場', 'confidence': 'B', 'c1_rank': ['B1'], 'odds_min': 30, 'odds_max': 50, 'venue_filter': ['10', '06', '16', '21', '09', '13', '20', '24', '07', '08']},
    {'name': 'B-10-30-穴源-会場', 'confidence': 'B', 'c1_rank': ['A1', 'A2', 'B1'], 'odds_min': 10, 'odds_max': 30, 'venue_filter': ['06', '07', '08', '10', '15', '19']},
    {'name': 'C-20-30-B1-会場', 'confidence': 'C', 'c1_rank': ['B1'], 'odds_min': 20, 'odds_max': 30, 'venue_filter': ['23', '18', '05', '04', '09', '15', '08', '24', '20', '17']},
    {'name': '鳴門-C-A2-30-80', 'confidence': 'C', 'c1_rank': ['A2'], 'odds_min': 30, 'odds_max': 80, 'venue_filter': ['14']},
    {'name': '唐津-C-B1-20-30', 'confidence': 'C', 'c1_rank': ['B1'], 'odds_min': 20, 'odds_max': 30, 'venue_filter': ['23']},
    {'name': '児島-C-B1-30-50', 'confidence': 'C', 'c1_rank': ['B1'], 'odds_min': 30, 'odds_max': 50, 'venue_filter': ['16']},
    {'name': 'D-40-50-B1-2連率', 'confidence': 'D', 'c1_rank': ['B1'], 'odds_min': 40, 'odds_max': 50, 'c1_second_rate_min': 20, 'c1_second_rate_max': 30},
    {'name': 'D-5コース予測', 'confidence': 'D', 'c1_rank': ['A1', 'A2', 'B1', 'B2'], 'odds_min': 10, 'odds_max': 200, 'predicted_course': 5},
]

hit_data = {c['name']: [] for c in conditions}
race_conditions = {}  # race_id -> [conditions]

for row in cursor.fetchall():
    race_id, race_date, venue, conf, c1_rank, odds, pred_course, second_rate, month = row
    for cond in conditions:
        # 信頼度チェック
        if conf != cond['confidence']:
            continue
        # 級別チェック
        if c1_rank not in cond['c1_rank']:
            continue
        # オッズチェック
        if not (cond['odds_min'] <= odds < cond['odds_max']):
            continue
        # 会場チェック
        if 'venue_filter' in cond and cond['venue_filter']:
            if venue not in cond['venue_filter']:
                continue
        # 月除外チェック
        if 'month_exclude' in cond and month in cond['month_exclude']:
            continue
        # 2連率チェック
        if 'c1_second_rate_min' in cond and second_rate is not None:
            if second_rate < cond['c1_second_rate_min'] or second_rate >= cond.get('c1_second_rate_max', 999):
                continue
        # 予測コースチェック
        if 'predicted_course' in cond and pred_course != cond['predicted_course']:
            continue

        hit_data[cond['name']].append({
            'race_id': race_id,
            'race_date': race_date,
            'odds': odds,
            'payout': odds * 100
        })

        if race_id not in race_conditions:
            race_conditions[race_id] = []
        race_conditions[race_id].append(cond['name'])

print('[1. 条件別の的中回数と払戻分布]')
print('-' * 60)
for cond in conditions:
    name = cond['name']
    hits = hit_data[name]
    if hits:
        total_payout = sum(h['payout'] for h in hits)
        max_payout = max(h['payout'] for h in hits)
        avg_payout = total_payout / len(hits)
        print(f'{name}:')
        print(f'  的中数: {len(hits)}件, 総払戻: {total_payout:,.0f}円')
        print(f'  最高: {max_payout:,.0f}円, 平均: {avg_payout:,.0f}円')
    else:
        print(f'{name}: 的中なし')
print()

print('[2. 重複的中の分析]')
print('-' * 60)
overlap_hits = {k: v for k, v in race_conditions.items() if len(v) >= 2}
print(f'重複的中レース数: {len(overlap_hits)}件')
print()

if overlap_hits:
    print('重複的中の詳細:')
    for race_id, conds in sorted(overlap_hits.items(), key=lambda x: len(x[1]), reverse=True)[:10]:
        # 該当レースの払戻を取得
        for cond_name in conds:
            hits = [h for h in hit_data[cond_name] if h['race_id'] == race_id]
            if hits:
                h = hits[0]
                print(f'  race_id={race_id}: {h["race_date"]} オッズ{h["odds"]:.1f}倍 払戻{h["payout"]:,.0f}円')
                print(f'    該当条件: {", ".join(conds)}')
                break
print()

print('[3. 収益上位レースの集中度]')
print('-' * 60)
# 全的中を払戻順でソート
all_hits = []
for name, hits in hit_data.items():
    for h in hits:
        all_hits.append({'name': name, **h})

all_hits_sorted = sorted(all_hits, key=lambda x: x['payout'], reverse=True)
total_payout_all = sum(h['payout'] for h in all_hits_sorted)

print(f'総払戻額: {total_payout_all:,.0f}円')
print()

# 上位10件
print('払戻上位10件:')
top10_payout = 0
for i, h in enumerate(all_hits_sorted[:10], 1):
    top10_payout += h['payout']
    print(f'  {i}. {h["race_date"]} {h["name"]}: オッズ{h["odds"]:.1f}倍 → {h["payout"]:,.0f}円')

print()
print(f'上位10件の合計: {top10_payout:,.0f}円（全体の{100.0*top10_payout/total_payout_all:.1f}%）')

# 上位20件
top20_payout = sum(h['payout'] for h in all_hits_sorted[:20])
print(f'上位20件の合計: {top20_payout:,.0f}円（全体の{100.0*top20_payout/total_payout_all:.1f}%）')

conn.close()
