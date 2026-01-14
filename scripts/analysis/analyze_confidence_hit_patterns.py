# -*- coding: utf-8 -*-
"""
信頼度別的中パターン分析

各信頼度(A/B/C/D)で「どの条件が揃うと的中しやすいか」を分析する。
予想モデルの自信度校正を深掘りし、購入判断の精度向上を目指す。

分析観点:
1. 信頼度×オッズ帯×的中率の関係
2. 信頼度×1コース級別×的中率
3. 信頼度×予測コース×的中率
4. 信頼度×スコア差×的中率
5. 的中時と不的中時の特徴比較
"""

import sqlite3
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH


def analyze_confidence_odds_pattern():
    """信頼度×オッズ帯の的中率パターン"""
    print("=" * 70)
    print("【分析1】信頼度×オッズ帯別 的中パターン")
    print("=" * 70)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    query = """
    WITH prediction_results AS (
        SELECT
            rp.confidence,
            t.odds,
            CASE
                WHEN t.odds < 10 THEN '01: <10倍'
                WHEN t.odds < 20 THEN '02: 10-20倍'
                WHEN t.odds < 30 THEN '03: 20-30倍'
                WHEN t.odds < 50 THEN '04: 30-50倍'
                WHEN t.odds < 100 THEN '05: 50-100倍'
                ELSE '06: 100倍+'
            END as odds_band,
            CASE
                WHEN r1.rank = '1' AND r2.rank = '2' AND r3.rank = '3' THEN 1
                ELSE 0
            END as is_hit
        FROM race_predictions rp
        JOIN races rc ON rp.race_id = rc.id
        JOIN trifecta_odds t ON rp.race_id = t.race_id AND t.combination = '1-2-3'
        JOIN results r1 ON rp.race_id = r1.race_id AND r1.pit_number = 1
        JOIN results r2 ON rp.race_id = r2.race_id AND r2.pit_number = 2
        JOIN results r3 ON rp.race_id = r3.race_id AND r3.pit_number = 3
        WHERE rp.prediction_type = 'before'
          AND rp.pit_number = 1
          AND rp.rank_prediction = 1
          AND rc.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    )
    SELECT
        confidence,
        odds_band,
        COUNT(*) as total,
        SUM(is_hit) as hits,
        ROUND(100.0 * SUM(is_hit) / COUNT(*), 2) as hit_rate,
        ROUND(AVG(odds), 1) as avg_odds,
        -- ROI計算（1点買い100円想定）
        ROUND(100.0 * SUM(CASE WHEN is_hit = 1 THEN odds ELSE 0 END) / COUNT(*), 1) as roi
    FROM prediction_results
    GROUP BY confidence, odds_band
    ORDER BY confidence, odds_band
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    print(f"\n{'信頼度':<4} {'オッズ帯':<12} {'件数':>7} {'的中':>5} {'的中率':>7} {'平均オッズ':>9} {'ROI':>8}")
    print("-" * 70)

    current_conf = None
    for row in rows:
        conf, odds_band, total, hits, hit_rate, avg_odds, roi = row
        if current_conf != conf:
            if current_conf is not None:
                print("-" * 70)
            current_conf = conf

        # ROI 100%以上は強調
        roi_mark = "★" if roi and roi >= 100 else " "
        print(f"{conf:<4} {odds_band:<12} {total:>7,} {hits:>5} {hit_rate:>6.2f}% {avg_odds:>9.1f} {roi:>7.1f}%{roi_mark}")

    conn.close()


def analyze_confidence_c1rank_pattern():
    """信頼度×1コース級別の的中率パターン"""
    print("\n" + "=" * 70)
    print("【分析2】信頼度×1コース級別 的中パターン")
    print("=" * 70)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    query = """
    WITH prediction_results AS (
        SELECT
            rp.confidence,
            e1.racer_rank as c1_rank,
            t.odds,
            CASE
                WHEN r1.rank = '1' AND r2.rank = '2' AND r3.rank = '3' THEN 1
                ELSE 0
            END as is_hit
        FROM race_predictions rp
        JOIN races rc ON rp.race_id = rc.id
        JOIN entries e1 ON rp.race_id = e1.race_id AND e1.pit_number = 1
        JOIN trifecta_odds t ON rp.race_id = t.race_id AND t.combination = '1-2-3'
        JOIN results r1 ON rp.race_id = r1.race_id AND r1.pit_number = 1
        JOIN results r2 ON rp.race_id = r2.race_id AND r2.pit_number = 2
        JOIN results r3 ON rp.race_id = r3.race_id AND r3.pit_number = 3
        WHERE rp.prediction_type = 'before'
          AND rp.pit_number = 1
          AND rp.rank_prediction = 1
          AND rc.race_date BETWEEN '2020-01-01' AND '2025-12-31'
          AND e1.racer_rank IN ('A1', 'A2', 'B1', 'B2')
    )
    SELECT
        confidence,
        c1_rank,
        COUNT(*) as total,
        SUM(is_hit) as hits,
        ROUND(100.0 * SUM(is_hit) / COUNT(*), 2) as hit_rate,
        ROUND(AVG(odds), 1) as avg_odds,
        ROUND(100.0 * SUM(CASE WHEN is_hit = 1 THEN odds ELSE 0 END) / COUNT(*), 1) as roi
    FROM prediction_results
    GROUP BY confidence, c1_rank
    ORDER BY confidence, c1_rank
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    print(f"\n{'信頼度':<4} {'1C級別':<6} {'件数':>8} {'的中':>5} {'的中率':>7} {'平均オッズ':>9} {'ROI':>8}")
    print("-" * 60)

    current_conf = None
    for row in rows:
        conf, c1_rank, total, hits, hit_rate, avg_odds, roi = row
        if current_conf != conf:
            if current_conf is not None:
                print("-" * 60)
            current_conf = conf

        roi_mark = "★" if roi and roi >= 100 else " "
        print(f"{conf:<4} {c1_rank:<6} {total:>8,} {hits:>5} {hit_rate:>6.2f}% {avg_odds:>9.1f} {roi:>7.1f}%{roi_mark}")

    conn.close()


