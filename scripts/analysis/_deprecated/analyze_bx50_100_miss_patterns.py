"""
B×50-100条件の不的中パターン分析

条件:
- 信頼度: B
- 1コース選手級別: A1またはB1（A2は含む）
- オッズ: 50-100倍（1-2-3のオッズで判定）
- 予測タイプ: before

パターンH（3点買い）:
- 1-2-3に200円
- 1-2-4に100円
- 1-2-5に100円
（計400円/レース）
"""

import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import DATABASE_PATH, VENUES


def analyze_bx50_100_miss_patterns():
    """B×50-100条件の不的中パターンを分析"""

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 6年間のデータ期間を確認
    cursor.execute("""
        SELECT MIN(race_date) as min_date, MAX(race_date) as max_date
        FROM races
    """)
    date_range = cursor.fetchone()
    print(f"データ期間: {date_range['min_date']} ~ {date_range['max_date']}")
    print()

    # B×50-100条件に該当するレースを抽出
    # beforeタイプの予測で、信頼度B、1コース選手がA1/B1（A2は除外）
    query = """
    WITH prediction_ranked AS (
        SELECT
            rp.race_id,
            rp.pit_number,
            rp.rank_prediction,
            rp.confidence,
            rp.racer_name,
            rp.racer_number
        FROM race_predictions rp
        WHERE rp.prediction_type = 'before'
    ),
    -- 予測1位の情報
    pred_1st AS (
        SELECT race_id, pit_number as pred_1st_pit, racer_name as pred_1st_name, confidence
        FROM prediction_ranked
        WHERE rank_prediction = 1
    ),
    -- 予測2位の情報
    pred_2nd AS (
        SELECT race_id, pit_number as pred_2nd_pit
        FROM prediction_ranked
        WHERE rank_prediction = 2
    ),
    -- 予測3位の情報
    pred_3rd AS (
        SELECT race_id, pit_number as pred_3rd_pit
        FROM prediction_ranked
        WHERE rank_prediction = 3
    ),
    -- 予測4位の情報
    pred_4th AS (
        SELECT race_id, pit_number as pred_4th_pit
        FROM prediction_ranked
        WHERE rank_prediction = 4
    ),
    -- 予測5位の情報
    pred_5th AS (
        SELECT race_id, pit_number as pred_5th_pit
        FROM prediction_ranked
        WHERE rank_prediction = 5
    ),
    -- 1コース選手の級別
    course1_rank AS (
        SELECT race_id, racer_rank
        FROM entries
        WHERE pit_number = 1
    ),
    -- 予測組み合わせを取得
    prediction_combos AS (
        SELECT
            p1.race_id,
            CAST(p1.pit_number AS TEXT) || '-' ||
            CAST(p2.pit_number AS TEXT) || '-' ||
            CAST(p3.pit_number AS TEXT) as pred_combo
        FROM race_predictions p1
        JOIN race_predictions p2 ON p1.race_id = p2.race_id
            AND p2.rank_prediction = 2 AND p2.prediction_type = 'before'
        JOIN race_predictions p3 ON p1.race_id = p3.race_id
            AND p3.rank_prediction = 3 AND p3.prediction_type = 'before'
        WHERE p1.rank_prediction = 1 AND p1.prediction_type = 'before'
    ),
    -- 予測組み合わせのオッズ
    odds_pred AS (
        SELECT pc.race_id, t.odds
        FROM prediction_combos pc
        JOIN trifecta_odds t ON pc.race_id = t.race_id AND t.combination = pc.pred_combo
    ),
    -- 実際の結果（1-3着）
    actual_results AS (
        SELECT
            race_id,
            MAX(CASE WHEN rank = '1' THEN pit_number END) as actual_1st,
            MAX(CASE WHEN rank = '2' THEN pit_number END) as actual_2nd,
            MAX(CASE WHEN rank = '3' THEN pit_number END) as actual_3rd
        FROM results
        WHERE is_invalid = 0 AND rank IN ('1', '2', '3')
        GROUP BY race_id
    ),
    -- 3連単払戻
    trifecta_payout AS (
        SELECT race_id, combination, amount
        FROM payouts
        WHERE bet_type = 'trifecta'
    )
    SELECT
        r.id as race_id,
        r.venue_code,
        r.race_date,
        r.race_number,
        p1.pred_1st_pit,
        p1.pred_1st_name,
        p1.confidence,
        p2.pred_2nd_pit,
        p3.pred_3rd_pit,
        p4.pred_4th_pit,
        p5.pred_5th_pit,
        c1.racer_rank as course1_rank,
        o.odds as odds_123,
        ar.actual_1st,
        ar.actual_2nd,
        ar.actual_3rd,
        tp.combination as winning_combination,
        tp.amount as payout_amount
    FROM races r
    INNER JOIN pred_1st p1 ON r.id = p1.race_id
    INNER JOIN pred_2nd p2 ON r.id = p2.race_id
    INNER JOIN pred_3rd p3 ON r.id = p3.race_id
    LEFT JOIN pred_4th p4 ON r.id = p4.race_id
    LEFT JOIN pred_5th p5 ON r.id = p5.race_id
    INNER JOIN course1_rank c1 ON r.id = c1.race_id
    INNER JOIN odds_pred o ON r.id = o.race_id
    LEFT JOIN actual_results ar ON r.id = ar.race_id
    LEFT JOIN trifecta_payout tp ON r.id = tp.race_id
    WHERE
        p1.confidence = 'B'
        AND c1.racer_rank IN ('A1', 'B1')  -- A2は除外
        AND o.odds >= 50 AND o.odds < 100
        AND ar.actual_1st IS NOT NULL  -- 結果が存在
    ORDER BY r.race_date, r.venue_code, r.race_number
    """

    cursor.execute(query)
    races = cursor.fetchall()

    print(f"=" * 80)
    print(f"B×50-100条件 不的中パターン分析")
    print(f"=" * 80)
    print(f"条件: 信頼度B, 1コース級別A1/B1, オッズ50-100倍, 予測タイプbefore")
    print(f"パターンH: 1-2-3に200円, 1-2-4に100円, 1-2-5に100円 (計400円/レース)")
    print(f"=" * 80)
    print()

    # 統計用変数
    total_races = len(races)
    hit_123 = 0  # 1-2-3的中
    hit_124 = 0  # 1-2-4的中
    hit_125 = 0  # 1-2-5的中
    total_hits = 0

    # 不的中パターン分析
    miss_1st = 0  # 1着外し
    miss_2nd = 0  # 2着外し（1着は的中）
    miss_3_4_5 = 0  # 3着外し（1-2着は的中したが3着候補が外れ）

    # 予測1位のコース別1着的中率
    pred1_course_stats = defaultdict(lambda: {'total': 0, 'hit': 0})

    # 会場別統計
    venue_stats = defaultdict(lambda: {'total': 0, 'hit': 0, 'payout': 0, 'bet': 0})

    # 年別統計
    year_stats = defaultdict(lambda: {'total': 0, 'hit': 0, 'payout': 0, 'bet': 0})

    # 級別統計
    rank_stats = defaultdict(lambda: {'total': 0, 'hit': 0, 'payout': 0, 'bet': 0})

    # 詳細な不的中パターン
    miss_patterns = defaultdict(int)

    total_bet = 0
    total_payout = 0

    for race in races:
        race_id = race['race_id']
        venue_code = race['venue_code']
        race_date = race['race_date']
        race_number = race['race_number']
        pred_1st = race['pred_1st_pit']
        pred_2nd = race['pred_2nd_pit']
        pred_3rd = race['pred_3rd_pit']
        pred_4th = race['pred_4th_pit']
        pred_5th = race['pred_5th_pit']
        course1_rank = race['course1_rank']
        actual_1st = race['actual_1st']
        actual_2nd = race['actual_2nd']
        actual_3rd = race['actual_3rd']
        payout_amount = race['payout_amount'] or 0

        year = race_date[:4]

        # 賭け金（400円/レース）
        bet_amount = 400
        total_bet += bet_amount

        # 的中判定（パターンH: 1-2-3, 1-2-4, 1-2-5）
        is_hit_123 = (pred_1st == actual_1st and pred_2nd == actual_2nd and pred_3rd == actual_3rd)
        is_hit_124 = (pred_1st == actual_1st and pred_2nd == actual_2nd and pred_4th == actual_3rd)
        is_hit_125 = (pred_1st == actual_1st and pred_2nd == actual_2nd and pred_5th == actual_3rd)

        is_hit = is_hit_123 or is_hit_124 or is_hit_125

        # 払戻計算
        payout = 0
        if is_hit_123:
            hit_123 += 1
            # 200円賭けなので払戻は payout_amount * 2
            payout = payout_amount * 2 // 100  # 100円単位なので2倍
        if is_hit_124 or is_hit_125:
            if is_hit_124:
                hit_124 += 1
            if is_hit_125:
                hit_125 += 1
            # 1-2-4または1-2-5の払戻を取得
            if is_hit_124:
                cursor.execute("""
                    SELECT amount FROM payouts
                    WHERE race_id = ? AND bet_type = 'trifecta'
                    AND combination = ?
                """, (race_id, f"{pred_1st}-{pred_2nd}-{pred_4th}"))
            else:
                cursor.execute("""
                    SELECT amount FROM payouts
                    WHERE race_id = ? AND bet_type = 'trifecta'
                    AND combination = ?
                """, (race_id, f"{pred_1st}-{pred_2nd}-{pred_5th}"))
            result = cursor.fetchone()
            if result:
                payout = result['amount']  # 100円単位

        total_payout += payout

        if is_hit:
            total_hits += 1

        # 予測1位のコース別統計
        pred1_course_stats[pred_1st]['total'] += 1
        if pred_1st == actual_1st:
            pred1_course_stats[pred_1st]['hit'] += 1

        # 会場別統計
        venue_stats[venue_code]['total'] += 1
        venue_stats[venue_code]['bet'] += bet_amount
        if is_hit:
            venue_stats[venue_code]['hit'] += 1
            venue_stats[venue_code]['payout'] += payout

        # 年別統計
        year_stats[year]['total'] += 1
        year_stats[year]['bet'] += bet_amount
        if is_hit:
            year_stats[year]['hit'] += 1
            year_stats[year]['payout'] += payout

        # 級別統計
        rank_stats[course1_rank]['total'] += 1
        rank_stats[course1_rank]['bet'] += bet_amount
        if is_hit:
            rank_stats[course1_rank]['hit'] += 1
            rank_stats[course1_rank]['payout'] += payout

        # 不的中パターン分析
        if not is_hit:
            # 1着が外れたか
            if pred_1st != actual_1st:
                miss_1st += 1
                miss_patterns[f"1着外し: 予測{pred_1st}コース → 実際{actual_1st}コース"] += 1
            # 1着は的中したが2着が外れた
            elif pred_2nd != actual_2nd:
                miss_2nd += 1
                miss_patterns[f"2着外し: 予測{pred_2nd}コース → 実際{actual_2nd}コース"] += 1
            # 1-2着は的中したが3着候補(3,4,5位)が外れた
            else:
                miss_3_4_5 += 1
                miss_patterns[f"3着外し: 予測3-5位({pred_3rd},{pred_4th},{pred_5th}) → 実際{actual_3rd}コース"] += 1

    # 結果出力
    print(f"【基本統計】")
    print(f"総レース数: {total_races}件")
    print(f"的中数: {total_hits}件")
    print(f"的中率: {total_hits/total_races*100:.2f}%")
    print(f"総賭け金: {total_bet:,}円")
    print(f"総払戻: {total_payout:,}円")
    print(f"収支: {total_payout - total_bet:+,}円")
    print(f"ROI: {total_payout/total_bet*100:.1f}%")
    print()

    print(f"【的中内訳】")
    print(f"1-2-3的中: {hit_123}件 ({hit_123/total_races*100:.2f}%)")
    print(f"1-2-4的中: {hit_124}件 ({hit_124/total_races*100:.2f}%)")
    print(f"1-2-5的中: {hit_125}件 ({hit_125/total_races*100:.2f}%)")
    print()

    miss_count = total_races - total_hits
    print(f"【不的中パターン内訳】")
    print(f"不的中総数: {miss_count}件 ({miss_count/total_races*100:.2f}%)")
    print(f"")
    print(f"1. 1着外し（予測1位が1着にならなかった）: {miss_1st}件 ({miss_1st/miss_count*100:.1f}%)")
    print(f"2. 2着外し（1着は的中、2着が外れた）: {miss_2nd}件 ({miss_2nd/miss_count*100:.1f}%)")
    print(f"3. 3着外し（1-2着的中、3-5位候補が3着に来なかった）: {miss_3_4_5}件 ({miss_3_4_5/miss_count*100:.1f}%)")
    print()

    print(f"【予測1位のコース別1着的中率】")
    print(f"{'コース':^6} | {'レース数':^8} | {'1着的中':^8} | {'的中率':^8}")
    print(f"{'-'*6} | {'-'*8} | {'-'*8} | {'-'*8}")
    for course in sorted(pred1_course_stats.keys()):
        stats = pred1_course_stats[course]
        rate = stats['hit'] / stats['total'] * 100 if stats['total'] > 0 else 0
        print(f"{course:^6} | {stats['total']:^8} | {stats['hit']:^8} | {rate:^7.1f}%")
    print()

    print(f"【年別統計】")
    print(f"{'年':^6} | {'レース数':^8} | {'的中':^6} | {'的中率':^8} | {'収支':^12} | {'ROI':^8}")
    print(f"{'-'*6} | {'-'*8} | {'-'*6} | {'-'*8} | {'-'*12} | {'-'*8}")
    for year in sorted(year_stats.keys()):
        stats = year_stats[year]
        rate = stats['hit'] / stats['total'] * 100 if stats['total'] > 0 else 0
        profit = stats['payout'] - stats['bet']
        roi = stats['payout'] / stats['bet'] * 100 if stats['bet'] > 0 else 0
        print(f"{year:^6} | {stats['total']:^8} | {stats['hit']:^6} | {rate:^7.1f}% | {profit:^+11,}円 | {roi:^7.1f}%")
    print()

    print(f"【1コース級別統計】")
    print(f"{'級別':^6} | {'レース数':^8} | {'的中':^6} | {'的中率':^8} | {'収支':^12} | {'ROI':^8}")
    print(f"{'-'*6} | {'-'*8} | {'-'*6} | {'-'*8} | {'-'*12} | {'-'*8}")
    for rank in sorted(rank_stats.keys()):
        stats = rank_stats[rank]
        rate = stats['hit'] / stats['total'] * 100 if stats['total'] > 0 else 0
        profit = stats['payout'] - stats['bet']
        roi = stats['payout'] / stats['bet'] * 100 if stats['bet'] > 0 else 0
        print(f"{rank:^6} | {stats['total']:^8} | {stats['hit']:^6} | {rate:^7.1f}% | {profit:^+11,}円 | {roi:^7.1f}%")
    print()

    # 会場名取得用
    venue_names = {v['code']: v['name'] for v in VENUES.values()}

    print(f"【会場別統計（ROI順）】")
    print(f"{'会場':^8} | {'レース数':^8} | {'的中':^6} | {'的中率':^8} | {'収支':^12} | {'ROI':^8}")
    print(f"{'-'*8} | {'-'*8} | {'-'*6} | {'-'*8} | {'-'*12} | {'-'*8}")

    # ROI順でソート
    sorted_venues = sorted(venue_stats.items(),
                          key=lambda x: x[1]['payout']/x[1]['bet'] if x[1]['bet'] > 0 else 0,
                          reverse=True)

    for venue_code, stats in sorted_venues:
        venue_name = venue_names.get(venue_code, venue_code)
        rate = stats['hit'] / stats['total'] * 100 if stats['total'] > 0 else 0
        profit = stats['payout'] - stats['bet']
        roi = stats['payout'] / stats['bet'] * 100 if stats['bet'] > 0 else 0
        print(f"{venue_name:^8} | {stats['total']:^8} | {stats['hit']:^6} | {rate:^7.1f}% | {profit:^+11,}円 | {roi:^7.1f}%")
    print()

    # 不的中パターン詳細
    print(f"【不的中パターン詳細（上位10件）】")
    sorted_patterns = sorted(miss_patterns.items(), key=lambda x: x[1], reverse=True)[:10]
    for pattern, count in sorted_patterns:
        print(f"  {pattern}: {count}件")
    print()

    # 追加分析: 1着外し時の実際の1着コース
    print(f"【1着外し時の詳細分析】")
    cursor.execute("""
    WITH prediction_ranked AS (
        SELECT
            rp.race_id,
            rp.pit_number,
            rp.rank_prediction,
            rp.confidence
        FROM race_predictions rp
        WHERE rp.prediction_type = 'before'
    ),
    pred_1st AS (
        SELECT race_id, pit_number as pred_1st_pit, confidence
        FROM prediction_ranked
        WHERE rank_prediction = 1
    ),
    course1_rank AS (
        SELECT race_id, racer_rank
        FROM entries
        WHERE pit_number = 1
    ),
    prediction_combos AS (
        SELECT
            p1.race_id,
            CAST(p1.pit_number AS TEXT) || '-' ||
            CAST(p2.pit_number AS TEXT) || '-' ||
            CAST(p3.pit_number AS TEXT) as pred_combo
        FROM race_predictions p1
        JOIN race_predictions p2 ON p1.race_id = p2.race_id
            AND p2.rank_prediction = 2 AND p2.prediction_type = 'before'
        JOIN race_predictions p3 ON p1.race_id = p3.race_id
            AND p3.rank_prediction = 3 AND p3.prediction_type = 'before'
        WHERE p1.rank_prediction = 1 AND p1.prediction_type = 'before'
    ),
    odds_pred AS (
        SELECT pc.race_id, t.odds
        FROM prediction_combos pc
        JOIN trifecta_odds t ON pc.race_id = t.race_id AND t.combination = pc.pred_combo
    ),
    actual_1st AS (
        SELECT race_id, pit_number as actual_1st
        FROM results
        WHERE is_invalid = 0 AND rank = '1'
    )
    SELECT
        p1.pred_1st_pit,
        a1.actual_1st,
        COUNT(*) as count
    FROM races r
    INNER JOIN pred_1st p1 ON r.id = p1.race_id
    INNER JOIN course1_rank c1 ON r.id = c1.race_id
    INNER JOIN odds_pred o ON r.id = o.race_id
    INNER JOIN actual_1st a1 ON r.id = a1.race_id
    WHERE
        p1.confidence = 'B'
        AND c1.racer_rank IN ('A1', 'B1')
        AND o.odds >= 50 AND o.odds < 100
        AND p1.pred_1st_pit != a1.actual_1st
    GROUP BY p1.pred_1st_pit, a1.actual_1st
    ORDER BY count DESC
    """)

    miss_1st_details = cursor.fetchall()
    print(f"予測1位コース → 実際1着コース (件数)")
    for row in miss_1st_details[:15]:
        print(f"  {row['pred_1st_pit']}コース予測 → {row['actual_1st']}コース1着: {row['count']}件")

    conn.close()


if __name__ == "__main__":
    analyze_bx50_100_miss_patterns()
