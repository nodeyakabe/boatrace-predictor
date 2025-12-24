# -*- coding: utf-8 -*-
"""
2025年データでモーター40%+条件の効果を詳細分析するスクリプト

【目的】
- なぜC×A2、C×B1でモーター40%+が逆効果になるのかを解明
- 既存条件との干渉を分析
- 実装推奨を提示
"""

import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def analyze_motor_effect():
    """モーター40%+条件の効果を信頼度×級別で分析"""

    conn = sqlite3.connect(project_root / 'data' / 'boatrace.db')
    cur = conn.cursor()

    print("=" * 120)
    print("2025年データ: モーター40%+条件の効果分析")
    print("=" * 120)

    # 1. 基本統計: 信頼度×級別×モーター条件別のパフォーマンス
    query = '''
    WITH race_data AS (
        SELECT DISTINCT
            rp.race_id,
            rp.confidence,
            r.venue_code
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE r.race_date >= '2025-01-01'
          AND r.race_date < '2025-12-01'
          AND rp.prediction_type = 'before'
          AND rp.confidence IN ('A', 'B', 'C', 'D')
    ),
    entries_with_motor AS (
        SELECT
            rd.race_id,
            rd.confidence,
            rd.venue_code,
            e.racer_rank as c1_rank,
            COALESCE(e.motor_second_rate, 0) as motor_2rate
        FROM race_data rd
        JOIN entries e ON rd.race_id = e.race_id AND e.pit_number = 1
        WHERE e.racer_rank IN ('A1', 'A2', 'B1', 'B2')
    ),
    predictions AS (
        SELECT
            em.*,
            GROUP_CONCAT(
                CAST(rp.pit_number AS TEXT)
                ORDER BY rp.rank_prediction
            ) as predicted_combination
        FROM entries_with_motor em
        JOIN race_predictions rp ON em.race_id = rp.race_id
        WHERE rp.prediction_type = 'before'
        GROUP BY em.race_id
    ),
    with_results AS (
        SELECT
            p.confidence,
            p.c1_rank,
            p.motor_2rate,
            p.venue_code,
            p.predicted_combination,
            CASE
                WHEN r1.rank = '1' AND r2.rank = '2' AND r3.rank = '3' THEN 1
                ELSE 0
            END as is_hit,
            COALESCE(pay.amount, 0) as payout
        FROM predictions p
        LEFT JOIN results r1 ON p.race_id = r1.race_id
            AND r1.pit_number = CAST(SUBSTR(p.predicted_combination, 1, 1) AS INTEGER)
        LEFT JOIN results r2 ON p.race_id = r2.race_id
            AND r2.pit_number = CAST(SUBSTR(p.predicted_combination, 2, 1) AS INTEGER)
        LEFT JOIN results r3 ON p.race_id = r3.race_id
            AND r3.pit_number = CAST(SUBSTR(p.predicted_combination, 3, 1) AS INTEGER)
        LEFT JOIN payouts pay ON p.race_id = pay.race_id
            AND pay.bet_type = 'trifecta'
            AND pay.combination =
                SUBSTR(p.predicted_combination, 1, 1) || '-' ||
                SUBSTR(p.predicted_combination, 2, 1) || '-' ||
                SUBSTR(p.predicted_combination, 3, 1)
    )
    SELECT
        confidence,
        c1_rank,
        CASE WHEN motor_2rate >= 40 THEN 'motor_40+' ELSE 'motor_other' END as motor_cond,
        COUNT(*) as sample,
        SUM(is_hit) as hits,
        ROUND(100.0 * SUM(is_hit) / COUNT(*), 2) as hit_rate,
        SUM(payout) as total_return,
        SUM(100) as total_cost,
        ROUND(100.0 * SUM(payout) / SUM(100), 1) as roi,
        ROUND(AVG(motor_2rate), 1) as avg_motor_rate
    FROM with_results
    GROUP BY confidence, c1_rank, motor_cond
    HAVING sample >= 5
    ORDER BY confidence, c1_rank, motor_cond
    '''

    cur.execute(query)
    results = cur.fetchall()

    print("\n【基本統計】信頼度×級別×モーター条件別パフォーマンス")
    print("-" * 120)
    print(f"{'信頼度':6} {'級別':4} {'モーター条件':15} {'件数':6} {'的中':6} {'的中率':8} {'回収額':12} {'投資額':10} {'ROI':8} {'平均モーター率':15}")
    print("-" * 120)

    # データを整理
    performance_data = defaultdict(dict)
    for row in results:
        key = (row[0], row[1])  # (confidence, c1_rank)
        motor_cond = row[2]
        performance_data[key][motor_cond] = {
            'sample': row[3],
            'hits': row[4],
            'hit_rate': row[5],
            'total_return': row[6],
            'total_cost': row[7],
            'roi': row[8],
            'avg_motor_rate': row[9]
        }
        print(f"{row[0]:6} {row[1]:4} {row[2]:15} {row[3]:6} {row[4]:6} {row[5]:7}% {row[6]:12,} {row[7]:10,} {row[8]:7}% {row[9]:15.1f}%")

    # 2. 効果分析: モーター40%+によるROI変化
    print("\n" + "=" * 120)
    print("【効果分析】モーター40%+条件追加によるROI変化")
    print("=" * 120)
    print(f"{'信頼度':6} {'級別':4} {'Other ROI':12} {'Motor40+ ROI':16} {'ROI差分':10} {'判定':10} {'Other件数':12} {'Motor40+件数':16}")
    print("-" * 120)

    effect_summary = []
    for key in sorted(performance_data.keys()):
        confidence, c1_rank = key
        if 'motor_other' in performance_data[key] and 'motor_40+' in performance_data[key]:
            other = performance_data[key]['motor_other']
            motor40 = performance_data[key]['motor_40+']
            roi_diff = motor40['roi'] - other['roi']

            # 判定
            if roi_diff >= 100:
                judgment = "✅大幅改善"
            elif roi_diff >= 50:
                judgment = "✅改善"
            elif roi_diff >= 0:
                judgment = "△小幅改善"
            elif roi_diff >= -50:
                judgment = "⚠小幅悪化"
            else:
                judgment = "❌大幅悪化"

            effect_summary.append({
                'confidence': confidence,
                'c1_rank': c1_rank,
                'other_roi': other['roi'],
                'motor40_roi': motor40['roi'],
                'roi_diff': roi_diff,
                'judgment': judgment,
                'other_sample': other['sample'],
                'motor40_sample': motor40['sample']
            })

            print(f"{confidence:6} {c1_rank:4} {other['roi']:11.1f}% {motor40['roi']:15.1f}% {roi_diff:+9.1f}pt {judgment:10} {other['sample']:12} {motor40['sample']:16}")

    # 3. 逆効果パターンの深掘り
    print("\n" + "=" * 120)
    print("【逆効果パターン分析】ROI悪化ケースの詳細")
    print("=" * 120)

    negative_cases = [e for e in effect_summary if e['roi_diff'] < 0]
    if negative_cases:
        for case in sorted(negative_cases, key=lambda x: x['roi_diff']):
            print(f"\n■ {case['confidence']} × {case['c1_rank']}: ROI {case['roi_diff']:+.1f}pt 悪化")
            print(f"  - Other: {case['other_sample']}件, ROI {case['other_roi']:.1f}%")
            print(f"  - Motor40+: {case['motor40_sample']}件, ROI {case['motor40_roi']:.1f}%")

            # 会場別の傾向を分析
            analyze_venue_bias(cur, case['confidence'], case['c1_rank'])

            # オッズ分布を確認
            analyze_odds_distribution(cur, case['confidence'], case['c1_rank'])

    # 4. 改善効果パターンの詳細
    print("\n" + "=" * 120)
    print("【改善効果パターン分析】ROI改善ケースの詳細")
    print("=" * 120)

    positive_cases = [e for e in effect_summary if e['roi_diff'] >= 100]
    if positive_cases:
        for case in sorted(positive_cases, key=lambda x: x['roi_diff'], reverse=True)[:5]:
            print(f"\n■ {case['confidence']} × {case['c1_rank']}: ROI {case['roi_diff']:+.1f}pt 改善")
            print(f"  - Other: {case['other_sample']}件, ROI {case['other_roi']:.1f}%")
            print(f"  - Motor40+: {case['motor40_sample']}件, ROI {case['motor40_roi']:.1f}%")

    conn.close()

    return effect_summary

