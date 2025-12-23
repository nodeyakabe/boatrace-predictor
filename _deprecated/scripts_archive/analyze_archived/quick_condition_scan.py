# -*- coding: utf-8 -*-
"""クイック条件スキャン

信頼度×級別ごとに最適オッズ範囲を素早く発見
"""

import sys
import sqlite3
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


def scan_odds_ranges(cursor, races, confidence, c1_rank):
    """特定の信頼度×級別で、10倍刻みのオッズ範囲をスキャン"""

    # オッズ範囲（10倍刻み）
    odds_boundaries = [1, 5, 10, 15, 20, 25, 30, 40, 50, 70, 100, 150, 200, 300, 500, 1000]

    results = []

    for i in range(len(odds_boundaries) - 1):
        odds_min = odds_boundaries[i]
        odds_max = odds_boundaries[i + 1]

        stats = {
            'target': 0,
            'hit': 0,
            'bet': 0,
            'payout': 0,
        }

        for race in races:
            race_id = race['race_id']

            # 1コース級別
            cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
            c1 = cursor.fetchone()
            c1_rank_actual = c1['racer_rank'] if c1 else 'B1'

            if c1_rank_actual != c1_rank:
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

            conf_actual = preds[0]['confidence']
            if conf_actual != confidence:
                continue

            pred = [p['pit_number'] for p in preds[:3]]
            combo = f"{pred[0]}-{pred[1]}-{pred[2]}"

            # オッズ取得
            cursor.execute('SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?', (race_id, combo))
            odds_row = cursor.fetchone()
            odds = odds_row['odds'] if odds_row else 0

            if odds < odds_min or odds >= odds_max:
                continue

            stats['target'] += 1
            stats['bet'] += 300  # 固定300円

            # 実際の結果
            cursor.execute('''
                SELECT pit_number FROM results
                WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
                ORDER BY rank
            ''', (race_id,))
            results_rows = cursor.fetchall()

            if len(results_rows) >= 3:
                actual_combo = f"{results_rows[0]['pit_number']}-{results_rows[1]['pit_number']}-{results_rows[2]['pit_number']}"

                if combo == actual_combo:
                    # 実際の払戻金を取得
                    cursor.execute('''
                        SELECT amount FROM payouts
                        WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                    ''', (race_id, actual_combo))
                    payout_row = cursor.fetchone()

                    if payout_row:
                        stats['hit'] += 1
                        actual_payout = (300 / 100) * payout_row['amount']
                        stats['payout'] += actual_payout

        if stats['target'] > 0:
            roi = stats['payout'] / stats['bet'] * 100
            hit_rate = stats['hit'] / stats['target'] * 100
            profit = stats['payout'] - stats['bet']

            results.append({
                'odds_min': odds_min,
                'odds_max': odds_max,
                'target': stats['target'],
                'hit': stats['hit'],
                'hit_rate': hit_rate,
                'roi': roi,
                'profit': profit,
                'bet': stats['bet'],
                'payout': stats['payout'],
            })

    return results


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=" * 70)
    print("クイック条件スキャン（信頼度×級別）")
    print("=" * 70)
    print()

    # 2025年全期間のレース取得
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')
    races = cursor.fetchall()

    print(f"検証期間: 2025年全期間（{len(races):,}レース）")
    print()

    # 信頼度×級別の組み合わせ
    combinations = [
        ('A', 'A1'), ('A', 'A2'), ('A', 'B1'),
        ('B', 'A1'), ('B', 'A2'), ('B', 'B1'),
        ('C', 'A1'), ('C', 'A2'), ('C', 'B1'),
        ('D', 'A1'), ('D', 'A2'), ('D', 'B1'),
    ]

    all_high_roi = []

    for confidence, c1_rank in combinations:
        print(f"信頼度{confidence} × {c1_rank}級:")
        print("-" * 70)

        results = scan_odds_ranges(cursor, races, confidence, c1_rank)

        if results:
            # ROI順にソート
            results.sort(key=lambda x: x['roi'], reverse=True)

            # 上位5件表示
            for i, r in enumerate(results[:5], 1):
                if r['target'] >= 20:  # 20レース以上のみ
                    print(f"  {i}. {r['odds_min']}-{r['odds_max']:3d}倍: ", end='')
                    print(f"ROI {r['roi']:6.1f}%, 購入{r['target']:4d}, 的中{r['hit']:3d} ({r['hit_rate']:4.1f}%), ", end='')
                    print(f"収支{r['profit']:+8,.0f}円")

                    # 高ROI条件を記録
                    if r['roi'] >= 150:
                        all_high_roi.append({
                            'confidence': confidence,
                            'c1_rank': c1_rank,
                            'odds_min': r['odds_min'],
                            'odds_max': r['odds_max'],
                            'roi': r['roi'],
                            'target': r['target'],
                            'hit': r['hit'],
                            'hit_rate': r['hit_rate'],
                            'profit': r['profit'],
                        })
        else:
            print("  データなし")

        print()

    conn.close()

    # 高ROI条件サマリー
    if all_high_roi:
        print("=" * 70)
        print(f"超高ROI条件（150%以上）: {len(all_high_roi)}件")
        print("=" * 70)
        print()

        all_high_roi.sort(key=lambda x: x['roi'], reverse=True)

        for i, cond in enumerate(all_high_roi, 1):
            print(f"{i:2d}. 信頼度{cond['confidence']} × {cond['c1_rank']}級 × {cond['odds_min']}-{cond['odds_max']}倍")
            print(f"    ROI {cond['roi']:6.1f}%, 購入{cond['target']:4d}, 的中{cond['hit']:3d}, 収支{cond['profit']:+,.0f}円")
            print()

    print("=" * 70)


if __name__ == '__main__':
    main()
