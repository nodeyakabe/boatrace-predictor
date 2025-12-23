#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
予測ロジック変更の高速検証スクリプト

目的: 予測ロジックを変更したとき、全期間再生成する前に効果を素早く検証
処理時間: 5-10分（従来の1-2時間 → 90%削減）

使い方:
    python scripts/quick_validation_test.py --sample-size 200
"""
import sys
import os
from pathlib import Path
import sqlite3
import time
from datetime import datetime
import random

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.race_predictor import RacePredictor
from src.betting.bet_target_evaluator import BetTargetEvaluator
from config.settings import DATABASE_PATH


def get_random_race_sample(db_path: str, year: str, sample_size: int = 200):
    """指定年からランダムにレースをサンプリング"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 結果が確定しているレースのみ
    cursor.execute("""
        SELECT r.id, r.venue_code, r.race_number, r.race_date
        FROM races r
        INNER JOIN results res ON r.id = res.race_id
        WHERE r.race_date LIKE ? || '%'
        AND res.rank = '1'
        GROUP BY r.id
        ORDER BY RANDOM()
        LIMIT ?
    """, (year, sample_size))

    races = cursor.fetchall()
    conn.close()

    return races


def test_prediction_logic_fast(year: str = "2025", sample_size: int = 200):
    """
    予測ロジックの高速検証

    Args:
        year: 検証対象年度
        sample_size: サンプル数（デフォルト200件）
    """
    print("=" * 80)
    print("予測ロジック高速検証")
    print("=" * 80)
    print(f"対象年度: {year}")
    print(f"サンプル数: {sample_size}件")
    print()

    start_time = time.time()

    # 1. ランダムサンプリング
    print("[1/4] レースをランダムサンプリング中...")
    races = get_random_race_sample(DATABASE_PATH, year, sample_size)
    print(f"[OK] {len(races)}件のレースを抽出")

    # 2. 予測生成
    print("\n[2/4] 新しい予測ロジックで予測生成中...")
    predictor = RacePredictor(use_cache=True)
    evaluator = BetTargetEvaluator()

    predictions_data = []
    success_count = 0

    for idx, (race_id, venue_code, race_num, race_date) in enumerate(races, 1):
        if idx % 50 == 0:
            elapsed = time.time() - start_time
            print(f"  進捗: {idx}/{len(races)} ({elapsed:.1f}秒経過)")

        try:
            # 予測生成（advance = 直前情報なし）
            predictions = predictor.predict_race(race_id, use_beforeinfo=False)

            if predictions and len(predictions) >= 6:
                # Top3を抽出
                top3 = sorted(predictions, key=lambda x: x.get('rank_prediction', 99))[:3]
                confidence = top3[0].get('confidence', 'E')

                predictions_data.append({
                    'race_id': race_id,
                    'race_date': race_date,
                    'top3': [p['pit_number'] for p in top3],
                    'confidence': confidence,
                    'predictions': predictions
                })
                success_count += 1
        except Exception as e:
            pass

    print(f"[OK] 予測生成完了: {success_count}/{len(races)}件")

    # 3. 結果と照合して的中率計算
    print("\n[3/4] 的中率を計算中...")

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    hit_count = 0
    total_checked = 0
    confidence_stats = {}

    for pred_data in predictions_data:
        race_id = pred_data['race_id']
        predicted_top3 = pred_data['top3']
        confidence = pred_data['confidence']

        # 実際の結果を取得
        cursor.execute("""
            SELECT pit_number, rank
            FROM results
            WHERE race_id = ?
            AND rank IN ('1', '2', '3')
            ORDER BY CAST(rank AS INTEGER)
        """, (race_id,))

        actual_results = cursor.fetchall()

        if len(actual_results) == 3:
            actual_top3 = [r[0] for r in actual_results]

            # 3連単的中判定
            if predicted_top3 == actual_top3:
                hit_count += 1

            # 信頼度別統計
            if confidence not in confidence_stats:
                confidence_stats[confidence] = {'total': 0, 'hit': 0}

            confidence_stats[confidence]['total'] += 1
            if predicted_top3 == actual_top3:
                confidence_stats[confidence]['hit'] += 1

            total_checked += 1

    conn.close()

    # 4. バックテスト（購入判定 + ROI計算）
    print("\n[4/4] 簡易バックテスト実行中...")

    purchase_count = 0
    total_investment = 0
    total_return = 0

    conn = sqlite3.connect(DATABASE_PATH)

    for pred_data in predictions_data:
        race_id = pred_data['race_id']
        predictions = pred_data['predictions']

        # 購入判定
        should_buy, reason = evaluator.evaluate_race(race_id, predictions)

        if should_buy:
            purchase_count += 1
            bet_amount = 400  # パターンH: 1レース400円
            total_investment += bet_amount

            # 払戻を取得
            predicted_top3 = pred_data['top3']
            combination = f"{predicted_top3[0]}-{predicted_top3[1]}-{predicted_top3[2]}"

            cursor = conn.cursor()
            cursor.execute("""
                SELECT amount
                FROM payouts
                WHERE race_id = ?
                AND bet_type = 'trifecta'
                AND combination = ?
            """, (race_id, combination))

            payout_row = cursor.fetchone()
            if payout_row:
                total_return += payout_row[0]

    conn.close()

    # 結果表示
    elapsed = time.time() - start_time

    print("\n" + "=" * 80)
    print("検証結果")
    print("=" * 80)
    print(f"処理時間: {elapsed:.1f}秒 ({elapsed/60:.1f}分)")
    print()
    print(f"サンプル数: {total_checked}件")
    print(f"3連単的中: {hit_count}件")
    print(f"的中率: {hit_count/total_checked*100:.2f}%" if total_checked > 0 else "的中率: N/A")
    print()
    print("【信頼度別的中率】")
    for conf in sorted(confidence_stats.keys()):
        stats = confidence_stats[conf]
        hit_rate = stats['hit'] / stats['total'] * 100 if stats['total'] > 0 else 0
        print(f"  信頼度{conf}: {stats['hit']}/{stats['total']} = {hit_rate:.1f}%")
    print()
    print("【簡易バックテスト結果】")
    print(f"購入対象: {purchase_count}件")

    if total_investment > 0:
        roi = total_return / total_investment * 100
        profit = total_return - total_investment
        print(f"投資額: {total_investment:,}円")
        print(f"払戻額: {total_return:,}円")
        print(f"収支: {profit:+,}円")
        print(f"ROI: {roi:.1f}%")
    else:
        print("購入対象なし（フィルターが厳しすぎる可能性）")

    print("=" * 80)
    print()
    print("【次のステップ】")

    if total_checked > 0:
        hit_rate = hit_count / total_checked * 100

        if hit_rate >= 4.0 and purchase_count > 0:
            roi_val = total_return / total_investment * 100 if total_investment > 0 else 0
            if roi_val >= 100:
                print("✅ 効果あり → 1ヶ月分の詳細検証を推奨")
                print("   コマンド: python scripts/monthly_validation_test.py --year 2025 --month 6")
            else:
                print("⚠️  的中率は良いがROIが低い → フィルター調整を推奨")
        else:
            print("❌ 効果なし/悪化 → ロジック見直しを推奨")

    print("=" * 80)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='予測ロジック高速検証（5-10分）')
    parser.add_argument('--year', type=str, default='2025', help='検証対象年度（デフォルト: 2025）')
    parser.add_argument('--sample-size', type=int, default=200, help='サンプル数（デフォルト: 200）')

    args = parser.parse_args()

    test_prediction_logic_fast(year=args.year, sample_size=args.sample_size)


if __name__ == "__main__":
    main()
