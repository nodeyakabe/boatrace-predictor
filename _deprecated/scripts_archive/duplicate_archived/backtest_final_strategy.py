# -*- coding: utf-8 -*-
"""
最終運用戦略バックテスト

残タスク一覧に記載の「最終運用戦略」をバックテストする
- 信頼度C: 従来方式、30-60倍/20-40倍、A1級
- 信頼度D: 新方式・従来、25-50倍/20-50倍、A1級
"""

import sys
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
from collections import defaultdict

# パス設定
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"

    print("=" * 70)
    print("最終運用戦略 バックテスト")
    print("=" * 70)
    print("検証対象: bet_target_evaluator.py の C,D 条件")
    print()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 2025年全期間
    cursor.execute('''
        SELECT
            r.id as race_id,
            r.venue_code,
            r.race_date,
            r.race_number
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')

    races = cursor.fetchall()
    print(f"データ取得: {len(races):,}レース（2025年全期間）")
    print()

    evaluator = BetTargetEvaluator()

    # 統計
    stats = {
        'total': 0,
        'target_trifecta': 0,
        'hit_trifecta': 0,
        'bet_trifecta': 0,
        'payout_trifecta': 0,
        'target_exacta': 0,
        'hit_exacta': 0,
        'bet_exacta': 0,
        'payout_exacta': 0,
        'by_month': defaultdict(lambda: {
            'target_trifecta': 0, 'hit_trifecta': 0, 'bet_trifecta': 0, 'payout_trifecta': 0,
            'target_exacta': 0, 'hit_exacta': 0, 'bet_exacta': 0, 'payout_exacta': 0,
        }),
        'by_confidence': defaultdict(lambda: {
            'target': 0, 'hit': 0, 'bet': 0, 'payout': 0,
        }),
    }

    for race in races:
        race_id = race['race_id']
        venue_code = int(race['venue_code']) if race['venue_code'] else 0
        race_date = race['race_date']
        month = race_date[:7]  # YYYY-MM

        # 1コース級別
        cursor.execute('''
            SELECT e.racer_rank
            FROM entries e
            WHERE e.race_id = ? AND e.pit_number = 1
        ''', (race_id,))
        c1 = cursor.fetchone()
        c1_rank = c1['racer_rank'] if c1 else 'B1'

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
        old_pred = [p['pit_number'] for p in preds[:3]]
        new_pred = old_pred

        # オッズ取得
        cursor.execute('''
            SELECT combination, odds
            FROM trifecta_odds
            WHERE race_id = ?
        ''', (race_id,))
        odds_rows = cursor.fetchall()
        odds_data = {row['combination']: row['odds'] for row in odds_rows}

        old_combo = f"{old_pred[0]}-{old_pred[1]}-{old_pred[2]}"
        new_combo = f"{new_pred[0]}-{new_pred[1]}-{new_pred[2]}"
        old_odds = odds_data.get(old_combo, 0)
        new_odds = odds_data.get(new_combo, 0)

        stats['total'] += 1

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
                    # オッズは100円あたりの払戻なので、賭け金100円として計算
                    payout = (result_trifecta.bet_amount / 100) * actual_odds
                    stats['payout_trifecta'] += payout
                    stats['by_month'][month]['hit_trifecta'] += 1
                    stats['by_month'][month]['payout_trifecta'] += payout
                    stats['by_confidence'][confidence]['hit'] += 1
                    stats['by_confidence'][confidence]['payout'] += payout

        # 2連単判定（スキップ - exacta_oddsテーブルが存在しない）
        # result_exacta = evaluator.evaluate_exacta(
        #     confidence=confidence,
        #     c1_rank=c1_rank,
        #     pred_1st=old_pred[0],
        #     pred_2nd=old_pred[1],
        # )

    conn.close()

    # 結果表示
    print("=" * 70)
    print("バックテスト結果（2025年全期間）")
    print("=" * 70)
    print(f"総レース数: {stats['total']:,}")
    print()

    # 3連単
    if stats['target_trifecta'] > 0:
        hit_rate_tri = stats['hit_trifecta'] / stats['target_trifecta'] * 100
        roi_tri = stats['payout_trifecta'] / stats['bet_trifecta'] * 100
        profit_tri = stats['payout_trifecta'] - stats['bet_trifecta']

        print("[3連単]")
        print(f"  購入: {stats['target_trifecta']}レース")
        print(f"  的中: {stats['hit_trifecta']}レース（的中率{hit_rate_tri:.1f}%）")
        print(f"  賭け金: {stats['bet_trifecta']:,}円")
        print(f"  払戻: {stats['payout_trifecta']:,.0f}円")
        print(f"  収支: {profit_tri:+,.0f}円")
        print(f"  ROI: {roi_tri:.1f}%")
        print()

    # 2連単
    if stats['target_exacta'] > 0:
        hit_rate_exa = stats['hit_exacta'] / stats['target_exacta'] * 100
        roi_exa = stats['payout_exacta'] / stats['bet_exacta'] * 100
        profit_exa = stats['payout_exacta'] - stats['bet_exacta']

        print("[2連単]")
        print(f"  購入: {stats['target_exacta']}レース")
        print(f"  的中: {stats['hit_exacta']}レース（的中率{hit_rate_exa:.1f}%）")
        print(f"  賭け金: {stats['bet_exacta']:,}円")
        print(f"  払戻: {stats['payout_exacta']:,.0f}円")
        print(f"  収支: {profit_exa:+,.0f}円")
        print(f"  ROI: {roi_exa:.1f}%")
        print()

    # 合計
    total_bet = stats['bet_trifecta'] + stats['bet_exacta']
    total_payout = stats['payout_trifecta'] + stats['payout_exacta']
    total_profit = total_payout - total_bet
    total_roi = total_payout / total_bet * 100 if total_bet > 0 else 0

    print("[合計]")
    print(f"  賭け金: {total_bet:,}円")
    print(f"  払戻: {total_payout:,.0f}円")
    print(f"  収支: {total_profit:+,.0f}円")
    print(f"  ROI: {total_roi:.1f}%")
    print()

    # 信頼度別
    print("=" * 70)
    print("信頼度別集計（3連単のみ）")
    print("=" * 70)
    for conf in ['C', 'D']:
        if stats['by_confidence'][conf]['target'] > 0:
            cstats = stats['by_confidence'][conf]
            chit_rate = cstats['hit'] / cstats['target'] * 100
            croi = cstats['payout'] / cstats['bet'] * 100
            cprofit = cstats['payout'] - cstats['bet']

            print(f"信頼度{conf}:")
            print(f"  購入{cstats['target']}件, 的中{cstats['hit']}件, 的中率{chit_rate:.1f}%")
            print(f"  賭け金{cstats['bet']:,}円, 払戻{cstats['payout']:,.0f}円")
            print(f"  収支{cprofit:+,.0f}円, ROI {croi:.1f}%")
            print()

    # 月別
    print("=" * 70)
    print("月別ROI（3連単）")
    print("=" * 70)
    for month in sorted(stats['by_month'].keys()):
        mstats = stats['by_month'][month]
        if mstats['target_trifecta'] > 0:
            mroi = mstats['payout_trifecta'] / mstats['bet_trifecta'] * 100
            print(f"{month}: ROI {mroi:6.1f}% ({mstats['target_trifecta']:3d}購入, {mstats['hit_trifecta']:2d}的中)")

    print("=" * 70)


if __name__ == '__main__':
    main()
