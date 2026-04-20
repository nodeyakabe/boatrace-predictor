#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
標準化バックテストスクリプト（T-1）

目的:
    3層アーキテクチャ（戦略B/フィルターC/パターンH）を全て適用した
    実購入と同じ条件でのバックテストを実行する

テスト対象:
    1. 全体テスト: 2020年〜2025年（6年間）
    2. 詳細テスト: 2025年1月〜12月（月別・条件別）

使用方法:
    # 2025年詳細テスト（月別・条件別）
    python scripts/backtest/standardized_backtest.py

    # 6年間全体テスト
    python scripts/backtest/standardized_backtest.py --full

    # 特定年のテスト
    python scripts/backtest/standardized_backtest.py --year 2024

    # ベースライン保存
    python scripts/backtest/standardized_backtest.py --save-baseline

    # ベースラインと比較
    python scripts/backtest/standardized_backtest.py --compare

出力:
    - 全体サマリー（ROI、収支、的中率）
    - 条件別パフォーマンス
    - 年度別パフォーマンス（--full時）
    - 月別パフォーマンス（詳細テスト時）

作成日: 2026-01-07
"""
import sqlite3
import sys
import io
import os
import json
import argparse
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from config.bet_conditions import STANDARD_BET_CONDITIONS, GLOBAL_VENUE_MONTH_EXCLUDES, GLOBAL_MONTH_EXCLUDES
from src.betting.evaluator_helpers import create_standard_evaluator

# ============================================================
# 購入条件定義（config/bet_conditions.py から読み込み）
# ============================================================
# ※変更時は config/bet_conditions.py を修正してください
# ※このファイルを直接編集しないでください

CONDITIONS = STANDARD_BET_CONDITIONS

# ============================================================
# RJ条件定義（データ補完後の再検証用）
# ============================================================
# config/review_conditions.json の条件をテスト可能な形式で定義
# 使用方法: python scripts/backtest/standard_backtest.py --rj-condition RJ-3 --full

RJ_CONDITIONS = {
    # RJ-3: 連帯率フィルター（Motor40%+）
    'RJ-3': {
        'name': 'B×10-30×穴源×会場+Motor40%',
        'confidence': 'B',
        'c1_rank': ['A1', 'A2', 'B1'],
        'odds_min': 10,
        'odds_max': 30,
        'venue_filter': [6, 7, 8, 10, 15, 19],  # 浜名湖,蒲郡,常滑,三国,丸亀,下関
        'bias_max': -0.3,
        'p1_motor_second_rate_min': 40,
        'description': 'RJ-3: B×10-30倍×穴源×会場+モーター2連対率40%+',
        'use_pattern_h': False,  # 1点買い
    },
    # RJ-4: D×A1×モーター40%+
    'RJ-4-A1': {
        'name': 'D×A1×Motor40%+',
        'confidence': 'D',
        'c1_rank': ['A1'],
        'odds_min': 10,
        'odds_max': 999,
        'venue_filter': None,
        'motor_min': 40,
        'description': 'RJ-4: D×A1級×モーター40%+（全オッズ帯）',
        'use_pattern_h': True,  # パターンH
    },
    # RJ-4: D×A2×モーター40%+
    'RJ-4-A2': {
        'name': 'D×A2×Motor40%+',
        'confidence': 'D',
        'c1_rank': ['A2'],
        'odds_min': 10,
        'odds_max': 999,
        'venue_filter': None,
        'motor_min': 40,
        'description': 'RJ-4: D×A2級×モーター40%+（全オッズ帯）',
        'use_pattern_h': True,  # パターンH
    },
    # RJ-5: A×A2×モーター40%+
    'RJ-5': {
        'name': 'A×A2×Motor40%+',
        'confidence': 'A',
        'c1_rank': ['A2'],
        'odds_min': 10,
        'odds_max': 999,
        'venue_filter': None,
        'motor_min': 40,
        'description': 'RJ-5: A×A2級×モーター40%+（全オッズ帯）',
        'use_pattern_h': False,  # 1点買い
    },
}

# ============================================================
# パターンH: 3点買い定義（1-2軸傾斜: 200円/100円/100円）
# ============================================================
# 総投資額: 400円/レース
# 買い目: 1-2-3, 1-2-4, 1-2-5 （1位-2位を軸に3位候補を3点）

PATTERN_H_CONFIG = {
    'name': 'パターンH',
    'description': '1-2軸傾斜買い（200/100/100円）',
    'bets': [
        {'rank3': 3, 'amount': 200},  # 1-2-3: 200円
        {'rank3': 4, 'amount': 100},  # 1-2-4: 100円
        {'rank3': 5, 'amount': 100},  # 1-2-5: 100円
    ],
    'total_investment': 400,
}

VENUE_NAMES = {
    1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川', 6: '浜名湖',
    7: '蒲郡', 8: '常滑', 9: '津', 10: '三国', 11: '琵琶湖', 12: '住之江',
    13: '尼崎', 14: '鳴門', 15: '丸亀', 16: '児島', 17: '宮島', 18: '徳山',
    19: '下関', 20: '若松', 21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村'
}


def build_condition_query(cond: Dict, date_start: str, date_end: str) -> str:
    """条件に応じたSQLクエリを構築

    use_pattern_h フラグに応じて:
    - True: パターンH（3点買い 200円/100円/100円 = 400円）
    - False: 1点買い（100円）
    """
    c1_rank_str = "','".join(cond['c1_rank'])
    use_pattern_h = cond.get('use_pattern_h', True)  # デフォルトはパターンH

    # 信頼度フィルター（2026-02-12追加: Noneの場合は全信頼度対象）
    confidence_clause = ""
    if cond.get('confidence') is not None:
        confidence_clause = f"AND rp.confidence = '{cond['confidence']}'"

    # 各種フィルター条件
    venue_clause = ""
    if cond.get('venue_filter'):
        # venue_codeは文字列（'01', '02', etc）なので、整数の場合は0埋め2桁文字列に変換
        venue_codes = []
        for v in cond['venue_filter']:
            if isinstance(v, int):
                venue_codes.append(f"'{v:02d}'")
            else:
                venue_codes.append(f"'{v}'")
        venue_clause = f"AND r.venue_code IN ({','.join(venue_codes)})"

    motor_clause = ""
    if cond.get('motor_min'):
        motor_clause = f"AND e1.motor_second_rate >= {cond['motor_min']}"

    race_exclude_clause = ""
    if cond.get('race_exclude'):
        race_exclude_clause = f"AND r.race_number NOT IN ({','.join(map(str, cond['race_exclude']))})"

    venue_exclude_clause = ""
    if cond.get('venue_exclude'):
        # venue_codeは文字列なので、整数の場合は0埋め2桁文字列に変換
        venue_codes = []
        for v in cond['venue_exclude']:
            if isinstance(v, int):
                venue_codes.append(f"'{v:02d}'")
            else:
                venue_codes.append(f"'{v}'")
        venue_exclude_clause = f"AND r.venue_code NOT IN ({','.join(venue_codes)})"

    predicted_course_clause = ""
    if cond.get('predicted_course'):
        predicted_course_clause = f"AND rp1.pit_number = {cond['predicted_course']}"

    c1_second_rate_clause = ""
    if cond.get('c1_second_rate_min') is not None:
        c1_second_rate_clause += f"AND e1.second_rate >= {cond['c1_second_rate_min']} "
    if cond.get('c1_second_rate_max') is not None:
        c1_second_rate_clause += f"AND e1.second_rate < {cond['c1_second_rate_max']} "

    # 月除外フィルター（2026-01-09追加：冬季除外用）
    month_exclude_clause = ""
    combined_month_exclude = list(cond.get('month_exclude') or []) + list(GLOBAL_MONTH_EXCLUDES or [])
    if combined_month_exclude:
        months = ','.join(map(str, sorted(set(combined_month_exclude))))
        month_exclude_clause = f"AND CAST(strftime('%m', r.race_date) AS INTEGER) NOT IN ({months})"

    # 会場×月除外フィルター（2026-02-16追加：1-4月特有の弱会場除外用）
    # 条件固有の除外リストとグローバル除外リストを統合
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

    # 逃げ率フィルター（2026-01-09追加、2026-02-16重複レコード対策）
    escape_rate_join = ""
    escape_rate_clause = ""
    if cond.get('escape_rate_min') is not None:
        # 1コース予測の選手の逃げ率をチェック（最新レコードのみ）
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

    # バイアス指数フィルター（2026-01-13追加：穴源選手抽出用、2026-02-16重複レコード対策）
    bias_join = ""
    bias_clause = ""
    if cond.get('bias_max') is not None:
        # 1着予測の選手のバイアス指数をチェック（最新レコードのみ）
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

    # モーター連帯率フィルター（2026-01-26追加）
    motor_rate_join = ""
    motor_rate_clause = ""
    if cond.get('p1_motor_second_rate_min') is not None:
        # 1着予測の選手のモーター2連対率をチェック
        motor_rate_join = """
        LEFT JOIN entries e_motor ON r.id = e_motor.race_id AND e_motor.pit_number = rp1.pit_number
        """
        motor_rate_clause = f"AND e_motor.motor_second_rate >= {cond['p1_motor_second_rate_min']} "

    # 予測順位別級別フィルター（2026-02-12追加：B2条件対応）
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

    # スコアフィルター（2026-04-17追加: p1予測のtotal_scoreで絞り込み）
    score_clause = ""
    if cond.get('score_min') is not None:
        score_clause += f"AND rp1.total_score >= {cond['score_min']} "
    if cond.get('score_max') is not None:
        score_clause += f"AND rp1.total_score < {cond['score_max']} "

    use_pattern_p142 = cond.get('use_pattern_p142', False)
    use_pattern_p143 = cond.get('use_pattern_p143', False)
    use_pattern_p132 = cond.get('use_pattern_p132', False)
    use_pattern_p124 = cond.get('use_pattern_p124', False)

    if use_pattern_p143:
        # p1-p4-p3 パターン: 予測1位-予測4位-予測3位の三連単 100円（2026-04-17追加）
        query = f'''
        WITH race_base AS (
            SELECT
                r.id as race_id,
                r.race_date,
                r.venue_code,
                rp.confidence,
                e1.racer_rank as c1_rank,
                rp1.pit_number as p1,
                rp3.pit_number as p3,
                rp4.pit_number as p4
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
            JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
            {escape_rate_join}
            {bias_join}
            {motor_rate_join}
            {wave_height_join}
            WHERE rp.rank_prediction = 1
            {confidence_clause}
            AND e1.racer_rank IN ('{c1_rank_str}')
            AND r.race_date >= '{date_start}'
            AND r.race_date < '{date_end}'
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
            {wave_height_clause}
            {predicted_rank_class_clause}
            {score_clause}
        ),
        race_bets AS (
            SELECT
                rb.*,
                -- p1-p4-p3 オッズ取得
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                          AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p4 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)), 0) as odds_143,
                -- 実際の結果
                (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') as actual_1st,
                (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') as actual_2nd,
                (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') as actual_3rd
            FROM race_base rb
        ),
        race_payouts AS (
            SELECT
                rb.*,
                -- 1点買い: 100円
                CASE WHEN odds_143 >= {cond['odds_min']} AND odds_143 < {cond['odds_max']} THEN 100 ELSE 0 END as bet_amount,
                -- 的中判定・払戻
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p4 AND actual_3rd = p3
                         AND odds_143 >= {cond['odds_min']} AND odds_143 < {cond['odds_max']}
                    THEN odds_143 * 100 ELSE 0
                END as payout,
                -- 的中フラグ
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p4 AND actual_3rd = p3
                         AND odds_143 >= {cond['odds_min']} AND odds_143 < {cond['odds_max']}
                    THEN 1 ELSE 0
                END as is_hit
            FROM race_bets rb
        )
        SELECT
            COUNT(*) as races,
            SUM(CASE WHEN bet_amount > 0 THEN 1 ELSE 0 END) as bets,
            SUM(is_hit) as hits,
            SUM(bet_amount) as total_investment,
            SUM(payout) as total_payout
        FROM race_payouts
        WHERE bet_amount > 0
        '''
    elif use_pattern_p132:
        # p1-p3-p2 パターン: 予測1位-予測3位-予測2位の三連単 100円（2026-04-17追加）
        query = f'''
        WITH race_base AS (
            SELECT
                r.id as race_id,
                r.race_date,
                r.venue_code,
                rp.confidence,
                e1.racer_rank as c1_rank,
                rp1.pit_number as p1,
                rp2.pit_number as p2,
                rp3.pit_number as p3
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
            {escape_rate_join}
            {bias_join}
            {motor_rate_join}
            {wave_height_join}
            WHERE rp.rank_prediction = 1
            {confidence_clause}
            AND e1.racer_rank IN ('{c1_rank_str}')
            AND r.race_date >= '{date_start}'
            AND r.race_date < '{date_end}'
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
            {wave_height_clause}
            {predicted_rank_class_clause}
            {score_clause}
        ),
        race_bets AS (
            SELECT
                rb.*,
                -- p1-p3-p2 オッズ取得
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                          AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p3 AS TEXT) || '-' || CAST(rb.p2 AS TEXT)), 0) as odds_132,
                -- 実際の結果
                (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') as actual_1st,
                (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') as actual_2nd,
                (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') as actual_3rd
            FROM race_base rb
        ),
        race_payouts AS (
            SELECT
                rb.*,
                -- 1点買い: 100円
                CASE WHEN odds_132 >= {cond['odds_min']} AND odds_132 < {cond['odds_max']} THEN 100 ELSE 0 END as bet_amount,
                -- 的中判定・払戻
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p3 AND actual_3rd = p2
                         AND odds_132 >= {cond['odds_min']} AND odds_132 < {cond['odds_max']}
                    THEN odds_132 * 100 ELSE 0
                END as payout,
                -- 的中フラグ
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p3 AND actual_3rd = p2
                         AND odds_132 >= {cond['odds_min']} AND odds_132 < {cond['odds_max']}
                    THEN 1 ELSE 0
                END as is_hit
            FROM race_bets rb
        )
        SELECT
            COUNT(*) as races,
            SUM(CASE WHEN bet_amount > 0 THEN 1 ELSE 0 END) as bets,
            SUM(is_hit) as hits,
            SUM(bet_amount) as total_investment,
            SUM(payout) as total_payout
        FROM race_payouts
        WHERE bet_amount > 0
        '''
    elif use_pattern_p142:
        # p1-p4-p2 パターン: 予測1位-予測4位-予測2位の三連単 100円（2026-04-17追加）
        query = f'''
        WITH race_base AS (
            SELECT
                r.id as race_id,
                r.race_date,
                r.venue_code,
                rp.confidence,
                e1.racer_rank as c1_rank,
                rp1.pit_number as p1,
                rp2.pit_number as p2,
                rp4.pit_number as p4
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
            JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
            {escape_rate_join}
            {bias_join}
            {motor_rate_join}
            {wave_height_join}
            WHERE rp.rank_prediction = 1
            {confidence_clause}
            AND e1.racer_rank IN ('{c1_rank_str}')
            AND r.race_date >= '{date_start}'
            AND r.race_date < '{date_end}'
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
            {wave_height_clause}
            {predicted_rank_class_clause}
            {score_clause}
        ),
        race_bets AS (
            SELECT
                rb.*,
                -- p1-p4-p2 オッズ取得
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                          AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p4 AS TEXT) || '-' || CAST(rb.p2 AS TEXT)), 0) as odds_142,
                -- 実際の結果
                (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') as actual_1st,
                (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') as actual_2nd,
                (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') as actual_3rd
            FROM race_base rb
        ),
        race_payouts AS (
            SELECT
                rb.*,
                -- 1点買い: 100円
                CASE WHEN odds_142 >= {cond['odds_min']} AND odds_142 < {cond['odds_max']} THEN 100 ELSE 0 END as bet_amount,
                -- 的中判定・払戻
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p4 AND actual_3rd = p2
                         AND odds_142 >= {cond['odds_min']} AND odds_142 < {cond['odds_max']}
                    THEN odds_142 * 100 ELSE 0
                END as payout,
                -- 的中フラグ
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p4 AND actual_3rd = p2
                         AND odds_142 >= {cond['odds_min']} AND odds_142 < {cond['odds_max']}
                    THEN 1 ELSE 0
                END as is_hit
            FROM race_bets rb
        )
        SELECT
            COUNT(*) as races,
            SUM(CASE WHEN bet_amount > 0 THEN 1 ELSE 0 END) as bets,
            SUM(is_hit) as hits,
            SUM(bet_amount) as total_investment,
            SUM(payout) as total_payout
        FROM race_payouts
        WHERE bet_amount > 0
        '''
    elif use_pattern_p124:
        # p1-p2-p4 パターン: 予測1位-予測2位-予測4位の三連単 100円（2026-04-20追加）
        query = f'''
        WITH race_base AS (
            SELECT
                r.id as race_id,
                r.race_date,
                r.venue_code,
                rp.confidence,
                e1.racer_rank as c1_rank,
                rp1.pit_number as p1,
                rp2.pit_number as p2,
                rp4.pit_number as p4
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
            JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
            {escape_rate_join}
            {bias_join}
            {motor_rate_join}
            {wave_height_join}
            WHERE rp.rank_prediction = 1
            {confidence_clause}
            AND e1.racer_rank IN ('{c1_rank_str}')
            AND r.race_date >= '{date_start}'
            AND r.race_date < '{date_end}'
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
            {wave_height_clause}
            {predicted_rank_class_clause}
            {score_clause}
        ),
        race_bets AS (
            SELECT
                rb.*,
                -- p1-p2-p4 オッズ取得
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                          AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p4 AS TEXT)), 0) as odds_124,
                -- 実際の結果
                (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') as actual_1st,
                (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') as actual_2nd,
                (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') as actual_3rd
            FROM race_base rb
        ),
        race_payouts AS (
            SELECT
                rb.*,
                -- 1点買い: 100円
                CASE WHEN odds_124 >= {cond['odds_min']} AND odds_124 < {cond['odds_max']} THEN 100 ELSE 0 END as bet_amount,
                -- 的中判定・払戻
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4
                         AND odds_124 >= {cond['odds_min']} AND odds_124 < {cond['odds_max']}
                    THEN odds_124 * 100 ELSE 0
                END as payout,
                -- 的中フラグ
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4
                         AND odds_124 >= {cond['odds_min']} AND odds_124 < {cond['odds_max']}
                    THEN 1 ELSE 0
                END as is_hit
            FROM race_bets rb
        )
        SELECT
            COUNT(*) as races,
            SUM(CASE WHEN bet_amount > 0 THEN 1 ELSE 0 END) as bets,
            SUM(is_hit) as hits,
            SUM(bet_amount) as total_investment,
            SUM(payout) as total_payout
        FROM race_payouts
        WHERE bet_amount > 0
        '''
    elif use_pattern_h:
        # パターンH: 3点買い（1-2-3: 200円, 1-2-4: 100円, 1-2-5: 100円）
        query = f'''
        WITH race_base AS (
            SELECT
                r.id as race_id,
                r.race_date,
                r.venue_code,
                rp.confidence,
                e1.racer_rank as c1_rank,
                rp1.pit_number as p1,
                rp2.pit_number as p2,
                rp3.pit_number as p3,
                rp4.pit_number as p4,
                rp5.pit_number as p5
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
            {wave_height_join}
            WHERE rp.rank_prediction = 1
            {confidence_clause}
            AND e1.racer_rank IN ('{c1_rank_str}')
            AND r.race_date >= '{date_start}'
            AND r.race_date < '{date_end}'
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
            {wave_height_clause}
            {predicted_rank_class_clause}
            {score_clause}
        ),
        race_with_results AS (
            SELECT
                rb.*,
                -- 3点買いオッズ取得
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                          AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)), 0) as odds_123,
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                          AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p4 AS TEXT)), 0) as odds_124,
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                          AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p5 AS TEXT)), 0) as odds_125,
                -- 実際の結果
                (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') as actual_1st,
                (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') as actual_2nd,
                (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') as actual_3rd
            FROM race_base rb
        ),
        race_payouts AS (
            SELECT
                rwr.*,
                -- パターンH: 1-2-3に200円、1-2-4に100円、1-2-5に100円
                CASE
                    WHEN odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']} THEN 200
                    ELSE 0
                END as bet_123,
                CASE
                    WHEN odds_124 >= {cond['odds_min']} AND odds_124 < {cond['odds_max']} THEN 100
                    ELSE 0
                END as bet_124,
                CASE
                    WHEN odds_125 >= {cond['odds_min']} AND odds_125 < {cond['odds_max']} THEN 100
                    ELSE 0
                END as bet_125,
                -- 的中判定・払戻
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3
                         AND odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']}
                    THEN odds_123 * 200 ELSE 0
                END as payout_123,
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4
                         AND odds_124 >= {cond['odds_min']} AND odds_124 < {cond['odds_max']}
                    THEN odds_124 * 100 ELSE 0
                END as payout_124,
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p5
                         AND odds_125 >= {cond['odds_min']} AND odds_125 < {cond['odds_max']}
                    THEN odds_125 * 100 ELSE 0
                END as payout_125,
                -- 的中フラグ
                CASE
                    WHEN (actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3 AND odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']})
                      OR (actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4 AND odds_124 >= {cond['odds_min']} AND odds_124 < {cond['odds_max']})
                      OR (actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p5 AND odds_125 >= {cond['odds_min']} AND odds_125 < {cond['odds_max']})
                    THEN 1 ELSE 0
                END as is_hit
            FROM race_with_results rwr
        )
        SELECT
            COUNT(*) as races,
            SUM(CASE WHEN bet_123 > 0 OR bet_124 > 0 OR bet_125 > 0 THEN 1 ELSE 0 END) as bets,
            SUM(is_hit) as hits,
            SUM(bet_123 + bet_124 + bet_125) as total_investment,
            SUM(payout_123 + payout_124 + payout_125) as total_payout
        FROM race_payouts
        WHERE bet_123 > 0 OR bet_124 > 0 OR bet_125 > 0
        '''
    else:
        # 1点買い: 1-2-3のみに100円
        query = f'''
        WITH race_base AS (
            SELECT
                r.id as race_id,
                r.race_date,
                r.venue_code,
                rp.confidence,
                e1.racer_rank as c1_rank,
                rp1.pit_number as p1,
                rp2.pit_number as p2,
                rp3.pit_number as p3
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
            {escape_rate_join}
            {bias_join}
            {motor_rate_join}
            {wave_height_join}
            WHERE rp.rank_prediction = 1
            {confidence_clause}
            AND e1.racer_rank IN ('{c1_rank_str}')
            AND r.race_date >= '{date_start}'
            AND r.race_date < '{date_end}'
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
            {wave_height_clause}
            {predicted_rank_class_clause}
            {score_clause}
        ),
        race_bets AS (
            SELECT
                rb.*,
                -- 1点買いオッズ取得
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                          AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)), 0) as odds_123,
                -- 実際の結果
                (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') as actual_1st,
                (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') as actual_2nd,
                (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') as actual_3rd
            FROM race_base rb
        ),
        race_payouts AS (
            SELECT
                rb.*,
                -- 1点買い: 100円
                CASE WHEN odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']} THEN 100 ELSE 0 END as bet_amount,
                -- 的中判定・払戻
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3
                         AND odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']}
                    THEN odds_123 * 100 ELSE 0
                END as payout,
                -- 的中フラグ
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3
                         AND odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']}
                    THEN 1 ELSE 0
                END as is_hit
            FROM race_bets rb
        )
        SELECT
            COUNT(*) as races,
            SUM(CASE WHEN bet_amount > 0 THEN 1 ELSE 0 END) as bets,
            SUM(is_hit) as hits,
            SUM(bet_amount) as total_investment,
            SUM(payout) as total_payout
        FROM race_payouts
        WHERE bet_amount > 0
        '''
    return query


def analyze_condition(cursor, cond: Dict, date_start: str, date_end: str) -> Dict:
    """条件別のパフォーマンスを分析（パターンH: 3点買い）"""
    query = build_condition_query(cond, date_start, date_end)
    cursor.execute(query)
    row = cursor.fetchone()

    if row and row[1] and row[1] > 0:
        races, bets, hits, investment, payout = row
        hits = hits or 0
        payout = payout or 0
        roi = 100.0 * payout / investment if investment > 0 else 0
        profit = payout - investment
        hit_rate = 100.0 * hits / bets if bets > 0 else 0
        return {
            'name': cond['name'],
            'description': cond.get('description', ''),
            'bets': bets,
            'hits': hits,
            'hit_rate': hit_rate,
            'investment': investment,
            'payout': payout,
            'roi': roi,
            'profit': profit,
        }
    return {
        'name': cond['name'],
        'description': cond.get('description', ''),
        'bets': 0,
        'hits': 0,
        'hit_rate': 0,
        'investment': 0,
        'payout': 0,
        'roi': 0,
        'profit': 0,
    }


def analyze_monthly(cursor, year: int, conditions: List[Dict] = None) -> List[Dict]:
    """月別の成績を分析

    Args:
        cursor: DBカーソル
        year: 対象年度
        conditions: 条件リスト（Noneの場合はCONDITIONSを使用）
    """
    if conditions is None:
        conditions = CONDITIONS

    monthly_results = []

    for month in range(1, 13):
        month_start = f"{year}-{month:02d}-01"
        if month == 12:
            month_end = f"{year + 1}-01-01"
        else:
            month_end = f"{year}-{month + 1:02d}-01"

        total_bets = 0
        total_hits = 0
        total_investment = 0
        total_payout = 0

        for cond in conditions:
            result = analyze_condition(cursor, cond, month_start, month_end)
            total_bets += result['bets']
            total_hits += result['hits']
            total_investment += result['investment']
            total_payout += result['payout']

        if total_bets > 0:
            roi = 100.0 * total_payout / total_investment if total_investment > 0 else 0
            profit = total_payout - total_investment
            hit_rate = 100.0 * total_hits / total_bets if total_bets > 0 else 0
            monthly_results.append({
                'month': month,
                'bets': total_bets,
                'hits': total_hits,
                'hit_rate': hit_rate,
                'investment': total_investment,
                'payout': total_payout,
                'roi': roi,
                'profit': profit,
            })
        else:
            monthly_results.append({
                'month': month,
                'bets': 0,
                'hits': 0,
                'hit_rate': 0,
                'investment': 0,
                'payout': 0,
                'roi': 0,
                'profit': 0,
            })

    return monthly_results


def analyze_condition_monthly(cursor, cond: Dict, year: int) -> List[Dict]:
    """特定条件の月別成績を分析"""
    monthly_results = []

    for month in range(1, 13):
        month_start = f"{year}-{month:02d}-01"
        if month == 12:
            month_end = f"{year + 1}-01-01"
        else:
            month_end = f"{year}-{month + 1:02d}-01"

        result = analyze_condition(cursor, cond, month_start, month_end)
        result['month'] = month
        monthly_results.append(result)

    return monthly_results


def analyze_yearly(cursor, years: List[int], conditions: List[Dict] = None) -> List[Dict]:
    """年度別の成績を分析

    Args:
        cursor: DBカーソル
        years: 対象年度リスト
        conditions: 条件リスト（Noneの場合はCONDITIONSを使用）
    """
    if conditions is None:
        conditions = CONDITIONS

    yearly_results = []

    for year in years:
        year_start = f"{year}-01-01"
        year_end = f"{year + 1}-01-01"

        total_bets = 0
        total_hits = 0
        total_investment = 0
        total_payout = 0

        for cond in conditions:
            result = analyze_condition(cursor, cond, year_start, year_end)
            total_bets += result['bets']
            total_hits += result['hits']
            total_investment += result['investment']
            total_payout += result['payout']

        if total_bets > 0:
            roi = 100.0 * total_payout / total_investment if total_investment > 0 else 0
            profit = total_payout - total_investment
            hit_rate = 100.0 * total_hits / total_bets if total_bets > 0 else 0
            yearly_results.append({
                'year': year,
                'bets': total_bets,
                'hits': total_hits,
                'hit_rate': hit_rate,
                'investment': total_investment,
                'payout': total_payout,
                'roi': roi,
                'profit': profit,
            })
        else:
            yearly_results.append({
                'year': year,
                'bets': 0,
                'hits': 0,
                'hit_rate': 0,
                'investment': 0,
                'payout': 0,
                'roi': 0,
                'profit': 0,
            })

    return yearly_results


def analyze_condition_yearly(cursor, cond: Dict, years: List[int]) -> List[Dict]:
    """特定条件の年度別成績を分析"""
    yearly_results = []

    for year in years:
        year_start = f"{year}-01-01"
        year_end = f"{year + 1}-01-01"

        result = analyze_condition(cursor, cond, year_start, year_end)
        result['year'] = year
        yearly_results.append(result)

    return yearly_results


def run_backtest(year: int = 2025, full_test: bool = False, rj_condition: Optional[str] = None) -> Dict:
    """バックテストを実行

    Args:
        year: 対象年度
        full_test: 6年間全体テスト
        rj_condition: RJ条件ID（例: 'RJ-3', 'RJ-4-A1'）
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # RJ条件が指定された場合は、その条件のみをテスト
    if rj_condition:
        if rj_condition not in RJ_CONDITIONS:
            raise ValueError(f"Unknown RJ condition: {rj_condition}. Available: {', '.join(RJ_CONDITIONS.keys())}")
        test_conditions = [RJ_CONDITIONS[rj_condition]]
        test_type = f'rj_{rj_condition}'
    else:
        test_conditions = CONDITIONS
        test_type = 'full' if full_test else 'detail'

    results = {
        'test_type': test_type,
        'date': datetime.now().isoformat(),
        'pattern': PATTERN_H_CONFIG['name'],
        'pattern_description': PATTERN_H_CONFIG['description'],
        'rj_condition': rj_condition,
        'conditions': [],
        'total': {},
    }

    if full_test:
        # 6年間全体テスト
        years = [2020, 2021, 2022, 2023, 2024, 2025]
        results['years'] = years
        results['year_start'] = years[0]
        results['year_end'] = years[-1]

        # 年度別サマリー
        results['yearly'] = analyze_yearly(cursor, years, test_conditions)

        # 条件別パフォーマンス（6年間合計）
        year_start = f"{years[0]}-01-01"
        year_end = f"{years[-1] + 1}-01-01"

        total_bets = 0
        total_hits = 0
        total_investment = 0
        total_payout = 0

        for cond in test_conditions:
            cond_result = analyze_condition(cursor, cond, year_start, year_end)
            # 年度別内訳を追加
            cond_result['yearly'] = analyze_condition_yearly(cursor, cond, years)
            results['conditions'].append(cond_result)

            total_bets += cond_result['bets']
            total_hits += cond_result['hits']
            total_investment += cond_result['investment']
            total_payout += cond_result['payout']

        # 6年間合計
        if total_bets > 0:
            results['total'] = {
                'bets': total_bets,
                'hits': total_hits,
                'hit_rate': 100.0 * total_hits / total_bets,
                'investment': total_investment,
                'payout': total_payout,
                'roi': 100.0 * total_payout / total_investment if total_investment > 0 else 0,
                'profit': total_payout - total_investment,
            }
        else:
            results['total'] = {
                'bets': 0, 'hits': 0, 'hit_rate': 0,
                'investment': 0, 'payout': 0, 'roi': 0, 'profit': 0,
            }

        # 2025年の月別サマリーを追加（--full時も表示するため）
        results['monthly_2025'] = analyze_monthly(cursor, 2025, test_conditions)
    else:
        # 詳細テスト（特定年）
        results['year'] = year
        year_start = f"{year}-01-01"
        year_end = f"{year + 1}-01-01"

        # 月別サマリー
        results['monthly'] = analyze_monthly(cursor, year, test_conditions)

        # 条件別パフォーマンス
        total_bets = 0
        total_hits = 0
        total_investment = 0
        total_payout = 0

        for cond in test_conditions:
            cond_result = analyze_condition(cursor, cond, year_start, year_end)
            # 月別内訳を追加
            cond_result['monthly'] = analyze_condition_monthly(cursor, cond, year)
            results['conditions'].append(cond_result)

            total_bets += cond_result['bets']
            total_hits += cond_result['hits']
            total_investment += cond_result['investment']
            total_payout += cond_result['payout']

        # 年間合計
        if total_bets > 0:
            results['total'] = {
                'bets': total_bets,
                'hits': total_hits,
                'hit_rate': 100.0 * total_hits / total_bets,
                'investment': total_investment,
                'payout': total_payout,
                'roi': 100.0 * total_payout / total_investment if total_investment > 0 else 0,
                'profit': total_payout - total_investment,
            }
        else:
            results['total'] = {
                'bets': 0, 'hits': 0, 'hit_rate': 0,
                'investment': 0, 'payout': 0, 'roi': 0, 'profit': 0,
            }

    conn.close()
    return results


