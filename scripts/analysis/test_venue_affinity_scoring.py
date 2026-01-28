"""
会場相性スコアリングのテストスクリプト
3-2: local_win_rateで会場相性スコア計算の動作確認
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.analysis.extended_scorer import ExtendedScorer
import sqlite3

def test_venue_affinity_scoring():
    """会場相性スコアリングのテスト"""

    db_path = Path(__file__).parent.parent.parent / "data" / "boatrace.db"
    scorer = ExtendedScorer(str(db_path))

    print("=" * 80)
    print("会場相性スコアリング テスト")
    print("=" * 80)
    print()

    # テストケース: 会場相性差が極端な選手を抽出してテスト
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            e.racer_number,
            e.racer_name,
            r.venue_code,
            e.local_win_rate,
            e.win_rate,
            (e.local_win_rate - e.win_rate) as affinity_diff,
            r.race_date,
            r.id as race_id
        FROM entries e
        JOIN races r ON e.race_id = r.id
        WHERE e.local_win_rate IS NOT NULL
          AND e.win_rate IS NOT NULL
          AND r.race_date >= '2025-01-01'
        ORDER BY ABS(e.local_win_rate - e.win_rate) DESC
        LIMIT 10
    """)

    test_cases = cursor.fetchall()

    print("【テストケース: 会場相性が極端な選手（2025年）】")
    print()

    for i, case in enumerate(test_cases, 1):
        print(f"--- テストケース {i} ---")
        print(f"選手: {case['racer_name']} ({case['racer_number']})")
        print(f"会場: {case['venue_code']}")
        print(f"日付: {case['race_date']}")
        print(f"当地勝率: {case['local_win_rate']:.1f}%")
        print(f"全国勝率: {case['win_rate']:.1f}%")
        print(f"相性差: {case['affinity_diff']:+.1f}pt")
        print()

        # スコアリング実行
        result = scorer.calculate_venue_affinity_score(
            racer_number=case['racer_number'],
            venue_code=case['venue_code'],
            race_date=case['race_date'],
            max_score=6.0,
            local_win_rate=case['local_win_rate'],
            national_win_rate=case['win_rate']
        )

        print(f"【スコアリング結果】")
        print(f"  スコア: {result['score']:.2f}点")
        print(f"  相性レベル: {result['affinity_level']}")
        print(f"  説明: {result['description']}")
        print()

    conn.close()

    print("=" * 80)

    # 統計: 各相性レベルの分布確認
    print()
    print("【相性レベル別スコア確認】")
    print()

    test_data = [
        ("得意会場", 8.0, 3.0, 5.0),  # +5pt
        ("やや得意", 7.0, 4.5, 2.5),  # +2.5pt
        ("標準", 6.0, 6.0, 0.0),       # 0pt
        ("やや苦手", 5.0, 8.0, -3.0),  # -3pt
        ("苦手会場", 3.0, 10.0, -7.0)  # -7pt
    ]

    for label, local, national, expected_diff in test_data:
        result = scorer.calculate_venue_affinity_score(
            racer_number="0000",  # ダミー
            venue_code="01",
            race_date="2025-01-01",
            max_score=6.0,
            local_win_rate=local,
            national_win_rate=national
        )
        print(f"{label:12} | 当地:{local:>4.1f}% 全国:{national:>4.1f}% 差:{expected_diff:>+5.1f}pt "
              f"→ スコア:{result['score']:>5.2f}点 ({result['affinity_level']})")

    print()
    print("=" * 80)
    print("テスト完了")
    print("=" * 80)

if __name__ == "__main__":
    test_venue_affinity_scoring()
