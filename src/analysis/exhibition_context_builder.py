"""
展示タイムコンテキスト構築モジュール

CompoundBuffSystemで使用する展示タイム関連の race_context を構築
"""

import sqlite3
from typing import Dict, List, Optional


def calculate_exhibition_rank(race_id: int, pit_number: int, db_path: str = "data/boatrace.db") -> Optional[int]:
    """
    指定艇の展示タイム順位を計算

    Args:
        race_id: レースID
        pit_number: 艇番（1-6）
        db_path: データベースパス

    Returns:
        int: 展示順位（1-6）、データがない場合はNone
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            pit_number,
            exhibition_time
        FROM race_details
        WHERE race_id = ?
        AND exhibition_time IS NOT NULL
        ORDER BY exhibition_time ASC
    """, (race_id,))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return None

    # 順位を計算
    for rank, (pit, time) in enumerate(rows, start=1):
        if pit == pit_number:
            return rank

    return None


def calculate_exhibition_gap(race_id: int, pit_number: int, db_path: str = "data/boatrace.db") -> Optional[float]:
    """
    1位との展示タイム差を計算

    Args:
        race_id: レースID
        pit_number: 艇番（1-6）
        db_path: データベースパス

    Returns:
        float: 1位との差（秒）、データがない場合はNone
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            pit_number,
            exhibition_time
        FROM race_details
        WHERE race_id = ?
        AND exhibition_time IS NOT NULL
        ORDER BY exhibition_time ASC
    """, (race_id,))

    rows = cursor.fetchall()
    conn.close()

    if not rows or len(rows) < 2:
        return None

    first_time = rows[0][1]

    for pit, time in rows:
        if pit == pit_number:
            return time - first_time

    return None


def calculate_exhibition_time_diff(race_id: int, db_path: str = "data/boatrace.db") -> Optional[float]:
    """
    展示1位と2位のタイム差を計算

    Args:
        race_id: レースID
        db_path: データベースパス

    Returns:
        float: 1位と2位の差（秒）、データがない場合はNone
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT exhibition_time
        FROM race_details
        WHERE race_id = ?
        AND exhibition_time IS NOT NULL
        ORDER BY exhibition_time ASC
        LIMIT 2
    """, (race_id,))

    rows = cursor.fetchall()
    conn.close()

    if len(rows) < 2:
        return None

    return rows[1][0] - rows[0][0]


def build_exhibition_context(race_id: int, pit_number: int, db_path: str = "data/boatrace.db") -> Dict:
    """
    展示タイム関連のコンテキストを構築

    Args:
        race_id: レースID
        pit_number: 艇番（1-6）
        db_path: データベースパス

    Returns:
        dict: {
            'exhibition_rank': int,      # 展示順位
            'exhibition_gap': float,     # 1位との差（秒）
            'exh_time_diff': float       # 1位と2位の差（秒）
        }
    """
    context = {}

    # 展示順位
    rank = calculate_exhibition_rank(race_id, pit_number, db_path)
    if rank is not None:
        context['exhibition_rank'] = rank

    # 1位との差
    gap = calculate_exhibition_gap(race_id, pit_number, db_path)
    if gap is not None:
        context['exhibition_gap'] = gap

    # 1位と2位の差（全艇共通）
    time_diff = calculate_exhibition_time_diff(race_id, db_path)
    if time_diff is not None:
        context['exh_time_diff'] = time_diff

    return context


# ========================================
# テスト用
# ========================================
if __name__ == '__main__':
    import sys
    import os
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.chdir(project_root)

    # サンプルレースでテスト
    conn = sqlite3.connect("data/boatrace.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT r.id
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        WHERE r.race_date >= '2025-01-01'
        AND rd.exhibition_time IS NOT NULL
        GROUP BY r.id
        HAVING COUNT(DISTINCT rd.pit_number) = 6
        LIMIT 1
    """)

    race_id = cursor.fetchone()[0]
    conn.close()

    print("=" * 60)
    print(f"展示コンテキスト構築テスト（レースID: {race_id}）")
    print("=" * 60)
    print()

    for pit in range(1, 7):
        context = build_exhibition_context(race_id, pit)
        print(f"艇番{pit}: {context}")

    print()
    print("=" * 60)
