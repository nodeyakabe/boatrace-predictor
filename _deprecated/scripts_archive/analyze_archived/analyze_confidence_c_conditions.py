# -*- coding: utf-8 -*-
"""信頼度C条件の詳細分析

残タスク一覧に記載された信頼度Cの各条件を検証
"""

import sys
import sqlite3
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=" * 70)
    print("信頼度C条件の詳細分析（2025年全期間）")
    print("=" * 70)
    print()

    # 2025年全期間
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')
    races = cursor.fetchall()

    # 条件定義（残タスク一覧より）
    conditions = [
        {
            'name': 'C × 新方式 × 5-15倍 × A1',
            'confidence': 'C',
            'method': 'new',
            'odds_min': 5.0,
            'odds_max': 15.0,
            'c1_rank': 'A1',
            'expected_roi': 127.2,
        },
        {
            'name': 'C × 新方式 × 15-50倍 × A1',
            'confidence': 'C',
            'method': 'new',
            'odds_min': 15.0,
            'odds_max': 50.0,
            'c1_rank': 'A1',
            'expected_roi': 122.8,
        },
    ]

    for cond in conditions:
        print(f"条件: {cond['name']}")
        print(f"期待ROI: {cond['expected_roi']}%")
        print("-" * 70)

        stats = {
            'target': 0,
            'hit': 0,
            'bet': 0,
            'payout': 0,
        }

        for race in races:
            race_id = race['race_id']
            venue_code = int(race['venue_code']) if race['venue_code'] else 0

            # 1コース級別
            cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
            c1 = cursor.fetchone()
            c1_rank = c1['racer_rank'] if c1 else 'B1'

            if c1_rank != cond['c1_rank']:
                continue

            # 予測情報
            cursor.execute('''
                SELECT pit_number, confidence
                FROM race_predictions
                WHERE race_id = ? AND prediction_type = 'advance'
                ORDER BY rank_prediction
            ''', (race_id,))
            preds = cursor.fetchall()

            if len(preds) < 6:
                continue

            confidence = preds[0]['confidence']
            if confidence != cond['confidence']:
                continue

            # 買い目（新方式 = advance予測そのまま）
            pred = [p['pit_number'] for p in preds[:3]]
            combo = f"{pred[0]}-{pred[1]}-{pred[2]}"

            # オッズ取得
            cursor.execute('SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?', (race_id, combo))
            odds_row = cursor.fetchone()
            odds = odds_row['odds'] if odds_row else 0

            if odds == 0:
                continue

            # オッズ範囲チェック
            if not (cond['odds_min'] <= odds < cond['odds_max']):
                continue

            stats['target'] += 1
            stats['bet'] += 100  # 100円

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
                    stats['payout'] += odds

        # 結果表示
        if stats['target'] > 0:
            hit_rate = stats['hit'] / stats['target'] * 100
            roi = stats['payout'] / stats['bet'] * 100
            profit = stats['payout'] - stats['bet']

            print(f"購入: {stats['target']}レース")
            print(f"的中: {stats['hit']}レース（的中率{hit_rate:.1f}%）")
            print(f"賭け金: {stats['bet']:,}円")
            print(f"払戻: {stats['payout']:,.0f}円")
            print(f"収支: {profit:+,.0f}円")
            print(f"実測ROI: {roi:.1f}%")
            print(f"期待ROI: {cond['expected_roi']:.1f}%")
            print(f"差分: {roi - cond['expected_roi']:+.1f}%")
        else:
            print("購入対象レースなし")

        print()
        print()

    conn.close()


if __name__ == '__main__':
    main()
