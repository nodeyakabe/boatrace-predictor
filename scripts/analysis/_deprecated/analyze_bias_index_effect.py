# -*- coding: utf-8 -*-
"""
Bias Index効果検証スクリプト

予測バイアス指数（Bias Index）がベッティングに有効かを検証する。
- Bias Index: 予想より上に来やすいか（負）、過大評価されがち（正）か
- Error Variance: 外れる時のブレ幅
"""

import sqlite3
import sys
import io
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_PATH = Path(__file__).parent.parent.parent / "data" / "boatrace.db"


def get_connection():
    return sqlite3.connect(str(DB_PATH))


def analyze_bias_distribution():
    """Bias Indexの分布を確認"""
    conn = get_connection()
    cursor = conn.cursor()

    print("=" * 60)
    print("1. Bias Index分布の確認")
    print("=" * 60)

    cursor.execute("""
    SELECT
        CASE
            WHEN bias_index < -0.3 THEN 'A: bias < -0.3 (穴源)'
            WHEN bias_index < -0.1 THEN 'B: -0.3 <= bias < -0.1'
            WHEN bias_index < 0.1 THEN 'C: -0.1 <= bias < 0.1'
            WHEN bias_index < 0.3 THEN 'D: 0.1 <= bias < 0.3'
            ELSE 'E: bias >= 0.3 (過大評価)'
        END as bias_group,
        COUNT(*) as count,
        AVG(total_races) as avg_races,
        AVG(hit_rate_top3) as avg_top3_rate
    FROM player_bias_stats
    WHERE bias_index IS NOT NULL
    GROUP BY bias_group
    ORDER BY bias_group
    """)

    print("\nBias Index分布:")
    print("-" * 70)
    print(f"{'グループ':<30} | {'選手数':>6} | {'平均出走':>8} | {'平均3着内率':>10}")
    print("-" * 70)

    for group, count, avg_races, avg_top3 in cursor.fetchall():
        print(f"{group:<30} | {count:>6} | {avg_races:>8.1f} | {avg_top3:>9.1%}")

    conn.close()


def analyze_bias_by_prediction_rank():
    """予想順位別のBias Index効果を分析"""
    conn = get_connection()
    cursor = conn.cursor()

    print("\n" + "=" * 60)
    print("2. 予想1位選手のBias Index別実績（2020-2025年）")
    print("=" * 60)

    # 予想1位選手のBias Indexと実際の着順
    cursor.execute("""
    SELECT
        pbs.bias_index,
        CAST(res.rank AS INTEGER) as actual_rank,
        strftime('%Y', rc.race_date) as year
    FROM race_predictions rp
    JOIN races rc ON rp.race_id = rc.id
    JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
    JOIN entries e ON rp.race_id = e.race_id AND rp.pit_number = e.pit_number
    LEFT JOIN player_bias_stats pbs ON e.racer_number = pbs.player_id AND pbs.stadium_id IS NULL
    WHERE rp.prediction_type = 'before'
      AND rp.rank_prediction = 1
      AND res.rank IN ('1', '2', '3', '4', '5', '6')
      AND rc.race_date >= '2020-01-01'
      AND rc.race_date < '2026-01-01'
    """)

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("データなし")
        return

    # Bias Indexを区間に分けて集計
    bins = [
        ('bias<-0.3 (穴源)', lambda x: x is not None and x < -0.3),
        ('-0.3<=bias<-0.1', lambda x: x is not None and -0.3 <= x < -0.1),
        ('-0.1<=bias<0.1', lambda x: x is not None and -0.1 <= x < 0.1),
        ('0.1<=bias<0.3', lambda x: x is not None and 0.1 <= x < 0.3),
        ('bias>=0.3 (過大評価)', lambda x: x is not None and x >= 0.3),
        ('Bias不明', lambda x: x is None),
    ]

    stats = {name: {'total': 0, 'first': 0, 'top3': 0} for name, _ in bins}
    year_stats = {}

    for bias, actual_rank, year in rows:
        for name, cond in bins:
            if cond(bias):
                stats[name]['total'] += 1
                if actual_rank == 1:
                    stats[name]['first'] += 1
                if actual_rank <= 3:
                    stats[name]['top3'] += 1

                if year not in year_stats:
                    year_stats[year] = {n: {'total': 0, 'first': 0} for n, _ in bins}
                year_stats[year][name]['total'] += 1
                if actual_rank == 1:
                    year_stats[year][name]['first'] += 1
                break

    print("\n予想1位選手のBias Index別パフォーマンス:")
    print("-" * 70)
    print(f"{'Bias区間':<25} | {'件数':>7} | {'1着率':>6} | {'3着内率':>7}")
    print("-" * 70)

    for name, _ in bins:
        s = stats[name]
        if s['total'] > 0:
            first_rate = s['first'] / s['total']
            top3_rate = s['top3'] / s['total']
            print(f"{name:<25} | {s['total']:>7} | {first_rate:>5.1%} | {top3_rate:>6.1%}")

    # 年度別比較（穴源 vs 過大評価）
    print("\n年度別1着率 (穴源 vs 過大評価):")
    print("-" * 50)
    print(f"{'年':<6} | {'穴源件数':>8} | {'穴源1着率':>9} | {'過大評価件数':>10} | {'過大評価1着率':>11}")
    print("-" * 50)

    for year in sorted(year_stats.keys()):
        low = year_stats[year]['bias<-0.3 (穴源)']
        high = year_stats[year]['bias>=0.3 (過大評価)']
        low_rate = low['first'] / low['total'] if low['total'] > 0 else 0
        high_rate = high['first'] / high['total'] if high['total'] > 0 else 0
        print(f"{year:<6} | {low['total']:>8} | {low_rate:>8.1%} | {high['total']:>10} | {high_rate:>10.1%}")


