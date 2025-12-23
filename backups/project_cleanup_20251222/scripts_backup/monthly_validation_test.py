#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
1ヶ月分の詳細検証スクリプト

quick_validation_test.pyで効果が確認できた場合の次ステップ
1ヶ月分（約1,500レース）で詳細なバックテストを実施

処理時間: 10-20分

使い方:
    python scripts/monthly_validation_test.py --year 2025 --month 6
"""
import sys
import os
from pathlib import Path
import sqlite3
import time
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.race_predictor import RacePredictor
from src.betting.bet_target_evaluator import BetTargetEvaluator
from config.settings import DATABASE_PATH


def get_monthly_races(db_path: str, year: str, month: str):
    """指定年月の全レースを取得"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 月のゼロ埋め
    month_str = f"{int(month):02d}"
    date_pattern = f"{year}-{month_str}-%"

    cursor.execute("""
        SELECT r.id, r.venue_code, r.race_number, r.race_date
        FROM races r
        INNER JOIN results res ON r.id = res.race_id
        WHERE r.race_date LIKE ?
        AND res.rank = '1'
        GROUP BY r.id
        ORDER BY r.race_date, r.venue_code, r.race_number
    """, (date_pattern,))

    races = cursor.fetchall()
    conn.close()

    return races


def monthly_validation_test(year: str = "2025", month: str = "6"):
    """
    1ヶ月分の詳細検証

    Args:
        year: 検証対象年
        month: 検証対象月
    """
    print("=" * 80)
    print("1ヶ月分詳細検証")
    print("=" * 80)
    print(f"対象: {year}年{month}月")
    print()

    start_time = time.time()

    # 1. 対象レース取得
    print("[1/3] 対象レースを取得中...")
    races = get_monthly_races(DATABASE_PATH, year, month)
    print(f"[OK] {len(races)}件のレースを取得")

    if len(races) == 0:
        print("[!] レースが見つかりませんでした")
        return

    # 2. 予測生成
    print("\n[2/3] 予測生成中...")
    predictor = RacePredictor(use_cache=True)
    evaluator = BetTargetEvaluator()

    predictions_data = []
    success_count = 0

    for idx, (race_id, venue_code, race_num, race_date) in enumerate(races, 1):
        if idx % 100 == 0:
            elapsed = time.time() - start_time
            remaining = (len(races) - idx) * (elapsed / idx)
            print(f"  進捗: {idx}/{len(races)} ({elapsed/60:.1f}分経過, 残り{remaining/60:.1f}分)")

        try:
            predictions = predictor.predict_race(race_id, use_beforeinfo=False)

            if predictions and len(predictions) >= 6:
                top3 = sorted(predictions, key=lambda x: x.get('rank_prediction', 99))[:3]
                confidence = top3[0].get('confidence', 'E')

                predictions_data.append({
                    'race_id': race_id,
                    'race_date': race_date,
                    'venue_code': venue_code,
                    'race_number': race_num,
                    'top3': [p['pit_number'] for p in top3],
                    'confidence': confidence,
                    'predictions': predictions
                })
                success_count += 1
        except:
            pass

    print(f"[OK] 予測生成完了: {success_count}/{len(races)}件")

    # 3. バックテスト
    print("\n[3/3] バックテスト実行中...")

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 統計用
    stats = {
        'total_predictions': len(predictions_data),
        'total_hits': 0,
        'purchase_count': 0,
        'total_investment': 0,
        'total_return': 0,
        'by_confidence': {},
        'by_month_week': {}
    }

    for pred_data in predictions_data:
        race_id = pred_data['race_id']
        predictions = pred_data['predictions']
        predicted_top3 = pred_data['top3']
        confidence = pred_data['confidence']

        # 実際の結果
        cursor.execute("""
            SELECT pit_number
            FROM results
            WHERE race_id = ?
            AND rank IN ('1', '2', '3')
            ORDER BY CAST(rank AS INTEGER)
        """, (race_id,))

        actual_results = cursor.fetchall()

        if len(actual_results) == 3:
            actual_top3 = [r[0] for r in actual_results]
            is_hit = (predicted_top3 == actual_top3)

            if is_hit:
                stats['total_hits'] += 1

            # 信頼度別統計
            if confidence not in stats['by_confidence']:
                stats['by_confidence'][confidence] = {
                    'total': 0, 'hits': 0, 'purchase': 0,
                    'investment': 0, 'return': 0
                }

            stats['by_confidence'][confidence]['total'] += 1
            if is_hit:
                stats['by_confidence'][confidence]['hits'] += 1

            # 購入判定
            should_buy, reason = evaluator.evaluate_race(race_id, predictions)

            if should_buy:
                stats['purchase_count'] += 1
                stats['by_confidence'][confidence]['purchase'] += 1

                bet_amount = 400  # パターンH
                stats['total_investment'] += bet_amount
                stats['by_confidence'][confidence]['investment'] += bet_amount

                # 払戻
                combination = f"{predicted_top3[0]}-{predicted_top3[1]}-{predicted_top3[2]}"

                cursor.execute("""
                    SELECT amount
                    FROM payouts
                    WHERE race_id = ?
                    AND bet_type = 'trifecta'
                    AND combination = ?
                """, (race_id, combination))

                payout_row = cursor.fetchone()
                if payout_row:
                    payout_amount = payout_row[0]
                    stats['total_return'] += payout_amount
                    stats['by_confidence'][confidence]['return'] += payout_amount

    conn.close()

    elapsed = time.time() - start_time

    # 結果表示
    print("\n" + "=" * 80)
    print("詳細検証結果")
    print("=" * 80)
    print(f"処理時間: {elapsed/60:.1f}分")
    print()
    print(f"【全体統計】")
    print(f"対象レース: {stats['total_predictions']}件")
    print(f"3連単的中: {stats['total_hits']}件")
    print(f"的中率: {stats['total_hits']/stats['total_predictions']*100:.2f}%")
    print()
    print(f"【購入対象統計】")
    print(f"購入レース数: {stats['purchase_count']}件")

    if stats['total_investment'] > 0:
        roi = stats['total_return'] / stats['total_investment'] * 100
        profit = stats['total_return'] - stats['total_investment']
        print(f"投資額: {stats['total_investment']:,}円")
        print(f"払戻額: {stats['total_return']:,}円")
        print(f"収支: {profit:+,}円")
        print(f"ROI: {roi:.1f}%")
    else:
        print("購入対象なし")

    print()
    print("【信頼度別詳細】")
    for conf in sorted(stats['by_confidence'].keys()):
        data = stats['by_confidence'][conf]
        hit_rate = data['hits'] / data['total'] * 100 if data['total'] > 0 else 0
        roi_val = data['return'] / data['investment'] * 100 if data['investment'] > 0 else 0

        print(f"  信頼度{conf}:")
        print(f"    的中率: {data['hits']}/{data['total']} = {hit_rate:.1f}%")
        if data['purchase'] > 0:
            print(f"    購入数: {data['purchase']}件")
            print(f"    ROI: {roi_val:.1f}% (収支: {data['return']-data['investment']:+,}円)")
        else:
            print(f"    購入数: 0件（フィルター未通過）")

    print("=" * 80)
    print()
    print("【次のステップ】")

    if stats['total_investment'] > 0:
        roi_val = stats['total_return'] / stats['total_investment'] * 100

        if roi_val >= 120:
            print("✅ 高い効果を確認 → 全期間再生成を推奨")
            print("   コマンド: python scripts/regenerate_predictions_2025_parallel.py")
        elif roi_val >= 100:
            print("⚠️  プラスだがROIがやや低い → 他の月でも検証を推奨")
            print("   コマンド: python scripts/monthly_validation_test.py --year 2025 --month 3")
        else:
            print("❌ マイナス収支 → ロジック調整を推奨")

    print("=" * 80)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='1ヶ月分詳細検証（10-20分）')
    parser.add_argument('--year', type=str, default='2025', help='検証対象年（デフォルト: 2025）')
    parser.add_argument('--month', type=str, default='6', help='検証対象月（デフォルト: 6）')

    args = parser.parse_args()

    monthly_validation_test(year=args.year, month=args.month)


if __name__ == "__main__":
    main()
