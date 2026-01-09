"""
逃げ率・まくり率・差し率を使った不的中パターン分析スクリプト（購入条件適用版）

既存の購入条件を適用した上で、追加フィルターの効果を分析
"""

import sqlite3
import pandas as pd
from datetime import datetime

DB_PATH = "data/boatrace.db"

def get_predictions_with_indicators():
    """予測データと指標データを取得"""
    conn = sqlite3.connect(DB_PATH)

    # before予測の1-3着予測を取得
    query = """
    WITH pred_top3 AS (
        SELECT
            race_id,
            MAX(CASE WHEN rank_prediction = 1 THEN pit_number END) AS pred_1st,
            MAX(CASE WHEN rank_prediction = 2 THEN pit_number END) AS pred_2nd,
            MAX(CASE WHEN rank_prediction = 3 THEN pit_number END) AS pred_3rd,
            MAX(CASE WHEN rank_prediction = 1 THEN confidence END) AS confidence,
            MAX(CASE WHEN rank_prediction = 1 THEN total_score END) AS score_1st,
            MAX(CASE WHEN rank_prediction = 2 THEN total_score END) AS score_2nd
        FROM race_predictions
        WHERE prediction_type = 'before'
        GROUP BY race_id
    ),
    actual_top3 AS (
        SELECT
            race_id,
            MAX(CASE WHEN rank = '1' THEN pit_number END) AS actual_1st,
            MAX(CASE WHEN rank = '2' THEN pit_number END) AS actual_2nd,
            MAX(CASE WHEN rank = '3' THEN pit_number END) AS actual_3rd
        FROM results
        WHERE is_invalid = 0 AND rank IN ('1', '2', '3')
        GROUP BY race_id
    )
    SELECT
        r.id AS race_id,
        r.venue_code,
        r.race_date,
        strftime('%Y', r.race_date) AS year,
        strftime('%m', r.race_date) AS month,
        p.pred_1st,
        p.pred_2nd,
        p.pred_3rd,
        p.confidence,
        p.score_1st,
        p.score_2nd,
        a.actual_1st,
        a.actual_2nd,
        a.actual_3rd,
        e.racer_number,
        e.racer_rank,
        o.odds AS trifecta_odds
    FROM races r
    INNER JOIN pred_top3 p ON r.id = p.race_id
    INNER JOIN actual_top3 a ON r.id = a.race_id
    INNER JOIN entries e ON r.id = e.race_id AND e.pit_number = p.pred_1st
    LEFT JOIN trifecta_odds o ON r.id = o.race_id
        AND o.combination = (
            CAST(p.pred_1st AS TEXT) || '-' ||
            CAST(p.pred_2nd AS TEXT) || '-' ||
            CAST(p.pred_3rd AS TEXT)
        )
    WHERE r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
    """

    df = pd.read_sql_query(query, conn)

    # 選手逃げ率（全国データ：stadium_id IS NULL）
    query_escape = """
    SELECT
        player_id AS racer_number,
        escape_rate,
        races_1course
    FROM player_escape_stats
    WHERE stadium_id IS NULL
    """
    df_escape = pd.read_sql_query(query_escape, conn)
    df_escape['racer_number'] = df_escape['racer_number'].astype(str)

    # 会場まくり率・差し率
    query_attack = """
    SELECT
        stadium_id AS venue_code,
        makuri_rate,
        sashi_rate,
        total_races
    FROM stadium_attack_stats
    """
    df_attack = pd.read_sql_query(query_attack, conn)

    conn.close()

    # マージ
    df['racer_number'] = df['racer_number'].astype(str)
    df = df.merge(df_escape, on='racer_number', how='left')
    df = df.merge(df_attack, on='venue_code', how='left')

    # 的中判定
    df['hit'] = (
        (df['pred_1st'] == df['actual_1st']) &
        (df['pred_2nd'] == df['actual_2nd']) &
        (df['pred_3rd'] == df['actual_3rd'])
    ).astype(int)

    # スコア差
    df['score_gap'] = df['score_1st'] - df['score_2nd']

    return df


