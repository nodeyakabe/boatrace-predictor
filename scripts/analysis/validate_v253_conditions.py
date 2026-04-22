#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
v2.53.0 新3条件の入念な検証スクリプト

検証内容:
  1. IS/OOS 詳細検証（2020-2022 vs 2023-2025）
  2. 論理的根拠分析（スコア分布・オッズ分布・1コース等級分布）
  3. 集中リスク確認（会場別・月別・的中内訳）
  4. 条件間の独立性確認

対象条件:
  - C_P143_125_150: C×p1-p4-p3×125-150倍×スコア70-80
  - C_P132_150_175: C×p1-p3-p2×150-175倍×スコア80-90
  - C_P143_175_200: C×p1-p4-p3×175-200倍×スコア90-100
"""
import sqlite3
import sys
import os
import io
from collections import defaultdict

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
elif hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)
from config.settings import DATABASE_PATH

VENUE_NAMES = {
    '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島', '05': '多摩川',
    '06': '浜名湖', '07': '蒲郡', '08': '常滑', '09': '津', '10': '三国',
    '11': 'びわこ', '12': '住之江', '13': '尼崎', '14': '鳴門', '15': '丸亀',
    '16': '児島', '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
    '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村',
}

CONDITIONS = [
    {
        'id': 'C_P143_125_150',
        'label': 'C×p1-p4-p3×125-150倍×スコア70-80',
        'pattern': '143',   # p1-p4-p3
        'odds_min': 125, 'odds_max': 150,
        'score_min': 70, 'score_max': 80,
    },
    {
        'id': 'C_P132_150_175',
        'label': 'C×p1-p3-p2×150-175倍×スコア80-90',
        'pattern': '132',   # p1-p3-p2
        'odds_min': 150, 'odds_max': 175,
        'score_min': 80, 'score_max': 90,
    },
    {
        'id': 'C_P143_175_200',
        'label': 'C×p1-p4-p3×175-200倍×スコア90-100',
        'pattern': '143',   # p1-p4-p3
        'odds_min': 175, 'odds_max': 200,
        'score_min': 90, 'score_max': 100,
    },
]

# 4月除外（GLOBAL_VENUE_MONTH_EXCLUDESに基づく標準フィルタ）
EXCLUDE_MONTHS = [4]


def build_query(pattern, odds_min, odds_max, score_min, score_max):
    """各条件のSQLを生成"""
    if pattern == '143':
        combo_expr = "CAST(pp.p1 AS TEXT)||'-'||CAST(pp.p4 AS TEXT)||'-'||CAST(pp.p3 AS TEXT)"
        hit_expr   = "CASE WHEN rp.act1=pp.p1 AND rp.act2=pp.p4 AND rp.act3=pp.p3 THEN 1 ELSE 0 END"
    else:  # 132
        combo_expr = "CAST(pp.p1 AS TEXT)||'-'||CAST(pp.p3 AS TEXT)||'-'||CAST(pp.p2 AS TEXT)"
        hit_expr   = "CASE WHEN rp.act1=pp.p1 AND rp.act2=pp.p3 AND rp.act3=pp.p2 THEN 1 ELSE 0 END"

    excl = ','.join(str(m) for m in EXCLUDE_MONTHS)

    sql = f"""
    WITH pred_pivot AS (
        SELECT race_id,
            MAX(CASE WHEN rank_prediction = 1 THEN pit_number END) AS p1,
            MAX(CASE WHEN rank_prediction = 2 THEN pit_number END) AS p2,
            MAX(CASE WHEN rank_prediction = 3 THEN pit_number END) AS p3,
            MAX(CASE WHEN rank_prediction = 4 THEN pit_number END) AS p4,
            MAX(CASE WHEN rank_prediction = 1 THEN confidence END) AS confidence,
            MAX(CASE WHEN rank_prediction = 1 THEN total_score END) AS total_score
        FROM race_predictions
        WHERE prediction_type = 'before'
        GROUP BY race_id
        HAVING p1 IS NOT NULL AND p2 IS NOT NULL
           AND p3 IS NOT NULL AND p4 IS NOT NULL
    ),
    result_pivot AS (
        SELECT race_id,
            MAX(CASE WHEN rank = '1' THEN pit_number END) AS act1,
            MAX(CASE WHEN rank = '2' THEN pit_number END) AS act2,
            MAX(CASE WHEN rank = '3' THEN pit_number END) AS act3
        FROM results WHERE is_invalid = 0
        GROUP BY race_id
        HAVING act1 IS NOT NULL AND act2 IS NOT NULL AND act3 IS NOT NULL
    )
    SELECT
        r.id            AS race_id,
        r.race_date,
        r.venue_code,
        r.race_number,
        CAST(strftime('%Y', r.race_date) AS INTEGER) AS yr,
        CAST(strftime('%m', r.race_date) AS INTEGER) AS mo,
        pp.confidence,
        CAST(pp.total_score AS REAL) AS score,
        e1.racer_rank   AS c1_grade,
        COALESCE(tod.odds, 0) AS odds,
        {hit_expr} AS hit
    FROM races r
    JOIN pred_pivot pp ON r.id = pp.race_id
    JOIN result_pivot rp ON r.id = rp.race_id
    LEFT JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
    LEFT JOIN trifecta_odds tod ON r.id = tod.race_id
        AND tod.combination = {combo_expr}
    WHERE r.race_date >= '2020-01-01'
      AND r.race_date < '2026-01-01'
      AND pp.confidence = 'C'
      AND CAST(strftime('%m', r.race_date) AS INTEGER) NOT IN ({excl})
      AND COALESCE(tod.odds, 0) >= {odds_min}
      AND COALESCE(tod.odds, 0) <  {odds_max}
      AND CAST(pp.total_score AS REAL) >= {score_min}
      AND CAST(pp.total_score AS REAL) <  {score_max}
    ORDER BY r.race_date, r.venue_code, r.race_number
    """
    return sql


def hhi(counts):
    """集中度指標 HHI（0=完全分散, 10000=完全集中）"""
    total = sum(counts)
    if total == 0:
        return 0
    return sum((c / total * 100) ** 2 for c in counts)


def analyze_condition(cursor, cond):
    rows = cursor.execute(build_query(
        cond['pattern'], cond['odds_min'], cond['odds_max'],
        cond['score_min'], cond['score_max']
    )).fetchall()

    cols = ['race_id', 'race_date', 'venue_id', 'race_number',
            'yr', 'mo', 'confidence', 'score', 'c1_grade', 'odds', 'hit']
    data = [dict(zip(cols, r)) for r in rows]

    IS_YEARS  = {2020, 2021, 2022}
    OOS_YEARS = {2023, 2024, 2025}

    is_rows  = [d for d in data if d['yr'] in IS_YEARS]
    oos_rows = [d for d in data if d['yr'] in OOS_YEARS]

    def stats(rows):
        bets = len(rows)
        hits = sum(d['hit'] for d in rows)
        invest = bets * 100
        payout = sum(d['odds'] * 100 for d in rows if d['hit'])
        roi = 100.0 * payout / invest if invest > 0 else 0
        profit = payout - invest
        hr = 100.0 * hits / bets if bets > 0 else 0
        return bets, hits, hr, roi, profit

    def year_stats(rows, years):
        out = {}
        for y in sorted(years):
            yr = [d for d in rows if d['yr'] == y]
            out[y] = stats(yr)
        return out

    print(f"\n{'='*80}")
    print(f"  {cond['id']}  /  {cond['label']}")
    print(f"{'='*80}")

    # ── 1. IS / OOS サマリー ─────────────────────────────────────
    print("\n[1] IS / OOS 比較\n")
    tot = stats(data)
    is_s  = stats(is_rows)
    oos_s = stats(oos_rows)
    print(f"{'期間':<12} {'件数':>5} {'的中':>4} {'的中率':>7} {'ROI':>8} {'収支':>12}")
    print("-" * 55)
    for label, s in [('IS  2020-22', is_s), ('OOS 2023-25', oos_s), ('全体 2020-25', tot)]:
        print(f"{label:<12} {s[0]:>5} {s[1]:>4} {s[2]:>6.1f}% {s[3]:>7.1f}% {s[4]:>+12,.0f}")

    # 年度別
    print("\n  年度別:")
    for y, s in year_stats(data, range(2020, 2026)).items():
        mark = 'IS' if y <= 2022 else 'OOS'
        judge = '○' if s[4] > 0 else '×'
        print(f"    {y}[{mark}]  {s[0]:>4}件  {s[1]:>2}的中  {s[2]:>5.1f}%  ROI {s[3]:>7.1f}%  {s[4]:>+10,.0f} {judge}")

    # IS/OOS ROI 判定
    if is_s[0] > 0 and oos_s[0] > 0:
        direction = "OOS > IS (良好・逆過学習)" if oos_s[3] > is_s[3] else "IS > OOS (要注意・過学習疑い)"
        print(f"\n  ROI方向: {direction}  (IS {is_s[3]:.1f}% → OOS {oos_s[3]:.1f}%)")

    # ── 2. 的中レース一覧（全件） ────────────────────────────────
    hits_data = [d for d in data if d['hit']]
    print(f"\n[2] 的中レース一覧  ({len(hits_data)}件)\n")
    print(f"{'日付':<12} {'会場':<6} {'R':>2} {'オッズ':>8} {'スコア':>6} {'等級':>4} {'IS/OOS':<7}")
    print("-" * 55)
    yr_payouts = defaultdict(float)
    for d in sorted(hits_data, key=lambda x: x['race_date']):
        mark = 'IS' if d['yr'] <= 2022 else 'OOS'
        vname = VENUE_NAMES.get(d['venue_id'], f"#{d['venue_id']}")
        yr_payouts[d['yr']] += d['odds'] * 100
        print(f"  {d['race_date']:<10}  {vname:<5}  {d['race_number']:>2}R  "
              f"{d['odds']:>6.1f}倍  {d['score']:>5.1f}pt  {str(d['c1_grade'] or '?'):<4}  {mark}")

    if hits_data:
        avg_odds = sum(d['odds'] for d in hits_data) / len(hits_data)
        max_odds = max(d['odds'] for d in hits_data)
        min_odds = min(d['odds'] for d in hits_data)
        print(f"\n  平均オッズ: {avg_odds:.1f}倍  最高: {max_odds:.1f}倍  最低: {min_odds:.1f}倍")
        # 最高配当1件の収支寄与率
        max_hit = max(hits_data, key=lambda x: x['odds'])
        total_payout = sum(d['odds'] * 100 for d in hits_data)
        contrib = 100.0 * max_hit['odds'] * 100 / total_payout
        print(f"  最高配当1件の収支寄与: {contrib:.1f}%  ({max_hit['race_date']} {VENUE_NAMES.get(max_hit['venue_id'], '?')} {max_hit['odds']:.1f}倍)")

    # ── 3. 会場分布（集中リスク） ────────────────────────────────
    print(f"\n[3] 会場別分布（集中リスク）\n")
    venue_bets = defaultdict(int)
    venue_hits = defaultdict(int)
    venue_payout = defaultdict(float)
    for d in data:
        venue_bets[d['venue_id']] += 1
        if d['hit']:
            venue_hits[d['venue_id']] += 1
            venue_payout[d['venue_id']] += d['odds'] * 100

    total_bets = len(data)
    total_hits = len(hits_data)
    print(f"{'会場':<6} {'件数':>5} {'%':>5} {'的中':>4} {'的中率':>7} {'収支':>10}")
    print("-" * 45)
    for vid, cnt in sorted(venue_bets.items(), key=lambda x: -x[1]):
        h = venue_hits[vid]
        pay = venue_payout[vid]
        profit = pay - cnt * 100
        hr = 100.0 * h / cnt if cnt > 0 else 0
        pct = 100.0 * cnt / total_bets
        print(f"  {VENUE_NAMES.get(vid, f'#{vid}'):<5} {cnt:>5}  {pct:>4.1f}%  {h:>3}  {hr:>6.1f}%  {profit:>+10,.0f}")

    hhi_bets = hhi(list(venue_bets.values()))
    hhi_hits = hhi(list(venue_hits.values())) if total_hits > 0 else 0
    print(f"\n  HHI（件数）: {hhi_bets:.0f}  HHI（的中）: {hhi_hits:.0f}")
    print(f"  ※ HHI目安: <500=分散 / 500-1500=中程度 / >1500=集中")

    # ── 4. 月別分布 ──────────────────────────────────────────────
    print(f"\n[4] 月別分布\n")
    mo_bets = defaultdict(int)
    mo_hits = defaultdict(int)
    mo_payout = defaultdict(float)
    for d in data:
        mo_bets[d['mo']] += 1
        if d['hit']:
            mo_hits[d['mo']] += 1
            mo_payout[d['mo']] += d['odds'] * 100

    print(f"{'月':<4} {'件数':>5} {'的中':>4} {'的中率':>7} {'収支':>10}")
    print("-" * 38)
    for m in range(1, 13):
        if m in EXCLUDE_MONTHS:
            continue
        cnt = mo_bets[m]
        h = mo_hits[m]
        if cnt == 0:
            continue
        profit = mo_payout[m] - cnt * 100
        hr = 100.0 * h / cnt
        print(f"  {m:>2}月  {cnt:>4}  {h:>3}  {hr:>6.1f}%  {profit:>+10,.0f}")

    hhi_mo = hhi(list(mo_bets.values()))
    hhi_mo_hits = hhi(list(mo_hits.values())) if total_hits > 0 else 0
    print(f"\n  HHI（件数）: {hhi_mo:.0f}  HHI（的中）: {hhi_mo_hits:.0f}")

    # ── 5. スコア分布 ─────────────────────────────────────────────
    print(f"\n[5] スコア帯内分布（5点刻み）\n")
    score_bets = defaultdict(int)
    score_hits = defaultdict(int)
    score_payout = defaultdict(float)
    for d in data:
        band = int(d['score'] // 5) * 5
        score_bets[band] += 1
        if d['hit']:
            score_hits[band] += 1
            score_payout[band] += d['odds'] * 100

    print(f"{'スコア帯':<10} {'件数':>5} {'的中':>4} {'的中率':>7} {'ROI':>8}")
    print("-" * 42)
    for band in sorted(score_bets.keys()):
        cnt = score_bets[band]
        h = score_hits[band]
        pay = score_payout[band]
        hr = 100.0 * h / cnt if cnt > 0 else 0
        roi = 100.0 * pay / (cnt * 100) if cnt > 0 else 0
        print(f"  {band}-{band+5}点   {cnt:>4}  {h:>3}  {hr:>6.1f}%  {roi:>7.1f}%")

    # ── 6. 1コース選手等級分布 ───────────────────────────────────
    print(f"\n[6] 1コース選手等級分布\n")
    grade_bets = defaultdict(int)
    grade_hits = defaultdict(int)
    for d in data:
        g = str(d['c1_grade'] or 'N/A')
        grade_bets[g] += 1
        if d['hit']:
            grade_hits[g] += 1

    print(f"{'等級':<6} {'件数':>5} {'%':>5} {'的中':>4} {'的中率':>7}")
    print("-" * 35)
    for g in ['A1', 'A2', 'B1', 'B2', 'N/A']:
        cnt = grade_bets[g]
        if cnt == 0:
            continue
        h = grade_hits[g]
        pct = 100.0 * cnt / total_bets
        hr = 100.0 * h / cnt
        print(f"  {g:<5} {cnt:>5}  {pct:>4.1f}%  {h:>3}  {hr:>6.1f}%")

    # ── 7. オッズ分布（帯内10倍刻み） ───────────────────────────
    print(f"\n[7] オッズ分布（10倍刻み）\n")
    odds_bets = defaultdict(int)
    odds_hits = defaultdict(int)
    odds_payout = defaultdict(float)
    for d in data:
        band = int(d['odds'] // 10) * 10
        odds_bets[band] += 1
        if d['hit']:
            odds_hits[band] += 1
            odds_payout[band] += d['odds'] * 100

    print(f"{'オッズ帯':<12} {'件数':>5} {'的中':>4} {'的中率':>7} {'ROI':>8}")
    print("-" * 45)
    for band in sorted(odds_bets.keys()):
        cnt = odds_bets[band]
        h = odds_hits[band]
        pay = odds_payout[band]
        hr = 100.0 * h / cnt if cnt > 0 else 0
        roi = 100.0 * pay / (cnt * 100) if cnt > 0 else 0
        print(f"  {band}-{band+10}倍  {cnt:>5}  {h:>3}  {hr:>6.1f}%  {roi:>7.1f}%")

    return data


def analyze_independence(all_data):
    """3条件間の重複チェック"""
    print(f"\n{'='*80}")
    print("  [補足] 3条件間の重複チェック")
    print(f"{'='*80}\n")
    sets = {cond['id']: set(d['race_id'] for d in rows) for cond, rows in all_data}
    ids = list(sets.keys())
    for i in range(len(ids)):
        for j in range(i+1, len(ids)):
            a, b = ids[i], ids[j]
            overlap = len(sets[a] & sets[b])
            print(f"  {a} ∩ {b} = {overlap}件")


def main():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("=" * 80)
    print("  v2.53.0 新3条件 入念検証レポート")
    print("  IS=2020-2022 / OOS=2023-2025 / 4月除外")
    print("=" * 80)

    all_data = []
    for cond in CONDITIONS:
        data = analyze_condition(cursor, cond)
        all_data.append((cond, data))

    analyze_independence(all_data)

    print(f"\n{'='*80}")
    print("  完了")
    print(f"{'='*80}\n")

    conn.close()


if __name__ == '__main__':
    main()
