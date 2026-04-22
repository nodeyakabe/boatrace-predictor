#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
中オッズ70-200倍帯 穴狙い4パターン拡張スキャン

目的:
    既採用穴狙い条件（p142/p132/p143/p124）の隣接オッズ帯を探索し、
    Tier1候補（ROI>=150%, 件数>=50件）を発見する。

スキャン対象（採用済み帯域の下方拡張）:
    p142 (p1-p4-p2): 現在100-300倍 → 70-100倍帯を追加検証
    p132 (p1-p3-p2): 現在200-300倍 → 100-200倍帯を追加検証
    p143 (p1-p4-p3): 現在200-300倍 → 100-200倍帯を追加検証
    p124 (p1-p2-p4): 現在150-200倍 → 70-150倍帯を追加検証

スキャン軸: パターン × 信頼度(A/B/C/D) × オッズ帯(25倍刻み) × スコア帯(10pt刻み)

評価:
    IS (2020-2022) / OOS (2023-2025) / Tier1 (2024-2025) の3段階

使用方法:
    python scripts/analysis/scan_middle_odds_patterns.py
    python scripts/analysis/scan_middle_odds_patterns.py --min-races 30  # 基準緩和
    python scripts/analysis/scan_middle_odds_patterns.py --all-bands     # 全帯域スキャン
