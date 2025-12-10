# -*- coding: utf-8 -*-
"""実運用パフォーマンスモニタリングツール

戦略Aの実運用成績を追跡し、問題を早期発見
"""

import sys
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


# 戦略A の条件定義
STRATEGY_A_CONDITIONS = [
    # Tier 1: 超高配当狙い
    {'tier': 1, 'name': 'D x B1 x 200-300倍', 'confidence': 'D', 'c1_rank': 'B1', 'odds_min': 200, 'odds_max': 300, 'expected_roi': 838.4, 'bet_amount': 300},
    {'tier': 1, 'name': 'D x A1 x 100-150倍', 'confidence': 'D', 'c1_rank': 'A1', 'odds_min': 100, 'odds_max': 150, 'expected_roi': 425.5, 'bet_amount': 300},
    {'tier': 1, 'name': 'D x A1 x 200-300倍', 'confidence': 'D', 'c1_rank': 'A1', 'odds_min': 200, 'odds_max': 300, 'expected_roi': 397.9, 'bet_amount': 300},
    {'tier': 1, 'name': 'C x B1 x 150-200倍', 'confidence': 'C', 'c1_rank': 'B1', 'odds_min': 150, 'odds_max': 200, 'expected_roi': 376.3, 'bet_amount': 300},

    # Tier 2: 中高配当狙い
    {'tier': 2, 'name': 'D x A2 x 30-40倍', 'confidence': 'D', 'c1_rank': 'A2', 'odds_min': 30, 'odds_max': 40, 'expected_roi': 273.9, 'bet_amount': 300},
    {'tier': 2, 'name': 'D x A1 x 40-50倍', 'confidence': 'D', 'c1_rank': 'A1', 'odds_min': 40, 'odds_max': 50, 'expected_roi': 537.8, 'bet_amount': 300},
    {'tier': 2, 'name': 'D x A1 x 20-25倍', 'confidence': 'D', 'c1_rank': 'A1', 'odds_min': 20, 'odds_max': 25, 'expected_roi': 277.9, 'bet_amount': 300},

    # Tier 3: 堅実狙い
    {'tier': 3, 'name': 'D x B1 x 5-10倍', 'confidence': 'D', 'c1_rank': 'B1', 'odds_min': 5, 'odds_max': 10, 'expected_roi': 111.1, 'bet_amount': 300},
]


def evaluate_condition(cursor, races, condition):
    """特定条件の成績を評価"""
    stats = {
        'target': 0,
        'hit': 0,
        'bet': 0,
        'payout': 0,
        'consecutive_losses': 0,
        'max_consecutive_losses': 0,
        'current_streak': 0,
    }

    for race in races:
        race_id = race['race_id']

        # 1コース級別チェック
        cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
        c1 = cursor.fetchone()
        c1_rank_actual = c1['racer_rank'] if c1 else 'B1'

        if c1_rank_actual != condition['c1_rank']:
            continue

        # 予測情報取得
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
        if conf_actual != condition['confidence']:
            continue

        pred = [p['pit_number'] for p in preds[:3]]
        combo = f"{pred[0]}-{pred[1]}-{pred[2]}"

        # オッズ取得
        cursor.execute('SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?', (race_id, combo))
        odds_row = cursor.fetchone()
        odds = odds_row['odds'] if odds_row else 0

        if odds < condition['odds_min'] or odds >= condition['odds_max']:
            continue

        stats['target'] += 1
        stats['bet'] += condition['bet_amount']

        # 実際の結果
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        results = cursor.fetchall()

        hit = False
        if len(results) >= 3:
            actual_combo = f"{results[0]['pit_number']}-{results[1]['pit_number']}-{results[2]['pit_number']}"

            if combo == actual_combo:
                # 実際の払戻金取得
                cursor.execute('''
                    SELECT amount FROM payouts
                    WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                ''', (race_id, actual_combo))
                payout_row = cursor.fetchone()

                if payout_row:
                    stats['hit'] += 1
                    actual_payout = (condition['bet_amount'] / 100) * payout_row['amount']
                    stats['payout'] += actual_payout
                    hit = True
                    stats['current_streak'] = 0

        if not hit:
            stats['current_streak'] += 1
            stats['max_consecutive_losses'] = max(stats['max_consecutive_losses'], stats['current_streak'])

    if stats['target'] > 0:
        stats['roi'] = stats['payout'] / stats['bet'] * 100
        stats['hit_rate'] = stats['hit'] / stats['target'] * 100
        stats['profit'] = stats['payout'] - stats['bet']
    else:
        stats['roi'] = 0
        stats['hit_rate'] = 0
        stats['profit'] = 0

    return stats