def analyze_condition(df, condition_name, investment_per_bet=400):
    """条件の分析"""
    if len(df) == 0:
        return None

    # 年度別分析
    yearly_stats = []
    for year in sorted(df['year'].unique()):
        year_data = df[df['year'] == year]
        count = len(year_data)
        hits = year_data['hit'].sum()
        hit_rate = hits / count * 100 if count > 0 else 0

        # ROI計算（オッズがある場合のみ）
        odds_data = year_data[year_data['trifecta_odds'].notna()]
        if len(odds_data) > 0:
            total_investment = len(odds_data) * investment_per_bet
            total_return = (odds_data[odds_data['hit'] == 1]['trifecta_odds'] * 100).sum()
            roi = total_return / total_investment * 100 if total_investment > 0 else 0
            profit = total_return - total_investment
        else:
            roi = 0
            profit = 0
            total_investment = 0

        yearly_stats.append({
            'year': year,
            'count': count,
            'hits': hits,
            'hit_rate': hit_rate,
            'roi': roi,
            'profit': profit,
        })

    # 全体集計
    total_count = len(df)
    total_hits = df['hit'].sum()
    total_hit_rate = total_hits / total_count * 100 if total_count > 0 else 0

    odds_data = df[df['trifecta_odds'].notna()]
    if len(odds_data) > 0:
        total_investment = len(odds_data) * investment_per_bet
        total_return = (odds_data[odds_data['hit'] == 1]['trifecta_odds'] * 100).sum()
        total_roi = total_return / total_investment * 100 if total_investment > 0 else 0
        total_profit = total_return - total_investment
    else:
        total_roi = 0
        total_profit = 0

    # 黒字年数
    profitable_years = sum(1 for y in yearly_stats if y['roi'] > 100)
    total_years = len(yearly_stats)

    return {
        'condition': condition_name,
        'total_count': total_count,
        'total_hits': total_hits,
        'hit_rate': total_hit_rate,
        'roi': total_roi,
        'profit': total_profit,
        'profitable_years': profitable_years,
        'total_years': total_years,
        'yearly': yearly_stats
    }


def print_result(result):
    """結果を表示"""
    if result is None:
        print("  対象データなし")
        return

    print(f"\n{'='*70}")
    print(f"条件: {result['condition']}")
    print(f"{'='*70}")
    print(f"件数: {result['total_count']:,}件 | 的中: {result['total_hits']}件 ({result['hit_rate']:.2f}%)")
    print(f"ROI: {result['roi']:.1f}% | 収支: {result['profit']:+,.0f}円 | 黒字年: {result['profitable_years']}/{result['total_years']}年")

    print(f"\n年度別:")
    print(f"{'年度':^6} | {'件数':>5} | {'的中':>3} | {'的中率':>7} | {'ROI':>7} | {'収支':>10}")
    print("-" * 60)
    for y in result['yearly']:
        print(f"{y['year']:^6} | {y['count']:>5} | {y['hits']:>3} | {y['hit_rate']:>5.2f}% | {y['roi']:>5.1f}% | {y['profit']:>+10,.0f}円")


