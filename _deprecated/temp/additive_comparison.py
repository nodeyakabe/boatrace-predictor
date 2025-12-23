#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""11月予測 比較テスト（追加効果検証）

既存特徴量 vs 既存特徴量 + 新規特徴量
の比較を行う。
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

def get_base_features(conn, cutoff_date):
    """既存特徴量（基本的な選手・モーター統計）を取得"""

    # 選手基本統計
    racer_stats = pd.read_sql_query(f'''
    SELECT
        e.racer_number,
        AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) as win_rate,
        AVG(CASE WHEN res.rank IN ('1','2') THEN 1.0 ELSE 0.0 END) as second_rate,
        AVG(CASE WHEN res.rank IN ('1','2','3') THEN 1.0 ELSE 0.0 END) as third_rate,
        COUNT(*) as total_races
    FROM entries e
    JOIN races r ON e.race_id = r.id
    JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
    WHERE res.rank IS NOT NULL AND res.rank NOT IN ('F', 'L', 'K', '')
      AND r.race_date <= '{cutoff_date}'
    GROUP BY e.racer_number
    ''', conn)

    # モーター基本統計
    motor_stats = pd.read_sql_query(f'''
    SELECT
        r.venue_code, e.motor_number,
        AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) as motor_win_rate,
        AVG(CASE WHEN res.rank IN ('1','2') THEN 1.0 ELSE 0.0 END) as motor_2ren_rate
    FROM races r
    JOIN entries e ON r.id = e.race_id
    JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
    WHERE res.rank IS NOT NULL AND res.rank NOT IN ('F', 'L', 'K', '')
      AND r.race_date <= '{cutoff_date}'
    GROUP BY r.venue_code, e.motor_number
    ''', conn)

    return racer_stats, motor_stats


def get_new_features(conn, cutoff_date):
    """新規特徴量（コース別・会場×コース）を取得"""

    # コース別勝率
    course_stats = pd.read_sql_query(f'''
    SELECT
        e.racer_number, e.pit_number,
        AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) as course_win_rate,
        AVG(CASE WHEN res.rank IN ('1','2') THEN 1.0 ELSE 0.0 END) as course_2ren_rate,
        AVG(CASE WHEN res.rank IN ('1','2','3') THEN 1.0 ELSE 0.0 END) as course_3ren_rate,
        COUNT(*) as course_count
    FROM entries e
    JOIN races r ON e.race_id = r.id
    JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
    WHERE res.rank IS NOT NULL AND res.rank NOT IN ('F', 'L', 'K', '')
      AND r.race_date <= '{cutoff_date}'
    GROUP BY e.racer_number, e.pit_number
    ''', conn)

    # 会場×コース勝率（Opus分析で最重要と判明）
    venue_course = pd.read_sql_query(f'''
    SELECT
        e.racer_number, r.venue_code, e.pit_number,
        AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) as venue_course_win,
        AVG(CASE WHEN res.rank IN ('1','2') THEN 1.0 ELSE 0.0 END) as venue_course_2ren,
        COUNT(*) as vc_count
    FROM races r
    JOIN entries e ON r.id = e.race_id
    JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
    WHERE res.rank IS NOT NULL AND res.rank NOT IN ('F', 'L', 'K', '')
      AND r.race_date <= '{cutoff_date}'
    GROUP BY e.racer_number, r.venue_code, e.pit_number
    ''', conn)

    return course_stats, venue_course


