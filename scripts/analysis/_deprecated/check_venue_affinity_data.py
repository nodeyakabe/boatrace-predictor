"""
会場相性データ（local_win_rate）の確認スクリプト
3-2: local_win_rateで会場相性スコア計算の準備
"""

import sqlite3
from pathlib import Path

def check_venue_affinity_data():
    """entriesテーブルのlocal_win_rate / win_rateデータを確認"""

    db_path = Path(__file__).parent.parent.parent / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=" * 80)
    print("会場相性データ（entries.local_win_rate / win_rate）の確認")
    print("=" * 80)
    print()

    # 1. データカバレッジ
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN local_win_rate IS NOT NULL THEN 1 END) as with_local,
            COUNT(CASE WHEN win_rate IS NOT NULL THEN 1 END) as with_national,
            COUNT(CASE WHEN local_win_rate IS NOT NULL AND win_rate IS NOT NULL THEN 1 END) as with_both
        FROM entries
    """)
    coverage = cursor.fetchone()
    print("【データカバレッジ（entriesテーブル）】")
    print(f"  総レコード数: {coverage['total']:,}")
    print(f"  local_win_rate有り: {coverage['with_local']:,} ({coverage['with_local']/coverage['total']*100:.1f}%)")
    print(f"  win_rate有り: {coverage['with_national']:,} ({coverage['with_national']/coverage['total']*100:.1f}%)")
    print(f"  両方あり: {coverage['with_both']:,} ({coverage['with_both']/coverage['total']*100:.1f}%)")
    print()

    # 2. 会場相性差の統計
    cursor.execute("""
        SELECT
            AVG(ABS(local_win_rate - win_rate)) as avg_diff,
            MAX(local_win_rate - win_rate) as max_positive,
            MIN(local_win_rate - win_rate) as max_negative,
            AVG(local_win_rate - win_rate) as avg_affinity
        FROM entries
        WHERE local_win_rate IS NOT NULL AND win_rate IS NOT NULL
    """)
    stats = cursor.fetchone()
    print("【会場相性差の統計】")
    print(f"  平均絶対差: {stats['avg_diff']:.2f}pt")
    print(f"  最大プラス差: {stats['max_positive']:.2f}pt")
    print(f"  最大マイナス差: {stats['max_negative']:.2f}pt")
    print(f"  平均相性差: {stats['avg_affinity']:.2f}pt")
    print()

    # 3. 会場相性が極端な選手のサンプル
    cursor.execute("""
        SELECT
            e.racer_number,
            e.racer_name,
            r.venue_code,
            e.local_win_rate,
            e.win_rate,
            (e.local_win_rate - e.win_rate) as affinity_diff,
            r.race_date
        FROM entries e
        JOIN races r ON e.race_id = r.id
        WHERE e.local_win_rate IS NOT NULL AND e.win_rate IS NOT NULL
        ORDER BY ABS(e.local_win_rate - e.win_rate) DESC
        LIMIT 15
    """)
    samples = cursor.fetchall()
    print("【会場相性が極端な選手（トップ15）】")
    print(f"{'選手番号':<8} {'選手名':<12} {'会場':<4} {'当地勝率':<8} {'全国勝率':<8} {'相性差':<8} {'日付':<12}")
    print("-" * 90)
    for row in samples:
        diff = row['affinity_diff']
        sign = '+' if diff >= 0 else ''
        print(f"{row['racer_number']:<8} {row['racer_name']:<12} {row['venue_code']:<4} "
              f"{row['local_win_rate']:>7.2f}% {row['win_rate']:>7.2f}% {sign}{diff:>6.2f}pt {row['race_date']:<12}")
    print()

    # 4. 分布の確認（相性差の範囲別件数）
    cursor.execute("""
        SELECT
            CASE
                WHEN (local_win_rate - win_rate) >= 5.0 THEN '5pt以上（得意）'
                WHEN (local_win_rate - win_rate) >= 2.0 THEN '2-5pt（やや得意）'
                WHEN (local_win_rate - win_rate) >= -2.0 THEN '-2～2pt（標準）'
                WHEN (local_win_rate - win_rate) >= -5.0 THEN '-5～-2pt（やや苦手）'
                ELSE '-5pt以下（苦手）'
            END as affinity_level,
            COUNT(*) as count
        FROM entries
        WHERE local_win_rate IS NOT NULL AND win_rate IS NOT NULL
        GROUP BY affinity_level
        ORDER BY
            CASE
                WHEN (local_win_rate - win_rate) >= 5.0 THEN 1
                WHEN (local_win_rate - win_rate) >= 2.0 THEN 2
                WHEN (local_win_rate - win_rate) >= -2.0 THEN 3
                WHEN (local_win_rate - win_rate) >= -5.0 THEN 4
                ELSE 5
            END
    """)
    distribution = cursor.fetchall()
    print("【会場相性差の分布】")
    print(f"{'相性レベル':<20} {'件数':<10} {'割合':<10}")
    print("-" * 80)
    total_count = sum(row['count'] for row in distribution)
    for row in distribution:
        percentage = row['count'] / total_count * 100
        print(f"{row['affinity_level']:<20} {row['count']:>8,} {percentage:>8.1f}%")
    print()

    # 5. 2025年データの確認
    cursor.execute("""
        SELECT
            COUNT(*) as total_2025,
            COUNT(CASE WHEN local_win_rate IS NOT NULL AND win_rate IS NOT NULL THEN 1 END) as with_affinity
        FROM entries e
        JOIN races r ON e.race_id = r.id
        WHERE r.race_date >= '2025-01-01'
    """)
    recent = cursor.fetchone()
    print("【2025年データの状況】")
    print(f"  2025年総エントリー数: {recent['total_2025']:,}")
    print(f"  会場相性計算可能: {recent['with_affinity']:,} ({recent['with_affinity']/recent['total_2025']*100:.1f}%)")
    print()

    conn.close()

    print("=" * 80)
    print("確認完了 - entriesテーブルのlocal_win_rate/win_rateで会場相性スコア計算可能")
    print("=" * 80)

if __name__ == "__main__":
    check_venue_affinity_data()
