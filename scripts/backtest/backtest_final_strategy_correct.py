# -*- coding: utf-8 -*-
"""最終運用戦略のバックテスト（正確な払戻金使用版）

trifecta_oddsのオッズではなく、payoutsテーブルの実際の払戻金を使用
"""

import sys
import sqlite3
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    evaluator = BetTargetEvaluator()

    print("=" * 70)
    print("最終運用戦略 バックテスト（実際の払戻金使用）")
    print("=" * 70)
    print("検証対象: bet_target_evaluator.py の C,D 条件")
    print()

    # 2025年全期間
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')
    races = cursor.fetchall()

    stats = {
        'total': 0,
        'target_trifecta': 0,
        'hit_trifecta': 0,
        'bet_trifecta': 0,
        'payout_trifecta': 0,
        'by_confidence': {
            'A': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
            'B': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
            'C': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
            'D': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
        },
        'by_month': {}
    }

    for race in races:
        race_id = race['race_id']
        venue_code = int(race['venue_code']) if race['venue_code'] else 0
        month = race['race_date'][:7]  # YYYY-MM

        if month not in stats['by_month']:
            stats['by_month'][month] = {
                'target_trifecta': 0, 'hit_trifecta': 0,
                'bet_trifecta': 0, 'payout_trifecta': 0
            }

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

        stats['total'] += 1

        confidence = preds[0]['confidence']
        old_pred = [p['pit_number'] for p in preds[:3]]
        new_pred = old_pred

        old_combo = f"{old_pred[0]}-{old_pred[1]}-{old_pred[2]}"
        new_combo = f"{new_pred[0]}-{new_pred[1]}-{new_pred[2]}"

        # オッズ取得（判定用）
        cursor.execute('SELECT combination, odds FROM trifecta_odds WHERE race_id = ?', (race_id,))
        odds_rows = cursor.fetchall()
        odds_data = {row['combination']: row['odds'] for row in odds_rows}

        old_odds = odds_data.get(old_combo, 0)
        new_odds = odds_data.get(new_combo, 0)

        # 3連単判定
        result_trifecta = evaluator.evaluate(
            confidence=confidence,
            c1_rank=c1_rank,
            old_combo=old_combo,
            new_combo=new_combo,
            old_odds=old_odds,
            new_odds=new_odds,
            has_beforeinfo=True,
            venue_code=venue_code
        )

        if result_trifecta.status in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
            stats['target_trifecta'] += 1
            stats['bet_trifecta'] += result_trifecta.bet_amount
            stats['by_month'][month]['target_trifecta'] += 1
            stats['by_month'][month]['bet_trifecta'] += result_trifecta.bet_amount
            stats['by_confidence'][confidence]['target'] += 1
            stats['by_confidence'][confidence]['bet'] += result_trifecta.bet_amount

            # 実際の結果
            cursor.execute('''
                SELECT pit_number FROM results
                WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
                ORDER BY rank
            ''', (race_id,))
            results = cursor.fetchall()

            if len(results) >= 3:
                actual_combo = f"{results[0]['pit_number']}-{results[1]['pit_number']}-{results[2]['pit_number']}"

                if result_trifecta.combination == actual_combo:
                    # ★重要★ payoutsテーブルから実際の払戻金を取得
                    cursor.execute('''
                        SELECT amount FROM payouts
                        WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                    ''', (race_id, actual_combo))
                    payout_row = cursor.fetchone()

                    if payout_row:
                        stats['hit_trifecta'] += 1
                        # 払戻金は100円あたりなので、実際の賭け金に応じて計算
                        actual_payout = (result_trifecta.bet_amount / 100) * payout_row['amount']
                        stats['payout_trifecta'] += actual_payout
                        stats['by_month'][month]['hit_trifecta'] += 1
                        stats['by_month'][month]['payout_trifecta'] += actual_payout
                        stats['by_confidence'][confidence]['hit'] += 1
                        stats['by_confidence'][confidence]['payout'] += actual_payout

    conn.close()

    # 結果表示
    print("データ取得: {:,}レース（2025年全期間）".format(len(races)))
    print()
    print("=" * 70)
    print("バックテスト結果（2025年全期間）")
    print("=" * 70)
    print(f"総レース数: {stats['total']:,}")
    print()

    # 3連単
    if stats['target_trifecta'] > 0:
        hit_rate = stats['hit_trifecta'] / stats['target_trifecta'] * 100
        roi = stats['payout_trifecta'] / stats['bet_trifecta'] * 100
        profit = stats['payout_trifecta'] - stats['bet_trifecta']

        print("[3連単]")
        print(f"  購入: {stats['target_trifecta']}レース")
        print(f"  的中: {stats['hit_trifecta']}レース（的中率{hit_rate:.1f}%）")
        print(f"  賭け金: {stats['bet_trifecta']:,}円")
        print(f"  払戻: {stats['payout_trifecta']:,.0f}円")
        print(f"  収支: {profit:+,.0f}円")
        print(f"  ROI: {roi:.1f}%")
        print()

        # 信頼度別
        print("=" * 70)
        print("信頼度別内訳（3連単のみ）")
        print("=" * 70)
        for conf in ['C', 'D']:
            cstats = stats['by_confidence'][conf]
            if cstats['target'] > 0:
                chit_rate = cstats['hit'] / cstats['target'] * 100
                croi = cstats['payout'] / cstats['bet'] * 100 if cstats['bet'] > 0 else 0
                cprofit = cstats['payout'] - cstats['bet']
                print(f"信頼度{conf}:")
                print(f"  購入{cstats['target']}件, 的中{cstats['hit']}件, 的中率{chit_rate:.1f}%")
                print(f"  賭け金{cstats['bet']:,}円, 払戻{cstats['payout']:,.0f}円")
                print(f"  収支{cprofit:+,.0f}円, ROI {croi:.1f}%")
                print()

        # 月別ROI
        print("=" * 70)
        print("月別ROI（3連単）")
        print("=" * 70)
        for month in sorted(stats['by_month'].keys()):
            mstats = stats['by_month'][month]
            if mstats['target_trifecta'] > 0:
                mroi = mstats['payout_trifecta'] / mstats['bet_trifecta'] * 100
                print(f"{month}: ROI {mroi:6.1f}% ({mstats['target_trifecta']:3d}購入, {mstats['hit_trifecta']:2d}的中)")

    else:
        print("購入対象レースなし")

    print("=" * 70)


if __name__ == '__main__':
    main()
