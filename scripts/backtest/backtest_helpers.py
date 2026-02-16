#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""バックテストの共通関数"""
import sqlite3
from typing import Dict, List, Set

def get_race_ids_for_condition(
    cursor: sqlite3.Cursor,
    cond: Dict,
    start_date: str,
    end_date: str,
    require_odds: bool = False
) -> Set[int]:
    """条件に該当するレースIDのセットを取得

    Args:
        cursor: DBカーソル
        cond: 条件定義（config/bet_conditions.pyのSTANDARD_BET_CONDITIONS要素）
        start_date: 開始日（'YYYY-MM-DD'形式）
        end_date: 終了日（'YYYY-MM-DD'形式）

    Returns:
        レースIDのセット

    Note:
        - Tier 2のbuild_condition_query()と同じフィルターロジックを使用
        - パターンHの場合は5位までの予測が必要（INNER JOIN）
    """
    c1_ranks_str = ','.join([f"'{r}'" for r in cond['c1_rank']])

    # 信頼度フィルター（Noneの場合は全信頼度対象）
    confidence_clause = ""
    if cond.get('confidence') is not None:
        confidence_clause = f"AND rp.confidence = '{cond['confidence']}'"

    # 各種フィルター条件（standard_backtest.pyと同じ）
    venue_clause = ""
    if cond.get('venue_filter'):
        venue_codes = [f"'{v:02d}'" if isinstance(v, int) else f"'{v}'" for v in cond['venue_filter']]
        venue_clause = f"AND r.venue_code IN ({','.join(venue_codes)})"

    motor_clause = ""
    if cond.get('motor_min'):
        motor_clause = f"AND e1.motor_second_rate >= {cond['motor_min']}"

    race_exclude_clause = ""
    if cond.get('race_exclude'):
        race_exclude_clause = f"AND r.race_number NOT IN ({','.join(map(str, cond['race_exclude']))})"

    venue_exclude_clause = ""
    if cond.get('venue_exclude'):
        venue_codes = [f"'{v:02d}'" if isinstance(v, int) else f"'{v}'" for v in cond['venue_exclude']]
        venue_exclude_clause = f"AND r.venue_code NOT IN ({','.join(venue_codes)})"

    predicted_course_clause = ""
    if cond.get('predicted_course'):
        predicted_course_clause = f"AND rp1.pit_number = {cond['predicted_course']}"

    c1_second_rate_clause = ""
    if cond.get('c1_second_rate_min') is not None:
        c1_second_rate_clause += f"AND e1.second_rate >= {cond['c1_second_rate_min']} "
    if cond.get('c1_second_rate_max') is not None:
        c1_second_rate_clause += f"AND e1.second_rate < {cond['c1_second_rate_max']} "

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

    # オッズデータの有無をチェック（Tier 3との一致のため）
    if require_odds and race_ids:
        use_pattern_h = cond.get('use_pattern_h', True)
        filtered_race_ids = set()

        for race_id in race_ids:
            # 予測順位を取得（オッズコンビネーション構築のため）
            cursor.execute("""
                SELECT pit_number
                FROM race_predictions
                WHERE race_id = ? AND prediction_type = 'before'
                ORDER BY rank_prediction
                LIMIT 5
            """, (race_id,))
            pits = [row[0] for row in cursor.fetchall()]

            if len(pits) < 3:
                continue

            # オッズコンビネーションを構築
            if use_pattern_h and len(pits) >= 5:
                combinations = [
                    f"{pits[0]}-{pits[1]}-{pits[2]}",
                    f"{pits[0]}-{pits[1]}-{pits[3]}",
                    f"{pits[0]}-{pits[1]}-{pits[4]}",
                ]
            else:
                combinations = [f"{pits[0]}-{pits[1]}-{pits[2]}"]

            # オッズデータの存在確認
            placeholders = ','.join(['?'] * len(combinations))
            cursor.execute(f"""
                SELECT COUNT(*) FROM trifecta_odds
                WHERE race_id = ? AND combination IN ({placeholders})
            """, [race_id] + combinations)

            if cursor.fetchone()[0] > 0:
                filtered_race_ids.add(race_id)

        return filtered_race_ids

    return race_ids