def generate_alerts(condition_stats):
    """アラート生成"""
    alerts = []

    for cond, stats in condition_stats.items():
        # アラート1: ROI 100%未満
        if stats['target'] >= 20 and stats['roi'] < 100:
            alerts.append({
                'level': 'WARNING',
                'condition': cond,
                'message': f"ROI {stats['roi']:.1f}%が100%未満（購入{stats['target']}レース）",
                'recommendation': '一時停止を検討'
            })

        # アラート2: 5連敗以上
        if stats['max_consecutive_losses'] >= 5:
            alerts.append({
                'level': 'CRITICAL',
                'condition': cond,
                'message': f"最大連敗{stats['max_consecutive_losses']}回",
                'recommendation': '1週間休止を推奨'
            })

        # アラート3: 期待ROIの50%未満
        expected_roi = next((c['expected_roi'] for c in STRATEGY_A_CONDITIONS if c['name'] == cond), None)
        if expected_roi and stats['target'] >= 20 and stats['roi'] < expected_roi * 0.5:
            alerts.append({
                'level': 'WARNING',
                'condition': cond,
                'message': f"ROI {stats['roi']:.1f}%が期待値{expected_roi:.1f}%の半分未満",
                'recommendation': '条件の見直しを検討'
            })

    return alerts


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=" * 80)
    print("戦略A 実運用モニタリングレポート")
    print("=" * 80)
    print()

    # 監視期間の設定（デフォルト: 直近30日）
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)

    print(f"監視期間: {start_date.strftime('%Y-%m-%d')} 〜 {end_date.strftime('%Y-%m-%d')}")
    print()

    # レース取得
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= ? AND r.race_date <= ?
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''', (start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')))
    races = cursor.fetchall()

    print(f"総レース数: {len(races):,}")
    print()

    # Tier別統計
    tier_stats = defaultdict(lambda: {
        'target': 0, 'hit': 0, 'bet': 0, 'payout': 0
    })

    # 条件別評価
    condition_stats = {}

    for condition in STRATEGY_A_CONDITIONS:
        stats = evaluate_condition(cursor, races, condition)
        condition_stats[condition['name']] = stats

        # Tier統計に集約
        tier_stats[condition['tier']]['target'] += stats['target']
        tier_stats[condition['tier']]['hit'] += stats['hit']
        tier_stats[condition['tier']]['bet'] += stats['bet']
        tier_stats[condition['tier']]['payout'] += stats['payout']

    # Tier別サマリー表示
    print("=" * 80)
    print("Tier別成績サマリー")
    print("=" * 80)
    print()

    tier_names = {1: 'Tier 1: 超高配当狙い', 2: 'Tier 2: 中高配当狙い', 3: 'Tier 3: 堅実狙い'}

    total_stats = {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0}

    for tier in [1, 2, 3]:
        stats = tier_stats[tier]
        if stats['target'] > 0:
            roi = stats['payout'] / stats['bet'] * 100
            hit_rate = stats['hit'] / stats['target'] * 100
            profit = stats['payout'] - stats['bet']

            print(f"{tier_names[tier]}:")
            print(f"  購入: {stats['target']:4d}レース, 的中: {stats['hit']:3d}回 ({hit_rate:5.1f}%)")
            print(f"  投資: {stats['bet']:,}円, 払戻: {stats['payout']:,.0f}円")
            print(f"  収支: {profit:+,.0f}円, ROI: {roi:6.1f}%")
            print()

            total_stats['target'] += stats['target']
            total_stats['hit'] += stats['hit']
            total_stats['bet'] += stats['bet']
            total_stats['payout'] += stats['payout']

    # 総合成績
    if total_stats['target'] > 0:
        total_roi = total_stats['payout'] / total_stats['bet'] * 100
        total_hit_rate = total_stats['hit'] / total_stats['target'] * 100
        total_profit = total_stats['payout'] - total_stats['bet']

        print("=" * 80)
        print("総合成績")
        print("=" * 80)
        print(f"購入: {total_stats['target']:4d}レース")
        print(f"的中: {total_stats['hit']:3d}回 ({total_hit_rate:.1f}%)")
        print(f"投資: {total_stats['bet']:,}円")
        print(f"払戻: {total_stats['payout']:,.0f}円")
        print(f"収支: {total_profit:+,.0f}円")
        print(f"ROI: {total_roi:.1f}%")
        print()

    # 条件別詳細
    print("=" * 80)
    print("条件別詳細（ROI順）")
    print("=" * 80)
    print()

    sorted_conditions = sorted(
        condition_stats.items(),
        key=lambda x: x[1]['roi'] if x[1]['target'] >= 5 else 0,
        reverse=True
    )

    for cond_name, stats in sorted_conditions:
        if stats['target'] > 0:
            print(f"{cond_name}:")
            print(f"  購入{stats['target']:4d}, 的中{stats['hit']:3d} ({stats['hit_rate']:5.1f}%), ", end='')
            print(f"ROI {stats['roi']:6.1f}%, 収支{stats['profit']:+9,.0f}円")
            print(f"  最大連敗: {stats['max_consecutive_losses']}回")
            print()

    # アラート生成
    alerts = generate_alerts(condition_stats)

    if alerts:
        print("=" * 80)
        print(f"アラート ({len(alerts)}件)")
        print("=" * 80)
        print()

        for alert in alerts:
            level_marker = "[CRITICAL]" if alert['level'] == 'CRITICAL' else "[WARNING]"
            print(f"{level_marker} {alert['condition']}")
            print(f"  問題: {alert['message']}")
            print(f"  推奨: {alert['recommendation']}")
            print()
    else:
        print("=" * 80)
        print("アラート: なし（正常稼働中）")
        print("=" * 80)
        print()

    conn.close()

    # 目標達成度評価（月間換算）
    if total_stats['target'] > 0:
        days = (end_date - start_date).days
        monthly_profit = total_profit * (30 / days) if days > 0 else 0
        monthly_hits = total_stats['hit'] * (30 / days) if days > 0 else 0

        print("=" * 80)
        print("月間目標達成度（30日換算）")
        print("=" * 80)
        print()
        print(f"月間収支目標 +25,000円: {monthly_profit:+,.0f}円 ", end='')
        if monthly_profit >= 25000:
            print("[OK] 達成")
        elif monthly_profit >= 15000:
            print("[WARN] やや未達")
        else:
            print("[NG] 未達")

        print(f"月間的中目標 2-3回: {monthly_hits:.1f}回 ", end='')
        if monthly_hits >= 2:
            print("[OK] 達成")
        elif monthly_hits >= 1:
            print("[WARN] やや未達")
        else:
            print("[NG] 未達")

        print(f"ROI目標 250%以上: {total_roi:.1f}% ", end='')
        if total_roi >= 250:
            print("[OK] 達成")
        elif total_roi >= 150:
            print("[WARN] やや未達")
        else:
            print("[NG] 未達")

        print()

    print("=" * 80)
    print("レポート生成日時:", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print("=" * 80)


if __name__ == '__main__':
    main()
