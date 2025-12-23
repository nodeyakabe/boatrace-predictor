# -*- coding: utf-8 -*-
"""BEFORE各要素の個別予測力測定

各BEFORE要素（展示タイム、ST、チルト角度、部品交換など）が
実際の着順とどれだけ相関しているかを個別に測定し、
データ駆動型の配点最適化の基礎データを提供する。
"""

import sys
import sqlite3
from pathlib import Path
import numpy as np
from scipy.stats import spearmanr, pointbiserialr
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


def analyze_element_correlation(db_path, limit=200):
    """
    BEFORE各要素の個別予測力測定

    Args:
        db_path: データベースパス
        limit: 分析するレース数

    Returns:
        dict: 各要素の分析結果
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

    print(f"分析対象レース数: {len(race_ids)}")
    print()

    # 各要素のデータを収集
    elements_data = {
        'exhibition_time': {'values': [], 'finish_positions': [], 'wins': []},
        'st_time': {'values': [], 'finish_positions': [], 'wins': []},
        'tilt_angle': {'values': [], 'finish_positions': [], 'wins': []},
        'has_fl': {'values': [], 'finish_positions': [], 'wins': []},
    }

    # 展示タイムとSTのレース内順位データ
    exhibition_rank_data = {'values': [], 'finish_positions': [], 'wins': []}
    st_rank_data = {'values': [], 'finish_positions': [], 'wins': []}

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

        # 展示タイムとSTのレース内順位を計算
        exhibition_times = [(row[0], row[2]) for row in race_data if row[2] is not None]
        st_times = [(row[0], row[3]) for row in race_data if row[3] is not None]

        # 展示タイムは小さいほど良い（昇順で順位付け）
        exhibition_times_sorted = sorted(exhibition_times, key=lambda x: x[1])
        exhibition_rank_map = {pit: rank+1 for rank, (pit, _) in enumerate(exhibition_times_sorted)}

        # STは0に近いほど良い（絶対値で昇順）
        st_times_sorted = sorted(st_times, key=lambda x: abs(x[1]))
        st_rank_map = {pit: rank+1 for rank, (pit, _) in enumerate(st_times_sorted)}

        # 各艇のデータを記録
        for row in race_data:
            pit_number = row[0]
            finish_position = row[1]
            exhibition_time = row[2]
            st_time = row[3]
            tilt_angle = row[4]

            if finish_position is None:
                continue

            is_win = 1 if finish_position == 1 else 0

            # 展示タイム（絶対値）
            if exhibition_time is not None:
                elements_data['exhibition_time']['values'].append(exhibition_time)
                elements_data['exhibition_time']['finish_positions'].append(finish_position)
                elements_data['exhibition_time']['wins'].append(is_win)

            # 展示タイム（レース内順位）
            if pit_number in exhibition_rank_map:
                exhibition_rank_data['values'].append(exhibition_rank_map[pit_number])
                exhibition_rank_data['finish_positions'].append(finish_position)
                exhibition_rank_data['wins'].append(is_win)

            # ST（絶対値）
            if st_time is not None:
                elements_data['st_time']['values'].append(abs(st_time))
                elements_data['st_time']['finish_positions'].append(finish_position)
                elements_data['st_time']['wins'].append(is_win)

                # F/L（0/1フラグ） - st_time < -1.0 (フライング) or st_time > 1.0 (出遅れ)
                has_fl = 1 if (st_time < -1.0 or st_time > 1.0) else 0
                elements_data['has_fl']['values'].append(has_fl)
                elements_data['has_fl']['finish_positions'].append(finish_position)
                elements_data['has_fl']['wins'].append(is_win)

            # ST（レース内順位）
            if pit_number in st_rank_map:
                st_rank_data['values'].append(st_rank_map[pit_number])
                st_rank_data['finish_positions'].append(finish_position)
                st_rank_data['wins'].append(is_win)

            # チルト角度
            if tilt_angle is not None:
                elements_data['tilt_angle']['values'].append(tilt_angle)
                elements_data['tilt_angle']['finish_positions'].append(finish_position)
                elements_data['tilt_angle']['wins'].append(is_win)

    # 結果表示
    print("=" * 80)
    print("BEFORE各要素の個別予測力測定")
    print("=" * 80)
    print()

    results = {}

    # 1. 展示タイム（絶対値）
    print("【1. 展示タイム（絶対値）】")
    analyze_and_display_element(
        '展示タイム',
        elements_data['exhibition_time'],
        is_lower_better=True,
        results_dict=results
    )
    print()

    # 2. 展示タイム（レース内順位）
    print("【2. 展示タイム（レース内順位）】")
    analyze_and_display_element(
        '展示タイム順位',
        exhibition_rank_data,
        is_rank=True,
        results_dict=results
    )
    print()

    # 3. ST（絶対値）
    print("【3. スタートタイミング（絶対値）】")
    analyze_and_display_element(
        'ST',
        elements_data['st_time'],
        is_lower_better=True,
        results_dict=results
    )
    print()

    # 4. ST（レース内順位）
    print("【4. スタートタイミング（レース内順位）】")
    analyze_and_display_element(
        'ST順位',
        st_rank_data,
        is_rank=True,
        results_dict=results
    )
    print()

    # 5. チルト角度
    print("【5. チルト角度】")
    analyze_and_display_element(
        'チルト角度',
        elements_data['tilt_angle'],
        results_dict=results
    )
    print()

    # 6. F/Lフラグ
    print("【6. フライング/出遅れフラグ】")
    analyze_and_display_element(
        'F/L',
        elements_data['has_fl'],
        is_binary=True,
        results_dict=results
    )
    print()

    # 総合評価
    print("=" * 80)
    print("総合評価とスコア配点推奨")
    print("=" * 80)
    print()

    # 相関係数でソート
    sorted_elements = sorted(results.items(), key=lambda x: abs(x[1]['correlation']), reverse=True)

    print("【予測力ランキング（相関係数の絶対値）】")
    for i, (name, data) in enumerate(sorted_elements, 1):
        print(f"{i}. {name}: {abs(data['correlation']):.3f}")
    print()

    # 現在の配点と推奨配点
    print("【現在の配点 vs 推奨配点】")
    print()

    current_weights = {
        '展示タイム順位': 25,
        'ST順位': 25,
        'チルト角度': 10,
        'F/L': 0,  # 現在未使用
    }

    # 相関係数に基づく推奨配点（合計100点）
    total_abs_correlation = sum(abs(data['correlation']) for _, data in sorted_elements)

    print(f"{'要素名':<20} {'現在配点':>10} {'予測力':>10} {'推奨配点':>10} {'差分':>10}")
    print("-" * 70)

    for name, current_weight in current_weights.items():
        if name in results:
            correlation = abs(results[name]['correlation'])
            recommended_weight = int(100 * correlation / total_abs_correlation)
            diff = recommended_weight - current_weight

            print(f"{name:<20} {current_weight:>10}点 {correlation:>10.3f} {recommended_weight:>10}点 {diff:>+10}点")
        else:
            print(f"{name:<20} {current_weight:>10}点 {'N/A':>10} {'N/A':>10} {'N/A':>10}")

    print()

    # 結論
    print("=" * 80)
    print("結論")
    print("=" * 80)
    print()

    # 最も予測力が高い要素
    best_element = sorted_elements[0]
    worst_element = sorted_elements[-1]

    print(f"最も予測力が高い要素: {best_element[0]} (相関係数: {abs(best_element[1]['correlation']):.3f})")
    print(f"最も予測力が低い要素: {worst_element[0]} (相関係数: {abs(worst_element[1]['correlation']):.3f})")
    print()

    print("推奨される改善策:")
    print()

    # 展示タイム順位とST順位の比較
    if '展示タイム順位' in results and 'ST順位' in results:
        ex_corr = abs(results['展示タイム順位']['correlation'])
        st_corr = abs(results['ST順位']['correlation'])

        if ex_corr > st_corr * 1.5:
            print(f"1. 展示タイム順位の配点を増やすべき（現在25点 → 推奨35-40点）")
            print(f"   理由: ST順位より{ex_corr/st_corr:.1f}倍予測力が高い")
            print()

        if st_corr < 0.15:
            print(f"2. ST順位の配点を減らすべき（現在25点 → 推奨10-15点）")
            print(f"   理由: 予測力が低い（相関係数{st_corr:.3f}）")
            print()

    # F/Lフラグの評価
    if 'F/L' in results:
        fl_corr = abs(results['F/L']['correlation'])
        fl_win_rate_diff = results['F/L'].get('win_rate_diff', 0)

        if fl_corr > 0.1 or abs(fl_win_rate_diff) > 10:
            print(f"3. F/Lフラグを新設すべき（推奨15-20点）")
            print(f"   理由: F/L有無で1着率に{abs(fl_win_rate_diff):.1f}%の差")
            print()

    print()
    print("=" * 80)

    return results


def analyze_and_display_element(name, data, is_lower_better=False, is_rank=False,
                                 is_binary=False, results_dict=None):
    """
    要素の分析結果を表示

    Args:
        name: 要素名
        data: データ辞書（values, finish_positions, wins）
        is_lower_better: 値が小さいほど良い場合True
        is_rank: 順位データの場合True
        is_binary: 0/1の二値データの場合True
        results_dict: 結果を格納する辞書（オプション）
    """
    values = np.array(data['values'])
    finish_positions = np.array(data['finish_positions'])
    wins = np.array(data['wins'])

    print(f"データ数: {len(values)}艇")

    # 相関係数（スピアマン順位相関）
    if is_binary:
        # 二値変数の場合は点双列相関係数
        correlation, p_value = pointbiserialr(values, finish_positions)
        print(f"点双列相関係数: {correlation:.3f} (p={p_value:.4f})")
    else:
        correlation, p_value = spearmanr(values, finish_positions)
        print(f"スピアマン順位相関係数: {correlation:.3f} (p={p_value:.4f})")

    # 解釈
    abs_corr = abs(correlation)
    if abs_corr > 0.5:
        interpretation = "非常に強い相関"
    elif abs_corr > 0.3:
        interpretation = "強い相関"
    elif abs_corr > 0.15:
        interpretation = "中程度の相関"
    elif abs_corr > 0.05:
        interpretation = "弱い相関"
    else:
        interpretation = "ほぼ相関なし"

    print(f"解釈: {interpretation}")

    if is_lower_better or is_rank:
        print(f"  → 値が{'小さい' if is_lower_better else '順位が良い'}ほど着順が良い" if correlation < 0 else
              f"  → 値が{'小さい' if is_lower_better else '順位が良い'}ほど着順が悪い（逆相関）")

    # 二値データの場合の追加分析
    if is_binary:
        # 0と1のグループ別の1着率
        group_0_wins = wins[values == 0]
        group_1_wins = wins[values == 1]

        if len(group_0_wins) > 0:
            win_rate_0 = np.mean(group_0_wins) * 100
        else:
            win_rate_0 = 0

        if len(group_1_wins) > 0:
            win_rate_1 = np.mean(group_1_wins) * 100
        else:
            win_rate_1 = 0

        print(f"{name}なし: {len(group_0_wins)}艇, 1着率 {win_rate_0:.1f}%")
        print(f"{name}あり: {len(group_1_wins)}艇, 1着率 {win_rate_1:.1f}%")
        print(f"差分: {win_rate_1 - win_rate_0:+.1f}%")

        if results_dict is not None:
            results_dict[name] = {
                'correlation': correlation,
                'p_value': p_value,
                'interpretation': interpretation,
                'win_rate_diff': win_rate_1 - win_rate_0
            }

    # 順位データまたは連続値の場合
    else:
        # 上位群と下位群の1着率比較
        if is_rank:
            # 1-2位 vs 5-6位
            top_group = wins[values <= 2]
            bottom_group = wins[values >= 5]
        else:
            # 中央値で分割
            median_value = np.median(values)
            if is_lower_better:
                top_group = wins[values <= median_value]
                bottom_group = wins[values > median_value]
            else:
                top_group = wins[values >= median_value]
                bottom_group = wins[values < median_value]

        if len(top_group) > 0:
            top_win_rate = np.mean(top_group) * 100
        else:
            top_win_rate = 0

        if len(bottom_group) > 0:
            bottom_win_rate = np.mean(bottom_group) * 100
        else:
            bottom_win_rate = 0

        print(f"上位群: {len(top_group)}艇, 1着率 {top_win_rate:.1f}%")
        print(f"下位群: {len(bottom_group)}艇, 1着率 {bottom_win_rate:.1f}%")
        print(f"差分: {top_win_rate - bottom_win_rate:+.1f}%")

        if results_dict is not None:
            results_dict[name] = {
                'correlation': correlation,
                'p_value': p_value,
                'interpretation': interpretation,
                'win_rate_diff': top_win_rate - bottom_win_rate
            }


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"

    print("=" * 80)
    print("BEFORE各要素の個別予測力測定")
    print("=" * 80)
    print()

    results = analyze_element_correlation(db_path, limit=200)

    print()
    print("分析完了")
    print()


if __name__ == '__main__':
    main()
