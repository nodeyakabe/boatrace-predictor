# -*- coding: utf-8 -*-
"""
実装シミュレーション
- 既存条件との組み合わせ効果を検証
- モーター条件追加の効果を試算
- 最終的な実装判断を支援
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
import json
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

DB_PATH = Path(__file__).parent.parent.parent / 'data' / 'boatrace.db'

def get_conn():
    return sqlite3.connect(str(DB_PATH))

def get_2025_data():
    """2025年のbefore予測データを取得"""
    conn = get_conn()

    df = pd.read_sql_query("""
        SELECT
            r.venue_code,
            r.race_date,
            rp.race_id,
            rp.pit_number,
            rp.confidence,
            rp.rank_prediction,
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
          AND substr(r.race_date, 1, 4) = '2025'
          AND rp.rank_prediction = 1
          AND res.is_invalid = 0
    """, conn)

    conn.close()

    # モーターカテゴリを追加
    df['motor_40plus'] = df['motor_second_rate'] >= 40

    return df

def simulate_current_conditions(df):
    """現在の条件でのパフォーマンス"""
    results = []

    # A × A1 × 10-12倍、14-16倍（現在の条件ではオッズがないため近似）
    # ここではモーター条件なしのA×A1をベースラインとして使用
    a_a1 = df[(df['confidence'] == 'A') & (df['racer_rank'] == 'A1')]
    hits = a_a1[a_a1['actual_rank'] == '1']
    roi = hits['trifecta_payout'].sum() / (len(a_a1) * 100) * 100 if len(a_a1) > 0 else 0
    results.append({
        'condition': 'A × A1 (現状)',
        'count': len(a_a1),
        'hits': len(hits),
        'roi': roi,
        'profit': hits['trifecta_payout'].sum() - len(a_a1) * 100
    })

    # B条件
    b_all = df[(df['confidence'] == 'B')]
    hits = b_all[b_all['actual_rank'] == '1']
    roi = hits['trifecta_payout'].sum() / (len(b_all) * 100) * 100 if len(b_all) > 0 else 0
    results.append({
        'condition': 'B (現状)',
        'count': len(b_all),
        'hits': len(hits),
        'roi': roi,
        'profit': hits['trifecta_payout'].sum() - len(b_all) * 100
    })

    # C × B1
    c_b1 = df[(df['confidence'] == 'C') & (df['racer_rank'] == 'B1')]
    hits = c_b1[c_b1['actual_rank'] == '1']
    roi = hits['trifecta_payout'].sum() / (len(c_b1) * 100) * 100 if len(c_b1) > 0 else 0
    results.append({
        'condition': 'C × B1 (現状)',
        'count': len(c_b1),
        'hits': len(hits),
        'roi': roi,
        'profit': hits['trifecta_payout'].sum() - len(c_b1) * 100
    })

    # D条件
    d_all = df[(df['confidence'] == 'D') & (df['racer_rank'].isin(['A1', 'A2', 'B1']))]
    hits = d_all[d_all['actual_rank'] == '1']
    roi = hits['trifecta_payout'].sum() / (len(d_all) * 100) * 100 if len(d_all) > 0 else 0
    results.append({
        'condition': 'D × A1/A2/B1 (現状)',
        'count': len(d_all),
        'hits': len(hits),
        'roi': roi,
        'profit': hits['trifecta_payout'].sum() - len(d_all) * 100
    })

    return results

def simulate_motor_filter(df):
    """モーター40%+フィルター追加の効果"""
    results = []

    # 各信頼度×級別×モーター40%+
    for conf in ['A', 'B', 'C', 'D']:
        for rank in ['A1', 'A2', 'B1']:
            # モーターなし
            base = df[(df['confidence'] == conf) & (df['racer_rank'] == rank)]
            # モーター40%+あり
            motor = df[(df['confidence'] == conf) & (df['racer_rank'] == rank) & (df['motor_40plus'] == True)]

            if len(base) >= 30 and len(motor) >= 10:
                base_hits = base[base['actual_rank'] == '1']
                motor_hits = motor[motor['actual_rank'] == '1']

                base_roi = base_hits['trifecta_payout'].sum() / (len(base) * 100) * 100 if len(base) > 0 else 0
                motor_roi = motor_hits['trifecta_payout'].sum() / (len(motor) * 100) * 100 if len(motor) > 0 else 0

                roi_diff = motor_roi - base_roi

                results.append({
                    'condition': f'{conf} × {rank}',
                    'base_count': len(base),
                    'base_roi': base_roi,
                    'motor_count': len(motor),
                    'motor_roi': motor_roi,
                    'roi_improvement': roi_diff,
                    'motor_profit': motor_hits['trifecta_payout'].sum() - len(motor) * 100
                })

    return results

def simulate_combined_effect(df):
    """既存条件 + モーター条件の組み合わせ効果"""
    # 現在の条件（概算）
    # A × A1 × (10-12 or 14-16) → モーター追加
    # B × 50-100 or B × 30-50 × B1 → モーター追加
    # C × 20-30 × B1 → モーター追加
    # D × 30-60 × A1/A2/B1 → モーター追加

    results = []

    # 信頼度A × A1 × モーター40%+
    a_a1_motor = df[(df['confidence'] == 'A') & (df['racer_rank'] == 'A1') & (df['motor_40plus'] == True)]
    hits = a_a1_motor[a_a1_motor['actual_rank'] == '1']
    roi = hits['trifecta_payout'].sum() / (len(a_a1_motor) * 100) * 100 if len(a_a1_motor) > 0 else 0
    results.append({
        'condition': 'A × A1 × モーター40%+',
        'count': len(a_a1_motor),
        'hits': len(hits),
        'hit_rate': len(hits) / len(a_a1_motor) * 100 if len(a_a1_motor) > 0 else 0,
        'roi': roi,
        'profit': hits['trifecta_payout'].sum() - len(a_a1_motor) * 100
    })

    # 信頼度B × モーター40%+
    b_motor = df[(df['confidence'] == 'B') & (df['motor_40plus'] == True)]
    hits = b_motor[b_motor['actual_rank'] == '1']
    roi = hits['trifecta_payout'].sum() / (len(b_motor) * 100) * 100 if len(b_motor) > 0 else 0
    results.append({
        'condition': 'B × モーター40%+',
        'count': len(b_motor),
        'hits': len(hits),
        'hit_rate': len(hits) / len(b_motor) * 100 if len(b_motor) > 0 else 0,
        'roi': roi,
        'profit': hits['trifecta_payout'].sum() - len(b_motor) * 100
    })

    # 信頼度C × B1 × モーター40%+
    c_b1_motor = df[(df['confidence'] == 'C') & (df['racer_rank'] == 'B1') & (df['motor_40plus'] == True)]
    hits = c_b1_motor[c_b1_motor['actual_rank'] == '1']
    roi = hits['trifecta_payout'].sum() / (len(c_b1_motor) * 100) * 100 if len(c_b1_motor) > 0 else 0
    results.append({
        'condition': 'C × B1 × モーター40%+',
        'count': len(c_b1_motor),
        'hits': len(hits),
        'hit_rate': len(hits) / len(c_b1_motor) * 100 if len(c_b1_motor) > 0 else 0,
        'roi': roi,
        'profit': hits['trifecta_payout'].sum() - len(c_b1_motor) * 100
    })

    # 信頼度D × A1/A2/B1 × モーター40%+
    d_motor = df[(df['confidence'] == 'D') & (df['racer_rank'].isin(['A1', 'A2', 'B1'])) & (df['motor_40plus'] == True)]
    hits = d_motor[d_motor['actual_rank'] == '1']
    roi = hits['trifecta_payout'].sum() / (len(d_motor) * 100) * 100 if len(d_motor) > 0 else 0
    results.append({
        'condition': 'D × A1/A2/B1 × モーター40%+',
        'count': len(d_motor),
        'hits': len(hits),
        'hit_rate': len(hits) / len(d_motor) * 100 if len(d_motor) > 0 else 0,
        'roi': roi,
        'profit': hits['trifecta_payout'].sum() - len(d_motor) * 100
    })

    return results

def compare_with_and_without_motor(df):
    """モーター条件あり/なしの直接比較"""
    results = []

    for conf in ['A', 'B', 'C', 'D']:
        for rank in ['A1', 'A2', 'B1']:
            # モーターなし
            without = df[(df['confidence'] == conf) & (df['racer_rank'] == rank) & (df['motor_40plus'] == False)]
            # モーター40%+
            with_motor = df[(df['confidence'] == conf) & (df['racer_rank'] == rank) & (df['motor_40plus'] == True)]

            if len(without) >= 10 and len(with_motor) >= 10:
                without_hits = without[without['actual_rank'] == '1']
                with_hits = with_motor[with_motor['actual_rank'] == '1']

                without_roi = without_hits['trifecta_payout'].sum() / (len(without) * 100) * 100 if len(without) > 0 else 0
                with_roi = with_hits['trifecta_payout'].sum() / (len(with_motor) * 100) * 100 if len(with_motor) > 0 else 0

                results.append({
                    'condition': f'{conf} × {rank}',
                    'without_motor_count': len(without),
                    'without_motor_roi': without_roi,
                    'with_motor_count': len(with_motor),
                    'with_motor_roi': with_roi,
                    'improvement': with_roi - without_roi,
                    'recommendation': '推奨' if with_roi > without_roi and with_roi > 100 else '見送り'
                })

    return results

def main():
    print("=" * 80)
    print("実装シミュレーション - 2025年データ")
    print("=" * 80)

    df = get_2025_data()
    print(f"\n2025年before予測データ: {len(df):,}件")
    print(f"モーター40%+: {df['motor_40plus'].sum():,}件 ({df['motor_40plus'].mean()*100:.1f}%)")

    # 現状のパフォーマンス
    print("\n" + "=" * 60)
    print("【現在の条件パフォーマンス（2025年）】")
    print("=" * 60)
    current = simulate_current_conditions(df)
    for r in current:
        print(f"{r['condition']}: {r['count']}件, ROI {r['roi']:.1f}%, 収支 {r['profit']:+,.0f}円")

    # モーター条件追加の効果
    print("\n" + "=" * 60)
    print("【モーター40%+追加の効果】")
    print("=" * 60)
    motor_effect = simulate_motor_filter(df)
    print("\n条件 | ベース件数 | ベースROI | モーター件数 | モーターROI | 改善")
    print("-" * 75)
    for r in sorted(motor_effect, key=lambda x: x['roi_improvement'], reverse=True):
        print(f"{r['condition']:12} | {r['base_count']:6} | {r['base_roi']:7.1f}% | {r['motor_count']:6} | {r['motor_roi']:7.1f}% | {r['roi_improvement']:+7.1f}pt")

    # 組み合わせ効果
    print("\n" + "=" * 60)
    print("【既存条件 + モーター40%+の組み合わせ効果】")
    print("=" * 60)
    combined = simulate_combined_effect(df)
    total_profit = 0
    for r in combined:
        print(f"{r['condition']}: {r['count']}件, 的中率 {r['hit_rate']:.1f}%, ROI {r['roi']:.1f}%, 収支 {r['profit']:+,.0f}円")
        total_profit += r['profit']
    print(f"\n合計収支: {total_profit:+,.0f}円")

    # モーターあり/なし比較
    print("\n" + "=" * 60)
    print("【モーター40%+ vs モーター40%未満 直接比較】")
    print("=" * 60)
    comparison = compare_with_and_without_motor(df)
    print("\n条件 | なし件数 | なしROI | あり件数 | ありROI | 改善 | 判定")
    print("-" * 85)
    for r in sorted(comparison, key=lambda x: x['improvement'], reverse=True):
        print(f"{r['condition']:12} | {r['without_motor_count']:6} | {r['without_motor_roi']:7.1f}% | {r['with_motor_count']:6} | {r['with_motor_roi']:7.1f}% | {r['improvement']:+7.1f}pt | {r['recommendation']}")

    # 推奨アクション
    print("\n" + "=" * 80)
    print("【推奨アクション】")
    print("=" * 80)

    # モーター条件で改善が大きいもの
    recommended = [r for r in comparison if r['improvement'] > 50 and r['with_motor_roi'] > 150]
    if recommended:
        print("\n■ 即座に追加可能（改善50pt以上、ROI 150%以上）:")
        for r in recommended:
            print(f"  - {r['condition']} × モーター40%+: ROI {r['without_motor_roi']:.0f}% → {r['with_motor_roi']:.0f}% (+{r['improvement']:.0f}pt)")

    # 注意が必要なもの
    caution = [r for r in comparison if r['improvement'] < 0]
    if caution:
        print("\n■ 注意（モーター条件で悪化）:")
        for r in caution:
            print(f"  - {r['condition']}: ROI {r['without_motor_roi']:.0f}% → {r['with_motor_roi']:.0f}% ({r['improvement']:.0f}pt)")

    return {
        'current': current,
        'motor_effect': motor_effect,
        'combined': combined,
        'comparison': comparison,
    }

if __name__ == "__main__":
    results = main()
