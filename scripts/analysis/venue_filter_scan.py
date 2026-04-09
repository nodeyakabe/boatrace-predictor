#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
フィルタ横展開スキャン: rank × venue × 30-50倍 の全組み合わせを評価

【目的】
  現行7条件でカバーされていない rank×venue の組み合わせを全列挙し、
  新たな「歪み」（市場の過小評価）を発見する。

【ルール（コア固定）】
  - 予測: P1-P2-P3 × 1点買い（変えない）
  - オッズ帯: 30-50倍（現行と同じ主力帯）
  - 4月除外: GLOBAL_MONTH_EXCLUDES = [4] に準拠

【採用基準（新Tier2）】
  - ROI 130%以上
  - 4/6年黒字
  - 6年合計 90件以上

【出力】
  全組み合わせのROI一覧 → 候補をハイライト
"""

import sqlite3
import sys
import os
import argparse
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

# 全24会場
VENUE_NAMES = {
    1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川',
    6: '浜名湖', 7: '蒲郡', 8: '常滑', 9: '津', 10: '三国',
    11: 'びわこ', 12: '住之江', 13: '尼崎', 14: '鳴門', 15: '丸亀',
    16: '児島', 17: '宮島', 18: '徳山', 19: '下関', 20: '若松',
    21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村',
}

# 現行でカバー済みの組み合わせ（スキャン結果でマーク）
ALREADY_COVERED = {
    # (rank, venue_id)
    ('B1', 15), ('B1', 13), ('B1', 7),   # A_B1_30_50_3VENUES
    ('B1', 9),                             # C_TSU_B1_30_50
    ('B1', 11),                            # C_B1_30_50_BIWAKO
    ('B1', 21),                            # C_B1_30_50_ASHIYA
    ('A1', 1), ('A1', 20), ('A1', 6), ('A1', 7),   # A_A1_30_50_4VENUES
    ('A1', 2), ('A1', 3), ('A1', 6), ('A1', 8),    # B_A1_30_50_8VENUES
    ('A1', 12), ('A1', 9), ('A1', 17), ('A1', 19),
    ('A2', 9), ('A2', 6), ('A2', 20),     # A_A2_30_50_3VENUES
}

GLOBAL_MONTH_EXCLUDES = [4]
ODDS_MIN = 30
ODDS_MAX = 50
YEARS = range(2020, 2026)


def scan_all_combinations(confidence_filter=None, rank_filter=None, venue_filter=None):
    """全rank×venue×confidence組み合わせのROIをスキャン"""

    ranks = rank_filter or ['B1', 'A1', 'A2']
    confidences = confidence_filter or ['A', 'B', 'C']

    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()

        # 必要なデータを一括取得
        print("データ取得中...", flush=True)

        # バックテストと完全に同じロジック:
        #   - confidence = rank_prediction=1（予測1位）の confidence
        #   - c1_rank = pit_number=1 の racer_rank（コース1選手のランク）
        # まず race_id ごとの基本情報（venue,date,conf,c1_rank）を取得
        cursor.execute('''
            SELECT r.id, CAST(r.venue_code AS INTEGER), r.race_date,
                   rp1.confidence, e1.racer_rank
            FROM races r
            JOIN race_predictions rp1 ON r.id = rp1.race_id
                AND rp1.prediction_type = 'before'
                AND rp1.rank_prediction = 1
            JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
            WHERE r.race_date >= '2020-01-01'
            AND r.race_date < '2026-01-01'
            AND CAST(strftime('%m', r.race_date) AS INTEGER) NOT IN (4)
        ''')
        rows_meta = cursor.fetchall()
        print(f"  レース件数（meta）: {len(rows_meta):,}", flush=True)

        race_info = {}
        conf_map = {}
        c1rank_map = {}
        for rid, vid, rdate, conf, c1r in rows_meta:
            race_info[rid] = (vid, rdate, int(rdate[5:7]), int(rdate[:4]))
            conf_map[rid] = conf
            c1rank_map[rid] = c1r

        all_race_ids = list(race_info.keys())

        # 全ピットのスコア・予測順位を取得
        print(f"  スコア取得中...", flush=True)
        score_map = {}
        rank_map = {}
        for i in range(0, len(all_race_ids), 5000):
            batch = all_race_ids[i:i+5000]
            ph2 = ','.join(['?'] * len(batch))
            cursor.execute(f'''
                SELECT race_id, pit_number, total_score, rank_prediction
                FROM race_predictions
                WHERE race_id IN ({ph2})
                AND prediction_type = 'before'
                AND total_score IS NOT NULL
            ''', batch)
            for rid, pit, sc, rp in cursor.fetchall():
                if rid not in score_map:
                    score_map[rid] = {}
                    rank_map[rid] = {}
                score_map[rid][pit] = sc
                rank_map[rid][pit] = rp

        print(f"  対象レース: {len(all_race_ids):,}", flush=True)

        # オッズ取得（30-50倍範囲のみ）
        print("  オッズ取得中...", flush=True)
        odds_map = {}
        for i in range(0, len(all_race_ids), 5000):
            batch = all_race_ids[i:i+5000]
            ph = ','.join(['?'] * len(batch))
            cursor.execute(f'''
                SELECT race_id, combination, odds FROM trifecta_odds
                WHERE race_id IN ({ph})
                AND odds >= {ODDS_MIN} AND odds < {ODDS_MAX}
            ''', batch)
            for rid, combo, odds in cursor.fetchall():
                if rid not in odds_map:
                    odds_map[rid] = {}
                odds_map[rid][combo] = odds

        # 結果取得
        print("  結果取得中...", flush=True)
        result_map = {}
        for i in range(0, len(all_race_ids), 5000):
            batch = all_race_ids[i:i+5000]
            ph = ','.join(['?'] * len(batch))
            cursor.execute(f'''
                SELECT race_id, pit_number, rank FROM results
                WHERE race_id IN ({ph})
                AND is_invalid=0 AND rank IN ('1','2','3')
            ''', batch)
            for rid, pit, rank in cursor.fetchall():
                if rid not in result_map:
                    result_map[rid] = {}
                result_map[rid][rank] = pit

    print(f"  データ準備完了。スキャン開始...\n", flush=True)

    # --- スキャン ---
    # (confidence, rank, venue_id) → {year: {n, hits, invest, payout}}
    combo_stats = {}

    for rid, (vid, rdate, month, year) in race_info.items():
        scores = score_map.get(rid)
        odds_data = odds_map.get(rid)
        res = result_map.get(rid)
        conf = conf_map.get(rid)
        c1r = c1rank_map.get(rid)

        if not scores or not odds_data or not res:
            continue
        if '1' not in res or '2' not in res or '3' not in res:
            continue
        pits = list(scores.keys())
        if len(pits) < 4:
            continue
        if conf not in confidences:
            continue
        if c1r not in ranks:
            continue
        if venue_filter and vid not in venue_filter:
            continue

        rm = rank_map.get(rid, {})
        pred_sorted = sorted([(rm.get(p, 9), p) for p in pits])
        pred_ranks = [p for _, p in pred_sorted]
        p1, p2, p3 = pred_ranks[0], pred_ranks[1], pred_ranks[2]
        combo_123 = f"{p1}-{p2}-{p3}"

        odds = odds_data.get(combo_123)
        if odds is None:
            continue

        actual = f"{res['1']}-{res['2']}-{res['3']}"
        hit = 1 if combo_123 == actual else 0

        key = (conf, c1r, vid)
        if key not in combo_stats:
            combo_stats[key] = {}
        if year not in combo_stats[key]:
            combo_stats[key][year] = {'n': 0, 'hits': 0, 'invest': 0, 'payout': 0.0}
        s = combo_stats[key][year]
        s['n'] += 1
        s['hits'] += hit
        s['invest'] += 100
        s['payout'] += odds * 100 if hit else 0

    # --- 集計 ---
    results = []
    for (conf, rank, vid), year_stats in combo_stats.items():
        total_n = sum(v['n'] for v in year_stats.values())
        total_hits = sum(v['hits'] for v in year_stats.values())
        total_invest = sum(v['invest'] for v in year_stats.values())
        total_payout = sum(v['payout'] for v in year_stats.values())

        if total_n < 30:  # 最低30件未満はスキップ
            continue

        roi = total_payout / total_invest * 100 if total_invest > 0 else 0
        profit = total_payout - total_invest
        hit_rate = total_hits / total_n * 100 if total_n > 0 else 0

        black_years = 0
        year_details = []
        for year in YEARS:
            ys = year_stats.get(year, {'n': 0, 'hits': 0, 'invest': 0, 'payout': 0.0})
            yr_profit = ys['payout'] - ys['invest']
            black_years += int(yr_profit > 0)
            year_details.append((year, ys['n'], yr_profit))

        covered = (rank, vid) in ALREADY_COVERED
        passes_tier2 = roi >= 130 and black_years >= 4 and total_n >= 90

        results.append({
            'conf': conf,
            'rank': rank,
            'vid': vid,
            'venue': VENUE_NAMES.get(vid, '?'),
            'n': total_n,
            'hits': total_hits,
            'roi': roi,
            'profit': profit,
            'hit_rate': hit_rate,
            'black_years': black_years,
            'year_details': year_details,
            'covered': covered,
            'passes': passes_tier2,
        })

    return results


def print_results(results, show_covered=False, min_n=50):
    # ROI降順
    results.sort(key=lambda x: x['roi'], reverse=True)

    print(f"\n{'='*95}")
    print(f"  フィルタ横展開スキャン結果（ROI降順）")
    print(f"  基準: ROI>=130% + 4/6年黒字 + 90件以上 -> 採用候補")
    print(f"{'='*95}")
    print(f"  {'信':>3} {'ランク':>5} {'会場':>6} {'件数':>5} {'的中':>4} {'ROI':>7} {'収支':>10} {'黒字年':>6}  年度別 / 現況")
    print("-" * 95)

    candidates = []
    for r in results:
        if r['n'] < min_n:
            continue
        if r['covered'] and not show_covered:
            continue

        marker = ''
        if r['passes']:
            marker = '★採用候補'
            candidates.append(r)
        elif r['roi'] >= 110 and r['black_years'] >= 3:
            marker = '△要注目'

        # 年度別収支サマリー
        yr_str = ' '.join(
            f"{'○' if p > 0 else '×'}{p/1000:+.0f}k"
            for yr, n, p in r['year_details'] if n > 0
        )

        print(f"  {r['conf']:>3} {r['rank']:>5} {r['venue']:>6}  "
              f"{r['n']:>4}  {r['hits']:>3}  {r['roi']:>6.1f}%  {r['profit']:>+9,.0f}  "
              f"{r['black_years']}/6年  {yr_str}  {marker}")

    print(f"\n  ★採用候補: {len(candidates)}件")
    return candidates


def print_candidates_detail(candidates):
    if not candidates:
        return
    print(f"\n{'='*70}")
    print("  ★採用候補 詳細（Tier2相当通過）")
    print(f"{'='*70}")
    for r in sorted(candidates, key=lambda x: x['roi'], reverse=True):
        print(f"\n  [{r['conf']}×{r['rank']}×{r['venue']}(id={r['vid']})×30-50倍]")
        print(f"    6年合計: {r['n']}件  {r['hits']}的中  ROI {r['roi']:.1f}%  収支{r['profit']:+,.0f}円  {r['black_years']}/6年黒字")
        for yr, n, p in r['year_details']:
            if n > 0:
                mark = '○' if p > 0 else '×'
                print(f"    {yr}年: {n}件  {mark}{p:+,.0f}円")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rank', nargs='+', choices=['B1','A1','A2'], default=None)
    parser.add_argument('--conf', nargs='+', choices=['A','B','C'], default=None)
    parser.add_argument('--venue', nargs='+', type=int, default=None)
    parser.add_argument('--show-covered', action='store_true', help='採用済みも表示')
    parser.add_argument('--min-n', type=int, default=50, help='最小件数フィルタ（デフォルト50）')
    parser.add_argument('--all', action='store_true', help='採用済み含む全組み合わせ表示')
    args = parser.parse_args()

    results = scan_all_combinations(
        confidence_filter=args.conf,
        rank_filter=args.rank,
        venue_filter=args.venue,
    )

    show_covered = args.show_covered or args.all
    candidates = print_results(results, show_covered=show_covered, min_n=args.min_n)
    print_candidates_detail(candidates)

    # 未開拓サマリー
    if not show_covered:
        print(f"\n  ※採用済みの条件は非表示（--show-covered で表示）")
        print(f"  ※件数{args.min_n}件未満は除外（--min-n N で変更）")


if __name__ == '__main__':
    main()
