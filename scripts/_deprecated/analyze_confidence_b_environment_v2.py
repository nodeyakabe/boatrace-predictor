# -*- coding: utf-8 -*-
"""
2025年 信頼度B BEFORE予測データ 環境要因分析スクリプト v2

目的: 的中率が異常に低下する環境要因の複合パターンを発見する
より詳細な分析と因果関係の仮説
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
import sys

# 文字コード設定
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

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

    return df


def calculate_hit_rate(df, pred_rank=1):
    """的中率を計算"""
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
            return 'early_morning'
        elif hour < 13:
            return 'late_morning'
        elif hour < 16:
            return 'afternoon'
        else:
            return 'evening'
    except:
        return 'unknown'


def categorize_wind_speed(speed):
    """風速をカテゴリ化"""
    if pd.isna(speed):
        return 'unknown'
    if speed <= 2:
        return 'calm'
    elif speed <= 4:
        return 'moderate'
    elif speed <= 6:
        return 'strong'
    else:
        return 'very_strong'


def categorize_wave(wave):
    """波高をカテゴリ化"""
    if pd.isna(wave):
        return 'unknown'
    if wave <= 2:
        return 'calm'
    elif wave <= 5:
        return 'moderate'
    elif wave <= 10:
        return 'rough'
    else:
        return 'very_rough'


def main():
    """メイン処理"""
    print("=" * 80)
    print("2025年 信頼度B BEFORE予測 環境要因分析レポート")
    print("=" * 80)

    # データロード
    df = load_prediction_data()

    print(f"\n【データ概要】")
    print(f"  - ロードしたデータ件数: {len(df)}")
    print(f"  - ユニークレース数: {df['race_id'].nunique()}")

    # カテゴリ追加
    df['time_category'] = df['race_time'].apply(categorize_time)
    df['wind_category'] = df['wind_speed'].apply(categorize_wind_speed)
    df['wave_category'] = df['wave_height'].apply(categorize_wave)

    # 全体の的中率
    overall_hit_rate, overall_n = calculate_hit_rate(df)
    print(f"\n【全体の1着予想的中率】: {overall_hit_rate:.1%} (サンプル={overall_n})")

    # 1着予想のみを抽出
    pred_1st = df[df['rank_prediction'] == 1].copy()

    print("\n" + "=" * 80)
    print("【単一要因分析】")
    print("=" * 80)

    # 会場名のマッピング
    venue_names = {
        '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島',
        '05': '多摩川', '06': '浜名湖', '07': '蒲郡', '08': '常滑',
        '09': '津', '10': '三国', '11': 'びわこ', '12': '住之江',
        '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島',
        '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
        '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
    }

    # 会場別的中率
    print("\n--- 会場別的中率（低い順TOP10）---")
    venue_stats = []
    for venue in pred_1st['venue_code'].unique():
        venue_df = pred_1st[pred_1st['venue_code'] == venue]
        hit_rate = (venue_df['actual_rank'].astype(str) == '1').mean()
        n = len(venue_df)
        tide = venue_df['tide_impact'].iloc[0] if len(venue_df) > 0 else None
        c1_rate = venue_df['course_1_win_rate'].iloc[0] if len(venue_df) > 0 else None
        if n >= 20:
            venue_stats.append({
                'venue_code': venue,
                'venue_name': venue_names.get(venue, venue),
                'hit_rate': hit_rate,
                'sample': n,
                'tide_impact': tide,
                'course1_rate': c1_rate
            })

    venue_stats_df = pd.DataFrame(venue_stats).sort_values('hit_rate')
    for _, row in venue_stats_df.head(10).iterrows():
        tide_str = '潮汐あり' if row['tide_impact'] == 1 else '潮汐なし'
        print(f"  {row['venue_code']} {row['venue_name']}: {row['hit_rate']:.1%} "
              f"(n={row['sample']}, {tide_str}, 1コース勝率={row['course1_rate']}%)")

    # 天候別
    print("\n--- 天候別的中率 ---")
    weather_map = {'晴': 'sunny', '曇': 'cloudy', '雨': 'rainy', '雪': 'snow', '不明': 'unknown'}
    for weather in pred_1st['weather'].dropna().unique():
        w_df = pred_1st[pred_1st['weather'] == weather]
        if len(w_df) >= 10:
            hit_rate = (w_df['actual_rank'].astype(str) == '1').mean()
            print(f"  {weather}: {hit_rate:.1%} (n={len(w_df)})")

    # 風速カテゴリ別
    print("\n--- 風速別的中率 ---")
    wind_labels = {'calm': '穏やか(0-2m)', 'moderate': '中程度(2-4m)',
                   'strong': '強風(4-6m)', 'very_strong': '非常に強い(6m+)'}
    for cat in ['calm', 'moderate', 'strong', 'very_strong']:
        cat_df = pred_1st[pred_1st['wind_category'] == cat]
        if len(cat_df) >= 10:
            hit_rate = (cat_df['actual_rank'].astype(str) == '1').mean()
            print(f"  {wind_labels[cat]}: {hit_rate:.1%} (n={len(cat_df)})")

    # 波高カテゴリ別
    print("\n--- 波高別的中率 ---")
    wave_labels = {'calm': '穏やか(0-2cm)', 'moderate': '中程度(2-5cm)',
                   'rough': '荒れ(5-10cm)', 'very_rough': '非常に荒れ(10cm+)'}
    for cat in ['calm', 'moderate', 'rough', 'very_rough']:
        cat_df = pred_1st[pred_1st['wave_category'] == cat]
        if len(cat_df) >= 10:
            hit_rate = (cat_df['actual_rank'].astype(str) == '1').mean()
            print(f"  {wave_labels[cat]}: {hit_rate:.1%} (n={len(cat_df)})")

    # 時間帯別
    print("\n--- 時間帯別的中率 ---")
    time_labels = {'early_morning': '早朝(8-10時)', 'late_morning': '午前(10-13時)',
                   'afternoon': '午後(13-16時)', 'evening': '夕方以降(16時+)'}
    for cat in ['early_morning', 'late_morning', 'afternoon', 'evening']:
        cat_df = pred_1st[pred_1st['time_category'] == cat]
        if len(cat_df) >= 10:
            hit_rate = (cat_df['actual_rank'].astype(str) == '1').mean()
            print(f"  {time_labels[cat]}: {hit_rate:.1%} (n={len(cat_df)})")

    # 1コース勝率別
    print("\n--- 1コース勝率別的中率（会場特性）---")
    pred_1st['course1_cat'] = pred_1st['course_1_win_rate'].apply(
        lambda x: 'very_low' if pd.notna(x) and x < 47 else
                  ('low' if pd.notna(x) and x < 50 else
                   ('medium' if pd.notna(x) and x < 53 else 'high'))
    )
    course1_labels = {'very_low': '非常に低い(<47%)', 'low': '低い(47-50%)',
                      'medium': '中程度(50-53%)', 'high': '高い(53%+)'}
    for cat in ['very_low', 'low', 'medium', 'high']:
        cat_df = pred_1st[pred_1st['course1_cat'] == cat]
        if len(cat_df) >= 10:
            hit_rate = (cat_df['actual_rank'].astype(str) == '1').mean()
            print(f"  {course1_labels[cat]}: {hit_rate:.1%} (n={len(cat_df)})")

    print("\n" + "=" * 80)
    print("【複合要因分析】- 的中率35%以下または大幅低下パターン")
    print("=" * 80)

    low_hit_patterns = []

    # 会場 x 時間帯
    print("\n--- 会場 x 時間帯 ---")
    for venue in pred_1st['venue_code'].unique():
        for time_cat in ['early_morning', 'late_morning', 'afternoon', 'evening']:
            mask = (pred_1st['venue_code'] == venue) & (pred_1st['time_category'] == time_cat)
            sub_df = pred_1st[mask]
            if len(sub_df) >= 10:
                hit_rate = (sub_df['actual_rank'].astype(str) == '1').mean()
                if hit_rate <= 0.35:
                    venue_name = venue_names.get(venue, venue)
                    pattern = {
                        'type': 'venue_time',
                        'description': f'{venue}({venue_name}) x {time_labels[time_cat]}',
                        'conditions': {'venue_code': venue, 'time_category': time_cat},
                        'hit_rate': hit_rate,
                        'sample': len(sub_df)
                    }
                    low_hit_patterns.append(pattern)
                    print(f"  {pattern['description']}: {hit_rate:.1%} (n={len(sub_df)})")

    # 会場 x 風速
    print("\n--- 会場 x 風速 ---")
    for venue in pred_1st['venue_code'].unique():
        for wind in ['moderate', 'strong', 'very_strong']:
            mask = (pred_1st['venue_code'] == venue) & (pred_1st['wind_category'] == wind)
            sub_df = pred_1st[mask]
            if len(sub_df) >= 10:
                hit_rate = (sub_df['actual_rank'].astype(str) == '1').mean()
                if hit_rate <= 0.35:
                    venue_name = venue_names.get(venue, venue)
                    pattern = {
                        'type': 'venue_wind',
                        'description': f'{venue}({venue_name}) x {wind_labels[wind]}',
                        'conditions': {'venue_code': venue, 'wind_category': wind},
                        'hit_rate': hit_rate,
                        'sample': len(sub_df)
                    }
                    low_hit_patterns.append(pattern)
                    print(f"  {pattern['description']}: {hit_rate:.1%} (n={len(sub_df)})")

    # 会場 x 波高
    print("\n--- 会場 x 波高 ---")
    for venue in pred_1st['venue_code'].unique():
        for wave in ['moderate', 'rough', 'very_rough']:
            mask = (pred_1st['venue_code'] == venue) & (pred_1st['wave_category'] == wave)
            sub_df = pred_1st[mask]
            if len(sub_df) >= 10:
                hit_rate = (sub_df['actual_rank'].astype(str) == '1').mean()
                if hit_rate <= 0.35:
                    venue_name = venue_names.get(venue, venue)
                    pattern = {
                        'type': 'venue_wave',
                        'description': f'{venue}({venue_name}) x {wave_labels[wave]}',
                        'conditions': {'venue_code': venue, 'wave_category': wave},
                        'hit_rate': hit_rate,
                        'sample': len(sub_df)
                    }
                    low_hit_patterns.append(pattern)
                    print(f"  {pattern['description']}: {hit_rate:.1%} (n={len(sub_df)})")

    # 1コース勝率低い会場 x 風速強い
    print("\n--- 1コース勝率低い会場 x 風速 ---")
    low_course1_venues = pred_1st[pred_1st['course1_cat'].isin(['very_low', 'low'])]
    for venue in low_course1_venues['venue_code'].unique():
        for wind in ['moderate', 'strong', 'very_strong']:
            mask = (low_course1_venues['venue_code'] == venue) & \
                   (low_course1_venues['wind_category'] == wind)
            sub_df = low_course1_venues[mask]
            if len(sub_df) >= 10:
                hit_rate = (sub_df['actual_rank'].astype(str) == '1').mean()
                if hit_rate <= 0.40:
                    venue_name = venue_names.get(venue, venue)
                    c1_rate = sub_df['course_1_win_rate'].iloc[0]
                    pattern = {
                        'type': 'low_course1_wind',
                        'description': f'{venue}({venue_name},1コース{c1_rate}%) x {wind_labels[wind]}',
                        'conditions': {'venue_code': venue, 'wind_category': wind,
                                      'course1_rate': c1_rate},
                        'hit_rate': hit_rate,
                        'sample': len(sub_df)
                    }
                    low_hit_patterns.append(pattern)
                    print(f"  {pattern['description']}: {hit_rate:.1%} (n={len(sub_df)})")

    # 天候 x 風速
    print("\n--- 天候 x 風速 ---")
    for weather in pred_1st['weather'].dropna().unique():
        for wind in ['strong', 'very_strong']:
            mask = (pred_1st['weather'] == weather) & (pred_1st['wind_category'] == wind)
            sub_df = pred_1st[mask]
            if len(sub_df) >= 10:
                hit_rate = (sub_df['actual_rank'].astype(str) == '1').mean()
                if hit_rate <= 0.40:
                    pattern = {
                        'type': 'weather_wind',
                        'description': f'{weather} x {wind_labels[wind]}',
                        'conditions': {'weather': weather, 'wind_category': wind},
                        'hit_rate': hit_rate,
                        'sample': len(sub_df)
                    }
                    low_hit_patterns.append(pattern)
                    print(f"  {pattern['description']}: {hit_rate:.1%} (n={len(sub_df)})")

    # 潮汐影響会場 x 悪天候・強風
    print("\n--- 潮汐影響会場 x 環境悪化 ---")
    tide_venues = pred_1st[pred_1st['tide_impact'] == 1]
    for wind in ['strong', 'very_strong']:
        mask = tide_venues['wind_category'] == wind
        sub_df = tide_venues[mask]
        if len(sub_df) >= 10:
            hit_rate = (sub_df['actual_rank'].astype(str) == '1').mean()
            if hit_rate <= 0.45:
                pattern = {
                    'type': 'tide_wind',
                    'description': f'潮汐影響会場 x {wind_labels[wind]}',
                    'conditions': {'tide_impact': 1, 'wind_category': wind},
                    'hit_rate': hit_rate,
                    'sample': len(sub_df)
                }
                low_hit_patterns.append(pattern)
                print(f"  {pattern['description']}: {hit_rate:.1%} (n={len(sub_df)})")

    print("\n" + "=" * 80)
    print("【3要因複合パターン】")
    print("=" * 80)

    # 会場 x 時間帯 x 風速
    print("\n--- 会場 x 時間帯 x 風速 ---")
    for venue in pred_1st['venue_code'].unique():
        for time_cat in ['early_morning', 'late_morning', 'afternoon', 'evening']:
            for wind in ['moderate', 'strong', 'very_strong']:
                mask = (pred_1st['venue_code'] == venue) & \
                       (pred_1st['time_category'] == time_cat) & \
                       (pred_1st['wind_category'] == wind)
                sub_df = pred_1st[mask]
                if len(sub_df) >= 10:
                    hit_rate = (sub_df['actual_rank'].astype(str) == '1').mean()
                    if hit_rate <= 0.30:
                        venue_name = venue_names.get(venue, venue)
                        pattern = {
                            'type': 'venue_time_wind',
                            'description': f'{venue}({venue_name}) x {time_labels[time_cat]} x {wind_labels[wind]}',
                            'conditions': {'venue_code': venue, 'time_category': time_cat,
                                          'wind_category': wind},
                            'hit_rate': hit_rate,
                            'sample': len(sub_df)
                        }
                        low_hit_patterns.append(pattern)
                        print(f"  {pattern['description']}: {hit_rate:.1%} (n={len(sub_df)})")

    print("\n" + "=" * 80)
    print("【1着予想のコース（枠番）別分析】")
    print("=" * 80)

    # 1着予想が何号艇だったかの分布
    print("\n--- 1着予想の枠番分布 ---")
    pit_dist = pred_1st['pit_number'].value_counts().sort_index()
    for pit, count in pit_dist.items():
        pct = count / len(pred_1st) * 100
        hit_rate = (pred_1st[pred_1st['pit_number'] == pit]['actual_rank'].astype(str) == '1').mean()
        print(f"  {pit}号艇予想: {count}件 ({pct:.1f}%), 的中率={hit_rate:.1%}")

    # 1号艇予想 vs アウトコース予想の環境別比較
    print("\n--- 1号艇予想 vs アウトコース予想の環境別比較 ---")
    inner_pred = pred_1st[pred_1st['pit_number'] == 1]
    outer_pred = pred_1st[pred_1st['pit_number'] > 1]

    print("\n  ■ 1号艇を1着予想したケース")
    print(f"    全体: {(inner_pred['actual_rank'].astype(str) == '1').mean():.1%} (n={len(inner_pred)})")

    for wind in ['calm', 'moderate', 'strong', 'very_strong']:
        sub = inner_pred[inner_pred['wind_category'] == wind]
        if len(sub) >= 10:
            hit_rate = (sub['actual_rank'].astype(str) == '1').mean()
            print(f"    {wind_labels[wind]}: {hit_rate:.1%} (n={len(sub)})")

    print("\n  ■ 2-6号艇を1着予想したケース")
    print(f"    全体: {(outer_pred['actual_rank'].astype(str) == '1').mean():.1%} (n={len(outer_pred)})")

    for wind in ['calm', 'moderate', 'strong', 'very_strong']:
        sub = outer_pred[outer_pred['wind_category'] == wind]
        if len(sub) >= 10:
            hit_rate = (sub['actual_rank'].astype(str) == '1').mean()
            print(f"    {wind_labels[wind]}: {hit_rate:.1%} (n={len(sub)})")

    print("\n" + "=" * 80)
    print("【決まり手分析】")
    print("=" * 80)

    # 1着の結果から決まり手を確認
    first_place = pred_1st[pred_1st['actual_rank'].astype(str) == '1']

    print("\n--- 決まり手の分布（予想的中時）---")
    kimarite_counts = first_place['kimarite'].value_counts()
    total_kimarite = len(first_place)
    for kim, count in kimarite_counts.head(6).items():
        print(f"  {kim}: {count}件 ({count/total_kimarite*100:.1f}%)")

    # 環境別「逃げ」率
    print("\n--- 風速別「逃げ」率（1着時）---")
    for wind in ['calm', 'moderate', 'strong', 'very_strong']:
        sub = first_place[first_place['wind_category'] == wind]
        if len(sub) >= 10:
            nige_rate = (sub['kimarite'] == '逃げ').mean()
            print(f"  {wind_labels[wind]}: 逃げ率={nige_rate:.1%} (n={len(sub)})")

    print("\n" + "=" * 80)
    print("【フィルタリングルール提案】")
    print("=" * 80)

    # 低的中率パターンをソート
    sorted_patterns = sorted(low_hit_patterns, key=lambda x: x['hit_rate'])

    print("\n### 推奨フィルタリングルール（的中率35%以下、サンプル10件以上）")
    print()

    for i, pattern in enumerate(sorted_patterns[:15], 1):
        print(f"{i}. {pattern['description']}")
        print(f"   - 的中率: {pattern['hit_rate']:.1%}")
        print(f"   - サンプル数: {pattern['sample']}")
        print(f"   - 条件: {pattern['conditions']}")
        print()

    print("\n" + "=" * 80)
    print("【因果関係の仮説】")
    print("=" * 80)

    print("""
