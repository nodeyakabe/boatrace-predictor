"""
racer_features / racer_venue_features 再生成スクリプト
対象: 2024-07-01 ～ 2026-02-26
"""
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.features.precompute_features import FeaturePrecomputer

START_DATE = '2024-07-01'
END_DATE   = '2026-02-26'
BATCH_SIZE = 100

def main():
    pc = FeaturePrecomputer()

    print(f"{'='*60}")
    print(f"racer_features / racer_venue_features 再生成")
    print(f"期間: {START_DATE} ～ {END_DATE}  batch_size={BATCH_SIZE}")
    print(f"開始: {datetime.now()}")
    print(f"{'='*60}")

    # Step 1: racer_features
    print(f"\n[Step 1] racer_features 生成中...")
    t0 = datetime.now()
    pc.compute_racer_features(START_DATE, END_DATE, batch_size=BATCH_SIZE)
    print(f"[Step 1] 完了: {datetime.now() - t0}")

    # Step 2: racer_venue_features
    print(f"\n[Step 2] racer_venue_features 生成中...")
    t0 = datetime.now()
    pc.compute_venue_features(START_DATE, END_DATE, batch_size=BATCH_SIZE)
    print(f"[Step 2] 完了: {datetime.now() - t0}")

    # 完了確認
    import sqlite3
    conn = sqlite3.connect(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data', 'boatrace.db'))
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), MIN(race_date), MAX(race_date) FROM racer_features WHERE race_date >= '2024-07-01'")
    rf = cur.fetchone()
    cur.execute("SELECT COUNT(*), MIN(race_date), MAX(race_date) FROM racer_venue_features WHERE race_date >= '2024-07-01'")
    rvf = cur.fetchone()
    conn.close()

    print(f"\n{'='*60}")
    print(f"完了確認:")
    print(f"  racer_features       (2024-07以降): {rf[0]:,}件  {rf[1]} ～ {rf[2]}")
    print(f"  racer_venue_features (2024-07以降): {rvf[0]:,}件  {rvf[1]} ～ {rvf[2]}")
    print(f"全処理完了: {datetime.now()}")
    print(f"{'='*60}")

if __name__ == '__main__':
    main()
