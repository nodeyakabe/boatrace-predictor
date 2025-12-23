"""
季節変動分析スクリプト

目的: 月別・四半期別の三連単的中率推移を分析

分析内容:
1. 月別三連単的中率（1月～12月）
2. 四半期別比較（Q1～Q4）
3. グラフ生成（matplotlib）

出力:
- CSVレポート: output/seasonal_trends_{confidence}.csv
- グラフ: output/seasonal_trends_{confidence}.png
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # GUIなしでグラフ生成

# 日本語フォント設定
plt.rcParams['font.sans-serif'] = ['MS Gothic', 'Yu Gothic', 'Meiryo']
plt.rcParams['axes.unicode_minus'] = False


def analyze_seasonal_trends(db_path: str, confidence: str = 'B', start_date: str = '2025-01-01', end_date: str = '2025-12-31'):
    """
    季節変動分析を実行

    Args:
        db_path: データベースパス
        confidence: 信頼度（A/B/C/D/E）
        start_date: 分析開始日
        end_date: 分析終了日
    """
    conn = sqlite3.connect(db_path)

    print("=" * 80)
    print(f"季節変動分析（信頼度{confidence}）")
    print("=" * 80)
    print(f"\n分析期間: {start_date} ～ {end_date}")
    print()

    # データ取得（validate_confidence_b_trifecta.pyと同じSQL構造）
    query = """
    WITH ranked_predictions AS (
        SELECT
            rp.race_id,
            r.race_date,
            rp.pit_number,
            rp.rank_prediction,
            rp.confidence,
            res.rank as actual_rank
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        LEFT JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
        WHERE r.race_date >= ?
          AND r.race_date <= ?
          AND rp.generated_at >= '2025-12-10'
          AND res.rank IS NOT NULL
    ),
    race_predictions_with_confidence AS (
        SELECT DISTINCT
            rp.race_id,
            r.race_date,
            MAX(CASE WHEN rp.confidence = ? THEN 1 ELSE 0 END) as has_target_confidence
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE r.race_date >= ?
          AND r.race_date <= ?
          AND rp.generated_at >= '2025-12-10'
        GROUP BY rp.race_id, r.race_date
        HAVING has_target_confidence = 1
    ),
    predicted_trifecta AS (
        SELECT
            rwc.race_id,
            rwc.race_date,
            MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.pit_number END) as pred_1st,
            MAX(CASE WHEN rp.rank_prediction = 2 THEN rp.pit_number END) as pred_2nd,
            MAX(CASE WHEN rp.rank_prediction = 3 THEN rp.pit_number END) as pred_3rd
        FROM race_predictions_with_confidence rwc
        JOIN ranked_predictions rp ON rwc.race_id = rp.race_id
        WHERE rp.rank_prediction <= 3
        GROUP BY rwc.race_id, rwc.race_date
    ),
    actual_trifecta AS (
        SELECT
            race_id,
            MAX(CASE WHEN actual_rank = '1' THEN pit_number END) as actual_1st,
            MAX(CASE WHEN actual_rank = '2' THEN pit_number END) as actual_2nd,
            MAX(CASE WHEN actual_rank = '3' THEN pit_number END) as actual_3rd
        FROM ranked_predictions
        WHERE actual_rank IN ('1', '2', '3')
        GROUP BY race_id
    )
    SELECT
        pt.race_id,
        pt.race_date,
        pt.pred_1st,
        pt.pred_2nd,
        pt.pred_3rd,
        at.actual_1st,
        at.actual_2nd,
        at.actual_3rd,
        CASE
            WHEN pt.pred_1st = at.actual_1st
             AND pt.pred_2nd = at.actual_2nd
             AND pt.pred_3rd = at.actual_3rd
            THEN 1
            ELSE 0
        END as is_trifecta_hit
    FROM predicted_trifecta pt
    LEFT JOIN actual_trifecta at ON pt.race_id = at.race_id
    WHERE pt.pred_1st IS NOT NULL
      AND pt.pred_2nd IS NOT NULL
      AND pt.pred_3rd IS NOT NULL
      AND at.actual_1st IS NOT NULL
      AND at.actual_2nd IS NOT NULL
      AND at.actual_3rd IS NOT NULL
    ORDER BY pt.race_date
    """

    df = pd.read_sql_query(query, conn, params=(start_date, end_date, confidence, start_date, end_date))
    conn.close()

    if len(df) == 0:
        print(f"警告: 信頼度{confidence}のデータが見つかりません。")
        return

    print(f"総レース数: {len(df):,}レース")
    print(f"総的中数: {df['is_trifecta_hit'].sum()}レース")
    print(f"全体的中率: {df['is_trifecta_hit'].mean() * 100:.2f}%")
    print()

    # 月別分析
    df['race_date'] = pd.to_datetime(df['race_date'])
    df['month'] = df['race_date'].dt.month
    df['quarter'] = df['race_date'].dt.quarter

    # 月別集計
    monthly_stats = df.groupby('month').agg({
        'race_id': 'count',
        'is_trifecta_hit': ['sum', 'mean']
    }).round(4)

    monthly_stats.columns = ['レース数', '的中数', '的中率']
    monthly_stats['的中率'] = monthly_stats['的中率'] * 100

    print("=" * 80)
    print("【1】 月別三連単的中率")
    print("=" * 80)
    print()
    print(monthly_stats.to_string())
    print()

    # 四半期別集計
    quarterly_stats = df.groupby('quarter').agg({
        'race_id': 'count',
        'is_trifecta_hit': ['sum', 'mean']
    }).round(4)

    quarterly_stats.columns = ['レース数', '的中数', '的中率']
    quarterly_stats['的中率'] = quarterly_stats['的中率'] * 100

    print("=" * 80)
    print("【2】 四半期別三連単的中率")
    print("=" * 80)
    print()
    print(quarterly_stats.to_string())
    print()

    # CSVレポート出力
    output_dir = Path('output')
    output_dir.mkdir(exist_ok=True)

    csv_path = output_dir / f'seasonal_trends_{confidence}.csv'
    monthly_stats.to_csv(csv_path, encoding='utf-8-sig')
    print(f"CSVレポート出力: {csv_path}")

    # グラフ生成
    fig, axes = plt.subplots(2, 1, figsize=(12, 10))

    # 月別グラフ
    ax1 = axes[0]
    x_months = monthly_stats.index
    y_rates = monthly_stats['的中率']
    y_counts = monthly_stats['レース数']

    ax1_twin = ax1.twinx()

    bars = ax1.bar(x_months, y_rates, color='steelblue', alpha=0.7, label='的中率')
    line = ax1_twin.plot(x_months, y_counts, color='orangered', marker='o', linewidth=2, label='レース数')

    ax1.set_xlabel('月', fontsize=12)
    ax1.set_ylabel('三連単的中率 (%)', fontsize=12, color='steelblue')
    ax1_twin.set_ylabel('レース数', fontsize=12, color='orangered')
    ax1.set_title(f'月別三連単的中率（信頼度{confidence}）', fontsize=14, fontweight='bold')
    ax1.set_xticks(x_months)
    ax1.tick_params(axis='y', labelcolor='steelblue')
    ax1_twin.tick_params(axis='y', labelcolor='orangered')
    ax1.grid(axis='y', alpha=0.3)
    ax1.legend(loc='upper left')
    ax1_twin.legend(loc='upper right')

    # 四半期別グラフ
    ax2 = axes[1]
    x_quarters = quarterly_stats.index
    y_rates_q = quarterly_stats['的中率']
    y_counts_q = quarterly_stats['レース数']

    ax2_twin = ax2.twinx()

    bars_q = ax2.bar(x_quarters, y_rates_q, color='forestgreen', alpha=0.7, label='的中率')
    line_q = ax2_twin.plot(x_quarters, y_counts_q, color='orangered', marker='s', linewidth=2, label='レース数')

    ax2.set_xlabel('四半期', fontsize=12)
    ax2.set_ylabel('三連単的中率 (%)', fontsize=12, color='forestgreen')
    ax2_twin.set_ylabel('レース数', fontsize=12, color='orangered')
    ax2.set_title(f'四半期別三連単的中率（信頼度{confidence}）', fontsize=14, fontweight='bold')
    ax2.set_xticks(x_quarters)
    ax2.set_xticklabels([f'Q{q}' for q in x_quarters])
    ax2.tick_params(axis='y', labelcolor='forestgreen')
    ax2_twin.tick_params(axis='y', labelcolor='orangered')
    ax2.grid(axis='y', alpha=0.3)
    ax2.legend(loc='upper left')
    ax2_twin.legend(loc='upper right')

    plt.tight_layout()

    png_path = output_dir / f'seasonal_trends_{confidence}.png'
    plt.savefig(png_path, dpi=150, bbox_inches='tight')
    print(f"グラフ出力: {png_path}")
    plt.close()

    # 統計サマリー
    print()
    print("=" * 80)
    print("【3】 統計サマリー")
    print("=" * 80)
    print()
    print(f"月別的中率の標準偏差: {monthly_stats['的中率'].std():.2f}%")
    print(f"月別的中率の範囲: {monthly_stats['的中率'].min():.2f}% ～ {monthly_stats['的中率'].max():.2f}%")
    print(f"最高的中率の月: {monthly_stats['的中率'].idxmax()}月 ({monthly_stats['的中率'].max():.2f}%)")
    print(f"最低的中率の月: {monthly_stats['的中率'].idxmin()}月 ({monthly_stats['的中率'].min():.2f}%)")
    print()


def main():
    import argparse

    parser = argparse.ArgumentParser(description='季節変動分析')
    parser.add_argument('--db', default='data/boatrace.db', help='データベースパス')
    parser.add_argument('--confidence', default='B', choices=['A', 'B', 'C', 'D', 'E'], help='信頼度')
    parser.add_argument('--start', default='2025-01-01', help='分析開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', default='2025-12-31', help='分析終了日 (YYYY-MM-DD)')

    args = parser.parse_args()

    try:
        analyze_seasonal_trends(args.db, args.confidence, args.start, args.end)
        print()
        print("=" * 80)
        print("[OK] 季節変動分析が正常に完了しました")
        print("=" * 80)
    except Exception as e:
        print()
        print("=" * 80)
        print("[ERROR] 季節変動分析でエラーが発生しました")
        print("=" * 80)
        print(f"\nエラー内容: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
