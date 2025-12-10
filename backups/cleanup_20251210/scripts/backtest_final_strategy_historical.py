# -*- coding: utf-8 -*-
"""最終運用戦略の過去データバックテスト

2024年、2023年のデータで検証し、高ROI条件が存在したか確認
"""

import sys
import sqlite3
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus


def backtest_year(year: int):
    """指定年のバックテスト"""
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    evaluator = BetTargetEvaluator()

    # 指定年のレース取得
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE strftime('%Y', r.race_date) = ?
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''', (str(year),))

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

        # オッズ取得
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
                actual_odds = odds_data.get(actual_combo, 0)

                if result_trifecta.combination == actual_combo and actual_odds > 0:
                    stats['hit_trifecta'] += 1
                    payout = (result_trifecta.bet_amount / 100) * actual_odds
                    stats['payout_trifecta'] += payout
                    stats['by_month'][month]['hit_trifecta'] += 1
                    stats['by_month'][month]['payout_trifecta'] += payout
                    stats['by_confidence'][confidence]['hit'] += 1
                    stats['by_confidence'][confidence]['payout'] += payout

    conn.close()
    return stats


def main():
    print("=" * 70)
    print("最終運用戦略 過去データバックテスト")
    print("=" * 70)
    print("検証対象: bet_target_evaluator.py の C,D 条件")
    print()

    # 2024年、2023年を検証
    for year in [2024, 2023, 2022]:
        print(f"\n{'=' * 70}")
        print(f"{year}年バックテスト結果")
        print("=" * 70)

        stats = backtest_year(year)

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
            print("信頼度別内訳:")
            for conf in ['C', 'D']:
                cstats = stats['by_confidence'][conf]
                if cstats['target'] > 0:
                    chit_rate = cstats['hit'] / cstats['target'] * 100
                    croi = cstats['payout'] / cstats['bet'] * 100 if cstats['bet'] > 0 else 0
                    cprofit = cstats['payout'] - cstats['bet']
                    print(f"  信頼度{conf}: {cstats['target']}購入, {cstats['hit']}的中, "
                          f"的中率{chit_rate:.1f}%, ROI {croi:.1f}%, 収支{cprofit:+,.0f}円")

            print()

            # 月別ROI（上位5ヶ月と下位5ヶ月）
            monthly = []
            for month, mstats in stats['by_month'].items():
                if mstats['bet_trifecta'] > 0:
                    mroi = mstats['payout_trifecta'] / mstats['bet_trifecta'] * 100
                    monthly.append((month, mroi, mstats['target_trifecta'], mstats['hit_trifecta']))

            if len(monthly) > 0:
                monthly.sort(key=lambda x: x[1], reverse=True)
                print("月別ROI（上位5ヶ月）:")
                for month, mroi, target, hit in monthly[:5]:
                    print(f"  {month}: ROI {mroi:6.1f}% ({target:3d}購入, {hit:2d}的中)")

                print()
                print("月別ROI（下位5ヶ月）:")
                for month, mroi, target, hit in monthly[-5:]:
                    print(f"  {month}: ROI {mroi:6.1f}% ({target:3d}購入, {hit:2d}的中)")

        else:
            print("購入対象レースなし")

    print("\n" + "=" * 70)


if __name__ == '__main__':
    main()
