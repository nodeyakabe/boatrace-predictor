#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
オッズ10倍未満の詳細分析スクリプト

目的:
  - 信頼度A×オッズ10倍未満の詳細分析
  - 会場別・月別の傾向分析
  - 季節性の確認
  - 新規条件の発見
"""
import sqlite3
import sys
import io
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DATABASE_PATH = 'data/boatrace.db'

def main():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("="*80)
    print("オッズ10倍未満の詳細分析")
    print("="*80)
    print()
    print(f"分析開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # ============================================================
    # 分析1: 信頼度A×オッズ帯別の詳細ROI
    # ============================================================
    print("【分析1】信頼度A×オッズ帯別の詳細ROI")
    print("="*80)
    print()

    cursor.execute('''
        WITH predictions AS (
            SELECT
                rp1.race_id,
                rp1.confidence,
                CAST(rp1.pit_number AS TEXT) || '-' ||
                CAST(rp2.pit_number AS TEXT) || '-' ||
                CAST(rp3.pit_number AS TEXT) as pred_combo
            FROM race_predictions rp1
            LEFT JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
                AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            LEFT JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
                AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            WHERE rp1.prediction_type = 'before'
            AND rp1.rank_prediction = 1
            AND rp1.confidence = 'A'
        ),
        results_agg AS (
            SELECT
                race_id,
                CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
                CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
                CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
            FROM results
            WHERE rank IN ('1', '2', '3')
            GROUP BY race_id
        )
        SELECT
            CASE
                WHEN t.odds < 3 THEN '01: 1-3倍未満'
                WHEN t.odds < 5 THEN '02: 3-5倍'
                WHEN t.odds < 7 THEN '03: 5-7倍'
                WHEN t.odds < 10 THEN '04: 7-10倍'
                WHEN t.odds < 15 THEN '05: 10-15倍'
                WHEN t.odds < 20 THEN '06: 15-20倍'
                WHEN t.odds < 30 THEN '07: 20-30倍'
                WHEN t.odds < 50 THEN '08: 30-50倍'
                ELSE '09: 50倍以上'
            END as odds_band,
            COUNT(*) as races,
            SUM(CASE WHEN p.pred_combo = r.actual_combo THEN 1 ELSE 0 END) as hits,
            ROUND(100.0 * SUM(CASE WHEN p.pred_combo = r.actual_combo THEN 1 ELSE 0 END) / COUNT(*), 2) as hit_rate,
            SUM(400) as investment,
            SUM(CASE WHEN p.pred_combo = r.actual_combo THEN t.odds * 400 ELSE 0 END) as returns,
            ROUND(100.0 * SUM(CASE WHEN p.pred_combo = r.actual_combo THEN t.odds * 400 ELSE 0 END) / SUM(400), 2) as roi,
            SUM(CASE WHEN p.pred_combo = r.actual_combo THEN t.odds * 400 ELSE 0 END) - SUM(400) as profit,
            ROUND(AVG(t.odds), 2) as avg_odds,
            ROUND(AVG(CASE WHEN p.pred_combo = r.actual_combo THEN t.odds END), 2) as avg_hit_odds
        FROM predictions p
        JOIN trifecta_odds t ON p.race_id = t.race_id AND t.combination = p.pred_combo
        LEFT JOIN results_agg r ON p.race_id = r.race_id
        GROUP BY odds_band
        ORDER BY odds_band
    ''')

    print(f"{'オッズ帯':<18} {'レース':<8} {'的中':<8} {'的中率':<8} {'ROI':<10} {'収支':<15} {'平均オッズ':<10}")
    print("-"*80)

    total_races = 0
    total_hits = 0
    total_investment = 0
    total_returns = 0
    under_10_races = 0
    under_10_profit = 0

    for row in cursor.fetchall():
        odds_band, races, hits, hit_rate, investment, returns, roi, profit, avg_odds, avg_hit_odds = row
        print(f"{odds_band:<18} {races:>6,}件  {hits:>6,}件  {hit_rate:>5.1f}%  {roi:>7.1f}%  {profit:>+12,.0f}円  {avg_odds:>7.1f}倍")

        total_races += races
        total_hits += hits
        total_investment += investment
        total_returns += returns

        # オッズ10倍未満の集計
        if odds_band in ['01: 1-3倍未満', '02: 3-5倍', '03: 5-7倍', '04: 7-10倍']:
            under_10_races += races
            under_10_profit += profit

    print("-"*80)
    total_roi = 100.0 * total_returns / total_investment if total_investment > 0 else 0
    total_profit = total_returns - total_investment
    print(f"{'合計':<18} {total_races:>6,}件  {total_hits:>6,}件  {100.0*total_hits/total_races:>5.1f}%  {total_roi:>7.1f}%  {total_profit:>+12,.0f}円")
    print()
    print(f"【オッズ10倍未満の合計】")
    print(f"  レース数: {under_10_races:,}件（全体の{100.0*under_10_races/total_races:.1f}%）")
    print(f"  収支: {under_10_profit:+,.0f}円")
    print()

    # ============================================================
    # 分析2: 信頼度A×オッズ10倍未満×会場別分析
    # ============================================================
    print("【分析2】信頼度A×オッズ10倍未満×会場別分析")
    print("="*80)
    print()

    VENUE_NAMES = {
        1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川', 6: '浜名湖',
        7: '蒲郡', 8: '常滑', 9: '津', 10: '三国', 11: 'びわこ', 12: '住之江',
        13: '尼崎', 14: '鳴門', 15: '丸亀', 16: '児島', 17: '宮島', 18: '徳山',
        19: '下関', 20: '若松', 21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村'
    }

    cursor.execute('''
        WITH predictions AS (
            SELECT
                rp1.race_id,
                rp1.confidence,
                CAST(rp1.pit_number AS TEXT) || '-' ||
                CAST(rp2.pit_number AS TEXT) || '-' ||
                CAST(rp3.pit_number AS TEXT) as pred_combo
            FROM race_predictions rp1
            LEFT JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
                AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            LEFT JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
                AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            WHERE rp1.prediction_type = 'before'
            AND rp1.rank_prediction = 1
            AND rp1.confidence = 'A'
        ),
        results_agg AS (
            SELECT
                race_id,
                CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
                CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
                CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
            FROM results
            WHERE rank IN ('1', '2', '3')
            GROUP BY race_id
        )
        SELECT
            r.venue_code,
            COUNT(*) as races,
            SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN 1 ELSE 0 END) as hits,
            ROUND(100.0 * SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN 1 ELSE 0 END) / COUNT(*), 2) as hit_rate,
            SUM(400) as investment,
            SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN t.odds * 400 ELSE 0 END) as returns,
            ROUND(100.0 * SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN t.odds * 400 ELSE 0 END) / SUM(400), 2) as roi,
            SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN t.odds * 400 ELSE 0 END) - SUM(400) as profit,
            ROUND(AVG(t.odds), 2) as avg_odds
        FROM predictions p
        JOIN races r ON p.race_id = r.id
        JOIN trifecta_odds t ON p.race_id = t.race_id AND t.combination = p.pred_combo
        LEFT JOIN results_agg ra ON p.race_id = ra.race_id
        WHERE t.odds < 10
        GROUP BY r.venue_code
        HAVING races >= 50
        ORDER BY roi DESC
    ''')

    print(f"{'会場':<10} {'レース':<8} {'的中':<8} {'的中率':<8} {'ROI':<10} {'収支':<15} {'平均オッズ':<10}")
    print("-"*80)

    venue_data = []
    for row in cursor.fetchall():
        venue_code, races, hits, hit_rate, investment, returns, roi, profit, avg_odds = row
        venue_name = VENUE_NAMES.get(venue_code, f'会場{venue_code}')
        venue_data.append({
            'venue_code': venue_code,
            'venue_name': venue_name,
            'races': races,
            'roi': roi,
            'profit': profit
        })
        print(f"{venue_name:<10} {races:>6,}件  {hits:>6,}件  {hit_rate:>5.1f}%  {roi:>7.1f}%  {profit:>+12,.0f}円  {avg_odds:>7.1f}倍")

    print()
    print(f"【高ROI会場（ROI 150%以上）】")
    high_roi_venues = [v for v in venue_data if v['roi'] >= 150]
    if high_roi_venues:
        for v in high_roi_venues:
            print(f"  - {v['venue_name']}: ROI {v['roi']:.1f}%, 収支 {v['profit']:+,.0f}円 ({v['races']:,}件)")
    else:
        print("  なし")
    print()

    # ============================================================
    # 分析3: 信頼度A×オッズ10倍未満×月別分析（季節性）
    # ============================================================
    print("【分析3】信頼度A×オッズ10倍未満×月別分析（季節性）")
    print("="*80)
    print()

    cursor.execute('''
        WITH predictions AS (
            SELECT
                rp1.race_id,
                rp1.confidence,
                CAST(rp1.pit_number AS TEXT) || '-' ||
                CAST(rp2.pit_number AS TEXT) || '-' ||
                CAST(rp3.pit_number AS TEXT) as pred_combo
            FROM race_predictions rp1
            LEFT JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
                AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            LEFT JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
                AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            WHERE rp1.prediction_type = 'before'
            AND rp1.rank_prediction = 1
            AND rp1.confidence = 'A'
        ),
        results_agg AS (
            SELECT
                race_id,
                CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
                CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
                CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
            FROM results
            WHERE rank IN ('1', '2', '3')
            GROUP BY race_id
        )
        SELECT
            CAST(substr(r.race_date, 6, 2) AS INTEGER) as month,
            COUNT(*) as races,
            SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN 1 ELSE 0 END) as hits,
            ROUND(100.0 * SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN 1 ELSE 0 END) / COUNT(*), 2) as hit_rate,
            SUM(400) as investment,
            SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN t.odds * 400 ELSE 0 END) as returns,
            ROUND(100.0 * SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN t.odds * 400 ELSE 0 END) / SUM(400), 2) as roi,
            SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN t.odds * 400 ELSE 0 END) - SUM(400) as profit
        FROM predictions p
        JOIN races r ON p.race_id = r.id
        JOIN trifecta_odds t ON p.race_id = t.race_id AND t.combination = p.pred_combo
        LEFT JOIN results_agg ra ON p.race_id = ra.race_id
        WHERE t.odds < 10
        GROUP BY month
        ORDER BY month
    ''')

    print(f"{'月':<6} {'レース':<8} {'的中':<8} {'的中率':<8} {'ROI':<10} {'収支':<15}")
    print("-"*70)

    month_data = []
    for row in cursor.fetchall():
        month, races, hits, hit_rate, investment, returns, roi, profit = row
        month_data.append({
            'month': month,
            'races': races,
            'roi': roi,
            'profit': profit
        })
        season = ''
        if month in [12, 1, 2]:
            season = '(冬)'
        elif month in [3, 4, 5]:
            season = '(春)'
        elif month in [6, 7, 8]:
            season = '(夏)'
        elif month in [9, 10, 11]:
            season = '(秋)'

        print(f"{month:>2}月{season:<4} {races:>6,}件  {hits:>6,}件  {hit_rate:>5.1f}%  {roi:>7.1f}%  {profit:>+12,.0f}円")

    print()
    print(f"【季節別サマリー】")

    seasons = {
        '冬(12-2月)': [12, 1, 2],
        '春(3-5月)': [3, 4, 5],
        '夏(6-8月)': [6, 7, 8],
        '秋(9-11月)': [9, 10, 11]
    }

    for season_name, months in seasons.items():
        season_data = [m for m in month_data if m['month'] in months]
        if season_data:
            total_races = sum(m['races'] for m in season_data)
            total_profit = sum(m['profit'] for m in season_data)
            avg_roi = sum(m['roi'] * m['races'] for m in season_data) / total_races if total_races > 0 else 0
            print(f"  {season_name}: ROI {avg_roi:.1f}%, 収支 {total_profit:+,.0f}円 ({total_races:,}件)")

    print()

    # ============================================================
    # 分析4: 信頼度A×オッズ10倍未満×級別分析
    # ============================================================
    print("【分析4】信頼度A×オッズ10倍未満×級別分析")
    print("="*80)
    print()

    cursor.execute('''
        WITH predictions AS (
            SELECT
                rp1.race_id,
                rp1.pit_number as p1,
                rp1.confidence,
                CAST(rp1.pit_number AS TEXT) || '-' ||
                CAST(rp2.pit_number AS TEXT) || '-' ||
                CAST(rp3.pit_number AS TEXT) as pred_combo
            FROM race_predictions rp1
            LEFT JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
                AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            LEFT JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
                AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            WHERE rp1.prediction_type = 'before'
            AND rp1.rank_prediction = 1
            AND rp1.confidence = 'A'
        ),
        results_agg AS (
            SELECT
                race_id,
                CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
                CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
                CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
            FROM results
            WHERE rank IN ('1', '2', '3')
            GROUP BY race_id
        )
        SELECT
            e.racer_rank,
            COUNT(*) as races,
            SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN 1 ELSE 0 END) as hits,
            ROUND(100.0 * SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN 1 ELSE 0 END) / COUNT(*), 2) as hit_rate,
            SUM(400) as investment,
            SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN t.odds * 400 ELSE 0 END) as returns,
            ROUND(100.0 * SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN t.odds * 400 ELSE 0 END) / SUM(400), 2) as roi,
            SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN t.odds * 400 ELSE 0 END) - SUM(400) as profit,
            ROUND(AVG(t.odds), 2) as avg_odds
        FROM predictions p
        JOIN entries e ON p.race_id = e.race_id AND p.p1 = e.pit_number
        JOIN trifecta_odds t ON p.race_id = t.race_id AND t.combination = p.pred_combo
        LEFT JOIN results_agg ra ON p.race_id = ra.race_id
        WHERE t.odds < 10
        GROUP BY e.racer_rank
        ORDER BY roi DESC
    ''')

    print(f"{'級別':<8} {'レース':<8} {'的中':<8} {'的中率':<8} {'ROI':<10} {'収支':<15} {'平均オッズ':<10}")
    print("-"*80)

    for row in cursor.fetchall():
        rank, races, hits, hit_rate, investment, returns, roi, profit, avg_odds = row
        rank_name = rank if rank else '不明'
        print(f"{rank_name:<8} {races:>6,}件  {hits:>6,}件  {hit_rate:>5.1f}%  {roi:>7.1f}%  {profit:>+12,.0f}円  {avg_odds:>7.1f}倍")

    print()

    # ============================================================
    # 分析5: 新規条件候補の提案
    # ============================================================
    print("【分析5】新規条件候補の提案")
    print("="*80)
    print()

    print("オッズ10倍未満の分析結果から、以下の新規条件を提案:")
    print()

    # 提案1: 信頼度A×オッズ1-5倍
    cursor.execute('''
        WITH predictions AS (
            SELECT
                rp1.race_id,
                CAST(rp1.pit_number AS TEXT) || '-' ||
                CAST(rp2.pit_number AS TEXT) || '-' ||
                CAST(rp3.pit_number AS TEXT) as pred_combo
            FROM race_predictions rp1
            LEFT JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
                AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            LEFT JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
                AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            WHERE rp1.prediction_type = 'before'
            AND rp1.rank_prediction = 1
            AND rp1.confidence = 'A'
        ),
        results_agg AS (
            SELECT
                race_id,
                CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
                CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
                CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
            FROM results
            WHERE rank IN ('1', '2', '3')
            GROUP BY race_id
        )
        SELECT
            COUNT(*) as races,
            SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN 1 ELSE 0 END) as hits,
            ROUND(100.0 * SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN 1 ELSE 0 END) / COUNT(*), 2) as hit_rate,
            ROUND(100.0 * SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN t.odds * 400 ELSE 0 END) / SUM(400), 2) as roi,
            SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN t.odds * 400 ELSE 0 END) - SUM(400) as profit
        FROM predictions p
        JOIN trifecta_odds t ON p.race_id = t.race_id AND t.combination = p.pred_combo
        LEFT JOIN results_agg ra ON p.race_id = ra.race_id
        WHERE t.odds >= 1 AND t.odds < 5
    ''')

    row = cursor.fetchone()
    if row and row[0] > 0:
        races, hits, hit_rate, roi, profit = row
        print(f"【提案1】信頼度A×オッズ1-5倍（1点買い）")
        print(f"  レース数: {races:,}件")
        print(f"  的中率: {hit_rate:.2f}%")
        print(f"  ROI: {roi:.2f}%")
        print(f"  期待収支: {profit:+,.0f}円/年")
        print(f"  評価: {'✅ 推奨' if roi > 150 else '△ 要検討' if roi > 100 else '❌ 不採用'}")
        print()

    # 提案2: 信頼度A×オッズ5-10倍
    cursor.execute('''
        WITH predictions AS (
            SELECT
                rp1.race_id,
                CAST(rp1.pit_number AS TEXT) || '-' ||
                CAST(rp2.pit_number AS TEXT) || '-' ||
                CAST(rp3.pit_number AS TEXT) as pred_combo
            FROM race_predictions rp1
            LEFT JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
                AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            LEFT JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
                AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            WHERE rp1.prediction_type = 'before'
            AND rp1.rank_prediction = 1
            AND rp1.confidence = 'A'
        ),
        results_agg AS (
            SELECT
                race_id,
                CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
                CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
                CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
            FROM results
            WHERE rank IN ('1', '2', '3')
            GROUP BY race_id
        )
        SELECT
            COUNT(*) as races,
            SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN 1 ELSE 0 END) as hits,
            ROUND(100.0 * SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN 1 ELSE 0 END) / COUNT(*), 2) as hit_rate,
            ROUND(100.0 * SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN t.odds * 400 ELSE 0 END) / SUM(400), 2) as roi,
            SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN t.odds * 400 ELSE 0 END) - SUM(400) as profit
        FROM predictions p
        JOIN trifecta_odds t ON p.race_id = t.race_id AND t.combination = p.pred_combo
        LEFT JOIN results_agg ra ON p.race_id = ra.race_id
        WHERE t.odds >= 5 AND t.odds < 10
    ''')

    row = cursor.fetchone()
    if row and row[0] > 0:
        races, hits, hit_rate, roi, profit = row
        print(f"【提案2】信頼度A×オッズ5-10倍（1点買い）")
        print(f"  レース数: {races:,}件")
        print(f"  的中率: {hit_rate:.2f}%")
        print(f"  ROI: {roi:.2f}%")
        print(f"  期待収支: {profit:+,.0f}円/年")
        print(f"  評価: {'✅ 推奨' if roi > 150 else '△ 要検討' if roi > 100 else '❌ 不採用'}")
        print()

    conn.close()

    print("="*80)
    print("分析完了")
    print("="*80)
    print()
    print(f"分析終了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("【次のステップ】")
    print("1. 高ROI会場でさらに詳細な条件探索")
    print("2. 季節性を考慮した条件設定")
    print("3. リアルタイムオッズ取得システムの設計")
    print("4. 新規条件のバックテストでの検証")

if __name__ == '__main__':
    main()