def print_results(data: Dict):
    """結果を表示"""
    print("=" * 90)
    if data.get('rj_condition'):
        print(f"RJ条件テスト結果: {data['rj_condition']}")
    else:
        print("標準化バックテスト結果")
    print("=" * 90)
    print(f"実行日時: {data['date'][:19]}")

    # 買い目方式の説明
    if data.get('rj_condition'):
        # RJ条件テスト時は、テスト中の条件の情報のみ表示
        test_cond = data['conditions'][0] if data['conditions'] else {}
        print(f"テスト条件: {test_cond.get('description', 'N/A')}")
    else:
        pattern_h_count = sum(1 for c in CONDITIONS if c.get('use_pattern_h', True))
        single_bet_count = len(CONDITIONS) - pattern_h_count
        print(f"買い目方式: パターンH（3点買い400円）×{pattern_h_count}条件 / 1点買い（100円）×{single_bet_count}条件")
    print()

    if data['test_type'] == 'full' or data['test_type'].startswith('rj_'):
        if 'year_start' in data:
            print(f"対象期間: {data['year_start']}年〜{data['year_end']}年（6年間）")
        else:
            print(f"対象期間: 2020年〜2025年（6年間）")
    else:
        print(f"対象期間: {data['year']}年")

    print()

    # 全体サマリー
    total = data['total']
    print("[全体サマリー]")
    print("-" * 60)
    print(f"  購入レース数: {total['bets']:,}件")
    print(f"  的中数: {total['hits']:,}件")
    print(f"  的中率: {total['hit_rate']:.2f}%")
    print(f"  総投資額: {total['investment']:,}円")
    print(f"  総払戻額: {total['payout']:,.0f}円")
    print(f"  ROI: {total['roi']:.1f}%")
    print(f"  収支: {total['profit']:+,.0f}円")
    print()

    # 条件別パフォーマンス
    print("[条件別パフォーマンス]")
    print("-" * 98)
    print(f"{'条件':<25} {'方式':<4} {'件数':>6} {'的中':>4} {'的中率':>7} {'ROI':>8} {'収支':>14}")
    print("-" * 98)

    # CONDITIONS から use_pattern_h を取得
    cond_pattern_map = {c['name']: 'P.H' if c.get('use_pattern_h', True) else '1点' for c in CONDITIONS}
    for cond in data['conditions']:
        pattern_type = cond_pattern_map.get(cond['name'], '1点')
        print(f"{cond['name']:<25} {pattern_type:<4} {cond['bets']:>6} {cond['hits']:>4} {cond['hit_rate']:>6.1f}% {cond['roi']:>7.1f}% {cond['profit']:>+14,.0f}")

    print("-" * 98)
    print(f"{'合計':<25} {'-':<4} {total['bets']:>6} {total['hits']:>4} {total['hit_rate']:>6.1f}% {total['roi']:>7.1f}% {total['profit']:>+14,.0f}")
    print()

    # 年度別サマリー（full test時）
    if 'yearly' in data and data['yearly']:
        print("[年度別パフォーマンス]")
        print("-" * 70)
        print(f"{'年度':>6} {'件数':>8} {'的中':>5} {'的中率':>8} {'ROI':>9} {'収支':>14} {'判定'}")
        print("-" * 70)

        black_years = 0
        for y in data['yearly']:
            status = "○黒字" if y['profit'] > 0 else "×赤字"
            if y['profit'] > 0:
                black_years += 1
            print(f"{y['year']:>6} {y['bets']:>8} {y['hits']:>5} {y['hit_rate']:>7.1f}% {y['roi']:>8.1f}% {y['profit']:>+14,.0f} {status}")

        print("-" * 70)
        print(f"黒字年数: {black_years}/{len(data['yearly'])}年")
        print()

    # 2025年月別サマリー（full test時も表示）
    if 'monthly_2025' in data and data['monthly_2025']:
        print("[2025年 月別パフォーマンス]")
        print("-" * 70)
        print(f"{'月':>4} {'件数':>8} {'的中':>5} {'的中率':>8} {'ROI':>9} {'収支':>14} {'判定'}")
        print("-" * 70)

        black_months = 0
        for m in data['monthly_2025']:
            if m['bets'] > 0:
                status = "○黒字" if m['profit'] > 0 else "×赤字"
                if m['profit'] > 0:
                    black_months += 1
                print(f"{m['month']:>3}月 {m['bets']:>8} {m['hits']:>5} {m['hit_rate']:>7.1f}% {m['roi']:>8.1f}% {m['profit']:>+14,.0f} {status}")

        print("-" * 70)
        print(f"黒字月数: {black_months}/12月")
        print()

    # 月別サマリー（detail test時）
    if 'monthly' in data and data['monthly']:
        print("[月別パフォーマンス]")
        print("-" * 70)
        print(f"{'月':>4} {'件数':>8} {'的中':>5} {'的中率':>8} {'ROI':>9} {'収支':>14} {'判定'}")
        print("-" * 70)

        black_months = 0
        for m in data['monthly']:
            if m['bets'] > 0:
                status = "○黒字" if m['profit'] > 0 else "×赤字"
                if m['profit'] > 0:
                    black_months += 1
                print(f"{m['month']:>3}月 {m['bets']:>8} {m['hits']:>5} {m['hit_rate']:>7.1f}% {m['roi']:>8.1f}% {m['profit']:>+14,.0f} {status}")

        print("-" * 70)
        print(f"黒字月数: {black_months}/12月")
        print()

    # 条件別の年度/月別詳細
    print("[条件別詳細]")
    print("=" * 90)

    for cond in data['conditions']:
        print(f"\n>>> {cond['name']} - {cond['description']}")
        print(f"    6年間: {cond['bets']}件, ROI {cond['roi']:.1f}%, 収支 {cond['profit']:+,.0f}円")

        if 'yearly' in cond and cond['yearly']:
            yearly_str = []
            for y in cond['yearly']:
                if y['bets'] > 0:
                    mark = "○" if y['profit'] > 0 else "×"
                    yearly_str.append(f"{y['year']}: {mark}{y['profit']:+,.0f}円")
            print(f"    年度別: {', '.join(yearly_str)}")

        if 'monthly' in cond and cond['monthly']:
            monthly_str = []
            for m in cond['monthly']:
                if m['bets'] > 0:
                    mark = "○" if m['profit'] > 0 else "×"
                    monthly_str.append(f"{m['month']}月: {mark}{m['profit']:+,.0f}")
            if monthly_str:
                # 2行に分けて表示
                mid = len(monthly_str) // 2
                print(f"    月別: {', '.join(monthly_str[:mid])}")
                print(f"          {', '.join(monthly_str[mid:])}")


