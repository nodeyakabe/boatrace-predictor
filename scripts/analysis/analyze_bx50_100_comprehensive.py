"""
B×50-100条件の不的中パターン総合分析

条件:
- 信頼度: B
- 1コース選手級別: A1またはB1（A2は除外）
- オッズ: 50-100倍（1-2-3のオッズで判定）
- 予測タイプ: advance と before の両方

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


def analyze_bx50_100_comprehensive():
    """B×50-100条件の不的中パターンを総合分析"""

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # データ期間を確認
    cursor.execute("""
        SELECT MIN(race_date) as min_date, MAX(race_date) as max_date
        FROM races
    """)
    date_range = cursor.fetchone()
    print(f"Data period: {date_range['min_date']} to {date_range['max_date']}")
    print()

    # 両方の予測タイプで分析
    for pred_type in ['advance', 'before', 'both']:
        print("=" * 80)
        print(f"B x 50-100 Analysis - Prediction Type: {pred_type.upper()}")
        print("=" * 80)
        print("Conditions: Confidence B, Course1 rank A1/B1, Odds 50-100x")
        print("Pattern H: 1-2-3 (200 yen), 1-2-4 (100 yen), 1-2-5 (100 yen) = 400 yen/race")
        print("=" * 80)
        print()

        # 予測タイプ条件
        if pred_type == 'both':
            type_condition = "rp.prediction_type IN ('advance', 'before')"
        else:
            type_condition = f"rp.prediction_type = '{pred_type}'"

        # B×50-100条件のクエリ
        query = f"""
        WITH prediction_ranked AS (
            SELECT
                rp.race_id,
                rp.pit_number,
                rp.rank_prediction,
                rp.confidence,
                rp.racer_name,
                rp.racer_number,
                rp.prediction_type
            FROM race_predictions rp
            WHERE {type_condition}
        ),
        pred_1st AS (
            SELECT race_id, pit_number as pred_1st_pit, confidence, prediction_type
            FROM prediction_ranked
            WHERE rank_prediction = 1
        ),
        pred_2nd AS (
            SELECT race_id, pit_number as pred_2nd_pit, prediction_type
            FROM prediction_ranked
            WHERE rank_prediction = 2
        ),
        pred_3rd AS (
            SELECT race_id, pit_number as pred_3rd_pit, prediction_type
            FROM prediction_ranked
            WHERE rank_prediction = 3
        ),
        pred_4th AS (
            SELECT race_id, pit_number as pred_4th_pit, prediction_type
            FROM prediction_ranked
            WHERE rank_prediction = 4
        ),
        pred_5th AS (
            SELECT race_id, pit_number as pred_5th_pit, prediction_type
            FROM prediction_ranked
            WHERE rank_prediction = 5
        ),
        course1_info AS (
            SELECT race_id, racer_rank, second_rate
            FROM entries
            WHERE pit_number = 1
        ),
        odds_123 AS (
            SELECT race_id, odds
            FROM trifecta_odds
            WHERE combination = '1-2-3'
        ),
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
        trifecta_payout AS (
            SELECT race_id, combination, amount
            FROM payouts
            WHERE bet_type = 'trifecta'
        )
        SELECT DISTINCT
            r.id as race_id,
            r.venue_code,
            r.race_date,
            r.race_number,
            p1.pred_1st_pit,
            p1.confidence,
            p1.prediction_type,
            p2.pred_2nd_pit,
            p3.pred_3rd_pit,
            p4.pred_4th_pit,
            p5.pred_5th_pit,
            c1.racer_rank as course1_rank,
            c1.second_rate as course1_second_rate,
            o.odds as odds_123,
            ar.actual_1st,
            ar.actual_2nd,
            ar.actual_3rd,
            tp.combination as winning_combination,
            tp.amount as payout_amount
        FROM races r
        INNER JOIN pred_1st p1 ON r.id = p1.race_id
        INNER JOIN pred_2nd p2 ON r.id = p2.race_id AND p2.prediction_type = p1.prediction_type
        INNER JOIN pred_3rd p3 ON r.id = p3.race_id AND p3.prediction_type = p1.prediction_type
        LEFT JOIN pred_4th p4 ON r.id = p4.race_id AND p4.prediction_type = p1.prediction_type
        LEFT JOIN pred_5th p5 ON r.id = p5.race_id AND p5.prediction_type = p1.prediction_type
        INNER JOIN course1_info c1 ON r.id = c1.race_id
        INNER JOIN odds_123 o ON r.id = o.race_id
        LEFT JOIN actual_results ar ON r.id = ar.race_id
        LEFT JOIN trifecta_payout tp ON r.id = tp.race_id
        WHERE
            p1.confidence = 'B'
            AND c1.racer_rank IN ('A1', 'B1')
            AND o.odds >= 50 AND o.odds < 100
            AND ar.actual_1st IS NOT NULL
        ORDER BY r.race_date, r.venue_code, r.race_number
        """

        cursor.execute(query)
        races = cursor.fetchall()

        # 統計用変数
        total_races = len(races)
        if total_races == 0:
            print(f"No races found for {pred_type}")
            print()
            continue

        hit_123 = 0
        hit_124 = 0
        hit_125 = 0
        total_hits = 0
        miss_1st = 0
        miss_2nd = 0
        miss_3_4_5 = 0

        pred1_course_stats = defaultdict(lambda: {'total': 0, 'hit': 0})
        venue_stats = defaultdict(lambda: {'total': 0, 'hit': 0, 'payout': 0, 'bet': 0})
        year_stats = defaultdict(lambda: {'total': 0, 'hit': 0, 'payout': 0, 'bet': 0})
        rank_stats = defaultdict(lambda: {'total': 0, 'hit': 0, 'payout': 0, 'bet': 0})
        miss_patterns_1st = defaultdict(int)
        miss_patterns_2nd = defaultdict(int)

        total_bet = 0
        total_payout = 0

        for race in races:
            race_id = race['race_id']
            venue_code = race['venue_code']
            race_date = race['race_date']
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
            bet_amount = 400
            total_bet += bet_amount

            is_hit_123 = (pred_1st == actual_1st and pred_2nd == actual_2nd and pred_3rd == actual_3rd)
            is_hit_124 = (pred_1st == actual_1st and pred_2nd == actual_2nd and pred_4th == actual_3rd)
            is_hit_125 = (pred_1st == actual_1st and pred_2nd == actual_2nd and pred_5th == actual_3rd)

            is_hit = is_hit_123 or is_hit_124 or is_hit_125

            payout = 0
            if is_hit_123:
                hit_123 += 1
                payout = payout_amount * 2 // 100
            if is_hit_124:
                hit_124 += 1
                cursor.execute("""
                    SELECT amount FROM payouts
                    WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                """, (race_id, f"{pred_1st}-{pred_2nd}-{pred_4th}"))
                result = cursor.fetchone()
                if result:
                    payout += result['amount']
            if is_hit_125:
                hit_125 += 1
                cursor.execute("""
                    SELECT amount FROM payouts
                    WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                """, (race_id, f"{pred_1st}-{pred_2nd}-{pred_5th}"))
                result = cursor.fetchone()
                if result:
                    payout += result['amount']

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
                if pred_1st != actual_1st:
                    miss_1st += 1
                    miss_patterns_1st[(pred_1st, actual_1st)] += 1
                elif pred_2nd != actual_2nd:
                    miss_2nd += 1
                    miss_patterns_2nd[(pred_2nd, actual_2nd)] += 1
                else:
                    miss_3_4_5 += 1

        # 結果出力
        print("[Basic Stats]")
        print(f"Total races: {total_races}")
        print(f"Hits: {total_hits}")
        print(f"Hit rate: {total_hits/total_races*100:.2f}%")
        print(f"Total bet: {total_bet:,} yen")
        print(f"Total payout: {total_payout:,} yen")
        print(f"Profit: {total_payout - total_bet:+,} yen")
        print(f"ROI: {total_payout/total_bet*100:.1f}%")
        print()

        print("[Hit Breakdown]")
        print(f"1-2-3 hits: {hit_123} ({hit_123/total_races*100:.2f}%)")
        print(f"1-2-4 hits: {hit_124} ({hit_124/total_races*100:.2f}%)")
        print(f"1-2-5 hits: {hit_125} ({hit_125/total_races*100:.2f}%)")
        print()

        miss_count = total_races - total_hits
        print("[Miss Pattern Breakdown]")
        print(f"Total misses: {miss_count} ({miss_count/total_races*100:.2f}%)")
        if miss_count > 0:
            print()
            print(f"1. 1st place miss (Pred 1st not 1st): {miss_1st} ({miss_1st/miss_count*100:.1f}% of misses)")
            print(f"2. 2nd place miss (1st hit, 2nd miss): {miss_2nd} ({miss_2nd/miss_count*100:.1f}% of misses)")
            print(f"3. 3rd place miss (1-2 hit, 3-5 pred not 3rd): {miss_3_4_5} ({miss_3_4_5/miss_count*100:.1f}% of misses)")
        print()

        print("[Pred 1st Course - Actual 1st Hit Rate]")
        print(f"{'Course':^8} | {'Races':^8} | {'1st Hit':^8} | {'Rate':^8}")
        print(f"{'-'*8} | {'-'*8} | {'-'*8} | {'-'*8}")
        for course in sorted(pred1_course_stats.keys()):
            stats = pred1_course_stats[course]
            rate = stats['hit'] / stats['total'] * 100 if stats['total'] > 0 else 0
            print(f"{course:^8} | {stats['total']:^8} | {stats['hit']:^8} | {rate:^7.1f}%")
        print()

        print("[Yearly Stats]")
        print(f"{'Year':^6} | {'Races':^6} | {'Hits':^5} | {'Rate':^7} | {'Profit':^12} | {'ROI':^8}")
        print(f"{'-'*6} | {'-'*6} | {'-'*5} | {'-'*7} | {'-'*12} | {'-'*8}")
        for year in sorted(year_stats.keys()):
            stats = year_stats[year]
            rate = stats['hit'] / stats['total'] * 100 if stats['total'] > 0 else 0
            profit = stats['payout'] - stats['bet']
            roi = stats['payout'] / stats['bet'] * 100 if stats['bet'] > 0 else 0
            print(f"{year:^6} | {stats['total']:^6} | {stats['hit']:^5} | {rate:^6.1f}% | {profit:^+11,} | {roi:^7.1f}%")
        print()

        print("[Course 1 Rank Stats]")
        print(f"{'Rank':^6} | {'Races':^6} | {'Hits':^5} | {'Rate':^7} | {'Profit':^12} | {'ROI':^8}")
        print(f"{'-'*6} | {'-'*6} | {'-'*5} | {'-'*7} | {'-'*12} | {'-'*8}")
        for rank in sorted(rank_stats.keys()):
            stats = rank_stats[rank]
            rate = stats['hit'] / stats['total'] * 100 if stats['total'] > 0 else 0
            profit = stats['payout'] - stats['bet']
            roi = stats['payout'] / stats['bet'] * 100 if stats['bet'] > 0 else 0
            print(f"{rank:^6} | {stats['total']:^6} | {stats['hit']:^5} | {rate:^6.1f}% | {profit:^+11,} | {roi:^7.1f}%")
        print()

        # 会場名取得用
        venue_names = {v['code']: v['name'] for v in VENUES.values()}

        print("[Venue Stats (ROI order)]")
        print(f"{'Venue':^10} | {'Races':^6} | {'Hits':^5} | {'Rate':^7} | {'Profit':^12} | {'ROI':^8}")
        print(f"{'-'*10} | {'-'*6} | {'-'*5} | {'-'*7} | {'-'*12} | {'-'*8}")

        sorted_venues = sorted(venue_stats.items(),
                              key=lambda x: x[1]['payout']/x[1]['bet'] if x[1]['bet'] > 0 else 0,
                              reverse=True)

        for venue_code, stats in sorted_venues:
            venue_name = venue_names.get(venue_code, venue_code)
            rate = stats['hit'] / stats['total'] * 100 if stats['total'] > 0 else 0
            profit = stats['payout'] - stats['bet']
            roi = stats['payout'] / stats['bet'] * 100 if stats['bet'] > 0 else 0
            print(f"{venue_name:^10} | {stats['total']:^6} | {stats['hit']:^5} | {rate:^6.1f}% | {profit:^+11,} | {roi:^7.1f}%")
        print()

        # 不的中パターン詳細（1着外し）
        print("[1st Place Miss Details - Top 10]")
        sorted_miss_1st = sorted(miss_patterns_1st.items(), key=lambda x: x[1], reverse=True)[:10]
        for (pred, actual), count in sorted_miss_1st:
            print(f"  Pred {pred} -> Actual {actual}: {count} races")
        print()

        # 不的中パターン詳細（2着外し）
        print("[2nd Place Miss Details (1st hit) - Top 10]")
        sorted_miss_2nd = sorted(miss_patterns_2nd.items(), key=lambda x: x[1], reverse=True)[:10]
        for (pred, actual), count in sorted_miss_2nd:
            print(f"  Pred {pred} -> Actual {actual}: {count} races")
        print()
        print()

    conn.close()


if __name__ == "__main__":
    analyze_bx50_100_comprehensive()
