#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
モデルの5号艇・6号艇過大評価問題を分析
複数レースで予測と実際の結果を比較
"""

import sys
import os
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.ml.conditional_rank_model import ConditionalRankModel


def get_actual_result(db_path: str, venue_code: str, race_date: str, race_number: int):
    """実際のレース結果を取得"""
    with sqlite3.connect(db_path) as conn:
        query = """
            SELECT
                r.pit_number,
                r.rank
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            WHERE ra.venue_code = ? AND ra.race_date = ? AND ra.race_number = ?
            ORDER BY CAST(r.rank AS INTEGER)
        """
        df = pd.read_sql_query(query, conn, params=(venue_code, race_date, race_number))

    if len(df) >= 3:
        first = int(df.iloc[0]['pit_number'])
        second = int(df.iloc[1]['pit_number'])
        third = int(df.iloc[2]['pit_number'])
        return f"{first}-{second}-{third}", first, second, third
    else:
        return None, None, None, None


def get_race_features(db_path: str, venue_code: str, race_date: str, race_number: int):
    """レース特徴量を取得"""
    with sqlite3.connect(db_path) as conn:
        query = """
            SELECT
                e.pit_number,
                COALESCE(e.win_rate, 5.0) as win_rate,
                COALESCE(e.second_rate, 10.0) as second_rate,
                COALESCE(e.third_rate, 15.0) as third_rate,
                COALESCE(e.motor_second_rate, 30.0) as motor_2nd_rate,
                COALESCE(e.motor_third_rate, 40.0) as motor_3rd_rate,
                COALESCE(e.boat_second_rate, 30.0) as boat_2nd_rate,
                COALESCE(e.boat_third_rate, 40.0) as boat_3rd_rate,
                COALESCE(e.racer_weight, 52.0) as weight,
                COALESCE(e.avg_st, 0.15) as avg_st,
                COALESCE(e.local_win_rate, 20.0) as local_win_rate,
                CASE e.racer_rank
                    WHEN 'A1' THEN 4
                    WHEN 'A2' THEN 3
                    WHEN 'B1' THEN 2
                    ELSE 1
                END as racer_rank_score
            FROM entries e
            JOIN races r ON e.race_id = r.id
            WHERE r.venue_code = ? AND r.race_date = ? AND r.race_number = ?
            ORDER BY e.pit_number
        """
        df = pd.read_sql_query(query, conn, params=(venue_code, race_date, race_number))

    return df if len(df) == 6 else None


def analyze_model_predictions():
    """モデルの予測傾向を分析"""
    db_path = 'data/boatrace.db'

    # モデル読み込み
    print("="*70)
    print("モデル予測精度分析")
    print("="*70)

    print("\nモデル読み込み中...")
    model = ConditionalRankModel(model_dir='models')

    try:
        model.load('conditional_rank_v1')
        print(f"[OK] モデル読み込み完了: {len(model.feature_names)}特徴量")
    except Exception as e:
        print(f"[ERROR] モデル読み込み失敗: {e}")
        return

    # 2025年10月のレースを分析
    print("\n分析対象: 2025年10月（サンプル100レース）")
    print("-"*70)

    analysis_results = []
    pit_win_counts = defaultdict(int)
    pit_pred_win_counts = defaultdict(int)
    pit_top3_counts = defaultdict(int)
    pit_pred_top3_counts = defaultdict(int)

    total_races = 0
    top1_hits = 0
    top3_hits = 0
    top5_hits = 0

    # 10月の特定日を分析
    test_dates = [
        '2025-10-25', '2025-10-26', '2025-10-27',
        '2025-10-20', '2025-10-21',
        '2025-10-15', '2025-10-16'
    ]

    for date_str in test_dates:

        # その日のレース一覧を取得
        with sqlite3.connect(db_path) as conn:
            races_query = """
                SELECT DISTINCT venue_code, race_number
                FROM races
                WHERE race_date = ?
                LIMIT 30
            """
            races_df = pd.read_sql_query(races_query, conn, params=(date_str,))

        print(f"\n{date_str}: {len(races_df)}レース")

        for _, race_row in races_df.iterrows():
            venue_code = race_row['venue_code']
            race_number = race_row['race_number']

            # 特徴量取得
            features = get_race_features(db_path, venue_code, date_str, race_number)
            if features is None:
                continue

            # 実際の結果取得
            actual_combo, first, second, third = get_actual_result(db_path, venue_code, date_str, race_number)
            if actual_combo is None:
                continue

            # 予測
            try:
                probs = model.predict_trifecta_probabilities(features)
                if not probs:
                    continue

                # 確率順にソート
                sorted_probs = sorted(probs.items(), key=lambda x: x[1], reverse=True)

                # Top1の組み合わせ
                pred_combo = sorted_probs[0][0]
                pred_prob = sorted_probs[0][1]

                # 予測の1着
                pred_first = int(pred_combo.split('-')[0])

                # 実際の1着
                pit_win_counts[first] += 1
                pit_pred_win_counts[pred_first] += 1

                # Top3に入っているか
                for i, (third_place_pit, _) in enumerate(sorted_probs[:3]):
                    combo_parts = third_place_pit.split('-')
                    for part in combo_parts:
                        pit_pred_top3_counts[int(part)] += 1

                # 実際のTop3
                for pit in [first, second, third]:
                    pit_top3_counts[pit] += 1

                # 的中判定
                total_races += 1
                if actual_combo == pred_combo:
                    top1_hits += 1

                # Top3に含まれるか
                top3_combos = [c for c, _ in sorted_probs[:3]]
                if actual_combo in top3_combos:
                    top3_hits += 1

                # Top5に含まれるか
                top5_combos = [c for c, _ in sorted_probs[:5]]
                if actual_combo in top5_combos:
                    top5_hits += 1

                analysis_results.append({
                    'date': date_str,
                    'venue': venue_code,
                    'race': race_number,
                    'actual': actual_combo,
                    'actual_first': first,
                    'predicted': pred_combo,
                    'pred_first': pred_first,
                    'pred_prob': pred_prob,
                    'rank': next((i+1 for i, (c, _) in enumerate(sorted_probs) if c == actual_combo), 999)
                })

            except Exception as e:
                print(f"  [ERROR] {venue_code}-{race_number}: {e}")
                continue

    # 結果サマリー
    print("\n" + "="*70)
    print("分析結果サマリー")
    print("="*70)

    print(f"\n総分析レース数: {total_races}")

    if total_races == 0:
        print("[WARNING] 分析対象レースがありません")
        return

    print(f"Top1的中: {top1_hits} ({top1_hits/total_races*100:.1f}%)")
    print(f"Top3的中: {top3_hits} ({top3_hits/total_races*100:.1f}%)")
    print(f"Top5的中: {top5_hits} ({top5_hits/total_races*100:.1f}%)")

    # 艇番別の分析
    print("\n【実際の1着】艇番別勝率:")
    for pit in range(1, 7):
        count = pit_win_counts[pit]
        rate = count / total_races * 100 if total_races > 0 else 0
        print(f"  {pit}号艇: {count:3d}回 ({rate:5.1f}%)")

    print("\n【予測の1着】艇番別頻度:")
    for pit in range(1, 7):
        count = pit_pred_win_counts[pit]
        rate = count / total_races * 100 if total_races > 0 else 0
        print(f"  {pit}号艇: {count:3d}回 ({rate:5.1f}%)")

    # バイアス分析
    print("\n【バイアス分析】実際 vs 予測:")
    for pit in range(1, 7):
        actual = pit_win_counts[pit] / total_races * 100 if total_races > 0 else 0
        predicted = pit_pred_win_counts[pit] / total_races * 100 if total_races > 0 else 0
        diff = predicted - actual
        bias_label = "過大評価" if diff > 5 else "過小評価" if diff < -5 else "適正"

        print(f"  {pit}号艇: 実際{actual:5.1f}% vs 予測{predicted:5.1f}% (差{diff:+5.1f}%) [{bias_label}]")

    # 詳細結果の一部表示
    print("\n【予測詳細】最初の10レース:")
    print(f"{'日付':12s} {'場':3s} {'R':2s} {'実際':7s} {'予測':7s} {'確率':6s} {'順位':4s}")
    print("-"*70)
    for result in analysis_results[:10]:
        print(f"{result['date']:12s} {result['venue']:>3s} {result['race']:2d}R "
              f"{result['actual']:7s} {result['predicted']:7s} "
              f"{result['pred_prob']*100:5.2f}% {result['rank']:3d}位")


if __name__ == "__main__":
    analyze_model_predictions()
