"""
会場別・条件別詳細分析スクリプト

目的: 会場・天候・風速などの条件別に三連単的中率を分析

分析内容:
1. 会場別三連単的中率（24会場）
2. 天候別（データがあれば）
3. 風速別（データがあれば）
4. グレード別（SG, G1, G2, G3, 一般）

出力:
- CSVレポート: output/condition_analysis_{confidence}.csv
- 会場別ヒートマップ: output/venue_heatmap_{confidence}.png
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')

# 日本語フォント設定
plt.rcParams['font.sans-serif'] = ['MS Gothic', 'Yu Gothic', 'Meiryo']
plt.rcParams['axes.unicode_minus'] = False

# 会場コードマッピング
VENUE_NAMES = {
    1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川', 6: '浜名湖',
    7: '蒲郡', 8: '常滑', 9: '津', 10: '三国', 11: 'びわこ', 12: '住之江',
    13: '尼崎', 14: '鳴門', 15: '丸亀', 16: '児島', 17: '宮島', 18: '徳山',
    19: '下関', 20: '若松', 21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村'
}


def analyze_conditions(db_path: str, confidence: str = 'B', start_date: str = '2025-01-01', end_date: str = '2025-12-31'):
    """
    会場別・条件別分析を実行

    Args:
        db_path: データベースパス
        confidence: 信頼度（A/B/C/D/E）
        start_date: 分析開始日
        end_date: 分析終了日
    """
    conn = sqlite3.connect(db_path)

    print("=" * 80)
    print(f"会場別・条件別分析（信頼度{confidence}）")
    print("=" * 80)
    print(f"\n分析期間: {start_date} ～ {end_date}")
    print()

    # データ取得（validate_confidence_b_trifecta.pyと同じSQL構造）
    query = """
    WITH ranked_predictions AS (
        SELECT
            rp.race_id,
            r.race_date,
            r.venue_code,
            r.race_number,
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
            r.venue_code,
            r.race_number,
            MAX(CASE WHEN rp.confidence = ? THEN 1 ELSE 0 END) as has_target_confidence
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE r.race_date >= ?
          AND r.race_date <= ?
          AND rp.generated_at >= '2025-12-10'
        GROUP BY rp.race_id, r.race_date, r.venue_code, r.race_number
        HAVING has_target_confidence = 1
    ),
    predicted_trifecta AS (
        SELECT
            rwc.race_id,
            rwc.race_date,
            rwc.venue_code,
            rwc.race_number,
            MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.pit_number END) as pred_1st,
            MAX(CASE WHEN rp.rank_prediction = 2 THEN rp.pit_number END) as pred_2nd,
            MAX(CASE WHEN rp.rank_prediction = 3 THEN rp.pit_number END) as pred_3rd
        FROM race_predictions_with_confidence rwc
        JOIN ranked_predictions rp ON rwc.race_id = rp.race_id
        WHERE rp.rank_prediction <= 3
        GROUP BY rwc.race_id, rwc.race_date, rwc.venue_code, rwc.race_number
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
        pt.venue_code,
        pt.race_number,
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
    ORDER BY pt.race_date, pt.venue_code, pt.race_number
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

    # venue_codeを整数に変換してから会場名追加
    df['venue_code'] = df['venue_code'].astype(int)
    df['venue_name'] = df['venue_code'].map(VENUE_NAMES)

    # 会場別集計
    venue_stats = df.groupby(['venue_code', 'venue_name']).agg({
        'race_id': 'count',
        'is_trifecta_hit': ['sum', 'mean']
    }).round(4)

    venue_stats.columns = ['レース数', '的中数', '的中率']
    venue_stats['的中率'] = venue_stats['的中率'] * 100
    venue_stats = venue_stats.sort_values('レース数', ascending=False)

    print("=" * 80)
    print("【1】 会場別三連単的中率（上位10会場）")
    print("=" * 80)
    print()
    print(venue_stats.head(10).to_string())
    print()

    # レース数が10件以上ある会場のみ抽出
    venue_stats_filtered = venue_stats[venue_stats['レース数'] >= 10].copy()

    if len(venue_stats_filtered) > 0:
        print(f"レース数10件以上の会場数: {len(venue_stats_filtered)}会場")
        print(f"最高的中率の会場: {venue_stats_filtered['的中率'].idxmax()[1]} ({venue_stats_filtered['的中率'].max():.2f}%)")
        print(f"最低的中率の会場: {venue_stats_filtered['的中率'].idxmin()[1]} ({venue_stats_filtered['的中率'].min():.2f}%)")
    print()

    # CSVレポート出力
    output_dir = Path('output')
    output_dir.mkdir(exist_ok=True)

    csv_path = output_dir / f'condition_analysis_{confidence}.csv'
    venue_stats.to_csv(csv_path, encoding='utf-8-sig')
    print(f"CSVレポート出力: {csv_path}")

    # グラフ生成（会場別ヒートマップ）
    if len(venue_stats_filtered) > 0:
        fig, ax = plt.subplots(figsize=(14, 8))

        # 横棒グラフ
        venues = venue_stats_filtered.index.get_level_values('venue_name')
        rates = venue_stats_filtered['的中率']
        counts = venue_stats_filtered['レース数']

        # 色分け（的中率ベース）
        colors = plt.cm.RdYlGn(rates / rates.max())

        bars = ax.barh(venues, rates, color=colors, alpha=0.8)

        # レース数をバーの横に表示
        for i, (rate, count) in enumerate(zip(rates, counts)):
            ax.text(rate + 0.5, i, f'{int(count)}件', va='center', fontsize=9)

        ax.set_xlabel('三連単的中率 (%)', fontsize=12)
        ax.set_ylabel('会場', fontsize=12)
        ax.set_title(f'会場別三連単的中率（信頼度{confidence}、10件以上）', fontsize=14, fontweight='bold')
        ax.grid(axis='x', alpha=0.3)

        plt.tight_layout()

        png_path = output_dir / f'venue_heatmap_{confidence}.png'
        plt.savefig(png_path, dpi=150, bbox_inches='tight')
        print(f"グラフ出力: {png_path}")
        plt.close()

    # 統計サマリー
    print()
    print("=" * 80)
    print("【2】 統計サマリー")
    print("=" * 80)
    print()
    if len(venue_stats_filtered) > 0:
        print(f"会場別的中率の標準偏差: {venue_stats_filtered['的中率'].std():.2f}%")
        print(f"会場別的中率の範囲: {venue_stats_filtered['的中率'].min():.2f}% ～ {venue_stats_filtered['的中率'].max():.2f}%")
        print(f"会場間のばらつき: {'大きい' if venue_stats_filtered['的中率'].std() > 2.0 else '小さい'}")
    print()


def main():
    import argparse

    parser = argparse.ArgumentParser(description='会場別・条件別分析')
    parser.add_argument('--db', default='data/boatrace.db', help='データベースパス')
    parser.add_argument('--confidence', default='B', choices=['A', 'B', 'C', 'D', 'E'], help='信頼度')
    parser.add_argument('--start', default='2025-01-01', help='分析開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', default='2025-12-31', help='分析終了日 (YYYY-MM-DD)')

    args = parser.parse_args()

    try:
        analyze_conditions(args.db, args.confidence, args.start, args.end)
        print()
        print("=" * 80)
        print("[OK] 会場別・条件別分析が正常に完了しました")
        print("=" * 80)
    except Exception as e:
        print()
        print("=" * 80)
        print("[ERROR] 会場別・条件別分析でエラーが発生しました")
        print("=" * 80)
        print(f"\nエラー内容: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
