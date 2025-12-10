# -*- coding: utf-8 -*-
"""
買い目戦略の最適化

オッズデータが蓄積されたので、全期間で最適条件を探索する
"""

import sqlite3
import sys
sys.path.insert(0, '.')

from src.second_model import SecondFeaturesGenerator
from src.analysis import CompoundRuleFinder


def run_optimization():
    print('=' * 80)
    print('買い目戦略の最適化分析')
    print('=' * 80)

    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    second_gen = SecondFeaturesGenerator()
    rule_finder = CompoundRuleFinder()

    # オッズデータがあるレースのみ対象（2025年1月〜）
    cursor.execute('''
        SELECT r.id, r.venue_code, r.race_date, p.confidence,
               e1.racer_rank as c1_rank
        FROM races r
        JOIN race_predictions p ON r.id = p.race_id
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE r.race_date >= '2025-01-01'
          AND p.prediction_type = 'advance' AND p.rank_prediction = 1
          AND p.confidence IN ('B', 'C', 'D')
          AND EXISTS (SELECT 1 FROM trifecta_odds t WHERE t.race_id = r.id)
    ''')
    races = cursor.fetchall()

    print(f'オッズ付きレース数: {len(races)}')

    # 条件別に結果を格納
    # キー: (confidence, method, odds_min, odds_max, extra_condition)
    results = {}

    # 条件パターン
    odds_ranges = [
        (0, 999, 'all'),
        (10, 20, '10-20'),
        (15, 30, '15-30'),
        (20, 40, '20-40'),
        (20, 50, '20-50'),
        (25, 50, '25-50'),
        (30, 60, '30-60'),
        (20, 999, '20+'),
        (30, 999, '30+'),
        (50, 999, '50+'),
    ]

    for race_id, venue_code, race_date, confidence, c1_rank in races:
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

        # 各条件で集計
        for method in ['old', 'new']:
            combo = old_combo if method == 'old' else new_combo
            bet_odds = old_bet_odds if method == 'old' else new_bet_odds
            hit = (combo == actual_combo)

            for odds_min, odds_max, odds_label in odds_ranges:
                # オッズ条件チェック
                if bet_odds == 0:
                    continue
                if bet_odds < odds_min or bet_odds >= odds_max:
                    continue

                # 追加条件パターン
                extra_conditions = [('none', True)]

                # 新方式のみ: 1-2予測条件
                if method == 'new':
                    extra_conditions.append(('1-2pred', new_1st == 1 and new_2nd == 2))
                    extra_conditions.append(('1C_win', new_1st == 1))

                # 1コースランク条件
                extra_conditions.append(('c1_A1', c1_rank == 'A1'))
                extra_conditions.append(('c1_A', c1_rank in ['A1', 'A2']))

                for extra_name, extra_match in extra_conditions:
                    if not extra_match:
                        continue

                    key = (confidence, method, odds_label, extra_name)
                    if key not in results:
                        results[key] = {'total': 0, 'hits': 0, 'payout': 0}

                    results[key]['total'] += 1
                    if hit:
                        results[key]['hits'] += 1
                        results[key]['payout'] += actual_odds

    conn.close()

    # 結果表示
    print()
    print('=' * 100)
    print('信頼度別・条件別の回収率')
    print('=' * 100)

    for conf in ['B', 'C', 'D']:
        print(f'\n【信頼度{conf}】')
        print(f"{'方式':<8} {'オッズ':<10} {'条件':<12} {'件数':<8} {'的中':<6} {'的中率':<10} {'回収率':<10}")
        print('-' * 70)

        conf_results = [(k, v) for k, v in results.items() if k[0] == conf]
        # 回収率でソート
        conf_results.sort(key=lambda x: x[1]['payout'] / x[1]['total'] if x[1]['total'] > 0 else 0, reverse=True)

        for key, r in conf_results:
            if r['total'] < 20:  # 最低20件
                continue
            method = '従来' if key[1] == 'old' else '新方式'
            odds_label = key[2]
            extra = key[3]
            hit_rate = r['hits'] / r['total'] * 100
            roi = r['payout'] / r['total'] * 100

            print(f"{method:<8} {odds_label:<10} {extra:<12} {r['total']:<8} {r['hits']:<6} {hit_rate:<10.1f}% {roi:<10.1f}%")

    # 回収率100%超えの条件をまとめ
    print()
    print('=' * 100)
    print('回収率100%超えの条件（20件以上）')
    print('=' * 100)
    print(f"{'信頼度':<8} {'方式':<8} {'オッズ':<10} {'条件':<12} {'件数':<8} {'的中率':<10} {'回収率':<10}")
    print('-' * 70)

    profitable = []
    for key, r in results.items():
        if r['total'] >= 20:
            roi = r['payout'] / r['total'] * 100
            if roi >= 100:
                profitable.append((key, r, roi))

    profitable.sort(key=lambda x: x[2], reverse=True)

    for key, r, roi in profitable:
        conf = key[0]
        method = '従来' if key[1] == 'old' else '新方式'
        odds_label = key[2]
        extra = key[3]
        hit_rate = r['hits'] / r['total'] * 100
        print(f"{conf:<8} {method:<8} {odds_label:<10} {extra:<12} {r['total']:<8} {hit_rate:<10.1f}% {roi:<10.1f}%")

    # 最適戦略の推奨
    print()
    print('=' * 100)
    print('推奨戦略（信頼度別ベスト）')
    print('=' * 100)

    for conf in ['B', 'C', 'D']:
        conf_profitable = [p for p in profitable if p[0][0] == conf]
        if conf_profitable:
            best = conf_profitable[0]
            key, r, roi = best
            method = '従来' if key[1] == 'old' else '新方式'
            print(f"\n【信頼度{conf}】")
            print(f"  方式: {method}")
            print(f"  オッズ: {key[2]}")
            print(f"  条件: {key[3]}")
            print(f"  件数: {r['total']}")
            print(f"  的中率: {r['hits'] / r['total'] * 100:.1f}%")
            print(f"  回収率: {roi:.1f}%")
        else:
            print(f"\n【信頼度{conf}】100%超えの条件なし")


if __name__ == "__main__":
    run_optimization()
