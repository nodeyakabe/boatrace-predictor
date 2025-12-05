#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
BatchDataLoaderのロード時間測定
"""
import sys
import os
import time

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from config.settings import DATABASE_PATH
from src.database.batch_data_loader import BatchDataLoader


def get_latest_race_date():
    """最新のレース日を取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT race_date FROM races ORDER BY race_date DESC LIMIT 1')
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def main():
    print("="*70)
    print("BatchDataLoader ロード時間測定")
    print("="*70)

    target_date = get_latest_race_date()

    if not target_date:
        print("レース日が見つかりませんでした")
        return

    print(f"\nテスト対象日: {target_date}")

    loader = BatchDataLoader(DATABASE_PATH)

    start = time.time()
    try:
        loader.load_daily_data(target_date)
        elapsed = time.time() - start

        print(f"\n✓ ロード完了: {elapsed:.2f}秒")

        # キャッシュサイズ確認
        cache_keys = list(loader._cache.keys())
        print(f"\nキャッシュキー数: {len(cache_keys)}")
        for key in cache_keys:
            data = loader._cache[key]
            if isinstance(data, dict):
                print(f"  {key}: {len(data)} 件")
            else:
                print(f"  {key}: {type(data)}")

    except Exception as e:
        elapsed = time.time() - start
        print(f"\n✗ エラー ({elapsed:.2f}秒): {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*70)


if __name__ == "__main__":
    main()
