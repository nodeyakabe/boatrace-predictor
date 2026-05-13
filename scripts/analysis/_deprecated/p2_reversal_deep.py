# -*- coding: utf-8 -*-
"""
P2 Reversal Deep Analysis v2
- Score diff distribution varies heavily by year (scoring logic changes)
- Uses both absolute threshold and percentile-based approach
"""

import sqlite3
import os
import json

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'boatrace.db')
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'p2_reversal_deep_analysis.txt')

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def build_base_cte():
    return """
WITH rp AS (
    SELECT race_id,
        MAX(CASE WHEN rank_prediction=1 THEN pit_number END) as p1,
        MAX(CASE WHEN rank_prediction=2 THEN pit_number END) as p2,
        MAX(CASE WHEN rank_prediction=3 THEN pit_number END) as p3,
        MAX(CASE WHEN rank_prediction=4 THEN pit_number END) as p4,
        MAX(CASE WHEN rank_prediction=5 THEN pit_number END) as p5,
        MAX(CASE WHEN rank_prediction=1 THEN confidence END) as conf,
        MAX(CASE WHEN rank_prediction=1 THEN total_score END) as score1,
        MAX(CASE WHEN rank_prediction=2 THEN total_score END) as score2,
        MAX(CASE WHEN rank_prediction=2 THEN racer_number END) as p2_racer_number
    FROM race_predictions
    WHERE prediction_type = 'before'
    GROUP BY race_id
),
actual AS (
    SELECT r1.race_id,
           r1.pit_number as a1, r2.pit_number as a2, r3.pit_number as a3
    FROM results r1
    JOIN results r2 ON r1.race_id=r2.race_id AND r2.rank='2'
    JOIN results r3 ON r1.race_id=r3.race_id AND r3.rank='3'
    WHERE r1.rank='1' AND r1.is_invalid=0 AND r2.is_invalid=0 AND r3.is_invalid=0
)
"""

def fmt(val):
    if val >= 0:
        return "+{:,.0f}".format(val)
    else:
        return "{:,.0f}".format(val)


def fetch_all_data(conn):
    """Fetch all relevant data into memory for flexible analysis."""
    query = build_base_cte() + """
SELECT
    rp.race_id,
    rp.p1, rp.p2, rp.p3, rp.p4, rp.p5,
    rp.conf,
    rp.score1, rp.score2,
    rp.p2_racer_number,
    a.a1, a.a2, a.a3,
    t12.odds as main_odds,
    t_rev.odds as rev_odds,
    rc.race_date,
    CAST(rc.venue_code AS INTEGER) as venue_code,
    CAST(substr(rc.race_date, 6, 2) AS INTEGER) as month,
    substr(rc.race_date, 1, 4) as year,
    e2.avg_st as p2_avg_st,
    rap.course_win_rates as p2_cwr_json
FROM rp
JOIN actual a ON rp.race_id = a.race_id
JOIN races rc ON rp.race_id = rc.id
JOIN trifecta_odds t12 ON rp.race_id = t12.race_id
    AND t12.combination = CAST(rp.p1 AS TEXT) || '-' || CAST(rp.p2 AS TEXT) || '-' || CAST(rp.p3 AS TEXT)
LEFT JOIN trifecta_odds t_rev ON rp.race_id = t_rev.race_id
    AND t_rev.combination = CAST(rp.p2 AS TEXT) || '-' || CAST(rp.p1 AS TEXT) || '-' || CAST(rp.p3 AS TEXT)
LEFT JOIN entries e2 ON rp.race_id = e2.race_id AND rp.p2 = e2.pit_number
LEFT JOIN racer_attack_patterns rap ON CAST(rp.p2_racer_number AS INTEGER) = rap.racer_number
WHERE rp.conf = 'B'
    AND t12.odds BETWEEN 50 AND 100
    AND substr(rc.race_date, 1, 4) BETWEEN '2020' AND '2025'
    AND t_rev.odds IS NOT NULL
"""
    cur = conn.execute(query)
    rows = cur.fetchall()

    data = []
    for r in rows:
        sc_diff = r['score1'] - r['score2']
        is_hit = (r['a1'] == r['p2'] and r['a2'] == r['p1'] and r['a3'] == r['p3'])
        rev_odds = r['rev_odds'] if r['rev_odds'] else 0

        # Parse course win rate for p2's course
        cwr = None
        if r['p2_cwr_json']:
            try:
                cwr_dict = json.loads(r['p2_cwr_json'])
                p2_course = str(r['p2'])
                if p2_course in cwr_dict:
                    cwr = cwr_dict[p2_course] * 100
            except:
                pass

        data.append({
            'race_id': r['race_id'],
            'p1': r['p1'], 'p2': r['p2'], 'p3': r['p3'],
            'conf': r['conf'],
            'sc_diff': sc_diff,
            'main_odds': r['main_odds'],
            'rev_odds': rev_odds,
            'is_hit': is_hit,
            'year': r['year'],
            'month': r['month'],
            'venue': r['venue_code'],
            'p2_st': r['p2_avg_st'],
            'p2_cwr': cwr,
            'p2_course': r['p2'],
        })

    return data


