"""
Phase 5重み調整後の効果確認
BEFORE_SAFE内の重み: ST/展示 30%ずつ（Phase 4: 20%）
BEFORE_SAFE全体: 15%（Phase 4: 10%）
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from src.analysis.before_safe_scorer import BeforeSafeScorer
import sqlite3


def main():
    db_path = "data/boatrace.db"

    # テストレースを1つ取得
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    query = """
        SELECT DISTINCT r.id
        FROM races r
        INNER JOIN race_details rd ON r.id = rd.race_id
        WHERE rd.st_time IS NOT NULL
          AND rd.exhibition_time IS NOT NULL
        ORDER BY r.race_date DESC, r.id DESC
        LIMIT 1
    """
    cursor.execute(query)
    race_id = cursor.fetchone()[0]
    conn.close()

    print("=" * 80)
    print(f"Phase 5重み調整後の効果確認 (race_id={race_id})")
    print("=" * 80)

    # Phase 4版の重み（ST/展示 20%ずつ）を再現
    print("\n【Phase 4版】ST/展示 20%ずつ（旧重み）")
    print("-" * 80)
    scorer_phase4 = BeforeSafeScorer(db_path, use_st_exhibition=True)
    # 一時的にPhase 4の重みに戻す
    scorer_phase4.ST_WEIGHT = 0.20
    scorer_phase4.EXHIBITION_WEIGHT = 0.20
    scorer_phase4.ENTRY_WEIGHT = 0.30
    scorer_phase4.PARTS_WEIGHT = 0.30

    phase4_scores = []
    for pit in range(1, 7):
        result = scorer_phase4.calculate_before_safe_score(race_id, pit)
        phase4_scores.append(result['total_score'])
        print(f"艇{pit}: total={result['total_score']:.1f}, st={result['st_score']:.1f}, exh={result['exhibition_score']:.1f}")

    # Phase 5版の重み（ST/展示 30%ずつ）
    print("\n【Phase 5版】ST/展示 30%ずつ（新重み）")
    print("-" * 80)
    scorer_phase5 = BeforeSafeScorer(db_path, use_st_exhibition=True)

    phase5_scores = []
    for pit in range(1, 7):
        result = scorer_phase5.calculate_before_safe_score(race_id, pit)
        phase5_scores.append(result['total_score'])
        print(f"艇{pit}: total={result['total_score']:.1f}, st={result['st_score']:.1f}, exh={result['exhibition_score']:.1f}")

    # スコア変化の分析
    print("\n【スコア変化】")
    print("-" * 80)
    max_change = 0
    for pit in range(1, 7):
        change = phase5_scores[pit-1] - phase4_scores[pit-1]
        max_change = max(max_change, abs(change))
        print(f"艇{pit}: {phase4_scores[pit-1]:.1f} → {phase5_scores[pit-1]:.1f} (変化: {change:+.1f})")

    # 順位変化
    phase4_ranking = sorted(range(1, 7), key=lambda x: phase4_scores[x-1], reverse=True)
    phase5_ranking = sorted(range(1, 7), key=lambda x: phase5_scores[x-1], reverse=True)

    print("\n【順位変化】")
    print("-" * 80)
    print(f"Phase 4版: {phase4_ranking}")
    print(f"Phase 5版: {phase5_ranking}")

    if phase4_ranking != phase5_ranking:
        print("→ 順位が変化しました！")
    else:
        print("→ 順位変化なし")

    print("\n" + "=" * 80)
    print(f"最大スコア変化: {max_change:.1f}点")
    print("=" * 80)


if __name__ == '__main__':
    main()