def main():
    print("=" * 80)
    print("逃げ率・まくり率・差し率 フィルター効果分析（購入条件適用版）")
    print("=" * 80)
    print(f"分析日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # データ取得
    print("\nデータ読み込み中...")
    df = get_predictions_with_indicators()
    print(f"総レコード数: {len(df):,}件")

    # 会場コードと会場名の対応
    venue_names = {
        '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島',
        '05': '多摩川', '06': '浜名湖', '07': '蒲郡', '08': '常滑',
        '09': '津', '10': '三国', '11': 'びわこ', '12': '住之江',
        '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島',
        '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
        '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
    }

    # 会場別まくり率・差し率を表示
    print("\n" + "=" * 80)
    print("会場別まくり率・差し率")
    print("=" * 80)
    venue_stats = df.groupby('venue_code').agg({
        'makuri_rate': 'first',
        'sashi_rate': 'first'
    }).reset_index()
    venue_stats['venue_name'] = venue_stats['venue_code'].map(venue_names)
    venue_stats = venue_stats.sort_values('makuri_rate', ascending=False)

    print(f"{'会場':^6} | {'まくり率':>8} | {'差し率':>8} | {'分類'}")
    print("-" * 50)
    for _, row in venue_stats.iterrows():
        makuri = row['makuri_rate'] * 100
        sashi = row['sashi_rate'] * 100
        if makuri >= 25:
            makuri_class = "高"
        elif makuri < 20:
            makuri_class = "低"
        else:
            makuri_class = "中"
        if sashi >= 22:
            sashi_class = "高"
        elif sashi < 18:
            sashi_class = "低"
        else:
            sashi_class = "中"
        print(f"{row['venue_name']:^6} | {makuri:>6.1f}% | {sashi:>6.1f}% | まくり{makuri_class}/差し{sashi_class}")

    results_all = []

    # ========== B×50-100条件での分析 ==========
    print("\n" + "=" * 80)
    print("1. B×50-100条件での逃げ率・会場フィルター効果")
    print("=" * 80)

    # B×50-100の基本条件
    df_b50 = df[
        (df['confidence'] == 'B') &
        (df['trifecta_odds'] >= 50) &
        (df['trifecta_odds'] < 100)
    ].copy()

    result = analyze_condition(df_b50, "B×50-100 ベースライン")
    print_result(result)
    results_all.append(result)

    # 1コース予測のみ
    df_b50_1c = df_b50[df_b50['pred_1st'] == 1].copy()
    print(f"\nB×50-100のうち1コース予測: {len(df_b50_1c):,}件 ({len(df_b50_1c)/len(df_b50)*100:.1f}%)")

    if len(df_b50_1c) > 0:
        # 逃げ率フィルター（母数50以上のみ）
        df_b50_1c_escape = df_b50_1c[df_b50_1c['races_1course'] >= 50].copy()
        print(f"  うち逃げ率データあり（母数50+）: {len(df_b50_1c_escape):,}件")

        if len(df_b50_1c_escape) > 0:
            # 各逃げ率閾値で分析
            for threshold in [0.40, 0.50, 0.60]:
                # 低逃げ率
                df_low = df_b50_1c_escape[df_b50_1c_escape['escape_rate'] < threshold]
                result = analyze_condition(df_low, f"B×50-100×1C予測×逃げ率<{int(threshold*100)}%")
                print_result(result)
                results_all.append(result)

                # 高逃げ率
                df_high = df_b50_1c_escape[df_b50_1c_escape['escape_rate'] >= threshold]
                result = analyze_condition(df_high, f"B×50-100×1C予測×逃げ率>={int(threshold*100)}%")
                print_result(result)
                results_all.append(result)

    # 会場特性フィルター
    print("\n--- B×50-100 × 会場まくり率フィルター ---")
    for threshold in [0.22, 0.25]:
        # 高まくり率会場
        df_high = df_b50[df_b50['makuri_rate'] >= threshold]
        result = analyze_condition(df_high, f"B×50-100×まくり率>={int(threshold*100)}%")
        print_result(result)
        results_all.append(result)

        # 低まくり率会場
        df_low = df_b50[df_b50['makuri_rate'] < threshold]
        result = analyze_condition(df_low, f"B×50-100×まくり率<{int(threshold*100)}%")
        print_result(result)
        results_all.append(result)

    # ========== C×20-30条件での分析 ==========
    print("\n" + "=" * 80)
    print("2. C×20-30条件での逃げ率・会場フィルター効果")
    print("=" * 80)

    df_c20 = df[
        (df['confidence'] == 'C') &
        (df['trifecta_odds'] >= 20) &
        (df['trifecta_odds'] < 30)
    ].copy()

    result = analyze_condition(df_c20, "C×20-30 ベースライン", 100)
    print_result(result)
    results_all.append(result)

    # 1コース予測での逃げ率フィルター
    df_c20_1c = df_c20[df_c20['pred_1st'] == 1].copy()
    print(f"\nC×20-30のうち1コース予測: {len(df_c20_1c):,}件")

    if len(df_c20_1c) > 0:
        df_c20_1c_escape = df_c20_1c[df_c20_1c['races_1course'] >= 50].copy()

        if len(df_c20_1c_escape) > 0:
            for threshold in [0.50, 0.60]:
                df_low = df_c20_1c_escape[df_c20_1c_escape['escape_rate'] < threshold]
                result = analyze_condition(df_low, f"C×20-30×1C×逃げ率<{int(threshold*100)}%", 100)
                print_result(result)
                results_all.append(result)

                df_high = df_c20_1c_escape[df_c20_1c_escape['escape_rate'] >= threshold]
                result = analyze_condition(df_high, f"C×20-30×1C×逃げ率>={int(threshold*100)}%", 100)
                print_result(result)
                results_all.append(result)

    # ========== D×40-50条件での分析 ==========
    print("\n" + "=" * 80)
    print("3. D×40-50条件での逃げ率・会場フィルター効果")
    print("=" * 80)

    df_d40 = df[
        (df['confidence'] == 'D') &
        (df['trifecta_odds'] >= 40) &
        (df['trifecta_odds'] < 50)
    ].copy()

    result = analyze_condition(df_d40, "D×40-50 ベースライン", 100)
    print_result(result)
    results_all.append(result)

    # 予測コース別
    for course in [1, 2, 3, 4, 5]:
        df_course = df_d40[df_d40['pred_1st'] == course]
        if len(df_course) >= 30:
            result = analyze_condition(df_course, f"D×40-50×{course}C予測", 100)
            print_result(result)
            results_all.append(result)

    # ========== D×5コース予測条件での分析 ==========
    print("\n" + "=" * 80)
    print("4. D×5コース予測条件での会場フィルター効果")
    print("=" * 80)

    df_d5c = df[
        (df['confidence'] == 'D') &
        (df['pred_1st'] == 5)
    ].copy()

    result = analyze_condition(df_d5c, "D×5C予測 ベースライン")
    print_result(result)
    results_all.append(result)

    # 差し率フィルター
    for threshold in [0.18, 0.20, 0.22]:
        df_high = df_d5c[df_d5c['sashi_rate'] >= threshold]
        result = analyze_condition(df_high, f"D×5C×差し率>={int(threshold*100)}%")
        print_result(result)
        results_all.append(result)

        df_low = df_d5c[df_d5c['sashi_rate'] < threshold]
        result = analyze_condition(df_low, f"D×5C×差し率<{int(threshold*100)}%")
        print_result(result)
        results_all.append(result)

    # ========== A×A1×10-12条件での分析 ==========
    print("\n" + "=" * 80)
    print("5. A×A1×10-12条件での逃げ率フィルター効果")
    print("=" * 80)

    df_a10 = df[
        (df['confidence'] == 'A') &
        (df['racer_rank'] == 'A1') &
        (df['trifecta_odds'] >= 10) &
        (df['trifecta_odds'] < 12)
    ].copy()

    result = analyze_condition(df_a10, "A×A1×10-12 ベースライン", 100)
    print_result(result)
    results_all.append(result)

    # 1コース予測での逃げ率フィルター
    df_a10_1c = df_a10[df_a10['pred_1st'] == 1].copy()
    print(f"\nA×A1×10-12のうち1コース予測: {len(df_a10_1c):,}件")

    if len(df_a10_1c) > 0:
        df_a10_1c_escape = df_a10_1c[df_a10_1c['races_1course'] >= 50].copy()

        if len(df_a10_1c_escape) > 0:
            for threshold in [0.60, 0.70]:
                df_high = df_a10_1c_escape[df_a10_1c_escape['escape_rate'] >= threshold]
                result = analyze_condition(df_high, f"A×A1×10-12×1C×逃げ率>={int(threshold*100)}%", 100)
                print_result(result)
                results_all.append(result)

    # ========== 全体サマリー ==========
    print("\n" + "=" * 80)
    print("分析サマリー")
    print("=" * 80)

    # 有効な結果のみ抽出
    valid_results = [r for r in results_all if r is not None and r['total_count'] >= 50]

    # ROI順でソート
    valid_results.sort(key=lambda x: x['roi'], reverse=True)

    print("\n【ROI上位パターン】（50件以上）:")
    print(f"{'条件':<45} | {'件数':>5} | {'ROI':>7} | {'黒字年'}")
    print("-" * 75)
    for r in valid_results[:15]:
        print(f"{r['condition']:<45} | {r['total_count']:>5} | {r['roi']:>5.1f}% | {r['profitable_years']}/{r['total_years']}年")

    print("\n【除外候補パターン】（ROI<80%）:")
    print(f"{'条件':<45} | {'件数':>5} | {'ROI':>7} | {'黒字年'}")
    print("-" * 75)
    exclusion = [r for r in valid_results if r['roi'] < 80]
    for r in exclusion:
        print(f"{r['condition']:<45} | {r['total_count']:>5} | {r['roi']:>5.1f}% | {r['profitable_years']}/{r['total_years']}年")

    print(f"\n分析完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
