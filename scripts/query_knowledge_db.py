#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
知見DB高度検索ツール
====================

SQLiteベースの高度な検索機能。

使用例:
    # カテゴリ別検索
    python scripts/query_knowledge_db.py --category odds_integration

    # 期間別検索
    python scripts/query_knowledge_db.py --from 2025-12-01 --to 2025-12-31

    # 不採用施策のみ
    python scripts/query_knowledge_db.py --result rejected

    # 統計情報
    python scripts/query_knowledge_db.py --stats
"""

import argparse
import sqlite3
import sys
import io
from pathlib import Path
from collections import defaultdict

# Windows環境でのUnicode出力対応
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

DB_PATH = Path(__file__).parent.parent / "knowledge.db"


def query_experiments(conn, args):
    """施策を検索"""
    cursor = conn.cursor()

    query = "SELECT * FROM experiments WHERE 1=1"
    params = []

    if args.category:
        query += " AND category = ?"
        params.append(args.category)

    if args.result:
        query += " AND result = ?"
        params.append(args.result)

    if args.from_date:
        query += " AND date_tested >= ?"
        params.append(args.from_date)

    if args.to_date:
        query += " AND date_tested <= ?"
        params.append(args.to_date)

    query += " ORDER BY date_tested DESC"

    cursor.execute(query, params)

    results = cursor.fetchall()

    if not results:
        print("該当する施策が見つかりませんでした")
        return

    print(f"\n{'='*80}")
    print(f"検索結果: {len(results)} 件")
    print(f"{'='*80}\n")

    for row in results:
        id_, name, category, date, result, effect, reason, lesson, doc, created = row

        result_icon = "✅" if result == "accepted" else "❌" if result == "rejected" else "⏳"

        print(f"{result_icon} {name}")
        print(f"   ID: {id_}")
        print(f"   カテゴリ: {category}")
        print(f"   実施日: {date}")
        print(f"   結果: {result}")
        if effect:
            print(f"   効果: {effect}")
        if reason:
            print(f"   理由: {reason}")
        if lesson:
            print(f"   教訓: {lesson}")
        if doc:
            print(f"   詳細: {doc}")
        print()


def show_statistics(conn):
    """統計情報を表示"""
    cursor = conn.cursor()

    print(f"\n{'='*80}")
    print("知見DB統計情報")
    print(f"{'='*80}\n")

    # 施策数
    cursor.execute("SELECT COUNT(*) FROM experiments")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM experiments WHERE result = 'accepted'")
    accepted = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM experiments WHERE result = 'rejected'")
    rejected = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM experiments WHERE result = 'pending'")
    pending = cursor.fetchone()[0]

    print(f"【施策数】")
    print(f"  総数:     {total} 件")
    print(f"  採用:     {accepted} 件 ({accepted/total*100:.1f}%)")
    print(f"  不採用:   {rejected} 件 ({rejected/total*100:.1f}%)")
    print(f"  検証中:   {pending} 件")
    print()

    # カテゴリ別統計
    cursor.execute("""
        SELECT category, result, COUNT(*) as count
        FROM experiments
        GROUP BY category, result
        ORDER BY category, result
    """)

    categories = defaultdict(lambda: defaultdict(int))
    for category, result, count in cursor.fetchall():
        categories[category][result] = count

    print(f"【カテゴリ別統計】")
    for category, results in sorted(categories.items()):
        total_cat = sum(results.values())
        accepted_cat = results.get('accepted', 0)
        rejected_cat = results.get('rejected', 0)
        success_rate = accepted_cat / total_cat * 100 if total_cat > 0 else 0

        print(f"  {category}: {total_cat} 件（採用率 {success_rate:.1f}%）")
        if accepted_cat > 0:
            print(f"    - 採用: {accepted_cat} 件")
        if rejected_cat > 0:
            print(f"    - 不採用: {rejected_cat} 件")

    print()

    # 既知の落とし穴
    cursor.execute("SELECT COUNT(*) FROM known_pitfalls")
    pitfalls = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(occurrence_count) FROM known_pitfalls")
    total_occurrences = cursor.fetchone()[0] or 0

    print(f"【既知の落とし穴】")
    print(f"  種類数:     {pitfalls} 件")
    print(f"  総発生回数: {total_occurrences} 回")
    print()

    # 頻出問題
    cursor.execute("""
        SELECT name, occurrence_count
        FROM known_pitfalls
        WHERE occurrence_count > 1
        ORDER BY occurrence_count DESC
    """)

    freq_pitfalls = cursor.fetchall()
    if freq_pitfalls:
        print(f"【頻出問題】")
        for name, count in freq_pitfalls:
            print(f"  - {name}: {count} 回")
        print()

    # 実装済み機能
    cursor.execute("SELECT COUNT(*) FROM implemented_features WHERE status = 'enabled'")
    enabled = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM implemented_features WHERE status = 'disabled'")
    disabled = cursor.fetchone()[0]

    print(f"【実装済み機能】")
    print(f"  有効:   {enabled} 件")
    print(f"  無効:   {disabled} 件")
    print()


def main():
    parser = argparse.ArgumentParser(description='知見DB高度検索')
    parser.add_argument('--category', help='カテゴリで検索')
    parser.add_argument('--result', choices=['accepted', 'rejected', 'pending'],
                        help='結果で検索')
    parser.add_argument('--from', dest='from_date', help='開始日（YYYY-MM-DD）')
    parser.add_argument('--to', dest='to_date', help='終了日（YYYY-MM-DD）')
    parser.add_argument('--stats', action='store_true', help='統計情報を表示')

    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"[ERROR] 知見DBが見つかりません: {DB_PATH}")
        print("先に 'python scripts/setup_knowledge_db.py' を実行してください")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)

    try:
        if args.stats:
            show_statistics(conn)
        else:
            query_experiments(conn, args)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