def analyze_trifecta_with_bias():
    """3連単的中時の1着選手Bias Index分析"""
    conn = get_connection()
    cursor = conn.cursor()

    print("\n" + "=" * 60)
    print("3. 3連単的中/ハズレ時の予想1位選手Bias Index比較")
    print("=" * 60)

    # 予想1-2-3と実際の1-2-3を比較
    cursor.execute("""
    WITH prediction_123 AS (
        SELECT
            rc.id as race_id,
            rc.race_date,
            rp1.pit_number as pred_1,
            rp2.pit_number as pred_2,
            rp3.pit_number as pred_3,
            e1.racer_number as p1_racer
        FROM races rc
        JOIN race_predictions rp1 ON rc.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON rc.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON rc.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON rc.id = e1.race_id AND e1.pit_number = rp1.pit_number
        WHERE rc.race_date >= '2020-01-01' AND rc.race_date < '2026-01-01'
    ),
    actual_123 AS (
        SELECT
            race_id,
            MAX(CASE WHEN rank = '1' THEN pit_number END) as actual_1,
            MAX(CASE WHEN rank = '2' THEN pit_number END) as actual_2,
            MAX(CASE WHEN rank = '3' THEN pit_number END) as actual_3
        FROM results
        WHERE rank IN ('1', '2', '3')
        GROUP BY race_id
    )
    SELECT
        CASE WHEN p.pred_1 = a.actual_1 AND p.pred_2 = a.actual_2 AND p.pred_3 = a.actual_3
             THEN 1 ELSE 0 END as is_hit,
        pbs.bias_index,
        strftime('%Y', p.race_date) as year
    FROM prediction_123 p
    JOIN actual_123 a ON p.race_id = a.race_id
    LEFT JOIN player_bias_stats pbs ON p.p1_racer = pbs.player_id AND pbs.stadium_id IS NULL
    WHERE pbs.bias_index IS NOT NULL
    """)

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("データなし")
        return

    # 的中/ハズレ別にBias Index集計
    hit_biases = []
    miss_biases = []
    year_stats = {}

    for is_hit, bias, year in rows:
        if is_hit:
            hit_biases.append(bias)
        else:
            miss_biases.append(bias)

        if year not in year_stats:
            year_stats[year] = {'hit_bias': [], 'miss_bias': []}
        if is_hit:
            year_stats[year]['hit_bias'].append(bias)
        else:
            year_stats[year]['miss_bias'].append(bias)

    avg_hit = sum(hit_biases) / len(hit_biases) if hit_biases else 0
    avg_miss = sum(miss_biases) / len(miss_biases) if miss_biases else 0

    print(f"\n3連単1-2-3的中時の予想1位選手 平均Bias Index: {avg_hit:+.4f} (n={len(hit_biases)})")
    print(f"3連単1-2-3ハズレ時の予想1位選手 平均Bias Index: {avg_miss:+.4f} (n={len(miss_biases)})")
    print(f"差: {avg_hit - avg_miss:+.4f}")

    print("\n年度別:")
    print("-" * 50)
    print(f"{'年':<6} | {'的中時Bias':>10} | {'ハズレ時Bias':>12} | {'差':>8}")
    print("-" * 50)

    for year in sorted(year_stats.keys()):
        hit_avg = sum(year_stats[year]['hit_bias']) / len(year_stats[year]['hit_bias']) if year_stats[year]['hit_bias'] else 0
        miss_avg = sum(year_stats[year]['miss_bias']) / len(year_stats[year]['miss_bias']) if year_stats[year]['miss_bias'] else 0
        print(f"{year:<6} | {hit_avg:>+9.4f} | {miss_avg:>+11.4f} | {hit_avg - miss_avg:>+7.4f}")