def analyze_venue_bias(cur, confidence, c1_rank):
    """会場別の偏りを分析"""
    query = '''
    WITH race_data AS (
        SELECT DISTINCT
            rp.race_id,
            r.venue_code,
            vd.venue_name
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        JOIN venue_data vd ON r.venue_code = vd.venue_code
        WHERE r.race_date >= '2025-01-01'
          AND r.race_date < '2025-12-01'
          AND rp.prediction_type = 'before'
          AND rp.confidence = ?
    ),
    entries_with_motor AS (
        SELECT
            rd.*,
            e.racer_rank,
            COALESCE(e.motor_second_rate, 0) as motor_2rate
        FROM race_data rd
        JOIN entries e ON rd.race_id = e.race_id AND e.pit_number = 1
        WHERE e.racer_rank = ?
    )
    SELECT
        venue_name,
        CASE WHEN motor_2rate >= 40 THEN 'motor_40+' ELSE 'motor_other' END as motor_cond,
        COUNT(*) as sample
    FROM entries_with_motor
    GROUP BY venue_name, motor_cond
    HAVING sample >= 3
    ORDER BY venue_name, motor_cond
    '''

    cur.execute(query, (confidence, c1_rank))
    results = cur.fetchall()

    if results:
        print(f"\n  【会場別分布】")
        venue_data = defaultdict(dict)
        for row in results:
            venue_data[row[0]][row[1]] = row[2]

        for venue in sorted(venue_data.keys()):
            other = venue_data[venue].get('motor_other', 0)
            motor40 = venue_data[venue].get('motor_40+', 0)
            total = other + motor40
            motor40_ratio = 100.0 * motor40 / total if total > 0 else 0
            print(f"    {venue:10}: Other {other:3}件, Motor40+ {motor40:3}件 (Motor40+比率: {motor40_ratio:.1f}%)")

