# -*- coding: utf-8 -*-
"""
全モード比較バックテスト

baseline, edge_test, venue_test を全期間で比較
"""

import sys
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting.config import set_strategy_mode, get_current_features, get_logic_version
from src.betting import BetSelector, get_venue_type


def get_test_data(db_path: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """テストデータを取得"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

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

        cursor.execute('''
            SELECT pit_number, rank_prediction, total_score, confidence
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'advance'
            ORDER BY rank_prediction
        ''', (race_id,))
        preds = cursor.fetchall()

        if len(preds) < 6:
            continue

        cursor.execute('''
            SELECT e.racer_rank
            FROM entries e
            WHERE e.race_id = ? AND e.pit_number = 1
        ''', (race_id,))
        c1 = cursor.fetchone()
        c1_rank = c1['racer_rank'] if c1 else 'B1'

        cursor.execute('''
            SELECT combination, odds
            FROM trifecta_odds
            WHERE race_id = ?
        ''', (race_id,))
        odds_rows = cursor.fetchall()
        odds_data = {row['combination']: row['odds'] for row in odds_rows}

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

        cursor.execute('''
            SELECT bet_type, amount FROM payouts
            WHERE race_id = ?
        ''', (race_id,))
        payouts = {row['bet_type']: row['amount'] for row in cursor.fetchall()}

        pred_sorted = sorted(preds, key=lambda x: x['rank_prediction'])
        old_combo = f"{pred_sorted[0]['pit_number']}-{pred_sorted[1]['pit_number']}-{pred_sorted[2]['pit_number']}"

        test_data.append({
            'race_id': str(race_id),
            'venue_code': int(race['venue_code']) if race['venue_code'] else 0,
            'race_date': race['race_date'],
            'race_number': race['race_number'],
            'confidence': race['confidence'],
            'c1_rank': c1_rank,
            'old_combo': old_combo,
            'new_combo': old_combo,
            'old_odds': odds_data.get(old_combo, 0),
            'odds_data': odds_data,
            'actual_combo': actual_combo,
            'actual_exacta': actual_exacta,
            'payout_trifecta': payouts.get('trifecta', 0),
            'payout_exacta': payouts.get('exacta', 0),
        })

    conn.close()
    return test_data


def run_backtest(test_data: List[Dict[str, Any]], mode: str) -> Dict[str, Any]:
    """指定モードでバックテスト実行"""
    set_strategy_mode(mode)
    bet_selector = BetSelector()

    results = {
        'mode': mode,
        'total_races': len(test_data),
        'target_races': 0,
        'trifecta': {'bets': 0, 'hits': 0, 'invested': 0, 'payout': 0},
        'exacta': {'bets': 0, 'hits': 0, 'invested': 0, 'payout': 0},
        'by_month': {},
    }

    for data in test_data:
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
        month = data['race_date'][:7]

        if month not in results['by_month']:
            results['by_month'][month] = {
                'bets': 0, 'hits': 0, 'invested': 0, 'payout': 0
            }

        if plan.trifecta:
            bet_amount = plan.trifecta.bet_amount
            results['trifecta']['bets'] += 1
            results['trifecta']['invested'] += bet_amount
            results['by_month'][month]['bets'] += 1
            results['by_month'][month]['invested'] += bet_amount

            if plan.trifecta.combination == data['actual_combo']:
                results['trifecta']['hits'] += 1
                results['trifecta']['payout'] += data['payout_trifecta']
                results['by_month'][month]['hits'] += 1
                results['by_month'][month]['payout'] += data['payout_trifecta']

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

    for month in results['by_month']:
        s = results['by_month'][month]
        s['hit_rate'] = s['hits'] / s['bets'] * 100 if s['bets'] > 0 else 0
        s['roi'] = s['payout'] / s['invested'] * 100 if s['invested'] > 0 else 0
        s['profit'] = s['payout'] - s['invested']

    total_invested = results['trifecta']['invested'] + results['exacta']['invested']
    total_payout = results['trifecta']['payout'] + results['exacta']['payout']
    results['total_invested'] = total_invested
    results['total_payout'] = total_payout
    results['total_profit'] = total_payout - total_invested
    results['total_roi'] = total_payout / total_invested * 100 if total_invested > 0 else 0

    return results


def main():
    print("=" * 80)
    print("全モード比較バックテスト (2025年全期間)")
    print("=" * 80)

    db_path = str(ROOT_DIR / 'data' / 'boatrace.db')

    # 全期間データ取得
    print("\nデータ取得中...")
    test_data = get_test_data(db_path, '2025-01-01', '2025-12-07')
    print(f"テストデータ: {len(test_data)}件\n")

    modes = ['baseline', 'edge_test', 'venue_test']
    all_results = {}

    for mode in modes:
        print(f"[{mode}] バックテスト実行中...")
        results = run_backtest(test_data, mode)
        all_results[mode] = results

    # 結果比較表
    print("\n" + "=" * 80)
    print("【総合結果比較】")
    print("=" * 80)
    print(f"{'モード':<15} {'3連単件数':>10} {'3連単ROI':>10} {'2連単件数':>10} {'2連単ROI':>10} {'総合ROI':>10} {'収支':>15}")
    print("-" * 80)

    for mode in modes:
        r = all_results[mode]
        print(f"{mode:<15} {r['trifecta']['bets']:>10} {r['trifecta']['roi']:>9.1f}% {r['exacta']['bets']:>10} {r['exacta']['roi']:>9.1f}% {r['total_roi']:>9.1f}% {r['total_profit']:>+14,}")

    # 月別比較（3連単のみ）
    print("\n" + "=" * 80)
    print("【月別3連単ROI比較】")
    print("=" * 80)
    print(f"{'月':<10}", end="")
    for mode in modes:
        print(f"{mode:>20}", end="")
    print()
    print("-" * 70)

    months = sorted(all_results['baseline']['by_month'].keys())
    for month in months:
        print(f"{month:<10}", end="")
        for mode in modes:
            m_data = all_results[mode]['by_month'].get(month, {})
            roi = m_data.get('roi', 0)
            bets = m_data.get('bets', 0)
            print(f"{roi:>8.1f}% ({bets:>3})", end="")
        print()

    # 月別勝敗カウント
    print("\n" + "=" * 80)
    print("【月別黒字/赤字カウント（3連単）】")
    print("=" * 80)

    for mode in modes:
        wins = sum(1 for m in all_results[mode]['by_month'].values() if m['profit'] > 0)
        losses = sum(1 for m in all_results[mode]['by_month'].values() if m['profit'] <= 0)
        print(f"  {mode}: 黒字 {wins}ヶ月, 赤字 {losses}ヶ月")

    print("\n完了")


if __name__ == '__main__':
    main()