def analyze_filter_simulation():
    """Bias Indexフィルターの効果シミュレーション"""
    conn = get_connection()
    cursor = conn.cursor()

    print("\n" + "=" * 60)
    print("4. Bias Indexフィルター効果シミュレーション（B信頼度×50-100倍）")
    print("=" * 60)

    # B信頼度×50-100倍の条件でシミュレーション
    cursor.execute("""
    WITH race_base AS (
        SELECT
            rc.id as race_id,
            rc.race_date,
            strftime('%Y', rc.race_date) as year,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3,
            e1.racer_number as p1_racer,
            rp.confidence
        FROM races rc
        JOIN race_predictions rp ON rc.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
        JOIN race_predictions rp1 ON rc.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON rc.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON rc.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON rc.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.confidence = 'B'
          AND e1.racer_rank IN ('A1', 'B1')
          AND rc.race_date >= '2020-01-01' AND rc.race_date < '2026-01-01'
    ),
    with_odds AS (
        SELECT
            rb.*,
            t.odds,
            pbs.bias_index
        FROM race_base rb
        JOIN trifecta_odds t ON rb.race_id = t.race_id
            AND t.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)
        LEFT JOIN player_bias_stats pbs ON rb.p1_racer = pbs.player_id AND pbs.stadium_id IS NULL
        WHERE t.odds >= 50 AND t.odds < 100
    ),
    with_results AS (
        SELECT
            wo.*,
            CASE WHEN r1.pit_number = wo.p1 AND r2.pit_number = wo.p2 AND r3.pit_number = wo.p3
                 THEN 1 ELSE 0 END as is_hit
        FROM with_odds wo
        LEFT JOIN results r1 ON wo.race_id = r1.race_id AND r1.rank = '1'
        LEFT JOIN results r2 ON wo.race_id = r2.race_id AND r2.rank = '2'
        LEFT JOIN results r3 ON wo.race_id = r3.race_id AND r3.rank = '3'
    )
    SELECT
        race_id, year, odds, is_hit, bias_index
    FROM with_results
    """)

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("データなし")
        return

    # ベースライン（フィルターなし）
    baseline = {'bets': 0, 'hits': 0, 'return': 0}
    year_baseline = {}

    for race_id, year, odds, is_hit, bias in rows:
        baseline['bets'] += 1
        if is_hit:
            baseline['hits'] += 1
            baseline['return'] += odds * 100

        if year not in year_baseline:
            year_baseline[year] = {'bets': 0, 'hits': 0, 'return': 0}
        year_baseline[year]['bets'] += 1
        if is_hit:
            year_baseline[year]['hits'] += 1
            year_baseline[year]['return'] += odds * 100

    baseline_roi = baseline['return'] / (baseline['bets'] * 100) if baseline['bets'] > 0 else 0

    print(f"\n【ベースライン】B信頼度×50-100倍（フィルターなし）:")
    print(f"  ベット数: {baseline['bets']}, 的中: {baseline['hits']}, ROI: {baseline_roi:.1%}")

    # フィルター候補
    filters = [
        ('予想1位のBias >= 0.3除外', lambda b: b is None or b < 0.3),
        ('予想1位のBias >= 0.2除外', lambda b: b is None or b < 0.2),
        ('予想1位のBias >= 0.1除外', lambda b: b is None or b < 0.1),
        ('予想1位のBias < -0.1のみ', lambda b: b is not None and b < -0.1),
        ('予想1位のBias < -0.2のみ', lambda b: b is not None and b < -0.2),
    ]

    print("\n【フィルター効果】:")
    print("-" * 80)
    print(f"{'フィルター':<30} | {'ベット':>6} | {'的中':>4} | {'ROI':>7} | {'ROI変化':>8}")
    print("-" * 80)

    best_filter = None
    best_roi_diff = -999

    for name, cond in filters:
        filtered = {'bets': 0, 'hits': 0, 'return': 0}
        year_filtered = {}

        for race_id, year, odds, is_hit, bias in rows:
            if cond(bias):
                filtered['bets'] += 1
                if is_hit:
                    filtered['hits'] += 1
                    filtered['return'] += odds * 100

                if year not in year_filtered:
                    year_filtered[year] = {'bets': 0, 'hits': 0, 'return': 0}
                year_filtered[year]['bets'] += 1
                if is_hit:
                    year_filtered[year]['hits'] += 1
                    year_filtered[year]['return'] += odds * 100

        if filtered['bets'] > 0:
            roi = filtered['return'] / (filtered['bets'] * 100)
            diff = roi - baseline_roi
            print(f"{name:<30} | {filtered['bets']:>6} | {filtered['hits']:>4} | {roi:>6.1%} | {diff:>+7.1%}")

            if diff > best_roi_diff:
                best_roi_diff = diff
                best_filter = (name, cond, filtered, year_filtered)

    # 最良フィルターの年度別詳細
    if best_filter:
        name, cond, filtered, year_filtered = best_filter
        print(f"\n【最良フィルター '{name}' の年度別詳細】:")
        print("-" * 60)
        print(f"{'年':<6} | {'ベット':>6} | {'的中':>4} | {'投資':>10} | {'回収':>10} | {'ROI':>7} | {'黒字?':>5}")
        print("-" * 60)

        profit_years = 0
        for year in sorted(year_filtered.keys()):
            s = year_filtered[year]
            if s['bets'] > 0:
                invest = s['bets'] * 100
                roi = s['return'] / invest if invest > 0 else 0
                profit = s['return'] - invest
                marker = "○" if roi > 1.0 else "×"
                if roi > 1.0:
                    profit_years += 1
                print(f"{year:<6} | {s['bets']:>6} | {s['hits']:>4} | {invest:>10,} | {int(s['return']):>10,} | {roi:>6.1%} | {marker:>5}")

        print("-" * 60)
        print(f"黒字年数: {profit_years}/{len(year_filtered)} (採用基準: 4/6以上)")

        # ベースラインの年度別も表示
        print(f"\n【比較用】ベースラインの年度別:")
        print("-" * 60)
        base_profit_years = 0
        for year in sorted(year_baseline.keys()):
            s = year_baseline[year]
            if s['bets'] > 0:
                invest = s['bets'] * 100
                roi = s['return'] / invest if invest > 0 else 0
                marker = "○" if roi > 1.0 else "×"
                if roi > 1.0:
                    base_profit_years += 1
                print(f"{year:<6} | {s['bets']:>6} | {s['hits']:>4} | {invest:>10,} | {int(s['return']):>10,} | {roi:>6.1%} | {marker:>5}")
        print(f"ベースライン黒字年数: {base_profit_years}/{len(year_baseline)}")


