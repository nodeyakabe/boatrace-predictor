#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
fast_backtest の正確性バリデーション

目的:
    fast_backtest.py の結果が standard_backtest_unique.py と一致することを確認する。
    prediction_features テーブルから再計算した confidence / rank が
    race_predictions テーブルの値と一致しているかを定量的に確認する。

使用方法:
    # 基本バリデーション（一致率確認）
    python scripts/validation/validate_fast_backtest.py

    # 特定年度のみ
    python scripts/validation/validate_fast_backtest.py --year 2024

    # 詳細レポート（不一致レースのサンプル表示）
    python scripts/validation/validate_fast_backtest.py --verbose

合格基準:
    - rank_prediction 一致率: 99%以上
    - confidence 一致率: 95%以上（_calculate_confidence と _recalculate_race_confidence の
      組み合わせが完全再現できない場合でも、バックテスト結果への影響は軽微）
"""
import sys
import os
import io
import sqlite3
import warnings
import argparse
from datetime import datetime

warnings.filterwarnings('ignore')

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

try:
    import pandas as pd
    import numpy as np
except ImportError:
    print("ERROR: pandas/numpy が必要です。")
    sys.exit(1)

# fast_backtest のロジックを再利用
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'scripts', 'backtest'))
from fast_backtest import (
    load_features, load_scoring_weights,
    recalculate_scores, DEFAULT_CONFIDENCE_THRESHOLDS
)


def load_existing_predictions(start_date: str, end_date: str) -> pd.DataFrame:
    """race_predictions テーブルから既存予測を取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    df = pd.read_sql_query("""
        SELECT rp.race_id, rp.pit_number, rp.rank_prediction, rp.confidence,
               rp.total_score
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE rp.prediction_type = 'before'
          AND r.race_date >= ? AND r.race_date <= ?
    """, conn, params=(start_date, end_date))
    conn.close()
    return df


