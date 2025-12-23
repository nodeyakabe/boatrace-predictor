# -*- coding: utf-8 -*-
"""
2025年 信頼度B BEFORE予測データ 環境要因分析スクリプト

目的: 的中率が異常に低下する環境要因の複合パターンを発見する
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')

# データベースパス
DB_PATH = Path(__file__).parent.parent / "data" / "boatrace.db"


def get_connection():
    """データベース接続"""
    return sqlite3.connect(str(DB_PATH))


def load_prediction_data():
    """2025年信頼度B BEFORE予測データをロード"""
    conn = get_connection()

    query = """
    SELECT
        p.race_id,
        p.pit_number,
        p.rank_prediction,
        p.total_score,
        p.racer_name,
        r.venue_code,
        r.race_date,
        r.race_time,
        r.race_number,
        r.race_grade,
        r.is_nighter,
        r.is_ladies,
        rc.weather,
        rc.wind_direction,
        rc.wind_speed,
        rc.wave_height,
        rc.temperature,
        rc.water_temperature,
        res.rank as actual_rank,
        res.kimarite,
        vs.tide_impact,
        vs.water_type,
        vs.name as venue_name,
        vd.course_1_win_rate
    FROM race_predictions p
    JOIN races r ON p.race_id = r.id
    LEFT JOIN race_conditions rc ON p.race_id = rc.race_id
    LEFT JOIN results res ON p.race_id = res.race_id AND p.pit_number = res.pit_number
    LEFT JOIN venue_strategies vs ON r.venue_code = vs.venue_code
    LEFT JOIN venue_data vd ON r.venue_code = vd.venue_code
    WHERE p.prediction_type = 'before'
      AND p.confidence = 'B'
      AND r.race_date LIKE '2025%'
      AND res.rank IS NOT NULL
      AND res.is_invalid = 0
    ORDER BY p.race_id, p.rank_prediction
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    print(f"ロードしたデータ件数: {len(df)}")
    print(f"ユニークレース数: {df['race_id'].nunique()}")

    return df


def calculate_hit_rate(df, pred_rank=1):
    """的中率を計算（1着予想に対して）"""
    pred_1st = df[df['rank_prediction'] == pred_rank]
    if len(pred_1st) == 0:
        return None, 0
    hits = (pred_1st['actual_rank'].astype(str) == '1').sum()
    return hits / len(pred_1st), len(pred_1st)


def categorize_time(time_str):
    """レース時間を時間帯にカテゴリ化"""
    if pd.isna(time_str):
        return 'unknown'
    try:
        hour = int(time_str.split(':')[0])
        if hour < 10:
            return 'morning_early'  # 早朝 (8-10時)
        elif hour < 13:
            return 'morning_late'   # 午前 (10-13時)
        elif hour < 16:
            return 'afternoon'      # 午後 (13-16時)
        else:
            return 'evening'        # 夕方以降 (16時～)
    except:
        return 'unknown'


def categorize_wind(wind_dir):
    """風向を向かい風/追い風/横風にカテゴリ化"""
    if pd.isna(wind_dir):
        return 'unknown'

    # 一般的に、向い風（スタート方向に対して）はインコースに不利
    if '向' in str(wind_dir):
        return 'headwind'  # 向かい風
    elif '追' in str(wind_dir):
        return 'tailwind'  # 追い風
    elif any(x in str(wind_dir) for x in ['東', '西']):
        return 'crosswind' # 横風
    elif any(x in str(wind_dir) for x in ['北', '南']):
        return 'longitudinal'  # 縦方向
    else:
        return 'other'


def categorize_wind_speed(speed):
    """風速をカテゴリ化"""
    if pd.isna(speed):
        return 'unknown'
    if speed <= 2:
        return 'calm'      # 穏やか
    elif speed <= 4:
        return 'moderate'  # 中程度
    elif speed <= 6:
        return 'strong'    # 強風
    else:
        return 'very_strong'  # 非常に強い


def categorize_wave(wave):
    """波高をカテゴリ化"""
    if pd.isna(wave):
        return 'unknown'
    if wave <= 2:
        return 'calm'      # 穏やか
    elif wave <= 5:
        return 'moderate'  # 中程度
    elif wave <= 10:
        return 'rough'     # 荒れ
    else:
        return 'very_rough'  # 非常に荒れ