def analyze_confidence_predicted_course():
    """信頼度×予測1着コース別の的中率"""
    print("\n" + "=" * 70)
    print("【分析3】信頼度×予測1着コース別 的中パターン")
    print("=" * 70)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    query = """
    WITH prediction_results AS (
        SELECT
            rp.confidence,
            rp.pit_number as predicted_course,
            t.odds,
            CASE
                WHEN r1.rank = '1' AND r2.rank = '2' AND r3.rank = '3' THEN 1
                ELSE 0
            END as is_hit
        FROM race_predictions rp
        JOIN races rc ON rp.race_id = rc.id
        JOIN trifecta_odds t ON rp.race_id = t.race_id
            AND t.combination = (
                SELECT CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
                FROM race_predictions rp1
                JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
                JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
                WHERE rp1.race_id = rp.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            )
        JOIN results r1 ON rp.race_id = r1.race_id
        JOIN results r2 ON rp.race_id = r2.race_id
        JOIN results r3 ON rp.race_id = r3.race_id
        WHERE rp.prediction_type = 'before'
          AND rp.rank_prediction = 1
          AND rc.race_date BETWEEN '2020-01-01' AND '2025-12-31'
          AND r1.pit_number = (SELECT pit_number FROM race_predictions WHERE race_id = rp.race_id AND prediction_type = 'before' AND rank_prediction = 1)
          AND r2.pit_number = (SELECT pit_number FROM race_predictions WHERE race_id = rp.race_id AND prediction_type = 'before' AND rank_prediction = 2)
          AND r3.pit_number = (SELECT pit_number FROM race_predictions WHERE race_id = rp.race_id AND prediction_type = 'before' AND rank_prediction = 3)
          AND r1.rank = '1' AND r2.rank = '2' AND r3.rank = '3'
    )
    SELECT * FROM prediction_results LIMIT 0
    """

    # 簡略化したクエリ
    query = """
    SELECT
        rp.confidence,
        rp.pit_number as predicted_course,
        COUNT(*) as total,
        SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as first_hits,
        ROUND(100.0 * SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) / COUNT(*), 2) as first_rate
    FROM race_predictions rp
    JOIN races rc ON rp.race_id = rc.id
    JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
    WHERE rp.prediction_type = 'before'
      AND rp.rank_prediction = 1
      AND rc.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    GROUP BY rp.confidence, rp.pit_number
    ORDER BY rp.confidence, rp.pit_number
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    print(f"\n{'信頼度':<4} {'予測1着コース':<10} {'件数':>8} {'1着的中':>7} {'1着率':>7}")
    print("-" * 50)

    current_conf = None
    for row in rows:
        conf, course, total, hits, rate = row
        if current_conf != conf:
            if current_conf is not None:
                print("-" * 50)
            current_conf = conf

        # 1着率が高いものを強調
        mark = "★" if rate and rate >= 30 else " "
        print(f"{conf:<4} {course}コース      {total:>8,} {hits:>7} {rate:>6.2f}%{mark}")

    conn.close()


def analyze_score_gap_hit_pattern():
    """スコア差と的中率の関係"""
    print("\n" + "=" * 70)
    print("【分析4】スコア差×信頼度 的中パターン")
    print("=" * 70)
    print("※スコア差 = 1位予測スコア - 2位予測スコア（大きいほど差が明確）")

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # スコアカラムの存在確認
    cursor.execute("PRAGMA table_info(race_predictions)")
    columns = [col[1] for col in cursor.fetchall()]

    if 'score' not in columns:
        print("\n※race_predictionsテーブルにscoreカラムがありません")
        print("  → 信頼度(confidence)で代替分析を行います")
        conn.close()
        return

    # スコア差を計算できるか確認
    cursor.execute("""
    SELECT
        rp1.score as score1,
        rp2.score as score2
    FROM race_predictions rp1
    JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
        AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    WHERE rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    LIMIT 5
    """)
    sample = cursor.fetchall()

    if sample and sample[0][0] is not None:
        query = """
        WITH score_data AS (
            SELECT
                rp1.race_id,
                rp1.confidence,
                rp1.score - rp2.score as score_gap,
                CASE
                    WHEN r1.rank = '1' AND r2.rank = '2' AND r3.rank = '3' THEN 1
                    ELSE 0
                END as is_hit,
                t.odds
            FROM race_predictions rp1
            JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
                AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN races rc ON rp1.race_id = rc.id
            JOIN trifecta_odds t ON rp1.race_id = t.race_id AND t.combination = '1-2-3'
            JOIN results r1 ON rp1.race_id = r1.race_id AND r1.pit_number = 1
            JOIN results r2 ON rp1.race_id = r2.race_id AND r2.pit_number = 2
            JOIN results r3 ON rp1.race_id = r3.race_id AND r3.pit_number = 3
            WHERE rp1.prediction_type = 'before'
              AND rp1.rank_prediction = 1
              AND rp1.pit_number = 1
              AND rc.race_date BETWEEN '2020-01-01' AND '2025-12-31'
              AND rp1.score IS NOT NULL
              AND rp2.score IS NOT NULL
        )
        SELECT
            confidence,
            CASE
                WHEN score_gap >= 15 THEN '01: 15pt+ (圧倒的)'
                WHEN score_gap >= 10 THEN '02: 10-15pt (明確)'
                WHEN score_gap >= 5 THEN '03: 5-10pt (やや差)'
                WHEN score_gap >= 0 THEN '04: 0-5pt (僅差)'
                ELSE '05: マイナス (逆転)'
            END as gap_band,
            COUNT(*) as total,
            SUM(is_hit) as hits,
            ROUND(100.0 * SUM(is_hit) / COUNT(*), 2) as hit_rate,
            ROUND(AVG(odds), 1) as avg_odds,
            ROUND(100.0 * SUM(CASE WHEN is_hit = 1 THEN odds ELSE 0 END) / COUNT(*), 1) as roi
        FROM score_data
        GROUP BY confidence, gap_band
        ORDER BY confidence, gap_band
        """

        cursor.execute(query)
        rows = cursor.fetchall()

        print(f"\n{'信頼度':<4} {'スコア差帯':<18} {'件数':>7} {'的中':>5} {'的中率':>7} {'ROI':>8}")
        print("-" * 65)

        current_conf = None
        for row in rows:
            conf, gap_band, total, hits, hit_rate, avg_odds, roi = row
            if current_conf != conf:
                if current_conf is not None:
                    print("-" * 65)
                current_conf = conf

            roi_mark = "★" if roi and roi >= 100 else " "
            print(f"{conf:<4} {gap_band:<18} {total:>7,} {hits:>5} {hit_rate:>6.2f}% {roi:>7.1f}%{roi_mark}")
    else:
        print("\n※スコアデータがありません")

    conn.close()


def analyze_hit_vs_miss_features():
    """的中時と不的中時の特徴比較"""
    print("\n" + "=" * 70)
    print("【分析5】的中レース vs 不的中レース 特徴比較")
    print("=" * 70)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    for conf in ['A', 'B', 'C', 'D']:
        query = f"""
        WITH race_results AS (
            SELECT
                rp.race_id,
                rp.confidence,
                e1.racer_rank as c1_rank,
                e1.win_rate as c1_winrate,
                e1.second_rate as c1_2nd_rate,
                t.odds,
                CASE
                    WHEN r1.rank = '1' AND r2.rank = '2' AND r3.rank = '3' THEN 1
                    ELSE 0
                END as is_hit
            FROM race_predictions rp
            JOIN races rc ON rp.race_id = rc.id
            JOIN entries e1 ON rp.race_id = e1.race_id AND e1.pit_number = 1
            JOIN trifecta_odds t ON rp.race_id = t.race_id AND t.combination = '1-2-3'
            JOIN results r1 ON rp.race_id = r1.race_id AND r1.pit_number = 1
            JOIN results r2 ON rp.race_id = r2.race_id AND r2.pit_number = 2
            JOIN results r3 ON rp.race_id = r3.race_id AND r3.pit_number = 3
            WHERE rp.prediction_type = 'before'
              AND rp.pit_number = 1
              AND rp.rank_prediction = 1
              AND rp.confidence = '{conf}'
              AND rc.race_date BETWEEN '2020-01-01' AND '2025-12-31'
        )
        SELECT
            is_hit,
            COUNT(*) as cnt,
            ROUND(AVG(odds), 1) as avg_odds,
            ROUND(AVG(c1_winrate), 1) as avg_winrate,
            ROUND(AVG(c1_2nd_rate), 1) as avg_2nd_rate
        FROM race_results
        GROUP BY is_hit
        """

        cursor.execute(query)
        rows = cursor.fetchall()

        print(f"\n【信頼度{conf}】")
        print(f"{'状態':<8} {'件数':>8} {'平均オッズ':>10} {'1C勝率':>8} {'1C2連率':>9}")
        print("-" * 50)

        for row in rows:
            is_hit, cnt, avg_odds, avg_winrate, avg_2nd = row
            status = "★的中" if is_hit else "×不的中"
            print(f"{status:<8} {cnt:>8,} {avg_odds:>10.1f} {avg_winrate:>8.1f}% {avg_2nd:>9.1f}%")

    conn.close()


def analyze_high_hit_rate_conditions():
    """高的中率条件の抽出"""
    print("\n" + "=" * 70)
    print("【分析6】高的中率・高ROI条件の探索")
    print("=" * 70)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 複合条件での的中率を分析
    query = """
    WITH race_data AS (
        SELECT
            rp.confidence,
            e1.racer_rank as c1_rank,
            CASE
                WHEN t.odds < 20 THEN 'low'
                WHEN t.odds < 50 THEN 'mid'
                ELSE 'high'
            END as odds_category,
            CASE
                WHEN e1.win_rate >= 50 THEN 'high_wr'
                WHEN e1.win_rate >= 30 THEN 'mid_wr'
                ELSE 'low_wr'
            END as winrate_cat,
            t.odds,
            CASE
                WHEN r1.rank = '1' AND r2.rank = '2' AND r3.rank = '3' THEN 1
                ELSE 0
            END as is_hit
        FROM race_predictions rp
        JOIN races rc ON rp.race_id = rc.id
        JOIN entries e1 ON rp.race_id = e1.race_id AND e1.pit_number = 1
        JOIN trifecta_odds t ON rp.race_id = t.race_id AND t.combination = '1-2-3'
        JOIN results r1 ON rp.race_id = r1.race_id AND r1.pit_number = 1
        JOIN results r2 ON rp.race_id = r2.race_id AND r2.pit_number = 2
        JOIN results r3 ON rp.race_id = r3.race_id AND r3.pit_number = 3
        WHERE rp.prediction_type = 'before'
          AND rp.pit_number = 1
          AND rp.rank_prediction = 1
          AND rc.race_date BETWEEN '2020-01-01' AND '2025-12-31'
          AND e1.racer_rank IN ('A1', 'A2', 'B1', 'B2')
    )
    SELECT
        confidence,
        c1_rank,
        odds_category,
        winrate_cat,
        COUNT(*) as total,
        SUM(is_hit) as hits,
        ROUND(100.0 * SUM(is_hit) / COUNT(*), 2) as hit_rate,
        ROUND(AVG(odds), 1) as avg_odds,
        ROUND(100.0 * SUM(CASE WHEN is_hit = 1 THEN odds ELSE 0 END) / COUNT(*), 1) as roi
    FROM race_data
    GROUP BY confidence, c1_rank, odds_category, winrate_cat
    HAVING COUNT(*) >= 50  -- 母数50件以上
    ORDER BY roi DESC
    LIMIT 30
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    print(f"\n【ROI上位30条件】（母数50件以上）")
    print(f"{'信頼度':<4} {'1C級別':<5} {'オッズ帯':<6} {'勝率帯':<8} {'件数':>6} {'的中':>4} {'的中率':>7} {'ROI':>8}")
    print("-" * 70)

    for row in rows:
        conf, c1_rank, odds_cat, wr_cat, total, hits, hit_rate, avg_odds, roi = row
        roi_mark = "★★" if roi >= 150 else ("★" if roi >= 100 else "  ")
        print(f"{conf:<4} {c1_rank:<5} {odds_cat:<6} {wr_cat:<8} {total:>6} {hits:>4} {hit_rate:>6.2f}% {roi:>7.1f}%{roi_mark}")

    conn.close()


