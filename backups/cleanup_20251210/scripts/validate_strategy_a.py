# -*- coding: utf-8 -*-
"""戦略A（バランス型）の検証

推奨最適戦略Aの実際の成績を2025年データで検証
"""

import sys
import sqlite3
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


def test_tier(cursor, races, tier_name, conditions, bet_amount=300):
    """Tierごとの検証"""
    print(f"\n{'=' * 70}")
    print(f"{tier_name}")
    print('=' * 70)

    tier_stats = {
        'total_target': 0,
        'total_hit': 0,
        'total_bet': 0,
        'total_payout': 0,
    }

    for cond in conditions:
        stats = {
            'target': 0,
            'hit': 0,
            'bet': 0,
            'payout': 0,
        }

        confidence = cond['confidence']
        c1_rank = cond['c1_rank']
        odds_min = cond['odds_min']
        odds_max = cond['odds_max']

        for race in races:
            race_id = race['race_id']

            # 1コース級別
            cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
            c1 = cursor.fetchone()
            c1_rank_actual = c1['racer_rank'] if c1 else 'B1'

            if c1_rank_actual != c1_rank:
                continue

            # 予測情報
            cursor.execute('''
                SELECT pit_number, confidence
                FROM race_predictions
                WHERE race_id = ? AND prediction_type = 'advance'
                ORDER BY rank_prediction
            ''', (race_id,))
            preds = cursor.fetchall()

            if len(preds) < 6:
                continue

            conf_actual = preds[0]['confidence']
            if conf_actual != confidence:
                continue

            pred = [p['pit_number'] for p in preds[:3]]
            combo = f"{pred[0]}-{pred[1]}-{pred[2]}"

            # オッズ取得
            cursor.execute('SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?', (race_id, combo))
            odds_row = cursor.fetchone()
            odds = odds_row['odds'] if odds_row else 0

            if odds < odds_min or odds >= odds_max:
                continue

            stats['target'] += 1
            stats['bet'] += bet_amount

            # 実際の結果
            cursor.execute('''
                SELECT pit_number FROM results
                WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
                ORDER BY rank
            ''', (race_id,))
            results = cursor.fetchall()

            if len(results) >= 3:
                actual_combo = f"{results[0]['pit_number']}-{results[1]['pit_number']}-{results[2]['pit_number']}"

                if combo == actual_combo:
                    # 実際の払戻金を取得
                    cursor.execute('''
                        SELECT amount FROM payouts
                        WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                    ''', (race_id, actual_combo))
                    payout_row = cursor.fetchone()

                    if payout_row:
                        stats['hit'] += 1
                        actual_payout = (bet_amount / 100) * payout_row['amount']
                        stats['payout'] += actual_payout

        # 条件の結果表示
        if stats['target'] > 0:
            roi = stats['payout'] / stats['bet'] * 100
            hit_rate = stats['hit'] / stats['target'] * 100
            profit = stats['payout'] - stats['bet']

            print(f"\n{cond['name']}:")
            print(f"  購入{stats['target']:4d}, 的中{stats['hit']:3d}, 的中率{hit_rate:5.1f}%, ROI {roi:6.1f}%, 収支{profit:+9,.0f}円")

            tier_stats['total_target'] += stats['target']
            tier_stats['total_hit'] += stats['hit']
            tier_stats['total_bet'] += stats['bet']
            tier_stats['total_payout'] += stats['payout']

    # Tier合計
    if tier_stats['total_target'] > 0:
        tier_roi = tier_stats['total_payout'] / tier_stats['total_bet'] * 100
        tier_hit_rate = tier_stats['total_hit'] / tier_stats['total_target'] * 100
        tier_profit = tier_stats['total_payout'] - tier_stats['total_bet']

        print(f"\n{tier_name} 合計:")
        print(f"  購入{tier_stats['total_target']:4d}, 的中{tier_stats['total_hit']:3d}, 的中率{tier_hit_rate:5.1f}%")
        print(f"  ROI {tier_roi:6.1f}%, 収支{tier_profit:+9,.0f}円")

    return tier_stats


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=" * 70)
    print("戦略A（バランス型）の検証")
    print("=" * 70)
    print()

    # 2025年全期間のレース取得
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')
    races = cursor.fetchall()

    print(f"検証期間: 2025年1月〜12月")
    print(f"総レース数: {len(races):,}")

    # Tier 1: 超高配当狙い
    tier1_conditions = [
        {'name': 'D × B1 × 200-300倍', 'confidence': 'D', 'c1_rank': 'B1', 'odds_min': 200, 'odds_max': 300},
        {'name': 'D × A1 × 100-150倍', 'confidence': 'D', 'c1_rank': 'A1', 'odds_min': 100, 'odds_max': 150},
        {'name': 'D × A1 × 200-300倍', 'confidence': 'D', 'c1_rank': 'A1', 'odds_min': 200, 'odds_max': 300},
        {'name': 'C × B1 × 150-200倍', 'confidence': 'C', 'c1_rank': 'B1', 'odds_min': 150, 'odds_max': 200},
    ]

    tier1_stats = test_tier(cursor, races, "Tier 1: 超高配当狙い", tier1_conditions)

    # Tier 2: 中高配当狙い
    tier2_conditions = [
        {'name': 'D × A2 × 30-40倍', 'confidence': 'D', 'c1_rank': 'A2', 'odds_min': 30, 'odds_max': 40},
        {'name': 'D × A1 × 40-50倍', 'confidence': 'D', 'c1_rank': 'A1', 'odds_min': 40, 'odds_max': 50},
        {'name': 'D × A1 × 20-25倍', 'confidence': 'D', 'c1_rank': 'A1', 'odds_min': 20, 'odds_max': 25},
    ]

    tier2_stats = test_tier(cursor, races, "Tier 2: 中高配当狙い", tier2_conditions)

    # Tier 3: 堅実狙い
    tier3_conditions = [
        {'name': 'D × B1 × 5-10倍', 'confidence': 'D', 'c1_rank': 'B1', 'odds_min': 5, 'odds_max': 10},
    ]

    tier3_stats = test_tier(cursor, races, "Tier 3: 堅実狙い", tier3_conditions)

    conn.close()

    # 総合結果
    print(f"\n{'=' * 70}")
    print("戦略A 総合成績")
    print('=' * 70)

    total_target = tier1_stats['total_target'] + tier2_stats['total_target'] + tier3_stats['total_target']
    total_hit = tier1_stats['total_hit'] + tier2_stats['total_hit'] + tier3_stats['total_hit']
    total_bet = tier1_stats['total_bet'] + tier2_stats['total_bet'] + tier3_stats['total_bet']
    total_payout = tier1_stats['total_payout'] + tier2_stats['total_payout'] + tier3_stats['total_payout']

    total_roi = total_payout / total_bet * 100 if total_bet > 0 else 0
    total_hit_rate = total_hit / total_target * 100 if total_target > 0 else 0
    total_profit = total_payout - total_bet

    print(f"\n年間購入: {total_target}レース（月{total_target/12:.1f}レース）")
    print(f"年間的中: {total_hit}回（月{total_hit/12:.1f}回）")
    print(f"的中率: {total_hit_rate:.1f}%")
    print()
    print(f"年間投資: {total_bet:,}円（月{total_bet/12:,.0f}円）")
    print(f"年間払戻: {total_payout:,.0f}円（月{total_payout/12:,.0f}円）")
    print(f"年間収支: {total_profit:+,.0f}円（月{total_profit/12:+,.0f}円）")
    print(f"ROI: {total_roi:.1f}%")

    print(f"\n{'=' * 70}")
    print("目標達成度")
    print('=' * 70)
    print(f"年間収支目標 +300,000円: {total_profit:+,.0f}円 ", end='')
    if total_profit >= 300000:
        print("[OK] 達成")
    elif total_profit >= 200000:
        print("[WARN] やや未達")
    else:
        print("[NG] 未達")

    print(f"月間的中目標 5-10回: 月{total_hit/12:.1f}回 ", end='')
    if total_hit/12 >= 5:
        print("[OK] 達成" if total_hit/12 <= 10 else "[OK] 超過達成")
    elif total_hit/12 >= 3:
        print("[WARN] やや未達")
    else:
        print("[NG] 未達")

    print(f"ROI目標 150%以上: {total_roi:.1f}% ", end='')
    if total_roi >= 150:
        print("[OK] 達成")
    elif total_roi >= 120:
        print("[WARN] やや未達")
    else:
        print("[NG] 未達")

    print('=' * 70)


if __name__ == '__main__':
    main()
