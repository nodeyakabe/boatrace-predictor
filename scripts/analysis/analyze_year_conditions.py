# -*- coding: utf-8 -*-
"""
年度別・信頼度別・オッズ帯別の購入条件最適化分析

2024年と2025年の両方でプラス収益になる購入条件を探索する
"""

import sqlite3
import pandas as pd
import numpy as np
from collections import defaultdict
from datetime import datetime

DB_PATH = 'data/boatrace.db'

def get_connection():
    return sqlite3.connect(DB_PATH)

def load_all_data():
    """全データを効率的にロード"""
    conn = get_connection()

    # 予測データ（事前予測のみ）
    pred_query = """
    SELECT
        rac.race_date,
        rac.venue_code,
        rac.race_number,
        p.race_id,
        p.confidence,
        p.rank_prediction,
        p.pit_number
    FROM race_predictions p
    JOIN races rac ON p.race_id = rac.id
    WHERE rac.race_date >= '2024-01-01'
        AND p.prediction_type = 'advance'
    ORDER BY p.race_id, p.rank_prediction
    """
    pred_df = pd.read_sql_query(pred_query, conn)

    # 結果データ（1着〜3着）
    result_query = """
    SELECT
        r.race_id,
        r.pit_number,
        r.rank
    FROM results r
    JOIN races rac ON r.race_id = rac.id
    WHERE rac.race_date >= '2024-01-01'
        AND r.rank IN ('1', '2', '3')
    """
    result_df = pd.read_sql_query(result_query, conn)

    # オッズデータ（trifecta_odds テーブルから）
    odds_query = """
    SELECT
        t.race_id,
        t.combination,
        t.odds
    FROM trifecta_odds t
    JOIN races rac ON t.race_id = rac.id
    WHERE rac.race_date >= '2024-01-01'
    """
    odds_df = pd.read_sql_query(odds_query, conn)

    # 1コース選手の級別
    entry_query = """
    SELECT
        e.race_id,
        e.racer_rank
    FROM entries e
    JOIN races rac ON e.race_id = rac.id
    WHERE e.pit_number = 1
        AND rac.race_date >= '2024-01-01'
    """
    entry_df = pd.read_sql_query(entry_query, conn)

    conn.close()

    return pred_df, result_df, odds_df, entry_df

def process_data(pred_df, result_df, odds_df, entry_df):
    """データを処理して分析用のDataFrameを作成"""

    # 予測データをピボット（1レース1行）
    predictions = []
    for race_id, group in pred_df.groupby('race_id'):
        first_row = group.iloc[0]
        sorted_group = group.sort_values('rank_prediction')
        if len(sorted_group) >= 3:
            pred_1st = int(sorted_group.iloc[0]['pit_number'])
            pred_2nd = int(sorted_group.iloc[1]['pit_number'])
            pred_3rd = int(sorted_group.iloc[2]['pit_number'])

            predictions.append({
                'race_id': race_id,
                'race_date': first_row['race_date'],
                'venue_code': first_row['venue_code'],
                'race_number': first_row['race_number'],
                'confidence': first_row['confidence'],
                'pred_1st': pred_1st,
                'pred_2nd': pred_2nd,
                'pred_3rd': pred_3rd,
                'pred_combo': f"{pred_1st}-{pred_2nd}-{pred_3rd}"
            })

    pred_pivot = pd.DataFrame(predictions)
    print(f"予測レース: {len(pred_pivot):,} 件")

    # 結果データをピボット（1レース1行）
    results = []
    for race_id, group in result_df.groupby('race_id'):
        first = group[group['rank'] == '1']
        second = group[group['rank'] == '2']
        third = group[group['rank'] == '3']

        if len(first) == 1 and len(second) == 1 and len(third) == 1:
            result_1st = int(first.iloc[0]['pit_number'])
            result_2nd = int(second.iloc[0]['pit_number'])
            result_3rd = int(third.iloc[0]['pit_number'])

            results.append({
                'race_id': race_id,
                'result_1st': result_1st,
                'result_2nd': result_2nd,
                'result_3rd': result_3rd,
                'result_combo': f"{result_1st}-{result_2nd}-{result_3rd}"
            })

    result_pivot = pd.DataFrame(results)
    print(f"結果レース: {len(result_pivot):,} 件")

    # オッズをピボット（レースID + 組み合わせで辞書化）
    odds_dict = {}
    for _, row in odds_df.iterrows():
        race_id = row['race_id']
        combo = row['combination']
        odds = row['odds']
        if race_id not in odds_dict:
            odds_dict[race_id] = {}
        odds_dict[race_id][combo] = odds

    print(f"オッズレース: {len(odds_dict):,} 件")

    # 結合
    df = pred_pivot.merge(result_pivot, on='race_id', how='inner')
    df = df.merge(entry_df, on='race_id', how='left')

    # オッズを取得
    def get_odds(row):
        race_id = row['race_id']
        result_combo = row['result_combo']
        if race_id in odds_dict and result_combo in odds_dict[race_id]:
            return odds_dict[race_id][result_combo]
        return None

    df['odds_trifecta'] = df.apply(get_odds, axis=1)

    # 予測組み合わせのオッズも取得
    def get_pred_odds(row):
        race_id = row['race_id']
        pred_combo = row['pred_combo']
        if race_id in odds_dict and pred_combo in odds_dict[race_id]:
            return odds_dict[race_id][pred_combo]
        return None

    df['pred_odds'] = df.apply(get_pred_odds, axis=1)

    # 加工
    df['c1_rank'] = df['racer_rank'].fillna('B1')
    df['year'] = pd.to_datetime(df['race_date']).dt.year

    # 的中フラグ
    df['is_hit'] = df['pred_combo'] == df['result_combo']

    # オッズがNULLまたは0のものを除外
    df = df[df['pred_odds'].notna() & (df['pred_odds'] > 0)]

    return df

