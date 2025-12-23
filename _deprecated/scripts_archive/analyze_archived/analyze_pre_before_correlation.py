# -*- coding: utf-8 -*-
"""PRE_SCOREとBEFORE_SCOREの相関分析

PRE順位とBEFORE順位がどれだけ相関しているかを調査し、
統合失敗の原因を特定する
"""

import sys
import sqlite3
from pathlib import Path
import numpy as np
from scipy.stats import spearmanr

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.analysis.race_predictor import RacePredictor
from src.analysis.beforeinfo_scorer import BeforeInfoScorer


def analyze_pre_before_correlation(db_path, limit=200):
    """
    PRE_SCOREとBEFORE_SCOREの相関分析

    Args:
        db_path: データベースパス
        limit: 分析するレース数

    Returns:
        dict: 分析結果
    """
    predictor = RacePredictor(db_path, use_cache=False)
    before_scorer = BeforeInfoScorer(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
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
    race_ids = [row['id'] for row in cursor.fetchall()]

    print(f"分析対象レース数: {len(race_ids)}")
    print()

    # 統計データ
    stats = {
        'total_races': 0,
        'pre_before_rank_match_1st': 0,  # PRE 1位 = BEFORE 1位
        'pre_before_rank_match_top3': 0,  # PRE上位3位とBEFORE上位3位の重複数
        'spearman_correlations': [],  # レースごとのスピアマン順位相関係数
        'pre_1st_before_ranks': [],  # PRE 1位の艇のBEFORE順位
        'before_1st_pre_ranks': [],  # BEFORE 1位の艇のPRE順位
        'rank_differences': [],  # 各艇のPRE順位 - BEFORE順位
    }

    for race_id in race_ids:
        # PRE予測を取得
        try:
            predictions = predictor.predict_race(race_id)
        except Exception as e:
            continue

        if not predictions or len(predictions) < 6:
            continue

        # BEFOREスコアを取得
        before_scores = {}
        for pit in range(1, 7):
            result = before_scorer.calculate_beforeinfo_score(race_id, pit)
            before_scores[pit] = result.get('total_score', 0.0)

        # PRE順位を作成
        pre_ranking = {pred['pit_number']: i+1 for i, pred in enumerate(predictions)}

        # BEFORE順位を作成
        before_ranking_list = sorted(before_scores.items(), key=lambda x: x[1], reverse=True)
        before_ranking = {pit: i+1 for i, (pit, score) in enumerate(before_ranking_list)}

        stats['total_races'] += 1

        # PRE 1位 = BEFORE 1位の一致確認
        pre_1st = predictions[0]['pit_number']
        before_1st = before_ranking_list[0][0]

        if pre_1st == before_1st:
            stats['pre_before_rank_match_1st'] += 1

        # PRE上位3位とBEFORE上位3位の重複確認
        pre_top3 = set([pred['pit_number'] for pred in predictions[:3]])
        before_top3 = set([pit for pit, score in before_ranking_list[:3]])
        overlap = len(pre_top3 & before_top3)
        stats['pre_before_rank_match_top3'] += overlap

        # PRE 1位の艇のBEFORE順位
        stats['pre_1st_before_ranks'].append(before_ranking[pre_1st])

        # BEFORE 1位の艇のPRE順位
        stats['before_1st_pre_ranks'].append(pre_ranking[before_1st])

        # スピアマン順位相関係数
        pre_ranks = [pre_ranking[pit] for pit in range(1, 7)]
        before_ranks = [before_ranking[pit] for pit in range(1, 7)]

        correlation, _ = spearmanr(pre_ranks, before_ranks)
        stats['spearman_correlations'].append(correlation)

        # 各艇の順位差
        for pit in range(1, 7):
            rank_diff = pre_ranking[pit] - before_ranking[pit]
            stats['rank_differences'].append(abs(rank_diff))

    conn.close()

    # 結果表示
    print("=" * 80)
    print("PRE_SCOREとBEFORE_SCOREの相関分析")
    print("=" * 80)
    print()

    print(f"分析完了レース数: {stats['total_races']}")
    print()

    # 1位一致率
    match_rate_1st = stats['pre_before_rank_match_1st'] / stats['total_races'] * 100
    print(f"【PRE 1位 = BEFORE 1位の一致率】")
    print(f"  {stats['pre_before_rank_match_1st']}/{stats['total_races']} = {match_rate_1st:.1f}%")
    print()

    # 上位3位の重複
    avg_overlap = stats['pre_before_rank_match_top3'] / stats['total_races']
    print(f"【PRE上位3位とBEFORE上位3位の平均重複数】")
    print(f"  {avg_overlap:.2f}艇/レース（最大3艇）")
    print(f"  重複率: {avg_overlap / 3 * 100:.1f}%")
    print()

    # PRE 1位の艇のBEFORE順位分布
    print(f"【PRE 1位の艇のBEFORE順位分布】")
    for rank in range(1, 7):
        count = stats['pre_1st_before_ranks'].count(rank)
        pct = count / len(stats['pre_1st_before_ranks']) * 100
        print(f"  BEFORE {rank}位: {count}回 ({pct:.1f}%)")
    print()

    # BEFORE 1位の艇のPRE順位分布
    print(f"【BEFORE 1位の艇のPRE順位分布】")
    for rank in range(1, 7):
        count = stats['before_1st_pre_ranks'].count(rank)
        pct = count / len(stats['before_1st_pre_ranks']) * 100
        print(f"  PRE {rank}位: {count}回 ({pct:.1f}%)")
    print()

    # スピアマン順位相関係数
    avg_correlation = np.mean(stats['spearman_correlations'])
    print(f"【スピアマン順位相関係数（レース平均）】")
    print(f"  平均: {avg_correlation:.3f}")
    print(f"  最小: {np.min(stats['spearman_correlations']):.3f}")
    print(f"  最大: {np.max(stats['spearman_correlations']):.3f}")
    print()
    print(f"  解釈:")
    if avg_correlation > 0.7:
        print(f"    → 非常に強い正の相関（統合してもほぼ新情報なし）")
    elif avg_correlation > 0.5:
        print(f"    → 強い正の相関（統合の効果は限定的）")
    elif avg_correlation > 0.3:
        print(f"    → 中程度の正の相関（統合に一定の意味あり）")
    else:
        print(f"    → 弱い相関（統合による新情報の可能性あり）")
    print()

    # 順位差の平均
    avg_rank_diff = np.mean(stats['rank_differences'])
    print(f"【PRE順位とBEFORE順位の平均差（絶対値）】")
    print(f"  平均: {avg_rank_diff:.2f}位")
    print(f"  解釈:")
    if avg_rank_diff < 1.0:
        print(f"    → 順位がほぼ一致（統合の意味が薄い）")
    elif avg_rank_diff < 1.5:
        print(f"    → 順位がかなり近い（統合効果は限定的）")
    else:
        print(f"    → 順位に違いあり（統合の可能性あり）")
    print()

    # 結論
    print("=" * 80)
    print("結論")
    print("=" * 80)
    print()

    if match_rate_1st > 70 and avg_correlation > 0.6:
        print("[結論] PRE_SCOREとBEFORE_SCOREは強く相関している")
        print()
        print("統合失敗の主要因:")
        print("  1. PRE 1位とBEFORE 1位の一致率が高い（{:.1f}%）".format(match_rate_1st))
        print("  2. 順位相関係数が高い（{:.3f}）".format(avg_correlation))
        print("  3. 統合しても新しい情報がほとんど加わらない")
        print("  4. BEFOREの誤差がPREの精度を下げるだけ")
        print()
        print("推奨:")
        print("  → BEFOREの統合は諦めるべき")
        print("  → または、PRE拮抗レース（1位と2位が接戦）でのみBEFOREを使用")
    elif match_rate_1st > 50 and avg_correlation > 0.4:
        print("[結論] PRE_SCOREとBEFORE_SCOREは中程度に相関している")
        print()
        print("統合失敗の原因:")
        print("  1. PRE 1位とBEFORE 1位がある程度一致（{:.1f}%）".format(match_rate_1st))
        print("  2. 順位相関係数が中程度（{:.3f}）".format(avg_correlation))
        print("  3. BEFOREの新情報は限定的")
        print()
        print("推奨:")
        print("  → 条件付き統合を検討（PRE拮抗時のみ）")
        print("  → BEFOREの使い方を工夫（フィルタリングなど）")
    else:
        print("[結論] PRE_SCOREとBEFORE_SCOREの相関は弱い")
        print()
        print("統合失敗の原因:")
        print("  → 相関は弱いが、それでも統合が失敗している")
        print("  → 他の原因を調査すべき（BEFORE配点、統合方法など）")
        print()
        print("推奨:")
        print("  → BEFOREの配点を見直す")
        print("  → 統合方法を改善する")

    print()
    print("=" * 80)

    return stats


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"

    print("=" * 80)
    print("PRE_SCOREとBEFORE_SCOREの相関分析")
    print("=" * 80)
    print()

    results = analyze_pre_before_correlation(db_path, limit=200)

    print()
    print("分析完了")
    print()


if __name__ == '__main__':
    main()
