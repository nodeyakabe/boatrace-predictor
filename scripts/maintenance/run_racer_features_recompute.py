"""
racer_features / racer_venue_features 再生成スクリプト
- 手動実行: python scripts/maintenance/run_racer_features_recompute.py
- スケジューラーからも呼び出し可能（recompute_racer_features()関数）
"""
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.features.precompute_features import FeaturePrecomputer

# 手動実行時の固定値（スケジューラー呼び出し時は動的日付を使用）
_MANUAL_START_DATE = '2024-07-01'
BATCH_SIZE = 100


def recompute_racer_features(start_date: str = None, end_date: str = None) -> bool:
    """
    racer_features / racer_venue_features を再計算する。
    スケジューラーや外部スクリプトから呼び出す際はこの関数を使用。

    Args:
        start_date: 開始日 (YYYY-MM-DD)。Noneの場合は2年前から。
        end_date:   終了日 (YYYY-MM-DD)。Noneの場合は本日。

    Returns:
        bool: 正常完了でTrue
    """
    today = datetime.now().strftime('%Y-%m-%d')
    if end_date is None:
        end_date = today
    if start_date is None:
        two_years_ago = (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d')
        start_date = two_years_ago

    pc = FeaturePrecomputer()

    print(f"{'='*60}")
    print(f"racer_features / racer_venue_features 再生成")
    print(f"期間: {start_date} ～ {end_date}  batch_size={BATCH_SIZE}")
    print(f"開始: {datetime.now()}")
    print(f"{'='*60}")

    try:
        # テーブルが未作成の場合も安全に動作するよう初回に作成
        pc.create_feature_tables()

        print(f"\n[Step 1] racer_features 生成中...")
        t0 = datetime.now()
        pc.compute_racer_features(start_date, end_date, batch_size=BATCH_SIZE)
        print(f"[Step 1] 完了: {datetime.now() - t0}")

        print(f"\n[Step 2] racer_venue_features 生成中...")
        t0 = datetime.now()
        pc.compute_venue_features(start_date, end_date, batch_size=BATCH_SIZE)
        print(f"[Step 2] 完了: {datetime.now() - t0}")

        # 完了確認
        import sqlite3
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data', 'boatrace.db')
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), MIN(race_date), MAX(race_date) FROM racer_features WHERE race_date >= ?", (start_date,))
        rf = cur.fetchone()
        cur.execute("SELECT COUNT(*), MIN(race_date), MAX(race_date) FROM racer_venue_features WHERE race_date >= ?", (start_date,))
        rvf = cur.fetchone()
        conn.close()

        print(f"\n{'='*60}")
        print(f"完了確認:")
        print(f"  racer_features       ({start_date}以降): {rf[0]:,}件  {rf[1]} ～ {rf[2]}")
        print(f"  racer_venue_features ({start_date}以降): {rvf[0]:,}件  {rvf[1]} ～ {rvf[2]}")
        print(f"全処理完了: {datetime.now()}")
        print(f"{'='*60}")
        return True

    except Exception as e:
        print(f"[ERROR] racer_features再生成エラー: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    recompute_racer_features(start_date=_MANUAL_START_DATE)


if __name__ == '__main__':
    main()
