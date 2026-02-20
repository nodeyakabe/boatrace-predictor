#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
パターンH 2025年プラス月 勝ちパターン詳細分析

最優先分析対象（高ROI月）:
1. 6月: +48,410円（ROI 303.4%）
2. 9月: +25,200円（ROI 189.4%）
3. 10月: +31,180円（ROI 174.1%）

追加分析対象:
4. 11月: +4,720円（ROI 128.4%）
5. 2月: +3,500円（ROI 124.3%）
6. 7月: +4,140円（ROI 116.2%）
"""
import sys
from pathlib import Path
import sqlite3
from collections import defaultdict
from datetime import datetime
import json

ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus
from src.betting.multi_bet_generator import MultiBetGenerator, MultiBetPattern

# データベース接続
DB_PATH = ROOT_DIR / 'data' / 'boatrace.db'

# プラス月定義
PLUS_MONTHS = ['2025-02', '2025-06', '2025-07', '2025-09', '2025-10', '2025-11']
HIGH_ROI_MONTHS = ['2025-06', '2025-09', '2025-10']  # 高ROI月（優先分析）

# マイナス月定義（比較用）
MINUS_MONTHS = ['2025-01', '2025-03', '2025-04', '2025-05', '2025-08', '2025-12']

# 会場名マッピング
VENUE_NAMES = {
    '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島', '05': '多摩川', '06': '浜名湖',
    '07': '蒲郡', '08': '常滑', '09': '津', '10': '三国', '11': 'びわこ', '12': '住之江',
    '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島', '17': '宮島', '18': '徳山',
    '19': '下関', '20': '若松', '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
}


def get_wind_range(wind_speed):
    """風速範囲を取得"""
    if wind_speed is None:
        return 'unknown'
    if wind_speed < 2:
        return '0-2m'
    elif wind_speed < 4:
        return '2-4m'
    elif wind_speed < 6:
        return '4-6m'
    else:
        return '6m+'


def get_odds_range(odds):
    """オッズ範囲を取得"""
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


def get_race_period(race_number):
    """レース時間帯を取得"""
    if race_number <= 4:
        return 'morning'
    elif race_number <= 8:
        return 'afternoon'
    else:
        return 'evening'


def get_weekday(date_str):
    """曜日を取得"""
    weekday_map = {0: 'Mon', 1: 'Tue', 2: 'Wed', 3: 'Thu', 4: 'Fri', 5: 'Sat', 6: 'Sun'}
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    return weekday_map[dt.weekday()]


def calc_stats(races):
    """統計を計算"""
    if not races:
        return {'count': 0, 'hits': 0, 'hit_rate': 0, 'investment': 0, 'return': 0, 'roi': 0, 'balance': 0}
    count = len(races)
    hits = sum(1 for r in races if r['is_hit'])
    investment = sum(r['investment'] for r in races)
    ret = sum(r['return'] for r in races)
    return {
        'count': count,
        'hits': hits,
        'hit_rate': hits / count * 100 if count > 0 else 0,
        'investment': investment,
        'return': ret,
        'roi': ret / investment * 100 if investment > 0 else 0,
        'balance': ret - investment
    }


def main():
    print("=" * 100)
    print("パターンH 2025年プラス月 勝ちパターン詳細分析")
    print("=" * 100)
    print()

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 評価器初期化
    evaluator = BetTargetEvaluator(use_multi_bet=True, multi_bet_pattern=MultiBetPattern.PATTERN_H)

    # 全レースデータを収集
    all_race_data = []

    # 2025年のレースを取得
    cursor.execute("""
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number, r.race_grade
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        ORDER BY r.race_date, r.venue_code, r.race_number
    """)
    races = cursor.fetchall()

    print(f"対象レース数: {len(races):,}件")
    print()

    for race in races:
        race_id = race['race_id']
        venue_code = race['venue_code'] if race['venue_code'] else '00'
        if isinstance(venue_code, int):
            venue_code = f"{venue_code:02d}"
        else:
            venue_code = str(venue_code).zfill(2)

        race_date = race['race_date']
        race_number = race['race_number']
        race_grade = race['race_grade'] or '一般'
        month = race_date[:7]

        # 1コース級別
        cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
        c1 = cursor.fetchone()
        c1_rank = c1['racer_rank'] if c1 else 'B1'

        # 予測情報
        cursor.execute('''
            SELECT pit_number, confidence, rank_prediction
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'before'
            ORDER BY rank_prediction
        ''', (race_id,))
        preds = cursor.fetchall()

        if len(preds) < 6:
            continue

        confidence = preds[0]['confidence']
        old_pred = [preds[0]['pit_number'], preds[1]['pit_number'], preds[2]['pit_number']]
        full_prediction = [p['pit_number'] for p in preds]

        # オッズ取得
        cursor.execute('SELECT combination, odds FROM trifecta_odds WHERE race_id = ?', (race_id,))
        odds_rows = cursor.fetchall()
        odds_dict = {row['combination']: row['odds'] for row in odds_rows}

        if not odds_dict:
            continue

        # 気象条件取得
        cursor.execute('''
            SELECT weather, wind_direction, wind_speed, wave_height, temperature
            FROM race_conditions
            WHERE race_id = ?
        ''', (race_id,))
        cond = cursor.fetchone()
        weather = cond['weather'] if cond else None
        wind_direction = cond['wind_direction'] if cond else None
        wind_speed = cond['wind_speed'] if cond else 0.0
        wave_height = cond['wave_height'] if cond else 0

        # 購入対象判定
        predictions_dict = {
            'confidence': confidence,
            'old_prediction': old_pred,
            'new_prediction': old_pred,
            'full_prediction': full_prediction,
        }
        race_data_for_eval = {
            'venue_code': int(venue_code),
            'wind_speed': wind_speed,
            'entries': [{'pit_number': 1, 'racer_rank': c1_rank}],
        }

        target = evaluator.evaluate_race(
            race_data=race_data_for_eval,
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
        kimarite = results[0]['kimarite'] if results else None

        # 各買い目を処理
        race_investment = 0
        race_return = 0
        hit_bet = None

        for bet in target.multi_bet_result.bets:
            race_investment += bet.bet_amount
            if bet.combination == actual_combo:
                race_return = bet.bet_amount * bet.odds
                hit_bet = bet.combination

        # 買い目のオッズ取得
        combo_123 = f"{old_pred[0]}-{old_pred[1]}-{old_pred[2]}"
        combo_124 = f"{old_pred[0]}-{old_pred[1]}-{full_prediction[3]}" if len(full_prediction) > 3 else None
        combo_125 = f"{old_pred[0]}-{old_pred[1]}-{full_prediction[4]}" if len(full_prediction) > 4 else None

        odds_123 = odds_dict.get(combo_123, 0)
        odds_124 = odds_dict.get(combo_124, 0) if combo_124 else 0
        odds_125 = odds_dict.get(combo_125, 0) if combo_125 else 0

        # データ記録
        race_data_entry = {
            'race_id': race_id,
            'month': month,
            'race_date': race_date,
            'race_number': race_number,
            'venue_code': venue_code,
            'venue_name': VENUE_NAMES.get(venue_code, '不明'),
            'race_grade': race_grade,
            'confidence': confidence,
            'c1_rank': c1_rank,
            'prediction': old_pred,
            'actual': actual,
            'combo_123': combo_123,
            'combo_124': combo_124,
            'combo_125': combo_125,
            'odds_123': odds_123,
            'odds_124': odds_124,
            'odds_125': odds_125,
            'weather': weather,
            'wind_direction': wind_direction,
            'wind_speed': wind_speed or 0,
            'wave_height': wave_height or 0,
            'investment': race_investment,
            'return': race_return,
            'balance': race_return - race_investment,
            'is_hit': race_return > 0,
            'hit_bet': hit_bet,
            'kimarite': kimarite,
            'weekday': get_weekday(race_date),
            'race_period': get_race_period(race_number),
            'odds_range': get_odds_range(odds_123) if odds_123 > 0 else 'unknown',
            'wind_range': get_wind_range(wind_speed),
        }

        all_race_data.append(race_data_entry)

    conn.close()

    # 分析開始
    print(f"\n購入対象レース総数: {len(all_race_data)}件")

    # プラス月 vs マイナス月でデータ分割
    plus_data = [r for r in all_race_data if r['month'] in PLUS_MONTHS]
    minus_data = [r for r in all_race_data if r['month'] in MINUS_MONTHS]
    high_roi_data = [r for r in all_race_data if r['month'] in HIGH_ROI_MONTHS]

    print(f"プラス月データ: {len(plus_data)}件")
    print(f"マイナス月データ: {len(minus_data)}件")
    print(f"高ROI月データ: {len(high_roi_data)}件")
    print()

    # 分析結果格納
    analysis_results = {
        'summary': {
            'total': calc_stats(all_race_data),
            'plus_months': calc_stats(plus_data),
            'minus_months': calc_stats(minus_data),
            'high_roi_months': calc_stats(high_roi_data),
        },
        'monthly': {},
        'venue': {},
        'confidence': {},
        'c1_rank': {},
        'odds_range': {},
        'wind_range': {},
        'wave_height': {},
        'race_number': {},
        'race_period': {},
        'weekday': {},
        'race_grade': {},
        'hit_bet_pattern': {},
        'kimarite': {},
        'cross_analysis': {},
    }

    # 月別詳細分析
    for month in sorted(set(r['month'] for r in all_race_data)):
        month_data = [r for r in all_race_data if r['month'] == month]
        analysis_results['monthly'][month] = calc_stats(month_data)

        # 月別の的中レースを抽出
        hit_races = [r for r in month_data if r['is_hit']]
        analysis_results['monthly'][month]['hit_races'] = []
        for hr in hit_races:
            analysis_results['monthly'][month]['hit_races'].append({
                'date': hr['race_date'],
                'venue': hr['venue_name'],
                'race_number': hr['race_number'],
                'confidence': hr['confidence'],
                'c1_rank': hr['c1_rank'],
                'hit_bet': hr['hit_bet'],
                'odds': hr['odds_123'] if hr['hit_bet'] == hr['combo_123'] else (hr['odds_124'] if hr['hit_bet'] == hr['combo_124'] else hr['odds_125']),
                'return': hr['return'],
                'wind_speed': hr['wind_speed'],
                'wind_range': hr['wind_range'],
            })

    # 会場別分析（プラス月 vs マイナス月）
    venues = sorted(set(r['venue_code'] for r in all_race_data))
    for v in venues:
        plus_venue = [r for r in plus_data if r['venue_code'] == v]
        minus_venue = [r for r in minus_data if r['venue_code'] == v]
        analysis_results['venue'][v] = {
            'name': VENUE_NAMES.get(v, '不明'),
            'plus': calc_stats(plus_venue),
            'minus': calc_stats(minus_venue),
        }

    # 信頼度別分析
    for conf in ['C', 'D']:
        plus_conf = [r for r in plus_data if r['confidence'] == conf]
        minus_conf = [r for r in minus_data if r['confidence'] == conf]
        analysis_results['confidence'][conf] = {
            'plus': calc_stats(plus_conf),
            'minus': calc_stats(minus_conf),
        }

    # 1コース級別分析
    for rank in ['A1', 'A2', 'B1', 'B2']:
        plus_rank = [r for r in plus_data if r['c1_rank'] == rank]
        minus_rank = [r for r in minus_data if r['c1_rank'] == rank]
        analysis_results['c1_rank'][rank] = {
            'plus': calc_stats(plus_rank),
            'minus': calc_stats(minus_rank),
        }

    # オッズ範囲別分析
    for odds_r in ['0-20', '20-30', '30-40', '40-50', '50-60', '60+']:
        plus_odds = [r for r in plus_data if r['odds_range'] == odds_r]
        minus_odds = [r for r in minus_data if r['odds_range'] == odds_r]
        analysis_results['odds_range'][odds_r] = {
            'plus': calc_stats(plus_odds),
            'minus': calc_stats(minus_odds),
        }

    # 風速範囲別分析
    for wind_r in ['0-2m', '2-4m', '4-6m', '6m+']:
        plus_wind = [r for r in plus_data if r['wind_range'] == wind_r]
        minus_wind = [r for r in minus_data if r['wind_range'] == wind_r]
        analysis_results['wind_range'][wind_r] = {
            'plus': calc_stats(plus_wind),
            'minus': calc_stats(minus_wind),
        }

    # レース番号別分析
    for rn in range(1, 13):
        plus_rn = [r for r in plus_data if r['race_number'] == rn]
        minus_rn = [r for r in minus_data if r['race_number'] == rn]
        analysis_results['race_number'][str(rn)] = {
            'plus': calc_stats(plus_rn),
            'minus': calc_stats(minus_rn),
        }

    # レース時間帯別分析
    for period in ['morning', 'afternoon', 'evening']:
        plus_period = [r for r in plus_data if r['race_period'] == period]
        minus_period = [r for r in minus_data if r['race_period'] == period]
        analysis_results['race_period'][period] = {
            'plus': calc_stats(plus_period),
            'minus': calc_stats(minus_period),
        }

    # 曜日別分析
    for wd in ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']:
        plus_wd = [r for r in plus_data if r['weekday'] == wd]
        minus_wd = [r for r in minus_data if r['weekday'] == wd]
        analysis_results['weekday'][wd] = {
            'plus': calc_stats(plus_wd),
            'minus': calc_stats(minus_wd),
        }

    # グレード別分析
    grades = sorted(set(r['race_grade'] for r in all_race_data if r['race_grade']))
    for grade in grades:
        plus_grade = [r for r in plus_data if r['race_grade'] == grade]
        minus_grade = [r for r in minus_data if r['race_grade'] == grade]
        analysis_results['race_grade'][grade] = {
            'plus': calc_stats(plus_grade),
            'minus': calc_stats(minus_grade),
        }

    # 買い目パターン分析（どの買い目が的中したか）
    for pattern in ['1-2-3', '1-2-4', '1-2-5', 'miss']:
        plus_hits = [r for r in plus_data if (
            (pattern == '1-2-3' and r['is_hit'] and r['hit_bet'] == r['combo_123']) or
            (pattern == '1-2-4' and r['is_hit'] and r['hit_bet'] == r['combo_124']) or
            (pattern == '1-2-5' and r['is_hit'] and r['hit_bet'] == r['combo_125']) or
            (pattern == 'miss' and not r['is_hit'])
        )]
        minus_hits = [r for r in minus_data if (
            (pattern == '1-2-3' and r['is_hit'] and r['hit_bet'] == r['combo_123']) or
            (pattern == '1-2-4' and r['is_hit'] and r['hit_bet'] == r['combo_124']) or
            (pattern == '1-2-5' and r['is_hit'] and r['hit_bet'] == r['combo_125']) or
            (pattern == 'miss' and not r['is_hit'])
        )]
        analysis_results['hit_bet_pattern'][pattern] = {
            'plus': {'count': len(plus_hits)},
            'minus': {'count': len(minus_hits)},
        }

    # 決まり手別分析
    kimarite_list = sorted(set(r['kimarite'] for r in all_race_data if r['kimarite']))
    for km in kimarite_list:
        plus_km = [r for r in plus_data if r['kimarite'] == km]
        minus_km = [r for r in minus_data if r['kimarite'] == km]
        analysis_results['kimarite'][km] = {
            'plus': calc_stats(plus_km),
            'minus': calc_stats(minus_km),
        }

    # クロス分析（信頼度 x 1コース級別 x オッズ範囲）
    for conf in ['C', 'D']:
        for rank in ['A1', 'A2', 'B1', 'B2']:
            for odds_r in ['20-30', '30-40', '40-50', '50-60']:
                key = f"{conf}_{rank}_{odds_r}"
                plus_cross = [r for r in plus_data if r['confidence'] == conf and r['c1_rank'] == rank and r['odds_range'] == odds_r]
                minus_cross = [r for r in minus_data if r['confidence'] == conf and r['c1_rank'] == rank and r['odds_range'] == odds_r]
                if plus_cross or minus_cross:
                    analysis_results['cross_analysis'][key] = {
                        'plus': calc_stats(plus_cross),
                        'minus': calc_stats(minus_cross),
                    }

    # 結果をJSON保存
    output_path = ROOT_DIR / 'scripts' / 'analysis' / 'pattern_h_winning_analysis.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(analysis_results, f, ensure_ascii=False, indent=2)

    print(f"分析結果を保存: {output_path}")
    print()

    # レポート出力
    print("=" * 100)
    print("分析レポート")
    print("=" * 100)

    # サマリー
    print("\n### サマリー ###")
    print(f"{'カテゴリ':<20} {'件数':>8} {'的中':>6} {'的中率':>8} {'ROI':>8} {'収支':>12}")
    print("-" * 70)
    for cat, stats in analysis_results['summary'].items():
        cat_name = {'total': '全体', 'plus_months': 'プラス月', 'minus_months': 'マイナス月', 'high_roi_months': '高ROI月'}.get(cat, cat)
        print(f"{cat_name:<20} {stats['count']:>8} {stats['hits']:>6} {stats['hit_rate']:>7.1f}% {stats['roi']:>7.1f}% {stats['balance']:>+11,}")

    # 月別
    print("\n### 月別詳細 ###")
    print(f"{'月':<10} {'件数':>6} {'的中':>4} {'的中率':>7} {'ROI':>8} {'収支':>12}")
    print("-" * 60)
    for month in sorted(analysis_results['monthly'].keys()):
        stats = analysis_results['monthly'][month]
        marker = " *" if month in HIGH_ROI_MONTHS else ""
        print(f"{month:<10} {stats['count']:>6} {stats['hits']:>4} {stats['hit_rate']:>6.1f}% {stats['roi']:>7.1f}% {stats['balance']:>+11,}{marker}")

    # 高ROI月の的中レース詳細
    print("\n### 高ROI月（6,9,10月）的中レース詳細 ###")
    for month in HIGH_ROI_MONTHS:
        print(f"\n【{month}】")
        if month in analysis_results['monthly'] and 'hit_races' in analysis_results['monthly'][month]:
            for hr in analysis_results['monthly'][month]['hit_races']:
                print(f"  {hr['date']} {hr['venue']} R{hr['race_number']} "
                      f"信頼度{hr['confidence']} {hr['c1_rank']} "
                      f"買目{hr['hit_bet']} オッズ{hr['odds']:.1f}倍 "
                      f"払戻{hr['return']:,.0f}円 風{hr['wind_range']}")

    # 会場別分析（プラス月で好成績の会場）
    print("\n### 会場別分析（プラス月で好成績TOP10）###")
    venue_sorted = sorted(
        [(v, s) for v, s in analysis_results['venue'].items() if s['plus']['count'] >= 3],
        key=lambda x: x[1]['plus']['roi'],
        reverse=True
    )[:10]
    print(f"{'会場':<10} {'プラス月件数':>10} {'プラス月ROI':>10} {'マイナス月件数':>10} {'マイナス月ROI':>10}")
    print("-" * 60)
    for v, s in venue_sorted:
        print(f"{s['name']:<10} {s['plus']['count']:>10} {s['plus']['roi']:>9.1f}% {s['minus']['count']:>10} {s['minus']['roi']:>9.1f}%")

    # 信頼度別
    print("\n### 信頼度別分析 ###")
    print(f"{'信頼度':<10} {'プラス月件数':>10} {'プラス月ROI':>10} {'マイナス月件数':>10} {'マイナス月ROI':>10}")
    print("-" * 60)
    for conf, s in analysis_results['confidence'].items():
        print(f"{conf:<10} {s['plus']['count']:>10} {s['plus']['roi']:>9.1f}% {s['minus']['count']:>10} {s['minus']['roi']:>9.1f}%")

    # 1コース級別
    print("\n### 1コース級別分析 ###")
    print(f"{'級別':<10} {'プラス月件数':>10} {'プラス月ROI':>10} {'マイナス月件数':>10} {'マイナス月ROI':>10}")
    print("-" * 60)
    for rank, s in analysis_results['c1_rank'].items():
        print(f"{rank:<10} {s['plus']['count']:>10} {s['plus']['roi']:>9.1f}% {s['minus']['count']:>10} {s['minus']['roi']:>9.1f}%")

    # オッズ範囲別
    print("\n### オッズ範囲別分析 ###")
    print(f"{'オッズ範囲':<12} {'プラス月件数':>10} {'プラス月ROI':>10} {'マイナス月件数':>10} {'マイナス月ROI':>10}")
    print("-" * 65)
    for odds_r in ['20-30', '30-40', '40-50', '50-60', '60+']:
        if odds_r in analysis_results['odds_range']:
            s = analysis_results['odds_range'][odds_r]
            print(f"{odds_r}倍{'':<6} {s['plus']['count']:>10} {s['plus']['roi']:>9.1f}% {s['minus']['count']:>10} {s['minus']['roi']:>9.1f}%")

    # 風速範囲別
    print("\n### 風速範囲別分析 ###")
    print(f"{'風速':<12} {'プラス月件数':>10} {'プラス月ROI':>10} {'マイナス月件数':>10} {'マイナス月ROI':>10}")
    print("-" * 65)
    for wind_r in ['0-2m', '2-4m', '4-6m', '6m+']:
        if wind_r in analysis_results['wind_range']:
            s = analysis_results['wind_range'][wind_r]
            print(f"{wind_r:<12} {s['plus']['count']:>10} {s['plus']['roi']:>9.1f}% {s['minus']['count']:>10} {s['minus']['roi']:>9.1f}%")

    # 買い目パターン分析
    print("\n### 買い目パターン分析 ###")
    print("（どの買い目が的中したか）")
    print(f"{'パターン':<12} {'プラス月':>10} {'マイナス月':>10}")
    print("-" * 35)
    for pattern, s in analysis_results['hit_bet_pattern'].items():
        print(f"{pattern:<12} {s['plus']['count']:>10} {s['minus']['count']:>10}")

    # クロス分析で高収益の条件を抽出
    print("\n### クロス分析（高収益条件TOP10）###")
    cross_sorted = sorted(
        [(k, s) for k, s in analysis_results['cross_analysis'].items() if s['plus']['count'] >= 3 and s['plus']['roi'] > 100],
        key=lambda x: x[1]['plus']['balance'],
        reverse=True
    )[:10]
    print(f"{'条件':<25} {'件数':>6} {'的中':>4} {'ROI':>8} {'収支':>12}")
    print("-" * 60)
    for k, s in cross_sorted:
        parts = k.split('_')
        cond_str = f"{parts[0]} x {parts[1]} x {parts[2]}倍"
        print(f"{cond_str:<25} {s['plus']['count']:>6} {s['plus']['hits']:>4} {s['plus']['roi']:>7.1f}% {s['plus']['balance']:>+11,}")

    print()
    print("=" * 100)
    print("分析完了")
    print("=" * 100)

    return analysis_results


if __name__ == '__main__':
    main()
