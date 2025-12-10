# -*- coding: utf-8 -*-
"""
信頼度C: 条件別回収率検証
"""

import sqlite3
import sys
sys.path.insert(0, '.')

from src.second_model import SecondFeaturesGenerator
from src.analysis import CompoundRuleFinder


def main():
    print('=' * 70)
    print('信頼度C: 条件別回収率検証')
    print('=' * 70)

    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    second_gen = SecondFeaturesGenerator()
    rule_finder = CompoundRuleFinder()

    # Cレースを取得
    cursor.execute('''
        SELECT r.id, r.venue_code,
               e1.racer_rank as c1_rank,
               e1.win_rate as c1_winrate
        FROM races r
        JOIN race_predictions p ON r.id = p.race_id
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE r.race_date LIKE '2025-11%'
          AND p.prediction_type = 'advance' AND p.rank_prediction = 1
          AND p.confidence = 'C'
    ''')
    races = cursor.fetchall()

    print(f'信頼度Cレース数: {len(races)}')

    # 条件別に集計
    conditions = {
        'all': {'old': {'t': 0, 'h': 0, 'o': 0}, 'new': {'t': 0, 'h': 0, 'o': 0}},
        'c1_a1': {'old': {'t': 0, 'h': 0, 'o': 0}, 'new': {'t': 0, 'h': 0, 'o': 0}},
        'c1_a': {'old': {'t': 0, 'h': 0, 'o': 0}, 'new': {'t': 0, 'h': 0, 'o': 0}},
        'odds_u20': {'old': {'t': 0, 'h': 0, 'o': 0}, 'new': {'t': 0, 'h': 0, 'o': 0}},
        'odds_20_50': {'old': {'t': 0, 'h': 0, 'o': 0}, 'new': {'t': 0, 'h': 0, 'o': 0}},
        'odds_50p': {'old': {'t': 0, 'h': 0, 'o': 0}, 'new': {'t': 0, 'h': 0, 'o': 0}},
        'c1_a1_u20': {'old': {'t': 0, 'h': 0, 'o': 0}, 'new': {'t': 0, 'h': 0, 'o': 0}},
        'new_12': {'old': {'t': 0, 'h': 0, 'o': 0}, 'new': {'t': 0, 'h': 0, 'o': 0}},
        'high_score': {'old': {'t': 0, 'h': 0, 'o': 0}, 'new': {'t': 0, 'h': 0, 'o': 0}},
    }

    for race_id, venue_code, c1_rank, c1_winrate in races:
        # 予測取得
        cursor.execute('''
            SELECT pit_number, total_score FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'advance'
            ORDER BY rank_prediction LIMIT 6
        ''', (race_id,))
        pred_rows = cursor.fetchall()
        if len(pred_rows) < 6:
            continue

        preds = [r[0] for r in pred_rows]
        score_1st = pred_rows[0][1] or 0
        score_2nd = pred_rows[1][1] or 0
        score_diff = score_1st - score_2nd

        # 結果取得
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        actuals = cursor.fetchall()
        if len(actuals) < 3:
            continue

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
        actual_combo = f'{actuals[0][0]}-{actuals[1][0]}-{actuals[2][0]}'

        old_hit = (old_combo == actual_combo)
        new_hit = (new_combo == actual_combo)

        def add_result(key):
            conditions[key]['old']['t'] += 1
            conditions[key]['new']['t'] += 1
            if old_hit:
                conditions[key]['old']['h'] += 1
                conditions[key]['old']['o'] += actual_odds
            if new_hit:
                conditions[key]['new']['h'] += 1
                conditions[key]['new']['o'] += actual_odds

        # 全体
        add_result('all')

        # 1コースA1
        if c1_rank == 'A1':
            add_result('c1_a1')

        # 1コースA級
        if c1_rank in ['A1', 'A2']:
            add_result('c1_a')

        # オッズ別
        if old_bet_odds > 0 and old_bet_odds < 20:
            add_result('odds_u20')
        elif old_bet_odds >= 20 and old_bet_odds < 50:
            add_result('odds_20_50')
        elif old_bet_odds >= 50:
            add_result('odds_50p')

        # 1コースA1 + オッズ20倍未満
        if c1_rank == 'A1' and old_bet_odds > 0 and old_bet_odds < 20:
            add_result('c1_a1_u20')

        # 新方式で1-2予測
        if new_1st == 1 and new_2nd == 2:
            add_result('new_12')

        # スコア差大きい（高信頼）
        if score_diff >= 10:
            add_result('high_score')

    conn.close()

    # 結果表示
    print()
    print(f"{'条件':<30} {'方式':<8} {'件数':<8} {'的中':<6} {'的中率':<10} {'回収率':<10}")
    print('-' * 80)

    labels = {
        'all': '全C',
        'c1_a1': '1コースA1',
        'c1_a': '1コースA級',
        'odds_u20': 'オッズ20倍未満',
        'odds_20_50': 'オッズ20-50倍',
        'odds_50p': 'オッズ50倍以上',
        'c1_a1_u20': '1コースA1 + オッズ<20',
        'new_12': '新方式で1-2予測',
        'high_score': 'スコア差10以上',
    }

    for key, label in labels.items():
        for method in ['old', 'new']:
            r = conditions[key][method]
            if r['t'] == 0:
                continue
            hit_rate = r['h'] / r['t'] * 100
            roi = r['o'] / r['t'] * 100
            m_label = '従来' if method == 'old' else '新方式'
            print(f"{label:<30} {m_label:<8} {r['t']:<8} {r['h']:<6} {hit_rate:<10.1f}% {roi:<10.1f}%")
        print()

    # 最適条件を探す
    print('=' * 70)
    print('回収率100%超えの条件')
    print('=' * 70)
    for key, label in labels.items():
        for method in ['old', 'new']:
            r = conditions[key][method]
            if r['t'] >= 10:  # 最低10件
                roi = r['o'] / r['t'] * 100
                if roi >= 100:
                    m_label = '従来' if method == 'old' else '新方式'
                    print(f"  {label} ({m_label}): {roi:.1f}%")


if __name__ == "__main__":
    main()
