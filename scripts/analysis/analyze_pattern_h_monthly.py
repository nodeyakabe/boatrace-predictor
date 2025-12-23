#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
パターンH月別収支分析（2025年）

パターンH（1-2軸3点傾斜配分）の月別収支を詳細分析
"""
import sys
from pathlib import Path
import sqlite3
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus, MultiBetPattern

# データベース接続
conn = sqlite3.connect('data/boatrace.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("=" * 100)
print("パターンH 月別収支分析（2025年全期間）")
print("=" * 100)
print("パターン: 1-2軸3点傾斜配分（1-2-3:200円、1-2-4:100円、1-2-5:100円）")
print()

# 評価器初期化（パターンH）
evaluator = BetTargetEvaluator(use_multi_bet=True, multi_bet_pattern=MultiBetPattern.PATTERN_H)

# 2025年のレースを取得
cursor.execute("""
    SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
    FROM races r
    WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
    ORDER BY r.race_date, r.venue_code, r.race_number
""")
races = cursor.fetchall()

# 月別統計
monthly_stats = defaultdict(lambda: {
    'target_count': 0,
    'total_investment': 0,
    'total_return': 0,
    'hit_count': 0,
    'balance': 0,
})

# 累積収支追跡用
cumulative_balance = 0

for race in races:
    race_id = race['race_id']
    venue_code = int(race['venue_code']) if race['venue_code'] else 0
    race_date = race['race_date']
    month = race_date[:7]  # YYYY-MM

    # 1コース級別
    cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
    c1 = cursor.fetchone()
    c1_rank = c1['racer_rank'] if c1 else 'B1'

    # 予測情報
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
    old_pred = [preds[0]['pit_number'], preds[1]['pit_number'], preds[2]['pit_number']]
    full_prediction = [p['pit_number'] for p in preds]

    # オッズ取得
    cursor.execute('SELECT combination, odds FROM trifecta_odds WHERE race_id = ?', (race_id,))
    odds_rows = cursor.fetchall()
    odds_dict = {row['combination']: row['odds'] for row in odds_rows}

    if not odds_dict:
        continue

    # 購入対象判定
    predictions_dict = {
        'confidence': confidence,
        'old_prediction': old_pred,
        'new_prediction': old_pred,
        'full_prediction': full_prediction,
    }
    race_data = {
        'venue_code': venue_code,
        'entries': [{'pit_number': 1, 'racer_rank': c1_rank}],
    }

    target = evaluator.evaluate_race(
        race_data=race_data,
        predictions=predictions_dict,
        odds_data=odds_dict,
        has_beforeinfo=True
    )

    if target.status != BetStatus.TARGET_CONFIRMED or not target.multi_bet_result:
        continue

    # 結果取得
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

    actual = [results[0]['pit_number'], results[1]['pit_number'], results[2]['pit_number']]
    actual_combo = f"{actual[0]}-{actual[1]}-{actual[2]}"

    # 月別統計更新
    monthly_stats[month]['target_count'] += 1

    # 各買い目を処理
    race_investment = 0
    race_return = 0
    race_hit = False

    for bet in target.multi_bet_result.bets:
        race_investment += bet.bet_amount
        monthly_stats[month]['total_investment'] += bet.bet_amount

        if bet.combination == actual_combo:
            race_return = bet.bet_amount * bet.odds
            monthly_stats[month]['total_return'] += race_return
            monthly_stats[month]['hit_count'] += 1
            race_hit = True

    # 収支計算
    race_balance = race_return - race_investment
    monthly_stats[month]['balance'] += race_balance
    cumulative_balance += race_balance

# 結果表示
print("=" * 100)
print("月別収支")
print("=" * 100)
print(f"{'月':>8} {'購入数':>8} {'投資額':>12} {'払戻額':>12} {'収支':>12} {'ROI':>8} {'的中':>6} {'的中率':>8} {'累積収支':>12}")
print("-" * 100)

total_stats = {
    'target_count': 0,
    'total_investment': 0,
    'total_return': 0,
    'hit_count': 0,
}

cumulative = 0

for month in sorted(monthly_stats.keys()):
    s = monthly_stats[month]

    total_stats['target_count'] += s['target_count']
    total_stats['total_investment'] += s['total_investment']
    total_stats['total_return'] += s['total_return']
    total_stats['hit_count'] += s['hit_count']

    roi = (s['total_return'] / s['total_investment'] * 100) if s['total_investment'] > 0 else 0
    hit_rate = (s['hit_count'] / s['target_count'] * 100) if s['target_count'] > 0 else 0

    cumulative += s['balance']

    print(f"{month:>8} {s['target_count']:>8} {s['total_investment']:>12,}円 {s['total_return']:>11,.0f}円 "
          f"{s['balance']:>+11,.0f}円 {roi:>7.1f}% {s['hit_count']:>6} {hit_rate:>7.1f}% {cumulative:>+11,.0f}円")

print("-" * 100)

# 年間合計
total_roi = (total_stats['total_return'] / total_stats['total_investment'] * 100) if total_stats['total_investment'] > 0 else 0
total_hit_rate = (total_stats['hit_count'] / total_stats['target_count'] * 100) if total_stats['target_count'] > 0 else 0
total_balance = total_stats['total_return'] - total_stats['total_investment']

print(f"{'年間計':>8} {total_stats['target_count']:>8} {total_stats['total_investment']:>12,}円 {total_stats['total_return']:>11,.0f}円 "
      f"{total_balance:>+11,.0f}円 {total_roi:>7.1f}% {total_stats['hit_count']:>6} {total_hit_rate:>7.1f}% {total_balance:>+11,.0f}円")

print()
print("=" * 100)
print("月別詳細統計")
print("=" * 100)

for month in sorted(monthly_stats.keys()):
    s = monthly_stats[month]
    roi = (s['total_return'] / s['total_investment'] * 100) if s['total_investment'] > 0 else 0
    hit_rate = (s['hit_count'] / s['target_count'] * 100) if s['target_count'] > 0 else 0

    print(f"\n【{month}】")
    print(f"  購入レース数: {s['target_count']}件")
    print(f"  投資額: {s['total_investment']:,}円")
    print(f"  払戻額: {s['total_return']:,.0f}円")
    print(f"  収支: {s['balance']:+,}円")
    print(f"  ROI: {roi:.1f}%")
    print(f"  的中数: {s['hit_count']}回")
    print(f"  的中率: {hit_rate:.1f}%")

    if s['target_count'] > 0:
        avg_investment = s['total_investment'] / s['target_count']
        print(f"  平均投資額/レース: {avg_investment:.0f}円")

    if s['hit_count'] > 0:
        avg_return = s['total_return'] / s['hit_count']
        print(f"  平均払戻額/的中: {avg_return:,.0f}円")

print()
print("=" * 100)
print("年間サマリー")
print("=" * 100)
print(f"総購入レース数: {total_stats['target_count']}件")
print(f"総投資額: {total_stats['total_investment']:,}円")
print(f"総払戻額: {total_stats['total_return']:,.0f}円")
print(f"年間収支: {total_balance:+,}円")
print(f"年間ROI: {total_roi:.1f}%")
print(f"総的中数: {total_stats['hit_count']}回")
print(f"年間的中率: {total_hit_rate:.1f}%")
print(f"月間平均的中: {total_stats['hit_count']/12:.1f}回")

if total_stats['target_count'] > 0:
    print(f"平均投資額/レース: {total_stats['total_investment']/total_stats['target_count']:.0f}円")

if total_stats['hit_count'] > 0:
    print(f"平均払戻額/的中: {total_stats['total_return']/total_stats['hit_count']:,.0f}円")

# 最高・最低月
if monthly_stats:
    best_month = max(monthly_stats.items(), key=lambda x: x[1]['balance'])
    worst_month = min(monthly_stats.items(), key=lambda x: x[1]['balance'])

    print()
    print(f"最高収支月: {best_month[0]} ({best_month[1]['balance']:+,}円)")
    print(f"最低収支月: {worst_month[0]} ({worst_month[1]['balance']:+,}円)")

conn.close()
print()
print("分析完了")
