"""
会場×コース特徴量のバックテスト

新規特徴量:
1. venue_course_advantage - 会場コース有利度
2. recent_course_win_rate - 直近10走のコース別成績
3. wind_course_factor - 風条件×コース調整係数
4. wave_course_factor - 波高×コース調整係数
5. racer_venue_course_combined - ベイズ推定による適性スコア
"""

import sys
sys.path.append('.')

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, log_loss, accuracy_score, precision_score, recall_score
import xgboost as xgb
import json
import warnings
warnings.filterwarnings('ignore')

from src.features.venue_course_features import VenueCourseFeatureExtractor


def load_base_data(db_path='data/boatrace.db', start_date='2024-10-01', end_date='2024-11-30'):
    """ベースデータを読み込み"""
    conn = sqlite3.connect(db_path)

    query = """
        SELECT
            r.id as race_id,
            r.race_date,
            r.venue_code,
            r.race_number,

            e.pit_number,
            e.racer_number,
            e.motor_number,
            e.win_rate,
            e.second_rate,
            e.third_rate,
            e.local_win_rate,
            e.motor_second_rate,
            e.avg_st,
            e.racer_age,
            e.racer_weight,

            rd.exhibition_time,
            rd.tilt_angle,
            rd.actual_course,
            rd.st_time,

            rc.temperature,
            rc.wind_speed,
            rc.wave_height,

            res.rank as result_rank

        FROM entries e
        JOIN races r ON e.race_id = r.id
        LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
        LEFT JOIN race_conditions rc ON e.race_id = rc.race_id
        LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
        WHERE r.race_date BETWEEN ? AND ?
            AND res.rank IS NOT NULL
            AND res.rank NOT IN ('F', 'L', 'K', '')
            AND rd.actual_course IS NOT NULL
        ORDER BY r.race_date, r.venue_code, r.race_number, e.pit_number
    """

    df = pd.read_sql_query(query, conn, params=(start_date, end_date))
    conn.close()

    df['is_win'] = (df['result_rank'] == '1').astype(int)

    return df


def compute_baseline_features(df):
    """ベースライン特徴量を計算"""
    df = df.copy()

    for col in ['win_rate', 'motor_second_rate', 'exhibition_time']:
        if col in df.columns:
            df[f'{col}_rank'] = df.groupby('race_id')[col].rank(ascending=False, method='min')

    df['is_inner'] = (df['pit_number'] == 1).astype(int)
    df['is_outer'] = (df['pit_number'] >= 5).astype(int)
    df['pit_course_diff'] = df['pit_number'] - df['actual_course'].fillna(df['pit_number'])
    df['got_inner'] = (df['actual_course'] < df['pit_number']).astype(int)

    return df


def add_venue_course_features_batch(df, db_path='data/boatrace.db'):
    """会場×コース特徴量をバッチで追加"""
    extractor = VenueCourseFeatureExtractor(db_path)
    conn = sqlite3.connect(db_path)

    new_features = []
    total = len(df)

    print(f"\n会場×コース特徴量計算中... ({total}行)")

    for idx, row in df.iterrows():
        if idx % 5000 == 0:
            print(f"  Progress: {idx}/{total} ({idx/total*100:.1f}%)")

        try:
            target_course = int(row['actual_course']) if pd.notna(row['actual_course']) else int(row['pit_number'])
            wind_speed = row['wind_speed'] if pd.notna(row['wind_speed']) else None
            wave_height = row['wave_height'] if pd.notna(row['wave_height']) else None

            features = extractor.extract_all_features(
                racer_number=str(row['racer_number']),
                venue_code=str(row['venue_code']),
                target_course=target_course,
                race_date=str(row['race_date']),
                wind_speed=wind_speed,
                wave_height=wave_height,
                conn=conn
            )
        except Exception as e:
            features = {
                'venue_course_advantage': 0.0,
                'recent_course_win_rate': 0.17,
                'recent_course_2ren_rate': 0.33,
                'recent_course_avg_rank': 3.5,
                'wind_course_factor': 0.0,
                'wave_course_factor': 0.0,
                'condition_course_factor': 0.0,
                'racer_venue_skill': 0.17,
                'racer_course_skill': 0.17,
                'racer_venue_course_skill': 0.17,
                'racer_venue_course_combined': 0.17
            }

        new_features.append(features)

    conn.close()

    df_new_features = pd.DataFrame(new_features, index=df.index)
    df = pd.concat([df, df_new_features], axis=1)

    print(f"  追加された特徴量: {len(df_new_features.columns)}個")

    return df


def prepare_features(df, feature_cols):
    """特徴量を準備"""
    X = df[feature_cols].copy()
    X = X.fillna(X.mean())
    X = X.replace([np.inf, -np.inf], 0)
    return X


def evaluate_model(y_true, y_pred, y_prob):
    """モデルを評価"""
    return {
        'auc': roc_auc_score(y_true, y_prob) if len(np.unique(y_true)) > 1 else 0,
        'accuracy': accuracy_score(y_true, y_pred),
        'precision': precision_score(y_true, y_pred, zero_division=0),
        'recall': recall_score(y_true, y_pred, zero_division=0),
        'log_loss': log_loss(y_true, y_prob) if len(np.unique(y_true)) > 1 else 0
    }


