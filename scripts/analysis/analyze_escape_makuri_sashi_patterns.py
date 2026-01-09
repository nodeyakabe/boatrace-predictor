"""
逃げ率・まくり率・差し率を使った不的中パターン分析スクリプト

分析対象:
1. 1コース予測時の逃げ率フィルター
2. 会場特性と予測コースの組み合わせ
3. 複合条件

データソース:
- player_escape_stats: 選手別逃げ率（stadium_id IS NULL で全国データ）
- stadium_attack_stats: 会場別まくり率・差し率
"""

import sqlite3
import pandas as pd
from datetime import datetime, timedelta

DB_PATH = "data/boatrace.db"

def get_base_data():
    """基本データを取得"""
    conn = sqlite3.connect(DB_PATH)

    # before予測データを取得（予測コース、信頼度、レース情報を含む）
    query = """
    SELECT
        r.id AS race_id,
        r.venue_code,
        r.race_date,
        strftime('%Y', r.race_date) AS year,
        strftime('%m', r.race_date) AS month,
        p.pit_number AS pred_1st_pit,
        p.confidence,
        p.total_score,
        e.racer_number,
        e.racer_rank,
        res1.pit_number AS actual_1st,
        res2.pit_number AS actual_2nd,
        res3.pit_number AS actual_3rd,
        o.odds AS trifecta_odds
    FROM races r
    INNER JOIN race_predictions p ON r.id = p.race_id
        AND p.prediction_type = 'before'
        AND p.rank_prediction = 1
    INNER JOIN entries e ON r.id = e.race_id AND e.pit_number = p.pit_number
    INNER JOIN results res1 ON r.id = res1.race_id AND res1.rank = '1' AND res1.is_invalid = 0
    INNER JOIN results res2 ON r.id = res2.race_id AND res2.rank = '2' AND res2.is_invalid = 0
    INNER JOIN results res3 ON r.id = res3.race_id AND res3.rank = '3' AND res3.is_invalid = 0
    LEFT JOIN trifecta_odds o ON r.id = o.race_id
        AND o.combination = (
            CAST(p.pit_number AS TEXT) || '-' ||
            (SELECT CAST(pit_number AS TEXT) FROM race_predictions
             WHERE race_id = r.id AND prediction_type = 'before' AND rank_prediction = 2) || '-' ||
            (SELECT CAST(pit_number AS TEXT) FROM race_predictions
             WHERE race_id = r.id AND prediction_type = 'before' AND rank_prediction = 3)
        )
    WHERE r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
    """

    df = pd.read_sql_query(query, conn)

    # 2着・3着予測も取得
    query_2nd_3rd = """
    SELECT
        race_id,
        pit_number AS pred_2nd_pit
    FROM race_predictions
    WHERE prediction_type = 'before' AND rank_prediction = 2
    """
    df_2nd = pd.read_sql_query(query_2nd_3rd, conn)

    query_3rd = """
    SELECT
        race_id,
        pit_number AS pred_3rd_pit
    FROM race_predictions
    WHERE prediction_type = 'before' AND rank_prediction = 3
    """
    df_3rd = pd.read_sql_query(query_3rd, conn)

    df = df.merge(df_2nd, on='race_id', how='left')
    df = df.merge(df_3rd, on='race_id', how='left')

    # 選手逃げ率（全国データ：stadium_id IS NULL、母数50以上）
    query_escape = """
    SELECT
        player_id AS racer_number,
        escape_rate,
        races_1course
    FROM player_escape_stats
    WHERE stadium_id IS NULL AND races_1course >= 50
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
        (df['pred_1st_pit'] == df['actual_1st']) &
        (df['pred_2nd_pit'] == df['actual_2nd']) &
        (df['pred_3rd_pit'] == df['actual_3rd'])
    ).astype(int)

    return df


def analyze_condition(df, condition_name, condition_mask, investment_per_bet=400):
    """特定条件の分析"""
    subset = df[condition_mask].copy()

    if len(subset) == 0:
        return None

    # 年度別分析
    yearly_stats = []
    for year in sorted(subset['year'].unique()):
        year_data = subset[subset['year'] == year]
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
            'investment': total_investment
        })

    # 全体集計
    total_count = len(subset)
    total_hits = subset['hit'].sum()
    total_hit_rate = total_hits / total_count * 100 if total_count > 0 else 0

    odds_data = subset[subset['trifecta_odds'].notna()]
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


def print_analysis_result(result):
    """分析結果を表示"""
    if result is None:
        print("  対象データなし")
        return

    print(f"\n{'='*60}")
    print(f"条件: {result['condition']}")
    print(f"{'='*60}")
    print(f"対象件数: {result['total_count']:,}件")
    print(f"的中数: {result['total_hits']}件")
    print(f"的中率: {result['hit_rate']:.2f}%")
    print(f"ROI: {result['roi']:.1f}%")
    print(f"収支: {result['profit']:+,.0f}円")
    print(f"黒字年数: {result['profitable_years']}/{result['total_years']}年")

    print(f"\n年度別詳細:")
    print(f"{'年度':^6} | {'件数':^6} | {'的中':^4} | {'的中率':^8} | {'ROI':^8} | {'収支':^12}")
    print("-" * 60)
    for y in result['yearly']:
        print(f"{y['year']:^6} | {y['count']:>6} | {y['hits']:>4} | {y['hit_rate']:>6.2f}% | {y['roi']:>6.1f}% | {y['profit']:>+10,.0f}円")


def main():
    print("=" * 80)
    print("逃げ率・まくり率・差し率を使った不的中パターン分析")
    print("=" * 80)
    print(f"分析開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # データ取得
    print("\nデータ読み込み中...")
    df = get_base_data()
    print(f"総レコード数: {len(df):,}件")
    print(f"逃げ率データあり: {df['escape_rate'].notna().sum():,}件 ({df['escape_rate'].notna().sum()/len(df)*100:.1f}%)")
    print(f"会場データあり: {df['makuri_rate'].notna().sum():,}件")

    # 基本統計
    print("\n" + "=" * 80)
    print("基本統計")
    print("=" * 80)

    # 会場まくり率・差し率の分布
    print("\n会場別まくり率・差し率:")
    venue_stats = df.groupby('venue_code').agg({
        'makuri_rate': 'first',
        'sashi_rate': 'first'
    }).reset_index()
    venue_stats = venue_stats.sort_values('makuri_rate', ascending=False)
    print(f"まくり率: 最低{venue_stats['makuri_rate'].min()*100:.1f}% ～ 最高{venue_stats['makuri_rate'].max()*100:.1f}%")
    print(f"差し率: 最低{venue_stats['sashi_rate'].min()*100:.1f}% ～ 最高{venue_stats['sashi_rate'].max()*100:.1f}%")

    results = []

    # ========== 1. 1コース予測時の逃げ率フィルター ==========
    print("\n" + "=" * 80)
    print("1. 1コース予測時の逃げ率フィルター分析")
    print("=" * 80)

    # 1コース予測のみ抽出
    df_1c = df[df['pred_1st_pit'] == 1].copy()
    print(f"\n1コース予測件数: {len(df_1c):,}件")
    print(f"  うち逃げ率データあり: {df_1c['escape_rate'].notna().sum():,}件")

    # ベースライン（1コース予測全体）
    result = analyze_condition(df_1c, "ベースライン（1C予測全体）", df_1c['escape_rate'].notna())
    print_analysis_result(result)
    results.append(result)

    # 各逃げ率閾値で分析
    escape_thresholds = [
        ("<40%", df_1c['escape_rate'] < 0.40),
        ("<50%", df_1c['escape_rate'] < 0.50),
        ("<60%", df_1c['escape_rate'] < 0.60),
        (">=60%", df_1c['escape_rate'] >= 0.60),
        (">=70%", df_1c['escape_rate'] >= 0.70),
    ]

    for name, mask in escape_thresholds:
        result = analyze_condition(df_1c, f"1C予測×逃げ率{name}", mask & df_1c['escape_rate'].notna())
        print_analysis_result(result)
        results.append(result)

    # ========== 2. 会場特性と予測コースの組み合わせ ==========
    print("\n" + "=" * 80)
    print("2. 会場特性と予測コースの組み合わせ分析")
    print("=" * 80)

    # まくり率の閾値
    makuri_high = df['makuri_rate'] >= 0.25  # 25%以上
    makuri_low = df['makuri_rate'] < 0.20    # 20%未満

    # 差し率の閾値
    sashi_high = df['sashi_rate'] >= 0.22    # 22%以上
    sashi_low = df['sashi_rate'] < 0.18      # 18%未満

    # 3・4コース予測（まくり系）
    df_34c = df[(df['pred_1st_pit'] == 3) | (df['pred_1st_pit'] == 4)].copy()
    print(f"\n3・4コース予測件数: {len(df_34c):,}件")

    result = analyze_condition(df_34c, "3・4C予測 全体", pd.Series([True] * len(df_34c), index=df_34c.index))
    print_analysis_result(result)
    results.append(result)

    result = analyze_condition(df_34c, "3・4C予測×まくり率高(>=25%)", makuri_high.loc[df_34c.index])
    print_analysis_result(result)
    results.append(result)

    result = analyze_condition(df_34c, "3・4C予測×まくり率低(<20%)", makuri_low.loc[df_34c.index])
    print_analysis_result(result)
    results.append(result)

    # 2・5コース予測（差し系）
    df_25c = df[(df['pred_1st_pit'] == 2) | (df['pred_1st_pit'] == 5)].copy()
    print(f"\n2・5コース予測件数: {len(df_25c):,}件")

    result = analyze_condition(df_25c, "2・5C予測 全体", pd.Series([True] * len(df_25c), index=df_25c.index))
    print_analysis_result(result)
    results.append(result)

    result = analyze_condition(df_25c, "2・5C予測×差し率高(>=22%)", sashi_high.loc[df_25c.index])
    print_analysis_result(result)
    results.append(result)

    result = analyze_condition(df_25c, "2・5C予測×差し率低(<18%)", sashi_low.loc[df_25c.index])
    print_analysis_result(result)
    results.append(result)

    # ========== 3. 複合条件 ==========
    print("\n" + "=" * 80)
    print("3. 複合条件分析")
    print("=" * 80)

    # 1C予測 × 低逃げ率 × 高まくり率会場（除外候補）
    result = analyze_condition(
        df_1c,
        "1C予測×逃げ率<50%×まくり率高(>=25%)【除外候補】",
        (df_1c['escape_rate'] < 0.50) & makuri_high.loc[df_1c.index]
    )
    print_analysis_result(result)
    results.append(result)

    # 1C予測 × 低逃げ率 × 低まくり率会場
    result = analyze_condition(
        df_1c,
        "1C予測×逃げ率<50%×まくり率低(<20%)",
        (df_1c['escape_rate'] < 0.50) & makuri_low.loc[df_1c.index]
    )
    print_analysis_result(result)
    results.append(result)

    # 1C予測 × 高逃げ率 × 高まくり率会場
    result = analyze_condition(
        df_1c,
        "1C予測×逃げ率>=60%×まくり率高(>=25%)",
        (df_1c['escape_rate'] >= 0.60) & makuri_high.loc[df_1c.index]
    )
    print_analysis_result(result)
    results.append(result)

    # 1C予測 × 高逃げ率 × 低差し率会場
    result = analyze_condition(
        df_1c,
        "1C予測×逃げ率>=60%×差し率低(<18%)",
        (df_1c['escape_rate'] >= 0.60) & sashi_low.loc[df_1c.index]
    )
    print_analysis_result(result)
    results.append(result)

    # ========== 4. 信頼度別分析 ==========
    print("\n" + "=" * 80)
    print("4. 信頼度別×逃げ率分析（1コース予測）")
    print("=" * 80)

    for conf in ['A', 'B', 'C', 'D']:
        df_conf = df_1c[df_1c['confidence'] == conf].copy()
        if len(df_conf) == 0:
            continue

        print(f"\n--- 信頼度{conf} ---")

        # ベースライン
        result = analyze_condition(
            df_conf,
            f"信頼度{conf}×1C予測 ベースライン",
            df_conf['escape_rate'].notna()
        )
        print_analysis_result(result)
        results.append(result)

        # 低逃げ率
        result = analyze_condition(
            df_conf,
            f"信頼度{conf}×1C予測×逃げ率<50%【除外候補】",
            df_conf['escape_rate'] < 0.50
        )
        print_analysis_result(result)
        results.append(result)

    # ========== 5. 追加分析：より細かい閾値 ==========
    print("\n" + "=" * 80)
    print("5. 追加分析：細かい閾値での検証")
    print("=" * 80)

    # まくり率の詳細閾値
    print("\n--- 3・4コース予測×まくり率詳細 ---")
    for threshold in [0.20, 0.22, 0.24, 0.26, 0.28]:
        mask_high = df_34c['makuri_rate'] >= threshold
        mask_low = df_34c['makuri_rate'] < threshold

        result_high = analyze_condition(df_34c, f"3・4C×まくり率>={threshold*100:.0f}%", mask_high)
        result_low = analyze_condition(df_34c, f"3・4C×まくり率<{threshold*100:.0f}%", mask_low)

        if result_high and result_low:
            print(f"\n閾値 {threshold*100:.0f}%:")
            print(f"  >= {threshold*100:.0f}%: {result_high['total_count']:,}件, ROI {result_high['roi']:.1f}%, 黒字{result_high['profitable_years']}/{result_high['total_years']}年")
            print(f"  <  {threshold*100:.0f}%: {result_low['total_count']:,}件, ROI {result_low['roi']:.1f}%, 黒字{result_low['profitable_years']}/{result_low['total_years']}年")

    # 差し率の詳細閾値
    print("\n--- 2・5コース予測×差し率詳細 ---")
    for threshold in [0.18, 0.20, 0.22, 0.24]:
        mask_high = df_25c['sashi_rate'] >= threshold
        mask_low = df_25c['sashi_rate'] < threshold

        result_high = analyze_condition(df_25c, f"2・5C×差し率>={threshold*100:.0f}%", mask_high)
        result_low = analyze_condition(df_25c, f"2・5C×差し率<{threshold*100:.0f}%", mask_low)

        if result_high and result_low:
            print(f"\n閾値 {threshold*100:.0f}%:")
            print(f"  >= {threshold*100:.0f}%: {result_high['total_count']:,}件, ROI {result_high['roi']:.1f}%, 黒字{result_high['profitable_years']}/{result_high['total_years']}年")
            print(f"  <  {threshold*100:.0f}%: {result_low['total_count']:,}件, ROI {result_low['roi']:.1f}%, 黒字{result_low['profitable_years']}/{result_low['total_years']}年")

    # ========== 6. サマリー ==========
    print("\n" + "=" * 80)
    print("6. 分析サマリー：除外候補パターン")
    print("=" * 80)

    # ROIが低く、黒字年数が少ない条件を抽出
    exclusion_candidates = []
    for r in results:
        if r is None:
            continue
        if r['roi'] < 90 and r['total_count'] >= 100:  # ROI90%未満かつ100件以上
            exclusion_candidates.append(r)

    print("\n【除外候補】ROI < 90% かつ 100件以上:")
    print(f"{'条件':<50} | {'件数':>6} | {'ROI':>7} | {'黒字年'}")
    print("-" * 80)

    exclusion_candidates.sort(key=lambda x: x['roi'])
    for r in exclusion_candidates:
        print(f"{r['condition']:<50} | {r['total_count']:>6} | {r['roi']:>5.1f}% | {r['profitable_years']}/{r['total_years']}年")

    # 採用候補（ROI高＆安定性あり）
    print("\n【採用候補】ROI > 110% かつ 黒字年4年以上:")
    print(f"{'条件':<50} | {'件数':>6} | {'ROI':>7} | {'黒字年'}")
    print("-" * 80)

    adoption_candidates = []
    for r in results:
        if r is None:
            continue
        if r['roi'] > 110 and r['profitable_years'] >= 4 and r['total_count'] >= 50:
            adoption_candidates.append(r)

    adoption_candidates.sort(key=lambda x: x['roi'], reverse=True)
    for r in adoption_candidates:
        print(f"{r['condition']:<50} | {r['total_count']:>6} | {r['roi']:>5.1f}% | {r['profitable_years']}/{r['total_years']}年")

    print(f"\n分析完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
