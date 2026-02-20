#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
高速化効果をテストするスクリプト（2025年1月のみ）
"""
import sys
import os
import time

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from scripts.analysis.test_new_scores_csv_fast import generate_predictions_to_csv_fast

if __name__ == '__main__':
    output_csv = os.path.join(PROJECT_ROOT, 'temp', 'speed_test_2025_01.csv')

    print('='*80)
    print('高速化版のスピードテスト（2025年1月）')
    print('='*80)

    start_time = time.time()

    generate_predictions_to_csv_fast('2025-01-01', '2025-01-31', output_csv)

    elapsed = time.time() - start_time

    print(f'\n{"="*80}')
    print(f'実行時間: {elapsed:.1f}秒 ({elapsed/60:.2f}分)')
    print(f'{"="*80}')

    # 10ヶ月分の見積もり
    estimated_full = elapsed * 10
    print(f'\n推定: 10ヶ月分なら約{estimated_full:.1f}秒 ({estimated_full/60:.2f}分)')
