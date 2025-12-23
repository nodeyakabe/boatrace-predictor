# -*- coding: utf-8 -*-
"""
期待値ベース買い目選択ツール

使用例:
  python scripts/ev_bet_tool.py backtest --start 2025-11-01 --end 2025-11-30 --max-bets 5
  python scripts/ev_bet_tool.py race --race-id 12345
  python scripts/ev_bet_tool.py compare --start 2025-11-01 --end 2025-11-30
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.betting.ev_bet_selector import EVBetSelector, EVBetAnalyzer


def cmd_backtest(args):
    """バックテストを実行"""
    analyzer = EVBetAnalyzer()

    print("=" * 70)
    print(f"期待値ベース戦略 バックテスト")
    print(f"期間: {args.start} ~ {args.end}")
    print(f"最大買い目数: {args.max_bets}")
    print("=" * 70)

    result = analyzer.backtest(
        start_date=args.start,
        end_date=args.end,
        max_bets=args.max_bets
    )

    print(analyzer.format_backtest_result(result))


def cmd_compare(args):
    """戦略を比較"""
    analyzer = EVBetAnalyzer()

    print("=" * 70)
    print("期待値ベース戦略 比較分析")
    print(f"期間: {args.start} ~ {args.end}")
    print("=" * 70)

    strategies = [
        ('Top 3 EV', 3),
        ('Top 5 EV', 5),
        ('Top 7 EV', 7),
        ('Standard 9pt', 9),
    ]

    print("")
    print(f"{'戦略':<15} {'レース':>6} {'的中':>5} {'的中率':>8} {'投資':>10} {'払戻':>10} {'収支':>10} {'ROI':>7}")
    print("-" * 80)

    for name, max_bets in strategies:
        result = analyzer.backtest(
            start_date=args.start,
            end_date=args.end,
            max_bets=max_bets
        )

        if result['total_races'] > 0:
            profit = result.get('profit', 0)
            profit_str = f"+{profit:,.0f}" if profit > 0 else f"{profit:,.0f}"
            print(f"{name:<15} {result['total_races']:>6} {result['total_hits']:>5} "
                  f"{result.get('hit_rate', 0):>7.2f}% {result['total_bet_amount']:>9,} "
                  f"{result['total_payout']:>9,} {profit_str:>10} {result.get('roi', 0):>6.1f}%")


def cmd_race(args):
    """特定レースの買い目を取得"""
    import sqlite3

    selector = EVBetSelector(max_bets=args.max_bets)

    with sqlite3.connect('data/boatrace.db') as conn:
        cursor = conn.cursor()

        # 予測データ取得
        cursor.execute('''
            SELECT pit_number, rank_prediction, confidence
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = ?
            ORDER BY rank_prediction
        ''', (args.race_id, args.pred_type))
        preds = cursor.fetchall()

        if len(preds) < 6:
            print("予測データが不足しています")
            return

        preds_sorted = sorted(preds, key=lambda x: x[1])
        predicted_ranks = [x[0] for x in preds_sorted]
        confidence = preds_sorted[0][2]

        # レース情報取得
        cursor.execute('''
            SELECT r.race_date, r.venue_code, r.race_number
            FROM races r WHERE r.id = ?
        ''', (args.race_id,))
        race_info = cursor.fetchone()

    if race_info:
        print(f"レース: {race_info[0]} {race_info[1]}場 {race_info[2]}R")

    print(f"予測順位: {predicted_ranks}")
    print(f"信頼度: {confidence}")

    recommendation = selector.get_bet_recommendation(
        args.race_id, predicted_ranks, confidence
    )

    print("")
    print(selector.format_recommendation(recommendation))


def cmd_weekly(args):
    """週次サマリー"""
    analyzer = EVBetAnalyzer()

    print("=" * 70)
    print("週次収支サマリー（Top 5 EV戦略）")
    print("=" * 70)

    weeks = [
        ('2025-11-01', '2025-11-07', 'Week1'),
        ('2025-11-08', '2025-11-14', 'Week2'),
        ('2025-11-15', '2025-11-21', 'Week3'),
        ('2025-11-22', '2025-11-28', 'Week4'),
    ]

    print("")
    print(f"{'週':<10} {'レース':>6} {'的中':>5} {'投資':>10} {'払戻':>10} {'収支':>10} {'ROI':>7}")
    print("-" * 70)

    total_races = 0
    total_bet = 0
    total_payout = 0
    positive_weeks = 0

    for start, end, name in weeks:
        result = analyzer.backtest(start, end, max_bets=5)

        if result['total_races'] > 0:
            profit = result.get('profit', 0)
            profit_str = f"+{profit:,.0f}" if profit > 0 else f"{profit:,.0f}"
            print(f"{name:<10} {result['total_races']:>6} {result['total_hits']:>5} "
                  f"{result['total_bet_amount']:>9,} {result['total_payout']:>9,} "
                  f"{profit_str:>10} {result.get('roi', 0):>6.1f}%")

            total_races += result['total_races']
            total_bet += result['total_bet_amount']
            total_payout += result['total_payout']

            if profit > 0:
                positive_weeks += 1
        else:
            print(f"{name:<10} データなし")

    print("-" * 70)
    total_profit = total_payout - total_bet
    total_roi = total_payout / total_bet * 100 if total_bet > 0 else 0
    profit_str = f"+{total_profit:,.0f}" if total_profit > 0 else f"{total_profit:,.0f}"
    print(f"{'合計':<10} {total_races:>6} {'-':>5} {total_bet:>9,} {total_payout:>9,} "
          f"{profit_str:>10} {total_roi:>6.1f}%")
    print(f"\n週次プラス: {positive_weeks}/4週")


def main():
    parser = argparse.ArgumentParser(description='期待値ベース買い目選択ツール')
    subparsers = parser.add_subparsers(dest='command')

    # backtest
    p_backtest = subparsers.add_parser('backtest', help='バックテストを実行')
    p_backtest.add_argument('--start', required=True, help='開始日 (YYYY-MM-DD)')
    p_backtest.add_argument('--end', required=True, help='終了日 (YYYY-MM-DD)')
    p_backtest.add_argument('--max-bets', type=int, default=5, help='最大買い目数')

    # compare
    p_compare = subparsers.add_parser('compare', help='戦略を比較')
    p_compare.add_argument('--start', required=True, help='開始日')
    p_compare.add_argument('--end', required=True, help='終了日')

    # race
    p_race = subparsers.add_parser('race', help='レースの買い目を取得')
    p_race.add_argument('--race-id', type=int, required=True, help='レースID')
    p_race.add_argument('--max-bets', type=int, default=5, help='最大買い目数')
    p_race.add_argument('--pred-type', default='advance', help='予測タイプ')

    # weekly
    p_weekly = subparsers.add_parser('weekly', help='週次サマリー')

    args = parser.parse_args()

    if args.command == 'backtest':
        cmd_backtest(args)
    elif args.command == 'compare':
        cmd_compare(args)
    elif args.command == 'race':
        cmd_race(args)
    elif args.command == 'weekly':
        cmd_weekly(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
