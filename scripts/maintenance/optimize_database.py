#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
データベース最適化スクリプト

SQLiteデータベースのロック対策とパフォーマンス最適化を実行します。

実行内容:
1. WALモード有効化（Write-Ahead Logging）
2. タイムアウト設定の延長（30秒）
3. キャッシュサイズの最適化
4. ページサイズの最適化
5. VACUUM実行（データベース最適化）
6. ANALYZE実行（統計情報更新）
"""
import sys
import io
import sqlite3
from pathlib import Path
from datetime import datetime

# Windows文字コード対策
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DATABASE_PATH

def optimize_database():
    """データベースを最適化"""
    print("=" * 80)
    print(f"データベース最適化")
    print(f"対象DB: {DATABASE_PATH}")
    print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print()

    # データベースに接続
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 1. 現在の設定を確認
    print("[1] 現在の設定")
    print("-" * 80)

    cursor.execute("PRAGMA journal_mode")
    journal_mode = cursor.fetchone()[0]
    print(f"ジャーナルモード: {journal_mode}")

    cursor.execute("PRAGMA synchronous")
    synchronous = cursor.fetchone()[0]
    print(f"同期モード: {synchronous}")

    cursor.execute("PRAGMA cache_size")
    cache_size = cursor.fetchone()[0]
    print(f"キャッシュサイズ: {cache_size} pages")

    cursor.execute("PRAGMA page_size")
    page_size = cursor.fetchone()[0]
    print(f"ページサイズ: {page_size} bytes")
    print()

    # 2. WALモード有効化
    print("[2] WALモード有効化")
    print("-" * 80)
    cursor.execute("PRAGMA journal_mode = WAL")
    result = cursor.fetchone()[0]
    print(f"WALモード設定: {result}")
    print("✓ Write-Ahead Loggingが有効になりました")
    print("  - 読み書きの並列性が向上します")
    print("  - データベースロックが減少します")
    print()

    # 3. タイムアウト設定
    print("[3] タイムアウト設定")
    print("-" * 80)
    cursor.execute("PRAGMA busy_timeout = 30000")
    print("✓ タイムアウトを30秒に設定しました")
    print("  - データベースロック時の待機時間が延長されます")
    print()

    # 4. キャッシュサイズ最適化
    print("[4] キャッシュサイズ最適化")
    print("-" * 80)
    # -64000 = 64MB (負の値はKB単位)
    cursor.execute("PRAGMA cache_size = -64000")
    cursor.execute("PRAGMA cache_size")
    new_cache_size = cursor.fetchone()[0]
    print(f"✓ キャッシュサイズを約64MBに設定しました")
    print(f"  新しいキャッシュサイズ: {new_cache_size} pages")
    print("  - クエリパフォーマンスが向上します")
    print()

    # 5. 同期モード設定
    print("[5] 同期モード設定")
    print("-" * 80)
    # WALモード使用時はNORMALが推奨
    cursor.execute("PRAGMA synchronous = NORMAL")
    cursor.execute("PRAGMA synchronous")
    new_sync = cursor.fetchone()[0]
    print(f"✓ 同期モードをNORMALに設定しました（{new_sync}）")
    print("  - 書き込みパフォーマンスとデータ保護のバランスが最適化されます")
    print()

    # 6. テーブル数とサイズ確認
    print("[6] データベース統計")
    print("-" * 80)
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table'
        ORDER BY name
    """)
    tables = cursor.fetchall()
    print(f"テーブル数: {len(tables)}個")

    # 各テーブルのレコード数を表示
    print("\n主要テーブルのレコード数:")
    main_tables = ['races', 'entries', 'results', 'trifecta_odds', 'race_predictions', 'race_details']
    for table_name in main_tables:
        if any(t[0] == table_name for t in tables):
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            print(f"  {table_name:20s}: {count:>10,}件")
    print()

    # 7. VACUUM実行（データベース最適化）
    print("[7] VACUUM実行（データベース最適化）")
    print("-" * 80)
    print("注意: VACUUMは時間がかかる場合があります...")
    try:
        # データベースサイズを確認
        import os
        db_size_before = os.path.getsize(DATABASE_PATH) / (1024 * 1024)  # MB
        print(f"実行前のDBサイズ: {db_size_before:.2f} MB")

        cursor.execute("VACUUM")
        conn.commit()

        db_size_after = os.path.getsize(DATABASE_PATH) / (1024 * 1024)  # MB
        saved_space = db_size_before - db_size_after
        print(f"実行後のDBサイズ: {db_size_after:.2f} MB")
        if saved_space > 0:
            print(f"✓ VACUUM完了（{saved_space:.2f} MB削減）")
        else:
            print(f"✓ VACUUM完了")
        print("  - 断片化が解消されました")
        print("  - ディスク使用量が最適化されました")
    except Exception as e:
        print(f"⚠ VACUUM実行エラー: {e}")
        print("  - VACUUMはスキップされましたが、他の最適化は有効です")
    print()

    # 8. ANALYZE実行（統計情報更新）
    print("[8] ANALYZE実行（統計情報更新）")
    print("-" * 80)
    cursor.execute("ANALYZE")
    conn.commit()
    print("✓ ANALYZE完了")
    print("  - クエリオプティマイザの統計情報が更新されました")
    print("  - クエリ実行計画が最適化されます")
    print()

    # 9. 最適化後の設定確認
    print("[9] 最適化後の設定")
    print("-" * 80)
    cursor.execute("PRAGMA journal_mode")
    print(f"ジャーナルモード: {cursor.fetchone()[0]}")
    cursor.execute("PRAGMA synchronous")
    print(f"同期モード: {cursor.fetchone()[0]}")
    cursor.execute("PRAGMA cache_size")
    print(f"キャッシュサイズ: {cursor.fetchone()[0]} pages")
    print()

    # 接続を閉じる
    cursor.close()
    conn.close()

    print("=" * 80)
    print("✅ データベース最適化が完了しました")
    print("=" * 80)
    print()
    print("次回以降のアプリケーション起動時から最適化設定が有効になります。")
    print()
    print("推奨事項:")
    print("1. 定期的に（月次）VACUUMとANALYZEを実行してください")
    print("2. 大量データ投入前にWALモードが有効か確認してください")
    print("3. データベースのバックアップを定期的に取得してください")
    print()

if __name__ == '__main__':
    try:
        optimize_database()
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ エラーが発生しました: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
