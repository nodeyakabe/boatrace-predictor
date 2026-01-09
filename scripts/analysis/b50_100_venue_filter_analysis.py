# -*- coding: utf-8 -*-
"""
B×50-100条件 会場フィルター分析スクリプト
"""
import sqlite3
import sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/boatrace.db')

venue_names = {
    '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島', '05': '多摩川',
    '06': '浜名湖', '07': '蒲郡', '08': '常滑', '09': '津', '10': '三国',
    '11': 'びわこ', '12': '住之江', '13': '尼崎', '14': '鳴門', '15': '丸亀',
    '16': '児島', '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
    '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
}

# 会場別データ取得（ROI順）
query = '''
WITH race_base AS (
    SELECT r.id as race_id, r.venue_code, r.race_date,
           rp1.pit_number as p1, rp2.pit_number as p2, rp3.pit_number as p3,
           strftime('%Y', r.race_date) as year
    FROM races r
    JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
    JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
    JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
    WHERE rp.rank_prediction = 1
    AND rp.confidence = 'B'
    AND e1.racer_rank IN ('A1', 'B1')
    AND r.race_date >= '2022-01-01' AND r.race_date <= '2025-12-31'
),
actual_results AS (
    SELECT
        race_id,
        MAX(CASE WHEN rank = '1' THEN pit_number END) as result_1,
        MAX(CASE WHEN rank = '2' THEN pit_number END) as result_2,
        MAX(CASE WHEN rank = '3' THEN pit_number END) as result_3
    FROM results
    WHERE rank IN ('1', '2', '3')
    GROUP BY race_id
),
trifecta_results AS (
    SELECT rb.race_id, rb.venue_code, rb.year,
           tr.odds as odds,
           CASE WHEN ar.result_1 = rb.p1 AND ar.result_2 = rb.p2 AND ar.result_3 = rb.p3 THEN 1 ELSE 0 END as hit
    FROM race_base rb
    JOIN actual_results ar ON rb.race_id = ar.race_id
    LEFT JOIN trifecta_odds tr ON rb.race_id = tr.race_id
        AND tr.combination = printf('%d-%d-%d', rb.p1, rb.p2, rb.p3)
    WHERE tr.odds >= 50 AND tr.odds < 100
)
SELECT
    venue_code,
    COUNT(*) as cnt,
    SUM(hit) as hits,
    SUM(CASE WHEN hit=1 THEN odds*100 ELSE 0 END) as returns,
    SUM(CASE WHEN hit=1 THEN odds*100 ELSE 0 END) - COUNT(*)*100 as profit,
    (SUM(CASE WHEN hit=1 THEN odds*100 ELSE 0 END)) * 100.0 / (COUNT(*)*100) as roi
FROM trifecta_results
GROUP BY venue_code
ORDER BY roi ASC
'''

cursor = conn.cursor()
cursor.execute(query)
venue_data = cursor.fetchall()

# データを辞書化
venue_stats = {}
for row in venue_data:
    venue_stats[row[0]] = {
        'cnt': row[1],
        'hits': row[2],
        'returns': row[3],
        'profit': row[4],
        'roi': row[5]
    }

# 全体統計
total_cnt = sum(v['cnt'] for v in venue_stats.values())
total_hits = sum(v['hits'] for v in venue_stats.values())
total_returns = sum(v['returns'] for v in venue_stats.values())
total_profit = sum(v['profit'] for v in venue_stats.values())
total_roi = total_returns / (total_cnt * 100) * 100

print('='*70)
print('【元データ】B×50-100条件 全体統計')
print('='*70)
print(f'件数: {total_cnt}件')
print(f'的中: {total_hits}件 ({total_hits/total_cnt*100:.1f}%)')
print(f'収支: {total_profit:,.0f}円')
print(f'ROI: {total_roi:.1f}%')

# パターン1: 最悪の3会場除外
print()
print('='*70)
print('【パターン1】最悪の3会場除外')
print('='*70)

# ROI最悪の3会場（件数が多い順で同率の場合）
worst3 = sorted(venue_stats.items(), key=lambda x: (x[1]['roi'], -x[1]['cnt']))[:3]
worst3_codes = [w[0] for w in worst3]
worst3_names = [venue_names[c] for c in worst3_codes]

print(f"除外会場: {', '.join(worst3_names)}")
excluded_cnt = sum(venue_stats[c]['cnt'] for c in worst3_codes)
excluded_profit = sum(venue_stats[c]['profit'] for c in worst3_codes)
remaining_cnt = total_cnt - excluded_cnt
remaining_returns = total_returns - sum(venue_stats[c]['returns'] for c in worst3_codes)
remaining_profit = remaining_returns - remaining_cnt * 100
remaining_roi = remaining_returns / (remaining_cnt * 100) * 100
remaining_hits = total_hits - sum(venue_stats[c]['hits'] for c in worst3_codes)

