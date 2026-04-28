# -*- coding: utf-8 -*-
"""
races テーブルのデータ整合性修正スクリプト

修正内容:
  1. is_nighter: 全399K件=0 → ナイター専用会場(9会場)を1に更新
  2. venue_code: 1桁336件 → 2桁ゼロパディング正規化

実行例:
    python scripts/maintenance/fix_races_nighter_venue_code.py --dry-run
    python scripts/maintenance/fix_races_nighter_venue_code.py
"""
import sys
import io
import sqlite3
import argparse
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / 'data' / 'boatrace.db'

# ナイター専用会場コード（2桁）
NIGHTER_VENUES = ('01', '02', '06', '07', '12', '17', '20', '21', '24')


def fix_venue_code(conn: sqlite3.Connection, dry_run: bool) -> int:
    """venue_code の1桁→2桁正規化"""
    cur = conn.cursor()

    # 確認
    cur.execute("SELECT COUNT(*) FROM races WHERE LENGTH(venue_code) = 1")
    count = cur.fetchone()[0]
    print(f"  1桁venue_code件数: {count}件")

    if count == 0:
        print("  → 対象なし。スキップ。")
        return 0

    if dry_run:
        cur.execute("""
            SELECT venue_code, COUNT(*) FROM races
            WHERE LENGTH(venue_code) = 1
            GROUP BY venue_code ORDER BY venue_code
        """)
        for row in cur.fetchall():
            print(f"    venue_code='{row[0]}' → '{row[0].zfill(2)}' ({row[1]}件)")
        print("  → [DRY RUN] 実際には更新しません")
        return count

    # 2桁版が既に存在する場合はDUPLICATE → 1桁版を削除
    cur.execute("""
        DELETE FROM races
        WHERE LENGTH(venue_code) = 1
          AND EXISTS (
            SELECT 1 FROM races r2
            WHERE r2.venue_code = printf('%02d', CAST(races.venue_code AS INTEGER))
              AND r2.race_date  = races.race_date
              AND r2.race_number = races.race_number
          )
    """)
    deleted = cur.rowcount
    if deleted > 0:
        print(f"  → 2桁版と重複していた {deleted} 件の1桁レコードを削除")

    # 残った1桁レコードを2桁に更新
    cur.execute("""
        UPDATE races
        SET venue_code = printf('%02d', CAST(venue_code AS INTEGER))
        WHERE LENGTH(venue_code) = 1
    """)
    updated = cur.rowcount
    conn.commit()
    print(f"  → {updated}件を2桁に正規化しました（合計処理: {deleted + updated}件）")
    return deleted + updated


def fix_is_nighter(conn: sqlite3.Connection, dry_run: bool) -> int:
    """ナイター専用会場の is_nighter を 0→1 に更新"""
    cur = conn.cursor()

    placeholders = ','.join(['?'] * len(NIGHTER_VENUES))

    # 確認
    cur.execute(f"""
        SELECT COUNT(*) FROM races
        WHERE venue_code IN ({placeholders}) AND is_nighter = 0
    """, NIGHTER_VENUES)
    count = cur.fetchone()[0]
    print(f"  is_nighter=0 のナイター会場レース数: {count}件")

    if count == 0:
        print("  → 対象なし。スキップ。")
        return 0

    if dry_run:
        cur.execute(f"""
            SELECT venue_code, COUNT(*) FROM races
            WHERE venue_code IN ({placeholders}) AND is_nighter = 0
            GROUP BY venue_code ORDER BY venue_code
        """, NIGHTER_VENUES)
        for row in cur.fetchall():
            print(f"    venue_code={row[0]}: {row[1]}件 → is_nighter=1")
        print("  → [DRY RUN] 実際には更新しません")
        return count

    cur.execute(f"""
        UPDATE races
        SET is_nighter = 1
        WHERE venue_code IN ({placeholders}) AND is_nighter = 0
    """, NIGHTER_VENUES)
    updated = cur.rowcount
    conn.commit()
    print(f"  → {updated}件を is_nighter=1 に更新しました")
    return updated


def verify(conn: sqlite3.Connection):
    """修正後の確認"""
    cur = conn.cursor()
    print("\n=== 修正後確認 ===")

    cur.execute("SELECT LENGTH(venue_code), COUNT(*) FROM races GROUP BY LENGTH(venue_code)")
    print("venue_code 桁数:")
    for row in cur.fetchall():
        print(f"  {row[0]}桁: {row[1]}件")

    cur.execute("SELECT is_nighter, COUNT(*) FROM races GROUP BY is_nighter")
    print("is_nighter 分布:")
    for row in cur.fetchall():
        print(f"  is_nighter={row[0]}: {row[1]}件")

    cur.execute("""
        SELECT venue_code, COUNT(*) FROM races
        WHERE is_nighter = 1
        GROUP BY venue_code ORDER BY venue_code
    """)
    rows = cur.fetchall()
    if rows:
        print("ナイター会場別件数:")
        for row in rows:
            print(f"  {row[0]}: {row[1]}件")


def main():
    parser = argparse.ArgumentParser(description='races テーブルのis_nighter・venue_code修正')
    parser.add_argument('--dry-run', action='store_true', help='確認のみ（DBを変更しない）')
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"[ERROR] DBが見つかりません: {DB_PATH}")
        sys.exit(1)

    mode = "[DRY RUN]" if args.dry_run else "[実行]"
    print(f"=== races テーブル整合性修正 {mode} ===")
    print(f"DB: {DB_PATH}\n")

    conn = sqlite3.connect(str(DB_PATH))
    try:
        print("--- Fix 1: venue_code 1桁→2桁正規化 ---")
        fix_venue_code(conn, args.dry_run)

        print("\n--- Fix 2: is_nighter ナイター会場を1に更新 ---")
        fix_is_nighter(conn, args.dry_run)

        if not args.dry_run:
            verify(conn)

    finally:
        conn.close()

    print("\n完了。")


if __name__ == '__main__':
    main()