"""
import sqlite3
import sys
import os
import io
import argparse
from collections import defaultdict
from typing import Dict, List, Tuple

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
elif hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)
from config.settings import DATABASE_PATH

# ─────────────────────────────────────────────
# スキャン設定
# ─────────────────────────────────────────────

# 既採用条件のオッズ帯（スキャン結果表示時に参考表示）
ADOPTED_BANDS = {
    'p142': (100, 300),
    'p132': (200, 300),
    'p143': (200, 300),
    'p124': (150, 200),
}

# スキャン対象帯域（採用済み帯域の「下方」）
SCAN_BANDS = {
    'p142': (70, 100),    # 70-100倍（採用100-300倍の下）
    'p132': (70, 200),    # 70-200倍（採用200-300倍の下）
    'p143': (70, 200),    # 70-200倍（採用200-300倍の下）
    'p124': (70, 150),    # 70-150倍（採用150-200倍の下）
}

# オッズ帯の分割境界（25倍刻み）
ODDS_BOUNDARIES = [70, 100, 125, 150, 175, 200, 250, 300]

# スコア帯の分割境界（10pt刻み）
SCORE_BOUNDARIES = [50, 60, 70, 80, 90, 100, 110]

CONFIDENCES = ['A', 'B', 'C', 'D']

YEAR_IS_END = 2022    # IS期間: 2020-2022
YEAR_OOS_START = 2023 # OOS期間: 2023-2025
YEAR_T1_START = 2024  # Tier1期間: 2024-2025


def fetch_scan_data(conn: sqlite3.Connection) -> List[dict]:
    """
    6年間の全予測×結果×オッズを一括取得する。
    バグ修正済み: strftime月抽出・予測rank_predictionベースのpit_number
    """
    print("データ取得中（初回は2-3分かかります）...")
    sql = """
    WITH pred_pivot AS (
        SELECT
            race_id,
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
        SELECT
            race_id,
            MAX(CASE WHEN rank = '1' THEN pit_number END) AS act1,
            MAX(CASE WHEN rank = '2' THEN pit_number END) AS act2,
            MAX(CASE WHEN rank = '3' THEN pit_number END) AS act3
        FROM results
        WHERE is_invalid = 0
        GROUP BY race_id
        HAVING act1 IS NOT NULL AND act2 IS NOT NULL AND act3 IS NOT NULL
    )
    SELECT
        CAST(strftime('%Y', r.race_date) AS INTEGER) AS yr,
        CAST(strftime('%m', r.race_date) AS INTEGER) AS mo,
        pp.confidence,
        pp.total_score,
        COALESCE(t142.odds, 0) AS odds_142,
        COALESCE(t132.odds, 0) AS odds_132,
        COALESCE(t143.odds, 0) AS odds_143,
        COALESCE(t124.odds, 0) AS odds_124,
        CASE WHEN rp.act1 = pp.p1 AND rp.act2 = pp.p4 AND rp.act3 = pp.p2 THEN 1 ELSE 0 END AS hit_142,
        CASE WHEN rp.act1 = pp.p1 AND rp.act2 = pp.p3 AND rp.act3 = pp.p2 THEN 1 ELSE 0 END AS hit_132,
        CASE WHEN rp.act1 = pp.p1 AND rp.act2 = pp.p4 AND rp.act3 = pp.p3 THEN 1 ELSE 0 END AS hit_143,
        CASE WHEN rp.act1 = pp.p1 AND rp.act2 = pp.p2 AND rp.act3 = pp.p4 THEN 1 ELSE 0 END AS hit_124
    FROM races r
    JOIN pred_pivot pp ON r.id = pp.race_id
    JOIN result_pivot rp ON r.id = rp.race_id
    LEFT JOIN trifecta_odds t142 ON r.id = t142.race_id
        AND t142.combination = CAST(pp.p1 AS TEXT)||'-'||CAST(pp.p4 AS TEXT)||'-'||CAST(pp.p2 AS TEXT)
    LEFT JOIN trifecta_odds t132 ON r.id = t132.race_id
        AND t132.combination = CAST(pp.p1 AS TEXT)||'-'||CAST(pp.p3 AS TEXT)||'-'||CAST(pp.p2 AS TEXT)
    LEFT JOIN trifecta_odds t143 ON r.id = t143.race_id
        AND t143.combination = CAST(pp.p1 AS TEXT)||'-'||CAST(pp.p4 AS TEXT)||'-'||CAST(pp.p3 AS TEXT)
    LEFT JOIN trifecta_odds t124 ON r.id = t124.race_id
        AND t124.combination = CAST(pp.p1 AS TEXT)||'-'||CAST(pp.p2 AS TEXT)||'-'||CAST(pp.p4 AS TEXT)
    WHERE r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
    """
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    print(f"  取得完了: {len(rows):,}件")
    return rows


def get_odds_band(odds: float, boundaries: list) -> str:
    if odds <= 0:
        return None
    for i in range(len(boundaries) - 1):
        lo, hi = boundaries[i], boundaries[i + 1]
        if lo <= odds < hi:
            return f"{lo}-{hi}"
    return None


def get_score_band(score: float, boundaries: list) -> str:
    if score is None:
        return None
    for i in range(len(boundaries) - 1):
        lo, hi = boundaries[i], boundaries[i + 1]
        if lo <= score < hi:
            return f"{lo}-{hi}"
    return None


def aggregate(rows, pattern: str, scan_lo: int, scan_hi: int) -> Dict:
    """
    指定パターン・オッズ帯でのスキャン集計を行う。
    key: (confidence, odds_band, score_band)
    value: {total, hits, investment, payout, ...年別データ}
    """
    # SQLのカラム名は odds_142 / hit_142（p を除いた番号のみ）
    num = pattern[1:]  # 'p142' -> '142'
    odds_key = f'odds_{num}'
    hit_key = f'hit_{num}'

    results = defaultdict(lambda: {
        'total': 0, 'hits': 0, 'investment': 0, 'payout': 0,
        'is_total': 0, 'is_hits': 0, 'is_invest': 0, 'is_payout': 0,
        'oos_total': 0, 'oos_hits': 0, 'oos_invest': 0, 'oos_payout': 0,
        't1_total': 0, 't1_hits': 0, 't1_invest': 0, 't1_payout': 0,
    })

    for row in rows:
        conf = row['confidence']
        if conf not in CONFIDENCES:
            continue
        score = row['total_score']
        odds = row[odds_key]
        hit = row[hit_key]
        yr = row['yr']
        mo = row['mo']

        # オッズ帯フィルター
        if not (scan_lo <= odds < scan_hi):
            continue

        obs = get_odds_band(odds, ODDS_BOUNDARIES)
        sbs = get_score_band(score, SCORE_BOUNDARIES)
        if obs is None or sbs is None:
            continue

        # 全体集計（信頼度別・オッズ帯別・スコア帯別）
        for key in [
            (conf, obs, sbs),       # 全3軸
            (conf, obs, 'all'),     # スコア帯なし
            (conf, 'all', sbs),     # オッズ帯なし（スコア帯のみ）
            ('all', obs, sbs),      # 信頼度なし
            (conf, 'all', 'all'),   # 信頼度のみ
            ('all', obs, 'all'),    # オッズ帯のみ
        ]:
            d = results[key]
            d['total'] += 1
            d['investment'] += 100
            if hit:
                d['hits'] += 1
                d['payout'] += odds * 100

            # IS/OOS/Tier1の分割
            if yr <= YEAR_IS_END:
                d['is_total'] += 1
                d['is_invest'] += 100
                if hit:
                    d['is_hits'] += 1
                    d['is_payout'] += odds * 100
            if yr >= YEAR_OOS_START:
                d['oos_total'] += 1
                d['oos_invest'] += 100
                if hit:
                    d['oos_hits'] += 1
                    d['oos_payout'] += odds * 100
            if yr >= YEAR_T1_START:
                d['t1_total'] += 1
                d['t1_invest'] += 100
                if hit:
                    d['t1_hits'] += 1
                    d['t1_payout'] += odds * 100

    return results


def calc_roi(invest, payout):
    if invest <= 0:
        return 0.0
    return 100.0 * payout / invest


def print_scan_result(pattern: str, agg: dict, min_races: int, show_all_bands: bool):
    """スキャン結果を表形式で出力"""
    adopted_lo, adopted_hi = ADOPTED_BANDS[pattern]
    scan_lo, scan_hi = SCAN_BANDS[pattern]

    print(f"\n{'='*110}")
    print(f"  パターン: {pattern.upper()} ({pattern_desc(pattern)})")
    print(f"  採用済み帯域: {adopted_lo}-{adopted_hi}倍  |  スキャン対象: {scan_lo}-{scan_hi}倍")
    print(f"{'='*110}")

    # Tier1候補（ROI>=150%, 件数>=50）を先に表示
    candidates = []
    for (conf, obs, sbs), d in agg.items():
        if conf == 'all' or obs == 'all' or sbs == 'all':
            continue
        if d['total'] < min_races:
            continue
        roi_full = calc_roi(d['investment'], d['payout'])
        roi_is = calc_roi(d['is_invest'], d['is_payout'])
        roi_oos = calc_roi(d['oos_invest'], d['oos_payout'])
        roi_t1 = calc_roi(d['t1_invest'], d['t1_payout'])
        profit = d['payout'] - d['investment']

        if roi_t1 >= 150 and d['t1_total'] >= 50:
            candidates.append({
                'conf': conf, 'obs': obs, 'sbs': sbs,
                'total': d['total'], 'hits': d['hits'],
                'roi_full': roi_full, 'profit': profit,
                'roi_is': roi_is, 'roi_oos': roi_oos, 'roi_t1': roi_t1,
                't1_total': d['t1_total'], 't1_hits': d['t1_hits'],
                'is_total': d['is_total'], 'oos_total': d['oos_total'],
            })

    if candidates:
        candidates.sort(key=lambda x: x['roi_t1'], reverse=True)
        print(f"\n  ★ Tier1候補（T1 ROI>=150%, T1件数>=50）")
        print(f"  {'信頼':>4} {'オッズ帯':>8} {'スコア帯':>8} {'全件':>6} {'IS ROI':>8} {'OOS ROI':>8} {'T1件':>6} {'T1 ROI':>8} {'T1的中':>6} {'6年収支':>12}")
        print("  " + "-"*90)
        for c in candidates:
            ois_oos_arrow = "↑" if c['roi_oos'] > c['roi_is'] else "↓"
            print(f"  {c['conf']:>4} {c['obs']:>8} {c['sbs']:>8} {c['total']:>6} "
                  f"{c['roi_is']:>7.1f}% {c['roi_oos']:>7.1f}%{ois_oos_arrow} "
                  f"{c['t1_total']:>6} {c['roi_t1']:>7.1f}% {c['t1_hits']:>6} "
                  f"{c['profit']:>+12,.0f}")
    else:
        print(f"  ★ Tier1候補なし（T1 ROI>=150%, T1件数>={min_races}を満たすセルなし）")

    # 信頼度別サマリー（スコア帯なし・オッズ帯別）
    print(f"\n  ─ 信頼度×オッズ帯 サマリー（全スコア帯合計, 件数>={min_races}）")
    print(f"  {'信頼':>4} {'オッズ帯':>8} {'全件':>6} {'IS ROI':>8} {'OOS ROI':>8} {'T1件':>6} {'T1 ROI':>8} {'6年収支':>12}")
    print("  " + "-"*75)

    summary_rows = []
    for conf in ['A', 'B', 'C', 'D']:
        for obs in get_odds_band_labels():
            d = agg.get((conf, obs, 'all'))
            if d is None or d['total'] < min_races:
                continue
            roi_full = calc_roi(d['investment'], d['payout'])
            roi_is = calc_roi(d['is_invest'], d['is_payout'])
            roi_oos = calc_roi(d['oos_invest'], d['oos_payout'])
            roi_t1 = calc_roi(d['t1_invest'], d['t1_payout'])
            profit = d['payout'] - d['investment']
            summary_rows.append((conf, obs, d['total'], roi_is, roi_oos, d['t1_total'], roi_t1, profit))

    summary_rows.sort(key=lambda x: x[6], reverse=True)
    for conf, obs, total, roi_is, roi_oos, t1_total, roi_t1, profit in summary_rows:
        arrow = "↑" if roi_oos > roi_is else "↓"
        marker = " ◎" if roi_t1 >= 200 else (" ○" if roi_t1 >= 150 else (" ×" if roi_t1 < 100 else ""))
        print(f"  {conf:>4} {obs:>8} {total:>6} "
              f"{roi_is:>7.1f}% {roi_oos:>7.1f}%{arrow} "
              f"{t1_total:>6} {roi_t1:>7.1f}%{marker} {profit:>+12,.0f}")

    if not summary_rows:
        print(f"  （{min_races}件以上のデータなし）")


def get_odds_band_labels() -> List[str]:
    labels = []
    for i in range(len(ODDS_BOUNDARIES) - 1):
        labels.append(f"{ODDS_BOUNDARIES[i]}-{ODDS_BOUNDARIES[i+1]}")
    return labels


def pattern_desc(p: str) -> str:
    descs = {
        'p142': 'p1-p4-p2: 4位が2着・2位が3着',
        'p132': 'p1-p3-p2: 3位が2着・2位が3着',
        'p143': 'p1-p4-p3: 4位が2着・3位が3着',
        'p124': 'p1-p2-p4: 2位が2着・4位が3着',
    }
    return descs.get(p, p)


def main():
    parser = argparse.ArgumentParser(description='中オッズ70-200倍帯 穴狙いパターン拡張スキャン')
    parser.add_argument('--min-races', type=int, default=50, help='最低件数（デフォルト: 50）')
    parser.add_argument('--all-bands', action='store_true', help='採用済み帯域含む全帯域スキャン')
    args = parser.parse_args()

    print("=" * 110)
    print("  中オッズ70-200倍帯 穴狙いパターン 拡張スキャン")
    print(f"  スキャン帯域: p142→70-100倍 / p132→70-200倍 / p143→70-200倍 / p124→70-150倍")
    print(f"  評価: IS(2020-2022) / OOS(2023-2025) / Tier1(2024-2025)")
    print(f"  最低件数フィルター: {args.min_races}件")
    print("=" * 110)

    conn = sqlite3.connect(DATABASE_PATH)
    rows = fetch_scan_data(conn)
    conn.close()

    for pattern in ['p142', 'p132', 'p143', 'p124']:
        lo, hi = SCAN_BANDS[pattern]
        if args.all_bands:
            hi = 300  # 全帯域
        agg = aggregate(rows, pattern, lo, hi)
        print_scan_result(pattern, agg, args.min_races, args.all_bands)

    print("\n" + "=" * 110)
    print("  スキャン完了")
    print("  ★Tier1候補があった場合 → quick_condition_test.py で単独Tier1テストを実施してください")
    print("=" * 110)


if __name__ == '__main__':
    main()
