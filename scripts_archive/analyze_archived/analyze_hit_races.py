# -*- coding: utf-8 -*-
"""
的中レースの配当分析

Opus分析がどのような計算をしていたか推測する
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
    print("信頼度D × イン強会場 × B1 の的中レース分析")
    print("=" * 70)
    print()

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

    hit_races = []

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
        c1_rank = c1['racer_rank'] if c1 else None

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

        confidence = preds[0]['confidence'] if preds else None

        if confidence != 'D':
            continue

        pred_combo = f"{preds[0]['pit_number']}-{preds[1]['pit_number']}-{preds[2]['pit_number']}"

        # 実際の結果
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        results = cursor.fetchall()

        if len(results) < 3:
            continue

        actual_combo = f"{results[0]['pit_number']}-{results[1]['pit_number']}-{results[2]['pit_number']}"

        # オッズ
        cursor.execute('''
            SELECT odds
            FROM trifecta_odds
            WHERE race_id = ? AND combination = ?
        ''', (race_id, actual_combo))
        odds_row = cursor.fetchone()
        actual_odds = odds_row['odds'] if odds_row else 0

        # 予測買い目のオッズ
        cursor.execute('''
            SELECT odds
            FROM trifecta_odds
            WHERE race_id = ? AND combination = ?
        ''', (race_id, pred_combo))
        pred_odds_row = cursor.fetchone()
        pred_odds = pred_odds_row['odds'] if pred_odds_row else 0

        # 的中判定
        is_hit = (pred_combo == actual_combo)

        if is_hit:
            hit_races.append({
                'race_id': race_id,
                'venue_code': venue_code,
                'date': race['race_date'],
                'race_no': race['race_number'],
                'combo': actual_combo,
                'odds': actual_odds,
            })

    conn.close()

    # 結果表示
    print(f"総的中レース数: {len(hit_races)}")
    print()

    if len(hit_races) > 0:
        print("的中レース一覧:")
        print("-" * 70)
        total_odds = 0
        for i, race in enumerate(hit_races, 1):
            venue_name = {24: '大村', 19: '下関', 18: '徳山'}.get(race['venue_code'], str(race['venue_code']))
            print(f"{i}. {race['date']} {venue_name} R{race['race_no']}: {race['combo']} = {race['odds']:.1f}倍")
            total_odds += race['odds']

        print("-" * 70)
        avg_odds = total_odds / len(hit_races)
        print(f"\n平均配当: {avg_odds:.1f}倍")
        print(f"合計配当: {total_odds:.1f}倍")
        print()

        # ROI計算（全レース購入した場合）
        print("=" * 70)
        print("仮想ROI計算")
        print("=" * 70)

        # パターン1: 的中レースのみ購入（Opus分析の可能性）
        roi_hit_only = (total_odds / len(hit_races)) * 100
        print(f"1. 的中レースのみ購入（{len(hit_races)}レース）: ROI {roi_hit_only:.1f}%")

        # パターン2: 実際のバックテスト（118レース購入、8的中）
        # 上記の結果から
        print(f"2. 全対象レース購入（118レース、{len(hit_races)}的中）: ROI 0.7%")

        print()
        print("Opus分析が「的中レースの平均配当」を見ていた場合:")
        print(f"  平均{avg_odds:.1f}倍 ≒ ROI {avg_odds:.1f}% (投資100円、払戻{avg_odds:.1f}円)")

    print("=" * 70)


if __name__ == '__main__':
    main()
