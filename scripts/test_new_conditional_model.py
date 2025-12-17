"""
新しい条件付きモデル（conditional_rank_v2_20251215）の精度テスト

2025年のデータを使って、新モデルの精度を直接評価する
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import pandas as pd
import numpy as np
from src.ml.conditional_rank_model import ConditionalRankModel


def load_test_data(db_path: str = 'data/boatrace.db') -> pd.DataFrame:
    """2025年のテストデータを読み込み"""
    print("=== テストデータの読み込み ===")

    conn = sqlite3.connect(db_path)

    query = """
    SELECT
        r.id as race_id,
        r.race_date,
        r.venue_code,
        CAST(res.pit_number AS INTEGER) as pit_number,
        CAST(res.rank AS INTEGER) as rank,
        e.racer_number,
        e.racer_rank,
        e.win_rate,
        e.second_rate,
        e.third_rate,
        e.local_win_rate,
        e.local_second_rate,
        e.motor_second_rate,
        e.boat_second_rate,
        e.avg_st,
        rd.exhibition_time,
        rd.st_time as exhibition_st,
        rd.exhibition_course,
        rd.tilt_angle,
        rc.wind_speed,
        rc.wave_height,
        rc.temperature,
        rc.water_temperature
    FROM races r
    JOIN results res ON r.id = res.race_id
    JOIN entries e ON r.id = e.race_id AND res.pit_number = e.pit_number
    LEFT JOIN race_details rd ON r.id = rd.race_id AND res.pit_number = rd.pit_number
    LEFT JOIN race_conditions rc ON r.id = rc.race_id
    WHERE r.race_date >= '2025-01-01'
      AND r.race_date <= '2025-12-31'
      AND res.rank IS NOT NULL
      AND CAST(res.rank AS INTEGER) <= 6
    ORDER BY r.race_date, r.id, res.pit_number
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    print(f"読み込みレコード数: {len(df):,}")
    print(f"ユニークレース数: {df['race_id'].nunique():,}")

    # 欠損値の処理
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        if df[col].isnull().sum() > 0:
            df[col] = df[col].fillna(df[col].median())

    return df


