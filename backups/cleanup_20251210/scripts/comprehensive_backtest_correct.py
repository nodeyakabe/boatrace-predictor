# -*- coding: utf-8 -*-
"""包括的バックテスト（正確な払戻金使用版）

全ての条件を正しい払戻金データで検証し、残タスク一覧の期待ROIと照合
"""

import sys
import sqlite3
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


def test_condition(cursor, races, condition_name, filter_func):
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

        # 1コース級別
        cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
        c1 = cursor.fetchone()
        c1_rank = c1['racer_rank'] if c1 else 'B1'

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
        pred = [p['pit_number'] for p in preds[:3]]
        combo = f"{pred[0]}-{pred[1]}-{pred[2]}"

        # オッズ取得
        cursor.execute('SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?', (race_id, combo))
        odds_row = cursor.fetchone()
        odds = odds_row['odds'] if odds_row else 0

        # 条件フィルタ適用
        filter_result = filter_func(confidence, c1_rank, odds, venue_code, combo)
        if not filter_result:
            continue

        bet_amount = filter_result['bet_amount']
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
    print("包括的バックテスト（正確な払戻金使用）")
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

    print(f"検証期間: 2025年1月〜12月")
    print(f"総レース数: {len(races):,}")
    print()

    # 条件定義（残タスク一覧より）
    conditions = [
        {
            'name': 'C × 新方式 × 5-15倍 × A1',
            'expected_roi': 127.2,
            'filter': lambda conf, c1, odds, venue, combo:
                {'bet_amount': 500} if (conf == 'C' and c1 == 'A1' and 5 <= odds < 15) else None
        },
        {
            'name': 'C × 新方式 × 15-50倍 × A1',
            'expected_roi': 122.8,
            'filter': lambda conf, c1, odds, venue, combo:
                {'bet_amount': 400} if (conf == 'C' and c1 == 'A1' and 15 <= odds < 50) else None
        },
        {
            'name': 'D × 新方式 × 25-50倍 × A1',
            'expected_roi': 251.5,
            'filter': lambda conf, c1, odds, venue, combo:
                {'bet_amount': 300} if (conf == 'D' and c1 == 'A1' and 25 <= odds < 50) else None
        },
        {
            'name': 'D × 従来 × 20-50倍 × A1',
            'expected_roi': 215.7,
            'filter': lambda conf, c1, odds, venue, combo:
                {'bet_amount': 300} if (conf == 'D' and c1 == 'A1' and 20 <= odds < 50) else None
        },
        {
            'name': 'D × イン強会場 × 10-200倍 × B1',
            'expected_roi': 120.6,
            'filter': lambda conf, c1, odds, venue, combo:
                {'bet_amount': 300} if (conf == 'D' and c1 == 'B1' and venue in [24, 19, 18] and 10 <= odds < 200) else None
        },
    ]

    print("=" * 70)
    print("各条件の検証結果")
    print("=" * 70)
    print()

    all_results = []

    for cond in conditions:
        stats = test_condition(cursor, races, cond['name'], cond['filter'])

        if stats['target'] > 0:
            hit_rate = stats['hit'] / stats['target'] * 100
            roi = stats['payout'] / stats['bet'] * 100
            profit = stats['payout'] - stats['bet']

            result = {
                'name': cond['name'],
                'expected_roi': cond['expected_roi'],
                'actual_roi': roi,
                'target': stats['target'],
                'hit': stats['hit'],
                'hit_rate': hit_rate,
                'bet': stats['bet'],
                'payout': stats['payout'],
                'profit': profit,
            }
            all_results.append(result)

            print(f"条件: {cond['name']}")
            print(f"  購入: {stats['target']}レース")
            print(f"  的中: {stats['hit']}レース（的中率{hit_rate:.1f}%）")
            print(f"  賭け金: {stats['bet']:,}円")
            print(f"  払戻: {stats['payout']:,.0f}円")
            print(f"  収支: {profit:+,.0f}円")
            print(f"  実測ROI: {roi:.1f}%")
            print(f"  期待ROI: {cond['expected_roi']:.1f}%")
            print(f"  差分: {roi - cond['expected_roi']:+.1f}%")

            if roi >= cond['expected_roi'] * 0.9:  # 90%以上なら合格
                print(f"  判定: [OK] 期待ROI達成（90%以上）")
            elif roi >= cond['expected_roi'] * 0.7:  # 70%以上なら許容
                print(f"  判定: [WARN] 期待ROIにやや届かない（70-90%）")
            else:
                print(f"  判定: [NG] 期待ROI未達（70%未満）")
        else:
            print(f"条件: {cond['name']}")
            print(f"  購入対象レースなし")
            print(f"  判定: [NG] データ不足")

        print()

    conn.close()

    # サマリー
    print("=" * 70)
    print("総合サマリー")
    print("=" * 70)
    print()

    if all_results:
        total_bet = sum(r['bet'] for r in all_results)
        total_payout = sum(r['payout'] for r in all_results)
        total_profit = total_payout - total_bet
        overall_roi = total_payout / total_bet * 100 if total_bet > 0 else 0

        print(f"全条件合計:")
        print(f"  総賭け金: {total_bet:,}円")
        print(f"  総払戻: {total_payout:,.0f}円")
        print(f"  総収支: {total_profit:+,.0f}円")
        print(f"  総合ROI: {overall_roi:.1f}%")
        print()

        # ROI順にソート
        sorted_results = sorted(all_results, key=lambda x: x['actual_roi'], reverse=True)

        print("ROI上位3条件:")
        for i, r in enumerate(sorted_results[:3], 1):
            print(f"  {i}. {r['name']}: ROI {r['actual_roi']:.1f}% ({r['target']}購入, {r['hit']}的中)")
        print()

        print("的中数上位3条件:")
        sorted_by_hits = sorted(all_results, key=lambda x: x['hit'], reverse=True)
        for i, r in enumerate(sorted_by_hits[:3], 1):
            print(f"  {i}. {r['name']}: {r['hit']}的中 / {r['target']}購入 (的中率{r['hit_rate']:.1f}%)")

    print("=" * 70)


if __name__ == '__main__':
    main()
