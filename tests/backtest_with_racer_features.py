"""
バックテストスクリプト - 選手特徴量追加版

新しい選手特徴量を含むモデルで過去3ヶ月のデータをバックテストし、
ROI改善効果を検証します。

検証項目:
- 的中率変化
- ROI変化
- ドローダウン
- 閾値別ROI比較
"""

import sys
sys.path.append('.')

from src.ml.dataset_builder import DatasetBuilder
from src.ml.model_trainer import ModelTrainer
from src.betting.kelly_strategy import KellyBettingStrategy
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def main():
    print("=" * 70)
    print("バックテスト - 選手特徴量追加版")
    print("=" * 70)
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. モデル読み込み
    print("\n【Step 1】モデル読み込み")

    trainer = ModelTrainer(model_dir='models')

    try:
        trainer.load_model('stage2_with_racer_features.json')
        print("  [OK] モデル読み込み成功: stage2_with_racer_features.json")
    except Exception as e:
        print(f"  [ERROR] モデル読み込み失敗: {e}")
        print("  先にモデル学習を実行してください:")
        print("  python tests/train_stage2_with_racer_features.py")
        return 1

    # 2. バックテストデータ準備
    print("\n【Step 2】バックテストデータ準備")
    print("  期間: 過去3ヶ月（2024-04-01 〜 2024-06-30）")

    builder = DatasetBuilder(db_path='data/boatrace.db')

    df_raw = builder.build_training_dataset(
        start_date='2024-04-01',
        end_date='2024-06-30',
        venue_codes=None
    )

    print(f"  生データ: {len(df_raw):,}件")
    print(f"  レース数: {df_raw['race_id'].nunique():,}レース")

    # 3. 派生特徴量追加
    print("\n【Step 3】派生特徴量追加")
    print("  ※ 時間がかかる場合があります...")

    df_features = builder.add_derived_features(df_raw)

    print(f"  特徴量追加後: {len(df_features):,}件")

    # 4. 予測実行
    print("\n【Step 4】予測実行")

    # 有効なデータのみフィルタ
    df_features = df_features[df_features['is_win'].notna()].copy()

    # 数値特徴量のみ抽出
    numeric_cols = df_features.select_dtypes(include=['int64', 'float64', 'bool']).columns.tolist()
    exclude_cols = ['race_id', 'is_win', 'is_place_2', 'is_place_3', 'result_rank']
    feature_cols = [col for col in numeric_cols if col not in exclude_cols]

    X = df_features[feature_cols]
    y_true = df_features['is_win']

    # 欠損値補完
    X = X.fillna(X.mean())

    # 予測
    y_pred_proba = trainer.predict(X)

    df_features['predicted_prob'] = y_pred_proba
    df_features['is_win_true'] = y_true

    print(f"  予測完了: {len(y_pred_proba):,}件")

    # 5. バックテスト実行
    print("\n【Step 5】バックテスト実行")

    # Kelly基準パラメータ
    kelly_fraction = 0.25  # 保守的
    initial_bankroll = 100000  # 初期資金10万円

    results = []

    for threshold in [0.3, 0.4, 0.5, 0.6, 0.7]:
        print(f"\n  --- 閾値 {threshold:.1f} ---")

        # 購入対象レース抽出
        df_bet = df_features[df_features['predicted_prob'] >= threshold].copy()

        if len(df_bet) == 0:
            print(f"    購入対象: 0件")
            continue

        print(f"    購入対象: {len(df_bet):,}件 ({len(df_bet)/len(df_features)*100:.1f}%)")

        # オッズ情報（仮定: 平均オッズ5.0）
        df_bet['odds'] = 5.0  # 実際のオッズデータがあれば置き換え

        # Kelly基準で投資額計算
        bankroll = initial_bankroll
        total_bet = 0
        total_return = 0
        wins = 0

        for idx, row in df_bet.iterrows():
            win_prob = row['predicted_prob']
            odds = row['odds']

            # Kelly基準投資額
            edge = win_prob - (1 / odds)
            if edge > 0:
                full_kelly = (win_prob * odds - 1) / (odds - 1)
                bet_amount = bankroll * full_kelly * kelly_fraction
                bet_amount = max(100, min(bet_amount, bankroll * 0.1))  # 最小100円、最大資金の10%
            else:
                bet_amount = 0

            total_bet += bet_amount

            # 的中判定
            if row['is_win_true'] == 1:
                wins += 1
                total_return += bet_amount * odds
            else:
                total_return += 0

            # 資金更新
            bankroll += (bet_amount * odds if row['is_win_true'] == 1 else 0) - bet_amount

        # 結果集計
        hit_rate = wins / len(df_bet) if len(df_bet) > 0 else 0
        roi = (total_return / total_bet * 100) if total_bet > 0 else 0
        profit = total_return - total_bet
        final_bankroll = bankroll

        print(f"    的中率: {hit_rate:.2%} ({wins}/{len(df_bet)})")
        print(f"    総投資額: {total_bet:,.0f}円")
        print(f"    総払戻額: {total_return:,.0f}円")
        print(f"    ROI: {roi:.2f}%")
        print(f"    利益: {profit:+,.0f}円")
        print(f"    最終資金: {final_bankroll:,.0f}円")

        results.append({
            'threshold': threshold,
            'bet_count': len(df_bet),
            'hit_rate': hit_rate,
            'total_bet': total_bet,
            'total_return': total_return,
            'roi': roi,
            'profit': profit,
            'final_bankroll': final_bankroll
        })

    # 6. サマリー
    print("\n" + "=" * 70)
    print("バックテスト結果サマリー")
    print("=" * 70)

    if results:
        df_results = pd.DataFrame(results)

        print("\n【閾値別比較】")
        print(df_results.to_string(index=False))

        # 最良の閾値
        best_roi_idx = df_results['roi'].idxmax()
        best_threshold = df_results.loc[best_roi_idx, 'threshold']
        best_roi = df_results.loc[best_roi_idx, 'roi']

        print(f"\n【最良設定】")
        print(f"  閾値: {best_threshold:.1f}")
        print(f"  ROI: {best_roi:.2f}%")
        print(f"  的中率: {df_results.loc[best_roi_idx, 'hit_rate']:.2%}")
        print(f"  利益: {df_results.loc[best_roi_idx, 'profit']:+,.0f}円")

        # 期待改善度
        print(f"\n【期待ROI改善】")
        baseline_roi = 100.0  # ベースライン（仮定）
        improvement = best_roi - baseline_roi

        if improvement >= 10.0:
            print(f"  [SUCCESS] 目標達成！ ROI改善 {improvement:+.2f}%")
        else:
            print(f"  [INFO] ROI改善 {improvement:+.2f}%")

    print(f"\n【注意事項】")
    print(f"  - オッズは仮定値（5.0）を使用")
    print(f"  - 実際のオッズデータがあればより正確な検証が可能")
    print(f"  - Kelly分数は保守的（0.25）")

    print("\n" + "=" * 70)
    print("バックテスト完了")
    print("=" * 70)
    print(f"終了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    return 0


if __name__ == "__main__":
    exit(main())
