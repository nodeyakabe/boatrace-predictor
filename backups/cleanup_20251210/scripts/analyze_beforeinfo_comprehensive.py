# -*- coding: utf-8 -*-
"""直前情報の本質的な使い方を調査

全順位にわたる直前情報の影響を分析し、
最適な活用方法を見つける
"""

import sys
import sqlite3
from pathlib import Path
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.analysis.beforeinfo_scorer import BeforeInfoScorer


def analyze_comprehensive_beforeinfo(db_path, limit=200):
    """直前情報の包括的分析

    Args:
        db_path: データベースパス
        limit: 分析するレース数

    Returns:
        dict: 分析結果
    """
    scorer = BeforeInfoScorer(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 2025年で直前情報が存在するレースを取得
    cursor.execute('''
        SELECT DISTINCT r.id, r.race_date, r.race_number
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        AND rd.exhibition_time IS NOT NULL
        ORDER BY r.race_date, r.race_number
        LIMIT ?
    ''', (limit,))
    races = cursor.fetchall()

    print(f"分析対象レース数: {len(races)}")
    print()

    # 各順位でのBEFOREスコアと実際の着順の関係を分析
    score_by_rank = defaultdict(list)  # 実際の着順別のBEFOREスコア
    predicted_by_before = defaultdict(list)  # BEFORE順位別の実際の着順

    # PRE_SCOREとBEFORE_SCOREの相関分析
    pre_before_correlation = []

    # BEFORE順位と実際の着順の一致率
    rank_match_counts = defaultdict(int)  # BEFORE順位での的中数
    rank_total_counts = defaultdict(int)   # BEFORE順位での総数

    races_analyzed = 0

    for race_row in races:
        race_id = race_row['id']

        # このレースの全艇の結果を取得
        cursor.execute('''
            SELECT pit_number, rank
            FROM results
            WHERE race_id = ? AND is_invalid = 0
            ORDER BY rank
        ''', (race_id,))
        results = cursor.fetchall()

        if len(results) != 6:
            continue

        # 各艇のBEFOREスコアを計算
        before_scores = {}
        for result in results:
            pit = result['pit_number']
            before_result = scorer.calculate_beforeinfo_score(race_id, pit)
            before_scores[pit] = before_result['total_score']

        # BEFORE順位を算出（スコア降順）
        before_ranking = sorted(before_scores.items(), key=lambda x: x[1], reverse=True)
        before_rank_map = {pit: rank+1 for rank, (pit, score) in enumerate(before_ranking)}

        # 実際の着順とBEFORE順位を記録
        for result in results:
            pit = result['pit_number']
            actual_rank = int(result['rank'])
            before_rank = before_rank_map[pit]
            before_score = before_scores[pit]

            # 実際の着順別のBEFOREスコア
            score_by_rank[actual_rank].append(before_score)

            # BEFORE順位別の実際の着順
            predicted_by_before[before_rank].append(actual_rank)

            # BEFORE順位での的中カウント
            rank_total_counts[before_rank] += 1
            if before_rank == actual_rank:
                rank_match_counts[before_rank] += 1

        races_analyzed += 1

    conn.close()

    print("=" * 80)
    print("分析1: 実際の着順別のBEFOREスコア平均")
    print("=" * 80)
    print()

    for rank in range(1, 7):
        scores = score_by_rank[rank]
        if scores:
            avg = sum(scores) / len(scores)
            print(f"{rank}着: {avg:6.2f}点 (サンプル数: {len(scores)})")

    print()

    # 着順間の差分を計算
    print("着順間のスコア差分:")
    for rank in range(1, 6):
        scores_current = score_by_rank[rank]
        scores_next = score_by_rank[rank + 1]
        if scores_current and scores_next:
            avg_current = sum(scores_current) / len(scores_current)
            avg_next = sum(scores_next) / len(scores_next)
            diff = avg_current - avg_next
            print(f"{rank}着 vs {rank+1}着: {diff:+6.2f}点")

    print()

    # 上位グループと下位グループの比較
    top3_scores = []
    bottom3_scores = []
    for rank in range(1, 4):
        top3_scores.extend(score_by_rank[rank])
    for rank in range(4, 7):
        bottom3_scores.extend(score_by_rank[rank])

    if top3_scores and bottom3_scores:
        avg_top3 = sum(top3_scores) / len(top3_scores)
        avg_bottom3 = sum(bottom3_scores) / len(bottom3_scores)
        print(f"1-3着平均: {avg_top3:6.2f}点")
        print(f"4-6着平均: {avg_bottom3:6.2f}点")
        print(f"差分: {avg_top3 - avg_bottom3:+6.2f}点")

    print()
    print("=" * 80)
    print("分析2: BEFORE順位別の実際の着順分布")
    print("=" * 80)
    print()

    for before_rank in range(1, 7):
        actual_ranks = predicted_by_before[before_rank]
        if actual_ranks:
            avg_actual = sum(actual_ranks) / len(actual_ranks)
            # 各着順の割合を計算
            rank_dist = defaultdict(int)
            for r in actual_ranks:
                rank_dist[r] += 1

            print(f"BEFORE {before_rank}位予測 → 実際の平均着順: {avg_actual:.2f}位 (n={len(actual_ranks)})")

            # 1-3着に入る確率
            top3_count = sum(1 for r in actual_ranks if r <= 3)
            top3_rate = top3_count / len(actual_ranks) * 100

            # 1着になる確率
            first_count = sum(1 for r in actual_ranks if r == 1)
            first_rate = first_count / len(actual_ranks) * 100

            print(f"  → 1着率: {first_rate:5.1f}% ({first_count}/{len(actual_ranks)})")
            print(f"  → 3着以内率: {top3_rate:5.1f}% ({top3_count}/{len(actual_ranks)})")
            print()

    print("=" * 80)
    print("分析3: BEFORE順位と実際の着順の一致率")
    print("=" * 80)
    print()

    for before_rank in range(1, 7):
        total = rank_total_counts[before_rank]
        match = rank_match_counts[before_rank]
        if total > 0:
            match_rate = match / total * 100
            print(f"BEFORE {before_rank}位予測 → 実際に{before_rank}着: {match_rate:5.1f}% ({match}/{total})")

    print()

    # 総合一致率
    total_all = sum(rank_total_counts.values())
    match_all = sum(rank_match_counts.values())
    if total_all > 0:
        overall_rate = match_all / total_all * 100
        print(f"総合一致率: {overall_rate:5.1f}% ({match_all}/{total_all})")

    print()
    print("=" * 80)
    print("結論と推奨事項")
    print("=" * 80)
    print()

    # 1着予測の精度
    first_actual_ranks = predicted_by_before[1]
    if first_actual_ranks:
        first_hit_count = sum(1 for r in first_actual_ranks if r == 1)
        first_hit_rate = first_hit_count / len(first_actual_ranks) * 100

        print(f"BEFORE1位予測の1着的中率: {first_hit_rate:.1f}%")

        if first_hit_rate < 20:
            print("  → [NG] BEFOREスコア単独では1着予測に不十分")
            print("  → PRE_SCOREとの統合が必須")
        elif first_hit_rate < 30:
            print("  → [OK] BEFOREスコアは補助的に使用すべき")
            print("  → PRE_SCOREを主軸に、BEFOREで微調整")
        else:
            print("  → [Good] BEFOREスコアは有効な予測要素")
            print("  → PRE_SCOREと同等の重みで統合可能")

    print()

    # 3着以内予測の精度
    first_top3_rate = top3_count / len(first_actual_ranks) * 100 if first_actual_ranks else 0
    print(f"BEFORE1位予測の3着以内率: {first_top3_rate:.1f}%")

    if first_top3_rate > 60:
        print("  → [Good] 上位艇の識別には有効")
        print("  → フィルター方式での活用が適切")

    print()

    # BEFOREスコアの強みと弱みを明確化
    print("BEFOREスコアの特性:")
    print()

    # 1着と2着の差分
    scores_1st = score_by_rank[1]
    scores_2nd = score_by_rank[2]
    if scores_1st and scores_2nd:
        avg_1st = sum(scores_1st) / len(scores_1st)
        avg_2nd = sum(scores_2nd) / len(scores_2nd)
        diff_1st_2nd = avg_1st - avg_2nd

        print(f"1着と2着の差: {diff_1st_2nd:+.2f}点")

        if diff_1st_2nd < 3:
            print("  → [弱み] 上位艇間の順位付けが困難")
            print("  → 「誰が勝つか」の予測には不向き")

    # 上位と下位の差分（再掲）
    if top3_scores and bottom3_scores:
        diff_top_bottom = avg_top3 - avg_bottom3
        print()
        print(f"1-3着と4-6着の差: {diff_top_bottom:+.2f}点")

        if diff_top_bottom > 5:
            print("  → [強み] 上位グループと下位グループの識別が可能")
            print("  → 「誰が圏外か」の予測に有効")

    print()
    print("=" * 80)
    print("推奨する活用方法:")
    print("=" * 80)
    print()

    # 分析結果に基づいた推奨方法を提示
    print("1. 階層的予測方式（推奨）")
    print("   - Step1: BEFOREで「上位候補グループ」を抽出（BEFORE上位3艇）")
    print("   - Step2: その中でPRE_SCOREで順位付け")
    print("   - 根拠: BEFOREは上位グループ識別に強い")
    print()

    print("2. 信頼度調整方式")
    print("   - PRE_SCOREでの予測順位は維持")
    print("   - BEFOREスコアが高い → 信頼度UP、購入額増")
    print("   - BEFOREスコアが低い → 信頼度DOWN、購入見送り")
    print("   - 根拠: BEFOREは「確実性」の指標として有効")
    print()

    print("3. 除外フィルター拡張方式")
    print("   - BEFORE下位2艇を除外（現在は6位のみ）")
    print("   - 残り4艇の中でPRE_SCOREで順位付け")
    print("   - 根拠: BEFOREの下位識別能力を最大活用")
    print()

    print("=" * 80)

    return {
        'score_by_rank': score_by_rank,
        'predicted_by_before': predicted_by_before,
        'rank_match_counts': rank_match_counts,
        'rank_total_counts': rank_total_counts,
        'races_analyzed': races_analyzed
    }


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"

    print("=" * 80)
    print("直前情報の本質的な使い方の調査")
    print("=" * 80)
    print()

    results = analyze_comprehensive_beforeinfo(db_path, limit=200)

    print()
    print("分析完了")
    print(f"分析レース数: {results['races_analyzed']}")
    print()


if __name__ == '__main__':
    main()
