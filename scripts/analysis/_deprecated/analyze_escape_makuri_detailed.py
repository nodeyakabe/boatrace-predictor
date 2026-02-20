"""
逃げ率・まくり率・差し率の詳細分析スクリプト

現行購入条件（冬除外等）の効果を確認しつつ、
追加フィルターの効果を分析
"""

import sqlite3
import pandas as pd
from datetime import datetime

DB_PATH = "data/boatrace.db"

def get_full_data():
    """全予測データと指標データを取得"""
    conn = sqlite3.connect(DB_PATH)

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
        CAST(strftime('%m', r.race_date) AS INTEGER) AS month,
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

    # 選手逃げ率
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
        sashi_rate
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

    # 季節判定
    df['is_winter'] = df['month'].isin([12, 1, 2])

    return df


def analyze(df, name, investment=400):
    """条件分析"""
    if len(df) == 0:
        return None

    yearly = []
    for year in sorted(df['year'].unique()):
        y_data = df[df['year'] == year]
        odds_data = y_data[y_data['trifecta_odds'].notna()]
        if len(odds_data) > 0:
            inv = len(odds_data) * investment
            ret = (odds_data[odds_data['hit'] == 1]['trifecta_odds'] * 100).sum()
            roi = ret / inv * 100
            profit = ret - inv
        else:
            roi = 0
            profit = 0
        yearly.append({
            'year': year,
            'count': len(y_data),
            'hits': y_data['hit'].sum(),
            'roi': roi,
            'profit': profit
        })

    # 全体
    odds_data = df[df['trifecta_odds'].notna()]
    if len(odds_data) > 0:
        total_inv = len(odds_data) * investment
        total_ret = (odds_data[odds_data['hit'] == 1]['trifecta_odds'] * 100).sum()
        total_roi = total_ret / total_inv * 100
        total_profit = total_ret - total_inv
    else:
        total_roi = 0
        total_profit = 0

    profitable = sum(1 for y in yearly if y['roi'] > 100)

    return {
        'name': name,
        'count': len(df),
        'hits': df['hit'].sum(),
        'hit_rate': df['hit'].mean() * 100,
        'roi': total_roi,
        'profit': total_profit,
        'profitable_years': profitable,
        'total_years': len(yearly),
        'yearly': yearly
    }


def print_result(r):
    """結果表示"""
    if r is None:
        print("  データなし")
        return

    print(f"\n{'='*70}")
    print(f"{r['name']}")
    print(f"{'='*70}")
    print(f"件数: {r['count']:,} | 的中: {r['hits']} ({r['hit_rate']:.2f}%) | ROI: {r['roi']:.1f}% | 収支: {r['profit']:+,.0f}円 | 黒字: {r['profitable_years']}/{r['total_years']}年")
    print(f"年度 | {'件数':>5} | {'的中':>3} | {'ROI':>7} | {'収支':>10}")
    for y in r['yearly']:
        print(f"{y['year']} | {y['count']:>5} | {y['hits']:>3} | {y['roi']:>5.1f}% | {y['profit']:>+10,.0f}円")


