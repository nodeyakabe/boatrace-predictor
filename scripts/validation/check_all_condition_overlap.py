"""全条件の重複状況を調査

目的:
    全10条件（BET_CONDITIONS）の組み合わせで重複レースを調査し、
    どの条件ペアで重複が多いかを把握する。

出力:
    1. 全条件の対象レース数
    2. 条件ペアごとの重複レース数・重複率
    3. 重複率の高い組み合わせトップ10
    4. 全体の重複レース数と割合
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import sqlite3
from config.bet_conditions import STANDARD_BET_CONDITIONS

def get_race_ids_for_condition(cursor, cond, start_date='2020-01-01', end_date='2026-01-01'):
    """条件に該当するレースIDのセットを取得

    ※Tier 2のbuild_condition_query()と同じフィルターロジックを使用
    """
    c1_ranks_str = ','.join([f"'{r}'" for r in cond['c1_rank']])

    # 信頼度フィルター（Noneの場合は全信頼度対象）
    confidence_clause = ""
    if cond.get('confidence') is not None:
        confidence_clause = f"AND rp.confidence = '{cond['confidence']}'"

    # 会場フィルター
    venue_clause = ""
    if cond.get('venue_filter'):
        venue_codes = [f"'{v:02d}'" if isinstance(v, int) else f"'{v}'" for v in cond['venue_filter']]
        venue_clause = f"AND r.venue_code IN ({','.join(venue_codes)})"

    # モーター2連率フィルター
    motor_clause = ""
    if cond.get('motor_min'):
        motor_clause = f"AND e1.motor_second_rate >= {cond['motor_min']}"

    # レース番号除外
    race_exclude_clause = ""
    if cond.get('race_exclude'):
        race_exclude_clause = f"AND r.race_number NOT IN ({','.join(map(str, cond['race_exclude']))})"

    # 会場除外
    venue_exclude_clause = ""
    if cond.get('venue_exclude'):
        venue_codes = [f"'{v:02d}'" if isinstance(v, int) else f"'{v}'" for v in cond['venue_exclude']]
        venue_exclude_clause = f"AND r.venue_code NOT IN ({','.join(venue_codes)})"

    # 予測コース
    predicted_course_clause = ""
    if cond.get('predicted_course'):
        predicted_course_clause = f"AND rp1.pit_number = {cond['predicted_course']}"

    # 1コース選手の全国2連率
    c1_second_rate_clause = ""
    if cond.get('c1_second_rate_min') is not None:
        c1_second_rate_clause += f"AND e1.second_rate >= {cond['c1_second_rate_min']} "
    if cond.get('c1_second_rate_max') is not None:
        c1_second_rate_clause += f"AND e1.second_rate < {cond['c1_second_rate_max']} "

    # 月除外フィルター
    month_exclude_clause = ""
    if cond.get('month_exclude'):
        months = ','.join(map(str, cond['month_exclude']))
        month_exclude_clause = f"AND CAST(strftime('%m', r.race_date) AS INTEGER) NOT IN ({months})"

    # 逃げ率フィルター（Tier 2と同じ重複対策：最新レコードのみ）
    escape_rate_join = ""
    escape_rate_clause = ""
    if cond.get('escape_rate_min') is not None:
        escape_rate_join = """
        LEFT JOIN entries e_pred ON r.id = e_pred.race_id AND e_pred.pit_number = rp1.pit_number
        LEFT JOIN (
            SELECT player_id, escape_rate
            FROM player_escape_stats
            WHERE stadium_id IS NULL AND escape_rate IS NOT NULL
            AND id IN (
                SELECT MAX(id)
                FROM player_escape_stats
                WHERE stadium_id IS NULL AND escape_rate IS NOT NULL
                GROUP BY player_id
            )
        ) pes ON e_pred.racer_number = pes.player_id
        """
        escape_rate_clause = f"AND pes.escape_rate IS NOT NULL AND pes.escape_rate >= {cond['escape_rate_min']} "

    # バイアス指数フィルター（Tier 2と同じ重複対策：最新レコードのみ）
    bias_join = ""
    bias_clause = ""
    if cond.get('bias_max') is not None:
        bias_join = """
        LEFT JOIN entries e_bias ON r.id = e_bias.race_id AND e_bias.pit_number = rp1.pit_number
        LEFT JOIN (
            SELECT player_id, bias_index
            FROM player_bias_stats
            WHERE stadium_id IS NULL AND bias_index IS NOT NULL
            AND id IN (
                SELECT MAX(id)
                FROM player_bias_stats
                WHERE stadium_id IS NULL AND bias_index IS NOT NULL
                GROUP BY player_id
            )
        ) pbs ON e_bias.racer_number = pbs.player_id
        """
        bias_clause = f"AND pbs.bias_index IS NOT NULL AND pbs.bias_index < {cond['bias_max']} "

    # モーター連帯率フィルター
    motor_rate_join = ""
    motor_rate_clause = ""
    if cond.get('p1_motor_second_rate_min') is not None:
        motor_rate_join = """
        LEFT JOIN entries e_motor ON r.id = e_motor.race_id AND e_motor.pit_number = rp1.pit_number
        """
        motor_rate_clause = f"AND e_motor.motor_second_rate >= {cond['p1_motor_second_rate_min']} "

    # パターンHの場合は5位までの予測が必要（INNER JOINでrp5まで）
    use_pattern_h = cond.get('use_pattern_h', True)

    if use_pattern_h:
        # パターンH: 5位までの予測が必要
        query = f"""
        SELECT DISTINCT r.id
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
        JOIN race_predictions rp5 ON r.id = rp5.race_id AND rp5.prediction_type = 'before' AND rp5.rank_prediction = 5
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        {escape_rate_join}
        {bias_join}
        {motor_rate_join}
        WHERE rp.rank_prediction = 1
        {confidence_clause}
        AND e1.racer_rank IN ({c1_ranks_str})
        AND r.race_date >= '{start_date}'
        AND r.race_date < '{end_date}'
        {venue_clause}
        {motor_clause}
        {race_exclude_clause}
        {venue_exclude_clause}
        {predicted_course_clause}
        {c1_second_rate_clause}
        {month_exclude_clause}
        {escape_rate_clause}
        {bias_clause}
        {motor_rate_clause}
        """
    else:
        # 1点買い: 3位までの予測でOK
        query = f"""
        SELECT DISTINCT r.id
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        {escape_rate_join}
        {bias_join}
        {motor_rate_join}
        WHERE rp.rank_prediction = 1
        {confidence_clause}
        AND e1.racer_rank IN ({c1_ranks_str})
        AND r.race_date >= '{start_date}'
        AND r.race_date < '{end_date}'
        {venue_clause}
        {motor_clause}
        {race_exclude_clause}
        {venue_exclude_clause}
        {predicted_course_clause}
        {c1_second_rate_clause}
        {month_exclude_clause}
        {escape_rate_clause}
        {bias_clause}
        {motor_rate_clause}
        """

    cursor.execute(query)
    race_ids = set(row[0] for row in cursor.fetchall())
    return race_ids

def main():
    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    # 期間設定（Tier 2と同じ6年間）
    start_date = '2020-01-01'
    end_date = '2026-01-01'

    print("=" * 90)
    print("全条件の重複状況調査（2020-2025年・6年間）")
    print("=" * 90)
    print()

    # STEP 1: 各条件の対象レース数を取得
    print("[STEP 1] 各条件の対象レース数")
    print("-" * 90)
    print(f"{'No':<4} {'条件ID':<20} {'条件名':<30} {'方式':<5} {'レース数':>8}")
    print("-" * 90)

    condition_races = {}
    for i, cond in enumerate(STANDARD_BET_CONDITIONS, 1):
        race_ids = get_race_ids_for_condition(cursor, cond, start_date, end_date)
        condition_races[cond['id']] = race_ids
        pattern = 'P.H' if cond.get('use_pattern_h', True) else '1点'
        print(f"{i:<4} {cond['id']:<20} {cond['name']:<30} {pattern:<5} {len(race_ids):>8}")

    print()

    # STEP 2: 条件ペアごとの重複を計算
    print("[STEP 2] 条件ペア間の重複レース数")
    print("-" * 90)
    print(f"{'条件1':<20} {'条件2':<20} {'重複数':>8} {'条件1基準':>10} {'条件2基準':>10}")
    print("-" * 90)

    overlaps = []
    total_unique_races = set()

    for i, cond1 in enumerate(STANDARD_BET_CONDITIONS):
        for j, cond2 in enumerate(STANDARD_BET_CONDITIONS):
            if i >= j:
                continue  # 同一条件と重複計算を避ける

            races1 = condition_races[cond1['id']]
            races2 = condition_races[cond2['id']]
            overlap = races1 & races2

            if len(overlap) > 0:
                overlap_rate1 = len(overlap) / len(races1) * 100 if len(races1) > 0 else 0
                overlap_rate2 = len(overlap) / len(races2) * 100 if len(races2) > 0 else 0
                overlaps.append({
                    'cond1_id': cond1['id'],
                    'cond2_id': cond2['id'],
                    'overlap_count': len(overlap),
                    'overlap_rate1': overlap_rate1,
                    'overlap_rate2': overlap_rate2,
                })
                print(f"{cond1['id']:<20} {cond2['id']:<20} {len(overlap):>8} {overlap_rate1:>9.1f}% {overlap_rate2:>9.1f}%")

        total_unique_races |= condition_races[cond1['id']]

    print()

    # STEP 3: 重複率の高い組み合わせトップ10
    print("[STEP 3] 重複率の高い組み合わせトップ10（条件2基準）")
    print("-" * 90)
    print(f"{'順位':<4} {'条件1':<20} {'条件2':<20} {'重複数':>8} {'条件2基準':>10}")
    print("-" * 90)

    # 条件2基準の重複率でソート
    overlaps_sorted = sorted(overlaps, key=lambda x: x['overlap_rate2'], reverse=True)
    for rank, overlap in enumerate(overlaps_sorted[:10], 1):
        print(f"{rank:<4} {overlap['cond1_id']:<20} {overlap['cond2_id']:<20} "
              f"{overlap['overlap_count']:>8} {overlap['overlap_rate2']:>9.1f}%")

    print()

    # STEP 4: 全体の重複状況
    print("[STEP 4] 全体サマリー")
    print("-" * 90)
    total_races_sum = sum(len(races) for races in condition_races.values())
    total_unique_count = len(total_unique_races)
    total_duplicates = total_races_sum - total_unique_count

    print(f"総レース数（各条件の合計）: {total_races_sum:,}件")
    print(f"ユニークレース数: {total_unique_count:,}件")
    print(f"重複レース数: {total_duplicates:,}件")
    print(f"重複割合: {total_duplicates / total_races_sum * 100:.1f}%")
    print()

    # 重複が最も多い条件を特定
    print("[参考] 重複回数の多い条件トップ5")
    print("-" * 90)
    condition_overlap_counts = {}
    for overlap in overlaps:
        cond1 = overlap['cond1_id']
        cond2 = overlap['cond2_id']
        condition_overlap_counts[cond1] = condition_overlap_counts.get(cond1, 0) + overlap['overlap_count']
        condition_overlap_counts[cond2] = condition_overlap_counts.get(cond2, 0) + overlap['overlap_count']

    top_conditions = sorted(condition_overlap_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    for rank, (cond_id, count) in enumerate(top_conditions, 1):
        print(f"{rank}. {cond_id}: {count:,}件の重複")

    conn.close()

if __name__ == '__main__':
    main()
