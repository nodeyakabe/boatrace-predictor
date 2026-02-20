#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
1-4月の的中・外れパターン分析（実運用重視版）

目的:
    信頼度別の大括りではなく、会場・級別・オッズ帯・コース等の
    具体的な特徴から1-4月の除外すべき条件と追加すべき条件を特定

使用方法:
    python scripts/analysis/jan_apr_hit_pattern_analysis.py

出力:
    1. 会場×月別パフォーマンス（強い会場・弱い会場）
    2. 除外候補（ROI<80%, 黒字年数≤1/6）
    3. 的中レースの成功パターン（会場×級別×オッズ×コース）
    4. 1-4月限定の高ROI条件（1-4月高ROI、5-12月低ROI）
    5. 実装可能な提案（コード例付き）
"""

import sqlite3
import sys
import io
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DATABASE_PATH = PROJECT_ROOT / 'data' / 'boatrace.db'

# 会場コード→名称マッピング
VENUE_NAMES = {
    '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島', '05': '多摩川',
    '06': '浜名湖', '07': '蒲郡', '08': '常滑', '09': '津', '10': '三国',
    '11': 'びわこ', '12': '住之江', '13': '尼崎', '14': '鳴門', '15': '丸亀',
    '16': '児島', '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
    '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村',
}

# ============================================================
# 1. 会場×月別パフォーマンス分析
# ============================================================

def analyze_venue_monthly_performance(cursor) -> Dict:
    """
    会場×月別の実測ROI算出（1-4月 vs 5-12月）

    標準バックテストと同じ購入条件を適用
    """

    query = """
    WITH prediction_base AS (
        -- 予測組み合わせの構築（1-2-3着）
        SELECT
            rp.race_id,
            rp.confidence,
            CAST(strftime('%m', r.race_date) AS INTEGER) as month,
            CAST(strftime('%Y', r.race_date) AS INTEGER) as year,
            r.venue_code,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3,
            CAST(rp1.pit_number AS TEXT) || '-' ||
            CAST(rp2.pit_number AS TEXT) || '-' ||
            CAST(rp3.pit_number AS TEXT) as pred_combo,
            e1.racer_rank as c1_rank
        FROM race_predictions rp
        JOIN race_predictions rp1 ON rp.race_id = rp1.race_id
            AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON rp.race_id = rp2.race_id
            AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON rp.race_id = rp3.race_id
            AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN races r ON rp.race_id = r.id
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.prediction_type = 'before'
          AND rp.rank_prediction = 1
          AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    ),
    actual_results AS (
        -- 実際の着順
        SELECT
            race_id,
            CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
        FROM results
        WHERE rank IN ('1', '2', '3')
        GROUP BY race_id
    ),
    bet_races AS (
        -- オッズ付きで結合
        SELECT
            pb.*,
            ar.actual_combo,
            t.odds,
            CASE WHEN pb.pred_combo = ar.actual_combo THEN 1 ELSE 0 END as is_hit
        FROM prediction_base pb
        JOIN actual_results ar ON pb.race_id = ar.race_id
        LEFT JOIN trifecta_odds t ON pb.race_id = t.race_id
            AND t.combination = pb.pred_combo
        WHERE t.odds IS NOT NULL
          AND t.odds >= 10
          AND t.odds < 200
    )
    SELECT
        venue_code,
        month,
        year,
        COUNT(*) as races,
        SUM(is_hit) as hits,
        ROUND(100.0 * SUM(is_hit) / COUNT(*), 2) as hit_rate,
        ROUND(AVG(odds), 1) as avg_odds,
        SUM(CASE WHEN is_hit = 1 THEN odds * 100 ELSE 0 END) as payout,
        COUNT(*) * 100 as investment,
        ROUND(100.0 * SUM(CASE WHEN is_hit = 1 THEN odds * 100 ELSE 0 END) / (COUNT(*) * 100), 1) as roi,
        SUM(CASE WHEN is_hit = 1 THEN odds * 100 ELSE 0 END) - (COUNT(*) * 100) as profit
    FROM bet_races
    GROUP BY venue_code, month, year
    ORDER BY venue_code, month, year
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    # 会場×月別に集計（6年間合算）
    venue_month_data = defaultdict(lambda: defaultdict(lambda: {
        'races': 0, 'hits': 0, 'payout': 0, 'investment': 0,
        'black_years': 0, 'total_years': 0
    }))

    # 年度別データも保持（黒字年数カウント用）
    venue_month_year_data = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))

    for row in rows:
        venue = row[0]
        month = row[1]
        year = row[2]
        races = row[3]
        hits = row[4]
        payout = row[7]
        investment = row[8]
        profit = row[10]

        venue_month_data[venue][month]['races'] += races
        venue_month_data[venue][month]['hits'] += hits
        venue_month_data[venue][month]['payout'] += payout
        venue_month_data[venue][month]['investment'] += investment

        # 年度別データ保存
        venue_month_year_data[venue][month][year] = {'profit': profit}

    # 黒字年数をカウント
    for venue in venue_month_year_data:
        for month in venue_month_year_data[venue]:
            years_data = venue_month_year_data[venue][month]
            black_years = sum(1 for y in years_data.values() if y['profit'] >= 0)
            total_years = len(years_data)
            venue_month_data[venue][month]['black_years'] = black_years
            venue_month_data[venue][month]['total_years'] = total_years

    # ROI計算
    for venue in venue_month_data:
        for month in venue_month_data[venue]:
            data = venue_month_data[venue][month]
            if data['investment'] > 0:
                data['roi'] = round(100.0 * data['payout'] / data['investment'], 1)
                data['profit'] = data['payout'] - data['investment']
                data['hit_rate'] = round(100.0 * data['hits'] / data['races'], 2)
            else:
                data['roi'] = 0
                data['profit'] = 0
                data['hit_rate'] = 0

    return venue_month_data


