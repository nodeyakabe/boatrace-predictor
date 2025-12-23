#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""スムージング強度のチューニング"""
import sys
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import sqlite3
import pandas as pd
import numpy as np
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
import xgboost as xgb
from sklearn.metrics import roc_auc_score
import warnings
warnings.filterwarnings('ignore')


def bayesian_smoothing(observed_rate, sample_count, prior_rate, prior_strength):
    return (observed_rate * sample_count + prior_rate * prior_strength) / (sample_count + prior_strength)


def test_smoothing(prior_strength, df_train, df_test, y_train, racer_stats, motor_stats, course_stats_raw, global_stats):
    """特定のスムージング強度でテスト"""

    # スムージング適用
    course_stats = course_stats_raw.copy()
    course_stats['course_win_rate'] = course_stats.apply(
        lambda row: bayesian_smoothing(row['course_win_raw'], row['course_count'],
                                       global_stats['global_win_rate'], prior_strength), axis=1)
    course_stats['course_2ren_rate'] = course_stats.apply(
        lambda row: bayesian_smoothing(row['course_2ren_raw'], row['course_count'],
                                       global_stats['global_2ren_rate'], prior_strength), axis=1)

    # データ準備
    df_train_full = df_train.copy()
    df_test_full = df_test.copy()

    for df in [df_train_full, df_test_full]:
        df['is_inner'] = (df['pit_number'] <= 2).astype(int)
        df['is_outer'] = (df['pit_number'] >= 5).astype(int)

    df_train_full = df_train_full.merge(racer_stats, on='racer_number', how='left')
    df_train_full = df_train_full.merge(motor_stats, on=['venue_code', 'motor_number'], how='left')
    df_train_full = df_train_full.merge(course_stats[['racer_number', 'pit_number', 'course_win_rate', 'course_2ren_rate']],
                                        on=['racer_number', 'pit_number'], how='left')

    df_test_full = df_test_full.merge(racer_stats, on='racer_number', how='left')
    df_test_full = df_test_full.merge(motor_stats, on=['venue_code', 'motor_number'], how='left')
    df_test_full = df_test_full.merge(course_stats[['racer_number', 'pit_number', 'course_win_rate', 'course_2ren_rate']],
                                      on=['racer_number', 'pit_number'], how='left')

    # 欠損補完
    df_train_full['course_win_rate'] = df_train_full['course_win_rate'].fillna(global_stats['global_win_rate'])
    df_train_full['course_2ren_rate'] = df_train_full['course_2ren_rate'].fillna(global_stats['global_2ren_rate'])
    df_test_full['course_win_rate'] = df_test_full['course_win_rate'].fillna(global_stats['global_win_rate'])
    df_test_full['course_2ren_rate'] = df_test_full['course_2ren_rate'].fillna(global_stats['global_2ren_rate'])

    features = ['pit_number', 'is_inner', 'is_outer',
                'win_rate', 'second_rate', 'third_rate',
                'motor_win_rate', 'motor_2ren_rate',
                'course_win_rate', 'course_2ren_rate']

    X_train = df_train_full[features].fillna(0)
    X_test = df_test_full[features].fillna(0)

    model = xgb.XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.05,
                              subsample=0.8, colsample_bytree=0.8, random_state=42, eval_metric='auc')
    model.fit(X_train, y_train, verbose=False)

    y_prob = model.predict_proba(X_test)[:, 1]

    result = df_test_full[['race_id', 'pit_number', 'result_rank', 'is_win']].copy()
    result['score'] = y_prob * 100
    result['pred_rank'] = result.groupby('race_id')['score'].rank(ascending=False, method='min').astype(int)

    result_valid = result[result['result_rank'] <= 6].copy()
    top1 = result_valid[result_valid['pred_rank'] == 1]
    hit_1st = top1['is_win'].mean() * 100

    auc = roc_auc_score(result_valid['is_win'], result_valid['score'])

    return hit_1st, auc


