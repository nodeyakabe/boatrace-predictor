#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
3年分（2023-2025）の予測を生成してCSV出力
"""
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from scripts.analysis.test_new_scores_csv_fast import generate_predictions_to_csv_fast

if __name__ == '__main__':
    output_csv = os.path.join(PROJECT_ROOT, 'temp', 'predictions_2023_2025.csv')

    print('='*80)
    print('3年分（2023-2025）の予測生成')
    print('='*80)
    print(f'出力: {output_csv}')
    print(f'推定時間: 2-4時間')
    print('='*80)

    generate_predictions_to_csv_fast('2023-01-01', '2025-12-31', output_csv)

    print('\n処理完了')
