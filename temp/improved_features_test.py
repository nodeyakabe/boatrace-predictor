#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""改善版特徴量テスト

問題点への対策:
1. 最小サンプル数フィルタ: 10走未満のデータは使用しない
2. ベイズスムージング: スパースデータは全国平均で補完
3. コース別勝率のみ使用: venue_course_winは除外（過学習の原因）
"""
import sys
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import sqlite3
import pandas as pd
import numpy as np
import time
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
import xgboost as xgb
from sklearn.metrics import roc_auc_score
import warnings
warnings.filterwarnings('ignore')

# 最小サンプル数の閾値
MIN_SAMPLES = 10
# ベイズスムージングの強度（仮想サンプル数）
PRIOR_STRENGTH = 5


def bayesian_smoothing(observed_rate, sample_count, prior_rate, prior_strength=PRIOR_STRENGTH):
    """
    ベイズスムージング: 少ないサンプルは事前分布（全体平均）に引き寄せる

    smoothed = (observed * n + prior * k) / (n + k)

    n: 実際のサンプル数
    k: 仮想サンプル数（prior_strength）
    """
    return (observed_rate * sample_count + prior_rate * prior_strength) / (sample_count + prior_strength)


def main():
    print('=' * 70)
    print('改善版特徴量テスト')
    print('対策: 最小サンプルフィルタ + ベイズスムージング')
    print('=' * 70)
    print(f'最小サンプル数: {MIN_SAMPLES}')
    print(f'ベイズスムージング強度: {PRIOR_STRENGTH}')
    print('', flush=True)

    conn = sqlite3.connect(DATABASE_PATH)
    cutoff_date = '2025-10-31'

    # データ取得
    print('【Step 1】データ取得', flush=True)
    start = time.time()

    # 訓練データ（10月）
    df_train = pd.read_sql_query('''
    SELECT r.id as race_id, r.venue_code, e.pit_number, e.racer_number, e.motor_number,
           CAST(COALESCE(NULLIF(res.rank, ''), '9') AS INTEGER) as result_rank
    FROM races r
    JOIN entries e ON r.id = e.race_id
    LEFT JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
    WHERE r.race_date BETWEEN '2025-10-01' AND '2025-10-31'
    ''', conn)
    df_train['is_win'] = (df_train['result_rank'] == 1).astype(int)
    print(f'  訓練データ: {len(df_train)}行')

    # テストデータ（11月）
    df_test = pd.read_sql_query('''
    SELECT r.id as race_id, r.venue_code, e.pit_number, e.racer_number, e.motor_number,
           CAST(COALESCE(NULLIF(res.rank, ''), '9') AS INTEGER) as result_rank
    FROM races r
    JOIN entries e ON r.id = e.race_id
    LEFT JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
    WHERE r.race_date BETWEEN '2025-11-01' AND '2025-11-30'
    ''', conn)
    df_test['is_win'] = (df_test['result_rank'] == 1).astype(int)
    print(f'  テストデータ: {len(df_test)}行')

    # ========================================
    # 既存特徴量（フィルタなし）
    # ========================================
    print('  既存特徴量を取得...', flush=True)

    racer_stats = pd.read_sql_query(f'''
    SELECT e.racer_number,
           AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) as win_rate,
           AVG(CASE WHEN res.rank IN ('1','2') THEN 1.0 ELSE 0.0 END) as second_rate,
           AVG(CASE WHEN res.rank IN ('1','2','3') THEN 1.0 ELSE 0.0 END) as third_rate,
           COUNT(*) as racer_count
    FROM entries e
    JOIN races r ON e.race_id = r.id
    JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
    WHERE res.rank IS NOT NULL AND res.rank NOT IN ('F', 'L', 'K', '')
      AND r.race_date <= '{cutoff_date}'
    GROUP BY e.racer_number
    ''', conn)

    motor_stats = pd.read_sql_query(f'''
    SELECT r.venue_code, e.motor_number,
           AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) as motor_win_rate,
           AVG(CASE WHEN res.rank IN ('1','2') THEN 1.0 ELSE 0.0 END) as motor_2ren_rate,
           COUNT(*) as motor_count
    FROM races r
    JOIN entries e ON r.id = e.race_id
    JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
    WHERE res.rank IS NOT NULL AND res.rank NOT IN ('F', 'L', 'K', '')
      AND r.race_date <= '{cutoff_date}'
    GROUP BY r.venue_code, e.motor_number
    ''', conn)

    # ========================================
    # 新規特徴量（フィルタ + スムージング適用）
    # ========================================
    print('  新規特徴量を取得（フィルタ + スムージング）...', flush=True)

    # 全国平均（事前分布）
    global_stats = pd.read_sql_query(f'''
    SELECT AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) as global_win_rate,
           AVG(CASE WHEN res.rank IN ('1','2') THEN 1.0 ELSE 0.0 END) as global_2ren_rate,
           AVG(CASE WHEN res.rank IN ('1','2','3') THEN 1.0 ELSE 0.0 END) as global_3ren_rate
    FROM results res
    JOIN races r ON res.race_id = r.id
    WHERE res.rank IS NOT NULL AND res.rank NOT IN ('F', 'L', 'K', '')
      AND r.race_date <= '{cutoff_date}'
    ''', conn).iloc[0]

    print(f'    全国平均勝率: {global_stats["global_win_rate"]:.4f}')

    # コース別勝率（最小サンプルフィルタ + ベイズスムージング）
    course_stats_raw = pd.read_sql_query(f'''
    SELECT e.racer_number, e.pit_number,
           AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) as course_win_raw,
           AVG(CASE WHEN res.rank IN ('1','2') THEN 1.0 ELSE 0.0 END) as course_2ren_raw,
           AVG(CASE WHEN res.rank IN ('1','2','3') THEN 1.0 ELSE 0.0 END) as course_3ren_raw,
           COUNT(*) as course_count
    FROM entries e
    JOIN races r ON e.race_id = r.id
    JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
    WHERE res.rank IS NOT NULL AND res.rank NOT IN ('F', 'L', 'K', '')
      AND r.race_date <= '{cutoff_date}'
    GROUP BY e.racer_number, e.pit_number
    ''', conn)

    # ベイズスムージング適用
    course_stats_raw['course_win_rate'] = course_stats_raw.apply(
        lambda row: bayesian_smoothing(
            row['course_win_raw'], row['course_count'],
            global_stats['global_win_rate']
        ), axis=1
    )
    course_stats_raw['course_2ren_rate'] = course_stats_raw.apply(
        lambda row: bayesian_smoothing(
            row['course_2ren_raw'], row['course_count'],
            global_stats['global_2ren_rate']
        ), axis=1
    )
    course_stats_raw['course_3ren_rate'] = course_stats_raw.apply(
        lambda row: bayesian_smoothing(
            row['course_3ren_raw'], row['course_count'],
            global_stats['global_3ren_rate']
        ), axis=1
    )

    # 最小サンプル数フィルタ: 信頼度フラグ
    course_stats_raw['course_reliable'] = (course_stats_raw['course_count'] >= MIN_SAMPLES).astype(int)

    course_stats = course_stats_raw[['racer_number', 'pit_number',
                                      'course_win_rate', 'course_2ren_rate', 'course_3ren_rate',
                                      'course_count', 'course_reliable']]

    print(f'    コース別勝率: {len(course_stats)}件')
    print(f'    うち信頼度高({MIN_SAMPLES}走以上): {course_stats["course_reliable"].sum()}件 ({course_stats["course_reliable"].mean()*100:.1f}%)')

    conn.close()
    print(f'  データ取得完了: {time.time()-start:.1f}秒')

    # ========================================
    # パターン1: 既存特徴量のみ
    # ========================================
    print('')
    print('【Step 2】既存特徴量のみでモデル訓練', flush=True)

    df_train_base = df_train.copy()
    df_test_base = df_test.copy()

    for df in [df_train_base, df_test_base]:
        df['is_inner'] = (df['pit_number'] <= 2).astype(int)
        df['is_outer'] = (df['pit_number'] >= 5).astype(int)

    df_train_base = df_train_base.merge(racer_stats, on='racer_number', how='left')
    df_train_base = df_train_base.merge(motor_stats, on=['venue_code', 'motor_number'], how='left')
    df_test_base = df_test_base.merge(racer_stats, on='racer_number', how='left')
    df_test_base = df_test_base.merge(motor_stats, on=['venue_code', 'motor_number'], how='left')

    base_features = ['pit_number', 'is_inner', 'is_outer',
                     'win_rate', 'second_rate', 'third_rate',
                     'motor_win_rate', 'motor_2ren_rate']

    X_train_base = df_train_base[base_features].fillna(0)
    y_train = df_train_base['is_win']
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
    result_base_valid['pred_top3'] = (result_base_valid['pred_rank'] <= 3).astype(int)
    result_base_valid['act_top3'] = result_base_valid['result_rank'].isin([1, 2, 3]).astype(int)
    base_hit_top3 = ((result_base_valid['pred_top3'] == 1) & (result_base_valid['act_top3'] == 1)).sum() / result_base_valid['pred_top3'].sum() * 100
    base_auc = roc_auc_score(result_base_valid['is_win'], result_base_valid['score'])

    print(f'  特徴量: {len(base_features)}個')
    print(f'  1着的中率: {base_hit_1st:.2f}%')
    print(f'  3着内的中率: {base_hit_top3:.2f}%')
    print(f'  AUC: {base_auc:.4f}')

    # ========================================
    # パターン2: 既存 + コース別勝率（スムージング版）
    # ========================================
    print('')
    print('【Step 3】既存 + コース別勝率（スムージング版）', flush=True)

    df_train_full = df_train.copy()
    df_test_full = df_test.copy()

    for df in [df_train_full, df_test_full]:
        df['is_inner'] = (df['pit_number'] <= 2).astype(int)
        df['is_outer'] = (df['pit_number'] >= 5).astype(int)

    df_train_full = df_train_full.merge(racer_stats, on='racer_number', how='left')
    df_train_full = df_train_full.merge(motor_stats, on=['venue_code', 'motor_number'], how='left')
    df_train_full = df_train_full.merge(course_stats, on=['racer_number', 'pit_number'], how='left')

    df_test_full = df_test_full.merge(racer_stats, on='racer_number', how='left')
    df_test_full = df_test_full.merge(motor_stats, on=['venue_code', 'motor_number'], how='left')
    df_test_full = df_test_full.merge(course_stats, on=['racer_number', 'pit_number'], how='left')

    # 信頼度が低い場合は全国平均で補完
    for col in ['course_win_rate', 'course_2ren_rate', 'course_3ren_rate']:
        global_col = col.replace('course', 'global')
        df_train_full[col] = df_train_full[col].fillna(global_stats[global_col])
        df_test_full[col] = df_test_full[col].fillna(global_stats[global_col])

    full_features = ['pit_number', 'is_inner', 'is_outer',
                     'win_rate', 'second_rate', 'third_rate',
                     'motor_win_rate', 'motor_2ren_rate',
                     'course_win_rate', 'course_2ren_rate', 'course_3ren_rate',
                     'course_reliable']

    X_train_full = df_train_full[full_features].fillna(0)
    X_test_full = df_test_full[full_features].fillna(0)

    model_full = xgb.XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.05,
                                   subsample=0.8, colsample_bytree=0.8, random_state=42, eval_metric='auc')
    model_full.fit(X_train_full, y_train, verbose=False)

    y_prob_full = model_full.predict_proba(X_test_full)[:, 1]

    result_full = df_test_full[['race_id', 'pit_number', 'result_rank', 'is_win']].copy()
    result_full['score'] = y_prob_full * 100
    result_full['pred_rank'] = result_full.groupby('race_id')['score'].rank(ascending=False, method='min').astype(int)

    result_full_valid = result_full[result_full['result_rank'] <= 6].copy()
    top1_full = result_full_valid[result_full_valid['pred_rank'] == 1]
    full_hit_1st = top1_full['is_win'].mean() * 100
    result_full_valid['pred_top3'] = (result_full_valid['pred_rank'] <= 3).astype(int)
    result_full_valid['act_top3'] = result_full_valid['result_rank'].isin([1, 2, 3]).astype(int)
    full_hit_top3 = ((result_full_valid['pred_top3'] == 1) & (result_full_valid['act_top3'] == 1)).sum() / result_full_valid['pred_top3'].sum() * 100
    full_auc = roc_auc_score(result_full_valid['is_win'], result_full_valid['score'])

    print(f'  特徴量: {len(full_features)}個 (+{len(full_features) - len(base_features)}個)')
    print(f'  1着的中率: {full_hit_1st:.2f}%')
    print(f'  3着内的中率: {full_hit_top3:.2f}%')
    print(f'  AUC: {full_auc:.4f}')

    # ========================================
    # 比較結果
    # ========================================
    print('')
    print('=' * 70)
    print('【比較結果】スムージング版新規特徴量の追加効果')
    print('=' * 70)

    diff_1st = full_hit_1st - base_hit_1st
    diff_top3 = full_hit_top3 - base_hit_top3
    diff_auc = full_auc - base_auc

    print(f'{"指標":<20} {"既存のみ":>12} {"既存+新規":>12} {"差分":>12}')
    print('-' * 70)
    print(f'{"1着的中率 (%)":<20} {base_hit_1st:>12.2f} {full_hit_1st:>12.2f} {diff_1st:>+12.2f}')
    print(f'{"3着内的中率 (%)":<20} {base_hit_top3:>12.2f} {full_hit_top3:>12.2f} {diff_top3:>+12.2f}')
    print(f'{"AUC":<20} {base_auc:>12.4f} {full_auc:>12.4f} {diff_auc:>+12.4f}')
    print('=' * 70)

    # 特徴量重要度
    print('')
    print('【特徴量重要度】')
    importances = model_full.feature_importances_
    sorted_idx = np.argsort(importances)[::-1]

    new_features = ['course_win_rate', 'course_2ren_rate', 'course_3ren_rate', 'course_reliable']
    for i in sorted_idx:
        marker = '★' if full_features[i] in new_features else '  '
        print(f'{marker} {full_features[i]:<25}: {importances[i]:.4f}')

    # 結論
    print('')
    print('【結論】')
    if diff_auc > 0.005:
        print(f'  ベイズスムージング版でAUC {diff_auc:+.4f} (+{diff_auc*100:.2f}%) 改善')
        print('  → コース別勝率（スムージング版）の追加を推奨')
    elif diff_auc > 0:
        print(f'  ベイズスムージング版でAUC {diff_auc:+.4f} (+{diff_auc*100:.2f}%) 微改善')
        print('  → 効果は限定的だが、追加しても問題なし')
    elif diff_auc > -0.005:
        print(f'  ベイズスムージング版でAUC {diff_auc:+.4f} ({diff_auc*100:.2f}%) ほぼ変化なし')
        print('  → 追加しても悪化はしない')
    else:
        print(f'  ベイズスムージング版でAUC {diff_auc:+.4f} ({diff_auc*100:.2f}%) 悪化')
        print('  → 追加は見送り')


if __name__ == '__main__':
    main()
