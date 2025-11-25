"""
欠損特徴量を補完するスクリプト

racer_features, racer_venue_featuresテーブルの欠損期間を検出し、
その期間だけを再計算して補完する
"""

import sqlite3
from datetime import datetime, timedelta
from src.features.precompute_features import FeaturePrecomputer


def fill_missing_dates():
    """欠損日付を補完"""

    print("=" * 70)
    print("欠損特徴量補完スクリプト")
    print("=" * 70)

    db_path = "data/boatrace.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 目標期間
    target_start = "2024-04-01"
    target_end = "2024-06-30"

    print(f"\n目標期間: {target_start} 〜 {target_end}")

    # racer_features の状況確認
    print("\n[1] racer_features 状況確認")
    cursor.execute("SELECT MIN(race_date), MAX(race_date), COUNT(*) FROM racer_features")
    rf_min, rf_max, rf_count = cursor.fetchone()
    print(f"  既存データ: {rf_min} 〜 {rf_max} ({rf_count:,}件)")

    # racer_venue_features の状況確認
    print("\n[2] racer_venue_features 状況確認")
    cursor.execute("SELECT MIN(race_date), MAX(race_date), COUNT(*) FROM racer_venue_features")
    rvf_result = cursor.fetchone()
    if rvf_result[0]:
        rvf_min, rvf_max, rvf_count = rvf_result
        print(f"  既存データ: {rvf_min} 〜 {rvf_max} ({rvf_count:,}件)")
    else:
        rvf_min, rvf_max, rvf_count = None, None, 0
        print(f"  既存データ: なし")

    conn.close()

    # 補完が必要な期間を特定
    precomputer = FeaturePrecomputer(db_path=db_path)

    # racer_features の補完
    if rf_min and rf_min > target_start:
        print(f"\n[3] racer_features 前方補完: {target_start} 〜 {rf_min}")
        # rf_minの前日まで計算
        end_date_obj = datetime.strptime(rf_min, "%Y-%m-%d") - timedelta(days=1)
        end_date = end_date_obj.strftime("%Y-%m-%d")

        precomputer.compute_racer_features(
            start_date=target_start,
            end_date=end_date,
            batch_size=500
        )

    # racer_venue_features の補完
    if not rvf_min or rvf_min > target_start:
        print(f"\n[4] racer_venue_features 前方補完: {target_start} 〜 {rvf_min or target_end}")
        if rvf_min:
            end_date_obj = datetime.strptime(rvf_min, "%Y-%m-%d") - timedelta(days=1)
            end_date = end_date_obj.strftime("%Y-%m-%d")
        else:
            end_date = target_end

        precomputer.compute_venue_features(
            start_date=target_start,
            end_date=end_date,
            batch_size=500
        )

    # racer_venue_features の後方補完
    if rvf_max and rvf_max < target_end:
        print(f"\n[5] racer_venue_features 後方補完: {rvf_max} 〜 {target_end}")
        start_date_obj = datetime.strptime(rvf_max, "%Y-%m-%d") + timedelta(days=1)
        start_date = start_date_obj.strftime("%Y-%m-%d")

        precomputer.compute_venue_features(
            start_date=start_date,
            end_date=target_end,
            batch_size=500
        )

    # 最終確認
    print("\n" + "=" * 70)
    print("補完完了 - 最終状況")
    print("=" * 70)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT MIN(race_date), MAX(race_date), COUNT(*) FROM racer_features")
    rf_min, rf_max, rf_count = cursor.fetchone()
    print(f"racer_features: {rf_min} 〜 {rf_max} ({rf_count:,}件)")

    cursor.execute("SELECT MIN(race_date), MAX(race_date), COUNT(*) FROM racer_venue_features")
    rvf_result = cursor.fetchone()
    if rvf_result[0]:
        rvf_min, rvf_max, rvf_count = rvf_result
        print(f"racer_venue_features: {rvf_min} 〜 {rvf_max} ({rvf_count:,}件)")
    else:
        print(f"racer_venue_features: データなし")

    conn.close()
    print("=" * 70)


if __name__ == "__main__":
    fill_missing_dates()
