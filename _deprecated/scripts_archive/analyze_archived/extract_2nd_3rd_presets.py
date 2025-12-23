# -*- coding: utf-8 -*-
"""2着・3着予測プリセットの抽出

1着ではなく、2着・3着に対するBEFORE情報のパターンを抽出する。

優先度A: 2着・3着予測プリセット
- 2着率が高いパターン
- 3着率が高いパターン
- 三連単・三連複の購入戦略に活用
"""

import sys
import sqlite3
from pathlib import Path
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.analysis.race_predictor import RacePredictor


def extract_2nd_3rd_presets(db_path, limit=200):
    """
    2着・3着予測プリセットの抽出

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
        SELECT DISTINCT r.id
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        AND rd.exhibition_time IS NOT NULL
        ORDER BY r.race_date, r.race_number
        LIMIT ?
    ''', (limit,))
    race_ids = [row[0] for row in cursor.fetchall()]

    print("=" * 80)
    print("2着・3着予測プリセットの抽出")
    print("=" * 80)
    print()
    print(f"分析対象レース数: {len(race_ids)}")
    print()

    # 統計用の辞書を初期化
    patterns_2nd = {}
    patterns_3rd = {}
    patterns_top3 = {}  # 3着以内

    # PRE予測を取得するためのインスタンス
    predictor = RacePredictor(db_path)

    # 各レースを走査
    for race_id in race_ids:
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

            is_2nd = 1 if finish_position == 2 else 0
            is_3rd = 1 if finish_position == 3 else 0
            is_top3 = 1 if finish_position <= 3 else 0

            ex_rank = exhibition_rank_map.get(pit_number)
            st_rank = st_rank_map.get(pit_number)
            pre_rank = pre_rank_map.get(pit_number)

            # 【2着パターン】
            if ex_rank is not None and st_rank is not None and pre_rank is not None:
                # 展示2位
                add_pattern(patterns_2nd, 'ex_rank_2', ex_rank == 2, is_2nd)

                # 展示1-3位（PRE2-3位）
                add_pattern(patterns_2nd, 'ex1_3_pre2_3', ex_rank <= 3 and 2 <= pre_rank <= 3, is_2nd)

                # PRE2位 & 展示1-3位
                add_pattern(patterns_2nd, 'pre2_ex1_3', pre_rank == 2 and ex_rank <= 3, is_2nd)

                # ST2-3位
                add_pattern(patterns_2nd, 'st_rank_2_3', 2 <= st_rank <= 3, is_2nd)

                # PRE2位 & ST1-3位
                add_pattern(patterns_2nd, 'pre2_st1_3', pre_rank == 2 and st_rank <= 3, is_2nd)

                # PRE2位 & 展示1-3位 & ST1-3位
                add_pattern(patterns_2nd, 'pre2_ex1_3_st1_3',
                           pre_rank == 2 and ex_rank <= 3 and st_rank <= 3, is_2nd)

                # PRE2-3位 & 展示1-2位
                add_pattern(patterns_2nd, 'pre2_3_ex1_2',
                           2 <= pre_rank <= 3 and ex_rank <= 2, is_2nd)

                # PRE2-3位 & ST1-2位
                add_pattern(patterns_2nd, 'pre2_3_st1_2',
                           2 <= pre_rank <= 3 and st_rank <= 2, is_2nd)

            # 【3着パターン】
            if ex_rank is not None and st_rank is not None and pre_rank is not None:
                # 展示3-4位
                add_pattern(patterns_3rd, 'ex_rank_3_4', 3 <= ex_rank <= 4, is_3rd)

                # PRE3-4位 & 展示2-4位
                add_pattern(patterns_3rd, 'pre3_4_ex2_4',
                           3 <= pre_rank <= 4 and 2 <= ex_rank <= 4, is_3rd)

                # ST3-4位
                add_pattern(patterns_3rd, 'st_rank_3_4', 3 <= st_rank <= 4, is_3rd)

                # PRE3位 & 展示1-3位
                add_pattern(patterns_3rd, 'pre3_ex1_3', pre_rank == 3 and ex_rank <= 3, is_3rd)

                # PRE3位 & ST1-3位
                add_pattern(patterns_3rd, 'pre3_st1_3', pre_rank == 3 and st_rank <= 3, is_3rd)

                # アウトコース（4-6枠）& 展示1-2位
                add_pattern(patterns_3rd, 'outer_ex1_2',
                           pit_number >= 4 and ex_rank <= 2, is_3rd)

                # アウトコース（4-6枠）& ST1-2位
                add_pattern(patterns_3rd, 'outer_st1_2',
                           pit_number >= 4 and st_rank <= 2, is_3rd)

                # PRE3-4位 & 展示1-3位 & ST1-3位
                add_pattern(patterns_3rd, 'pre3_4_ex1_3_st1_3',
                           3 <= pre_rank <= 4 and ex_rank <= 3 and st_rank <= 3, is_3rd)

            # 【3着以内パターン】（三連単・三連複用）
            if ex_rank is not None and st_rank is not None and pre_rank is not None:
                # 展示1-2位
                add_pattern(patterns_top3, 'ex_rank_1_2', ex_rank <= 2, is_top3)

                # PRE1-3位 & 展示1-3位
                add_pattern(patterns_top3, 'pre1_3_ex1_3',
                           pre_rank <= 3 and ex_rank <= 3, is_top3)

                # PRE1-3位 & ST1-3位
                add_pattern(patterns_top3, 'pre1_3_st1_3',
                           pre_rank <= 3 and st_rank <= 3, is_top3)

                # PRE1-4位 & 展示1-2位
                add_pattern(patterns_top3, 'pre1_4_ex1_2',
                           pre_rank <= 4 and ex_rank <= 2, is_top3)

                # 展示1-3位 & ST1-3位
                add_pattern(patterns_top3, 'ex1_3_st1_3',
                           ex_rank <= 3 and st_rank <= 3, is_top3)

    # 結果を表示
    print("=" * 80)
    print("抽出された法則性")
    print("=" * 80)
    print()

    # ベースライン（理論値）
    baseline_2nd = 1.0 / 6.0 * 100  # 16.67%
    baseline_3rd = 1.0 / 6.0 * 100  # 16.67%
    baseline_top3 = 3.0 / 6.0 * 100  # 50.00%

    # カテゴリ別に表示
    display_category(patterns_2nd, baseline_2nd, "2着率パターン", [
        'ex_rank_2',
        'ex1_3_pre2_3',
        'pre2_ex1_3',
        'st_rank_2_3',
        'pre2_st1_3',
        'pre2_ex1_3_st1_3',
        'pre2_3_ex1_2',
        'pre2_3_st1_2',
    ])

    display_category(patterns_3rd, baseline_3rd, "3着率パターン", [
        'ex_rank_3_4',
        'pre3_4_ex2_4',
        'st_rank_3_4',
        'pre3_ex1_3',
        'pre3_st1_3',
        'outer_ex1_2',
        'outer_st1_2',
        'pre3_4_ex1_3_st1_3',
    ])

    display_category(patterns_top3, baseline_top3, "3着以内パターン", [
        'ex_rank_1_2',
        'pre1_3_ex1_3',
        'pre1_3_st1_3',
        'pre1_4_ex1_2',
        'ex1_3_st1_3',
    ])

    # 推奨プリセットの抽出
    print()
    print("=" * 80)
    print("推奨プリセット（2着率または3着率が20%以上、または効果+5%以上）")
    print("=" * 80)
    print()

    recommended_2nd = extract_recommended(patterns_2nd, baseline_2nd, 20.0, 5.0)
    recommended_3rd = extract_recommended(patterns_3rd, baseline_3rd, 20.0, 5.0)
    recommended_top3 = extract_recommended(patterns_top3, baseline_top3, 55.0, 5.0)

    print("【2着予測】")
    print(f"{'パターン名':<35} {'該当数':<10} {'2着数':<10} {'2着率':<10} {'効果':<10} {'推奨ボーナス':<15}")
    print("-" * 100)
    for preset in recommended_2nd:
        bonus_multiplier = 1.0 + (preset['effect'] / 100.0 * 0.6)
        print(f"{get_pattern_description_2nd(preset['name']):<35} "
              f"{preset['count']:<10} "
              f"{preset['wins']:<10} "
              f"{preset['win_rate']:>6.2f}% "
              f"{preset['effect']:>+7.2f}% "
              f"x{bonus_multiplier:.3f}")
    print()

    print("【3着予測】")
    print(f"{'パターン名':<35} {'該当数':<10} {'3着数':<10} {'3着率':<10} {'効果':<10} {'推奨ボーナス':<15}")
    print("-" * 100)
    for preset in recommended_3rd:
        bonus_multiplier = 1.0 + (preset['effect'] / 100.0 * 0.6)
        print(f"{get_pattern_description_3rd(preset['name']):<35} "
              f"{preset['count']:<10} "
              f"{preset['wins']:<10} "
              f"{preset['win_rate']:>6.2f}% "
              f"{preset['effect']:>+7.2f}% "
              f"x{bonus_multiplier:.3f}")
    print()

    print("【3着以内予測】")
    print(f"{'パターン名':<35} {'該当数':<10} {'3着以内数':<12} {'3着以内率':<12} {'効果':<10} {'推奨ボーナス':<15}")
    print("-" * 105)
    for preset in recommended_top3:
        bonus_multiplier = 1.0 + (preset['effect'] / 100.0 * 0.6)
        print(f"{get_pattern_description_top3(preset['name']):<35} "
              f"{preset['count']:<10} "
              f"{preset['wins']:<12} "
              f"{preset['win_rate']:>6.2f}% "
              f"{preset['effect']:>+7.2f}% "
              f"x{bonus_multiplier:.3f}")
    print()

    conn.close()

    return patterns_2nd, patterns_3rd, patterns_top3, recommended_2nd, recommended_3rd, recommended_top3


def add_pattern(patterns, pattern_name, condition, is_target):
    """パターンに該当するデータを記録"""
    if pattern_name not in patterns:
        patterns[pattern_name] = {'count': 0, 'wins': 0}

    if condition:
        patterns[pattern_name]['count'] += 1
        patterns[pattern_name]['wins'] += is_target


def display_category(patterns, baseline, category_name, pattern_names):
    """カテゴリ別の結果表示"""
    print(f"【{category_name}】")
    print()
    print(f"{'パターン':<35} {'該当数':<10} {'目標着数':<12} {'目標着率':<12} {'効果':<10}")
    print("-" * 80)

    for pattern_name in pattern_names:
        if pattern_name in patterns:
            stats = patterns[pattern_name]
            if stats['count'] > 0:
                win_rate = stats['wins'] / stats['count'] * 100
                effect = win_rate - baseline
                print(f"{pattern_name:<35} "
                      f"{stats['count']:<10} "
                      f"{stats['wins']:<12} "
                      f"{win_rate:>6.2f}% "
                      f"{effect:>+7.2f}%")
            else:
                print(f"{pattern_name:<35} {'0':<10} {'0':<12} {'N/A':<12} {'N/A':<10}")

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


def get_pattern_description_2nd(pattern_name):
    """2着パターン名を説明文に変換"""
    descriptions = {
        'ex_rank_2': '展示2位',
        'ex1_3_pre2_3': '展示1-3位 & PRE2-3位',
        'pre2_ex1_3': 'PRE2位 & 展示1-3位',
        'st_rank_2_3': 'ST2-3位',
        'pre2_st1_3': 'PRE2位 & ST1-3位',
        'pre2_ex1_3_st1_3': 'PRE2位 & 展示1-3位 & ST1-3位',
        'pre2_3_ex1_2': 'PRE2-3位 & 展示1-2位',
        'pre2_3_st1_2': 'PRE2-3位 & ST1-2位',
    }
    return descriptions.get(pattern_name, pattern_name)


def get_pattern_description_3rd(pattern_name):
    """3着パターン名を説明文に変換"""
    descriptions = {
        'ex_rank_3_4': '展示3-4位',
        'pre3_4_ex2_4': 'PRE3-4位 & 展示2-4位',
        'st_rank_3_4': 'ST3-4位',
        'pre3_ex1_3': 'PRE3位 & 展示1-3位',
        'pre3_st1_3': 'PRE3位 & ST1-3位',
        'outer_ex1_2': 'アウトコース(4-6枠) & 展示1-2位',
        'outer_st1_2': 'アウトコース(4-6枠) & ST1-2位',
        'pre3_4_ex1_3_st1_3': 'PRE3-4位 & 展示1-3位 & ST1-3位',
    }
    return descriptions.get(pattern_name, pattern_name)


def get_pattern_description_top3(pattern_name):
    """3着以内パターン名を説明文に変換"""
    descriptions = {
        'ex_rank_1_2': '展示1-2位',
        'pre1_3_ex1_3': 'PRE1-3位 & 展示1-3位',
        'pre1_3_st1_3': 'PRE1-3位 & ST1-3位',
        'pre1_4_ex1_2': 'PRE1-4位 & 展示1-2位',
        'ex1_3_st1_3': '展示1-3位 & ST1-3位',
    }
    return descriptions.get(pattern_name, pattern_name)


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"

    (patterns_2nd, patterns_3rd, patterns_top3,
     recommended_2nd, recommended_3rd, recommended_top3) = extract_2nd_3rd_presets(db_path, limit=200)

    print()
    print("分析完了")
    print()


if __name__ == '__main__':
    main()
