#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
パターンH外れレース詳細分析

マイナス月（1月、3月、4月、5月、8月、12月）の外れレースを詳細分析し、
外れパターンの法則や共通点を探る
"""
import sys
from pathlib import Path
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
import json

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus, MultiBetPattern

# 会場名マッピング
VENUE_NAMES = {
    '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島',
    '05': '多摩川', '06': '浜名湖', '07': '蒲郡', '08': '常滑',
    '09': '津', '10': '三国', '11': 'びわこ', '12': '住之江',
    '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島',
    '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
    '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
}

# マイナス月・プラス月
MINUS_MONTHS = ['2025-01', '2025-03', '2025-04', '2025-05', '2025-08', '2025-12']
PLUS_MONTHS = ['2025-02', '2025-06', '2025-07', '2025-09', '2025-10', '2025-11']

def analyze_pattern_h_losses():
    """パターンH外れレースの詳細分析"""

    # データベース接続
    db_path = ROOT_DIR / 'data' / 'boatrace.db'
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=" * 120)
    print("パターンH 外れレース詳細分析")
    print("=" * 120)
    print()

    # 評価器初期化（パターンH）
    evaluator = BetTargetEvaluator(use_multi_bet=True, multi_bet_pattern=MultiBetPattern.PATTERN_H)

    # 2025年のレースを取得
    cursor.execute("""
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number, r.race_time
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        ORDER BY r.race_date, r.venue_code, r.race_number
    """)
    races = cursor.fetchall()

    # 分析用データ収集
    all_races_data = []

    for race in races:
        race_id = race['race_id']
        venue_code = race['venue_code']
        race_date = race['race_date']
        race_number = race['race_number']
        month = race_date[:7]

        # 1コース選手情報
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

        # 予測情報
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

        # オッズ取得
        cursor.execute('SELECT combination, odds FROM trifecta_odds WHERE race_id = ?', (race_id,))
        odds_rows = cursor.fetchall()
        odds_dict = {row['combination']: row['odds'] for row in odds_rows}

        if not odds_dict:
            continue

        # 購入対象判定
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

        # 結果取得
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

        # 買い目情報
        bet_combos = [bet.combination for bet in target.multi_bet_result.bets]
        is_hit = actual_combo in bet_combos

        # 投資・リターン計算
        investment = sum(bet.bet_amount for bet in target.multi_bet_result.bets)
        ret = 0
        for bet in target.multi_bet_result.bets:
            if bet.combination == actual_combo:
                ret = bet.bet_amount * bet.odds

        # 外れパターン分類
        miss_pattern = classify_miss_pattern(full_prediction[:3], actual, bet_combos)

        # 気象情報取得
        cursor.execute('''
            SELECT wind_speed, wave_height, temperature, wind_direction
            FROM race_conditions WHERE race_id = ?
        ''', (race_id,))
        cond = cursor.fetchone()
        wind_speed = cond['wind_speed'] if cond and cond['wind_speed'] else 0
        wave_height = cond['wave_height'] if cond and cond['wave_height'] else 0
        temperature = cond['temperature'] if cond and cond['temperature'] else 0
        wind_direction = cond['wind_direction'] if cond and cond['wind_direction'] else ''

        # データ保存
        all_races_data.append({
            'race_id': race_id,
            'venue_code': venue_code,
            'venue_name': VENUE_NAMES.get(venue_code, venue_code),
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

    # ====================
    # 分析開始
    # ====================

    # 1. 外れパターン分類
    print("\n" + "=" * 120)
    print("【1】外れパターン分類（マイナス月 vs プラス月）")
    print("=" * 120)
    analyze_miss_patterns(all_races_data)

    # 2. 会場別傾向
    print("\n" + "=" * 120)
    print("【2】会場別傾向分析")
    print("=" * 120)
    analyze_by_venue(all_races_data)

    # 3. 信頼度別傾向
    print("\n" + "=" * 120)
    print("【3】信頼度別傾向分析")
    print("=" * 120)
    analyze_by_confidence(all_races_data)

    # 4. 1コース級別傾向
    print("\n" + "=" * 120)
    print("【4】1コース級別傾向分析")
    print("=" * 120)
    analyze_by_c1_rank(all_races_data)

    # 5. オッズレンジ別傾向
    print("\n" + "=" * 120)
    print("【5】オッズレンジ別傾向分析")
    print("=" * 120)
    analyze_by_odds_range(all_races_data)

    # 6. 時期的要因
    print("\n" + "=" * 120)
    print("【6】時期的要因分析")
    print("=" * 120)
    analyze_by_timing(all_races_data)

    # 7. 気象条件
    print("\n" + "=" * 120)
    print("【7】気象条件分析")
    print("=" * 120)
    analyze_by_weather(all_races_data)

    # 8. レース番号別
    print("\n" + "=" * 120)
    print("【8】レース番号別分析")
    print("=" * 120)
    analyze_by_race_number(all_races_data)

    # 9. 決まり手分析
    print("\n" + "=" * 120)
    print("【9】決まり手分析")
    print("=" * 120)
    analyze_by_kimarite(all_races_data)

    # 10. 外れレースの具体例
    print("\n" + "=" * 120)
    print("【10】マイナス月の大外れレース例（上位20件）")
    print("=" * 120)
    show_worst_losses(all_races_data)

    # 11. 改善提案
    print("\n" + "=" * 120)
    print("【11】改善提案")
    print("=" * 120)
    generate_improvement_proposals(all_races_data)

    conn.close()


def classify_miss_pattern(prediction, actual, bet_combos):
    """外れパターンを分類"""
    # 的中した場合
    actual_combo = f"{actual[0]}-{actual[1]}-{actual[2]}"
    if actual_combo in bet_combos:
        return 'HIT'

    # 1着的中・2着外れ
    if prediction[0] == actual[0]:
        return '1着的中・2着外れ'

    # 惜しい外れ（順位入れ替わり）
    if set(prediction[:2]) == set(actual[:2]):
        return '惜しい外れ（1-2入替）'

    # 惜しい外れ（予測1-3位に実際1-3位が含まれる）
    if len(set(prediction[:3]) & set(actual[:3])) >= 2:
        return '惜しい外れ（2艇入り）'

    # 予測上位3艇のうち1艇のみ入り
    if len(set(prediction[:3]) & set(actual[:3])) == 1:
        return '1艇のみ入り'

    # 大外れ（予測上位3艇が全く入らない）
    if len(set(prediction[:3]) & set(actual[:3])) == 0:
        return '大外れ'

    return 'その他'


def analyze_miss_patterns(data):
    """外れパターン分析"""
    # マイナス月とプラス月に分離
    minus_data = [d for d in data if d['month'] in MINUS_MONTHS]
    plus_data = [d for d in data if d['month'] in PLUS_MONTHS]

    def count_patterns(races):
        patterns = defaultdict(int)
        for r in races:
            patterns[r['miss_pattern']] += 1
        return patterns

    minus_patterns = count_patterns(minus_data)
    plus_patterns = count_patterns(plus_data)

    print(f"\n{'パターン':<25} {'マイナス月':>12} {'割合':>8} {'プラス月':>12} {'割合':>8} {'差異':>10}")
    print("-" * 80)

    all_patterns = set(minus_patterns.keys()) | set(plus_patterns.keys())
    for pattern in sorted(all_patterns):
        m_cnt = minus_patterns.get(pattern, 0)
        p_cnt = plus_patterns.get(pattern, 0)
        m_total = len(minus_data)
        p_total = len(plus_data)
        m_rate = m_cnt / m_total * 100 if m_total > 0 else 0
        p_rate = p_cnt / p_total * 100 if p_total > 0 else 0
        diff = m_rate - p_rate
        print(f"{pattern:<25} {m_cnt:>12} {m_rate:>7.1f}% {p_cnt:>12} {p_rate:>7.1f}% {diff:>+9.1f}%")

    print("-" * 80)
    print(f"{'合計':<25} {len(minus_data):>12} {'100.0%':>8} {len(plus_data):>12} {'100.0%':>8}")

    # 的中率比較
    minus_hit = sum(1 for d in minus_data if d['is_hit'])
    plus_hit = sum(1 for d in plus_data if d['is_hit'])
    minus_hit_rate = minus_hit / len(minus_data) * 100 if minus_data else 0
    plus_hit_rate = plus_hit / len(plus_data) * 100 if plus_data else 0

    print(f"\n【的中率比較】")
    print(f"マイナス月: {minus_hit}/{len(minus_data)} = {minus_hit_rate:.1f}%")
    print(f"プラス月:   {plus_hit}/{len(plus_data)} = {plus_hit_rate:.1f}%")
    print(f"差異: {minus_hit_rate - plus_hit_rate:+.1f}%")


def analyze_by_venue(data):
    """会場別分析"""
    minus_data = [d for d in data if d['month'] in MINUS_MONTHS]
    plus_data = [d for d in data if d['month'] in PLUS_MONTHS]

    def venue_stats(races):
        stats = defaultdict(lambda: {'count': 0, 'hit': 0, 'investment': 0, 'return': 0})
        for r in races:
            key = r['venue_name']
            stats[key]['count'] += 1
            stats[key]['hit'] += 1 if r['is_hit'] else 0
            stats[key]['investment'] += r['investment']
            stats[key]['return'] += r['return']
        return stats

    minus_stats = venue_stats(minus_data)
    plus_stats = venue_stats(plus_data)

    print(f"\n【マイナス月の会場別統計（件数順）】")
    print(f"{'会場':<10} {'件数':>6} {'的中':>4} {'的中率':>7} {'投資額':>12} {'払戻額':>12} {'収支':>12} {'ROI':>8}")
    print("-" * 90)

    sorted_venues = sorted(minus_stats.items(), key=lambda x: x[1]['count'], reverse=True)
    for venue, s in sorted_venues[:15]:
        hit_rate = s['hit'] / s['count'] * 100 if s['count'] > 0 else 0
        roi = s['return'] / s['investment'] * 100 if s['investment'] > 0 else 0
        balance = s['return'] - s['investment']
        print(f"{venue:<10} {s['count']:>6} {s['hit']:>4} {hit_rate:>6.1f}% {s['investment']:>11,}円 {s['return']:>11,.0f}円 {balance:>+11,.0f}円 {roi:>7.1f}%")

    # 最悪会場
    worst_venues = sorted(minus_stats.items(), key=lambda x: (x[1]['return'] - x[1]['investment']))[:5]
    print(f"\n【マイナス月の最悪会場TOP5（収支順）】")
    for venue, s in worst_venues:
        hit_rate = s['hit'] / s['count'] * 100 if s['count'] > 0 else 0
        balance = s['return'] - s['investment']
        print(f"  {venue}: 収支{balance:+,}円（{s['count']}件、的中{s['hit']}件、的中率{hit_rate:.1f}%）")

    # プラス月との比較
    print(f"\n【プラス月との会場別比較（ROI差が大きい順）】")
    all_venues = set(minus_stats.keys()) | set(plus_stats.keys())
    venue_diffs = []
    for venue in all_venues:
        ms = minus_stats.get(venue, {'count': 0, 'hit': 0, 'investment': 0, 'return': 0})
        ps = plus_stats.get(venue, {'count': 0, 'hit': 0, 'investment': 0, 'return': 0})
        if ms['count'] >= 3 and ps['count'] >= 3:
            m_roi = ms['return'] / ms['investment'] * 100 if ms['investment'] > 0 else 0
            p_roi = ps['return'] / ps['investment'] * 100 if ps['investment'] > 0 else 0
            venue_diffs.append((venue, m_roi, p_roi, m_roi - p_roi, ms['count'], ps['count']))

    print(f"{'会場':<10} {'マイナス月ROI':>14} {'プラス月ROI':>12} {'差異':>10} {'M件数':>6} {'P件数':>6}")
    print("-" * 70)
    for v in sorted(venue_diffs, key=lambda x: x[3])[:10]:
        print(f"{v[0]:<10} {v[1]:>13.1f}% {v[2]:>11.1f}% {v[3]:>+9.1f}% {v[4]:>6} {v[5]:>6}")


def analyze_by_confidence(data):
    """信頼度別分析"""
    minus_data = [d for d in data if d['month'] in MINUS_MONTHS]
    plus_data = [d for d in data if d['month'] in PLUS_MONTHS]

    def conf_stats(races):
        stats = defaultdict(lambda: {'count': 0, 'hit': 0, 'investment': 0, 'return': 0})
        for r in races:
            key = r['confidence']
            stats[key]['count'] += 1
            stats[key]['hit'] += 1 if r['is_hit'] else 0
            stats[key]['investment'] += r['investment']
            stats[key]['return'] += r['return']
        return stats

    minus_stats = conf_stats(minus_data)
    plus_stats = conf_stats(plus_data)

    print(f"\n{'信頼度':<6} {'マイナス月':>40} {'プラス月':>40}")
    print(f"{'':>6} {'件数':>6} {'的中':>4} {'的中率':>7} {'ROI':>8} {'収支':>12} | {'件数':>6} {'的中':>4} {'的中率':>7} {'ROI':>8} {'収支':>12}")
    print("-" * 100)

    for conf in ['C', 'D']:
        ms = minus_stats.get(conf, {'count': 0, 'hit': 0, 'investment': 0, 'return': 0})
        ps = plus_stats.get(conf, {'count': 0, 'hit': 0, 'investment': 0, 'return': 0})

        m_hit_rate = ms['hit'] / ms['count'] * 100 if ms['count'] > 0 else 0
        m_roi = ms['return'] / ms['investment'] * 100 if ms['investment'] > 0 else 0
        m_balance = ms['return'] - ms['investment']

        p_hit_rate = ps['hit'] / ps['count'] * 100 if ps['count'] > 0 else 0
        p_roi = ps['return'] / ps['investment'] * 100 if ps['investment'] > 0 else 0
        p_balance = ps['return'] - ps['investment']

        print(f"{conf:<6} {ms['count']:>6} {ms['hit']:>4} {m_hit_rate:>6.1f}% {m_roi:>7.1f}% {m_balance:>+11,.0f}円 | {ps['count']:>6} {ps['hit']:>4} {p_hit_rate:>6.1f}% {p_roi:>7.1f}% {p_balance:>+11,.0f}円")


def analyze_by_c1_rank(data):
    """1コース級別分析"""
    minus_data = [d for d in data if d['month'] in MINUS_MONTHS]
    plus_data = [d for d in data if d['month'] in PLUS_MONTHS]

    def rank_stats(races):
        stats = defaultdict(lambda: {'count': 0, 'hit': 0, 'investment': 0, 'return': 0})
        for r in races:
            key = r['c1_rank']
            stats[key]['count'] += 1
            stats[key]['hit'] += 1 if r['is_hit'] else 0
            stats[key]['investment'] += r['investment']
            stats[key]['return'] += r['return']
        return stats

    minus_stats = rank_stats(minus_data)
    plus_stats = rank_stats(plus_data)

    print(f"\n{'1コース級別':<10} {'マイナス月':>40} {'プラス月':>40}")
    print(f"{'':>10} {'件数':>6} {'的中':>4} {'的中率':>7} {'ROI':>8} {'収支':>12} | {'件数':>6} {'的中':>4} {'的中率':>7} {'ROI':>8} {'収支':>12}")
    print("-" * 105)

    for rank in ['A1', 'A2', 'B1', 'B2']:
        ms = minus_stats.get(rank, {'count': 0, 'hit': 0, 'investment': 0, 'return': 0})
        ps = plus_stats.get(rank, {'count': 0, 'hit': 0, 'investment': 0, 'return': 0})

        m_hit_rate = ms['hit'] / ms['count'] * 100 if ms['count'] > 0 else 0
        m_roi = ms['return'] / ms['investment'] * 100 if ms['investment'] > 0 else 0
        m_balance = ms['return'] - ms['investment']

        p_hit_rate = ps['hit'] / ps['count'] * 100 if ps['count'] > 0 else 0
        p_roi = ps['return'] / ps['investment'] * 100 if ps['investment'] > 0 else 0
        p_balance = ps['return'] - ps['investment']

        print(f"{rank:<10} {ms['count']:>6} {ms['hit']:>4} {m_hit_rate:>6.1f}% {m_roi:>7.1f}% {m_balance:>+11,.0f}円 | {ps['count']:>6} {ps['hit']:>4} {p_hit_rate:>6.1f}% {p_roi:>7.1f}% {p_balance:>+11,.0f}円")


def analyze_by_odds_range(data):
    """オッズレンジ別分析"""

    def get_odds_range(odds):
        if odds < 20:
            return '0-20'
        elif odds < 30:
            return '20-30'
        elif odds < 40:
            return '30-40'
        elif odds < 50:
            return '40-50'
        elif odds < 60:
            return '50-60'
        else:
            return '60+'

    minus_data = [d for d in data if d['month'] in MINUS_MONTHS]
    plus_data = [d for d in data if d['month'] in PLUS_MONTHS]

    def odds_stats(races):
        stats = defaultdict(lambda: {'count': 0, 'hit': 0, 'investment': 0, 'return': 0})
        for r in races:
            key = get_odds_range(r['odds_123'])
            stats[key]['count'] += 1
            stats[key]['hit'] += 1 if r['is_hit'] else 0
            stats[key]['investment'] += r['investment']
            stats[key]['return'] += r['return']
        return stats

    minus_stats = odds_stats(minus_data)
    plus_stats = odds_stats(plus_data)

    print(f"\n【1-2-3オッズレンジ別分析】")
    print(f"{'オッズ':<10} {'マイナス月':>40} {'プラス月':>40}")
    print(f"{'':>10} {'件数':>6} {'的中':>4} {'的中率':>7} {'ROI':>8} {'収支':>12} | {'件数':>6} {'的中':>4} {'的中率':>7} {'ROI':>8} {'収支':>12}")
    print("-" * 105)

    for odds_range in ['0-20', '20-30', '30-40', '40-50', '50-60', '60+']:
        ms = minus_stats.get(odds_range, {'count': 0, 'hit': 0, 'investment': 0, 'return': 0})
        ps = plus_stats.get(odds_range, {'count': 0, 'hit': 0, 'investment': 0, 'return': 0})

        m_hit_rate = ms['hit'] / ms['count'] * 100 if ms['count'] > 0 else 0
        m_roi = ms['return'] / ms['investment'] * 100 if ms['investment'] > 0 else 0
        m_balance = ms['return'] - ms['investment']

        p_hit_rate = ps['hit'] / ps['count'] * 100 if ps['count'] > 0 else 0
        p_roi = ps['return'] / ps['investment'] * 100 if ps['investment'] > 0 else 0
        p_balance = ps['return'] - ps['investment']

        print(f"{odds_range:<10} {ms['count']:>6} {ms['hit']:>4} {m_hit_rate:>6.1f}% {m_roi:>7.1f}% {m_balance:>+11,.0f}円 | {ps['count']:>6} {ps['hit']:>4} {p_hit_rate:>6.1f}% {p_roi:>7.1f}% {p_balance:>+11,.0f}円")


def analyze_by_timing(data):
    """時期的要因分析"""
    minus_data = [d for d in data if d['month'] in MINUS_MONTHS]
    plus_data = [d for d in data if d['month'] in PLUS_MONTHS]

    # 曜日別
    def get_weekday(date_str):
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return dt.strftime('%A')

    WEEKDAY_JP = {'Monday': '月曜', 'Tuesday': '火曜', 'Wednesday': '水曜',
                  'Thursday': '木曜', 'Friday': '金曜', 'Saturday': '土曜', 'Sunday': '日曜'}

    def weekday_stats(races):
        stats = defaultdict(lambda: {'count': 0, 'hit': 0, 'investment': 0, 'return': 0})
        for r in races:
            key = WEEKDAY_JP.get(get_weekday(r['race_date']), '不明')
            stats[key]['count'] += 1
            stats[key]['hit'] += 1 if r['is_hit'] else 0
            stats[key]['investment'] += r['investment']
            stats[key]['return'] += r['return']
        return stats

    minus_stats = weekday_stats(minus_data)
    plus_stats = weekday_stats(plus_data)

    print(f"\n【曜日別分析】")
    print(f"{'曜日':<8} {'マイナス月':>35} {'プラス月':>35}")
    print(f"{'':>8} {'件数':>6} {'的中':>4} {'的中率':>7} {'ROI':>8} | {'件数':>6} {'的中':>4} {'的中率':>7} {'ROI':>8}")
    print("-" * 85)

    for wd in ['月曜', '火曜', '水曜', '木曜', '金曜', '土曜', '日曜']:
        ms = minus_stats.get(wd, {'count': 0, 'hit': 0, 'investment': 0, 'return': 0})
        ps = plus_stats.get(wd, {'count': 0, 'hit': 0, 'investment': 0, 'return': 0})

        m_hit_rate = ms['hit'] / ms['count'] * 100 if ms['count'] > 0 else 0
        m_roi = ms['return'] / ms['investment'] * 100 if ms['investment'] > 0 else 0

        p_hit_rate = ps['hit'] / ps['count'] * 100 if ps['count'] > 0 else 0
        p_roi = ps['return'] / ps['investment'] * 100 if ps['investment'] > 0 else 0

        print(f"{wd:<8} {ms['count']:>6} {ms['hit']:>4} {m_hit_rate:>6.1f}% {m_roi:>7.1f}% | {ps['count']:>6} {ps['hit']:>4} {p_hit_rate:>6.1f}% {p_roi:>7.1f}%")

    # 月初・月中・月末
    def get_period(date_str):
        day = int(date_str.split('-')[2])
        if day <= 10:
            return '月初（1-10日）'
        elif day <= 20:
            return '月中（11-20日）'
        else:
            return '月末（21-31日）'

    def period_stats(races):
        stats = defaultdict(lambda: {'count': 0, 'hit': 0, 'investment': 0, 'return': 0})
        for r in races:
            key = get_period(r['race_date'])
            stats[key]['count'] += 1
            stats[key]['hit'] += 1 if r['is_hit'] else 0
            stats[key]['investment'] += r['investment']
            stats[key]['return'] += r['return']
        return stats

    minus_p_stats = period_stats(minus_data)
    plus_p_stats = period_stats(plus_data)

    print(f"\n【月内時期別分析】")
    print(f"{'時期':<18} {'マイナス月':>35} {'プラス月':>35}")
    print(f"{'':>18} {'件数':>6} {'的中':>4} {'的中率':>7} {'ROI':>8} | {'件数':>6} {'的中':>4} {'的中率':>7} {'ROI':>8}")
    print("-" * 95)

    for period in ['月初（1-10日）', '月中（11-20日）', '月末（21-31日）']:
        ms = minus_p_stats.get(period, {'count': 0, 'hit': 0, 'investment': 0, 'return': 0})
        ps = plus_p_stats.get(period, {'count': 0, 'hit': 0, 'investment': 0, 'return': 0})

        m_hit_rate = ms['hit'] / ms['count'] * 100 if ms['count'] > 0 else 0
        m_roi = ms['return'] / ms['investment'] * 100 if ms['investment'] > 0 else 0

        p_hit_rate = ps['hit'] / ps['count'] * 100 if ps['count'] > 0 else 0
        p_roi = ps['return'] / ps['investment'] * 100 if ps['investment'] > 0 else 0

        print(f"{period:<18} {ms['count']:>6} {ms['hit']:>4} {m_hit_rate:>6.1f}% {m_roi:>7.1f}% | {ps['count']:>6} {ps['hit']:>4} {p_hit_rate:>6.1f}% {p_roi:>7.1f}%")


def analyze_by_weather(data):
    """気象条件分析"""
    minus_data = [d for d in data if d['month'] in MINUS_MONTHS]
    plus_data = [d for d in data if d['month'] in PLUS_MONTHS]

    # 風速別
    def get_wind_range(wind):
        if wind < 2:
            return '弱風（0-2m）'
        elif wind < 4:
            return '中風（2-4m）'
        elif wind < 6:
            return 'やや強風（4-6m）'
        else:
            return '強風（6m+）'

    def wind_stats(races):
        stats = defaultdict(lambda: {'count': 0, 'hit': 0, 'investment': 0, 'return': 0})
        for r in races:
            key = get_wind_range(r['wind_speed'])
            stats[key]['count'] += 1
            stats[key]['hit'] += 1 if r['is_hit'] else 0
            stats[key]['investment'] += r['investment']
            stats[key]['return'] += r['return']
        return stats

    minus_stats = wind_stats(minus_data)
    plus_stats = wind_stats(plus_data)

    print(f"\n【風速別分析】")
    print(f"{'風速':<20} {'マイナス月':>35} {'プラス月':>35}")
    print(f"{'':>20} {'件数':>6} {'的中':>4} {'的中率':>7} {'ROI':>8} | {'件数':>6} {'的中':>4} {'的中率':>7} {'ROI':>8}")
    print("-" * 95)

    for wind_range in ['弱風（0-2m）', '中風（2-4m）', 'やや強風（4-6m）', '強風（6m+）']:
        ms = minus_stats.get(wind_range, {'count': 0, 'hit': 0, 'investment': 0, 'return': 0})
        ps = plus_stats.get(wind_range, {'count': 0, 'hit': 0, 'investment': 0, 'return': 0})

        m_hit_rate = ms['hit'] / ms['count'] * 100 if ms['count'] > 0 else 0
        m_roi = ms['return'] / ms['investment'] * 100 if ms['investment'] > 0 else 0

        p_hit_rate = ps['hit'] / ps['count'] * 100 if ps['count'] > 0 else 0
        p_roi = ps['return'] / ps['investment'] * 100 if ps['investment'] > 0 else 0

        print(f"{wind_range:<20} {ms['count']:>6} {ms['hit']:>4} {m_hit_rate:>6.1f}% {m_roi:>7.1f}% | {ps['count']:>6} {ps['hit']:>4} {p_hit_rate:>6.1f}% {p_roi:>7.1f}%")

    # 波高別
    def get_wave_range(wave):
        if wave <= 2:
            return '穏やか（0-2cm）'
        elif wave <= 5:
            return '普通（3-5cm）'
        elif wave <= 10:
            return 'やや荒れ（6-10cm）'
        else:
            return '荒れ（10cm+）'

    def wave_stats(races):
        stats = defaultdict(lambda: {'count': 0, 'hit': 0, 'investment': 0, 'return': 0})
        for r in races:
            key = get_wave_range(r['wave_height'])
            stats[key]['count'] += 1
            stats[key]['hit'] += 1 if r['is_hit'] else 0
            stats[key]['investment'] += r['investment']
            stats[key]['return'] += r['return']
        return stats

    minus_w_stats = wave_stats(minus_data)
    plus_w_stats = wave_stats(plus_data)

    print(f"\n【波高別分析】")
    print(f"{'波高':<20} {'マイナス月':>35} {'プラス月':>35}")
    print(f"{'':>20} {'件数':>6} {'的中':>4} {'的中率':>7} {'ROI':>8} | {'件数':>6} {'的中':>4} {'的中率':>7} {'ROI':>8}")
    print("-" * 95)

    for wave_range in ['穏やか（0-2cm）', '普通（3-5cm）', 'やや荒れ（6-10cm）', '荒れ（10cm+）']:
        ms = minus_w_stats.get(wave_range, {'count': 0, 'hit': 0, 'investment': 0, 'return': 0})
        ps = plus_w_stats.get(wave_range, {'count': 0, 'hit': 0, 'investment': 0, 'return': 0})

        m_hit_rate = ms['hit'] / ms['count'] * 100 if ms['count'] > 0 else 0
        m_roi = ms['return'] / ms['investment'] * 100 if ms['investment'] > 0 else 0

        p_hit_rate = ps['hit'] / ps['count'] * 100 if ps['count'] > 0 else 0
        p_roi = ps['return'] / ps['investment'] * 100 if ps['investment'] > 0 else 0

        print(f"{wave_range:<20} {ms['count']:>6} {ms['hit']:>4} {m_hit_rate:>6.1f}% {m_roi:>7.1f}% | {ps['count']:>6} {ps['hit']:>4} {p_hit_rate:>6.1f}% {p_roi:>7.1f}%")


def analyze_by_race_number(data):
    """レース番号別分析"""
    minus_data = [d for d in data if d['month'] in MINUS_MONTHS]
    plus_data = [d for d in data if d['month'] in PLUS_MONTHS]

    def race_stats(races):
        stats = defaultdict(lambda: {'count': 0, 'hit': 0, 'investment': 0, 'return': 0})
        for r in races:
            key = r['race_number']
            stats[key]['count'] += 1
            stats[key]['hit'] += 1 if r['is_hit'] else 0
            stats[key]['investment'] += r['investment']
            stats[key]['return'] += r['return']
        return stats

    minus_stats = race_stats(minus_data)
    plus_stats = race_stats(plus_data)

    print(f"\n{'R':>4} {'マイナス月':>35} {'プラス月':>35}")
    print(f"{'':>4} {'件数':>6} {'的中':>4} {'的中率':>7} {'ROI':>8} | {'件数':>6} {'的中':>4} {'的中率':>7} {'ROI':>8}")
    print("-" * 80)

    for rn in range(1, 13):
        ms = minus_stats.get(rn, {'count': 0, 'hit': 0, 'investment': 0, 'return': 0})
        ps = plus_stats.get(rn, {'count': 0, 'hit': 0, 'investment': 0, 'return': 0})

        m_hit_rate = ms['hit'] / ms['count'] * 100 if ms['count'] > 0 else 0
        m_roi = ms['return'] / ms['investment'] * 100 if ms['investment'] > 0 else 0

        p_hit_rate = ps['hit'] / ps['count'] * 100 if ps['count'] > 0 else 0
        p_roi = ps['return'] / ps['investment'] * 100 if ps['investment'] > 0 else 0

        print(f"{rn:>4}R {ms['count']:>6} {ms['hit']:>4} {m_hit_rate:>6.1f}% {m_roi:>7.1f}% | {ps['count']:>6} {ps['hit']:>4} {p_hit_rate:>6.1f}% {p_roi:>7.1f}%")


def analyze_by_kimarite(data):
    """決まり手分析"""
    minus_data = [d for d in data if d['month'] in MINUS_MONTHS]
    plus_data = [d for d in data if d['month'] in PLUS_MONTHS]

    def kimarite_stats(races):
        stats = defaultdict(lambda: {'count': 0, 'hit': 0})
        for r in races:
            key = r['kimarite'] if r['kimarite'] else '不明'
            stats[key]['count'] += 1
            stats[key]['hit'] += 1 if r['is_hit'] else 0
        return stats

    minus_stats = kimarite_stats(minus_data)
    plus_stats = kimarite_stats(plus_data)

    print(f"\n{'決まり手':<12} {'マイナス月':>25} {'プラス月':>25} {'的中率差':>10}")
    print(f"{'':>12} {'件数':>6} {'的中':>4} {'的中率':>8} | {'件数':>6} {'的中':>4} {'的中率':>8}")
    print("-" * 80)

    all_kimarite = set(minus_stats.keys()) | set(plus_stats.keys())
    for km in sorted(all_kimarite):
        ms = minus_stats.get(km, {'count': 0, 'hit': 0})
        ps = plus_stats.get(km, {'count': 0, 'hit': 0})

        m_hit_rate = ms['hit'] / ms['count'] * 100 if ms['count'] > 0 else 0
        p_hit_rate = ps['hit'] / ps['count'] * 100 if ps['count'] > 0 else 0
        diff = m_hit_rate - p_hit_rate

        print(f"{km:<12} {ms['count']:>6} {ms['hit']:>4} {m_hit_rate:>7.1f}% | {ps['count']:>6} {ps['hit']:>4} {p_hit_rate:>7.1f}% {diff:>+9.1f}%")


def show_worst_losses(data):
    """マイナス月の大外れレース例"""
    minus_data = [d for d in data if d['month'] in MINUS_MONTHS and not d['is_hit']]

    # 投資額が大きく、大外れしたものをソート
    sorted_losses = sorted(minus_data, key=lambda x: x['balance'])[:20]

    print(f"\n{'No':>3} {'日付':>12} {'会場':<8} {'R':>3} {'信頼':>4} {'級別':>4} {'予測':>10} {'結果':>10} {'決まり手':<10} {'収支':>10} {'外れパターン':<18}")
    print("-" * 120)

    for i, r in enumerate(sorted_losses, 1):
        pred_str = '-'.join(map(str, r['prediction']))
        actual_str = '-'.join(map(str, r['actual']))
        print(f"{i:>3} {r['race_date']:>12} {r['venue_name']:<8} {r['race_number']:>3}R {r['confidence']:>4} {r['c1_rank']:>4} {pred_str:>10} {actual_str:>10} {r['kimarite']:<10} {r['balance']:>+9,}円 {r['miss_pattern']:<18}")


def generate_improvement_proposals(data):
    """改善提案の生成"""
    minus_data = [d for d in data if d['month'] in MINUS_MONTHS]
    plus_data = [d for d in data if d['month'] in PLUS_MONTHS]

    print("\n" + "=" * 80)
    print("【統計的発見と改善提案】")
    print("=" * 80)

    # 1. 会場別の問題点
    def venue_stats(races):
        stats = defaultdict(lambda: {'count': 0, 'hit': 0, 'investment': 0, 'return': 0})
        for r in races:
            key = (r['venue_code'], r['venue_name'])
            stats[key]['count'] += 1
            stats[key]['hit'] += 1 if r['is_hit'] else 0
            stats[key]['investment'] += r['investment']
            stats[key]['return'] += r['return']
        return stats

    minus_venue = venue_stats(minus_data)

    print("\n【1. 除外推奨会場（マイナス月のみ）】")
    bad_venues = []
    for (code, name), s in minus_venue.items():
        if s['count'] >= 5:
            roi = s['return'] / s['investment'] * 100 if s['investment'] > 0 else 0
            balance = s['return'] - s['investment']
            if roi < 50:  # ROI 50%未満
                bad_venues.append((code, name, s['count'], roi, balance))

    bad_venues.sort(key=lambda x: x[3])  # ROI順
    for v in bad_venues[:5]:
        print(f"  - {v[1]}（コード: {v[0]}）: {v[2]}件、ROI {v[3]:.1f}%、収支 {v[4]:+,}円")

    # 2. レース番号の問題点
    def race_num_stats(races):
        stats = defaultdict(lambda: {'count': 0, 'hit': 0, 'investment': 0, 'return': 0})
        for r in races:
            key = r['race_number']
            stats[key]['count'] += 1
            stats[key]['hit'] += 1 if r['is_hit'] else 0
            stats[key]['investment'] += r['investment']
            stats[key]['return'] += r['return']
        return stats

    minus_race = race_num_stats(minus_data)

    print("\n【2. 除外推奨レース番号（マイナス月のみ）】")
    bad_races = []
    for rn, s in minus_race.items():
        if s['count'] >= 10:
            roi = s['return'] / s['investment'] * 100 if s['investment'] > 0 else 0
            hit_rate = s['hit'] / s['count'] * 100 if s['count'] > 0 else 0
            if roi < 50:
                bad_races.append((rn, s['count'], roi, hit_rate))

    bad_races.sort(key=lambda x: x[2])
    for r in bad_races[:3]:
        print(f"  - {r[0]}R: {r[1]}件、ROI {r[2]:.1f}%、的中率 {r[3]:.1f}%")

    # 3. 気象条件の問題点
    print("\n【3. 気象条件に関する発見】")
    high_wind = [d for d in minus_data if d['wind_speed'] >= 4]
    if high_wind:
        high_wind_hit = sum(1 for d in high_wind if d['is_hit'])
        high_wind_rate = high_wind_hit / len(high_wind) * 100 if high_wind else 0
        print(f"  - 風速4m以上: {len(high_wind)}件中{high_wind_hit}的中（{high_wind_rate:.1f}%）")

        low_wind = [d for d in minus_data if d['wind_speed'] < 4]
        if low_wind:
            low_wind_hit = sum(1 for d in low_wind if d['is_hit'])
            low_wind_rate = low_wind_hit / len(low_wind) * 100 if low_wind else 0
            print(f"  - 風速4m未満: {len(low_wind)}件中{low_wind_hit}的中（{low_wind_rate:.1f}%）")

    # 4. 外れパターンの分析
    print("\n【4. 外れパターン別の傾向】")
    miss_patterns = defaultdict(int)
    for d in minus_data:
        if not d['is_hit']:
            miss_patterns[d['miss_pattern']] += 1

    total_miss = sum(miss_patterns.values())
    for pattern, cnt in sorted(miss_patterns.items(), key=lambda x: -x[1]):
        rate = cnt / total_miss * 100 if total_miss > 0 else 0
        print(f"  - {pattern}: {cnt}件（{rate:.1f}%）")

    # 5. 具体的な改善提案
    print("\n【5. 具体的な改善提案】")
    print()
    print("■ 提案1: 会場フィルタリング")
    print("  マイナス月で特にROIが低い会場を除外条件に追加")
    if bad_venues:
        codes = [v[0] for v in bad_venues[:3]]
        print(f"  除外候補: {', '.join(codes)}")

    print()
    print("■ 提案2: 気象条件フィルタリング")
    print("  強風（4m以上）時は購入を控える、または金額を減らす")

    print()
    print("■ 提案3: 時期別戦略")
    print("  3月・5月・8月は特に収支が悪いため、購入を控えるか条件を厳しくする")

    print()
    print("■ 提案4: 1コース選手の詳細条件追加")
    minus_a2 = [d for d in minus_data if d['c1_rank'] == 'A2']
    if minus_a2:
        a2_hit = sum(1 for d in minus_a2 if d['is_hit'])
        a2_rate = a2_hit / len(minus_a2) * 100 if minus_a2 else 0
        print(f"  A2級の的中率: {a2_rate:.1f}%（{a2_hit}/{len(minus_a2)}）")

        # A2のうち勝率が低い選手
        low_win_a2 = [d for d in minus_a2 if d['c1_win_rate'] < 6.0]
        if low_win_a2:
            low_hit = sum(1 for d in low_win_a2 if d['is_hit'])
            low_rate = low_hit / len(low_win_a2) * 100 if low_win_a2 else 0
            print(f"  A2級かつ勝率6.0未満: 的中率{low_rate:.1f}%（{low_hit}/{len(low_win_a2)}）")


if __name__ == '__main__':
    analyze_pattern_h_losses()
