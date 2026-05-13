#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tier 3で特定レースの判定プロセスをデバッグ
"""
import sqlite3
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from src.betting.evaluator_helpers import create_standard_evaluator
from src.betting.bet_target_evaluator import BetStatus


def debug_race(race_id: str):
    """特定レースの購入判定プロセスをデバッグ"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print(f"=" * 80)
    print(f"レースID: {race_id} の判定プロセス詳細")
    print(f"=" * 80)
    print()

    # レースデータ取得
    cursor.execute("""
        SELECT id, venue_code, race_number, race_date, race_time
        FROM races WHERE id = ?
    """, (race_id,))
    row = cursor.fetchone()
    if not row:
        print(f"エラー: レースID {race_id} が見つかりません")
        return

    race_data = {
        'id': row['id'],
        'venue_code': row['venue_code'],
        'race_number': row['race_number'],
        'race_date': row['race_date'],
        'race_time': row['race_time'],
    }

    # 気象情報
    cursor.execute("SELECT wind_speed FROM race_conditions WHERE race_id = ?", (race_id,))
    conditions_row = cursor.fetchone()
    race_data['wind_speed'] = conditions_row['wind_speed'] if conditions_row and conditions_row['wind_speed'] else 0.0

    # エントリー情報
    cursor.execute("""
        SELECT pit_number, racer_number, racer_name, racer_rank, motor_second_rate, second_rate
        FROM entries WHERE race_id = ? ORDER BY pit_number
    """, (race_id,))
    entries = [dict(row) for row in cursor.fetchall()]
    race_data['entries'] = entries

    print("[レースデータ]")
    print(f"  会場: {race_data['venue_code']}")
    print(f"  レース番号: {race_data['race_number']}")
    print(f"  日付: {race_data['race_date']}")
    print(f"  風速: {race_data['wind_speed']}m/s")
    print()

    # 予測データ取得
    cursor.execute("""
        SELECT pit_number, rank_prediction, confidence
        FROM race_predictions
        WHERE race_id = ? AND prediction_type = 'before'
        ORDER BY rank_prediction
    """, (race_id,))
    predictions_raw = [dict(row) for row in cursor.fetchall()]

    if len(predictions_raw) < 3:
        print("エラー: 予測データが不足しています")
        return

    old_pred = [p['pit_number'] for p in predictions_raw[:3]]
    predictions = {
        'confidence': predictions_raw[0]['confidence'],
        'old_prediction': old_pred,
        'new_prediction': old_pred
    }

    print("[予測データ]")
    print(f"  信頼度: {predictions['confidence']}")
    print(f"  1位予測: pit={predictions_raw[0]['pit_number']} (confidence={predictions_raw[0]['confidence']})")
    print(f"  2位予測: pit={predictions_raw[1]['pit_number']} (confidence={predictions_raw[1]['confidence']})")
    print(f"  3位予測: pit={predictions_raw[2]['pit_number']} (confidence={predictions_raw[2]['confidence']})")
    print(f"  買目: {old_pred[0]}-{old_pred[1]}-{old_pred[2]}")
    print()

    # オッズデータ取得（パターンH対応：3点分）
    combinations = []
    if len(old_pred) >= 3:
        combinations.append(f"{old_pred[0]}-{old_pred[1]}-{old_pred[2]}")  # 1-2-3
    if len(old_pred) >= 4:
        combinations.append(f"{old_pred[0]}-{old_pred[1]}-{old_pred[3]}")  # 1-2-4
    if len(old_pred) >= 5:
        combinations.append(f"{old_pred[0]}-{old_pred[1]}-{old_pred[4]}")  # 1-2-5

    print("[オッズ取得（パターンH対応）]")
    print(f"  取得対象: {combinations}")

    if combinations:
        placeholders = ','.join(['?'] * len(combinations))
        cursor.execute(f"""
            SELECT combination, odds
            FROM trifecta_odds
            WHERE race_id = ? AND combination IN ({placeholders})
        """, (race_id, *combinations))
        odds_data = {row['combination']: row['odds'] for row in cursor.fetchall()}
    else:
        odds_data = {}

    print(f"  取得結果: {odds_data}")
    print()

    # 1コース選手の級別
    c1_entry = next((e for e in entries if e['pit_number'] == 1), None)
    c1_rank = c1_entry['racer_rank'] if c1_entry else 'B1'

    print("[1コース選手]")
    if c1_entry:
        print(f"  級別: {c1_entry['racer_rank']}")
        print(f"  選手名: {c1_entry['racer_name']}")
        print(f"  モーター2連率: {c1_entry.get('motor_second_rate')}%")
        print(f"  全国2連率: {c1_entry.get('second_rate')}%")
    print()

    # BetTargetEvaluatorで判定
    evaluator = create_standard_evaluator(db_path=DATABASE_PATH)

    print("[購入判定実行]")
    print(f"  evaluator.use_multi_bet: {evaluator.use_multi_bet}")
    print(f"  evaluator.enable_venue_wind_filter: {evaluator.enable_venue_wind_filter}")
    print(f"  evaluator.BET_CONDITIONS keys: {list(evaluator.BET_CONDITIONS.keys())}")
    print()

    # B条件の詳細をチェック
    if 'B' in evaluator.BET_CONDITIONS:
        print("[B条件の詳細]")
        for i, cond in enumerate(evaluator.BET_CONDITIONS['B']):
            print(f"  条件{i+1}: {cond.get('description', 'N/A')}")
            print(f"    odds_min: {cond['odds_min']}, odds_max: {cond['odds_max']}")
            print(f"    c1_rank: {cond['c1_rank']}")
            if 'venue_filter' in cond:
                print(f"    venue_filter: {cond['venue_filter']}")
                print(f"    venue_code=2 in venue_filter: {2 in cond['venue_filter']}")
            if 'month_exclude' in cond:
                print(f"    month_exclude: {cond['month_exclude']}")
            print()

    print(f"[レース情報]")
    print(f"  venue_code: {race_data['venue_code']} (type: {type(race_data['venue_code'])})")
    print(f"  race_month: {race_data['race_date'].split('-')[1]}")
    print()

    try:
        bet_target = evaluator.evaluate_race(
            race_data=race_data,
            predictions=predictions,
            odds_data=odds_data,
            has_beforeinfo=True
        )

        print("[判定結果]")
        print(f"  ステータス: {bet_target.status.value}")
        print(f"  信頼度: {bet_target.confidence}")
        print(f"  買目: {bet_target.combination}")
        print(f"  オッズ: {bet_target.odds}")
        print(f"  オッズ範囲: {bet_target.odds_range}")
        print(f"  1コース級別: {bet_target.c1_rank}")
        print(f"  期待ROI: {bet_target.expected_roi}%")
        print(f"  推奨賭金: {bet_target.bet_amount}円")
        print(f"  理由: {bet_target.reason}")
        print(f"  パターンH使用: {bet_target.use_pattern_h}")
        print()

        if bet_target.status in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
            print("OK: 購入対象")
        else:
            print("NG: 購入対象外")

    except Exception as e:
        print(f"エラー: {e}")
        import traceback
        traceback.print_exc()

    conn.close()


if __name__ == '__main__':
    import sys
    race_id = sys.argv[1] if len(sys.argv) > 1 else '16078'
    debug_race(race_id)
