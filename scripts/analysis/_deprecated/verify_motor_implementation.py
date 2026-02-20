# -*- coding: utf-8 -*-
"""
モーター40%+条件実装の効果検証
- 新規実装した条件が正しく機能するか検証
- 6年間データ（2020-2025）で期待通りの効果が出るか確認
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

DB_PATH = Path(__file__).parent.parent.parent / 'data' / 'boatrace.db'

def get_conn():
    return sqlite3.connect(str(DB_PATH))

def get_data_for_verification():
    """検証用データを取得"""
    conn = get_conn()

    df = pd.read_sql_query("""
        SELECT
            r.venue_code,
            substr(r.race_date, 1, 4) as year,
            rp.race_id,
            rp.confidence,
            e.racer_rank,
            e.motor_second_rate,
            p.amount as trifecta_payout,
            res.rank as actual_rank
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        JOIN entries e ON rp.race_id = e.race_id AND rp.pit_number = e.pit_number
        JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
        LEFT JOIN payouts p ON rp.race_id = p.race_id AND p.bet_type = 'trifecta'
        WHERE rp.prediction_type = 'before'
          AND substr(r.race_date, 1, 4) >= '2020'
          AND rp.rank_prediction = 1
          AND res.is_invalid = 0
    """, conn)

    conn.close()
    df['motor_40plus'] = df['motor_second_rate'] >= 40
    return df

def calc_roi(subset):
    """ROIを計算"""
    if len(subset) == 0:
        return 0, 0, 0
    hits = subset[subset['actual_rank'] == '1']
    roi = hits['trifecta_payout'].sum() / (len(subset) * 100) * 100 if len(subset) > 0 else 0
    profit = hits['trifecta_payout'].sum() - len(subset) * 100
    return roi, len(subset), profit

def verify_new_conditions(df):
    """新規実装した条件の効果を検証"""
    print("=" * 80)
    print("モーター40%+条件 実装効果検証")
    print("=" * 80)

    results = []

    # 新規条件1: A × B1 × モーター40%+
    print("\n" + "-" * 60)
    print("【1】A × B1 × モーター40%+（新規）")
    print("-" * 60)

    # モーターなし（従来）
    a_b1_base = df[(df['confidence'] == 'A') & (df['racer_rank'] == 'B1')]
    base_roi, base_count, base_profit = calc_roi(a_b1_base)
    print(f"  ベースライン（モーターなし）: ROI {base_roi:.1f}%, 件数 {base_count:,}, 収支 {base_profit:+,.0f}円")

    # モーター40%+（新規）
    a_b1_motor = df[(df['confidence'] == 'A') & (df['racer_rank'] == 'B1') & (df['motor_40plus'] == True)]
    motor_roi, motor_count, motor_profit = calc_roi(a_b1_motor)
    print(f"  モーター40%+: ROI {motor_roi:.1f}%, 件数 {motor_count:,}, 収支 {motor_profit:+,.0f}円")
    print(f"  改善効果: {motor_roi - base_roi:+.1f}pt")

    # 年度別
    print("  年度別ROI:")
    yearly_positive = 0
    for year in ['2020', '2021', '2022', '2023', '2024', '2025']:
        year_data = a_b1_motor[a_b1_motor['year'] == year]
        if len(year_data) >= 5:
            roi, cnt, _ = calc_roi(year_data)
            mark = '+' if roi > 100 else '-'
            if roi > 100:
                yearly_positive += 1
            print(f"    {year}: ROI {roi:,.0f}% ({cnt}件) {mark}")
    print(f"  プラス年度: {yearly_positive}/6年")

    results.append({
        'condition': 'A × B1 × モーター40%+',
        'roi': motor_roi,
        'count': motor_count,
        'profit': motor_profit,
        'positive_years': yearly_positive,
        'status': 'PASS' if yearly_positive >= 5 and motor_roi > 100 else 'FAIL'
    })

    # 新規条件2: A × A2 × モーター40%+
    print("\n" + "-" * 60)
    print("【2】A × A2 × モーター40%+（新規）")
    print("-" * 60)

    a_a2_base = df[(df['confidence'] == 'A') & (df['racer_rank'] == 'A2')]
    base_roi, base_count, base_profit = calc_roi(a_a2_base)
    print(f"  ベースライン（モーターなし）: ROI {base_roi:.1f}%, 件数 {base_count:,}, 収支 {base_profit:+,.0f}円")

    a_a2_motor = df[(df['confidence'] == 'A') & (df['racer_rank'] == 'A2') & (df['motor_40plus'] == True)]
    motor_roi, motor_count, motor_profit = calc_roi(a_a2_motor)
    print(f"  モーター40%+: ROI {motor_roi:.1f}%, 件数 {motor_count:,}, 収支 {motor_profit:+,.0f}円")
    print(f"  改善効果: {motor_roi - base_roi:+.1f}pt")

    print("  年度別ROI:")
    yearly_positive = 0
    for year in ['2020', '2021', '2022', '2023', '2024', '2025']:
        year_data = a_a2_motor[a_a2_motor['year'] == year]
        if len(year_data) >= 5:
            roi, cnt, _ = calc_roi(year_data)
            mark = '+' if roi > 100 else '-'
            if roi > 100:
                yearly_positive += 1
            print(f"    {year}: ROI {roi:,.0f}% ({cnt}件) {mark}")
    print(f"  プラス年度: {yearly_positive}/6年")

    results.append({
        'condition': 'A × A2 × モーター40%+',
        'roi': motor_roi,
        'count': motor_count,
        'profit': motor_profit,
        'positive_years': yearly_positive,
        'status': 'PASS' if yearly_positive >= 5 and motor_roi > 100 else 'FAIL'
    })

    # 新規条件3: D × A1 × モーター40%+
    print("\n" + "-" * 60)
    print("【3】D × A1 × モーター40%+（新規）")
    print("-" * 60)

    d_a1_base = df[(df['confidence'] == 'D') & (df['racer_rank'] == 'A1')]
    base_roi, base_count, base_profit = calc_roi(d_a1_base)
    print(f"  ベースライン（モーターなし）: ROI {base_roi:.1f}%, 件数 {base_count:,}, 収支 {base_profit:+,.0f}円")

    d_a1_motor = df[(df['confidence'] == 'D') & (df['racer_rank'] == 'A1') & (df['motor_40plus'] == True)]
    motor_roi, motor_count, motor_profit = calc_roi(d_a1_motor)
    print(f"  モーター40%+: ROI {motor_roi:.1f}%, 件数 {motor_count:,}, 収支 {motor_profit:+,.0f}円")
    print(f"  改善効果: {motor_roi - base_roi:+.1f}pt")

    print("  年度別ROI:")
    yearly_positive = 0
    for year in ['2020', '2021', '2022', '2023', '2024', '2025']:
        year_data = d_a1_motor[d_a1_motor['year'] == year]
        if len(year_data) >= 5:
            roi, cnt, _ = calc_roi(year_data)
            mark = '+' if roi > 100 else '-'
            if roi > 100:
                yearly_positive += 1
            print(f"    {year}: ROI {roi:,.0f}% ({cnt}件) {mark}")
    print(f"  プラス年度: {yearly_positive}/6年")

    results.append({
        'condition': 'D × A1 × モーター40%+',
        'roi': motor_roi,
        'count': motor_count,
        'profit': motor_profit,
        'positive_years': yearly_positive,
        'status': 'PASS' if yearly_positive >= 5 and motor_roi > 100 else 'FAIL'
    })

    # 新規条件4: D × A2 × モーター40%+
    print("\n" + "-" * 60)
    print("【4】D × A2 × モーター40%+（新規）")
    print("-" * 60)

    d_a2_base = df[(df['confidence'] == 'D') & (df['racer_rank'] == 'A2')]
    base_roi, base_count, base_profit = calc_roi(d_a2_base)
    print(f"  ベースライン（モーターなし）: ROI {base_roi:.1f}%, 件数 {base_count:,}, 収支 {base_profit:+,.0f}円")

    d_a2_motor = df[(df['confidence'] == 'D') & (df['racer_rank'] == 'A2') & (df['motor_40plus'] == True)]
    motor_roi, motor_count, motor_profit = calc_roi(d_a2_motor)
    print(f"  モーター40%+: ROI {motor_roi:.1f}%, 件数 {motor_count:,}, 収支 {motor_profit:+,.0f}円")
    print(f"  改善効果: {motor_roi - base_roi:+.1f}pt")

    print("  年度別ROI:")
    yearly_positive = 0
    for year in ['2020', '2021', '2022', '2023', '2024', '2025']:
        year_data = d_a2_motor[d_a2_motor['year'] == year]
        if len(year_data) >= 5:
            roi, cnt, _ = calc_roi(year_data)
            mark = '+' if roi > 100 else '-'
            if roi > 100:
                yearly_positive += 1
            print(f"    {year}: ROI {roi:,.0f}% ({cnt}件) {mark}")
    print(f"  プラス年度: {yearly_positive}/6年")

    results.append({
        'condition': 'D × A2 × モーター40%+',
        'roi': motor_roi,
        'count': motor_count,
        'profit': motor_profit,
        'positive_years': yearly_positive,
        'status': 'PASS' if yearly_positive >= 5 and motor_roi > 100 else 'FAIL'
    })

    return results

def compare_before_after(df):
    """実装前後の比較"""
    print("\n" + "=" * 80)
    print("実装前後の比較（2025年データ）")
    print("=" * 80)

    df_2025 = df[df['year'] == '2025']

    # 既存条件のみ（モーター条件なし）
    print("\n■ 既存条件（モーター条件なし）:")

    # A × A1
    a_a1 = df_2025[(df_2025['confidence'] == 'A') & (df_2025['racer_rank'] == 'A1')]
    roi, cnt, profit = calc_roi(a_a1)
    print(f"  A × A1: ROI {roi:.1f}%, {cnt}件, {profit:+,.0f}円")

    # D × A1/A2/B1
    d_all = df_2025[(df_2025['confidence'] == 'D') & (df_2025['racer_rank'].isin(['A1', 'A2', 'B1']))]
    roi, cnt, profit = calc_roi(d_all)
    print(f"  D × A1/A2/B1: ROI {roi:.1f}%, {cnt}件, {profit:+,.0f}円")

    existing_total_profit = profit

    print("\n■ 新規条件（モーター40%+）:")

    # A × B1 × モーター40%+
    a_b1_motor = df_2025[(df_2025['confidence'] == 'A') & (df_2025['racer_rank'] == 'B1') & (df_2025['motor_40plus'] == True)]
    roi, cnt, profit = calc_roi(a_b1_motor)
    print(f"  A × B1 × モーター40%+: ROI {roi:.1f}%, {cnt}件, {profit:+,.0f}円")
    new_profit_1 = profit

    # A × A2 × モーター40%+
    a_a2_motor = df_2025[(df_2025['confidence'] == 'A') & (df_2025['racer_rank'] == 'A2') & (df_2025['motor_40plus'] == True)]
    roi, cnt, profit = calc_roi(a_a2_motor)
    print(f"  A × A2 × モーター40%+: ROI {roi:.1f}%, {cnt}件, {profit:+,.0f}円")
    new_profit_2 = profit

    # D × A1 × モーター40%+
    d_a1_motor = df_2025[(df_2025['confidence'] == 'D') & (df_2025['racer_rank'] == 'A1') & (df_2025['motor_40plus'] == True)]
    roi, cnt, profit = calc_roi(d_a1_motor)
    print(f"  D × A1 × モーター40%+: ROI {roi:.1f}%, {cnt}件, {profit:+,.0f}円")
    new_profit_3 = profit

    # D × A2 × モーター40%+
    d_a2_motor = df_2025[(df_2025['confidence'] == 'D') & (df_2025['racer_rank'] == 'A2') & (df_2025['motor_40plus'] == True)]
    roi, cnt, profit = calc_roi(d_a2_motor)
    print(f"  D × A2 × モーター40%+: ROI {roi:.1f}%, {cnt}件, {profit:+,.0f}円")
    new_profit_4 = profit

    total_new_profit = new_profit_1 + new_profit_2 + new_profit_3 + new_profit_4

    print("\n" + "-" * 40)
    print(f"新規条件による追加収支（2025年）: {total_new_profit:+,.0f}円")
    print("-" * 40)

    return total_new_profit

def main():
    print("=" * 80)
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    df = get_data_for_verification()
    print(f"\n総レコード数: {len(df):,}件")
    print(f"モーター40%+レコード: {df['motor_40plus'].sum():,}件 ({df['motor_40plus'].mean()*100:.1f}%)")

    # 新規条件の検証
    results = verify_new_conditions(df)

    # 実装前後の比較
    additional_profit = compare_before_after(df)

    # サマリー
    print("\n" + "=" * 80)
    print("【検証結果サマリー】")
    print("=" * 80)

    passed = [r for r in results if r['status'] == 'PASS']
    failed = [r for r in results if r['status'] == 'FAIL']

    print(f"\n検証PASS: {len(passed)}/{len(results)}件")
    for r in passed:
        print(f"  [PASS] {r['condition']}: ROI {r['roi']:.1f}%, {r['positive_years']}年プラス")

    if failed:
        print(f"\n検証FAIL: {len(failed)}件")
        for r in failed:
            print(f"  [FAIL] {r['condition']}: ROI {r['roi']:.1f}%, {r['positive_years']}年プラス")

    print("\n" + "=" * 80)
    print("【結論】")
    print("=" * 80)

    total_profit = sum(r['profit'] for r in results)
    print(f"\n新規モーター条件による6年間合計収支: {total_profit:+,.0f}円")
    print(f"2025年の追加収支: {additional_profit:+,.0f}円")

    if len(passed) >= 3:
        print("\n=> 実装効果は期待通り。本番運用を継続。")
    else:
        print("\n=> 一部条件で期待を下回る。詳細確認が必要。")

    return results

if __name__ == "__main__":
    results = main()
