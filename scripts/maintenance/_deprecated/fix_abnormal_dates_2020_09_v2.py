"""
2020年9月のYYYYMMDD形式レコード削除スクリプト（重複解消版）

調査結果:
- YYYYMMDD形式: 3,000件（ID: 171267-176666）
  - 関連データ: なし（entries, results, race_conditions等すべて0件）

- YYYY-MM-DD形式: 4,522件
  - 関連データ: あり（entries 39,870件、results 39,222件）

- 重複: 3,000ペア（完全に重複）

対処方針:
- YYYYMMDD形式の3,000件を削除（空データのため安全）
- YYYY-MM-DD形式は保持（実データが存在）
- その後、元の日付形式修正スクリプトを実行可能になる
"""

import sqlite3
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import DATABASE_PATH as DB_PATH

def verify_before_delete(conn):
    """削除前の検証"""
    cursor = conn.cursor()

    print("=" * 80)
    print("削除前の検証")
    print("=" * 80)

    # 削除対象のレコード数確認
    cursor.execute("""
        SELECT COUNT(*)
        FROM races
        WHERE race_date LIKE '202009%' AND race_date NOT LIKE '%-%'
    """)
    abnormal_count = cursor.fetchone()[0]
    print(f"削除対象レコード数: {abnormal_count} 件")

    # 関連データの確認
    cursor.execute("""
        SELECT
            SUM(CASE WHEN e.id IS NOT NULL THEN 1 ELSE 0 END) as entries,
            SUM(CASE WHEN res.id IS NOT NULL THEN 1 ELSE 0 END) as results,
            SUM(CASE WHEN rc.id IS NOT NULL THEN 1 ELSE 0 END) as conditions,
            SUM(CASE WHEN rp.id IS NOT NULL THEN 1 ELSE 0 END) as predictions,
            SUM(CASE WHEN t.id IS NOT NULL THEN 1 ELSE 0 END) as trifecta_odds
        FROM races r
        LEFT JOIN entries e ON r.id = e.race_id
        LEFT JOIN results res ON r.id = res.race_id
        LEFT JOIN race_conditions rc ON r.id = rc.race_id
        LEFT JOIN race_predictions rp ON r.id = rp.race_id
        LEFT JOIN trifecta_odds t ON r.id = t.race_id
        WHERE r.race_date LIKE '202009%' AND r.race_date NOT LIKE '%-%'
    """)
    row = cursor.fetchone()
    print(f"関連データ - entries: {row[0]}, results: {row[1]}, conditions: {row[2]}")
    print(f"           predictions: {row[3]}, trifecta_odds: {row[4]}")

    # すべてゼロなら安全
    if all(v == 0 for v in row):
        print("\n[OK] 関連データなし - 安全に削除可能")
        return True
    else:
        print("\n[NG] 関連データあり - 削除中止")
        return False

def delete_abnormal_records(conn):
    """YYYYMMDD形式のレコードを削除"""
    cursor = conn.cursor()

    print("\n" + "=" * 80)
    print("削除実行")
    print("=" * 80)

    # 削除実行
    cursor.execute("""
        DELETE FROM races
        WHERE race_date LIKE '202009%' AND race_date NOT LIKE '%-%'
    """)

    deleted_count = cursor.rowcount
    print(f"削除完了: {deleted_count} 件")

    return deleted_count

def verify_after_delete(conn):
    """削除後の検証"""
    cursor = conn.cursor()

    print("\n" + "=" * 80)
    print("削除後の検証")
    print("=" * 80)

    # 異常形式が残っていないか確認
    cursor.execute("""
        SELECT COUNT(*)
        FROM races
        WHERE race_date LIKE '202009%' AND race_date NOT LIKE '%-%'
    """)
    remaining = cursor.fetchone()[0]
    print(f"YYYYMMDD形式の残存: {remaining} 件")

    # 正常形式のレコード数確認
    cursor.execute("""
        SELECT COUNT(*)
        FROM races
        WHERE race_date LIKE '2020-09-%'
    """)
    normal_count = cursor.fetchone()[0]
    print(f"YYYY-MM-DD形式: {normal_count} 件")

    # UNIQUE制約テスト（変換後に衝突がないか）
    cursor.execute("""
        SELECT
            race_date,
            venue_code,
            race_number,
            COUNT(*) as cnt
        FROM races
        WHERE race_date LIKE '2020-09-%'
        GROUP BY race_date, venue_code, race_number
        HAVING COUNT(*) > 1
    """)
    duplicates = cursor.fetchall()

    if duplicates:
        print(f"\n[NG] 重複あり: {len(duplicates)} 件")
        for dup in duplicates[:5]:
            print(f"  {dup}")
        return False
    else:
        print("\n[OK] 重複なし - 日付形式修正が可能")
        return True

def main():
    """メイン処理"""
    print("2020年9月 YYYYMMDD形式レコード削除スクリプト")
    print("=" * 80)

    conn = sqlite3.connect(DB_PATH)

    try:
        # 削除前検証
        if not verify_before_delete(conn):
            print("\n処理を中止します")
            return

        # 確認
        print("\n" + "=" * 80)
        response = input("削除を実行しますか？ (yes/no): ")
        if response.lower() != 'yes':
            print("処理をキャンセルしました")
            return

        # 削除実行
        deleted = delete_abnormal_records(conn)

        # コミット
        conn.commit()
        print("\nトランザクションをコミットしました")

        # 削除後検証
        if verify_after_delete(conn):
            print("\n" + "=" * 80)
            print("[OK] すべての検証に成功")
            print("次のステップ: fix_abnormal_dates.py を実行してください")
            print("=" * 80)
        else:
            print("\n[NG] 検証に失敗しました")

    except Exception as e:
        conn.rollback()
        print(f"\nエラーが発生しました: {e}")
        print("ロールバックしました")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()
