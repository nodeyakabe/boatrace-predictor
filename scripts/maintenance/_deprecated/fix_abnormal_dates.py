"""
YYYYMMDD形式の日付をYYYY-MM-DD形式に修正するスクリプト

対象:
- 2020年9月以外のYYYYMMDD形式レコード
- 2020年9月は fix_abnormal_dates_2020_09_v2.py で事前処理済み
"""

import sqlite3
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import DATABASE_PATH as DB_PATH

def find_abnormal_dates(conn):
    """YYYYMMDD形式のレコードを検出"""
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            race_date,
            COUNT(*) as count
        FROM races
        WHERE race_date NOT LIKE '%-%--%'
        GROUP BY race_date
        ORDER BY race_date
    """)

    abnormal_dates = cursor.fetchall()
    return abnormal_dates

def convert_date_format(date_str):
    """YYYYMMDDをYYYY-MM-DDに変換"""
    if len(date_str) != 8:
        raise ValueError(f"Invalid date format: {date_str}")

    year = date_str[:4]
    month = date_str[4:6]
    day = date_str[6:8]

    return f"{year}-{month}-{day}"

def check_duplicates(conn, old_date, new_date):
    """変換後に重複が発生しないか確認"""
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            a.id as old_id,
            a.venue_code,
            a.race_number,
            b.id as new_id
        FROM races a
        LEFT JOIN races b ON
            b.race_date = ?
            AND b.venue_code = a.venue_code
            AND b.race_number = a.race_number
        WHERE a.race_date = ?
        AND b.id IS NOT NULL
    """, (new_date, old_date))

    duplicates = cursor.fetchall()
    return duplicates

def update_date_format(conn, old_date, new_date):
    """日付形式を更新"""
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE races
        SET race_date = ?
        WHERE race_date = ?
    """, (new_date, old_date))

    updated_count = cursor.rowcount
    return updated_count

def main():
    """メイン処理"""
    print("日付形式修正スクリプト（YYYYMMDD → YYYY-MM-DD）")
    print("=" * 80)

    conn = sqlite3.connect(DB_PATH)

    try:
        # 異常な日付を検出
        print("\n異常な日付形式のレコードを検索中...")
        abnormal_dates = find_abnormal_dates(conn)

        if not abnormal_dates:
            print("異常な日付形式のレコードは見つかりませんでした")
            return

        print(f"\n異常な日付形式: {len(abnormal_dates)} 種類")
        print("\n日付形式 | レコード数")
        print("-" * 30)
        for date_str, count in abnormal_dates[:20]:
            print(f"{date_str} | {count} 件")

        if len(abnormal_dates) > 20:
            print(f"... 他 {len(abnormal_dates) - 20} 件")

        # 確認
        print("\n" + "=" * 80)
        response = input("修正を実行しますか？ (yes/no): ")
        if response.lower() != 'yes':
            print("処理をキャンセルしました")
            return

        # 変換実行
        print("\n" + "=" * 80)
        print("日付形式を修正中...")
        print("=" * 80)

        total_updated = 0
        errors = []

        for old_date, count in abnormal_dates:
            try:
                # 日付変換
                new_date = convert_date_format(old_date)

                # 重複チェック
                duplicates = check_duplicates(conn, old_date, new_date)
                if duplicates:
                    error_msg = f"{old_date} → {new_date}: 重複あり ({len(duplicates)} 件)"
                    errors.append(error_msg)
                    print(f"[SKIP] {error_msg}")
                    continue

                # 更新実行
                updated = update_date_format(conn, old_date, new_date)
                total_updated += updated
                print(f"[OK] {old_date} → {new_date}: {updated} 件")

            except Exception as e:
                error_msg = f"{old_date}: {str(e)}"
                errors.append(error_msg)
                print(f"[ERROR] {error_msg}")

        # コミット
        conn.commit()
        print("\n" + "=" * 80)
        print("トランザクションをコミットしました")

        # 結果サマリー
        print("\n" + "=" * 80)
        print("修正結果")
        print("=" * 80)
        print(f"更新レコード数: {total_updated} 件")

        if errors:
            print(f"\nエラー・スキップ: {len(errors)} 件")
            for error in errors[:10]:
                print(f"  - {error}")
            if len(errors) > 10:
                print(f"  ... 他 {len(errors) - 10} 件")
        else:
            print("\n[OK] すべての修正に成功")

        # 検証
        print("\n" + "=" * 80)
        print("修正後の検証")
        print("=" * 80)
        abnormal_dates_after = find_abnormal_dates(conn)
        if abnormal_dates_after:
            print(f"[WARNING] まだ異常な日付形式が {len(abnormal_dates_after)} 種類残っています")
            for date_str, count in abnormal_dates_after[:5]:
                print(f"  {date_str}: {count} 件")
        else:
            print("[OK] すべての日付形式が修正されました")

    except Exception as e:
        conn.rollback()
        print(f"\nエラーが発生しました: {e}")
        print("ロールバックしました")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()
