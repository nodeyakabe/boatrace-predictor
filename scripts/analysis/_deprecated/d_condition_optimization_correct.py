"""
D×35-60条件の最適化分析スクリプト（正確版）
3連単買い目（予測1-2-3）の的中で計算
"""
import sqlite3
import pandas as pd
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "boatrace.db"

def get_connection():
    return sqlite3.connect(DB_PATH)

def create_base_df():
    """ベースデータフレームを作成"""
    conn = get_connection()

    query = """
    WITH pred_combos AS (
        SELECT
            r.id as race_id,
            r.race_date,
            r.venue_code,
            r.race_number,
            strftime('%Y', r.race_date) as year,
            (SELECT pit_number FROM race_predictions WHERE race_id = r.id AND rank_prediction = 1 AND prediction_type = 'advance') as pred_1,
            (SELECT pit_number FROM race_predictions WHERE race_id = r.id AND rank_prediction = 2 AND prediction_type = 'advance') as pred_2,
            (SELECT pit_number FROM race_predictions WHERE race_id = r.id AND rank_prediction = 3 AND prediction_type = 'advance') as pred_3,
            (SELECT confidence FROM race_predictions WHERE race_id = r.id AND rank_prediction = 1 AND prediction_type = 'advance') as confidence
        FROM races r
        WHERE r.race_date >= '2020-01-01'
        AND r.race_date <= '2025-12-31'
    ),
    actual_results AS (
        SELECT
            race_id,
            MAX(CASE WHEN rank = '1' THEN pit_number END) as actual_1,
            MAX(CASE WHEN rank = '2' THEN pit_number END) as actual_2,
            MAX(CASE WHEN rank = '3' THEN pit_number END) as actual_3
        FROM results
        WHERE is_invalid = 0 AND rank IN ('1', '2', '3')
        GROUP BY race_id
    ),
    with_odds AS (
        SELECT
            pc.race_id,
            pc.race_date,
            pc.venue_code,
            pc.race_number,
            pc.year,
            pc.pred_1, pc.pred_2, pc.pred_3,
            pc.confidence,
            ar.actual_1, ar.actual_2, ar.actual_3,
            e.racer_rank as c1_rank,
            pred_odds.odds as pred_combo_odds,
            actual_odds.odds as actual_combo_odds,
            CASE WHEN pc.pred_1 = ar.actual_1 AND pc.pred_2 = ar.actual_2 AND pc.pred_3 = ar.actual_3 THEN 1 ELSE 0 END as is_hit
        FROM pred_combos pc
        INNER JOIN actual_results ar ON pc.race_id = ar.race_id
        INNER JOIN entries e ON pc.race_id = e.race_id AND e.pit_number = 1
        LEFT JOIN trifecta_odds pred_odds ON pc.race_id = pred_odds.race_id
            AND pred_odds.combination = pc.pred_1 || '-' || pc.pred_2 || '-' || pc.pred_3
        LEFT JOIN trifecta_odds actual_odds ON pc.race_id = actual_odds.race_id
            AND actual_odds.combination = ar.actual_1 || '-' || ar.actual_2 || '-' || ar.actual_3
        WHERE pc.confidence = 'D'
        AND pc.pred_1 IS NOT NULL
        AND pc.pred_2 IS NOT NULL
        AND pc.pred_3 IS NOT NULL
    )
    SELECT * FROM with_odds
    """

    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def calc_stats(df, name=""):
    """統計を計算して表示"""
    if len(df) == 0:
        return {'count': 0, 'hits': 0, 'roi': 0, 'profit': 0, 'black_years': 0}

    hits = df['is_hit'].sum()
    total = len(df)
    # 的中した場合は払戻オッズ（actual_combo_odds）を使用
    payout = df[df['is_hit'] == 1]['actual_combo_odds'].sum()
    roi = payout * 100 / total if total > 0 else 0
    profit = payout * 100 - total * 100

    # 黒字年数カウント
    black_years = 0
    for year in df['year'].unique():
        year_data = df[df['year'] == year]
        if len(year_data) > 0:
            year_payout = year_data[year_data['is_hit'] == 1]['actual_combo_odds'].sum()
            year_roi = year_payout * 100 / len(year_data)
            if year_roi >= 100:
                black_years += 1

    return {
        'count': total,
        'hits': hits,
        'roi': roi,
        'profit': profit,
        'black_years': black_years
    }

