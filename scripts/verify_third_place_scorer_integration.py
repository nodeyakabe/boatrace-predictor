#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ThirdPlaceSpecializedScorer統合の効果測定スクリプト
============================================================

P-6-1タスク: TrifectaCalculatorへのThirdPlaceSpecializedScorer統合効果を検証

検証日: 2025-12-20
目的: 決まり手別3着予測がTrifectaCalculatorに統合されたことによる精度改善を測定

検証項目:
1. 3着的中率の改善（1着・2着正解時）
2. 三連単的中率の改善
3. 決まり手別の精度比較

参考値（P-5分析結果）:
- 現状3着精度: 1着○2着○時でも38.7%
- 決まり手「逃げ」: 81.6%精度（強い）
- 決まり手「まくり差し」: 13.5%精度（弱い）
"""

import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import warnings
warnings.filterwarnings('ignore')
os.environ['PYTHONWARNINGS'] = 'ignore'

from src.prediction.trifecta_calculator import TrifectaCalculator
from config.feature_flags import set_feature_flag, is_feature_enabled
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
from collections import defaultdict

# データベースパス
DB_PATH = str(Path(__file__).parent.parent / "data" / "boatrace.db")

def get_race_features(conn, race_id):
    """レースの特徴量を取得（6艇分）

    重複エントリーがある場合は、pit_number毎に最初の1件を使用
    """
    query = '''
        SELECT
            e.race_id,
            e.pit_number,
            e.racer_number,
            COALESCE(e.win_rate, 0.0) as win_rate,
            COALESCE(e.second_rate, 0.0) as second_rate,
            COALESCE(e.third_rate, 0.0) as third_rate,
            COALESCE(e.local_win_rate, 0.0) as local_win_rate,
            COALESCE(e.local_second_rate, 0.0) as local_second_rate,
            COALESCE(e.local_third_rate, 0.0) as local_third_rate,
            COALESCE(e.motor_second_rate, 0.0) as motor_second_rate,
            COALESCE(e.motor_third_rate, 0.0) as motor_third_rate,
            COALESCE(e.boat_second_rate, 0.0) as boat_second_rate,
            COALESCE(e.boat_third_rate, 0.0) as boat_third_rate,
            COALESCE(e.avg_st, 0.0) as avg_st,
            COALESCE(e.f_count, 0) as f_count,
            COALESCE(e.l_count, 0) as l_count
        FROM entries e
        WHERE e.race_id = ?
        ORDER BY e.pit_number, e.id
    '''
    df = pd.read_sql_query(query, conn, params=(race_id,))

    # 重複がある場合は、pit_number毎に最初の1件を使用
    if len(df) > 6:
        df = df.drop_duplicates(subset=['pit_number'], keep='first')

    # 6艇以外の場合は空のDataFrameを返す
    if len(df) != 6:
        return pd.DataFrame()

    # pit_numberが1-6の順になるようにリセット
    df = df.sort_values('pit_number').reset_index(drop=True)

    return df

def get_race_result(conn, race_id):
    """レース結果を取得"""
    query = '''
        SELECT pit_number, rank, kimarite
        FROM results
        WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
        ORDER BY rank
    '''
    cursor = conn.cursor()
    cursor.execute(query, (race_id,))
    rows = cursor.fetchall()

    if len(rows) < 3:
        return None

    return {
        'first': rows[0][0],
        'second': rows[1][0],
        'third': rows[2][0],
        'kimarite': rows[0][2],  # 1着の決まり手
        'trifecta': f"{rows[0][0]}-{rows[1][0]}-{rows[2][0]}"
    }

def evaluate_calculator(conn, race_ids, use_third_place_scorer=True, verbose=False):
    """TrifectaCalculatorの精度を評価"""

    # TrifectaCalculatorの初期化
    # モデル名は'hierarchical'を使用（デフォルトの'conditional'はファイルが存在しない）
    calculator = TrifectaCalculator(
        model_dir='models',
        model_name='hierarchical',
        use_third_place_scorer=use_third_place_scorer
    )

    results = {
        'total': 0,
        'trifecta_hits': 0,
        'third_hits_given_12': 0,  # 1着・2着正解時の3着正解数
        'first_second_correct': 0,  # 1着・2着両方正解数
        'kimarite_stats': defaultdict(lambda: {'total': 0, 'third_hits': 0})
    }

    for i, race_id in enumerate(race_ids):
        if verbose and i % 50 == 0:
            print(f"  進捗: {i}/{len(race_ids)}", end="\r")

        try:
            # 特徴量取得
            features = get_race_features(conn, race_id)
            if features.empty or len(features) != 6:
                continue

            # 結果取得
            result = get_race_result(conn, race_id)
            if result is None:
                continue

            # 三連単確率計算
            try:
                probs = calculator.calculate(features, pit_column='pit_number')
            except Exception as e:
                if verbose:
                    print(f"\n  計算エラー: {race_id} - {e}")
                continue

            if not probs:
                continue

            # 上位3通りを取得
            top3 = sorted(probs.items(), key=lambda x: x[1], reverse=True)[:3]
            if not top3:
                continue

            pred_trifecta = top3[0][0]

            # 予測の1着・2着・3着を取得
            pred_parts = pred_trifecta.split('-')
            if len(pred_parts) < 3:
                continue

            pred_first = int(pred_parts[0])
            pred_second = int(pred_parts[1])
            pred_third = int(pred_parts[2])

            results['total'] += 1

            # 三連単的中判定
            if pred_trifecta == result['trifecta']:
                results['trifecta_hits'] += 1

            # 1着・2着両方正解の場合
            if pred_first == result['first'] and pred_second == result['second']:
                results['first_second_correct'] += 1

                # 3着も正解か
                if pred_third == result['third']:
                    results['third_hits_given_12'] += 1

                # 決まり手別の統計
                kimarite = result['kimarite'] or 'unknown'
                results['kimarite_stats'][kimarite]['total'] += 1
                if pred_third == result['third']:
                    results['kimarite_stats'][kimarite]['third_hits'] += 1

        except Exception as e:
            if verbose:
                print(f"\n  エラー: {race_id} - {e}")
                import traceback
                traceback.print_exc()
            continue

    if verbose:
        print(f"  完了: {len(race_ids)}/{len(race_ids)}")

    return results

def verify_integration(num_races=200, verbose=True):
    """ThirdPlaceSpecializedScorer統合の効果検証"""

    print("=" * 80)
    print("ThirdPlaceSpecializedScorer統合 効果検証")
    print("P-6-1タスク: TrifectaCalculatorへの決まり手別3着予測統合")
    print("=" * 80)
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"検証レース数: {num_races}")
    print()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 結果が存在するレースを取得（エントリーは重複対応済み）
    cursor.execute('''
        SELECT DISTINCT r.id
        FROM races r
        INNER JOIN entries e ON e.race_id = r.id
        INNER JOIN results res ON res.race_id = r.id
        WHERE res.is_invalid = 0
            AND res.rank <= 3
        GROUP BY r.id
        HAVING COUNT(DISTINCT e.pit_number) = 6
            AND COUNT(DISTINCT CASE WHEN res.rank <= 3 THEN res.rank END) >= 3
        ORDER BY r.race_date DESC, r.id DESC
        LIMIT ?
    ''', (num_races,))
    race_ids = [row[0] for row in cursor.fetchall()]

    print(f"[DATA] 取得レース数: {len(race_ids)}")
    print()

    # ========================================
    # ベースライン測定（機能無効）
    # ========================================
    print("[1/2] ベースライン測定（ThirdPlaceSpecializedScorer無効）")
    print("-" * 80)

    baseline_results = evaluate_calculator(conn, race_ids, use_third_place_scorer=False, verbose=verbose)

    baseline_trifecta_rate = baseline_results['trifecta_hits'] / baseline_results['total'] if baseline_results['total'] > 0 else 0
    baseline_third_rate = baseline_results['third_hits_given_12'] / baseline_results['first_second_correct'] if baseline_results['first_second_correct'] > 0 else 0

    print(f"  検証レース数: {baseline_results['total']}")
    print(f"  三連単的中率: {baseline_trifecta_rate:.4%} ({baseline_results['trifecta_hits']}/{baseline_results['total']})")
    print(f"  1着・2着正解数: {baseline_results['first_second_correct']}")
    print(f"  3着的中率（1着○2着○時）: {baseline_third_rate:.4%} ({baseline_results['third_hits_given_12']}/{baseline_results['first_second_correct']})")
    print()

    # 決まり手別の統計
    print("  [決まり手別 3着精度（ベースライン）]")
    for kimarite, stats in sorted(baseline_results['kimarite_stats'].items(), key=lambda x: x[1]['total'], reverse=True):
        if stats['total'] >= 5:  # サンプル数5以上のみ表示
            rate = stats['third_hits'] / stats['total'] if stats['total'] > 0 else 0
            print(f"    {kimarite}: {rate:.1%} ({stats['third_hits']}/{stats['total']})")
    print()

    # ========================================
    # 本番測定（機能有効）
    # ========================================
    print("[2/2] 本番測定（ThirdPlaceSpecializedScorer有効）")
    print("-" * 80)

    production_results = evaluate_calculator(conn, race_ids, use_third_place_scorer=True, verbose=verbose)

    production_trifecta_rate = production_results['trifecta_hits'] / production_results['total'] if production_results['total'] > 0 else 0
    production_third_rate = production_results['third_hits_given_12'] / production_results['first_second_correct'] if production_results['first_second_correct'] > 0 else 0

    print(f"  検証レース数: {production_results['total']}")
    print(f"  三連単的中率: {production_trifecta_rate:.4%} ({production_results['trifecta_hits']}/{production_results['total']})")
    print(f"  1着・2着正解数: {production_results['first_second_correct']}")
    print(f"  3着的中率（1着○2着○時）: {production_third_rate:.4%} ({production_results['third_hits_given_12']}/{production_results['first_second_correct']})")
    print()

    # 決まり手別の統計
    print("  [決まり手別 3着精度（本番）]")
    for kimarite, stats in sorted(production_results['kimarite_stats'].items(), key=lambda x: x[1]['total'], reverse=True):
        if stats['total'] >= 5:  # サンプル数5以上のみ表示
            rate = stats['third_hits'] / stats['total'] if stats['total'] > 0 else 0
            # ベースラインとの比較
            baseline_stats = baseline_results['kimarite_stats'].get(kimarite, {'total': 0, 'third_hits': 0})
            baseline_rate = baseline_stats['third_hits'] / baseline_stats['total'] if baseline_stats['total'] > 0 else 0
            diff = (rate - baseline_rate) * 100
            print(f"    {kimarite}: {rate:.1%} ({stats['third_hits']}/{stats['total']}) [{diff:+.1f}pt]")
    print()

    # ========================================
    # 結果サマリー
    # ========================================
    diff_trifecta = (production_trifecta_rate - baseline_trifecta_rate) * 100
    diff_third = (production_third_rate - baseline_third_rate) * 100

    print("=" * 80)
    print("検証結果サマリー")
    print("=" * 80)
    print(f"検証レース数: {production_results['total']}")
    print()
    print("[三連単的中率]")
    print(f"  ベースライン（無効）: {baseline_trifecta_rate:.4%}")
    print(f"  本番（有効）:         {production_trifecta_rate:.4%}")
    print(f"  差分:                 {diff_trifecta:+.2f}pt")
    print()
    print("[3着的中率（1着○2着○時）]")
    print(f"  ベースライン（無効）: {baseline_third_rate:.4%}")
    print(f"  本番（有効）:         {production_third_rate:.4%}")
    print(f"  差分:                 {diff_third:+.2f}pt")
    print()

    # 参考値との比較
    print("[参考] P-5分析結果")
    print("  現状3着精度（1着○2着○時）: 38.7%")
    print("  決まり手「逃げ」精度: 81.6%")
    print("  決まり手「まくり差し」精度: 13.5%")
    print()

    # 判定
    if diff_third > 2.0:
        status = "[EXCELLENT] 大幅な改善効果あり"
        action = "-> 機能を継続使用、統合重みの最適化を検討"
    elif diff_third > 0.5:
        status = "[GOOD] 改善効果あり"
        action = "-> 継続モニタリング"
    elif diff_third > -0.5:
        status = "[NEUTRAL] 効果微小"
        action = "-> 統合重みの調整を検討"
    else:
        status = "[NG] 悪化"
        action = "-> 原因調査が必要、一時的に機能を無効化"

    print(f"判定: {status}")
    print(f"推奨アクション: {action}")
    print()
    print("=" * 80)

    conn.close()

    return {
        'baseline_trifecta_rate': baseline_trifecta_rate,
        'production_trifecta_rate': production_trifecta_rate,
        'baseline_third_rate': baseline_third_rate,
        'production_third_rate': production_third_rate,
        'diff_trifecta': diff_trifecta,
        'diff_third': diff_third
    }

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='ThirdPlaceSpecializedScorer統合の効果検証')
    parser.add_argument('-n', '--num_races', type=int, default=200, help='検証レース数')
    parser.add_argument('-v', '--verbose', action='store_true', help='詳細出力')
    args = parser.parse_args()

    verify_integration(args.num_races, args.verbose)