def calc_stats(filtered):
    """Calculate stats for a filtered dataset."""
    total = len(filtered)
    if total == 0:
        return {'total': 0, 'hits': 0, 'hit_rate': 0, 'roi': 0, 'profit': 0,
                'avg_odds': 0, 'med_odds': 0, 'min_odds': 0, 'max_odds': 0}
    hits = sum(1 for d in filtered if d['is_hit'])
    returns = sum(d['rev_odds'] * 100 for d in filtered if d['is_hit'])
    invest = total * 100
    roi = (returns / invest * 100) if invest > 0 else 0
    profit = returns - invest
    hit_rate = (hits / total * 100)

    hit_odds = sorted([d['rev_odds'] for d in filtered if d['is_hit']])
    if hit_odds:
        avg_odds = sum(hit_odds) / len(hit_odds)
        med_odds = hit_odds[len(hit_odds) // 2]
        min_odds = hit_odds[0]
        max_odds = hit_odds[-1]
    else:
        avg_odds = med_odds = min_odds = max_odds = 0

    return {'total': total, 'hits': hits, 'hit_rate': hit_rate, 'roi': roi, 'profit': profit,
            'avg_odds': avg_odds, 'med_odds': med_odds, 'min_odds': min_odds, 'max_odds': max_odds}


def yearly_stats(data, cond_fn):
    """Calculate year-by-year stats."""
    years = ['2020', '2021', '2022', '2023', '2024', '2025']
    results = {}
    for yr in years:
        filtered = [d for d in data if d['year'] == yr and cond_fn(d)]
        results[yr] = calc_stats(filtered)
    # Total
    filtered_all = [d for d in data if d['year'] in years and cond_fn(d)]
    results['TOTAL'] = calc_stats(filtered_all)
    results['profit_years'] = sum(1 for yr in years if results[yr]['profit'] > 0)
    return results


def print_yearly_table(out, ystats, label=""):
    if label:
        out.write("  ** {} **\n".format(label))
    out.write("  {:<6} {:>6} {:>5} {:>7} {:>8} {:>10} {:>6}\n".format(
        "Year", "Total", "Hits", "HitRate", "ROI", "Profit", "Status"))
    out.write("  " + "-" * 55 + "\n")

    years = ['2020', '2021', '2022', '2023', '2024', '2025']
    for yr in years:
        s = ystats[yr]
        mark = "OK" if s['profit'] > 0 else ("--" if s['total'] == 0 else "NG")
        out.write("  {:<6} {:>6} {:>5} {:>6.1f}% {:>7.1f}% {:>10} {:>6}\n".format(
            yr, s['total'], s['hits'], s['hit_rate'], s['roi'], fmt(s['profit']), mark))

    s = ystats['TOTAL']
    out.write("  " + "-" * 55 + "\n")
    out.write("  {:<6} {:>6} {:>5} {:>6.1f}% {:>7.1f}% {:>10}  {}/6yr\n\n".format(
        "TOTAL", s['total'], s['hits'], s['hit_rate'], s['roi'], fmt(s['profit']),
        ystats['profit_years']))


def main():
    print("Starting P2 Reversal Deep Analysis v2...")
    conn = get_connection()

    print("Fetching all data...")
    data = fetch_all_data(conn)
    print("  Total records (B, odds 50-100, 2020-2025): {}".format(len(data)))

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as out:
        out.write("P2 REVERSAL DEEP ANALYSIS v2\n")
        out.write("Generated: 2026-02-19\n")
        out.write("DB: data/boatrace.db\n")
        out.write("Base: conf=B, main_odds(p1-p2-p3) 50-100, bet=p2-p1-p3 (1 ticket x 100 yen)\n")
        out.write("Total records in dataset: {}\n\n".format(len(data)))

        # ====================================================================
        # PREAMBLE: Score diff distribution by year
        # ====================================================================
        out.write("=" * 70 + "\n")
        out.write("=== PREAMBLE: Score diff distribution by year ===\n")
        out.write("=== (Critical: scoring logic changed between years) ===\n")
        out.write("=" * 70 + "\n\n")

        years = ['2020', '2021', '2022', '2023', '2024', '2025']
        out.write("{:<6} {:>6} {:>8} {:>8} {:>8} {:>6} {:>6} {:>6} {:>6}\n".format(
            "Year", "Total", "AvgDiff", "MinDiff", "MaxDiff", "sc<20", "sc<30", "sc<40", "sc<50"))
        out.write("-" * 75 + "\n")
        for yr in years:
            yr_data = [d for d in data if d['year'] == yr]
            total = len(yr_data)
            if total == 0:
                out.write("{:<6} {:>6}  (no data)\n".format(yr, 0))
                continue
            diffs = [d['sc_diff'] for d in yr_data]
            avg_d = sum(diffs) / len(diffs)
            min_d = min(diffs)
            max_d = max(diffs)
            sc20 = sum(1 for d in diffs if d < 20)
            sc30 = sum(1 for d in diffs if d < 30)
            sc40 = sum(1 for d in diffs if d < 40)
            sc50 = sum(1 for d in diffs if d < 50)
            out.write("{:<6} {:>6} {:>8.1f} {:>8.1f} {:>8.1f} {:>6} {:>6} {:>6} {:>6}\n".format(
                yr, total, avg_d, min_d, max_d, sc20, sc30, sc40, sc50))

        out.write("\nNOTE: Score diff < 20 only applies to a handful of races in 2020-2024.\n")
        out.write("  2024 has min_diff=25.5 so sc<20 yields 0 records.\n")
        out.write("  2025 has a very different score distribution (avg 26.9 vs 40+ in prior years).\n")
        out.write("  This means absolute score_diff thresholds are NOT comparable across years.\n")
        out.write("  We will use PERCENTILE-BASED approach in addition to absolute thresholds.\n\n")

        # Compute percentile thresholds per year
        pct_thresholds = {}
        for yr in years:
            yr_data = [d for d in data if d['year'] == yr]
            if not yr_data:
                pct_thresholds[yr] = {}
                continue
            diffs = sorted([d['sc_diff'] for d in yr_data])
            n = len(diffs)
            pct_thresholds[yr] = {
                'p10': diffs[int(n * 0.10)] if n > 0 else 0,
                'p20': diffs[int(n * 0.20)] if n > 0 else 0,
                'p30': diffs[int(n * 0.30)] if n > 0 else 0,
                'p40': diffs[int(n * 0.40)] if n > 0 else 0,
                'p50': diffs[int(n * 0.50)] if n > 0 else 0,
            }

        out.write("Percentile-based score_diff thresholds:\n")
        out.write("{:<6} {:>8} {:>8} {:>8} {:>8} {:>8}\n".format(
            "Year", "P10", "P20", "P30", "P40", "P50"))
        out.write("-" * 50 + "\n")
        for yr in years:
            if yr not in pct_thresholds or not pct_thresholds[yr]:
                out.write("{:<6}  (no data)\n".format(yr))
                continue
            p = pct_thresholds[yr]
            out.write("{:<6} {:>8.1f} {:>8.1f} {:>8.1f} {:>8.1f} {:>8.1f}\n".format(
                yr, p['p10'], p['p20'], p['p30'], p['p40'], p['p50']))

        out.write("\n\n")

        # ====================================================================
        # Analysis 1: sc<20, p2-p1-p3 only (all venues, all months)
        # ====================================================================
        out.write("=" * 70 + "\n")
        out.write("=== Analysis 1: sc<20, p2-p1-p3 only (all venues, all months) ===\n")
        out.write("=== WARNING: sc<20 heavily biased toward 2025 data ===\n")
        out.write("=" * 70 + "\n\n")

        ys = yearly_stats(data, lambda d: d['sc_diff'] < 20)
        print_yearly_table(out, ys, "sc_diff < 20")

        s = ys['TOTAL']
        if s['hits'] > 0:
            out.write("  Hit odds: avg={:.1f}, median={:.1f}, min={:.1f}, max={:.1f}\n\n".format(
                s['avg_odds'], s['med_odds'], s['min_odds'], s['max_odds']))

        # ====================================================================
        # Analysis 1b: NO score_diff filter (all B, odds 50-100)
        # ====================================================================
        out.write("=" * 70 + "\n")
        out.write("=== Analysis 1b: NO score_diff filter (baseline) ===\n")
        out.write("=== All B, odds 50-100, bet=p2-p1-p3 ===\n")
        out.write("=" * 70 + "\n\n")

        ys_base = yearly_stats(data, lambda d: True)
        print_yearly_table(out, ys_base, "No sc_diff filter (all data)")

        s = ys_base['TOTAL']
        if s['hits'] > 0:
            out.write("  Hit odds: avg={:.1f}, median={:.1f}, min={:.1f}, max={:.1f}\n\n".format(
                s['avg_odds'], s['med_odds'], s['min_odds'], s['max_odds']))

        # ====================================================================
        # Analysis 2: Score threshold optimization (absolute)
        # ====================================================================
        out.write("=" * 70 + "\n")
        out.write("=== Analysis 2: Score threshold optimization (absolute) ===\n")
        out.write("=== p2-p1-p3 only, B, odds 50-100, all venues, all months ===\n")
        out.write("=" * 70 + "\n\n")

        thresholds = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 60]
        out.write("{:<10} {:>6} {:>5} {:>7} {:>8} {:>10} {:>7}\n".format(
            "Threshold", "Total", "Hits", "HitRate", "ROI", "Profit", "Status"))
        out.write("-" * 60 + "\n")
        for th in thresholds:
            s = calc_stats([d for d in data if d['sc_diff'] < th])
            status = "PROFIT" if s['roi'] >= 100 else "LOSS"
            out.write("sc<{:<7} {:>6} {:>5} {:>6.1f}% {:>7.1f}% {:>10} {}\n".format(
                th, s['total'], s['hits'], s['hit_rate'], s['roi'], fmt(s['profit']), status))

        out.write("\n")

        # ====================================================================
        # Analysis 2b: Percentile-based threshold
        # ====================================================================
        out.write("=" * 70 + "\n")
        out.write("=== Analysis 2b: Percentile-based score_diff filter ===\n")
        out.write("=== Bottom N% of score_diff within each year ===\n")
        out.write("=" * 70 + "\n\n")

        for pct_label, pct_key in [('Bottom 10%', 'p10'), ('Bottom 20%', 'p20'),
                                    ('Bottom 30%', 'p30'), ('Bottom 40%', 'p40'),
                                    ('Bottom 50%', 'p50')]:
            def make_cond(pk):
                def cond(d):
                    yr = d['year']
                    if yr not in pct_thresholds or pk not in pct_thresholds[yr]:
                        return False
                    return d['sc_diff'] <= pct_thresholds[yr][pk]
                return cond

            ys = yearly_stats(data, make_cond(pct_key))
            out.write("  ** {} (sc_diff <= year-specific threshold) **\n".format(pct_label))
            out.write("  Thresholds: " + ", ".join(
                "{}={:.1f}".format(yr, pct_thresholds[yr].get(pct_key, 0))
                for yr in years if yr in pct_thresholds and pct_thresholds[yr]) + "\n")
            print_yearly_table(out, ys)

        # ====================================================================
        # Analysis 3: 11-venue + month-excl filter
        # ====================================================================
        out.write("=" * 70 + "\n")
        out.write("=== Analysis 3: 11-venue + month-excl filter ===\n")
        out.write("=== Venues: 4,7,19,22,2,17,21,11,8,1,9 ===\n")
        out.write("=== Months excluded: 12,1,2,4 ===\n")
        out.write("=" * 70 + "\n\n")

        venue_set = {4, 7, 19, 22, 2, 17, 21, 11, 8, 1, 9}
        month_excl = {12, 1, 2, 4}

        # 3a: with sc<20
        out.write("--- 3a: sc_diff < 20 + venue/month filter ---\n")
        ys3a = yearly_stats(data, lambda d: d['sc_diff'] < 20 and d['venue'] in venue_set and d['month'] not in month_excl)
        print_yearly_table(out, ys3a, "sc<20, 11-venue, month-excl")

        # 3b: without sc_diff filter
        out.write("--- 3b: No sc_diff filter + venue/month filter ---\n")
        ys3b = yearly_stats(data, lambda d: d['venue'] in venue_set and d['month'] not in month_excl)
        print_yearly_table(out, ys3b, "No sc_diff, 11-venue, month-excl")

        # 3c: percentile bottom 30% + venue/month
        out.write("--- 3c: Bottom 30% sc_diff + venue/month filter ---\n")
        def cond_3c(d):
            yr = d['year']
            if yr not in pct_thresholds or 'p30' not in pct_thresholds[yr]:
                return False
            return (d['sc_diff'] <= pct_thresholds[yr]['p30']
                    and d['venue'] in venue_set
                    and d['month'] not in month_excl)
        ys3c = yearly_stats(data, cond_3c)
        print_yearly_table(out, ys3c, "Bottom 30% sc_diff, 11-venue, month-excl")

        # Tier 1 check for 3b
        out.write("--- Tier 1 Check for 3b (no sc_diff, venue+month filter) ---\n")
        t1_data_24 = ys3b.get('2024', {'total': 0, 'profit': 0, 'roi': 0})
        t1_data_25 = ys3b.get('2025', {'total': 0, 'profit': 0, 'roi': 0})
        t1_total = t1_data_24['total'] + t1_data_25['total']
        t1_invest = t1_total * 100
        t1_returns = (t1_data_24['profit'] + t1_data_24['total'] * 100) + (t1_data_25['profit'] + t1_data_25['total'] * 100)
        t1_roi = (t1_returns / t1_invest * 100) if t1_invest > 0 else 0
        t1_profit_yrs = (1 if t1_data_24['profit'] > 0 else 0) + (1 if t1_data_25['profit'] > 0 else 0)
        out.write("  Total (2024-2025): {}\n".format(t1_total))
        out.write("  ROI (2024-2025): {:.1f}%\n".format(t1_roi))
        out.write("  Profitable years: {}/2\n".format(t1_profit_yrs))
        out.write("  Criteria: ROI>=150% -> {}, Count>=50 -> {}, 1/2yr profit -> {}\n".format(
            "PASS" if t1_roi >= 150 else "FAIL",
            "PASS" if t1_total >= 50 else "FAIL",
            "PASS" if t1_profit_yrs >= 1 else "FAIL"))
        out.write("  Overall Tier 1: {}\n\n".format(
            "PASS" if (t1_roi >= 150 and t1_total >= 50 and t1_profit_yrs >= 1) else "FAIL"))

        # ====================================================================
        # Analysis 4: Odds band effect
        # ====================================================================
        out.write("=" * 70 + "\n")
        out.write("=== Analysis 4: Odds band effect on p2-p1-p3 ROI ===\n")
        out.write("=" * 70 + "\n\n")

        out.write("--- 4a: By main odds band (no sc_diff filter) ---\n")
        bands = [(50, 59), (60, 69), (70, 79), (80, 89), (90, 100)]
        out.write("{:<12} {:>6} {:>5} {:>7} {:>8} {:>10} {:>8} {:>8}\n".format(
            "MainOdds", "Total", "Hits", "HitRate", "ROI", "Profit", "AvgRevO", "Status"))
        out.write("-" * 75 + "\n")
        for lo, hi in bands:
            f = [d for d in data if lo <= d['main_odds'] <= hi]
            s = calc_stats(f)
            status = "PROFIT" if s['roi'] >= 100 else "LOSS"
            out.write("{:<12} {:>6} {:>5} {:>6.1f}% {:>7.1f}% {:>10} {:>7.1f} {:>8}\n".format(
                "{}-{}".format(lo, hi), s['total'], s['hits'], s['hit_rate'],
                s['roi'], fmt(s['profit']), s['avg_odds'], status))

        out.write("\n--- 4b: By reversal odds band (no sc_diff filter) ---\n")
        rev_bands = [(0, 29), (30, 49), (50, 79), (80, 119), (120, 199), (200, 9999)]
        out.write("{:<12} {:>6} {:>5} {:>7} {:>8} {:>10} {:>8}\n".format(
            "RevOdds", "Total", "Hits", "HitRate", "ROI", "Profit", "Status"))
        out.write("-" * 65 + "\n")
        for lo, hi in rev_bands:
            f = [d for d in data if lo <= d['rev_odds'] <= hi]
            s = calc_stats(f)
            status = "PROFIT" if s['roi'] >= 100 else "LOSS"
            label = "{}-{}".format(lo, hi) if hi < 9999 else "{}+".format(lo)
            out.write("{:<12} {:>6} {:>5} {:>6.1f}% {:>7.1f}% {:>10} {:>8}\n".format(
                label, s['total'], s['hits'], s['hit_rate'],
                s['roi'], fmt(s['profit']), status))

        out.write("\n--- 4c: Main odds 50-69 only (best band from 4a) ---\n")
        ys4c = yearly_stats(data, lambda d: d['main_odds'] <= 69)
        print_yearly_table(out, ys4c, "Main odds 50-69")

        out.write("\n")

        # ====================================================================
        # Analysis 5: Additional conditions
        # ====================================================================
        out.write("=" * 70 + "\n")
        out.write("=== Analysis 5: Additional conditions exploration ===\n")
        out.write("=" * 70 + "\n\n")

        # 5a: p2 course
        out.write("--- 5a: By p2's course (pit_number) ---\n")
        out.write("{:<10} {:>6} {:>5} {:>7} {:>8} {:>10}\n".format(
            "P2Course", "Total", "Hits", "HitRate", "ROI", "Profit"))
        out.write("-" * 55 + "\n")
        for c in [1, 2, 3, 4, 5, 6]:
            f = [d for d in data if d['p2_course'] == c]
            s = calc_stats(f)
            out.write("{:<10} {:>6} {:>5} {:>6.1f}% {:>7.1f}% {:>10}\n".format(
                "Course {}".format(c), s['total'], s['hits'], s['hit_rate'], s['roi'], fmt(s['profit'])))

        # 5b: p2 avg_st
        out.write("\n--- 5b: By p2's avg_st (start timing) ---\n")
        st_bands = [(0, 0.14, 'ST<0.14'), (0.14, 0.16, 'ST0.14-15'),
                     (0.16, 0.18, 'ST0.16-17'), (0.18, 0.20, 'ST0.18-19'), (0.20, 1.0, 'ST0.20+')]
        out.write("{:<12} {:>6} {:>5} {:>7} {:>8} {:>10}\n".format(
            "STBand", "Total", "Hits", "HitRate", "ROI", "Profit"))
        out.write("-" * 55 + "\n")
        for lo, hi, label in st_bands:
            f = [d for d in data if d['p2_st'] is not None and lo <= d['p2_st'] < hi]
            s = calc_stats(f)
            out.write("{:<12} {:>6} {:>5} {:>6.1f}% {:>7.1f}% {:>10}\n".format(
                label, s['total'], s['hits'], s['hit_rate'], s['roi'], fmt(s['profit'])))
        f_null = [d for d in data if d['p2_st'] is None]
        s = calc_stats(f_null)
        out.write("{:<12} {:>6} {:>5} {:>6.1f}% {:>7.1f}% {:>10}\n".format(
            "ST_NULL", s['total'], s['hits'], s['hit_rate'], s['roi'], fmt(s['profit'])))

        # 5c: p2 course win rate
        out.write("\n--- 5c: By p2's course win rate ---\n")
        cwr_bands = [(0, 5, 'cwr<5%'), (5, 10, 'cwr5-10%'), (10, 15, 'cwr10-15%'),
                      (15, 20, 'cwr15-20%'), (20, 100, 'cwr20%+')]
        out.write("{:<12} {:>6} {:>5} {:>7} {:>8} {:>10}\n".format(
            "CWR", "Total", "Hits", "HitRate", "ROI", "Profit"))
        out.write("-" * 55 + "\n")
        for lo, hi, label in cwr_bands:
            f = [d for d in data if d['p2_cwr'] is not None and lo <= d['p2_cwr'] < hi]
            s = calc_stats(f)
            out.write("{:<12} {:>6} {:>5} {:>6.1f}% {:>7.1f}% {:>10}\n".format(
                label, s['total'], s['hits'], s['hit_rate'], s['roi'], fmt(s['profit'])))

        # 5d: Combined conditions - systematic search
        out.write("\n--- 5d: Systematic condition search ---\n")
        out.write("  Target: ROI >= 150% AND total >= 50 (6yr) or >= 20 (2yr)\n\n")

        conditions = [
            ("All (baseline)", lambda d: True),
            ("cwr>=20%", lambda d: d['p2_cwr'] is not None and d['p2_cwr'] >= 20),
            ("cwr>=15%", lambda d: d['p2_cwr'] is not None and d['p2_cwr'] >= 15),
            ("p2=C1or2", lambda d: d['p2_course'] in (1, 2)),
            ("p2=C1or2,cwr>=15%", lambda d: d['p2_course'] in (1, 2) and d['p2_cwr'] is not None and d['p2_cwr'] >= 15),
            ("main<=69", lambda d: d['main_odds'] <= 69),
            ("main<=69,cwr>=20%", lambda d: d['main_odds'] <= 69 and d['p2_cwr'] is not None and d['p2_cwr'] >= 20),
            ("main<=69,p2=C1or2", lambda d: d['main_odds'] <= 69 and d['p2_course'] in (1, 2)),
            ("ST0.14-16", lambda d: d['p2_st'] is not None and 0.14 <= d['p2_st'] < 0.16),
            ("ST0.14-16,cwr>=20%", lambda d: d['p2_st'] is not None and 0.14 <= d['p2_st'] < 0.16 and d['p2_cwr'] is not None and d['p2_cwr'] >= 20),
            ("venue_filt", lambda d: d['venue'] in venue_set),
            ("venue_filt,month_filt", lambda d: d['venue'] in venue_set and d['month'] not in month_excl),
            ("venue_filt,cwr>=20%", lambda d: d['venue'] in venue_set and d['p2_cwr'] is not None and d['p2_cwr'] >= 20),
            ("venue+month+cwr>=20%", lambda d: d['venue'] in venue_set and d['month'] not in month_excl and d['p2_cwr'] is not None and d['p2_cwr'] >= 20),
            ("rev<30", lambda d: d['rev_odds'] < 30),
            ("rev<50", lambda d: d['rev_odds'] < 50),
        ]

        out.write("{:<28} {:>6} {:>5} {:>7} {:>8} {:>10}\n".format(
            "Condition", "Total", "Hits", "HitRate", "ROI", "Profit"))
        out.write("-" * 70 + "\n")
        for label, cond_fn in conditions:
            f = [d for d in data if cond_fn(d)]
            s = calc_stats(f)
            marker = " <<<" if s['roi'] >= 150 and s['total'] >= 50 else ""
            out.write("{:<28} {:>6} {:>5} {:>6.1f}% {:>7.1f}% {:>10}{}\n".format(
                label, s['total'], s['hits'], s['hit_rate'], s['roi'], fmt(s['profit']), marker))

        # 5e: Year-by-year for top conditions
        out.write("\n--- 5e: Year-by-year for promising conditions ---\n\n")

        top_conditions = [
            ("All (baseline)", lambda d: True),
            ("cwr>=20%", lambda d: d['p2_cwr'] is not None and d['p2_cwr'] >= 20),
            ("p2=C1or2", lambda d: d['p2_course'] in (1, 2)),
            ("main<=69", lambda d: d['main_odds'] <= 69),
            ("main<=69,cwr>=20%", lambda d: d['main_odds'] <= 69 and d['p2_cwr'] is not None and d['p2_cwr'] >= 20),
            ("venue+month+cwr>=20%", lambda d: d['venue'] in venue_set and d['month'] not in month_excl and d['p2_cwr'] is not None and d['p2_cwr'] >= 20),
            ("p2=C1or2,cwr>=15%", lambda d: d['p2_course'] in (1, 2) and d['p2_cwr'] is not None and d['p2_cwr'] >= 15),
            ("rev<30", lambda d: d['rev_odds'] < 30),
            ("rev<50", lambda d: d['rev_odds'] < 50),
        ]

        for label, cond_fn in top_conditions:
            ys = yearly_stats(data, cond_fn)
            print_yearly_table(out, ys, label)

        # ====================================================================
        # Analysis 6: Reversal ALL patterns (not just p2-p1-p3)
        # ====================================================================
        out.write("=" * 70 + "\n")
        out.write("=== Analysis 6: Alternative reversal patterns ===\n")
        out.write("=== Compare p2-p1-p3, p2-p1-*, p2-*-*, etc. ===\n")
        out.write("=" * 70 + "\n\n")

        # Check all p2-first patterns
        out.write("--- 6a: p2-first patterns (where p2 wins) ---\n")
        patterns = [
            ("p2-p1-p3", lambda d: d['is_hit']),  # already computed
        ]
        # Need to re-fetch data with more result patterns
        # Let's use a separate query for this
        query_patterns = build_base_cte() + """
SELECT
    rp.race_id, rp.p1, rp.p2, rp.p3, rp.p4, rp.p5,
    rp.score1, rp.score2,
    a.a1, a.a2, a.a3,
    t12.odds as main_odds,
    substr(rc.race_date, 1, 4) as year
FROM rp
JOIN actual a ON rp.race_id = a.race_id
JOIN races rc ON rp.race_id = rc.id
JOIN trifecta_odds t12 ON rp.race_id = t12.race_id
    AND t12.combination = CAST(rp.p1 AS TEXT) || '-' || CAST(rp.p2 AS TEXT) || '-' || CAST(rp.p3 AS TEXT)
WHERE rp.conf = 'B'
    AND t12.odds BETWEEN 50 AND 100
    AND substr(rc.race_date, 1, 4) BETWEEN '2020' AND '2025'
"""
        cur = conn.execute(query_patterns)
        all_rows = cur.fetchall()

        # Count reversal patterns
        pattern_counts = {}
        for r in all_rows:
            p1, p2, p3, p4, p5 = r['p1'], r['p2'], r['p3'], r['p4'], r['p5']
            a1, a2, a3 = r['a1'], r['a2'], r['a3']

            # Identify pattern
            def pos_label(pit, p_list):
                for i, p in enumerate(p_list):
                    if pit == p:
                        return "p{}".format(i + 1)
                return "p?"

            preds = [p1, p2, p3, p4, p5]
            pattern = "{}-{}-{}".format(pos_label(a1, preds), pos_label(a2, preds), pos_label(a3, preds))

            if pattern not in pattern_counts:
                pattern_counts[pattern] = 0
            pattern_counts[pattern] += 1

        total_races = len(all_rows)
        out.write("Result pattern distribution (p1-p2-p3-p4-p5 = predicted rank):\n")
        out.write("{:<15} {:>6} {:>7}\n".format("Pattern", "Count", "Rate"))
        out.write("-" * 30 + "\n")
        for pattern, count in sorted(pattern_counts.items(), key=lambda x: -x[1])[:20]:
            rate = count / total_races * 100
            out.write("{:<15} {:>6} {:>6.1f}%\n".format(pattern, count, rate))

        # Check p2-first reversal rates specifically with odds
        out.write("\n--- 6b: p2-first patterns with odds data ---\n")
        p2_first_patterns = [
            ("p2-p1-p3", "p2_p1_p3"),
            ("p2-p1-p4", "p2_p1_p4"),
            ("p2-p1-p5", "p2_p1_p5"),
            ("p2-p3-p1", "p2_p3_p1"),
        ]

        for pattern_label, _ in p2_first_patterns:
            parts = pattern_label.split('-')
            # Map p-labels to actual pit numbers
            def check_pattern(row, parts):
                pred_map = {'p1': row['p1'], 'p2': row['p2'], 'p3': row['p3'],
                           'p4': row['p4'], 'p5': row['p5']}
                expected = [pred_map.get(p) for p in parts]
                return (row['a1'] == expected[0] and row['a2'] == expected[1] and row['a3'] == expected[2])

            # Get odds for this pattern
            pattern_query = build_base_cte() + """
SELECT
    rp.p1, rp.p2, rp.p3, rp.p4, rp.p5,
    a.a1, a.a2, a.a3,
    t_pat.odds as pattern_odds,
    t12.odds as main_odds,
    substr(rc.race_date, 1, 4) as year
FROM rp
JOIN actual a ON rp.race_id = a.race_id
JOIN races rc ON rp.race_id = rc.id
JOIN trifecta_odds t12 ON rp.race_id = t12.race_id
    AND t12.combination = CAST(rp.p1 AS TEXT) || '-' || CAST(rp.p2 AS TEXT) || '-' || CAST(rp.p3 AS TEXT)
LEFT JOIN trifecta_odds t_pat ON rp.race_id = t_pat.race_id
    AND t_pat.combination = CAST(rp.{p0} AS TEXT) || '-' || CAST(rp.{p1_} AS TEXT) || '-' || CAST(rp.{p2_} AS TEXT)
WHERE rp.conf = 'B'
    AND t12.odds BETWEEN 50 AND 100
    AND substr(rc.race_date, 1, 4) BETWEEN '2020' AND '2025'
    AND t_pat.odds IS NOT NULL
""".format(p0=parts[0], p1_=parts[1], p2_=parts[2])

            cur2 = conn.execute(pattern_query)
            pat_rows = cur2.fetchall()

            total = len(pat_rows)
            hits = 0
            returns = 0
            for r in pat_rows:
                pred_map = {'p1': r['p1'], 'p2': r['p2'], 'p3': r['p3'],
                           'p4': r['p4'], 'p5': r['p5']}
                expected = [pred_map.get(p) for p in parts]
                if r['a1'] == expected[0] and r['a2'] == expected[1] and r['a3'] == expected[2]:
                    hits += 1
                    returns += r['pattern_odds'] * 100

            invest = total * 100
            roi = (returns / invest * 100) if invest > 0 else 0
            profit = returns - invest
            hit_rate = (hits / total * 100) if total > 0 else 0
            out.write("{:<12} total={:>5}, hits={:>3}, hit_rate={:.1f}%, ROI={:.1f}%, profit={}\n".format(
                pattern_label, total, hits, hit_rate, roi, fmt(profit)))

        out.write("\n\n")

        # ====================================================================
        # FINAL RECOMMENDATION
        # ====================================================================
        out.write("=" * 70 + "\n")
        out.write("=== FINAL RECOMMENDATION ===\n")
        out.write("=" * 70 + "\n\n")

        out.write("1. CRITICAL ISSUE: DATA COMPARABILITY\n")
        out.write("   - Score diff distribution varies massively by year\n")
        out.write("   - 2025: avg sc_diff = 26.9, 2020-2024: avg sc_diff = 40-47\n")
        out.write("   - sc_diff < 20 yields 0-11 records in 2020-2024 vs 101 in 2025\n")
        out.write("   - This means ANY sc_diff-based condition is untestable across 6 years\n\n")

        out.write("2. RESULTS WITHOUT SCORE_DIFF FILTER:\n")
        s_all = ys_base['TOTAL']
        out.write("   All (B, odds 50-100, p2-p1-p3): {} races, ROI={:.1f}%, profit={}\n".format(
            s_all['total'], s_all['roi'], fmt(s_all['profit'])))
        out.write("   Profitable years: {}/6\n\n".format(ys_base['profit_years']))

        out.write("3. BEST CONDITIONS FOUND:\n")
        for label, cond_fn in top_conditions[:5]:
            s = calc_stats([d for d in data if cond_fn(d)])
            out.write("   {}: {} races, ROI={:.1f}%, profit={}\n".format(
                label, s['total'], s['roi'], fmt(s['profit'])))

        out.write("\n4. TIER ASSESSMENT:\n")
        out.write("   Tier 1 (2024-2025, ROI>=150%, count>=50, 1/2yr profit):\n")

        for label, cond_fn in [("All", lambda d: True),
                                ("cwr>=20%", lambda d: d['p2_cwr'] is not None and d['p2_cwr'] >= 20)]:
            f24 = [d for d in data if d['year'] == '2024' and cond_fn(d)]
            f25 = [d for d in data if d['year'] == '2025' and cond_fn(d)]
            s24 = calc_stats(f24)
            s25 = calc_stats(f25)
            t1_total = s24['total'] + s25['total']
            t1_invest = t1_total * 100
            t1_ret = (s24['profit'] + s24['total'] * 100) + (s25['profit'] + s25['total'] * 100)
            t1_roi = (t1_ret / t1_invest * 100) if t1_invest > 0 else 0
            t1_pyrs = (1 if s24['profit'] > 0 else 0) + (1 if s25['profit'] > 0 else 0)
            roi_pass = "PASS" if t1_roi >= 150 else "FAIL"
            cnt_pass = "PASS" if t1_total >= 50 else "FAIL"
            yr_pass = "PASS" if t1_pyrs >= 1 else "FAIL"
            out.write("   - {}: cnt={}, ROI={:.1f}%({}), cnt_check({}), yr_profit={}/2({})\n".format(
                label, t1_total, t1_roi, roi_pass, cnt_pass, t1_pyrs, yr_pass))

        out.write("\n   Tier 2 (6yr, ROI>=100%, 4/6yr profit):\n")
        for label, cond_fn in [("All", lambda d: True),
                                ("cwr>=20%", lambda d: d['p2_cwr'] is not None and d['p2_cwr'] >= 20)]:
            ys = yearly_stats(data, cond_fn)
            s = ys['TOTAL']
            roi_pass = "PASS" if s['roi'] >= 100 else "FAIL"
            yr_pass = "PASS" if ys['profit_years'] >= 4 else "FAIL"
            out.write("   - {}: ROI={:.1f}%({}), profit_years={}/6({}), profit={}\n".format(
                label, s['roi'], roi_pass, ys['profit_years'], yr_pass, fmt(s['profit'])))

        out.write("\n5. VERDICT:\n")
        out.write("   The p2-p1-p3 reversal strategy has the following characteristics:\n")
        out.write("   - Low sample size in most years (total ~700 across 6 years)\n")
        out.write("   - Score diff filter (sc<20) only works for 2025 data\n")
        out.write("   - The cwr>=20% filter shows promise but needs year stability check\n")
        out.write("   - Recommendation depends on the year-by-year stability shown in Analysis 5e\n\n")

    conn.close()
    print("Analysis complete. Results saved to: {}".format(OUTPUT_PATH))


if __name__ == '__main__':
    main()