def analyze_single_factors(df):
    """単一要因での的中率分析"""
    print("\n" + "="*80)
    print("【単一要因分析】")
    print("="*80)

    results = []

    # 会場別
    print("\n--- 会場別的中率 ---")
    for venue_code in sorted(df['venue_code'].unique()):
        venue_df = df[df['venue_code'] == venue_code]
        hit_rate, n = calculate_hit_rate(venue_df)
        venue_name = venue_df['venue_name'].iloc[0] if len(venue_df) > 0 else 'unknown'
        if n >= 10:
            results.append({
                'factor': 'venue',
                'value': f"{venue_code}_{venue_name}",
                'hit_rate': hit_rate,
                'sample_size': n
            })
            if hit_rate < 0.35:
                print(f"  {venue_code} ({venue_name}): 的中率={hit_rate:.1%}, サンプル={n}")

    # 天候別
    print("\n--- 天候別的中率 ---")
    for weather in df['weather'].dropna().unique():
        weather_df = df[df['weather'] == weather]
        hit_rate, n = calculate_hit_rate(weather_df)
        if n >= 10:
            results.append({
                'factor': 'weather',
                'value': weather,
                'hit_rate': hit_rate,
                'sample_size': n
            })
            print(f"  {weather}: 的中率={hit_rate:.1%}, サンプル={n}")

    # 風速カテゴリ別
    print("\n--- 風速別的中率 ---")
    df['wind_category'] = df['wind_speed'].apply(categorize_wind_speed)
    for cat in ['calm', 'moderate', 'strong', 'very_strong']:
        cat_df = df[df['wind_category'] == cat]
        hit_rate, n = calculate_hit_rate(cat_df)
        if n >= 10:
            results.append({
                'factor': 'wind_speed',
                'value': cat,
                'hit_rate': hit_rate,
                'sample_size': n
            })
            print(f"  {cat}: 的中率={hit_rate:.1%}, サンプル={n}")

    # 波高カテゴリ別
    print("\n--- 波高別的中率 ---")
    df['wave_category'] = df['wave_height'].apply(categorize_wave)
    for cat in ['calm', 'moderate', 'rough', 'very_rough']:
        cat_df = df[df['wave_category'] == cat]
        hit_rate, n = calculate_hit_rate(cat_df)
        if n >= 10:
            results.append({
                'factor': 'wave_height',
                'value': cat,
                'hit_rate': hit_rate,
                'sample_size': n
            })
            print(f"  {cat}: 的中率={hit_rate:.1%}, サンプル={n}")

    # 時間帯別
    print("\n--- 時間帯別的中率 ---")
    df['time_category'] = df['race_time'].apply(categorize_time)
    for cat in ['morning_early', 'morning_late', 'afternoon', 'evening']:
        cat_df = df[df['time_category'] == cat]
        hit_rate, n = calculate_hit_rate(cat_df)
        if n >= 10:
            results.append({
                'factor': 'time',
                'value': cat,
                'hit_rate': hit_rate,
                'sample_size': n
            })
            print(f"  {cat}: 的中率={hit_rate:.1%}, サンプル={n}")

    # 潮汐影響あり/なし
    print("\n--- 潮汐影響別的中率 ---")
    for tide_impact in [0, 1]:
        tide_df = df[df['tide_impact'] == tide_impact]
        hit_rate, n = calculate_hit_rate(tide_df)
        if n >= 10:
            results.append({
                'factor': 'tide_impact',
                'value': str(tide_impact),
                'hit_rate': hit_rate,
                'sample_size': n
            })
            label = '潮汐影響あり' if tide_impact == 1 else '潮汐影響なし'
            print(f"  {label}: 的中率={hit_rate:.1%}, サンプル={n}")

    # ナイター
    print("\n--- ナイター別的中率 ---")
    for is_nighter in [0, 1]:
        nighter_df = df[df['is_nighter'] == is_nighter]
        hit_rate, n = calculate_hit_rate(nighter_df)
        if n >= 10:
            results.append({
                'factor': 'nighter',
                'value': str(is_nighter),
                'hit_rate': hit_rate,
                'sample_size': n
            })
            label = 'ナイター' if is_nighter == 1 else 'デイレース'
            print(f"  {label}: 的中率={hit_rate:.1%}, サンプル={n}")

    # 1コース勝率が低い会場
    print("\n--- 1コース勝率別的中率 ---")
    df['course1_low'] = df['course_1_win_rate'] < 50
    for is_low in [True, False]:
        low_df = df[df['course1_low'] == is_low]
        hit_rate, n = calculate_hit_rate(low_df)
        if n >= 10:
            label = '1コース勝率低(50%未満)' if is_low else '1コース勝率高(50%以上)'
            print(f"  {label}: 的中率={hit_rate:.1%}, サンプル={n}")

    return pd.DataFrame(results)


