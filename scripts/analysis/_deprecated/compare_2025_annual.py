#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2025年年間成績比較
ペアワイズスコアリング vs Baseline
"""

import sys
import os
sys.path.insert(0, '.')

import warnings
warnings.filterwarnings('ignore')

import sqlite3
import numpy as np
from datetime import datetime

from config.feature_flags import enable_feature, disable_feature

DB_PATH = 'data/boatrace.db'


def get_test_races(conn, start_date, end_date, limit=None):
    """テスト対象レースを取得"""
    cursor = conn.cursor()
    query = '''
        SELECT DISTINCT r.id, r.race_date
        FROM races r
        INNER JOIN results res ON res.race_id = r.id
        WHERE r.race_date BETWEEN ? AND ?
            AND res.is_invalid = 0
            AND EXISTS (
                SELECT 1 FROM entries e WHERE e.race_id = r.id
                GROUP BY e.race_id HAVING COUNT(*) = 6
            )
        ORDER BY r.race_date, r.id
    '''
    if limit:
        query += f' LIMIT {limit}'
    cursor.execute(query, (start_date, end_date))
    return [row[0] for row in cursor.fetchall()]


def get_race_results(conn, race_id):
    """レース結果を取得"""
    cursor = conn.cursor()
    cursor.execute('''
        SELECT pit_number, rank
        FROM results
        WHERE race_id = ? AND is_invalid = 0 AND rank IS NOT NULL
        ORDER BY CAST(rank AS INTEGER)
    ''', (race_id,))
    results = cursor.fetchall()
    if len(results) < 3:
        return None
    actual_order = [int(r[0]) for r in results[:3]]

    # 3連単オッズ
    combination = f"{actual_order[0]}-{actual_order[1]}-{actual_order[2]}"
    cursor.execute('''
        SELECT odds FROM trifecta_odds
        WHERE race_id = ? AND combination = ?
    ''', (race_id, combination))
    row = cursor.fetchone()
    odds = float(row[0]) if row else 0.0

    return {
        'actual_1st': actual_order[0],
        'actual_2nd': actual_order[1],
        'actual_3rd': actual_order[2],
        'odds': odds
    }


def get_race_features(conn, race_id):
    """レースの特徴量を取得"""
    import pandas as pd
    query = '''
    SELECT
        e.pit_number,
        e.win_rate,
        e.motor_second_rate
    FROM entries e
    WHERE e.race_id = ?
    ORDER BY e.pit_number
    '''
    df = pd.read_sql_query(query, conn, params=(race_id,))
    if len(df) == 6:
        df['total_score'] = df['win_rate'] * 10 + df['motor_second_rate'].fillna(0) * 0.5
    return df


def run_backtest(conn, race_ids, use_pairwise=False, pairwise_model=None, gamma=0.5):
    """バックテストを実行"""
    results = {
        'total': 0, 'hit_1st': 0, 'hit_2nd': 0, 'hit_3rd': 0,
        'hit_trifecta': 0, 'total_return': 0
    }

    for i, race_id in enumerate(race_ids):
        if (i + 1) % 1000 == 0:
            print(f"  処理中: {i+1}/{len(race_ids)}")

        try:
            actual = get_race_results(conn, race_id)
            if actual is None:
                continue

            race_features = get_race_features(conn, race_id)
            if len(race_features) != 6:
                continue

            # 簡易予測（勝率ベース）
            predictions = []
            for _, row in race_features.iterrows():
                predictions.append({
                    'pit_number': int(row['pit_number']),
                    'total_score': row.get('total_score', 50)
                })
            predictions.sort(key=lambda x: x['total_score'], reverse=True)

            # ペアワイズ適用
            if use_pairwise and pairwise_model is not None and pairwise_model.model is not None:
                predictions = pairwise_model.get_pairwise_adjusted_predictions(
                    predictions, race_features, gamma=gamma
                )

            results['total'] += 1

            pred_1st = predictions[0]['pit_number']
            pred_2nd = predictions[1]['pit_number']
            pred_3rd = predictions[2]['pit_number']

            if pred_1st == actual['actual_1st']:
                results['hit_1st'] += 1
            if pred_2nd == actual['actual_2nd']:
                results['hit_2nd'] += 1
            if pred_3rd == actual['actual_3rd']:
                results['hit_3rd'] += 1

            if (pred_1st == actual['actual_1st'] and
                pred_2nd == actual['actual_2nd'] and
                pred_3rd == actual['actual_3rd']):
                results['hit_trifecta'] += 1
                results['total_return'] += actual['odds'] * 100

        except Exception as e:
            continue

    return results


def calculate_metrics(results):
    """メトリクスを計算"""
    n = results['total']
    if n == 0:
        return {}

    return {
        'total': n,
        'hit_1st': results['hit_1st'],
        'hit_2nd': results['hit_2nd'],
        'hit_3rd': results['hit_3rd'],
        'hit_trifecta': results['hit_trifecta'],
        'rate_1st': results['hit_1st'] / n * 100,
        'rate_2nd': results['hit_2nd'] / n * 100,
        'rate_3rd': results['hit_3rd'] / n * 100,
        'rate_trifecta': results['hit_trifecta'] / n * 100,
        'roi': results['total_return'] / (n * 100) * 100
    }


def main():
    print("=" * 70)
    print("2025年 年間成績比較")
    print("ペアワイズスコアリング vs Baseline")
    print("=" * 70)
    print()

    conn = sqlite3.connect(DB_PATH)

    # 2025年全データ
    start_date = '2025-01-01'
    end_date = '2025-12-18'

    print(f"期間: {start_date} ~ {end_date}")

    # サンプリング（全データだと時間がかかるため3000レース）
    race_ids = get_test_races(conn, start_date, end_date, limit=3000)
    print(f"テストレース数: {len(race_ids)}")
    print()

    # ペアワイズモデル読み込み
    from src.ml.pairwise_rank_model import PairwiseRankModel
    pairwise_model = PairwiseRankModel(model_dir='models', db_path=DB_PATH)
    model_path = os.path.join('models', 'pairwise_rank.txt')
    if os.path.exists(model_path):
        pairwise_model.load('pairwise_rank')
        print("ペアワイズモデル読み込み完了")
    else:
        print("エラー: ペアワイズモデルが見つかりません")
        return
    print()

    # Baseline
    print("=== [1] Baseline（勝率ベース） ===")
    baseline_results = run_backtest(conn, race_ids, use_pairwise=False)
    baseline = calculate_metrics(baseline_results)
    print(f"  レース数: {baseline['total']}")
    print(f"  1着的中: {baseline['rate_1st']:.1f}% ({baseline['hit_1st']}件)")
    print(f"  2着的中: {baseline['rate_2nd']:.1f}% ({baseline['hit_2nd']}件)")
    print(f"  3着的中: {baseline['rate_3rd']:.1f}% ({baseline['hit_3rd']}件)")
    print(f"  3連単的中: {baseline['rate_trifecta']:.2f}% ({baseline['hit_trifecta']}件)")
    print(f"  ROI: {baseline['roi']:.1f}%")
    print()

    # ペアワイズ適用
    print("=== [2] ペアワイズスコアリング (gamma=0.5) ===")
    pairwise_results = run_backtest(conn, race_ids, use_pairwise=True,
                                     pairwise_model=pairwise_model, gamma=0.5)
    pairwise = calculate_metrics(pairwise_results)
    print(f"  レース数: {pairwise['total']}")
    print(f"  1着的中: {pairwise['rate_1st']:.1f}% ({pairwise['hit_1st']}件)")
    print(f"  2着的中: {pairwise['rate_2nd']:.1f}% ({pairwise['hit_2nd']}件)")
    print(f"  3着的中: {pairwise['rate_3rd']:.1f}% ({pairwise['hit_3rd']}件)")
    print(f"  3連単的中: {pairwise['rate_trifecta']:.2f}% ({pairwise['hit_trifecta']}件)")
    print(f"  ROI: {pairwise['roi']:.1f}%")
    print()

    # 比較
    print("=" * 70)
    print("=== 結果比較 ===")
    print("=" * 70)
    print()
    print("                | Baseline | Pairwise | 改善量")
    print("-" * 55)
    print(f"1着的中率       | {baseline['rate_1st']:6.1f}%  | {pairwise['rate_1st']:6.1f}%  | {pairwise['rate_1st']-baseline['rate_1st']:+.1f}pt")
    print(f"2着的中率       | {baseline['rate_2nd']:6.1f}%  | {pairwise['rate_2nd']:6.1f}%  | {pairwise['rate_2nd']-baseline['rate_2nd']:+.1f}pt")
    print(f"3着的中率       | {baseline['rate_3rd']:6.1f}%  | {pairwise['rate_3rd']:6.1f}%  | {pairwise['rate_3rd']-baseline['rate_3rd']:+.1f}pt")
    print(f"3連単的中率     | {baseline['rate_trifecta']:6.2f}%  | {pairwise['rate_trifecta']:6.2f}%  | {pairwise['rate_trifecta']-baseline['rate_trifecta']:+.2f}pt")
    print(f"ROI             | {baseline['roi']:6.1f}%  | {pairwise['roi']:6.1f}%  | {pairwise['roi']-baseline['roi']:+.1f}pt")
    print()

    conn.close()
    print("完了")


if __name__ == '__main__':
    main()
