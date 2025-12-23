# -*- coding: utf-8 -*-
"""直前情報から法則性を抽出

プリセット方式と同じ手順で、直前情報の様々な条件下での1着率を測定し、
効果のある法則性（パターン）を発見する。

フェーズ1: 法則性の抽出
- 展示タイム順位別
- ST順位別
- 複合条件（展示×ST）
- PRE順位との組み合わせ
- その他BEFORE要素
"""

import sys
import sqlite3
from pathlib import Path
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.analysis.race_predictor import RacePredictor


def extract_before_patterns(db_path, limit=200):
    """
    直前情報から法則性を抽出

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
    print("直前情報からの法則性抽出")
    print("=" * 80)
    print()
    print(f"分析対象レース数: {len(race_ids)}")
    print()

    # 統計用の辞書を初期化
    patterns = {}

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
                rd.st_time,
                rd.tilt_angle
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

            # パターン1: 展示タイム順位
            if ex_rank is not None:
                # 展示1位
                add_pattern(patterns, 'exhibition_rank_1', ex_rank == 1, is_win)
                # 展示6位
                add_pattern(patterns, 'exhibition_rank_6', ex_rank == 6, is_win)
                # 展示1-2位
                add_pattern(patterns, 'exhibition_rank_1_2', ex_rank <= 2, is_win)
                # 展示1-3位
                add_pattern(patterns, 'exhibition_rank_1_3', ex_rank <= 3, is_win)
                # 展示5-6位
                add_pattern(patterns, 'exhibition_rank_5_6', ex_rank >= 5, is_win)

            # パターン2: ST順位
            if st_rank is not None:
                # ST1位
                add_pattern(patterns, 'st_rank_1', st_rank == 1, is_win)
                # ST6位
                add_pattern(patterns, 'st_rank_6', st_rank == 6, is_win)
                # ST1-2位
                add_pattern(patterns, 'st_rank_1_2', st_rank <= 2, is_win)
                # ST1-3位
                add_pattern(patterns, 'st_rank_1_3', st_rank <= 3, is_win)

            # パターン3: 展示×ST複合条件
            if ex_rank is not None and st_rank is not None:
                # 展示1位 & ST1位
                add_pattern(patterns, 'ex1_st1', ex_rank == 1 and st_rank == 1, is_win)
                # 展示1位 & ST2-3位
                add_pattern(patterns, 'ex1_st2_3', ex_rank == 1 and 2 <= st_rank <= 3, is_win)
                # 展示1位 & ST4-6位
                add_pattern(patterns, 'ex1_st4_6', ex_rank == 1 and st_rank >= 4, is_win)
                # 展示1-3位 & ST1-3位（両方上位）
                add_pattern(patterns, 'ex1_3_st1_3', ex_rank <= 3 and st_rank <= 3, is_win)
                # 展示4-6位 & ST4-6位（両方下位）
                add_pattern(patterns, 'ex4_6_st4_6', ex_rank >= 4 and st_rank >= 4, is_win)

            # パターン4: PRE×展示複合条件
            if pre_rank is not None and ex_rank is not None:
                # PRE1位 & 展示1位
                add_pattern(patterns, 'pre1_ex1', pre_rank == 1 and ex_rank == 1, is_win)
                # PRE1位 & 展示1-3位
                add_pattern(patterns, 'pre1_ex1_3', pre_rank == 1 and ex_rank <= 3, is_win)
                # PRE1位 & 展示4-6位
                add_pattern(patterns, 'pre1_ex4_6', pre_rank == 1 and ex_rank >= 4, is_win)
                # PRE2-3位 & 展示1位（逆転の可能性）
                add_pattern(patterns, 'pre2_3_ex1', 2 <= pre_rank <= 3 and ex_rank == 1, is_win)
                # PRE1-3位 & 展示1-3位（両方上位）
                add_pattern(patterns, 'pre1_3_ex1_3', pre_rank <= 3 and ex_rank <= 3, is_win)

            # パターン5: PRE×ST複合条件
            if pre_rank is not None and st_rank is not None:
                # PRE1位 & ST1位
                add_pattern(patterns, 'pre1_st1', pre_rank == 1 and st_rank == 1, is_win)
                # PRE1位 & ST1-3位
                add_pattern(patterns, 'pre1_st1_3', pre_rank == 1 and st_rank <= 3, is_win)
                # PRE1位 & ST4-6位
                add_pattern(patterns, 'pre1_st4_6', pre_rank == 1 and st_rank >= 4, is_win)

            # パターン6: 3要素複合（PRE×展示×ST）
            if pre_rank is not None and ex_rank is not None and st_rank is not None:
                # PRE1位 & 展示1位 & ST1位（トリプル1位）
                add_pattern(patterns, 'pre1_ex1_st1',
                           pre_rank == 1 and ex_rank == 1 and st_rank == 1, is_win)
                # PRE1位 & 展示1-3位 & ST1-3位（全て上位）
                add_pattern(patterns, 'pre1_ex1_3_st1_3',
                           pre_rank == 1 and ex_rank <= 3 and st_rank <= 3, is_win)

    # 結果を表示
    print("=" * 80)
    print("抽出された法則性")
    print("=" * 80)
    print()

    # ベースライン（理論値）
    baseline = 1.0 / 6.0 * 100  # 16.67%

    # カテゴリ別に表示
    display_category(patterns, baseline, "展示タイム順位", [
        'exhibition_rank_1',
        'exhibition_rank_6',
        'exhibition_rank_1_2',
        'exhibition_rank_1_3',
        'exhibition_rank_5_6',
    ])

    display_category(patterns, baseline, "ST順位", [
        'st_rank_1',
        'st_rank_6',
        'st_rank_1_2',
        'st_rank_1_3',
    ])

    display_category(patterns, baseline, "展示×ST複合条件", [
        'ex1_st1',
        'ex1_st2_3',
        'ex1_st4_6',
        'ex1_3_st1_3',
        'ex4_6_st4_6',
    ])

    display_category(patterns, baseline, "PRE×展示複合条件", [
        'pre1_ex1',
        'pre1_ex1_3',
        'pre1_ex4_6',
        'pre2_3_ex1',
        'pre1_3_ex1_3',
    ])

    display_category(patterns, baseline, "PRE×ST複合条件", [
        'pre1_st1',
        'pre1_st1_3',
        'pre1_st4_6',
    ])

    display_category(patterns, baseline, "3要素複合（PRE×展示×ST）", [
        'pre1_ex1_st1',
        'pre1_ex1_3_st1_3',
    ])

    # 推奨プリセットの抽出
    print()
    print("=" * 80)
    print("推奨プリセット（1着率20%以上または効果+5%以上）")
    print("=" * 80)
    print()

    recommended_presets = []

    for pattern_name, stats in patterns.items():
        if stats['count'] > 0:
            win_rate = stats['wins'] / stats['count'] * 100
            effect = win_rate - baseline

            # 1着率20%以上、または効果+5%以上のパターンを推奨
            if win_rate >= 20.0 or effect >= 5.0:
                recommended_presets.append({
                    'name': pattern_name,
                    'win_rate': win_rate,
                    'effect': effect,
                    'count': stats['count'],
                    'wins': stats['wins']
                })

    # 効果順にソート
    recommended_presets.sort(key=lambda x: x['effect'], reverse=True)

    print(f"{'パターン名':<30} {'該当数':<10} {'1着数':<10} {'1着率':<10} {'効果':<10} {'推奨ボーナス':<15}")
    print("-" * 95)

    for preset in recommended_presets:
        bonus_multiplier = 1.0 + (preset['effect'] / 100.0 * 0.6)  # 効果の60%をボーナスに
        print(f"{get_pattern_description(preset['name']):<30} "
              f"{preset['count']:<10} "
              f"{preset['wins']:<10} "
              f"{preset['win_rate']:>6.2f}% "
              f"{preset['effect']:>+7.2f}% "
              f"x{bonus_multiplier:.3f}")

    print()
    print("=" * 80)
    print("次のステップ")
    print("=" * 80)
    print()
    print("1. 上記の推奨プリセットから、実装する条件を選定")
    print("2. 各プリセットを個別にバックテストで検証")
    print("3. 効果があるプリセットのみを採用")
    print()

    conn.close()

    return patterns, recommended_presets


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
    print(f"{'パターン':<30} {'該当数':<10} {'1着数':<10} {'1着率':<10} {'効果':<10}")
    print("-" * 70)

    for pattern_name in pattern_names:
        if pattern_name in patterns:
            stats = patterns[pattern_name]
            if stats['count'] > 0:
                win_rate = stats['wins'] / stats['count'] * 100
                effect = win_rate - baseline
                print(f"{get_pattern_description(pattern_name):<30} "
                      f"{stats['count']:<10} "
                      f"{stats['wins']:<10} "
                      f"{win_rate:>6.2f}% "
                      f"{effect:>+7.2f}%")
            else:
                print(f"{get_pattern_description(pattern_name):<30} {'0':<10} {'0':<10} {'N/A':<10} {'N/A':<10}")

    print()


def get_pattern_description(pattern_name):
    """パターン名を説明文に変換"""
    descriptions = {
        'exhibition_rank_1': '展示1位',
        'exhibition_rank_6': '展示6位',
        'exhibition_rank_1_2': '展示1-2位',
        'exhibition_rank_1_3': '展示1-3位',
        'exhibition_rank_5_6': '展示5-6位',
        'st_rank_1': 'ST1位',
        'st_rank_6': 'ST6位',
        'st_rank_1_2': 'ST1-2位',
        'st_rank_1_3': 'ST1-3位',
        'ex1_st1': '展示1位 & ST1位',
        'ex1_st2_3': '展示1位 & ST2-3位',
        'ex1_st4_6': '展示1位 & ST4-6位',
        'ex1_3_st1_3': '展示1-3位 & ST1-3位',
        'ex4_6_st4_6': '展示4-6位 & ST4-6位',
        'pre1_ex1': 'PRE1位 & 展示1位',
        'pre1_ex1_3': 'PRE1位 & 展示1-3位',
        'pre1_ex4_6': 'PRE1位 & 展示4-6位',
        'pre2_3_ex1': 'PRE2-3位 & 展示1位',
        'pre1_3_ex1_3': 'PRE1-3位 & 展示1-3位',
        'pre1_st1': 'PRE1位 & ST1位',
        'pre1_st1_3': 'PRE1位 & ST1-3位',
        'pre1_st4_6': 'PRE1位 & ST4-6位',
        'pre1_ex1_st1': 'PRE1位 & 展示1位 & ST1位',
        'pre1_ex1_3_st1_3': 'PRE1位 & 展示1-3位 & ST1-3位',
    }
    return descriptions.get(pattern_name, pattern_name)


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"

    patterns, recommended_presets = extract_before_patterns(db_path, limit=200)

    print()
    print("分析完了")
    print()


if __name__ == '__main__':
    main()
