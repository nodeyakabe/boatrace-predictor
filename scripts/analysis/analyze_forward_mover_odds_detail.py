# -*- coding: utf-8 -*-
"""
前付けレース × オッズ帯の詳細分析（購入対象のみ）
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

    ff.FEATURE_FLAGS['ab_rank_special_betting'] = True
    evaluator = BetTargetEvaluator()

    print("=" * 100)
    print("前付けレース × オッズ帯詳細分析（購入対象のみ）")
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

    # 購入対象のみカウント
    forward_by_odds = defaultdict(lambda: {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0})
    no_forward_by_odds = defaultdict(lambda: {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0})

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

        # オッズ帯
        if odds < 10:
            band = "0-10"
        elif odds < 20:
            band = "10-20"
        elif odds < 30:
            band = "20-30"
        elif odds < 50:
            band = "30-50"
        elif odds < 100:
            band = "50-100"
        else:
            band = "100+"

        bet_amount = result.bet_amount
        stats = forward_by_odds[band] if has_forward else no_forward_by_odds[band]
        stats['target'] += 1
        stats['bet'] += bet_amount

        # 的中判定
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        actual_results = cursor.fetchall()

        if len(actual_results) >= 3:
            actual_combo = f"{actual_results[0]['pit_number']}-{actual_results[1]['pit_number']}-{actual_results[2]['pit_number']}"

            if combo == actual_combo:
                cursor.execute('''
                    SELECT amount FROM payouts
                    WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                ''', (race_id, actual_combo))
                payout_row = cursor.fetchone()

                if payout_row:
                    payout = (bet_amount / 100) * payout_row['amount']
                    stats['hit'] += 1
                    stats['payout'] += payout

    conn.close()

    # 結果表示
    bands = ["0-10", "10-20", "20-30", "30-50", "50-100", "100+"]

    print("【前付けあり - 購入対象のみ】")
    print(f"{'オッズ帯':<10} {'購入数':>8} {'的中':>6} {'的中率':>8} {'ROI':>10} {'収支':>12}")
    print("-" * 60)

    total_forward = {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0}
    for band in bands:
        s = forward_by_odds[band]
        if s['target'] == 0:
            continue
        total_forward['target'] += s['target']
        total_forward['hit'] += s['hit']
        total_forward['bet'] += s['bet']
        total_forward['payout'] += s['payout']

        roi = s['payout'] / s['bet'] * 100 if s['bet'] > 0 else 0
        hit_rate = s['hit'] / s['target'] * 100 if s['target'] > 0 else 0
        profit = s['payout'] - s['bet']
        print(f"{band:<10} {s['target']:>8} {s['hit']:>6} {hit_rate:>7.2f}% {roi:>9.1f}% {profit:>+11,.0f}円")

    print("-" * 60)
    roi = total_forward['payout'] / total_forward['bet'] * 100 if total_forward['bet'] > 0 else 0
    hit_rate = total_forward['hit'] / total_forward['target'] * 100 if total_forward['target'] > 0 else 0
    profit = total_forward['payout'] - total_forward['bet']
    print(f"{'合計':<10} {total_forward['target']:>8} {total_forward['hit']:>6} {hit_rate:>7.2f}% {roi:>9.1f}% {profit:>+11,.0f}円")

    print()
    print("【前付けなし - 購入対象のみ】")
    print(f"{'オッズ帯':<10} {'購入数':>8} {'的中':>6} {'的中率':>8} {'ROI':>10} {'収支':>12}")
    print("-" * 60)

    total_no_forward = {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0}
    for band in bands:
        s = no_forward_by_odds[band]
        if s['target'] == 0:
            continue
        total_no_forward['target'] += s['target']
        total_no_forward['hit'] += s['hit']
        total_no_forward['bet'] += s['bet']
        total_no_forward['payout'] += s['payout']

        roi = s['payout'] / s['bet'] * 100 if s['bet'] > 0 else 0
        hit_rate = s['hit'] / s['target'] * 100 if s['target'] > 0 else 0
        profit = s['payout'] - s['bet']
        print(f"{band:<10} {s['target']:>8} {s['hit']:>6} {hit_rate:>7.2f}% {roi:>9.1f}% {profit:>+11,.0f}円")

    print("-" * 60)
    roi = total_no_forward['payout'] / total_no_forward['bet'] * 100 if total_no_forward['bet'] > 0 else 0
    hit_rate = total_no_forward['hit'] / total_no_forward['target'] * 100 if total_no_forward['target'] > 0 else 0
    profit = total_no_forward['payout'] - total_no_forward['bet']
    print(f"{'合計':<10} {total_no_forward['target']:>8} {total_no_forward['hit']:>6} {hit_rate:>7.2f}% {roi:>9.1f}% {profit:>+11,.0f}円")

    # 20-30倍帯を除外した場合の効果
    print()
    print("=" * 100)
    print("20-30倍帯除外のシミュレーション（前付けレースのみ対象）")
    print("=" * 100)

    excluded = forward_by_odds["20-30"]
    if excluded['target'] > 0:
        excluded_profit = excluded['payout'] - excluded['bet']
        print(f"\n除外対象: {excluded['target']}件, 的中{excluded['hit']}件, 収支 {excluded_profit:+,.0f}円")

        # 除外後の前付けレース成績
        new_forward = {
            'target': total_forward['target'] - excluded['target'],
            'hit': total_forward['hit'] - excluded['hit'],
            'bet': total_forward['bet'] - excluded['bet'],
            'payout': total_forward['payout'] - excluded['payout'],
        }
        new_roi = new_forward['payout'] / new_forward['bet'] * 100 if new_forward['bet'] > 0 else 0
        new_profit = new_forward['payout'] - new_forward['bet']
        old_roi = total_forward['payout'] / total_forward['bet'] * 100 if total_forward['bet'] > 0 else 0

        print(f"\n除外前: {total_forward['target']}件, ROI {old_roi:.1f}%, 収支 {profit:+,.0f}円")
        print(f"除外後: {new_forward['target']}件, ROI {new_roi:.1f}%, 収支 {new_profit:+,.0f}円")
        print(f"ROI変化: {new_roi - old_roi:+.1f}pt")

        if excluded_profit < 0:
            print(f"\n→ 赤字({excluded_profit:,.0f}円)の除外で収益改善！")
        else:
            print(f"\n→ 黒字({excluded_profit:+,.0f}円)を失うため除外は非推奨")


if __name__ == "__main__":
    main()
