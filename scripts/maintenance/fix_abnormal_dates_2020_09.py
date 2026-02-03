#!/usr/bin/env python3
"""
2020年9月の異常な日付形式（YYYYMMDD）を正常な形式（YYYY-MM-DD）に修正するスクリプト

問題:
  2020年9月のレースデータが「YYYYMMDD」形式（例: 20200901）で登録されている
  正常な形式は「YYYY-MM-DD」（例: 2020-09-01）

修正内容:
  - YYYYMMDD形式の日付をYYYY-MM-DD形式に変換
  - race_id、venue_code、race_numberは保持
  - トランザクション管理で安全に更新

使用方法:
  python scripts/maintenance/fix_abnormal_dates_2020_09.py
  python scripts/maintenance/fix_abnormal_dates_2020_09.py --dry-run  # 確認のみ
"""

import sqlite3
import sys
from pathlib import Path
import argparse

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from config.settings import DATABASE_PATH


def fix_abnormal_dates(dry_run=False):
    """
    YYYYMMDD形式の日付をYYYY-MM-DD形式に修正

    Args:
        dry_run: Trueの場合、実際の更新は行わず確認のみ
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        # 異常な形式のレコードを取得
        cursor.execute("""
            SELECT id, race_date, venue_code, race_number
            FROM races
            WHERE race_date LIKE '202009__'
              AND race_date NOT LIKE '%-%'
            ORDER BY race_date, venue_code, race_number
        """)

        abnormal_records = cursor.fetchall()

        if not abnormal_records:
            print("異常な日付形式のレコードは見つかりませんでした。")
            return

        print(f"異常な日付形式のレコード: {len(abnormal_records)}件")
        print("\n【修正対象のサンプル（先頭10件）】")
        for i, (race_id, old_date, venue, race_num) in enumerate(abnormal_records[:10], 1):
            new_date = f"{old_date[:4]}-{old_date[4:6]}-{old_date[6:]}"
            venue_int = int(venue) if str(venue).isdigit() else 0
            race_int = int(race_num) if str(race_num).isdigit() else 0
            print(f"  {i}. race_id={race_id}, {old_date} -> {new_date} (会場{venue_int:02d} R{race_int:02d})")

        if len(abnormal_records) > 10:
            print(f"  ... 他 {len(abnormal_records) - 10} 件")

        if dry_run:
            print("\n[DRY-RUN MODE] 実際の更新は行いません。")
            print("\n【統計情報】")

            # 日付別の件数を表示
            cursor.execute("""
                SELECT race_date, COUNT(*) as cnt
                FROM races
                WHERE race_date LIKE '202009__'
                  AND race_date NOT LIKE '%-%'
                GROUP BY race_date
                ORDER BY race_date
            """)
            print("\n日付別の件数:")
            for old_date, cnt in cursor.fetchall():
                new_date = f"{old_date[:4]}-{old_date[4:6]}-{old_date[6:]}"
                print(f"  {old_date} -> {new_date}: {cnt}件")

            return

        # 実際の更新処理
        print("\n更新を開始します...")

        updated_count = 0
        for race_id, old_date, venue, race_num in abnormal_records:
            new_date = f"{old_date[:4]}-{old_date[4:6]}-{old_date[6:]}"

            cursor.execute("""
                UPDATE races
                SET race_date = ?
                WHERE id = ?
            """, (new_date, race_id))

            updated_count += 1

            if updated_count % 100 == 0:
                print(f"  {updated_count}/{len(abnormal_records)} 件更新完了")

        # コミット
        conn.commit()
        print(f"\nOK: 更新完了: {updated_count}件のレコードを修正しました")

        # 検証: 異常な形式が残っていないか確認
        cursor.execute("""
            SELECT COUNT(*)
            FROM races
            WHERE race_date LIKE '202009__'
              AND race_date NOT LIKE '%-%'
        """)
        remaining = cursor.fetchone()[0]

        if remaining > 0:
            print(f"\n⚠ 警告: まだ{remaining}件の異常な形式が残っています")
        else:
            print("\nOK: 検証完了: すべての異常な形式が修正されました")

            # 修正後の2020年9月のデータを確認
            cursor.execute("""
                SELECT race_date, COUNT(*) as cnt
                FROM races
                WHERE race_date >= '2020-09-01' AND race_date <= '2020-09-30'
                GROUP BY race_date
                ORDER BY race_date
                LIMIT 10
            """)
            print("\n【修正後のデータ（先頭10日分）】")
            for date, cnt in cursor.fetchall():
                print(f"  {date}: {cnt}件")

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: エラーが発生しました: {e}")
        raise

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="2020年9月の異常な日付形式を修正",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # dry-runで確認
  python scripts/maintenance/fix_abnormal_dates_2020_09.py --dry-run

  # 実際に修正
  python scripts/maintenance/fix_abnormal_dates_2020_09.py
        """
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='実際の更新は行わず、確認のみ行う'
    )

    args = parser.parse_args()

    print("=" * 70)
    print("2020年9月 異常な日付形式修正スクリプト")
    print("=" * 70)
    print(f"データベース: {DATABASE_PATH}")
    print(f"モード: {'DRY-RUN（確認のみ）' if args.dry_run else '実行モード（実際に更新）'}")
    print("=" * 70)
    print()

    fix_abnormal_dates(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
