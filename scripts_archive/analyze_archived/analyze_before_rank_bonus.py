# -*- coding: utf-8 -*-
"""BEFORE順位別の1着率分析

各BEFORE要素（展示タイム、ST）の順位別に1着率を測定し、
条件付きボーナス方式の妥当性を検証する。

例：「展示1位なら1着率+10%」は実際に効果があるか？
"""

import sys
import sqlite3
from pathlib import Path
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


def analyze_before_rank_bonus(db_path, limit=200):
    """
    BEFORE順位別の1着率を分析

    Args:
        db_path: データベースパス
        limit: 分析するレース数

    Returns:
        dict: 分析結果
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
    print("BEFORE順位別1着率分析")
    print("=" * 80)
    print()
    print(f"分析対象レース数: {len(race_ids)}")
    print()

    # 展示タイム順位別の統計
    exhibition_rank_stats = {i: {'total': 0, 'wins': 0} for i in range(1, 7)}

    # ST順位別の統計
    st_rank_stats = {i: {'total': 0, 'wins': 0} for i in range(1, 7)}

    # BEFORE総合順位別の統計（展示タイム+ST総合）
    before_total_rank_stats = {i: {'total': 0, 'wins': 0} for i in range(1, 7)}

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

        # ST順位を計算（0に近いほど良い）
        st_times = [(row[0], row[3]) for row in race_data if row[3] is not None]
        if len(st_times) >= 6:
            st_times_sorted = sorted(st_times, key=lambda x: abs(x[1]))
            st_rank_map = {pit: rank+1 for rank, (pit, _) in enumerate(st_times_sorted)}
        else:
            st_rank_map = {}

        # BEFORE総合順位（展示タイム順位とST順位の合計、小さいほど良い）
        before_total_scores = {}
        for pit in range(1, 7):
            ex_rank = exhibition_rank_map.get(pit, 3.5)  # データなしは平均
            st_rank = st_rank_map.get(pit, 3.5)
            before_total_scores[pit] = ex_rank + st_rank

        before_total_sorted = sorted(before_total_scores.items(), key=lambda x: x[1])
        before_total_rank_map = {pit: rank+1 for rank, (pit, _) in enumerate(before_total_sorted)}

        # 各艇の統計を更新
        for row in race_data:
            pit_number = row[0]
            finish_position = row[1]

            if finish_position is None:
                continue

            is_win = 1 if finish_position == 1 else 0

            # 展示タイム順位
            if pit_number in exhibition_rank_map:
                rank = exhibition_rank_map[pit_number]
                exhibition_rank_stats[rank]['total'] += 1
                exhibition_rank_stats[rank]['wins'] += is_win

            # ST順位
            if pit_number in st_rank_map:
                rank = st_rank_map[pit_number]
                st_rank_stats[rank]['total'] += 1
                st_rank_stats[rank]['wins'] += is_win

            # BEFORE総合順位
            if pit_number in before_total_rank_map:
                rank = before_total_rank_map[pit_number]
                before_total_rank_stats[rank]['total'] += 1
                before_total_rank_stats[rank]['wins'] += is_win

    # 結果表示
    print("=" * 80)
    print("【1. 展示タイム順位別の1着率】")
    print("=" * 80)
    print()

    print(f"{'順位':<6} {'出走数':<10} {'1着回数':<10} {'1着率':<10} {'ベースライン差':<15}")
    print("-" * 60)

    baseline_win_rate = 1.0 / 6.0 * 100  # 理論値16.67%

    exhibition_results = {}
    for rank in range(1, 7):
        stats = exhibition_rank_stats[rank]
        if stats['total'] > 0:
            win_rate = stats['wins'] / stats['total'] * 100
            diff = win_rate - baseline_win_rate
            print(f"{rank:<6} {stats['total']:<10} {stats['wins']:<10} {win_rate:>6.2f}% {diff:>+13.2f}%")
            exhibition_results[rank] = win_rate
        else:
            print(f"{rank:<6} {'0':<10} {'0':<10} {'N/A':<10} {'N/A':<15}")
            exhibition_results[rank] = 0.0

    print()

    # 展示1位の実際の1着率
    if exhibition_results[1] > 0:
        ex_1st_bonus = exhibition_results[1] - baseline_win_rate
        print(f"💡 展示1位の1着率: {exhibition_results[1]:.2f}% (ベースライン+{ex_1st_bonus:.2f}%)")
        print(f"   → 展示1位ボーナスの目安: +{ex_1st_bonus:.1f}% ~ +{ex_1st_bonus*1.5:.1f}%")
    print()

    # ST順位
    print("=" * 80)
    print("【2. ST順位別の1着率】")
    print("=" * 80)
    print()

    print(f"{'順位':<6} {'出走数':<10} {'1着回数':<10} {'1着率':<10} {'ベースライン差':<15}")
    print("-" * 60)

    st_results = {}
    for rank in range(1, 7):
        stats = st_rank_stats[rank]
        if stats['total'] > 0:
            win_rate = stats['wins'] / stats['total'] * 100
            diff = win_rate - baseline_win_rate
            print(f"{rank:<6} {stats['total']:<10} {stats['wins']:<10} {win_rate:>6.2f}% {diff:>+13.2f}%")
            st_results[rank] = win_rate
        else:
            print(f"{rank:<6} {'0':<10} {'0':<10} {'N/A':<10} {'N/A':<15}")
            st_results[rank] = 0.0

    print()

    if st_results[1] > 0:
        st_1st_bonus = st_results[1] - baseline_win_rate
        print(f"💡 ST1位の1着率: {st_results[1]:.2f}% (ベースライン+{st_1st_bonus:.2f}%)")
        print(f"   → ST1位ボーナスの目安: +{st_1st_bonus:.1f}% ~ +{st_1st_bonus*1.5:.1f}%")
        print()
        print(f"⚠️  注意: ST順位の相関は疑似相関の可能性あり（強い選手→良いST）")
    print()

    # BEFORE総合順位
    print("=" * 80)
    print("【3. BEFORE総合順位別の1着率】")
    print("=" * 80)
    print()
    print("※ 展示タイム順位 + ST順位の合計で評価")
    print()

    print(f"{'順位':<6} {'出走数':<10} {'1着回数':<10} {'1着率':<10} {'ベースライン差':<15}")
    print("-" * 60)

    before_total_results = {}
    for rank in range(1, 7):
        stats = before_total_rank_stats[rank]
        if stats['total'] > 0:
            win_rate = stats['wins'] / stats['total'] * 100
            diff = win_rate - baseline_win_rate
            print(f"{rank:<6} {stats['total']:<10} {stats['wins']:<10} {win_rate:>6.2f}% {diff:>+13.2f}%")
            before_total_results[rank] = win_rate
        else:
            print(f"{rank:<6} {'0':<10} {'0':<10} {'N/A':<10} {'N/A':<15}")
            before_total_results[rank] = 0.0

    print()

    if before_total_results[1] > 0:
        before_1st_bonus = before_total_results[1] - baseline_win_rate
        print(f"💡 BEFORE総合1位の1着率: {before_total_results[1]:.2f}% (ベースライン+{before_1st_bonus:.2f}%)")
        print(f"   → BEFORE総合1位ボーナスの目安: +{before_1st_bonus:.1f}% ~ +{before_1st_bonus*1.5:.1f}%")
    print()

    # 推奨ボーナス設定
    print("=" * 80)
    print("【推奨ボーナス設定】")
    print("=" * 80)
    print()

    print("条件付きボーナス方式の実装例:")
    print()

    # 展示1位ボーナス
    if exhibition_results[1] > baseline_win_rate * 1.2:  # 20%以上向上なら推奨
        ex_bonus = ex_1st_bonus / 100  # パーセントから倍率へ
        print(f"1. 展示タイム1位ボーナス")
        print(f"   条件: 展示タイム = レース内1位")
        print(f"   効果: PRE_SCORE × {1 + ex_bonus:.3f} (約+{ex_1st_bonus:.1f}%)")
        print(f"   実装: if exhibition_rank == 1: score *= {1 + ex_bonus:.3f}")
        print()

    # BEFORE総合1位ボーナス
    if before_total_results[1] > baseline_win_rate * 1.3:  # 30%以上向上なら推奨
        before_bonus = before_1st_bonus / 100
        print(f"2. BEFORE総合1位ボーナス（推奨）")
        print(f"   条件: 展示タイム順位 + ST順位 = レース内最小")
        print(f"   効果: PRE_SCORE × {1 + before_bonus:.3f} (約+{before_1st_bonus:.1f}%)")
        print(f"   実装: if before_total_rank == 1: score *= {1 + before_bonus:.3f}")
        print()

    # ネガティブボーナス（下位ペナルティ）
    if before_total_results[6] < baseline_win_rate * 0.5:  # 50%以下なら推奨
        print(f"3. BEFORE総合6位ペナルティ")
        print(f"   条件: 展示タイム順位 + ST順位 = レース内最大")
        print(f"   効果: PRE_SCORE × 0.90 (約-10%)")
        print(f"   実装: if before_total_rank == 6: score *= 0.90")
        print()

    # 展示・ST両方1位のスーパーボーナス
    both_1st_count = 0
    both_1st_wins = 0

    # 再度データを走査して「展示1位かつST1位」の統計を取得
    for race_id in race_ids:
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

        exhibition_times = [(row[0], row[2]) for row in race_data if row[2] is not None]
        st_times = [(row[0], row[3]) for row in race_data if row[3] is not None]

        if len(exhibition_times) < 6 or len(st_times) < 6:
            continue

        ex_sorted = sorted(exhibition_times, key=lambda x: x[1])
        st_sorted = sorted(st_times, key=lambda x: abs(x[1]))

        ex_1st_pit = ex_sorted[0][0]
        st_1st_pit = st_sorted[0][0]

        # 展示1位とST1位が同じ艇の場合
        if ex_1st_pit == st_1st_pit:
            both_1st_count += 1
            finish_pos = next((row[1] for row in race_data if row[0] == ex_1st_pit), None)
            if finish_pos == 1:
                both_1st_wins += 1

    if both_1st_count > 0:
        both_1st_win_rate = both_1st_wins / both_1st_count * 100
        both_1st_bonus_pct = both_1st_win_rate - baseline_win_rate
        both_1st_bonus = both_1st_bonus_pct / 100

        print(f"4. 展示1位 & ST1位 スーパーボーナス")
        print(f"   条件: 展示タイム1位 かつ ST1位")
        print(f"   該当: {both_1st_count}レース, 1着: {both_1st_wins}回, 1着率: {both_1st_win_rate:.2f}%")
        print(f"   効果: PRE_SCORE × {1 + both_1st_bonus:.3f} (約+{both_1st_bonus_pct:.1f}%)")
        print(f"   実装: if exhibition_rank == 1 and st_rank == 1: score *= {1 + both_1st_bonus:.3f}")
        print()

    print()
    print("=" * 80)
    print("結論")
    print("=" * 80)
    print()

    print("条件付きボーナス方式は以下の理由で推奨:")
    print()
    print("✅ PRE_SCOREを直接汚染しない（掛け算による微調整）")
    print("✅ 明確な条件（1位・6位など）でシンプル")
    print("✅ 実データに基づいたボーナス率設定が可能")
    print("✅ 法則性・プリセット適用と同様の仕組みで実装容易")
    print()

    print("次のステップ:")
    print("1. 最も効果の高いボーナス条件を1つ選んで実装")
    print("2. バックテストで55.5%以上の的中率を確認")
    print("3. 効果があれば、他のボーナス条件も追加")
    print()

    conn.close()

    return {
        'exhibition_rank_stats': exhibition_results,
        'st_rank_stats': st_results,
        'before_total_rank_stats': before_total_results,
        'both_1st': {
            'count': both_1st_count,
            'wins': both_1st_wins,
            'win_rate': both_1st_win_rate if both_1st_count > 0 else 0.0
        }
    }


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"

    results = analyze_before_rank_bonus(db_path, limit=200)

    print()
    print("分析完了")
    print()


if __name__ == '__main__':
    main()
