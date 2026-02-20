"""
直線タイムスコアリングのテストスクリプト
3-3: chikusen_timeの補完と活用の動作確認
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.analysis.extended_scorer import ExtendedScorer
import sqlite3

def test_chikusen_time_scoring():
    """直線タイムスコアリングのテスト"""

    db_path = Path(__file__).parent.parent.parent / "data" / "boatrace.db"
    scorer = ExtendedScorer(str(db_path))

    print("=" * 80)
    print("直線タイムスコアリング テスト")
    print("=" * 80)
    print()

    # 直線タイムデータがあるレースを抽出
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            r.id as race_id,
            r.race_date,
            r.venue_code,
            r.race_number,
            ed.pit_number,
            ed.chikusen_time
        FROM exhibition_data ed
        JOIN races r ON ed.race_id = r.id
        WHERE ed.chikusen_time IS NOT NULL
        ORDER BY r.race_date DESC
        LIMIT 30
    """)

    test_cases = cursor.fetchall()

    if not test_cases:
        print("テストデータが見つかりません")
        conn.close()
        return

    print(f"【テストケース: 直線タイムデータがあるレース（最新30件）】")
    print()

    # レースごとにグループ化してテスト
    race_groups = {}
    for case in test_cases:
        race_id = case['race_id']
        if race_id not in race_groups:
            race_groups[race_id] = {
                'race_date': case['race_date'],
                'venue_code': case['venue_code'],
                'race_number': case['race_number'],
                'pits': []
            }
        race_groups[race_id]['pits'].append({
            'pit_number': case['pit_number'],
            'chikusen_time': case['chikusen_time']
        })

    # 最初の3レースをテスト
    for i, (race_id, race_info) in enumerate(list(race_groups.items())[:3], 1):
        print(f"--- テストレース {i} ---")
        print(f"レースID: {race_id}")
        print(f"日付: {race_info['race_date']}")
        print(f"会場: {race_info['venue_code']}")
        print(f"レース: {race_info['race_number']}R")
        print()

        # 全艇の直線タイムを表示
        pits_sorted = sorted(race_info['pits'], key=lambda x: x['chikusen_time'])
        print("直線タイムランキング:")
        for rank, pit_info in enumerate(pits_sorted, 1):
            print(f"  {rank}位: {pit_info['pit_number']}号艇 {pit_info['chikusen_time']:.2f}秒")
        print()

        # 各艇のスコアリング実行
        print("スコアリング結果:")
        for pit_info in race_info['pits']:
            result = scorer.calculate_chikusen_time_score(
                race_id=race_id,
                pit_number=pit_info['pit_number'],
                max_score=4.0
            )

            print(f"  {pit_info['pit_number']}号艇: "
                  f"スコア={result['score']:.2f}点 "
                  f"({result['level']}) - {result['description']}")
        print()
        print("-" * 80)
        print()

    conn.close()

    # 統計: データカバレッジ確認
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(DISTINCT race_id) as races_with_time
        FROM exhibition_data
        WHERE chikusen_time IS NOT NULL
    """)
    races_with_time = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) as total_races FROM races WHERE race_date >= '2025-01-01'")
    total_races_2025 = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(DISTINCT ed.race_id) as races_with_time_2025
        FROM exhibition_data ed
        JOIN races r ON ed.race_id = r.id
        WHERE ed.chikusen_time IS NOT NULL
          AND r.race_date >= '2025-01-01'
    """)
    races_with_time_2025 = cursor.fetchone()[0]

    conn.close()

    print("=" * 80)
    print("【データカバレッジ統計】")
    print(f"  直線タイムありレース数（全期間）: {races_with_time:,}レース")
    print(f"  直線タイムありレース数（2025年）: {races_with_time_2025:,}レース / {total_races_2025:,}レース ({races_with_time_2025/total_races_2025*100:.1f}%)")
    print()
    print("【注意】")
    print("  - 直線タイムデータは限定的（オリジナル展示データ収集開始後のみ）")
    print("  - 今後の自動収集により徐々にカバレッジが向上します")
    print("=" * 80)

if __name__ == "__main__":
    test_chikusen_time_scoring()
