# -*- coding: utf-8 -*-
"""
3着候補選択の改善分析 v2
B×A1×30-50×8会場条件を対象に4つの改善案を検証する

【修正内容】
- get_race_ids_for_condition を使いバックテストと完全に同じ母集団を使用
- advance_before_match フィルタを含む全条件が自動適用される
- オッズフィルタもバックテストと同じ「p3 OR p4 が範囲内」方式

案A: p1-p2が1-2着に来たとき、3着は予測何位が来るか
案B: p4軸の期待値（オッズ × 的中確率）
案C: p3/p4のスコア差と的中率の相関
案D: コース番号ベースの3着出現パターン（会場別・統計的有意性検証付き）
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import os
import sqlite3
import pandas as pd
import numpy as np
from scipy import stats as scipy_stats

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from scripts.backtest.backtest_helpers import get_race_ids_for_condition
from config.bet_conditions import STANDARD_BET_CONDITIONS

DB_PATH = os.path.join(PROJECT_ROOT, "data/boatrace.db")

VENUE_NAMES = {
    '02': '戸田', '03': '江戸川', '06': '浜名湖', '08': '常滑',
    '09': '津', '12': '住之江', '17': '宮島', '19': '下関',
    2: '戸田', 3: '江戸川', 6: '浜名湖', 8: '常滑',
    9: '津', 12: '住之江', 17: '宮島', 19: '下関',
}

def get_condition():
    """B_A1_30_50_8VENUESの条件定義を取得"""
    for cond in STANDARD_BET_CONDITIONS:
        if cond.get('id') == 'B_A1_30_50_8VENUES':
            return cond
    raise ValueError("B_A1_30_50_8VENUES 条件が見つかりません")

def load_race_data(conn, race_ids):
    """
    バックテストと同じレースIDセットに対して分析用データを取得

    オッズはp3・p4両方を取得する。
    バックテストと同様に「どちらかが30-50倍」であれば対象レースとする。
    """
    if not race_ids:
        return pd.DataFrame()

    # 一時テーブルにレースIDを格納
    conn.execute("DROP TABLE IF EXISTS _target_race_ids")
    conn.execute("CREATE TEMP TABLE _target_race_ids (race_id INTEGER PRIMARY KEY)")
    conn.executemany("INSERT INTO _target_race_ids VALUES (?)", [(rid,) for rid in race_ids])

    query = """
    SELECT
        r.id AS race_id,
        r.race_date,
        r.venue_code,
        r.race_number,
        rp1.pit_number AS p1_pit,
        rp2.pit_number AS p2_pit,
        rp3.pit_number AS p3_pit,
        rp4.pit_number AS p4_pit,
        rp5.pit_number AS p5_pit,
        rp1.total_score AS p1_score,
        rp2.total_score AS p2_score,
        rp3.total_score AS p3_score,
        rp4.total_score AS p4_score,
        -- p3軸オッズ（p1-p2-p3）
        COALESCE((
            SELECT o.odds FROM trifecta_odds o
            WHERE o.race_id = r.id
              AND o.combination = CAST(rp1.pit_number AS TEXT) || '-'
                               || CAST(rp2.pit_number AS TEXT) || '-'
                               || CAST(rp3.pit_number AS TEXT)
        ), 0) AS odds_p3,
        -- p4軸オッズ（p1-p2-p4）
        COALESCE((
            SELECT o.odds FROM trifecta_odds o
            WHERE o.race_id = r.id
              AND o.combination = CAST(rp1.pit_number AS TEXT) || '-'
                               || CAST(rp2.pit_number AS TEXT) || '-'
                               || CAST(rp4.pit_number AS TEXT)
        ), 0) AS odds_p4,
        -- 実際の着順（pit別）
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') AS actual_1st,
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') AS actual_2nd,
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') AS actual_3rd
    FROM races r
    JOIN _target_race_ids tr ON tr.race_id = r.id
    JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
    JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
    LEFT JOIN race_predictions rp5 ON r.id = rp5.race_id AND rp5.prediction_type = 'before' AND rp5.rank_prediction = 5
    """
    df = pd.read_sql_query(query, conn)
    return df


def add_derived_columns(df, cond):
    """分析用の派生カラムを追加"""
    odds_min = cond['odds_min']
    odds_max = cond['odds_max']

    # バックテストと同じ: p3軸 OR p4軸のどちらかがオッズ範囲内 → 投資対象
    df['bet_p3'] = df['odds_p3'].apply(lambda x: 200 if odds_min <= x < odds_max else 0)
    df['bet_p4'] = df['odds_p4'].apply(lambda x: 100 if odds_min <= x < odds_max else 0)
    df['is_bet'] = (df['bet_p3'] > 0) | (df['bet_p4'] > 0)

    # p1-p2が1-2着的中（順序通り）
    df['p12_hit'] = (df['actual_1st'] == df['p1_pit']) & (df['actual_2nd'] == df['p2_pit'])

    # 3着に来た艇が予測何位だったか
    def get_third_pred_rank(row):
        third = row['actual_3rd']
        if pd.isna(third):
            return None
        for r in range(1, 6):
            col = f'p{r}_pit'
            if col in row.index and row[col] == third:
                return r
        return 6  # p6以下

    df['actual_third_pred_rank'] = df.apply(get_third_pred_rank, axis=1)

    # p3/p4スコア差
    df['score_diff_p3_p4'] = df['p3_score'] - df['p4_score']

    # p3軸・p4軸の的中フラグ
    df['p3_hit'] = (df['p12_hit']) & (df['actual_3rd'] == df['p3_pit']) & (df['bet_p3'] > 0)
    df['p4_hit'] = (df['p12_hit']) & (df['actual_3rd'] == df['p4_pit']) & (df['bet_p4'] > 0)
    df['any_hit'] = df['p3_hit'] | df['p4_hit']

    return df


def analyze_case_a(df):
    """案A: p1-p2的中時の3着予測順位分布"""
    print("\n" + "="*60)
    print("【案A】p1-p2的中時の3着予測順位分布")
    print("="*60)

    bet_df = df[df['is_bet']].copy()
    hit_df = bet_df[bet_df['p12_hit']].copy()
    n_bet = len(bet_df)
    n_hit = len(hit_df)

    print(f"投資対象レース（p3 OR p4がオッズ範囲内）: {n_bet}件")
    print(f"p1-p2が1-2着的中: {n_hit}件 ({n_hit/n_bet*100:.1f}%)")
    print()

    # 3着が予測何位だったかの分布
    dist = hit_df['actual_third_pred_rank'].value_counts().sort_index()
    total = dist.sum()
    print(f"3着に来た艇の予測順位分布（p1-p2的中レースのみ）:")
    print(f"{'予測順位':>8} | {'件数':>5} | {'割合':>7} | {'累積':>7}")
    print("-" * 35)
    cumulative = 0
    for rank, count in dist.items():
        pct = count / total * 100
        cumulative += pct
        label = f"p{int(rank)}" if rank <= 5 else "p6+"
        print(f"{label:>8} | {count:>5} | {pct:>6.1f}% | {cumulative:>6.1f}%")

    print()
    covered_p3 = dist.get(3, 0)
    covered_p4 = dist.get(4, 0)
    covered_p5 = dist.get(5, 0)

    print(f"現行H2（p3のみ・200円）  カバー: {covered_p3}/{total} = {covered_p3/total*100:.1f}%")
    print(f"現行H2（p3+p4・300円）   カバー: {covered_p3+covered_p4}/{total} = {(covered_p3+covered_p4)/total*100:.1f}%")
    print(f"旧H  （p3+p4+p5・400円） カバー: {covered_p3+covered_p4+covered_p5}/{total} = {(covered_p3+covered_p4+covered_p5)/total*100:.1f}%")

    print()
    print(f"【全体的中率（投資レース基準）】")
    n_p3_hit = df['p3_hit'].sum()
    n_p4_hit = df['p4_hit'].sum()
    n_any_hit = df['any_hit'].sum()
    print(f"p3軸的中（1-2-3）: {n_p3_hit}/{n_bet} = {n_p3_hit/n_bet*100:.2f}%")
    print(f"p4軸的中（1-2-4）: {n_p4_hit}/{n_bet} = {n_p4_hit/n_bet*100:.2f}%")
    print(f"いずれか的中    : {n_any_hit}/{n_bet} = {n_any_hit/n_bet*100:.2f}%")

    return hit_df


def analyze_case_b(df):
    """案B: p3軸・p4軸それぞれの期待値比較"""
    print("\n" + "="*60)
    print("【案B】p3軸 vs p4軸の期待値比較")
    print("="*60)

    bet_df = df[df['is_bet']].copy()

    for label, odds_col, hit_col, bet_col in [
        ('p3軸（1-2-3）', 'odds_p3', 'p3_hit', 'bet_p3'),
        ('p4軸（1-2-4）', 'odds_p4', 'p4_hit', 'bet_p4'),
    ]:
        sub = bet_df[bet_df[bet_col] > 0].copy()
        n = len(sub)
        hits = sub[hit_col].sum()
        hit_rate = hits / n if n > 0 else 0
        avg_odds = sub[sub[odds_col] > 0][odds_col].mean() if n > 0 else 0
        payout = (sub[hit_col] * sub[odds_col] * sub[bet_col]).sum()
        investment = sub[bet_col].sum()
        roi = payout / investment * 100 if investment > 0 else 0
        profit = payout - investment
        ev = hit_rate * avg_odds

        print(f"\n{label}:")
        print(f"  件数: {n}件 / 的中: {hits}件 / 的中率: {hit_rate*100:.2f}%")
        print(f"  平均オッズ: {avg_odds:.1f}倍")
        print(f"  EV（的中率×平均オッズ）: {ev:.3f}  ({'プラス' if ev >= 1 else 'マイナス'})")
        print(f"  投資: {investment:,}円 / 払戻: {payout:,}円")
        print(f"  ROI: {roi:.1f}% / 収支: {profit:+,}円")

    print()
    print("【p4軸オッズ帯別の期待値】")
    print(f"{'オッズ帯':>12} | {'件数':>5} | {'的中':>5} | {'的中率':>8} | {'平均EV':>8} | {'100円収益':>9}")
    print("-" * 60)
    p4_sub = bet_df[bet_df['bet_p4'] > 0].copy()
    for lo, hi in [(0,30),(30,50),(50,80),(80,120),(120,9999)]:
        mask = (p4_sub['odds_p4'] >= lo) & (p4_sub['odds_p4'] < hi)
        s = p4_sub[mask]
        if len(s) == 0:
            continue
        n = len(s)
        hits = s['p4_hit'].sum()
        hr = hits / n
        avg_o = s['odds_p4'].mean()
        ev = hr * avg_o
        label = f"{lo}-{hi}倍" if hi < 9999 else f"{lo}倍+"
        print(f"{label:>12} | {n:>5} | {hits:>5} | {hr*100:>7.1f}% | {ev:>8.3f} | {ev*100-100:>+8.0f}円")


def analyze_case_c(df):
    """案C: p3/p4スコア差 × p4的中率の相関"""
    print("\n" + "="*60)
    print("【案C】p3/p4スコア差 × p4的中率の相関")
    print("="*60)

    # p4軸が投資対象のレースで分析
    sub = df[df['bet_p4'] > 0].copy()
    valid = sub[sub['score_diff_p3_p4'].notna()].copy()
    n_total = len(valid)

    print(f"p4軸投資対象レース: {n_total}件")
    print(f"p3_score - p4_score の統計:")
    print(f"  平均: {valid['score_diff_p3_p4'].mean():.2f}  中央値: {valid['score_diff_p3_p4'].median():.2f}  標準偏差: {valid['score_diff_p3_p4'].std():.2f}")
    print()

    # 閾値別
    print(f"{'スコア差閾値':>12} | {'件数':>6} | {'全体%':>7} | {'p4的中':>7} | {'p4的中率':>9}")
    print("-" * 55)
    for thr in [1, 2, 3, 5, 8, 10, 15]:
        s = valid[valid['score_diff_p3_p4'] <= thr]
        n = len(s)
        if n == 0:
            continue
        hits = s['p4_hit'].sum()
        hr = hits / n * 100
        pct = n / n_total * 100
        print(f"差<={thr:3d}pt     | {n:>6} | {pct:>6.1f}% | {hits:>7} | {hr:>8.2f}%")

    print(f"{'全体':>12} | {n_total:>6} | {'100.0%':>7} | {valid['p4_hit'].sum():>7} | {valid['p4_hit'].mean()*100:>8.2f}%")

    corr = valid[['score_diff_p3_p4', 'p4_hit']].corr().iloc[0, 1]
    print(f"\nスコア差 vs p4的中 相関係数: {corr:.4f}")
    print("  （負の値 → スコア差が小さいほどp4が来やすい方向）")

    # 分位数別
    print()
    print("スコア差の分位数別 p4的中率（5分割）:")
    valid['qtile'] = pd.qcut(valid['score_diff_p3_p4'], 5,
                              labels=['最小20%','20-40%','40-60%','60-80%','最大20%'])
    grp = valid.groupby('qtile', observed=True).agg(
        件数=('p4_hit','count'),
        的中=('p4_hit','sum'),
        的中率=('p4_hit','mean'),
        差_min=('score_diff_p3_p4','min'),
        差_max=('score_diff_p3_p4','max'),
    )
    for idx, row in grp.iterrows():
        print(f"  {idx}: 差 {row['差_min']:.1f}~{row['差_max']:.1f}pt | {row['件数']:>5}件 | 的中率 {row['的中率']*100:>5.1f}%")


def analyze_case_d(df):
    """案D: コース別3着出現パターン（会場別・統計的有意性検証）"""
    print("\n" + "="*60)
    print("【案D】3着コース別出現パターン（会場別・統計的有意性検証）")
    print("="*60)
    print("注意: 多重比較あり。p<0.05は参考値。会場別に独立判断すること")
    print()

    bet_df = df[df['is_bet']].copy()
    hit_df = bet_df[bet_df['p12_hit']].copy()
    n_hit = len(hit_df)

    if n_hit == 0:
        print("p1-p2的中レースが0件のため分析不能")
        return {}

    # venue_codeを整数に正規化（'02' → 2）
    def normalize_venue(v):
        try:
            return int(v)
        except:
            return v

    hit_df = hit_df.copy()
    hit_df['venue_int'] = hit_df['venue_code'].apply(normalize_venue)

    # 全会場合算
    print(f"【全会場合算】p1-p2的中レース {n_hit}件")
    dist_all = hit_df['actual_3rd'].value_counts().sort_index()
    for course, cnt in dist_all.items():
        print(f"  {course}コース: {cnt}件 ({cnt/n_hit*100:.1f}%)")

    print()
    print("【会場別分析】（n>=10 の会場のみ）")

    venue_results = {}
    target_venues_int = [2, 3, 6, 8, 9, 12, 17, 19]

    for venue_int in sorted(target_venues_int):
        name = VENUE_NAMES.get(venue_int, str(venue_int))
        v_df = hit_df[hit_df['venue_int'] == venue_int]
        n = len(v_df)

        if n < 10:
            print(f"\n{name}(会場{venue_int:02d}): {n}件 → サンプル不足のためスキップ")
            continue

        print(f"\n{name}(会場{venue_int:02d}): {n}件")
        observed = [v_df[v_df['actual_3rd'] == c].shape[0] for c in range(1, 7)]
        expected = [n / 6.0] * 6

        chi2, p_value = scipy_stats.chisquare(observed, f_exp=expected)
        sig = "★有意(p<0.05)" if p_value < 0.05 else "n.s."
        print(f"  カイ二乗検定: chi2={chi2:.2f}, p={p_value:.3f}  {sig}")
        print(f"  {'コース':>4} | {'件数':>4} | {'実際%':>7} | {'期待%':>7} | {'偏差':>6}")
        print(f"  {'----':>4}-+-{'----':>4}-+-{'-------':>7}-+-{'-------':>7}-+-{'------':>6}")
        for i, c in enumerate(range(1, 7)):
            cnt = observed[i]
            pct = cnt / n * 100
            exp_pct = 100 / 6
            diff = pct - exp_pct
            mark = " <--" if abs(diff) > 10 else ""
            print(f"  {c}コース | {cnt:>4} | {pct:>6.1f}% | {exp_pct:>6.1f}% | {diff:>+5.1f}%{mark}")

        venue_results[venue_int] = {'name': name, 'n': n, 'chi2': chi2, 'p': p_value,
                                    'dist': dict(zip(range(1,7), observed))}

    # 有意なパターンのサマリー
    sig_venues = {k: v for k, v in venue_results.items() if v['p'] < 0.05}
    print()
    if sig_venues:
        print("【有意なパターン（p<0.05）】")
        for vc, res in sig_venues.items():
            total = sum(res['dist'].values())
            print(f"  {res['name']}: n={res['n']}, p={res['p']:.3f}")
            for c, cnt in res['dist'].items():
                diff = cnt/total*100 - 100/6
                if abs(diff) > 10:
                    direction = "多い" if diff > 0 else "少ない"
                    print(f"    → {c}コースが{direction} ({cnt/total*100:.1f}% vs 期待{100/6:.1f}%)")
    else:
        print("【有意なパターンなし】（全会場 p>=0.05）")

    print()
    n_tests = len(venue_results) * 6
    print(f"多重比較: {len(venue_results)}会場 x 6コース = {n_tests}回検定")
    print(f"偽陽性期待数 = {n_tests} x 0.05 = {n_tests*0.05:.1f}件")
    bonferroni = 0.05 / n_tests if n_tests > 0 else 0.05
    print(f"Bonferroni補正後の有意水準 = {bonferroni:.4f}")

    return venue_results


def print_summary(df):
    """バックテスト再現確認（件数・収支がバックテストと一致するか）"""
    print("\n" + "="*60)
    print("【バックテスト再現確認】")
    print("="*60)

    bet_df = df[df['is_bet']].copy()
    investment = (bet_df['bet_p3'] + bet_df['bet_p4']).sum()
    payout_p3 = (bet_df['p3_hit'] * bet_df['odds_p3'] * bet_df['bet_p3']).sum()
    payout_p4 = (bet_df['p4_hit'] * bet_df['odds_p4'] * bet_df['bet_p4']).sum()
    payout = payout_p3 + payout_p4
    hits = bet_df['any_hit'].sum()
    roi = payout / investment * 100 if investment > 0 else 0
    profit = payout - investment

    print(f"投資レース数: {len(bet_df)}件")
    print(f"的中数:       {hits}件 ({hits/len(bet_df)*100:.1f}%)")
    print(f"投資総額:     {investment:,}円")
    print(f"払戻総額:     {payout:,}円")
    print(f"ROI:          {roi:.1f}%")
    print(f"収支:         {profit:+,}円")
    print()
    print("※ バックテスト(v2.48.0): 480件/ROI 200.1%/+73,660円 と比較してください")
    print("  （注: バックテストはunique重複除外あり・こちらは単独条件）")


def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("=" * 60)
    print("3着候補選択の改善分析 v2")
    print("対象条件: B×A1×30-50×8会場（2020-2025）")
    print("=" * 60)

    # 条件定義を取得
    cond = get_condition()
    print(f"条件ID: {cond['id']}")
    print(f"条件名: {cond['name']}")

    # バックテストと同じ方法でレースIDを取得
    print("\nget_race_ids_for_condition でレースID取得中...")
    race_ids = get_race_ids_for_condition(
        cursor, cond,
        start_date='2020-01-01',
        end_date='2026-01-01'
    )
    print(f"  取得レース数: {len(race_ids)}件")

    if len(race_ids) == 0:
        print("ERROR: レースが取得できませんでした")
        conn.close()
        return

    # 分析用データを取得
    print("分析用データを取得中...")
    df = load_race_data(conn, race_ids)
    print(f"  データ取得件数: {len(df)}件")

    if len(df) == 0:
        print("ERROR: データが取得できませんでした")
        conn.close()
        return

    # 派生カラムを追加
    df = add_derived_columns(df, cond)

    # バックテスト再現確認
    print_summary(df)

    # 各案の分析
    analyze_case_a(df)
    analyze_case_b(df)
    analyze_case_c(df)
    analyze_case_d(df)

    conn.close()
    print("\n分析完了")


if __name__ == '__main__':
    main()
