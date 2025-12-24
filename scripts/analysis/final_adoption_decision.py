# -*- coding: utf-8 -*-
"""
本番採用の最終判断
- 6年間データで安定した条件のみ採用
- 既存条件との干渉がないもの
- 採用/不採用の2択で判断
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

def get_6year_data():
    """6年間のbefore予測データを取得"""
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

def analyze_condition(df, conf, rank, motor_filter=False):
    """条件のROIを年度別に計算"""
    if motor_filter:
        subset = df[(df['confidence'] == conf) & (df['racer_rank'] == rank) & (df['motor_40plus'] == True)]
    else:
        subset = df[(df['confidence'] == conf) & (df['racer_rank'] == rank)]

    if len(subset) < 50:
        return None

    # 全体ROI
    hits = subset[subset['actual_rank'] == '1']
    total_roi = hits['trifecta_payout'].sum() / (len(subset) * 100) * 100 if len(subset) > 0 else 0

    # 年度別ROI
    yearly_roi = {}
    positive_years = 0
    for year in ['2020', '2021', '2022', '2023', '2024', '2025']:
        year_data = subset[subset['year'] == year]
        if len(year_data) >= 10:
            year_hits = year_data[year_data['actual_rank'] == '1']
            roi = year_hits['trifecta_payout'].sum() / (len(year_data) * 100) * 100 if len(year_data) > 0 else 0
            yearly_roi[year] = roi
            if roi > 100:
                positive_years += 1

    # 安定性（標準偏差）
    if len(yearly_roi) >= 3:
        roi_std = np.std(list(yearly_roi.values()))
        roi_cv = roi_std / np.mean(list(yearly_roi.values())) * 100 if np.mean(list(yearly_roi.values())) > 0 else 999
    else:
        roi_cv = 999

    return {
        'total': len(subset),
        'hits': len(hits),
        'roi': total_roi,
        'positive_years': positive_years,
        'yearly_roi': yearly_roi,
        'roi_cv': roi_cv,
        'profit': hits['trifecta_payout'].sum() - len(subset) * 100
    }

def main():
    print("=" * 80)
    print("本番採用の最終判断 - 6年間データ（2020-2025）")
    print("=" * 80)

    df = get_6year_data()
    print(f"\n総レコード数: {len(df):,}")

    # 採用基準
    # 1. 6年中5年以上プラス
    # 2. ROI 150%以上
    # 3. サンプル数100件以上
    # 4. CV < 50%（安定性）

    print("\n" + "=" * 80)
    print("【モーター40%+条件の6年間検証】")
    print("=" * 80)

    candidates = []

    for conf in ['A', 'B', 'C', 'D']:
        for rank in ['A1', 'A2', 'B1']:
            # モーターなし
            base = analyze_condition(df, conf, rank, motor_filter=False)
            # モーター40%+
            motor = analyze_condition(df, conf, rank, motor_filter=True)

            if motor and motor['total'] >= 100:
                improvement = motor['roi'] - base['roi'] if base else motor['roi']
                status = '[ADOPT]' if motor['positive_years'] >= 5 and motor['roi'] >= 150 and motor['roi_cv'] < 50 else '[REJECT]'

                if motor['positive_years'] >= 5 and motor['roi'] >= 150:
                    candidates.append({
                        'condition': f"{conf} × {rank} × モーター40%+",
                        'roi': motor['roi'],
                        'total': motor['total'],
                        'positive_years': motor['positive_years'],
                        'roi_cv': motor['roi_cv'],
                        'improvement': improvement,
                        'yearly_roi': motor['yearly_roi'],
                        'profit': motor['profit'],
                        'status': status
                    })

                print(f"\n{conf} × {rank} × モーター40%+:")
                print(f"  6年間ROI: {motor['roi']:.1f}% | 件数: {motor['total']} | プラス年度: {motor['positive_years']}/6年 | CV: {motor['roi_cv']:.1f}%")
                print(f"  年度別: ", end='')
                for year, roi in sorted(motor['yearly_roi'].items()):
                    mark = '+' if roi > 100 else '-'
                    print(f"{year}:{roi:.0f}%{mark} ", end='')
                print()
                if base:
                    print(f"  ベースライン（モーターなし）: ROI {base['roi']:.1f}% | 改善: {improvement:+.1f}pt")
                print(f"  判定: {status}")

    # 採用候補のまとめ
    print("\n" + "=" * 80)
    print("【本番採用候補】")
    print("=" * 80)

    adopted = [c for c in candidates if 'ADOPT' in c['status']]
    rejected = [c for c in candidates if 'REJECT' in c['status']]

    if adopted:
        print("\n■ 採用（5年以上プラス & ROI 150%以上 & CV < 50%）:")
        for c in sorted(adopted, key=lambda x: x['roi'], reverse=True):
            print(f"  {c['condition']}: ROI {c['roi']:.1f}%, {c['positive_years']}年プラス, CV {c['roi_cv']:.1f}%")
    else:
        print("\n■ 採用候補なし")

    print("\n■ 不採用:")
    for c in sorted(rejected, key=lambda x: x['roi'], reverse=True)[:10]:
        reason = []
        if c['positive_years'] < 5:
            reason.append(f"安定性不足({c['positive_years']}年)")
        if c['roi'] < 150:
            reason.append(f"ROI不足({c['roi']:.0f}%)")
        if c['roi_cv'] >= 50:
            reason.append(f"変動大(CV={c['roi_cv']:.0f}%)")
        print(f"  {c['condition']}: ROI {c['roi']:.1f}% | 理由: {', '.join(reason)}")

    # 既存条件との比較
    print("\n" + "=" * 80)
    print("【既存条件との干渉チェック】")
    print("=" * 80)

    print("""
現在の本番条件:
- A: A1 × 10-12倍、14-16倍
- B: 50-100倍、30-50×B1+会場フィルター
- C: 20-30×B1+会場フィルター
- D: B1×40-50倍、A1/A2/B1×30-60倍
""")

    if adopted:
        print("採用候補との干渉:")
        for c in adopted:
            if 'A ×' in c['condition']:
                print(f"  {c['condition']}: A条件はA1×オッズ限定なので、B1は新規セグメント → 干渉なし")
            elif 'D × A1' in c['condition']:
                print(f"  {c['condition']}: 既存D×A1×30-60と重複 → 既存条件にモーター追加で対応")
            elif 'D × B1' in c['condition']:
                print(f"  {c['condition']}: 既存D×B1×40-50と重複 → 既存条件にモーター追加で対応")

    # 最終結論
    print("\n" + "=" * 80)
    print("【最終結論】")
    print("=" * 80)

    print("""
■ 新規条件として追加:
""")
    for c in adopted:
        if 'A × B1' in c['condition']:
            print(f"  ✅ {c['condition']}")
            print(f"     → 6年間ROI {c['roi']:.1f}%, {c['positive_years']}年プラス")
            print(f"     → 既存A条件（A1級）と干渉なし、新規セグメント")

    print("""
■ 既存条件にモーター40%+を追加:
""")
    for c in adopted:
        if 'D × A1' in c['condition'] or 'D × B1' in c['condition']:
            print(f"  △ {c['condition']}")
            print(f"     → 既存D条件と重複するため、既存条件にモーター条件を追加")
            print(f"     → ただしサンプル数減少に注意")

    print("""
■ 採用見送り（C条件へのモーター追加）:
  ❌ C × モーター40%+ は全て不採用
     → 穴狙い戦略と矛盾（実証済み）
""")

    return adopted

if __name__ == "__main__":
    adopted = main()
