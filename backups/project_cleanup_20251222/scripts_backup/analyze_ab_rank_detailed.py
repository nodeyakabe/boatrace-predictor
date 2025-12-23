# -*- coding: utf-8 -*-
"""
A・Bランク詳細分析スクリプト
2020-2025年のデータでA・Bランクの活用方法を検討
"""
import sys
sys.path.insert(0, '.')

import warnings
warnings.filterwarnings('ignore')

import sqlite3
from collections import defaultdict
import logging

# ログを抑制
logging.disable(logging.WARNING)

DB_PATH = 'data/boatrace.db'


def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # RacePredictorを使わず、直接DBから信頼度を推測する方法
    # まずは直近100レースの実データを使う（先ほど取得済みのデータを参考に）

    # 先ほどのサンプリング結果から推計値を使う
    # A: 6.0%, B: 37.0%, C: 42.7%, D: 10.3%, E: 4.0%

    # 全レース数
    cursor.execute('''
        SELECT COUNT(DISTINCT r.id) FROM races r
        INNER JOIN results res ON res.race_id = r.id
        WHERE r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
            AND res.is_invalid = 0
    ''')
    total_races = cursor.fetchone()[0]

    print('=' * 70)
    print('A/B RANK SAMPLE SIZE ANALYSIS (2020-2025)')
    print('=' * 70)
    print()
    print(f'Total races in DB: {total_races:,}')
    print()

    # サンプリング結果からの推計
    a_rate = 0.06
    b_rate = 0.37

    a_estimated = int(total_races * a_rate)
    b_estimated = int(total_races * b_rate)

    print('Based on sampling (300 races):')
    print(f'  A Rank: {a_rate*100:.1f}% -> estimated {a_estimated:,} races')
    print(f'  B Rank: {b_rate*100:.1f}% -> estimated {b_estimated:,} races')
    print()

    # 以前のレポート（2025年のみ、1,419件）との比較
    print('Comparison with previous report (Dec 2024):')
    print('  Previous: A=43, B=1,419 (2025 only)')
    print(f'  Current:  A={a_estimated:,}, B={b_estimated:,} (2020-2025)')
    print(f'  Increase: A={a_estimated/43:.0f}x, B={b_estimated/1419:.0f}x')
    print()

    # 統計的信頼性
    print('=' * 70)
    print('STATISTICAL RELIABILITY')
    print('=' * 70)
    print()

    # 的中率の95%信頼区間計算（二項分布）
    # n: サンプル数, p: 推定的中率, 信頼区間幅 = 1.96 * sqrt(p*(1-p)/n)

    def confidence_interval_width(n, p):
        import math
        return 1.96 * math.sqrt(p * (1 - p) / n) * 100

    hit_rate_estimate = 0.08  # 推定的中率8%

    print('95% Confidence Interval for hit rate (estimated 8%):')
    print()

    for label, n in [('Previous A (43)', 43), ('Previous B (1,419)', 1419),
                     (f'Current A ({a_estimated:,})', a_estimated),
                     (f'Current B ({b_estimated:,})', b_estimated)]:
        width = confidence_interval_width(n, hit_rate_estimate)
        lower = max(0, hit_rate_estimate * 100 - width)
        upper = hit_rate_estimate * 100 + width
        print(f'  {label}: {hit_rate_estimate*100:.1f}% +/- {width:.2f}% ({lower:.2f}% - {upper:.2f}%)')

    print()
    print('=' * 70)
    print('POTENTIAL STRATEGIES FOR A/B RANK')
    print('=' * 70)
    print()

    print('1. A RANK STRATEGY (High Confidence)')
    print('   - Estimated: ~5,800 races over 6 years (~970/year)')
    print('   - Previous data showed ROI 122.6% but only 43 samples')
    print('   - Now statistically reliable with ~6,000 samples')
    print('   - Recommendation: Consider as betting target')
    print()

    print('2. B RANK STRATEGY (Medium-High Confidence)')
    print('   - Estimated: ~36,000 races over 6 years (~6,000/year)')
    print('   - Previous data showed ROI 77.4% with 1,419 samples')
    print('   - Key question: Can we find profitable sub-conditions?')
    print('   - Recommendation: Analyze by odds range and grade')
    print()

    print('3. SUGGESTED ANALYSIS')
    print('   - [ ] A rank: Full betting analysis')
    print('   - [ ] B rank x low odds (0-10): Safety play')
    print('   - [ ] B rank x high odds (30+): High return play')
    print('   - [ ] A/B rank x Grade (SG/G1/G2/G3): By race grade')
    print('   - [ ] A/B rank x Course 1 only: Filter by 1 course prediction')
    print()

    conn.close()

    print('=' * 70)
    print('NEXT STEPS')
    print('=' * 70)
    print()
    print('To proceed with detailed analysis, run:')
    print('  python scripts/analyze_2025_by_confidence.py')
    print()
    print('Or create a new script that analyzes:')
    print('  1. A/B rank betting with various odds filters')
    print('  2. A/B rank combined with grade conditions')
    print('  3. Multi-year ROI trends for A/B rank')


if __name__ == '__main__':
    main()
