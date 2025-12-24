# -*- coding: utf-8 -*-
"""
会場別完全分析スクリプト
24会場×6年間の環境・選手・コース・オッズの深掘り分析
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
import json
from datetime import datetime
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')

DB_PATH = Path(__file__).parent.parent.parent / 'data' / 'boatrace.db'

def get_conn():
    return sqlite3.connect(str(DB_PATH))

# ==============================================================================
# 1. 環境要因分析（風向・風速・波高・潮位）
# ==============================================================================

def analyze_wind_impact():
    """風向・風速がコース別勝率に与える影響を分析"""
    conn = get_conn()

    # 風向を数値化（追い風/向かい風判定用）
    wind_direction_map = {
        '北': 'headwind', '北北東': 'headwind', '北東': 'headwind', '東北東': 'headwind',
        '東': 'cross', '東南東': 'tailwind', '南東': 'tailwind', '南南東': 'tailwind',
        '南': 'tailwind', '南南西': 'tailwind', '南西': 'tailwind', '西南西': 'tailwind',
        '西': 'cross', '西北西': 'headwind', '北西': 'headwind', '北北西': 'headwind',
        '向い風': 'headwind', '追い風': 'tailwind'
    }

    df = pd.read_sql_query("""
        SELECT
            r.venue_code,
            substr(r.race_date, 1, 4) as year,
            rc.wind_direction,
            rc.wind_speed,
            rc.wave_height,
            rd.actual_course as winner_course,
            res.kimarite,
            e.racer_rank as winner_rank,
            p.amount as trifecta_payout
        FROM races r
        JOIN race_conditions rc ON r.id = rc.race_id
        JOIN results res ON r.id = res.race_id AND res.rank = '1'
        JOIN race_details rd ON r.id = rd.race_id AND res.pit_number = rd.pit_number
        JOIN entries e ON r.id = e.race_id AND res.pit_number = e.pit_number
        LEFT JOIN payouts p ON r.id = p.race_id AND p.bet_type = 'trifecta'
        WHERE substr(r.race_date, 1, 4) >= '2020'
          AND res.is_invalid = 0
          AND rd.actual_course IS NOT NULL
    """, conn)
    conn.close()

    # 風速カテゴリ
    df['wind_category'] = pd.cut(
        df['wind_speed'].fillna(0),
        bins=[-1, 2, 4, 6, 100],
        labels=['0-2m', '2-4m', '4-6m', '6m+']
    )

    # 波高カテゴリ
    df['wave_category'] = pd.cut(
        df['wave_height'].fillna(0),
        bins=[-1, 2, 5, 100],
        labels=['0-2cm', '2-5cm', '5cm+']
    )

    return df

def analyze_wind_by_venue(df):
    """会場別×風向・風速別の1コース勝率"""
    results = {}

    for venue in sorted(df['venue_code'].unique()):
        venue_df = df[df['venue_code'] == venue]
        venue_results = {
            'total_races': len(venue_df),
            'course1_rate': (venue_df['winner_course'] == 1).mean() * 100,
            'by_wind_speed': {},
            'by_wind_direction': {}
        }

        # 風速別
        for cat in ['0-2m', '2-4m', '4-6m', '6m+']:
            cat_df = venue_df[venue_df['wind_category'] == cat]
            if len(cat_df) > 0:
                venue_results['by_wind_speed'][cat] = {
                    'races': len(cat_df),
                    'course1_rate': (cat_df['winner_course'] == 1).mean() * 100,
                    'course456_rate': (cat_df['winner_course'] >= 4).mean() * 100
                }

        # 波高別
        for cat in ['0-2cm', '2-5cm', '5cm+']:
            cat_df = venue_df[venue_df['wave_category'] == cat]
            if len(cat_df) > 0:
                venue_results['by_wave'] = venue_results.get('by_wave', {})
                venue_results['by_wave'][cat] = {
                    'races': len(cat_df),
                    'course1_rate': (cat_df['winner_course'] == 1).mean() * 100
                }

        results[venue] = venue_results

    return results

# ==============================================================================
# 2. 選手要因分析（地元・年齢・級別）
# ==============================================================================

def analyze_racer_factors():
    """選手要因がレース結果に与える影響"""
    conn = get_conn()

    df = pd.read_sql_query("""
        SELECT
            r.venue_code,
            substr(r.race_date, 1, 4) as year,
            e.pit_number,
            e.racer_rank,
            e.racer_home,
            e.racer_age,
            e.win_rate,
            e.motor_second_rate,
            e.avg_st,
            rd.actual_course,
            res.rank as result_rank,
            res.kimarite
        FROM entries e
        JOIN races r ON e.race_id = r.id
        JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
        LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
        WHERE substr(r.race_date, 1, 4) >= '2020'
          AND res.is_invalid = 0
    """, conn)
    conn.close()

    return df

def analyze_local_racer_advantage(df):
    """地元選手のアドバンテージ分析"""
    # 会場コードと都道府県のマッピング
    venue_home_map = {
        '01': ['群馬'],  # 桐生
        '02': ['埼玉'],  # 戸田
        '03': ['東京'],  # 江戸川
        '04': ['静岡'],  # 浜名湖
        '05': ['愛知'],  # 蒲郡
        '06': ['静岡'],  # 浜名湖
        '07': ['静岡'],  # 蒲郡
        '08': ['愛知'],  # 常滑
        '09': ['三重'],  # 津
        '10': ['福井'],  # 三国
        '11': ['滋賀'],  # びわこ
        '12': ['大阪'],  # 住之江
        '13': ['兵庫'],  # 尼崎
        '14': ['兵庫'],  # 鳴門
        '15': ['香川'],  # 丸亀
        '16': ['岡山'],  # 児島
        '17': ['広島'],  # 宮島
        '18': ['山口'],  # 徳山
        '19': ['山口'],  # 下関
        '20': ['福岡'],  # 若松
        '21': ['福岡'],  # 芦屋
        '22': ['福岡'],  # 福岡
        '23': ['佐賀'],  # 唐津
        '24': ['長崎'],  # 大村
    }

    results = {}
    for venue, homes in venue_home_map.items():
        venue_df = df[df['venue_code'] == venue]
        if len(venue_df) == 0:
            continue

        # 地元選手の判定
        is_local = venue_df['racer_home'].apply(lambda x: any(h in str(x) for h in homes) if pd.notna(x) else False)

        local_df = venue_df[is_local]
        away_df = venue_df[~is_local]

        if len(local_df) > 0 and len(away_df) > 0:
            results[venue] = {
                'local_races': len(local_df),
                'away_races': len(away_df),
                'local_win_rate': (local_df['result_rank'] == '1').mean() * 100,
                'away_win_rate': (away_df['result_rank'] == '1').mean() * 100,
                'local_in3_rate': (local_df['result_rank'].isin(['1', '2', '3'])).mean() * 100,
                'away_in3_rate': (away_df['result_rank'].isin(['1', '2', '3'])).mean() * 100,
            }

    return results

def analyze_age_impact(df):
    """年齢がレース結果に与える影響"""
    # 年齢カテゴリ
    df['age_category'] = pd.cut(
        df['racer_age'].fillna(35),
        bins=[0, 25, 30, 35, 40, 45, 50, 100],
        labels=['~25', '26-30', '31-35', '36-40', '41-45', '46-50', '51+']
    )

    results = {}
    for venue in sorted(df['venue_code'].unique()):
        venue_df = df[df['venue_code'] == venue]
        venue_results = {}

        for age in ['~25', '26-30', '31-35', '36-40', '41-45', '46-50', '51+']:
            age_df = venue_df[venue_df['age_category'] == age]
            if len(age_df) >= 100:
                venue_results[age] = {
                    'races': len(age_df),
                    'win_rate': (age_df['result_rank'] == '1').mean() * 100,
                    'in3_rate': (age_df['result_rank'].isin(['1', '2', '3'])).mean() * 100
                }

        results[venue] = venue_results

    return results

def analyze_rank_impact(df):
    """級別がレース結果に与える影響"""
    results = {}

    for venue in sorted(df['venue_code'].unique()):
        venue_df = df[df['venue_code'] == venue]
        venue_results = {}

        for rank in ['A1', 'A2', 'B1', 'B2']:
            rank_df = venue_df[venue_df['racer_rank'] == rank]
            if len(rank_df) >= 100:
                venue_results[rank] = {
                    'races': len(rank_df),
                    'win_rate': (rank_df['result_rank'] == '1').mean() * 100,
                    'in3_rate': (rank_df['result_rank'].isin(['1', '2', '3'])).mean() * 100
                }

        results[venue] = venue_results

    return results

# ==============================================================================
# 3. コース・決まり手分析
# ==============================================================================

def analyze_course_kimarite():
    """コース別×決まり手別の分析"""
    conn = get_conn()

    df = pd.read_sql_query("""
        SELECT
            r.venue_code,
            substr(r.race_date, 1, 4) as year,
            rd.actual_course as winner_course,
            res.kimarite,
            COUNT(*) as count
        FROM races r
        JOIN results res ON r.id = res.race_id AND res.rank = '1'
        JOIN race_details rd ON r.id = rd.race_id AND res.pit_number = rd.pit_number
        WHERE substr(r.race_date, 1, 4) >= '2020'
          AND res.is_invalid = 0
          AND rd.actual_course IS NOT NULL
          AND res.kimarite IS NOT NULL
        GROUP BY r.venue_code, year, rd.actual_course, res.kimarite
    """, conn)
    conn.close()

    return df

def analyze_course_rates_by_venue(df):
    """会場別コース勝率"""
    results = {}

    for venue in sorted(df['venue_code'].unique()):
        venue_df = df[df['venue_code'] == venue]
        total = venue_df['count'].sum()

        venue_results = {'total': total, 'courses': {}}
        for course in range(1, 7):
            course_df = venue_df[venue_df['winner_course'] == course]
            course_total = course_df['count'].sum()
            venue_results['courses'][course] = {
                'rate': course_total / total * 100 if total > 0 else 0,
                'kimarite': {}
            }

            # 決まり手別
            for _, row in course_df.iterrows():
                venue_results['courses'][course]['kimarite'][row['kimarite']] = row['count']

        results[venue] = venue_results

    return results

# ==============================================================================
# 4. オッズ・払戻分析
# ==============================================================================

def analyze_payout_patterns():
    """払戻パターン分析"""
    conn = get_conn()

    df = pd.read_sql_query("""
        SELECT
            r.venue_code,
            substr(r.race_date, 1, 4) as year,
            p.amount as payout,
            p.popularity,
            res.pit_number as winner_pit
        FROM payouts p
        JOIN races r ON p.race_id = r.id
        JOIN results res ON p.race_id = res.race_id AND res.rank = '1'
        WHERE p.bet_type = 'trifecta'
          AND substr(r.race_date, 1, 4) >= '2020'
          AND res.is_invalid = 0
    """, conn)
    conn.close()

    return df

def analyze_odds_distribution_by_venue(df):
    """会場別オッズ分布"""
    results = {}

    # オッズ帯を定義（100円換算）
    df['odds'] = df['payout'] / 100

    for venue in sorted(df['venue_code'].unique()):
        venue_df = df[df['venue_code'] == venue]

        results[venue] = {
            'total_races': len(venue_df),
            'avg_payout': venue_df['payout'].mean(),
            'median_payout': venue_df['payout'].median(),
            'odds_distribution': {
                '~10x': (venue_df['odds'] < 10).mean() * 100,
                '10-20x': ((venue_df['odds'] >= 10) & (venue_df['odds'] < 20)).mean() * 100,
                '20-30x': ((venue_df['odds'] >= 20) & (venue_df['odds'] < 30)).mean() * 100,
                '30-50x': ((venue_df['odds'] >= 30) & (venue_df['odds'] < 50)).mean() * 100,
                '50-100x': ((venue_df['odds'] >= 50) & (venue_df['odds'] < 100)).mean() * 100,
                '100x+': (venue_df['odds'] >= 100).mean() * 100
            },
            'high_payout_rate': (venue_df['payout'] >= 10000).mean() * 100
        }

    return results

# ==============================================================================
# 5. 予測精度分析
# ==============================================================================

def analyze_prediction_accuracy():
    """予測精度の分析"""
    conn = get_conn()

    # advance予測の精度
    advance_df = pd.read_sql_query("""
        SELECT
            r.venue_code,
            substr(r.race_date, 1, 4) as year,
            rp.confidence,
            rp.rank_prediction,
            res.rank as actual_rank,
            CASE WHEN rp.rank_prediction = 1 AND res.rank = '1' THEN 1 ELSE 0 END as first_hit,
            p.amount as trifecta_payout
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
        LEFT JOIN payouts p ON rp.race_id = p.race_id AND p.bet_type = 'trifecta'
        WHERE rp.prediction_type = 'advance'
          AND substr(r.race_date, 1, 4) >= '2020'
          AND res.is_invalid = 0
    """, conn)

    # before予測の精度
    before_df = pd.read_sql_query("""
        SELECT
            r.venue_code,
            substr(r.race_date, 1, 4) as year,
            rp.confidence,
            rp.rank_prediction,
            res.rank as actual_rank,
            CASE WHEN rp.rank_prediction = 1 AND res.rank = '1' THEN 1 ELSE 0 END as first_hit,
            p.amount as trifecta_payout
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
        LEFT JOIN payouts p ON rp.race_id = p.race_id AND p.bet_type = 'trifecta'
        WHERE rp.prediction_type = 'before'
          AND substr(r.race_date, 1, 4) >= '2020'
          AND res.is_invalid = 0
    """, conn)

    conn.close()
    return advance_df, before_df

def analyze_prediction_by_venue(advance_df, before_df):
    """会場別予測精度"""
    results = {}

    for venue in sorted(advance_df['venue_code'].unique()):
        adv_venue = advance_df[advance_df['venue_code'] == venue]
        bef_venue = before_df[before_df['venue_code'] == venue]

        # 1着予測のみ抽出
        adv_first = adv_venue[adv_venue['rank_prediction'] == 1]
        bef_first = bef_venue[bef_venue['rank_prediction'] == 1]

        results[venue] = {
            'advance': {
                'total': len(adv_first),
                'first_accuracy': adv_first['first_hit'].mean() * 100 if len(adv_first) > 0 else 0,
                'by_confidence': {}
            },
            'before': {
                'total': len(bef_first),
                'first_accuracy': bef_first['first_hit'].mean() * 100 if len(bef_first) > 0 else 0,
                'by_confidence': {}
            }
        }

        # 信頼度別精度
        for conf in ['A', 'B', 'C', 'D', 'E']:
            adv_conf = adv_first[adv_first['confidence'] == conf]
            bef_conf = bef_first[bef_first['confidence'] == conf]

            if len(adv_conf) >= 30:
                results[venue]['advance']['by_confidence'][conf] = {
                    'races': len(adv_conf),
                    'accuracy': adv_conf['first_hit'].mean() * 100
                }
            if len(bef_conf) >= 30:
                results[venue]['before']['by_confidence'][conf] = {
                    'races': len(bef_conf),
                    'accuracy': bef_conf['first_hit'].mean() * 100
                }

    return results

# ==============================================================================
# 6. 法則性探索
# ==============================================================================

def find_patterns(wind_df, racer_df, course_df, payout_df, advance_df, before_df):
    """法則性・パターンの探索"""
    patterns = []

    # パターン1: 強風時の外コース有利
    print("\n=== 法則性探索 ===")

    # 風速6m以上で4-6コース勝率が高い会場
    strong_wind = wind_df[wind_df['wind_category'] == '6m+']
    for venue in strong_wind['venue_code'].unique():
        venue_sw = strong_wind[strong_wind['venue_code'] == venue]
        if len(venue_sw) >= 50:
            outer_rate = (venue_sw['winner_course'] >= 4).mean() * 100
            if outer_rate > 30:  # 通常の2倍以上
                patterns.append({
                    'type': 'strong_wind_outer',
                    'venue': venue,
                    'condition': 'wind >= 6m',
                    'effect': f'outer course (4-6) win rate: {outer_rate:.1f}%',
                    'sample_size': len(venue_sw)
                })

    # パターン2: A1級×1コースの高勝率会場
    for venue in racer_df['venue_code'].unique():
        venue_df = racer_df[(racer_df['venue_code'] == venue) &
                           (racer_df['racer_rank'] == 'A1') &
                           (racer_df['actual_course'] == 1)]
        if len(venue_df) >= 100:
            win_rate = (venue_df['result_rank'] == '1').mean() * 100
            if win_rate > 70:  # 70%以上
                patterns.append({
                    'type': 'a1_course1_dominant',
                    'venue': venue,
                    'condition': 'A1 rank + Course 1',
                    'effect': f'win rate: {win_rate:.1f}%',
                    'sample_size': len(venue_df)
                })

    # パターン3: 高齢選手（50歳以上）が活躍する会場
    for venue in racer_df['venue_code'].unique():
        venue_df = racer_df[(racer_df['venue_code'] == venue) &
                           (racer_df['racer_age'] >= 50)]
        if len(venue_df) >= 100:
            win_rate = (venue_df['result_rank'] == '1').mean() * 100
            if win_rate > 18:  # 期待値(16.7%)より高い
                patterns.append({
                    'type': 'veteran_advantage',
                    'venue': venue,
                    'condition': 'age >= 50',
                    'effect': f'win rate: {win_rate:.1f}%',
                    'sample_size': len(venue_df)
                })

    # パターン4: 高配当が出やすい会場
    for venue in payout_df['venue_code'].unique():
        venue_df = payout_df[payout_df['venue_code'] == venue]
        if len(venue_df) >= 500:
            high_payout_rate = (venue_df['payout'] >= 10000).mean() * 100
            if high_payout_rate > 35:
                patterns.append({
                    'type': 'high_payout_venue',
                    'venue': venue,
                    'condition': 'normal',
                    'effect': f'10000yen+ payout rate: {high_payout_rate:.1f}%',
                    'sample_size': len(venue_df)
                })

    return patterns

# ==============================================================================
# メイン実行
# ==============================================================================

def main():
    print("=" * 80)
    print("会場別完全分析 - 24会場×6年間")
    print("=" * 80)

    # 会場名マッピング
    conn = get_conn()
    venue_names = pd.read_sql_query(
        "SELECT venue_code, venue_name FROM venue_data",
        conn
    ).set_index('venue_code')['venue_name'].to_dict()
    conn.close()

    # 1. 環境要因分析
    print("\n【1】環境要因分析...")
    wind_df = analyze_wind_impact()
    wind_results = analyze_wind_by_venue(wind_df)
    print(f"  レース数: {len(wind_df)}")

    # 2. 選手要因分析
    print("\n【2】選手要因分析...")
    racer_df = analyze_racer_factors()
    local_results = analyze_local_racer_advantage(racer_df)
    age_results = analyze_age_impact(racer_df)
    rank_results = analyze_rank_impact(racer_df)
    print(f"  エントリー数: {len(racer_df)}")

    # 3. コース・決まり手分析
    print("\n【3】コース・決まり手分析...")
    course_df = analyze_course_kimarite()
    course_results = analyze_course_rates_by_venue(course_df)
    print(f"  レコード数: {len(course_df)}")

    # 4. オッズ・払戻分析
    print("\n【4】オッズ・払戻分析...")
    payout_df = analyze_payout_patterns()
    odds_results = analyze_odds_distribution_by_venue(payout_df)
    print(f"  レコード数: {len(payout_df)}")

    # 5. 予測精度分析
    print("\n【5】予測精度分析...")
    advance_df, before_df = analyze_prediction_accuracy()
    pred_results = analyze_prediction_by_venue(advance_df, before_df)
    print(f"  advance: {len(advance_df)}, before: {len(before_df)}")

    # 6. 法則性探索
    print("\n【6】法則性探索...")
    patterns = find_patterns(wind_df, racer_df, course_df, payout_df, advance_df, before_df)
    print(f"  発見パターン数: {len(patterns)}")

    # 結果を整形して出力
    all_results = {
        'venue_names': venue_names,
        'wind': wind_results,
        'local': local_results,
        'age': age_results,
        'rank': rank_results,
        'course': course_results,
        'odds': odds_results,
        'prediction': pred_results,
        'patterns': patterns
    }

    # JSON出力
    output_path = Path(__file__).parent.parent.parent / 'data' / 'venue_analysis_results.json'

    # NumPy型をPython型に変換
    def convert_numpy(obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, dict):
            return {k: convert_numpy(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_numpy(i) for i in obj]
        return obj

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(convert_numpy(all_results), f, ensure_ascii=False, indent=2)

    print(f"\n結果保存: {output_path}")

    return all_results

if __name__ == "__main__":
    results = main()

    # サマリー出力
    print("\n" + "=" * 80)
    print("分析結果サマリー")
    print("=" * 80)

    venue_names = results['venue_names']

    # 風による影響が大きい会場
    print("\n【風の影響が大きい会場】")
    for venue, data in results['wind'].items():
        if '6m+' in data['by_wind_speed']:
            strong = data['by_wind_speed']['6m+']
            weak = data['by_wind_speed'].get('0-2m', {})
            if strong.get('races', 0) >= 50 and weak.get('races', 0) >= 100:
                diff = strong['course1_rate'] - weak.get('course1_rate', 0)
                if abs(diff) > 10:
                    name = venue_names.get(venue, venue)
                    print(f"  {name}: 強風時1コース率 {strong['course1_rate']:.1f}% (弱風比 {diff:+.1f}pt)")

    # 地元有利な会場
    print("\n【地元選手有利な会場】")
    for venue, data in sorted(results['local'].items(),
                              key=lambda x: x[1]['local_win_rate'] - x[1]['away_win_rate'],
                              reverse=True)[:5]:
        name = venue_names.get(venue, venue)
        diff = data['local_win_rate'] - data['away_win_rate']
        print(f"  {name}: 地元勝率 {data['local_win_rate']:.1f}% (非地元比 +{diff:.1f}pt)")

    # 高配当が出やすい会場
    print("\n【高配当(1万円以上)が出やすい会場】")
    for venue, data in sorted(results['odds'].items(),
                              key=lambda x: x[1]['high_payout_rate'],
                              reverse=True)[:5]:
        name = venue_names.get(venue, venue)
        print(f"  {name}: 1万円以上率 {data['high_payout_rate']:.1f}%")

    # 発見したパターン
    print("\n【発見した法則性】")
    for p in results['patterns']:
        name = venue_names.get(p['venue'], p['venue'])
        print(f"  [{p['type']}] {name}: {p['condition']} -> {p['effect']} (n={p['sample_size']})")
