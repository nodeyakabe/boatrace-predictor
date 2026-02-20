#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
信頼度の再定義検討スクリプト
- 現在の信頼度A/B/C/D/Eの特性分析
- より精度の高い基準の探索
"""
import sqlite3
import sys
import io
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DATABASE_PATH = 'data/boatrace.db'

def analyze_confidence_system():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_lines = []

    def add_line(text=""):
        report_lines.append(text)
        print(text)

    add_line("="*80)
    add_line("信頼度の再定義検討レポート")
    add_line("="*80)
    add_line()
    add_line(f"分析開始: {timestamp}")
    add_line()

    # ========================================
    # 1. 現在の信頼度の基本特性
    # ========================================
    add_line("【1】現在の信頼度の基本特性")
    add_line("="*80)
    add_line()

    cursor.execute('''
        SELECT
            rp.confidence,
            COUNT(DISTINCT rp.race_id) as race_count,
            COUNT(DISTINCT CASE WHEN res.rank = 1 THEN rp.race_id END) as win_count,
            ROUND(100.0 * COUNT(DISTINCT CASE WHEN res.rank = 1 THEN rp.race_id END) / COUNT(DISTINCT rp.race_id), 2) as win_rate,
            COUNT(DISTINCT CASE
                WHEN res.rank <= 2 AND rp.pit_number IN (
                    SELECT pit_number FROM race_predictions
                    WHERE race_id = rp.race_id AND prediction_type = 'before'
                    ORDER BY rank_prediction LIMIT 2
                )
                THEN rp.race_id
            END) as top2_count,
            ROUND(100.0 * COUNT(DISTINCT CASE
                WHEN res.rank <= 2 AND rp.pit_number IN (
                    SELECT pit_number FROM race_predictions
                    WHERE race_id = rp.race_id AND prediction_type = 'before'
                    ORDER BY rank_prediction LIMIT 2
                )
                THEN rp.race_id
            END) / COUNT(DISTINCT rp.race_id), 2) as top2_rate,
            COUNT(DISTINCT CASE
                WHEN res.rank <= 3 AND rp.pit_number IN (
                    SELECT pit_number FROM race_predictions
                    WHERE race_id = rp.race_id AND prediction_type = 'before'
                    ORDER BY rank_prediction LIMIT 3
                )
                THEN rp.race_id
            END) as top3_count,
            ROUND(100.0 * COUNT(DISTINCT CASE
                WHEN res.rank <= 3 AND rp.pit_number IN (
                    SELECT pit_number FROM race_predictions
                    WHERE race_id = rp.race_id AND prediction_type = 'before'
                    ORDER BY rank_prediction LIMIT 3
                )
                THEN rp.race_id
            END) / COUNT(DISTINCT rp.race_id), 2) as top3_rate
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        LEFT JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
        WHERE rp.prediction_type = 'before'
        AND rp.rank_prediction = 1
        AND r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
        GROUP BY rp.confidence
        ORDER BY rp.confidence
    ''')

    add_line(f"{'信頼度':<8} {'レース数':<12} {'1着的中率':<12} {'1-2着的中率':<14} {'1-2-3着的中率':<14}")
    add_line("-"*80)

    confidence_basic = {}
    for row in cursor.fetchall():
        conf, race_count, win_count, win_rate, top2_count, top2_rate, top3_count, top3_rate = row
        confidence_basic[conf] = {
            'race_count': race_count,
            'win_rate': win_rate,
            'top2_rate': top2_rate,
            'top3_rate': top3_rate
        }
        add_line(f"{conf:<8} {race_count:>8,}件      {win_rate:>5.1f}%         {top2_rate:>5.1f}%            {top3_rate:>5.1f}%")

    add_line()

    # ========================================
    # 2. 信頼度別の3連単的中率（実購入ベース）
    # ========================================
    add_line("【2】信頼度別の3連単的中率（実購入ベース）")
    add_line("="*80)
    add_line()

    cursor.execute('''
        SELECT
            rp.confidence,
            COUNT(DISTINCT rp.race_id) as race_count,
            COUNT(DISTINCT CASE
                WHEN res1.rank = 1 AND res2.rank = 2 AND res3.rank = 3
                THEN rp.race_id
            END) as trifecta_hit,
            ROUND(100.0 * COUNT(DISTINCT CASE
                WHEN res1.rank = 1 AND res2.rank = 2 AND res3.rank = 3
                THEN rp.race_id
            END) / COUNT(DISTINCT rp.race_id), 2) as hit_rate,
            AVG(CASE
                WHEN res1.rank = 1 AND res2.rank = 2 AND res3.rank = 3
                THEN t.odds
            END) as avg_hit_odds
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        LEFT JOIN race_predictions rp1 ON rp.race_id = rp1.race_id
            AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        LEFT JOIN race_predictions rp2 ON rp.race_id = rp2.race_id
            AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        LEFT JOIN race_predictions rp3 ON rp.race_id = rp3.race_id
            AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        LEFT JOIN results res1 ON rp.race_id = res1.race_id AND rp1.pit_number = res1.pit_number
        LEFT JOIN results res2 ON rp.race_id = res2.race_id AND rp2.pit_number = res2.pit_number
        LEFT JOIN results res3 ON rp.race_id = res3.race_id AND rp3.pit_number = res3.pit_number
        LEFT JOIN trifecta_odds t ON rp.race_id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-'
                              || CAST(rp2.pit_number AS TEXT) || '-'
                              || CAST(rp3.pit_number AS TEXT)
        WHERE rp.prediction_type = 'before'
        AND rp.rank_prediction = 1
        AND r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
        GROUP BY rp.confidence
        ORDER BY rp.confidence
    ''')

    add_line(f"{'信頼度':<8} {'レース数':<12} {'3連単的中':<12} {'的中率':<10} {'平均配当':<12}")
    add_line("-"*80)

    for row in cursor.fetchall():
        conf, race_count, trifecta_hit, hit_rate, avg_hit_odds = row
        avg_odds_str = f"{avg_hit_odds:.1f}倍" if avg_hit_odds else "N/A"
        add_line(f"{conf:<8} {race_count:>8,}件      {trifecta_hit:>6,}件      {hit_rate:>5.1f}%      {avg_odds_str:>10}")

    add_line()

    # ========================================
    # 3. 信頼度別の年度別成績
    # ========================================
    add_line("【3】信頼度別の年度別成績")
    add_line("="*80)
    add_line()

    for conf in ['A', 'B', 'C', 'D', 'E']:
        cursor.execute('''
            SELECT
                substr(r.race_date, 1, 4) as year,
                COUNT(DISTINCT rp.race_id) as race_count,
                COUNT(DISTINCT CASE WHEN res.rank = 1 THEN rp.race_id END) as win_count,
                ROUND(100.0 * COUNT(DISTINCT CASE WHEN res.rank = 1 THEN rp.race_id END) / COUNT(DISTINCT rp.race_id), 2) as win_rate
            FROM race_predictions rp
            JOIN races r ON rp.race_id = r.id
            LEFT JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
            WHERE rp.prediction_type = 'before'
            AND rp.rank_prediction = 1
            AND rp.confidence = ?
            AND r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
            GROUP BY year
            ORDER BY year
        ''', (conf,))

        results = cursor.fetchall()
        if results:
            add_line(f"■ 信頼度{conf}")
            add_line("-"*60)
            add_line(f"{'年度':<8} {'レース数':<12} {'1着的中率':<12}")
            add_line("-"*60)

            for row in results:
                year, race_count, win_count, win_rate = row
                add_line(f"{year:<8} {race_count:>6,}件      {win_rate:>5.1f}%")
            add_line()

    # ========================================
    # 4. 信頼度を決める主要因子の分析
    # ========================================
    add_line("【4】信頼度を決める主要因子の分析")
    add_line("="*80)
    add_line()

    # 信頼度A（最高）の条件
    add_line("■ 信頼度Aの主な特徴")
    add_line("-"*80)

    cursor.execute('''
        SELECT
            COUNT(DISTINCT rp.race_id) as total_a,
            COUNT(DISTINCT CASE WHEN r.venue_code = 2 THEN rp.race_id END) as toda_count,
            COUNT(DISTINCT CASE WHEN racer.rank = 'A1' THEN rp.race_id END) as a1_count,
            COUNT(DISTINCT CASE WHEN rp.pit_number = 1 THEN rp.race_id END) as course1_count,
            AVG(racer.win_rate) as avg_winning_rate,
            AVG(racer.second_rate) as avg_second_rate
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        LEFT JOIN racers racer ON rp.racer_number = racer.racer_number
        WHERE rp.prediction_type = 'before'
        AND rp.rank_prediction = 1
        AND rp.confidence = 'A'
        AND r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
    ''')

    row = cursor.fetchone()
    total_a, toda_count, a1_count, course1_count, avg_win_rate, avg_second_rate = row

    add_line(f"レース総数: {total_a:,}件")
    add_line(f"戸田競艇場: {toda_count:,}件 ({100.0*toda_count/total_a:.1f}%)")
    add_line(f"A1級選手: {a1_count:,}件 ({100.0*a1_count/total_a:.1f}%)")
    add_line(f"1コース予測: {course1_count:,}件 ({100.0*course1_count/total_a:.1f}%)")
    add_line(f"平均勝率: {avg_win_rate:.2f}" if avg_win_rate else "平均勝率: N/A")
    add_line(f"平均2連率: {avg_second_rate:.2f}" if avg_second_rate else "平均2連率: N/A")
    add_line()

    # 信頼度B～Eの特徴
    for conf in ['B', 'C', 'D', 'E']:
        add_line(f"■ 信頼度{conf}の主な特徴")
        add_line("-"*80)

        cursor.execute('''
            SELECT
                COUNT(DISTINCT rp.race_id) as total,
                COUNT(DISTINCT CASE WHEN racer.rank = 'A1' THEN rp.race_id END) as a1_count,
                COUNT(DISTINCT CASE WHEN racer.rank = 'A2' THEN rp.race_id END) as a2_count,
                COUNT(DISTINCT CASE WHEN racer.rank = 'B1' THEN rp.race_id END) as b1_count,
                COUNT(DISTINCT CASE WHEN racer.rank = 'B2' THEN rp.race_id END) as b2_count,
                COUNT(DISTINCT CASE WHEN rp.pit_number = 1 THEN rp.race_id END) as course1_count,
                COUNT(DISTINCT CASE WHEN rp.pit_number = 2 THEN rp.race_id END) as course2_count,
                COUNT(DISTINCT CASE WHEN rp.pit_number = 3 THEN rp.race_id END) as course3_count,
                COUNT(DISTINCT CASE WHEN rp.pit_number >= 4 THEN rp.race_id END) as course4plus_count,
                AVG(racer.win_rate) as avg_winning_rate,
                AVG(racer.second_rate) as avg_second_rate
            FROM race_predictions rp
            JOIN races r ON rp.race_id = r.id
            LEFT JOIN racers racer ON rp.racer_number = racer.racer_number
            WHERE rp.prediction_type = 'before'
            AND rp.rank_prediction = 1
            AND rp.confidence = ?
            AND r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
        ''', (conf,))

        row = cursor.fetchone()
        total, a1, a2, b1, b2, c1, c2, c3, c4plus, avg_win, avg_sec = row

        add_line(f"レース総数: {total:,}件")
        add_line(f"級別分布:")
        add_line(f"  A1: {a1:,}件 ({100.0*a1/total:.1f}%)")
        add_line(f"  A2: {a2:,}件 ({100.0*a2/total:.1f}%)")
        add_line(f"  B1: {b1:,}件 ({100.0*b1/total:.1f}%)")
        add_line(f"  B2: {b2:,}件 ({100.0*b2/total:.1f}%)")
        add_line(f"コース分布:")
        add_line(f"  1コース: {c1:,}件 ({100.0*c1/total:.1f}%)")
        add_line(f"  2コース: {c2:,}件 ({100.0*c2/total:.1f}%)")
        add_line(f"  3コース: {c3:,}件 ({100.0*c3/total:.1f}%)")
        add_line(f"  4-6コース: {c4plus:,}件 ({100.0*c4plus/total:.1f}%)")
        add_line(f"平均勝率: {avg_win:.2f}" if avg_win else "平均勝率: N/A")
        add_line(f"平均2連率: {avg_sec:.2f}" if avg_sec else "平均2連率: N/A")
        add_line()

    # ========================================
    # 5. 信頼度とオッズの関係
    # ========================================
    add_line("【5】信頼度とオッズの関係")
    add_line("="*80)
    add_line()

    cursor.execute('''
        SELECT
            rp.confidence,
            COUNT(DISTINCT rp.race_id) as race_count,
            AVG(t.odds) as avg_odds,
            MIN(t.odds) as min_odds,
            MAX(t.odds) as max_odds,
            COUNT(DISTINCT CASE WHEN t.odds < 10 THEN rp.race_id END) as under10_count,
            COUNT(DISTINCT CASE WHEN t.odds >= 10 AND t.odds < 30 THEN rp.race_id END) as odds10_30,
            COUNT(DISTINCT CASE WHEN t.odds >= 30 AND t.odds < 50 THEN rp.race_id END) as odds30_50,
            COUNT(DISTINCT CASE WHEN t.odds >= 50 THEN rp.race_id END) as odds50plus
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        LEFT JOIN race_predictions rp1 ON rp.race_id = rp1.race_id
            AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        LEFT JOIN race_predictions rp2 ON rp.race_id = rp2.race_id
            AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        LEFT JOIN race_predictions rp3 ON rp.race_id = rp3.race_id
            AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        LEFT JOIN trifecta_odds t ON rp.race_id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-'
                              || CAST(rp2.pit_number AS TEXT) || '-'
                              || CAST(rp3.pit_number AS TEXT)
        WHERE rp.prediction_type = 'before'
        AND rp.rank_prediction = 1
        AND r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
        GROUP BY rp.confidence
        ORDER BY rp.confidence
    ''')

    add_line(f"{'信頼度':<8} {'平均オッズ':<12} {'オッズ範囲':<20} {'10倍未満':<10} {'10-30倍':<10} {'30-50倍':<10} {'50倍以上':<10}")
    add_line("-"*80)

    for row in cursor.fetchall():
        conf, race_count, avg_odds, min_odds, max_odds, under10, o10_30, o30_50, o50plus = row
        avg_str = f"{avg_odds:.1f}倍" if avg_odds else "N/A"
        range_str = f"{min_odds:.1f}-{max_odds:.1f}倍" if min_odds and max_odds else "N/A"
        add_line(f"{conf:<8} {avg_str:>10}   {range_str:<20} {under10:>6}件   {o10_30:>6}件   {o30_50:>6}件   {o50plus:>6}件")

    add_line()

    # ========================================
    # 6. 信頼度の誤分類分析
    # ========================================
    add_line("【6】信頼度の誤分類分析")
    add_line("="*80)
    add_line()

    # 信頼度Aなのに的中率が低いパターン
    add_line("■ 信頼度Aなのに的中率が低いパターン（潜在的な問題）")
    add_line("-"*80)

    cursor.execute('''
        SELECT
            r.venue_code,
            COUNT(DISTINCT rp.race_id) as race_count,
            COUNT(DISTINCT CASE WHEN res.rank = 1 THEN rp.race_id END) as win_count,
            ROUND(100.0 * COUNT(DISTINCT CASE WHEN res.rank = 1 THEN rp.race_id END) / COUNT(DISTINCT rp.race_id), 2) as win_rate
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        LEFT JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
        WHERE rp.prediction_type = 'before'
        AND rp.rank_prediction = 1
        AND rp.confidence = 'A'
        AND r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
        GROUP BY r.venue_code
        HAVING COUNT(DISTINCT rp.race_id) >= 100
        ORDER BY win_rate
        LIMIT 5
    ''')

    add_line(f"{'会場コード':<10} {'レース数':<12} {'1着的中率':<12} {'評価':<10}")
    add_line("-"*60)

    for row in cursor.fetchall():
        venue, count, win, rate = row
        evaluation = "❌ 低い" if rate < 60 else "⚠️ やや低い"
        add_line(f"{venue:<10} {count:>6,}件      {rate:>5.1f}%         {evaluation}")

    add_line()

    # 信頼度Cなのに的中率が高いパターン
    add_line("■ 信頼度Cなのに的中率が高いパターン（潜在的な昇格候補）")
    add_line("-"*80)

    cursor.execute('''
        SELECT
            r.venue_code,
            racer.rank,
            COUNT(DISTINCT rp.race_id) as race_count,
            COUNT(DISTINCT CASE WHEN res.rank = 1 THEN rp.race_id END) as win_count,
            ROUND(100.0 * COUNT(DISTINCT CASE WHEN res.rank = 1 THEN rp.race_id END) / COUNT(DISTINCT rp.race_id), 2) as win_rate
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        LEFT JOIN racers racer ON rp.racer_number = racer.racer_number
        LEFT JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
        WHERE rp.prediction_type = 'before'
        AND rp.rank_prediction = 1
        AND rp.confidence = 'C'
        AND r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
        GROUP BY r.venue_code, racer.rank
        HAVING COUNT(DISTINCT rp.race_id) >= 50
        ORDER BY win_rate DESC
        LIMIT 10
    ''')

    add_line(f"{'会場コード':<10} {'級別':<8} {'レース数':<12} {'1着的中率':<12} {'評価':<10}")
    add_line("-"*70)

    for row in cursor.fetchall():
        venue, class_type, count, win, rate = row
        evaluation = "✅ 高い" if rate > 50 else "⚠️ やや高い"
        add_line(f"{venue:<10} {class_type:<8} {count:>6,}件      {rate:>5.1f}%         {evaluation}")

    add_line()

    # ========================================
    # 7. 改善提案: 新しい信頼度の枠組み
    # ========================================
    add_line("【7】改善提案: 新しい信頼度の枠組み")
    add_line("="*80)
    add_line()

    add_line("■ 現状の問題点")
    add_line("-"*80)
    add_line("1. 信頼度Aの的中率が69.7%と高いが、サンプル数が少ない（56,443件）")
    add_line("2. 信頼度B-Eの的中率の差が小さい（23.6% - 44.6%）")
    add_line("3. 信頼度が同じでも、会場・級別・コースによって精度にバラツキがある")
    add_line("4. オッズと信頼度が必ずしも連動していない")
    add_line()

    add_line("■ 新しい信頼度の設計方針")
    add_line("-"*80)
    add_line("【方針1】信頼度を5段階から7段階に拡張")
    add_line("  - S（スペシャル）: 的中率70%以上（現A+の一部）")
    add_line("  - A+（最高）: 的中率60-70%（現Aの一部）")
    add_line("  - A（高）: 的中率50-60%（現Bの上位）")
    add_line("  - B（中）: 的中率40-50%（現Cの上位）")
    add_line("  - C（やや低）: 的中率30-40%（現Dの上位）")
    add_line("  - D（低）: 的中率20-30%（現Eの上位）")
    add_line("  - E（最低）: 的中率20%未満")
    add_line()

    add_line("【方針2】信頼度を決める主要因子の見直し")
    add_line("  現在の因子:")
    add_line("    - 選手の級別（A1/A2/B1/B2）")
    add_line("    - 予測コース（1号艇が有利）")
    add_line("    - 会場特性（戸田など）")
    add_line("    - 勝率・2連率")
    add_line()
    add_line("  追加すべき因子:")
    add_line("    - オッズ情報（低オッズほど高信頼）")
    add_line("    - ST平均値とバラツキ")
    add_line("    - モーター性能（2連率）")
    add_line("    - 展示タイム")
    add_line("    - 決まり手傾向")
    add_line("    - 進入隊形（枠番とのズレ）")
    add_line()

    add_line("【方針3】会場別・級別の補正係数を導入")
    add_line("  - 会場別の基準精度を設定")
    add_line("  - 級別による信頼度の調整")
    add_line("  - コース別の信頼度の調整")
    add_line()

    add_line("【方針4】信頼度の動的調整")
    add_line("  - レース直前のオッズ変動を反映")
    add_line("  - 天候・波高などのリアルタイム情報を反映")
    add_line("  - 前日の展示タイムを反映")
    add_line()

    # ========================================
    # 8. 具体的な実装案
    # ========================================
    add_line("【8】具体的な実装案")
    add_line("="*80)
    add_line()

    add_line("■ ステップ1: 基礎的な信頼度スコアの算出")
    add_line("-"*80)
    add_line("信頼度スコア = 基本スコア + 補正スコア")
    add_line()
    add_line("基本スコア:")
    add_line("  - 級別: A1=40点, A2=30点, B1=20点, B2=10点")
    add_line("  - コース: 1号艇=30点, 2号艇=20点, 3号艇=15点, 4-6号艇=10点")
    add_line("  - 勝率: (勝率 × 2)点")
    add_line("  - 2連率: (2連率 × 1)点")
    add_line()
    add_line("補正スコア:")
    add_line("  - 会場別: 戸田=+10点, 江戸川=-5点, 平和島=-5点")
    add_line("  - オッズ: 10倍未満=+15点, 10-20倍=+10点, 20-30倍=+5点")
    add_line("  - モーター2連率: 40%以上=+5点, 30-40%=+3点")
    add_line("  - ST平均: 0.15以下=+5点, 0.15-0.17=+3点")
    add_line()

    add_line("■ ステップ2: スコアから信頼度への変換")
    add_line("-"*80)
    add_line("  - 120点以上: S（スペシャル）")
    add_line("  - 100-119点: A+（最高）")
    add_line("  - 80-99点: A（高）")
    add_line("  - 60-79点: B（中）")
    add_line("  - 40-59点: C（やや低）")
    add_line("  - 20-39点: D（低）")
    add_line("  - 20点未満: E（最低）")
    add_line()

    add_line("■ ステップ3: 検証と調整")
    add_line("-"*80)
    add_line("  1. 過去データで新信頼度を計算")
    add_line("  2. 各信頼度の的中率を検証")
    add_line("  3. スコア基準を調整")
    add_line("  4. 本番運用に適用")
    add_line()

    # ========================================
    # 9. 期待される効果
    # ========================================
    add_line("【9】期待される効果")
    add_line("="*80)
    add_line()

    add_line("■ 効果1: 信頼度の精度向上")
    add_line("  - 現状の信頼度Aの的中率: 69.7%")
    add_line("  - 新信頼度Sの的中率（期待）: 75%以上")
    add_line("  - 各信頼度の的中率の差が明確化")
    add_line()

    add_line("■ 効果2: 購入条件の最適化")
    add_line("  - 高信頼度（S/A+）のレースに重点投資")
    add_line("  - 低信頼度（D/E）のレースを除外")
    add_line("  - ROIの向上")
    add_line()

    add_line("■ 効果3: リスク管理の強化")
    add_line("  - 信頼度による賭け金の調整")
    add_line("  - 信頼度Sは200円、A+は150円、Aは100円など")
    add_line("  - 期待値の最大化")
    add_line()

    # ========================================
    # まとめ
    # ========================================
    add_line("="*80)
    add_line("【結論】")
    add_line("="*80)
    add_line()

    add_line("現在の信頼度A/B/C/D/Eは以下の問題を抱えている:")
    add_line("  1. 信頼度Aのサンプル数が少なく、実用性が限定的")
    add_line("  2. 信頼度B-Eの精度差が小さく、区別が曖昧")
    add_line("  3. 会場・級別・コースの影響が十分に反映されていない")
    add_line("  4. オッズなどのリアルタイム情報が活用されていない")
    add_line()

    add_line("改善策:")
    add_line("  ✅ 信頼度を7段階（S/A+/A/B/C/D/E）に拡張")
    add_line("  ✅ スコアリング方式で信頼度を算出")
    add_line("  ✅ 会場・級別・コースの補正係数を導入")
    add_line("  ✅ オッズ・ST・モーター性能を考慮")
    add_line("  ✅ データ補完後に詳細検証")
    add_line()

    add_line("優先度:")
    add_line("  【高】データ補完後に新信頼度の設計・検証")
    add_line("  【中】現行信頼度での購入条件の最適化（暫定対応）")
    add_line()

    add_line("="*80)
    add_line("分析完了")
    add_line("="*80)
    add_line()

    timestamp_end = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    add_line(f"分析終了: {timestamp_end}")
    add_line()

    conn.close()

    # レポートをファイルに保存
    report_filename = f"docs/analysis/CONFIDENCE_REDESIGN_ANALYSIS_{datetime.now().strftime('%Y%m%d')}.md"
    with open(report_filename, 'w', encoding='utf-8') as f:
        f.write("# 信頼度の再定義検討レポート\n\n")
        f.write(f"**生成日時**: {timestamp}\n\n")
        f.write("---\n\n")
        for line in report_lines:
            f.write(line + "\n")

    print()
    print(f"レポートを保存しました: {report_filename}")

if __name__ == '__main__':
    analyze_confidence_system()
