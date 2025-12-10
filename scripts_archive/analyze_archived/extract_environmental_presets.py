# -*- coding: utf-8 -*-
"""環境要因プリセットの抽出

天候・潮位・風向・波高などの環境要因と直前情報の組み合わせパターンを抽出する。

優先度B: 環境要因プリセット
- 潮位×場 (干満×会場の特性)
- 風向×展示タイム
- 波高×ST
"""

import sys
import sqlite3
from pathlib import Path
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.analysis.race_predictor import RacePredictor


def extract_environmental_presets(db_path, limit=200):
    """
    環境要因プリセットの抽出

    Args:
        db_path: データベースパス
        limit: 分析するレース数

    Returns:
        dict: 抽出された法則性
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 2025年で直前情報が存在するレースを取得
    cursor.execute('''
        SELECT DISTINCT r.id, r.venue_code
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        AND rd.exhibition_time IS NOT NULL
        ORDER BY r.race_date, r.race_number
        LIMIT ?
    ''', (limit,))
    race_info = cursor.fetchall()

    print("=" * 80)
    print("環境要因プリセットの抽出")
    print("=" * 80)
    print()
    print(f"分析対象レース数: {len(race_info)}")
    print()

    # 統計用の辞書を初期化
    patterns_tide = {}
    patterns_wind = {}
    patterns_wave = {}

    # PRE予測を取得するためのインスタンス
    predictor = RacePredictor(db_path)

    # 各レースを走査
    for race_id, venue_code in race_info:
        # 環境情報を取得
        cursor.execute('''
            SELECT weather, wind_direction, wind_speed, wave_height, water_temperature
            FROM races
            WHERE id = ?
        ''', (race_id,))
        env_row = cursor.fetchone()

        if not env_row:
            continue

        weather, wind_direction, wind_speed, wave_height, water_temp = env_row

        # レース内の全艇データを取得
        cursor.execute('''
            SELECT
                rd.pit_number,
                CAST(res.rank AS INTEGER) as finish_position,
                rd.exhibition_time,
                rd.st_time
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            WHERE rd.race_id = ?
            ORDER BY rd.pit_number
        ''', (race_id,))

        race_data = cursor.fetchall()

        if len(race_data) < 6:
            continue

        # 展示タイム順位を計算
        exhibition_times = [(row[0], row[2]) for row in race_data if row[2] is not None]
        if len(exhibition_times) >= 6:
            exhibition_times_sorted = sorted(exhibition_times, key=lambda x: x[1])
            exhibition_rank_map = {pit: rank+1 for rank, (pit, _) in enumerate(exhibition_times_sorted)}
        else:
            exhibition_rank_map = {}

        # ST順位を計算
        st_times = [(row[0], row[3]) for row in race_data if row[3] is not None]
        if len(st_times) >= 6:
            st_times_sorted = sorted(st_times, key=lambda x: abs(x[1]))
            st_rank_map = {pit: rank+1 for rank, (pit, _) in enumerate(st_times_sorted)}
        else:
            st_rank_map = {}

        # PRE順位を取得
        try:
            predictions = predictor.predict_race(race_id)
            if predictions and len(predictions) >= 6:
                pre_rank_map = {pred['pit_number']: i+1 for i, pred in enumerate(predictions)}
            else:
                pre_rank_map = {}
        except:
            pre_rank_map = {}

        # 各艇の条件を記録
        for row in race_data:
            pit_number = row[0]
            finish_position = row[1]

            if finish_position is None:
                continue

            is_win = 1 if finish_position == 1 else 0

            ex_rank = exhibition_rank_map.get(pit_number)
            st_rank = st_rank_map.get(pit_number)
            pre_rank = pre_rank_map.get(pit_number)

            # 【潮位パターン】（データが無いので簡易的に時間帯で代用）
            # 会場ごとに干満の特性が異なる
            # ここではプレースホルダーとして記録

            # 【風向×展示タイムパターン】
            if wind_direction is not None and ex_rank is not None and pre_rank is not None:
                # 追い風（wind_direction = 1-4）& 展示1位
                if wind_direction in [1, 2, 3, 4]:
                    add_pattern(patterns_wind, 'tailwind_ex1', ex_rank == 1, is_win)
                    add_pattern(patterns_wind, 'tailwind_ex1_pre1',
                               ex_rank == 1 and pre_rank == 1, is_win)

                # 向かい風（wind_direction = 5-8）& ST1位
                if wind_direction in [5, 6, 7, 8]:
                    add_pattern(patterns_wind, 'headwind_st1', st_rank == 1 if st_rank else False, is_win)
                    add_pattern(patterns_wind, 'headwind_st1_pre1',
                               st_rank == 1 and pre_rank == 1 if st_rank else False, is_win)

                # 横風（wind_direction = 3, 7）& コース2-3
                if wind_direction in [3, 7] and pit_number in [2, 3]:
                    add_pattern(patterns_wind, 'crosswind_course2_3',
                               pit_number in [2, 3], is_win)
                    add_pattern(patterns_wind, 'crosswind_course2_3_ex1_2',
                               pit_number in [2, 3] and ex_rank <= 2 if ex_rank else False, is_win)

            # 【波高×展示タイム・STパターン】
            if wave_height is not None and ex_rank is not None and st_rank is not None and pre_rank is not None:
                # 荒れた水面（wave_height >= 2）& 展示1位
                if wave_height >= 2.0:
                    add_pattern(patterns_wave, 'rough_ex1', ex_rank == 1, is_win)
                    add_pattern(patterns_wave, 'rough_ex1_pre1',
                               ex_rank == 1 and pre_rank == 1, is_win)

                # 穏やかな水面（wave_height <= 0.5）& ST1位
                if wave_height <= 0.5:
                    add_pattern(patterns_wave, 'calm_st1', st_rank == 1, is_win)
                    add_pattern(patterns_wave, 'calm_st1_pre1',
                               st_rank == 1 and pre_rank == 1, is_win)

                # 荒れた水面 & PRE1位 & 展示1-3位
                if wave_height >= 2.0:
                    add_pattern(patterns_wave, 'rough_pre1_ex1_3',
                               pre_rank == 1 and ex_rank <= 3, is_win)

    # 結果を表示
    print("=" * 80)
    print("抽出された法則性")
    print("=" * 80)
    print()

    # ベースライン（理論値）
    baseline = 1.0 / 6.0 * 100  # 16.67%

    # カテゴリ別に表示
    display_category(patterns_wind, baseline, "風向×BEFORE", [
        'tailwind_ex1',
        'tailwind_ex1_pre1',
        'headwind_st1',
        'headwind_st1_pre1',
        'crosswind_course2_3',
        'crosswind_course2_3_ex1_2',
    ])

    display_category(patterns_wave, baseline, "波高×BEFORE", [
        'rough_ex1',
        'rough_ex1_pre1',
        'calm_st1',
        'calm_st1_pre1',
        'rough_pre1_ex1_3',
    ])

    # 推奨プリセットの抽出
    print()
    print("=" * 80)
    print("推奨プリセット（1着率20%以上または効果+5%以上）")
    print("=" * 80)
    print()

    recommended_wind = extract_recommended(patterns_wind, baseline, 20.0, 5.0)
    recommended_wave = extract_recommended(patterns_wave, baseline, 20.0, 5.0)

    print("【風向×BEFORE】")
    print(f"{'パターン名':<40} {'該当数':<10} {'1着数':<10} {'1着率':<10} {'効果':<10} {'推奨ボーナス':<15}")
    print("-" * 105)
    for preset in recommended_wind:
        bonus_multiplier = 1.0 + (preset['effect'] / 100.0 * 0.6)
        print(f"{get_pattern_description_wind(preset['name']):<40} "
              f"{preset['count']:<10} "
              f"{preset['wins']:<10} "
              f"{preset['win_rate']:>6.2f}% "
              f"{preset['effect']:>+7.2f}% "
              f"x{bonus_multiplier:.3f}")
    print()

    print("【波高×BEFORE】")
    print(f"{'パターン名':<40} {'該当数':<10} {'1着数':<10} {'1着率':<10} {'効果':<10} {'推奨ボーナス':<15}")
    print("-" * 105)
    for preset in recommended_wave:
        bonus_multiplier = 1.0 + (preset['effect'] / 100.0 * 0.6)
        print(f"{get_pattern_description_wave(preset['name']):<40} "
              f"{preset['count']:<10} "
              f"{preset['wins']:<10} "
              f"{preset['win_rate']:>6.2f}% "
              f"{preset['effect']:>+7.2f}% "
              f"x{bonus_multiplier:.3f}")
    print()

    conn.close()

    return patterns_wind, patterns_wave, recommended_wind, recommended_wave


def add_pattern(patterns, pattern_name, condition, is_win):
    """パターンに該当するデータを記録"""
    if pattern_name not in patterns:
        patterns[pattern_name] = {'count': 0, 'wins': 0}

    if condition:
        patterns[pattern_name]['count'] += 1
        patterns[pattern_name]['wins'] += is_win


def display_category(patterns, baseline, category_name, pattern_names):
    """カテゴリ別の結果表示"""
    print(f"【{category_name}】")
    print()
    print(f"{'パターン':<40} {'該当数':<10} {'1着数':<10} {'1着率':<10} {'効果':<10}")
    print("-" * 80)

    for pattern_name in pattern_names:
        if pattern_name in patterns:
            stats = patterns[pattern_name]
            if stats['count'] > 0:
                win_rate = stats['wins'] / stats['count'] * 100
                effect = win_rate - baseline
                print(f"{pattern_name:<40} "
                      f"{stats['count']:<10} "
                      f"{stats['wins']:<10} "
                      f"{win_rate:>6.2f}% "
                      f"{effect:>+7.2f}%")
            else:
                print(f"{pattern_name:<40} {'0':<10} {'0':<10} {'N/A':<10} {'N/A':<10}")

    print()


def extract_recommended(patterns, baseline, min_rate, min_effect):
    """推奨プリセットの抽出"""
    recommended = []

    for pattern_name, stats in patterns.items():
        if stats['count'] > 0:
            win_rate = stats['wins'] / stats['count'] * 100
            effect = win_rate - baseline

            if win_rate >= min_rate or effect >= min_effect:
                recommended.append({
                    'name': pattern_name,
                    'win_rate': win_rate,
                    'effect': effect,
                    'count': stats['count'],
                    'wins': stats['wins']
                })

    recommended.sort(key=lambda x: x['effect'], reverse=True)
    return recommended


def get_pattern_description_wind(pattern_name):
    """風向パターン名を説明文に変換"""
    descriptions = {
        'tailwind_ex1': '追い風 & 展示1位',
        'tailwind_ex1_pre1': '追い風 & 展示1位 & PRE1位',
        'headwind_st1': '向かい風 & ST1位',
        'headwind_st1_pre1': '向かい風 & ST1位 & PRE1位',
        'crosswind_course2_3': '横風 & コース2-3',
        'crosswind_course2_3_ex1_2': '横風 & コース2-3 & 展示1-2位',
    }
    return descriptions.get(pattern_name, pattern_name)


def get_pattern_description_wave(pattern_name):
    """波高パターン名を説明文に変換"""
    descriptions = {
        'rough_ex1': '荒れた水面(≥2m) & 展示1位',
        'rough_ex1_pre1': '荒れた水面(≥2m) & 展示1位 & PRE1位',
        'calm_st1': '穏やかな水面(≤0.5m) & ST1位',
        'calm_st1_pre1': '穏やかな水面(≤0.5m) & ST1位 & PRE1位',
        'rough_pre1_ex1_3': '荒れた水面(≥2m) & PRE1位 & 展示1-3位',
    }
    return descriptions.get(pattern_name, pattern_name)


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"

    (patterns_wind, patterns_wave,
     recommended_wind, recommended_wave) = extract_environmental_presets(db_path, limit=200)

    print()
    print("分析完了")
    print()


if __name__ == '__main__':
    main()