def main():
    print('=' * 70)
    print('スムージング強度チューニング')
    print('=' * 70)
    print('')

    conn = sqlite3.connect(DATABASE_PATH)
    cutoff_date = '2025-10-31'

    # データ取得
    df_train = pd.read_sql_query('''
    SELECT r.id as race_id, r.venue_code, e.pit_number, e.racer_number, e.motor_number,
           CAST(COALESCE(NULLIF(res.rank, ''), '9') AS INTEGER) as result_rank
    FROM races r
    JOIN entries e ON r.id = e.race_id
    LEFT JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
    WHERE r.race_date BETWEEN '2025-10-01' AND '2025-10-31'
    ''', conn)
    df_train['is_win'] = (df_train['result_rank'] == 1).astype(int)
    y_train = df_train['is_win']

    df_test = pd.read_sql_query('''
    SELECT r.id as race_id, r.venue_code, e.pit_number, e.racer_number, e.motor_number,
           CAST(COALESCE(NULLIF(res.rank, ''), '9') AS INTEGER) as result_rank
    FROM races r
    JOIN entries e ON r.id = e.race_id
    LEFT JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
    WHERE r.race_date BETWEEN '2025-11-01' AND '2025-11-30'
    ''', conn)
    df_test['is_win'] = (df_test['result_rank'] == 1).astype(int)

    # 統計データ
    racer_stats = pd.read_sql_query(f'''
    SELECT e.racer_number,
           AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) as win_rate,
           AVG(CASE WHEN res.rank IN ('1','2') THEN 1.0 ELSE 0.0 END) as second_rate,
           AVG(CASE WHEN res.rank IN ('1','2','3') THEN 1.0 ELSE 0.0 END) as third_rate
    FROM entries e JOIN races r ON e.race_id = r.id
    JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
    WHERE res.rank IS NOT NULL AND res.rank NOT IN ('F', 'L', 'K', '') AND r.race_date <= '{cutoff_date}'
    GROUP BY e.racer_number
    ''', conn)

    motor_stats = pd.read_sql_query(f'''
    SELECT r.venue_code, e.motor_number,
           AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) as motor_win_rate,
           AVG(CASE WHEN res.rank IN ('1','2') THEN 1.0 ELSE 0.0 END) as motor_2ren_rate
    FROM races r JOIN entries e ON r.id = e.race_id
    JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
    WHERE res.rank IS NOT NULL AND res.rank NOT IN ('F', 'L', 'K', '') AND r.race_date <= '{cutoff_date}'
    GROUP BY r.venue_code, e.motor_number
    ''', conn)

    global_stats = pd.read_sql_query(f'''
    SELECT AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) as global_win_rate,
           AVG(CASE WHEN res.rank IN ('1','2') THEN 1.0 ELSE 0.0 END) as global_2ren_rate
    FROM results res JOIN races r ON res.race_id = r.id
    WHERE res.rank IS NOT NULL AND res.rank NOT IN ('F', 'L', 'K', '') AND r.race_date <= '{cutoff_date}'
    ''', conn).iloc[0]

    course_stats_raw = pd.read_sql_query(f'''
    SELECT e.racer_number, e.pit_number,
           AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) as course_win_raw,
           AVG(CASE WHEN res.rank IN ('1','2') THEN 1.0 ELSE 0.0 END) as course_2ren_raw,
           COUNT(*) as course_count
    FROM entries e JOIN races r ON e.race_id = r.id
    JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
    WHERE res.rank IS NOT NULL AND res.rank NOT IN ('F', 'L', 'K', '') AND r.race_date <= '{cutoff_date}'
    GROUP BY e.racer_number, e.pit_number
    ''', conn)

    conn.close()

    # ベースライン（既存特徴量のみ）
    df_train_base = df_train.copy()
    df_test_base = df_test.copy()
    for df in [df_train_base, df_test_base]:
        df['is_inner'] = (df['pit_number'] <= 2).astype(int)
        df['is_outer'] = (df['pit_number'] >= 5).astype(int)

    df_train_base = df_train_base.merge(racer_stats, on='racer_number', how='left')
    df_train_base = df_train_base.merge(motor_stats, on=['venue_code', 'motor_number'], how='left')
    df_test_base = df_test_base.merge(racer_stats, on='racer_number', how='left')
    df_test_base = df_test_base.merge(motor_stats, on=['venue_code', 'motor_number'], how='left')

    base_features = ['pit_number', 'is_inner', 'is_outer', 'win_rate', 'second_rate', 'third_rate',
                     'motor_win_rate', 'motor_2ren_rate']
    X_train_base = df_train_base[base_features].fillna(0)
    X_test_base = df_test_base[base_features].fillna(0)

    model_base = xgb.XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.05,
                                   subsample=0.8, colsample_bytree=0.8, random_state=42, eval_metric='auc')
    model_base.fit(X_train_base, y_train, verbose=False)
    y_prob_base = model_base.predict_proba(X_test_base)[:, 1]

    result_base = df_test_base[['race_id', 'pit_number', 'result_rank', 'is_win']].copy()
    result_base['score'] = y_prob_base * 100
    result_base['pred_rank'] = result_base.groupby('race_id')['score'].rank(ascending=False, method='min').astype(int)
    result_base_valid = result_base[result_base['result_rank'] <= 6].copy()
    top1_base = result_base_valid[result_base_valid['pred_rank'] == 1]
    base_hit_1st = top1_base['is_win'].mean() * 100
    base_auc = roc_auc_score(result_base_valid['is_win'], result_base_valid['score'])

    print(f'ベースライン（既存特徴量のみ）:')
    print(f'  1着的中率: {base_hit_1st:.2f}%')
    print(f'  AUC: {base_auc:.4f}')
    print('')

    # スムージング強度を変えてテスト
    print('スムージング強度別結果:')
    print(f'{"強度":<10} {"1着的中率":>12} {"AUC":>12} {"AUC差分":>12}')
    print('-' * 50)

    best_auc = base_auc
    best_strength = 0

    for strength in [0, 5, 10, 15, 20, 30, 50]:
        if strength == 0:
            # スムージングなし（生の値）
            hit_1st, auc = test_smoothing(0.001, df_train, df_test, y_train, racer_stats, motor_stats, course_stats_raw, global_stats)
        else:
            hit_1st, auc = test_smoothing(strength, df_train, df_test, y_train, racer_stats, motor_stats, course_stats_raw, global_stats)

        diff = auc - base_auc
        marker = ' ★' if auc > best_auc else ''
        print(f'{strength:<10} {hit_1st:>12.2f} {auc:>12.4f} {diff:>+12.4f}{marker}')

        if auc > best_auc:
            best_auc = auc
            best_strength = strength

    print('-' * 50)
    print(f'最適スムージング強度: {best_strength}')
    print(f'最高AUC: {best_auc:.4f} (ベースライン比 {best_auc - base_auc:+.4f})')


if __name__ == '__main__':
    main()