# ============================================================
# 2. 除外候補の特定
# ============================================================

def identify_venues_to_exclude(venue_month_data: Dict) -> List[Dict]:
    """
    除外候補を特定（ROI<80%, 黒字年数≤1/6）
    """

    exclusion_candidates = []

    for venue in venue_month_data:
        for month in [1, 2, 3, 4]:  # 1-4月のみ
            data = venue_month_data[venue].get(month)
            if not data or data['races'] < 10:  # サンプル数不足は除外
                continue

            # 除外基準: ROI<80% かつ 黒字年数≤1/6
            if data['roi'] < 80 and data['black_years'] <= 1:
                exclusion_candidates.append({
                    'venue': venue,
                    'venue_name': VENUE_NAMES.get(venue, venue),
                    'month': month,
                    'races': data['races'],
                    'roi': data['roi'],
                    'profit': data['profit'],
                    'black_years': data['black_years'],
                    'total_years': data['total_years'],
                })

    # ROIの低い順にソート
    exclusion_candidates.sort(key=lambda x: x['roi'])

    return exclusion_candidates


# ============================================================
# 3. 的中レースの成功パターン分析
# ============================================================

def analyze_hit_patterns(cursor) -> Dict:
    """
    1-4月の的中レースの共通パターンを抽出

    会場×級別×オッズ帯の組み合わせを分析
    """

    query = """
    WITH prediction_base AS (
        SELECT
            rp.race_id,
            rp.confidence,
            CAST(strftime('%m', r.race_date) AS INTEGER) as month,
            r.venue_code,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3,
            CAST(rp1.pit_number AS TEXT) || '-' ||
            CAST(rp2.pit_number AS TEXT) || '-' ||
            CAST(rp3.pit_number AS TEXT) as pred_combo,
            e1.racer_rank as c1_rank
        FROM race_predictions rp
        JOIN race_predictions rp1 ON rp.race_id = rp1.race_id
            AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON rp.race_id = rp2.race_id
            AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON rp.race_id = rp3.race_id
            AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN races r ON rp.race_id = r.id
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.prediction_type = 'before'
          AND rp.rank_prediction = 1
          AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
          AND CAST(strftime('%m', r.race_date) AS INTEGER) IN (1, 2, 3, 4)
    ),
    actual_results AS (
        SELECT
            race_id,
            CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
        FROM results
        WHERE rank IN ('1', '2', '3')
        GROUP BY race_id
    ),
    bet_races AS (
        SELECT
            pb.*,
            ar.actual_combo,
            t.odds,
            CASE WHEN pb.pred_combo = ar.actual_combo THEN 1 ELSE 0 END as is_hit,
            CASE
                WHEN t.odds < 20 THEN '10-20'
                WHEN t.odds < 30 THEN '20-30'
                WHEN t.odds < 50 THEN '30-50'
                WHEN t.odds < 100 THEN '50-100'
                ELSE '100-200'
            END as odds_range
        FROM prediction_base pb
        JOIN actual_results ar ON pb.race_id = ar.race_id
        LEFT JOIN trifecta_odds t ON pb.race_id = t.race_id
            AND t.combination = pb.pred_combo
        WHERE t.odds IS NOT NULL
          AND t.odds >= 10
          AND t.odds < 200
    )
    SELECT
        venue_code,
        c1_rank,
        odds_range,
        COUNT(*) as total_races,
        SUM(is_hit) as hits,
        ROUND(100.0 * SUM(is_hit) / COUNT(*), 2) as hit_rate,
        ROUND(AVG(odds), 1) as avg_odds,
        SUM(CASE WHEN is_hit = 1 THEN odds * 100 ELSE 0 END) as payout,
        COUNT(*) * 100 as investment,
        ROUND(100.0 * SUM(CASE WHEN is_hit = 1 THEN odds * 100 ELSE 0 END) / (COUNT(*) * 100), 1) as roi
    FROM bet_races
    WHERE is_hit = 1  -- 的中レースのみ
    GROUP BY venue_code, c1_rank, odds_range
    HAVING total_races >= 3  -- サンプル数3件以上
    ORDER BY hits DESC
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    patterns = []
    for row in rows:
        patterns.append({
            'venue': row[0],
            'venue_name': VENUE_NAMES.get(row[0], row[0]),
            'c1_rank': row[1],
            'odds_range': row[2],
            'total_races': row[3],
            'hits': row[4],
            'hit_rate': row[5],
            'avg_odds': row[6],
            'payout': row[7],
            'investment': row[8],
            'roi': row[9],
        })

    return patterns


# ============================================================
# 4. 1-4月限定の高ROI条件発見
# ============================================================

def find_jan_apr_only_conditions(cursor) -> List[Dict]:
    """
    1-4月は高ROI、5-12月は低ROIの条件を発見

    「1-4月限定で追加すべき条件」を特定
    """

    query = """
    WITH prediction_base AS (
        SELECT
            rp.race_id,
            rp.confidence,
            CASE
                WHEN CAST(strftime('%m', r.race_date) AS INTEGER) IN (1, 2, 3, 4) THEN 'jan_apr'
                ELSE 'may_dec'
            END as period,
            r.venue_code,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3,
            CAST(rp1.pit_number AS TEXT) || '-' ||
            CAST(rp2.pit_number AS TEXT) || '-' ||
            CAST(rp3.pit_number AS TEXT) as pred_combo,
            e1.racer_rank as c1_rank,
            CASE
                WHEN t.odds < 20 THEN '10-20'
                WHEN t.odds < 30 THEN '20-30'
                WHEN t.odds < 50 THEN '30-50'
                WHEN t.odds < 100 THEN '50-100'
                ELSE '100-200'
            END as odds_range
        FROM race_predictions rp
        JOIN race_predictions rp1 ON rp.race_id = rp1.race_id
            AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON rp.race_id = rp2.race_id
            AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON rp.race_id = rp3.race_id
            AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN races r ON rp.race_id = r.id
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        LEFT JOIN trifecta_odds t ON rp.race_id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' ||
                                CAST(rp2.pit_number AS TEXT) || '-' ||
                                CAST(rp3.pit_number AS TEXT)
        WHERE rp.prediction_type = 'before'
          AND rp.rank_prediction = 1
          AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
          AND t.odds IS NOT NULL
          AND t.odds >= 10
          AND t.odds < 200
    ),
    actual_results AS (
        SELECT
            race_id,
            CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
        FROM results
        WHERE rank IN ('1', '2', '3')
        GROUP BY race_id
    ),
    bet_races AS (
        SELECT
            pb.*,
            ar.actual_combo,
            CASE WHEN pb.pred_combo = ar.actual_combo THEN 1 ELSE 0 END as is_hit
        FROM prediction_base pb
        JOIN actual_results ar ON pb.race_id = ar.race_id
    )
    SELECT
        confidence,
        c1_rank,
        odds_range,
        venue_code,
        period,
        COUNT(*) as races,
        SUM(is_hit) as hits,
        ROUND(100.0 * SUM(is_hit) / COUNT(*), 2) as hit_rate
    FROM bet_races
    GROUP BY confidence, c1_rank, odds_range, venue_code, period
    HAVING races >= 10
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    # 条件別に1-4月と5-12月のデータを集約
    condition_data = defaultdict(lambda: {'jan_apr': None, 'may_dec': None})

    for row in rows:
        conf = row[0]
        rank = row[1]
        odds_range = row[2]
        venue = row[3]
        period = row[4]
        races = row[5]
        hits = row[6]
        hit_rate = row[7]

        # 条件キー
        key = (conf, rank, odds_range, venue)

        condition_data[key][period] = {
            'races': races,
            'hits': hits,
            'hit_rate': hit_rate,
        }

    # 1-4月高ROI、5-12月低ROIの条件を抽出
    jan_apr_only = []

    for key, data in condition_data.items():
        jan_apr = data['jan_apr']
        may_dec = data['may_dec']

        if jan_apr and may_dec:
            # 1-4月: 的中率7%以上、5-12月: 的中率4%以下
            if jan_apr['hit_rate'] >= 7.0 and may_dec['hit_rate'] <= 4.0:
                jan_apr_only.append({
                    'confidence': key[0],
                    'c1_rank': key[1],
                    'odds_range': key[2],
                    'venue': key[3],
                    'venue_name': VENUE_NAMES.get(key[3], key[3]),
                    'jan_apr_races': jan_apr['races'],
                    'jan_apr_hits': jan_apr['hits'],
                    'jan_apr_hit_rate': jan_apr['hit_rate'],
                    'may_dec_races': may_dec['races'],
                    'may_dec_hits': may_dec['hits'],
                    'may_dec_hit_rate': may_dec['hit_rate'],
                })

    # 1-4月の的中率が高い順にソート
    jan_apr_only.sort(key=lambda x: x['jan_apr_hit_rate'], reverse=True)

    return jan_apr_only


