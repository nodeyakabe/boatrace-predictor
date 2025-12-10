# -*- coding: utf-8 -*-
"""
信頼度B,C,D別の問題点分析

目的:
1. 信頼度B: 購入対象レース少・3連単的中率20%の原因分析
2. 信頼度C,D: 現状ロジックの偏り（イン・A1重視）の影響度分析
3. 中穴に適した法則性の発見
"""

import sys
import sqlite3
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple
import json

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

DB_PATH = 'data/boatrace.db'


def analyze_confidence_b_issues():
    """信頼度Bの問題点を分析"""

    print("=" * 80)
    print("信頼度B 問題点分析")
    print("=" * 80)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 信頼度B予想のレース数
    cursor.execute('''
        SELECT COUNT(DISTINCT race_id) as total
        FROM race_predictions
        WHERE confidence = 'B' AND prediction_type = 'advance'
    ''')
    total_b = cursor.fetchone()['total']
    print(f"\n1. 信頼度Bレース数: {total_b:,}件")

    # 1着的中率
    cursor.execute('''
        SELECT
            COUNT(DISTINCT p.race_id) as total,
            SUM(CASE WHEN res.rank = 1 THEN 1 ELSE 0 END) as first_hit
        FROM race_predictions p
        JOIN results res ON p.race_id = res.race_id AND p.pit_number = res.pit_number
        WHERE p.confidence = 'B'
          AND p.prediction_type = 'advance'
          AND p.rank_prediction = 1
          AND res.is_invalid = 0
    ''')
    row = cursor.fetchone()
    first_acc = (row['first_hit'] / row['total'] * 100) if row['total'] > 0 else 0
    print(f"   1着的中率: {first_acc:.2f}% ({row['first_hit']}/{row['total']})")

    # 3連単的中率
    cursor.execute('''
        SELECT
            COUNT(*) as total,
            SUM(CASE
                WHEN EXISTS (
                    SELECT 1 FROM results r1, results r2, results r3
                    WHERE r1.race_id = p1.race_id AND r1.rank = 1 AND r1.pit_number = p1.pit_number
                      AND r2.race_id = p1.race_id AND r2.rank = 2 AND r2.pit_number = p2.pit_number
                      AND r3.race_id = p1.race_id AND r3.rank = 3 AND r3.pit_number = p3.pit_number
                      AND r1.is_invalid = 0 AND r2.is_invalid = 0 AND r3.is_invalid = 0
                )
                THEN 1 ELSE 0
            END) as trifecta_hit
        FROM race_predictions p1
        JOIN race_predictions p2 ON p1.race_id = p2.race_id
            AND p2.confidence = 'B' AND p2.rank_prediction = 2 AND p2.prediction_type = 'advance'
        JOIN race_predictions p3 ON p1.race_id = p3.race_id
            AND p3.confidence = 'B' AND p3.rank_prediction = 3 AND p3.prediction_type = 'advance'
        WHERE p1.confidence = 'B' AND p1.rank_prediction = 1 AND p1.prediction_type = 'advance'
    ''')
    row = cursor.fetchone()
    trifecta_acc = (row['trifecta_hit'] / row['total'] * 100) if row['total'] > 0 else 0
    print(f"   3連単的中率: {trifecta_acc:.2f}% ({row['trifecta_hit']}/{row['total']})")

    # オッズ分布
    print(f"\n2. 信頼度Bのオッズ分布:")
    cursor.execute('''
        SELECT
            CASE
                WHEN odds < 10 THEN '～10倍'
                WHEN odds < 20 THEN '10～20倍'
                WHEN odds < 30 THEN '20～30倍'
                WHEN odds < 50 THEN '30～50倍'
                ELSE '50倍～'
            END as odds_range,
            COUNT(*) as count,
            AVG(odds) as avg_odds
        FROM (
            SELECT DISTINCT
                p1.race_id,
                p1.pit_number || '-' || p2.pit_number || '-' || p3.pit_number as combo,
                t.odds
            FROM race_predictions p1
            JOIN race_predictions p2 ON p1.race_id = p2.race_id
                AND p2.confidence = 'B' AND p2.rank_prediction = 2
            JOIN race_predictions p3 ON p1.race_id = p3.race_id
                AND p3.confidence = 'B' AND p3.rank_prediction = 3
            LEFT JOIN trifecta_odds t ON p1.race_id = t.race_id
                AND t.combination = p1.pit_number || '-' || p2.pit_number || '-' || p3.pit_number
            WHERE p1.confidence = 'B' AND p1.rank_prediction = 1
              AND t.odds IS NOT NULL
        )
        GROUP BY odds_range
        ORDER BY avg_odds
    ''')

    for row in cursor.fetchall():
        print(f"   {row['odds_range']:12s}: {row['count']:5,}件 (平均{row['avg_odds']:.1f}倍)")

    # 1コース選手のランク分布
    print(f"\n3. 1コース選手のランク分布:")
    cursor.execute('''
        SELECT
            e.racer_rank,
            COUNT(*) as count
        FROM race_predictions p
        JOIN entries e ON p.race_id = e.race_id AND e.pit_number = 1
        WHERE p.confidence = 'B' AND p.prediction_type = 'advance'
        GROUP BY e.racer_rank
        ORDER BY count DESC
    ''')

    for row in cursor.fetchall():
        print(f"   {row['racer_rank']:4s}: {row['count']:5,}件")

    # 現在のフィルタリング条件で除外されるレース
    print(f"\n4. 購入対象判定（bet_target_evaluator基準）:")
    print(f"   ※現在、信頼度Bは EXCLUDED_CONFIDENCE に含まれており全て除外")

    conn.close()


