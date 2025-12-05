"""潮位紐付け進捗監視"""
import sqlite3
import time

db_path = 'data/boatrace.db'

print("=" * 80)
print("潮位データ紐付け進捗監視")
print("=" * 80)

while True:
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 総件数
        cursor.execute('''
            SELECT COUNT(*) FROM race_tide_data
        ''')
        total_linked = cursor.fetchone()[0]

        # RDMDB実測値
        cursor.execute('''
            SELECT COUNT(*) FROM race_tide_data
            WHERE data_source = 'rdmdb'
        ''')
        rdmdb_count = cursor.fetchone()[0]

        # 推論値
        cursor.execute('''
            SELECT COUNT(*) FROM race_tide_data
            WHERE data_source = 'inferred'
        ''')
        inferred_count = cursor.fetchone()[0]

        # 対象レース総数
        cursor.execute('''
            SELECT COUNT(*) FROM races
            WHERE venue_code IN ('15', '16', '17', '18', '20', '22', '24')
            AND race_status = 'completed'
            AND race_time IS NOT NULL
        ''')
        total_races = cursor.fetchone()[0]

        conn.close()

        print(f"\r進捗: {total_linked:,}/{total_races:,} ({total_linked/total_races*100:.1f}%) | RDMDB: {rdmdb_count:,} | 推論: {inferred_count:,}", end='')

        time.sleep(5)

    except KeyboardInterrupt:
        print("\n監視終了")
        break
    except Exception as e:
        print(f"\nエラー: {e}")
        time.sleep(5)