def analyze_by_conditions(df, year):
    """年度別・条件別の分析"""
    results = []

    year_df = df[df['year'] == year].copy()

    # 信頼度別
    for conf in ['A', 'B', 'C', 'D']:
        conf_df = year_df[year_df['confidence'] == conf]

        # オッズ帯別
        for odds_min, odds_max in [(10, 20), (20, 30), (30, 40), (40, 50), (50, 100), (100, 200)]:
            odds_df = conf_df[(conf_df['pred_odds'] >= odds_min) &
                              (conf_df['pred_odds'] < odds_max)]

            if len(odds_df) < 5:
                continue

            # 的中判定
            hits = odds_df[odds_df['is_hit'] == True]

            hit_count = len(hits)
            total = len(odds_df)
            hit_rate = hit_count / total * 100 if total > 0 else 0

            investment = total * 100
            payout = hits['pred_odds'].sum() * 100
            profit = payout - investment
            roi = payout / investment * 100 if investment > 0 else 0

            results.append({
                'year': year,
                'confidence': conf,
                'odds_range': f'{odds_min}-{odds_max}',
                'total': total,
                'hits': hit_count,
                'hit_rate': hit_rate,
                'investment': investment,
                'payout': payout,
                'profit': profit,
                'roi': roi
            })

    return results

def analyze_by_rank_and_conditions(df, year):
    """年度別・級別・条件別の分析"""
    results = []

    year_df = df[df['year'] == year].copy()

    # 信頼度別
    for conf in ['A', 'B', 'C', 'D']:
        conf_df = year_df[year_df['confidence'] == conf]

        # 級別
        for rank in ['A1', 'A2', 'B1', 'B2']:
            rank_df = conf_df[conf_df['c1_rank'] == rank]

            # オッズ帯別
            for odds_min, odds_max in [(10, 20), (20, 30), (30, 40), (40, 50), (50, 100)]:
                odds_df = rank_df[(rank_df['pred_odds'] >= odds_min) &
                                  (rank_df['pred_odds'] < odds_max)]

                if len(odds_df) < 3:
                    continue

                # 的中判定
                hits = odds_df[odds_df['is_hit'] == True]

                hit_count = len(hits)
                total = len(odds_df)
                hit_rate = hit_count / total * 100 if total > 0 else 0

                investment = total * 100
                payout = hits['pred_odds'].sum() * 100
                profit = payout - investment
                roi = payout / investment * 100 if investment > 0 else 0

                results.append({
                    'year': year,
                    'confidence': conf,
                    'c1_rank': rank,
                    'odds_range': f'{odds_min}-{odds_max}',
                    'total': total,
                    'hits': hit_count,
                    'hit_rate': hit_rate,
                    'investment': investment,
                    'payout': payout,
                    'profit': profit,
                    'roi': roi
                })

    return results

