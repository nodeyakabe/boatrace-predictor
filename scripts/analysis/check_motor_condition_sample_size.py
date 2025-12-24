# -*- coding: utf-8 -*-
"""
モーター40%+条件のサンプル数・オッズ帯を確認するスクリプト

採用推奨条件:
1. A × B1 × モーター40%+
2. D × A1 × モーター40%+
3. D × B1 × モーター40%+

確認項目:
- サンプル数（2025年、および2020-2025年の各年）
- オッズ分布
- 的中率・ROI
"""

import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def analyze_condition(cur, confidence, c1_rank, motor_min=40):
    """特定条件のサンプル数・オッズ帯・ROIを分析"""

    print(f"\n{'='*100}")
    print(f"条件: {confidence} × {c1_rank} × モーター{motor_min}%+")
    print(f"{'='*100}")

    # 年度別のサンプル数・ROI
    query = '''
    WITH predictions AS (
        SELECT DISTINCT
            rp.race_id,
            r.race_date,
            SUBSTR(r.race_date, 1, 4) as year,
            GROUP_CONCAT(
                CAST(rp.pit_number AS TEXT)
                ORDER BY rp.rank_prediction
            ) as pred_combo
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE rp.confidence = ?
          AND rp.prediction_type = 'before'
          AND r.race_date >= '2020-01-01'
        GROUP BY rp.race_id
    ),
    with_entries AS (
        SELECT
            p.*,
            e.racer_rank,
            COALESCE(e.motor_second_rate, 0) as motor_2rate
        FROM predictions p
        JOIN entries e ON p.race_id = e.race_id AND e.pit_number = 1
        WHERE e.racer_rank = ?
          AND e.motor_second_rate >= ?
    ),
    with_odds AS (
        SELECT
            we.*,
            COALESCE(o.odds, 0) as odds
        FROM with_entries we
        LEFT JOIN trifecta_odds o ON we.race_id = o.race_id
            AND o.combination =
                SUBSTR(we.pred_combo, 1, 1) || '-' ||
                SUBSTR(we.pred_combo, 2, 1) || '-' ||
                SUBSTR(we.pred_combo, 3, 1)
    ),
    with_results AS (
        SELECT
            wo.*,
            CASE
                WHEN r1.rank = '1' AND r2.rank = '2' AND r3.rank = '3' THEN 1
                ELSE 0
            END as is_hit,
            COALESCE(pay.amount, 0) as payout
        FROM with_odds wo
        LEFT JOIN results r1 ON wo.race_id = r1.race_id
            AND r1.pit_number = CAST(SUBSTR(wo.pred_combo, 1, 1) AS INTEGER)
        LEFT JOIN results r2 ON wo.race_id = r2.race_id
            AND r2.pit_number = CAST(SUBSTR(wo.pred_combo, 2, 1) AS INTEGER)
        LEFT JOIN results r3 ON wo.race_id = r3.race_id
            AND r3.pit_number = CAST(SUBSTR(wo.pred_combo, 3, 1) AS INTEGER)
        LEFT JOIN payouts pay ON wo.race_id = pay.race_id
            AND pay.bet_type = 'trifecta'
            AND pay.combination =
                SUBSTR(wo.pred_combo, 1, 1) || '-' ||
                SUBSTR(wo.pred_combo, 2, 1) || '-' ||
                SUBSTR(wo.pred_combo, 3, 1)
    )
    SELECT
        year,
        COUNT(*) as sample,
        COUNT(CASE WHEN odds > 0 THEN 1 END) as with_odds,
        SUM(is_hit) as hits,
        ROUND(100.0 * SUM(is_hit) / COUNT(*), 2) as hit_rate,
        SUM(payout) as total_return,
        SUM(100) as total_cost,
        ROUND(100.0 * SUM(payout) / SUM(100), 1) as roi,
        ROUND(AVG(CASE WHEN odds > 0 THEN odds END), 1) as avg_odds,
        ROUND(MIN(CASE WHEN odds > 0 THEN odds END), 1) as min_odds,
        ROUND(MAX(CASE WHEN odds > 0 THEN odds END), 1) as max_odds
    FROM with_results
    GROUP BY year
    ORDER BY year
    '''

    cur.execute(query, (confidence, c1_rank, motor_min))
    results = cur.fetchall()

    print(f"\n年度別サンプル数・ROI:")
    print(f"{'年度':6} {'サンプル':8} {'オッズあり':10} {'的中':6} {'的中率':8} {'ROI':8} {'平均オッズ':10} {'最小-最大オッズ':20}")
    print("-"*100)

    total_sample = 0
    total_hits = 0
    total_return = 0
    total_cost = 0
    positive_roi_years = 0

    for row in results:
        year, sample, with_odds, hits, hit_rate, total_ret, cost, roi, avg_odds, min_odds, max_odds = row
        total_sample += sample
        total_hits += hits
        total_return += total_ret
        total_cost += cost

        if roi >= 100:
            positive_roi_years += 1

        odds_range = f"{min_odds:.1f} - {max_odds:.1f}" if min_odds and max_odds else "N/A"
        print(f"{year:6} {sample:8} {with_odds:10} {hits:6} {hit_rate:7.2f}% {roi:7.1f}% {avg_odds:10.1f} {odds_range:20}")

    overall_roi = 100.0 * total_return / total_cost if total_cost > 0 else 0
    overall_hit_rate = 100.0 * total_hits / total_sample if total_sample > 0 else 0

    print("-"*100)
    print(f"{'合計':6} {total_sample:8} {'-':10} {total_hits:6} {overall_hit_rate:7.2f}% {overall_roi:7.1f}%")

    # 統計的信頼性の評価
    print(f"\n統計的信頼性評価:")
    print(f"  - 6年間合計サンプル: {total_sample}件")
    if total_sample >= 600:
        print(f"    -> OK（年間平均100件以上）")
    elif total_sample >= 300:
        print(f"    -> 注意（年間平均50-100件）")
    else:
        print(f"    -> NG（サンプル不足）")

    print(f"  - 黒字年数: {positive_roi_years}/6年")
    if positive_roi_years >= 5:
        print(f"    -> OK（高安定性）")
    elif positive_roi_years >= 4:
        print(f"    -> 注意（中安定性）")
    else:
        print(f"    -> NG（不安定）")

    print(f"  - 6年間平均ROI: {overall_roi:.1f}%")
    if overall_roi >= 150:
        print(f"    -> 優秀")
    elif overall_roi >= 120:
        print(f"    -> 良好")
    elif overall_roi >= 100:
        print(f"    -> 黒字")
    else:
        print(f"    -> 赤字（採用見送り）")

    # 最適オッズ帯の推定
    print(f"\nオッズ分布（2024-2025年データ）:")
    analyze_odds_distribution(cur, confidence, c1_rank, motor_min)

    return {
        'total_sample': total_sample,
        'positive_roi_years': positive_roi_years,
        'overall_roi': overall_roi,
    }

