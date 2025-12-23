#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""11月・12月の購入対象レース詳細分析"""
import sys
from pathlib import Path
import sqlite3

ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus

conn = sqlite3.connect('data/boatrace.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()
evaluator = BetTargetEvaluator()

print("=" * 80)
print("11月の購入対象レース分析")
print("=" * 80)

# 11月のレース取得
cursor.execute("""
    SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
    FROM races r
    WHERE r.race_date >= '2025-11-01' AND r.race_date <= '2025-11-30'
    ORDER BY r.race_date, r.venue_code, r.race_number
""")
races = cursor.fetchall()

stats = {
    'total': 0,
    'with_pred': 0,
    'with_odds': 0,
    'confidence_cd': 0,
    'target': 0,
    'candidate': 0,
    'excluded': 0,
    'hit': 0,
}

target_races = []

for race in races:
    race_id = race['race_id']
    venue_code = int(race['venue_code']) if race['venue_code'] else 0
    stats['total'] += 1

    # 1コース級別
    cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
    c1 = cursor.fetchone()
    c1_rank = c1['racer_rank'] if c1 else 'B1'

    # 予測情報
    cursor.execute('''
        SELECT pit_number, confidence
        FROM race_predictions
        WHERE race_id = ? AND prediction_type = 'before'
        ORDER BY rank_prediction
    ''', (race_id,))
    preds = cursor.fetchall()

    if len(preds) < 6:
        continue

    stats['with_pred'] += 1
    confidence = preds[0]['confidence']
    old_pred = [preds[0]['pit_number'], preds[1]['pit_number'], preds[2]['pit_number']]

    if confidence not in ['C', 'D']:
        continue

    stats['confidence_cd'] += 1

    # オッズ取得
    old_combo = f"{old_pred[0]}-{old_pred[1]}-{old_pred[2]}"
    cursor.execute('SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?',
                  (race_id, old_combo))
    odds_row = cursor.fetchone()
    old_odds = odds_row['odds'] if odds_row else 0

    if old_odds > 0:
        stats['with_odds'] += 1

    # 購入判定
    target = evaluator.evaluate(
        confidence=confidence,
        c1_rank=c1_rank,
        old_combo=old_combo,
        new_combo=old_combo,
        old_odds=old_odds,
        new_odds=old_odds,
        has_beforeinfo=True,
        venue_code=venue_code
    )

    if target.status == BetStatus.TARGET_CONFIRMED:
        stats['target'] += 1

        # 結果確認
        cursor.execute('''
            SELECT pit_number, rank
            FROM results
            WHERE race_id = ?
            ORDER BY CAST(rank AS INTEGER)
            LIMIT 3
        ''', (race_id,))
        results = cursor.fetchall()

        if len(results) == 3:
            actual = [results[0]['pit_number'], results[1]['pit_number'], results[2]['pit_number']]
            is_hit = (actual == old_pred)
            if is_hit:
                stats['hit'] += 1

        target_races.append({
            'date': race['race_date'],
            'venue': venue_code,
            'race_num': race['race_number'],
            'confidence': confidence,
            'c1_rank': c1_rank,
            'combo': old_combo,
            'odds': old_odds,
            'odds_range': target.odds_range,
            'bet_amount': target.bet_amount,
            'expected_roi': target.expected_roi,
        })
    elif target.status == BetStatus.CANDIDATE:
        stats['candidate'] += 1
    else:
        stats['excluded'] += 1

print("\n統計:")
print(f"総レース数: {stats['total']}")
print(f"予測あり: {stats['with_pred']}")
print(f"信頼度C/D: {stats['confidence_cd']}")
print(f"オッズあり: {stats['with_odds']}")
print(f"購入対象: {stats['target']}")
print(f"候補: {stats['candidate']}")
print(f"除外: {stats['excluded']}")
print(f"的中数: {stats['hit']}")
if stats['target'] > 0:
    print(f"的中率: {stats['hit']/stats['target']*100:.2f}%")

print(f"\n購入対象レース一覧（計{len(target_races)}件）:")
print(f"{'日付':<12} {'会場':>4} {'R':>3} {'信頼度':>6} {'1C級':>6} {'買目':>10} {'オッズ':>8} {'範囲':>12} {'賭金':>6}")
print("-" * 80)
for t in target_races[:20]:
    print(f"{t['date']:<12} {t['venue']:>4} {t['race_num']:>3}R {t['confidence']:>6} {t['c1_rank']:>6} {t['combo']:>10} {t['odds']:>8.1f}倍 {t['odds_range']:>12} {t['bet_amount']:>6}円")

if len(target_races) > 20:
    print(f"... 他{len(target_races)-20}件")

print("\n" + "=" * 80)
print("12月の購入対象レース分析")
print("=" * 80)

# 12月のレース取得
cursor.execute("""
    SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
    FROM races r
    WHERE r.race_date >= '2025-12-01' AND r.race_date <= '2025-12-31'
    ORDER BY r.race_date, r.venue_code, r.race_number
""")
races_dec = cursor.fetchall()

stats_dec = {
    'total': 0,
    'with_pred': 0,
    'with_odds': 0,
    'confidence_cd': 0,
    'target': 0,
    'candidate': 0,
    'excluded': 0,
    'hit': 0,
}

target_races_dec = []

for race in races_dec:
    race_id = race['race_id']
    venue_code = int(race['venue_code']) if race['venue_code'] else 0
    stats_dec['total'] += 1

    # 1コース級別
    cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
    c1 = cursor.fetchone()
    c1_rank = c1['racer_rank'] if c1 else 'B1'

    # 予測情報
    cursor.execute('''
        SELECT pit_number, confidence
        FROM race_predictions
        WHERE race_id = ? AND prediction_type = 'before'
        ORDER BY rank_prediction
    ''', (race_id,))
    preds = cursor.fetchall()

    if len(preds) < 6:
        continue

    stats_dec['with_pred'] += 1
    confidence = preds[0]['confidence']
    old_pred = [preds[0]['pit_number'], preds[1]['pit_number'], preds[2]['pit_number']]

    if confidence not in ['C', 'D']:
        continue

    stats_dec['confidence_cd'] += 1

    # オッズ取得
    old_combo = f"{old_pred[0]}-{old_pred[1]}-{old_pred[2]}"
    cursor.execute('SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?',
                  (race_id, old_combo))
    odds_row = cursor.fetchone()
    old_odds = odds_row['odds'] if odds_row else 0

    if old_odds > 0:
        stats_dec['with_odds'] += 1

    # 購入判定
    target = evaluator.evaluate(
        confidence=confidence,
        c1_rank=c1_rank,
        old_combo=old_combo,
        new_combo=old_combo,
        old_odds=old_odds,
        new_odds=old_odds,
        has_beforeinfo=True,
        venue_code=venue_code
    )

    if target.status == BetStatus.TARGET_CONFIRMED:
        stats_dec['target'] += 1

        # 結果確認
        cursor.execute('''
            SELECT pit_number, rank
            FROM results
            WHERE race_id = ?
            ORDER BY CAST(rank AS INTEGER)
            LIMIT 3
        ''', (race_id,))
        results = cursor.fetchall()

        if len(results) == 3:
            actual = [results[0]['pit_number'], results[1]['pit_number'], results[2]['pit_number']]
            is_hit = (actual == old_pred)
            if is_hit:
                stats_dec['hit'] += 1

        target_races_dec.append({
            'date': race['race_date'],
            'venue': venue_code,
            'race_num': race['race_number'],
            'confidence': confidence,
            'c1_rank': c1_rank,
            'combo': old_combo,
            'odds': old_odds,
            'odds_range': target.odds_range,
            'bet_amount': target.bet_amount,
            'expected_roi': target.expected_roi,
        })
    elif target.status == BetStatus.CANDIDATE:
        stats_dec['candidate'] += 1
    else:
        stats_dec['excluded'] += 1

print("\n統計:")
print(f"総レース数: {stats_dec['total']}")
print(f"予測あり: {stats_dec['with_pred']}")
print(f"信頼度C/D: {stats_dec['confidence_cd']}")
print(f"オッズあり: {stats_dec['with_odds']}")
print(f"購入対象: {stats_dec['target']}")
print(f"候補: {stats_dec['candidate']}")
print(f"除外: {stats_dec['excluded']}")
print(f"的中数: {stats_dec['hit']}")
if stats_dec['target'] > 0:
    print(f"的中率: {stats_dec['hit']/stats_dec['target']*100:.2f}%")

print(f"\n購入対象レース一覧（計{len(target_races_dec)}件）:")
print(f"{'日付':<12} {'会場':>4} {'R':>3} {'信頼度':>6} {'1C級':>6} {'買目':>10} {'オッズ':>8} {'範囲':>12} {'賭金':>6}")
print("-" * 80)
for t in target_races_dec:
    print(f"{t['date']:<12} {t['venue']:>4} {t['race_num']:>3}R {t['confidence']:>6} {t['c1_rank']:>6} {t['combo']:>10} {t['odds']:>8.1f}倍 {t['odds_range']:>12} {t['bet_amount']:>6}円")

conn.close()
print("\n分析完了")
