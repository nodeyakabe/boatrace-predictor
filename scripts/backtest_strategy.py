# -*- coding: utf-8 -*-
"""
最終戦略バックテスト

戦略:
- 信頼度B: 新方式 1点買い（全レース）
- 信頼度C: 従来方式 1点買い（オッズ20-50倍のみ）
- 信頼度D: 新方式 1点買い（新方式1-2予測 + オッズ20倍以上）
"""

import sqlite3
import sys
sys.path.insert(0, '.')

from src.second_model import SecondFeaturesGenerator
from src.analysis import CompoundRuleFinder


def run_backtest(start_date, end_date, label):
    print('=' * 70)
    print(f'バックテスト: {label} ({start_date} ~ {end_date})')
    print('=' * 70)

    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    second_gen = SecondFeaturesGenerator()
    rule_finder = CompoundRuleFinder()

    # 結果格納
    results = {
        'B': {'total': 0, 'bet': 0, 'hits': 0, 'win': 0},
        'C': {'total': 0, 'bet': 0, 'hits': 0, 'win': 0},
        'D': {'total': 0, 'bet': 0, 'hits': 0, 'win': 0},
    }

    # レース取得
    cursor.execute('''
        SELECT r.id, r.venue_code, p.confidence,
               e1.racer_rank as c1_rank
        FROM races r
        JOIN race_predictions p ON r.id = p.race_id
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE r.race_date >= ? AND r.race_date <= ?
          AND p.prediction_type = 'advance' AND p.rank_prediction = 1
          AND p.confidence IN ('B', 'C', 'D')
    ''', (start_date, end_date))
    races = cursor.fetchall()

    print(f'対象レース数: {len(races)}')

    for race_id, venue_code, confidence, c1_rank in races:
        # 予測取得
        cursor.execute('''
            SELECT pit_number FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'advance'
            ORDER BY rank_prediction LIMIT 6
        ''', (race_id,))
        preds = [r[0] for r in cursor.fetchall()]
        if len(preds) < 6:
            continue

        # 結果取得
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        actuals = cursor.fetchall()
        if len(actuals) < 3:
            continue

        actual_combo = f'{actuals[0][0]}-{actuals[1][0]}-{actuals[2][0]}'

        # 払戻金
        cursor.execute('''
            SELECT amount FROM payouts
            WHERE race_id = ? AND bet_type = 'trifecta'
        ''', (race_id,))
        payout = cursor.fetchone()
        actual_odds = payout[0] / 100 if payout else 0

        # 事前オッズ
        cursor.execute('''
            SELECT combination, odds FROM trifecta_odds
            WHERE race_id = ?
        ''', (race_id,))
        pre_odds = {r[0]: r[1] for r in cursor.fetchall()}

        # 従来予測
        old_combo = f'{preds[0]}-{preds[1]}-{preds[2]}'
        old_bet_odds = pre_odds.get(old_combo, 0)

        # 新方式予測
        old_1st = preds[0]
        new_1st = old_1st
        rules = rule_finder.get_applicable_rules(race_id, old_1st)
        best_score = max([r.hit_rate for r in rules], default=0)
        for pit in range(1, 7):
            if pit == old_1st:
                continue
            other_rules = rule_finder.get_applicable_rules(race_id, pit)
            for rule in other_rules:
                if rule.hit_rate > best_score + 0.05:
                    new_1st = pit
                    best_score = rule.hit_rate

        candidates = second_gen.rank_second_candidates(race_id, new_1st)
        if candidates and len(candidates) >= 2:
            new_2nd, new_3rd = candidates[0][0], candidates[1][0]
        else:
            new_2nd, new_3rd = preds[1], preds[2]

        new_combo = f'{new_1st}-{new_2nd}-{new_3rd}'
        new_bet_odds = pre_odds.get(new_combo, 0)

        results[confidence]['total'] += 1

        # 信頼度B: 新方式 1点買い（全レース）
        if confidence == 'B':
            results['B']['bet'] += 100
            if new_combo == actual_combo:
                results['B']['hits'] += 1
                results['B']['win'] += actual_odds * 100

        # 信頼度C: 従来方式 1点買い
        # オッズ条件: 20-50倍（オッズデータがある場合のみ適用）
        elif confidence == 'C':
            # オッズデータがない場合は従来方式で全参加
            if old_bet_odds == 0:
                results['C']['bet'] += 100
                if old_combo == actual_combo:
                    results['C']['hits'] += 1
                    results['C']['win'] += actual_odds * 100
            elif old_bet_odds >= 20 and old_bet_odds < 50:
                results['C']['bet'] += 100
                if old_combo == actual_combo:
                    results['C']['hits'] += 1
                    results['C']['win'] += actual_odds * 100

        # 信頼度D: 新方式 1点買い（新方式1-2予測）
        # オッズ条件: 20倍以上（オッズデータがある場合のみ適用）
        elif confidence == 'D':
            if new_1st == 1 and new_2nd == 2:
                if new_bet_odds == 0:
                    # オッズデータなし→条件なしで参加
                    results['D']['bet'] += 100
                    if new_combo == actual_combo:
                        results['D']['hits'] += 1
                        results['D']['win'] += actual_odds * 100
                elif new_bet_odds >= 20:
                    results['D']['bet'] += 100
                    if new_combo == actual_combo:
                        results['D']['hits'] += 1
                        results['D']['win'] += actual_odds * 100

    conn.close()

    # 結果表示
    print()
    print(f"{'信頼度':<10} {'レース数':<10} {'参加数':<10} {'的中':<8} {'投資':<12} {'回収':<12} {'回収率':<10}")
    print('-' * 80)

    total_bet = 0
    total_win = 0

    for conf in ['B', 'C', 'D']:
        r = results[conf]
        if r['bet'] == 0:
            roi = 0
            participated = 0
        else:
            roi = r['win'] / r['bet'] * 100
            participated = r['bet'] // 100

        total_bet += r['bet']
        total_win += r['win']

        print(f"{conf:<10} {r['total']:<10} {participated:<10} {r['hits']:<8} {r['bet']:<12,} {r['win']:<12,.0f} {roi:<10.1f}%")

    print('-' * 80)
    total_roi = total_win / total_bet * 100 if total_bet > 0 else 0
    print(f"{'合計':<10} {'':<10} {total_bet//100:<10} {'':<8} {total_bet:<12,} {total_win:<12,.0f} {total_roi:<10.1f}%")

    return total_bet, total_win


def main():
    # 1月
    bet1, win1 = run_backtest('2025-01-01', '2025-01-31', '2025年1月')

    print()

    # 10月
    bet10, win10 = run_backtest('2025-10-01', '2025-10-31', '2025年10月')

    print()

    # 11月（検証用）
    bet11, win11 = run_backtest('2025-11-01', '2025-11-30', '2025年11月')

    print()
    print('=' * 70)
    print('総合結果')
    print('=' * 70)

    total_bet = bet1 + bet10 + bet11
    total_win = win1 + win10 + win11
    total_roi = total_win / total_bet * 100 if total_bet > 0 else 0

    print(f'総投資: {total_bet:,}円')
    print(f'総回収: {total_win:,.0f}円')
    print(f'総回収率: {total_roi:.1f}%')
    print(f'損益: {total_win - total_bet:+,.0f}円')


if __name__ == "__main__":
    main()
