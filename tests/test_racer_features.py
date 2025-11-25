"""
選手特徴量の動作テスト

実際のDBデータを使って特徴量計算が正しく動作するか確認
"""

import sys
sys.path.append('.')

from src.features.racer_features import RacerFeatureExtractor, extract_racer_features
import sqlite3
import pandas as pd


def main():
    print("=" * 70)
    print("選手特徴量 - 動作テスト")
    print("=" * 70)

    # 1. データベースから適当な選手情報を取得
    conn = sqlite3.connect('data/boatrace.db')

    print("\n【Step 1】テスト用の選手データを取得中...")

    query = """
    SELECT DISTINCT
        e.racer_number,
        e.racer_name,
        e.motor_number,
        rc.race_date,
        rc.venue_code
    FROM entries e
    JOIN races rc ON e.race_id = rc.id
    WHERE e.racer_number IS NOT NULL
      AND e.motor_number IS NOT NULL
      AND rc.race_date >= '2024-01-01'
    ORDER BY rc.race_date DESC
    LIMIT 5
    """

    df_test = pd.read_sql_query(query, conn)
    print(f"テスト用選手数: {len(df_test)}名")
    print(df_test.to_string(index=False))

    # 2. 各選手の特徴量を計算
    print("\n" + "=" * 70)
    print("【Step 2】特徴量計算実行")
    print("=" * 70)

    extractor = RacerFeatureExtractor()

    for idx, row in df_test.iterrows():
        racer_number = row['racer_number']
        racer_name = row['racer_name']
        motor_number = row['motor_number']
        race_date = row['race_date']
        venue_code = row['venue_code']

        print(f"\n【選手 {idx + 1}/{len(df_test)}】{racer_name} (登録番号: {racer_number})")
        print(f"  レース日: {race_date}, 会場: {venue_code}, モーター: {motor_number}")

        # 特徴量抽出
        features = extractor.extract_all_features(
            racer_number=racer_number,
            motor_number=motor_number,
            race_date=race_date,
            conn=conn
        )

        print("\n  ■ 直近着順系:")
        print(f"    - recent_avg_rank_3  : {features['recent_avg_rank_3']:.3f}")
        print(f"    - recent_avg_rank_5  : {features['recent_avg_rank_5']:.3f}")
        print(f"    - recent_avg_rank_10 : {features['recent_avg_rank_10']:.3f}")

        print("\n  ■ 直近勝率系:")
        print(f"    - recent_win_rate_3  : {features['recent_win_rate_3']:.3f} ({features['recent_win_rate_3']*100:.1f}%)")
        print(f"    - recent_win_rate_5  : {features['recent_win_rate_5']:.3f} ({features['recent_win_rate_5']*100:.1f}%)")
        print(f"    - recent_win_rate_10 : {features['recent_win_rate_10']:.3f} ({features['recent_win_rate_10']*100:.1f}%)")

        print("\n  ■ モーター性能:")
        print(f"    - motor_recent_2rate_diff: {features['motor_recent_2rate_diff']:+.3f}")
        print(f"      (正 = モーター良, 負 = モーター悪)")

    # 3. 統計情報
    print("\n" + "=" * 70)
    print("【Step 3】特徴量の統計情報")
    print("=" * 70)

    all_features = []
    for idx, row in df_test.iterrows():
        features = extractor.extract_all_features(
            racer_number=row['racer_number'],
            motor_number=row['motor_number'],
            race_date=row['race_date'],
            conn=conn
        )
        all_features.append(features)

    df_features = pd.DataFrame(all_features)

    print("\n統計サマリー:")
    print(df_features.describe().to_string())

    # 4. 関数形式のテスト
    print("\n" + "=" * 70)
    print("【Step 4】便利関数のテスト")
    print("=" * 70)

    test_row = df_test.iloc[0]
    features_func = extract_racer_features(
        racer_number=test_row['racer_number'],
        motor_number=test_row['motor_number'],
        race_date=test_row['race_date']
    )

    print(f"\n選手: {test_row['racer_name']} (関数形式で取得)")
    print(f"  recent_avg_rank_5: {features_func['recent_avg_rank_5']:.3f}")
    print(f"  recent_win_rate_5: {features_func['recent_win_rate_5']:.3f}")

    # 5. 完了
    conn.close()

    print("\n" + "=" * 70)
    print("全てのテストが完了しました")
    print("=" * 70)
    print("\n【成功】選手特徴量の計算が正常に動作しています。")
    print("\n【次のステップ】")
    print("  1. Stage2モデル (model_trainer.py) への特徴量統合")
    print("  2. モデル再学習")
    print("  3. バックテストでのROI検証")


if __name__ == "__main__":
    main()
