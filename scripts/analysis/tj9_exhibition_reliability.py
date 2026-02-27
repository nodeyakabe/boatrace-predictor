#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TJ-9: 展示タイム信頼性マップ作成

会場別に「展示タイム順位と実着順の一致率」を定量化し、
ExtendedScorerの展示タイム重み付け調整の材料を得る。

出力: data/venue_exhibition_reliability.json
"""
import sqlite3
import sys
import io
import json
import argparse
from pathlib import Path
import pandas as pd
import numpy as np

try:
    from scipy.stats import spearmanr
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    print("警告: scipy未インストール。手動Spearman計算を使用。")

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ===========================
# 定数
# ===========================

DB_PATH = Path(__file__).parent.parent.parent / "data" / "boatrace.db"
OUTPUT_JSON = Path(__file__).parent.parent.parent / "data" / "venue_exhibition_reliability.json"
MIN_SAMPLE = 200  # 信頼性評価に最低200レース

VENUE_NAMES = {
    1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川', 6: '浜名湖',
    7: '蒲郡', 8: '常滑', 9: '津', 10: '三国', 11: '琵琶湖', 12: '住之江',
    13: '尼崎', 14: '鳴門', 15: '丸亀', 16: '児島', 17: '宮島', 18: '徳山',
    19: '下関', 20: '若松', 21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村'
}


def get_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ===========================
# Spearman相関ヘルパー
# ===========================

def calc_spearman(x, y):
    """scipy or 手動Spearman相関計算"""
    if len(x) < 4:
        return np.nan
    if HAS_SCIPY:
        corr, _ = spearmanr(x, y)
        return corr
    else:
        # 手動計算
        n = len(x)
        rx = pd.Series(x).rank()
        ry = pd.Series(y).rank()
        d2 = ((rx - ry) ** 2).sum()
        return 1 - 6 * d2 / (n * (n ** 2 - 1))


# ===========================
# Step 1: データ充足率確認
# ===========================

def check_data_coverage(conn, start_year, end_year):
    print("=" * 60)
    print("Step 1: データ充足率確認")
    print("=" * 60)

    query = f"""
    SELECT
        CAST(r.venue_code AS INTEGER) as venue_code,
        COUNT(DISTINCT rd.race_id) as races_with_exh,
        COUNT(*) as total_rows,
        COUNT(rd.exhibition_time) as has_exh_time,
        ROUND(100.0 * COUNT(rd.exhibition_time) / COUNT(*), 1) as exh_rate
    FROM race_details rd
    JOIN races r ON rd.race_id = r.id
    JOIN results res ON rd.race_id = res.race_id
        AND rd.pit_number = res.pit_number
        AND res.is_invalid = 0
    WHERE r.race_date BETWEEN '{start_year}-01-01' AND '{end_year}-12-31'
      AND rd.exhibition_time IS NOT NULL AND rd.exhibition_time > 0
    GROUP BY r.venue_code
    ORDER BY CAST(r.venue_code AS INTEGER)
    """
    df = pd.read_sql_query(query, conn)

    print(f"\n{'会場コード':>8} {'会場名':<10} {'レース数':>10} {'行数':>10} {'展示あり':>10} {'充足率':>8}")
    for _, row in df.iterrows():
        vc = int(row['venue_code'])
        vname = VENUE_NAMES.get(vc, f'会場{vc}')
        print(f"  {vc:>6} {vname:<10} {int(row['races_with_exh']):>10,} "
              f"{int(row['total_rows']):>10,} {int(row['has_exh_time']):>10,} "
              f"{row['exh_rate']:>7.1f}%")

    total_races = df['races_with_exh'].sum()
    print(f"\n  合計レース数（展示タイムあり）: {int(total_races):,}件")
    print(f"  対象会場数: {len(df)}会場")


# ===========================
# Step 2: メインデータ取得
# ===========================

def load_data(conn, start_year, end_year):
    print("=" * 60)
    print("Step 2: 展示タイムと実着順データ取得")
    print("=" * 60)

    query = f"""
    SELECT
        rd.race_id,
        CAST(r.venue_code AS INTEGER) as venue_code,
        strftime('%Y', r.race_date) as year,
        rd.pit_number,
        rd.exhibition_time,
        CAST(res.rank AS INTEGER) as actual_rank
    FROM race_details rd
    JOIN races r ON rd.race_id = r.id
    JOIN results res ON rd.race_id = res.race_id
        AND rd.pit_number = res.pit_number
        AND res.is_invalid = 0
    WHERE r.race_date BETWEEN '{start_year}-01-01' AND '{end_year}-12-31'
      AND rd.exhibition_time IS NOT NULL AND rd.exhibition_time > 0
      AND res.rank IS NOT NULL
      AND CAST(res.rank AS INTEGER) BETWEEN 1 AND 6
    """
    print("  データ取得中...")
    df = pd.read_sql_query(query, conn)
    print(f"  取得件数: {len(df):,}行, レース数: {df['race_id'].nunique():,}レース")

    # 各レース内で展示タイムの速い順にランク付け（小さい=速い=1位）
    print("  展示タイムランク付け中...")
    df['exhibition_rank'] = df.groupby('race_id')['exhibition_time'].rank(
        method='min', ascending=True
    )

    print(f"  会場数: {df['venue_code'].nunique()}会場")
    print(f"  年度: {sorted(df['year'].unique())}")

    return df


# ===========================
# Step 3: 会場別信頼性指標計算
# ===========================

def _spearman_per_race(group):
    """各レース内のSpearman相関をpandas applyで計算（高速化）"""
    if len(group) < 4:
        return np.nan
    x = group['exhibition_rank'].values
    y = group['actual_rank'].values
    # 定数チェック（全艇同タイム等）
    if np.all(x == x[0]) or np.all(y == y[0]):
        return np.nan
    if HAS_SCIPY:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            corr, _ = spearmanr(x, y)
        return corr
    else:
        n = len(x)
        rx = pd.Series(x).rank()
        ry = pd.Series(y).rank()
        d2 = ((rx - ry) ** 2).sum()
        return 1 - 6 * d2 / (n * (n ** 2 - 1))


def analyze_venue_reliability(df):
    print("=" * 60)
    print("Step 3: 会場別信頼性指標計算")
    print("=" * 60)

    venue_codes = sorted(df['venue_code'].unique())
    print(f"  {len(venue_codes)}会場の計算開始...")

    # レース単位でSpearman相関を一括計算（apply）
    print("  Spearman相関をレース単位で一括計算中...")
    race_spearman_series = df.groupby('race_id', group_keys=False).apply(_spearman_per_race)
    race_spearman_df = race_spearman_series.reset_index()
    race_spearman_df.columns = ['race_id', 'spearman']

    # race_idごとのvenue_codeを紐付け
    race_venue = df[['race_id', 'venue_code']].drop_duplicates()
    race_spearman_df = race_spearman_df.merge(race_venue, on='race_id')

    # 展示1位→実1着フラグ
    exh1_df = df[df['exhibition_rank'] == 1].copy()
    exh1_df['top1_hit'] = (exh1_df['actual_rank'] == 1).astype(int)

    results_list = []
    for venue_code in venue_codes:
        # top1_rate
        venue_exh1 = exh1_df[exh1_df['venue_code'] == venue_code]
        top1_rate = venue_exh1['top1_hit'].mean() if len(venue_exh1) > 0 else np.nan

        # Spearman平均
        venue_sp = race_spearman_df[
            (race_spearman_df['venue_code'] == venue_code) &
            race_spearman_df['spearman'].notna()
        ]['spearman']
        avg_spearman = venue_sp.mean() if len(venue_sp) > 0 else np.nan
        n_spearman_samples = len(venue_sp)

        n_races = df[df['venue_code'] == venue_code]['race_id'].nunique()

        results_list.append({
            'venue_code': int(venue_code),
            'venue_name': VENUE_NAMES.get(int(venue_code), f'会場{venue_code}'),
            'n_races': n_races,
            'top1_rate': round(float(top1_rate), 4) if not np.isnan(top1_rate) else 0.0,
            'spearman': round(float(avg_spearman), 4) if not np.isnan(avg_spearman) else None,
            'n_spearman_samples': n_spearman_samples
        })

    # top1_rate順にソートして表示
    results_sorted = sorted(results_list, key=lambda x: x['top1_rate'], reverse=True)
    print(f"\n{'会場':<12} {'レース数':>8} {'展示1位→1着率':>14} {'Spearman相関':>14} {'Spearmanサンプル':>16}")
    for v in results_sorted:
        sp_str = f"{v['spearman']:.4f}" if v['spearman'] is not None else "  N/A  "
        print(f"  {v['venue_name']:<10} {v['n_races']:>8,} {v['top1_rate']*100:>13.1f}% "
              f"{sp_str:>14} {v['n_spearman_samples']:>15,}")

    return results_list


# ===========================
# Step 4: 年度別トレンド分析
# ===========================

def analyze_yearly_trend(df):
    print("=" * 60)
    print("Step 4: 年度別トレンド分析（安定性確認）")
    print("=" * 60)

    # 各会場 × 年度でtop1_rateを計算
    yearly_results = []
    for (venue_code, year), gdf in df.groupby(['venue_code', 'year']):
        exh1_rows = gdf[gdf['exhibition_rank'] == 1]
        if len(exh1_rows) < 10:
            continue
        top1_rate = (exh1_rows['actual_rank'] == 1).mean()
        n_races = gdf['race_id'].nunique()
        yearly_results.append({
            'venue_code': int(venue_code),
            'venue_name': VENUE_NAMES.get(int(venue_code), f'会場{venue_code}'),
            'year': str(year),
            'top1_rate': top1_rate,
            'n_races': n_races
        })

    df_yearly = pd.DataFrame(yearly_results)

    # 変動係数（CV = std/mean）を会場別に計算
    cv_results = []
    for venue_code, vdf in df_yearly.groupby('venue_code'):
        if len(vdf) < 2:
            continue
        mean_rate = vdf['top1_rate'].mean()
        std_rate = vdf['top1_rate'].std()
        cv = (std_rate / mean_rate) if mean_rate > 0 else np.nan
        cv_results.append({
            'venue_code': int(venue_code),
            'venue_name': VENUE_NAMES.get(int(venue_code), f'会場{venue_code}'),
            'mean_top1_rate': mean_rate,
            'std_top1_rate': std_rate,
            'cv': cv,
            'n_years': len(vdf)
        })

    cv_df = pd.DataFrame(cv_results).sort_values('cv', ascending=False)

    # CVが大きい（>10%）会場を「年度依存性高」として注意表示
    high_cv = cv_df[cv_df['cv'] > 0.10]
    print(f"\n  年度依存性高（CV > 10%）: {len(high_cv)}会場")
    if len(high_cv) > 0:
        for _, row in high_cv.iterrows():
            print(f"    {row['venue_name']}: CV={row['cv']*100:.1f}%, "
                  f"平均={row['mean_top1_rate']*100:.1f}%, 標準偏差={row['std_top1_rate']*100:.1f}%")

    # 上位5会場（CV小=安定）の詳細
    cv_stable = cv_df.nsmallest(5, 'cv')
    print(f"\n[安定TOP5会場（年度依存性が低い）]")
    years = sorted(df_yearly['year'].unique())
    print(f"  {'会場':<10} {'CV':>6} {'平均top1':>9}", end='')
    for y in years:
        print(f"  {y:>6}", end='')
    print()

    for _, row in cv_stable.iterrows():
        vc = row['venue_code']
        vdf = df_yearly[df_yearly['venue_code'] == vc]
        print(f"  {row['venue_name']:<10} {row['cv']*100:>5.1f}% {row['mean_top1_rate']*100:>8.1f}%", end='')
        for y in years:
            yr = vdf[vdf['year'] == y]
            if len(yr) > 0:
                print(f"  {yr['top1_rate'].values[0]*100:>5.1f}%", end='')
            else:
                print(f"  {'N/A':>6}", end='')
        print()

    # 下位5会場（CV大=不安定）の詳細
    cv_unstable = cv_df.nlargest(5, 'cv')
    print(f"\n[不安定TOP5会場（年度依存性が高い）]")
    print(f"  {'会場':<10} {'CV':>6} {'平均top1':>9}", end='')
    for y in years:
        print(f"  {y:>6}", end='')
    print()

    for _, row in cv_unstable.iterrows():
        vc = row['venue_code']
        vdf = df_yearly[df_yearly['venue_code'] == vc]
        print(f"  {row['venue_name']:<10} {row['cv']*100:>5.1f}% {row['mean_top1_rate']*100:>8.1f}%", end='')
        for y in years:
            yr = vdf[vdf['year'] == y]
            if len(yr) > 0:
                print(f"  {yr['top1_rate'].values[0]*100:>5.1f}%", end='')
            else:
                print(f"  {'N/A':>6}", end='')
        print()


# ===========================
# Step 5: コース補正分析
# ===========================

def analyze_course_corrected(df):
    print("=" * 60)
    print("Step 5: コース補正（1コース有利効果を除いた分析）")
    print("=" * 60)

    print("  問題: 1コース艇は有利 → 展示タイム1位 = 1コース艇の場合の効果を除外")
    print("  簡易補正: pit_number=1 の艇を除外して分析")

    # 1コース除外
    df_no_pit1 = df[df['pit_number'] != 1].copy()

    # 除外後に再ランク付け
    df_no_pit1['exhibition_rank'] = df_no_pit1.groupby('race_id')['exhibition_time'].rank(
        method='min', ascending=True
    )

    print(f"\n  除外前: {len(df):,}行 / 除外後: {len(df_no_pit1):,}行 "
          f"(除外: {len(df) - len(df_no_pit1):,}行)")

    # 補正前後のtop1_rateを会場ごとに比較
    correction_results = []
    venue_codes = sorted(df['venue_code'].unique())

    for venue_code in venue_codes:
        vdf_orig = df[df['venue_code'] == venue_code]
        vdf_corr = df_no_pit1[df_no_pit1['venue_code'] == venue_code]

        if len(vdf_orig) == 0 or len(vdf_corr) == 0:
            continue

        # 補正前
        exh1_orig = vdf_orig[vdf_orig['exhibition_rank'] == 1]
        top1_orig = (exh1_orig['actual_rank'] == 1).mean() if len(exh1_orig) > 0 else np.nan

        # 補正後
        exh1_corr = vdf_corr[vdf_corr['exhibition_rank'] == 1]
        top1_corr = (exh1_corr['actual_rank'] == 1).mean() if len(exh1_corr) > 0 else np.nan

        diff = top1_corr - top1_orig if not (np.isnan(top1_orig) or np.isnan(top1_corr)) else np.nan

        correction_results.append({
            'venue_code': int(venue_code),
            'venue_name': VENUE_NAMES.get(int(venue_code), f'会場{venue_code}'),
            'top1_orig': top1_orig,
            'top1_corr': top1_corr,
            'diff': diff
        })

    # diff順にソート（変化量が大きい順）
    corr_sorted = sorted(correction_results,
                         key=lambda x: abs(x['diff']) if not np.isnan(x['diff']) else 0,
                         reverse=True)

    print(f"\n{'会場':<12} {'補正前':>8} {'補正後':>8} {'変化':>8} {'評価':>10}")
    for v in corr_sorted:
        diff_str = f"{v['diff']*100:+.1f}pt" if not np.isnan(v['diff']) else "  N/A"
        orig_str = f"{v['top1_orig']*100:.1f}%" if not np.isnan(v['top1_orig']) else "N/A"
        corr_str = f"{v['top1_corr']*100:.1f}%" if not np.isnan(v['top1_corr']) else "N/A"
        eval_str = "1コース依存高" if (not np.isnan(v['diff']) and v['diff'] < -0.03) else ""
        print(f"  {v['venue_name']:<10} {orig_str:>8} {corr_str:>8} {diff_str:>8} {eval_str:>10}")

    return correction_results


# ===========================
# Step 6: 信頼性スコア算出
# ===========================

def calc_reliability_scores(venue_results):
    print("=" * 60)
    print("Step 6: 信頼性スコア算出（0-100点）")
    print("=" * 60)

    # MIN_SAMPLE未満の会場は除外
    valid = [v for v in venue_results if v['n_races'] >= MIN_SAMPLE and v['spearman'] is not None]
    excluded = [v for v in venue_results if v['n_races'] < MIN_SAMPLE or v['spearman'] is None]

    if excluded:
        print(f"\n  サンプル不足またはSpearman未計算のため除外: {len(excluded)}会場")
        for v in excluded:
            print(f"    {v['venue_name']}: n_races={v['n_races']}, spearman={v['spearman']}")

    if len(valid) == 0:
        print("  有効な会場がありません。")
        return venue_results

    # top1_rateを0-100にスケーリング（全会場の10%tile-90%tileで正規化）
    top1_vals = [v['top1_rate'] for v in valid]
    sp_vals = [v['spearman'] for v in valid]

    p10_t = np.percentile(top1_vals, 10)
    p90_t = np.percentile(top1_vals, 90)
    p10_s = np.percentile(sp_vals, 10)
    p90_s = np.percentile(sp_vals, 90)

    def norm_score(val, p10, p90):
        if p90 == p10:
            return 50.0
        return max(0.0, min(100.0, (val - p10) / (p90 - p10) * 100))

    for v in valid:
        s_top1 = norm_score(v['top1_rate'], p10_t, p90_t) * 0.5
        s_sp = norm_score(v['spearman'], p10_s, p90_s) * 0.4
        # サンプルボーナス: 1000レース以上で満点10pt
        s_sample = min(10.0, v['n_races'] / 1000 * 10) * 0.1
        v['reliability_score'] = round(s_top1 + s_sp + s_sample, 1)

    # スコアなし会場にはデフォルト値を設定
    for v in excluded:
        v['reliability_score'] = 50.0  # デフォルト中間値

    # ソートして表示
    valid_sorted = sorted(valid, key=lambda x: x['reliability_score'], reverse=True)

    print(f"\n  スコア算出: {len(valid)}会場 (除外: {len(excluded)}会場)")
    print(f"\n{'会場':<15} {'スコア':>6} {'展示1位→1着':>12} {'Spearman':>10} {'サンプル数':>10}")
    for v in valid_sorted:
        print(f"  {v['venue_name']:<13} {v['reliability_score']:>6.1f} "
              f"{v['top1_rate']*100:>11.1f}% {v['spearman']:>10.3f} {v['n_races']:>10,}")

    # 全venue_resultsにスコアを反映（valid以外もデフォルト50.0は設定済み）
    # valid に含まれないものを元のリストに上書き
    score_map = {v['venue_code']: v for v in valid}
    for v in venue_results:
        if v['venue_code'] in score_map:
            v['reliability_score'] = score_map[v['venue_code']]['reliability_score']
        elif 'reliability_score' not in v:
            v['reliability_score'] = 50.0

    return venue_results


# ===========================
# Step 7: JSON保存とExtendedScorerへの活用提案
# ===========================

def save_json_and_suggest(venue_results, no_json=False):
    print("=" * 60)
    print("Step 7: JSON保存とExtendedScorerへの活用提案")
    print("=" * 60)

    # JSON形式
    venue_reliability = {}
    for v in venue_results:
        vc = v['venue_code']
        venue_reliability[vc] = {
            "name": v['venue_name'],
            "score": v.get('reliability_score', 50.0),
            "spearman": v['spearman'],
            "top1_rate": v['top1_rate'],
            "sample": v['n_races']
        }

    if not no_json:
        OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
            json.dump(venue_reliability, f, ensure_ascii=False, indent=2)
        print(f"\n  JSONを保存: {OUTPUT_JSON}")

    # ExtendedScorerへの活用提案
    sorted_venues = sorted(venue_results, key=lambda x: x.get('reliability_score', 50.0), reverse=True)

    high_venues = [v for v in sorted_venues if v.get('reliability_score', 0) >= 70]
    low_venues = [v for v in sorted_venues if v.get('reliability_score', 100) < 40]

    print(f"\n=== ExtendedScorer 展示タイム重み調整案 ===")
    print(f"\n高信頼会場 (score >= 70): 展示タイムの重みを増加推奨")
    if high_venues:
        for v in high_venues:
            vc_padded = str(v['venue_code']).zfill(2)
            print(f"  {v['venue_name']}({vc_padded}) score={v.get('reliability_score', 0):.1f} "
                  f"→ 重み係数 1.2")
    else:
        print("  (該当会場なし)")

    print(f"\n低信頼会場 (score < 40): 展示タイムの重みを減少推奨")
    if low_venues:
        for v in low_venues:
            vc_padded = str(v['venue_code']).zfill(2)
            print(f"  {v['venue_name']}({vc_padded}) score={v.get('reliability_score', 0):.1f} "
                  f"→ 重み係数 0.7")
    else:
        print("  (該当会場なし)")

    # 高信頼会場コードリスト
    high_codes = [v['venue_code'] for v in high_venues]
    low_codes = [v['venue_code'] for v in low_venues]

    print(f"\n=== 次のアクション ===")
    print(f"1. {OUTPUT_JSON}")
    print(f"   を ExtendedScorer から参照")
    print(f"2. 高信頼会場でのbeforeタイム条件フィルターを追加検討")
    print(f"3. Tier1テスト候補コマンド:")
    if high_codes:
        print(f'   python scripts/backtest/quick_condition_test.py --condition-json \'{{')
        print(f'     "id": "EXH_HIGH_VENUE",')
        print(f'     "name": "展示高信頼会場フィルター",')
        print(f'     "confidence": "B",')
        print(f'     "venue_filter": {high_codes},')
        print(f'     "use_pattern_h": true')
        print(f"   }}'")

    return venue_reliability


# ===========================
# メイン実行
# ===========================

def main():
    parser = argparse.ArgumentParser(description='TJ-9: 展示タイム信頼性マップ')
    parser.add_argument('--start-year', type=int, default=2020)
    parser.add_argument('--end-year', type=int, default=2025)
    parser.add_argument('--no-json', action='store_true', help='JSON出力を省略')
    args = parser.parse_args()

    print(f"TJ-9: 展示タイム信頼性マップ ({args.start_year}-{args.end_year}年)")
    print("=" * 60)

    conn = get_connection()
    try:
        check_data_coverage(conn, args.start_year, args.end_year)
        df = load_data(conn, args.start_year, args.end_year)
        if df is None or len(df) == 0:
            print("データが取得できませんでした。")
            return
        venue_results = analyze_venue_reliability(df)
        analyze_yearly_trend(df)
        analyze_course_corrected(df)
        venue_results = calc_reliability_scores(venue_results)
        save_json_and_suggest(venue_results, no_json=args.no_json)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
