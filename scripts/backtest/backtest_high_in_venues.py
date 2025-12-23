# -*- coding: utf-8 -*-
"""
信頼度D × イン強会場 バックテスト

Opus分析で発見した条件の検証:
- 信頼度D × イン強会場（大村/下関/徳山）
- 期待ROI: +53.1%
- 月間約47レース
"""

import sys
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# パス設定
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"

    print("=" * 70)
    print("信頼度D × イン強会場 バックテスト")
    print("=" * 70)
    print(f"対象会場: 大村(24), 下関(19), 徳山(18)")
    print(f"信頼度: D")
    print(f"1コース級別: B1")
    print()

    # データ取得
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 2025年1-7月のデータ（Opus分析と同じ期間）
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
    print(f"データ取得: {len(races)}レース（イン強会場の全レース）")
    print()

    # BetTargetEvaluatorで判定
    evaluator = BetTargetEvaluator()

    stats = {
        'total': 0,
        'target': 0,
        'hit': 0,
        'bet': 0,
        'payout': 0,
        'by_venue': {},
    }

    venue_names = {24: '大村', 19: '下関', 18: '徳山'}

    for race in races:
        race_id = race['race_id']
        venue_code = int(race['venue_code']) if race['venue_code'] else 0

        # 1コース級別を取得
        cursor.execute('''
            SELECT e.racer_rank
            FROM entries e
            WHERE e.race_id = ? AND e.pit_number = 1
        ''', (race_id,))
        c1 = cursor.fetchone()
        c1_rank = c1['racer_rank'] if c1 else 'B1'

        # B1のみ（Opus分析の結果に基づく）
        if c1_rank != 'B1':
            continue

        # 予測情報を取得（1位予測のconfidenceを確認）
        cursor.execute('''
            SELECT pit_number, rank_prediction, confidence
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'advance'
            ORDER BY rank_prediction
        ''', (race_id,))
        preds = cursor.fetchall()

        if len(preds) < 6:
            continue

        # 1位予測の信頼度を取得
        confidence = preds[0]['confidence'] if preds else 'E'

        # 信頼度Dのみ対象
        if confidence != 'D':
            continue

        old_pred = [p['pit_number'] for p in preds[:3]]
        new_pred = old_pred  # 従来方式と同じ

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

        # BetTargetEvaluatorで判定
        result = evaluator.evaluate(
            confidence='D',
            c1_rank=c1_rank,
            old_combo=old_combo,
            new_combo=new_combo,
            old_odds=old_odds,
            new_odds=new_odds,
            has_beforeinfo=True,
            venue_code=venue_code
        )

        # 購入対象かチェック
        if result.status in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
            stats['target'] += 1
            stats['bet'] += result.bet_amount

            # 実際の結果を取得
            cursor.execute('''
                SELECT pit_number FROM results
                WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
                ORDER BY rank
            ''', (race_id,))
            results = cursor.fetchall()

            if len(results) >= 3:
                actual_combo = f"{results[0]['pit_number']}-{results[1]['pit_number']}-{results[2]['pit_number']}"

                # 的中判定
                if result.combination == actual_combo:
                    stats['hit'] += 1
                    payout_odds = odds_data.get(actual_combo, 0)
                    stats['payout'] += result.bet_amount * payout_odds / 100

            # 会場別集計
            venue_name = venue_names.get(venue_code, str(venue_code))
            if venue_name not in stats['by_venue']:
                stats['by_venue'][venue_name] = {
                    'target': 0, 'hit': 0, 'bet': 0, 'payout': 0
                }
            stats['by_venue'][venue_name]['target'] += 1
            stats['by_venue'][venue_name]['bet'] += result.bet_amount
            if result.combination == actual_combo:
                stats['by_venue'][venue_name]['hit'] += 1
                stats['by_venue'][venue_name]['payout'] += result.bet_amount * payout_odds / 100

    conn.close()

    # 結果表示
    print("=" * 70)
    print("バックテスト結果")
    print("=" * 70)
    print(f"総レース数（D×イン強会場×B1）: {stats['total']}")
    print(f"購入対象: {stats['target']}レース")
    print()

    if stats['target'] > 0:
        hit_rate = stats['hit'] / stats['target'] * 100
        roi = stats['payout'] / stats['bet'] * 100 if stats['bet'] > 0 else 0
        profit = stats['payout'] - stats['bet']

        print(f"[3連単]")
        print(f"  購入: {stats['target']}レース")
        print(f"  的中: {stats['hit']}レース")
        print(f"  的中率: {hit_rate:.1f}%")
        print(f"  賭け金: {stats['bet']:,}円")
        print(f"  払戻: {stats['payout']:,.0f}円")
        print(f"  収支: {profit:+,.0f}円")
        print(f"  ROI: {roi:.1f}%")
        print()

        print("=" * 70)
        print("会場別集計")
        print("=" * 70)
        for venue_name, vstats in stats['by_venue'].items():
            if vstats['target'] > 0:
                vhit_rate = vstats['hit'] / vstats['target'] * 100
                vroi = vstats['payout'] / vstats['bet'] * 100 if vstats['bet'] > 0 else 0
                vprofit = vstats['payout'] - vstats['bet']

                print(f"{venue_name}:")
                print(f"  購入: {vstats['target']}レース, 的中: {vstats['hit']}レース, 的中率: {vhit_rate:.1f}%")
                print(f"  賭け金: {vstats['bet']:,}円, 払戻: {vstats['payout']:,.0f}円")
                print(f"  収支: {vprofit:+,.0f}円, ROI: {vroi:.1f}%")
                print()

        print("=" * 70)
        print("Opus分析との比較")
        print("=" * 70)
        print(f"Opus分析: ROI +120.6%, 156レース/7ヶ月, 的中率 5.77%")
        print(f"実測値:   ROI {roi:.1f}% (差分{roi-100:+.1f}%), {stats['target']}レース/7ヶ月, 的中率 {hit_rate:.1f}%")
        print()

        if roi >= 120.6:
            print("[OK] 期待ROIを達成！")
        elif roi >= 115.0:
            print("[WARN] 期待ROIには届かないが、黒字を維持")
        else:
            print("[NG] ROI基準未達（115%未満）")
    else:
        print("購入対象レースがありませんでした")

    print("=" * 70)


if __name__ == '__main__':
    main()
