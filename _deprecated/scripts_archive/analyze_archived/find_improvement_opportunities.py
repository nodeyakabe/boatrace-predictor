# -*- coding: utf-8 -*-
"""改善機会の発見

戦略Aを超える条件の探索と、安定性向上策の検討
"""

import sys
import sqlite3
from pathlib import Path
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


def evaluate_condition_with_stability(cursor, races, condition):
    """条件を安定性指標込みで評価"""
    stats = {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0}
    monthly_stats = defaultdict(lambda: {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0})

    # 連敗・連勝追跡
    max_consecutive_losses = 0
    max_consecutive_wins = 0
    current_loss_streak = 0
    current_win_streak = 0

    for race in races:
        race_id = race['race_id']
        race_date = race['race_date']
        month = race_date[:7]

        # 1コース級別
        cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
        c1 = cursor.fetchone()
        c1_rank_actual = c1['racer_rank'] if c1 else 'B1'

        if c1_rank_actual != condition['c1_rank']:
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
        stats['bet'] += 300
        monthly_stats[month]['target'] += 1
        monthly_stats[month]['bet'] += 300

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
                cursor.execute('''
                    SELECT amount FROM payouts
                    WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                ''', (race_id, actual_combo))
                payout_row = cursor.fetchone()

                if payout_row:
                    stats['hit'] += 1
                    actual_payout = (300 / 100) * payout_row['amount']
                    stats['payout'] += actual_payout
                    monthly_stats[month]['hit'] += 1
                    monthly_stats[month]['payout'] += actual_payout
                    hit = True

                    # 連勝更新
                    current_win_streak += 1
                    max_consecutive_wins = max(max_consecutive_wins, current_win_streak)
                    current_loss_streak = 0

        if not hit:
            current_loss_streak += 1
            max_consecutive_losses = max(max_consecutive_losses, current_loss_streak)
            current_win_streak = 0

    # 安定性指標計算
    if stats['target'] > 0:
        roi = stats['payout'] / stats['bet'] * 100
        hit_rate = stats['hit'] / stats['target'] * 100
        profit = stats['payout'] - stats['bet']

        # 月別安定性
        monthly_rois = []
        monthly_profits = []
        black_months = 0
        for m_stats in monthly_stats.values():
            if m_stats['target'] >= 3:  # 3レース以上の月のみ
                m_roi = m_stats['payout'] / m_stats['bet'] * 100 if m_stats['bet'] > 0 else 0
                m_profit = m_stats['payout'] - m_stats['bet']
                monthly_rois.append(m_roi)
                monthly_profits.append(m_profit)
                if m_profit > 0:
                    black_months += 1

        # ROI標準偏差（安定性の指標）
        import statistics
        roi_std = statistics.stdev(monthly_rois) if len(monthly_rois) >= 2 else 0

        # 安定性スコア（高いほど安定）
        # = 黒字月率 × (1 - 連敗リスク) × ROI一貫性
        black_month_rate = black_months / len(monthly_rois) if monthly_rois else 0
        loss_streak_penalty = min(max_consecutive_losses / 50, 1.0)  # 50連敗で最悪
        roi_consistency = max(0, 1 - (roi_std / 200))  # 標準偏差200%で最悪

        stability_score = black_month_rate * (1 - loss_streak_penalty) * roi_consistency * 100

        return {
            'target': stats['target'],
            'hit': stats['hit'],
            'hit_rate': hit_rate,
            'roi': roi,
            'profit': profit,
            'max_consecutive_losses': max_consecutive_losses,
            'max_consecutive_wins': max_consecutive_wins,
            'black_months': black_months,
            'total_months': len(monthly_rois),
            'black_month_rate': black_month_rate * 100,
            'roi_std': roi_std,
            'stability_score': stability_score,
        }
    else:
        return None


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=" * 80)
    print("改善機会の発見")
    print("=" * 80)
    print()

    # 2025年全期間のレース取得
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')
    races = cursor.fetchall()

    print(f"検証期間: 2025年全期間（{len(races):,}レース）")
    print()

    # 探索する条件
    # 1. 信頼度Bの有望条件
    # 2. 戦略Aの条件を微調整（オッズ範囲の拡張など）
    # 3. 複合条件（会場条件など）

    candidates = []

    print("=" * 80)
    print("探索1: 信頼度B（解禁候補）の詳細評価")
    print("=" * 80)
    print()

    confidence_b_conditions = [
        {'name': 'B x A1 x 15-20倍', 'confidence': 'B', 'c1_rank': 'A1', 'odds_min': 15, 'odds_max': 20},
        {'name': 'B x A1 x 20-25倍', 'confidence': 'B', 'c1_rank': 'A1', 'odds_min': 20, 'odds_max': 25},
        {'name': 'B x A1 x 25-30倍', 'confidence': 'B', 'c1_rank': 'A1', 'odds_min': 25, 'odds_max': 30},
        {'name': 'B x A2 x 15-20倍', 'confidence': 'B', 'c1_rank': 'A2', 'odds_min': 15, 'odds_max': 20},
        {'name': 'B x A2 x 20-25倍', 'confidence': 'B', 'c1_rank': 'A2', 'odds_min': 20, 'odds_max': 25},
        {'name': 'B x A2 x 25-30倍', 'confidence': 'B', 'c1_rank': 'A2', 'odds_min': 25, 'odds_max': 30},
        {'name': 'B x A1 x 30-40倍', 'confidence': 'B', 'c1_rank': 'A1', 'odds_min': 30, 'odds_max': 40},
        {'name': 'B x A2 x 30-40倍', 'confidence': 'B', 'c1_rank': 'A2', 'odds_min': 30, 'odds_max': 40},
    ]

    for condition in confidence_b_conditions:
        result = evaluate_condition_with_stability(cursor, races, condition)
        if result and result['target'] >= 20:  # 20レース以上
            candidates.append({
                'condition': condition,
                'result': result,
                'category': '信頼度B',
            })

            print(f"{condition['name']}:")
            print(f"  購入{result['target']:4d}, 的中{result['hit']:3d}, ROI {result['roi']:6.1f}%, 収支{result['profit']:+9,.0f}円")
            print(f"  安定性スコア: {result['stability_score']:.1f}, 黒字月率: {result['black_month_rate']:.1f}%")
            print(f"  最大連敗: {result['max_consecutive_losses']}回, ROI標準偏差: {result['roi_std']:.1f}")
            print()

    # 探索2: 戦略A条件の拡張版
    print("=" * 80)
    print("探索2: 戦略A条件の微調整（オッズ範囲拡張）")
    print("=" * 80)
    print()

    extended_conditions = [
        # Tier 2の拡張
        {'name': 'D x A1 x 15-20倍', 'confidence': 'D', 'c1_rank': 'A1', 'odds_min': 15, 'odds_max': 20},
        {'name': 'D x A1 x 25-30倍', 'confidence': 'D', 'c1_rank': 'A1', 'odds_min': 25, 'odds_max': 30},
        {'name': 'D x A2 x 20-25倍', 'confidence': 'D', 'c1_rank': 'A2', 'odds_min': 20, 'odds_max': 25},
        {'name': 'D x A2 x 25-30倍', 'confidence': 'D', 'c1_rank': 'A2', 'odds_min': 25, 'odds_max': 30},
        {'name': 'D x A2 x 40-50倍', 'confidence': 'D', 'c1_rank': 'A2', 'odds_min': 40, 'odds_max': 50},

        # Tier 3の拡張
        {'name': 'D x B1 x 10-15倍', 'confidence': 'D', 'c1_rank': 'B1', 'odds_min': 10, 'odds_max': 15},
        {'name': 'D x A1 x 5-10倍', 'confidence': 'D', 'c1_rank': 'A1', 'odds_min': 5, 'odds_max': 10},
        {'name': 'D x A2 x 5-10倍', 'confidence': 'D', 'c1_rank': 'A2', 'odds_min': 5, 'odds_max': 10},
        {'name': 'D x A2 x 10-15倍', 'confidence': 'D', 'c1_rank': 'A2', 'odds_min': 10, 'odds_max': 15},

        # Tier 1の拡張
        {'name': 'D x A1 x 70-100倍', 'confidence': 'D', 'c1_rank': 'A1', 'odds_min': 70, 'odds_max': 100},
        {'name': 'D x A1 x 150-200倍', 'confidence': 'D', 'c1_rank': 'A1', 'odds_min': 150, 'odds_max': 200},
        {'name': 'D x B1 x 100-150倍', 'confidence': 'D', 'c1_rank': 'B1', 'odds_min': 100, 'odds_max': 150},
        {'name': 'D x B1 x 150-200倍', 'confidence': 'D', 'c1_rank': 'B1', 'odds_min': 150, 'odds_max': 200},
    ]

    for condition in extended_conditions:
        result = evaluate_condition_with_stability(cursor, races, condition)
        if result and result['target'] >= 20:
            candidates.append({
                'condition': condition,
                'result': result,
                'category': '戦略A拡張',
            })

            print(f"{condition['name']}:")
            print(f"  購入{result['target']:4d}, 的中{result['hit']:3d}, ROI {result['roi']:6.1f}%, 収支{result['profit']:+9,.0f}円")
            print(f"  安定性スコア: {result['stability_score']:.1f}, 黒字月率: {result['black_month_rate']:.1f}%")
            print(f"  最大連敗: {result['max_consecutive_losses']}回, ROI標準偏差: {result['roi_std']:.1f}")
            print()

    conn.close()

    # 改善候補のランキング
    print("=" * 80)
    print("改善候補ランキング（安定性スコア順）")
    print("=" * 80)
    print()

    # ROI 150%以上かつ安定性スコア30以上
    promising = [c for c in candidates if c['result']['roi'] >= 150 and c['result']['stability_score'] >= 30]
    promising.sort(key=lambda x: x['result']['stability_score'], reverse=True)

    print("条件: ROI 150%以上 かつ 安定性スコア30以上")
    print()

    if promising:
        for i, candidate in enumerate(promising[:10], 1):
            cond = candidate['condition']
            res = candidate['result']
            print(f"{i:2d}. {cond['name']} ({candidate['category']})")
            print(f"    ROI {res['roi']:6.1f}%, 収支{res['profit']:+9,.0f}円, 安定性{res['stability_score']:.1f}")
            print(f"    購入{res['target']:4d}, 的中{res['hit']:3d}, 黒字月率{res['black_month_rate']:.1f}%, 最大連敗{res['max_consecutive_losses']:3d}回")
            print()
    else:
        print("該当なし")

    print()
    print("=" * 80)
    print("推奨アクション")
    print("=" * 80)
    print()

    if promising:
        top3 = promising[:3]
        print("即追加推奨（TOP 3）:")
        for i, candidate in enumerate(top3, 1):
            cond = candidate['condition']
            res = candidate['result']
            print(f"  {i}. {cond['name']}")
            print(f"     → 年間+{res['profit']:,.0f}円, ROI {res['roi']:.1f}%, 安定性{res['stability_score']:.1f}")
    else:
        print("現時点では追加推奨条件なし。")
        print("戦略A（8条件）を維持することを推奨。")

    print()
    print("=" * 80)


if __name__ == '__main__':
    main()
