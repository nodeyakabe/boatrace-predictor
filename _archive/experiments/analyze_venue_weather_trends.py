# -*- coding: utf-8 -*-
"""
会場別の天候傾向分析スクリプト

各会場の風向・風速・波高が1着率に与える影響を分析し、
予測に組み込むための法則を抽出する
"""

import sqlite3
from collections import defaultdict
import statistics

DB_PATH = "data/boatrace.db"

# 会場名マッピング
VENUE_NAMES = {
    "01": "桐生", "02": "戸田", "03": "江戸川", "04": "平和島", "05": "多摩川",
    "06": "浜名湖", "07": "蒲郡", "08": "常滑", "09": "津", "10": "三国",
    "11": "びわこ", "12": "住之江", "13": "尼崎", "14": "鳴門", "15": "丸亀",
    "16": "児島", "17": "宮島", "18": "徳山", "19": "下関", "20": "若松",
    "21": "芦屋", "22": "福岡", "23": "唐津", "24": "大村"
}

# 海水/淡水/汽水の分類（潮位の影響があるのは海水・汽水）
VENUE_WATER_TYPE = {
    "01": "淡水", "02": "淡水", "03": "汽水", "04": "海水", "05": "淡水",
    "06": "汽水", "07": "汽水", "08": "海水", "09": "海水", "10": "淡水",
    "11": "淡水", "12": "海水", "13": "海水", "14": "海水", "15": "海水",
    "16": "海水", "17": "海水", "18": "海水", "19": "海水", "20": "海水",
    "21": "海水", "22": "海水", "23": "海水", "24": "海水"
}