def print_year_breakdown(df, title=""):
    """年度別内訳を表示"""
    print(f"\n  {title} 年度別:")
    for year in sorted(df['year'].unique()):
        year_data = df[df['year'] == year]
        stats = calc_stats(year_data)
        status = "◎" if stats['roi'] >= 100 else "×"
        print(f"    {year}年: {stats['count']}件, 的中{stats['hits']}件, ROI {stats['roi']:.1f}%, 収支 {stats['profit']:+,.0f}円 {status}")

def main():
    print("=" * 80)
    print("D×35-60条件 最適化分析（正確版）")
    print("3連単買い目（予測1-2-3）の的中判定を使用")
    print("=" * 80)

    df = create_base_df()
    print(f"\n信頼度Dの全データ: {len(df)}件（オッズ条件なし）")

    # ============================================================
    # 1. 現行条件の確認
    # ============================================================
    print("\n" + "=" * 80)
    print("1. 現行条件（D×35-60×A1/A2/B1、9R除外、三国除外）の確認")
    print("=" * 80)

    current = df[
        (df['pred_combo_odds'] >= 35) &
        (df['pred_combo_odds'] < 60) &
        (df['c1_rank'].isin(['A1', 'A2', 'B1'])) &
        (df['race_number'] != 9) &
        (df['venue_code'] != '10')
    ]
    stats = calc_stats(current)
    print(f"\n現行条件: {stats['count']}件, 的中{stats['hits']}件, ROI {stats['roi']:.1f}%, 収支 {stats['profit']:+,.0f}円, {stats['black_years']}/6年黒字")
    print_year_breakdown(current, "現行条件")

    # ============================================================
    # 2. オッズ範囲の再調整
    # ============================================================
    print("\n" + "=" * 80)
    print("2. オッズ範囲別ROI比較（A1/A2/B1、9R除外、三国除外）")
    print("=" * 80)

    odds_ranges = [
        (35, 60, "35-60倍（現行）"),
        (40, 55, "40-55倍"),
        (40, 60, "40-60倍"),
        (35, 55, "35-55倍"),
        (45, 60, "45-60倍"),
        (35, 50, "35-50倍"),
        (40, 50, "40-50倍"),
        (30, 60, "30-60倍"),
        (30, 50, "30-50倍"),
        (50, 70, "50-70倍"),
        (45, 55, "45-55倍"),
        (50, 60, "50-60倍"),
    ]

    base_df = df[
        (df['c1_rank'].isin(['A1', 'A2', 'B1'])) &
        (df['race_number'] != 9) &
        (df['venue_code'] != '10')
    ]

    print(f"\n{'オッズ範囲':<20} {'件数':>8} {'的中':>6} {'的中率':>8} {'ROI':>10} {'収支':>12} {'黒字年':>8}")
    print("-" * 80)

    odds_results = []
    for low, high, label in odds_ranges:
        subset = base_df[(base_df['pred_combo_odds'] >= low) & (base_df['pred_combo_odds'] < high)]
        stats = calc_stats(subset)
        odds_results.append({'label': label, 'low': low, 'high': high, **stats})
        hit_rate = stats['hits'] / stats['count'] * 100 if stats['count'] > 0 else 0
        roi_mark = "◎" if stats['roi'] >= 100 else "×"
        print(f"{label:<20} {stats['count']:>8} {stats['hits']:>6} {hit_rate:>7.1f}% {stats['roi']:>9.1f}% {stats['profit']:>+11,.0f}円 {stats['black_years']}/6年 {roi_mark}")

    # 有望なオッズ範囲の年度別詳細
    print("\n--- 有望オッズ範囲の年度別詳細 ---")
    for res in sorted(odds_results, key=lambda x: x['roi'], reverse=True)[:5]:
        if res['count'] >= 30:
            subset = base_df[(base_df['pred_combo_odds'] >= res['low']) & (base_df['pred_combo_odds'] < res['high'])]
            print(f"\n{res['label']} (全体ROI {res['roi']:.1f}%):")
            print_year_breakdown(subset, "")

    # ============================================================
    # 3. 級別の絞り込み
    # ============================================================
    print("\n" + "=" * 80)
    print("3. 級別ROI比較（35-60倍、9R除外、三国除外）")
    print("=" * 80)

    rank_combinations = [
        (['A1', 'A2', 'B1'], "A1/A2/B1（現行）"),
        (['B1'], "B1のみ"),
        (['A1', 'B1'], "A1/B1"),
        (['A2', 'B1'], "A2/B1"),
        (['A1'], "A1のみ"),
        (['A2'], "A2のみ"),
        (['A1', 'A2'], "A1/A2"),
    ]

    base_odds_df = df[
        (df['pred_combo_odds'] >= 35) &
        (df['pred_combo_odds'] < 60) &
        (df['race_number'] != 9) &
        (df['venue_code'] != '10')
    ]

    print(f"\n{'級別組み合わせ':<20} {'件数':>8} {'的中':>6} {'的中率':>8} {'ROI':>10} {'収支':>12} {'黒字年':>8}")
    print("-" * 80)

    rank_results = []
    for ranks, label in rank_combinations:
        subset = base_odds_df[base_odds_df['c1_rank'].isin(ranks)]
        stats = calc_stats(subset)
        rank_results.append({'ranks': ranks, 'label': label, **stats})
        hit_rate = stats['hits'] / stats['count'] * 100 if stats['count'] > 0 else 0
        roi_mark = "◎" if stats['roi'] >= 100 else "×"
        print(f"{label:<20} {stats['count']:>8} {stats['hits']:>6} {hit_rate:>7.1f}% {stats['roi']:>9.1f}% {stats['profit']:>+11,.0f}円 {stats['black_years']}/6年 {roi_mark}")

    # 各級別の年度別詳細
    print("\n--- 各級別の年度別詳細 ---")
    for res in rank_results[:4]:
        subset = base_odds_df[base_odds_df['c1_rank'].isin(res['ranks'])]
        print(f"\n{res['label']} (全体ROI {res['roi']:.1f}%):")
        print_year_breakdown(subset, "")

    # ============================================================
    # 4. オッズ×級別マトリックス
    # ============================================================
    print("\n" + "=" * 80)
    print("4. オッズ×級別マトリックス（9R除外、三国除外、ROI）")
    print("=" * 80)

    base_filter_df = df[
        (df['race_number'] != 9) &
        (df['venue_code'] != '10')
    ]

    print(f"\n{'オッズ\\級別':<15}", end="")
    for ranks, label in rank_combinations[:5]:
        print(f"{label[:12]:>12}", end="")
    print()
    print("-" * 75)

    matrix_results = []
    for low, high, odds_label in odds_ranges[:9]:
        print(f"{odds_label[:15]:<15}", end="")
        for ranks, rank_label in rank_combinations[:5]:
            subset = base_filter_df[
                (base_filter_df['pred_combo_odds'] >= low) &
                (base_filter_df['pred_combo_odds'] < high) &
                (base_filter_df['c1_rank'].isin(ranks))
            ]
            stats = calc_stats(subset)
            matrix_results.append({
                'odds_label': odds_label, 'rank_label': rank_label,
                'low': low, 'high': high, 'ranks': ranks, **stats
            })
            if stats['count'] > 0:
                mark = "◎" if stats['roi'] >= 100 else ""
                print(f"{stats['roi']:>9.1f}%{mark:>2}", end="")
            else:
                print(f"{'---':>12}", end="")
        print()

    # ============================================================
    # 5. 有望な組み合わせランキング
    # ============================================================
    print("\n" + "=" * 80)
    print("5. 有望な組み合わせランキング（ROI順、件数30以上）")
    print("=" * 80)

    valid_results = [r for r in matrix_results if r['count'] >= 30]
    valid_results.sort(key=lambda x: x['roi'], reverse=True)

    print(f"\n{'順位':<4} {'オッズ×級別':<35} {'件数':>6} {'ROI':>10} {'収支':>12} {'黒字年':>8}")
    print("-" * 85)

    for i, res in enumerate(valid_results[:20], 1):
        combo = f"{res['odds_label']} × {res['rank_label']}"
        roi_mark = "◎" if res['roi'] >= 100 else ""
        print(f"{i:<4} {combo:<35} {res['count']:>6} {res['roi']:>9.1f}% {res['profit']:>+11,.0f}円 {res['black_years']}/6年 {roi_mark}")

    # ============================================================
    # 6. 最有望組み合わせの年度別詳細
    # ============================================================
    print("\n" + "=" * 80)
    print("6. 最有望組み合わせの年度別詳細")
    print("=" * 80)

    for i, res in enumerate([r for r in valid_results if r['roi'] >= 80][:5], 1):
        subset = base_filter_df[
            (base_filter_df['pred_combo_odds'] >= res['low']) &
            (base_filter_df['pred_combo_odds'] < res['high']) &
            (base_filter_df['c1_rank'].isin(res['ranks']))
        ]
        print(f"\n{i}. {res['odds_label']} × {res['rank_label']} (全体ROI {res['roi']:.1f}%)")
        print_year_breakdown(subset, "")

    # ============================================================
    # 7. 除外条件の効果検証
    # ============================================================
    print("\n" + "=" * 80)
    print("7. 除外条件の効果検証（35-60倍×A1/A2/B1に対して）")
    print("=" * 80)

    base_cond = df[
        (df['pred_combo_odds'] >= 35) &
        (df['pred_combo_odds'] < 60) &
        (df['c1_rank'].isin(['A1', 'A2', 'B1']))
    ]

    filters = [
        ("除外なし", base_cond),
        ("9R除外のみ", base_cond[base_cond['race_number'] != 9]),
        ("三国除外のみ", base_cond[base_cond['venue_code'] != '10']),
        ("両方除外", base_cond[(base_cond['race_number'] != 9) & (base_cond['venue_code'] != '10')]),
    ]

    print(f"\n{'フィルター':<15} {'件数':>8} {'ROI':>10} {'収支':>12} {'黒字年':>8}")
    print("-" * 60)

    for name, subset in filters:
        stats = calc_stats(subset)
        roi_mark = "◎" if stats['roi'] >= 100 else ""
        print(f"{name:<15} {stats['count']:>8} {stats['roi']:>9.1f}% {stats['profit']:>+11,.0f}円 {stats['black_years']}/6年 {roi_mark}")

    # ============================================================
    # 8. 2025年単年の成績比較
    # ============================================================
    print("\n" + "=" * 80)
    print("8. 2025年単年成績（有望組み合わせ）")
    print("=" * 80)

    df_2025 = base_filter_df[base_filter_df['year'] == '2025']

    print(f"\n{'オッズ×級別':<35} {'件数':>6} {'的中':>6} {'ROI':>10} {'収支':>12}")
    print("-" * 75)

    for res in valid_results[:15]:
        subset = df_2025[
            (df_2025['pred_combo_odds'] >= res['low']) &
            (df_2025['pred_combo_odds'] < res['high']) &
            (df_2025['c1_rank'].isin(res['ranks']))
        ]
        if len(subset) > 0:
            stats = calc_stats(subset)
            combo = f"{res['odds_label']} × {res['rank_label']}"
            roi_mark = "◎" if stats['roi'] >= 100 else ""
            print(f"{combo:<35} {stats['count']:>6} {stats['hits']:>6} {stats['roi']:>9.1f}% {stats['profit']:>+11,.0f}円 {roi_mark}")

    # ============================================================
    # 9. 最終推奨
    # ============================================================
    print("\n" + "=" * 80)
    print("9. 最終推奨")
    print("=" * 80)

    # ROI >= 100% の条件
    profitable = [r for r in valid_results if r['roi'] >= 100]
    # ROI >= 80% かつ 黒字年 >= 2 の条件
    promising = [r for r in valid_results if r['roi'] >= 80 and r['black_years'] >= 2 and r not in profitable]

    if profitable:
        print("\n【採用推奨】ROI 100%以上の条件:")
        for i, res in enumerate(profitable[:3], 1):
            print(f"\n  {i}. {res['odds_label']} × {res['rank_label']}")
            print(f"     6年間: {res['count']}件, ROI {res['roi']:.1f}%, 収支 {res['profit']:+,.0f}円")
            print(f"     安定性: {res['black_years']}/6年黒字")
    else:
        print("\nROI 100%以上の条件なし")

    if promising:
        print("\n【要検討】ROI 80%以上、2年以上黒字の条件:")
        for i, res in enumerate(promising[:3], 1):
            print(f"\n  {i}. {res['odds_label']} × {res['rank_label']}")
            print(f"     6年間: {res['count']}件, ROI {res['roi']:.1f}%, 収支 {res['profit']:+,.0f}円")
            print(f"     安定性: {res['black_years']}/6年黒字")

    # 現行条件との比較
    print("\n" + "=" * 80)
    print("10. 改善提案")
    print("=" * 80)

    current_stats = calc_stats(current)
    print(f"\n現行条件: D×35-60×A1/A2/B1（9R除外、三国除外）")
    print(f"  ROI: {current_stats['roi']:.1f}%, 収支: {current_stats['profit']:+,.0f}円, 黒字年: {current_stats['black_years']}/6年")

    if profitable:
        best = profitable[0]
        print(f"\n推奨変更: {best['odds_label']} × {best['rank_label']}")
        print(f"  ROI: {best['roi']:.1f}%, 収支: {best['profit']:+,.0f}円, 黒字年: {best['black_years']}/6年")
        print(f"  改善効果: ROI {best['roi'] - current_stats['roi']:+.1f}pt, 収支 {best['profit'] - current_stats['profit']:+,.0f}円")
    else:
        print("\n推奨: D×35-60条件は廃止を検討")
        print("  理由: すべての組み合わせでROI 100%未満")

if __name__ == "__main__":
    main()