def analyze_cd_logic_bias():
    """信頼度C,Dにおける現状ロジックの偏り分析"""

    print("\n" + "=" * 80)
    print("信頼度C,D ロジック偏り分析（イン・A1重視の影響）")
    print("=" * 80)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    for conf in ['C', 'D']:
        print(f"\n【信頼度{conf}】")

        # 1着予想のコース分布
        cursor.execute('''
            SELECT
                e.pit_number as course,
                COUNT(*) as count,
                AVG(p.total_score) as avg_score
            FROM race_predictions p
            JOIN entries e ON p.race_id = e.race_id AND p.pit_number = e.pit_number
            WHERE p.confidence = ? AND p.rank_prediction = 1 AND p.prediction_type = 'advance'
            GROUP BY e.pit_number
            ORDER BY count DESC
        ''', (conf,))

        print(f"  1. 1着予想のコース分布:")
        total_first = 0
        for row in cursor.fetchall():
            total_first += row['count']

        cursor.execute('''
            SELECT
                e.pit_number as course,
                COUNT(*) as count,
                AVG(p.total_score) as avg_score
            FROM race_predictions p
            JOIN entries e ON p.race_id = e.race_id AND p.pit_number = e.pit_number
            WHERE p.confidence = ? AND p.rank_prediction = 1 AND p.prediction_type = 'advance'
            GROUP BY e.pit_number
            ORDER BY count DESC
        ''', (conf,))

        for row in cursor.fetchall():
            pct = (row['count'] / total_first * 100) if total_first > 0 else 0
            print(f"     {row['course']}コース: {row['count']:5,}件 ({pct:5.1f}%) 平均スコア{row['avg_score']:.1f}")

        # 1着予想選手のランク分布
        cursor.execute('''
            SELECT
                e.racer_rank,
                COUNT(*) as count
            FROM race_predictions p
            JOIN entries e ON p.race_id = e.race_id AND p.pit_number = e.pit_number
            WHERE p.confidence = ? AND p.rank_prediction = 1 AND p.prediction_type = 'advance'
            GROUP BY e.racer_rank
            ORDER BY count DESC
        ''', (conf,))

        print(f"  2. 1着予想選手のランク分布:")
        for row in cursor.fetchall():
            pct = (row['count'] / total_first * 100) if total_first > 0 else 0
            print(f"     {row['racer_rank']:4s}: {row['count']:5,}件 ({pct:5.1f}%)")

        # オッズ分布
        cursor.execute('''
            SELECT
                CASE
                    WHEN odds < 10 THEN '～10倍'
                    WHEN odds < 20 THEN '10～20倍'
                    WHEN odds < 30 THEN '20～30倍'
                    WHEN odds < 50 THEN '30～50倍'
                    WHEN odds < 100 THEN '50～100倍'
                    ELSE '100倍～'
                END as odds_range,
                COUNT(*) as count,
                AVG(odds) as avg_odds
            FROM (
                SELECT DISTINCT
                    p1.race_id,
                    t.odds
                FROM race_predictions p1
                JOIN race_predictions p2 ON p1.race_id = p2.race_id
                    AND p2.confidence = ? AND p2.rank_prediction = 2
                JOIN race_predictions p3 ON p1.race_id = p3.race_id
                    AND p3.confidence = ? AND p3.rank_prediction = 3
                LEFT JOIN trifecta_odds t ON p1.race_id = t.race_id
                    AND t.combination = p1.pit_number || '-' || p2.pit_number || '-' || p3.pit_number
                WHERE p1.confidence = ? AND p1.rank_prediction = 1
                  AND t.odds IS NOT NULL
            )
            GROUP BY odds_range
            ORDER BY avg_odds
        ''', (conf, conf, conf))

        print(f"  3. オッズ分布:")
        for row in cursor.fetchall():
            print(f"     {row['odds_range']:12s}: {row['count']:5,}件 (平均{row['avg_odds']:.1f}倍)")

    conn.close()


