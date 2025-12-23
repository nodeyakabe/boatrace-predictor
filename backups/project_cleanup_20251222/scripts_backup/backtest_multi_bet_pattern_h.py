#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
パターンH複数点買いバックテスト（戦略B統合版）

戦略Bにパターンメ実装を統合し、2025年データで最終検証する
"""
import sys
from pathlib import Path
import sqlite3

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus, MultiBetPattern

# データベース接続
conn = sqlite3.connect('data/boatrace.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("=" * 100)
print("パターンH複数点買いバックテスト（2025年全期間）")
print("=" * 100)
print()

# 評価器の初期化
evaluator_single = BetTargetEvaluator(use_multi_bet=False)  # 1点買い（現行）
evaluator_multi = BetTargetEvaluator(use_multi_bet=True, multi_bet_pattern=MultiBetPattern.PATTERN_H)  # パターンH

# 2025年のレースを取得
cursor.execute("""
    SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
    FROM races r
    WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
    ORDER BY r.race_date, r.venue_code, r.race_number
""")
races = cursor.fetchall()

# 統計情報
stats_single = {
    'target_count': 0,
    'total_investment': 0,
    'total_return': 0,
    'hit_count': 0,
}

stats_multi = {
    'target_count': 0,
    'total_investment': 0,
    'total_return': 0,
    'hit_count': 0,
}

print(f"対象レース数: {len(races):,}件")
print()

for race in races:
    race_id = race['race_id']
    venue_code = int(race['venue_code']) if race['venue_code'] else 0

    # 1コース級別
    cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
    c1 = cursor.fetchone()
    c1_rank = c1['racer_rank'] if c1 else 'B1'

    # 予測情報（rank_prediction順で取得）
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
    full_prediction = [p['pit_number'] for p in preds]  # 1-6位の全予測

    # オッズを全て取得
    cursor.execute('SELECT combination, odds FROM trifecta_odds WHERE race_id = ?', (race_id,))
    odds_rows = cursor.fetchall()
    odds_dict = {row['combination']: row['odds'] for row in odds_rows}

    old_combo = f"{old_pred[0]}-{old_pred[1]}-{old_pred[2]}"
    old_odds = odds_dict.get(old_combo, 0)

    if old_odds == 0:
        continue

    # 1点買い評価
    target_single = evaluator_single.evaluate(
        confidence=confidence,
        c1_rank=c1_rank,
        old_combo=old_combo,
        new_combo=old_combo,
        old_odds=old_odds,
        new_odds=old_odds,
        has_beforeinfo=True,
        venue_code=venue_code
    )

    # 複数点買い評価（パターンH）
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
    target_multi = evaluator_multi.evaluate_race(
        race_data=race_data,
        predictions=predictions_dict,
        odds_data=odds_dict,
        has_beforeinfo=True
    )

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

    # 1点買いの集計
    if target_single.status == BetStatus.TARGET_CONFIRMED:
        stats_single['target_count'] += 1
        stats_single['total_investment'] += target_single.bet_amount

        if actual == old_pred:
            stats_single['hit_count'] += 1
            stats_single['total_return'] += target_single.bet_amount * old_odds

    # 複数点買いの集計
    if target_multi.status == BetStatus.TARGET_CONFIRMED and target_multi.multi_bet_result:
        stats_multi['target_count'] += 1

        # 各買い目を集計
        for bet in target_multi.multi_bet_result.bets:
            stats_multi['total_investment'] += bet.bet_amount

            # 的中チェック
            if bet.combination == actual_combo:
                stats_multi['hit_count'] += 1
                stats_multi['total_return'] += bet.bet_amount * bet.odds

# 結果表示
print("=" * 100)
print("バックテスト結果比較")
print("=" * 100)
print()

print("【1点買い（現行戦略）】")
print(f"購入対象レース数: {stats_single['target_count']:,}件")
print(f"総投資額: {stats_single['total_investment']:,}円")
print(f"総払戻額: {stats_single['total_return']:,}円")
print(f"収支: {stats_single['total_return'] - stats_single['total_investment']:+,}円")
if stats_single['total_investment'] > 0:
    roi = stats_single['total_return'] / stats_single['total_investment'] * 100
    print(f"ROI: {roi:.1f}%")
if stats_single['target_count'] > 0:
    hit_rate = stats_single['hit_count'] / stats_single['target_count'] * 100
    print(f"的中数: {stats_single['hit_count']}回")
    print(f"的中率: {hit_rate:.2f}%")
print()

print("【パターンH（複数点買い）】")
print(f"購入対象レース数: {stats_multi['target_count']:,}件")
print(f"総投資額: {stats_multi['total_investment']:,}円")
print(f"総払戻額: {stats_multi['total_return']:,}円")
print(f"収支: {stats_multi['total_return'] - stats_multi['total_investment']:+,}円")
if stats_multi['total_investment'] > 0:
    roi = stats_multi['total_return'] / stats_multi['total_investment'] * 100
    print(f"ROI: {roi:.1f}%")
if stats_multi['target_count'] > 0:
    hit_rate = stats_multi['hit_count'] / stats_multi['target_count'] * 100
    print(f"的中数: {stats_multi['hit_count']}回")
    print(f"的中率: {hit_rate:.2f}%")
print()

# 改善効果
if stats_single['total_investment'] > 0 and stats_multi['total_investment'] > 0:
    print("=" * 100)
    print("改善効果")
    print("=" * 100)
    profit_diff = (stats_multi['total_return'] - stats_multi['total_investment']) - \
                  (stats_single['total_return'] - stats_single['total_investment'])
    roi_diff = (stats_multi['total_return'] / stats_multi['total_investment'] * 100) - \
               (stats_single['total_return'] / stats_single['total_investment'] * 100)
    hit_rate_diff = (stats_multi['hit_count'] / stats_multi['target_count'] * 100) - \
                    (stats_single['hit_count'] / stats_single['target_count'] * 100)

    print(f"収支改善: {profit_diff:+,}円")
    print(f"ROI改善: {roi_diff:+.1f}pt")
    print(f"的中率改善: {hit_rate_diff:+.1f}pt")
    print(f"月間平均的中回数: {stats_single['hit_count']/12:.1f}回 → {stats_multi['hit_count']/12:.1f}回")
    print()

conn.close()
print("バックテスト完了")
