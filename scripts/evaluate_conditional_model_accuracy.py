"""
条件付きモデルの精度評価スクリプト

2025年データを使用して、新しいモデルの着順予測精度を評価する
- 1着/2着/3着の予測精度
- システム全体の精度
- 信頼度別の精度
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import pandas as pd
import numpy as np
from collections import defaultdict

def load_predictions_and_results(db_path: str = 'data/boatrace.db') -> pd.DataFrame:
    """2025年の予測データと結果を読み込み"""
    conn = sqlite3.connect(db_path)

    query = """
    SELECT
        p.race_id,
        p.pit_number,
        p.rank_prediction as predicted_rank,
        p.total_score,
        p.prediction_type,
        p.confidence,
        r.race_date,
        CAST(res.rank AS INTEGER) as actual_rank
    FROM race_predictions p
    JOIN races r ON p.race_id = r.id
    JOIN results res ON p.race_id = res.race_id AND p.pit_number = res.pit_number
    WHERE r.race_date >= '2025-01-01'
      AND r.race_date <= '2025-12-31'
      AND p.prediction_type = 'advance'
      AND p.rank_prediction <= 3
      AND res.rank IS NOT NULL
    ORDER BY r.race_date, p.race_id, p.pit_number
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    # データ型を明示的に変換
    df['actual_rank'] = pd.to_numeric(df['actual_rank'], errors='coerce').fillna(0).astype(int)

    return df


def analyze_rank_accuracy(df: pd.DataFrame) -> dict:
    """着順別の精度を分析"""
    results = {}

    for pred_rank in [1, 2, 3]:
        rank_df = df[df['predicted_rank'] == pred_rank]
        if len(rank_df) == 0:
            continue

        # 予測が当たった件数
        correct = (rank_df['actual_rank'] == pred_rank).sum()
        total = len(rank_df)
        accuracy = correct / total * 100 if total > 0 else 0

        results[f'{pred_rank}着精度'] = {
            'correct': int(correct),
            'total': int(total),
            'accuracy': round(accuracy, 2)
        }

    return results


def analyze_overall_accuracy(df: pd.DataFrame) -> dict:
    """システム全体の精度（1着+2着+3着の複合評価）"""
    # レース単位でグループ化
    race_ids = df['race_id'].unique()

    correct_count = 0
    total_count = 0

    # 1コース常時予測の場合（ベースライン）
    baseline_correct = 0

    for race_id in race_ids:
        race_df = df[df['race_id'] == race_id]

        # 1着予測の確認
        first_pred = race_df[race_df['predicted_rank'] == 1]
        if len(first_pred) == 0:
            continue

        first_pit = first_pred['pit_number'].iloc[0]
        first_actual = first_pred['actual_rank'].iloc[0]

        if first_actual == 1:
            correct_count += 1
        total_count += 1

        # ベースライン（1コース常時予測）
        race_first_course = race_df[race_df['pit_number'] == 1]
        if len(race_first_course) > 0:
            if race_first_course['actual_rank'].iloc[0] == 1:
                baseline_correct += 1

    system_accuracy = correct_count / total_count * 100 if total_count > 0 else 0
    baseline_accuracy = baseline_correct / total_count * 100 if total_count > 0 else 0

    return {
        'system': {
            'correct': int(correct_count),
            'total': int(total_count),
            'accuracy': round(system_accuracy, 2)
        },
        'baseline_1course': {
            'correct': int(baseline_correct),
            'total': int(total_count),
            'accuracy': round(baseline_accuracy, 2)
        },
        'added_value': round(system_accuracy - baseline_accuracy, 2)
    }


def analyze_confidence_accuracy(df: pd.DataFrame) -> dict:
    """信頼度別の精度を分析"""
    results = {}

    # 1着予測のみを対象
    first_df = df[df['predicted_rank'] == 1].copy()

    for conf in ['A', 'B', 'C', 'D', 'E']:
        conf_df = first_df[first_df['confidence'] == conf]
        if len(conf_df) == 0:
            continue

        correct = (conf_df['actual_rank'] == 1).sum()
        total = len(conf_df)
        accuracy = correct / total * 100 if total > 0 else 0

        results[f'信頼度{conf}'] = {
            'correct': int(correct),
            'total': int(total),
            'accuracy': round(accuracy, 2)
        }

    return results


