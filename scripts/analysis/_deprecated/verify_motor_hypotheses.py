# -*- coding: utf-8 -*-
"""
モーター40%+条件の逆効果仮説を検証するスクリプト

仮説:
1. 既存条件（会場フィルター）との干渉
2. モーター率の分布バイアス（低モーター率でも勝つパターン）
3. オッズ帯との相性（過剰な信頼でオッズ低下）
4. サンプルサイズの問題
"""

import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def hypothesis1_venue_motor_distribution(cur):
    """仮説1: 会場フィルター対象会場でのモーター率分布"""
    print("\n" + "="*100)
    print("【仮説1】会場フィルター対象会場でのモーター率分布")
    print("="*100)

    # C条件の会場フィルター対象
    venue_filter = ['23', '18', '05', '04', '09', '15', '08', '24', '20', '17']

    query = f'''
    SELECT
        vd.venue_name,
        AVG(e.motor_second_rate) as avg_motor_rate,
        COUNT(*) as sample_count,
        SUM(CASE WHEN e.motor_second_rate >= 40 THEN 1 ELSE 0 END) as motor_40plus_count,
        ROUND(100.0 * SUM(CASE WHEN e.motor_second_rate >= 40 THEN 1 ELSE 0 END) / COUNT(*), 1) as motor_40plus_ratio
    FROM races r
    JOIN entries e ON r.id = e.race_id AND e.pit_number = 1
    JOIN venue_data vd ON r.venue_code = vd.venue_code
    WHERE r.venue_code IN ({','.join("'" + v + "'" for v in venue_filter)})
      AND e.racer_rank IN ('A2', 'B1')
      AND r.race_date >= '2025-01-01'
      AND r.race_date < '2025-12-01'
    GROUP BY vd.venue_name
    ORDER BY avg_motor_rate DESC
    '''

    cur.execute(query)
    results = cur.fetchall()

    print(f"\n{'会場':10} {'平均モーター率':15} {'サンプル数':12} {'40%+件数':12} {'40%+比率':12}")
    print("-"*100)
    total_sample = 0
    total_40plus = 0
    for row in results:
        print(f"{row[0]:10} {row[1]:14.1f}% {row[2]:12} {row[3]:12} {row[4]:11.1f}%")
        total_sample += row[2]
        total_40plus += row[3]

    overall_ratio = 100.0 * total_40plus / total_sample if total_sample > 0 else 0
    print("-"*100)
    print(f"{'合計':10} {'-':14} {total_sample:12} {total_40plus:12} {overall_ratio:11.1f}%")

    print(f"\n【考察】")
    if overall_ratio > 50:
        print(f"  ※ 会場フィルター対象会場のモーター40%+比率が{overall_ratio:.1f}%と高い")
        print(f"  → さらにモーター40%+で絞ると過剰フィルターになる可能性が高い")
    else:
        print(f"  ※ 会場フィルター対象会場のモーター40%+比率は{overall_ratio:.1f}%と標準的")

