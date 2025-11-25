#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
統合予測システムの動作テスト（昨日のデータ使用）
オッズ取得 → 確率計算 → 期待値計算の全フローを検証
"""

import sys
import os
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 直接インポートして依存関係の問題を回避
from src.scraper.playwright_odds_scraper import PlaywrightOddsScraper
from src.ml.conditional_rank_model import ConditionalRankModel


def get_race_features_from_db(db_path: str, venue_code: str, race_date: str, race_number: int):
    """DBから実際のレース特徴量を取得"""
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

    return df


def test_full_prediction():
    """統合予測システムの全フローテスト"""
    yesterday = datetime.now() - timedelta(days=1)
    race_date_iso = yesterday.strftime('%Y-%m-%d')
    race_date_yyyymmdd = yesterday.strftime('%Y%m%d')

    venue_code = '02'  # 戸田
    race_number = 1

    print("="*70)
    print("統合予測システム 全フローテスト")
    print(f"対象: {venue_code}場 {race_number}R ({race_date_iso})")
    print("="*70)

    db_path = 'data/boatrace.db'

    # 1. DBから特徴量を取得
    print("\n[1/4] データベースからレース特徴量を取得...")
    features = get_race_features_from_db(db_path, venue_code, race_date_iso, race_number)

    if features.empty or len(features) != 6:
        print(f"[ERROR] レースデータが不完全です（{len(features)}艇）")

        # ダミーデータで代替
        print("[INFO] ダミーデータで実行します")
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

    print(f"[OK] 特徴量取得完了: {features.shape}")
    print("\n出走表サマリー:")
    print(features[['pit_number', 'win_rate', 'racer_rank_score']].to_string(index=False))

    # 2. オッズスクレイパーとモデルを初期化
    print("\n[2/4] システム初期化...")
    odds_scraper = PlaywrightOddsScraper(headless=True, timeout=30000)
    model = ConditionalRankModel(model_dir='models')

    try:
        model.load('conditional_rank_v1')
        print(f"[OK] モデル読み込み完了: {len(model.feature_names)}特徴量")
    except Exception as e:
        print(f"[ERROR] モデル読み込み失敗: {e}")
        return False

    # 3. オッズ取得
    print(f"\n[3/4] オッズ取得...")
    odds = odds_scraper.get_trifecta_odds(venue_code, race_date_yyyymmdd, race_number)

    if not odds:
        print("[ERROR] オッズ取得失敗")
        return False

    print(f"[OK] オッズ取得成功: {len(odds)}通り")

    # 4. 確率計算
    print(f"\n[4/4] 確率計算と期待値分析...")
    probabilities = model.predict_trifecta_probabilities(features)

    if not probabilities:
        print("[ERROR] 確率計算失敗")
        return False

    print(f"[OK] 確率計算完了: {len(probabilities)}通り")

    # 期待値計算
    ev_data = {}
    for combo in probabilities:
        prob = probabilities[combo]
        actual_odds = odds.get(combo, 0)

        if actual_odds > 0:
            ev = prob * actual_odds
            b = actual_odds - 1
            kelly = max(0, (prob * actual_odds - (1 - prob)) / actual_odds if actual_odds > 0 else 0)

            ev_data[combo] = {
                'probability': prob,
                'odds': actual_odds,
                'expected_value': ev,
                'kelly_fraction': kelly
            }

    # 推奨ベット選定
    recommended = []
    for combo, data in ev_data.items():
        if data['expected_value'] >= 1.0 and data['probability'] >= 0.005:
            recommended.append({'combination': combo, **data})

    recommended.sort(key=lambda x: x['expected_value'], reverse=True)
    for i, bet in enumerate(recommended[:10], 1):
        bet['rank'] = i

    # Top10作成
    top10_prob = sorted(ev_data.items(), key=lambda x: x[1]['probability'], reverse=True)[:10]
    top10_prob_list = [{'combination': c, **d} for c, d in top10_prob]

    top10_ev = sorted(ev_data.items(), key=lambda x: x[1]['expected_value'], reverse=True)[:10]
    top10_ev_list = [{'combination': c, **d} for c, d in top10_ev]

    result = {
        'venue_code': venue_code,
        'race_date': race_date_yyyymmdd,
        'race_number': race_number,
        'odds_retrieved': len(odds),
        'probabilities_calculated': len(probabilities),
        'recommended_bets': recommended[:10],
        'top_10_by_probability': top10_prob_list,
        'top_10_by_expected_value': top10_ev_list
    }

    # 5. 結果を詳細表示
    if result:
        print("\n" + "="*70)
        print("[5/5] 分析結果")
        print("="*70)

        print(f"\nオッズデータ: {result['odds_retrieved']}通り取得")
        print(f"確率計算: {result['probabilities_calculated']}通り")
        print(f"推奨ベット数: {len(result['recommended_bets'])}通り")

        # 確率Top10
        print("\n【予測確率 Top10】")
        for i, item in enumerate(result['top_10_by_probability'][:10], 1):
            print(f"  {i:2d}. {item['combination']}: "
                  f"確率{item['probability']*100:5.2f}% × "
                  f"オッズ{item['odds']:7.1f}倍 = "
                  f"期待値{item['expected_value']:6.2f}")

        # 期待値Top10
        print("\n【期待値 Top10】")
        for i, item in enumerate(result['top_10_by_expected_value'][:10], 1):
            print(f"  {i:2d}. {item['combination']}: "
                  f"確率{item['probability']*100:5.2f}% × "
                  f"オッズ{item['odds']:7.1f}倍 = "
                  f"期待値{item['expected_value']:6.2f}")

        # 推奨ベット
        if result['recommended_bets']:
            print(f"\n【推奨ベット（期待値1.0以上）】{len(result['recommended_bets'])}通り")
            for bet in result['recommended_bets'][:10]:
                print(f"  {bet['rank']:2d}. {bet['combination']}: "
                      f"確率{bet['probability']*100:5.2f}% × "
                      f"オッズ{bet['odds']:7.1f}倍 = "
                      f"期待値{bet['expected_value']:6.2f} "
                      f"(Kelly={bet['kelly_fraction']*100:4.1f}%)")
        else:
            print("\n[INFO] 期待値1.0以上の組み合わせはありません")

        # 実際の結果と比較（DBにあれば）
        print("\n[6/6] 実際の結果と比較...")
        with sqlite3.connect(db_path) as conn:
            result_query = """
                SELECT
                    r.first_place,
                    r.second_place,
                    r.third_place
                FROM results r
                JOIN races ra ON r.race_id = ra.id
                WHERE ra.venue_code = ? AND ra.race_date = ? AND ra.race_number = ?
            """
            actual_result = pd.read_sql_query(
                result_query, conn,
                params=(venue_code, race_date_iso, race_number)
            )

        if not actual_result.empty:
            first = int(actual_result.iloc[0]['first_place'])
            second = int(actual_result.iloc[0]['second_place'])
            third = int(actual_result.iloc[0]['third_place'])
            actual_combo = f"{first}-{second}-{third}"

            print(f"\n実際の結果: {actual_combo}")

            # 予測確率と期待値を確認
            for item in result['top_10_by_probability']:
                if item['combination'] == actual_combo:
                    print(f"  確率順位: {result['top_10_by_probability'].index(item) + 1}位")
                    print(f"  予測確率: {item['probability']*100:.2f}%")
                    print(f"  実際のオッズ: {item['odds']:.1f}倍")
                    print(f"  期待値: {item['expected_value']:.2f}")
                    break
            else:
                # Top10外の場合
                print("  [INFO] 予測確率Top10外でした")
        else:
            print("[INFO] 実際の結果データがありません")

        return True
    else:
        print("\n[ERROR] 分析失敗")
        return False


if __name__ == "__main__":
    success = test_full_prediction()

    print("\n" + "="*70)
    if success:
        print("テスト完了: 成功")
    else:
        print("テスト完了: 失敗")
    print("="*70)

    sys.exit(0 if success else 1)
