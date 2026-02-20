# -*- coding: utf-8 -*-
"""
B×50-100条件 年度別安定性分析
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

# 年度×会場別データ取得
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
    year,
    venue_code,
    COUNT(*) as cnt,
    SUM(hit) as hits,
    SUM(CASE WHEN hit=1 THEN odds*100 ELSE 0 END) as returns,
    SUM(CASE WHEN hit=1 THEN odds*100 ELSE 0 END) - COUNT(*)*100 as profit
FROM trifecta_results
GROUP BY year, venue_code
ORDER BY year, venue_code
'''

cursor = conn.cursor()
cursor.execute(query)
data = cursor.fetchall()

# データを整理
yearly_venue_data = {}
for row in data:
    year, venue_code, cnt, hits, returns, profit = row
    if year not in yearly_venue_data:
        yearly_venue_data[year] = {}
    yearly_venue_data[year][venue_code] = {
        'cnt': cnt, 'hits': hits, 'returns': returns, 'profit': profit
    }

# 除外パターン定義
worst3_codes = ['14', '09', '23']  # 鳴門, 津, 唐津
worst5_codes = ['14', '09', '23', '10', '18']  # 鳴門, 津, 唐津, 三国, 徳山
roi_under50_codes = ['01', '05', '06', '09', '10', '12', '13', '14', '15', '16', '18', '20', '21', '22', '23', '24']

patterns = {
    'フィルタなし': [],
    '3会場除外(鳴門,津,唐津)': worst3_codes,
    '5会場除外(鳴門,津,唐津,三国,徳山)': worst5_codes,
    'ROI50%未満除外(16会場)': roi_under50_codes
}

print('='*90)
print('B×50-100条件 年度別安定性分析')
print('='*90)

for pattern_name, exclude_codes in patterns.items():
    print()
    print(f'【{pattern_name}】')
    print('-'*90)
    print(f"{'年度':>6} {'件数':>6} {'的中':>4} {'的中率':>8} {'収支':>12} {'ROI':>10}")
    print('-'*90)

    all_years_cnt = 0
    all_years_returns = 0
    all_years_hits = 0
    all_years_profit = 0

    for year in sorted(yearly_venue_data.keys()):
        year_cnt = 0
        year_returns = 0
        year_hits = 0

        for venue_code, stats in yearly_venue_data[year].items():
            if venue_code not in exclude_codes:
                year_cnt += stats['cnt']
                year_returns += stats['returns']
                year_hits += stats['hits']

        if year_cnt > 0:
            year_profit = year_returns - year_cnt * 100
            year_roi = year_returns / (year_cnt * 100) * 100
            print(f"{year:>6} {year_cnt:>6} {year_hits:>4} {year_hits/year_cnt*100:>7.1f}% {year_profit:>11,.0f} {year_roi:>9.1f}%")

            all_years_cnt += year_cnt
            all_years_returns += year_returns
            all_years_hits += year_hits
            all_years_profit += year_profit

    print('-'*90)
    if all_years_cnt > 0:
        all_roi = all_years_returns / (all_years_cnt * 100) * 100
        print(f"{'合計':>6} {all_years_cnt:>6} {all_years_hits:>4} {all_years_hits/all_years_cnt*100:>7.1f}% {all_years_profit:>11,.0f} {all_roi:>9.1f}%")

conn.close()