def analyze_odds_distribution(cur, confidence, c1_rank, motor_min):
    """オッズ分布を分析して最適オッズ帯を推定"""

    query = '''
    WITH predictions AS (
        SELECT DISTINCT
            rp.race_id,
            GROUP_CONCAT(
                CAST(rp.pit_number AS TEXT)
                ORDER BY rp.rank_prediction
            ) as pred_combo
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE rp.confidence = ?
          AND rp.prediction_type = 'before'
          AND r.race_date >= '2024-01-01'
        GROUP BY rp.race_id
    ),
    with_entries AS (
        SELECT
            p.*,
            e.racer_rank,
            COALESCE(e.motor_second_rate, 0) as motor_2rate
        FROM predictions p
        JOIN entries e ON p.race_id = e.race_id AND e.pit_number = 1
        WHERE e.racer_rank = ?
          AND e.motor_second_rate >= ?
    ),
    with_odds AS (
        SELECT
            we.*,
            COALESCE(o.odds, 0) as odds
        FROM with_entries we
        LEFT JOIN trifecta_odds o ON we.race_id = o.race_id
            AND o.combination =
                SUBSTR(we.pred_combo, 1, 1) || '-' ||
                SUBSTR(we.pred_combo, 2, 1) || '-' ||
                SUBSTR(we.pred_combo, 3, 1)
        WHERE o.odds > 0
    ),
    with_results AS (
        SELECT
            wo.*,
            CASE
                WHEN r1.rank = '1' AND r2.rank = '2' AND r3.rank = '3' THEN 1
                ELSE 0
            END as is_hit,
            COALESCE(pay.amount, 0) as payout
        FROM with_odds wo
        LEFT JOIN results r1 ON wo.race_id = r1.race_id
            AND r1.pit_number = CAST(SUBSTR(wo.pred_combo, 1, 1) AS INTEGER)
        LEFT JOIN results r2 ON wo.race_id = r2.race_id
            AND r2.pit_number = CAST(SUBSTR(wo.pred_combo, 2, 1) AS INTEGER)
        LEFT JOIN results r3 ON wo.race_id = r3.race_id
            AND r3.pit_number = CAST(SUBSTR(wo.pred_combo, 3, 1) AS INTEGER)
        LEFT JOIN payouts pay ON wo.race_id = pay.race_id
            AND pay.bet_type = 'trifecta'
            AND pay.combination =
                SUBSTR(wo.pred_combo, 1, 1) || '-' ||
                SUBSTR(wo.pred_combo, 2, 1) || '-' ||
                SUBSTR(wo.pred_combo, 3, 1)
    )
    SELECT
        CASE
            WHEN odds < 20 THEN '< 20'
            WHEN odds < 30 THEN '20-30'
            WHEN odds < 40 THEN '30-40'
            WHEN odds < 50 THEN '40-50'
            WHEN odds < 60 THEN '50-60'
            WHEN odds < 80 THEN '60-80'
            WHEN odds < 100 THEN '80-100'
            ELSE '100+'
        END as odds_range,
        COUNT(*) as sample,
        SUM(is_hit) as hits,
        ROUND(100.0 * SUM(is_hit) / COUNT(*), 2) as hit_rate,
        SUM(payout) as total_return,
        SUM(100) as total_cost,
        ROUND(100.0 * SUM(payout) / SUM(100), 1) as roi
    FROM with_results
    GROUP BY odds_range
    ORDER BY
        CASE odds_range
            WHEN '< 20' THEN 1
            WHEN '20-30' THEN 2
            WHEN '30-40' THEN 3
            WHEN '40-50' THEN 4
            WHEN '50-60' THEN 5
            WHEN '60-80' THEN 6
            WHEN '80-100' THEN 7
            ELSE 8
        END
    '''

    cur.execute(query, (confidence, c1_rank, motor_min))
    results = cur.fetchall()

    print(f"  {'オッズ帯':10} {'サンプル':8} {'的中':6} {'的中率':8} {'ROI':8}")
    print("  " + "-"*60)
    for row in results:
        odds_range, sample, hits, hit_rate, total_ret, cost, roi = row
        marker = " <-" if roi >= 120 else ""
        print(f"  {odds_range:10} {sample:8} {hits:6} {hit_rate:7.2f}% {roi:7.1f}%{marker}")

    print(f"\n  推奨オッズ帯: ROI 120%以上のオッズ帯を採用")