def main():
    print("=" * 80)
    print("逃げ率・まくり率・差し率 詳細分析")
    print("=" * 80)
    print(f"分析日時: {datetime.now()}")

    df = get_full_data()
    print(f"\n総レコード数: {len(df):,}")

    results = []

    # ========== B×50-100 冬除外効果確認 ==========
    print("\n" + "=" * 80)
    print("1. B×50-100 冬除外フィルターの効果確認")
    print("=" * 80)

    df_b50 = df[
        (df['confidence'] == 'B') &
        (df['trifecta_odds'] >= 50) &
        (df['trifecta_odds'] < 100)
    ].copy()

    r = analyze(df_b50, "B×50-100 全期間（冬含む）")
    print_result(r)
    results.append(r)

    # 冬除外
    df_b50_no_winter = df_b50[~df_b50['is_winter']]
    r = analyze(df_b50_no_winter, "B×50-100 冬除外")
    print_result(r)
    results.append(r)

    # 冬のみ
    df_b50_winter = df_b50[df_b50['is_winter']]
    r = analyze(df_b50_winter, "B×50-100 冬のみ")
    print_result(r)
    results.append(r)

    # ========== B×50-100 冬除外後の追加フィルター ==========
    print("\n" + "=" * 80)
    print("2. B×50-100 冬除外後の追加フィルター候補")
    print("=" * 80)

    # 1コース予測×逃げ率フィルター
    df_b50_nw_1c = df_b50_no_winter[df_b50_no_winter['pred_1st'] == 1].copy()
    print(f"\n冬除外後の1コース予測: {len(df_b50_nw_1c)}件")

    # 逃げ率データあり（母数50以上）
    df_b50_nw_1c_esc = df_b50_nw_1c[df_b50_nw_1c['races_1course'] >= 50]
    print(f"  うち逃げ率データあり: {len(df_b50_nw_1c_esc)}件")

    if len(df_b50_nw_1c_esc) > 0:
        for thresh in [0.50, 0.60, 0.70]:
            df_low = df_b50_nw_1c_esc[df_b50_nw_1c_esc['escape_rate'] < thresh]
            r = analyze(df_low, f"B×50-100(冬除外)×1C×逃げ率<{int(thresh*100)}%【除外候補】")
            print_result(r)
            results.append(r)

            df_high = df_b50_nw_1c_esc[df_b50_nw_1c_esc['escape_rate'] >= thresh]
            r = analyze(df_high, f"B×50-100(冬除外)×1C×逃げ率>={int(thresh*100)}%")
            print_result(r)
            results.append(r)

    # 会場フィルター（冬除外後）
    print("\n--- まくり率フィルター ---")
    for thresh in [0.22, 0.25]:
        df_high = df_b50_no_winter[df_b50_no_winter['makuri_rate'] >= thresh]
        r = analyze(df_high, f"B×50-100(冬除外)×まくり率>={int(thresh*100)}%")
        print_result(r)
        results.append(r)

        df_low = df_b50_no_winter[df_b50_no_winter['makuri_rate'] < thresh]
        r = analyze(df_low, f"B×50-100(冬除外)×まくり率<{int(thresh*100)}%")
        print_result(r)
        results.append(r)

    # ========== D×5コース予測 差し率フィルター ==========
    print("\n" + "=" * 80)
    print("3. D×5コース予測 差し率フィルター")
    print("=" * 80)

    df_d5c = df[
        (df['confidence'] == 'D') &
        (df['pred_1st'] == 5)
    ].copy()

    r = analyze(df_d5c, "D×5C ベースライン")
    print_result(r)
    results.append(r)

    # 差し率フィルター
    for thresh in [0.18, 0.20, 0.22]:
        df_high = df_d5c[df_d5c['sashi_rate'] >= thresh]
        r = analyze(df_high, f"D×5C×差し率>={int(thresh*100)}%")
        print_result(r)
        results.append(r)

        df_low = df_d5c[df_d5c['sashi_rate'] < thresh]
        r = analyze(df_low, f"D×5C×差し率<{int(thresh*100)}%【除外候補】")
        print_result(r)
        results.append(r)

    # ========== A×A1×10-12 逃げ率フィルター ==========
    print("\n" + "=" * 80)
    print("4. A×A1×10-12 逃げ率フィルター")
    print("=" * 80)

    df_a10 = df[
        (df['confidence'] == 'A') &
        (df['racer_rank'] == 'A1') &
        (df['trifecta_odds'] >= 10) &
        (df['trifecta_odds'] < 12)
    ].copy()

    r = analyze(df_a10, "A×A1×10-12 ベースライン", 100)
    print_result(r)
    results.append(r)

    # 1コース予測のみ
    df_a10_1c = df_a10[df_a10['pred_1st'] == 1].copy()
    df_a10_1c_esc = df_a10_1c[df_a10_1c['races_1course'] >= 50]

    if len(df_a10_1c_esc) > 0:
        for thresh in [0.60, 0.70, 0.75]:
            df_high = df_a10_1c_esc[df_a10_1c_esc['escape_rate'] >= thresh]
            r = analyze(df_high, f"A×A1×10-12×1C×逃げ率>={int(thresh*100)}%", 100)
            print_result(r)
            results.append(r)

            df_low = df_a10_1c_esc[df_a10_1c_esc['escape_rate'] < thresh]
            r = analyze(df_low, f"A×A1×10-12×1C×逃げ率<{int(thresh*100)}%【除外候補】", 100)
            print_result(r)
            results.append(r)

    # ========== 全条件共通：予測コース×会場特性 ==========
    print("\n" + "=" * 80)
    print("5. 予測コース×会場特性の普遍的パターン探索")
    print("=" * 80)

    # オッズデータがあるレースのみ
    df_odds = df[df['trifecta_odds'].notna()].copy()

    # 3・4コース予測 × まくり率
    print("\n--- 3・4コース予測 × まくり率 ---")
    df_34c = df_odds[(df_odds['pred_1st'] == 3) | (df_odds['pred_1st'] == 4)]
    print(f"3・4コース予測件数: {len(df_34c):,}")

    for thresh in [0.22, 0.25, 0.28]:
        df_high = df_34c[df_34c['makuri_rate'] >= thresh]
        r = analyze(df_high, f"3・4C予測×まくり率>={int(thresh*100)}%")
        if r:
            print(f"  >={int(thresh*100)}%: {r['count']:,}件, ROI {r['roi']:.1f}%, 黒字{r['profitable_years']}/{r['total_years']}年")
            results.append(r)

        df_low = df_34c[df_34c['makuri_rate'] < thresh]
        r = analyze(df_low, f"3・4C予測×まくり率<{int(thresh*100)}%")
        if r:
            print(f"  <{int(thresh*100)}%: {r['count']:,}件, ROI {r['roi']:.1f}%, 黒字{r['profitable_years']}/{r['total_years']}年")
            results.append(r)

    # 2・5コース予測 × 差し率
    print("\n--- 2・5コース予測 × 差し率 ---")
    df_25c = df_odds[(df_odds['pred_1st'] == 2) | (df_odds['pred_1st'] == 5)]
    print(f"2・5コース予測件数: {len(df_25c):,}")

    for thresh in [0.18, 0.20, 0.22]:
        df_high = df_25c[df_25c['sashi_rate'] >= thresh]
        r = analyze(df_high, f"2・5C予測×差し率>={int(thresh*100)}%")
        if r:
            print(f"  >={int(thresh*100)}%: {r['count']:,}件, ROI {r['roi']:.1f}%, 黒字{r['profitable_years']}/{r['total_years']}年")
            results.append(r)

        df_low = df_25c[df_25c['sashi_rate'] < thresh]
        r = analyze(df_low, f"2・5C予測×差し率<{int(thresh*100)}%")
        if r:
            print(f"  <{int(thresh*100)}%: {r['count']:,}件, ROI {r['roi']:.1f}%, 黒字{r['profitable_years']}/{r['total_years']}年")
            results.append(r)

    # ========== サマリー ==========
    print("\n" + "=" * 80)
    print("分析サマリー")
    print("=" * 80)

    valid = [r for r in results if r and r['count'] >= 30]

    # 採用候補（ROI高＆安定）
    print("\n【採用候補】ROI>100% かつ 黒字3年以上:")
    adoption = [r for r in valid if r['roi'] > 100 and r['profitable_years'] >= 3]
    adoption.sort(key=lambda x: x['roi'], reverse=True)
    print(f"{'条件':<50} | {'件数':>5} | {'ROI':>7} | {'黒字年'}")
    print("-" * 75)
    for r in adoption[:10]:
        print(f"{r['name']:<50} | {r['count']:>5} | {r['roi']:>5.1f}% | {r['profitable_years']}/{r['total_years']}年")

    # 除外候補（ROI低＆不安定）
    print("\n【除外候補】ROI<70% かつ 件数50以上:")
    exclusion = [r for r in valid if r['roi'] < 70 and r['count'] >= 50]
    exclusion.sort(key=lambda x: x['roi'])
    print(f"{'条件':<50} | {'件数':>5} | {'ROI':>7} | {'黒字年'}")
    print("-" * 75)
    for r in exclusion[:10]:
        print(f"{r['name']:<50} | {r['count']:>5} | {r['roi']:>5.1f}% | {r['profitable_years']}/{r['total_years']}年")

    print(f"\n分析完了: {datetime.now()}")


if __name__ == "__main__":
    main()