def analyze_error_variance():
    """Error Variance（着順差の分散）の効果を分析"""
    conn = get_connection()
    cursor = conn.cursor()

    print("\n" + "=" * 60)
    print("5. Error Variance（着順差の分散）の効果分析")
    print("=" * 60)

    # 予想1位選手のError Varianceと実際の着順
    cursor.execute("""
    SELECT
        pbs.error_variance,
        CAST(res.rank AS INTEGER) as actual_rank,
        strftime('%Y', rc.race_date) as year
    FROM race_predictions rp
    JOIN races rc ON rp.race_id = rc.id
    JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
    JOIN entries e ON rp.race_id = e.race_id AND rp.pit_number = e.pit_number
    LEFT JOIN player_bias_stats pbs ON e.racer_number = pbs.player_id AND pbs.stadium_id IS NULL
    WHERE rp.prediction_type = 'before'
      AND rp.rank_prediction = 1
      AND res.rank IN ('1', '2', '3', '4', '5', '6')
      AND rc.race_date >= '2020-01-01'
      AND rc.race_date < '2026-01-01'
      AND pbs.error_variance IS NOT NULL
    """)

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("データなし")
        return

    # Error Varianceを区間に分けて集計
    bins = [
        ('variance < 2.5 (安定)', lambda x: x < 2.5),
        ('2.5 <= variance < 3.0', lambda x: 2.5 <= x < 3.0),
        ('3.0 <= variance < 3.5', lambda x: 3.0 <= x < 3.5),
        ('variance >= 3.5 (不安定)', lambda x: x >= 3.5),
    ]

    stats = {name: {'total': 0, 'first': 0, 'top3': 0} for name, _ in bins}

    for var, actual_rank, year in rows:
        for name, cond in bins:
            if cond(var):
                stats[name]['total'] += 1
                if actual_rank == 1:
                    stats[name]['first'] += 1
                if actual_rank <= 3:
                    stats[name]['top3'] += 1
                break

    print("\n予想1位選手のError Variance別パフォーマンス:")
    print("-" * 70)
    print(f"{'Variance区間':<25} | {'件数':>7} | {'1着率':>6} | {'3着内率':>7}")
    print("-" * 70)

    for name, _ in bins:
        s = stats[name]
        if s['total'] > 0:
            first_rate = s['first'] / s['total']
            top3_rate = s['top3'] / s['total']
            print(f"{name:<25} | {s['total']:>7} | {first_rate:>5.1%} | {top3_rate:>6.1%}")


if __name__ == "__main__":
    print("Bias Index効果検証")
    print("=" * 60)

    analyze_bias_distribution()
    analyze_bias_by_prediction_rank()
    analyze_trifecta_with_bias()
    analyze_filter_simulation()
    analyze_error_variance()

    print("\n" + "=" * 60)
    print("検証完了")
    print("=" * 60)