def analyze_two_factor_combinations(df):
    """2要因の組み合わせ分析"""
    print("\n" + "="*80)
    print("【2要因組み合わせ分析】- 的中率30%以下のパターン")
    print("="*80)

    # カテゴリ追加
    df['wind_category'] = df['wind_speed'].apply(categorize_wind_speed)
    df['wave_category'] = df['wave_height'].apply(categorize_wave)
    df['time_category'] = df['race_time'].apply(categorize_time)
    df['course1_category'] = df['course_1_win_rate'].apply(
        lambda x: 'low' if pd.notna(x) and x < 48 else ('medium' if pd.notna(x) and x < 52 else 'high')
    )

    low_hit_patterns = []

    # 会場 x 風速
    print("\n--- 会場 x 風速 ---")
    for venue in df['venue_code'].unique():
        for wind in ['moderate', 'strong', 'very_strong']:
            mask = (df['venue_code'] == venue) & (df['wind_category'] == wind)
            sub_df = df[mask]
            hit_rate, n = calculate_hit_rate(sub_df)
            if n >= 10 and hit_rate is not None and hit_rate <= 0.30:
                venue_name = sub_df['venue_name'].iloc[0] if len(sub_df) > 0 else 'unknown'
                pattern = {
                    'pattern': f'{venue}({venue_name}) x 風速{wind}',
                    'factors': {'venue': venue, 'wind': wind},
                    'hit_rate': hit_rate,
                    'sample_size': n
                }
                low_hit_patterns.append(pattern)
                print(f"  {pattern['pattern']}: 的中率={hit_rate:.1%}, サンプル={n}")

    # 会場 x 波高
    print("\n--- 会場 x 波高 ---")
    for venue in df['venue_code'].unique():
        for wave in ['moderate', 'rough', 'very_rough']:
            mask = (df['venue_code'] == venue) & (df['wave_category'] == wave)
            sub_df = df[mask]
            hit_rate, n = calculate_hit_rate(sub_df)
            if n >= 10 and hit_rate is not None and hit_rate <= 0.30:
                venue_name = sub_df['venue_name'].iloc[0] if len(sub_df) > 0 else 'unknown'
                pattern = {
                    'pattern': f'{venue}({venue_name}) x 波高{wave}',
                    'factors': {'venue': venue, 'wave': wave},
                    'hit_rate': hit_rate,
                    'sample_size': n
                }
                low_hit_patterns.append(pattern)
                print(f"  {pattern['pattern']}: 的中率={hit_rate:.1%}, サンプル={n}")

    # 会場 x 時間帯
    print("\n--- 会場 x 時間帯 ---")
    for venue in df['venue_code'].unique():
        for time_cat in ['morning_early', 'morning_late', 'afternoon', 'evening']:
            mask = (df['venue_code'] == venue) & (df['time_category'] == time_cat)
            sub_df = df[mask]
            hit_rate, n = calculate_hit_rate(sub_df)
            if n >= 10 and hit_rate is not None and hit_rate <= 0.30:
                venue_name = sub_df['venue_name'].iloc[0] if len(sub_df) > 0 else 'unknown'
                pattern = {
                    'pattern': f'{venue}({venue_name}) x 時間帯{time_cat}',
                    'factors': {'venue': venue, 'time': time_cat},
                    'hit_rate': hit_rate,
                    'sample_size': n
                }
                low_hit_patterns.append(pattern)
                print(f"  {pattern['pattern']}: 的中率={hit_rate:.1%}, サンプル={n}")

    # 潮汐影響あり会場 x 時間帯
    print("\n--- 潮汐影響会場 x 時間帯 ---")
    tide_venues = df[df['tide_impact'] == 1]
    for venue in tide_venues['venue_code'].unique():
        for time_cat in ['morning_early', 'morning_late', 'afternoon', 'evening']:
            mask = (tide_venues['venue_code'] == venue) & (tide_venues['time_category'] == time_cat)
            sub_df = tide_venues[mask]
            hit_rate, n = calculate_hit_rate(sub_df)
            if n >= 10 and hit_rate is not None and hit_rate <= 0.30:
                venue_name = sub_df['venue_name'].iloc[0] if len(sub_df) > 0 else 'unknown'
                pattern = {
                    'pattern': f'潮汐場{venue}({venue_name}) x {time_cat}',
                    'factors': {'venue': venue, 'time': time_cat, 'tide_impact': 1},
                    'hit_rate': hit_rate,
                    'sample_size': n
                }
                low_hit_patterns.append(pattern)
                print(f"  {pattern['pattern']}: 的中率={hit_rate:.1%}, サンプル={n}")

    # 風速 x 波高
    print("\n--- 風速 x 波高 ---")
    for wind in ['calm', 'moderate', 'strong', 'very_strong']:
        for wave in ['calm', 'moderate', 'rough', 'very_rough']:
            mask = (df['wind_category'] == wind) & (df['wave_category'] == wave)
            sub_df = df[mask]
            hit_rate, n = calculate_hit_rate(sub_df)
            if n >= 10 and hit_rate is not None and hit_rate <= 0.30:
                pattern = {
                    'pattern': f'風速{wind} x 波高{wave}',
                    'factors': {'wind': wind, 'wave': wave},
                    'hit_rate': hit_rate,
                    'sample_size': n
                }
                low_hit_patterns.append(pattern)
                print(f"  {pattern['pattern']}: 的中率={hit_rate:.1%}, サンプル={n}")

    # 天候 x 風速
    print("\n--- 天候 x 風速 ---")
    for weather in df['weather'].dropna().unique():
        for wind in ['moderate', 'strong', 'very_strong']:
            mask = (df['weather'] == weather) & (df['wind_category'] == wind)
            sub_df = df[mask]
            hit_rate, n = calculate_hit_rate(sub_df)
            if n >= 10 and hit_rate is not None and hit_rate <= 0.30:
                pattern = {
                    'pattern': f'{weather} x 風速{wind}',
                    'factors': {'weather': weather, 'wind': wind},
                    'hit_rate': hit_rate,
                    'sample_size': n
                }
                low_hit_patterns.append(pattern)
                print(f"  {pattern['pattern']}: 的中率={hit_rate:.1%}, サンプル={n}")

    # 1コース勝率 x 風速
    print("\n--- 1コース勝率 x 風速 ---")
    for course1_cat in ['low', 'medium']:
        for wind in ['moderate', 'strong', 'very_strong']:
            mask = (df['course1_category'] == course1_cat) & (df['wind_category'] == wind)
            sub_df = df[mask]
            hit_rate, n = calculate_hit_rate(sub_df)
            if n >= 10 and hit_rate is not None and hit_rate <= 0.30:
                pattern = {
                    'pattern': f'1コース{course1_cat} x 風速{wind}',
                    'factors': {'course1': course1_cat, 'wind': wind},
                    'hit_rate': hit_rate,
                    'sample_size': n
                }
                low_hit_patterns.append(pattern)
                print(f"  {pattern['pattern']}: 的中率={hit_rate:.1%}, サンプル={n}")

    return low_hit_patterns


