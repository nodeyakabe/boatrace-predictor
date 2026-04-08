#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""バックテストの共通関数"""
import sqlite3
from typing import Dict, List, Set

import sys
import os
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)
from config.bet_conditions import GLOBAL_VENUE_MONTH_EXCLUDES, GLOBAL_MONTH_EXCLUDES

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
    combined_month_exclude = list(cond.get('month_exclude') or []) + list(GLOBAL_MONTH_EXCLUDES or [])
    if combined_month_exclude:
        months = ','.join(map(str, sorted(set(combined_month_exclude))))
        month_exclude_clause = f"AND CAST(strftime('%m', r.race_date) AS INTEGER) NOT IN ({months})"

    # 会場×月除外フィルター（standard_backtest.pyと同じロジック）
    venue_month_exclude_clause = ""
    combined_excludes = list(cond.get('venue_month_exclude') or []) + list(GLOBAL_VENUE_MONTH_EXCLUDES or [])
    if combined_excludes:
        conditions = []
        for venue, month in combined_excludes:
            if isinstance(venue, int):
                venue_code = f"'{venue:02d}'"
            else:
                venue_code = f"'{venue}'"
            conditions.append(f"(r.venue_code = {venue_code} AND CAST(strftime('%m', r.race_date) AS INTEGER) = {month})")
        venue_month_exclude_clause = f"AND NOT ({' OR '.join(conditions)})"

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

    # 予測順位別級別フィルター（B2条件対応: 予測1-3位のいずれかが指定級別）
    predicted_rank_class_clause = ""
    if cond.get('predicted_rank_has_class') and cond.get('predicted_rank_range'):
        class_list = "','".join(cond['predicted_rank_has_class'])
        rank_min, rank_max = cond['predicted_rank_range']
        predicted_rank_class_clause = f"""
        AND EXISTS (
            SELECT 1
            FROM race_predictions rp_class
            LEFT JOIN racers r_class ON rp_class.racer_number = r_class.racer_number
            WHERE rp_class.race_id = r.id
            AND rp_class.prediction_type = 'before'
            AND rp_class.rank_prediction BETWEEN {rank_min} AND {rank_max}
            AND r_class.rank IN ('{class_list}')
        )
        """

    # スコア差フィルター（rp1.total_score - rp2.total_score >= min_score_gap）
    score_gap_clause = ""
    if cond.get('min_score_gap') is not None:
        score_gap_clause = f"AND (rp1.total_score - rp2.total_score) >= {cond['min_score_gap']}"

    # 3位-4位スコア差フィルター（3着予測の確度フィルタ）
    score_gap_3_4_join = ""
    score_gap_3_4_clause = ""
    if cond.get('min_score_gap_3_4') is not None:
        score_gap_3_4_join = """
        JOIN race_predictions rp4_gap ON r.id = rp4_gap.race_id
            AND rp4_gap.prediction_type = 'before' AND rp4_gap.rank_prediction = 4
        """
        score_gap_3_4_clause = f"AND (rp3.total_score - rp4_gap.total_score) >= {cond['min_score_gap_3_4']}"

    # モーター連帯率フィルター
    motor_rate_join = ""
    motor_rate_clause = ""
    if cond.get('p1_motor_second_rate_min') is not None:
        motor_rate_join = """
        LEFT JOIN entries e_motor ON r.id = e_motor.race_id AND e_motor.pit_number = rp1.pit_number
        """
        motor_rate_clause = f"AND e_motor.motor_second_rate >= {cond['p1_motor_second_rate_min']} "

    # 予測1位選手のavg_stフィルター（TJ-3: STタイム安定度）
    avg_st_join = ""
    avg_st_clause = ""
    if cond.get('p1_avg_st_max') is not None:
        avg_st_join = """
        LEFT JOIN entries e_avgst ON r.id = e_avgst.race_id AND e_avgst.pit_number = rp1.pit_number
        """
        avg_st_clause = f"AND e_avgst.avg_st IS NOT NULL AND e_avgst.avg_st <= {cond['p1_avg_st_max']} "

    # advance/before 完全一致フィルタ（2026-04-07追加）
    # びわこ(venue_code='11')はフィルタ不適用、advance欠損はパススルー
    advance_match_join = ""
    advance_match_clause = ""
    if cond.get('advance_before_match', False):
        advance_match_join = """
        LEFT JOIN race_predictions adv1 ON r.id = adv1.race_id AND adv1.prediction_type = 'advance' AND adv1.rank_prediction = 1
        LEFT JOIN race_predictions adv2 ON r.id = adv2.race_id AND adv2.prediction_type = 'advance' AND adv2.rank_prediction = 2
        LEFT JOIN race_predictions adv3 ON r.id = adv3.race_id AND adv3.prediction_type = 'advance' AND adv3.rank_prediction = 3
        """
        advance_match_clause = """
        AND (
            r.venue_code = '11'
            OR adv1.pit_number IS NULL
            OR (adv1.pit_number = rp1.pit_number AND adv2.pit_number = rp2.pit_number AND adv3.pit_number = rp3.pit_number)
        )
        """

    # 波高フィルター（2026-04-06追加）
    # wave_height_max: この値を超える波高を除外（荒れレース除外が主用途）
    # wave_height_min: この値未満の波高を除外（荒れレース専用条件が主用途）
    wave_height_join = ""
    wave_height_clause = ""
    if cond.get('wave_height_max') is not None or cond.get('wave_height_min') is not None:
        wave_height_join = "LEFT JOIN race_conditions rc ON r.id = rc.race_id"
        if cond.get('wave_height_max') is not None:
            wave_height_clause += f"AND (rc.wave_height IS NULL OR rc.wave_height <= {cond['wave_height_max']}) "
        if cond.get('wave_height_min') is not None:
            wave_height_clause += f"AND rc.wave_height IS NOT NULL AND rc.wave_height >= {cond['wave_height_min']} "

    # パターンHの場合は予測が必要（INNER JOINでrp4/rp5まで）
    use_pattern_h = cond.get('use_pattern_h', False)
    exclude_p5 = cond.get('pattern_h_exclude_p5', False)

    if use_pattern_h:
        # パターンH: 4位まで必要（p5除外時）/ 5位まで必要（通常）
        _rp5_join = "" if exclude_p5 else "JOIN race_predictions rp5 ON r.id = rp5.race_id AND rp5.prediction_type = 'before' AND rp5.rank_prediction = 5"
        query = f"""
        SELECT DISTINCT r.id
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
        {_rp5_join}
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        {escape_rate_join}
        {bias_join}
        {motor_rate_join}
        {avg_st_join}
        {wave_height_join}
        {advance_match_join}
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
        {venue_month_exclude_clause}
        {escape_rate_clause}
        {bias_clause}
        {motor_rate_clause}
        {score_gap_clause}
        {avg_st_clause}
        {wave_height_clause}
        {predicted_rank_class_clause}
        {advance_match_clause}
        """
    else:
        # 1点買い: 3位までの予測でOK（min_score_gap_3_4 指定時は rp4_gap もJOIN）
        query = f"""
        SELECT DISTINCT r.id
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        {score_gap_3_4_join}
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        {escape_rate_join}
        {bias_join}
        {motor_rate_join}
        {avg_st_join}
        {wave_height_join}
        {advance_match_join}
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
        {venue_month_exclude_clause}
        {escape_rate_clause}
        {bias_clause}
        {motor_rate_clause}
        {score_gap_clause}
        {score_gap_3_4_clause}
        {avg_st_clause}
        {wave_height_clause}
        {predicted_rank_class_clause}
        {advance_match_clause}
        """

    cursor.execute(query)
    race_ids = set(row[0] for row in cursor.fetchall())

    # オッズデータの有無をチェック（Tier 3との一致のため）
    if require_odds and race_ids:
        _use_ph = cond.get('use_pattern_h', False)
        _excl_p5 = cond.get('pattern_h_exclude_p5', False)
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
            if _use_ph and _excl_p5 and len(pits) >= 4:
                combinations = [
                    f"{pits[0]}-{pits[1]}-{pits[2]}",
                    f"{pits[0]}-{pits[1]}-{pits[3]}",
                ]
            elif _use_ph and len(pits) >= 5:
                combinations = [
                    f"{pits[0]}-{pits[1]}-{pits[2]}",
                    f"{pits[0]}-{pits[1]}-{pits[3]}",
                    f"{pits[0]}-{pits[1]}-{pits[4]}",
                ]
            else:
                combinations = [f"{pits[0]}-{pits[1]}-{pits[2]}"]

            # オッズ範囲を取得
            odds_min = cond.get('odds_min', 0)
            odds_max = cond.get('odds_max', 9999)

            # オッズデータの存在確認 + 範囲チェック
            placeholders = ','.join(['?'] * len(combinations))
            cursor.execute(f"""
                SELECT combination, odds FROM trifecta_odds
                WHERE race_id = ? AND combination IN ({placeholders})
            """, [race_id] + combinations)

            odds_rows = cursor.fetchall()
            # いずれかのコンビネーションがオッズ範囲内ならOK
            has_valid_odds = any(odds_min <= row[1] < odds_max for row in odds_rows if row[1])

            if has_valid_odds:
                filtered_race_ids.add(race_id)

        return filtered_race_ids

    return race_ids