def find_upset_patterns():
    """中穴（荒れ）のパターンを探索"""

    print("\n" + "=" * 80)
    print("中穴パターン探索（市場との乖離・過小評価検出）")
    print("=" * 80)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1コース以外が勝ったレース（荒れ）
    print(f"\n1. 荒れレースの特徴分析（1コース以外が1着）:")

    cursor.execute('''
        SELECT
            res.pit_number as winner_course,
            e.racer_rank,
            COUNT(*) as count,
            AVG(p.amount) as avg_payout
        FROM results res
        JOIN entries e ON res.race_id = e.race_id AND res.pit_number = e.pit_number
        LEFT JOIN payouts p ON res.race_id = p.race_id AND p.bet_type = 'trifecta'
        WHERE res.rank = 1
          AND res.pit_number > 1
          AND res.is_invalid = 0
        GROUP BY res.pit_number, e.racer_rank
        ORDER BY res.pit_number, count DESC
    ''')

    upset_by_course = defaultdict(list)
    for row in cursor.fetchall():
        upset_by_course[row['winner_course']].append({
            'rank': row['racer_rank'],
            'count': row['count'],
            'avg_payout': row['avg_payout']
        })

    for course in sorted(upset_by_course.keys()):
        print(f"\n  {course}コース勝利:")
        for data in upset_by_course[course][:3]:  # 上位3つ
            print(f"    {data['rank']:4s}: {data['count']:5,}回 (平均払戻{data['avg_payout'] or 0:,.0f}円)")

    # 高配当レース（3連単50倍以上）の特徴
    print(f"\n2. 高配当レース（50倍以上）の特徴:")

    cursor.execute('''
        SELECT
            r.venue_code,
            COUNT(*) as count,
            AVG(p.amount) as avg_payout
        FROM payouts p
        JOIN races r ON p.race_id = r.id
        WHERE p.bet_type = 'trifecta'
          AND p.amount >= 5000
        GROUP BY r.venue_code
        ORDER BY count DESC
        LIMIT 10
    ''')

    print(f"  荒れやすい会場TOP10:")
    for row in cursor.fetchall():
        print(f"    会場{row['venue_code']:2s}: {row['count']:5,}回 (平均{row['avg_payout']:,.0f}円)")

    # 市場との乖離（予想1着がオッズ人気薄だったケース）
    print(f"\n3. 予想的中 × 高配当（市場との乖離）:")

    cursor.execute('''
        SELECT
            p.confidence,
            COUNT(*) as count,
            AVG(pay.amount) as avg_payout
        FROM race_predictions p
        JOIN results res ON p.race_id = res.race_id
            AND p.pit_number = res.pit_number
            AND res.rank = 1
        JOIN payouts pay ON p.race_id = pay.race_id AND pay.bet_type = 'trifecta'
        WHERE p.rank_prediction = 1
          AND p.prediction_type = 'advance'
          AND pay.amount >= 3000
          AND res.is_invalid = 0
        GROUP BY p.confidence
        ORDER BY avg_payout DESC
    ''')

    print(f"  信頼度別の高配当的中:")
    for row in cursor.fetchall():
        print(f"    {row['confidence']}: {row['count']:5,}回 (平均{row['avg_payout']:,.0f}円)")

    conn.close()


def export_analysis_summary():
    """分析結果のサマリーをJSON出力"""

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    summary = {
        'analysis_date': '2025-12-08',
        'confidence_b': {},
        'confidence_cd': {},
        'upset_patterns': {}
    }

    # 信頼度B
    cursor.execute('''
        SELECT
            COUNT(DISTINCT p.race_id) as total,
            SUM(CASE WHEN res.rank = 1 THEN 1 ELSE 0 END) as first_hit
        FROM race_predictions p
        JOIN results res ON p.race_id = res.race_id AND p.pit_number = res.pit_number
        WHERE p.confidence = 'B' AND p.rank_prediction = 1
          AND p.prediction_type = 'advance' AND res.is_invalid = 0
    ''')
    row = cursor.fetchone()
    summary['confidence_b'] = {
        'total_races': row['total'],
        'first_accuracy': (row['first_hit'] / row['total'] * 100) if row['total'] > 0 else 0,
        'issue': '購入対象レース少・3連単的中率20%'
    }

    # 信頼度C,D
    for conf in ['C', 'D']:
        cursor.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN e.pit_number = 1 THEN 1 ELSE 0 END) as course1_count
            FROM race_predictions p
            JOIN entries e ON p.race_id = e.race_id AND p.pit_number = e.pit_number
            WHERE p.confidence = ? AND p.rank_prediction = 1 AND p.prediction_type = 'advance'
        ''', (conf,))
        row = cursor.fetchone()
        course1_pct = (row['course1_count'] / row['total'] * 100) if row['total'] > 0 else 0

        summary['confidence_cd'][conf] = {
            'total_races': row['total'],
            'course1_bias': course1_pct,
            'issue': 'イン・A1重視でオッズ低い買い目が出やすい'
        }

    conn.close()

    output_path = ROOT_DIR / 'results' / 'confidence_analysis_summary.json'
    output_path.parent.mkdir(exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n分析サマリーを出力: {output_path}")


if __name__ == "__main__":
    print("信頼度別問題点分析スタート\n")

    analyze_confidence_b_issues()
    analyze_cd_logic_bias()
    find_upset_patterns()
    export_analysis_summary()

    print("\n" + "=" * 80)
    print("分析完了")
    print("=" * 80)
