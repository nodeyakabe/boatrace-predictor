"""
BEFORE_SAFEスコアラーのデバッグテスト
Phase 4統合が正しく動作しているかを確認
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from src.analysis.before_safe_scorer import BeforeSafeScorer
from config import feature_flags
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
    print(f"BEFORE_SAFEスコアラー デバッグテスト (race_id={race_id})")
    print("=" * 80)

    # Phase 3版（ST/展示なし）
    print("\n【Phase 3版】ST/展示なし")
    print("-" * 80)
    scorer_phase3 = BeforeSafeScorer(db_path, use_st_exhibition=False)
    for pit in range(1, 7):
        result = scorer_phase3.calculate_before_safe_score(race_id, pit)
        print(f"艇{pit}: total={result['total_score']:.1f}, entry={result['entry_score']:.1f}, parts={result['parts_score']:.1f}, weight={result['weight_score']:.1f}")

    # Phase 4版（ST/展示あり）
    print("\n【Phase 4版】ST/展示あり")
    print("-" * 80)
    scorer_phase4 = BeforeSafeScorer(db_path, use_st_exhibition=True)
    for pit in range(1, 7):
        result = scorer_phase4.calculate_before_safe_score(race_id, pit)
        print(f"艇{pit}: total={result['total_score']:.1f}, entry={result['entry_score']:.1f}, parts={result['parts_score']:.1f}, weight={result['weight_score']:.1f}, st={result['st_score']:.1f}, exh={result['exhibition_score']:.1f}")

    print("\n" + "=" * 80)
    print("Phase 3版とPhase 4版のtotal_scoreが異なっていれば、統合が正しく動作しています")
    print("=" * 80)


if __name__ == '__main__':
    main()
