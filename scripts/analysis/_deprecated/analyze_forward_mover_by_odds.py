# -*- coding: utf-8 -*-
"""
前付けレース × オッズ帯別の分析

仮説: 前付けレースの高ROIはオッズの歪みが原因
→ 低オッズ（本命）は除外し、高オッズだけ残せば効率UP？
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


def get_odds_band(odds):
    """オッズ帯を判定"""
    if odds < 10:
        return "0-10倍"
    elif odds < 20:
        return "10-20倍"
    elif odds < 30:
        return "20-30倍"
    elif odds < 50:
        return "30-50倍"
    elif odds < 100:
        return "50-100倍"
    else:
        return "100倍以上"


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    forward_movers = load_forward_movers()

    ff.FEATURE_FLAGS['ab_rank_special_betting'] = True
    evaluator = BetTargetEvaluator()

    print("=" * 100)
    print("前付けレース × オッズ帯別分析")
    print("=" * 100)
    print()

    # 2024-2025年データ
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code
        FROM races r
        WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2025-11-30'
          AND EXISTS (SELECT 1 FROM race_predictions WHERE race_id = r.id AND prediction_type = 'before')
          AND EXISTS (SELECT 1 FROM results WHERE race_id = r.id AND is_invalid = 0)
    ''')
    races = cursor.fetchall()

    # 統計: forward/no_forward × odds_band
    stats = defaultdict(lambda: {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0})

    for race in races:
        race_id = race['race_id']
        venue_code = int(race['venue_code']) if race['venue_code'] else 0

        # 前付け常習者チェック
        cursor.execute('SELECT racer_number FROM entries WHERE race_id = ?', (race_id,))
        racer_numbers = [str(row['racer_number']) for row in cursor.fetchall()]
        has_forward = bool(set(racer_numbers) & forward_movers)
        category = 'forward' if has_forward else 'no_forward'

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
        odds_band = get_odds_band(odds)

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
        key = (category, odds_band)
        stats[key]['target'] += 1
        stats[key]['bet'] += bet_amount

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
                    stats[key]['hit'] += 1
                    stats[key]['payout'] += payout

    conn.close()

    # 結果表示
    odds_bands = ["0-10倍", "10-20倍", "20-30倍", "30-50倍", "50-100倍", "100倍以上"]

    print("=" * 120)
    print("オッズ帯別 × 前付け有無別の収益性")
    print("=" * 120)
    print(f"\n{'オッズ帯':<12} | {'カテゴリ':<12} | {'購入数':>8} | {'的中':>6} | {'的中率':>8} | {'ROI':>10} | {'収支':>15}")
    print("-" * 100)

    for odds_band in odds_bands:
        for category, label in [('forward', '前付けあり'), ('no_forward', '前付けなし')]:
            key = (category, odds_band)
            s = stats[key]
            if s['target'] == 0:
                continue
            roi = s['payout'] / s['bet'] * 100 if s['bet'] > 0 else 0
            hit_rate = s['hit'] / s['target'] * 100 if s['target'] > 0 else 0
            profit = s['payout'] - s['bet']
            print(f"{odds_band:<12} | {label:<12} | {s['target']:>8,} | {s['hit']:>6} | {hit_rate:>7.2f}% | {roi:>9.1f}% | {profit:>+14,.0f}円")
        print("-" * 100)

    # 前付けレースのオッズ帯別まとめ
    print()
    print("=" * 100)
    print("前付けレースのオッズ帯別まとめ")
    print("=" * 100)
    print(f"\n{'オッズ帯':<12} | {'購入数':>8} | {'的中':>6} | {'的中率':>8} | {'ROI':>10} | {'収支':>15} | {'判定':<10}")
    print("-" * 90)

    for odds_band in odds_bands:
        key = ('forward', odds_band)
        s = stats[key]
        if s['target'] == 0:
            continue
        roi = s['payout'] / s['bet'] * 100 if s['bet'] > 0 else 0
        hit_rate = s['hit'] / s['target'] * 100 if s['target'] > 0 else 0
        profit = s['payout'] - s['bet']

        # 判定
        if roi >= 150:
            judgment = "✅ 超優良"
        elif roi >= 100:
            judgment = "✅ 黒字"
        elif roi >= 80:
            judgment = "🟡 微損"
        else:
            judgment = "❌ 赤字"

        print(f"{odds_band:<12} | {s['target']:>8,} | {s['hit']:>6} | {hit_rate:>7.2f}% | {roi:>9.1f}% | {profit:>+14,.0f}円 | {judgment}")

    # 提案
    print()
    print("=" * 100)
    print("分析と提案")
    print("=" * 100)

    # 低オッズ帯の前付けレース
    low_odds_forward = stats[('forward', '0-10倍')]
    if low_odds_forward['target'] > 0:
        low_roi = low_odds_forward['payout'] / low_odds_forward['bet'] * 100 if low_odds_forward['bet'] > 0 else 0
        low_profit = low_odds_forward['payout'] - low_odds_forward['bet']
        print(f"\n低オッズ(0-10倍) × 前付けあり: {low_odds_forward['target']}件, ROI {low_roi:.1f}%, 収支 {low_profit:+,.0f}円")

        if low_roi < 100:
            print("→ 低オッズの前付けレースは赤字 → 除外すべき！")
        else:
            print("→ 低オッズの前付けレースも黒字 → 除外不要")

    # 高オッズ帯の前付けレース
    high_odds_forward = stats[('forward', '50-100倍')]
    if high_odds_forward['target'] > 0:
        high_roi = high_odds_forward['payout'] / high_odds_forward['bet'] * 100 if high_odds_forward['bet'] > 0 else 0
        high_profit = high_odds_forward['payout'] - high_odds_forward['bet']
        print(f"\n高オッズ(50-100倍) × 前付けあり: {high_odds_forward['target']}件, ROI {high_roi:.1f}%, 収支 {high_profit:+,.0f}円")


if __name__ == "__main__":
    main()
