# -*- coding: utf-8 -*-
"""
P-1パラドックスの深層分析

理屈: 前付けレース → 予測精度低下 → 除外すべき
統計: P-1除外 → ROI悪化

この矛盾を解明する
"""
import sys
import sqlite3
import io
import json
from pathlib import Path
from collections import defaultdict

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

import config.feature_flags as ff
from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus


def load_forward_movers():
    path = ROOT_DIR / "config" / "forward_movers.json"
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return set(str(rn) for rn in data.get('racer_numbers', []))
    except:
        return set()


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    forward_movers = load_forward_movers()

    # ab_rank ON設定
    ff.FEATURE_FLAGS['ab_rank_special_betting'] = True
    evaluator = BetTargetEvaluator()

    print("=" * 100)
    print("P-1パラドックス深層分析")
    print("=" * 100)
    print()

    # 全レース取得
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-11-30'
          AND EXISTS (SELECT 1 FROM race_predictions WHERE race_id = r.id AND prediction_type = 'before')
          AND EXISTS (SELECT 1 FROM results WHERE race_id = r.id AND is_invalid = 0)
    ''')
    races = cursor.fetchall()

    # 統計収集
    stats = {
        'all': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
        'forward': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
        'no_forward': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
    }

    # 信頼度別
    by_confidence = {
        'A': {'forward': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
              'no_forward': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0}},
        'B': {'forward': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
              'no_forward': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0}},
        'C': {'forward': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
              'no_forward': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0}},
        'D': {'forward': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
              'no_forward': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0}},
    }

    for race in races:
        race_id = race['race_id']
        venue_code = int(race['venue_code']) if race['venue_code'] else 0

        # 前付け常習者チェック
        cursor.execute('SELECT racer_number FROM entries WHERE race_id = ?', (race_id,))
        racer_numbers = [str(row['racer_number']) for row in cursor.fetchall()]
        has_forward = bool(set(racer_numbers) & forward_movers)

        # 予測取得
        cursor.execute('''
            SELECT pit_number, confidence, total_score
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'before'
            ORDER BY total_score DESC
        ''', (race_id,))
        preds = cursor.fetchall()

        if len(preds) < 6:
            continue

        confidence = preds[0]['confidence']
        top3 = [p['pit_number'] for p in preds[:3]]
        combo = f"{top3[0]}-{top3[1]}-{top3[2]}"

        # 1コース級別
        cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
        c1 = cursor.fetchone()
        c1_rank = c1['racer_rank'] if c1 else 'B1'

        # オッズ
        cursor.execute(
            'SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?',
            (race_id, combo))
        odds_row = cursor.fetchone()
        if not odds_row:
            continue

        odds = odds_row['odds']

        result = evaluator.evaluate(
            confidence=confidence,
            c1_rank=c1_rank,
            old_combo=combo,
            new_combo=combo,
            old_odds=odds,
            new_odds=odds,
            has_beforeinfo=True,
            venue_code=venue_code
        )

        if result.status not in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
            continue

        bet_amount = result.bet_amount

        # 統計更新
        category = 'forward' if has_forward else 'no_forward'
        stats['all']['target'] += 1
        stats['all']['bet'] += bet_amount
        stats[category]['target'] += 1
        stats[category]['bet'] += bet_amount

        if confidence in by_confidence:
            by_confidence[confidence][category]['target'] += 1
            by_confidence[confidence][category]['bet'] += bet_amount

        # 的中判定
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        results = cursor.fetchall()

        if len(results) >= 3:
            actual_combo = f"{results[0]['pit_number']}-{results[1]['pit_number']}-{results[2]['pit_number']}"

            if combo == actual_combo:
                cursor.execute('''
                    SELECT amount FROM payouts
                    WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                ''', (race_id, actual_combo))
                payout_row = cursor.fetchone()

                if payout_row:
                    payout = (bet_amount / 100) * payout_row['amount']
                    stats['all']['hit'] += 1
                    stats['all']['payout'] += payout
                    stats[category]['hit'] += 1
                    stats[category]['payout'] += payout

                    if confidence in by_confidence:
                        by_confidence[confidence][category]['hit'] += 1
                        by_confidence[confidence][category]['payout'] += payout

    conn.close()

    # 結果表示
    def calc_roi(s):
        return s['payout'] / s['bet'] * 100 if s['bet'] > 0 else 0

    def calc_hit_rate(s):
        return s['hit'] / s['target'] * 100 if s['target'] > 0 else 0

    print("=" * 100)
    print("1. 全体統計（購入対象レースのみ）")
    print("=" * 100)
    print(f"\n{'カテゴリ':<20} {'購入数':>10} {'的中数':>8} {'的中率':>10} {'ROI':>10} {'収支':>15}")
    print("-" * 85)

    for cat, label in [('all', '全体'), ('forward', '前付けあり'), ('no_forward', '前付けなし')]:
        s = stats[cat]
        roi = calc_roi(s)
        hit_rate = calc_hit_rate(s)
        profit = s['payout'] - s['bet']
        print(f"{label:<20} {s['target']:>10,} {s['hit']:>8} {hit_rate:>9.2f}% {roi:>9.1f}% {profit:>+14,.0f}円")

    print()
    print("=" * 100)
    print("2. 信頼度別・前付け有無別の詳細")
    print("=" * 100)

    for conf in ['A', 'B', 'C', 'D']:
        print(f"\n【信頼度 {conf}】")
        print(f"{'カテゴリ':<15} {'購入数':>8} {'的中数':>6} {'的中率':>8} {'ROI':>10} {'収支':>12}")
        print("-" * 65)

        for cat, label in [('forward', '前付けあり'), ('no_forward', '前付けなし')]:
            s = by_confidence[conf][cat]
            if s['target'] == 0:
                continue
            roi = calc_roi(s)
            hit_rate = calc_hit_rate(s)
            profit = s['payout'] - s['bet']
            print(f"{label:<15} {s['target']:>8,} {s['hit']:>6} {hit_rate:>7.2f}% {roi:>9.1f}% {profit:>+11,.0f}円")

    print()
    print("=" * 100)
    print("3. パラドックスの分析")
    print("=" * 100)

    # 前付けありの収支
    forward_profit = stats['forward']['payout'] - stats['forward']['bet']
    forward_roi = calc_roi(stats['forward'])

    # 前付けなしの収支
    no_forward_profit = stats['no_forward']['payout'] - stats['no_forward']['bet']
    no_forward_roi = calc_roi(stats['no_forward'])

    print(f"\n前付けありレース: ROI {forward_roi:.1f}%, 収支 {forward_profit:+,.0f}円")
    print(f"前付けなしレース: ROI {no_forward_roi:.1f}%, 収支 {no_forward_profit:+,.0f}円")
    print(f"差分: ROI {forward_roi - no_forward_roi:+.1f}pt, 収支 {forward_profit - no_forward_profit:+,.0f}円")

    print()
    if forward_roi > no_forward_roi:
        print("【結論】前付けありレースの方がROIが高い！")
        print("  → P-1で除外すると、高収益レースを捨てることになる")
        print()
        print("【考察】なぜ前付けレースのROIが高いのか？")
        print("  1. 前付けでレースが荒れる → オッズが高い → 的中時の払戻が大きい")
        print("  2. 市場が前付けリスクを過大評価 → 実際より高いオッズになっている")
        print("  3. 我々の予測モデルは前付け影響を織り込み済み → 市場より正確")
    else:
        print("【結論】前付けなしレースの方がROIが高い")
        print("  → P-1フィルターは理論通り有効なはず")
        print("  → 別の要因でROIが下がっている可能性")


if __name__ == "__main__":
    main()