def analyze_weather_impact():
    """天候データとレース結果の関係を分析"""

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # weatherテーブルとレース結果を結合
    cursor.execute("""
        SELECT
            r.venue_code,
            r.race_date,
            r.race_number,
            w.wind_speed,
            w.wave_height,
            w.temperature,
            w.water_temperature,
            res.pit_number,
            res.rank,
            rd.actual_course
        FROM races r
        JOIN weather w ON r.venue_code = w.venue_code AND r.race_date = w.weather_date
        JOIN results res ON r.id = res.race_id
        LEFT JOIN race_details rd ON r.id = rd.race_id AND res.pit_number = rd.pit_number
        WHERE res.rank = '1'
        AND w.wind_speed IS NOT NULL
        ORDER BY r.venue_code, r.race_date
    """)

    results = cursor.fetchall()

    print("=" * 80)
    print("会場別 天候傾向分析")
    print("=" * 80)
    print(f"分析対象: {len(results)}件のレース結果（天候データあり）")

    if not results:
        print("\n天候データとレース結果の結合データがありません。")
        print("weatherテーブルのデータを確認してください。")
        conn.close()
        return

    # 会場別に集計
    venue_data = defaultdict(lambda: {
        'total': 0,
        'course1_wins': 0,
        'wind_speed': [],
        'wave_height': [],
        # 風速別1着コース
        'wind_low': defaultdict(int),    # 風速 0-2m
        'wind_mid': defaultdict(int),    # 風速 3-5m
        'wind_high': defaultdict(int),   # 風速 6m以上
        # 波高別1着コース
        'wave_low': defaultdict(int),    # 波高 0-2cm
        'wave_mid': defaultdict(int),    # 波高 3-5cm
        'wave_high': defaultdict(int),   # 波高 6cm以上
    })

    for row in results:
        venue = row['venue_code']
        wind = row['wind_speed'] or 0
        wave = row['wave_height'] or 0
        winner_pit = row['pit_number']
        winner_course = row['actual_course'] or winner_pit  # actual_courseがなければpit_number

        venue_data[venue]['total'] += 1
        venue_data[venue]['wind_speed'].append(wind)
        venue_data[venue]['wave_height'].append(wave)

        if winner_course == 1:
            venue_data[venue]['course1_wins'] += 1

        # 風速別
        if wind <= 2:
            venue_data[venue]['wind_low'][winner_course] += 1
        elif wind <= 5:
            venue_data[venue]['wind_mid'][winner_course] += 1
        else:
            venue_data[venue]['wind_high'][winner_course] += 1

        # 波高別
        if wave <= 2:
            venue_data[venue]['wave_low'][winner_course] += 1
        elif wave <= 5:
            venue_data[venue]['wave_mid'][winner_course] += 1
        else:
            venue_data[venue]['wave_high'][winner_course] += 1

    # 結果を表示
    print("\n" + "=" * 80)
    print("【会場別サマリー】")
    print("=" * 80)
    print(f"{'会場':^8s} | {'名称':^6s} | {'水質':^4s} | {'件数':>5s} | {'1コース勝率':>10s} | {'平均風速':>8s} | {'平均波高':>8s}")
    print("-" * 80)

    for venue in sorted(venue_data.keys()):
        data = venue_data[venue]
        name = VENUE_NAMES.get(venue, "不明")
        water = VENUE_WATER_TYPE.get(venue, "不明")
        total = data['total']
        course1_rate = data['course1_wins'] / total * 100 if total > 0 else 0
        avg_wind = statistics.mean(data['wind_speed']) if data['wind_speed'] else 0
        avg_wave = statistics.mean(data['wave_height']) if data['wave_height'] else 0

        print(f"  {venue}    | {name:^6s} | {water:^4s} | {total:5d} | {course1_rate:8.1f}% | {avg_wind:6.1f}m | {avg_wave:6.1f}cm")

    # 風速の影響分析
    print("\n" + "=" * 80)
    print("【風速別 1コース勝率】")
    print("=" * 80)
    print(f"{'会場':^8s} | {'名称':^6s} | {'弱風(0-2m)':>12s} | {'中風(3-5m)':>12s} | {'強風(6m+)':>12s} | {'差異':>8s}")
    print("-" * 80)

    significant_wind_venues = []

    for venue in sorted(venue_data.keys()):
        data = venue_data[venue]
        name = VENUE_NAMES.get(venue, "不明")

        # 各風速帯の1コース勝率
        low_total = sum(data['wind_low'].values())
        mid_total = sum(data['wind_mid'].values())
        high_total = sum(data['wind_high'].values())

        low_c1 = data['wind_low'].get(1, 0) / low_total * 100 if low_total > 0 else 0
        mid_c1 = data['wind_mid'].get(1, 0) / mid_total * 100 if mid_total > 0 else 0
        high_c1 = data['wind_high'].get(1, 0) / high_total * 100 if high_total > 0 else 0

        # 弱風と強風の差
        diff = low_c1 - high_c1 if low_total > 10 and high_total > 10 else None
        diff_str = f"{diff:+6.1f}%" if diff is not None else "N/A"

        print(f"  {venue}    | {name:^6s} | {low_c1:6.1f}%({low_total:3d}) | {mid_c1:6.1f}%({mid_total:3d}) | {high_c1:6.1f}%({high_total:3d}) | {diff_str}")

        if diff is not None and abs(diff) > 10:
            significant_wind_venues.append({
                'venue': venue,
                'name': name,
                'low_c1': low_c1,
                'high_c1': high_c1,
                'diff': diff
            })

    # 波高の影響分析
    print("\n" + "=" * 80)
    print("【波高別 1コース勝率】")
    print("=" * 80)
    print(f"{'会場':^8s} | {'名称':^6s} | {'静穏(0-2cm)':>12s} | {'中波(3-5cm)':>12s} | {'高波(6cm+)':>12s} | {'差異':>8s}")
    print("-" * 80)

    significant_wave_venues = []

    for venue in sorted(venue_data.keys()):
        data = venue_data[venue]
        name = VENUE_NAMES.get(venue, "不明")

        # 各波高帯の1コース勝率
        low_total = sum(data['wave_low'].values())
        mid_total = sum(data['wave_mid'].values())
        high_total = sum(data['wave_high'].values())

        low_c1 = data['wave_low'].get(1, 0) / low_total * 100 if low_total > 0 else 0
        mid_c1 = data['wave_mid'].get(1, 0) / mid_total * 100 if mid_total > 0 else 0
        high_c1 = data['wave_high'].get(1, 0) / high_total * 100 if high_total > 0 else 0

        # 静穏と高波の差
        diff = low_c1 - high_c1 if low_total > 10 and high_total > 10 else None
        diff_str = f"{diff:+6.1f}%" if diff is not None else "N/A"

        print(f"  {venue}    | {name:^6s} | {low_c1:6.1f}%({low_total:3d}) | {mid_c1:6.1f}%({mid_total:3d}) | {high_c1:6.1f}%({high_total:3d}) | {diff_str}")

        if diff is not None and abs(diff) > 10:
            significant_wave_venues.append({
                'venue': venue,
                'name': name,
                'low_c1': low_c1,
                'high_c1': high_c1,
                'diff': diff
            })

    # 法則性のまとめ
    print("\n" + "=" * 80)
    print("【発見された法則性】")
    print("=" * 80)

    if significant_wind_venues:
        print("\n■ 風速の影響が大きい会場（1コース勝率差10%以上）:")
        for v in significant_wind_venues:
            if v['diff'] > 0:
                print(f"  {v['name']}({v['venue']}): 弱風時 {v['low_c1']:.1f}% → 強風時 {v['high_c1']:.1f}% (差: {v['diff']:+.1f}%)")
                print(f"    → 強風時は1コースが不利、外枠に注目")
            else:
                print(f"  {v['name']}({v['venue']}): 弱風時 {v['low_c1']:.1f}% → 強風時 {v['high_c1']:.1f}% (差: {v['diff']:+.1f}%)")
                print(f"    → 強風時でも1コースが有利な特殊会場")
    else:
        print("\n■ 風速の影響が大きい会場: データ不足または有意差なし")

    if significant_wave_venues:
        print("\n■ 波高の影響が大きい会場（1コース勝率差10%以上）:")
        for v in significant_wave_venues:
            if v['diff'] > 0:
                print(f"  {v['name']}({v['venue']}): 静穏時 {v['low_c1']:.1f}% → 高波時 {v['high_c1']:.1f}% (差: {v['diff']:+.1f}%)")
                print(f"    → 高波時は1コースが不利、まくり・差しに注目")
            else:
                print(f"  {v['name']}({v['venue']}): 静穏時 {v['low_c1']:.1f}% → 高波時 {v['high_c1']:.1f}% (差: {v['diff']:+.1f}%)")
    else:
        print("\n■ 波高の影響が大きい会場: データ不足または有意差なし")

    conn.close()


