"""
exhibition_dataの直線タイムをrace_detailsテーブルに補完

exhibition_dataテーブルには直線タイムが62.7%のレコードに存在しますが、
race_detailsテーブルには0.4%しかありません。

このスクリプトはexhibition_dataからrace_detailsへ直線タイムをコピーします。
"""

import sqlite3
from pathlib import Path
import sys

def copy_chikusen_time_to_race_details(db_path=None, dry_run=False):
    """
    exhibition_dataの直線タイムをrace_detailsにコピー

    Args:
        db_path: データベースパス
        dry_run: True の場合は実行せずに確認のみ

    Returns:
        dict: 統計情報
    """

    if db_path is None:
        db_path = Path(__file__).parent.parent.parent / "data" / "boatrace.db"

    print("=" * 80)
    print("exhibition_data → race_details 直線タイム補完スクリプト")
    print("=" * 80)
    print()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. 現在の状況確認
    print("【現在の状況】")
    print()

    cursor.execute("SELECT COUNT(*) as total FROM race_details")
    total_race_details = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) as with_time FROM race_details WHERE chikusen_time IS NOT NULL")
    race_details_with_time = cursor.fetchone()['with_time']

    cursor.execute("SELECT COUNT(*) as total FROM exhibition_data")
    total_exhibition = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) as with_time FROM exhibition_data WHERE chikusen_time IS NOT NULL")
    exhibition_with_time = cursor.fetchone()['with_time']

    print(f"race_details:")
    print(f"  総レコード数: {total_race_details:,}")
    print(f"  直線タイムあり: {race_details_with_time:,} ({race_details_with_time/total_race_details*100:.1f}%)")
    print()

    print(f"exhibition_data:")
    print(f"  総レコード数: {total_exhibition:,}")
    print(f"  直線タイムあり: {exhibition_with_time:,} ({exhibition_with_time/total_exhibition*100:.1f}%)")
    print()

    # 2. 補完可能なレコード数を確認
    cursor.execute("""
        SELECT COUNT(*) as copyable
        FROM exhibition_data ed
        JOIN race_details rd
            ON ed.race_id = rd.race_id
            AND ed.pit_number = rd.pit_number
        WHERE ed.chikusen_time IS NOT NULL
          AND (rd.chikusen_time IS NULL OR rd.chikusen_time != ed.chikusen_time)
    """)
    copyable_count = cursor.fetchone()['copyable']

    print(f"【補完可能なレコード数】")
    print(f"  {copyable_count:,}件のレコードが補完可能")
    print()

    if dry_run:
        print("【ドライランモード】実際の更新は行いません")
        print()

        # サンプル表示
        cursor.execute("""
            SELECT
                r.race_date,
                r.venue_code,
                r.race_number,
                rd.pit_number,
                ed.chikusen_time as ed_time,
                rd.chikusen_time as rd_time
            FROM exhibition_data ed
            JOIN race_details rd
                ON ed.race_id = rd.race_id
                AND ed.pit_number = rd.pit_number
            JOIN races r ON ed.race_id = r.id
            WHERE ed.chikusen_time IS NOT NULL
              AND (rd.chikusen_time IS NULL OR rd.chikusen_time != ed.chikusen_time)
            ORDER BY r.race_date DESC
            LIMIT 10
        """)
        samples = cursor.fetchall()

        print("【補完されるデータのサンプル（最新10件）】")
        print(f"{'日付':<12} {'会場':<4} {'R':<3} {'艇':<3} {'exhibition':<12} {'race_details':<12}")
        print("-" * 80)
        for row in samples:
            ed_time = f"{row['ed_time']:.2f}秒" if row['ed_time'] else "NULL"
            rd_time = f"{row['rd_time']:.2f}秒" if row['rd_time'] else "NULL"
            print(f"{row['race_date']:<12} {row['venue_code']:<4} {row['race_number']:<3} "
                  f"{row['pit_number']:<3} {ed_time:<12} {rd_time:<12}")

        conn.close()
        return {
            'dry_run': True,
            'copyable_count': copyable_count
        }

    # 3. 実際の補完実行
    print("【補完実行中...】")
    print()

    cursor.execute("""
        UPDATE race_details
        SET
            chikusen_time = (
                SELECT ed.chikusen_time
                FROM exhibition_data ed
                WHERE ed.race_id = race_details.race_id
                  AND ed.pit_number = race_details.pit_number
                  AND ed.chikusen_time IS NOT NULL
            ),
            isshu_time = (
                SELECT ed.isshu_time
                FROM exhibition_data ed
                WHERE ed.race_id = race_details.race_id
                  AND ed.pit_number = race_details.pit_number
                  AND ed.isshu_time IS NOT NULL
            ),
            mawariashi_time = (
                SELECT ed.mawariashi_time
                FROM exhibition_data ed
                WHERE ed.race_id = race_details.race_id
                  AND ed.pit_number = race_details.pit_number
                  AND ed.mawariashi_time IS NOT NULL
            )
        WHERE EXISTS (
            SELECT 1
            FROM exhibition_data ed
            WHERE ed.race_id = race_details.race_id
              AND ed.pit_number = race_details.pit_number
              AND (
                  (ed.chikusen_time IS NOT NULL AND (race_details.chikusen_time IS NULL OR race_details.chikusen_time != ed.chikusen_time))
                  OR (ed.isshu_time IS NOT NULL AND (race_details.isshu_time IS NULL OR race_details.isshu_time != ed.isshu_time))
                  OR (ed.mawariashi_time IS NOT NULL AND (race_details.mawariashi_time IS NULL OR race_details.mawariashi_time != ed.mawariashi_time))
              )
        )
    """)

    updated_count = cursor.rowcount
    conn.commit()

    print(f"  [OK] 更新完了: {updated_count:,}件")
    print()

    # 4. 補完後の状況確認
    cursor.execute("SELECT COUNT(*) as with_time FROM race_details WHERE chikusen_time IS NOT NULL")
    after_count = cursor.fetchone()['with_time']

    cursor.execute("SELECT COUNT(*) as with_isshu FROM race_details WHERE isshu_time IS NOT NULL")
    after_isshu = cursor.fetchone()['with_isshu']

    cursor.execute("SELECT COUNT(*) as with_mawariashi FROM race_details WHERE mawariashi_time IS NOT NULL")
    after_mawariashi = cursor.fetchone()['with_mawariashi']

    print("【補完後の状況】")
    print(f"race_details:")
    print(f"  直線タイムあり: {after_count:,} ({after_count/total_race_details*100:.1f}%)")
    print(f"  1周タイムあり: {after_isshu:,} ({after_isshu/total_race_details*100:.1f}%)")
    print(f"  回り足タイムあり: {after_mawariashi:,} ({after_mawariashi/total_race_details*100:.1f}%)")
    print()

    print(f"【増加数】")
    print(f"  直線タイム: +{after_count - race_details_with_time:,}件")
    print()

    conn.close()

    print("=" * 80)
    print("補完完了")
    print("=" * 80)

    return {
        'dry_run': False,
        'before_count': race_details_with_time,
        'after_count': after_count,
        'updated_count': updated_count,
        'increase': after_count - race_details_with_time
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='exhibition_dataからrace_detailsへ直線タイムを補完')
    parser.add_argument('--dry-run', action='store_true', help='ドライランモード（実際には更新しない）')
    parser.add_argument('--execute', action='store_true', help='実行モード（明示的に指定が必要）')

    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        print("エラー: --dry-run または --execute を指定してください")
        print()
        print("確認のみ: python scripts/maintenance/補完_展示データからrace_detailsへ.py --dry-run")
        print("実行: python scripts/maintenance/補完_展示データからrace_detailsへ.py --execute")
        sys.exit(1)

    result = copy_chikusen_time_to_race_details(dry_run=args.dry_run)

    if result['dry_run']:
        print()
        print(f"実行する場合: python {sys.argv[0]} --execute")
