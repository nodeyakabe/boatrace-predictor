"""
直線タイム（chikusen_time）データの確認スクリプト
3-3: chikusen_timeの補完と活用の準備
"""

import sqlite3
from pathlib import Path

def check_chikusen_time_data():
    """直線タイムデータの状況を確認"""

    db_path = Path(__file__).parent.parent.parent / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=" * 80)
    print("直線タイム（chikusen_time）データの確認")
    print("=" * 80)
    print()

    # 1. 直線タイムのカラムがあるテーブルを確認
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table'
        ORDER BY name
    """)
    tables = [row['name'] for row in cursor.fetchall()]

    # 各テーブルのカラムをチェック
    chikusen_tables = []
    for table in tables:
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [col[1] for col in cursor.fetchall()]
        if 'chikusen_time' in columns:
            chikusen_tables.append(table)

    print("【chikusen_timeカラムを持つテーブル】")
    if chikusen_tables:
        for table in chikusen_tables:
            cursor.execute(f"SELECT COUNT(*) as total FROM {table}")
            total = cursor.fetchone()['total']
            cursor.execute(f"SELECT COUNT(*) as with_time FROM {table} WHERE chikusen_time IS NOT NULL")
            with_time = cursor.fetchone()['with_time']
            coverage = (with_time / total * 100) if total > 0 else 0
            print(f"  - {table:<30} 総数:{total:>10,}  直線タイム有:{with_time:>10,} ({coverage:>5.1f}%)")
    else:
        print("  ※ chikusen_timeカラムが見つかりませんでした")
        print()
        print("  【代替確認: exhibition_dataテーブル】")
        # exhibition_dataテーブルの構造確認
        cursor.execute("PRAGMA table_info(exhibition_data)")
        columns = cursor.fetchall()
        print("  カラム一覧:")
        for col in columns:
            print(f"    - {col[1]:<30} {col[2]}")

    print()

    # 2. exhibition_dataテーブルの詳細確認
    cursor.execute("SELECT COUNT(*) as total FROM exhibition_data")
    total = cursor.fetchone()['total']

    if total > 0:
        print("【exhibition_data テーブルのデータ】")
        print(f"  総レコード数: {total:,}")
        print()

        # サンプルデータ表示
        cursor.execute("SELECT * FROM exhibition_data LIMIT 5")
        samples = cursor.fetchall()
        if samples:
            print("  サンプルデータ:")
            for i, sample in enumerate(samples, 1):
                print(f"  --- サンプル {i} ---")
                for key in sample.keys():
                    print(f"    {key}: {sample[key]}")
                print()

    # 3. オリジナル展示データ（original_tenji）の確認
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name LIKE '%tenji%'
        ORDER BY name
    """)
    tenji_tables = cursor.fetchall()

    if tenji_tables:
        print("【オリジナル展示データテーブル】")
        for table in tenji_tables:
            table_name = table['name']
            cursor.execute(f"SELECT COUNT(*) as total FROM {table_name}")
            total = cursor.fetchone()['total']
            print(f"  - {table_name:<30} レコード数:{total:>10,}")

            # カラム確認
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            print(f"    カラム: {', '.join([col[1] for col in columns])}")
            print()

    # 4. 結果テーブルでの直線タイム確認
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND (name LIKE '%result%' OR name LIKE '%race_detail%')
        ORDER BY name
    """)
    result_tables = cursor.fetchall()

    print("【結果・詳細テーブル】")
    for table in result_tables:
        table_name = table['name']
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [col[1] for col in cursor.fetchall()]

        cursor.execute(f"SELECT COUNT(*) as total FROM {table_name}")
        total = cursor.fetchone()['total']

        print(f"  - {table_name:<30} レコード数:{total:>10,}")

        # 直線タイム関連カラムをチェック
        time_columns = [c for c in columns if 'time' in c.lower() or 'chikusen' in c.lower()]
        if time_columns:
            print(f"    タイム関連カラム: {', '.join(time_columns)}")
        print()

    conn.close()

    print("=" * 80)
    print("確認完了")
    print("=" * 80)

if __name__ == "__main__":
    check_chikusen_time_data()
