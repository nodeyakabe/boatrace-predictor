#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
パターンH外れレース詳細分析 v2 - JSON出力版
"""
import sys
from pathlib import Path
import sqlite3
from collections import defaultdict
from datetime import datetime
import json

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus, MultiBetPattern

# 会場名マッピング
VENUE_NAMES = {
    '01': 'Kiryu', '02': 'Toda', '03': 'Edogawa', '04': 'Heiwajima',
    '05': 'Tamagawa', '06': 'Hamanako', '07': 'Gamagori', '08': 'Tokoname',
    '09': 'Tsu', '10': 'Mikuni', '11': 'Biwako', '12': 'Suminoe',
    '13': 'Amagasaki', '14': 'Naruto', '15': 'Marugame', '16': 'Kojima',
    '17': 'Miyajima', '18': 'Tokuyama', '19': 'Shimonoseki', '20': 'Wakamatsu',
    '21': 'Ashiya', '22': 'Fukuoka', '23': 'Karatsu', '24': 'Omura'
}

VENUE_NAMES_JP = {
    '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島',
    '05': '多摩川', '06': '浜名湖', '07': '蒲郡', '08': '常滑',
    '09': '津', '10': '三国', '11': 'びわこ', '12': '住之江',
    '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島',
    '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
    '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
}

MINUS_MONTHS = ['2025-01', '2025-03', '2025-04', '2025-05', '2025-08', '2025-12']
PLUS_MONTHS = ['2025-02', '2025-06', '2025-07', '2025-09', '2025-10', '2025-11']

def classify_miss_pattern(prediction, actual, bet_combos):
    """外れパターンを分類"""
    actual_combo = f"{actual[0]}-{actual[1]}-{actual[2]}"
    if actual_combo in bet_combos:
        return 'HIT'
    if prediction[0] == actual[0]:
        return '1st_hit_2nd_miss'
    if set(prediction[:2]) == set(actual[:2]):
        return 'close_miss_swap'
    if len(set(prediction[:3]) & set(actual[:3])) >= 2:
        return 'close_miss_2boats'
    if len(set(prediction[:3]) & set(actual[:3])) == 1:
        return '1boat_only'
    if len(set(prediction[:3]) & set(actual[:3])) == 0:
        return 'total_miss'
    return 'other'

def main():
    db_path = ROOT_DIR / 'data' / 'boatrace.db'
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    evaluator = BetTargetEvaluator(use_multi_bet=True, multi_bet_pattern=MultiBetPattern.PATTERN_H)

    cursor.execute("""
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number, r.race_time
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        ORDER BY r.race_date, r.venue_code, r.race_number
    """)
    races = cursor.fetchall()

    all_races_data = []

    for race in races:
        race_id = race['race_id']
        venue_code = race['venue_code']
        race_date = race['race_date']
        race_number = race['race_number']
        month = race_date[:7]

        cursor.execute('''
            SELECT racer_rank, racer_number, win_rate, motor_second_rate, avg_st
            FROM entries WHERE race_id = ? AND pit_number = 1
        ''', (race_id,))
        c1 = cursor.fetchone()
        if not c1:
            continue
        c1_rank = c1['racer_rank'] if c1['racer_rank'] else 'B1'
        c1_win_rate = c1['win_rate'] if c1['win_rate'] else 0
        c1_motor_2rate = c1['motor_second_rate'] if c1['motor_second_rate'] else 0
        c1_avg_st = c1['avg_st'] if c1['avg_st'] else 0

        cursor.execute('''
            SELECT pit_number, confidence, rank_prediction, total_score
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'before'
            ORDER BY rank_prediction
        ''', (race_id,))
        preds = cursor.fetchall()

        if len(preds) < 6:
            continue

        confidence = preds[0]['confidence']
        full_prediction = [p['pit_number'] for p in preds]
        pred_scores = {p['pit_number']: p['total_score'] for p in preds}

        cursor.execute('SELECT combination, odds FROM trifecta_odds WHERE race_id = ?', (race_id,))
        odds_rows = cursor.fetchall()
        odds_dict = {row['combination']: row['odds'] for row in odds_rows}

        if not odds_dict:
            continue

        predictions_dict = {
            'confidence': confidence,
            'old_prediction': full_prediction[:3],
            'new_prediction': full_prediction[:3],
            'full_prediction': full_prediction,
        }
        race_data = {
            'venue_code': int(venue_code) if venue_code else 0,
            'entries': [{'pit_number': 1, 'racer_rank': c1_rank}],
        }

        target = evaluator.evaluate_race(
            race_data=race_data,
            predictions=predictions_dict,
            odds_data=odds_dict,
            has_beforeinfo=True
        )

        if target.status != BetStatus.TARGET_CONFIRMED or not target.multi_bet_result:
            continue

        cursor.execute('''
            SELECT pit_number, rank, kimarite
            FROM results
            WHERE race_id = ? AND is_invalid = 0
            ORDER BY CAST(rank AS INTEGER)
            LIMIT 3
        ''', (race_id,))
        results = cursor.fetchall()

        if len(results) < 3:
            continue

        actual = [results[0]['pit_number'], results[1]['pit_number'], results[2]['pit_number']]
        actual_combo = f"{actual[0]}-{actual[1]}-{actual[2]}"
        kimarite = results[0]['kimarite'] if results[0]['kimarite'] else ''

        bet_combos = [bet.combination for bet in target.multi_bet_result.bets]
        is_hit = actual_combo in bet_combos

        investment = sum(bet.bet_amount for bet in target.multi_bet_result.bets)
        ret = 0
        for bet in target.multi_bet_result.bets:
            if bet.combination == actual_combo:
                ret = bet.bet_amount * bet.odds

        miss_pattern = classify_miss_pattern(full_prediction[:3], actual, bet_combos)

        cursor.execute('''
            SELECT wind_speed, wave_height, temperature, wind_direction
            FROM race_conditions WHERE race_id = ?
        ''', (race_id,))
        cond = cursor.fetchone()
        wind_speed = cond['wind_speed'] if cond and cond['wind_speed'] else 0
        wave_height = cond['wave_height'] if cond and cond['wave_height'] else 0
        temperature = cond['temperature'] if cond and cond['temperature'] else 0
        wind_direction = cond['wind_direction'] if cond and cond['wind_direction'] else ''

        all_races_data.append({
            'race_id': race_id,
            'venue_code': venue_code,
            'venue_name': VENUE_NAMES.get(venue_code, venue_code),
            'venue_name_jp': VENUE_NAMES_JP.get(venue_code, venue_code),
            'race_date': race_date,
            'race_number': race_number,
            'month': month,
            'confidence': confidence,
            'c1_rank': c1_rank,
            'c1_win_rate': c1_win_rate,
            'c1_motor_2rate': c1_motor_2rate,
            'c1_avg_st': c1_avg_st,
            'prediction': full_prediction[:3],
            'actual': actual,
            'actual_combo': actual_combo,
            'bet_combos': bet_combos,
            'is_hit': is_hit,
            'miss_pattern': miss_pattern,
            'investment': investment,
            'return': ret,
            'balance': ret - investment,
            'kimarite': kimarite,
            'wind_speed': wind_speed,
            'wave_height': wave_height,
            'temperature': temperature,
            'wind_direction': wind_direction,
            'odds_123': odds_dict.get('1-2-3', 0),
            'odds_124': odds_dict.get('1-2-4', 0),
            'odds_125': odds_dict.get('1-2-5', 0),
        })

    # 分析結果をJSONで保存
    output_path = ROOT_DIR / 'scripts' / 'pattern_h_analysis.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_races_data, f, ensure_ascii=False, indent=2)

    print(f"Total races analyzed: {len(all_races_data)}")

    minus_data = [d for d in all_races_data if d['month'] in MINUS_MONTHS]
    plus_data = [d for d in all_races_data if d['month'] in PLUS_MONTHS]

    print(f"Minus months: {len(minus_data)} races")
    print(f"Plus months: {len(plus_data)} races")

    minus_hit = sum(1 for d in minus_data if d['is_hit'])
    plus_hit = sum(1 for d in plus_data if d['is_hit'])

    print(f"Minus hit rate: {minus_hit}/{len(minus_data)} = {minus_hit/len(minus_data)*100:.1f}%")
    print(f"Plus hit rate: {plus_hit}/{len(plus_data)} = {plus_hit/len(plus_data)*100:.1f}%")

    # サマリー統計
    summary = {
        'total_races': len(all_races_data),
        'minus_months': {
            'count': len(minus_data),
            'hits': minus_hit,
            'hit_rate': minus_hit/len(minus_data)*100 if minus_data else 0,
            'investment': sum(d['investment'] for d in minus_data),
            'return': sum(d['return'] for d in minus_data),
        },
        'plus_months': {
            'count': len(plus_data),
            'hits': plus_hit,
            'hit_rate': plus_hit/len(plus_data)*100 if plus_data else 0,
            'investment': sum(d['investment'] for d in plus_data),
            'return': sum(d['return'] for d in plus_data),
        }
    }

    summary['minus_months']['roi'] = summary['minus_months']['return'] / summary['minus_months']['investment'] * 100 if summary['minus_months']['investment'] > 0 else 0
    summary['minus_months']['balance'] = summary['minus_months']['return'] - summary['minus_months']['investment']
    summary['plus_months']['roi'] = summary['plus_months']['return'] / summary['plus_months']['investment'] * 100 if summary['plus_months']['investment'] > 0 else 0
    summary['plus_months']['balance'] = summary['plus_months']['return'] - summary['plus_months']['investment']

    summary_path = ROOT_DIR / 'scripts' / 'pattern_h_summary.json'
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\nMinus balance: {summary['minus_months']['balance']:+,.0f}")
    print(f"Plus balance: {summary['plus_months']['balance']:+,.0f}")

    conn.close()

if __name__ == '__main__':
    main()
