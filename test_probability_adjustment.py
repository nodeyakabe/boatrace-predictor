#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
確率補正機能のテスト
補正前後で予測がどう変わるかを比較
"""

import sys
import os
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.scraper.playwright_odds_scraper import PlaywrightOddsScraper
from src.ml.conditional_rank_model import ConditionalRankModel
from src.ml.probability_adjuster import ProbabilityAdjuster


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


def test_probability_adjustment():
    """確率補正のテスト"""
    print("="*70)
    print("確率補正機能テスト")
    print("="*70)

    db_path = 'data/boatrace.db'
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    yesterday_yyyymmdd = yesterday.replace('-', '')

    venue_code = '02'  # 戸田
    race_number = 1

    print(f"\nテスト対象: {venue_code}場 {race_number}R ({yesterday})")

    # 特徴量取得
    features = get_race_features(db_path, venue_code, yesterday, race_number)

    if features is None or len(features) != 6:
        print(f"[ERROR] レースデータが不完全です")
        # ダミーデータで代替
        features = pd.DataFrame({
            'pit_number': [1, 2, 3, 4, 5, 6],
            'win_rate': [35.0, 15.0, 12.0, 10.0, 8.0, 5.0],
            'second_rate': [25.0, 20.0, 18.0, 15.0, 12.0, 10.0],
            'third_rate': [20.0, 22.0, 20.0, 18.0, 15.0, 12.0],
            'motor_2nd_rate': [35.0, 32.0, 30.0, 28.0, 25.0, 22.0],
            'motor_3rd_rate': [45.0, 42.0, 40.0, 38.0, 35.0, 32.0],
            'boat_2nd_rate': [33.0, 31.0, 29.0, 27.0, 25.0, 23.0],
            'boat_3rd_rate': [43.0, 41.0, 39.0, 37.0, 35.0, 33.0],
            'weight': [52.0, 51.5, 53.0, 52.5, 51.0, 54.0],
            'avg_st': [0.14, 0.15, 0.16, 0.15, 0.17, 0.18],
            'local_win_rate': [40.0, 25.0, 20.0, 15.0, 10.0, 5.0],
            'racer_rank_score': [4, 3, 3, 2, 2, 1]
        })

    # モデル読み込み
    print("\n1. モデル読み込み...")
    model = ConditionalRankModel(model_dir='models')
    model.load('conditional_rank_v1')
    print(f"   [OK] {len(model.feature_names)}特徴量")

    # 補正器初期化
    adjuster = ProbabilityAdjuster(adjustment_strength=0.7)

    # 確率予測（補正前）
    print("\n2. 確率予測（補正前）...")
    probs_before = model.predict_trifecta_probabilities(features)

    if not probs_before:
        print("   [ERROR] 予測失敗")
        return

    print(f"   [OK] {len(probs_before)}通り")

    # 確率予測（補正後）
    print("\n3. 確率補正適用...")
    probs_after = adjuster.adjust_trifecta_probabilities(probs_before)
    print(f"   [OK] 補正完了")

    # 結果比較
    print("\n" + "="*70)
    print("補正前後の比較")
    print("="*70)

    # 艇番別の1着予測頻度を集計
    pit_freq_before = defaultdict(float)
    pit_freq_after = defaultdict(float)

    for combo, prob in probs_before.items():
        first_pit = int(combo.split('-')[0])
        pit_freq_before[first_pit] += prob

    for combo, prob in probs_after.items():
        first_pit = int(combo.split('-')[0])
        pit_freq_after[first_pit] += prob

    print("\n【艇番別1着予測頻度】")
    print(f"{'艇番':4s} {'補正前':>8s} {'補正後':>8s} {'変化':>8s} {'実際':>8s} {'評価':10s}")
    print("-"*70)

    actual_rates = ProbabilityAdjuster.ACTUAL_WIN_RATES

    for pit in range(1, 7):
        before = pit_freq_before.get(pit, 0) * 100
        after = pit_freq_after.get(pit, 0) * 100
        actual = actual_rates.get(pit, 0) * 100
        change = after - before

        # 評価
        if abs(after - actual) < abs(before - actual):
            status = "[改善]"
        elif abs(after - actual) > abs(before - actual):
            status = "[悪化]"
        else:
            status = "[変化なし]"

        print(f"{pit}号艇 {before:7.2f}% {after:7.2f}% {change:+7.2f}% {actual:7.2f}% {status}")

    # Top10の比較
    print("\n【確率Top10の変化】")
    sorted_before = sorted(probs_before.items(), key=lambda x: x[1], reverse=True)[:10]
    sorted_after = sorted(probs_after.items(), key=lambda x: x[1], reverse=True)[:10]

    print("\n補正前:")
    for i, (combo, prob) in enumerate(sorted_before, 1):
        print(f"  {i:2d}. {combo}: {prob*100:5.2f}%")

    print("\n補正後:")
    for i, (combo, prob) in enumerate(sorted_after, 1):
        print(f"  {i:2d}. {combo}: {prob*100:5.2f}%")

    # オッズと組み合わせて期待値を計算
    print("\n4. オッズ取得して期待値計算...")
    odds_scraper = PlaywrightOddsScraper(headless=True, timeout=30000)
    odds = odds_scraper.get_trifecta_odds(venue_code, yesterday_yyyymmdd, race_number)

    if odds:
        print(f"   [OK] オッズ取得: {len(odds)}通り")

        # 期待値Top10（補正前）
        ev_before = {combo: probs_before.get(combo, 0) * odds.get(combo, 0) for combo in probs_before}
        top10_ev_before = sorted(ev_before.items(), key=lambda x: x[1], reverse=True)[:10]

        # 期待値Top10（補正後）
        ev_after = {combo: probs_after.get(combo, 0) * odds.get(combo, 0) for combo in probs_after}
        top10_ev_after = sorted(ev_after.items(), key=lambda x: x[1], reverse=True)[:10]

        print("\n【期待値Top10の変化】")
        print("\n補正前:")
        for i, (combo, ev) in enumerate(top10_ev_before, 1):
            prob = probs_before.get(combo, 0)
            odd = odds.get(combo, 0)
            print(f"  {i:2d}. {combo}: 確率{prob*100:5.2f}% × オッズ{odd:7.1f}倍 = 期待値{ev:5.2f}")

        print("\n補正後:")
        for i, (combo, ev) in enumerate(top10_ev_after, 1):
            prob = probs_after.get(combo, 0)
            odd = odds.get(combo, 0)
            print(f"  {i:2d}. {combo}: 確率{prob*100:5.2f}% × オッズ{odd:7.1f}倍 = 期待値{ev:5.2f}")

        # 1号艇がどう変化したか
        print("\n【1号艇絡みの組み合わせ】")
        one_combos_before = [(c, probs_before.get(c, 0), odds.get(c, 0)) for c in probs_before if c.startswith('1-')]
        one_combos_after = [(c, probs_after.get(c, 0), odds.get(c, 0)) for c in probs_after if c.startswith('1-')]

        one_combos_before.sort(key=lambda x: x[1], reverse=True)
        one_combos_after.sort(key=lambda x: x[1], reverse=True)

        print("\n補正前Top5:")
        for i, (combo, prob, odd) in enumerate(one_combos_before[:5], 1):
            ev = prob * odd
            print(f"  {i}. {combo}: 確率{prob*100:5.2f}% × オッズ{odd:6.1f}倍 = 期待値{ev:5.2f}")

        print("\n補正後Top5:")
        for i, (combo, prob, odd) in enumerate(one_combos_after[:5], 1):
            ev = prob * odd
            print(f"  {i}. {combo}: 確率{prob*100:5.2f}% × オッズ{odd:6.1f}倍 = 期待値{ev:5.2f}")

    print("\n" + "="*70)
    print("テスト完了")
    print("="*70)


if __name__ == "__main__":
    test_probability_adjustment()