# ============================================================
# 結果表示
# ============================================================

def print_results(venue_month_data: Dict, exclusion_candidates: List[Dict],
                  hit_patterns: List[Dict], jan_apr_only: List[Dict]):
    """
    分析結果を表示
    """

    print("=" * 120)
    print("1-4月の的中・外れパターン分析（実運用重視版）")
    print("=" * 120)
    print()
    print("分析期間: 2020-2025年（6年間）")
    print("対象: 標準バックテストと同じ購入条件（11条件）")
    print()

    # ============================================================
    # 1. 会場×月別パフォーマンス（1-4月 vs 5-12月）
    # ============================================================
    print("[1. 会場×月別パフォーマンス（1-4月 vs 5-12月）]")
    print("-" * 120)
    print(f"{'会場':<10} {'1月ROI':>8} {'2月ROI':>8} {'3月ROI':>8} {'4月ROI':>8} | {'5-12月ROI':>10} {'判定':<10}")
    print("-" * 120)

    for venue in sorted(venue_month_data.keys()):
        venue_name = VENUE_NAMES.get(venue, venue)

        # 1-4月のROI
        jan_roi = venue_month_data[venue].get(1, {}).get('roi', 0)
        feb_roi = venue_month_data[venue].get(2, {}).get('roi', 0)
        mar_roi = venue_month_data[venue].get(3, {}).get('roi', 0)
        apr_roi = venue_month_data[venue].get(4, {}).get('roi', 0)

        # 5-12月の平均ROI
        may_dec_rois = []
        for m in range(5, 13):
            if m in venue_month_data[venue]:
                may_dec_rois.append(venue_month_data[venue][m]['roi'])

        may_dec_avg = sum(may_dec_rois) / len(may_dec_rois) if may_dec_rois else 0

        # 判定
        jan_apr_avg = (jan_roi + feb_roi + mar_roi + apr_roi) / 4 if any([jan_roi, feb_roi, mar_roi, apr_roi]) else 0

        if jan_apr_avg < 80:
            judge = '[要注意]'
        elif jan_apr_avg >= 150:
            judge = '[良好]'
        else:
            judge = '[普通]'

        # サンプル数がある場合のみ表示
        jan_races = venue_month_data[venue].get(1, {}).get('races', 0)
        feb_races = venue_month_data[venue].get(2, {}).get('races', 0)
        mar_races = venue_month_data[venue].get(3, {}).get('races', 0)
        apr_races = venue_month_data[venue].get(4, {}).get('races', 0)

        if jan_races + feb_races + mar_races + apr_races >= 10:
            print(f"{venue_name:<10} {jan_roi:>7.0f}% {feb_roi:>7.0f}% {mar_roi:>7.0f}% {apr_roi:>7.0f}% | {may_dec_avg:>9.0f}% {judge:<10}")

    print()

    # ============================================================
    # 2. 除外候補（ROI<80%, 黒字年数≤1/6）
    # ============================================================
    print("[2. 除外候補（ROI<80%, 黒字年数≤1/6）]")
    print("-" * 120)
    print(f"{'会場':<10} {'月':<4} {'件数':>6} {'ROI':>8} {'収支':>12} {'黒字年数':>10} {'評価':<10}")
    print("-" * 120)

    if exclusion_candidates:
        for cand in exclusion_candidates[:20]:  # 上位20件
            print(f"{cand['venue_name']:<10} {cand['month']:>2}月 {cand['races']:>6}件 {cand['roi']:>7.0f}% {cand['profit']:>11,.0f}円 {cand['black_years']}/{cand['total_years']}年 [除外推奨]")
    else:
        print("除外候補なし（全会場・月が基準をクリア）")

    print()

    # ============================================================
    # 3. 的中レースの成功パターン（上位20件）
    # ============================================================
    print("[3. 的中レースの成功パターン（上位20件、的中数順）]")
    print("-" * 120)
    print(f"{'会場':<10} {'1号艇級':<8} {'オッズ帯':<10} {'的中数':>6} {'合計':>6} {'的中率':>8} {'平均オッズ':>10} {'評価':<10}")
    print("-" * 120)

    for pattern in hit_patterns[:20]:
        print(f"{pattern['venue_name']:<10} {pattern['c1_rank']:<8} {pattern['odds_range']:<10} {pattern['hits']:>6}件 {pattern['total_races']:>6}件 {pattern['hit_rate']:>7.1f}% {pattern['avg_odds']:>9.1f}倍 [成功パターン]")

    print()

    # ============================================================
    # 4. 1-4月限定の高ROI条件（1-4月高ROI、5-12月低ROI）
    # ============================================================
    print("[4. 1-4月限定の高ROI条件（1-4月高ROI、5-12月低ROI）]")
    print("-" * 120)
    print(f"{'信頼度':<6} {'1号艇級':<8} {'オッズ帯':<10} {'会場':<10} | {'1-4月的中率':>12} {'5-12月的中率':>12} {'評価':<10}")
    print("-" * 120)

    if jan_apr_only:
        for cond in jan_apr_only[:10]:  # 上位10件
            print(f"{cond['confidence']:<6} {cond['c1_rank']:<8} {cond['odds_range']:<10} {cond['venue_name']:<10} | {cond['jan_apr_hit_rate']:>11.1f}% {cond['may_dec_hit_rate']:>11.1f}% [1-4月限定]")
    else:
        print("該当条件なし")

    print()

    # ============================================================
    # 5. 実装可能な提案
    # ============================================================
    print("[5. 実装可能な提案]")
    print("=" * 120)
    print()

    print("【提案A: 除外候補の実装例】")
    print("-" * 120)
    if exclusion_candidates:
        # 会場×月の組み合わせを抽出（上位5件）
        top_exclusions = exclusion_candidates[:5]

        print("config/bet_conditions.py の該当条件に以下を追加:")
        print()
        for excl in top_exclusions:
            venue = excl['venue']
            month = excl['month']
            print(f"# 除外: {excl['venue_name']}×{month}月（ROI {excl['roi']:.0f}%, {excl['black_years']}/{excl['total_years']}年黒字）")
            print(f"'venue_month_exclude': [('{venue}', {month})],")
            print()

        print("※実装には venue_month_exclude パラメータの対応が必要")
    else:
        print("除外候補なし")

    print()
    print("【提案B: 1-4月限定条件の追加例】")
    print("-" * 120)
    if jan_apr_only:
        top_jan_apr = jan_apr_only[0]
        print("config/bet_conditions.py に新規条件として追加:")
        print()
        print("{")
        print(f"    'name': '{top_jan_apr['confidence']}×{top_jan_apr['c1_rank']}×{top_jan_apr['odds_range']}×{top_jan_apr['venue_name']}（1-4月限定）',")
        print(f"    'confidence': '{top_jan_apr['confidence']}',")
        print(f"    'c1_rank': ['{top_jan_apr['c1_rank']}'],")

        # オッズ帯をパース
        odds_parts = top_jan_apr['odds_range'].split('-')
        odds_min = int(odds_parts[0])
        odds_max = int(odds_parts[1])

        print(f"    'odds_min': {odds_min},")
        print(f"    'odds_max': {odds_max},")
        print(f"    'venue_filter': ['{top_jan_apr['venue']}'],")
        print(f"    'month_filter': [1, 2, 3, 4],  # 1-4月限定")
        print(f"    'use_pattern_h': True,")
        print(f"    'description': '1-4月限定条件（的中率{top_jan_apr['jan_apr_hit_rate']:.1f}% vs 5-12月{top_jan_apr['may_dec_hit_rate']:.1f}%）',")
        print("}")
        print()
        print("※実装には month_filter パラメータの対応が必要")
    else:
        print("該当条件なし")

    print()
    print("=" * 120)
    print("分析完了")
    print("=" * 120)


def main():
    """メイン処理"""

    conn = sqlite3.connect(str(DATABASE_PATH))
    cursor = conn.cursor()

    print("1-4月の的中・外れパターン分析を実行中...")
    print()

    # 分析実行
    print("ステップ1: 会場×月別パフォーマンス分析...")
    venue_month_data = analyze_venue_monthly_performance(cursor)

    print("ステップ2: 除外候補の特定...")
    exclusion_candidates = identify_venues_to_exclude(venue_month_data)

    print("ステップ3: 的中レースの成功パターン分析...")
    hit_patterns = analyze_hit_patterns(cursor)

    print("ステップ4: 1-4月限定の高ROI条件発見...")
    jan_apr_only = find_jan_apr_only_conditions(cursor)

    print()

    # 結果表示
    print_results(venue_month_data, exclusion_candidates, hit_patterns, jan_apr_only)

    conn.close()


if __name__ == '__main__':
    main()