def analyze_three_factor_combinations(df):
    """3要因の組み合わせ分析"""
    print("\n" + "="*80)
    print("【3要因組み合わせ分析】- 的中率30%以下のパターン")
    print("="*80)

    # カテゴリ追加
    df['wind_category'] = df['wind_speed'].apply(categorize_wind_speed)
    df['wave_category'] = df['wave_height'].apply(categorize_wave)
    df['time_category'] = df['race_time'].apply(categorize_time)

    low_hit_patterns = []

    # 会場 x 時間帯 x 風速
    print("\n--- 会場 x 時間帯 x 風速 ---")
    for venue in df['venue_code'].unique():
        for time_cat in ['morning_early', 'morning_late', 'afternoon', 'evening']:
            for wind in ['moderate', 'strong', 'very_strong']:
                mask = (df['venue_code'] == venue) & \
                       (df['time_category'] == time_cat) & \
                       (df['wind_category'] == wind)
                sub_df = df[mask]
                hit_rate, n = calculate_hit_rate(sub_df)
                if n >= 10 and hit_rate is not None and hit_rate <= 0.25:
                    venue_name = sub_df['venue_name'].iloc[0] if len(sub_df) > 0 else 'unknown'
                    pattern = {
                        'pattern': f'{venue}({venue_name}) x {time_cat} x 風速{wind}',
                        'factors': {'venue': venue, 'time': time_cat, 'wind': wind},
                        'hit_rate': hit_rate,
                        'sample_size': n
                    }
                    low_hit_patterns.append(pattern)
                    print(f"  {pattern['pattern']}: 的中率={hit_rate:.1%}, サンプル={n}")

    # 潮汐影響会場 x 時間帯 x 天候
    print("\n--- 潮汐影響会場 x 時間帯 x 天候 ---")
    tide_venues = df[df['tide_impact'] == 1]
    for venue in tide_venues['venue_code'].unique():
        for time_cat in ['morning_early', 'morning_late', 'afternoon', 'evening']:
            for weather in tide_venues['weather'].dropna().unique():
                mask = (tide_venues['venue_code'] == venue) & \
                       (tide_venues['time_category'] == time_cat) & \
                       (tide_venues['weather'] == weather)
                sub_df = tide_venues[mask]
                hit_rate, n = calculate_hit_rate(sub_df)
                if n >= 10 and hit_rate is not None and hit_rate <= 0.25:
                    venue_name = sub_df['venue_name'].iloc[0] if len(sub_df) > 0 else 'unknown'
                    pattern = {
                        'pattern': f'潮汐場{venue}({venue_name}) x {time_cat} x {weather}',
                        'factors': {'venue': venue, 'time': time_cat, 'weather': weather, 'tide_impact': 1},
                        'hit_rate': hit_rate,
                        'sample_size': n
                    }
                    low_hit_patterns.append(pattern)
                    print(f"  {pattern['pattern']}: 的中率={hit_rate:.1%}, サンプル={n}")

    # 会場 x 風速 x 波高
    print("\n--- 会場 x 風速 x 波高 ---")
    for venue in df['venue_code'].unique():
        for wind in ['moderate', 'strong', 'very_strong']:
            for wave in ['moderate', 'rough', 'very_rough']:
                mask = (df['venue_code'] == venue) & \
                       (df['wind_category'] == wind) & \
                       (df['wave_category'] == wave)
                sub_df = df[mask]
                hit_rate, n = calculate_hit_rate(sub_df)
                if n >= 10 and hit_rate is not None and hit_rate <= 0.25:
                    venue_name = sub_df['venue_name'].iloc[0] if len(sub_df) > 0 else 'unknown'
                    pattern = {
                        'pattern': f'{venue}({venue_name}) x 風速{wind} x 波高{wave}',
                        'factors': {'venue': venue, 'wind': wind, 'wave': wave},
                        'hit_rate': hit_rate,
                        'sample_size': n
                    }
                    low_hit_patterns.append(pattern)
                    print(f"  {pattern['pattern']}: 的中率={hit_rate:.1%}, サンプル={n}")

    return low_hit_patterns


