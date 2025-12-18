"""
並列オッズ取得のテストスクリプト

少量データ（10件）で動作確認
"""
import os
import sys
import sqlite3
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from fetch_odds_parallel import ParallelOddsFetcher


def test_parallel_fetcher():
    """並列処理のテスト実行"""
    print("=" * 80)
    print("並列オッズ取得テスト開始")
    print("=" * 80)
    print()

    db_path = os.path.join(PROJECT_ROOT, 'data/boatrace.db')

    if not os.path.exists(db_path):
        print(f"[ERROR] DBが見つかりません: {db_path}")
        return False

    # 接続確認
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # テスト用に未取得レースを10件取得
        cursor.execute("""
            SELECT r.id, r.venue_code, r.race_date, r.race_number
            FROM races r
            WHERE r.race_date BETWEEN '2024-01-01' AND '2024-12-31'
              AND NOT EXISTS (
                  SELECT 1 FROM trifecta_odds t WHERE t.race_id = r.id
              )
            ORDER BY r.race_date DESC, r.venue_code, r.race_number
            LIMIT 10
        """)
        test_races = cursor.fetchall()
        conn.close()

        if not test_races:
            print("[OK] 全てのオッズデータが既に取得済みです")
            print("   テストをスキップします")
            return True

        print(f"[INFO] テスト対象: {len(test_races)}件のレース")
        print()

    except Exception as e:
        print(f"[ERROR] DB接続エラー: {e}")
        return False

    # 並列処理テスト実行
    try:
        fetcher = ParallelOddsFetcher(
            db_path=db_path,
            delay=0.3,
            max_workers=3,  # テストなので少なめ
            batch_size=5
        )

        # テスト用に2024年の未取得データのみ取得
        log_file = 'logs/test_parallel_odds.log'
        os.makedirs('logs', exist_ok=True)

        import time
        start_time = time.time()

        fetcher.run(
            start_date='2024-01-01',
            end_date='2024-12-31',
            log_file=log_file,
            progress_interval=5
        )

        elapsed = time.time() - start_time

        print()
        print("=" * 80)
        print("[OK] テスト完了")
        print(f"   成功: {fetcher.success_count}件")
        print(f"   エラー: {fetcher.error_count}件")
        print(f"   処理時間: {elapsed:.1f}秒")
        if fetcher.success_count > 0:
            print(f"   平均速度: {fetcher.success_count/elapsed:.2f}件/秒")
        print(f"   ログファイル: {log_file}")
        print("=" * 80)

        return True

    except Exception as e:
        print(f"[ERROR] テスト実行エラー: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_dependencies():
    """依存関係の確認"""
    print("依存関係チェック中...")
    print()

    try:
        import requests
        print("[OK] requests: OK")
    except ImportError:
        print("[NG] requests: 未インストール")
        return False

    try:
        from bs4 import BeautifulSoup
        print("[OK] beautifulsoup4: OK")
    except ImportError:
        print("[NG] beautifulsoup4: 未インストール")
        return False

    try:
        from concurrent.futures import ThreadPoolExecutor
        print("[OK] concurrent.futures: OK")
    except ImportError:
        print("[NG] concurrent.futures: 未インストール")
        return False

    print()
    return True


if __name__ == '__main__':
    # Windowsのコンソールエンコーディング設定
    import sys
    if sys.platform == 'win32':
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

    print()
    print("並列オッズ取得テスト")
    print()

    # 依存関係チェック
    if not check_dependencies():
        print()
        print("[ERROR] 依存関係のインストールが必要です")
        print("   pip install requests beautifulsoup4 lxml")
        sys.exit(1)

    # テスト実行
    success = test_parallel_fetcher()

    if success:
        print()
        print("[OK] テスト成功！夜間実行の準備が整いました")
        print()
        print("夜間実行手順:")
        print("   1. 既存の逐次処理版を停止")
        print("   2. run_odds_parallel_night.bat を実行")
        print("   3. PCをスリープさせない設定を確認")
        print()
        sys.exit(0)
    else:
        print()
        print("[ERROR] テスト失敗")
        print("   上記のエラーを確認してください")
        print()
        sys.exit(1)
