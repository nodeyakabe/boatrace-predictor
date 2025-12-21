"""
4年間（2022-2025年）の3連単的中/不的中パターン探索

目的: 年度を跨いで安定した「的中しやすい条件」と「的中しにくい条件」を探索
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
import sys

# プロジェクトルートを追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import DATABASE_PATH

def get_connection():
    """DB接続を取得"""
    return sqlite3.connect(DATABASE_PATH)

def get_trifecta_data():
    """4年分の3連単予測データと結果を取得"""
    query = """
    WITH predicted_trifecta AS (
        -- 各レースの予測1-2-3着を取得
        SELECT
            rp.race_id,
            MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.pit_number END) as pred_1st,
            MAX(CASE WHEN rp.rank_prediction = 2 THEN rp.pit_number END) as pred_2nd,
            MAX(CASE WHEN rp.rank_prediction = 3 THEN rp.pit_number END) as pred_3rd,
            MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.total_score END) as score_1st,
            MAX(CASE WHEN rp.rank_prediction = 2 THEN rp.total_score END) as score_2nd,
            MAX(CASE WHEN rp.rank_prediction = 3 THEN rp.total_score END) as score_3rd,
            MAX(CASE WHEN rp.rank_prediction = 6 THEN rp.total_score END) as score_6th,
            MAX(rp.confidence) as confidence
        FROM race_predictions rp
        WHERE rp.prediction_type = 'advance'
        GROUP BY rp.race_id
        HAVING pred_1st IS NOT NULL AND pred_2nd IS NOT NULL AND pred_3rd IS NOT NULL
    ),
    actual_results AS (
        -- 各レースの実際の1-2-3着を取得
        SELECT
            r.race_id,
            MAX(CASE WHEN r.rank = 1 THEN r.pit_number END) as actual_1st,
            MAX(CASE WHEN r.rank = 2 THEN r.pit_number END) as actual_2nd,
            MAX(CASE WHEN r.rank = 3 THEN r.pit_number END) as actual_3rd
        FROM results r
        WHERE r.rank BETWEEN 1 AND 3
        GROUP BY r.race_id
    ),
    entry_info AS (
        -- 1号艇の選手級別を取得
        SELECT
            e.race_id,
            e.racer_rank as course1_rank
        FROM entries e
        WHERE e.pit_number = 1
    )
    SELECT
        pt.race_id,
        ra.race_date,
        ra.venue_code,
        ra.race_grade,
        pt.pred_1st,
        pt.pred_2nd,
        pt.pred_3rd,
        pt.score_1st,
        pt.score_2nd,
        pt.score_3rd,
        pt.score_6th,
        pt.confidence,
        ar.actual_1st,
        ar.actual_2nd,
        ar.actual_3rd,
        CASE
            WHEN pt.pred_1st = ar.actual_1st
                 AND pt.pred_2nd = ar.actual_2nd
                 AND pt.pred_3rd = ar.actual_3rd
            THEN 1 ELSE 0
        END as hit,
        od.odds as trifecta_odds,
        ei.course1_rank
    FROM predicted_trifecta pt
    INNER JOIN races ra ON pt.race_id = ra.id
    INNER JOIN actual_results ar ON pt.race_id = ar.race_id
    LEFT JOIN trifecta_odds od ON pt.race_id = od.race_id
        AND od.combination = (pt.pred_1st || '-' || pt.pred_2nd || '-' || pt.pred_3rd)
    LEFT JOIN entry_info ei ON pt.race_id = ei.race_id
    WHERE ra.race_date >= '2022-01-01' AND ra.race_date <= '2025-12-31'
    ORDER BY ra.race_date
    """

    conn = get_connection()
    df = pd.read_sql_query(query, conn)
    conn.close()

    # 年度列を追加
    df['year'] = pd.to_datetime(df['race_date']).dt.year

    # スコア差を計算
    df['score_diff_1_2'] = df['score_1st'] - df['score_2nd']
    df['score_diff_1_6'] = df['score_1st'] - df['score_6th']

    # オッズ帯を分類
    def categorize_odds(odds):
        if pd.isna(odds):
            return 'unknown'
        elif odds < 10:
            return '0-10'
        elif odds < 30:
            return '10-30'
        elif odds < 100:
            return '30-100'
        else:
            return '100+'

    df['odds_band'] = df['trifecta_odds'].apply(categorize_odds)

    # グレードを分類
    def categorize_grade(grade):
        if pd.isna(grade):
            return '一般'
        grade = str(grade).upper()
        if 'SG' in grade:
            return 'SG'
        elif 'G1' in grade or 'GI' in grade or 'G１' in grade:
            return 'G1'
        elif 'G2' in grade or 'GII' in grade or 'G２' in grade:
            return 'G2'
        elif 'G3' in grade or 'GIII' in grade or 'G３' in grade:
            return 'G3'
        else:
            return '一般'

    df['grade_category'] = df['race_grade'].apply(categorize_grade)

    return df


def analyze_by_condition(df, condition_col, condition_name):
    """条件別の的中率・ROIを年度別に分析"""
    results = []

    for condition_val in df[condition_col].dropna().unique():
        condition_df = df[df[condition_col] == condition_val]

        if len(condition_df) < 100:  # サンプル数が少なすぎる場合はスキップ
            continue

        row = {'condition': f"{condition_name}={condition_val}"}

        for year in [2022, 2023, 2024, 2025]:
            year_df = condition_df[condition_df['year'] == year]
            if len(year_df) > 0:
                hit_rate = year_df['hit'].mean() * 100

                # ROI計算（オッズが不明なものは除外）
                valid_df = year_df[year_df['trifecta_odds'].notna()]
                if len(valid_df) > 0:
                    total_bet = len(valid_df) * 100  # 1点100円
                    total_return = (valid_df['hit'] * valid_df['trifecta_odds'] * 100).sum()
                    roi = (total_return / total_bet - 1) * 100
                else:
                    roi = np.nan

                row[f'{year}_n'] = len(year_df)
                row[f'{year}_hit'] = hit_rate
                row[f'{year}_roi'] = roi
            else:
                row[f'{year}_n'] = 0
                row[f'{year}_hit'] = np.nan
                row[f'{year}_roi'] = np.nan

        # 全体統計
        row['total_n'] = len(condition_df)
        row['total_hit'] = condition_df['hit'].mean() * 100
        valid_df = condition_df[condition_df['trifecta_odds'].notna()]
        if len(valid_df) > 0:
            total_bet = len(valid_df) * 100
            total_return = (valid_df['hit'] * valid_df['trifecta_odds'] * 100).sum()
            row['total_roi'] = (total_return / total_bet - 1) * 100
        else:
            row['total_roi'] = np.nan

        # 年度間の安定性（標準偏差）
        hit_rates = [row.get(f'{y}_hit', np.nan) for y in [2022, 2023, 2024, 2025]]
        hit_rates = [h for h in hit_rates if not pd.isna(h)]
        row['hit_std'] = np.std(hit_rates) if len(hit_rates) >= 2 else np.nan

        results.append(row)

    return pd.DataFrame(results)


def analyze_score_diff_bands(df):
    """スコア差帯別の分析"""
    results = []

    # スコア差（1位-2位）の帯を作成
    bins_1_2 = [0, 5, 10, 15, 20, 100]
    labels_1_2 = ['0-5', '5-10', '10-15', '15-20', '20+']
    df['score_diff_band_1_2'] = pd.cut(df['score_diff_1_2'], bins=bins_1_2, labels=labels_1_2)

    for band in labels_1_2:
        band_df = df[df['score_diff_band_1_2'] == band]

        if len(band_df) < 100:
            continue

        row = {'condition': f"スコア差(1-2位)={band}"}

        for year in [2022, 2023, 2024, 2025]:
            year_df = band_df[band_df['year'] == year]
            if len(year_df) > 0:
                hit_rate = year_df['hit'].mean() * 100
                valid_df = year_df[year_df['trifecta_odds'].notna()]
                if len(valid_df) > 0:
                    total_bet = len(valid_df) * 100
                    total_return = (valid_df['hit'] * valid_df['trifecta_odds'] * 100).sum()
                    roi = (total_return / total_bet - 1) * 100
                else:
                    roi = np.nan

                row[f'{year}_n'] = len(year_df)
                row[f'{year}_hit'] = hit_rate
                row[f'{year}_roi'] = roi

        row['total_n'] = len(band_df)
        row['total_hit'] = band_df['hit'].mean() * 100
        valid_df = band_df[band_df['trifecta_odds'].notna()]
        if len(valid_df) > 0:
            total_bet = len(valid_df) * 100
            total_return = (valid_df['hit'] * valid_df['trifecta_odds'] * 100).sum()
            row['total_roi'] = (total_return / total_bet - 1) * 100

        hit_rates = [row.get(f'{y}_hit', np.nan) for y in [2022, 2023, 2024, 2025]]
        hit_rates = [h for h in hit_rates if not pd.isna(h)]
        row['hit_std'] = np.std(hit_rates) if len(hit_rates) >= 2 else np.nan

        results.append(row)

    return pd.DataFrame(results)


def analyze_combinations(df):
    """複合条件の分析"""
    results = []

    # 信頼度 × オッズ帯
    for conf in df['confidence'].dropna().unique():
        for odds_band in ['0-10', '10-30', '30-100', '100+']:
            cond_df = df[(df['confidence'] == conf) & (df['odds_band'] == odds_band)]

            if len(cond_df) < 50:
                continue

            row = {'condition': f"信頼度{conf}×オッズ{odds_band}"}

            for year in [2022, 2023, 2024, 2025]:
                year_df = cond_df[cond_df['year'] == year]
                if len(year_df) > 0:
                    row[f'{year}_n'] = len(year_df)
                    row[f'{year}_hit'] = year_df['hit'].mean() * 100
                    valid_df = year_df[year_df['trifecta_odds'].notna()]
                    if len(valid_df) > 0:
                        total_bet = len(valid_df) * 100
                        total_return = (valid_df['hit'] * valid_df['trifecta_odds'] * 100).sum()
                        row[f'{year}_roi'] = (total_return / total_bet - 1) * 100

            row['total_n'] = len(cond_df)
            row['total_hit'] = cond_df['hit'].mean() * 100
            valid_df = cond_df[cond_df['trifecta_odds'].notna()]
            if len(valid_df) > 0:
                total_bet = len(valid_df) * 100
                total_return = (valid_df['hit'] * valid_df['trifecta_odds'] * 100).sum()
                row['total_roi'] = (total_return / total_bet - 1) * 100

            hit_rates = [row.get(f'{y}_hit', np.nan) for y in [2022, 2023, 2024, 2025]]
            hit_rates = [h for h in hit_rates if not pd.isna(h)]
            row['hit_std'] = np.std(hit_rates) if len(hit_rates) >= 2 else np.nan

            results.append(row)

    # 1コース級別 × 予測1着コース
    for rank in df['course1_rank'].dropna().unique():
        for pred_1st in range(1, 7):
            cond_df = df[(df['course1_rank'] == rank) & (df['pred_1st'] == pred_1st)]

            if len(cond_df) < 50:
                continue

            row = {'condition': f"1コース{rank}×予測1着{pred_1st}コース"}

            for year in [2022, 2023, 2024, 2025]:
                year_df = cond_df[cond_df['year'] == year]
                if len(year_df) > 0:
                    row[f'{year}_n'] = len(year_df)
                    row[f'{year}_hit'] = year_df['hit'].mean() * 100
                    valid_df = year_df[year_df['trifecta_odds'].notna()]
                    if len(valid_df) > 0:
                        total_bet = len(valid_df) * 100
                        total_return = (valid_df['hit'] * valid_df['trifecta_odds'] * 100).sum()
                        row[f'{year}_roi'] = (total_return / total_bet - 1) * 100

            row['total_n'] = len(cond_df)
            row['total_hit'] = cond_df['hit'].mean() * 100
            valid_df = cond_df[cond_df['trifecta_odds'].notna()]
            if len(valid_df) > 0:
                total_bet = len(valid_df) * 100
                total_return = (valid_df['hit'] * valid_df['trifecta_odds'] * 100).sum()
                row['total_roi'] = (total_return / total_bet - 1) * 100

            hit_rates = [row.get(f'{y}_hit', np.nan) for y in [2022, 2023, 2024, 2025]]
            hit_rates = [h for h in hit_rates if not pd.isna(h)]
            row['hit_std'] = np.std(hit_rates) if len(hit_rates) >= 2 else np.nan

            results.append(row)

    return pd.DataFrame(results)


def main():
    print("=" * 80)
    print("4年間（2022-2025年）の3連単的中/不的中パターン探索")
    print("=" * 80)

    print("\n[1] データ取得中...")
    df = get_trifecta_data()
    print(f"   取得レース数: {len(df):,}")
    print(f"   年度別レース数:")
    for year in [2022, 2023, 2024, 2025]:
        year_count = len(df[df['year'] == year])
        hit_count = df[df['year'] == year]['hit'].sum()
        hit_rate = df[df['year'] == year]['hit'].mean() * 100
        print(f"     {year}年: {year_count:,}レース, 的中{hit_count:,}件 ({hit_rate:.2f}%)")

    print("\n" + "=" * 80)
    print("[2] 単一条件分析")
    print("=" * 80)

    all_results = []

    # 信頼度別
    print("\n--- 信頼度別 ---")
    conf_results = analyze_by_condition(df, 'confidence', '信頼度')
    if len(conf_results) > 0:
        all_results.append(conf_results)
        print(conf_results.to_string(index=False))

    # オッズ帯別
    print("\n--- オッズ帯別 ---")
    odds_results = analyze_by_condition(df, 'odds_band', 'オッズ帯')
    if len(odds_results) > 0:
        all_results.append(odds_results)
        print(odds_results.to_string(index=False))

    # 1コース級別
    print("\n--- 1コース級別 ---")
    rank_results = analyze_by_condition(df, 'course1_rank', '1コース級別')
    if len(rank_results) > 0:
        all_results.append(rank_results)
        print(rank_results.to_string(index=False))

    # 予測1着コース別
    print("\n--- 予測1着コース別 ---")
    pred1st_results = analyze_by_condition(df, 'pred_1st', '予測1着コース')
    if len(pred1st_results) > 0:
        all_results.append(pred1st_results)
        print(pred1st_results.to_string(index=False))

    # グレード別
    print("\n--- グレード別 ---")
    grade_results = analyze_by_condition(df, 'grade_category', 'グレード')
    if len(grade_results) > 0:
        all_results.append(grade_results)
        print(grade_results.to_string(index=False))

    # スコア差帯別
    print("\n--- スコア差（1位-2位）帯別 ---")
    score_results = analyze_score_diff_bands(df)
    if len(score_results) > 0:
        all_results.append(score_results)
        print(score_results.to_string(index=False))

    print("\n" + "=" * 80)
    print("[3] 複合条件分析")
    print("=" * 80)

    combo_results = analyze_combinations(df)
    if len(combo_results) > 0:
        all_results.append(combo_results)

    # 全結果をマージ
    all_df = pd.concat(all_results, ignore_index=True)

    # 年度間で安定したパターンを抽出（標準偏差が小さいもの）
    print("\n" + "=" * 80)
    print("[4] 年度間で安定したパターン（的中率の標準偏差が小さい順）")
    print("=" * 80)
    stable_df = all_df[all_df['hit_std'].notna()].sort_values('hit_std')
    print("\n--- 的中しやすい条件（的中率高 & 安定）TOP10 ---")
    high_hit = stable_df[(stable_df['total_hit'] >= 10) & (stable_df['total_n'] >= 500)].head(10)
    if len(high_hit) > 0:
        print(high_hit[['condition', 'total_n', 'total_hit', 'total_roi', 'hit_std',
                        '2022_hit', '2023_hit', '2024_hit', '2025_hit']].to_string(index=False))

    print("\n--- 的中しにくい条件（的中率低 & 安定）TOP10 ---")
    low_hit = stable_df[(stable_df['total_hit'] < 5) & (stable_df['total_n'] >= 500)].head(10)
    if len(low_hit) > 0:
        print(low_hit[['condition', 'total_n', 'total_hit', 'total_roi', 'hit_std',
                       '2022_hit', '2023_hit', '2024_hit', '2025_hit']].to_string(index=False))

    print("\n" + "=" * 80)
    print("[5] ROIがプラスの条件（4年間トータル）")
    print("=" * 80)
    positive_roi = all_df[all_df['total_roi'] > 0].sort_values('total_roi', ascending=False)
    if len(positive_roi) > 0:
        print(positive_roi[['condition', 'total_n', 'total_hit', 'total_roi', 'hit_std',
                            '2022_roi', '2023_roi', '2024_roi', '2025_roi']].head(20).to_string(index=False))
    else:
        print("ROIがプラスの条件は見つかりませんでした")

    print("\n" + "=" * 80)
    print("[6] 2024-2025年で特にROIが高い条件")
    print("=" * 80)
    # 2024-2025年の平均ROI
    all_df['recent_roi'] = (all_df['2024_roi'].fillna(0) + all_df['2025_roi'].fillna(0)) / 2
    recent_good = all_df[(all_df['2024_roi'].notna()) | (all_df['2025_roi'].notna())].sort_values('recent_roi', ascending=False)
    print(recent_good[['condition', 'total_n', '2022_roi', '2023_roi', '2024_roi', '2025_roi', 'recent_roi']].head(20).to_string(index=False))

    print("\n" + "=" * 80)
    print("[7] 会場別分析")
    print("=" * 80)
    venue_results = analyze_by_condition(df, 'venue_code', '会場')
    if len(venue_results) > 0:
        # 安定して的中率が高い会場
        print("\n--- 安定して的中率が高い会場 ---")
        venue_sorted = venue_results.sort_values('total_hit', ascending=False)
        print(venue_sorted[['condition', 'total_n', 'total_hit', 'total_roi', 'hit_std',
                           '2022_hit', '2023_hit', '2024_hit', '2025_hit']].head(10).to_string(index=False))

        print("\n--- 安定して的中率が低い会場 ---")
        venue_sorted = venue_results.sort_values('total_hit', ascending=True)
        print(venue_sorted[['condition', 'total_n', 'total_hit', 'total_roi', 'hit_std',
                           '2022_hit', '2023_hit', '2024_hit', '2025_hit']].head(10).to_string(index=False))

    return all_df


if __name__ == "__main__":
    results = main()
