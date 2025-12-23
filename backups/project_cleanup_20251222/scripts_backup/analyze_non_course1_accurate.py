# -*- coding: utf-8 -*-
"""
非1コース予測の正確な分析

矛盾解消のための正確な分析スクリプト:
- prediction_type = 'before'（直前情報）を使用
- BetTargetEvaluatorの条件を適用
- 1コース予測 vs 非1コース予測のROI貢献度を正確に測定

2025-12-16 作成
"""
import sys
import sqlite3
from pathlib import Path
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus


def main():
    db_path = ROOT_DIR / 'data' / 'boatrace.db'
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    evaluator = BetTargetEvaluator()

    # 2025年1月〜11月のレースを取得
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-11-30'
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')
    races = cursor.fetchall()

    # 1コース予測の統計
    course1_stats = {
        'count': 0,
        'hit': 0,
        'bet': 0,
        'payout': 0,
        'by_confidence': defaultdict(lambda: {'count': 0, 'hit': 0, 'bet': 0, 'payout': 0}),
        'by_odds_range': defaultdict(lambda: {'count': 0, 'hit': 0, 'bet': 0, 'payout': 0}),
    }

    # 非1コース予測の統計
    non_course1_stats = {
        'count': 0,
        'hit': 0,
        'bet': 0,
        'payout': 0,
        'by_confidence': defaultdict(lambda: {'count': 0, 'hit': 0, 'bet': 0, 'payout': 0}),
        'by_odds_range': defaultdict(lambda: {'count': 0, 'hit': 0, 'bet': 0, 'payout': 0}),
        'by_top_course': defaultdict(lambda: {'count': 0, 'hit': 0, 'bet': 0, 'payout': 0}),
    }

    # 非1コース予測の詳細
    non_course1_details = []

    for race in races:
        race_id = race['race_id']
        venue_code = int(race['venue_code']) if race['venue_code'] else 0
        race_date = race['race_date']

        # 1コース級別を取得
        cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
        c1 = cursor.fetchone()
        c1_rank = c1['racer_rank'] if c1 else 'B1'

        # 予測情報を取得（直前情報 = before）
        cursor.execute('''
            SELECT pit_number, confidence, total_score
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'before'
            ORDER BY total_score DESC
        ''', (race_id,))
        preds_rows = cursor.fetchall()

        if len(preds_rows) < 6:
            continue

        # 予測情報
        confidence = preds_rows[0]['confidence']
        top3 = [p['pit_number'] for p in preds_rows[:3]]
        combo = f"{top3[0]}-{top3[1]}-{top3[2]}"
        top_pred = top3[0]
        is_course1 = (top_pred == 1)

        # 信頼度A, Bは除外（BetTargetEvaluatorの条件）
        if confidence in ['A', 'B']:
            continue

        # オッズ取得
        cursor.execute('SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?',
                       (race_id, combo))
        odds_row = cursor.fetchone()

        if not odds_row:
            continue

        odds = odds_row['odds']

        # BetTargetEvaluatorで購入判定
        result = evaluator.evaluate(
            confidence=confidence,
            c1_rank=c1_rank,
            old_combo=combo,
            new_combo=combo,
            old_odds=odds,
            new_odds=odds,
            has_beforeinfo=True,
            venue_code=venue_code
        )

        # 購入対象でない場合はスキップ
        if result.status not in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
            continue

        bet_amount = result.bet_amount

        # 実際の結果を取得
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        results_rows = cursor.fetchall()

        if len(results_rows) < 3:
            continue

        actual_combo = f"{results_rows[0]['pit_number']}-{results_rows[1]['pit_number']}-{results_rows[2]['pit_number']}"
        actual_1st = results_rows[0]['pit_number']
        is_hit = (combo == actual_combo)

        # 払戻取得
        payout = 0
        if is_hit:
            cursor.execute('''
                SELECT amount FROM payouts
                WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
            ''', (race_id, actual_combo))
            payout_row = cursor.fetchone()
            if payout_row:
                payout = (bet_amount / 100) * payout_row['amount']

        # オッズ範囲を特定
        if odds < 20:
            odds_range = '0-20倍'
        elif odds < 30:
            odds_range = '20-30倍'
        elif odds < 40:
            odds_range = '30-40倍'
        elif odds < 50:
            odds_range = '40-50倍'
        else:
            odds_range = '50倍+'

        # 統計を更新
        if is_course1:
            stats = course1_stats
        else:
            stats = non_course1_stats
            stats['by_top_course'][top_pred]['count'] += 1
            stats['by_top_course'][top_pred]['bet'] += bet_amount
            if is_hit:
                stats['by_top_course'][top_pred]['hit'] += 1
                stats['by_top_course'][top_pred]['payout'] += payout

            non_course1_details.append({
                'race_id': race_id,
                'race_date': race_date,
                'venue_code': venue_code,
                'confidence': confidence,
                'c1_rank': c1_rank,
                'top_pred': top_pred,
                'combo': combo,
                'actual_combo': actual_combo,
                'actual_1st': actual_1st,
                'odds': odds,
                'bet_amount': bet_amount,
                'is_hit': is_hit,
                'payout': payout,
            })

        stats['count'] += 1
        stats['bet'] += bet_amount
        stats['by_confidence'][confidence]['count'] += 1
        stats['by_confidence'][confidence]['bet'] += bet_amount
        stats['by_odds_range'][odds_range]['count'] += 1
        stats['by_odds_range'][odds_range]['bet'] += bet_amount

        if is_hit:
            stats['hit'] += 1
            stats['payout'] += payout
            stats['by_confidence'][confidence]['hit'] += 1
            stats['by_confidence'][confidence]['payout'] += payout
            stats['by_odds_range'][odds_range]['hit'] += 1
            stats['by_odds_range'][odds_range]['payout'] += payout

    conn.close()

    # 結果出力
    print('=' * 100)
    print('非1コース予測の正確な分析（BetTargetEvaluator条件適用）')
    print('=' * 100)
    print()
    print('条件:')
    print('  - prediction_type = "before"（直前情報）')
    print('  - 信頼度: C, D のみ')
    print('  - BetTargetEvaluatorの購入条件を適用')
    print()

    print('=' * 100)
    print('1. 全体サマリー')
    print('=' * 100)
    print()

    # 1コース予測
    c1 = course1_stats
    c1_hr = (c1['hit'] / c1['count'] * 100) if c1['count'] > 0 else 0
    c1_roi = (c1['payout'] / c1['bet'] * 100) if c1['bet'] > 0 else 0
    c1_profit = c1['payout'] - c1['bet']

    print('【1コース予測】')
    print(f'  購入数: {c1["count"]}件')
    print(f'  的中数: {c1["hit"]}件')
    print(f'  的中率: {c1_hr:.2f}%')
    print(f'  投資額: {c1["bet"]:,.0f}円')
    print(f'  払戻額: {c1["payout"]:,.0f}円')
    print(f'  収支: {c1_profit:+,.0f}円')
    print(f'  ROI: {c1_roi:.1f}%')
    print()

    # 非1コース予測
    nc1 = non_course1_stats
    nc1_hr = (nc1['hit'] / nc1['count'] * 100) if nc1['count'] > 0 else 0
    nc1_roi = (nc1['payout'] / nc1['bet'] * 100) if nc1['bet'] > 0 else 0
    nc1_profit = nc1['payout'] - nc1['bet']

    print('【非1コース予測】')
    print(f'  購入数: {nc1["count"]}件')
    print(f'  的中数: {nc1["hit"]}件')
    print(f'  的中率: {nc1_hr:.2f}%')
    print(f'  投資額: {nc1["bet"]:,.0f}円')
    print(f'  払戻額: {nc1["payout"]:,.0f}円')
    print(f'  収支: {nc1_profit:+,.0f}円')
    print(f'  ROI: {nc1_roi:.1f}%')
    print()

    # 合計
    total_count = c1['count'] + nc1['count']
    total_hit = c1['hit'] + nc1['hit']
    total_bet = c1['bet'] + nc1['bet']
    total_payout = c1['payout'] + nc1['payout']
    total_hr = (total_hit / total_count * 100) if total_count > 0 else 0
    total_roi = (total_payout / total_bet * 100) if total_bet > 0 else 0
    total_profit = total_payout - total_bet

    print('【合計（現行戦略）】')
    print(f'  購入数: {total_count}件')
    print(f'  的中数: {total_hit}件')
    print(f'  的中率: {total_hr:.2f}%')
    print(f'  投資額: {total_bet:,.0f}円')
    print(f'  払戻額: {total_payout:,.0f}円')
    print(f'  収支: {total_profit:+,.0f}円')
    print(f'  ROI: {total_roi:.1f}%')
    print()

    # ROI貢献度
    print('=' * 100)
    print('2. ROI貢献度分析')
    print('=' * 100)
    print()

    c1_contribution = (c1_profit / total_profit * 100) if total_profit != 0 else 0
    nc1_contribution = (nc1_profit / total_profit * 100) if total_profit != 0 else 0

    print(f'  1コース予測の収支貢献: {c1_profit:+,.0f}円 ({c1_contribution:.1f}%)')
    print(f'  非1コース予測の収支貢献: {nc1_profit:+,.0f}円 ({nc1_contribution:.1f}%)')
    print()

    # 非1コース予測を排除した場合のシミュレーション
    print('=' * 100)
    print('3. 非1コース予測排除シミュレーション')
    print('=' * 100)
    print()

    print('【非1コース予測を完全排除した場合】')
    print(f'  購入数: {c1["count"]}件 (変化: {-nc1["count"]}件)')
    print(f'  的中数: {c1["hit"]}件 (変化: {-nc1["hit"]}件)')
    print(f'  投資額: {c1["bet"]:,.0f}円 (変化: {-nc1["bet"]:,.0f}円)')
    print(f'  収支: {c1_profit:+,.0f}円 (変化: {c1_profit - total_profit:+,.0f}円)')
    print(f'  ROI: {c1_roi:.1f}% (変化: {c1_roi - total_roi:+.1f}pt)')
    print()

    # 信頼度別詳細
    print('=' * 100)
    print('4. 信頼度別詳細')
    print('=' * 100)
    print()

    print(f'{"信頼度":<8} | {"1コース":<12} {"1コースROI":<12} | {"非1コース":<12} {"非1コースROI":<12} | {"非1収支":<14}')
    print('-' * 90)

    for conf in ['C', 'D']:
        c1_conf = course1_stats['by_confidence'][conf]
        nc1_conf = non_course1_stats['by_confidence'][conf]

        c1_conf_roi = (c1_conf['payout'] / c1_conf['bet'] * 100) if c1_conf['bet'] > 0 else 0
        nc1_conf_roi = (nc1_conf['payout'] / nc1_conf['bet'] * 100) if nc1_conf['bet'] > 0 else 0
        nc1_conf_profit = nc1_conf['payout'] - nc1_conf['bet']

        print(f'{conf:<8} | {c1_conf["count"]:<12} {c1_conf_roi:>10.1f}% | {nc1_conf["count"]:<12} {nc1_conf_roi:>10.1f}% | {nc1_conf_profit:>+13,.0f}円')

    print()

    # オッズ範囲別詳細
    print('=' * 100)
    print('5. オッズ範囲別詳細（非1コース予測のみ）')
    print('=' * 100)
    print()

    print(f'{"オッズ範囲":<12} | {"購入数":<8} {"的中数":<8} {"的中率":<10} {"ROI":<10} {"収支":<14}')
    print('-' * 70)

    for odds_range in ['0-20倍', '20-30倍', '30-40倍', '40-50倍', '50倍+']:
        nc1_or = non_course1_stats['by_odds_range'][odds_range]
        if nc1_or['count'] == 0:
            continue

        nc1_or_hr = (nc1_or['hit'] / nc1_or['count'] * 100) if nc1_or['count'] > 0 else 0
        nc1_or_roi = (nc1_or['payout'] / nc1_or['bet'] * 100) if nc1_or['bet'] > 0 else 0
        nc1_or_profit = nc1_or['payout'] - nc1_or['bet']

        print(f'{odds_range:<12} | {nc1_or["count"]:<8} {nc1_or["hit"]:<8} {nc1_or_hr:>8.1f}% {nc1_or_roi:>8.1f}% {nc1_or_profit:>+13,.0f}円')

    print()

    # コース別詳細
    print('=' * 100)
    print('6. 予測1着コース別詳細（非1コース予測のみ）')
    print('=' * 100)
    print()

    print(f'{"予測コース":<12} | {"購入数":<8} {"的中数":<8} {"的中率":<10} {"ROI":<10} {"収支":<14}')
    print('-' * 70)

    for course in range(2, 7):
        nc1_c = non_course1_stats['by_top_course'][course]
        if nc1_c['count'] == 0:
            continue

        nc1_c_hr = (nc1_c['hit'] / nc1_c['count'] * 100) if nc1_c['count'] > 0 else 0
        nc1_c_roi = (nc1_c['payout'] / nc1_c['bet'] * 100) if nc1_c['bet'] > 0 else 0
        nc1_c_profit = nc1_c['payout'] - nc1_c['bet']

        print(f'{course}コース      | {nc1_c["count"]:<8} {nc1_c["hit"]:<8} {nc1_c_hr:>8.1f}% {nc1_c_roi:>8.1f}% {nc1_c_profit:>+13,.0f}円')

    print()

    # 非1コース予測の的中例
    print('=' * 100)
    print('7. 非1コース予測の的中例（最新10件）')
    print('=' * 100)
    print()

    hit_details = [d for d in non_course1_details if d['is_hit']]
    for d in hit_details[-10:]:
        print(f'  {d["race_date"]} race_id={d["race_id"]}: {d["combo"]} (オッズ{d["odds"]:.1f}倍) → 払戻 {d["payout"]:,.0f}円')

    print()

    # 結論と推奨
    print('=' * 100)
    print('8. 分析結論と推奨戦略')
    print('=' * 100)
    print()

    if nc1_profit > 0:
        print('【結論】')
        print(f'  非1コース予測は収支に対して正の貢献をしている（+{nc1_profit:,.0f}円）')
        print(f'  ROI: {nc1_roi:.1f}%（100%超）')
        print()
        print('【推奨】')
        print('  非1コース予測を排除しないこと')
        print('  現行戦略を維持')
    elif nc1_profit < 0:
        print('【結論】')
        print(f'  非1コース予測は収支に対して負の貢献をしている（{nc1_profit:,.0f}円）')
        print(f'  ROI: {nc1_roi:.1f}%（100%未満）')
        print()
        print('【推奨】')
        print('  非1コース予測の条件を見直す:')
        print('  - オッズ下限の引き上げ')
        print('  - 特定コースのみに限定')
        print('  - スコア差閾値の導入')
    else:
        print('【結論】')
        print('  非1コース予測の収支貢献はゼロ')

    print()

    return {
        'course1_stats': course1_stats,
        'non_course1_stats': non_course1_stats,
        'non_course1_details': non_course1_details,
    }


if __name__ == '__main__':
    main()
