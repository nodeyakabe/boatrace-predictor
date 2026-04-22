# -*- coding: utf-8 -*-
"""
候補1: p1-p4-p2 × 100倍〜 × 信頼度A 的中レース深掘り分析
的中28件 vs 非的中3,068件の共通点・条件を探す
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import os
import sqlite3
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

DB_PATH = os.path.join(PROJECT_ROOT, "data/boatrace.db")

VENUE_NAMES = {
    1:'桐生', 2:'戸田', 3:'江戸川', 4:'平和島', 5:'多摩川', 6:'浜名湖',
    7:'蒲郡', 8:'常滑', 9:'津', 10:'三国', 11:'びわこ', 12:'住之江',
    13:'尼崎', 14:'鳴門', 15:'丸亀', 16:'児島', 17:'宮島', 18:'徳山',
    19:'下関', 20:'若松', 21:'芦屋', 22:'福岡', 23:'唐津', 24:'大村'
}


def load_data(conn):
    query = """
    SELECT
        r.id AS race_id,
        r.race_date,
        r.venue_code,
        r.race_number,
        CAST(SUBSTR(r.race_date, 1, 4) AS INTEGER) AS year,
        CAST(SUBSTR(r.race_date, 6, 2) AS INTEGER) AS month,
        r.race_grade,
        rp1.pit_number AS p1,
        rp2.pit_number AS p2,
        rp3.pit_number AS p3,
        rp4.pit_number AS p4,
        rp1.confidence AS confidence,
        rp1.total_score AS p1_score,
        t.odds AS odds,
        e1.racer_rank AS c1_rank,
        e1.win_rate AS c1_win_rate,
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') AS actual_1st,
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') AS actual_2nd,
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') AS actual_3rd
    FROM races r
    JOIN race_predictions rp1 ON r.id = rp1.race_id
        AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id
        AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp3 ON r.id = rp3.race_id
        AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
    JOIN race_predictions rp4 ON r.id = rp4.race_id
        AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
    JOIN trifecta_odds t ON r.id = t.race_id
        AND t.combination = CAST(rp1.pit_number AS TEXT) || '-'
                         || CAST(rp4.pit_number AS TEXT) || '-'
                         || CAST(rp2.pit_number AS TEXT)
    LEFT JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
    WHERE rp1.confidence = 'A'
      AND t.odds >= 100
      AND r.race_date >= '2020-01-01'
      AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') IS NOT NULL
      AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') IS NOT NULL
    ORDER BY r.race_date
    """
    df = pd.read_sql_query(query, conn)
    df['hit'] = (
        (df['actual_1st'] == df['p1']) &
        (df['actual_2nd'] == df['p4']) &
        (df['actual_3rd'] == df['p2'])
    )
    df['venue_code'] = df['venue_code'].astype(int)
    df['venue_name'] = df['venue_code'].map(VENUE_NAMES).fillna('不明')
    return df


def print_comparison(label, df, group_col, display_col=None, top_n=None, sort_col='ROI'):
    """グループ別 的中率・ROI比較"""
    if display_col is None:
        display_col = group_col

    rows = []
    for val, sub in df.groupby(group_col, observed=True):
        n = len(sub)
        if n == 0:
            continue
        h = int(sub['hit'].sum())
        pay = float((sub['hit'] * sub['odds'] * 100).sum())
        inv = n * 100
        roi = pay / inv * 100 if inv > 0 else 0.0
        profit = int(pay - inv)
        rows.append({'key': val, '件数': n, '的中': h,
                     '的中率': h / n * 100, 'ROI': roi, '収支': profit})

    if not rows:
        print(f"  (データなし)")
        return
    result = pd.DataFrame(rows).sort_values(sort_col, ascending=False)
    if top_n:
        result = result.head(top_n)

    print(f"\n{'='*70}")
    print(f"【{label}】")
    print(f"{'='*70}")
    print(f"  {'項目':>10} | {'件数':>5} | {'的中':>4} | {'的中率':>6} | {'ROI':>7} | {'収支':>10}")
    print(f"  {'-'*58}")
    for _, row in result.iterrows():
        mark = '★' if row['ROI'] >= 100 else ''
        print(f"  {str(row['key']):>10} | {int(row['件数']):>5} | {int(row['的中']):>4} | "
              f"{row['的中率']:>5.1f}% | {row['ROI']:>6.1f}%{mark} | {int(row['収支']):>+10,}円")

    # 全体との比較
    total_n = len(df)
    total_h = int(df['hit'].sum())
    total_roi = float((df['hit'] * df['odds'] * 100).sum()) / (total_n * 100) * 100
    print(f"  {'[全体]':>10} | {total_n:>5} | {total_h:>4} | "
          f"{total_h/total_n*100:>5.1f}% | {total_roi:>6.1f}% | -")


def main():
    conn = sqlite3.connect(DB_PATH)

    print("="*70)
    print("候補1: p1-p4-p2 × 100倍〜 × 信頼度A  的中パターン深掘り分析")
    print("="*70)

    print("\nデータ取得中...")
    df = load_data(conn)
    hits = df[df['hit']]
    print(f"  総対象: {len(df):,}件  /  的中: {len(hits)}件  /  的中率: {len(hits)/len(df)*100:.2f}%")
    print(f"  IS(2020-22): {(df['year']<=2022).sum():,}件  /  OOS(2023-25): {(df['year']>=2023).sum():,}件")

    # ================================================================
    # Part 1: 会場別
    # ================================================================
    df['venue_label'] = df['venue_code'].astype(str) + ':' + df['venue_name']
    print_comparison("Part 1: 会場別 的中率・ROI（ROI降順）", df, 'venue_label', top_n=None)

    # ================================================================
    # Part 2: 月別
    # ================================================================
    print_comparison("Part 2: 月別 的中率・ROI", df, 'month')

    # ================================================================
    # Part 3: 1コース選手ランク別
    # ================================================================
    df['c1_rank_g'] = df['c1_rank'].fillna('不明')
    print_comparison("Part 3: 1コース選手ランク別", df, 'c1_rank_g', sort_col='的中率')

    # ================================================================
    # Part 4: オッズ帯（100倍〜の内訳）
    # ================================================================
    bins = [100, 150, 200, 300, 500, 10000]
    labels = ['100-150', '150-200', '200-300', '300-500', '500+']
    df['odds_band'] = pd.cut(df['odds'], bins=bins, labels=labels, right=False)
    print_comparison("Part 4: オッズ帯別（100倍〜の内訳）", df, 'odds_band')

    # ================================================================
    # Part 5: p1の枠番別
    # ================================================================
    print_comparison("Part 5: p1枠番別（1着予測の実際の枠）", df, 'p1', sort_col='ROI')

    # ================================================================
    # Part 6: p4の枠番別（2着に来る予測4位の枠）
    # ================================================================
    print_comparison("Part 6: p4枠番別（2着買い目の実際の枠）", df, 'p4', sort_col='ROI')

    # ================================================================
    # Part 7: レース番号別
    # ================================================================
    print_comparison("Part 7: レース番号別（1〜12レース）", df, 'race_number', sort_col='ROI')

    # ================================================================
    # Part 8: p1スコア帯別（信頼度内のスコア分布）
    # ================================================================
    df['score_band'] = pd.cut(df['p1_score'],
                               bins=[0, 50, 60, 70, 80, 90, 200],
                               labels=['〜50','50-60','60-70','70-80','80-90','90+'],
                               right=False)
    print_comparison("Part 8: p1スコア帯別", df, 'score_band', sort_col='ROI')

    # ================================================================
    # Part 9: advance-before一致フィルタ効果
    # ================================================================
    print(f"\n{'='*70}")
    print("【Part 9】advance-before 上位3艇一致フィルタ効果")
    print(f"{'='*70}")

    race_ids = df['race_id'].tolist()
    # advance予測の上位3艇pit番号を取得
    id_str = ','.join(str(x) for x in race_ids)
    adv_df = pd.read_sql_query(f"""
        SELECT race_id,
               GROUP_CONCAT(pit_number ORDER BY rank_prediction) AS adv_pits
        FROM race_predictions
        WHERE prediction_type = 'advance'
          AND rank_prediction <= 3
          AND race_id IN ({id_str})
        GROUP BY race_id
        HAVING COUNT(*) = 3
    """, conn)

    bef_top3 = df[['race_id', 'p1', 'p2', 'p3']].copy()
    merged = bef_top3.merge(adv_df, on='race_id', how='left')

    def is_match(row):
        if pd.isna(row['adv_pits']):
            return False
        adv_set = set(int(x) for x in str(row['adv_pits']).split(','))
        bef_set = {int(row['p1']), int(row['p2']), int(row['p3'])}
        return adv_set == bef_set

    merged['ab_match'] = merged.apply(is_match, axis=1)
    df = df.merge(merged[['race_id', 'ab_match']], on='race_id', how='left')
    df['ab_match'] = df['ab_match'].fillna(False)

    for match, label in [(True, 'advance一致（上位3艇同じ）'), (False, 'advance不一致')]:
        sub = df[df['ab_match'] == match]
        if len(sub) == 0:
            continue
        n = len(sub); h = int(sub['hit'].sum())
        pay = float((sub['hit'] * sub['odds'] * 100).sum()); inv = n * 100
        roi = pay / inv * 100 if inv > 0 else 0
        profit = int(pay - inv)
        mark = '★' if roi >= 100 else ''
        print(f"  {label}: {n:>5}件 / {h:>3}的中 / {h/n*100:.2f}% / ROI {roi:.1f}%{mark} / {profit:>+10,}円")

    # ================================================================
    # Part 10: IS/OOS 別会場ランキング比較
    # ================================================================
    print(f"\n{'='*70}")
    print("【Part 10】IS vs OOS 会場別 ROI比較（安定性チェック）")
    print(f"{'='*70}")
    print(f"  {'会場':>12} | IS件数 | IS ROI |  IS収支 | OOS件数 | OOS ROI | OOS収支 | 判定")
    print(f"  {'-'*80}")

    df_is = df[df['year'] <= 2022]
    df_oos = df[df['year'] >= 2023]

    venue_list = sorted(df['venue_code'].unique())
    rows = []
    for v in venue_list:
        sub_is = df_is[df_is['venue_code'] == v]
        sub_oos = df_oos[df_oos['venue_code'] == v]
        if len(sub_is) == 0 and len(sub_oos) == 0:
            continue

        def calc(sub):
            n = len(sub); h = int(sub['hit'].sum())
            pay = float((sub['hit'] * sub['odds'] * 100).sum()); inv = n * 100
            roi = pay / inv * 100 if inv > 0 else 0
            profit = int(pay - inv)
            return n, h, roi, profit

        ni, hi, roi_i, pr_i = calc(sub_is)
        no, ho, roi_o, pr_o = calc(sub_oos)
        rows.append({'v': v, 'ni': ni, 'roi_i': roi_i, 'pr_i': pr_i,
                     'no': no, 'roi_o': roi_o, 'pr_o': pr_o,
                     'oos_roi': roi_o})

    rows.sort(key=lambda x: x['oos_roi'], reverse=True)
    for row in rows:
        name = VENUE_NAMES.get(row['v'], str(row['v']))
        both_ok = '◎' if row['roi_i'] >= 100 and row['roi_o'] >= 100 else \
                  '○IS' if row['roi_i'] >= 100 else \
                  '○OOS' if row['roi_o'] >= 100 else '×'
        mi = '★' if row['roi_i'] >= 100 else ''
        mo = '★' if row['roi_o'] >= 100 else ''
        print(f"  {str(row['v'])+':'+name:>12} | {row['ni']:>6} | {row['roi_i']:>5.0f}%{mi} | {row['pr_i']:>+8,} | "
              f"{row['no']:>7} | {row['roi_o']:>6.0f}%{mo} | {row['pr_o']:>+8,} | {both_ok}")

    # ================================================================
    # Part 11: 的中28件の詳細リスト
    # ================================================================
    print(f"\n{'='*70}")
    print("【Part 11】的中全件 詳細リスト")
    print(f"{'='*70}")
    print(f"  {'日付':>10} | {'会場':>6} | {'R':>2} | {'odds':>7} | {'組み合わせ':>10} | {'p1スコア':>8}")
    print(f"  {'-'*65}")
    for _, row in hits.sort_values('race_date').iterrows():
        vname = VENUE_NAMES.get(int(row['venue_code']), str(int(row['venue_code'])))
        combo = f"{int(row['p1'])}-{int(row['p4'])}-{int(row['p2'])}"
        print(f"  {row['race_date']:>10} | {vname:>6} | {int(row['race_number']):>2}R | "
              f"{row['odds']:>7.1f}倍 | {combo:>10} | スコア:{row['p1_score']:.1f}")

    # ================================================================
    # Part 12: 多変量スクリーニング（◎会場 × ◎月の組み合わせ）
    # ================================================================
    print(f"\n{'='*70}")
    print("【Part 12】複合条件スクリーニング（OOS ROI上位の組み合わせ）")
    print(f"{'='*70}")

    # OOSで黒字の会場を特定
    oos_good_venues = []
    for row in rows:
        if row['roi_o'] >= 100:
            oos_good_venues.append(row['v'])

    if oos_good_venues:
        print(f"\n  OOS黒字会場 ({len(oos_good_venues)}会場): {oos_good_venues}")
        sub = df[df['venue_code'].isin(oos_good_venues)]
        n = len(sub); h = int(sub['hit'].sum())
        pay = float((sub['hit'] * sub['odds'] * 100).sum()); inv = n * 100
        roi = pay / inv * 100 if inv > 0 else 0
        profit = int(pay - inv)
        mark = '★' if roi >= 100 else ''
        print(f"  合計: {n:,}件 / {h}的中 / ROI {roi:.1f}%{mark} / {profit:>+,}円")

        # IS/OOS分割
        sub_is = sub[sub['year'] <= 2022]
        sub_oos = sub[sub['year'] >= 2023]
        for period, s in [('IS', sub_is), ('OOS', sub_oos)]:
            nn = len(s); hh = int(s['hit'].sum())
            pp = float((s['hit'] * s['odds'] * 100).sum()); ii = nn * 100
            rr = pp / ii * 100 if ii > 0 else 0
            pr = int(pp - ii)
            mk = '★' if rr >= 100 else ''
            print(f"  {period}: {nn:>4}件 / {hh}的中 / ROI {rr:.1f}%{mk} / {pr:>+,}円")

    # OOS黒字会場 × advance一致
    if oos_good_venues and 'ab_match' in df.columns:
        sub2 = df[df['venue_code'].isin(oos_good_venues) & df['ab_match']]
        if len(sub2) > 0:
            n = len(sub2); h = int(sub2['hit'].sum())
            pay = float((sub2['hit'] * sub2['odds'] * 100).sum()); inv = n * 100
            roi = pay / inv * 100 if inv > 0 else 0
            profit = int(pay - inv)
            mark = '★' if roi >= 100 else ''
            sub2_oos = sub2[sub2['year'] >= 2023]
            no = len(sub2_oos); ho = int(sub2_oos['hit'].sum())
            payo = float((sub2_oos['hit'] * sub2_oos['odds'] * 100).sum()); invo = no * 100
            roio = payo / invo * 100 if invo > 0 else 0
            profito = int(payo - invo)
            marko = '★' if roio >= 100 else ''
            print(f"\n  OOS黒字会場 × advance一致: 全体 {n}件/ROI {roi:.1f}%{mark}/{profit:>+,}円  OOS {no}件/ROI {roio:.1f}%{marko}/{profito:>+,}円")

    conn.close()
    print("\n完了")


if __name__ == '__main__':
    main()