def analyze_confidence_calibration():
    """信頼度の校正状態を分析"""
    print("\n" + "=" * 70)
    print("【分析7】信頼度校正分析 - モデルの自信と実際の的中率")
    print("=" * 70)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 1着的中率で校正を確認
    query = """
    SELECT
        confidence,
        COUNT(*) as total,
        SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as first_hits,
        ROUND(100.0 * SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) / COUNT(*), 2) as first_rate,
        SUM(CASE WHEN res.rank IN ('1', '2', '3') THEN 1 ELSE 0 END) as top3_hits,
        ROUND(100.0 * SUM(CASE WHEN res.rank IN ('1', '2', '3') THEN 1 ELSE 0 END) / COUNT(*), 2) as top3_rate
    FROM race_predictions rp
    JOIN races rc ON rp.race_id = rc.id
    JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
    WHERE rp.prediction_type = 'before'
      AND rp.rank_prediction = 1
      AND rp.pit_number = 1  -- 1コース予測のみ
      AND rc.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    GROUP BY confidence
    ORDER BY confidence
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    print(f"\n【1コース1着予測時の実際の成績】")
    print(f"{'信頼度':<6} {'件数':>10} {'1着的中':>8} {'1着率':>8} {'3着内':>8} {'3着内率':>8}")
    print("-" * 60)

    for row in rows:
        conf, total, first_hits, first_rate, top3_hits, top3_rate = row
        # 期待される順序（A>B>C>D）と実際が合っているか
        print(f"{conf:<6} {total:>10,} {first_hits:>8} {first_rate:>7.2f}% {top3_hits:>8} {top3_rate:>7.2f}%")

    # 2着、3着予測の精度も確認
    print(f"\n【2着・3着予測の精度】")

    for rank in [2, 3]:
        query = f"""
        SELECT
            confidence,
            COUNT(*) as total,
            SUM(CASE WHEN res.rank = '{rank}' THEN 1 ELSE 0 END) as exact_hits,
            ROUND(100.0 * SUM(CASE WHEN res.rank = '{rank}' THEN 1 ELSE 0 END) / COUNT(*), 2) as exact_rate
        FROM race_predictions rp
        JOIN races rc ON rp.race_id = rc.id
        JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
        WHERE rp.prediction_type = 'before'
          AND rp.rank_prediction = {rank}
          AND rc.race_date BETWEEN '2020-01-01' AND '2025-12-31'
        GROUP BY confidence
        ORDER BY confidence
        """

        cursor.execute(query)
        rows = cursor.fetchall()

        print(f"\n[{rank}着予測]")
        print(f"{'信頼度':<6} {'件数':>10} {f'{rank}着的中':>10} {f'{rank}着率':>8}")
        print("-" * 45)

        for row in rows:
            conf, total, hits, rate = row
            print(f"{conf:<6} {total:>10,} {hits:>10} {rate:>7.2f}%")

    conn.close()


def main():
    print("信頼度別的中パターン深掘り分析")
    print("=" * 70)
    print("目的: 各信頼度で「どの条件が揃うと的中しやすいか」を発見する")
    print("=" * 70)

    analyze_confidence_odds_pattern()
    analyze_confidence_c1rank_pattern()
    analyze_confidence_predicted_course()
    analyze_score_gap_hit_pattern()
    analyze_hit_vs_miss_features()
    analyze_high_hit_rate_conditions()
    analyze_confidence_calibration()

    print("\n" + "=" * 70)
    print("分析完了")
    print("=" * 70)


if __name__ == "__main__":
    main()