def save_baseline(data: Dict):
    """ベースラインを保存"""
    baseline_path = os.path.join(PROJECT_ROOT, 'data', 'standardized_backtest_baseline.json')
    os.makedirs(os.path.dirname(baseline_path), exist_ok=True)
    with open(baseline_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\nベースラインを保存しました: {baseline_path}")


def save_results_to_json(data: Dict, output_path: str):
    """Tier 2の結果をJSON保存（Tier 3での比較用）

    Args:
        data: バックテスト結果
        output_path: 出力JSONファイルパス
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n✅ Tier 2結果を保存しました: {output_path}")
    print(f"   Tier 3検証時に使用してください:")
    print(f"   python scripts/validation/verify_prediction_consistency.py \\")
    print(f"       --start 2020-01-01 --end 2025-12-31 \\")
    print(f"       --tier2-results {output_path}")


def compare_with_baseline(current: Dict):
    """ベースラインと比較"""
    baseline_path = os.path.join(PROJECT_ROOT, 'data', 'standardized_backtest_baseline.json')
    if not os.path.exists(baseline_path):
        print("\nベースラインが見つかりません。--save-baseline で保存してください。")
        return

    with open(baseline_path, 'r', encoding='utf-8') as f:
        baseline = json.load(f)

    print()
    print("=" * 80)
    print("ベースラインとの比較")
    print("=" * 80)
    print()
    print(f"ベースライン日時: {baseline['date'][:19]}")
    print(f"現在: {current['date'][:19]}")
    print()

    print(f"{'指標':<15} {'ベースライン':>15} {'現在':>15} {'差分':>15}")
    print("-" * 65)

    b_total = baseline['total']
    c_total = current['total']

    print(f"{'件数':<15} {b_total['bets']:>15,} {c_total['bets']:>15,} {c_total['bets'] - b_total['bets']:>+15,}")
    print(f"{'的中数':<15} {b_total['hits']:>15,} {c_total['hits']:>15,} {c_total['hits'] - b_total['hits']:>+15,}")
    print(f"{'的中率':<15} {b_total['hit_rate']:>14.2f}% {c_total['hit_rate']:>14.2f}% {c_total['hit_rate'] - b_total['hit_rate']:>+14.2f}pt")
    print(f"{'ROI':<15} {b_total['roi']:>14.1f}% {c_total['roi']:>14.1f}% {c_total['roi'] - b_total['roi']:>+14.1f}pt")
    print(f"{'収支':<15} {b_total['profit']:>+14,.0f} {c_total['profit']:>+14,.0f} {c_total['profit'] - b_total['profit']:>+14,.0f}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description='標準化バックテストスクリプト（3層アーキテクチャ対応）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
使用例:
  python scripts/backtest/standardized_backtest.py           # 2025年詳細テスト
  python scripts/backtest/standardized_backtest.py --full    # 6年間全体テスト
  python scripts/backtest/standardized_backtest.py --year 2024  # 2024年テスト
  python scripts/backtest/standardized_backtest.py --save-baseline  # ベースライン保存
  python scripts/backtest/standardized_backtest.py --compare        # ベースライン比較

  # RJ条件テスト（データ補完後の再検証用）
  python scripts/backtest/standardized_backtest.py --rj-condition RJ-3 --full
  python scripts/backtest/standardized_backtest.py --rj-condition RJ-4-A1 --full
  python scripts/backtest/standardized_backtest.py --rj-condition RJ-5 --full
        '''
    )
    parser.add_argument('--year', type=int, default=2025, help='対象年度（デフォルト: 2025）')
    parser.add_argument('--full', action='store_true', help='6年間全体テストを実行')
    parser.add_argument('--rj-condition', type=str, help='RJ条件ID（例: RJ-3, RJ-4-A1, RJ-5）')
    parser.add_argument('--save-baseline', action='store_true', help='結果をベースラインとして保存')
    parser.add_argument('--compare', action='store_true', help='ベースラインと比較')
    parser.add_argument('--save-json', type=str, help='結果をJSON保存（Tier 3用）')
    args = parser.parse_args()

    print("バックテストを実行中...")
    data = run_backtest(args.year, args.full, args.rj_condition)
    print_results(data)

    if args.save_baseline:
        save_baseline(data)

    if args.compare:
        compare_with_baseline(data)

    if args.save_json:
        save_results_to_json(data, args.save_json)


if __name__ == '__main__':
    main()
