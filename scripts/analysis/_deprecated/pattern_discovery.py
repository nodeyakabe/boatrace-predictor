# -*- coding: utf-8 -*-
"""
法則性・パターン発見スクリプト
予測×結果から投資価値のある条件を探索
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

DB_PATH = Path(__file__).parent.parent.parent / 'data' / 'boatrace.db'

def get_conn():
    return sqlite3.connect(str(DB_PATH))

def get_venue_names():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT venue_code, venue_name FROM venue_data')
    result = {row[0]: row[1] for row in cur.fetchall()}
    conn.close()
    return result

def analyze_profitable_patterns():
    """収益性のあるパターンを探索"""
    conn = get_conn()

    # 予測×結果×オッズの統合データ
    df = pd.read_sql_query("""
        SELECT
            r.venue_code,
            substr(r.race_date, 1, 4) as year,
            r.race_date,
            rp.race_id,
            rp.confidence,
            rp.rank_prediction,
            rp.total_score,
            e.racer_rank,
            e.racer_age,
            e.motor_second_rate,
            e.avg_st,
            rd.actual_course,
            rc.wind_speed,
            rc.wind_direction,
            rc.wave_height,
            res.rank as actual_rank,
            res.kimarite,
            p.amount as trifecta_payout
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        JOIN entries e ON rp.race_id = e.race_id AND rp.pit_number = e.pit_number
        LEFT JOIN race_details rd ON rp.race_id = rd.race_id AND rp.pit_number = rd.pit_number
        LEFT JOIN race_conditions rc ON rp.race_id = rc.race_id
        JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
        LEFT JOIN payouts p ON rp.race_id = p.race_id AND p.bet_type = 'trifecta'
        WHERE rp.prediction_type = 'before'
          AND substr(r.race_date, 1, 4) >= '2020'
          AND res.is_invalid = 0
          AND rp.rank_prediction = 1
    """, conn)

    conn.close()
    return df

def calculate_roi(df, investment=100):
    """ROI計算"""
    if len(df) == 0:
        return 0, 0, 0
    hits = df[df['actual_rank'] == '1']
    hit_count = len(hits)
    total_investment = len(df) * investment
    total_return = hits['trifecta_payout'].sum() if hit_count > 0 else 0
    roi = (total_return / total_investment * 100) if total_investment > 0 else 0
    return roi, hit_count, len(df)

def find_all_patterns(df):
    """すべてのパターンを探索"""
    patterns = []
    venue_names = get_venue_names()

    # 1. 会場×信頼度×級別
    print("パターン探索: 会場×信頼度×級別...")
    for venue in df['venue_code'].unique():
        for conf in ['A', 'B', 'C', 'D']:
            for rank in ['A1', 'A2', 'B1', 'B2']:
                subset = df[(df['venue_code'] == venue) &
                           (df['confidence'] == conf) &
                           (df['racer_rank'] == rank)]
                if len(subset) >= 30:
                    roi, hits, total = calculate_roi(subset)
                    if roi > 100:  # プラスのみ記録
                        patterns.append({
                            'type': 'venue_conf_rank',
                            'venue': venue,
                            'venue_name': venue_names.get(venue, venue),
                            'confidence': conf,
                            'racer_rank': rank,
                            'roi': roi,
                            'hits': hits,
                            'total': total,
                            'hit_rate': hits / total * 100 if total > 0 else 0
                        })

    # 2. 会場×風速カテゴリ
    print("パターン探索: 会場×風速...")
    df['wind_cat'] = pd.cut(
        df['wind_speed'].fillna(0),
        bins=[-1, 2, 4, 6, 100],
        labels=['0-2m', '2-4m', '4-6m', '6m+']
    )

    for venue in df['venue_code'].unique():
        for wind in ['0-2m', '2-4m', '4-6m', '6m+']:
            for conf in ['A', 'B', 'C', 'D']:
                subset = df[(df['venue_code'] == venue) &
                           (df['wind_cat'] == wind) &
                           (df['confidence'] == conf)]
                if len(subset) >= 30:
                    roi, hits, total = calculate_roi(subset)
                    if roi > 120:  # 高ROIのみ
                        patterns.append({
                            'type': 'venue_wind_conf',
                            'venue': venue,
                            'venue_name': venue_names.get(venue, venue),
                            'wind': wind,
                            'confidence': conf,
                            'roi': roi,
                            'hits': hits,
                            'total': total,
                            'hit_rate': hits / total * 100 if total > 0 else 0
                        })

    # 3. 会場×年齢帯
    print("パターン探索: 会場×年齢帯...")
    df['age_cat'] = pd.cut(
        df['racer_age'].fillna(35),
        bins=[0, 30, 40, 50, 100],
        labels=['~30', '31-40', '41-50', '51+']
    )

    for venue in df['venue_code'].unique():
        for age in ['~30', '31-40', '41-50', '51+']:
            for conf in ['A', 'B', 'C', 'D']:
                subset = df[(df['venue_code'] == venue) &
                           (df['age_cat'] == age) &
                           (df['confidence'] == conf)]
                if len(subset) >= 30:
                    roi, hits, total = calculate_roi(subset)
                    if roi > 120:
                        patterns.append({
                            'type': 'venue_age_conf',
                            'venue': venue,
                            'venue_name': venue_names.get(venue, venue),
                            'age': age,
                            'confidence': conf,
                            'roi': roi,
                            'hits': hits,
                            'total': total,
                            'hit_rate': hits / total * 100 if total > 0 else 0
                        })

    # 4. 会場×モーター2連率
    print("パターン探索: 会場×モーター...")
    df['motor_cat'] = pd.cut(
        df['motor_second_rate'].fillna(35),
        bins=[0, 30, 35, 40, 100],
        labels=['~30%', '30-35%', '35-40%', '40%+']
    )

    for venue in df['venue_code'].unique():
        for motor in ['~30%', '30-35%', '35-40%', '40%+']:
            for conf in ['A', 'B', 'C', 'D']:
                subset = df[(df['venue_code'] == venue) &
                           (df['motor_cat'] == motor) &
                           (df['confidence'] == conf)]
                if len(subset) >= 30:
                    roi, hits, total = calculate_roi(subset)
                    if roi > 120:
                        patterns.append({
                            'type': 'venue_motor_conf',
                            'venue': venue,
                            'venue_name': venue_names.get(venue, venue),
                            'motor': motor,
                            'confidence': conf,
                            'roi': roi,
                            'hits': hits,
                            'total': total,
                            'hit_rate': hits / total * 100 if total > 0 else 0
                        })

    # 5. 複合条件（会場×信頼度×級別×モーター）
    print("パターン探索: 複合条件...")
    for venue in df['venue_code'].unique():
        for conf in ['A', 'B', 'C', 'D']:
            for rank in ['A1', 'A2', 'B1', 'B2']:
                for motor in ['40%+']:  # 好調モーターのみ
                    subset = df[(df['venue_code'] == venue) &
                               (df['confidence'] == conf) &
                               (df['racer_rank'] == rank) &
                               (df['motor_cat'] == motor)]
                    if len(subset) >= 20:
                        roi, hits, total = calculate_roi(subset)
                        if roi > 150:
                            patterns.append({
                                'type': 'complex',
                                'venue': venue,
                                'venue_name': venue_names.get(venue, venue),
                                'confidence': conf,
                                'racer_rank': rank,
                                'motor': motor,
                                'roi': roi,
                                'hits': hits,
                                'total': total,
                                'hit_rate': hits / total * 100 if total > 0 else 0
                            })

    return patterns

def analyze_yearly_stability(df, patterns):
    """年度間の安定性を検証"""
    stable_patterns = []

    for p in patterns:
        # パターンに該当するデータを抽出
        if p['type'] == 'venue_conf_rank':
            subset = df[(df['venue_code'] == p['venue']) &
                       (df['confidence'] == p['confidence']) &
                       (df['racer_rank'] == p['racer_rank'])]
        elif p['type'] == 'venue_wind_conf':
            subset = df[(df['venue_code'] == p['venue']) &
                       (df['wind_cat'] == p['wind']) &
                       (df['confidence'] == p['confidence'])]
        elif p['type'] == 'venue_age_conf':
            subset = df[(df['venue_code'] == p['venue']) &
                       (df['age_cat'] == p['age']) &
                       (df['confidence'] == p['confidence'])]
        elif p['type'] == 'venue_motor_conf':
            subset = df[(df['venue_code'] == p['venue']) &
                       (df['motor_cat'] == p['motor']) &
                       (df['confidence'] == p['confidence'])]
        else:
            continue

        # 年度別ROI
        yearly_roi = {}
        positive_years = 0
        for year in ['2020', '2021', '2022', '2023', '2024', '2025']:
            year_data = subset[subset['year'] == year]
            if len(year_data) >= 10:
                roi, hits, total = calculate_roi(year_data)
                yearly_roi[year] = roi
                if roi > 100:
                    positive_years += 1

        # 4年以上プラスなら安定パターン
        if positive_years >= 4:
            p['yearly_roi'] = yearly_roi
            p['positive_years'] = positive_years
            stable_patterns.append(p)

    return stable_patterns

def main():
    print("=" * 80)
    print("法則性・パターン発見分析")
    print("=" * 80)

    print("\nデータ読み込み中...")
    df = analyze_profitable_patterns()
    print(f"総レコード数: {len(df):,}")

    print("\nパターン探索中...")
    patterns = find_all_patterns(df)
    print(f"発見パターン数: {len(patterns)}")

    print("\n年度間安定性検証中...")
    stable_patterns = analyze_yearly_stability(df, patterns)
    print(f"安定パターン数: {len(stable_patterns)}")

    # 結果表示
    print("\n" + "=" * 80)
    print("【高ROIパターン TOP20】")
    print("=" * 80)

    top_patterns = sorted(patterns, key=lambda x: x['roi'], reverse=True)[:20]
    for i, p in enumerate(top_patterns, 1):
        print(f"\n{i}. {p['venue_name']} - {p['type']}")
        if p['type'] == 'venue_conf_rank':
            print(f"   条件: 信頼度{p['confidence']} × {p['racer_rank']}")
        elif p['type'] == 'venue_wind_conf':
            print(f"   条件: 風速{p['wind']} × 信頼度{p['confidence']}")
        elif p['type'] == 'venue_age_conf':
            print(f"   条件: 年齢{p['age']} × 信頼度{p['confidence']}")
        elif p['type'] == 'venue_motor_conf':
            print(f"   条件: モーター{p['motor']} × 信頼度{p['confidence']}")
        elif p['type'] == 'complex':
            print(f"   条件: 信頼度{p['confidence']} × {p['racer_rank']} × モーター{p['motor']}")
        print(f"   ROI: {p['roi']:.1f}% | 的中: {p['hits']}/{p['total']} ({p['hit_rate']:.1f}%)")

    print("\n" + "=" * 80)
    print("【年度間安定パターン（4年以上プラス）】")
    print("=" * 80)

    for i, p in enumerate(sorted(stable_patterns, key=lambda x: x['roi'], reverse=True), 1):
        print(f"\n{i}. {p['venue_name']} - {p['type']}")
        if p['type'] == 'venue_conf_rank':
            print(f"   条件: 信頼度{p['confidence']} × {p['racer_rank']}")
        elif p['type'] == 'venue_wind_conf':
            print(f"   条件: 風速{p['wind']} × 信頼度{p['confidence']}")
        elif p['type'] == 'venue_age_conf':
            print(f"   条件: 年齢{p['age']} × 信頼度{p['confidence']}")
        elif p['type'] == 'venue_motor_conf':
            print(f"   条件: モーター{p['motor']} × 信頼度{p['confidence']}")
        print(f"   6年ROI: {p['roi']:.1f}% | プラス年度: {p['positive_years']}年")
        print(f"   年度別: ", end='')
        for year, roi in sorted(p.get('yearly_roi', {}).items()):
            marker = '★' if roi > 100 else ' '
            print(f"{year}:{roi:.0f}%{marker} ", end='')
        print()

    return patterns, stable_patterns

if __name__ == "__main__":
    patterns, stable = main()
