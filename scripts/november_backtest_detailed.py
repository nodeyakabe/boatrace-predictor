# -*- coding: utf-8 -*-
"""
11月詳細バックテストスクリプト

11月のデータを使って、現在のシステムを運用した場合のシミュレーションを行う。
- 日別の購入金額・回収率
- 信頼度別の的中率・払戻金
- 期待値別の成績分析

使用方法:
    python scripts/november_backtest_detailed.py
"""

import sys
import os
import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH


def get_november_races(db_path: str) -> list:
    """11月のレースを取得（オッズデータがあるもの）"""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT DISTINCT r.id, r.race_date, r.venue_code, r.race_number
            FROM races r
            JOIN trifecta_odds t ON r.id = t.race_id
            WHERE r.race_date >= '2025-11-01' AND r.race_date <= '2025-11-30'
            ORDER BY r.race_date, r.venue_code, r.race_number
        ''')
        return cursor.fetchall()


def get_race_prediction(db_path: str, race_id: int) -> list:
    """レースの予測データを取得"""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT pit_number, rank_prediction, confidence, total_score
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'advance'
            ORDER BY rank_prediction
        ''', (race_id,))
        return cursor.fetchall()


def get_race_result(db_path: str, race_id: int) -> dict:
    """レースの結果を取得"""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        # 実際の着順
        cursor.execute('''
            SELECT pit_number, rank
            FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        result_rows = cursor.fetchall()

        if len(result_rows) < 3:
            return None

        actual_combo = f"{result_rows[0][0]}-{result_rows[1][0]}-{result_rows[2][0]}"

        # 払戻金
        cursor.execute('''
            SELECT amount FROM payouts
            WHERE race_id = ? AND bet_type = 'trifecta'
        ''', (race_id,))
        payout_row = cursor.fetchone()
        payout = payout_row[0] if payout_row else 0

        return {
            'actual_combo': actual_combo,
            'payout': payout,
            '1st': result_rows[0][0],
            '2nd': result_rows[1][0],
            '3rd': result_rows[2][0]
        }


def get_race_odds(db_path: str, race_id: int) -> dict:
    """レースのオッズを取得"""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT combination, odds
            FROM trifecta_odds
            WHERE race_id = ?
        ''', (race_id,))
        return {row[0]: row[1] for row in cursor.fetchall()}


def calculate_ev(odds: float, confidence: str) -> float:
    """期待値を計算"""
    # 信頼度別の的中確率（実績値ベース）
    CONFIDENCE_PROBABILITIES = {
        'A': 0.0800,  # 8.00%
        'B': 0.0513,  # 5.13%
        'C': 0.0354,  # 3.54%
        'D': 0.0171,  # 1.71%
        'E': 0.0100,  # 1.00%
    }
    prob = CONFIDENCE_PROBABILITIES.get(confidence, 0.02)
    return prob * odds


def generate_bet_combinations(predicted_ranks: list, pattern: str = '1-234-2345') -> list:
    """買い目の組み合わせを生成"""
    p = predicted_ranks

    if pattern == '1-234-234':
        seconds = [p[1], p[2], p[3]]
        thirds = [p[1], p[2], p[3]]
    elif pattern == '1-234-2345':
        seconds = [p[1], p[2], p[3]]
        thirds = [p[1], p[2], p[3], p[4]]
    else:
        seconds = [p[1], p[2], p[3]]
        thirds = [p[1], p[2], p[3], p[4]]

    combos = []
    for s in seconds:
        for t in thirds:
            if s != t and t != p[0]:
                combos.append(f"{p[0]}-{s}-{t}")

    return combos


