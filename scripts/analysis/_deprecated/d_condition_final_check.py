"""
D×35-60条件の最終検証
条件廃止または代替条件の提案
"""
import sqlite3
import pandas as pd
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "boatrace.db"

def get_connection():
    return sqlite3.connect(DB_PATH)

def calc_stats(df):
    """統計を計算"""
    if len(df) == 0:
        return {'count': 0, 'hits': 0, 'roi': 0, 'profit': 0, 'black_years': 0}

    hits = df['is_hit'].sum()
    total = len(df)
    payout = df[df['is_hit'] == 1]['actual_combo_odds'].sum()
    roi = payout * 100 / total if total > 0 else 0
    profit = payout * 100 - total * 100

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

def main():
    conn = get_connection()

    # 信頼度D全体のデータ取得
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
    )
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
    """

    df = pd.read_sql_query(query, conn)

    print("=" * 80)
    print("D×35-60条件 最終検証レポート")
    print("=" * 80)

    # ============================================================
    # 1. 現行条件の詳細
    # ============================================================
    print("\n" + "=" * 80)
    print("1. 現行条件の評価")
    print("=" * 80)

    current = df[
        (df['pred_combo_odds'] >= 35) &
        (df['pred_combo_odds'] < 60) &
        (df['c1_rank'].isin(['A1', 'A2', 'B1'])) &
        (df['race_number'] != 9) &
        (df['venue_code'] != '10')
    ]
    stats = calc_stats(current)
    print(f"\n現行条件: D×35-60×A1/A2/B1（9R除外、三国除外）")
    print(f"  件数: {stats['count']}, ROI: {stats['roi']:.1f}%, 収支: {stats['profit']:+,.0f}円")
    print(f"  黒字年: {stats['black_years']}/6年")
    print(f"  判定: {'赤字条件 → 廃止検討' if stats['roi'] < 100 else '継続'}")

    # ============================================================
    # 2. 条件全廃止の影響
    # ============================================================
    print("\n" + "=" * 80)
    print("2. 条件廃止の影響")
    print("=" * 80)

    print(f"\n廃止による改善効果:")
    print(f"  投資額削減: {stats['count'] * 100:,.0f}円")
    print(f"  損失回避: {-stats['profit']:+,.0f}円")

    # ============================================================
    # 3. 代替条件の探索（信頼度D全体から黒字領域を探す）
    # ============================================================
    print("\n" + "=" * 80)
    print("3. 代替条件の探索（信頼度D全体から黒字領域を探す）")
    print("=" * 80)

    # 広いオッズ範囲で探索
    base_df = df[(df['race_number'] != 9) & (df['venue_code'] != '10')]

    print("\n【オッズ5倍刻みでの探索】")
    print(f"{'オッズ範囲':<15} {'A1':>15} {'A2':>15} {'B1':>15} {'A1/A2/B1':>15}")
    print("-" * 80)

    for low in range(10, 100, 5):
        high = low + 10
        print(f"{low}-{high}倍        ", end="")
        for ranks in [['A1'], ['A2'], ['B1'], ['A1', 'A2', 'B1']]:
            subset = base_df[
                (base_df['pred_combo_odds'] >= low) &
                (base_df['pred_combo_odds'] < high) &
                (base_df['c1_rank'].isin(ranks))
            ]
            if len(subset) >= 20:
                stats = calc_stats(subset)
                mark = "◎" if stats['roi'] >= 100 else ""
                print(f"{stats['roi']:>6.0f}%({stats['count']:>3}){mark:>2}", end="")
            else:
                print(f"{'---':>15}", end="")
        print()

    # ============================================================
    # 4. 黒字領域の詳細分析
    # ============================================================
    print("\n" + "=" * 80)
    print("4. 黒字領域の詳細分析（ROI 100%以上、件数20以上）")
    print("=" * 80)

    results = []
    for low in range(10, 100, 5):
        for high in [low + 5, low + 10, low + 15, low + 20]:
            for ranks in [['A1'], ['A2'], ['B1'], ['A1', 'A2'], ['A1', 'B1'], ['A2', 'B1'], ['A1', 'A2', 'B1']]:
                subset = base_df[
                    (base_df['pred_combo_odds'] >= low) &
                    (base_df['pred_combo_odds'] < high) &
                    (base_df['c1_rank'].isin(ranks))
                ]
                if len(subset) >= 20:
                    stats = calc_stats(subset)
                    if stats['roi'] >= 100:
                        rank_str = '/'.join(ranks)
                        results.append({
                            'odds_range': f"{low}-{high}倍",
                            'ranks': rank_str,
                            'low': low,
                            'high': high,
                            'rank_list': ranks,
                            **stats
                        })

    if results:
        results.sort(key=lambda x: x['roi'], reverse=True)
        print(f"\n{'順位':<4} {'オッズ×級別':<30} {'件数':>6} {'ROI':>10} {'収支':>12} {'黒字年':>8}")
        print("-" * 80)
        for i, res in enumerate(results[:15], 1):
            combo = f"{res['odds_range']} × {res['ranks']}"
            print(f"{i:<4} {combo:<30} {res['count']:>6} {res['roi']:>9.1f}% {res['profit']:>+11,.0f}円 {res['black_years']}/6年 ◎")

        # 上位3つの年度別詳細
        print("\n【上位条件の年度別詳細】")
        for i, res in enumerate(results[:3], 1):
            subset = base_df[
                (base_df['pred_combo_odds'] >= res['low']) &
                (base_df['pred_combo_odds'] < res['high']) &
                (base_df['c1_rank'].isin(res['rank_list']))
            ]
            print(f"\n{i}. {res['odds_range']} × {res['ranks']} (全体ROI {res['roi']:.1f}%)")
            for year in sorted(subset['year'].unique()):
                year_data = subset[subset['year'] == year]
                year_stats = calc_stats(year_data)
                status = "◎" if year_stats['roi'] >= 100 else "×"
                print(f"  {year}年: {year_stats['count']}件, 的中{year_stats['hits']}件, ROI {year_stats['roi']:.1f}%, 収支 {year_stats['profit']:+,.0f}円 {status}")
    else:
        print("\n黒字領域なし（全組み合わせがROI 100%未満）")

    # ============================================================
    # 5. 結論と推奨
    # ============================================================
    print("\n" + "=" * 80)
    print("5. 結論と推奨")
    print("=" * 80)

    print("\n【現行条件の評価】")
    current_stats = calc_stats(current)
    print(f"  D×35-60×A1/A2/B1（9R除外、三国除外）")
    print(f"  - ROI: {current_stats['roi']:.1f}% (赤字)")
    print(f"  - 6年間損失: {current_stats['profit']:+,.0f}円")
    print(f"  - 安定性: {current_stats['black_years']}/6年黒字 (不安定)")

    print("\n【推奨アクション】")
    if current_stats['roi'] < 100:
        print(f"  1. D×35-60条件を廃止")
        print(f"     → 年間約{-current_stats['profit']/6:,.0f}円の損失回避")

        if results:
            best = results[0]
            if best['roi'] >= 110 and best['black_years'] >= 2:
                print(f"\n  2. 代替条件として以下を検討:")
                print(f"     {best['odds_range']} × {best['ranks']}")
                print(f"     - ROI: {best['roi']:.1f}%")
                print(f"     - 収支: {best['profit']:+,.0f}円")
                print(f"     - 安定性: {best['black_years']}/6年黒字")
            else:
                print(f"\n  2. 代替条件なし")
                print(f"     ※ 安定した黒字領域が見つからないため、D×35-60帯は見送り")
    else:
        print(f"  現行条件を継続")

    conn.close()

if __name__ == "__main__":
    main()
