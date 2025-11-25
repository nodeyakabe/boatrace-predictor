"""
条件付き着順予測モデルの学習パイプライン
Phase 2.1の核心部分を実際のデータで学習
"""
import sys
import os
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.ml.conditional_rank_model import ConditionalRankModel
from src.features.interaction_features import InteractionFeatureGenerator
from src.features.equipment_embedding import EquipmentEmbedding


def load_training_data(db_path: str, start_date: str, end_date: str) -> pd.DataFrame:
    """学習データを読み込み"""
    print(f"データ読み込み: {start_date} ~ {end_date}")

    with sqlite3.connect(db_path) as conn:
        query = """
            SELECT
                r.id as race_id,
                r.race_date,
                r.venue_code,
                r.race_number,
                e.pit_number,
                e.racer_number,
                e.racer_rank,
                e.win_rate,
                e.second_rate,
                e.third_rate,
                e.motor_number,
                e.boat_number,
                COALESCE(e.motor_second_rate, 0) as motor_2nd_rate,
                COALESCE(e.motor_third_rate, 0) as motor_3rd_rate,
                COALESCE(e.boat_second_rate, 0) as boat_2nd_rate,
                COALESCE(e.boat_third_rate, 0) as boat_3rd_rate,
                COALESCE(e.racer_weight, 52) as weight,
                COALESCE(e.avg_st, 0.15) as avg_st,
                COALESCE(e.local_win_rate, 0) as local_win_rate,
                res.rank as result_rank
            FROM races r
            JOIN entries e ON r.id = e.race_id
            JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
            WHERE r.race_date BETWEEN ? AND ?
                AND res.rank IN ('1', '2', '3', '4', '5', '6')
            ORDER BY r.race_date, r.id, e.pit_number
        """

        df = pd.read_sql_query(query, conn, params=(start_date, end_date))

    print(f"  読み込み完了: {len(df)}行")
    return df


def prepare_race_features(df: pd.DataFrame) -> pd.DataFrame:
    """レース単位の特徴量を準備"""
    print("特徴量準備中...")

    # 級別をスコアに変換
    rank_map = {'A1': 4, 'A2': 3, 'B1': 2, 'B2': 1}
    df['racer_rank_score'] = df['racer_rank'].map(rank_map).fillna(2)

    # 基本特徴量（学習に使用するカラムのみ）
    feature_cols = [
        'race_id',  # レースID（グループ化用）
        'pit_number',  # 艇番（識別用）
        'win_rate',
        'second_rate',
        'third_rate',
        'motor_2nd_rate',
        'motor_3rd_rate',
        'boat_2nd_rate',
        'boat_3rd_rate',
        'weight',
        'avg_st',
        'local_win_rate',
        'racer_rank_score',
    ]

    # 欠損値処理
    for col in feature_cols:
        if col in df.columns and col not in ['race_id', 'pit_number']:
            df[col] = df[col].fillna(df[col].median() if df[col].dtype in ['float64', 'int64'] else 0)

    # 結果をintに変換し、カラム名を'rank'に変更（モデルが期待する形式）
    df['rank'] = df['result_rank'].astype(int)

    # 必要なカラムのみを保持
    result_df = df[feature_cols + ['rank']].copy()

    print(f"  特徴量数: {len(feature_cols) - 2}")  # race_idとpit_numberを除く
    return result_df


def train_model(train_df: pd.DataFrame, valid_df: pd.DataFrame = None):
    """条件付きモデルを学習"""
    print("\n" + "=" * 60)
    print("条件付き着順予測モデルの学習")
    print("=" * 60)

    model = ConditionalRankModel(model_dir='models')

    # XGBoostパラメータ
    params = {
        'max_depth': 6,
        'learning_rate': 0.05,
        'n_estimators': 200,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'random_state': 42,
        'eval_metric': 'auc',
    }

    # 学習実行
    results = model.train(train_df, valid_df, params)

    print("\n=== 学習結果 ===")
    for key, value in results.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.4f}")
        else:
            print(f"  {key}: {value}")

    # モデル保存
    model.save('conditional_rank_v1')

    return model, results