def analyze_predicted_winner_course(df):
    """1着予想が何号艇だったかによる分析"""
    print("\n" + "="*80)
    print("【1着予想のコース別分析】")
    print("="*80)

    df['wind_category'] = df['wind_speed'].apply(categorize_wind_speed)
    df['wave_category'] = df['wave_height'].apply(categorize_wave)

    # 1着予想のみを抽出
    pred_1st = df[df['rank_prediction'] == 1].copy()

    print("\n--- 1着予想が1号艇だったケース ---")
    inner_pred = pred_1st[pred_1st['pit_number'] == 1]

    # 全体的中率
    total_hit_rate = (inner_pred['actual_rank'].astype(str) == '1').mean()
    print(f"  全体: 的中率={total_hit_rate:.1%}, サンプル={len(inner_pred)}")

    # 風速別
    print("\n  風速別:")
    for wind in ['calm', 'moderate', 'strong', 'very_strong']:
        sub = inner_pred[inner_pred['wind_category'] == wind]
        if len(sub) >= 10:
            hit_rate = (sub['actual_rank'].astype(str) == '1').mean()
            print(f"    {wind}: 的中率={hit_rate:.1%}, サンプル={len(sub)}")

    # 波高別
    print("\n  波高別:")
    for wave in ['calm', 'moderate', 'rough', 'very_rough']:
        sub = inner_pred[inner_pred['wave_category'] == wave]
        if len(sub) >= 10:
            hit_rate = (sub['actual_rank'].astype(str) == '1').mean()
            print(f"    {wave}: 的中率={hit_rate:.1%}, サンプル={len(sub)}")

    # 潮汐影響会場
    print("\n  潮汐影響別:")
    for tide in [0, 1]:
        sub = inner_pred[inner_pred['tide_impact'] == tide]
        if len(sub) >= 10:
            hit_rate = (sub['actual_rank'].astype(str) == '1').mean()
            label = '潮汐あり' if tide == 1 else '潮汐なし'
            print(f"    {label}: 的中率={hit_rate:.1%}, サンプル={len(sub)}")

    print("\n--- 1着予想が2-6号艇（アウトコース）だったケース ---")
    outer_pred = pred_1st[pred_1st['pit_number'] > 1]

    total_hit_rate = (outer_pred['actual_rank'].astype(str) == '1').mean()
    print(f"  全体: 的中率={total_hit_rate:.1%}, サンプル={len(outer_pred)}")

    # コース別
    print("\n  コース別:")
    for pit in range(2, 7):
        sub = pred_1st[pred_1st['pit_number'] == pit]
        if len(sub) >= 10:
            hit_rate = (sub['actual_rank'].astype(str) == '1').mean()
            print(f"    {pit}号艇予想: 的中率={hit_rate:.1%}, サンプル={len(sub)}")