def hypothesis2_motor_distribution_by_hit(cur):
    """仮説2: C×A2、C×B1の的中レースにおけるモーター率分布"""
    print("\n" + "="*100)
    print("【仮説2】C×A2、C×B1の的中レースのモーター率分布")
    print("="*100)

    for c1_rank in ['A2', 'B1']:
        print(f"\n■ C × {c1_rank}")

        # race_predictionsテーブルの構造に合わせてクエリを修正
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
            WHERE rp.confidence = 'C'
              AND rp.prediction_type = 'before'
              AND r.race_date >= '2025-01-01'
              AND r.race_date < '2025-12-01'
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
        ),
        with_results AS (
            SELECT
                we.*,
                CASE
                    WHEN r1.rank = '1' AND r2.rank = '2' AND r3.rank = '3' THEN 1
                    ELSE 0
                END as is_hit,
                COALESCE(pay.amount, 0) as payout
            FROM with_entries we
            LEFT JOIN results r1 ON we.race_id = r1.race_id
                AND r1.pit_number = CAST(SUBSTR(we.pred_combo, 1, 1) AS INTEGER)
            LEFT JOIN results r2 ON we.race_id = r2.race_id
                AND r2.pit_number = CAST(SUBSTR(we.pred_combo, 2, 1) AS INTEGER)
            LEFT JOIN results r3 ON we.race_id = r3.race_id
                AND r3.pit_number = CAST(SUBSTR(we.pred_combo, 3, 1) AS INTEGER)
            LEFT JOIN payouts pay ON we.race_id = pay.race_id
                AND pay.bet_type = 'trifecta'
                AND pay.combination =
                    SUBSTR(we.pred_combo, 1, 1) || '-' ||
                    SUBSTR(we.pred_combo, 2, 1) || '-' ||
                    SUBSTR(we.pred_combo, 3, 1)
        )
        SELECT
            CASE
                WHEN motor_2rate >= 40 THEN 'motor_40+'
                WHEN motor_2rate >= 30 THEN 'motor_30-40'
                ELSE 'motor_under_30'
            END as motor_range,
            SUM(is_hit) as hit_count,
            COUNT(*) as total_count,
            ROUND(100.0 * SUM(is_hit) / COUNT(*), 2) as hit_rate,
            ROUND(AVG(CASE WHEN is_hit = 1 THEN payout ELSE NULL END), 0) as avg_payout
        FROM with_results
        GROUP BY motor_range
        ORDER BY
            CASE motor_range
                WHEN 'motor_40+' THEN 1
                WHEN 'motor_30-40' THEN 2
                ELSE 3
            END
        '''

        cur.execute(query, (c1_rank,))
        results = cur.fetchall()

        print(f"\n  {'モーター率帯':15} {'的中数':8} {'総数':8} {'的中率':8} {'平均払戻':12}")
        print("  " + "-"*80)
        for row in results:
            avg_payout_str = f"{int(row[4]):,}" if row[4] is not None else "N/A"
            print(f"  {row[0]:15} {row[1]:8} {row[2]:8} {row[3]:7.2f}% {avg_payout_str:12}")

        print(f"\n  【考察】")
        if results:
            motor_40_plus = [r for r in results if r[0] == 'motor_40+']
            motor_other = [r for r in results if r[0] != 'motor_40+']

            if motor_40_plus and motor_other:
                hit_rate_40 = motor_40_plus[0][3]
                hit_rate_other = sum(r[1] for r in motor_other) / sum(r[2] for r in motor_other) * 100 if motor_other else 0

                if hit_rate_40 < hit_rate_other:
                    print(f"    ※ モーター40%+の的中率({hit_rate_40:.2f}%)が、それ以外({hit_rate_other:.2f}%)より低い")
                    print(f"    → モーター40%+に絞ると的中機会を失う可能性がある")

def hypothesis3_odds_distribution(cur):
    """仮説3: C×A2×モーター40%+のオッズ分布"""
    print("\n" + "="*100)
    print("【仮説3】C×A2、C×B1でのモーター条件別オッズ分布")
    print("="*100)

    for c1_rank in ['A2', 'B1']:
        print(f"\n■ C × {c1_rank}")

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
            WHERE rp.confidence = 'C'
              AND rp.prediction_type = 'before'
              AND r.race_date >= '2025-01-01'
              AND r.race_date < '2025-12-01'
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
        ),
        with_odds AS (
            SELECT
                we.motor_2rate,
                COALESCE(o.odds, 0) as odds
            FROM with_entries we
            LEFT JOIN trifecta_odds o ON we.race_id = o.race_id
                AND o.combination =
                    SUBSTR(we.pred_combo, 1, 1) || '-' ||
                    SUBSTR(we.pred_combo, 2, 1) || '-' ||
                    SUBSTR(we.pred_combo, 3, 1)
        )
        SELECT
            CASE WHEN motor_2rate >= 40 THEN 'motor_40+' ELSE 'motor_other' END as motor_cond,
            CASE
                WHEN odds = 0 THEN 'no_odds'
                WHEN odds < 20 THEN 'under_20'
                WHEN odds BETWEEN 20 AND 30 THEN '20-30'
                WHEN odds BETWEEN 30 AND 50 THEN '30-50'
                ELSE '50+'
            END as odds_range,
            COUNT(*) as sample_count,
            ROUND(AVG(CASE WHEN odds > 0 THEN odds ELSE NULL END), 1) as avg_odds
        FROM with_odds
        GROUP BY motor_cond, odds_range
        ORDER BY motor_cond,
            CASE odds_range
                WHEN 'no_odds' THEN 0
                WHEN 'under_20' THEN 1
                WHEN '20-30' THEN 2
                WHEN '30-50' THEN 3
                ELSE 4
            END
        '''

        cur.execute(query, (c1_rank,))
        results = cur.fetchall()

        print(f"\n  {'モーター条件':15} {'オッズ帯':12} {'件数':8} {'平均オッズ':12}")
        print("  " + "-"*80)
        for row in results:
            avg_odds_str = f"{row[3]:.1f}" if row[3] is not None else "N/A"
            print(f"  {row[0]:15} {row[1]:12} {row[2]:8} {avg_odds_str:12}")

        print(f"\n  【考察】")
        motor_40_odds = [r for r in results if r[0] == 'motor_40+']
        motor_other_odds = [r for r in results if r[0] == 'motor_other']

        if motor_40_odds and motor_other_odds:
            # オッズ20-30倍の件数比較
            motor_40_20_30 = sum(r[2] for r in motor_40_odds if r[1] == '20-30')
            motor_other_20_30 = sum(r[2] for r in motor_other_odds if r[1] == '20-30')

            motor_40_total = sum(r[2] for r in motor_40_odds if r[1] != 'no_odds')
            motor_other_total = sum(r[2] for r in motor_other_odds if r[1] != 'no_odds')

            if motor_40_total > 0 and motor_other_total > 0:
                ratio_40 = 100.0 * motor_40_20_30 / motor_40_total
                ratio_other = 100.0 * motor_other_20_30 / motor_other_total

                print(f"    ※ C条件のオッズ目標（20-30倍）に該当する比率:")
                print(f"       motor_40+: {ratio_40:.1f}%")
                print(f"       motor_other: {ratio_other:.1f}%")

                if ratio_40 < ratio_other * 0.8:
                    print(f"    → モーター40%+では20-30倍の機会が減少している可能性")