def analyze_course_by_conditions():
    """条件別の各コース勝率を詳細分析"""

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 条件別勝率を集計
    cursor.execute("""
        SELECT
            r.venue_code,
            w.wind_speed,
            w.wave_height,
            COALESCE(rd.actual_course, res.pit_number) as winner_course,
            COUNT(*) as cnt
        FROM races r
        JOIN weather w ON r.venue_code = w.venue_code AND r.race_date = w.weather_date
        JOIN results res ON r.id = res.race_id
        LEFT JOIN race_details rd ON r.id = rd.race_id AND res.pit_number = rd.pit_number
        WHERE res.rank = '1'
        AND w.wind_speed IS NOT NULL
        GROUP BY r.venue_code,
                 CASE
                     WHEN w.wind_speed <= 2 THEN 'low'
                     WHEN w.wind_speed <= 5 THEN 'mid'
                     ELSE 'high'
                 END,
                 CASE
                     WHEN w.wave_height <= 2 THEN 'calm'
                     WHEN w.wave_height <= 5 THEN 'mid'
                     ELSE 'rough'
                 END,
                 COALESCE(rd.actual_course, res.pit_number)
    """)

    # 結果をまとめて表示（上位会場のみ）
    print("\n" + "=" * 80)
    print("【条件別コース勝率（全会場合計）】")
    print("=" * 80)

    # 全会場合計で集計
    cursor.execute("""
        SELECT
            CASE
                WHEN w.wind_speed <= 2 THEN 'wind_low'
                WHEN w.wind_speed <= 5 THEN 'wind_mid'
                ELSE 'wind_high'
            END as wind_cat,
            COALESCE(rd.actual_course, res.pit_number) as winner_course,
            COUNT(*) as cnt
        FROM races r
        JOIN weather w ON r.venue_code = w.venue_code AND r.race_date = w.weather_date
        JOIN results res ON r.id = res.race_id
        LEFT JOIN race_details rd ON r.id = rd.race_id AND res.pit_number = rd.pit_number
        WHERE res.rank = '1'
        AND w.wind_speed IS NOT NULL
        GROUP BY wind_cat, winner_course
    """)

    wind_stats = defaultdict(lambda: defaultdict(int))
    for row in cursor.fetchall():
        wind_stats[row[0]][row[1]] = row[2]

    print("\n風速別コース勝率:")
    print(f"{'風速':^12s} | {'1コース':>8s} | {'2コース':>8s} | {'3コース':>8s} | {'4コース':>8s} | {'5コース':>8s} | {'6コース':>8s}")
    print("-" * 80)

    for wind_cat in ['wind_low', 'wind_mid', 'wind_high']:
        total = sum(wind_stats[wind_cat].values())
        if total == 0:
            continue
        label = {'wind_low': '弱風(0-2m)', 'wind_mid': '中風(3-5m)', 'wind_high': '強風(6m+)'}[wind_cat]
        rates = [wind_stats[wind_cat].get(c, 0) / total * 100 for c in range(1, 7)]
        print(f"{label:^12s} | {rates[0]:6.1f}% | {rates[1]:6.1f}% | {rates[2]:6.1f}% | {rates[3]:6.1f}% | {rates[4]:6.1f}% | {rates[5]:6.1f}%")

    conn.close()


def check_tide_data():
    """潮位データの状況を確認"""

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("\n" + "=" * 80)
    print("【潮位データの状況】")
    print("=" * 80)

    cursor.execute("SELECT COUNT(*) FROM tide")
    count = cursor.fetchone()[0]
    print(f"\ntideテーブルのレコード数: {count}")

    if count == 0:
        print("\n潮位データがありません。")
        print("潮位データを収集する機能を確認・追加する必要があります。")

        # 海水会場のリスト
        print("\n潮位の影響がある会場（海水・汽水）:")
        for venue, water_type in sorted(VENUE_WATER_TYPE.items()):
            if water_type in ["海水", "汽水"]:
                print(f"  {venue}: {VENUE_NAMES.get(venue, '不明')} ({water_type})")
    else:
        cursor.execute("SELECT * FROM tide LIMIT 5")
        print("\nサンプルデータ:")
        for row in cursor.fetchall():
            print(row)

    conn.close()


if __name__ == "__main__":
    analyze_weather_impact()
    analyze_course_by_conditions()
    check_tide_data()
