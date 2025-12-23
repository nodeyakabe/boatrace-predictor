# -*- coding: utf-8 -*-
"""BEFORE_SCORE逆相関問題の原因調査（軽量版）

直前情報スコアが予測精度に与える影響を分析
サンプル数を絞り込んで高速実行
"""

import sys
import sqlite3
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.analysis.beforeinfo_scorer import BeforeInfoScorer


def analyze_beforeinfo_scores(db_path, limit=100):
    """
    直前情報スコアと実際の結果の相関を分析

    Args:
        db_path: データベースパス
        limit: 分析するレース数上限
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    scorer = BeforeInfoScorer(db_path)

    print("=" * 80)
    print("BEFORE_SCORE逆相関問題の原因調査（軽量版）")
    print("=" * 80)
    print()

    # 直前情報が存在する2025年レースを取得
    cursor.execute(f'''
        SELECT DISTINCT r.id as race_id
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        AND rd.exhibition_time IS NOT NULL
        ORDER BY r.race_date, r.race_number
        LIMIT {limit}
    ''')
    race_ids = [row['race_id'] for row in cursor.fetchall()]

    print(f"分析対象レース: {len(race_ids)}")
    print()

    # 各艇のBEFOREスコアと実際の着順を収集
    score_by_rank = {1: [], 2: [], 3: [], 4: [], 5: [], 6: []}
    exhibition_by_rank = {1: [], 2: [], 3: [], 4: [], 5: [], 6: []}
    st_by_rank = {1: [], 2: [], 3: [], 4: [], 5: [], 6: []}

    total_boats = 0
    valid_boats = 0

    for race_id in race_ids:
        # 実際の結果取得
        cursor.execute('''
            SELECT pit_number, rank
            FROM results
            WHERE race_id = ? AND is_invalid = 0
            ORDER BY rank
        ''', (race_id,))
        results = cursor.fetchall()

        if len(results) < 6:
            continue

        # 各艇のスコア計算
        for result in results:
            pit = result['pit_number']
            rank = int(result['rank'])

            if rank > 6:
                continue

            total_boats += 1

            try:
                before_result = scorer.calculate_beforeinfo_score(race_id, pit)

                if before_result['data_completeness'] > 0:
                    valid_boats += 1
                    score_by_rank[rank].append(before_result['total_score'])
                    exhibition_by_rank[rank].append(before_result['exhibition_time_score'])
                    st_by_rank[rank].append(before_result['st_score'])
            except Exception as e:
                continue

    conn.close()

    print(f"総艇数: {total_boats}")
    print(f"有効データ艇数: {valid_boats} ({valid_boats/total_boats*100:.1f}%)")
    print()

    # 着順別の平均スコア
    print("=" * 80)
    print("着順別の平均スコア")
    print("=" * 80)
    print()

    print("着順 | サンプル | 総合スコア | 展示タイム | ST")
    print("-" * 60)

    for rank in range(1, 7):
        if score_by_rank[rank]:
            avg_total = sum(score_by_rank[rank]) / len(score_by_rank[rank])
            avg_exh = sum(exhibition_by_rank[rank]) / len(exhibition_by_rank[rank])
            avg_st = sum(st_by_rank[rank]) / len(st_by_rank[rank])

            print(f"{rank}着 | {len(score_by_rank[rank]):4d}件 | {avg_total:7.2f}点 | {avg_exh:7.2f}点 | {avg_st:7.2f}点")

    print()

    # 相関分析
    print("=" * 80)
    print("相関分析")
    print("=" * 80)
    print()

    if score_by_rank[1] and score_by_rank[6]:
        avg_1st = sum(score_by_rank[1]) / len(score_by_rank[1])
        avg_6th = sum(score_by_rank[6]) / len(score_by_rank[6])

        diff_total = avg_1st - avg_6th

        avg_1st_exh = sum(exhibition_by_rank[1]) / len(exhibition_by_rank[1])
        avg_6th_exh = sum(exhibition_by_rank[6]) / len(exhibition_by_rank[6])
        diff_exh = avg_1st_exh - avg_6th_exh

        avg_1st_st = sum(st_by_rank[1]) / len(st_by_rank[1])
        avg_6th_st = sum(st_by_rank[6]) / len(st_by_rank[6])
        diff_st = avg_1st_st - avg_6th_st

        print("1着 vs 6着の平均スコア差:")
        print(f"  総合スコア: {diff_total:+.2f}点 (1着:{avg_1st:.2f}, 6着:{avg_6th:.2f})")
        print(f"  展示タイム: {diff_exh:+.2f}点 (1着:{avg_1st_exh:.2f}, 6着:{avg_6th_exh:.2f})")
        print(f"  ST: {diff_st:+.2f}点 (1着:{avg_1st_st:.2f}, 6着:{avg_6th_st:.2f})")
        print()

        print("判定:")
        if diff_total > 5:
            print("  [OK] 正相関: BEFOREスコアが高い艇ほど上位に入る")
        elif diff_total < -5:
            print("  [NG] 逆相関: BEFOREスコアが高い艇ほど下位に沈む")
            print("  → スコアリングロジックに根本的な問題あり")
        else:
            print("  [WARN] 弱相関: BEFOREスコアと着順に明確な関係なし")
            print("  → 直前情報は予測精度向上にほとんど寄与しない")

        print()

        # 個別項目の診断
        print("個別項目の診断:")

        if abs(diff_exh) < 2:
            print("  展示タイム: 相関弱い（スコアリング無効）")
        elif diff_exh > 0:
            print("  展示タイム: 正相関 → 使用可能")
        else:
            print("  展示タイム: 逆相関 → ロジック修正必要")

        if abs(diff_st) < 2:
            print("  ST: 相関弱い（スコアリング無効）")
        elif diff_st > 0:
            print("  ST: 正相関 → 使用可能")
        else:
            print("  ST: 逆相関 → ロジック修正必要")

    print()

    # 推奨アクション
    print("=" * 80)
    print("推奨アクション")
    print("=" * 80)
    print()

    if score_by_rank[1] and score_by_rank[6]:
        if diff_total > 5:
            print("[アクション1] BEFOREスコアは有効 → 動的統合を有効化推奨")
            print("  - feature_flags: dynamic_integration = True")
            print("  - 統合式: FINAL = PRE * 0.6 + BEFORE * 0.4")
        elif diff_total < -5:
            print("[アクション1] BEFOREスコアが逆相関 → ロジック修正必要")
            print("  - 展示タイムのスコアリングを逆転（1位=0点、6位=25点）")
            print("  - STのスコアリングを逆転（良ST=減点、悪ST=加点）")
            print("  - または、スコアの正負を反転して統合")
        else:
            print("[アクション1] BEFOREスコアは弱相関 → フィルター活用推奨")
            print("  - スコアでの順位付けは無効")
            print("  - 展示タイム下位・ST不良の艇を除外フィルターとして使用")
            print("  - 例: 展示タイム6位 or ST > 0.20 → 購入対象から除外")

    print()
    print("=" * 80)


if __name__ == '__main__':
    db_path = ROOT_DIR / "data" / "boatrace.db"
    analyze_beforeinfo_scores(db_path, limit=100)