def find_profitable_conditions(df):
    """両年度で利益が出る条件を探索"""

    results_2024 = analyze_by_rank_and_conditions(df, 2024)
    results_2025 = analyze_by_rank_and_conditions(df, 2025)

    # DataFrameに変換
    df_2024 = pd.DataFrame(results_2024)
    df_2025 = pd.DataFrame(results_2025)

    # 条件キーでマージ
    if len(df_2024) > 0 and len(df_2025) > 0:
        merged = df_2024.merge(df_2025,
                               on=['confidence', 'c1_rank', 'odds_range'],
                               suffixes=('_2024', '_2025'))

        # 両年度でROI >= 100% かつ サンプル >= 5 の条件を抽出
        profitable = merged[
            (merged['roi_2024'] >= 100) &
            (merged['roi_2025'] >= 100) &
            (merged['total_2024'] >= 5) &
            (merged['total_2025'] >= 5)
        ]

        return profitable, merged

    return pd.DataFrame(), pd.DataFrame()

def main():
    print("=" * 80)
    print("年度別・条件別購入条件最適化分析")
    print("=" * 80)

    # データロード
    print("\n[データロード中...]")
    pred_df, result_df, odds_df, entry_df = load_all_data()

    print(f"予測データ: {len(pred_df):,} 件")
    print(f"結果データ: {len(result_df):,} 件")
    print(f"オッズデータ: {len(odds_df):,} 件")
    print(f"エントリー: {len(entry_df):,} 件")

    # データ処理
    print("\n[データ変換中...]")
    df = process_data(pred_df, result_df, odds_df, entry_df)

    print(f"\n分析対象: {len(df):,} レース")
    print(f"  - 2024年: {len(df[df['year'] == 2024]):,} レース")
    print(f"  - 2025年: {len(df[df['year'] == 2025]):,} レース")

    # 全体統計
    print("\n[全体統計]")
    for year in [2024, 2025]:
        year_df = df[df['year'] == year]
        hits = year_df[year_df['is_hit'] == True]
        investment = len(year_df) * 100
        payout = hits['pred_odds'].sum() * 100
        roi = payout / investment * 100 if investment > 0 else 0
        print(f"  {year}年: {len(year_df)}件, 的中{len(hits)}件 ({len(hits)/len(year_df)*100:.2f}%), ROI {roi:.1f}%")

    # ==========================================
    # 1. 年度別・信頼度別・オッズ帯別の基本分析
    # ==========================================
    print("\n" + "=" * 80)
    print("1. 年度別・信頼度別・オッズ帯別 ROI分析")
    print("=" * 80)

    for year in [2024, 2025]:
        results = analyze_by_conditions(df, year)
        results_df = pd.DataFrame(results)

        print(f"\n### {year}年 ###")

        for conf in ['A', 'B', 'C', 'D']:
            conf_df = results_df[results_df['confidence'] == conf]
            if len(conf_df) == 0:
                continue

            print(f"\n【信頼度{conf}】")
            print(f"{'オッズ帯':<12} {'件数':>6} {'的中':>4} {'的中率':>8} {'ROI':>10}")
            print("-" * 48)

            for _, row in conf_df.iterrows():
                roi_str = f"{row['roi']:.1f}%"
                if row['roi'] >= 100:
                    roi_str = f"★{row['roi']:.1f}%"
                print(f"{row['odds_range']:<12} {int(row['total']):>6} {int(row['hits']):>4} {row['hit_rate']:>7.2f}% {roi_str:>10}")

    # ==========================================
    # 2. 両年度で利益が出る条件の探索
    # ==========================================
    print("\n" + "=" * 80)
    print("2. 両年度で利益が出る条件（ROI >= 100%）")
    print("=" * 80)

    profitable, merged = find_profitable_conditions(df)

    if len(profitable) > 0:
        print(f"\n両年度でROI >= 100% の条件: {len(profitable)} 件")
        print("\n" + "-" * 100)
        print(f"{'信頼度':<6} {'級別':<6} {'オッズ帯':<12} {'2024件数':>8} {'2024ROI':>10} {'2025件数':>8} {'2025ROI':>10} {'平均ROI':>10}")
        print("-" * 100)

        for _, row in profitable.sort_values('roi_2024', ascending=False).iterrows():
            avg_roi = (row['roi_2024'] + row['roi_2025']) / 2
            print(f"{row['confidence']:<6} {row['c1_rank']:<6} {row['odds_range']:<12} {int(row['total_2024']):>8} {row['roi_2024']:>9.1f}% {int(row['total_2025']):>8} {row['roi_2025']:>9.1f}% {avg_roi:>9.1f}%")
    else:
        print("\n両年度でROI >= 100% の条件は見つかりませんでした")

    # ==========================================
    # 3. 準黒字条件（片方がプラス、片方が80%以上）
    # ==========================================
    print("\n" + "=" * 80)
    print("3. 準黒字条件（片方がROI>=100%、もう片方がROI>=80%）")
    print("=" * 80)

    if len(merged) > 0:
        semi_profitable = merged[
            (((merged['roi_2024'] >= 100) & (merged['roi_2025'] >= 80)) |
             ((merged['roi_2025'] >= 100) & (merged['roi_2024'] >= 80))) &
            (merged['total_2024'] >= 5) &
            (merged['total_2025'] >= 5)
        ]

        if len(semi_profitable) > 0:
            print(f"\n準黒字条件: {len(semi_profitable)} 件")
            print("\n" + "-" * 100)
            print(f"{'信頼度':<6} {'級別':<6} {'オッズ帯':<12} {'2024件数':>8} {'2024ROI':>10} {'2025件数':>8} {'2025ROI':>10} {'平均ROI':>10}")
            print("-" * 100)

            for _, row in semi_profitable.sort_values(['roi_2024', 'roi_2025'], ascending=False).head(20).iterrows():
                avg_roi = (row['roi_2024'] + row['roi_2025']) / 2
                print(f"{row['confidence']:<6} {row['c1_rank']:<6} {row['odds_range']:<12} {int(row['total_2024']):>8} {row['roi_2024']:>9.1f}% {int(row['total_2025']):>8} {row['roi_2025']:>9.1f}% {avg_roi:>9.1f}%")
        else:
            print("\n準黒字条件は見つかりませんでした")

    # ==========================================
    # 4. 信頼度別の年度間ROI差の詳細
    # ==========================================
    print("\n" + "=" * 80)
    print("4. 信頼度別・オッズ帯別の年度間ROI差")
    print("=" * 80)

    # 信頼度 x オッズ帯の詳細比較
    results_2024 = analyze_by_conditions(df, 2024)
    results_2025 = analyze_by_conditions(df, 2025)

    df_2024 = pd.DataFrame(results_2024)
    df_2025 = pd.DataFrame(results_2025)

    if len(df_2024) > 0 and len(df_2025) > 0:
        comp = df_2024.merge(df_2025,
                             on=['confidence', 'odds_range'],
                             suffixes=('_2024', '_2025'),
                             how='outer')

        for conf in ['A', 'B', 'C', 'D']:
            conf_comp = comp[comp['confidence'] == conf]
            if len(conf_comp) == 0:
                continue

            print(f"\n【信頼度{conf}】")
            print(f"{'オッズ帯':<12} {'2024件数':>8} {'2024ROI':>10} {'2025件数':>8} {'2025ROI':>10} {'差':>10}")
            print("-" * 60)

            for _, row in conf_comp.iterrows():
                t2024 = int(row['total_2024']) if pd.notna(row['total_2024']) else 0
                t2025 = int(row['total_2025']) if pd.notna(row['total_2025']) else 0
                r2024 = row['roi_2024'] if pd.notna(row['roi_2024']) else 0
                r2025 = row['roi_2025'] if pd.notna(row['roi_2025']) else 0
                diff = r2025 - r2024
                diff_str = f"{diff:+.1f}pt"
                print(f"{row['odds_range']:<12} {t2024:>8} {r2024:>9.1f}% {t2025:>8} {r2025:>9.1f}% {diff_str:>10}")

    # ==========================================
    # 5. 2024年Cランクの詳細分析
    # ==========================================
    print("\n" + "=" * 80)
    print("5. 2024年Cランク低ROIの原因分析")
    print("=" * 80)

    c_2024 = df[(df['year'] == 2024) & (df['confidence'] == 'C')]

    if len(c_2024) > 0:
        # 級別のROI
        print("\n【Cランク × 級別】")
        for rank in ['A1', 'A2', 'B1', 'B2']:
            rank_df = c_2024[c_2024['c1_rank'] == rank]
            if len(rank_df) == 0:
                continue

            hits = rank_df[rank_df['is_hit'] == True]

            investment = len(rank_df) * 100
            payout = hits['pred_odds'].sum() * 100
            roi = payout / investment * 100 if investment > 0 else 0

            print(f"  {rank}: {len(rank_df)}件, 的中{len(hits)}件, ROI {roi:.1f}%")

        # オッズ帯別
        print("\n【Cランク × オッズ帯】")
        for odds_min, odds_max in [(10, 20), (20, 30), (30, 40), (40, 50), (50, 100)]:
            odds_df = c_2024[(c_2024['pred_odds'] >= odds_min) &
                              (c_2024['pred_odds'] < odds_max)]
            if len(odds_df) == 0:
                continue

            hits = odds_df[odds_df['is_hit'] == True]

            investment = len(odds_df) * 100
            payout = hits['pred_odds'].sum() * 100
            roi = payout / investment * 100 if investment > 0 else 0

            print(f"  {odds_min}-{odds_max}倍: {len(odds_df)}件, 的中{len(hits)}件, ROI {roi:.1f}%")
    else:
        print("2024年Cランクのデータがありません")

    # ==========================================
    # 6. 年度横断で安定した条件の特定
    # ==========================================
    print("\n" + "=" * 80)
    print("6. 年度横断で安定した条件（両年度でサンプル10件以上）")
    print("=" * 80)

    if len(merged) > 0:
        stable = merged[
            (merged['total_2024'] >= 10) &
            (merged['total_2025'] >= 10)
        ].copy()

        if len(stable) > 0:
            stable['avg_roi'] = (stable['roi_2024'] + stable['roi_2025']) / 2
            stable['roi_variance'] = abs(stable['roi_2024'] - stable['roi_2025'])
            stable['total_combined'] = stable['total_2024'] + stable['total_2025']

            # 平均ROIが高く、分散が低い条件
            stable_good = stable[stable['avg_roi'] >= 70].sort_values(
                ['avg_roi', 'roi_variance'],
                ascending=[False, True]
            )

            print(f"\n安定性の高い条件（平均ROI >= 70%）: {len(stable_good)} 件")
            if len(stable_good) > 0:
                print("\n" + "-" * 120)
                print(f"{'信頼度':<6} {'級別':<6} {'オッズ帯':<12} {'2024件数':>8} {'2024ROI':>10} {'2025件数':>8} {'2025ROI':>10} {'平均ROI':>10} {'差':>10}")
                print("-" * 120)

                for _, row in stable_good.head(20).iterrows():
                    diff = abs(row['roi_2024'] - row['roi_2025'])
                    avg_roi = row['avg_roi']
                    print(f"{row['confidence']:<6} {row['c1_rank']:<6} {row['odds_range']:<12} {int(row['total_2024']):>8} {row['roi_2024']:>9.1f}% {int(row['total_2025']):>8} {row['roi_2025']:>9.1f}% {avg_roi:>9.1f}% {diff:>9.1f}pt")
        else:
            print("\n両年度で10件以上のデータがある条件はありませんでした")
    else:
        print("\nマージ結果がありません")

    # ==========================================
    # 7. 新購入条件の提案
    # ==========================================
    print("\n" + "=" * 80)
    print("7. 現行条件と新条件の年度別検証")
    print("=" * 80)

    # 両年度で検証
    conditions_to_test = [
        # 現行条件
        ('D × A1 × 40-50倍(現行)', 'D', ['A1'], 40, 50),
        ('D × A2 × 20-30倍(現行)', 'D', ['A2'], 20, 30),
        ('D × B1 × 40-50倍(現行)', 'D', ['B1'], 40, 50),
        ('C × B1 × 30-40倍(現行)', 'C', ['B1'], 30, 40),
        ('C × A1 × 30-40倍(現行)', 'C', ['A1'], 30, 40),
        ('B × B1 × 全域(現行)', 'B', ['B1'], 10, 100),
        ('B × 50-100倍(現行)', 'B', ['A1', 'A2', 'B1'], 50, 100),
        # 新条件（広いオッズ帯）
        ('D × A1/A2 × 20-50倍(新)', 'D', ['A1', 'A2'], 20, 50),
        ('D × B1 × 30-50倍(新)', 'D', ['B1'], 30, 50),
        ('D × A1/A2/B1 × 30-60倍(新)', 'D', ['A1', 'A2', 'B1'], 30, 60),
        ('C × A1/B1 × 25-45倍(新)', 'C', ['A1', 'B1'], 25, 45),
        ('C × A1/B1 × 20-50倍(新)', 'C', ['A1', 'B1'], 20, 50),
        # Dランク単独
        ('D × 全条件(参考)', 'D', ['A1', 'A2', 'B1', 'B2'], 10, 200),
    ]

    print(f"\n{'条件名':<30} {'2024件数':>8} {'2024ROI':>10} {'2025件数':>8} {'2025ROI':>10} {'合計件数':>8} {'合計ROI':>10}")
    print("-" * 100)

    for name, conf, ranks, odds_min, odds_max in conditions_to_test:
        total_2024 = 0
        payout_2024 = 0
        total_2025 = 0
        payout_2025 = 0

        for year in [2024, 2025]:
            year_df = df[df['year'] == year]
            cond_df = year_df[
                (year_df['confidence'] == conf) &
                (year_df['c1_rank'].isin(ranks)) &
                (year_df['pred_odds'] >= odds_min) &
                (year_df['pred_odds'] < odds_max)
            ]

            hits = cond_df[cond_df['is_hit'] == True]
            payout = hits['pred_odds'].sum() * 100

            if year == 2024:
                total_2024 = len(cond_df)
                payout_2024 = payout
            else:
                total_2025 = len(cond_df)
                payout_2025 = payout

        invest_2024 = total_2024 * 100
        invest_2025 = total_2025 * 100
        roi_2024 = payout_2024 / invest_2024 * 100 if invest_2024 > 0 else 0
        roi_2025 = payout_2025 / invest_2025 * 100 if invest_2025 > 0 else 0

        total_combined = total_2024 + total_2025
        invest_combined = invest_2024 + invest_2025
        payout_combined = payout_2024 + payout_2025
        roi_combined = payout_combined / invest_combined * 100 if invest_combined > 0 else 0

        # 両年度黒字のマーク
        mark = ""
        if roi_2024 >= 100 and roi_2025 >= 100:
            mark = "★★"
        elif roi_combined >= 100:
            mark = "★"

        print(f"{name:<30} {total_2024:>8} {roi_2024:>9.1f}% {total_2025:>8} {roi_2025:>9.1f}% {total_combined:>8} {roi_combined:>9.1f}% {mark}")

    # ==========================================
    # 8. 総合分析と提案
    # ==========================================
    print("\n" + "=" * 80)
    print("8. 総合分析と提案")
    print("=" * 80)

    # 信頼度Dの年度別全体分析
    print("\n【信頼度D 年度別全体】")
    for year in [2024, 2025]:
        d_df = df[(df['year'] == year) & (df['confidence'] == 'D')]
        if len(d_df) > 0:
            hits = d_df[d_df['is_hit'] == True]
            investment = len(d_df) * 100
            payout = hits['pred_odds'].sum() * 100
            roi = payout / investment * 100 if investment > 0 else 0
            print(f"  {year}年: {len(d_df)}件, 的中{len(hits)}件 ({len(hits)/len(d_df)*100:.2f}%), ROI {roi:.1f}%")

    # 信頼度Cの年度別全体分析
    print("\n【信頼度C 年度別全体】")
    for year in [2024, 2025]:
        c_df = df[(df['year'] == year) & (df['confidence'] == 'C')]
        if len(c_df) > 0:
            hits = c_df[c_df['is_hit'] == True]
            investment = len(c_df) * 100
            payout = hits['pred_odds'].sum() * 100
            roi = payout / investment * 100 if investment > 0 else 0
            print(f"  {year}年: {len(c_df)}件, 的中{len(hits)}件 ({len(hits)/len(c_df)*100:.2f}%), ROI {roi:.1f}%")

    # 信頼度Bの年度別全体分析
    print("\n【信頼度B 年度別全体】")
    for year in [2024, 2025]:
        b_df = df[(df['year'] == year) & (df['confidence'] == 'B')]
        if len(b_df) > 0:
            hits = b_df[b_df['is_hit'] == True]
            investment = len(b_df) * 100
            payout = hits['pred_odds'].sum() * 100
            roi = payout / investment * 100 if investment > 0 else 0
            print(f"  {year}年: {len(b_df)}件, 的中{len(hits)}件 ({len(hits)/len(b_df)*100:.2f}%), ROI {roi:.1f}%")

    print("\n" + "=" * 80)
    print("分析完了")
    print("=" * 80)

if __name__ == '__main__':
    main()