def main():
    print('=' * 70)
    print('11月予測 追加効果検証')
    print('既存特徴量 vs 既存特徴量 + 新規特徴量')
    print('=' * 70)
    print('※ 統計計算は2025年10月末までのデータのみ使用')
    print('', flush=True)

    conn = sqlite3.connect(DATABASE_PATH)
    cutoff_date = '2025-10-31'

    # 訓練データ（10月）
    print('【Step 1】データ取得', flush=True)
    start = time.time()

    query_train = '''
    SELECT
        r.id as race_id, r.race_date, r.venue_code, r.race_number,
        e.pit_number, e.racer_number, e.motor_number,
        CAST(COALESCE(NULLIF(res.rank, ''), '9') AS INTEGER) as result_rank
    FROM races r
    JOIN entries e ON r.id = e.race_id
    LEFT JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
    WHERE r.race_date BETWEEN '2025-10-01' AND '2025-10-31'
    '''
    df_train = pd.read_sql_query(query_train, conn)
    df_train['is_win'] = (df_train['result_rank'] == 1).astype(int)
    print(f'  訓練データ: {len(df_train)}行')

    # テストデータ（11月）
    query_test = '''
    SELECT
        r.id as race_id, r.race_date, r.venue_code, r.race_number,
        e.pit_number, e.racer_number, e.motor_number,
        CAST(COALESCE(NULLIF(res.rank, ''), '9') AS INTEGER) as result_rank
    FROM races r
    JOIN entries e ON r.id = e.race_id
    LEFT JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
    WHERE r.race_date BETWEEN '2025-11-01' AND '2025-11-30'
    '''
    df_test = pd.read_sql_query(query_test, conn)
    df_test['is_win'] = (df_test['result_rank'] == 1).astype(int)
    print(f'  テストデータ: {len(df_test)}行')

    # 既存特徴量
    print('  既存特徴量を取得...', flush=True)
    racer_stats, motor_stats = get_base_features(conn, cutoff_date)
    print(f'    選手統計: {len(racer_stats)}件')
    print(f'    モーター統計: {len(motor_stats)}件')

    # 新規特徴量
    print('  新規特徴量を取得...', flush=True)
    course_stats, venue_course = get_new_features(conn, cutoff_date)
    print(f'    コース別勝率: {len(course_stats)}件')
    print(f'    会場×コース: {len(venue_course)}件')
    print(f'  データ取得完了: {time.time()-start:.1f}秒')

    conn.close()

    # 基本特徴量を追加
    for df in [df_train, df_test]:
        df['is_inner'] = (df['pit_number'] <= 2).astype(int)
        df['is_outer'] = (df['pit_number'] >= 5).astype(int)

    # ========================================
    # パターン1: 既存特徴量のみ
    # ========================================
    print('')
    print('【Step 2】既存特徴量のみでモデル訓練', flush=True)

    df_train_base = df_train.copy()
    df_test_base = df_test.copy()

    df_train_base = df_train_base.merge(racer_stats, on='racer_number', how='left')
    df_train_base = df_train_base.merge(motor_stats, on=['venue_code', 'motor_number'], how='left')

    df_test_base = df_test_base.merge(racer_stats, on='racer_number', how='left')
    df_test_base = df_test_base.merge(motor_stats, on=['venue_code', 'motor_number'], how='left')

    base_features = ['pit_number', 'is_inner', 'is_outer',
                     'win_rate', 'second_rate', 'third_rate',
                     'motor_win_rate', 'motor_2ren_rate']

    X_train_base = df_train_base[base_features].fillna(0).replace([np.inf, -np.inf], 0)
    y_train = df_train_base['is_win']
    X_test_base = df_test_base[base_features].fillna(0).replace([np.inf, -np.inf], 0)

    print(f'  特徴量: {len(base_features)}個')

    model_base = xgb.XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.05,
                                   subsample=0.8, colsample_bytree=0.8, random_state=42, eval_metric='auc')
    model_base.fit(X_train_base, y_train, verbose=False)

    y_prob_base = model_base.predict_proba(X_test_base)[:, 1]

    result_base = df_test_base[['race_id', 'pit_number', 'result_rank', 'is_win']].copy()
    result_base['score'] = y_prob_base * 100
    result_base['pred_rank'] = result_base.groupby('race_id')['score'].rank(ascending=False, method='min').astype(int)

    # 評価（結果があるデータのみ）
    result_base_valid = result_base[result_base['result_rank'] <= 6].copy()

    top1_base = result_base_valid[result_base_valid['pred_rank'] == 1]
    base_hit_1st = top1_base['is_win'].mean() * 100

    result_base_valid['pred_top3'] = (result_base_valid['pred_rank'] <= 3).astype(int)
    result_base_valid['act_top3'] = result_base_valid['result_rank'].isin([1, 2, 3]).astype(int)
    base_hit_top3 = ((result_base_valid['pred_top3'] == 1) & (result_base_valid['act_top3'] == 1)).sum() / result_base_valid['pred_top3'].sum() * 100
    base_auc = roc_auc_score(result_base_valid['is_win'], result_base_valid['score'])

    print(f'  1着的中率: {base_hit_1st:.2f}%')
    print(f'  3着内的中率: {base_hit_top3:.2f}%')
    print(f'  AUC: {base_auc:.4f}')

    # ========================================
    # パターン2: 既存 + 新規特徴量
    # ========================================
    print('')
    print('【Step 3】既存 + 新規特徴量でモデル訓練', flush=True)

    df_train_full = df_train.copy()
    df_test_full = df_test.copy()

    # 既存特徴量
    df_train_full = df_train_full.merge(racer_stats, on='racer_number', how='left')
    df_train_full = df_train_full.merge(motor_stats, on=['venue_code', 'motor_number'], how='left')

    df_test_full = df_test_full.merge(racer_stats, on='racer_number', how='left')
    df_test_full = df_test_full.merge(motor_stats, on=['venue_code', 'motor_number'], how='left')

    # 新規特徴量を追加
    df_train_full = df_train_full.merge(course_stats, on=['racer_number', 'pit_number'], how='left')
    df_train_full = df_train_full.merge(venue_course, on=['racer_number', 'venue_code', 'pit_number'], how='left')

    df_test_full = df_test_full.merge(course_stats, on=['racer_number', 'pit_number'], how='left')
    df_test_full = df_test_full.merge(venue_course, on=['racer_number', 'venue_code', 'pit_number'], how='left')

    full_features = ['pit_number', 'is_inner', 'is_outer',
                     # 既存
                     'win_rate', 'second_rate', 'third_rate',
                     'motor_win_rate', 'motor_2ren_rate',
                     # 新規（コース別）
                     'course_win_rate', 'course_2ren_rate', 'course_3ren_rate',
                     # 新規（会場×コース）
                     'venue_course_win', 'venue_course_2ren']

    X_train_full = df_train_full[full_features].fillna(0).replace([np.inf, -np.inf], 0)
    X_test_full = df_test_full[full_features].fillna(0).replace([np.inf, -np.inf], 0)

    print(f'  特徴量: {len(full_features)}個 (+{len(full_features) - len(base_features)}個)')

    model_full = xgb.XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.05,
                                   subsample=0.8, colsample_bytree=0.8, random_state=42, eval_metric='auc')
    model_full.fit(X_train_full, y_train, verbose=False)

    y_prob_full = model_full.predict_proba(X_test_full)[:, 1]

    result_full = df_test_full[['race_id', 'pit_number', 'result_rank', 'is_win']].copy()
    result_full['score'] = y_prob_full * 100
    result_full['pred_rank'] = result_full.groupby('race_id')['score'].rank(ascending=False, method='min').astype(int)

    # 評価
    result_full_valid = result_full[result_full['result_rank'] <= 6].copy()

    top1_full = result_full_valid[result_full_valid['pred_rank'] == 1]
    full_hit_1st = top1_full['is_win'].mean() * 100

    result_full_valid['pred_top3'] = (result_full_valid['pred_rank'] <= 3).astype(int)
    result_full_valid['act_top3'] = result_full_valid['result_rank'].isin([1, 2, 3]).astype(int)
    full_hit_top3 = ((result_full_valid['pred_top3'] == 1) & (result_full_valid['act_top3'] == 1)).sum() / result_full_valid['pred_top3'].sum() * 100
    full_auc = roc_auc_score(result_full_valid['is_win'], result_full_valid['score'])

    print(f'  1着的中率: {full_hit_1st:.2f}%')
    print(f'  3着内的中率: {full_hit_top3:.2f}%')
    print(f'  AUC: {full_auc:.4f}')

    # ========================================
    # 比較結果
    # ========================================
    print('')
    print('=' * 70)
    print('【比較結果】新規特徴量の追加効果')
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
    print('【特徴量重要度（既存+新規モデル）】')
    importances = model_full.feature_importances_
    sorted_idx = np.argsort(importances)[::-1]

    new_feature_names = ['course_win_rate', 'course_2ren_rate', 'course_3ren_rate',
                         'venue_course_win', 'venue_course_2ren']

    for i in sorted_idx:
        marker = '★' if full_features[i] in new_feature_names else '  '
        print(f'{marker} {full_features[i]:<25}: {importances[i]:.4f}')

    # 結論
    print('')
    print('【結論】')
    if diff_auc > 0.005:
        print(f'  新規特徴量の追加でAUC {diff_auc:+.4f} (+{diff_auc*100:.2f}%) 改善')
        print('  → 新規特徴量の追加を推奨')
    elif diff_auc > 0:
        print(f'  新規特徴量の追加でAUC {diff_auc:+.4f} (+{diff_auc*100:.2f}%) 微改善')
        print('  → 効果は限定的だが、追加しても良い')
    else:
        print(f'  新規特徴量の追加でAUC {diff_auc:+.4f} ({diff_auc*100:.2f}%) 変化なし/悪化')
        print('  → 追加効果なし')


if __name__ == '__main__':
    main()
