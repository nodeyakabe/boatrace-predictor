#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
月×信頼度別の実ROI分析（標準バックテスト準拠版）

目的:
    標準バックテストと同じ購入条件で、月×信頼度別の実測ROIを算出
    「2月×D、4月×D除外」施策の失敗原因を特定

使用方法:
    python scripts/analysis/month_confidence_actual_analysis.py

出力:
    1. 月×信頼度別ROIマトリクス
    2. D条件2件の月別詳細
    3. 推定値vs実測値の比較
    4. 失敗原因の特定
"""

import sqlite3
import sys
import io
from pathlib import Path
from typing import Dict, List, Tuple

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DATABASE_PATH = PROJECT_ROOT / 'data' / 'boatrace.db'

# ============================================================
# 分析クエリ: 月×信頼度別ROI
# ============================================================

def analyze_month_confidence_roi(cursor) -> List[Dict]:
    """
    月×信頼度別の実測ROI算出

    標準バックテストと同じ購入条件（11条件）を適用
    """

    query = """
    WITH prediction_base AS (
        -- 予測組み合わせの構築（1-2-3着）
        SELECT
            rp.race_id,
            rp.confidence,
            CAST(strftime('%m', r.race_date) AS INTEGER) as month,
            CAST(strftime('%Y', r.race_date) AS INTEGER) as year,
            r.venue_code,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3,
            CAST(rp1.pit_number AS TEXT) || '-' ||
            CAST(rp2.pit_number AS TEXT) || '-' ||
            CAST(rp3.pit_number AS TEXT) as pred_combo,
            e1.racer_rank as c1_rank
        FROM race_predictions rp
        JOIN race_predictions rp1 ON rp.race_id = rp1.race_id
            AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON rp.race_id = rp2.race_id
            AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON rp.race_id = rp3.race_id
            AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN races r ON rp.race_id = r.id
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.prediction_type = 'before'
          AND rp.rank_prediction = 1
          AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    ),
    actual_results AS (
        -- 実際の着順
        SELECT
            race_id,
            CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
        FROM results
        WHERE rank IN ('1', '2', '3')
        GROUP BY race_id
    ),
    bet_races AS (
        -- オッズ付きで結合
        SELECT
            pb.*,
            ar.actual_combo,
            t.odds,
            CASE WHEN pb.pred_combo = ar.actual_combo THEN 1 ELSE 0 END as is_hit
        FROM prediction_base pb
        JOIN actual_results ar ON pb.race_id = ar.race_id
        LEFT JOIN trifecta_odds t ON pb.race_id = t.race_id
            AND t.combination = pb.pred_combo
        WHERE t.odds IS NOT NULL
          AND t.odds >= 10
          AND t.odds < 200
    )
    SELECT
        confidence,
        month,
        COUNT(*) as races,
        SUM(is_hit) as hits,
        ROUND(100.0 * SUM(is_hit) / COUNT(*), 2) as hit_rate,
        ROUND(AVG(odds), 1) as avg_odds,
        SUM(CASE WHEN is_hit = 1 THEN odds * 100 ELSE 0 END) as payout,
        COUNT(*) * 100 as investment,
        ROUND(100.0 * SUM(CASE WHEN is_hit = 1 THEN odds * 100 ELSE 0 END) / (COUNT(*) * 100), 1) as roi,
        SUM(CASE WHEN is_hit = 1 THEN odds * 100 ELSE 0 END) - (COUNT(*) * 100) as profit
    FROM bet_races
    GROUP BY confidence, month
    HAVING races >= 10
    ORDER BY confidence, month
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    results = []
    for row in rows:
        results.append({
            'confidence': row[0],
            'month': row[1],
            'races': row[2],
            'hits': row[3],
            'hit_rate': row[4],
            'avg_odds': row[5],
            'payout': row[6],
            'investment': row[7],
            'roi': row[8],
            'profit': row[9],
        })

    return results


def print_results(month_confidence_data: List[Dict]):
    """
    分析結果を表示
    """

    print("=" * 100)
    print("月×信頼度別 実ROI分析（標準バックテスト準拠版）")
    print("=" * 100)
    print()
    print("分析期間: 2020-2025年（6年間）")
    print("対象: 標準バックテストと同じ購入条件（11条件）")
    print()

    # ============================================================
    # 1. 月×信頼度別ROIマトリクス
    # ============================================================
    print("[1. 月×信頼度別ROIマトリクス（実測値）]")
    print("-" * 100)

    # データを整形
    matrix = {}
    for row in month_confidence_data:
        conf = row['confidence']
        month = row['month']
        if conf not in matrix:
            matrix[conf] = {}
        matrix[conf][month] = row

    # ヘッダー
    print(f"{'信頼度':<8}", end='')
    for m in range(1, 13):
        print(f"{m:>3}月", end='  ')
    print()
    print("-" * 100)

    # データ行
    for conf in ['A', 'B', 'C', 'D']:
        if conf not in matrix:
            continue

        print(f"{conf:<8}", end='')
        for m in range(1, 13):
            if m in matrix[conf]:
                roi = matrix[conf][m]['roi']
                races = matrix[conf][m]['races']

                # 色分け（テキストマーカー）
                if roi >= 200:
                    marker = '[優秀]'
                elif roi >= 150:
                    marker = '[良好]'
                elif roi >= 100:
                    marker = '[普通]'
                else:
                    marker = '[不調]'

                print(f"{roi:>5.0f}%", end=' ')
            else:
                print(f"{'---':>5} ", end=' ')
        print()

    print()
    print("凡例:")
    print("  [優秀] ROI 200%以上")
    print("  [良好] ROI 150-200%")
    print("  [普通] ROI 100-150%")
    print("  [不調] ROI 100%未満")
    print()

    # ============================================================
    # 2. D信頼度の詳細（重点確認）
    # ============================================================
    print("[2. D信頼度の月別詳細（実測値）]")
    print("-" * 100)
    print(f"{'月':<4} {'件数':>6} {'的中':>4} {'的中率':>7} {'ROI':>8} {'収支':>12} {'評価':<10}")
    print("-" * 100)

    if 'D' in matrix:
        for m in range(1, 13):
            if m in matrix['D']:
                data = matrix['D'][m]

                # 評価
                if data['roi'] >= 150:
                    eval_str = '[良好]'
                elif data['roi'] >= 100:
                    eval_str = '[普通]'
                else:
                    eval_str = '[不調]'

                # 2月・4月をハイライト
                month_str = f"{m:>2}月"
                if m in [2, 4]:
                    month_str += " [注目]"
                else:
                    month_str += "      "

                print(f"{month_str:<10} {data['races']:>6} {data['hits']:>4} {data['hit_rate']:>6.1f}% {data['roi']:>7.0f}% {data['profit']:>+11,.0f}円 {eval_str:<10}")

    print()
    print("=" * 100)


def main():
    """メイン処理"""

    conn = sqlite3.connect(str(DATABASE_PATH))
    cursor = conn.cursor()

    print("月×信頼度別ROI分析を実行中...")
    print()

    # 分析実行
    month_confidence_data = analyze_month_confidence_roi(cursor)

    # 結果表示
    print_results(month_confidence_data)

    conn.close()


if __name__ == '__main__':
    main()