def validate(start_date: str, end_date: str, verbose: bool = False) -> dict:
    """
    prediction_features（再計算）と race_predictions（既存）を比較

    Returns:
        {'rank_match_rate': float, 'conf_match_rate': float, 'total_rows': int}
    """
    print(f"\n[1] prediction_features を読み込み中...")
    df_features = load_features(start_date, end_date)
    if df_features.empty:
        print("  ERROR: prediction_features が空です。generate_features.py を先に実行してください。")
        return {}

    print(f"  {len(df_features):,}行 ロード完了")

    print(f"\n[2] race_predictions（既存）を読み込み中...")
    df_existing = load_existing_predictions(start_date, end_date)
    if df_existing.empty:
        print("  WARNING: race_predictions が空です。")
        return {}
    print(f"  {len(df_existing):,}行 ロード完了")

    print(f"\n[3] fast_backtest の confidence/rank を再計算中...")
    weights = load_scoring_weights()
    df_recalc = recalculate_scores(df_features, weights, DEFAULT_CONFIDENCE_THRESHOLDS,
                                   mode='confidence_only')
    df_recalc = df_recalc[['race_id', 'pit_number', 'rank_prediction', 'confidence', 'total_score']].copy()
    df_recalc.columns = ['race_id', 'pit_number', 'rank_recalc', 'conf_recalc', 'score_recalc']
    print(f"  再計算完了")

    print(f"\n[4] 比較中...")
    merged = df_existing.merge(
        df_recalc,
        on=['race_id', 'pit_number'],
        how='inner'
    )

    if merged.empty:
        print("  WARNING: 共通レースが見つかりません。")
        return {}

    total = len(merged)

    # rank 一致率
    rank_match = (merged['rank_prediction'] == merged['rank_recalc']).sum()
    rank_match_rate = rank_match / total

    # confidence 一致率（1位のみ）
    top1 = merged[merged['rank_prediction'] == 1]
    conf_match = (top1['confidence'] == top1['conf_recalc']).sum()
    conf_match_rate = conf_match / len(top1) if len(top1) > 0 else 0.0

    # total_score 差の統計
    score_diff = (merged['total_score'] - merged['score_recalc']).abs()

    print(f"\n{'='*60}")
    print(f"バリデーション結果: {start_date} 〜 {end_date}")
    print(f"{'='*60}")
    print(f"比較行数: {total:,}")
    print(f"")
    print(f"【rank_prediction 一致率】: {rank_match_rate:.4%} ({rank_match:,}/{total:,})")
    print(f"  目標: 99%以上  → {'✅ 合格' if rank_match_rate >= 0.99 else '❌ 要確認'}")
    print(f"")
    print(f"【confidence 一致率（1位のみ）】: {conf_match_rate:.4%} ({conf_match:,}/{len(top1):,})")
    print(f"  目標: 95%以上  → {'✅ 合格' if conf_match_rate >= 0.95 else '❌ 要確認'}")
    print(f"")
    print(f"【total_score 差の統計】")
    print(f"  平均差: {score_diff.mean():.4f}点")
    print(f"  最大差: {score_diff.max():.4f}点")
    print(f"  中央値: {score_diff.median():.4f}点")

    if verbose:
        # confidence 不一致のサンプルを表示
        mismatch = top1[top1['confidence'] != top1['conf_recalc']].copy()
        if not mismatch.empty:
            print(f"\n【confidence 不一致のサンプル（上位20件）】")
            print(f"{'race_id':>8} {'既存':^6} {'再計算':^6} {'total_score':>12} {'再計算score':>12}")
            print('-' * 55)
            for _, row in mismatch.head(20).iterrows():
                print(f"{row['race_id']:>8} {row['confidence']:^6} {row['conf_recalc']:^6} "
                      f"{row['total_score']:>12.2f} {row['score_recalc']:>12.2f}")

        # 信頼度分布の比較
        print(f"\n【confidence 分布比較（1位のみ）】")
        print(f"{'信頼度':^6} {'既存':>8} {'再計算':>8}")
        print('-' * 25)
        for conf in ['A', 'B', 'C', 'D', 'E']:
            cnt_existing = (top1['confidence'] == conf).sum()
            cnt_recalc   = (top1['conf_recalc'] == conf).sum()
            print(f"  {conf:^6} {cnt_existing:>8,} {cnt_recalc:>8,}")

    print(f"\n{'='*60}")

    if rank_match_rate >= 0.99 and conf_match_rate >= 0.95:
        print(f"✅ バリデーション合格: fast_backtest.py の結果は十分な正確性を持っています。")
    else:
        print(f"⚠️  バリデーション要確認:")
        if rank_match_rate < 0.99:
            print(f"  - rank_prediction 一致率が低い（{rank_match_rate:.2%}）")
            print(f"    → extended_detail 等の保存漏れがないか確認してください")
        if conf_match_rate < 0.95:
            print(f"  - confidence 一致率が低い（{conf_match_rate:.2%}）")
            print(f"    → _calculate_confidence と score_gap の組み合わせ判定を確認してください")
        print(f"  ※ fast_backtest は confidence 閾値変更テストには利用できますが、")
        print(f"    正式な結果は standard_backtest_unique.py で確認してください。")

    return {
        'rank_match_rate': rank_match_rate,
        'conf_match_rate': conf_match_rate,
        'total_rows': total,
    }


def compare_backtest_roi(start_date: str, end_date: str):
    """
    fast_backtest と standard_backtest_unique の ROI を比較（簡易版）
    """
    print(f"\n【ROI 比較】（デフォルト設定）")
    print(f"  fast_backtest: python scripts/backtest/fast_backtest.py --full")
    print(f"  standard:      python scripts/backtest/standard_backtest_unique.py --full")
    print(f"  ※ 両者の ROI 差が ±5pt 以内であれば正常")


def main():
    parser = argparse.ArgumentParser(description='fast_backtest バリデーション')
    parser.add_argument('--year',    type=int, help='特定年度（例: 2024）')
    parser.add_argument('--start',   type=str, help='開始日（YYYY-MM-DD）')
    parser.add_argument('--end',     type=str, help='終了日（YYYY-MM-DD）')
    parser.add_argument('--verbose', action='store_true', help='不一致サンプルを表示')
    args = parser.parse_args()

    if args.year:
        start_date = f'{args.year}-01-01'
        end_date   = f'{args.year}-12-31'
    elif args.start:
        start_date = args.start
        end_date   = args.end or '2099-12-31'
    else:
        # デフォルト: 2024年で検証
        start_date = '2024-01-01'
        end_date   = '2024-12-31'
        print("（期間未指定のため 2024年でバリデーション）")

    validate(start_date, end_date, verbose=args.verbose)
    compare_backtest_roi(start_date, end_date)


if __name__ == '__main__':
    main()
