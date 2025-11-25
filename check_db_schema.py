"""データベーススキーマを詳細確認"""
import sys
sys.path.append('src')
import sqlite3
from config.settings import DATABASE_PATH

conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()

print("="*70)
print("データベーススキーマ確認")
print("="*70)

# 全テーブルリスト
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [row[0] for row in cursor.fetchall()]
print(f"\n全テーブル ({len(tables)}個):")
for table in tables:
    print(f"  - {table}")

# 主要テーブルの詳細スキーマ
important_tables = ['races', 'race_details', 'results', 'entries']

for table in important_tables:
    if table in tables:
        print(f"\n{'='*70}")
        print(f"テーブル: {table}")
        print('-'*70)

        cursor.execute(f"PRAGMA table_info({table})")
        columns = cursor.fetchall()

        print(f"カラム数: {len(columns)}")
        for col in columns:
            cid, name, type_, notnull, default, pk = col
            pk_mark = " [PK]" if pk else ""
            null_mark = " NOT NULL" if notnull else ""
            default_mark = f" DEFAULT {default}" if default else ""
            print(f"  {name:25s} {type_:15s}{pk_mark}{null_mark}{default_mark}")

        # レコード数
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"\nレコード数: {count:,}")

        # サンプルデータ（最初の1行）
        if count > 0:
            cursor.execute(f"SELECT * FROM {table} LIMIT 1")
            sample = cursor.fetchone()
            print("\nサンプルデータ:")
            for i, col in enumerate(columns):
                print(f"  {col[1]:25s} = {sample[i]}")

# race_detailsの特殊カラムをチェック
print(f"\n{'='*70}")
print("race_details の finish_position と kimarite をチェック")
print('-'*70)

cursor.execute("PRAGMA table_info(race_details)")
rd_columns = [col[1] for col in cursor.fetchall()]

if 'finish_position' in rd_columns:
    print("✓ finish_position カラムが存在します")
    cursor.execute("SELECT COUNT(*) FROM race_details WHERE finish_position IS NOT NULL")
    count = cursor.fetchone()[0]
    print(f"  データ件数: {count:,}")
else:
    print("✗ finish_position カラムが存在しません")

if 'kimarite' in rd_columns:
    print("✓ kimarite カラムが存在します")
    cursor.execute("SELECT COUNT(*) FROM race_details WHERE kimarite IS NOT NULL")
    count = cursor.fetchone()[0]
    print(f"  データ件数: {count:,}")
else:
    print("✗ kimarite カラムが存在しません")

# resultsの特殊カラムをチェック
print(f"\n{'='*70}")
print("results の kimarite をチェック")
print('-'*70)

cursor.execute("PRAGMA table_info(results)")
results_columns = [col[1] for col in cursor.fetchall()]

if 'kimarite' in results_columns:
    print("✓ kimarite カラムが存在します")
    cursor.execute("SELECT COUNT(*) FROM results WHERE kimarite IS NOT NULL")
    count = cursor.fetchone()[0]
    print(f"  データ件数: {count:,}")
else:
    print("✗ kimarite カラムが存在しません")

# fast_data_manager の race_results テーブル確認
if 'race_results' in tables:
    print(f"\n{'='*70}")
    print("⚠️ race_results テーブルが存在します（fast_data_manager用）")
    print('-'*70)
    cursor.execute("PRAGMA table_info(race_results)")
    rr_columns = cursor.fetchall()
    print(f"カラム数: {len(rr_columns)}")
    for col in rr_columns:
        print(f"  {col[1]:25s} {col[2]:15s}")

    cursor.execute("SELECT COUNT(*) FROM race_results")
    count = cursor.fetchone()[0]
    print(f"レコード数: {count:,}")

conn.close()

print("\n" + "="*70)
print("チェック完了")
print("="*70)