def run_detailed_backtest(db_path: str, max_bets: int = 5, bet_amount: int = 100):
    """
    詳細なバックテストを実行

    Args:
        db_path: データベースパス
        max_bets: 1レースあたりの最大買い目数
        bet_amount: 1点あたりの賭け金（円）
    """
    print("=" * 80)
    print("11月詳細バックテスト")
    print("=" * 80)
    print(f"期間: 2025-11-01 ～ 2025-11-30")
    print(f"最大買い目数: {max_bets}点/レース")
    print(f"賭け金: {bet_amount}円/点")
    print("=" * 80)
    print()

    # 11月のレースを取得
    races = get_november_races(db_path)
    print(f"対象レース数（オッズあり）: {len(races)}")

    # 日別集計
    daily_stats = defaultdict(lambda: {
        'races': 0,
        'bets': 0,
        'hits': 0,
        'bet_amount': 0,
        'payout': 0
    })

    # 信頼度別集計
    confidence_stats = defaultdict(lambda: {
        'races': 0,
        'bets': 0,
        'hits': 0,
        'bet_amount': 0,
        'payout': 0
    })

    # 期待値別集計
    ev_ranges = [
        (0.0, 0.5, '0.0-0.5'),
        (0.5, 0.8, '0.5-0.8'),
        (0.8, 1.0, '0.8-1.0'),
        (1.0, 1.5, '1.0-1.5'),
        (1.5, 2.0, '1.5-2.0'),
        (2.0, 999, '2.0+')
    ]
    ev_stats = defaultdict(lambda: {
        'bets': 0,
        'hits': 0,
        'bet_amount': 0,
        'payout': 0
    })

    # 詳細記録（日別）
    daily_details = defaultdict(list)

    total_races = 0
    total_bets = 0
    total_hits = 0
    total_bet_amount = 0
    total_payout = 0
    skipped_races = 0

    for race_id, race_date, venue_code, race_number in races:
        # 予測データを取得
        predictions = get_race_prediction(db_path, race_id)
        if len(predictions) < 6:
            skipped_races += 1
            continue

        # 結果を取得
        result = get_race_result(db_path, race_id)
        if not result:
            skipped_races += 1
            continue

        # オッズを取得
        odds_data = get_race_odds(db_path, race_id)
        if not odds_data:
            skipped_races += 1
            continue

        # 予測順位で並び替え
        predictions_sorted = sorted(predictions, key=lambda x: x[1])
        predicted_ranks = [p[0] for p in predictions_sorted]
        confidence = predictions_sorted[0][2]  # 1位予想の信頼度

        # 買い目を生成
        all_combos = generate_bet_combinations(predicted_ranks, '1-234-2345')

        # 期待値でソート
        combos_with_ev = []
        for combo in all_combos:
            if combo in odds_data:
                odds = odds_data[combo]
                ev = calculate_ev(odds, confidence)
                combos_with_ev.append({
                    'combo': combo,
                    'odds': odds,
                    'ev': ev
                })

        # 期待値順にソート
        combos_with_ev.sort(key=lambda x: x['ev'], reverse=True)

        # 上位N点を選択
        selected_bets = combos_with_ev[:max_bets]

        if not selected_bets:
            skipped_races += 1
            continue

        # 結果判定
        race_bet_amount = len(selected_bets) * bet_amount
        race_payout = 0
        race_hit = False
        hit_bet = None

        for bet in selected_bets:
            if bet['combo'] == result['actual_combo']:
                race_hit = True
                race_payout = result['payout']
                hit_bet = bet
                break

        # 統計更新
        total_races += 1
        total_bets += len(selected_bets)
        total_bet_amount += race_bet_amount

        if race_hit:
            total_hits += 1
            total_payout += race_payout

        # 日別集計
        daily_stats[race_date]['races'] += 1
        daily_stats[race_date]['bets'] += len(selected_bets)
        daily_stats[race_date]['bet_amount'] += race_bet_amount
        if race_hit:
            daily_stats[race_date]['hits'] += 1
            daily_stats[race_date]['payout'] += race_payout

        # 信頼度別集計
        confidence_stats[confidence]['races'] += 1
        confidence_stats[confidence]['bets'] += len(selected_bets)
        confidence_stats[confidence]['bet_amount'] += race_bet_amount
        if race_hit:
            confidence_stats[confidence]['hits'] += 1
            confidence_stats[confidence]['payout'] += race_payout

        # 期待値別集計
        for bet in selected_bets:
            for ev_min, ev_max, ev_label in ev_ranges:
                if ev_min <= bet['ev'] < ev_max:
                    ev_stats[ev_label]['bets'] += 1
                    ev_stats[ev_label]['bet_amount'] += bet_amount
                    if bet['combo'] == result['actual_combo']:
                        ev_stats[ev_label]['hits'] += 1
                        ev_stats[ev_label]['payout'] += result['payout']
                    break

        # 詳細記録
        daily_details[race_date].append({
            'race_number': race_number,
            'venue_code': venue_code,
            'confidence': confidence,
            'bet_count': len(selected_bets),
            'bet_amount': race_bet_amount,
            'hit': race_hit,
            'payout': race_payout if race_hit else 0,
            'selected_bets': selected_bets[:3],  # 上位3点のみ記録
            'actual_combo': result['actual_combo'],
            'actual_payout': result['payout']
        })

    # 結果出力
    print(f"\n{'='*80}")
    print("総合成績")
    print("=" * 80)
    print(f"対象レース数: {total_races}")
    print(f"スキップ数: {skipped_races} (予測/結果/オッズなし)")
    print(f"総買い目数: {total_bets}")
    print(f"的中数: {total_hits}")
    print(f"的中率: {total_hits/total_races*100:.2f}%" if total_races > 0 else "的中率: N/A")
    print(f"投資額: {total_bet_amount:,}円")
    print(f"払戻額: {total_payout:,}円")
    print(f"収支: {total_payout - total_bet_amount:+,}円")
    print(f"ROI: {total_payout/total_bet_amount*100:.1f}%" if total_bet_amount > 0 else "ROI: N/A")

    # 日別成績
    print(f"\n{'='*80}")
    print("日別成績")
    print("=" * 80)
    print(f"{'日付':<12} {'レース':<6} {'買い目':<8} {'的中':<6} {'投資額':>10} {'払戻':>12} {'収支':>12} {'ROI':>8}")
    print("-" * 80)

    cumulative_bet = 0
    cumulative_payout = 0

    for date in sorted(daily_stats.keys()):
        stats = daily_stats[date]
        roi = stats['payout']/stats['bet_amount']*100 if stats['bet_amount'] > 0 else 0
        profit = stats['payout'] - stats['bet_amount']
        cumulative_bet += stats['bet_amount']
        cumulative_payout += stats['payout']

        print(f"{date:<12} {stats['races']:<6} {stats['bets']:<8} {stats['hits']:<6} "
              f"{stats['bet_amount']:>10,} {stats['payout']:>12,} {profit:>+12,} {roi:>7.1f}%")

    print("-" * 80)
    print(f"{'累計':<12} {total_races:<6} {total_bets:<8} {total_hits:<6} "
          f"{cumulative_bet:>10,} {cumulative_payout:>12,} "
          f"{cumulative_payout - cumulative_bet:>+12,} "
          f"{cumulative_payout/cumulative_bet*100:.1f}%" if cumulative_bet > 0 else "N/A")

    # 信頼度別成績
    print(f"\n{'='*80}")
    print("信頼度別成績")
    print("=" * 80)
    print(f"{'信頼度':<8} {'レース':<8} {'買い目':<8} {'的中':<6} {'的中率':>8} {'投資額':>10} {'払戻':>12} {'ROI':>8}")
    print("-" * 80)

    for conf in ['A', 'B', 'C', 'D', 'E']:
        if conf in confidence_stats:
            stats = confidence_stats[conf]
            hit_rate = stats['hits']/stats['races']*100 if stats['races'] > 0 else 0
            roi = stats['payout']/stats['bet_amount']*100 if stats['bet_amount'] > 0 else 0
            print(f"{conf:<8} {stats['races']:<8} {stats['bets']:<8} {stats['hits']:<6} "
                  f"{hit_rate:>7.1f}% {stats['bet_amount']:>10,} {stats['payout']:>12,} {roi:>7.1f}%")

    # 期待値別成績
    print(f"\n{'='*80}")
    print("期待値別成績")
    print("=" * 80)
    print(f"{'EV範囲':<12} {'買い目':<8} {'的中':<6} {'的中率':>8} {'投資額':>10} {'払戻':>12} {'ROI':>8}")
    print("-" * 80)

    for _, _, ev_label in ev_ranges:
        if ev_label in ev_stats:
            stats = ev_stats[ev_label]
            hit_rate = stats['hits']/stats['bets']*100 if stats['bets'] > 0 else 0
            roi = stats['payout']/stats['bet_amount']*100 if stats['bet_amount'] > 0 else 0
            print(f"{ev_label:<12} {stats['bets']:<8} {stats['hits']:<6} "
                  f"{hit_rate:>7.2f}% {stats['bet_amount']:>10,} {stats['payout']:>12,} {roi:>7.1f}%")

    # 週別サマリー
    print(f"\n{'='*80}")
    print("週別サマリー")
    print("=" * 80)

    weekly_stats = defaultdict(lambda: {
        'races': 0, 'hits': 0, 'bet_amount': 0, 'payout': 0
    })

    for date_str in daily_stats.keys():
        date = datetime.strptime(date_str, '%Y-%m-%d')
        week_num = date.isocalendar()[1]
        week_key = f"Week {week_num} ({date_str[:10]}~)"

        stats = daily_stats[date_str]
        weekly_stats[week_key]['races'] += stats['races']
        weekly_stats[week_key]['hits'] += stats['hits']
        weekly_stats[week_key]['bet_amount'] += stats['bet_amount']
        weekly_stats[week_key]['payout'] += stats['payout']

    print(f"{'週':<25} {'レース':<8} {'的中':<6} {'的中率':>8} {'投資額':>10} {'払戻':>12} {'ROI':>8}")
    print("-" * 80)

    for week in sorted(weekly_stats.keys()):
        stats = weekly_stats[week]
        hit_rate = stats['hits']/stats['races']*100 if stats['races'] > 0 else 0
        roi = stats['payout']/stats['bet_amount']*100 if stats['bet_amount'] > 0 else 0
        profit = stats['payout'] - stats['bet_amount']
        print(f"{week:<25} {stats['races']:<8} {stats['hits']:<6} "
              f"{hit_rate:>7.1f}% {stats['bet_amount']:>10,} {stats['payout']:>12,} {roi:>7.1f}%")

    # 高配当的中一覧
    print(f"\n{'='*80}")
    print("高配当的中一覧（払戻10,000円以上）")
    print("=" * 80)

    high_payouts = []
    for date in daily_details.keys():
        for detail in daily_details[date]:
            if detail['hit'] and detail['payout'] >= 10000:
                high_payouts.append({
                    'date': date,
                    'venue': detail['venue_code'],
                    'race': detail['race_number'],
                    'confidence': detail['confidence'],
                    'payout': detail['payout'],
                    'combo': detail['actual_combo']
                })

    high_payouts.sort(key=lambda x: x['payout'], reverse=True)

    if high_payouts:
        print(f"{'日付':<12} {'会場':>4} {'R':>3} {'信頼度':>6} {'払戻':>12} {'組合せ':<10}")
        print("-" * 60)
        for hp in high_payouts[:20]:  # 上位20件
            print(f"{hp['date']:<12} {hp['venue']:>4} {hp['race']:>3}R "
                  f"{hp['confidence']:>6} {hp['payout']:>12,}円 {hp['combo']:<10}")
    else:
        print("該当なし")

    print(f"\n{'='*80}")
    print("バックテスト完了")
    print("=" * 80)

    return {
        'total_races': total_races,
        'total_bets': total_bets,
        'total_hits': total_hits,
        'total_bet_amount': total_bet_amount,
        'total_payout': total_payout,
        'roi': total_payout/total_bet_amount*100 if total_bet_amount > 0 else 0,
        'daily_stats': dict(daily_stats),
        'confidence_stats': dict(confidence_stats),
        'ev_stats': dict(ev_stats)
    }


if __name__ == '__main__':
    result = run_detailed_backtest(DATABASE_PATH, max_bets=5, bet_amount=100)