def analyze_kimarite_impact(df):
    """決まり手による分析"""
    print("\n" + "="*80)
    print("【決まり手と環境要因の関係】")
    print("="*80)

    # 1着の結果から決まり手を確認
    first_place = df[df['actual_rank'].astype(str) == '1']

    print("\n--- 決まり手の分布 ---")
    kimarite_counts = first_place['kimarite'].value_counts()
    for kim, count in kimarite_counts.head(10).items():
        print(f"  {kim}: {count}件 ({count/len(first_place)*100:.1f}%)")

    # 逃げ以外の決まり手が多い環境
    print("\n--- 「逃げ」以外で決着した環境要因 ---")
    non_nige = first_place[first_place['kimarite'] != '逃げ']
    nige = first_place[first_place['kimarite'] == '逃げ']

    df['wind_category'] = df['wind_speed'].apply(categorize_wind_speed)

    # 風速別の「逃げ」率
    print("\n  風速別「逃げ」率:")
    for wind in ['calm', 'moderate', 'strong', 'very_strong']:
        sub_all = first_place[first_place['wind_category'] == wind]
        sub_nige = sub_all[sub_all['kimarite'] == '逃げ']
        if len(sub_all) >= 10:
            nige_rate = len(sub_nige) / len(sub_all)
            print(f"    {wind}: 逃げ率={nige_rate:.1%}, サンプル={len(sub_all)}")


def generate_filter_rules(low_hit_patterns):
    """低的中率パターンからフィルタリングルールを生成"""
    print("\n" + "="*80)
    print("【フィルタリングルール提案】")
    print("="*80)

    # 的中率の低い順にソート
    sorted_patterns = sorted(low_hit_patterns, key=lambda x: x['hit_rate'])

    print("\n### 推奨フィルタリングルール（的中率25%以下、サンプル10件以上）")
    print()

    rules = []
    for i, pattern in enumerate(sorted_patterns[:20], 1):
        if pattern['hit_rate'] <= 0.25:
            print(f"{i}. {pattern['pattern']}")
            print(f"   - 的中率: {pattern['hit_rate']:.1%}")
            print(f"   - サンプル数: {pattern['sample_size']}")
            print(f"   - 要因: {pattern['factors']}")
            print()
            rules.append(pattern)

    return rules