print(f'除外後件数: {remaining_cnt}件 (元: {total_cnt}件, -{excluded_cnt}件)')
print(f'除外後的中: {remaining_hits}件 ({remaining_hits/remaining_cnt*100:.1f}%)')
print(f'除外後収支: {remaining_profit:,.0f}円 (元: {total_profit:,.0f}円, +{remaining_profit - total_profit:,.0f}円)')
print(f'除外後ROI: {remaining_roi:.1f}% (元: {total_roi:.1f}%, +{remaining_roi - total_roi:.1f}pt)')

# パターン2: 最悪の5会場除外
print()
print('='*70)
print('【パターン2】最悪の5会場除外')
print('='*70)

worst5 = sorted(venue_stats.items(), key=lambda x: (x[1]['roi'], -x[1]['cnt']))[:5]
worst5_codes = [w[0] for w in worst5]
worst5_names = [venue_names[c] for c in worst5_codes]

print(f"除外会場: {', '.join(worst5_names)}")
excluded_cnt = sum(venue_stats[c]['cnt'] for c in worst5_codes)
remaining_cnt = total_cnt - excluded_cnt
remaining_returns = total_returns - sum(venue_stats[c]['returns'] for c in worst5_codes)
remaining_profit = remaining_returns - remaining_cnt * 100
remaining_roi = remaining_returns / (remaining_cnt * 100) * 100
remaining_hits = total_hits - sum(venue_stats[c]['hits'] for c in worst5_codes)

print(f'除外後件数: {remaining_cnt}件 (元: {total_cnt}件, -{total_cnt - remaining_cnt}件)')
print(f'除外後的中: {remaining_hits}件 ({remaining_hits/remaining_cnt*100:.1f}%)')
print(f'除外後収支: {remaining_profit:,.0f}円 (元: {total_profit:,.0f}円, +{remaining_profit - total_profit:,.0f}円)')
print(f'除外後ROI: {remaining_roi:.1f}% (元: {total_roi:.1f}%, +{remaining_roi - total_roi:.1f}pt)')

# パターン3: ROI 50%未満の会場除外
print()
print('='*70)
print('【パターン3】ROI 50%未満の会場除外')
print('='*70)

under50_codes = [c for c, v in venue_stats.items() if v['roi'] < 50]
under50_names = [venue_names[c] for c in under50_codes]

print(f"除外会場({len(under50_codes)}会場): {', '.join(under50_names)}")
excluded_cnt = sum(venue_stats[c]['cnt'] for c in under50_codes)
remaining_cnt = total_cnt - excluded_cnt
remaining_returns = total_returns - sum(venue_stats[c]['returns'] for c in under50_codes)
remaining_profit = remaining_returns - remaining_cnt * 100
remaining_roi = remaining_returns / (remaining_cnt * 100) * 100
remaining_hits = total_hits - sum(venue_stats[c]['hits'] for c in under50_codes)

print(f'除外後件数: {remaining_cnt}件 (元: {total_cnt}件, -{total_cnt - remaining_cnt}件)')
print(f'除外後的中: {remaining_hits}件 ({remaining_hits/remaining_cnt*100:.1f}%)')
print(f'除外後収支: {remaining_profit:,.0f}円 (元: {total_profit:,.0f}円, +{remaining_profit - total_profit:,.0f}円)')
print(f'除外後ROI: {remaining_roi:.1f}% (元: {total_roi:.1f}%, +{remaining_roi - total_roi:.1f}pt)')

# パターン4: ROI 80%未満の会場除外
print()
print('='*70)
print('【パターン4】ROI 80%未満の会場除外')
print('='*70)

under80_codes = [c for c, v in venue_stats.items() if v['roi'] < 80]
under80_names = [venue_names[c] for c in under80_codes]

print(f"除外会場({len(under80_codes)}会場): {', '.join(under80_names)}")
excluded_cnt = sum(venue_stats[c]['cnt'] for c in under80_codes)
remaining_cnt = total_cnt - excluded_cnt
remaining_returns = total_returns - sum(venue_stats[c]['returns'] for c in under80_codes)
remaining_profit = remaining_returns - remaining_cnt * 100
remaining_roi = remaining_returns / (remaining_cnt * 100) * 100
remaining_hits = total_hits - sum(venue_stats[c]['hits'] for c in under80_codes)

print(f'除外後件数: {remaining_cnt}件 (元: {total_cnt}件, -{total_cnt - remaining_cnt}件)')
print(f'除外後的中: {remaining_hits}件 ({remaining_hits/remaining_cnt*100:.1f}%)')
print(f'除外後収支: {remaining_profit:,.0f}円 (元: {total_profit:,.0f}円, +{remaining_profit - total_profit:,.0f}円)')
print(f'除外後ROI: {remaining_roi:.1f}% (元: {total_roi:.1f}%, +{remaining_roi - total_roi:.1f}pt)')

conn.close()