def evaluate_model_accuracy(model: ConditionalRankModel, df: pd.DataFrame) -> dict:
    """モデルの着順予測精度を評価"""
    print("\n=== モデル精度評価 ===")

    results = {
        '1着': {'correct': 0, 'total': 0},
        '2着': {'correct': 0, 'total': 0},
        '3着': {'correct': 0, 'total': 0},
        '3連単': {'correct': 0, 'total': 0}
    }

    baseline_correct = 0

    # レース単位で処理
    race_ids = df['race_id'].unique()

    for i, race_id in enumerate(race_ids):
        if i % 1000 == 0:
            print(f"  処理中: {i}/{len(race_ids)} レース...")

        race_df = df[df['race_id'] == race_id]

        if len(race_df) != 6:
            continue

        # 実際の1着、2着、3着
        actual_1st = race_df[race_df['rank'] == 1]['pit_number'].iloc[0] if len(race_df[race_df['rank'] == 1]) > 0 else None
        actual_2nd = race_df[race_df['rank'] == 2]['pit_number'].iloc[0] if len(race_df[race_df['rank'] == 2]) > 0 else None
        actual_3rd = race_df[race_df['rank'] == 3]['pit_number'].iloc[0] if len(race_df[race_df['rank'] == 3]) > 0 else None

        if actual_1st is None or actual_2nd is None or actual_3rd is None:
            continue

        try:
            # 1着予測用データを準備
            X_1st, _ = model._prepare_first_place_data(race_df)

            # 特徴量を揃える
            for col in model.feature_names:
                if col not in X_1st.columns:
                    X_1st[col] = 0
            X_1st = X_1st[model.feature_names]

            # 1着確率を予測
            first_probs = model.models['first'].predict_proba(X_1st)[:, 1]
            pred_1st_idx = np.argmax(first_probs)
            pred_1st = race_df.iloc[pred_1st_idx]['pit_number']

            # 1着精度
            results['1着']['total'] += 1
            if pred_1st == actual_1st:
                results['1着']['correct'] += 1

            # ベースライン（1コース常時予測）
            if actual_1st == 1:
                baseline_correct += 1

            # 2着予測（1着確定後の残り5艇から予測）
            remaining_2nd = race_df[race_df['pit_number'] != pred_1st].copy()
            if len(remaining_2nd) == 5 and model.models['second'] is not None:
                # 2着予測用特徴量を準備
                first_features = race_df[race_df['pit_number'] == pred_1st].drop(['rank', 'race_id', 'pit_number'], axis=1, errors='ignore')
                first_features = first_features.select_dtypes(include=[np.number])

                # 候補艇の特徴量 + 1着艇の特徴量を結合
                X_2nd_list = []
                for _, row in remaining_2nd.iterrows():
                    candidate_features = row.drop(['rank', 'race_id', 'pit_number'], errors='ignore')
                    candidate_features = candidate_features[candidate_features.index.isin(first_features.columns)]
                    combined = np.concatenate([candidate_features.values, first_features.values.flatten()])
                    X_2nd_list.append(combined)

                # 特徴量名を確認
                if len(X_2nd_list) > 0 and len(model.second_feature_names) > 0:
                    try:
                        X_2nd = pd.DataFrame(X_2nd_list, columns=model.second_feature_names[:len(X_2nd_list[0])])
                        for col in model.second_feature_names:
                            if col not in X_2nd.columns:
                                X_2nd[col] = 0
                        X_2nd = X_2nd[model.second_feature_names]

                        second_probs = model.models['second'].predict_proba(X_2nd)[:, 1]
                        pred_2nd_idx = np.argmax(second_probs)
                        pred_2nd = remaining_2nd.iloc[pred_2nd_idx]['pit_number']

                        results['2着']['total'] += 1
                        if pred_2nd == actual_2nd:
                            results['2着']['correct'] += 1

                        # 3着予測（1着・2着確定後の残り4艇から予測）
                        remaining_3rd = remaining_2nd[remaining_2nd['pit_number'] != pred_2nd].copy()
                        if len(remaining_3rd) == 4 and model.models['third'] is not None:
                            second_features = remaining_2nd[remaining_2nd['pit_number'] == pred_2nd].drop(['rank', 'race_id', 'pit_number'], axis=1, errors='ignore')
                            second_features = second_features.select_dtypes(include=[np.number])

                            X_3rd_list = []
                            for _, row in remaining_3rd.iterrows():
                                candidate_features = row.drop(['rank', 'race_id', 'pit_number'], errors='ignore')
                                candidate_features = candidate_features[candidate_features.index.isin(first_features.columns)]
                                combined = np.concatenate([candidate_features.values, first_features.values.flatten(), second_features.values.flatten()])
                                X_3rd_list.append(combined)

                            if len(X_3rd_list) > 0 and len(model.third_feature_names) > 0:
                                try:
                                    X_3rd = pd.DataFrame(X_3rd_list, columns=model.third_feature_names[:len(X_3rd_list[0])])
                                    for col in model.third_feature_names:
                                        if col not in X_3rd.columns:
                                            X_3rd[col] = 0
                                    X_3rd = X_3rd[model.third_feature_names]

                                    third_probs = model.models['third'].predict_proba(X_3rd)[:, 1]
                                    pred_3rd_idx = np.argmax(third_probs)
                                    pred_3rd = remaining_3rd.iloc[pred_3rd_idx]['pit_number']

                                    results['3着']['total'] += 1
                                    if pred_3rd == actual_3rd:
                                        results['3着']['correct'] += 1

                                    # 3連単精度
                                    results['3連単']['total'] += 1
                                    if pred_1st == actual_1st and pred_2nd == actual_2nd and pred_3rd == actual_3rd:
                                        results['3連単']['correct'] += 1
                                except:
                                    pass
                    except:
                        pass

        except Exception as e:
            continue

    # 精度計算
    print("\n=== 結果 ===")
    for key, val in results.items():
        if val['total'] > 0:
            accuracy = val['correct'] / val['total'] * 100
            print(f"  {key}精度: {accuracy:.2f}% ({val['correct']:,}/{val['total']:,})")

    # ベースラインとの比較
    if results['1着']['total'] > 0:
        baseline_acc = baseline_correct / results['1着']['total'] * 100
        system_acc = results['1着']['correct'] / results['1着']['total'] * 100
        print(f"\n  ベースライン（1コース常時予測）: {baseline_acc:.2f}%")
        print(f"  付加価値: {system_acc - baseline_acc:+.2f}pt")

    return results


def main():
    print("=" * 70)
    print("新条件付きモデル（conditional_rank_v2_20251215）精度テスト")
    print("=" * 70)

    # モデル読み込み
    print("\n=== モデル読み込み ===")
    model = ConditionalRankModel()
    model.load('conditional_rank_v2_20251215')
    print(f"  1着モデル特徴量数: {len(model.feature_names)}")
    print(f"  2着モデル特徴量数: {len(model.second_feature_names)}")
    print(f"  3着モデル特徴量数: {len(model.third_feature_names)}")

    # テストデータ読み込み
    df = load_test_data()

    # 精度評価
    results = evaluate_model_accuracy(model, df)

    print("\n" + "=" * 70)
    print("完了")


if __name__ == '__main__':
    main()
