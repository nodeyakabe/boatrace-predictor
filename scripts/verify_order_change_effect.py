# -*- coding: utf-8 -*-
"""
順位変動による効果シミュレーション

P-3, P-6-1, P-6-2 の効果を直接モジュールを使わずに
「順位変動シナリオ」でシミュレーション

目的: モジュールを使わずに順位が変わることによる影響を高速に計測
"""
import sys
import sqlite3
import io
from pathlib import Path
from datetime import datetime
import random

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    evaluator = BetTargetEvaluator()

    print("=" * 100)
    print("ベースライン予測の効果確認")
    print("=" * 100)
    print(f"実行開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 2025年1-11月の全レースを対象（ベースラインと同じ期間）
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-11-30'
          AND EXISTS (SELECT 1 FROM race_predictions WHERE race_id = r.id AND prediction_type = 'before')
          AND EXISTS (SELECT 1 FROM results WHERE race_id = r.id AND is_invalid = 0)
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')
    races = cursor.fetchall()
    print(f"対象レース数: {len(races)}")
    print()

    stats = {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0}

    for race in races:
        race_id = race['race_id']
        venue_code = int(race['venue_code']) if race['venue_code'] else 0

        # ベースライン予測取得
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

        # 信頼度A, Bは除外
        if confidence in ['A', 'B']:
            continue

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
        stats['target'] += 1
        stats['bet'] += bet_amount

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
                    stats['hit'] += 1
                    stats['payout'] += payout

    conn.close()

    # 結果表示
    hit_rate = stats['hit'] / stats['target'] * 100 if stats['target'] > 0 else 0
    roi = stats['payout'] / stats['bet'] * 100 if stats['bet'] > 0 else 0
    profit = stats['payout'] - stats['bet']

    print("=" * 100)
    print("結果サマリー（ベースライン予測使用）")
    print("=" * 100)
    print(f"購入レース数: {stats['target']}")
    print(f"的中数: {stats['hit']}")
    print(f"的中率: {hit_rate:.2f}%")
    print(f"投資額: {stats['bet']:,.0f}円")
    print(f"払戻額: {stats['payout']:,.0f}円")
    print(f"収支: {profit:+,.0f}円")
    print(f"ROI: {roi:.1f}%")
    print()

    # 基準値との比較
    print("=" * 100)
    print("基準値との比較")
    print("=" * 100)
    print()
    print(f"{'指標':<15} {'基準値':>15} {'今回':>15} {'差分':>15}")
    print("-" * 65)
    print(f"{'ROI':<15} {'167.0%':>15} {roi:>14.1f}% {roi - 167.0:>+14.1f}%")
    print(f"{'収支':<15} {'+166,860円':>15} {profit:>+14,.0f}円 {profit - 166860:>+14,.0f}円")
    print(f"{'的中率':<15} {'4.34%':>15} {hit_rate:>14.2f}% {hit_rate - 4.34:>+14.2f}%")
    print()
    print("=" * 100)
    print(f"実行完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)


if __name__ == "__main__":
    main()