def analyze_causality(df, low_hit_patterns):
    """因果関係の仮説を分析"""
    print("\n" + "="*80)
    print("【因果関係の仮説】")
    print("="*80)

    # 1着予想のコース分布を確認
    pred_1st = df[df['rank_prediction'] == 1]

    print("\n### 1. インコース予想と強風・高波の関係")
    print()

    # 強風時のインコース予想
    df['wind_category'] = df['wind_speed'].apply(categorize_wind_speed)
    strong_wind = pred_1st[pred_1st['wind_category'].isin(['strong', 'very_strong'])]
    inner_in_strong = strong_wind[strong_wind['pit_number'] == 1]

    if len(inner_in_strong) >= 10:
        hit_rate = (inner_in_strong['actual_rank'].astype(str) == '1').mean()
        print(f"強風時の1号艇予想的中率: {hit_rate:.1%} (サンプル={len(inner_in_strong)})")

        calm_wind = pred_1st[pred_1st['wind_category'] == 'calm']
        inner_in_calm = calm_wind[calm_wind['pit_number'] == 1]
        if len(inner_in_calm) >= 10:
            calm_hit = (inner_in_calm['actual_rank'].astype(str) == '1').mean()
            print(f"穏やか時の1号艇予想的中率: {calm_hit:.1%} (サンプル={len(inner_in_calm)})")

            if hit_rate < calm_hit:
                print(f"\n→ 仮説: 強風時はスタートタイミングが乱れやすく、インコースの「逃げ」が決まりにくい")

    print("\n### 2. 潮汐影響会場と時間帯の関係")
    print()

    tide_venues = pred_1st[pred_1st['tide_impact'] == 1]
    df['time_category'] = df['race_time'].apply(categorize_time)

    for time_cat in ['morning_early', 'afternoon', 'evening']:
        time_sub = tide_venues[tide_venues['time_category'] == time_cat]
        if len(time_sub) >= 10:
            inner = time_sub[time_sub['pit_number'] == 1]
            if len(inner) >= 5:
                hit_rate = (inner['actual_rank'].astype(str) == '1').mean()
                print(f"潮汐会場 {time_cat} 1号艇予想: {hit_rate:.1%} (サンプル={len(inner)})")

    print("\n→ 仮説: 潮汐影響のある会場では、潮位変化の大きい時間帯にインコースの旋回が不安定になる可能性")

    print("\n### 3. 特定会場の特性")
    print()

    # 会場別の1着予想的中率
    venue_stats = []
    for venue in pred_1st['venue_code'].unique():
        venue_df = pred_1st[pred_1st['venue_code'] == venue]
        if len(venue_df) >= 20:
            hit_rate = (venue_df['actual_rank'].astype(str) == '1').mean()
            venue_name = venue_df['venue_name'].iloc[0] if 'venue_name' in venue_df.columns else venue
            tide_impact = venue_df['tide_impact'].iloc[0] if 'tide_impact' in venue_df.columns else None
            course1_rate = venue_df['course_1_win_rate'].iloc[0] if 'course_1_win_rate' in venue_df.columns else None
            venue_stats.append({
                'venue': venue,
                'name': venue_name,
                'hit_rate': hit_rate,
                'sample': len(venue_df),
                'tide_impact': tide_impact,
                'course1_rate': course1_rate
            })

    venue_stats_df = pd.DataFrame(venue_stats).sort_values('hit_rate')
    print("的中率が低い会場TOP5:")
    for _, row in venue_stats_df.head(5).iterrows():
        tide_str = '潮汐あり' if row['tide_impact'] == 1 else '潮汐なし'
        print(f"  {row['venue']} ({row['name']}): {row['hit_rate']:.1%}, {tide_str}, 1コース勝率={row['course1_rate']}%")


def main():
    """メイン処理"""
    print("="*80)
    print("2025年 信頼度B BEFORE予測 環境要因分析")
    print("="*80)

    # データロード
    df = load_prediction_data()

    # 全体の的中率
    overall_hit_rate, overall_n = calculate_hit_rate(df)
    print(f"\n全体の1着予想的中率: {overall_hit_rate:.1%} (サンプル={overall_n})")

    # 単一要因分析
    single_results = analyze_single_factors(df)

    # 2要因組み合わせ分析
    two_factor_patterns = analyze_two_factor_combinations(df)

    # 3要因組み合わせ分析
    three_factor_patterns = analyze_three_factor_combinations(df)

    # 予想コース別分析
    analyze_predicted_winner_course(df)

    # 決まり手分析
    analyze_kimarite_impact(df)

    # 全パターンを統合
    all_patterns = two_factor_patterns + three_factor_patterns

    # フィルタリングルール生成
    rules = generate_filter_rules(all_patterns)

    # 因果関係の仮説
    analyze_causality(df, all_patterns)

    print("\n" + "="*80)
    print("分析完了")
    print("="*80)

    return df, all_patterns, rules


if __name__ == "__main__":
    df, patterns, rules = main()