def hypothesis4_sample_size(cur):
    """仮説4: サンプルサイズの問題"""
    print("\n" + "="*100)
    print("【仮説4】C×A2、C×B1でのサンプルサイズ")
    print("="*100)

    query = '''
    WITH predictions AS (
        SELECT DISTINCT
            rp.race_id,
            rp.confidence
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE rp.confidence = 'C'
          AND rp.prediction_type = 'before'
          AND r.race_date >= '2025-01-01'
          AND r.race_date < '2025-12-01'
    ),
    with_entries AS (
        SELECT
            p.*,
            e.racer_rank,
            COALESCE(e.motor_second_rate, 0) as motor_2rate
        FROM predictions p
        JOIN entries e ON p.race_id = e.race_id AND e.pit_number = 1
        WHERE e.racer_rank IN ('A2', 'B1')
    )
    SELECT
        racer_rank,
        CASE WHEN motor_2rate >= 40 THEN 'motor_40+' ELSE 'motor_other' END as motor_cond,
        COUNT(*) as sample_count
    FROM with_entries
    GROUP BY racer_rank, motor_cond
    ORDER BY racer_rank, motor_cond
    '''

    cur.execute(query)
    results = cur.fetchall()

    print(f"\n  {'級別':6} {'モーター条件':15} {'サンプル数':12} {'統計的信頼性':20}")
    print("  " + "-"*80)
    for row in results:
        confidence_level = ""
        if row[2] < 50:
            confidence_level = "❌ 低（過学習リスク高）"
        elif row[2] < 100:
            confidence_level = "⚠ 中（要注意）"
        else:
            confidence_level = "✅ 高"

        print(f"  {row[0]:6} {row[1]:15} {row[2]:12} {confidence_level:20}")

    print(f"\n  【考察】")
    motor_40_samples = [r[2] for r in results if r[1] == 'motor_40+']
    if motor_40_samples:
        avg_sample = sum(motor_40_samples) / len(motor_40_samples)
        if avg_sample < 100:
            print(f"    ※ モーター40%+のサンプル数平均: {avg_sample:.0f}件")
            print(f"    → 統計的信頼性が低く、効果測定が不正確な可能性がある")

def main():
    conn = sqlite3.connect(project_root / 'data' / 'boatrace.db')
    cur = conn.cursor()

    print("\n" + "="*100)
    print("モーター40%+条件の逆効果仮説検証")
    print("対象: 2025年1-11月データ（before予測）")
    print("="*100)

    # 仮説1: 会場フィルター対象会場のモーター率分布
    hypothesis1_venue_motor_distribution(cur)

    # 仮説2: モーター率の分布バイアス
    hypothesis2_motor_distribution_by_hit(cur)

    # 仮説3: オッズ帯との相性
    hypothesis3_odds_distribution(cur)

    # 仮説4: サンプルサイズ
    hypothesis4_sample_size(cur)

    conn.close()

    print("\n" + "="*100)
    print("検証完了")
    print("="*100)
    print("\n次のステップ:")
    print("1. 上記の考察を元に、実装判断を行う")
    print("2. 採用推奨条件（A×B1、D×A1、D×B1）の6年間安定性を検証")
    print("3. ペーパートレードまたは本番採用の判断")

if __name__ == '__main__':
    main()