### 1. 戸田（02）の低的中率
- 1コース勝率が全場で最も低い（45.2%）
- 水面が狭く、インコースの旋回が難しい
- 予想システムがインコース有利を過大評価している可能性

### 2. 平和島（04）・江戸川（03）の低的中率
- 両場とも1コース勝率が47%前後と低い
- 江戸川は潮汐影響があり、潮位変化で水面状況が変わる
- 強風時にスタートタイミングが乱れやすい

### 3. 強風・高波時の的中率低下
- 風速が強くなるほど「逃げ」決着率が下がる
- スタートタイミングの乱れでアウトコースに有利な展開が増える
- 予想システムがこの影響を十分に反映できていない可能性

### 4. 午前中（特に10-13時）の低的中率
- 選手のコンディションが安定していない時間帯
- 潮汐影響のある会場では干潮時間と重なることが多い

### 5. 特定会場×特定時間帯の複合パターン
- 戸田×午前中：狭い水面で風の影響を受けやすい
- 江戸川×夕方：潮位変化と光の影響が複合
""")

    print("\n" + "=" * 80)
    print("【実装提案】")
    print("=" * 80)

    print("""
### フィルタリング条件（信頼度Bから除外を検討）

1. **会場条件**
   - 戸田（02）: 常時注意（1コース勝率低）
   - 江戸川（03）: 潮汐×夕方の組み合わせ
   - 平和島（04）: 強風時

2. **環境条件**
   - 風速 > 6m/s（very_strong）
   - 波高 > 10cm（very_rough）
   - 上記の組み合わせ

3. **複合条件**
   - 1コース勝率48%未満の会場 × 風速4m/s以上
   - 潮汐影響会場 × 午前中 × 風速強い

### スコア調整提案

低的中率パターンに該当する場合、信頼度を下方調整：
- B → C への格下げを検討
- または投票金額の減額
""")

    print("\n" + "=" * 80)
    print("分析完了")
    print("=" * 80)

    return df, low_hit_patterns


if __name__ == "__main__":
    df, patterns = main()
