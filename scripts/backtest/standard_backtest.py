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

# ============================================================
# 購入条件定義（bet_target_evaluator.py と完全同期）
# ============================================================
# 変更時は bet_target_evaluator.py も合わせて変更すること
# 参照: src/betting/bet_target_evaluator.py

CONDITIONS = [
    # ----------------------------------------------------------------
    # A条件（2026-01-07改善版）
    # ----------------------------------------------------------------
    # 【2026-01-07改善】A×A1×10-12 + 会場フィルター
    # 改善前: 6年間ROI 98.3%, -2,000円（赤字）
    # 改善後: 6年間ROI 103.5%, +1,150円（黒字）
    {
        'name': 'A×A1×10-12+会場+逃げ率',
        'confidence': 'A',
        'c1_rank': ['A1'],
        'odds_min': 10,
        'odds_max': 12,
        # 黒字7会場: 三国,鳴門,芦屋,徳山,常滑,下関,びわこ
        'venue_filter': [10, 14, 21, 18, 8, 19, 12],
        'escape_rate_min': 0.70,  # 逃げ率70%以上（2026-01-09追加）
        'predicted_course': 1,  # 1コース予測時のみ適用
        'description': 'A×A1級×10-12倍+会場+逃げ率70%+（2026-01-09改善）',
        'use_pattern_h': False,  # 1点買い（低オッズ帯）
    },
    # 【2026-01-07廃止】A×A1×14-16
    # 廃止理由: 6年間ROI 84.3%, -7,700円（大幅赤字）
    # {
    #     'name': 'A×A1×14-16',
    #     'confidence': 'A',
    #     'c1_rank': ['A1'],
    #     'odds_min': 14,
    #     'odds_max': 16,
    #     'venue_filter': None,
    #     'description': 'A×A1級×14-16倍（廃止・6年間赤字）',
    #     'use_pattern_h': False,
    # },
    # 【2026-01-07廃止】A×B1×Motor40%+
    # 廃止理由: 6年間ROI 92.2%, -3,580円（赤字）、黒字年1/6年のみ
    # 採用経緯: 2025年単年でROI 196.6%だったが、6年間では不安定
    # 年度別: 2020:-1,210円, 2021:-370円, 2022:-620円, 2023:-1,110円, 2024:-640円, 2025:+370円
    # {
    #     'name': 'A×B1×Motor40%+',
    #     'confidence': 'A',
    #     'c1_rank': ['B1'],
    #     'odds_min': 10,
    #     'odds_max': 100,
    #     'venue_filter': None,
    #     'motor_min': 40,
    #     'description': 'A×B1級×モーター40%+（廃止・6年間赤字）',
    #     'use_pattern_h': False,
    # },
    # ----------------------------------------------------------------
    # B条件（高オッズ帯→パターンH推奨）
    # ----------------------------------------------------------------
    # 【2026-01-13更新】4月除外追加（6年間的中0回の完全赤字月）
    # 効果: 1180件→1082件(-8.3%), ROI 168.2%→183.6%(+15.4pt), 収支+15,300円
    {
        'name': 'B×50-100×冬+4月除外',
        'confidence': 'B',
        'c1_rank': ['A1', 'B1'],  # A2除外
        'odds_min': 50,
        'odds_max': 100,
        'venue_filter': None,
        'month_exclude': [12, 1, 2, 4],  # 冬季+4月除外（2026-01-13追加）
        'description': 'B×50-100倍×冬+4月除外（ROI 183.6%）',
        'use_pattern_h': True,  # パターンH（高オッズ帯）
    },
    # 【2026-01-13更新】会場を高ROI上位4会場に限定
    # 変更前: 10会場, ROI 130.7%, 4/6年黒字, 2025年-11,680円
    # 変更後: 4会場, ROI 196.7%, 6/6年黒字, 2025年+1,220円
    {
        'name': 'B×30-50×B1+4会場',
        'confidence': 'B',
        'c1_rank': ['B1'],
        'odds_min': 30,
        'odds_max': 50,
        # 津,三国,芦屋,浜名湖（高ROI上位4会場のみ）
        'venue_filter': [9, 10, 21, 6],
        'description': 'B×30-50倍×B1級×4会場（ROI 196.7%）',
        'use_pattern_h': True,  # パターンH（高オッズ帯）
    },
    # 【2026-01-13追加】B×10-30倍×穴源×黒字会場
    # バイアス指数分析で発見: 予想より上に来やすい選手（穴源）を狙う
    # 検証結果: 202件, ROI 168.8%, +13,890円, 4/6年黒字
    {
        'name': 'B×10-30×穴源×会場',
        'confidence': 'B',
        'c1_rank': ['A1', 'A2', 'B1'],
        'odds_min': 10,
        'odds_max': 30,
        # 黒字会場: 浜名湖,蒲郡,常滑,三国,丸亀,下関
        'venue_filter': [6, 7, 8, 10, 15, 19],
        'bias_max': -0.3,  # バイアス指数<-0.3（穴源選手）
        'description': 'B×10-30倍×穴源(bias<-0.3)×会場',
        'use_pattern_h': False,  # 1点買い（低オッズ帯）
    },
    # 【2026-01-26検証→不採用】B×10-30倍×穴源×会場+モーター2連対率
    # 連帯率分析で発見: モーター好調（2連対率40%以上）で改善
    # 検証結果: 27件, ROI 214.1%, +3,080円, 黒字3/6年（採用基準4/6年未達）
    # 不採用理由: サンプル数27件（過少）、元条件より収支-1,840円悪化
    # {
    #     'name': 'B×10-30×穴源×会場+Motor40%',
    #     'confidence': 'B',
    #     'c1_rank': ['A1', 'A2', 'B1'],
    #     'odds_min': 10,
    #     'odds_max': 30,
    #     'venue_filter': [6, 7, 8, 10, 15, 19],
    #     'bias_max': -0.3,
    #     'p1_motor_second_rate_min': 40,
    #     'description': 'B×10-30倍×穴源×会場+モーター2連対率40%+（不採用）',
    #     'use_pattern_h': False,
    # },
    # 【2026-01-13検証→不採用】B×A1×会場限定
    # 検証結果: 341件, ROI 65.9%, -11,620円（全年赤字）
    # 不採用理由: 分析時の計算ミス（1-2-3固定オッズで計算していた）
    # {
    #     'name': 'B×A1×会場限定',
    #     'confidence': 'B',
    #     'c1_rank': ['A1'],
    #     'odds_min': 10,
    #     'odds_max': 30,
    #     'venue_filter': [6, 8, 10, 12, 17, 19, 20, 23],
    #     'description': 'B×A1級×10-30倍×会場限定',
    #     'use_pattern_h': False,
    # },
    # 【2026-01-13検証→不採用】A×50倍+
    # 検証結果: 508件, ROI 58.4%, -21,130円
    # 不採用理由: 分析時の計算ミス（1-2-3固定オッズで計算していた）
    # {
    #     'name': 'A×50倍+',
    #     'confidence': 'A',
    #     'c1_rank': ['A1', 'A2', 'B1', 'B2'],
    #     'odds_min': 50,
    #     'odds_max': 999,
    #     'venue_filter': None,
    #     'description': 'A×50倍+',
    #     'use_pattern_h': False,
    # },
    # 【2026-01-13検証→不採用】A×(A1+A2)×50倍+
    # 検証結果: 376件, ROI 78.9%, -7,930円
    # 不採用理由: 分析時の計算ミス（1-2-3固定オッズで計算していた）
    # {
    #     'name': 'A×上位級×50倍+',
    #     'confidence': 'A',
    #     'c1_rank': ['A1', 'A2'],
    #     'odds_min': 50,
    #     'odds_max': 999,
    #     'venue_filter': None,
    #     'description': 'A×A1/A2級×50倍+',
    #     'use_pattern_h': False,
    # },
    # ----------------------------------------------------------------
    # C条件
    # ----------------------------------------------------------------
    # 【2026-01-13更新】唐津(23)を除外（唐津×C×B1×20-30条件と完全重複のため）
    {
        'name': 'C×20-30×B1+会場',
        'confidence': 'C',
        'c1_rank': ['B1'],
        'odds_min': 20,
        'odds_max': 30,
        # 徳山,多摩川,平和島,津,丸亀,常滑,大村,若松,宮島（唐津除外）
        'venue_filter': [18, 5, 4, 9, 15, 8, 24, 20, 17],
        'description': 'C×20-30倍×B1級（会場フィルター・唐津除外）',
        'use_pattern_h': False,  # 1点買い（低オッズ帯）
    },
    {
        'name': '鳴門×C×A2×30-80',
        'confidence': 'C',
        'c1_rank': ['A2'],
        'odds_min': 30,
        'odds_max': 80,
        'venue_filter': [14],  # 鳴門のみ
        'description': '鳴門×C×A2級×30-80倍（直近4年連続黒字）',
        'use_pattern_h': True,  # パターンH（高オッズ帯）
    },
    # 【2026-01-08追加】唐津×C×B1×20-30倍
    # 探索結果: ROI 175.5%, +9,290円, 直近4年連続黒字
    {
        'name': '唐津×C×B1×20-30',
        'confidence': 'C',
        'c1_rank': ['B1'],
        'odds_min': 20,
        'odds_max': 30,
        'venue_filter': [23],  # 唐津のみ
        'description': '唐津×C×B1級×20-30倍（直近4年連続黒字）',
        'use_pattern_h': False,  # 1点買い（低オッズ帯）
    },
    # 【2026-01-08追加】児島×C×B1×30-50倍
    # 探索結果: ROI 184.3%, +13,650円, 直近3年連続黒字
    {
        'name': '児島×C×B1×30-50',
        'confidence': 'C',
        'c1_rank': ['B1'],
        'odds_min': 30,
        'odds_max': 50,
        'venue_filter': [16],  # 児島のみ
        'description': '児島×C×B1級×30-50倍（直近3年連続黒字）',
        'use_pattern_h': True,  # パターンH（高オッズ帯）
    },
    # ----------------------------------------------------------------
    # D条件
    # ----------------------------------------------------------------
    {
        'name': 'D×40-50×B1×2連率20-30%',
        'confidence': 'D',
        'c1_rank': ['B1'],
        'odds_min': 40,
        'odds_max': 50,
        'venue_filter': None,
        'c1_second_rate_min': 20,
        'c1_second_rate_max': 30,
        'description': 'D×B1級×40-50倍×2連率20-30%',
        'use_pattern_h': False,  # 1点買い
    },
    # 【2026-01-13更新】A2級を除外（6年間ROI 23.8%, -19,800円の大赤字）
    # 変更前: 全級別, 493件, ROI 142.9%, 収支+50,530円, 5/6年黒字
    # 変更後: A2除外, 379件, ROI 176.6%, 収支+70,330円, 5/6年黒字
    {
        'name': 'D×5コース予測×A2除外',
        'confidence': 'D',
        'c1_rank': ['A1', 'B1', 'B2'],  # A2除外（2026-01-13）
        'odds_min': 10,
        'odds_max': 200,
        'venue_filter': None,
        'predicted_course': 5,
        'description': 'D×5コース予測×A2除外（ROI 176.6%）',
        'use_pattern_h': True,  # パターンH
    },
]

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

    # 各種フィルター条件
    venue_clause = ""
    if cond.get('venue_filter'):
        venue_clause = f"AND r.venue_code IN ({','.join(map(str, cond['venue_filter']))})"

    motor_clause = ""
    if cond.get('motor_min'):
        motor_clause = f"AND e1.motor_second_rate >= {cond['motor_min']}"

    race_exclude_clause = ""
    if cond.get('race_exclude'):
        race_exclude_clause = f"AND r.race_number NOT IN ({','.join(map(str, cond['race_exclude']))})"

    venue_exclude_clause = ""
    if cond.get('venue_exclude'):
        venue_exclude_clause = f"AND r.venue_code NOT IN ({','.join(map(str, cond['venue_exclude']))})"

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
    if cond.get('month_exclude'):
        months = ','.join(map(str, cond['month_exclude']))
        month_exclude_clause = f"AND CAST(strftime('%m', r.race_date) AS INTEGER) NOT IN ({months})"

    # 逃げ率フィルター（2026-01-09追加）
    escape_rate_join = ""
    escape_rate_clause = ""
    if cond.get('escape_rate_min') is not None:
        # 1コース予測の選手の逃げ率をチェック
        escape_rate_join = """
        LEFT JOIN entries e_pred ON r.id = e_pred.race_id AND e_pred.pit_number = rp1.pit_number
        LEFT JOIN player_escape_stats pes ON e_pred.racer_number = pes.player_id AND pes.stadium_id IS NULL
        """
        escape_rate_clause = f"AND pes.escape_rate >= {cond['escape_rate_min']} "

    # バイアス指数フィルター（2026-01-13追加：穴源選手抽出用）
    bias_join = ""
    bias_clause = ""
    if cond.get('bias_max') is not None:
        # 1着予測の選手のバイアス指数をチェック
        bias_join = """
        LEFT JOIN entries e_bias ON r.id = e_bias.race_id AND e_bias.pit_number = rp1.pit_number
        LEFT JOIN player_bias_stats pbs ON e_bias.racer_number = pbs.player_id AND pbs.stadium_id IS NULL
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

    if use_pattern_h:
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
            WHERE rp.rank_prediction = 1
            AND rp.confidence = '{cond["confidence"]}'
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
            {escape_rate_clause}
            {bias_clause}
            {motor_rate_clause}
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
            WHERE rp.rank_prediction = 1
            AND rp.confidence = '{cond["confidence"]}'
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
            {escape_rate_clause}
            {bias_clause}
            {motor_rate_clause}
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


def analyze_monthly(cursor, year: int) -> List[Dict]:
    """月別の成績を分析"""
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

        for cond in CONDITIONS:
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


def analyze_yearly(cursor, years: List[int]) -> List[Dict]:
    """年度別の成績を分析"""
    yearly_results = []

    for year in years:
        year_start = f"{year}-01-01"
        year_end = f"{year + 1}-01-01"

        total_bets = 0
        total_hits = 0
        total_investment = 0
        total_payout = 0

        for cond in CONDITIONS:
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


def run_backtest(year: int = 2025, full_test: bool = False) -> Dict:
    """バックテストを実行"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    results = {
        'test_type': 'full' if full_test else 'detail',
        'date': datetime.now().isoformat(),
        'pattern': PATTERN_H_CONFIG['name'],
        'pattern_description': PATTERN_H_CONFIG['description'],
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
        results['yearly'] = analyze_yearly(cursor, years)

        # 条件別パフォーマンス（6年間合計）
        year_start = f"{years[0]}-01-01"
        year_end = f"{years[-1] + 1}-01-01"

        total_bets = 0
        total_hits = 0
        total_investment = 0
        total_payout = 0

        for cond in CONDITIONS:
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
        results['monthly_2025'] = analyze_monthly(cursor, 2025)
    else:
        # 詳細テスト（特定年）
        results['year'] = year
        year_start = f"{year}-01-01"
        year_end = f"{year + 1}-01-01"

        # 月別サマリー
        results['monthly'] = analyze_monthly(cursor, year)

        # 条件別パフォーマンス
        total_bets = 0
        total_hits = 0
        total_investment = 0
        total_payout = 0

        for cond in CONDITIONS:
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
    print("標準化バックテスト結果")
    print("=" * 90)
    print(f"実行日時: {data['date'][:19]}")
    # 買い目方式の説明
    pattern_h_count = sum(1 for c in CONDITIONS if c.get('use_pattern_h', True))
    single_bet_count = len(CONDITIONS) - pattern_h_count
    print(f"買い目方式: パターンH（3点買い400円）×{pattern_h_count}条件 / 1点買い（100円）×{single_bet_count}条件")
    print()

    if data['test_type'] == 'full':
        print(f"対象期間: {data['year_start']}年〜{data['year_end']}年（6年間）")
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
        '''
    )
    parser.add_argument('--year', type=int, default=2025, help='対象年度（デフォルト: 2025）')
    parser.add_argument('--full', action='store_true', help='6年間全体テストを実行')
    parser.add_argument('--save-baseline', action='store_true', help='結果をベースラインとして保存')
    parser.add_argument('--compare', action='store_true', help='ベースラインと比較')
    args = parser.parse_args()

    print("バックテストを実行中...")
    data = run_backtest(args.year, args.full)
    print_results(data)

    if args.save_baseline:
        save_baseline(data)

    if args.compare:
        compare_with_baseline(data)


if __name__ == '__main__':
    main()