def main():
    conn = sqlite3.connect(project_root / 'data' / 'boatrace.db')
    cur = conn.cursor()

    print("\n" + "="*100)
    print("モーター40%+条件のサンプル数・オッズ帯確認")
    print("="*100)

    # 採用推奨条件を順に分析
    conditions = [
        ('A', 'B1', 40),
        ('D', 'A1', 40),
        ('D', 'B1', 40),
    ]

    results_summary = []
    for conf, rank, motor_min in conditions:
        result = analyze_condition(cur, conf, rank, motor_min)
        results_summary.append({
            'condition': f"{conf} × {rank} × motor{motor_min}+",
            **result
        })

    # サマリー
    print("\n" + "="*100)
    print("サマリー")
    print("="*100)
    print(f"\n{'条件':30} {'6年間サンプル':15} {'黒字年数':10} {'平均ROI':10} {'判定':15}")
    print("-"*100)

    for res in results_summary:
        judgment = ""
        if res['overall_roi'] >= 100 and res['positive_roi_years'] >= 5 and res['total_sample'] >= 600:
            judgment = "本番採用可"
        elif res['overall_roi'] >= 100 and res['positive_roi_years'] >= 4 and res['total_sample'] >= 300:
            judgment = "ペーパートレード"
        else:
            judgment = "要検討"

        print(f"{res['condition']:30} {res['total_sample']:15} {res['positive_roi_years']:10}/6年 {res['overall_roi']:9.1f}% {judgment:15}")

    conn.close()

    print("\n次のステップ:")
    print("1. 既存条件との重複確認: python scripts/analysis/check_condition_overlap.py")
    print("2. 詳細バックテスト実施: python scripts/backtest/backtest_motor_conditions_6years.py")

if __name__ == '__main__':
    main()
