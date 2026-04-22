# -*- coding: utf-8 -*-
"""
三連単 全組み合わせ分析

p1（1着予測）固定・p2〜p5を2着3着に使う12通りの組み合わせについて
「100円ずつ毎回購入した場合の的中率・ROI・収支」をIS/OOS比較する

目的: 現行パターンH2（p1-p2-p3 + p1-p2-p4）がベストか再検証し
     最も収支が出る組み合わせの傾向を把握する

使い方:
  TARGET_CONFIDENCE = ['A', 'B']  → 信頼度B以上
  TARGET_CONFIDENCE = ['C', 'D']  → 信頼度B未満
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

# ============================================================
# 設定（コマンドライン引数で上書き可能）
# ============================================================
import argparse
_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument('--conf', default='AB', choices=['AB', 'CD', 'ALL'])
_args, _ = _parser.parse_known_args()

if _args.conf == 'AB':
    TARGET_CONFIDENCE = ['A', 'B']   # B以上
elif _args.conf == 'CD':
    TARGET_CONFIDENCE = ['C', 'D']   # B未満
else:
    TARGET_CONFIDENCE = ['A', 'B', 'C', 'D']  # 全レース

# IS/OOS期間
IS_START  = '2020-01-01'
IS_END    = '2022-12-31'
OOS_START = '2023-01-01'
OOS_END   = '2025-12-31'

# 12通りの組み合わせ定義 (ラベル, 2着予測列, 3着予測列)
COMBINATIONS = [
    ('p1-p2-p3', 'p2', 'p3'),
    ('p1-p2-p4', 'p2', 'p4'),
    ('p1-p2-p5', 'p2', 'p5'),
    ('p1-p3-p2', 'p3', 'p2'),
    ('p1-p3-p4', 'p3', 'p4'),
    ('p1-p3-p5', 'p3', 'p5'),
    ('p1-p4-p2', 'p4', 'p2'),
    ('p1-p4-p3', 'p4', 'p3'),
    ('p1-p4-p5', 'p4', 'p5'),
    ('p1-p5-p2', 'p5', 'p2'),
    ('p1-p5-p3', 'p5', 'p3'),
    ('p1-p5-p4', 'p5', 'p4'),
]


def load_race_data(conn, confidence_list, start_date, end_date):
    """対象期間・信頼度のレースデータを取得"""
    conf_in = ','.join(f"'{c}'" for c in confidence_list)
    query = f"""
    SELECT
        r.id          AS race_id,
        r.race_date,
        r.venue_code,
        rp1.pit_number AS p1,
        rp2.pit_number AS p2,
        rp3.pit_number AS p3,
        rp4.pit_number AS p4,
        rp5.pit_number AS p5,
        rp1.confidence AS confidence,
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') AS actual_1st,
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') AS actual_2nd,
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') AS actual_3rd
    FROM races r
    JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
    JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
    JOIN race_predictions rp5 ON r.id = rp5.race_id AND rp5.prediction_type = 'before' AND rp5.rank_prediction = 5
    WHERE r.race_date >= '{start_date}'
      AND r.race_date <= '{end_date}'
      AND rp1.confidence IN ({conf_in})
      AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') IS NOT NULL
      AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') IS NOT NULL
    ORDER BY r.race_date
    """
    return pd.read_sql_query(query, conn)


def load_odds(conn, race_ids):
    """対象レースの三連単オッズを一括取得"""
    if len(race_ids) == 0:
        return pd.DataFrame(columns=['race_id', 'combination', 'odds'])

    conn.execute("DROP TABLE IF EXISTS _ca_race_ids")
    conn.execute("CREATE TEMP TABLE _ca_race_ids (race_id INTEGER PRIMARY KEY)")
    conn.executemany("INSERT INTO _ca_race_ids VALUES (?)", [(int(rid),) for rid in race_ids])

    query = """
    SELECT o.race_id, o.combination, o.odds
    FROM trifecta_odds o
    JOIN _ca_race_ids t ON t.race_id = o.race_id
    WHERE o.odds > 0
    """
    return pd.read_sql_query(query, conn)


def analyze_combinations(df_base, df_odds):
    """12通りの組み合わせを一括分析（ベクトル化）"""
    results = []

    for combo_label, col_2nd, col_3rd in COMBINATIONS:
        # 買い目キー列を作成
        df_work = df_base[['race_id', 'p1', col_2nd, col_3rd,
                             'actual_1st', 'actual_2nd', 'actual_3rd']].copy()
        df_work.columns = ['race_id', 'p1', 'p_2nd', 'p_3rd',
                            'actual_1st', 'actual_2nd', 'actual_3rd']
        df_work['combination'] = (
            df_work['p1'].astype(str) + '-' +
            df_work['p_2nd'].astype(str) + '-' +
            df_work['p_3rd'].astype(str)
        )

        # オッズとマージ（オッズのないレースは除外）
        merged = df_work.merge(df_odds[['race_id', 'combination', 'odds']],
                                on=['race_id', 'combination'], how='inner')

        if len(merged) == 0:
            results.append({
                'combination': combo_label,
                'n_races': 0, 'n_hits': 0, 'hit_rate': 0,
                'investment': 0, 'payout': 0, 'profit': 0, 'roi': 0,
            })
            continue

        # 的中フラグ
        merged['hit'] = (
            (merged['actual_1st'] == merged['p1']) &
            (merged['actual_2nd'] == merged['p_2nd']) &
            (merged['actual_3rd'] == merged['p_3rd'])
        )

        n      = len(merged)
        hits   = int(merged['hit'].sum())
        payout = float((merged['hit'] * merged['odds'] * 100).sum())
        inv    = n * 100

        results.append({
            'combination': combo_label,
            'n_races':   n,
            'n_hits':    hits,
            'hit_rate':  hits / n * 100,
            'investment': inv,
            'payout':    int(payout),
            'profit':    int(payout - inv),
            'roi':       payout / inv * 100 if inv > 0 else 0,
        })

    return pd.DataFrame(results)


def print_table(df_res, title):
    print(f"\n{'='*78}")
    print(f"【{title}】")
    print(f"{'='*78}")
    print(f"  {'組み合わせ':<12} | {'件数':>7} | {'的中':>5} | {'的中率':>6} | {'ROI':>7} | {'収支':>11}")
    print(f"  {'-'*68}")
    for _, row in df_res.sort_values('profit', ascending=False).iterrows():
        mark = '★' if row['roi'] >= 100 else ('  ' if row['roi'] < 100 else '')
        print(f"  {row['combination']:<12} | {row['n_races']:>7,} | {row['n_hits']:>5} | "
              f"{row['hit_rate']:>5.2f}% | {row['roi']:>6.1f}% | {row['profit']:>+10,}円 {mark}")


def print_is_oos_comparison(res_is, res_oos):
    print(f"\n{'='*78}")
    print("【IS/OOS 安定性比較（ROI）】")
    print("IS=2020-2022探索期間 / OOS=2023-2025検証期間")
    print(f"{'='*78}")
    print(f"  {'組み合わせ':<12} | {'IS ROI':>8} | {'IS収支':>10} | {'OOS ROI':>8} | {'OOS収支':>10} | 判定")
    print(f"  {'-'*72}")

    merged = res_is[['combination', 'roi', 'profit']].merge(
        res_oos[['combination', 'roi', 'profit']],
        on='combination', suffixes=('_is', '_oos')
    )
    merged = merged.sort_values('profit_oos', ascending=False)

    for _, row in merged.iterrows():
        is_pos  = row['roi_is']  >= 100
        oos_pos = row['roi_oos'] >= 100
        if is_pos and oos_pos:
            judge = '◎ 両期間+'
        elif oos_pos:
            judge = '○ OOS+'
        elif is_pos:
            judge = '△ ISのみ+'
        else:
            judge = '× 両期間-'
        print(f"  {row['combination']:<12} | {row['roi_is']:>7.1f}% | {row['profit_is']:>+9,}円 | "
              f"{row['roi_oos']:>7.1f}% | {row['profit_oos']:>+9,}円 | {judge}")


def print_confidence_breakdown(df_base, df_odds):
    """信頼度A/Bを個別に表示（B以上の場合のみ有用）"""
    for conf in sorted(df_base['confidence'].unique()):
        df_c = df_base[df_base['confidence'] == conf]
        race_ids_c = set(df_c['race_id'])
        df_odds_c = df_odds[df_odds['race_id'].isin(race_ids_c)]
        res_c = analyze_combinations(df_c, df_odds_c)

        top3 = res_c.sort_values('profit', ascending=False).head(3)
        print(f"\n  信頼度{conf}（{len(df_c):,}件）- 収支上位3組み合わせ:")
        for _, row in top3.iterrows():
            print(f"    {row['combination']:<12}: {row['n_races']:>6,}件 / ROI {row['roi']:>6.1f}% / {row['profit']:>+10,}円")


def main():
    conn = sqlite3.connect(DB_PATH)
    conf_label = 'B以上（A+B）' if 'A' in TARGET_CONFIDENCE else 'B未満（C+D）'

    print("="*78)
    print(f"三連単 全組み合わせ分析 - 信頼度{conf_label}")
    print("p1（1着予測）固定 / p2〜p5で2着3着を構成する12通り")
    print("全組み合わせ100円固定で評価（収支比較を公平に）")
    print("="*78)

    # ------------------------------------------------------------------
    # データ取得
    # ------------------------------------------------------------------
    print(f"\nIS期間データ取得中（{IS_START} 〜 {IS_END}）...")
    df_is = load_race_data(conn, TARGET_CONFIDENCE, IS_START, IS_END)
    odds_is = load_odds(conn, df_is['race_id'].unique())
    print(f"  レース数: {len(df_is):,}件  オッズデータ: {len(odds_is):,}行")

    print(f"OOS期間データ取得中（{OOS_START} 〜 {OOS_END}）...")
    df_oos = load_race_data(conn, TARGET_CONFIDENCE, OOS_START, OOS_END)
    odds_oos = load_odds(conn, df_oos['race_id'].unique())
    print(f"  レース数: {len(df_oos):,}件  オッズデータ: {len(odds_oos):,}行")

    df_all  = pd.concat([df_is, df_oos], ignore_index=True)
    odds_all = pd.concat([odds_is, odds_oos], ignore_index=True)

    # ------------------------------------------------------------------
    # 全体分析
    # ------------------------------------------------------------------
    res_is  = analyze_combinations(df_is,  odds_is)
    res_oos = analyze_combinations(df_oos, odds_oos)
    res_all = analyze_combinations(df_all, odds_all)

    print_table(res_all, f"6年間通算（2020-2025） / 信頼度{conf_label}")
    print_table(res_is,  f"IS期間（2020-2022）    / 信頼度{conf_label}")
    print_table(res_oos, f"OOS期間（2023-2025）   / 信頼度{conf_label}")

    print_is_oos_comparison(res_is, res_oos)

    # ------------------------------------------------------------------
    # 信頼度別内訳（B以上の場合: A/B個別）
    # ------------------------------------------------------------------
    if len(TARGET_CONFIDENCE) > 1:
        print(f"\n{'='*78}")
        print("【信頼度別内訳】")
        print(f"{'='*78}")
        print_confidence_breakdown(df_all, odds_all)

    # ------------------------------------------------------------------
    # 現行パターンH2との対比サマリー
    # ------------------------------------------------------------------
    print(f"\n{'='*78}")
    print("【参考: 現行パターンH2との単純比較（6年間・各100円ベース）】")
    print(f"{'='*78}")
    current = res_all[res_all['combination'].isin(['p1-p2-p3', 'p1-p2-p4'])]
    for _, row in current.iterrows():
        print(f"  {row['combination']}: {row['n_races']:,}件 / ROI {row['roi']:.1f}% / {row['profit']:+,}円")
    combo_total_inv  = current['investment'].sum()
    combo_total_pay  = current['payout'].sum()
    combo_total_prof = int(combo_total_pay - combo_total_inv)
    combo_roi        = combo_total_pay / combo_total_inv * 100 if combo_total_inv > 0 else 0
    print(f"  合算（H2相当）: 投資{combo_total_inv:,}円 / ROI {combo_roi:.1f}% / {combo_total_prof:+,}円")

    conn.close()
    print("\n完了")


if __name__ == '__main__':
    main()
