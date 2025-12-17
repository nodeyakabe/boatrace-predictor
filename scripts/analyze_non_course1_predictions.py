# -*- coding: utf-8 -*-
"""
非1コース予測の詳細分析

目的:
- 非1コース予測のオッズ別ROI分析
- 最適なオッズ下限の特定
- スコア差と的中率・ROIの関係分析
"""

import sys
import sqlite3
from pathlib import Path
from typing import Dict, Any, List
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting import BetSelector


def analyze_non_course1_predictions(db_path: str, start_date: str, end_date: str):
    """非1コース予測の詳細分析"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 非1コース予測のレースを取得
    cursor.execute('''
        SELECT DISTINCT
            r.id as race_id,
            r.venue_code,
            r.race_date,
            r.race_number,
            p.confidence,
            p.prediction_type
        FROM races r
        JOIN race_predictions p ON r.id = p.race_id
        WHERE r.race_date >= ? AND r.race_date <= ?
          AND p.prediction_type = 'advance'
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''', (start_date, end_date))

    races = cursor.fetchall()

    # オッズ帯別の統計
    odds_ranges = [
        (0, 10),
        (10, 20),
        (20, 30),
        (30, 40),
        (40, 50),
        (50, 100),
        (100, float('inf'))
    ]

    stats_by_odds = defaultdict(lambda: {
        'total': 0,
        'course1': 0,
        'non_course1': 0,
        'course1_hits': 0,
        'non_course1_hits': 0,
        'course1_invested': 0,
        'non_course1_invested': 0,
        'course1_payout': 0,
        'non_course1_payout': 0,
    })

    # スコア差別の統計
    score_diff_ranges = [
        (0, 5),
        (5, 10),
        (10, 15),
        (15, 20),
        (20, 30),
        (30, float('inf'))
    ]

    stats_by_score = defaultdict(lambda: {
        'total': 0,
        'hits': 0,
        'invested': 0,
        'payout': 0,
    })

    non_course1_details = []

    for race in races:
        race_id = race['race_id']

        # 予測データ取得
        cursor.execute('''
            SELECT pit_number, rank_prediction, total_score, confidence
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'advance'
            ORDER BY rank_prediction
        ''', (race_id,))
        preds = cursor.fetchall()

        if len(preds) < 6:
            continue

        # 1着予測
        top_pred = preds[0]['pit_number']
        top_score = preds[0]['total_score']
        second_score = preds[1]['total_score'] if len(preds) > 1 else 0
        score_diff = top_score - second_score

        # オッズ取得
        pred_combo = f"{preds[0]['pit_number']}-{preds[1]['pit_number']}-{preds[2]['pit_number']}"

        cursor.execute('''
            SELECT odds FROM trifecta_odds
            WHERE race_id = ? AND combination = ?
        ''', (race_id, pred_combo))
        odds_row = cursor.fetchone()
        odds = odds_row['odds'] if odds_row else 0

        # 結果取得
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        results = cursor.fetchall()

        if len(results) < 3:
            continue

        actual_combo = f"{results[0]['pit_number']}-{results[1]['pit_number']}-{results[2]['pit_number']}"

        # 払戻取得
        cursor.execute('''
            SELECT amount FROM payouts
            WHERE race_id = ? AND bet_type = 'trifecta'
        ''', (race_id,))
        payout_row = cursor.fetchone()
        payout = payout_row['amount'] if payout_row else 0

        # 的中判定
        is_hit = (pred_combo == actual_combo)

        # 信頼度C以上のみ対象
        if race['confidence'] not in ['A', 'B', 'C']:
            continue

        # オッズ範囲を特定
        odds_range = None
        for min_odds, max_odds in odds_ranges:
            if min_odds <= odds < max_odds:
                odds_range = f"{min_odds}-{max_odds if max_odds != float('inf') else '∞'}"
                break

        # スコア差範囲を特定
        score_range = None
        for min_score, max_score in score_diff_ranges:
            if min_score <= score_diff < max_score:
                score_range = f"{min_score}-{max_score if max_score != float('inf') else '∞'}"
                break

        # 1コースかどうか
        is_course1 = (top_pred == 1)

        if odds_range:
            stats = stats_by_odds[odds_range]
            stats['total'] += 1

            if is_course1:
                stats['course1'] += 1
                stats['course1_invested'] += 300
                if is_hit:
                    stats['course1_hits'] += 1
                    stats['course1_payout'] += payout
            else:
                stats['non_course1'] += 1
                stats['non_course1_invested'] += 300
                if is_hit:
                    stats['non_course1_hits'] += 1
                    stats['non_course1_payout'] += payout

                # 非1コース予測の詳細記録
                non_course1_details.append({
                    'race_id': race_id,
                    'race_date': race['race_date'],
                    'venue_code': race['venue_code'],
                    'predicted_course': top_pred,
                    'score_diff': score_diff,
                    'odds': odds,
                    'is_hit': is_hit,
                    'payout': payout if is_hit else 0,
                })

        # スコア差別統計（非1コースのみ）
        if not is_course1 and score_range:
            score_stats = stats_by_score[score_range]
            score_stats['total'] += 1
            score_stats['invested'] += 300
            if is_hit:
                score_stats['hits'] += 1
                score_stats['payout'] += payout

    conn.close()

    # 結果出力
    print("=" * 80)
    print("非1コース予測の詳細分析")
    print("=" * 80)
    print(f"期間: {start_date} ～ {end_date}")
    print(f"対象: 信頼度A/B/Cのみ")
    print()

    print("【1. オッズ帯別の分析】")
    print()
    print(f"{'オッズ帯':>15} | {'1コース':>8} | {'非1コース':>8} | {'1コースROI':>10} | {'非1コースROI':>10} | {'非1的中率':>8}")
    print("-" * 80)

    for min_odds, max_odds in odds_ranges:
        odds_range = f"{min_odds}-{max_odds if max_odds != float('inf') else '∞'}"
        stats = stats_by_odds.get(odds_range)

        if not stats or stats['total'] == 0:
            continue

        c1_roi = (stats['course1_payout'] / stats['course1_invested'] * 100) if stats['course1_invested'] > 0 else 0
        non_c1_roi = (stats['non_course1_payout'] / stats['non_course1_invested'] * 100) if stats['non_course1_invested'] > 0 else 0
        non_c1_hit_rate = (stats['non_course1_hits'] / stats['non_course1'] * 100) if stats['non_course1'] > 0 else 0

        print(f"{odds_range:>15} | {stats['course1']:>8} | {stats['non_course1']:>8} | {c1_roi:>9.1f}% | {non_c1_roi:>9.1f}% | {non_c1_hit_rate:>7.1f}%")

    print()
    print("【2. スコア差別の分析（非1コース予測のみ）】")
    print()
    print(f"{'スコア差':>15} | {'件数':>8} | {'的中数':>8} | {'的中率':>8} | {'ROI':>10} | {'収支':>10}")
    print("-" * 80)

    for min_score, max_score in score_diff_ranges:
        score_range = f"{min_score}-{max_score if max_score != float('inf') else '∞'}"
        stats = stats_by_score.get(score_range)

        if not stats or stats['total'] == 0:
            continue

        hit_rate = (stats['hits'] / stats['total'] * 100) if stats['total'] > 0 else 0
        roi = (stats['payout'] / stats['invested'] * 100) if stats['invested'] > 0 else 0
        profit = stats['payout'] - stats['invested']

        print(f"{score_range:>15} | {stats['total']:>8} | {stats['hits']:>8} | {hit_rate:>7.1f}% | {roi:>9.1f}% | {profit:>+9,}円")

    print()
    print("【3. 非1コース予測の総合統計】")
    print()

    total_non_c1 = sum(s['non_course1'] for s in stats_by_odds.values())
    total_non_c1_hits = sum(s['non_course1_hits'] for s in stats_by_odds.values())
    total_non_c1_invested = sum(s['non_course1_invested'] for s in stats_by_odds.values())
    total_non_c1_payout = sum(s['non_course1_payout'] for s in stats_by_odds.values())

    if total_non_c1 > 0:
        print(f"非1コース予測数: {total_non_c1}件")
        print(f"的中数: {total_non_c1_hits}件")
        print(f"的中率: {total_non_c1_hits / total_non_c1 * 100:.1f}%")
        print(f"投資額: {total_non_c1_invested:,}円")
        print(f"払戻額: {total_non_c1_payout:,}円")
        print(f"収支: {total_non_c1_payout - total_non_c1_invested:+,}円")
        print(f"ROI: {total_non_c1_payout / total_non_c1_invested * 100:.1f}%")

    print()
    print("【4. オッズ下限別のシミュレーション】")
    print()
    print(f"{'オッズ下限':>10} | {'購入数':>8} | {'的中数':>8} | {'的中率':>8} | {'ROI':>10} | {'収支':>10}")
    print("-" * 80)

    # オッズ下限別のシミュレーション
    for min_odds_threshold in [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
        filtered_details = [d for d in non_course1_details if d['odds'] >= min_odds_threshold]

        if not filtered_details:
            continue

        total = len(filtered_details)
        hits = sum(1 for d in filtered_details if d['is_hit'])
        invested = total * 300
        payout = sum(d['payout'] for d in filtered_details)
        hit_rate = (hits / total * 100) if total > 0 else 0
        roi = (payout / invested * 100) if invested > 0 else 0
        profit = payout - invested

        print(f"{min_odds_threshold:>10}倍 | {total:>8} | {hits:>8} | {hit_rate:>7.1f}% | {roi:>9.1f}% | {profit:>+9,}円")

    print()
    print("【5. 推奨設定】")
    print()

    # 最適オッズ下限を特定（ROI最大）
    best_roi = 0
    best_threshold = 0

    for min_odds_threshold in range(0, 101, 5):
        filtered_details = [d for d in non_course1_details if d['odds'] >= min_odds_threshold]

        if not filtered_details:
            continue

        invested = len(filtered_details) * 300
        payout = sum(d['payout'] for d in filtered_details)
        roi = (payout / invested * 100) if invested > 0 else 0

        if roi > best_roi and len(filtered_details) >= 30:  # サンプル数30件以上
            best_roi = roi
            best_threshold = min_odds_threshold

    print(f"最適オッズ下限: {best_threshold}倍")
    print(f"期待ROI: {best_roi:.1f}%")
    print()
    print("【設定例】")
    print("```yaml")
    print("# config/prediction_strategy.yaml")
    print("non_course1_prediction:")
    print("  enabled: true")
    print(f"  min_odds: {best_threshold}  # オッズ下限")
    print("  min_score_difference: 20  # スコア差下限")
    print("```")

    return {
        'stats_by_odds': dict(stats_by_odds),
        'stats_by_score': dict(stats_by_score),
        'non_course1_details': non_course1_details,
        'best_threshold': best_threshold,
        'best_roi': best_roi,
    }


def main():
    db_path = str(ROOT_DIR / 'data' / 'boatrace.db')

    print("2025年全期間データで分析中...")
    print()

    results = analyze_non_course1_predictions(db_path, '2025-01-01', '2025-11-30')

    print()
    print("=" * 80)
    print("分析完了")
    print("=" * 80)


if __name__ == '__main__':
    main()
