"""
D×35-60条件の最適化分析スクリプト
"""
import sqlite3
import pandas as pd
from pathlib import Path

# データベースパス
DB_PATH = Path(__file__).parent.parent.parent / "data" / "boatrace.db"

def get_connection():
    return sqlite3.connect(DB_PATH)

def analyze_d_condition():
    """D×35-60条件の詳細分析"""
    conn = get_connection()

    # 基本クエリ: 信頼度D、1位予測、結果付きレース
    base_query = """
    WITH prediction_results AS (
        SELECT
            r.id as race_id,
            r.race_date,
            r.venue_code,
            r.race_number,
            strftime('%Y', r.race_date) as year,
            rp.pit_number as pred_pit,
            rp.confidence,
            e.racer_rank,
            t.odds as trifecta_odds,
            CASE
                WHEN res1.pit_number = rp.pit_number
                     AND res2.pit_number IS NOT NULL
                     AND res3.pit_number IS NOT NULL
                THEN 1 ELSE 0
            END as is_hit,
            res1.pit_number as first_place,
            res2.pit_number as second_place,
            res3.pit_number as third_place
        FROM races r
        INNER JOIN race_predictions rp ON r.id = rp.race_id
        INNER JOIN entries e ON r.id = e.race_id AND rp.pit_number = e.pit_number
        INNER JOIN results res1 ON r.id = res1.race_id AND res1.rank = '1' AND res1.is_invalid = 0
        INNER JOIN results res2 ON r.id = res2.race_id AND res2.rank = '2' AND res2.is_invalid = 0
        INNER JOIN results res3 ON r.id = res3.race_id AND res3.rank = '3' AND res3.is_invalid = 0
        LEFT JOIN trifecta_odds t ON r.id = t.race_id
            AND t.combination = res1.pit_number || '-' || res2.pit_number || '-' || res3.pit_number
        WHERE rp.rank_prediction = 1
        AND rp.confidence = 'D'
        AND r.race_date >= '2020-01-01'
        AND r.race_date <= '2025-12-31'
    )
    SELECT * FROM prediction_results
    """

    print("=" * 80)
    print("D×35-60条件 最適化分析")
    print("=" * 80)

    df = pd.read_sql_query(base_query, conn)
    print(f"\n基本データ取得: {len(df)}件")

    # 1. 現行条件の確認（35-60倍、A1/A2/B1、9R除外、三国除外）
    print("\n" + "=" * 80)
    print("1. 現行条件（D×35-60×A1/A2/B1、9R除外、三国除外）の確認")
    print("=" * 80)

    current_cond = df[
        (df['trifecta_odds'] >= 35) &
        (df['trifecta_odds'] < 60) &
        (df['racer_rank'].isin(['A1', 'A2', 'B1'])) &
        (df['race_number'] != 9) &
        (df['venue_code'] != '10')  # 三国
    ].copy()

    print(f"\n現行条件の全体成績:")
    print_stats(current_cond)

    print(f"\n年度別成績:")
    for year in sorted(current_cond['year'].unique()):
        year_data = current_cond[current_cond['year'] == year]
        hits = year_data['is_hit'].sum()
        total = len(year_data)
        roi = year_data[year_data['is_hit'] == 1]['trifecta_odds'].sum() * 100 / total if total > 0 else 0
        profit = year_data[year_data['is_hit'] == 1]['trifecta_odds'].sum() * 100 - total * 100
        status = "◎" if roi >= 100 else "×"
        print(f"  {year}年: {total}件, 的中{hits}件, ROI {roi:.1f}%, 収支 {profit:+,.0f}円 {status}")

    # 2. オッズ範囲の再調整
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
    ]

    base_df = df[
        (df['racer_rank'].isin(['A1', 'A2', 'B1'])) &
        (df['race_number'] != 9) &
        (df['venue_code'] != '10')
    ].copy()

    print(f"\n{'オッズ範囲':<20} {'件数':>8} {'的中':>6} {'的中率':>8} {'ROI':>10} {'収支':>12} {'黒字年':>8}")
    print("-" * 80)

    results_odds = []
    for low, high, label in odds_ranges:
        subset = base_df[(base_df['trifecta_odds'] >= low) & (base_df['trifecta_odds'] < high)]
        if len(subset) > 0:
            hits = subset['is_hit'].sum()
            total = len(subset)
            roi = subset[subset['is_hit'] == 1]['trifecta_odds'].sum() * 100 / total if total > 0 else 0
            profit = subset[subset['is_hit'] == 1]['trifecta_odds'].sum() * 100 - total * 100
            hit_rate = hits / total * 100 if total > 0 else 0

            # 黒字年数カウント
            black_years = 0
            for year in subset['year'].unique():
                year_data = subset[subset['year'] == year]
                year_roi = year_data[year_data['is_hit'] == 1]['trifecta_odds'].sum() * 100 / len(year_data) if len(year_data) > 0 else 0
                if year_roi >= 100:
                    black_years += 1

            results_odds.append({
                'range': label, 'count': total, 'hits': hits, 'hit_rate': hit_rate,
                'roi': roi, 'profit': profit, 'black_years': black_years, 'low': low, 'high': high
            })

            roi_mark = "◎" if roi >= 100 else "×"
            print(f"{label:<20} {total:>8} {hits:>6} {hit_rate:>7.1f}% {roi:>9.1f}% {profit:>+11,.0f}円 {black_years}/6年 {roi_mark}")

    # 各オッズ範囲の年度別詳細
    print("\n--- 各オッズ範囲の年度別ROI ---")
    for res in results_odds[:5]:  # 上位5つのみ
        print(f"\n{res['range']}:")
        subset = base_df[(base_df['trifecta_odds'] >= res['low']) & (base_df['trifecta_odds'] < res['high'])]
        for year in sorted(subset['year'].unique()):
            year_data = subset[subset['year'] == year]
            year_roi = year_data[year_data['is_hit'] == 1]['trifecta_odds'].sum() * 100 / len(year_data) if len(year_data) > 0 else 0
            year_profit = year_data[year_data['is_hit'] == 1]['trifecta_odds'].sum() * 100 - len(year_data) * 100
            status = "◎" if year_roi >= 100 else "×"
            print(f"  {year}年: {len(year_data)}件, ROI {year_roi:.1f}%, 収支 {year_profit:+,.0f}円 {status}")

    # 3. 級別の絞り込み
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
        (df['trifecta_odds'] >= 35) &
        (df['trifecta_odds'] < 60) &
        (df['race_number'] != 9) &
        (df['venue_code'] != '10')
    ].copy()

    print(f"\n{'級別組み合わせ':<20} {'件数':>8} {'的中':>6} {'的中率':>8} {'ROI':>10} {'収支':>12} {'黒字年':>8}")
    print("-" * 80)

    results_rank = []
    for ranks, label in rank_combinations:
        subset = base_odds_df[base_odds_df['racer_rank'].isin(ranks)]
        if len(subset) > 0:
            hits = subset['is_hit'].sum()
            total = len(subset)
            roi = subset[subset['is_hit'] == 1]['trifecta_odds'].sum() * 100 / total if total > 0 else 0
            profit = subset[subset['is_hit'] == 1]['trifecta_odds'].sum() * 100 - total * 100
            hit_rate = hits / total * 100 if total > 0 else 0

            # 黒字年数カウント
            black_years = 0
            for year in subset['year'].unique():
                year_data = subset[subset['year'] == year]
                year_roi = year_data[year_data['is_hit'] == 1]['trifecta_odds'].sum() * 100 / len(year_data) if len(year_data) > 0 else 0
                if year_roi >= 100:
                    black_years += 1

            results_rank.append({
                'ranks': ranks, 'label': label, 'count': total, 'hits': hits,
                'hit_rate': hit_rate, 'roi': roi, 'profit': profit, 'black_years': black_years
            })

            roi_mark = "◎" if roi >= 100 else "×"
            print(f"{label:<20} {total:>8} {hits:>6} {hit_rate:>7.1f}% {roi:>9.1f}% {profit:>+11,.0f}円 {black_years}/6年 {roi_mark}")

    # 各級別の年度別詳細
    print("\n--- 各級別の年度別ROI ---")
    for res in results_rank[:4]:
        print(f"\n{res['label']}:")
        subset = base_odds_df[base_odds_df['racer_rank'].isin(res['ranks'])]
        for year in sorted(subset['year'].unique()):
            year_data = subset[subset['year'] == year]
            year_roi = year_data[year_data['is_hit'] == 1]['trifecta_odds'].sum() * 100 / len(year_data) if len(year_data) > 0 else 0
            year_profit = year_data[year_data['is_hit'] == 1]['trifecta_odds'].sum() * 100 - len(year_data) * 100
            status = "◎" if year_roi >= 100 else "×"
            print(f"  {year}年: {len(year_data)}件, ROI {year_roi:.1f}%, 収支 {year_profit:+,.0f}円 {status}")

    # 4. オッズ×級別マトリックス
    print("\n" + "=" * 80)
    print("4. オッズ×級別マトリックス（9R除外、三国除外、ROI）")
    print("=" * 80)

    base_filter_df = df[
        (df['race_number'] != 9) &
        (df['venue_code'] != '10')
    ].copy()

    # マトリックス表示
    print(f"\n{'オッズ\\級別':<12}", end="")
    for ranks, label in rank_combinations[:5]:
        print(f"{label[:10]:>12}", end="")
    print()
    print("-" * 72)

    matrix_results = []
    for low, high, odds_label in odds_ranges[:7]:
        print(f"{odds_label[:12]:<12}", end="")
        for ranks, rank_label in rank_combinations[:5]:
            subset = base_filter_df[
                (base_filter_df['trifecta_odds'] >= low) &
                (base_filter_df['trifecta_odds'] < high) &
                (base_filter_df['racer_rank'].isin(ranks))
            ]
            if len(subset) > 0:
                roi = subset[subset['is_hit'] == 1]['trifecta_odds'].sum() * 100 / len(subset)
                profit = subset[subset['is_hit'] == 1]['trifecta_odds'].sum() * 100 - len(subset) * 100

                # 黒字年数
                black_years = 0
                for year in subset['year'].unique():
                    year_data = subset[subset['year'] == year]
                    year_roi = year_data[year_data['is_hit'] == 1]['trifecta_odds'].sum() * 100 / len(year_data) if len(year_data) > 0 else 0
                    if year_roi >= 100:
                        black_years += 1

                matrix_results.append({
                    'odds': odds_label, 'ranks': rank_label,
                    'count': len(subset), 'roi': roi, 'profit': profit,
                    'black_years': black_years, 'low': low, 'high': high, 'rank_list': ranks
                })

                mark = "◎" if roi >= 100 else ""
                print(f"{roi:>9.1f}%{mark:>2}", end="")
            else:
                print(f"{'---':>12}", end="")
        print()

    # 5. 有望な組み合わせのランキング
    print("\n" + "=" * 80)
    print("5. 有望な組み合わせランキング（ROI順、件数50以上）")
    print("=" * 80)

    # 件数50以上でフィルタ
    valid_results = [r for r in matrix_results if r['count'] >= 50 and r['roi'] >= 90]
    valid_results.sort(key=lambda x: x['roi'], reverse=True)

    print(f"\n{'順位':<4} {'オッズ×級別':<30} {'件数':>6} {'ROI':>10} {'収支':>12} {'黒字年':>8}")
    print("-" * 80)

    for i, res in enumerate(valid_results[:15], 1):
        combo = f"{res['odds']} × {res['ranks']}"
        roi_mark = "◎" if res['roi'] >= 100 else ""
        print(f"{i:<4} {combo:<30} {res['count']:>6} {res['roi']:>9.1f}% {res['profit']:>+11,.0f}円 {res['black_years']}/6年 {roi_mark}")

    # 6. 最有望組み合わせの詳細分析
    print("\n" + "=" * 80)
    print("6. 最有望組み合わせの年度別詳細")
    print("=" * 80)

    # トップ5の詳細
    for i, res in enumerate(valid_results[:5], 1):
        print(f"\n{i}. {res['odds']} × {res['ranks']}")
        subset = base_filter_df[
            (base_filter_df['trifecta_odds'] >= res['low']) &
            (base_filter_df['trifecta_odds'] < res['high']) &
            (base_filter_df['racer_rank'].isin(res['rank_list']))
        ]
        for year in sorted(subset['year'].unique()):
            year_data = subset[subset['year'] == year]
            hits = year_data['is_hit'].sum()
            total = len(year_data)
            year_roi = year_data[year_data['is_hit'] == 1]['trifecta_odds'].sum() * 100 / total if total > 0 else 0
            year_profit = year_data[year_data['is_hit'] == 1]['trifecta_odds'].sum() * 100 - total * 100
            status = "◎" if year_roi >= 100 else "×"
            print(f"  {year}年: {total}件, 的中{hits}件, ROI {year_roi:.1f}%, 収支 {year_profit:+,.0f}円 {status}")

    # 7. 9R除外・三国除外の効果検証
    print("\n" + "=" * 80)
    print("7. 除外条件の効果検証（最適化後の条件に対して）")
    print("=" * 80)

    if valid_results:
        best = valid_results[0]

        # ベース条件
        print(f"\n検証対象: {best['odds']} × {best['ranks']}")

        # a) 除外なし
        no_filter = df[
            (df['trifecta_odds'] >= best['low']) &
            (df['trifecta_odds'] < best['high']) &
            (df['racer_rank'].isin(best['rank_list']))
        ]

        # b) 9R除外のみ
        r9_filter = df[
            (df['trifecta_odds'] >= best['low']) &
            (df['trifecta_odds'] < best['high']) &
            (df['racer_rank'].isin(best['rank_list'])) &
            (df['race_number'] != 9)
        ]

        # c) 三国除外のみ
        mikuni_filter = df[
            (df['trifecta_odds'] >= best['low']) &
            (df['trifecta_odds'] < best['high']) &
            (df['racer_rank'].isin(best['rank_list'])) &
            (df['venue_code'] != '10')
        ]

        # d) 両方除外
        both_filter = df[
            (df['trifecta_odds'] >= best['low']) &
            (df['trifecta_odds'] < best['high']) &
            (df['racer_rank'].isin(best['rank_list'])) &
            (df['race_number'] != 9) &
            (df['venue_code'] != '10')
        ]

        filters = [
            ("除外なし", no_filter),
            ("9R除外のみ", r9_filter),
            ("三国除外のみ", mikuni_filter),
            ("両方除外", both_filter),
        ]

        print(f"\n{'フィルター':<15} {'件数':>8} {'ROI':>10} {'収支':>12}")
        print("-" * 50)

        for name, subset in filters:
            if len(subset) > 0:
                roi = subset[subset['is_hit'] == 1]['trifecta_odds'].sum() * 100 / len(subset)
                profit = subset[subset['is_hit'] == 1]['trifecta_odds'].sum() * 100 - len(subset) * 100
                roi_mark = "◎" if roi >= 100 else ""
                print(f"{name:<15} {len(subset):>8} {roi:>9.1f}% {profit:>+11,.0f}円 {roi_mark}")

    # 8. 2025年単年の成績比較
    print("\n" + "=" * 80)
    print("8. 2025年単年成績（上位組み合わせ）")
    print("=" * 80)

    df_2025 = base_filter_df[base_filter_df['year'] == '2025']

    print(f"\n{'オッズ×級別':<30} {'件数':>6} {'的中':>6} {'ROI':>10} {'収支':>12}")
    print("-" * 70)

    for res in valid_results[:10]:
        subset = df_2025[
            (df_2025['trifecta_odds'] >= res['low']) &
            (df_2025['trifecta_odds'] < res['high']) &
            (df_2025['racer_rank'].isin(res['rank_list']))
        ]
        if len(subset) > 0:
            hits = subset['is_hit'].sum()
            roi = subset[subset['is_hit'] == 1]['trifecta_odds'].sum() * 100 / len(subset) if len(subset) > 0 else 0
            profit = subset[subset['is_hit'] == 1]['trifecta_odds'].sum() * 100 - len(subset) * 100
            combo = f"{res['odds']} × {res['ranks']}"
            roi_mark = "◎" if roi >= 100 else ""
            print(f"{combo:<30} {len(subset):>6} {hits:>6} {roi:>9.1f}% {profit:>+11,.0f}円 {roi_mark}")

    # 9. 最終推奨
    print("\n" + "=" * 80)
    print("9. 最終推奨")
    print("=" * 80)

    # ROI >= 100% かつ 黒字年 >= 3 の条件を抽出
    recommended = [r for r in valid_results if r['roi'] >= 100 and r['black_years'] >= 3]

    if recommended:
        print("\n推奨条件（ROI >= 100%、黒字年 >= 3年）:")
        for i, res in enumerate(recommended[:5], 1):
            print(f"\n  {i}. {res['odds']} × {res['ranks']}")
            print(f"     6年間: {res['count']}件, ROI {res['roi']:.1f}%, 収支 {res['profit']:+,.0f}円")
            print(f"     安定性: {res['black_years']}/6年黒字")
    else:
        print("\n推奨条件なし（全組み合わせがROI 100%未満または安定性不足）")

    conn.close()

def print_stats(df):
    """統計情報を表示"""
    if len(df) == 0:
        print("  データなし")
        return

    hits = df['is_hit'].sum()
    total = len(df)
    roi = df[df['is_hit'] == 1]['trifecta_odds'].sum() * 100 / total if total > 0 else 0
    profit = df[df['is_hit'] == 1]['trifecta_odds'].sum() * 100 - total * 100
    hit_rate = hits / total * 100 if total > 0 else 0

    print(f"  件数: {total}件")
    print(f"  的中: {hits}件 ({hit_rate:.1f}%)")
    print(f"  ROI: {roi:.1f}%")
    print(f"  収支: {profit:+,.0f}円")

if __name__ == "__main__":
    analyze_d_condition()