def evaluate_model(model: ConditionalRankModel, test_df: pd.DataFrame):
    """モデルを評価"""
    print("\n" + "=" * 60)
    print("モデル評価")
    print("=" * 60)

    # レースごとにグループ化
    race_ids = test_df['race_id'].unique()
    print(f"評価レース数: {len(race_ids)}")

    # サンプリング（時間短縮のため）
    if len(race_ids) > 50:
        np.random.seed(42)
        race_ids = np.random.choice(race_ids, 50, replace=False)
        print(f"サンプリング後: {len(race_ids)}レース")

    top1_correct = 0
    top3_correct = 0
    trifecta_correct = 0

    for race_id in race_ids:
        race_data = test_df[test_df['race_id'] == race_id].copy()

        if len(race_data) != 6:
            continue

        # 特徴量準備（pit_numberとrank以外を使用）
        feature_cols = [col for col in race_data.columns if col not in ['race_id', 'rank']]

        try:
            # 三連単確率を予測
            race_features = race_data[feature_cols].copy()
            trifecta_probs = model.predict_trifecta_probabilities(race_features)

            if not trifecta_probs:
                continue

            # 上位予測
            top_combo = max(trifecta_probs.items(), key=lambda x: x[1])[0]

            # 実際の結果
            actual_ranks = race_data.sort_values('rank')
            actual_combo = f"{int(actual_ranks.iloc[0]['pit_number'])}-{int(actual_ranks.iloc[1]['pit_number'])}-{int(actual_ranks.iloc[2]['pit_number'])}"

            # 1着予測
            pred_1st = int(top_combo.split('-')[0])
            actual_1st = int(actual_combo.split('-')[0])

            if pred_1st == actual_1st:
                top1_correct += 1

            # 3着以内予測（Top3に実際の1着が含まれるか）
            top3_combos = sorted(trifecta_probs.items(), key=lambda x: x[1], reverse=True)[:3]
            pred_1st_candidates = set(int(c[0].split('-')[0]) for c in top3_combos)

            if actual_1st in pred_1st_candidates:
                top3_correct += 1

            # 三連単的中
            if top_combo == actual_combo:
                trifecta_correct += 1

        except Exception as e:
            if race_id == race_ids[0]:  # 最初のエラーのみ表示
                print(f"  予測エラー: {e}")
            continue

    total_races = len(race_ids)
    print(f"\n評価結果:")
    print(f"  1着予測精度: {top1_correct/total_races:.1%} ({top1_correct}/{total_races})")
    print(f"  1着Top3含有率: {top3_correct/total_races:.1%} ({top3_correct}/{total_races})")
    print(f"  三連単的中率: {trifecta_correct/total_races:.1%} ({trifecta_correct}/{total_races})")

    # 理論値との比較
    print(f"\n理論値比較:")
    print(f"  ランダム1着予測: 16.7%")
    print(f"  ランダム三連単: 0.83%")
    print(f"  改善倍率(1着): {(top1_correct/total_races)/0.167:.2f}x")
    print(f"  改善倍率(三連単): {(trifecta_correct/total_races)/0.0083:.2f}x")

    return {
        'top1_accuracy': top1_correct / total_races,
        'top3_hit_rate': top3_correct / total_races,
        'trifecta_accuracy': trifecta_correct / total_races,
    }


def main():
    """メイン実行"""
    print("=" * 60)
    print("条件付き着順予測モデル 学習パイプライン")
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    db_path = "data/boatrace.db"

    if not os.path.exists(db_path):
        print(f"[ERROR] DBファイルが見つかりません: {db_path}")
        return

    # データ期間設定
    # 学習: 2020-01-01 ~ 2024-12-31
    # 検証: 2025-01-01 ~ 2025-06-30
    # テスト: 2025-07-01 ~ 2025-10-31

    train_start = "2020-01-01"
    train_end = "2024-12-31"
    valid_start = "2025-01-01"
    valid_end = "2025-06-30"
    test_start = "2025-07-01"
    test_end = "2025-10-31"

    # データ読み込み
    train_df = load_training_data(db_path, train_start, train_end)
    valid_df = load_training_data(db_path, valid_start, valid_end)
    test_df = load_training_data(db_path, test_start, test_end)

    # 特徴量準備
    train_df = prepare_race_features(train_df)
    valid_df = prepare_race_features(valid_df)
    test_df = prepare_race_features(test_df)

    print(f"\nデータセットサイズ:")
    print(f"  学習: {len(train_df)}行 ({len(train_df)//6}レース)")
    print(f"  検証: {len(valid_df)}行 ({len(valid_df)//6}レース)")
    print(f"  テスト: {len(test_df)}行 ({len(test_df)//6}レース)")

    # モデル学習
    model, train_results = train_model(train_df, valid_df)

    # テストセットで評価
    test_results = evaluate_model(model, test_df)

    print("\n" + "=" * 60)
    print("学習完了！")
    print("=" * 60)

    # 結果を保存
    results_summary = {
        'train_results': train_results,
        'test_results': test_results,
        'timestamp': datetime.now().isoformat(),
        'data_info': {
            'train_period': f"{train_start} ~ {train_end}",
            'valid_period': f"{valid_start} ~ {valid_end}",
            'test_period': f"{test_start} ~ {test_end}",
        }
    }

    import json
    with open('models/training_results.json', 'w', encoding='utf-8') as f:
        # numpy型をfloatに変換
        def convert(obj):
            if isinstance(obj, np.floating):
                return float(obj)
            elif isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, dict):
                return {k: convert(v) for k, v in obj.items()}
            return obj

        json.dump(convert(results_summary), f, indent=2, ensure_ascii=False)

    print(f"結果を models/training_results.json に保存しました")


if __name__ == "__main__":
    main()
