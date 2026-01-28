#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""1月14日の予想結果を集計"""
import sqlite3
from pathlib import Path

db_path = Path('data/boatrace.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print('=' * 80)
print('1月14日の予想結果集計')
print('=' * 80)

# 1月14日の全レースIDを取得
cursor.execute("SELECT id FROM races WHERE race_date = '2026-01-14'")
jan14_race_ids = [row[0] for row in cursor.fetchall()]

def calculate_results(prediction_type):
    """予想タイプ別に結果を集計"""
    total_races = 0
    hit_count = 0
    total_return = 0
    hit_odds_list = []

    for race_id in jan14_race_ids:
        # 予想を取得（1-2-3着）
        cursor.execute('''
            SELECT pit_number FROM race_predictions
            WHERE race_id = ? AND prediction_type = ?
            ORDER BY rank_prediction
            LIMIT 3
        ''', (race_id, prediction_type))
        pred_rows = cursor.fetchall()
        if len(pred_rows) != 3:
            continue
        pred_combo = '-'.join([str(r[0]) for r in pred_rows])

        # 結果を取得
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0
            ORDER BY CAST(rank AS INTEGER)
            LIMIT 3
        ''', (race_id,))
        result_rows = cursor.fetchall()
        if len(result_rows) != 3:
            continue
        result_combo = '-'.join([str(r[0]) for r in result_rows])

        # オッズを取得
        cursor.execute('''
            SELECT odds FROM trifecta_odds
            WHERE race_id = ? AND combination = ?
        ''', (race_id, pred_combo))
        odds_row = cursor.fetchone()
        if not odds_row:
            continue
        odds = odds_row[0]

        total_races += 1

        # 的中判定
        if pred_combo == result_combo:
            hit_count += 1
            payout = odds * 100  # 100円購入
            total_return += (payout - 300)
            hit_odds_list.append(odds)
        else:
            total_return -= 300

    return {
        'total': total_races,
        'hits': hit_count,
        'returns': total_return,
        'hit_rate': (hit_count / total_races * 100) if total_races > 0 else 0,
        'roi': (total_return / (total_races * 300) * 100) if total_races > 0 else 0,
        'avg_odds': sum(hit_odds_list) / len(hit_odds_list) if hit_odds_list else 0,
        'min_odds': min(hit_odds_list) if hit_odds_list else 0,
        'max_odds': max(hit_odds_list) if hit_odds_list else 0
    }

# 事前予想
advance_results = calculate_results('advance')
print('\n【事前予想（advance）】')
print(f'予想レース数: {advance_results["total"]}')
print(f'的中数: {advance_results["hits"]}')
print(f'的中率: {advance_results["hit_rate"]:.2f}%')
if advance_results["avg_odds"] > 0:
    print(f'平均的中オッズ: {advance_results["avg_odds"]:.1f}倍')
    print(f'最小的中オッズ: {advance_results["min_odds"]:.1f}倍')
    print(f'最大的中オッズ: {advance_results["max_odds"]:.1f}倍')
print(f'収支: {advance_results["returns"]:,.0f}円')
print(f'ROI: {advance_results["roi"]:.1f}%')
status = '○黒字' if advance_results["returns"] > 0 else '×赤字'
print(f'判定: {status}')

# 直前予想
before_results = calculate_results('before')
print('\n【直前予想（before）】')
print(f'予想レース数: {before_results["total"]}')
print(f'的中数: {before_results["hits"]}')
print(f'的中率: {before_results["hit_rate"]:.2f}%')
if before_results["avg_odds"] > 0:
    print(f'平均的中オッズ: {before_results["avg_odds"]:.1f}倍')
    print(f'最小的中オッズ: {before_results["min_odds"]:.1f}倍')
    print(f'最大的中オッズ: {before_results["max_odds"]:.1f}倍')
print(f'収支: {before_results["returns"]:,.0f}円')
print(f'ROI: {before_results["roi"]:.1f}%')
status = '○黒字' if before_results["returns"] > 0 else '×赤字'
print(f'判定: {status}')

print('\n' + '=' * 80)
print('【まとめ】')
print('=' * 80)
print('■ 1月のデータ状況:')
print('  - 1月1日～13日: 結果データのみ（オッズなし）')
print('  - 1月14日: 結果・オッズ・予想すべて揃っている → 分析完了')
print('  - 1月15日～21日: 結果データなし（予想のみ）')
print('')
print('■ 完全なデータが揃っているのは1月14日のみ')
print('  その他の日は、オッズまたは結果が欠損しており、収支計算不可')
print('=' * 80)

conn.close()
