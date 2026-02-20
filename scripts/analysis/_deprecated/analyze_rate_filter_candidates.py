# -*- coding: utf-8 -*-
"""
連対率フィルター候補の詳細分析

候補条件:
1. A×A1×14-16: 2着予測選手の3連対率 >= 35%を除外
2. A×A1×14-16: 2着予測選手の2連対率 >= 25%を除外
3. A×A1×10-12: 3着予測選手の2連対率 < 55%を除外

分析内容:
- 年度別ROI/収支/的中率
- クロスバリデーション検証
- 閾値感度分析
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path

# 設定
DB_PATH = Path(__file__).parent.parent.parent / 'data' / 'boatrace.db'

def get_base_data(conn):
    """基本データを取得"""
    query = """
    SELECT
        rp.race_id,
        substr(r.race_date, 1, 4) as year,
        r.venue_code,
        r.race_number,
        rp.confidence,
        rp.pit_number as pred1_pit,
        pred2.pit_number as pred2_pit,
        pred3.pit_number as pred3_pit,
        e1.racer_rank as c1_rank,
        e1.second_rate as c1_second_rate,
        e1.third_rate as c1_third_rate,
        e2.second_rate as pred2_second_rate,
        e2.third_rate as pred2_third_rate,
        e3.second_rate as pred3_second_rate,
        e3.third_rate as pred3_third_rate,
        t.odds,
        CASE WHEN res1.rank = '1' AND res2.rank = '2' AND res3.rank = '3' THEN 1 ELSE 0 END as is_hit,
        COALESCE(p.amount, 0) as payout
    FROM race_predictions rp
    JOIN races r ON rp.race_id = r.id
    -- 1着予測
    JOIN entries e1 ON rp.race_id = e1.race_id AND e1.pit_number = 1
    -- 2着予測
    JOIN race_predictions pred2 ON rp.race_id = pred2.race_id
        AND pred2.prediction_type = rp.prediction_type AND pred2.rank_prediction = 2
    JOIN entries e2 ON rp.race_id = e2.race_id AND pred2.pit_number = e2.pit_number
    -- 3着予測
    JOIN race_predictions pred3 ON rp.race_id = pred3.race_id
        AND pred3.prediction_type = rp.prediction_type AND pred3.rank_prediction = 3
    JOIN entries e3 ON rp.race_id = e3.race_id AND pred3.pit_number = e3.pit_number
    -- オッズ
    LEFT JOIN trifecta_odds t ON rp.race_id = t.race_id
        AND t.combination = rp.pit_number || '-' || pred2.pit_number || '-' || pred3.pit_number
    -- 結果
    LEFT JOIN results res1 ON rp.race_id = res1.race_id AND rp.pit_number = res1.pit_number
    LEFT JOIN results res2 ON rp.race_id = res2.race_id AND pred2.pit_number = res2.pit_number
    LEFT JOIN results res3 ON rp.race_id = res3.race_id AND pred3.pit_number = res3.pit_number
    -- 払戻
    LEFT JOIN payouts p ON rp.race_id = p.race_id AND p.bet_type = 'trifecta'
        AND p.combination = rp.pit_number || '-' || pred2.pit_number || '-' || pred3.pit_number
    WHERE rp.prediction_type = 'before'
        AND rp.rank_prediction = 1
        AND rp.confidence IN ('A', 'B', 'C', 'D')
    """
    return pd.read_sql_query(query, conn)


def analyze_condition(df, condition_name, base_filter, exclusion_filter):
    """条件の年度別分析"""
    print(f"\n{'='*80}")
    print(f"【{condition_name}】")
    print('='*80)

    # 基本条件でフィルタ
    df_base = df[base_filter(df)].copy()

    if len(df_base) == 0:
        print("該当データなし")
        return None

    # 除外フィルタ適用後
    df_filtered = df_base[~exclusion_filter(df_base)].copy()

    results = []
    years = sorted(df_base['year'].unique())

    print("\n年度別詳細:")
    print("-" * 100)
    print(f"{'年度':^6} | {'件数(前)':^8} | {'件数(後)':^8} | {'除外数':^6} | {'的中(前)':^8} | {'的中(後)':^8} | {'ROI(前)':^10} | {'ROI(後)':^10} | {'収支(前)':^12} | {'収支(後)':^12}")
    print("-" * 100)

    for year in years:
        df_year_base = df_base[df_base['year'] == year]
        df_year_filtered = df_filtered[df_filtered['year'] == year]

        # 除外前
        n_before = len(df_year_base)
        hits_before = df_year_base['is_hit'].sum()
        payout_before = (df_year_base['is_hit'] * df_year_base['payout']).sum()
        cost_before = n_before * 100
        roi_before = payout_before / cost_before * 100 if cost_before > 0 else 0
        profit_before = payout_before - cost_before

        # 除外後
        n_after = len(df_year_filtered)
        hits_after = df_year_filtered['is_hit'].sum()
        payout_after = (df_year_filtered['is_hit'] * df_year_filtered['payout']).sum()
        cost_after = n_after * 100
        roi_after = payout_after / cost_after * 100 if cost_after > 0 else 0
        profit_after = payout_after - cost_after

        n_excluded = n_before - n_after

        results.append({
            'year': year,
            'n_before': n_before,
            'n_after': n_after,
            'n_excluded': n_excluded,
            'hits_before': hits_before,
            'hits_after': hits_after,
            'roi_before': roi_before,
            'roi_after': roi_after,
            'profit_before': profit_before,
            'profit_after': profit_after
        })

        print(f"{year:^6} | {n_before:^8} | {n_after:^8} | {n_excluded:^6} | {hits_before:^8} | {hits_after:^8} | {roi_before:>9.1f}% | {roi_after:>9.1f}% | {profit_before:>+11,.0f} | {profit_after:>+11,.0f}")

    # 合計
    print("-" * 100)
    total_n_before = sum(r['n_before'] for r in results)
    total_n_after = sum(r['n_after'] for r in results)
    total_excluded = sum(r['n_excluded'] for r in results)
    total_hits_before = sum(r['hits_before'] for r in results)
    total_hits_after = sum(r['hits_after'] for r in results)
    total_profit_before = sum(r['profit_before'] for r in results)
    total_profit_after = sum(r['profit_after'] for r in results)
    total_cost_before = total_n_before * 100
    total_cost_after = total_n_after * 100
    total_roi_before = (total_profit_before + total_cost_before) / total_cost_before * 100 if total_cost_before > 0 else 0
    total_roi_after = (total_profit_after + total_cost_after) / total_cost_after * 100 if total_cost_after > 0 else 0

    print(f"{'合計':^6} | {total_n_before:^8} | {total_n_after:^8} | {total_excluded:^6} | {total_hits_before:^8} | {total_hits_after:^8} | {total_roi_before:>9.1f}% | {total_roi_after:>9.1f}% | {total_profit_before:>+11,.0f} | {total_profit_after:>+11,.0f}")

    # ROI改善
    roi_improvement = total_roi_after - total_roi_before
    profit_improvement = total_profit_after - total_profit_before
    print(f"\n■ 効果: ROI {roi_improvement:+.1f}pt, 収支 {profit_improvement:+,.0f}円")

    # 年度安定性
    positive_years_before = sum(1 for r in results if r['profit_before'] > 0)
    positive_years_after = sum(1 for r in results if r['profit_after'] > 0)
    print(f"■ 黒字年度: {positive_years_before}/6年 → {positive_years_after}/6年")

    return results


def cross_validation(df, base_filter, exclusion_filter, test_year):
    """クロスバリデーション: test_year以外でルールを構築し、test_yearでテスト"""
    # 学習データ
    train_years = [y for y in ['2020', '2021', '2022', '2023', '2024', '2025'] if y != test_year]
    df_train = df[df['year'].isin(train_years)]
    df_test = df[df['year'] == test_year]

    # 学習データで基本条件適用
    df_train_base = df_train[base_filter(df_train)]
    df_test_base = df_test[base_filter(df_test)]

    if len(df_train_base) == 0 or len(df_test_base) == 0:
        return None

    # 学習データでフィルタ有効性を確認
    df_train_filtered = df_train_base[~exclusion_filter(df_train_base)]

    train_roi_before = (df_train_base['is_hit'] * df_train_base['payout']).sum() / (len(df_train_base) * 100) * 100
    train_roi_after = (df_train_filtered['is_hit'] * df_train_filtered['payout']).sum() / (len(df_train_filtered) * 100) * 100 if len(df_train_filtered) > 0 else 0

    # テストデータで検証
    df_test_filtered = df_test_base[~exclusion_filter(df_test_base)]

    test_roi_before = (df_test_base['is_hit'] * df_test_base['payout']).sum() / (len(df_test_base) * 100) * 100
    test_roi_after = (df_test_filtered['is_hit'] * df_test_filtered['payout']).sum() / (len(df_test_filtered) * 100) * 100 if len(df_test_filtered) > 0 else 0

    return {
        'test_year': test_year,
        'train_n': len(df_train_base),
        'test_n_before': len(df_test_base),
        'test_n_after': len(df_test_filtered),
        'train_roi_before': train_roi_before,
        'train_roi_after': train_roi_after,
        'test_roi_before': test_roi_before,
        'test_roi_after': test_roi_after,
        'train_improvement': train_roi_after - train_roi_before,
        'test_improvement': test_roi_after - test_roi_before
    }


def threshold_sensitivity(df, condition_name, base_filter, rate_column, thresholds, exclude_above=True):
    """閾値感度分析"""
    print(f"\n{'='*80}")
    print(f"【閾値感度分析: {condition_name}】")
    print('='*80)

    df_base = df[base_filter(df)].copy()

    if len(df_base) == 0:
        print("該当データなし")
        return None

    results = []

    print(f"\n{'閾値':^8} | {'除外後件数':^10} | {'除外数':^8} | {'的中数':^8} | {'ROI':^10} | {'収支':^12}")
    print("-" * 70)

    # ベースライン（フィルタなし）
    n = len(df_base)
    hits = df_base['is_hit'].sum()
    payout = (df_base['is_hit'] * df_base['payout']).sum()
    roi = payout / (n * 100) * 100 if n > 0 else 0
    profit = payout - n * 100
    print(f"{'なし':^8} | {n:^10} | {0:^8} | {hits:^8} | {roi:>9.1f}% | {profit:>+11,.0f}")

    for threshold in thresholds:
        if exclude_above:
            df_filtered = df_base[df_base[rate_column] < threshold]
        else:
            df_filtered = df_base[df_base[rate_column] >= threshold]

        n_after = len(df_filtered)
        excluded = n - n_after
        hits_after = df_filtered['is_hit'].sum()
        payout_after = (df_filtered['is_hit'] * df_filtered['payout']).sum()
        roi_after = payout_after / (n_after * 100) * 100 if n_after > 0 else 0
        profit_after = payout_after - n_after * 100

        results.append({
            'threshold': threshold,
            'n_after': n_after,
            'excluded': excluded,
            'hits': hits_after,
            'roi': roi_after,
            'profit': profit_after
        })

        direction = "以上除外" if exclude_above else "未満除外"
        print(f"{threshold:>6.0f}%{direction[0]} | {n_after:^10} | {excluded:^8} | {hits_after:^8} | {roi_after:>9.1f}% | {profit_after:>+11,.0f}")

    return results


def analyze_other_conditions(df):
    """他条件への適用可能性"""
    print(f"\n{'='*80}")
    print("【他条件への連対率フィルター適用可能性】")
    print('='*80)

    conditions = [
        {
            'name': 'B×50-100',
            'base_filter': lambda d: (d['confidence'] == 'B') & (d['odds'] >= 50) & (d['odds'] < 100) & (d['c1_rank'].isin(['A1', 'B1'])),
        },
        {
            'name': 'C×20-30×B1',
            'base_filter': lambda d: (d['confidence'] == 'C') & (d['odds'] >= 20) & (d['odds'] < 30) & (d['c1_rank'] == 'B1'),
        },
        {
            'name': 'D×35-60',
            'base_filter': lambda d: (d['confidence'] == 'D') & (d['odds'] >= 35) & (d['odds'] < 60) & (d['c1_rank'].isin(['A1', 'A2', 'B1'])),
        },
        {
            'name': 'D×40-50×B1',
            'base_filter': lambda d: (d['confidence'] == 'D') & (d['odds'] >= 40) & (d['odds'] < 50) & (d['c1_rank'] == 'B1'),
        },
    ]

    for cond in conditions:
        df_base = df[cond['base_filter'](df)].copy()
        if len(df_base) == 0:
            continue

        print(f"\n--- {cond['name']} (n={len(df_base)}) ---")

        # 2着予測選手の連対率分析
        for rate_col, rate_name in [('pred2_second_rate', '2着予測2連対率'), ('pred2_third_rate', '2着予測3連対率')]:
            for threshold in [25, 30, 35, 40]:
                df_filtered = df_base[df_base[rate_col] < threshold]
                if len(df_filtered) == 0:
                    continue

                roi_before = (df_base['is_hit'] * df_base['payout']).sum() / (len(df_base) * 100) * 100
                roi_after = (df_filtered['is_hit'] * df_filtered['payout']).sum() / (len(df_filtered) * 100) * 100

                if roi_after - roi_before > 10:  # 10pt以上改善なら報告
                    print(f"  {rate_name} >= {threshold}% 除外: {len(df_base)} → {len(df_filtered)}件, ROI {roi_before:.1f}% → {roi_after:.1f}% (+{roi_after-roi_before:.1f}pt)")


def main():
    print("連対率フィルター候補の詳細分析")
    print("=" * 80)

    conn = sqlite3.connect(DB_PATH)

    print("\nデータ取得中...")
    df = get_base_data(conn)
    print(f"取得データ数: {len(df):,}件")
    print(f"年度: {sorted(df['year'].unique())}")
    print(f"信頼度分布: {df['confidence'].value_counts().to_dict()}")

    # オッズが取得できているデータのみ
    df = df[df['odds'].notna() & (df['odds'] > 0)]
    print(f"オッズ有効データ数: {len(df):,}件")

    # ============================================================
    # 候補条件1: A×A1×14-16 + 2着予測選手の3連対率 >=35% 除外
    # ============================================================
    base_filter_1 = lambda d: (d['confidence'] == 'A') & (d['c1_rank'] == 'A1') & (d['odds'] >= 14) & (d['odds'] < 16)
    exclusion_filter_1 = lambda d: d['pred2_third_rate'] >= 35

    results_1 = analyze_condition(
        df,
        "候補条件1: A×A1×14-16 + 2着予測3連対率 >=35% 除外",
        base_filter_1,
        exclusion_filter_1
    )

    # ============================================================
    # 候補条件2: A×A1×14-16 + 2着予測選手の2連対率 >=25% 除外
    # ============================================================
    exclusion_filter_2 = lambda d: d['pred2_second_rate'] >= 25

    results_2 = analyze_condition(
        df,
        "候補条件2: A×A1×14-16 + 2着予測2連対率 >=25% 除外",
        base_filter_1,
        exclusion_filter_2
    )

    # ============================================================
    # 候補条件3: A×A1×10-12 + 3着予測選手の2連対率 <55% 除外
    # ============================================================
    base_filter_3 = lambda d: (d['confidence'] == 'A') & (d['c1_rank'] == 'A1') & (d['odds'] >= 10) & (d['odds'] < 12)
    exclusion_filter_3 = lambda d: d['pred3_second_rate'] < 55

    results_3 = analyze_condition(
        df,
        "候補条件3: A×A1×10-12 + 3着予測2連対率 <55% 除外",
        base_filter_3,
        exclusion_filter_3
    )

    # ============================================================
    # クロスバリデーション検証
    # ============================================================
    print(f"\n{'='*80}")
    print("【クロスバリデーション検証】")
    print('='*80)

    print("\n--- 候補条件1: A×A1×14-16 + 2着予測3連対率 >=35% 除外 ---")
    print(f"{'テスト年':^10} | {'学習件数':^8} | {'テスト件数(前)':^14} | {'テスト件数(後)':^14} | {'学習ROI改善':^12} | {'テストROI改善':^12}")
    print("-" * 80)

    cv_results_1 = []
    for test_year in ['2020', '2021', '2022', '2023', '2024', '2025']:
        result = cross_validation(df, base_filter_1, exclusion_filter_1, test_year)
        if result:
            cv_results_1.append(result)
            print(f"{result['test_year']:^10} | {result['train_n']:^8} | {result['test_n_before']:^14} | {result['test_n_after']:^14} | {result['train_improvement']:>+11.1f}pt | {result['test_improvement']:>+11.1f}pt")

    if cv_results_1:
        avg_train = np.mean([r['train_improvement'] for r in cv_results_1])
        avg_test = np.mean([r['test_improvement'] for r in cv_results_1])
        print(f"\n平均: 学習 {avg_train:+.1f}pt, テスト {avg_test:+.1f}pt")
        consistent = sum(1 for r in cv_results_1 if r['test_improvement'] > 0)
        print(f"テストで改善した年度: {consistent}/6年")

    # ============================================================
    # 閾値感度分析
    # ============================================================
    threshold_sensitivity(
        df,
        "A×A1×14-16 の 2着予測3連対率",
        base_filter_1,
        'pred2_third_rate',
        [25, 30, 35, 40, 45, 50],
        exclude_above=True
    )

    threshold_sensitivity(
        df,
        "A×A1×14-16 の 2着予測2連対率",
        base_filter_1,
        'pred2_second_rate',
        [20, 25, 30, 35, 40],
        exclude_above=True
    )

    # ============================================================
    # 他条件への適用
    # ============================================================
    analyze_other_conditions(df)

    conn.close()

    # ============================================================
    # 最終推奨
    # ============================================================
    print(f"\n{'='*80}")
    print("【最終推奨】")
    print('='*80)

    print("""
■ 候補条件1: A×A1×14-16 + 2着予測3連対率 >=35% 除外
  - 判定: 【見送り】
  - 理由: サンプルサイズが極めて小さい（除外後各年3-5件程度）
  - リスク: 過学習の懸念が高く、統計的信頼性が不十分

■ 候補条件2: A×A1×14-16 + 2着予測2連対率 >=25% 除外
  - 判定: 【見送り】
  - 理由: 候補条件1と同様、サンプルサイズ不足

■ 候補条件3: A×A1×10-12 + 3着予測2連対率 <55% 除外
  - 判定: 【見送り】
  - 理由: 年度別で効果が一貫しない可能性が高い

■ 結論
  元の分析で見つかった有意なp値は、サンプルサイズの小ささによる
  偶然の結果である可能性が高い。連対率フィルターによる除外は
  現時点では推奨しない。

  今後、より多くのデータが蓄積された段階（各条件で年間100件以上）で
  再検証することを推奨する。
""")


if __name__ == '__main__':
    main()
