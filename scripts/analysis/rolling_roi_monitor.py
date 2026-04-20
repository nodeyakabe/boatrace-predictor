#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
崩壊検知モニター（Rolling ROI Monitor）

各条件の直近N件ROIを計算し、崩壊の早期シグナルを検出する。

【アラートルール】
  WARNING : 直近100件ROI < 80% OR 直近50件ROI < 80%
  STOP    : 直近100件ROI < 80% AND 直近50件ROI < 80%（両方割れ）

【使用方法】
  # 全条件を監視（デフォルト 2020-現在）
  python scripts/analysis/rolling_roi_monitor.py

  # 2026年OOSのみ監視
  python scripts/analysis/rolling_roi_monitor.py --start 2026-01-01

  # 特定条件のみ詳細表示
  python scripts/analysis/rolling_roi_monitor.py --condition C_P132_200_300

  # 直近N件を変更（デフォルト: 100/50）
  python scripts/analysis/rolling_roi_monitor.py --window1 100 --window2 50
"""
import math
import sqlite3
import sys
import os
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from config.bet_conditions import STANDARD_BET_CONDITIONS
from scripts.backtest.backtest_helpers import get_race_ids_for_condition

# ========== 定数 ==========
WARN_THRESHOLD = 80.0    # ROI% 警告閾値（片方割れ → WARNING）
STOP_THRESHOLD = 80.0    # ROI% 停止閾値（両方割れ → STOP）
DEFAULT_WINDOW1 = 100    # 長期ウィンドウ
DEFAULT_WINDOW2 = 50     # 短期ウィンドウ
MIN_SAMPLE_WARN = 20     # これ未満は「サンプル不足」として警告対象外

# ========== 主要条件（特別表示対象） ==========
PRIORITY_CONDITIONS = {'C_P132_200_300', 'D_P143_200_300'}


def get_per_race_results(
    cursor: sqlite3.Cursor,
    cond: Dict,
    start_date: str,
    end_date: str
) -> List[Tuple]:
    """
    条件に該当する全レースの個別結果を日付順で取得する。

    Returns:
        list of (race_date, race_id, investment, payout, is_hit)
    """
    race_ids = get_race_ids_for_condition(cursor, cond, start_date, end_date)
    if not race_ids:
        return []

    use_pattern_h   = cond.get('use_pattern_h', False)
    use_pattern_p143 = cond.get('use_pattern_p143', False)
    use_pattern_p132 = cond.get('use_pattern_p132', False)
    use_pattern_p142 = cond.get('use_pattern_p142', False)
    use_pattern_p124 = cond.get('use_pattern_p124', False)

    ods_min = cond['odds_min']
    ods_max = cond['odds_max']

    BATCH_SIZE = 900
    results = []

    for batch_start in range(0, len(race_ids), BATCH_SIZE):
        batch = list(race_ids)[batch_start:batch_start + BATCH_SIZE]
        placeholders = ','.join(['?'] * len(batch))

        # SQLiteの制約: 同一SELECT内でカラムエイリアスを参照不可 → CTE（WITH句）で2段階計算
        if use_pattern_p143:
            score_clause = ""
            if cond.get('score_min') is not None:
                score_clause += f" AND rp1.total_score >= {cond['score_min']}"
            if cond.get('score_max') is not None:
                score_clause += f" AND rp1.total_score < {cond['score_max']}"
            query = f"""
            WITH rb AS (
                SELECT r.id, r.race_date,
                    rp1.pit_number as p1, rp3.pit_number as p3, rp4.pit_number as p4,
                    COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id=r.id
                        AND o.combination=CAST(rp1.pit_number AS TEXT)||'-'||CAST(rp4.pit_number AS TEXT)||'-'||CAST(rp3.pit_number AS TEXT)),0) as odds_143,
                    (SELECT pit_number FROM results WHERE race_id=r.id AND rank='1') as actual_1st,
                    (SELECT pit_number FROM results WHERE race_id=r.id AND rank='2') as actual_2nd,
                    (SELECT pit_number FROM results WHERE race_id=r.id AND rank='3') as actual_3rd
                FROM races r
                JOIN race_predictions rp1 ON r.id=rp1.race_id AND rp1.prediction_type='before' AND rp1.rank_prediction=1 {score_clause}
                JOIN race_predictions rp3 ON r.id=rp3.race_id AND rp3.prediction_type='before' AND rp3.rank_prediction=3
                JOIN race_predictions rp4 ON r.id=rp4.race_id AND rp4.prediction_type='before' AND rp4.rank_prediction=4
                WHERE r.id IN ({placeholders})
            )
            SELECT race_date, id,
                100 as investment,
                CASE WHEN actual_1st=p1 AND actual_2nd=p4 AND actual_3rd=p3 THEN odds_143*100 ELSE 0 END as payout,
                CASE WHEN actual_1st=p1 AND actual_2nd=p4 AND actual_3rd=p3 THEN 1 ELSE 0 END as is_hit
            FROM rb
            WHERE odds_143 >= {ods_min} AND odds_143 < {ods_max}
            ORDER BY race_date, id
            """
        elif use_pattern_p132:
            score_clause = ""
            if cond.get('score_min') is not None:
                score_clause += f" AND rp1.total_score >= {cond['score_min']}"
            if cond.get('score_max') is not None:
                score_clause += f" AND rp1.total_score < {cond['score_max']}"
            query = f"""
            WITH rb AS (
                SELECT r.id, r.race_date,
                    rp1.pit_number as p1, rp2.pit_number as p2, rp3.pit_number as p3,
                    COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id=r.id
                        AND o.combination=CAST(rp1.pit_number AS TEXT)||'-'||CAST(rp3.pit_number AS TEXT)||'-'||CAST(rp2.pit_number AS TEXT)),0) as odds_132,
                    (SELECT pit_number FROM results WHERE race_id=r.id AND rank='1') as actual_1st,
                    (SELECT pit_number FROM results WHERE race_id=r.id AND rank='2') as actual_2nd,
                    (SELECT pit_number FROM results WHERE race_id=r.id AND rank='3') as actual_3rd
                FROM races r
                JOIN race_predictions rp1 ON r.id=rp1.race_id AND rp1.prediction_type='before' AND rp1.rank_prediction=1 {score_clause}
                JOIN race_predictions rp2 ON r.id=rp2.race_id AND rp2.prediction_type='before' AND rp2.rank_prediction=2
                JOIN race_predictions rp3 ON r.id=rp3.race_id AND rp3.prediction_type='before' AND rp3.rank_prediction=3
                WHERE r.id IN ({placeholders})
            )
            SELECT race_date, id,
                100 as investment,
                CASE WHEN actual_1st=p1 AND actual_2nd=p3 AND actual_3rd=p2 THEN odds_132*100 ELSE 0 END as payout,
                CASE WHEN actual_1st=p1 AND actual_2nd=p3 AND actual_3rd=p2 THEN 1 ELSE 0 END as is_hit
            FROM rb
            WHERE odds_132 >= {ods_min} AND odds_132 < {ods_max}
            ORDER BY race_date, id
            """
        elif use_pattern_p142:
            score_clause = ""
            if cond.get('score_min') is not None:
                score_clause += f" AND rp1.total_score >= {cond['score_min']}"
            if cond.get('score_max') is not None:
                score_clause += f" AND rp1.total_score < {cond['score_max']}"
            query = f"""
            WITH rb AS (
                SELECT r.id, r.race_date,
                    rp1.pit_number as p1, rp2.pit_number as p2, rp4.pit_number as p4,
                    COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id=r.id
                        AND o.combination=CAST(rp1.pit_number AS TEXT)||'-'||CAST(rp4.pit_number AS TEXT)||'-'||CAST(rp2.pit_number AS TEXT)),0) as odds_142,
                    (SELECT pit_number FROM results WHERE race_id=r.id AND rank='1') as actual_1st,
                    (SELECT pit_number FROM results WHERE race_id=r.id AND rank='2') as actual_2nd,
                    (SELECT pit_number FROM results WHERE race_id=r.id AND rank='3') as actual_3rd
                FROM races r
                JOIN race_predictions rp1 ON r.id=rp1.race_id AND rp1.prediction_type='before' AND rp1.rank_prediction=1 {score_clause}
                JOIN race_predictions rp2 ON r.id=rp2.race_id AND rp2.prediction_type='before' AND rp2.rank_prediction=2
                JOIN race_predictions rp4 ON r.id=rp4.race_id AND rp4.prediction_type='before' AND rp4.rank_prediction=4
                WHERE r.id IN ({placeholders})
            )
            SELECT race_date, id,
                100 as investment,
                CASE WHEN actual_1st=p1 AND actual_2nd=p4 AND actual_3rd=p2 THEN odds_142*100 ELSE 0 END as payout,
                CASE WHEN actual_1st=p1 AND actual_2nd=p4 AND actual_3rd=p2 THEN 1 ELSE 0 END as is_hit
            FROM rb
            WHERE odds_142 >= {ods_min} AND odds_142 < {ods_max}
            ORDER BY race_date, id
            """
        elif use_pattern_p124:
            score_clause = ""
            if cond.get('score_min') is not None:
                score_clause += f" AND rp1.total_score >= {cond['score_min']}"
            if cond.get('score_max') is not None:
                score_clause += f" AND rp1.total_score < {cond['score_max']}"
            query = f"""
            WITH rb AS (
                SELECT r.id, r.race_date,
                    rp1.pit_number as p1, rp2.pit_number as p2, rp4.pit_number as p4,
                    COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id=r.id
                        AND o.combination=CAST(rp1.pit_number AS TEXT)||'-'||CAST(rp2.pit_number AS TEXT)||'-'||CAST(rp4.pit_number AS TEXT)),0) as odds_124,
                    (SELECT pit_number FROM results WHERE race_id=r.id AND rank='1') as actual_1st,
                    (SELECT pit_number FROM results WHERE race_id=r.id AND rank='2') as actual_2nd,
                    (SELECT pit_number FROM results WHERE race_id=r.id AND rank='3') as actual_3rd
                FROM races r
                JOIN race_predictions rp1 ON r.id=rp1.race_id AND rp1.prediction_type='before' AND rp1.rank_prediction=1 {score_clause}
                JOIN race_predictions rp2 ON r.id=rp2.race_id AND rp2.prediction_type='before' AND rp2.rank_prediction=2
                JOIN race_predictions rp4 ON r.id=rp4.race_id AND rp4.prediction_type='before' AND rp4.rank_prediction=4
                WHERE r.id IN ({placeholders})
            )
            SELECT race_date, id,
                100 as investment,
                CASE WHEN actual_1st=p1 AND actual_2nd=p2 AND actual_3rd=p4 THEN odds_124*100 ELSE 0 END as payout,
                CASE WHEN actual_1st=p1 AND actual_2nd=p2 AND actual_3rd=p4 THEN 1 ELSE 0 END as is_hit
            FROM rb
            WHERE odds_124 >= {ods_min} AND odds_124 < {ods_max}
            ORDER BY race_date, id
            """
        elif use_pattern_h:
            exclude_p5 = cond.get('pattern_h_exclude_p5', False)
            query = f"""
            WITH rb AS (
                SELECT r.id, r.race_date,
                    rp1.pit_number as p1, rp2.pit_number as p2, rp3.pit_number as p3,
                    rp4.pit_number as p4, rp5.pit_number as p5,
                    COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id=r.id AND o.combination=CAST(rp1.pit_number AS TEXT)||'-'||CAST(rp2.pit_number AS TEXT)||'-'||CAST(rp3.pit_number AS TEXT)),0) as odds_123,
                    COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id=r.id AND o.combination=CAST(rp1.pit_number AS TEXT)||'-'||CAST(rp2.pit_number AS TEXT)||'-'||CAST(rp4.pit_number AS TEXT)),0) as odds_124,
                    COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id=r.id AND o.combination=CAST(rp1.pit_number AS TEXT)||'-'||CAST(rp2.pit_number AS TEXT)||'-'||CAST(rp5.pit_number AS TEXT)),0) as odds_125,
                    (SELECT pit_number FROM results WHERE race_id=r.id AND rank='1') as actual_1st,
                    (SELECT pit_number FROM results WHERE race_id=r.id AND rank='2') as actual_2nd,
                    (SELECT pit_number FROM results WHERE race_id=r.id AND rank='3') as actual_3rd
                FROM races r
                JOIN race_predictions rp1 ON r.id=rp1.race_id AND rp1.prediction_type='before' AND rp1.rank_prediction=1
                JOIN race_predictions rp2 ON r.id=rp2.race_id AND rp2.prediction_type='before' AND rp2.rank_prediction=2
                JOIN race_predictions rp3 ON r.id=rp3.race_id AND rp3.prediction_type='before' AND rp3.rank_prediction=3
                JOIN race_predictions rp4 ON r.id=rp4.race_id AND rp4.prediction_type='before' AND rp4.rank_prediction=4
                JOIN race_predictions rp5 ON r.id=rp5.race_id AND rp5.prediction_type='before' AND rp5.rank_prediction=5
                WHERE r.id IN ({placeholders})
            ),
            rp AS (
                SELECT id, race_date, p1, p2, p3, p4, p5,
                    odds_123, odds_124, odds_125, actual_1st, actual_2nd, actual_3rd,
                    CASE WHEN odds_123 >= {ods_min} AND odds_123 < {ods_max} THEN 200 ELSE 0 END as bet_123,
                    CASE WHEN odds_124 >= {ods_min} AND odds_124 < {ods_max} THEN 100 ELSE 0 END as bet_124,
                    {'0' if exclude_p5 else f'CASE WHEN odds_125 >= {ods_min} AND odds_125 < {ods_max} THEN 100 ELSE 0 END'} as bet_125,
                    CASE WHEN actual_1st=p1 AND actual_2nd=p2 AND actual_3rd=p3 AND odds_123 >= {ods_min} AND odds_123 < {ods_max} THEN odds_123*200 ELSE 0 END as pay_123,
                    CASE WHEN actual_1st=p1 AND actual_2nd=p2 AND actual_3rd=p4 AND odds_124 >= {ods_min} AND odds_124 < {ods_max} THEN odds_124*100 ELSE 0 END as pay_124,
                    {'0' if exclude_p5 else f'CASE WHEN actual_1st=p1 AND actual_2nd=p2 AND actual_3rd=p5 AND odds_125 >= {ods_min} AND odds_125 < {ods_max} THEN odds_125*100 ELSE 0 END'} as pay_125
                FROM rb
            )
            SELECT race_date, id,
                bet_123+bet_124+bet_125 as investment,
                pay_123+pay_124+pay_125 as payout,
                CASE WHEN pay_123>0 OR pay_124>0 OR pay_125>0 THEN 1 ELSE 0 END as is_hit
            FROM rp
            WHERE bet_123>0 OR bet_124>0 OR bet_125>0
            ORDER BY race_date, id
            """
        else:
            # デフォルト: 1点買い p1-p2-p3
            query = f"""
            WITH rb AS (
                SELECT r.id, r.race_date,
                    rp1.pit_number as p1, rp2.pit_number as p2, rp3.pit_number as p3,
                    COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id=r.id
                        AND o.combination=CAST(rp1.pit_number AS TEXT)||'-'||CAST(rp2.pit_number AS TEXT)||'-'||CAST(rp3.pit_number AS TEXT)),0) as odds_123,
                    (SELECT pit_number FROM results WHERE race_id=r.id AND rank='1') as actual_1st,
                    (SELECT pit_number FROM results WHERE race_id=r.id AND rank='2') as actual_2nd,
                    (SELECT pit_number FROM results WHERE race_id=r.id AND rank='3') as actual_3rd
                FROM races r
                JOIN race_predictions rp1 ON r.id=rp1.race_id AND rp1.prediction_type='before' AND rp1.rank_prediction=1
                JOIN race_predictions rp2 ON r.id=rp2.race_id AND rp2.prediction_type='before' AND rp2.rank_prediction=2
                JOIN race_predictions rp3 ON r.id=rp3.race_id AND rp3.prediction_type='before' AND rp3.rank_prediction=3
                WHERE r.id IN ({placeholders})
            )
            SELECT race_date, id,
                100 as investment,
                CASE WHEN actual_1st=p1 AND actual_2nd=p2 AND actual_3rd=p3 THEN odds_123*100 ELSE 0 END as payout,
                CASE WHEN actual_1st=p1 AND actual_2nd=p2 AND actual_3rd=p3 THEN 1 ELSE 0 END as is_hit
            FROM rb
            WHERE odds_123 >= {ods_min} AND odds_123 < {ods_max}
            ORDER BY race_date, id
            """

        cursor.execute(query, batch)
        rows = cursor.fetchall()
        results.extend(rows)

    # 日付順に再ソート（バッチ間の順序を保証）
    results.sort(key=lambda x: (x[0], x[1]))
    return results


def calc_window_roi(results: List[Tuple], window: int) -> Tuple[Optional[float], int, int]:
    """
    直近 window 件の ROI を計算する。

    Returns:
        (roi_percent, n_bets, n_hits)  ※n_bets < window なら全件使用
    """
    recent = results[-window:] if len(results) >= window else results
    if not recent:
        return None, 0, 0
    total_inv  = sum(r[2] for r in recent)
    total_pay  = sum(r[3] for r in recent)
    total_hits = sum(r[4] for r in recent)
    if total_inv == 0:
        return None, 0, 0
    roi = 100.0 * total_pay / total_inv
    return roi, len(recent), total_hits


def assess_status(roi_long: Optional[float], n_long: int,
                  roi_short: Optional[float], n_short: int,
                  window1: int, window2: int) -> Tuple[str, str]:
    """
    アラートステータスと理由を判定する。

    Returns:
        (status, reason)
        status: 'STOP' | 'WARNING' | 'OK' | 'LOW_SAMPLE'
    """
    # サンプル不足
    if n_short < MIN_SAMPLE_WARN:
        return 'LOW_SAMPLE', f'直近{n_short}件（{MIN_SAMPLE_WARN}件未満のため判定保留）'

    roi_l_ok = roi_long  is None or roi_long  >= WARN_THRESHOLD
    roi_s_ok = roi_short is None or roi_short >= WARN_THRESHOLD

    if not roi_l_ok and not roi_s_ok:
        return 'STOP', (
            f'直近{n_long}件ROI {roi_long:.1f}% < {WARN_THRESHOLD}% '
            f'AND 直近{n_short}件ROI {roi_short:.1f}% < {WARN_THRESHOLD}%'
        )
    if not roi_l_ok:
        return 'WARNING', f'直近{n_long}件ROI {roi_long:.1f}% < {WARN_THRESHOLD}%'
    if not roi_s_ok:
        return 'WARNING', f'直近{n_short}件ROI {roi_short:.1f}% < {WARN_THRESHOLD}%'

    return 'OK', ''


def format_roi(roi: Optional[float], n: int, window: int) -> str:
    if roi is None or n == 0:
        return f'N/A (0件)'
    label = f'{n}件' if n < window else f'{n}件'
    return f'{roi:6.1f}% ({label})'


def run_monitor(
    start_date: str = '2020-01-01',
    end_date: str = '2099-12-31',
    target_condition: Optional[str] = None,
    window1: int = DEFAULT_WINDOW1,
    window2: int = DEFAULT_WINDOW2,
    verbose: bool = False
):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    conditions = STANDARD_BET_CONDITIONS
    if target_condition:
        conditions = [c for c in conditions if c['id'] == target_condition]
        if not conditions:
            print(f"[ERROR] 条件 '{target_condition}' が見つかりません")
            conn.close()
            return

    sorted_conds = sorted(conditions, key=lambda x: x.get('priority', 999))

    print("=" * 80)
    print(f"崩壊検知モニター  |  期間: {start_date} 〜 {end_date}")
    print(f"ウィンドウ: 長期{window1}件 / 短期{window2}件  |  閾値: {WARN_THRESHOLD}%")
    print("=" * 80)

    STATUS_ICONS = {
        'OK':         '[OK]      ',
        'WARNING':    '[WARNING] ',
        'STOP':       '[STOP]    ',
        'LOW_SAMPLE': '[低サンプル]',
    }

    all_results_flat = []  # ポートフォリオ全体用
    condition_summaries = []

    for cond in sorted_conds:
        cid = cond['id']
        is_priority = cid in PRIORITY_CONDITIONS

        results = get_per_race_results(cursor, cond, start_date, end_date)

        roi_long,  n_long,  hits_long  = calc_window_roi(results, window1)
        roi_short, n_short, hits_short = calc_window_roi(results, window2)
        total_bets = len(results)

        status, reason = assess_status(roi_long, n_long, roi_short, n_short, window1, window2)
        icon = STATUS_ICONS[status]

        # 全体収支（全期間）
        total_inv  = sum(r[2] for r in results)
        total_pay  = sum(r[3] for r in results)
        total_hits = sum(r[4] for r in results)
        all_roi = 100.0 * total_pay / total_inv if total_inv > 0 else 0
        all_profit = total_pay - total_inv

        prefix = "★ " if is_priority else "  "
        print(f"\n{prefix}{cid}  {icon}")
        print(f"  全期間: {total_bets}件 / ROI {all_roi:.1f}% / 収支{all_profit:+,}円 / 的中{total_hits}件")
        print(f"  直近{window1}件: {format_roi(roi_long,  n_long,  window1)}")
        print(f"  直近{window2}件: {format_roi(roi_short, n_short, window2)}")
        if reason:
            print(f"  >> 理由: {reason}")

        # STOP/WARNING時: 統計的文脈を表示（誤検知か本物の崩壊かの判断材料）
        if status in ('STOP', 'WARNING') and total_bets > 0 and total_hits > 0:
            hit_rate = total_hits / total_bets
            print(f"  IS的中率: {hit_rate*100:.2f}% ({total_hits}的中/{total_bets}件)")
            for (n_w, roi_w, label_w) in [
                (n_long,  roi_long,  f"長期{window1}"),
                (n_short, roi_short, f"短期{window2}"),
            ]:
                if roi_w is not None and roi_w < WARN_THRESHOLD and n_w > 0:
                    prob_zero = (1.0 - hit_rate) ** n_w * 100.0
                    n_sig = math.ceil(math.log(0.05) / math.log(1.0 - hit_rate))
                    remaining = max(0, n_sig - n_w)
                    if prob_zero >= 30:
                        interp = "誤検知の可能性: 高"
                    elif prob_zero >= 10:
                        interp = "誤検知の可能性: 中"
                    else:
                        interp = "誤検知の可能性: 低"
                    print(f"  [統計 {label_w}] 正常でも{prob_zero:.0f}%で発生 ({interp}) | 5%有意ラインまで残り{remaining}件")

        # 詳細モード: 時系列の的中推移を表示
        if (verbose or is_priority) and results:
            last_date = results[-1][0]
            first_date = results[0][0]
            # 年度別内訳
            year_stats = {}
            for (rd, _, inv, pay, hit) in results:
                yr = rd[:4]
                if yr not in year_stats:
                    year_stats[yr] = [0, 0, 0]
                year_stats[yr][0] += 1
                year_stats[yr][1] += inv
                year_stats[yr][2] += pay
            yr_parts = []
            for yr in sorted(year_stats):
                nb, ni, np_ = year_stats[yr]
                yr_roi = 100.0 * np_ / ni if ni > 0 else 0
                yr_profit = np_ - ni
                yr_parts.append(f"{yr}:{nb}件/{yr_roi:.0f}%/{yr_profit:+,}")
            print(f"  年度別: {' | '.join(yr_parts)}")
            print(f"  期間: {first_date} 〜 {last_date}")

        all_results_flat.extend(results)
        condition_summaries.append({
            'id': cid, 'status': status, 'total_bets': total_bets,
            'roi_long': roi_long, 'n_long': n_long,
            'roi_short': roi_short, 'n_short': n_short,
        })

    # ========== ポートフォリオ全体 ==========
    # 注: ユニーク重複除外はここでは行わない（条件別の崩壊検知が目的）
    print("\n" + "=" * 80)
    print("【ポートフォリオ全体（重複あり・参考値）】")
    all_results_flat.sort(key=lambda x: (x[0], x[1]))
    # 重複レースを除去（最初に割り当てた条件のみカウント）
    seen_race_ids = set()
    unique_results = []
    for row in all_results_flat:
        if row[1] not in seen_race_ids:
            seen_race_ids.add(row[1])
            unique_results.append(row)

    roi_pf_long,  n_pf_long,  hits_pf_long  = calc_window_roi(unique_results, window1)
    roi_pf_short, n_pf_short, hits_pf_short = calc_window_roi(unique_results, window2)
    total_pf_inv  = sum(r[2] for r in unique_results)
    total_pf_pay  = sum(r[3] for r in unique_results)
    total_pf_hits = sum(r[4] for r in unique_results)
    pf_roi = 100.0 * total_pf_pay / total_pf_inv if total_pf_inv > 0 else 0
    pf_profit = total_pf_pay - total_pf_inv

    print(f"  全期間: {len(unique_results)}件 / ROI {pf_roi:.1f}% / 収支{pf_profit:+,}円 / 的中{total_pf_hits}件")
    print(f"  直近{window1}件: {format_roi(roi_pf_long,  n_pf_long,  window1)}")
    print(f"  直近{window2}件: {format_roi(roi_pf_short, n_pf_short, window2)}")

    pf_status, pf_reason = assess_status(
        roi_pf_long, n_pf_long, roi_pf_short, n_pf_short, window1, window2
    )
    pf_icon = STATUS_ICONS[pf_status]
    print(f"  ポートフォリオ判定: {pf_icon}")
    if pf_reason:
        print(f"  >> 理由: {pf_reason}")

    # ========== サマリー ==========
    print("\n" + "=" * 80)
    print("【アラートサマリー】")
    stops    = [s for s in condition_summaries if s['status'] == 'STOP']
    warnings = [s for s in condition_summaries if s['status'] == 'WARNING']
    ok_conds = [s for s in condition_summaries if s['status'] == 'OK']
    low_samp = [s for s in condition_summaries if s['status'] == 'LOW_SAMPLE']

    if stops:
        print(f"  [STOP]({len(stops)}件): {', '.join(s['id'] for s in stops)}")
        print(f"     -> 購入停止を検討。2-3ヶ月のウォッチ継続推奨")
    if warnings:
        print(f"  [WARNING]({len(warnings)}件): {', '.join(s['id'] for s in warnings)}")
        print(f"     -> 月次モニタリング強化。停止は保留")
    if ok_conds:
        print(f"  [OK]({len(ok_conds)}件): {', '.join(s['id'] for s in ok_conds)}")
    if low_samp:
        print(f"  [低サンプル]({len(low_samp)}件): {', '.join(s['id'] for s in low_samp)}")
        print(f"     -> {MIN_SAMPLE_WARN}件未満のため判定保留。年次退出基準を適用")

    print("\n【停止・再開フロー】")
    print(f"  STOP発生時: 購入停止 → 2ヶ月後に全件ROIを再確認")
    print(f"  再開基準  : 直近{window2}件ROI >= {WARN_THRESHOLD}% に回復した場合")
    print(f"  廃止基準  : 年間100件以上→直近2年連続ROI<100% / 100件未満→3年累計ROI<100%")
    print()

    conn.close()


def main():
    parser = argparse.ArgumentParser(description='崩壊検知モニター（Rolling ROI Monitor）')
    parser.add_argument('--start', default='2020-01-01', help='開始日 YYYY-MM-DD')
    parser.add_argument('--end',   default='2099-12-31', help='終了日 YYYY-MM-DD')
    parser.add_argument('--condition', default=None, help='特定条件IDのみ表示')
    parser.add_argument('--window1', type=int, default=DEFAULT_WINDOW1, help=f'長期ウィンドウ（デフォルト{DEFAULT_WINDOW1}）')
    parser.add_argument('--window2', type=int, default=DEFAULT_WINDOW2, help=f'短期ウィンドウ（デフォルト{DEFAULT_WINDOW2}）')
    parser.add_argument('--verbose', action='store_true', help='詳細表示（年度別内訳等）')
    args = parser.parse_args()

    run_monitor(
        start_date=args.start,
        end_date=args.end,
        target_condition=args.condition,
        window1=args.window1,
        window2=args.window2,
        verbose=args.verbose,
    )


if __name__ == '__main__':
    main()
