"""
DatasetBuilderの統合テスト - 選手特徴量追加版

改善アドバイスに基づく選手特徴量が正しくデータセットに統合されているか確認
"""

import sys
sys.path.append('.')

from src.ml.dataset_builder import DatasetBuilder
import pandas as pd


def main():
    print("=" * 70)
    print("DatasetBuilder 統合テスト - 選手特徴量追加版")
    print("=" * 70)

    # 1. DatasetBuilder インスタンス作成
    print("\n【Step 1】DatasetBuilder インスタンス作成")
    builder = DatasetBuilder(db_path='data/boatrace.db')

    # 2. 学習データセット構築（少量でテスト）
    print("\n【Step 2】学習データセット構築（直近1週間、最大100レコード）")
    df_raw = builder.build_training_dataset(
        start_date='2024-06-01',
        end_date='2024-06-07',
        venue_codes=None  # 全会場
    )

    print(f"  生データ件数: {len(df_raw):,}件")
    print(f"  レース数: {df_raw['race_id'].nunique():,}レース")
    print(f"  カラム数: {len(df_raw.columns)}個")

    # 最初の100件に絞る（テスト高速化）
    df_raw = df_raw.head(100)
    print(f"  テスト用にサンプリング: {len(df_raw)}件")

    # 3. 派生特徴量を追加（選手特徴量を含む）
    print("\n【Step 3】派生特徴量を追加中（選手特徴量含む）...")
    print("  ※ 時間がかかる場合があります...")
    df_features = builder.add_derived_features(df_raw)

    print(f"\n  特徴量追加後の件数: {len(df_features):,}件")
    print(f"  特徴量追加後のカラム数: {len(df_features.columns)}個")

    # 4. 選手特徴量が追加されているか確認
    print("\n【Step 4】選手特徴量の確認")
    racer_feature_cols = [
        'recent_avg_rank_3',
        'recent_avg_rank_5',
        'recent_avg_rank_10',
        'recent_win_rate_3',
        'recent_win_rate_5',
        'recent_win_rate_10',
        'motor_recent_2rate_diff'
    ]

    missing_cols = [col for col in racer_feature_cols if col not in df_features.columns]
    present_cols = [col for col in racer_feature_cols if col in df_features.columns]

    print(f"\n  [OK] 追加済み特徴量 ({len(present_cols)}個):")
    for col in present_cols:
        print(f"    - {col}")

    if missing_cols:
        print(f"\n  [NG] 未追加特徴量 ({len(missing_cols)}個):")
        for col in missing_cols:
            print(f"    - {col}")
    else:
        print(f"\n  [OK] 全ての選手特徴量が正常に追加されました")

    # 5. 選手特徴量の統計情報
    print("\n【Step 5】選手特徴量の統計情報")
    if present_cols:
        print("\n統計サマリー:")
        print(df_features[present_cols].describe().to_string())

        # 欠損値確認
        print("\n欠損値:")
        for col in present_cols:
            missing_count = df_features[col].isna().sum()
            missing_pct = (missing_count / len(df_features) * 100)
            print(f"  {col}: {missing_count}件 ({missing_pct:.1f}%)")

    # 6. サンプルデータ確認
    print("\n【Step 6】サンプルデータ確認（最初の3件）")
    sample_cols = ['racer_name'] + present_cols
    sample_cols = [col for col in sample_cols if col in df_features.columns]

    if sample_cols:
        print(df_features[sample_cols].head(3).to_string(index=False))

    # 7. 全カラム一覧
    print("\n【Step 7】全カラム一覧（参考）")
    print(f"  総カラム数: {len(df_features.columns)}個\n")
    for i, col in enumerate(df_features.columns, 1):
        col_type = df_features[col].dtype
        print(f"  {i:3d}. {col:<35} ({col_type})")

    # 8. 完了
    print("\n" + "=" * 70)
    print("統合テスト完了")
    print("=" * 70)

    if missing_cols:
        print("\n【結果】[WARNING] 一部の選手特徴量が追加されませんでした")
        return 1
    else:
        print("\n【結果】[SUCCESS] 選手特徴量が正常にデータセットに統合されました")
        print("\n【次のステップ】")
        print("  1. モデル再学習 (python tests/train_stage2_with_racer_features.py)")
        print("  2. バックテストでROI検証")
        return 0


if __name__ == "__main__":
    exit(main())
