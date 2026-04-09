#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
分析2: 高オッズ帯スキャン（50-70倍 × 全rank×venue）

現行30-50倍帯と同じロジックで、オッズ帯を50-70倍に変更してスキャン。

採用基準（50-70倍は件数が少ないため緩和）:
  - ROI >= 130%
  - 4/6年黒字
  - 50件以上（30-50倍の90件から緩和）
"""

import sqlite3
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

VENUE_NAMES = {
    1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川',
    6: '浜名湖', 7: '蒲郡', 8: '常滑', 9: '津', 10: '三国',
    11: 'びわこ', 12: '住之江', 13: '尼崎', 14: '鳴門', 15: '丸亀',
    16: '児島', 17: '宮島', 18: '徳山', 19: '下関', 20: '若松',
    21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村',
}

GLOBAL_MONTH_EXCLUDES = [4]
ODDS_MIN = 50
ODDS_MAX = 70
YEARS = range(2020, 2026)

# 現行30-50倍でカバー済みのrank×venue（参考情報として表示）
COVERED_30_50 = {
    ('B1', 15), ('B1', 13), ('B1', 7),   # A_B1_30_50_3VENUES
    ('B1', 9),                             # C_TSU_B1_30_50
    ('B1', 11),                            # C_B1_30_50_BIWAKO
    ('B1', 21),                            # C_B1_30_50_ASHIYA
    ('A1', 1), ('A1', 20), ('A1', 6), ('A1', 7),   # A_A1_30_50_4VENUES（30-70）
    ('A1', 2), ('A1', 3), ('A1', 8), ('A1', 12),   # B_A1_30_50_8VENUES
    ('A1', 9), ('A1', 17), ('A1', 19),
    ('A2', 9), ('A2', 6), ('A2', 20),     # A_A2_30_50_3VENUES
}


def scan_50_70():
    """50-70倍帯の全rank×venue×confidence組み合わせROIをスキャン"""

    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()

        print("データ取得中...", flush=True)

        # バックテストと完全に同じロジック:
        #   - confidence = rank_prediction=1（予測1位）のconfidence
        #   - c1_rank = pit_number=1 のracer_rank（コース1選手のランク）
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

        # 予測順位取得（P1-P2-P3コンビネーション構築のため）
        print("  スコア・予測順位取得中...", flush=True)
        rank_map = {}
        for i in range(0, len(all_race_ids), 5000):
            batch = all_race_ids[i:i+5000]
            ph2 = ','.join(['?'] * len(batch))
            cursor.execute(f'''
                SELECT race_id, pit_number, rank_prediction
                FROM race_predictions
                WHERE race_id IN ({ph2})
                AND prediction_type = 'before'
                AND rank_prediction <= 3
            ''', batch)
            for rid, pit, rp in cursor.fetchall():
                if rid not in rank_map:
                    rank_map[rid] = {}
                rank_map[rid][rp] = pit

        print(f"  対象レース: {len(all_race_ids):,}", flush=True)

        # オッズ取得（50-70倍範囲のみ）
        print("  オッズ取得中（50-70倍）...", flush=True)
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

    ranks = ['B1', 'A1', 'A2']
    confidences = ['A', 'B', 'C']

    # (confidence, rank, venue_id) → {year: stats}
    combo_stats = {}

    for rid, (vid, rdate, month, year) in race_info.items():
        odds_data = odds_map.get(rid)
        res = result_map.get(rid)
        conf = conf_map.get(rid)
        c1r = c1rank_map.get(rid)

        if not odds_data or not res:
            continue
        if '1' not in res or '2' not in res or '3' not in res:
            continue
        if conf not in confidences:
            continue
        if c1r not in ranks:
            continue

        # P1-P2-P3コンビネーション
        rm = rank_map.get(rid, {})
        p1 = rm.get(1)
        p2 = rm.get(2)
        p3 = rm.get(3)
        if not p1 or not p2 or not p3:
            continue
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

    # 集計
    results = []
    for (conf, rank, vid), year_stats in combo_stats.items():
        total_n = sum(v['n'] for v in year_stats.values())
        total_hits = sum(v['hits'] for v in year_stats.values())
        total_invest = sum(v['invest'] for v in year_stats.values())
        total_payout = sum(v['payout'] for v in year_stats.values())

        if total_n < 20:  # 最低20件未満はスキップ
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

        already_50_70 = False  # 50-70倍帯は今回新規スキャン

        passes_tier2 = roi >= 130 and black_years >= 4 and total_n >= 50

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
            'passes': passes_tier2,
            'in_30_50': (rank, vid) in COVERED_30_50,
        })

    return results


def print_results(results, min_n=30):
    results.sort(key=lambda x: x['roi'], reverse=True)

    print(f"\n{'='*105}")
    print(f"  分析2: 50-70倍帯スキャン結果（ROI降順）")
    print(f"  採用基準: ROI>=130% + 4/6年黒字 + 50件以上")
    print(f"{'='*105}")
    print(f"  {'信':>3} {'ランク':>5} {'会場':>6} {'件数':>5} {'的中':>4} {'的中率':>7} {'ROI':>8} {'収支':>10} {'黒字年':>6}  年度別  現況")
    print("-" * 105)

    candidates = []
    for r in results:
        if r['n'] < min_n:
            continue

        marker = ''
        if r['passes']:
            marker = '★採用候補'
            candidates.append(r)
        elif r['roi'] >= 110 and r['black_years'] >= 3:
            marker = '△要注目'
        elif r['roi'] >= 100 and r['black_years'] >= 3:
            marker = '参考'

        in_30_50_mark = '[30-50済]' if r['in_30_50'] else ''

        yr_str = '  '.join(
            f"{'○' if p > 0 else '×'}{p/1000:+.0f}k"
            for yr, n, p in r['year_details'] if n > 0
        )

        print(f"  {r['conf']:>3} {r['rank']:>5} {r['venue']:>6}  "
              f"{r['n']:>4}  {r['hits']:>3}  {r['hit_rate']:>5.1f}%  {r['roi']:>7.1f}%  {r['profit']:>+9,.0f}  "
              f"{r['black_years']}/6年  {yr_str}  {marker} {in_30_50_mark}")

    print(f"\n  ★採用候補: {len(candidates)}件")
    return candidates


def print_candidates_detail(candidates):
    if not candidates:
        return
    print(f"\n{'='*70}")
    print("  ★採用候補 詳細（50-70倍・Tier2相当通過）")
    print(f"{'='*70}")
    for r in sorted(candidates, key=lambda x: x['roi'], reverse=True):
        print(f"\n  [{r['conf']}×{r['rank']}×{r['venue']}(id={r['vid']})×50-70倍]")
        print(f"    6年合計: {r['n']}件  {r['hits']}的中  ROI {r['roi']:.1f}%  収支{r['profit']:+,.0f}円  {r['black_years']}/6年黒字")
        for yr, n, p in r['year_details']:
            if n > 0:
                mark = '○' if p > 0 else '×'
                print(f"    {yr}年: {n}件  {mark}{p:+,.0f}円")


if __name__ == '__main__':
    print("=== 分析2: 50-70倍帯スキャン ===")
    results = scan_50_70()
    candidates = print_results(results, min_n=30)
    print_candidates_detail(candidates)

    # 候補なしの場合
    tier2_candidates = [r for r in results if r['passes']]
    if not tier2_candidates:
        print("\n  発見: 候補なし（ROI>=130% + 4/6年黒字 + 50件以上を満たす組み合わせはなし）")
    else:
        print(f"\n  発見: {len(tier2_candidates)}件の採用候補を発見")
        for c in sorted(tier2_candidates, key=lambda x: x['roi'], reverse=True):
            print(f"    - {c['conf']}×{c['rank']}×{c['venue']}×50-70倍: {c['n']}件 ROI {c['roi']:.1f}% {c['black_years']}/6年黒字")
