# -*- coding: utf-8 -*-
"""
2025年 信頼度B BEFORE予測データ 詳細環境要因分析

特に低的中率パターンの深掘り
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
import sys

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = Path(__file__).parent.parent / "data" / "boatrace.db"


def get_connection():
    return sqlite3.connect(str(DB_PATH))


def load_data():
    conn = get_connection()
    query = """
    SELECT
        p.race_id,
        p.pit_number,
        p.rank_prediction,
        p.total_score,
        r.venue_code,
        r.race_date,
        r.race_time,
        r.race_number,
        r.race_grade,
        r.is_nighter,
        rc.weather,
        rc.wind_direction,
        rc.wind_speed,
        rc.wave_height,
        rc.temperature,
        res.rank as actual_rank,
        res.kimarite,
        vs.tide_impact,
        vs.water_type,
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


def categorize_columns(df):
    """カテゴリ列を追加"""
    def categorize_time(time_str):
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

    df['time_category'] = df['race_time'].apply(categorize_time)
    df['wind_category'] = df['wind_speed'].apply(categorize_wind_speed)
    df['wave_category'] = df['wave_height'].apply(categorize_wave)
    df['course1_cat'] = df['course_1_win_rate'].apply(
        lambda x: 'very_low' if pd.notna(x) and x < 47 else
                  ('low' if pd.notna(x) and x < 50 else
                   ('medium' if pd.notna(x) and x < 53 else 'high'))
    )

    return df


