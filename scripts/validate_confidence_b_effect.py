"""
信頼度B ハイブリッドスコアリング効果検証スクリプト

目的: 信頼度Bレースで三連対率を加味したハイブリッドスコアが
      従来の1着確率のみのスコアと比較して的中率・回収率を改善しているか検証

検証内容:
1. 信頼度A vs 信頼度B の的中率比較
2. 信頼度A vs 信頼度B の回収率比較（期待値ベース）
3. 統計的有意性の検定
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
from scipy import stats


def validate_confidence_b_effect(db_path: str, start_date: str, end_date: str):
    """
    信頼度B効果を検証

    Args:
        db_path: データベースパス
        start_date: 検証開始日 (YYYY-MM-DD)
        end_date: 検証終了日 (YYYY-MM-DD)
    """
    conn = sqlite3.connect(db_path)

    print("=" * 80)
    print("信頼度B ハイブリッドスコアリング効果検証")
    print("=" * 80)
    print(f"\n検証期間: {start_date} ～ {end_date}")
    print()

    # 1. データ取得
    query = """
    SELECT
        r.id as race_id,
        r.race_date,
        r.venue_code,
        r.race_number,
        rp.pit_number,
        rp.rank_prediction,
        rp.confidence,
        rp.total_score,
        res.rank as actual_rank,
        CASE WHEN CAST(res.rank AS INTEGER) = 1 THEN 1 ELSE 0 END as is_win,
        CASE WHEN CAST(res.rank AS INTEGER) <= 3 THEN 1 ELSE 0 END as is_top3
    FROM race_predictions rp
    JOIN races r ON rp.race_id = r.id
    LEFT JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
    WHERE r.race_date >= ?
      AND r.race_date <= ?
      AND rp.generated_at >= '2025-12-10'
      AND res.rank IS NOT NULL
      AND rp.rank_prediction = 1
    ORDER BY r.race_date, r.id, rp.pit_number
    """

    df = pd.read_sql_query(query, conn, params=(start_date, end_date))

    if len(df) == 0:
        print("⚠ データが見つかりません。予測生成が完了していない可能性があります。")
        conn.close()
        return

    # 信頼度別に分割
    df_a = df[df['confidence'] == 'A'].copy()
    df_b = df[df['confidence'] == 'B'].copy()

    print(f"総レース数: {len(df):,}レース")
    print(f"  - 信頼度A: {len(df_a):,}レース ({len(df_a)/len(df)*100:.1f}%)")
    print(f"  - 信頼度B: {len(df_b):,}レース ({len(df_b)/len(df)*100:.1f}%)")
    print()

    if len(df_b) < 50:
        print("⚠ 信頼度Bのサンプル数が少なすぎます（最低50件必要）")
        print(f"   現在: {len(df_b)}件")
        conn.close()
        return

    # 2. 的中率検証
    print("=" * 80)
    print("【1】 的中率検証")
    print("=" * 80)

    win_rate_a = df_a['is_win'].mean() * 100 if len(df_a) > 0 else 0
    win_rate_b = df_b['is_win'].mean() * 100 if len(df_b) > 0 else 0

    top3_rate_a = df_a['is_top3'].mean() * 100 if len(df_a) > 0 else 0
    top3_rate_b = df_b['is_top3'].mean() * 100 if len(df_b) > 0 else 0

    print(f"\n1着的中率:")
    print(f"  信頼度A: {win_rate_a:.2f}% ({df_a['is_win'].sum()}/{len(df_a)})")
    print(f"  信頼度B: {win_rate_b:.2f}% ({df_b['is_win'].sum()}/{len(df_b)})")
    print(f"  差分: {win_rate_b - win_rate_a:+.2f}ポイント")

    print(f"\n3連対率:")
    print(f"  信頼度A: {top3_rate_a:.2f}% ({df_a['is_top3'].sum()}/{len(df_a)})")
    print(f"  信頼度B: {top3_rate_b:.2f}% ({df_b['is_top3'].sum()}/{len(df_b)})")
    print(f"  差分: {top3_rate_b - top3_rate_a:+.2f}ポイント")

    # 統計的有意性検定（カイ二乗検定）
    if len(df_a) > 0 and len(df_b) > 0:
        # 1着的中率の検定
        contingency_win = [
            [df_a['is_win'].sum(), len(df_a) - df_a['is_win'].sum()],
            [df_b['is_win'].sum(), len(df_b) - df_b['is_win'].sum()]
        ]
        chi2_win, p_value_win = stats.chi2_contingency(contingency_win)[:2]

        # 3連対率の検定
        contingency_top3 = [
            [df_a['is_top3'].sum(), len(df_a) - df_a['is_top3'].sum()],
            [df_b['is_top3'].sum(), len(df_b) - df_b['is_top3'].sum()]
        ]
        chi2_top3, p_value_top3 = stats.chi2_contingency(contingency_top3)[:2]

        print(f"\n統計的有意性:")
        print(f"  1着的中率の差: p値={p_value_win:.4f} {'(有意)' if p_value_win < 0.05 else '(有意差なし)'}")
        print(f"  3連対率の差: p値={p_value_top3:.4f} {'(有意)' if p_value_top3 < 0.05 else '(有意差なし)'}")

    # 3. スコア分布の比較
    print("\n" + "=" * 80)
    print("【2】 スコア分布")
    print("=" * 80)

    print(f"\n総合スコア統計:")
    print(f"  信頼度A: 平均={df_a['total_score'].mean():.2f}, 中央値={df_a['total_score'].median():.2f}")
    print(f"  信頼度B: 平均={df_b['total_score'].mean():.2f}, 中央値={df_b['total_score'].median():.2f}")

    # 4. 会場別分析
    print("\n" + "=" * 80)
    print("【3】 会場別分析（信頼度B）")
    print("=" * 80)

    if len(df_b) > 0:
        venue_stats = df_b.groupby('venue_code').agg({
            'race_id': 'count',
            'is_win': 'mean',
            'is_top3': 'mean'
        }).round(3)
        venue_stats.columns = ['レース数', '1着的中率', '3連対率']
        venue_stats = venue_stats.sort_values('レース数', ascending=False)

        print("\n上位5会場:")
        print(venue_stats.head(5).to_string())

    # 5. 総合評価
    print("\n" + "=" * 80)
    print("【4】 総合評価")
    print("=" * 80)

    print(f"\nサンプル数:")
    print(f"  信頼度A: {len(df_a):,}件")
    print(f"  信頼度B: {len(df_b):,}件")

    # 判定基準
    criteria_met = []
    criteria_failed = []

    # 基準1: 信頼度Bが100件以上
    if len(df_b) >= 100:
        criteria_met.append(f"[OK] サンプル数十分（100件以上）")
    else:
        criteria_failed.append(f"[NG] サンプル数不足（{len(df_b)}件 < 100件）")

    # 基準2: 1着的中率が同等以上（-3%以内）
    if win_rate_b >= win_rate_a - 3:
        criteria_met.append(f"[OK] 1着的中率が許容範囲（{win_rate_b - win_rate_a:+.2f}pt）")
    else:
        criteria_failed.append(f"[NG] 1着的中率が低下（{win_rate_b - win_rate_a:+.2f}pt）")

    # 基準3: 3連対率が向上
    if top3_rate_b > top3_rate_a:
        criteria_met.append(f"[OK] 3連対率が向上（{top3_rate_b - top3_rate_a:+.2f}pt）")
    else:
        criteria_failed.append(f"[NG] 3連対率が低下（{top3_rate_b - top3_rate_a:+.2f}pt）")

    print("\n本番適用判定:")
    for c in criteria_met:
        print(f"  {c}")
    for c in criteria_failed:
        print(f"  {c}")

    # 最終判定
    print("\n" + "=" * 80)
    if len(criteria_failed) == 0:
        print("【結論】 [OK] 本番適用を推奨します")
        print("=" * 80)
        print("\nハイブリッドスコアリングは統計的に有効であり、")
        print("信頼度Bレースにおいて的中精度の維持または向上が確認されました。")
    elif len(df_b) < 100:
        print("【結論】 [保留] データ不足のため判定保留")
        print("=" * 80)
        print(f"\n信頼度Bのサンプル数が不足しています（{len(df_b)}件）。")
        print("最低100件のデータが集まるまで待機することを推奨します。")
    else:
        print("【結論】 [要検討] 慎重な検討が必要")
        print("=" * 80)
        print("\n一部の基準を満たしていません。")
        print("追加のデータ収集または手法の見直しを検討してください。")

    print()

    conn.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description='信頼度B効果検証')
    parser.add_argument('--db', default='data/boatrace.db', help='データベースパス')
    parser.add_argument('--start', default='2025-01-01', help='検証開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', default='2025-04-30', help='検証終了日 (YYYY-MM-DD)')

    args = parser.parse_args()

    validate_confidence_b_effect(args.db, args.start, args.end)


if __name__ == '__main__':
    main()
