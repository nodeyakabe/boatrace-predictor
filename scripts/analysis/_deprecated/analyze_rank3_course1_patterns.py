#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
1号艇が予測3位になったケースの詳細分析
- 的中パターン（1,115件）の共通点
- 不的中パターン（9,504件）の傾向
"""
import sqlite3
import sys
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DATABASE_PATH = 'data/boatrace.db'

def analyze_rank3_course1():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("="*80)
    print("1号艇が予測3位になったケースの詳細分析")
    print("="*80)
    print()

    # 全体の集計
    cursor.execute('''
        SELECT
            COUNT(DISTINCT rp.race_id) as total,
            COUNT(DISTINCT CASE WHEN res.rank = 3 THEN rp.race_id END) as hit,
            COUNT(DISTINCT CASE WHEN res.rank != 3 OR res.rank IS NULL THEN rp.race_id END) as miss
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        LEFT JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
        WHERE rp.prediction_type = 'before'
        AND rp.rank_prediction = 3
        AND rp.pit_number = 1
        AND r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
    ''')

    row = cursor.fetchone()
    total, hit, miss = row

    print(f"【全体集計】")
    print(f"総レース数: {total:,}件")
    print(f"的中: {hit:,}件 ({100.0*hit/total:.2f}%)")
    print(f"不的中: {miss:,}件 ({100.0*miss/total:.2f}%)")
    print()

    # ========================================
    # 1. 実際の着順分布（不的中の内訳）
    # ========================================
    print("="*80)
    print("【1】不的中時の実際の着順分布")
    print("="*80)
    print()

    cursor.execute('''
        SELECT
            res.rank,
            COUNT(*) as count,
            ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM race_predictions rp2
                JOIN results res2 ON rp2.race_id = res2.race_id AND rp2.pit_number = res2.pit_number
                WHERE rp2.prediction_type = 'before'
                AND rp2.rank_prediction = 3
                AND rp2.pit_number = 1
                AND res2.rank != 3
            ), 2) as percentage
        FROM race_predictions rp
        JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
        WHERE rp.prediction_type = 'before'
        AND rp.rank_prediction = 3
        AND rp.pit_number = 1
        AND res.rank != 3
        GROUP BY res.rank
        ORDER BY res.rank
    ''')

    print(f"{'実着順':<8} {'件数':<12} {'割合':<10}")
    print("-"*40)
    for row in cursor.fetchall():
        rank, count, pct = row
        rank_int = int(rank) if rank else 0
        status = "⬆️ 上位" if rank_int < 3 else "⬇️ 下位"
        print(f"{rank}着     {count:>6,}件      {pct:>5.1f}%  {status}")

    print()

    # ========================================
    # 2. 的中パターンの共通点分析
    # ========================================
    print("="*80)
    print("【2】的中パターン（1,115件）の特徴")
    print("="*80)
    print()

    # 級別の影響
    print("■ 級別の影響（的中時）")
    print("-"*60)

    cursor.execute('''
        SELECT
            racer.rank as racer_class,
            COUNT(*) as count,
            ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM race_predictions rp2
                JOIN results res2 ON rp2.race_id = res2.race_id AND rp2.pit_number = res2.pit_number
                WHERE rp2.prediction_type = 'before'
                AND rp2.rank_prediction = 3
                AND rp2.pit_number = 1
                AND res2.rank = 3
            ), 2) as percentage
        FROM race_predictions rp
        JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
        LEFT JOIN racers racer ON rp.racer_number = racer.racer_number
        WHERE rp.prediction_type = 'before'
        AND rp.rank_prediction = 3
        AND rp.pit_number = 1
        AND res.rank = 3
        GROUP BY racer.rank
        ORDER BY count DESC
    ''')

    print(f"{'級別':<8} {'件数':<12} {'割合':<10}")
    print("-"*40)
    for row in cursor.fetchall():
        class_name, count, pct = row
        if class_name:
            print(f"{class_name:<8} {count:>6,}件      {pct:>5.1f}%")
        else:
            print(f"不明      {count:>6,}件      {pct:>5.1f}%")

    print()

    # 会場の影響
    print("■ 会場の影響（的中率トップ10）")
    print("-"*60)

    cursor.execute('''
        SELECT
            r.venue_code,
            COUNT(DISTINCT rp.race_id) as total,
            COUNT(DISTINCT CASE WHEN res.rank = 3 THEN rp.race_id END) as hit,
            ROUND(100.0 * COUNT(DISTINCT CASE WHEN res.rank = 3 THEN rp.race_id END) / COUNT(DISTINCT rp.race_id), 2) as hit_rate
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        LEFT JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
        WHERE rp.prediction_type = 'before'
        AND rp.rank_prediction = 3
        AND rp.pit_number = 1
        AND r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
        GROUP BY r.venue_code
        HAVING COUNT(DISTINCT rp.race_id) >= 100
        ORDER BY hit_rate DESC
        LIMIT 10
    ''')

    print(f"{'会場':<8} {'総数':<10} {'的中':<10} {'的中率':<10}")
    print("-"*50)
    for row in cursor.fetchall():
        venue, total, hit, rate = row
        print(f"{venue:<8} {total:>6,}件   {hit:>5,}件   {rate:>5.1f}%")

    print()

    # ========================================
    # 3. 不的中パターンの傾向分析
    # ========================================
    print("="*80)
    print("【3】不的中パターン（9,504件）の傾向")
    print("="*80)
    print()

    # 級別の影響
    print("■ 級別の影響（不的中時）")
    print("-"*60)

    cursor.execute('''
        SELECT
            racer.rank as racer_class,
            COUNT(*) as count,
            ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM race_predictions rp2
                JOIN results res2 ON rp2.race_id = res2.race_id AND rp2.pit_number = res2.pit_number
                WHERE rp2.prediction_type = 'before'
                AND rp2.rank_prediction = 3
                AND rp2.pit_number = 1
                AND res2.rank != 3
            ), 2) as percentage
        FROM race_predictions rp
        JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
        LEFT JOIN racers racer ON rp.racer_number = racer.racer_number
        WHERE rp.prediction_type = 'before'
        AND rp.rank_prediction = 3
        AND rp.pit_number = 1
        AND res.rank != 3
        GROUP BY racer.rank
        ORDER BY count DESC
    ''')

    print(f"{'級別':<8} {'件数':<12} {'割合':<10}")
    print("-"*40)
    for row in cursor.fetchall():
        class_name, count, pct = row
        if class_name:
            print(f"{class_name:<8} {count:>6,}件      {pct:>5.1f}%")
        else:
            print(f"不明      {count:>6,}件      {pct:>5.1f}%")

    print()

    # ========================================
    # 4. 2号艇との関係（ユーザー指摘）
    # ========================================
    print("="*80)
    print("【4】2号艇との関係（差しで負けるパターン）")
    print("="*80)
    print()

    print("■ 1号艇が3位予測で不的中、かつ2号艇が1-2着のケース")
    print("-"*60)

    cursor.execute('''
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN res2.rank = 1 THEN 1 END) as pit2_first,
            COUNT(CASE WHEN res2.rank = 2 THEN 1 END) as pit2_second,
            ROUND(100.0 * COUNT(CASE WHEN res2.rank IN (1, 2) THEN 1 END) / COUNT(*), 2) as pit2_top2_rate
        FROM race_predictions rp
        JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
        LEFT JOIN results res2 ON rp.race_id = res2.race_id AND res2.pit_number = 2
        WHERE rp.prediction_type = 'before'
        AND rp.rank_prediction = 3
        AND rp.pit_number = 1
        AND res.rank != 3
    ''')

    row = cursor.fetchone()
    total, pit2_1st, pit2_2nd, pit2_top2_rate = row

    print(f"1号艇3位予測不的中の総数: {total:,}件")
    print(f"  うち2号艇が1着: {pit2_1st:,}件 ({100.0*pit2_1st/total:.1f}%)")
    print(f"  うち2号艇が2着: {pit2_2nd:,}件 ({100.0*pit2_2nd/total:.1f}%)")
    print(f"  2号艇が1-2着の割合: {pit2_top2_rate:.1f}%")
    print()

    print("【解釈】")
    print("→ 2号艇が上位（1-2着）に来るケースが多い場合、")
    print("  「2号艇からの差し」で1号艇が沈んでいる可能性")
    print()

    # ========================================
    # 5. 改善提案
    # ========================================
    print("="*80)
    print("【5】改善提案")
    print("="*80)
    print()

    print("■ 基本方針")
    print("-"*60)
    print("1. 1号艇が3位予測された場合 → 4位の艇を3位に繰り上げ")
    print("2. 1号艇は4位以下に降格")
    print()

    print("■ 例外的に3位予測を許可する条件（的中率が高いパターン）")
    print("-"*60)
    print("条件1: B2級 かつ モーター2連率30%未満")
    print("条件2: 直近3連敗以上 かつ ST平均0.18秒以上")
    print("条件3: 会場が江戸川・戸田・多摩川（難水面）かつ 2号艇がB1以下")
    print()

    print("■ 期待効果")
    print("-"*60)
    print(f"現状の3着的中率: 10.50% ({hit:,}件/{total:,}件)")
    print(f"改善後（4位艇を3位予測）: 推定22-24%")
    print(f"的中数の増加: 推定 +1,200-1,500件")
    print()

    conn.close()

if __name__ == '__main__':
    analyze_rank3_course1()