def analyze_trifecta_accuracy(df: pd.DataFrame) -> dict:
    """3連単（1-2-3着すべて的中）の精度を分析"""
    race_ids = df['race_id'].unique()

    correct_count = 0
    total_count = 0

    for race_id in race_ids:
        race_df = df[df['race_id'] == race_id]

        # 1-2-3着の予測と実際を取得
        pred_1st = race_df[race_df['predicted_rank'] == 1]
        pred_2nd = race_df[race_df['predicted_rank'] == 2]
        pred_3rd = race_df[race_df['predicted_rank'] == 3]

        if len(pred_1st) == 0 or len(pred_2nd) == 0 or len(pred_3rd) == 0:
            continue

        # 予測の艇番
        pit_1st = pred_1st['pit_number'].iloc[0]
        pit_2nd = pred_2nd['pit_number'].iloc[0]
        pit_3rd = pred_3rd['pit_number'].iloc[0]

        # 実際の着順
        actual_1st = pred_1st['actual_rank'].iloc[0]
        actual_2nd = pred_2nd['actual_rank'].iloc[0]
        actual_3rd = pred_3rd['actual_rank'].iloc[0]

        total_count += 1

        # 全て的中？
        if actual_1st == 1 and actual_2nd == 2 and actual_3rd == 3:
            correct_count += 1

    accuracy = correct_count / total_count * 100 if total_count > 0 else 0

    return {
        'correct': int(correct_count),
        'total': int(total_count),
        'accuracy': round(accuracy, 2)
    }


def main():
    print("=" * 70)
    print("条件付きモデルの精度評価レポート")
    print("=" * 70)
    print(f"評価データ: 2025年（advance予測）")
    print()

    # データ読み込み
    df = load_predictions_and_results()
    print(f"予測レコード数: {len(df):,}")
    print(f"ユニークレース数: {df['race_id'].nunique():,}")
    print()

    # 着順別精度
    print("=" * 70)
    print("【着順別精度】")
    print("=" * 70)
    rank_results = analyze_rank_accuracy(df)
    for key, val in rank_results.items():
        print(f"  {key}: {val['accuracy']:.1f}% ({val['correct']:,}/{val['total']:,})")
    print()

    # システム全体精度
    print("=" * 70)
    print("【システム全体精度 vs ベースライン】")
    print("=" * 70)
    overall_results = analyze_overall_accuracy(df)
    print(f"  予測システム: {overall_results['system']['accuracy']:.1f}% ({overall_results['system']['correct']:,}/{overall_results['system']['total']:,})")
    print(f"  ベースライン（1コース常時予測）: {overall_results['baseline_1course']['accuracy']:.1f}%")
    print(f"  付加価値: {overall_results['added_value']:+.1f}pt")
    print()

    # 信頼度別精度
    print("=" * 70)
    print("【信頼度別精度（1着予測）】")
    print("=" * 70)
    conf_results = analyze_confidence_accuracy(df)
    for key, val in conf_results.items():
        print(f"  {key}: {val['accuracy']:.1f}% ({val['correct']:,}/{val['total']:,})")
    print()

    # 3連単精度
    print("=" * 70)
    print("【3連単精度（1-2-3着すべて的中）】")
    print("=" * 70)
    trifecta_results = analyze_trifecta_accuracy(df)
    print(f"  的中率: {trifecta_results['accuracy']:.2f}% ({trifecta_results['correct']:,}/{trifecta_results['total']:,})")
    print()

    # サマリー
    print("=" * 70)
    print("【サマリー】")
    print("=" * 70)
    print(f"  1着精度: {rank_results.get('1着精度', {}).get('accuracy', 'N/A')}%")
    print(f"  2着精度: {rank_results.get('2着精度', {}).get('accuracy', 'N/A')}%（目標: 45%）")
    print(f"  3着精度: {rank_results.get('3着精度', {}).get('accuracy', 'N/A')}%（目標: 35%）")
    print(f"  システム全体: {overall_results['system']['accuracy']:.1f}%（ベースライン: {overall_results['baseline_1course']['accuracy']:.1f}%）")
    print(f"  付加価値: {overall_results['added_value']:+.1f}pt（目標: ベースライン超え）")
    print()

    # 目標達成判定
    second_acc = rank_results.get('2着精度', {}).get('accuracy', 0)
    third_acc = rank_results.get('3着精度', {}).get('accuracy', 0)
    added_value = overall_results['added_value']

    print("=" * 70)
    print("[Goal Achievement]")
    print("=" * 70)
    print(f"  2着精度: {'[OK]' if second_acc >= 45 else '[NG]'} ({second_acc}% / Goal 45%)")
    print(f"  3着精度: {'[OK]' if third_acc >= 35 else '[NG]'} ({third_acc}% / Goal 35%)")
    print(f"  Baseline超え: {'[OK]' if added_value > 0 else '[NG]'} ({added_value:+.1f}pt)")


if __name__ == '__main__':
    main()
