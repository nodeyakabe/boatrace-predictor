#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""11月予測 比較テスト（時系列厳密版）

データリークを防ぐため、統計計算に使用するデータを
テスト期間より前に厳密に制限する。
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

def main():
    print('=== 11月予測 比較テスト（時系列厳密版） ===')
    print('※ 統計計算は2025年10月末までのデータのみ使用')
    print('', flush=True)

    conn = sqlite3.connect(DATABASE_PATH)

    # カットオフ日: テストデータの前日
    cutoff_date = '2025-10-31'

    # 現行版予測を取得
    print('【Step 1】現行版予測を取得', flush=True)
    df_current = pd.read_sql_query('''
        SELECT p.race_id, p.pit_number, p.rank_prediction, p.total_score
        FROM race_predictions p
        JOIN races r ON p.race_id = r.id
        WHERE r.race_date BETWEEN '2025-11-01' AND '2025-11-30' AND p.prediction_type = 'before'
    ''', conn)

    # 結果データを取得
    df_results = pd.read_sql_query('''
        SELECT r.id as race_id, e.pit_number, res.rank as result_rank
        FROM races r JOIN entries e ON r.id = e.race_id
        JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
        WHERE r.race_date BETWEEN '2025-11-01' AND '2025-11-30'
            AND res.rank IS NOT NULL AND res.rank NOT IN ('F', 'L', 'K', '')
    ''', conn)
    df_results['is_win'] = (df_results['result_rank'] == '1').astype(int)

    print(f'  現行版予測: {len(df_current)}件')
    print(f'  結果データ: {len(df_results)}件')

    # 現行版の精度評価
    merged = df_results.merge(df_current, on=['race_id', 'pit_number'], how='inner')
    top1 = merged[merged['rank_prediction'] == 1]
    current_hit_1st = top1['is_win'].mean() * 100
    merged['pred_top3'] = (merged['rank_prediction'] <= 3).astype(int)
    merged['act_top3'] = merged['result_rank'].astype(str).isin(['1', '2', '3']).astype(int)
    current_hit_top3 = ((merged['pred_top3'] == 1) & (merged['act_top3'] == 1)).sum() / merged['pred_top3'].sum() * 100
    current_auc = roc_auc_score(merged['is_win'], merged['total_score'])

    print('')
    print('【現行版の予測精度】')
    print(f'  1着的中率: {current_hit_1st:.2f}%')
    print(f'  3着内的中率: {current_hit_top3:.2f}%')
    print(f'  AUC: {current_auc:.4f}')
    print(f'  対象レース: {merged["race_id"].nunique()}')
    print('', flush=True)

    # 改善版: 時系列厳密版
    print('【Step 2】改善版予測を実行（時系列厳密）')
    print(f'  統計計算のカットオフ: {cutoff_date}', flush=True)
    start = time.time()

    # 訓練データ（10月）
    query_train = f'''
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
    print(f'    訓練データ: {len(df_train)}行')

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
    print(f'    テストデータ: {len(df_test)}行')

    # ★重要: 統計計算は全てカットオフ日以前のデータのみ使用
    print(f'  選手統計を取得（{cutoff_date}以前）...', flush=True)
    start = time.time()
    racer_stats = pd.read_sql_query(f'''
    SELECT
        e.racer_number,
        AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) as racer_win_rate,
        AVG(CASE WHEN res.rank IN ('1','2') THEN 1.0 ELSE 0.0 END) as racer_2ren_rate,
        AVG(CASE WHEN res.rank IN ('1','2','3') THEN 1.0 ELSE 0.0 END) as racer_3ren_rate,
        COUNT(*) as race_count
    FROM entries e
    JOIN races r ON e.race_id = r.id
    JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
    WHERE res.rank IS NOT NULL AND res.rank NOT IN ('F', 'L', 'K', '')
      AND r.race_date <= '{cutoff_date}'
    GROUP BY e.racer_number
    ''', conn)
    print(f'    選手統計: {len(racer_stats)}件, {time.time()-start:.1f}秒')

    # コース別勝率（カットオフ日以前）
    print(f'  コース別勝率を取得（{cutoff_date}以前）...', flush=True)
    start = time.time()
    course_stats = pd.read_sql_query(f'''
    SELECT
        e.racer_number, e.pit_number,
        AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) as course_win_rate,
        AVG(CASE WHEN res.rank IN ('1','2') THEN 1.0 ELSE 0.0 END) as course_2ren_rate,
        COUNT(*) as course_count
    FROM entries e
    JOIN races r ON e.race_id = r.id
    JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
    WHERE res.rank IS NOT NULL AND res.rank NOT IN ('F', 'L', 'K', '')
      AND r.race_date <= '{cutoff_date}'
    GROUP BY e.racer_number, e.pit_number
    ''', conn)
    print(f'    コース別勝率: {len(course_stats)}件, {time.time()-start:.1f}秒')

    # 会場×コース勝率（カットオフ日以前）
    print(f'  会場×コース勝率を取得（{cutoff_date}以前）...', flush=True)
    start = time.time()
    venue_course = pd.read_sql_query(f'''
    SELECT
        e.racer_number, r.venue_code, e.pit_number,
        AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) as venue_course_win,
        COUNT(*) as vc_count
    FROM races r
    JOIN entries e ON r.id = e.race_id
    JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
    WHERE res.rank IS NOT NULL AND res.rank NOT IN ('F', 'L', 'K', '')
      AND r.race_date <= '{cutoff_date}'
    GROUP BY e.racer_number, r.venue_code, e.pit_number
    ''', conn)
    print(f'    会場×コース: {len(venue_course)}件, {time.time()-start:.1f}秒')

    # モーター成績（カットオフ日以前）
    print(f'  モーター成績を取得（{cutoff_date}以前）...', flush=True)
    start = time.time()
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
    print(f'    モーター成績: {len(motor_stats)}件, {time.time()-start:.1f}秒')

    conn.close()

    # 特徴量をマージ
    print('')
    print('  特徴量をマージ...', flush=True)
    for df in [df_train, df_test]:
        df['is_inner'] = (df['pit_number'] <= 2).astype(int)
        df['is_outer'] = (df['pit_number'] >= 5).astype(int)

    df_train = df_train.merge(racer_stats, on='racer_number', how='left')
    df_train = df_train.merge(course_stats, on=['racer_number', 'pit_number'], how='left')
    df_train = df_train.merge(venue_course, on=['racer_number', 'venue_code', 'pit_number'], how='left')
    df_train = df_train.merge(motor_stats, on=['venue_code', 'motor_number'], how='left')

    df_test = df_test.merge(racer_stats, on='racer_number', how='left')
    df_test = df_test.merge(course_stats, on=['racer_number', 'pit_number'], how='left')
    df_test = df_test.merge(venue_course, on=['racer_number', 'venue_code', 'pit_number'], how='left')
    df_test = df_test.merge(motor_stats, on=['venue_code', 'motor_number'], how='left')

    # 特徴量
    feature_cols = ['pit_number', 'is_inner', 'is_outer',
                    'racer_win_rate', 'racer_2ren_rate', 'racer_3ren_rate',
                    'course_win_rate', 'course_2ren_rate',
                    'venue_course_win', 'motor_win_rate', 'motor_2ren_rate']
    print(f'  使用特徴量: {len(feature_cols)}個', flush=True)

    X_train = df_train[feature_cols].fillna(0).replace([np.inf, -np.inf], 0)
    y_train = df_train['is_win']
    X_test = df_test[feature_cols].fillna(0).replace([np.inf, -np.inf], 0)

    # モデル訓練
    print('')
    print('  モデル訓練中...', flush=True)
    start = time.time()
    model = xgb.XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.05,
                              subsample=0.8, colsample_bytree=0.8, random_state=42, eval_metric='auc')
    model.fit(X_train, y_train, verbose=False)
    print(f'    訓練完了: {time.time()-start:.1f}秒')

    # 予測
    print('  予測実行...', flush=True)
    y_prob = model.predict_proba(X_test)[:, 1]

    result_df = df_test[['race_id', 'pit_number', 'result_rank', 'is_win']].copy()
    result_df['improved_score'] = y_prob * 100
    result_df['improved_rank'] = result_df.groupby('race_id')['improved_score'].rank(ascending=False, method='min').astype(int)

    # 評価（結果があるデータのみ）
    result_valid = result_df[result_df['result_rank'] <= 6].copy()

    top1_imp = result_valid[result_valid['improved_rank'] == 1]
    improved_hit_1st = top1_imp['is_win'].mean() * 100

    result_valid['pred_top3'] = (result_valid['improved_rank'] <= 3).astype(int)
    result_valid['act_top3'] = result_valid['result_rank'].isin([1, 2, 3]).astype(int)
    improved_hit_top3 = ((result_valid['pred_top3'] == 1) & (result_valid['act_top3'] == 1)).sum() / result_valid['pred_top3'].sum() * 100
    improved_auc = roc_auc_score(result_valid['is_win'], result_valid['improved_score'])

    print('')
    print('【改善版の予測精度】')
    print(f'  1着的中率: {improved_hit_1st:.2f}%')
    print(f'  3着内的中率: {improved_hit_top3:.2f}%')
    print(f'  AUC: {improved_auc:.4f}')
    print(f'  対象レース: {result_valid["race_id"].nunique()}')

    # 比較
    print('')
    print('='*60)
    print('【比較結果】')
    print('='*60)
    diff_1st = improved_hit_1st - current_hit_1st
    diff_top3 = improved_hit_top3 - current_hit_top3
    diff_auc = improved_auc - current_auc

    print(f'{"指標":<20} {"現行版":>12} {"改善版":>12} {"差分":>12}')
    print('-'*60)
    print(f'{"1着的中率 (%)":<20} {current_hit_1st:>12.2f} {improved_hit_1st:>12.2f} {diff_1st:>+12.2f}')
    print(f'{"3着内的中率 (%)":<20} {current_hit_top3:>12.2f} {improved_hit_top3:>12.2f} {diff_top3:>+12.2f}')
    print(f'{"AUC":<20} {current_auc:>12.4f} {improved_auc:>12.4f} {diff_auc:>+12.4f}')
    print('='*60)

    # 特徴量重要度
    print('')
    print('【特徴量重要度】')
    importances = model.feature_importances_
    sorted_idx = np.argsort(importances)[::-1]
    for i in sorted_idx[:10]:
        print(f'  {feature_cols[i]:<25}: {importances[i]:.4f}')

    # 判定
    print('')
    print('【結論】')
    if diff_auc > 0.01:
        print(f'  改善版はAUCで {diff_auc:.4f} (+{diff_auc*100:.2f}%)改善')
        print('  → 新規特徴量の採用を推奨')
    elif diff_auc > 0:
        print(f'  改善版はAUCで {diff_auc:.4f} (+{diff_auc*100:.2f}%)微改善')
        print('  → 効果は限定的だが、採用しても問題なし')
    else:
        print(f'  改善版はAUCで {diff_auc:.4f} ({diff_auc*100:.2f}%)悪化')
        print('  → 新規特徴量の採用は見送り')


if __name__ == '__main__':
    main()
