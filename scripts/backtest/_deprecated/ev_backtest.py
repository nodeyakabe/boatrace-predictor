#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
期待値ベース買い目選択バックテスト

現在の条件フィルター（bet_conditions.py）で選ばれたレースに対して、
1点買いの代わりにEV >= 閾値の複数点買いを適用した場合の成績を検証する。

【比較内容】
  現行方式: 条件フィルター → 1点買い（1-2-3のみ）
  新EV方式: 条件フィルター → EV閾値以上の全組み合わせを購入（複数点）

使用方法:
    python scripts/backtest/ev_backtest.py --year 2025
    python scripts/backtest/ev_backtest.py --full
    python scripts/backtest/ev_backtest.py --full --ev-threshold 1.2 --max-bets 5
"""

import sqlite3
import sys
import os
import argparse
from typing import Dict, List

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from config.bet_conditions import STANDARD_BET_CONDITIONS
from scripts.backtest.backtest_helpers import get_race_ids_for_condition
from scripts.backtest.standard_backtest_unique import assign_races_to_conditions
from src.betting.ev_bet_selector import EVBetSelector


def run_ev_backtest(
    start_date: str,
    end_date: str,
    ev_threshold: float = 1.0,
    max_bets: int = 9,
    use_plackett_luce: bool = True,
    pattern: str = '1-234-2345',
    odds_max_per_bet: float = None,
) -> Dict:
    """
    EV方式バックテスト実行

    Args:
        start_date: 開始日（YYYY-MM-DD）
        end_date: 終了日（YYYY-MM-DD）
        ev_threshold: EV閾値（この値以上の組み合わせのみ購入）
        max_bets: 1レース最大買い目数
        use_plackett_luce: True=Plackett-Luce確率, False=DB実績確率テーブル
        pattern: 候補生成パターン ('1-234-2345' or 'all120')
        odds_max_per_bet: 各買い目の上限オッズ（超えたものは除外）

    Returns:
        バックテスト結果辞書
    """
    selector = EVBetSelector(
        db_path=DATABASE_PATH,
        min_ev=ev_threshold,
        max_bets=max_bets,
        use_top_n=False  # EV閾値方式
    )

    results_by_cond = {}
    total = {'races': 0, 'bets': 0, 'invest': 0, 'hits': 0, 'payout': 0}

    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()

        # 条件フィルターで割り当て（standard_backtest_uniqueと同じロジック）
        assigned = assign_races_to_conditions(cursor, STANDARD_BET_CONDITIONS, start_date, end_date)

        for cond in STANDARD_BET_CONDITIONS:
            cid = cond['id']
            race_ids = assigned.get(cid, [])
            if not race_ids:
                results_by_cond[cid] = {'name': cond['name'], 'races': 0, 'bets': 0, 'invest': 0, 'hits': 0, 'payout': 0}
                continue

            cond_res = {'name': cond['name'], 'races': 0, 'bets': 0, 'invest': 0, 'hits': 0, 'payout': 0}
            placeholders = ','.join(['?'] * len(race_ids))

            for race_id in race_ids:
                # 予測データ取得（1位艇・信頼度・全艇スコア）
                cursor.execute('''
                    SELECT pit_number, rank_prediction, confidence, total_score
                    FROM race_predictions
                    WHERE race_id = ? AND prediction_type = 'before'
                    ORDER BY rank_prediction
                ''', (race_id,))
                preds = cursor.fetchall()

                if len(preds) < 5:
                    continue

                preds_sorted = sorted(preds, key=lambda x: x[1])
                predicted_ranks = [x[0] for x in preds_sorted]
                confidence = preds_sorted[0][2]

                # Plackett-Luce用スコアマップ
                scores = None
                if use_plackett_luce:
                    scores = {x[0]: (x[3] or 0.0) for x in preds_sorted}

                # オッズ範囲チェック（条件のオッズ帯に1-2-3が入っているレースのみ対象）
                odds_min = cond.get('odds_min', 0)
                odds_max = cond.get('odds_max', 9999)
                combo_123 = f'{predicted_ranks[0]}-{predicted_ranks[1]}-{predicted_ranks[2]}'
                cursor.execute(
                    'SELECT odds FROM trifecta_odds WHERE race_id=? AND combination=?',
                    (race_id, combo_123)
                )
                odds_row = cursor.fetchone()
                if not odds_row:
                    continue
                main_odds = odds_row[0]
                if not (odds_min <= main_odds < odds_max):
                    continue

                # 全オッズ取得
                cursor.execute('SELECT combination, odds FROM trifecta_odds WHERE race_id=?', (race_id,))
                odds_data = {row[0]: row[1] for row in cursor.fetchall()}

                # EV選択
                selected_bets = selector.select_bets(
                    predicted_ranks, confidence, odds_data, pattern, scores,
                    odds_max_per_bet=odds_max_per_bet
                )

                if not selected_bets:
                    # EV閾値を満たす組み合わせがない場合、1-2-3を1点購入（フォールバック）
                    continue

                # 実際の結果
                cursor.execute('''
                    SELECT pit_number FROM results
                    WHERE race_id=? AND is_invalid=0 AND rank IN ('1','2','3')
                    ORDER BY rank
                ''', (race_id,))
                actual = cursor.fetchall()
                if len(actual) < 3:
                    continue

                actual_combo = f'{actual[0][0]}-{actual[1][0]}-{actual[2][0]}'

                # 的中チェックと払戻
                hit_payout = 0
                for bet in selected_bets:
                    if bet.combination == actual_combo:
                        hit_payout = odds_data.get(actual_combo, 0) * 100
                        break

                invest = len(selected_bets) * 100
                cond_res['races'] += 1
                cond_res['bets'] += len(selected_bets)
                cond_res['invest'] += invest
                cond_res['payout'] += hit_payout
                if hit_payout > 0:
                    cond_res['hits'] += 1

            results_by_cond[cid] = cond_res
            total['races'] += cond_res['races']
            total['bets'] += cond_res['bets']
            total['invest'] += cond_res['invest']
            total['hits'] += cond_res['hits']
            total['payout'] += cond_res['payout']

    # ROI・収支計算
    for cid, r in results_by_cond.items():
        if r['invest'] > 0:
            r['roi'] = r['payout'] / r['invest'] * 100
            r['profit'] = r['payout'] - r['invest']
            r['hit_rate'] = r['hits'] / r['races'] * 100 if r['races'] > 0 else 0
        else:
            r['roi'] = 0.0
            r['profit'] = 0
            r['hit_rate'] = 0.0

    if total['invest'] > 0:
        total['roi'] = total['payout'] / total['invest'] * 100
        total['profit'] = total['payout'] - total['invest']
        total['hit_rate'] = total['hits'] / total['races'] * 100 if total['races'] > 0 else 0

    return {'by_condition': results_by_cond, 'total': total}


def print_result(result: Dict, label: str = ''):
    if label:
        print(f'\n{"="*70}')
        print(f'  {label}')
        print(f'{"="*70}')

    total = result['total']
    invest = total['invest']
    payout = total['payout']
    profit = total['profit']
    roi = total['roi'] if 'roi' in total else 0

    print(f'購入レース数: {total["races"]:,}件  買い目数: {total["bets"]:,}点')
    print(f'投資額: {invest:,}円  払戻: {payout:,}円')
    print(f'収支: {profit:+,}円  ROI: {roi:.1f}%  的中: {total["hits"]}回 ({total.get("hit_rate",0):.1f}%)')
    print()
    print('条件別:')
    print(f'{"条件名":<30} {"件数":>5} {"買目":>6} {"投資":>8} {"収支":>9} {"ROI":>7} {"的中":>5}')
    print('-' * 80)
    for cid, r in result['by_condition'].items():
        if r['races'] == 0:
            continue
        avg_bets = r['bets'] / r['races'] if r['races'] > 0 else 0
        print(f'{r["name"]:<30} {r["races"]:>5} {avg_bets:>5.1f}点 {r["invest"]:>8,} {r["profit"]:>+9,} {r["roi"]:>6.1f}% {r["hits"]:>5}')


def main():
    parser = argparse.ArgumentParser(description='EV方式バックテスト')
    parser.add_argument('--year', type=int, help='対象年度')
    parser.add_argument('--full', action='store_true', help='6年間全体（2020-2025）')
    parser.add_argument('--ev-threshold', type=float, default=1.0, help='EV閾値（デフォルト1.0）')
    parser.add_argument('--max-bets', type=int, default=9, help='最大買い目数（デフォルト9）')
    parser.add_argument('--no-pl', action='store_true', help='Plackett-Luceを使わずDB実績確率テーブルを使用')
    parser.add_argument('--pattern', type=str, default='1-234-2345',
                        help='候補生成パターン: 1-234-2345（デフォルト）or all120')
    parser.add_argument('--odds-max-per-bet', type=float, default=None,
                        help='各買い目の上限オッズ（例: 100）')
    args = parser.parse_args()

    use_pl = not args.no_pl
    prob_method = 'Plackett-Luce' if use_pl else 'DB実績確率テーブル'
    odds_cap = f' 各買目上限{args.odds_max_per_bet}倍' if args.odds_max_per_bet else ''

    print(f'EV方式バックテスト  EV>={args.ev_threshold}  最大{args.max_bets}点  パターン={args.pattern}  確率={prob_method}{odds_cap}')

    if args.full:
        # 6年間を年度別に集計
        print('\n=== 6年間 年度別 ===')
        all_totals = []
        for year in range(2020, 2026):
            s = f'{year}-01-01'
            e = f'{year+1}-01-01'
            res = run_ev_backtest(s, e, args.ev_threshold, args.max_bets, use_pl,
                                  args.pattern, args.odds_max_per_bet)
            t = res['total']
            profit = t.get('profit', 0)
            roi = t.get('roi', 0)
            mark = 'O' if profit > 0 else 'X'
            avg = t['bets'] / t['races'] if t['races'] > 0 else 0
            print(f'{year}: {t["races"]:>4}件 avg{avg:.1f}点 投資{t["invest"]:>8,}円 収支{profit:>+9,}円 ROI{roi:>6.1f}% {mark}')
            all_totals.append(t)

        # 合計
        tr = sum(t['races'] for t in all_totals)
        tb = sum(t['bets'] for t in all_totals)
        ti = sum(t['invest'] for t in all_totals)
        th = sum(t['hits'] for t in all_totals)
        tp = sum(t['payout'] for t in all_totals)
        total_roi = tp / ti * 100 if ti > 0 else 0
        total_profit = tp - ti
        black = sum(1 for t in all_totals if t.get('profit', 0) > 0)
        print(f'合計: {tr:>4}件 avg{tb/tr:.1f}点 投資{ti:>8,}円 収支{total_profit:>+9,}円 ROI{total_roi:>6.1f}% 黒字{black}/6年')

    elif args.year:
        s = f'{args.year}-01-01'
        e = f'{args.year+1}-01-01'
        res = run_ev_backtest(s, e, args.ev_threshold, args.max_bets, use_pl,
                              args.pattern, args.odds_max_per_bet)
        print_result(res, f'{args.year}年')
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
