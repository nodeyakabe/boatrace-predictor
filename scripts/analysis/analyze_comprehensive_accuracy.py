"""
信頼度別予測精度の総合レポート作成

目的: 全信頼度（A/B/C/D/E）の詳細分析と比較

分析内容:
1. 信頼度別の三連単的中率
2. 1着・2着・3着の個別的中率
3. 月別推移
4. 会場別推移
5. 信頼度分布

出力:
- 総合レポート: output/comprehensive_accuracy_report.md
- CSVデータ: output/comprehensive_accuracy.csv
- グラフ: output/comprehensive_accuracy.png
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

plt.rcParams['font.sans-serif'] = ['MS Gothic', 'Yu Gothic', 'Meiryo']
plt.rcParams['axes.unicode_minus'] = False


def analyze_comprehensive_accuracy(db_path: str, start_date: str = '2025-01-01', end_date: str = '2025-12-31'):
    """
    信頼度別予測精度の総合分析

    Args:
        db_path: データベースパス
        start_date: 分析開始日
        end_date: 分析終了日
    """
    conn = sqlite3.connect(db_path)

    print("=" * 80)
    print("信頼度別予測精度 総合レポート")
    print("=" * 80)
    print(f"\n分析期間: {start_date} ～ {end_date}")
    print()

    # 基本データ取得（validate_confidence_b_trifecta.pyと同じSQL）
    query = """
    WITH ranked_predictions AS (
        SELECT
            rp.race_id,
            r.race_date,
            r.venue_code,
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
    race_predictions_ranked AS (
        SELECT DISTINCT
            race_id,
            race_date,
            venue_code,
            confidence
        FROM ranked_predictions
        GROUP BY race_id, race_date, venue_code, confidence
    ),
    predicted_trifecta AS (
        SELECT
            rpr.race_id,
            rpr.race_date,
            rpr.venue_code,
            rpr.confidence,
            MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.pit_number END) as pred_1st,
            MAX(CASE WHEN rp.rank_prediction = 2 THEN rp.pit_number END) as pred_2nd,
            MAX(CASE WHEN rp.rank_prediction = 3 THEN rp.pit_number END) as pred_3rd
        FROM race_predictions_ranked rpr
        JOIN ranked_predictions rp ON rpr.race_id = rp.race_id
        WHERE rp.rank_prediction <= 3
        GROUP BY rpr.race_id, rpr.race_date, rpr.venue_code, rpr.confidence
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
        pt.confidence,
        pt.pred_1st,
        pt.pred_2nd,
        pt.pred_3rd,
        at.actual_1st,
        at.actual_2nd,
        at.actual_3rd,
        CASE WHEN pt.pred_1st = at.actual_1st THEN 1 ELSE 0 END as is_1st_hit,
        CASE WHEN pt.pred_2nd = at.actual_2nd THEN 1 ELSE 0 END as is_2nd_hit,
        CASE WHEN pt.pred_3rd = at.actual_3rd THEN 1 ELSE 0 END as is_3rd_hit,
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

    df = pd.read_sql_query(query, conn, params=(start_date, end_date))
    conn.close()

    if len(df) == 0:
        print("警告: データが見つかりません。")
        return

    print(f"総レース数: {len(df):,}レース")
    print()

    # 1. 信頼度分布
    print("=" * 80)
    print("【1】 信頼度分布")
    print("=" * 80)
    print()

    conf_dist = df['confidence'].value_counts().sort_index()
    for conf in ['A', 'B', 'C', 'D', 'E']:
        count = conf_dist.get(conf, 0)
        pct = count / len(df) * 100 if len(df) > 0 else 0
        print(f"信頼度{conf}: {count:,}レース ({pct:.1f}%)")
    print()

    # 2. 信頼度別的中率
    print("=" * 80)
    print("【2】 信頼度別的中率")
    print("=" * 80)
    print()

    results = []
    for conf in ['A', 'B', 'C', 'D', 'E']:
        df_conf = df[df['confidence'] == conf]
        if len(df_conf) == 0:
            continue

        trifecta_rate = df_conf['is_trifecta_hit'].mean() * 100
        first_rate = df_conf['is_1st_hit'].mean() * 100

        # 1着的中時の2着的中率
        df_1st = df_conf[df_conf['is_1st_hit'] == 1]
        second_rate = df_1st['is_2nd_hit'].mean() * 100 if len(df_1st) > 0 else 0

        # 1-2着的中時の3着的中率
        df_12 = df_1st[df_1st['is_2nd_hit'] == 1]
        third_rate = df_12['is_3rd_hit'].mean() * 100 if len(df_12) > 0 else 0

        results.append({
            '信頼度': conf,
            'レース数': len(df_conf),
            '三連単的中率(%)': round(trifecta_rate, 2),
            '1着的中率(%)': round(first_rate, 2),
            '2着的中率(%)': round(second_rate, 2),
            '3着的中率(%)': round(third_rate, 2)
        })

        print(f"信頼度{conf}:")
        print(f"  レース数: {len(df_conf):,}件")
        print(f"  三連単的中率: {trifecta_rate:.2f}%")
        print(f"  1着的中率: {first_rate:.2f}%")
        print(f"  2着的中率（1着的中時）: {second_rate:.2f}%")
        print(f"  3着的中率（1-2着的中時）: {third_rate:.2f}%")
        print()

    df_results = pd.DataFrame(results)

    # 3. 月別推移（主要信頼度のみ）
    print("=" * 80)
    print("【3】 月別推移（信頼度B）")
    print("=" * 80)
    print()

    df['race_date'] = pd.to_datetime(df['race_date'])
    df['month'] = df['race_date'].dt.month

    df_b = df[df['confidence'] == 'B']
    if len(df_b) > 0:
        monthly_b = df_b.groupby('month').agg({
            'race_id': 'count',
            'is_trifecta_hit': 'mean'
        }).round(4)
        monthly_b.columns = ['レース数', '三連単的中率']
        monthly_b['三連単的中率'] *= 100

        print(monthly_b.to_string())
        print()

    # CSVレポート出力
    output_dir = Path('output')
    output_dir.mkdir(exist_ok=True)

    csv_path = output_dir / 'comprehensive_accuracy.csv'
    df_results.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"CSVレポート出力: {csv_path}")

    # グラフ生成
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # グラフ1: 信頼度別レース数
    ax1 = axes[0, 0]
    conf_counts = df_results['レース数'].values
    conf_labels = df_results['信頼度'].values
    ax1.bar(conf_labels, conf_counts, color='steelblue', alpha=0.7)
    ax1.set_xlabel('信頼度', fontsize=12)
    ax1.set_ylabel('レース数', fontsize=12)
    ax1.set_title('信頼度別レース数', fontsize=14, fontweight='bold')
    ax1.grid(axis='y', alpha=0.3)

    # グラフ2: 信頼度別三連単的中率
    ax2 = axes[0, 1]
    trifecta_rates = df_results['三連単的中率(%)'].values
    bars = ax2.bar(conf_labels, trifecta_rates, color='forestgreen', alpha=0.7)
    ax2.axhline(y=5.0, color='red', linestyle='--', linewidth=2, label='基準5%')
    ax2.set_xlabel('信頼度', fontsize=12)
    ax2.set_ylabel('三連単的中率 (%)', fontsize=12)
    ax2.set_title('信頼度別三連単的中率', fontsize=14, fontweight='bold')
    ax2.legend()
    ax2.grid(axis='y', alpha=0.3)

    # グラフ3: 信頼度別1着的中率
    ax3 = axes[1, 0]
    first_rates = df_results['1着的中率(%)'].values
    ax3.bar(conf_labels, first_rates, color='orange', alpha=0.7)
    ax3.set_xlabel('信頼度', fontsize=12)
    ax3.set_ylabel('1着的中率 (%)', fontsize=12)
    ax3.set_title('信頼度別1着的中率', fontsize=14, fontweight='bold')
    ax3.grid(axis='y', alpha=0.3)

    # グラフ4: 月別推移（信頼度B）
    ax4 = axes[1, 1]
    if len(df_b) > 0 and len(monthly_b) > 0:
        months = monthly_b.index
        rates = monthly_b['三連単的中率']
        ax4.plot(months, rates, marker='o', color='steelblue', linewidth=2)
        ax4.axhline(y=5.0, color='red', linestyle='--', linewidth=2, label='基準5%')
        ax4.set_xlabel('月', fontsize=12)
        ax4.set_ylabel('三連単的中率 (%)', fontsize=12)
        ax4.set_title('月別三連単的中率（信頼度B）', fontsize=14, fontweight='bold')
        ax4.legend()
        ax4.grid(alpha=0.3)

    plt.tight_layout()

    png_path = output_dir / 'comprehensive_accuracy.png'
    plt.savefig(png_path, dpi=150, bbox_inches='tight')
    print(f"グラフ出力: {png_path}")
    plt.close()

    # Markdownレポート生成
    md_path = output_dir / 'comprehensive_accuracy_report.md'
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write("# 信頼度別予測精度 総合レポート\n\n")
        f.write(f"**分析期間**: {start_date} ～ {end_date}\n\n")
        f.write(f"**総レース数**: {len(df):,}レース\n\n")
        f.write("---\n\n")

        f.write("## 1. 信頼度分布\n\n")
        f.write("| 信頼度 | レース数 | 割合 |\n")
        f.write("|--------|----------|------|\n")
        for conf in ['A', 'B', 'C', 'D', 'E']:
            count = conf_dist.get(conf, 0)
            pct = count / len(df) * 100 if len(df) > 0 else 0
            f.write(f"| {conf} | {count:,} | {pct:.1f}% |\n")
        f.write("\n")

        f.write("## 2. 信頼度別的中率\n\n")
        f.write("| 信頼度 | レース数 | 三連単的中率 | 1着的中率 | 2着的中率 | 3着的中率 |\n")
        f.write("|--------|----------|--------------|-----------|-----------|------------|\n")
        for _, row in df_results.iterrows():
            f.write(f"| {row['信頼度']} | {row['レース数']:,} | {row['三連単的中率(%)']}% | ")
            f.write(f"{row['1着的中率(%)']}% | {row['2着的中率(%)']}% | {row['3着的中率(%)']}% |\n")
        f.write("\n")

        f.write("## 3. 重要な知見\n\n")

        # 信頼度Bの評価
        b_row = df_results[df_results['信頼度'] == 'B']
        if not b_row.empty:
            b_trifecta = b_row.iloc[0]['三連単的中率(%)']
            if b_trifecta >= 5.0:
                f.write(f"- ✅ **信頼度B**: 三連単的中率{b_trifecta}%は基準（5%）をクリア\n")
            else:
                f.write(f"- ⚠️ **信頼度B**: 三連単的中率{b_trifecta}%は基準（5%）未達\n")

        # 信頼度Cの評価
        c_row = df_results[df_results['信頼度'] == 'C']
        if not c_row.empty:
            c_trifecta = c_row.iloc[0]['三連単的中率(%)']
            if c_trifecta >= 5.0:
                f.write(f"- ✅ **信頼度C**: 三連単的中率{c_trifecta}%は基準（5%）をクリア\n")
            else:
                f.write(f"- ⚠️ **信頼度C**: 三連単的中率{c_trifecta}%は基準（5%）未達\n")

        f.write("\n")
        f.write("---\n\n")
        f.write(f"**作成日時**: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    print(f"Markdownレポート出力: {md_path}")
    print()

    print("=" * 80)
    print("[OK] 信頼度別予測精度の総合分析が完了しました")
    print("=" * 80)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='信頼度別予測精度の総合分析')
    parser.add_argument('--db', default='data/boatrace.db', help='データベースパス')
    parser.add_argument('--start', default='2025-01-01', help='分析開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', default='2025-12-31', help='分析終了日 (YYYY-MM-DD)')

    args = parser.parse_args()

    try:
        analyze_comprehensive_accuracy(args.db, args.start, args.end)
    except Exception as e:
        print()
        print("=" * 80)
        print("[ERROR] 総合分析でエラーが発生しました")
        print("=" * 80)
        print(f"\nエラー内容: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
