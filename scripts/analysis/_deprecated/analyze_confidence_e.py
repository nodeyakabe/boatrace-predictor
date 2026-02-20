# -*- coding: utf-8 -*-
"""
信頼度E導入の可否判断分析
==========================

信頼度Eの特性を分析し、購入条件としての採用可否を判断する。

使用例:
    python scripts/analysis/analyze_confidence_e.py
"""

import sqlite3
import pandas as pd
from pathlib import Path
from datetime import datetime


def load_data(db_path: str) -> pd.DataFrame:
    """信頼度Eのデータを読み込む"""
    conn = sqlite3.connect(db_path)

    # ml_analysis_featuresテーブルに信頼度Eがあるか確認
    query_check = """
        SELECT DISTINCT confidence FROM ml_analysis_features
    """
    df_conf = pd.read_sql_query(query_check, conn)
    print(f"利用可能な信頼度: {df_conf['confidence'].tolist()}")

    # 信頼度E含めて取得
    query = """
        SELECT
            maf.*,
            CASE
                WHEN maf.wind_direction IN ('北', '北北東', '北東', '北北西', '北西') THEN 'north'
                WHEN maf.wind_direction IN ('南', '南南東', '南東', '南南西', '南西') THEN 'south'
                WHEN maf.wind_direction IN ('東', '東北東', '東南東') THEN 'east'
                WHEN maf.wind_direction IN ('西', '西北西', '西南西') THEN 'west'
                ELSE 'unknown'
            END as wind_direction_group
        FROM ml_analysis_features maf
        WHERE maf.prediction_type = 'before'
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    return df


def analyze_confidence_e_basic(df: pd.DataFrame):
    """信頼度Eの基本分析"""
    print("\n" + "=" * 60)
    print("信頼度E 基本分析")
    print("=" * 60)

    # 信頼度Eのみ
    e_data = df[df['confidence'] == 'E']

    if len(e_data) == 0:
        print("信頼度Eのデータがありません")
        return None

    print(f"\n信頼度Eレース数: {len(e_data):,}件")

    # 全体成績
    hits = e_data['is_trifecta_hit'].sum()
    total = len(e_data)
    payout = e_data['trifecta_payout'].sum()
    investment = total * 100
    roi = payout / investment * 100

    print(f"的中率: {hits}/{total} ({hits/total*100:.2f}%)")
    print(f"ROI: {roi:.1f}%")
    print(f"収支: {payout - investment:+,.0f}円")

    # 年度別
    print("\n--- 年度別成績 ---")
    yearly_results = []
    for year in sorted(e_data['year'].unique()):
        year_data = e_data[e_data['year'] == year]
        y_total = len(year_data)
        y_hits = year_data['is_trifecta_hit'].sum()
        y_payout = year_data['trifecta_payout'].sum()
        y_invest = y_total * 100
        y_roi = y_payout / y_invest * 100 if y_invest > 0 else 0
        y_profit = y_payout - y_invest

        status = "+" if y_profit > 0 else "-"
        print(f"  {year}: {y_total:,}件, {y_hits}的中, ROI {y_roi:.1f}%, {y_profit:+,.0f}円 [{status}]")
        yearly_results.append({'year': year, 'roi': y_roi, 'profit': y_profit})

    return e_data


def analyze_e_by_conditions(e_data: pd.DataFrame):
    """信頼度Eの条件別分析"""
    if e_data is None or len(e_data) == 0:
        return

    print("\n" + "=" * 60)
    print("信頼度E 条件別分析")
    print("=" * 60)

    # オッズ帯別
    print("\n--- オッズ帯別 ---")
    for odds_band in ['10-20', '20-30', '30-50', '50-100', '100+']:
        subset = e_data[e_data['odds_band'] == odds_band]
        if len(subset) > 50:
            payout = subset['trifecta_payout'].sum()
            invest = len(subset) * 100
            roi = payout / invest * 100
            hits = subset['is_trifecta_hit'].sum()
            print(f"  {odds_band}: {len(subset)}件, {hits}的中, ROI {roi:.1f}%")

    # 1コース級別
    print("\n--- 1コース級別 ---")
    for rank in ['A1', 'A2', 'B1', 'B2']:
        subset = e_data[e_data['course1_rank'] == rank]
        if len(subset) > 50:
            payout = subset['trifecta_payout'].sum()
            invest = len(subset) * 100
            roi = payout / invest * 100
            hits = subset['is_trifecta_hit'].sum()
            print(f"  {rank}: {len(subset)}件, {hits}的中, ROI {roi:.1f}%")

    # 予測コース別
    print("\n--- 予測コース別 ---")
    e_data_copy = e_data.copy()
    e_data_copy['predicted_pit_str'] = e_data_copy['predicted_pit'].astype(str).str.replace('.0', '', regex=False)

    for course in ['1', '2', '3', '4', '5', '6']:
        subset = e_data_copy[e_data_copy['predicted_pit_str'] == course]
        if len(subset) > 50:
            payout = subset['trifecta_payout'].sum()
            invest = len(subset) * 100
            roi = payout / invest * 100
            hits = subset['is_trifecta_hit'].sum()
            print(f"  {course}コース: {len(subset)}件, {hits}的中, ROI {roi:.1f}%")


def find_promising_e_patterns(e_data: pd.DataFrame):
    """信頼度Eで有望なパターンを探索"""
    if e_data is None or len(e_data) == 0:
        return

    print("\n" + "=" * 60)
    print("信頼度E 有望パターン探索")
    print("=" * 60)

    e_data = e_data.copy()
    e_data['predicted_pit_str'] = e_data['predicted_pit'].astype(str).str.replace('.0', '', regex=False)
    e_data['venue_code_str'] = e_data['venue_code'].astype(str).str.zfill(2)

    # 会場コードマッピング
    venue_names = {
        '01': '桐生', '02': '戸田', '03': 'E川', '04': '平和島', '05': '多摩川',
        '06': '浜名湖', '07': '蒲郡', '08': '常滑', '09': '津', '10': '三国',
        '11': 'B湖', '12': '住之江', '13': '尼崎', '14': '鳴門', '15': '丸亀',
        '16': '児島', '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
        '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
    }

    results = []

    # パターン1: 会場 × オッズ帯
    print("\n--- 会場×オッズ帯 ---")
    for venue in e_data['venue_code_str'].unique():
        for odds_band in ['30-50', '50-100', '100+']:
            subset = e_data[(e_data['venue_code_str'] == venue) & (e_data['odds_band'] == odds_band)]
            if len(subset) >= 50:
                payout = subset['trifecta_payout'].sum()
                invest = len(subset) * 100
                roi = payout / invest * 100
                if roi >= 120:
                    # 年度別確認
                    yearly_positive = 0
                    for year in subset['year'].unique():
                        y_sub = subset[subset['year'] == year]
                        y_payout = y_sub['trifecta_payout'].sum()
                        y_invest = len(y_sub) * 100
                        if y_payout > y_invest:
                            yearly_positive += 1
                    venue_name = venue_names.get(venue, venue)
                    print(f"  {venue_name}×{odds_band}: {len(subset)}件, ROI {roi:.1f}%, {yearly_positive}年黒字")
                    results.append({
                        'pattern': f'E×{venue_name}×{odds_band}',
                        'count': len(subset),
                        'roi': roi,
                        'positive_years': yearly_positive
                    })

    # パターン2: 予測コース × オッズ帯
    print("\n--- 予測コース×オッズ帯 ---")
    for course in ['2', '3', '4', '5', '6']:
        for odds_band in ['30-50', '50-100', '100+']:
            subset = e_data[(e_data['predicted_pit_str'] == course) & (e_data['odds_band'] == odds_band)]
            if len(subset) >= 50:
                payout = subset['trifecta_payout'].sum()
                invest = len(subset) * 100
                roi = payout / invest * 100
                if roi >= 120:
                    yearly_positive = 0
                    for year in subset['year'].unique():
                        y_sub = subset[subset['year'] == year]
                        y_payout = y_sub['trifecta_payout'].sum()
                        y_invest = len(y_sub) * 100
                        if y_payout > y_invest:
                            yearly_positive += 1
                    print(f"  {course}コース×{odds_band}: {len(subset)}件, ROI {roi:.1f}%, {yearly_positive}年黒字")
                    results.append({
                        'pattern': f'E×{course}コース×{odds_band}',
                        'count': len(subset),
                        'roi': roi,
                        'positive_years': yearly_positive
                    })

    # パターン3: 会場 × 1コース級別
    print("\n--- 会場×1コース級別 ---")
    for venue in e_data['venue_code_str'].unique():
        for rank in ['A1', 'B1']:
            subset = e_data[(e_data['venue_code_str'] == venue) & (e_data['course1_rank'] == rank)]
            if len(subset) >= 50:
                payout = subset['trifecta_payout'].sum()
                invest = len(subset) * 100
                roi = payout / invest * 100
                if roi >= 120:
                    yearly_positive = 0
                    for year in subset['year'].unique():
                        y_sub = subset[subset['year'] == year]
                        y_payout = y_sub['trifecta_payout'].sum()
                        y_invest = len(y_sub) * 100
                        if y_payout > y_invest:
                            yearly_positive += 1
                    venue_name = venue_names.get(venue, venue)
                    print(f"  {venue_name}×{rank}: {len(subset)}件, ROI {roi:.1f}%, {yearly_positive}年黒字")
                    results.append({
                        'pattern': f'E×{venue_name}×{rank}',
                        'count': len(subset),
                        'roi': roi,
                        'positive_years': yearly_positive
                    })

    # サマリー
    if results:
        print("\n--- 有望パターン TOP10 ---")
        sorted_results = sorted(results, key=lambda x: (x['positive_years'], x['roi']), reverse=True)
        for r in sorted_results[:10]:
            print(f"  {r['pattern']}: {r['count']}件, ROI {r['roi']:.1f}%, {r['positive_years']}年黒字")

    return results


def main():
    db_path = Path(__file__).parent.parent.parent / "data" / "boatrace.db"

    print("=" * 60)
    print("信頼度E導入可否判断分析")
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # データ読み込み
    df = load_data(str(db_path))

    # 基本分析
    e_data = analyze_confidence_e_basic(df)

    if e_data is not None:
        # 条件別分析
        analyze_e_by_conditions(e_data)

        # 有望パターン探索
        results = find_promising_e_patterns(e_data)

        # 結論
        print("\n" + "=" * 60)
        print("結論")
        print("=" * 60)

        if results:
            stable_patterns = [r for r in results if r['positive_years'] >= 4]
            if stable_patterns:
                print(f"\n採用候補パターン: {len(stable_patterns)}件")
                for p in stable_patterns[:5]:
                    print(f"  - {p['pattern']}: ROI {p['roi']:.1f}%, {p['positive_years']}年黒字")
            else:
                print("\n安定したパターン（4年+黒字）が見つかりませんでした")
                print("→ 信頼度Eの即時採用は見送り推奨")
        else:
            print("\n有望なパターンが見つかりませんでした")
            print("→ 信頼度Eの即時採用は見送り推奨")


if __name__ == "__main__":
    main()