def main():
    print("=" * 70)
    print("会場×コース特徴量 効果検証バックテスト")
    print("=" * 70)
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # データロード
    print("\n【Step 1】データロード")
    df = load_base_data(start_date='2024-10-01', end_date='2024-11-30')
    print(f"  読み込みデータ: {len(df):,}行 ({df['race_id'].nunique():,}レース)")

    # ベースライン特徴量
    print("\n【Step 2】ベースライン特徴量計算")
    df = compute_baseline_features(df)

    baseline_cols = [
        'pit_number', 'win_rate', 'second_rate', 'third_rate',
        'local_win_rate', 'motor_second_rate', 'avg_st',
        'racer_age', 'racer_weight',
        'exhibition_time', 'tilt_angle', 'st_time',
        'temperature', 'wind_speed', 'wave_height',
        'win_rate_rank', 'motor_second_rate_rank', 'exhibition_time_rank',
        'is_inner', 'is_outer', 'pit_course_diff', 'got_inner'
    ]
    baseline_cols = [c for c in baseline_cols if c in df.columns]
    print(f"  ベースライン特徴量: {len(baseline_cols)}個")

    # Train/Test分割
    print("\n【Step 3】Train/Test分割")
    split_date = '2024-11-15'
    df_train = df[df['race_date'] < split_date].copy()
    df_test = df[df['race_date'] >= split_date].copy()
    print(f"  Train: {len(df_train):,}行")
    print(f"  Test: {len(df_test):,}行")

    # ベースラインモデル
    print("\n【Step 4】ベースラインモデル学習・評価")
    X_train_base = prepare_features(df_train, baseline_cols)
    X_test_base = prepare_features(df_test, baseline_cols)
    y_train = df_train['is_win']
    y_test = df_test['is_win']

    model_base = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric='auc',
        early_stopping_rounds=20
    )

    model_base.fit(X_train_base, y_train, eval_set=[(X_test_base, y_test)], verbose=False)

    y_pred_base = model_base.predict(X_test_base)
    y_prob_base = model_base.predict_proba(X_test_base)[:, 1]
    metrics_base = evaluate_model(y_test, y_pred_base, y_prob_base)

    print(f"\n  【ベースライン結果】")
    print(f"    AUC: {metrics_base['auc']:.4f}")
    print(f"    Accuracy: {metrics_base['accuracy']:.4f}")
    print(f"    Precision: {metrics_base['precision']:.4f}")
    print(f"    Recall: {metrics_base['recall']:.4f}")

    # 新規特徴量追加
    print("\n【Step 5】会場×コース特徴量追加")
    df = add_venue_course_features_batch(df)

    venue_course_cols = [
        'venue_course_advantage',
        'recent_course_win_rate', 'recent_course_2ren_rate', 'recent_course_avg_rank',
        'wind_course_factor', 'wave_course_factor', 'condition_course_factor',
        'racer_venue_skill', 'racer_course_skill',
        'racer_venue_course_skill', 'racer_venue_course_combined'
    ]
    venue_course_cols = [c for c in venue_course_cols if c in df.columns]
    print(f"  会場×コース特徴量: {len(venue_course_cols)}個")

    all_cols = baseline_cols + venue_course_cols

    # 再分割
    df_train_new = df[df['race_date'] < split_date].copy()
    df_test_new = df[df['race_date'] >= split_date].copy()

    # 新規特徴量モデル
    print("\n【Step 6】新規特徴量モデル学習・評価")
    X_train_new = prepare_features(df_train_new, all_cols)
    X_test_new = prepare_features(df_test_new, all_cols)
    y_train_new = df_train_new['is_win']
    y_test_new = df_test_new['is_win']

    model_new = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric='auc',
        early_stopping_rounds=20
    )

    model_new.fit(X_train_new, y_train_new, eval_set=[(X_test_new, y_test_new)], verbose=False)

    y_pred_new = model_new.predict(X_test_new)
    y_prob_new = model_new.predict_proba(X_test_new)[:, 1]
    metrics_new = evaluate_model(y_test_new, y_pred_new, y_prob_new)

    print(f"\n  【新規特徴量結果】")
    print(f"    AUC: {metrics_new['auc']:.4f}")
    print(f"    Accuracy: {metrics_new['accuracy']:.4f}")
    print(f"    Precision: {metrics_new['precision']:.4f}")
    print(f"    Recall: {metrics_new['recall']:.4f}")

    # 改善率
    print("\n【Step 7】改善率分析")
    auc_improvement = (metrics_new['auc'] - metrics_base['auc']) / metrics_base['auc'] * 100
    acc_improvement = (metrics_new['accuracy'] - metrics_base['accuracy']) / metrics_base['accuracy'] * 100
    recall_improvement = (metrics_new['recall'] - metrics_base['recall']) / max(metrics_base['recall'], 0.001) * 100

    print(f"\n  AUC改善率: {auc_improvement:+.2f}%")
    print(f"  Accuracy改善率: {acc_improvement:+.2f}%")
    print(f"  Recall改善率: {recall_improvement:+.2f}%")

    # 特徴量重要度
    print("\n【Step 8】特徴量重要度")
    importance = pd.DataFrame({
        'feature': all_cols,
        'importance': model_new.feature_importances_
    }).sort_values('importance', ascending=False)

    print("\n  Top 15 特徴量:")
    for idx, row in importance.head(15).iterrows():
        marker = "★" if row['feature'] in venue_course_cols else " "
        print(f"    {marker} {row['feature']}: {row['importance']:.4f}")

    # 新規特徴量の重要度
    new_importance = importance[importance['feature'].isin(venue_course_cols)]
    print(f"\n  会場×コース特徴量の重要度合計: {new_importance['importance'].sum():.4f}")

    # 結果保存
    result = {
        'timestamp': datetime.now().isoformat(),
        'baseline': metrics_base,
        'with_venue_course_features': metrics_new,
        'improvement': {
            'auc_pct': auc_improvement,
            'accuracy_pct': acc_improvement,
            'recall_pct': recall_improvement
        },
        'new_features_importance': new_importance.to_dict('records')
    }

    with open('temp/venue_course_features_backtest_result.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n結果を temp/venue_course_features_backtest_result.json に保存しました")
    print("\n" + "=" * 70)
    print(f"完了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
