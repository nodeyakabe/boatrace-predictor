# -*- coding: utf-8 -*-
"""
異常的中率パターン探索スクリプト

複合条件で的中率が異常に低下するパターンを発見:
- 会場 × スコア帯 × 月
- 会場 × 天候条件
- 会場 × レースグレード
- 会場 × 時間帯
- その他の複合条件
"""
import sys
import sqlite3
from pathlib import Path
from collections import defaultdict
import json

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from config.settings import DATABASE_PATH, VENUES

def get_venue_name(venue_code):
    """会場コードから会場名を取得"""
    for venue_id, venue_info in VENUES.items():
        if venue_info['code'] == venue_code:
            return venue_info['name']
    return f"会場{venue_code}"


def find_low_hit_patterns(min_sample=10, max_hit_rate=50.0):
    """
    複合条件で低的中率パターンを探索

    Args:
        min_sample: 最小サンプル数
        max_hit_rate: この的中率以下を「低い」と判定
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()

    # 全データ取得（天候・グレード・時間帯も含む）
    # まず予測データと実際の1着を別々に取得
    cur.execute("""
        SELECT
            r.id as race_id,
            r.venue_code,
            r.race_date,
            r.race_number,
            r.race_grade,
            r.race_time,
            rp.total_score,
            SUBSTR(r.race_date, 6, 2) as month,
            rc.wind_speed,
            rc.wave_height,
            rc.weather,
            rc.wind_direction,
            rp.pit_number as predicted_pit
        FROM races r
        INNER JOIN race_predictions rp ON r.id = rp.race_id
        LEFT JOIN race_conditions rc ON r.id = rc.race_id
        WHERE rp.prediction_type = 'before'
            AND rp.confidence = 'B'
            AND rp.rank_prediction = 1
            AND r.race_date >= '2025-01-01'
            AND r.race_date <= '2025-12-31'
    """)

    temp_data = cur.fetchall()

    # 実際の1着を確認
    data = []
    for row in temp_data:
        race_id = row[0]
        predicted_pit = row[12]

        # 実際の1着を取得
        cur.execute("""
            SELECT COUNT(*) FROM results
            WHERE race_id = ? AND pit_number = ? AND rank = 1
        """, (race_id, predicted_pit))

        is_hit = cur.fetchone()[0]
        data.append(row[:12] + (is_hit,))
    conn.close()

    print("=" * 100)
    print("異常的中率パターン探索（2025年BEFORE予測）")
    print("=" * 100)
    print(f"対象データ: {len(data)}レース")
    print(f"最小サンプル数: {min_sample}件")
    print(f"低的中率基準: {max_hit_rate}%以下")
    print("=" * 100)

    # スコア帯の定義
    def get_score_range(score):
        if score < 80: return "~80"
        elif score < 90: return "80-90"
        elif score < 100: return "90-100"
        elif score < 110: return "100-110"
        else: return "110+"

    # 時間帯の定義
    def get_time_slot(race_time):
        if not race_time:
            return "不明"
        try:
            hour = int(race_time.split(':')[0])
            if hour < 12:
                return "午前"
            elif hour < 15:
                return "午後前半"
            else:
                return "午後後半"
        except:
            return "不明"

    # 天候カテゴリ
    def get_weather_category(weather):
        if not weather:
            return "不明"
        if '晴' in weather or '曇' in weather:
            return "晴曇"
        elif '雨' in weather:
            return "雨"
        else:
            return weather

    # 1. 会場 × スコア帯 × 月
    print("\n【パターン1】会場 × スコア帯 × 月")
    print("-" * 100)

    pattern1 = defaultdict(lambda: {'total': 0, 'hits': 0})

    for row in data:
        venue_code, score, month = row[1], row[6], row[7]
        score_range = get_score_range(score)
        is_hit = row[12]  # 既に整数

        key = (venue_code, score_range, month)
        pattern1[key]['total'] += 1
        pattern1[key]['hits'] += is_hit

    anomalies_1 = []
    for key, stats in pattern1.items():
        if stats['total'] >= min_sample:
            hit_rate = stats['hits'] / stats['total'] * 100
            if hit_rate <= max_hit_rate:
                venue_name = get_venue_name(key[0])
                anomalies_1.append({
                    'venue': venue_name,
                    'score_range': key[1],
                    'month': key[2],
                    'total': stats['total'],
                    'hits': stats['hits'],
                    'hit_rate': hit_rate
                })

    anomalies_1.sort(key=lambda x: x['hit_rate'])

    if anomalies_1:
        print(f"{'会場':8s} | {'スコア帯':10s} | {'月':>4s} | {'件数':>6s} | {'的中':>6s} | {'的中率':>8s}")
        print("-" * 100)
        for a in anomalies_1[:20]:  # 上位20件
            print(f"{a['venue']:8s} | {a['score_range']:10s} | {a['month']:>4s} | {a['total']:6d} | {a['hits']:6d} | {a['hit_rate']:7.2f}%")
    else:
        print("  異常パターンなし")

    # 2. 会場 × 天候 × スコア帯
    print("\n【パターン2】会場 × 天候 × スコア帯")
    print("-" * 100)

    pattern2 = defaultdict(lambda: {'total': 0, 'hits': 0})

    for row in data:
        venue_code, score, weather = row[1], row[6], row[10]
        score_range = get_score_range(score)
        weather_cat = get_weather_category(weather)
        is_hit = row[12]

        key = (venue_code, weather_cat, score_range)
        pattern2[key]['total'] += 1
        pattern2[key]['hits'] += is_hit

    anomalies_2 = []
    for key, stats in pattern2.items():
        if stats['total'] >= min_sample:
            hit_rate = stats['hits'] / stats['total'] * 100
            if hit_rate <= max_hit_rate:
                venue_name = get_venue_name(key[0])
                anomalies_2.append({
                    'venue': venue_name,
                    'weather': key[1],
                    'score_range': key[2],
                    'total': stats['total'],
                    'hits': stats['hits'],
                    'hit_rate': hit_rate
                })

    anomalies_2.sort(key=lambda x: x['hit_rate'])

    if anomalies_2:
        print(f"{'会場':8s} | {'天候':8s} | {'スコア帯':10s} | {'件数':>6s} | {'的中':>6s} | {'的中率':>8s}")
        print("-" * 100)
        for a in anomalies_2[:20]:
            print(f"{a['venue']:8s} | {a['weather']:8s} | {a['score_range']:10s} | {a['total']:6d} | {a['hits']:6d} | {a['hit_rate']:7.2f}%")
    else:
        print("  異常パターンなし")

    # 3. 会場 × グレード × スコア帯
    print("\n【パターン3】会場 × グレード × スコア帯")
    print("-" * 100)

    pattern3 = defaultdict(lambda: {'total': 0, 'hits': 0})

    for row in data:
        venue_code, score, grade = row[1], row[6], row[4]
        score_range = get_score_range(score)
        grade = grade if grade else "一般"
        is_hit = row[12]

        key = (venue_code, grade, score_range)
        pattern3[key]['total'] += 1
        pattern3[key]['hits'] += is_hit

    anomalies_3 = []
    for key, stats in pattern3.items():
        if stats['total'] >= min_sample:
            hit_rate = stats['hits'] / stats['total'] * 100
            if hit_rate <= max_hit_rate:
                venue_name = get_venue_name(key[0])
                anomalies_3.append({
                    'venue': venue_name,
                    'grade': key[1],
                    'score_range': key[2],
                    'total': stats['total'],
                    'hits': stats['hits'],
                    'hit_rate': hit_rate
                })

    anomalies_3.sort(key=lambda x: x['hit_rate'])

    if anomalies_3:
        print(f"{'会場':8s} | {'グレード':12s} | {'スコア帯':10s} | {'件数':>6s} | {'的中':>6s} | {'的中率':>8s}")
        print("-" * 100)
        for a in anomalies_3[:20]:
            print(f"{a['venue']:8s} | {a['grade']:12s} | {a['score_range']:10s} | {a['total']:6d} | {a['hits']:6d} | {a['hit_rate']:7.2f}%")
    else:
        print("  異常パターンなし")

    # 4. 会場 × 時間帯 × スコア帯
    print("\n【パターン4】会場 × 時間帯 × スコア帯")
    print("-" * 100)

    pattern4 = defaultdict(lambda: {'total': 0, 'hits': 0})

    for row in data:
        venue_code, score, race_time = row[1], row[6], row[5]
        score_range = get_score_range(score)
        time_slot = get_time_slot(race_time)
        is_hit = row[12]

        key = (venue_code, time_slot, score_range)
        pattern4[key]['total'] += 1
        pattern4[key]['hits'] += is_hit

    anomalies_4 = []
    for key, stats in pattern4.items():
        if stats['total'] >= min_sample:
            hit_rate = stats['hits'] / stats['total'] * 100
            if hit_rate <= max_hit_rate:
                venue_name = get_venue_name(key[0])
                anomalies_4.append({
                    'venue': venue_name,
                    'time_slot': key[1],
                    'score_range': key[2],
                    'total': stats['total'],
                    'hits': stats['hits'],
                    'hit_rate': hit_rate
                })

    anomalies_4.sort(key=lambda x: x['hit_rate'])

    if anomalies_4:
        print(f"{'会場':8s} | {'時間帯':10s} | {'スコア帯':10s} | {'件数':>6s} | {'的中':>6s} | {'的中率':>8s}")
        print("-" * 100)
        for a in anomalies_4[:20]:
            print(f"{a['venue']:8s} | {a['time_slot']:10s} | {a['score_range']:10s} | {a['total']:6d} | {a['hits']:6d} | {a['hit_rate']:7.2f}%")
    else:
        print("  異常パターンなし")

    # 5. 風速・波高との関連
    print("\n【パターン5】会場 × 風速帯 × スコア帯")
    print("-" * 100)

    def get_wind_category(wind_speed):
        if wind_speed is None:
            return "不明"
        try:
            ws = float(wind_speed)
            if ws < 3:
                return "弱風"
            elif ws < 6:
                return "中風"
            else:
                return "強風"
        except:
            return "不明"

    pattern5 = defaultdict(lambda: {'total': 0, 'hits': 0})

    for row in data:
        venue_code, score, wind_speed = row[1], row[6], row[8]
        score_range = get_score_range(score)
        wind_cat = get_wind_category(wind_speed)
        is_hit = row[12]

        key = (venue_code, wind_cat, score_range)
        pattern5[key]['total'] += 1
        pattern5[key]['hits'] += is_hit

    anomalies_5 = []
    for key, stats in pattern5.items():
        if stats['total'] >= min_sample:
            hit_rate = stats['hits'] / stats['total'] * 100
            if hit_rate <= max_hit_rate:
                venue_name = get_venue_name(key[0])
                anomalies_5.append({
                    'venue': venue_name,
                    'wind': key[1],
                    'score_range': key[2],
                    'total': stats['total'],
                    'hits': stats['hits'],
                    'hit_rate': hit_rate
                })

    anomalies_5.sort(key=lambda x: x['hit_rate'])

    if anomalies_5:
        print(f"{'会場':8s} | {'風速':8s} | {'スコア帯':10s} | {'件数':>6s} | {'的中':>6s} | {'的中率':>8s}")
        print("-" * 100)
        for a in anomalies_5[:20]:
            print(f"{a['venue']:8s} | {a['wind']:8s} | {a['score_range']:10s} | {a['total']:6d} | {a['hits']:6d} | {a['hit_rate']:7.2f}%")
    else:
        print("  異常パターンなし")

    # 総合サマリー
    print("\n" + "=" * 100)
    print("異常パターン検出サマリー")
    print("=" * 100)
    print(f"パターン1（会場×スコア×月）: {len(anomalies_1)}件")
    print(f"パターン2（会場×天候×スコア）: {len(anomalies_2)}件")
    print(f"パターン3（会場×グレード×スコア）: {len(anomalies_3)}件")
    print(f"パターン4（会場×時間帯×スコア）: {len(anomalies_4)}件")
    print(f"パターン5（会場×風速×スコア）: {len(anomalies_5)}件")

    total_anomalies = len(anomalies_1) + len(anomalies_2) + len(anomalies_3) + len(anomalies_4) + len(anomalies_5)
    print(f"\n合計異常パターン: {total_anomalies}件")

    # 最も危険なパターンTOP10
    all_anomalies = []
    for a in anomalies_1:
        all_anomalies.append({
            'type': '会場×スコア×月',
            'description': f"{a['venue']} {a['score_range']} {a['month']}月",
            'total': a['total'],
            'hit_rate': a['hit_rate']
        })
    for a in anomalies_2:
        all_anomalies.append({
            'type': '会場×天候×スコア',
            'description': f"{a['venue']} {a['weather']} {a['score_range']}",
            'total': a['total'],
            'hit_rate': a['hit_rate']
        })
    for a in anomalies_3:
        all_anomalies.append({
            'type': '会場×グレード×スコア',
            'description': f"{a['venue']} {a['grade']} {a['score_range']}",
            'total': a['total'],
            'hit_rate': a['hit_rate']
        })
    for a in anomalies_4:
        all_anomalies.append({
            'type': '会場×時間×スコア',
            'description': f"{a['venue']} {a['time_slot']} {a['score_range']}",
            'total': a['total'],
            'hit_rate': a['hit_rate']
        })
    for a in anomalies_5:
        all_anomalies.append({
            'type': '会場×風速×スコア',
            'description': f"{a['venue']} {a['wind']} {a['score_range']}",
            'total': a['total'],
            'hit_rate': a['hit_rate']
        })

    all_anomalies.sort(key=lambda x: x['hit_rate'])

    if all_anomalies:
        print("\n【最も危険なパターン TOP10】")
        print("-" * 100)
        print(f"{'タイプ':18s} | {'条件':40s} | {'件数':>6s} | {'的中率':>8s}")
        print("-" * 100)
        for a in all_anomalies[:10]:
            print(f"{a['type']:18s} | {a['description']:40s} | {a['total']:6d} | {a['hit_rate']:7.2f}%")

    print("\n" + "=" * 100)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='異常的中率パターン探索')
    parser.add_argument('--min-sample', type=int, default=10, help='最小サンプル数')
    parser.add_argument('--max-hit-rate', type=float, default=50.0, help='低的中率基準')

    args = parser.parse_args()

    find_low_hit_patterns(args.min_sample, args.max_hit_rate)