def analyze_odds_distribution(cur, confidence, c1_rank):
    """オッズ分布を分析（既存条件との干渉チェック）"""
    query = '''
    WITH race_data AS (
        SELECT DISTINCT
            rp.race_id
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE r.race_date >= '2025-01-01'
          AND r.race_date < '2025-12-01'
          AND rp.prediction_type = 'before'
          AND rp.confidence = ?
    ),
    entries_with_motor AS (
        SELECT
            rd.race_id,
            e.racer_rank,
            COALESCE(e.motor_second_rate, 0) as motor_2rate
        FROM race_data rd
        JOIN entries e ON rd.race_id = e.race_id AND e.pit_number = 1
        WHERE e.racer_rank = ?
    ),
    predictions AS (
        SELECT
            em.*,
            GROUP_CONCAT(
                CAST(rp.pit_number AS TEXT)
                ORDER BY rp.rank_prediction
            ) as predicted_combination
        FROM entries_with_motor em
        JOIN race_predictions rp ON em.race_id = rp.race_id
        WHERE rp.prediction_type = 'before'
        GROUP BY em.race_id
    ),
    with_odds AS (
        SELECT
            p.motor_2rate,
            COALESCE(o.odds, 0) as odds
        FROM predictions p
        LEFT JOIN trifecta_odds o ON p.race_id = o.race_id
            AND o.combination =
                SUBSTR(p.predicted_combination, 1, 1) || '-' ||
                SUBSTR(p.predicted_combination, 2, 1) || '-' ||
                SUBSTR(p.predicted_combination, 3, 1)
    )
    SELECT
        CASE WHEN motor_2rate >= 40 THEN 'motor_40+' ELSE 'motor_other' END as motor_cond,
        COUNT(*) as sample,
        ROUND(AVG(odds), 1) as avg_odds,
        ROUND(MIN(odds), 1) as min_odds,
        ROUND(MAX(odds), 1) as max_odds,
        SUM(CASE WHEN odds BETWEEN 20 AND 30 THEN 1 ELSE 0 END) as odds_20_30,
        SUM(CASE WHEN odds BETWEEN 30 AND 50 THEN 1 ELSE 0 END) as odds_30_50,
        SUM(CASE WHEN odds >= 50 THEN 1 ELSE 0 END) as odds_50plus
    FROM with_odds
    WHERE odds > 0
    GROUP BY motor_cond
    '''

    cur.execute(query, (confidence, c1_rank))
    results = cur.fetchall()

    if results:
        print(f"\n  【オッズ分布】")
        print(f"    {'条件':15} {'件数':6} {'平均':8} {'最小':8} {'最大':8} {'20-30倍':10} {'30-50倍':10} {'50倍+':8}")
        for row in results:
            print(f"    {row[0]:15} {row[1]:6} {row[2]:8.1f} {row[3]:8.1f} {row[4]:8.1f} {row[5]:10} {row[6]:10} {row[7]:8}")

def main():
    print("\n2025年データでモーター40%+条件の詳細分析を開始します...")
    print("分析対象: before予測（2025年1-11月）\n")

    effect_summary = analyze_motor_effect()

    # 実装推奨の提示
    print("\n" + "=" * 120)
    print("【実装推奨】")
    print("=" * 120)

    # ROI改善が大きい順に上位5件
    top_improvements = sorted([e for e in effect_summary if e['roi_diff'] >= 0],
                             key=lambda x: x['roi_diff'], reverse=True)[:5]

    print("\n✅ 採用推奨（ROI改善効果が大きい条件）")
    for i, case in enumerate(top_improvements, 1):
        print(f"{i}. {case['confidence']} × {case['c1_rank']} × モーター40%+")
        print(f"   ROI: {case['other_roi']:.1f}% → {case['motor40_roi']:.1f}% (+{case['roi_diff']:.1f}pt)")
        print(f"   サンプル: {case['motor40_sample']}件")

    # ROI悪化が大きい順に上位3件
    worst_cases = sorted([e for e in effect_summary if e['roi_diff'] < 0],
                        key=lambda x: x['roi_diff'])[:3]

    if worst_cases:
        print("\n❌ 不採用推奨（ROI悪化する条件）")
        for i, case in enumerate(worst_cases, 1):
            print(f"{i}. {case['confidence']} × {case['c1_rank']} × モーター40%+")
            print(f"   ROI: {case['other_roi']:.1f}% → {case['motor40_roi']:.1f}% ({case['roi_diff']:.1f}pt)")
            print(f"   サンプル: {case['motor40_sample']}件")

    print("\n分析完了！")

if __name__ == '__main__':
    main()
