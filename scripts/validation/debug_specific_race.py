#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
特定レースの詳細デバッグ

Tier 2で購入対象だがTier 3で除外されるレースを詳しく調査
"""
import sqlite3
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from config.bet_conditions import STANDARD_BET_CONDITIONS
from src.betting.evaluator_helpers import create_custom_evaluator
from src.betting.bet_target_evaluator import BetStatus


def get_race_data(cursor, race_id: str):
    """レースデータを取得"""
    cursor.execute("""
        SELECT id, venue_code, race_number, race_date, race_time
        FROM races WHERE id = ?
    """, (race_id,))

    row = cursor.fetchone()
    if not row:
        return None

    cursor.execute("SELECT wind_speed FROM race_conditions WHERE race_id = ?", (race_id,))
    conditions_row = cursor.fetchone()
    wind_speed = conditions_row['wind_speed'] if conditions_row and conditions_row['wind_speed'] else 0.0

    cursor.execute("""
        SELECT pit_number, racer_number, racer_name, racer_rank, motor_second_rate, second_rate
        FROM entries WHERE race_id = ? ORDER BY pit_number
    """, (race_id,))
    entries = [dict(row) for row in cursor.fetchall()]

    return {
        'id': row['id'],
        'venue_code': row['venue_code'],
        'race_number': row['race_number'],
        'race_date': row['race_date'],
        'race_time': row['race_time'],
        'wind_speed': wind_speed,
        'entries': entries
    }


def get_predictions(cursor, race_id: str):
    """予測データを取得"""
    cursor.execute("""
        SELECT pit_number, rank_prediction, confidence, racer_number
        FROM race_predictions
        WHERE race_id = ? AND prediction_type = 'before'
        ORDER BY rank_prediction
    """, (race_id,))

    predictions = [dict(row) for row in cursor.fetchall()]
    if len(predictions) < 3:
        return None

    old_pred = [p['pit_number'] for p in predictions]
    first_racer = predictions[0]['racer_number'] if predictions else None

    return {
        'confidence': predictions[0]['confidence'],
        'old_prediction': old_pred,
        'new_prediction': old_pred,
        'full_prediction': old_pred[:6] if len(old_pred) >= 6 else old_pred,
        'first_racer_number': first_racer
    }


def get_odds_data(cursor, race_id: str, predictions):
    """オッズデータを取得（パターンH対応：3点分）"""
    old_pred = predictions['old_prediction']

    if len(old_pred) < 3:
        return {}

    combinations = []
    combinations.append(f"{old_pred[0]}-{old_pred[1]}-{old_pred[2]}")
    if len(old_pred) >= 4:
        combinations.append(f"{old_pred[0]}-{old_pred[1]}-{old_pred[3]}")
    if len(old_pred) >= 5:
        combinations.append(f"{old_pred[0]}-{old_pred[1]}-{old_pred[4]}")

    placeholders = ','.join(['?'] * len(combinations))
    cursor.execute(f"""
        SELECT combination, odds
        FROM trifecta_odds
        WHERE race_id = ? AND combination IN ({placeholders})
    """, (race_id, *combinations))

    return {row['combination']: row['odds'] for row in cursor.fetchall()}


def check_tier2_conditions(cursor, race_id: str):
    """Tier 2（SQL）でどの条件に該当するかチェック"""
    # レース情報を取得
    cursor.execute("""
        SELECT
            r.id,
            r.venue_code,
            r.race_number,
            r.race_date,
            rp1.confidence,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3,
            rp4.pit_number as p4,
            rp5.pit_number as p5,
            e1.racer_rank as c1_rank,
            e1.motor_second_rate,
            e1.second_rate as c1_second_rate,
            e_pred.racer_number as first_racer_number
        FROM races r
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        LEFT JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
        LEFT JOIN race_predictions rp5 ON r.id = rp5.race_id AND rp5.prediction_type = 'before' AND rp5.rank_prediction = 5
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        LEFT JOIN entries e_pred ON r.id = e_pred.race_id AND e_pred.pit_number = rp1.pit_number
        WHERE r.id = ?
    """, (race_id,))

    race_row = cursor.fetchone()
    if not race_row:
        return None, []

    venue_code = int(race_row['venue_code']) if race_row['venue_code'] else None
    confidence = race_row['confidence']
    c1_rank = race_row['c1_rank']
    c1_second_rate = race_row['c1_second_rate']
    motor_second_rate = race_row['motor_second_rate']
    race_number = race_row['race_number']
    first_racer_number = race_row['first_racer_number']

    # レース月を取得
    race_date = race_row['race_date']
    race_month = int(race_date.split('-')[1]) if race_date else None

    # オッズを取得
    combo_123 = f"{race_row['p1']}-{race_row['p2']}-{race_row['p3']}"
    cursor.execute("""
        SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?
    """, (race_id, combo_123))
    odds_row = cursor.fetchone()
    odds_123 = odds_row['odds'] if odds_row else 0

    # 逃げ率を取得
    escape_rate = None
    if first_racer_number and race_row['p1'] == 1:
        cursor.execute("""
            SELECT escape_rate FROM player_escape_stats
            WHERE player_id = ? AND stadium_id IS NULL
        """, (str(first_racer_number),))
        escape_row = cursor.fetchone()
        escape_rate = escape_row['escape_rate'] if escape_row else None

    # バイアス指数を取得
    bias_index = None
    if first_racer_number:
        cursor.execute("""
            SELECT bias_index FROM player_bias_stats
            WHERE player_id = ? AND stadium_id IS NULL
        """, (str(first_racer_number),))
        bias_row = cursor.fetchone()
        bias_index = bias_row['bias_index'] if bias_row else None

    print(f"=== レース情報 (ID: {race_id}) ===")
    print(f"日付: {race_date}, 会場: {venue_code}, レース番号: {race_number}")
    print(f"信頼度: {confidence}, 1コース級別: {c1_rank}")
    print(f"予測: {combo_123}, オッズ: {odds_123:.1f}")
    print(f"1コース2連率: {c1_second_rate}%, モーター2連率: {motor_second_rate}%")
    print(f"逃げ率: {escape_rate if escape_rate is not None else 'データなし'}")
    print(f"バイアス指数: {bias_index if bias_index is not None else 'データなし'}")
    print(f"レース月: {race_month}月")
    print()

    # 各条件をチェック
    matching_conditions = []

    for i, cond in enumerate(STANDARD_BET_CONDITIONS):
        matched = True
        reason = []

        # 信頼度チェック
        if cond.get('confidence') is not None and cond['confidence'] != confidence:
            matched = False
            reason.append(f"信頼度不一致 (要求:{cond['confidence']}, 実際:{confidence})")

        # 級別チェック
        if c1_rank not in cond['c1_rank']:
            matched = False
            reason.append(f"級別不一致 (要求:{cond['c1_rank']}, 実際:{c1_rank})")

        # 会場フィルター
        if cond.get('venue_filter'):
            if venue_code not in cond['venue_filter']:
                matched = False
                reason.append(f"会場フィルター除外 (要求:{cond['venue_filter']}, 実際:{venue_code})")

        # オッズ範囲チェック
        if odds_123 > 0:
            if not (cond['odds_min'] <= odds_123 < cond['odds_max']):
                matched = False
                reason.append(f"オッズ範囲外 (要求:{cond['odds_min']}-{cond['odds_max']}, 実際:{odds_123:.1f})")
        else:
            matched = False
            reason.append("オッズデータなし")

        # 月除外チェック
        if cond.get('month_exclude'):
            if race_month in cond['month_exclude']:
                matched = False
                reason.append(f"月除外 (除外月:{cond['month_exclude']}, 実際:{race_month})")

        # 逃げ率チェック
        if cond.get('escape_rate_min'):
            if escape_rate is None:
                matched = False
                reason.append(f"逃げ率データなし (要求:{cond['escape_rate_min']}以上)")
            elif escape_rate < cond['escape_rate_min']:
                matched = False
                reason.append(f"逃げ率不足 (要求:{cond['escape_rate_min']}, 実際:{escape_rate:.2f})")

        # バイアス指数チェック
        if cond.get('bias_max'):
            if bias_index is None:
                matched = False
                reason.append(f"バイアス指数データなし (要求:{cond['bias_max']}未満)")
            elif bias_index >= cond['bias_max']:
                matched = False
                reason.append(f"バイアス指数範囲外 (要求:{cond['bias_max']}未満, 実際:{bias_index:.2f})")

        # 2連率チェック
        if cond.get('c1_second_rate_min'):
            if c1_second_rate is None or c1_second_rate < cond['c1_second_rate_min']:
                matched = False
                reason.append(f"2連率不足 (要求:{cond['c1_second_rate_min']}以上)")

        if cond.get('c1_second_rate_max'):
            if c1_second_rate is None or c1_second_rate >= cond['c1_second_rate_max']:
                matched = False
                reason.append(f"2連率超過 (要求:{cond['c1_second_rate_max']}未満)")

        # 予測コースチェック
        if cond.get('predicted_course'):
            if race_row['p1'] != cond['predicted_course']:
                matched = False
                reason.append(f"予測コース不一致 (要求:{cond['predicted_course']}, 実際:{race_row['p1']})")

        if matched:
            matching_conditions.append((i+1, cond['name']))
        else:
            print(f"【条件{i+1}】{cond['name']}: 不一致")
            print(f"  理由: {', '.join(reason)}")

    return race_row, matching_conditions


def debug_specific_race(race_id: str):
    """特定レースをデバッグ"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Tier 2での条件チェック
    race_row, matching_conditions = check_tier2_conditions(cursor, race_id)

    if matching_conditions:
        print(f"\n該当条件: {', '.join([f'条件{i}: {name}' for i, name in matching_conditions])}")
    else:
        print("\n該当条件なし（Tier 2でも除外される）")

    # Tier 3での判定
    print("\n=== Tier 3での購入判定 ===")

    race_data = get_race_data(cursor, race_id)
    predictions = get_predictions(cursor, race_id)
    odds_data = get_odds_data(cursor, race_id, predictions)

    evaluator = create_custom_evaluator(
        enable_venue_wind_filter=False,
        db_path=DATABASE_PATH
    )

    bet_target = evaluator.evaluate_race(
        race_data=race_data,
        predictions=predictions,
        odds_data=odds_data,
        has_beforeinfo=True
    )

    print(f"判定: {bet_target.status.value}")
    print(f"理由: {bet_target.reason}")
    print(f"信頼度: {bet_target.confidence}, 1コース級別: {bet_target.c1_rank}")
    print(f"オッズ: {bet_target.odds}")

    conn.close()


if __name__ == '__main__':
    # サンプルレースをデバッグ
    sample_race_ids = ['25262', '13067', '21558', '9598', '19550']

    for race_id in sample_race_ids:
        print("=" * 80)
        debug_specific_race(race_id)
        print()
