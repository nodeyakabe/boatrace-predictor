# -*- coding: utf-8 -*-
"""高ROI条件の探索

信頼度 × 級別 × オッズ範囲 × 会場条件の組み合わせを網羅的に検証し、
高ROI条件を発見する
"""

import sys
import sqlite3
from pathlib import Path
from itertools import product

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


def test_condition(cursor, races, confidence, c1_rank, odds_min, odds_max, venue_filter, bet_amount):
    """特定条件でのバックテスト"""
    stats = {
        'target': 0,
        'hit': 0,
        'bet': 0,
        'payout': 0,
    }

    for race in races:
        race_id = race['race_id']
        venue_code = int(race['venue_code']) if race['venue_code'] else 0

        # 会場フィルタ適用
        if venue_filter:
            if venue_code not in venue_filter:
                continue

        # 1コース級別
        cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
        c1 = cursor.fetchone()
        c1_rank_actual = c1['racer_rank'] if c1 else 'B1'

        if c1_rank and c1_rank_actual != c1_rank:
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
        if confidence and conf_actual != confidence:
            continue

        pred = [p['pit_number'] for p in preds[:3]]
        combo = f"{pred[0]}-{pred[1]}-{pred[2]}"

        # オッズ取得
        cursor.execute('SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?', (race_id, combo))
        odds_row = cursor.fetchone()
        odds = odds_row['odds'] if odds_row else 0

        if odds == 0:
            continue

        # オッズ範囲チェック
        if odds < odds_min or odds >= odds_max:
            continue

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
                # 実際の払戻金を取得
                cursor.execute('''
                    SELECT amount FROM payouts
                    WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                ''', (race_id, actual_combo))
                payout_row = cursor.fetchone()

                if payout_row:
                    stats['hit'] += 1
                    actual_payout = (bet_amount / 100) * payout_row['amount']
                    stats['payout'] += actual_payout

    return stats


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=" * 70)
    print("高ROI条件の探索")
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

    print(f"検証期間: 2025年全期間")
    print(f"総レース数: {len(races):,}")
    print()

    # 探索パラメータ
    confidences = ['A', 'B', 'C', 'D', None]  # None = 全信頼度
    c1_ranks = ['A1', 'A2', 'B1', 'B2', None]  # None = 全級別
    odds_ranges = [
        (1, 5), (5, 10), (10, 15), (15, 20), (20, 30), (30, 40), (40, 50),
        (50, 70), (70, 100), (100, 150), (150, 200), (200, 300), (300, 500),
        # 広範囲
        (1, 10), (5, 15), (10, 20), (15, 30), (20, 40), (30, 50), (40, 70),
        (50, 100), (70, 150), (100, 200), (150, 300),
        # 特定範囲
        (5, 20), (10, 30), (15, 40), (20, 50), (25, 50), (30, 60),
    ]
    venue_filters = [
        None,  # 全会場
        [24, 19, 18],  # イン強会場（大村、下関、徳山）
        [1, 2, 3, 4, 5, 6],  # イン弱会場群
    ]
    bet_amount = 300  # 固定

    print("探索条件:")
    print(f"  信頼度: {len([c for c in confidences if c])}種類 + 全信頼度")
    print(f"  級別: {len([r for r in c1_ranks if r])}種類 + 全級別")
    print(f"  オッズ範囲: {len(odds_ranges)}種類")
    print(f"  会場フィルタ: {len(venue_filters)}種類")
    print(f"  総組み合わせ数: {len(confidences) * len(c1_ranks) * len(odds_ranges) * len(venue_filters):,}")
    print()
    print("検証開始...")
    print()

    high_roi_conditions = []
    total_combinations = 0

    for conf, c1, (odds_min, odds_max), venue_filter in product(confidences, c1_ranks, odds_ranges, venue_filters):
        total_combinations += 1

        stats = test_condition(cursor, races, conf, c1, odds_min, odds_max, venue_filter, bet_amount)

        # 最低30レース以上購入した条件のみ評価
        if stats['target'] >= 30:
            roi = stats['payout'] / stats['bet'] * 100 if stats['bet'] > 0 else 0
            hit_rate = stats['hit'] / stats['target'] * 100

            # ROI 120%以上または的中率8%以上の条件を保存
            if roi >= 120 or hit_rate >= 8:
                high_roi_conditions.append({
                    'confidence': conf if conf else '全',
                    'c1_rank': c1 if c1 else '全',
                    'odds_min': odds_min,
                    'odds_max': odds_max,
                    'venue_filter': venue_filter,
                    'target': stats['target'],
                    'hit': stats['hit'],
                    'hit_rate': hit_rate,
                    'bet': stats['bet'],
                    'payout': stats['payout'],
                    'roi': roi,
                    'profit': stats['payout'] - stats['bet'],
                })

    conn.close()

    print(f"総検証組み合わせ数: {total_combinations:,}")
    print(f"高ROI条件発見数: {len(high_roi_conditions)}")
    print()

    if high_roi_conditions:
        # ROI順にソート
        high_roi_conditions.sort(key=lambda x: x['roi'], reverse=True)

        print("=" * 70)
        print(f"高ROI条件 上位30件（ROI 120%以上 または 的中率8%以上）")
        print("=" * 70)
        print()

        for i, cond in enumerate(high_roi_conditions[:30], 1):
            venue_name = '全会場'
            if cond['venue_filter'] == [24, 19, 18]:
                venue_name = 'イン強'
            elif cond['venue_filter'] == [1, 2, 3, 4, 5, 6]:
                venue_name = 'イン弱'

            print(f"{i:2d}. 信頼度{cond['confidence']} × {cond['c1_rank']}級 × {cond['odds_min']}-{cond['odds_max']}倍 × {venue_name}")
            print(f"    購入{cond['target']:4d}, 的中{cond['hit']:3d}, 的中率{cond['hit_rate']:5.1f}%")
            print(f"    ROI {cond['roi']:6.1f}%, 収支{cond['profit']:+,.0f}円")
            print()

        # 収益順TOP10
        profit_sorted = sorted(high_roi_conditions, key=lambda x: x['profit'], reverse=True)
        print("=" * 70)
        print("収益額 上位10件")
        print("=" * 70)
        print()

        for i, cond in enumerate(profit_sorted[:10], 1):
            venue_name = '全会場'
            if cond['venue_filter'] == [24, 19, 18]:
                venue_name = 'イン強'
            elif cond['venue_filter'] == [1, 2, 3, 4, 5, 6]:
                venue_name = 'イン弱'

            print(f"{i:2d}. 信頼度{cond['confidence']} × {cond['c1_rank']}級 × {cond['odds_min']}-{cond['odds_max']}倍 × {venue_name}")
            print(f"    購入{cond['target']:4d}, 的中{cond['hit']:3d}, ROI {cond['roi']:6.1f}%")
            print(f"    収支{cond['profit']:+,.0f}円")
            print()

        # 的中率順TOP10
        hitrate_sorted = sorted(high_roi_conditions, key=lambda x: x['hit_rate'], reverse=True)
        print("=" * 70)
        print("的中率 上位10件")
        print("=" * 70)
        print()

        for i, cond in enumerate(hitrate_sorted[:10], 1):
            venue_name = '全会場'
            if cond['venue_filter'] == [24, 19, 18]:
                venue_name = 'イン強'
            elif cond['venue_filter'] == [1, 2, 3, 4, 5, 6]:
                venue_name = 'イン弱'

            print(f"{i:2d}. 信頼度{cond['confidence']} × {cond['c1_rank']}級 × {cond['odds_min']}-{cond['odds_max']}倍 × {venue_name}")
            print(f"    的中率{cond['hit_rate']:5.1f}%, 購入{cond['target']:4d}, 的中{cond['hit']:3d}")
            print(f"    ROI {cond['roi']:6.1f}%, 収支{cond['profit']:+,.0f}円")
            print()

    else:
        print("高ROI条件は見つかりませんでした")

    print("=" * 70)


if __name__ == '__main__':
    main()