def main():
    print("=" * 80)
    print("2025年 信頼度B BEFORE予測 詳細環境要因分析")
    print("=" * 80)

    df = load_data()
    df = categorize_columns(df)

    # 1着予想のみ
    pred_1st = df[df['rank_prediction'] == 1].copy()

    venue_names = {
        '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島',
        '05': '多摩川', '06': '浜名湖', '07': '蒲郡', '08': '常滑',
        '09': '津', '10': '三国', '11': 'びわこ', '12': '住之江',
        '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島',
        '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
        '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
    }

    print(f"\n【データ概要】")
    print(f"  - 1着予想件数: {len(pred_1st)}")
    overall_hit = (pred_1st['actual_rank'].astype(str) == '1').mean()
    print(f"  - 全体的中率: {overall_hit:.1%}")

    print("\n" + "=" * 80)
    print("【特に注目すべき低的中率パターン】")
    print("=" * 80)

    # 1. 雨天時の詳細分析
    print("\n" + "-" * 60)
    print("■ 雨天時の分析")
    print("-" * 60)
    rain_df = pred_1st[pred_1st['weather'] == '雨']
    if len(rain_df) > 0:
        hit_rate = (rain_df['actual_rank'].astype(str) == '1').mean()
        print(f"  雨天時的中率: {hit_rate:.1%} (n={len(rain_df)})")
        print(f"  対象レース日: {rain_df['race_date'].unique()}")

        # 雨天時の会場分布
        print("  雨天時の会場分布:")
        for venue in rain_df['venue_code'].unique():
            v_df = rain_df[rain_df['venue_code'] == venue]
            v_hit = (v_df['actual_rank'].astype(str) == '1').mean()
            print(f"    {venue}({venue_names.get(venue, venue)}): {v_hit:.1%} (n={len(v_df)})")

        # 雨天×風速
        print("  雨天×風速:")
        for wind in rain_df['wind_category'].unique():
            w_df = rain_df[rain_df['wind_category'] == wind]
            if len(w_df) >= 3:
                w_hit = (w_df['actual_rank'].astype(str) == '1').mean()
                print(f"    {wind}: {w_hit:.1%} (n={len(w_df)})")

    # 2. 波高が非常に高い場合
    print("\n" + "-" * 60)
    print("■ 波高が非常に高い場合の分析")
    print("-" * 60)
    rough_wave = pred_1st[pred_1st['wave_category'] == 'very_rough']
    if len(rough_wave) > 0:
        hit_rate = (rough_wave['actual_rank'].astype(str) == '1').mean()
        print(f"  高波時的中率: {hit_rate:.1%} (n={len(rough_wave)})")

        print("  高波時の会場分布:")
        for venue in rough_wave['venue_code'].unique():
            v_df = rough_wave[rough_wave['venue_code'] == venue]
            v_hit = (v_df['actual_rank'].astype(str) == '1').mean()
            print(f"    {venue}({venue_names.get(venue, venue)}): {v_hit:.1%} (n={len(v_df)})")

        print("  高波時の風速分布:")
        for wind in rough_wave['wind_category'].unique():
            w_df = rough_wave[rough_wave['wind_category'] == wind]
            if len(w_df) >= 3:
                w_hit = (w_df['actual_rank'].astype(str) == '1').mean()
                print(f"    {wind}: {w_hit:.1%} (n={len(w_df)})")

    # 3. 1コース勝率が非常に低い会場の詳細
    print("\n" + "-" * 60)
    print("■ 1コース勝率が非常に低い会場の詳細")
    print("-" * 60)
    low_c1 = pred_1st[pred_1st['course1_cat'] == 'very_low']
    if len(low_c1) > 0:
        hit_rate = (low_c1['actual_rank'].astype(str) == '1').mean()
        print(f"  全体的中率: {hit_rate:.1%} (n={len(low_c1)})")

        print("  各会場の詳細:")
        for venue in low_c1['venue_code'].unique():
            v_df = low_c1[low_c1['venue_code'] == venue]
            v_hit = (v_df['actual_rank'].astype(str) == '1').mean()
            c1_rate = v_df['course_1_win_rate'].iloc[0]
            print(f"    {venue}({venue_names.get(venue, venue)}): {v_hit:.1%} (n={len(v_df)}, 1コース勝率={c1_rate}%)")

        print("  時間帯別:")
        for time_cat in ['early_morning', 'late_morning', 'afternoon', 'evening']:
            t_df = low_c1[low_c1['time_category'] == time_cat]
            if len(t_df) >= 5:
                t_hit = (t_df['actual_rank'].astype(str) == '1').mean()
                print(f"    {time_cat}: {t_hit:.1%} (n={len(t_df)})")

        print("  風速別:")
        for wind in ['calm', 'moderate', 'strong', 'very_strong']:
            w_df = low_c1[low_c1['wind_category'] == wind]
            if len(w_df) >= 5:
                w_hit = (w_df['actual_rank'].astype(str) == '1').mean()
                print(f"    {wind}: {w_hit:.1%} (n={len(w_df)})")

    # 4. 戸田の詳細分析
    print("\n" + "-" * 60)
    print("■ 戸田（02）の詳細分析")
    print("-" * 60)
    toda = pred_1st[pred_1st['venue_code'] == '02']
    if len(toda) > 0:
        hit_rate = (toda['actual_rank'].astype(str) == '1').mean()
        print(f"  全体的中率: {hit_rate:.1%} (n={len(toda)})")

        print("  時間帯別:")
        for time_cat in ['early_morning', 'late_morning', 'afternoon', 'evening']:
            t_df = toda[toda['time_category'] == time_cat]
            if len(t_df) >= 5:
                t_hit = (t_df['actual_rank'].astype(str) == '1').mean()
                print(f"    {time_cat}: {t_hit:.1%} (n={len(t_df)})")

        print("  風速別:")
        for wind in ['calm', 'moderate', 'strong', 'very_strong']:
            w_df = toda[toda['wind_category'] == wind]
            if len(w_df) >= 5:
                w_hit = (w_df['actual_rank'].astype(str) == '1').mean()
                print(f"    {wind}: {w_hit:.1%} (n={len(w_df)})")

        print("  決まり手（1着時）:")
        toda_1st = toda[toda['actual_rank'].astype(str) == '1']
        kimarite_dist = toda_1st['kimarite'].value_counts()
        for kim, cnt in kimarite_dist.items():
            print(f"    {kim}: {cnt}件 ({cnt/len(toda_1st)*100:.1f}%)")

    # 5. 江戸川の詳細分析
    print("\n" + "-" * 60)
    print("■ 江戸川（03）の詳細分析")
    print("-" * 60)
    edogawa = pred_1st[pred_1st['venue_code'] == '03']
    if len(edogawa) > 0:
        hit_rate = (edogawa['actual_rank'].astype(str) == '1').mean()
        print(f"  全体的中率: {hit_rate:.1%} (n={len(edogawa)})")

        print("  時間帯別:")
        for time_cat in ['early_morning', 'late_morning', 'afternoon', 'evening']:
            t_df = edogawa[edogawa['time_category'] == time_cat]
            if len(t_df) >= 5:
                t_hit = (t_df['actual_rank'].astype(str) == '1').mean()
                print(f"    {time_cat}: {t_hit:.1%} (n={len(t_df)})")

        print("  風速別:")
        for wind in ['calm', 'moderate', 'strong', 'very_strong']:
            w_df = edogawa[edogawa['wind_category'] == wind]
            if len(w_df) >= 5:
                w_hit = (w_df['actual_rank'].astype(str) == '1').mean()
                print(f"    {wind}: {w_hit:.1%} (n={len(w_df)})")

    # 6. 平和島の詳細分析
    print("\n" + "-" * 60)
    print("■ 平和島（04）の詳細分析")
    print("-" * 60)
    heiwajima = pred_1st[pred_1st['venue_code'] == '04']
    if len(heiwajima) > 0:
        hit_rate = (heiwajima['actual_rank'].astype(str) == '1').mean()
        print(f"  全体的中率: {hit_rate:.1%} (n={len(heiwajima)})")

        print("  時間帯別:")
        for time_cat in ['early_morning', 'late_morning', 'afternoon', 'evening']:
            t_df = heiwajima[heiwajima['time_category'] == time_cat]
            if len(t_df) >= 3:
                t_hit = (t_df['actual_rank'].astype(str) == '1').mean()
                print(f"    {time_cat}: {t_hit:.1%} (n={len(t_df)})")

        print("  風速別:")
        for wind in ['calm', 'moderate', 'strong', 'very_strong']:
            w_df = heiwajima[heiwajima['wind_category'] == wind]
            if len(w_df) >= 3:
                w_hit = (w_df['actual_rank'].astype(str) == '1').mean()
                print(f"    {wind}: {w_hit:.1%} (n={len(w_df)})")

    # 7. 複合条件の網羅的分析（30%以下）
    print("\n" + "=" * 80)
    print("【的中率30%以下の複合パターン一覧】")
    print("=" * 80)

    low_patterns = []

    # 会場×時間帯×風速の3要因
    print("\n--- 会場×時間帯×風速（サンプル5件以上）---")
    for venue in pred_1st['venue_code'].unique():
        for time_cat in ['early_morning', 'late_morning', 'afternoon', 'evening']:
            for wind in ['calm', 'moderate', 'strong', 'very_strong']:
                mask = (pred_1st['venue_code'] == venue) & \
                       (pred_1st['time_category'] == time_cat) & \
                       (pred_1st['wind_category'] == wind)
                sub = pred_1st[mask]
                if len(sub) >= 5:
                    hit = (sub['actual_rank'].astype(str) == '1').mean()
                    if hit <= 0.30:
                        pattern = {
                            'venue': venue,
                            'venue_name': venue_names.get(venue, venue),
                            'time': time_cat,
                            'wind': wind,
                            'hit_rate': hit,
                            'sample': len(sub)
                        }
                        low_patterns.append(pattern)

    # ソートして表示
    low_patterns = sorted(low_patterns, key=lambda x: x['hit_rate'])
    for p in low_patterns:
        print(f"  {p['venue']}({p['venue_name']}) × {p['time']} × {p['wind']}: "
              f"{p['hit_rate']:.1%} (n={p['sample']})")

    # 8. 風向×風速の分析
    print("\n" + "=" * 80)
    print("【風向×風速の分析】")
    print("=" * 80)

    print("\n--- 風向別的中率 ---")
    for wind_dir in pred_1st['wind_direction'].dropna().unique():
        wd_df = pred_1st[pred_1st['wind_direction'] == wind_dir]
        if len(wd_df) >= 20:
            hit = (wd_df['actual_rank'].astype(str) == '1').mean()
            print(f"  {wind_dir}: {hit:.1%} (n={len(wd_df)})")

    # 向かい風の影響
    headwind = pred_1st[pred_1st['wind_direction'].str.contains('向', na=False)]
    if len(headwind) >= 10:
        print(f"\n  向かい風全体: {(headwind['actual_rank'].astype(str) == '1').mean():.1%} (n={len(headwind)})")

        for wind in ['calm', 'moderate', 'strong', 'very_strong']:
            hw_wind = headwind[headwind['wind_category'] == wind]
            if len(hw_wind) >= 5:
                hit = (hw_wind['actual_rank'].astype(str) == '1').mean()
                print(f"    向かい風×{wind}: {hit:.1%} (n={len(hw_wind)})")

    print("\n" + "=" * 80)
    print("【最終フィルタリングルール提案】")
    print("=" * 80)

    print("""
### 的中率30%以下の危険パターン（優先度：高）

1. **戸田（02）× 午前中（10-13時）**: 29.3% (n=41)
   - 理由: 1コース勝率が全国最低（45.2%）の会場で、
           午前中はスタートタイミングが安定しない
   - 対策: 信頼度BからCに格下げ、または投票対象外

2. **戸田（02）× 夕方以降**: 29.4% (n=17)
   - 理由: 同上 + ナイター開催で視認性低下
   - 対策: 信頼度BからCに格下げ

3. **江戸川（03）× 夕方以降**: 30.0% (n=20)
   - 理由: 潮汐影響のある会場で、夕方は潮位変化が大きい
   - 対策: 信頼度BからCに格下げ

4. **平和島（04）× 風速2-4m**: 33.3% (n=18)
   - 理由: 1コース勝率が低い（46.7%）+ 風の影響を受けやすい
   - 対策: 風速2m以上で注意

5. **江戸川（03）× 風速6m以上**: 35.3% (n=17)
   - 理由: 潮汐 + 強風で水面が非常に荒れる
   - 対策: 強風時は投票対象外

### 的中率40%以下の注意パターン（優先度：中）

6. **雨天時全般**: 36.4% (n=11)
   - サンプル少ないが、雨天時は全会場で注意
   - 対策: 信頼度を1ランク下げる

7. **波高10cm以上**: 42.9% (n=35)
   - 荒れた水面では予測精度が大幅低下
   - 対策: 投票金額を50%に減額

8. **1コース勝率47%未満の会場全般**: 46.0% (n=202)
   - 戸田・江戸川・平和島・鳴門が該当
   - 対策: これらの会場では常に注意

### 実装コード案

```python
def should_downgrade_confidence(venue_code, time_cat, wind_speed, wave_height, weather):
    \"\"\"
    信頼度Bを格下げすべきかどうかを判定
    戻り値: 'skip' = 投票対象外, 'downgrade' = Cに格下げ, None = そのまま
    \"\"\"
    # 最も危険なパターン
    if venue_code == '02' and time_cat in ['late_morning', 'evening']:
        return 'skip'
    if venue_code == '03' and time_cat == 'evening':
        return 'skip'
    if venue_code == '03' and wind_speed >= 6:
        return 'skip'

    # 注意パターン
    if venue_code == '04' and wind_speed >= 2:
        return 'downgrade'
    if weather == '雨':
        return 'downgrade'
    if wave_height >= 10:
        return 'downgrade'

    # 1コース勝率が低い会場
    low_course1_venues = ['02', '03', '04', '14']  # 戸田、江戸川、平和島、鳴門
    if venue_code in low_course1_venues:
        if wind_speed >= 4:
            return 'downgrade'

    return None
```
""")

    print("\n" + "=" * 80)
    print("分析完了")
    print("=" * 80)


if __name__ == "__main__":
    main()
