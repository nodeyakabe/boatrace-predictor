# -*- coding: utf-8 -*-
"""
v2.0 戦略エンジン バックテスト

改善版戦略の効果検証:
- Edge計算
- 場タイプ別オッズレンジ
- 動的資金配分
- 除外条件強化
"""

import sys
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

# パス設定
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting import (
    LOGIC_VERSION,
    FEATURES,
    StrategyEngine,
    EVCalculator,
    FilterEngine,
    BetSelector,
    get_odds_range,
    get_venue_type,
)
from src.betting.config import (
    BET_CONDITIONS,
    EXACTA_CONDITIONS,
    CONFIDENCE_HIT_RATES,
)


def get_test_data(db_path: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """テストデータを取得"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    # 予測データがあるレースを取得
    cursor.execute('''
        SELECT DISTINCT
            r.id as race_id,
            r.venue_code,
            r.race_date,
            r.race_number,
            p.confidence,
            p.prediction_type
        FROM races r
        JOIN race_predictions p ON r.id = p.race_id
        WHERE r.race_date >= ? AND r.race_date <= ?
          AND p.prediction_type = 'advance'
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''', (start_date, end_date))

    races = cursor.fetchall()
    test_data = []

    for race in races:
        race_id = race['race_id']

        # 予測を取得
        cursor.execute('''
            SELECT pit_number, rank_prediction, total_score, confidence
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'advance'
            ORDER BY rank_prediction
        ''', (race_id,))
        preds = cursor.fetchall()

        if len(preds) < 6:
            continue

        # 1コース情報
        cursor.execute('''
            SELECT e.racer_rank
            FROM entries e
            WHERE e.race_id = ? AND e.pit_number = 1
        ''', (race_id,))
        c1 = cursor.fetchone()
        c1_rank = c1['racer_rank'] if c1 else 'B1'

        # オッズ取得
        cursor.execute('''
            SELECT combination, odds
            FROM trifecta_odds
            WHERE race_id = ?
        ''', (race_id,))
        odds_rows = cursor.fetchall()
        odds_data = {row['combination']: row['odds'] for row in odds_rows}

        # 実際の結果
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        results = cursor.fetchall()

        if len(results) < 3:
            continue

        actual_combo = f"{results[0]['pit_number']}-{results[1]['pit_number']}-{results[2]['pit_number']}"
        actual_exacta = f"{results[0]['pit_number']}-{results[1]['pit_number']}"

        # 配当取得
        cursor.execute('''
            SELECT bet_type, amount FROM payouts
            WHERE race_id = ?
        ''', (race_id,))
        payouts = {row['bet_type']: row['amount'] for row in cursor.fetchall()}

        # 予測買い目
        pred_sorted = sorted(preds, key=lambda x: x['rank_prediction'])
        old_combo = f"{pred_sorted[0]['pit_number']}-{pred_sorted[1]['pit_number']}-{pred_sorted[2]['pit_number']}"
        old_exacta = f"{pred_sorted[0]['pit_number']}-{pred_sorted[1]['pit_number']}"

        test_data.append({
            'race_id': str(race_id),
            'venue_code': int(race['venue_code']) if race['venue_code'] else 0,
            'race_date': race['race_date'],
            'race_number': race['race_number'],
            'confidence': race['confidence'],
            'c1_rank': c1_rank,
            'old_combo': old_combo,
            'new_combo': old_combo,  # 新方式は同じと仮定
            'old_odds': odds_data.get(old_combo, 0),
            'odds_data': odds_data,
            'actual_combo': actual_combo,
            'actual_exacta': actual_exacta,
            'payout_trifecta': payouts.get('trifecta', 0),
            'payout_exacta': payouts.get('exacta', 0),
        })

    conn.close()
    return test_data


def run_backtest_v2(test_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """v2.0戦略でバックテスト"""
    ev_calc = EVCalculator()
    filter_engine = FilterEngine()
    bet_selector = BetSelector()

    results = {
        'total_races': len(test_data),
        'target_races': 0,
        'trifecta': {'bets': 0, 'hits': 0, 'invested': 0, 'payout': 0},
        'exacta': {'bets': 0, 'hits': 0, 'invested': 0, 'payout': 0},
        'by_confidence': {},
        'by_venue_type': {},
        'details': [],
    }

    for data in test_data:
        # フィルタチェック
        filter_data = {
            'confidence': data['confidence'],
            'c1_rank': data['c1_rank'],
            'venue_code': data['venue_code'],
            'odds': data['old_odds'],
        }
        filter_result = filter_engine.is_target_race(filter_data)

        if not filter_result.is_target:
            continue

        # 購入条件チェック
        race_data = {
            'race_id': data['race_id'],
            'venue_code': data['venue_code'],
            'entries': [{'pit_number': 1, 'racer_rank': data['c1_rank']}],
        }
        predictions = {
            'confidence': data['confidence'],
            'old_prediction': [int(x) for x in data['old_combo'].split('-')],
            'new_prediction': [int(x) for x in data['new_combo'].split('-')],
        }

        plan = bet_selector.select_bets(
            race_data=race_data,
            predictions=predictions,
            odds_data=data['odds_data']
        )

        if plan.total_bet == 0:
            continue

        results['target_races'] += 1

        # 信頼度別集計
        conf = data['confidence']
        if conf not in results['by_confidence']:
            results['by_confidence'][conf] = {
                'bets': 0, 'hits': 0, 'invested': 0, 'payout': 0
            }

        # 場タイプ別集計
        venue_type = get_venue_type(data['venue_code'])
        if venue_type not in results['by_venue_type']:
            results['by_venue_type'][venue_type] = {
                'bets': 0, 'hits': 0, 'invested': 0, 'payout': 0
            }

        # 3連単判定
        if plan.trifecta:
            bet_amount = plan.trifecta.bet_amount
            results['trifecta']['bets'] += 1
            results['trifecta']['invested'] += bet_amount
            results['by_confidence'][conf]['bets'] += 1
            results['by_confidence'][conf]['invested'] += bet_amount
            results['by_venue_type'][venue_type]['bets'] += 1
            results['by_venue_type'][venue_type]['invested'] += bet_amount

            if plan.trifecta.combination == data['actual_combo']:
                results['trifecta']['hits'] += 1
                results['trifecta']['payout'] += data['payout_trifecta']
                results['by_confidence'][conf]['hits'] += 1
                results['by_confidence'][conf]['payout'] += data['payout_trifecta']
                results['by_venue_type'][venue_type]['hits'] += 1
                results['by_venue_type'][venue_type]['payout'] += data['payout_trifecta']

        # 2連単判定
        if plan.exacta:
            bet_amount = plan.exacta.bet_amount
            results['exacta']['bets'] += 1
            results['exacta']['invested'] += bet_amount

            if plan.exacta.combination == data['actual_exacta']:
                results['exacta']['hits'] += 1
                results['exacta']['payout'] += data['payout_exacta']

    # ROI計算
    for key in ['trifecta', 'exacta']:
        s = results[key]
        s['hit_rate'] = s['hits'] / s['bets'] * 100 if s['bets'] > 0 else 0
        s['roi'] = s['payout'] / s['invested'] * 100 if s['invested'] > 0 else 0
        s['profit'] = s['payout'] - s['invested']

    for conf in results['by_confidence']:
        s = results['by_confidence'][conf]
        s['hit_rate'] = s['hits'] / s['bets'] * 100 if s['bets'] > 0 else 0
        s['roi'] = s['payout'] / s['invested'] * 100 if s['invested'] > 0 else 0
        s['profit'] = s['payout'] - s['invested']

    for vtype in results['by_venue_type']:
        s = results['by_venue_type'][vtype]
        s['hit_rate'] = s['hits'] / s['bets'] * 100 if s['bets'] > 0 else 0
        s['roi'] = s['payout'] / s['invested'] * 100 if s['invested'] > 0 else 0
        s['profit'] = s['payout'] - s['invested']

    # 総合
    total_invested = results['trifecta']['invested'] + results['exacta']['invested']
    total_payout = results['trifecta']['payout'] + results['exacta']['payout']
    results['total_invested'] = total_invested
    results['total_payout'] = total_payout
    results['total_profit'] = total_payout - total_invested
    results['total_roi'] = total_payout / total_invested * 100 if total_invested > 0 else 0

    return results


def print_results(results: Dict[str, Any], title: str):
    """結果を表示"""
    print("=" * 70)
    print(title)
    print("=" * 70)
    print(f"総レース数: {results['total_races']}")
    print(f"対象レース数: {results['target_races']}")
    print()

    print("[3連単]")
    s = results['trifecta']
    print(f"  購入: {s['bets']}件, 的中: {s['hits']}件, 的中率: {s['hit_rate']:.1f}%")
    print(f"  投資: {s['invested']:,}円, 払戻: {s['payout']:,}円, 収支: {s['profit']:+,}円")
    print(f"  ROI: {s['roi']:.1f}%")
    print()

    print("[2連単]")
    s = results['exacta']
    print(f"  購入: {s['bets']}件, 的中: {s['hits']}件, 的中率: {s['hit_rate']:.1f}%")
    print(f"  投資: {s['invested']:,}円, 払戻: {s['payout']:,}円, 収支: {s['profit']:+,}円")
    print(f"  ROI: {s['roi']:.1f}%")
    print()

    print("[総合]")
    print(f"  投資: {results['total_invested']:,}円")
    print(f"  払戻: {results['total_payout']:,}円")
    print(f"  収支: {results['total_profit']:+,}円")
    print(f"  ROI: {results['total_roi']:.1f}%")
    print()

    print("[信頼度別]")
    for conf in sorted(results['by_confidence'].keys()):
        s = results['by_confidence'][conf]
        print(f"  {conf}: {s['bets']}件, 的中{s['hits']}, 率{s['hit_rate']:.1f}%, ROI {s['roi']:.1f}%, 収支{s['profit']:+,}円")
    print()

    print("[場タイプ別]")
    for vtype in sorted(results['by_venue_type'].keys()):
        s = results['by_venue_type'][vtype]
        print(f"  {vtype}: {s['bets']}件, 的中{s['hits']}, 率{s['hit_rate']:.1f}%, ROI {s['roi']:.1f}%, 収支{s['profit']:+,}円")
    print()


def main():
    print("=" * 70)
    print("v2.0 戦略エンジン バックテスト")
    print("=" * 70)
    print(f"LOGIC_VERSION: {LOGIC_VERSION}")
    print(f"FEATURES: {FEATURES}")
    print()

    db_path = str(ROOT_DIR / 'data' / 'boatrace.db')

    # 11月データでテスト
    print("データ取得中...")
    test_data = get_test_data(db_path, '2025-11-01', '2025-11-30')
    print(f"テストデータ: {len(test_data)}件")
    print()

    # バックテスト実行
    print("バックテスト実行中...")
    results = run_backtest_v2(test_data)
    print_results(results, "v2.0戦略 バックテスト結果 (2025年11月)")

    # 1月データでもテスト
    print("\n" + "=" * 70)
    test_data_jan = get_test_data(db_path, '2025-01-01', '2025-01-31')
    if test_data_jan:
        results_jan = run_backtest_v2(test_data_jan)
        print_results(results_jan, "v2.0戦略 バックテスト結果 (2025年1月)")

    # 10月データでもテスト
    print("\n" + "=" * 70)
    test_data_oct = get_test_data(db_path, '2025-10-01', '2025-10-31')
    if test_data_oct:
        results_oct = run_backtest_v2(test_data_oct)
        print_results(results_oct, "v2.0戦略 バックテスト結果 (2025年10月)")


if __name__ == '__main__':
    main()
