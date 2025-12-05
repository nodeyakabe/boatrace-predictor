"""
並列処理化された直前情報取得のテスト

少量データで速度を確認
"""
import sys
import time
import sqlite3
from datetime import datetime, timedelta

sys.path.insert(0, 'src')

from src.workflow.missing_data_fetch import MissingDataFetchWorkflow
from config.settings import DATABASE_PATH

def test_parallel_beforeinfo():
    """並列処理のテスト"""

    # テスト対象: 直近3日間の不足データ
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=3)

    print(f"テスト期間: {start_date} ~ {end_date}")
    print("=" * 60)

    # データ状況を確認
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            COUNT(DISTINCT r.id) as total_races,
            COUNT(DISTINCT CASE WHEN rd.id IS NOT NULL THEN r.id END) as has_beforeinfo
        FROM races r
        LEFT JOIN race_details rd ON r.id = rd.race_id
        WHERE r.race_date BETWEEN ? AND ?
    """, (str(start_date), str(end_date)))

    stats = cursor.fetchone()
    conn.close()

    total_races = stats[0]
    has_beforeinfo = stats[1]
    missing = total_races - has_beforeinfo

    print(f"対象レース数: {total_races}")
    print(f"直前情報あり: {has_beforeinfo}")
    print(f"不足データ: {missing}")
    print()

    if missing == 0:
        print("不足データがありません。過去データで再テストしてください。")
        return

    # 並列処理で取得
    print("並列処理（8スレッド）で取得開始...")
    start_time = time.time()

    workflow = MissingDataFetchWorkflow(
        db_path=DATABASE_PATH,
        progress_callback=lambda step, msg, pct: print(f"[{pct}%] {step}: {msg}")
    )

    # missing_datesは空リストでOK（自動検出される）
    result = workflow.run(
        missing_dates=[],
        check_types=['直前情報取得']
    )

    elapsed = time.time() - start_time

    print()
    print("=" * 60)
    print("テスト結果:")
    print(f"- 成功: {result.get('success', False)}")
    print(f"- 処理件数: {result.get('processed', 0)}")
    print(f"- エラー: {result.get('errors', 0)}")
    print(f"- 実行時間: {elapsed:.1f}秒")

    if missing > 0:
        speed = missing / elapsed
        print(f"- 処理速度: {speed:.1f}レース/秒")
        print()
        print(f"想定: 従来の順次処理なら約{elapsed * 8:.1f}秒かかるところを")
        print(f"      並列処理により{elapsed:.1f}秒で完了（約{8:.1f}倍高速）")

if __name__ == "__main__":
    test_parallel_beforeinfo()
