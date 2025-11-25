#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
本日のレース予測スクリプト
リアルタイムオッズを取得し、期待値ベースの推奨ベットを提示
"""

import sys
import os
import sqlite3
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 直接インポートして依存関係の問題を回避
from src.scraper.playwright_odds_scraper import PlaywrightOddsScraper
from src.ml.conditional_rank_model import ConditionalRankModel
from src.ml.probability_adjuster import ProbabilityAdjuster
from config.settings import VENUES


def get_race_features(db_path: str, venue_code: str, race_date: str, race_number: int) -> pd.DataFrame:
    """
    指定レースの特徴量を取得

    Args:
        db_path: データベースパス
        venue_code: 競艇場コード
        race_date: レース日付（YYYY-MM-DD）
        race_number: レース番号

    Returns:
        6行の特徴量DataFrame
    """
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


def get_today_schedule(db_path: str) -> list:
    """
    本日開催中の会場とレース情報を取得

    Returns:
        [{'venue_code': '02', 'venue_name': '戸田', 'races': [1,2,3,...12]}, ...]
    """
    today = datetime.now().strftime('%Y-%m-%d')

    with sqlite3.connect(db_path) as conn:
        query = """
            SELECT DISTINCT
                r.venue_code,
                r.race_number
            FROM races r
            WHERE r.race_date = ?
            ORDER BY r.venue_code, r.race_number
        """
        df = pd.read_sql_query(query, conn, params=(today,))

    if df.empty:
        return []

    # 会場ごとにグループ化
    schedule = {}
    for _, row in df.iterrows():
        venue_code = row['venue_code']
        race_number = row['race_number']

        if venue_code not in schedule:
            # 会場名を取得
            venue_name = None
            for venue_id, info in VENUES.items():
                if info['code'] == venue_code:
                    venue_name = info['name']
                    break
            venue_name = venue_name or f"会場{venue_code}"

            schedule[venue_code] = {
                'venue_code': venue_code,
                'venue_name': venue_name,
                'races': []
            }

        schedule[venue_code]['races'].append(race_number)

    return list(schedule.values())


def predict_single_race(odds_scraper, model, adjuster,
                         db_path: str,
                         venue_code: str,
                         venue_name: str,
                         race_date_yyyymmdd: str,
                         race_date_iso: str,
                         race_number: int) -> dict:
    """
    単一レースを予測

    Returns:
        予測結果辞書
    """
    print(f"\n{'='*60}")
    print(f"{venue_name} {race_number}R 予測")
    print(f"{'='*60}")

    # 特徴量取得
    features = get_race_features(db_path, venue_code, race_date_iso, race_number)

    if features.empty or len(features) != 6:
        print(f"[WARNING] 出走表データが不完全です（{len(features)}艇）")
        return None

    # オッズ取得
    print("オッズ取得中...")
    odds = odds_scraper.get_trifecta_odds(venue_code, race_date_yyyymmdd, race_number)

    if not odds:
        print("[ERROR] オッズ取得失敗")
        return None

    print(f"[OK] オッズ取得: {len(odds)}通り")

    # 確率予測
    print("確率計算中...")
    probs = model.predict_trifecta_probabilities(features)

    if not probs:
        print("[ERROR] 確率計算失敗")
        return None

    # 確率補正
    probs = adjuster.adjust_trifecta_probabilities(probs)
    print(f"[OK] 確率計算・補正完了: {len(probs)}通り")

    # 期待値計算
    ev_data = {}
    for combo in probs:
        prob = probs[combo]
        actual_odds = odds.get(combo, 0)

        if actual_odds > 0:
            ev = prob * actual_odds
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
        'probabilities_calculated': len(probs),
        'recommended_bets': recommended[:10],
        'top_10_by_probability': top10_prob_list,
        'top_10_by_expected_value': top10_ev_list
    }

    return result


def main():
    """メイン実行"""
    print("="*70)
    print("BoatRace リアルタイム予測システム")
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    db_path = "data/boatrace.db"

    if not os.path.exists(db_path):
        print(f"[ERROR] データベースが見つかりません: {db_path}")
        print("先にデータを収集してください")
        return

    # システム初期化
    print("\n予測システム初期化中...")
    odds_scraper = PlaywrightOddsScraper(headless=True, timeout=30000)
    model = ConditionalRankModel(model_dir='models')
    model.load('conditional_rank_v1')
    adjuster = ProbabilityAdjuster(adjustment_strength=0.7)
    print("[OK] 初期化完了")

    # 今日の日付
    today_iso = datetime.now().strftime('%Y-%m-%d')
    today_yyyymmdd = datetime.now().strftime('%Y%m%d')

    # 本日のスケジュール確認
    print(f"\n本日（{today_iso}）のスケジュールを確認...")
    schedule = get_today_schedule(db_path)

    if not schedule:
        print("[WARNING] 本日のレースデータがありません")
        print("直近のデータを使用してテストを実行します")

        # 直近のデータを取得
        with sqlite3.connect(db_path) as conn:
            query = """
                SELECT DISTINCT venue_code, race_date
                FROM races
                ORDER BY race_date DESC
                LIMIT 1
            """
            df = pd.read_sql_query(query, conn)

        if not df.empty:
            test_venue = df.iloc[0]['venue_code']
            test_date = df.iloc[0]['race_date']
            test_date_yyyymmdd = test_date.replace('-', '')

            venue_name = None
            for venue_id, info in VENUES.items():
                if info['code'] == test_venue:
                    venue_name = info['name']
                    break
            venue_name = venue_name or f"会場{test_venue}"

            print(f"\nテスト: {venue_name} ({test_date})")

            # 1Rを予測（オッズは今日のものを使用）
            result = predict_single_race(
                odds_scraper, model, adjuster, db_path,
                test_venue, venue_name,
                today_yyyymmdd, test_date, 1
            )

            if result:
                print("\n\n" + "="*70)
                print("予測完了")
                print("="*70)
                print(f"オッズデータ: {result['odds_retrieved']}通り")
                print(f"確率計算: {result['probabilities_calculated']}通り")
                print(f"推奨ベット数: {len(result['recommended_bets'])}通り")

                if result['recommended_bets']:
                    print("\n【期待値1.0以上の推奨ベット】")
                    for bet in result['recommended_bets'][:10]:
                        print(f"  {bet['rank']:2d}. {bet['combination']}: "
                              f"確率{bet['probability']*100:.2f}% × "
                              f"オッズ{bet['odds']:.1f}倍 = "
                              f"期待値{bet['expected_value']:.2f}")
    else:
        print(f"\n本日開催中: {len(schedule)}会場")
        for venue in schedule:
            print(f"  {venue['venue_name']}（{venue['venue_code']}）: "
                  f"{len(venue['races'])}R ({min(venue['races'])}R~{max(venue['races'])}R)")

        # 各会場の1Rを予測
        print("\n各会場の1Rを予測します...")

        for venue in schedule[:3]:  # 最大3会場
            venue_code = venue['venue_code']
            venue_name = venue['venue_name']

            if 1 in venue['races']:
                result = predict_single_race(
                    odds_scraper, model, adjuster, db_path,
                    venue_code, venue_name,
                    today_yyyymmdd, today_iso, 1
                )

                if result and result['recommended_bets']:
                    print(f"\n[{venue_name} 1R] 推奨ベットTop3:")
                    for bet in result['recommended_bets'][:3]:
                        print(f"  {bet['combination']}: 期待値{bet['expected_value']:.2f}")

    print("\n" + "="*70)
    print("予測完了")
    print("="*70)


if __name__ == "__main__":
    main()
