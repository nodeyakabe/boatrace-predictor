# -*- coding: utf-8 -*-
"""
信頼度D × イン強会場 バックテスト（オッズフィルタなし）

Opus分析の再現：オッズ範囲フィルタを適用せず全レースを購入
"""

import sys
import sqlite3
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"

    print("=" * 70)
    print("信頼度D × イン強会場 バックテスト（オッズフィルタなし）")
    print("=" * 70)
    print("対象会場: 大村(24), 下関(19), 徳山(18)")
    print("信頼度: D")
    print("1コース級別: B1")
    print("オッズフィルタ: なし（全レース購入）")
    print()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 2025年1-7月
    cursor.execute('''
        SELECT
            r.id as race_id,
            r.venue_code,
            r.race_date,
            r.race_number
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-07-31'
          AND r.venue_code IN (24, 19, 18)
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')

    races = cursor.fetchall()
    print(f"データ取得: {len(races)}レース")
    print()

    stats = {
        'total': 0,
        'target': 0,
        'hit': 0,
        'bet': 0,
        'payout': 0,
    }

    bet_amount = 100  # 1レース100円

    for race in races:
        race_id = race['race_id']
        venue_code = int(race['venue_code']) if race['venue_code'] else 0

        # 1コース級別
        cursor.execute('''
            SELECT e.racer_rank
            FROM entries e
            WHERE e.race_id = ? AND e.pit_number = 1
        ''', (race_id,))
        c1 = cursor.fetchone()
        c1_rank = c1['racer_rank'] if c1 else 'B1'

        if c1_rank != 'B1':
            continue

        # 予測情報
        cursor.execute('''
            SELECT pit_number, rank_prediction, confidence
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'advance'
            ORDER BY rank_prediction
        ''', (race_id,))
        preds = cursor.fetchall()

        if len(preds) < 6:
            continue

        confidence = preds[0]['confidence'] if preds else 'E'

        if confidence != 'D':
            continue

        old_pred = [p['pit_number'] for p in preds[:3]]
        combo = f"{old_pred[0]}-{old_pred[1]}-{old_pred[2]}"

        # オッズ取得
        cursor.execute('''
            SELECT odds
            FROM trifecta_odds
            WHERE race_id = ? AND combination = ?
        ''', (race_id, combo))
        odds_row = cursor.fetchone()
        odds = odds_row['odds'] if odds_row else 0

        if odds == 0:
            continue

        stats['total'] += 1
        stats['target'] += 1
        stats['bet'] += bet_amount

        # 実際の結果
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        results = cursor.fetchall()

        if len(results) >= 3:
            actual_combo = f"{results[0]['pit_number']}-{results[1]['pit_number']}-{results[2]['pit_number']}"

            if combo == actual_combo:
                stats['hit'] += 1
                stats['payout'] += bet_amount * odds / 100

    conn.close()

    # 結果表示
    print("=" * 70)
    print("バックテスト結果")
    print("=" * 70)
    print(f"対象レース（D×イン強×B1）: {stats['total']}")
    print(f"購入レース: {stats['target']}")
    print()

    if stats['target'] > 0:
        hit_rate = stats['hit'] / stats['target'] * 100
        roi = stats['payout'] / stats['bet'] * 100 if stats['bet'] > 0 else 0
        profit = stats['payout'] - stats['bet']

        print(f"的中: {stats['hit']}レース")
        print(f"的中率: {hit_rate:.2f}%")
        print(f"賭け金: {stats['bet']:,}円")
        print(f"払戻: {stats['payout']:,.0f}円")
        print(f"収支: {profit:+,.0f}円")
        print(f"ROI: {roi:.1f}%")
        print()

        print("=" * 70)
        print("Opus分析との比較")
        print("=" * 70)
        print(f"Opus分析: ROI +120.6%, 156レース, 的中9レース, 的中率5.77%")
        print(f"実測値:   ROI {roi:.1f}%, {stats['target']}レース, 的中{stats['hit']}レース, 的中率{hit_rate:.2f}%")
        print()

        if abs(stats['target'] - 156) <= 5:
            print("[OK] レース数がOpus分析と一致")
        else:
            print(f"[INFO] レース数の差: {stats['target'] - 156:+d}")

        if abs(hit_rate - 5.77) < 1.0:
            print("[OK] 的中率がOpus分析と一致")

        if roi >= 120.6:
            print("[OK] ROIがOpus分析と一致")
        else:
            print(f"[NG] ROIの差: {roi - 120.6:+.1f}%")
    else:
        print("購入対象レースがありませんでした")

    print("=" * 70)


if __name__ == '__main__':
    main()
