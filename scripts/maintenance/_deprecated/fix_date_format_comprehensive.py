#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
日付フォーマット修正スクリプト

YYYYMMDD形式の異常データを削除し、CSVを修正して再投入します。

実行手順:
1. 異常データ（YYYYMMDD形式）をDBから削除
2. CSVファイルの日付をYYYY-MM-DD形式に修正
3. 修正したCSVを再投入

推定所要時間: 約30分
"""
import sys
import io
import sqlite3
import csv
from pathlib import Path
from datetime import datetime

# Windows文字コード対策
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DATABASE_PATH

def fix_date_format(date_str):
    """YYYYMMDD → YYYY-MM-DD"""
    if isinstance(date_str, str) and len(date_str) == 8 and date_str.isdigit():
        return f'{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}'
    return date_str

def step1_delete_invalid_data():
    """ステップ1: 異常データの削除"""
    print("=" * 80)
    print("ステップ1: 異常データの削除")
    print("=" * 80)
    print()

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 異常データの数を確認
    cursor.execute("""
        SELECT COUNT(*) FROM races
        WHERE race_date NOT LIKE '____-__-__'
    """)
    invalid_races = cursor.fetchone()[0]
    print(f"削除対象レース数: {invalid_races:,}件")

    if invalid_races == 0:
        print("✅ 異常データはありません")
        conn.close()
        return

    # 関連データの数を確認
    cursor.execute("""
        SELECT COUNT(*) FROM entries
        WHERE race_id IN (
            SELECT id FROM races WHERE race_date NOT LIKE '____-__-__'
        )
    """)
    invalid_entries = cursor.fetchone()[0]
    print(f"削除対象エントリー数: {invalid_entries:,}件")

    cursor.execute("""
        SELECT COUNT(*) FROM results
        WHERE race_id IN (
            SELECT id FROM races WHERE race_date NOT LIKE '____-__-__'
        )
    """)
    invalid_results = cursor.fetchone()[0]
    print(f"削除対象結果数: {invalid_results:,}件")

    # 確認
    print()
    print("以下のデータを削除します:")
    print(f"  - レース: {invalid_races:,}件")
    print(f"  - エントリー: {invalid_entries:,}件")
    print(f"  - 結果: {invalid_results:,}件")
    print()

    # 削除実行
    print("削除を実行中...")
    cursor.execute("BEGIN TRANSACTION")

    # entries削除
    cursor.execute("""
        DELETE FROM entries
        WHERE race_id IN (
            SELECT id FROM races WHERE race_date NOT LIKE '____-__-__'
        )
    """)
    print(f"✓ エントリー削除: {cursor.rowcount:,}件")

    # results削除
    cursor.execute("""
        DELETE FROM results
        WHERE race_id IN (
            SELECT id FROM races WHERE race_date NOT LIKE '____-__-__'
        )
    """)
    print(f"✓ 結果削除: {cursor.rowcount:,}件")

    # payouts削除
    cursor.execute("""
        DELETE FROM payouts
        WHERE race_id IN (
            SELECT id FROM races WHERE race_date NOT LIKE '____-__-__'
        )
    """)
    print(f"✓ 払戻削除: {cursor.rowcount:,}件")

    # trifecta_odds削除
    cursor.execute("""
        DELETE FROM trifecta_odds
        WHERE race_id IN (
            SELECT id FROM races WHERE race_date NOT LIKE '____-__-__'
        )
    """)
    print(f"✓ オッズ削除: {cursor.rowcount:,}件")

    # race_conditions削除
    cursor.execute("""
        DELETE FROM race_conditions
        WHERE race_id IN (
            SELECT id FROM races WHERE race_date NOT LIKE '____-__-__'
        )
    """)
    print(f"✓ レース条件削除: {cursor.rowcount:,}件")

    # race_details削除
    cursor.execute("""
        DELETE FROM race_details
        WHERE race_id IN (
            SELECT id FROM races WHERE race_date NOT LIKE '____-__-__'
        )
    """)
    print(f"✓ レース詳細削除: {cursor.rowcount:,}件")

    # races削除
    cursor.execute("""
        DELETE FROM races
        WHERE race_date NOT LIKE '____-__-__'
    """)
    print(f"✓ レース削除: {cursor.rowcount:,}件")

    # コミット
    cursor.execute("COMMIT")
    print()
    print("✅ 異常データの削除が完了しました")
    print()

    conn.close()

def step2_fix_csv_files():
    """ステップ2: CSVファイルの日付修正"""
    print("=" * 80)
    print("ステップ2: CSVファイルの日付修正")
    print("=" * 80)
    print()

    fixed_files = 0
    fixed_records = 0

    for year in [2021, 2023]:
        for month in range(1, 13):
            csv_dir = PROJECT_ROOT / 'data' / 'csv' / '補完' / str(year) / f'{month:02d}'
            if not csv_dir.exists():
                continue

            print(f"処理中: {year}年{month}月")

            for csv_filename in ['races.csv', 'entries.csv', 'results.csv', 'payouts.csv']:
                csv_path = csv_dir / csv_filename
                if not csv_path.exists():
                    continue

                # CSVを読み込み
                data = []
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    headers = reader.fieldnames
                    for row in reader:
                        if 'race_date' in row:
                            row['race_date'] = fix_date_format(row['race_date'])
                            fixed_records += 1
                        data.append(row)

                # 上書き保存
                if data:
                    with open(csv_path, 'w', encoding='utf-8', newline='') as f:
                        writer = csv.DictWriter(f, fieldnames=headers)
                        writer.writeheader()
                        writer.writerows(data)
                    fixed_files += 1
                    print(f"  ✓ {csv_filename}: {len(data):,}件修正")

    print()
    print(f"✅ CSVファイルの修正が完了しました")
    print(f"   修正ファイル数: {fixed_files}個")
    print(f"   修正レコード数: {fixed_records:,}件")
    print()

def step3_verify():
    """ステップ3: 検証"""
    print("=" * 80)
    print("ステップ3: 修正結果の検証")
    print("=" * 80)
    print()

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 異常データの確認
    cursor.execute("""
        SELECT COUNT(*) FROM races
        WHERE race_date NOT LIKE '____-__-__'
    """)
    remaining_invalid = cursor.fetchone()[0]

    if remaining_invalid == 0:
        print("✅ 異常データは全て削除されました")
    else:
        print(f"⚠️ 警告: まだ{remaining_invalid:,}件の異常データが残っています")

    # 全体のレース数
    cursor.execute("SELECT COUNT(*) FROM races")
    total_races = cursor.fetchone()[0]
    print(f"✅ 現在のレース数: {total_races:,}件")

    print()
    print("次のステップ:")
    print("1. 修正したCSVを再投入してください:")
    print("   python scripts/maintenance/投入_2021_2023_補完データ.py --year 2021 --all-months")
    print("   python scripts/maintenance/投入_2021_2023_補完データ.py --year 2023 --all-months")
    print()
    print("2. 再投入後、データ充足率を確認してください:")
    print("   python scripts/analysis/check_2021_2023_data.py")
    print()

    conn.close()

def main():
    print("=" * 80)
    print("日付フォーマット包括的修正スクリプト")
    print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print()

    try:
        # ステップ1: 異常データ削除
        step1_delete_invalid_data()

        # ステップ2: CSVファイル修正
        step2_fix_csv_files()

        # ステップ3: 検証
        step3_verify()

        print("=" * 80)
        print("✅ 全ての修正処理が完了しました")
        print("=" * 80)
        print()

        return 0

    except Exception as e:
        print(f"\n❌ エラーが発生しました: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())
