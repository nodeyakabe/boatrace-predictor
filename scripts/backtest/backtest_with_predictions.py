#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
予測データを使った汎用バックテストスクリプト

目的: 生成済みの予測データを使い、任意の期間のバックテストを実行
使い方:
    # 単一年度
    python scripts/backtest_with_predictions.py --year 2025

    # 複数年度
    python scripts/backtest_with_predictions.py --years 2022,2023,2024,2025

    # 特定期間
    python scripts/backtest_with_predictions.py --start-date 2025-06-01 --end-date 2025-06-30

    # 詳細レポート出力
    python scripts/backtest_with_predictions.py --year 2025 --report output/backtest_2025.md
"""
import sys
import os
from pathlib import Path
import sqlite3
from datetime import datetime, timedelta
import argparse
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DATABASE_PATH
from src.betting.bet_target_evaluator import BetTargetEvaluator


def get_date_range(args):
    """引数から日付範囲を生成"""
    if args.year:
        start_date = f'{args.year}-01-01'
        end_date = f'{args.year}-12-31'

    elif args.years:
        year_list = [int(y.strip()) for y in args.years.split(',')]
        min_year = min(year_list)
        max_year = max(year_list)
        start_date = f'{min_year}-01-01'
        end_date = f'{max_year}-12-31'

    elif args.start_date and args.end_date:
        start_date = args.start_date
        end_date = args.end_date

    else:
        # デフォルト: 今年
        current_year = datetime.now().year
        start_date = f'{current_year}-01-01'
        end_date = f'{current_year}-12-31'

    return start_date, end_date


def run_backtest(start_date, end_date, prediction_type='advance'):
    """バックテスト実行"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 対象レースを取得
    cursor.execute("""
        SELECT DISTINCT r.id, r.race_date, r.venue_code, r.race_number
        FROM races r
        INNER JOIN race_predictions rp ON r.id = rp.race_id
        WHERE r.race_date >= ? AND r.race_date <= ?
        AND rp.prediction_type = ?
        ORDER BY r.race_date, r.venue_code, r.race_number
    """, (start_date, end_date, prediction_type))

    races = cursor.fetchall()

    if len(races) == 0:
        print(f"[!] {start_date} ～ {end_date} の予測データが見つかりませんでした")
        print(f"    prediction_type = {prediction_type}")
        conn.close()
        return None

    print(f"対象レース: {len(races)}件")
    print()

    evaluator = BetTargetEvaluator()

    # 統計
    stats = {
        'total_races': len(races),
        'total_predictions': 0,
        'total_hits': 0,
        'purchase_count': 0,
        'total_investment': 0,
        'total_return': 0,
        'by_confidence': {},
        'by_year': {},
        'by_month': {},
        'purchase_details': []
    }

    # レースごとに処理
    for race_id, race_date, venue_code, race_num in races:
        # 予測データを取得
        cursor.execute("""
            SELECT pit_number, rank_prediction, total_score, confidence,
                   racer_name, racer_number
            FROM race_predictions
            WHERE race_id = ?
            AND prediction_type = ?
            ORDER BY rank_prediction
        """, (race_id, prediction_type))

        pred_rows = cursor.fetchall()

        if len(pred_rows) == 0:
            continue

        predictions = []
        for row in pred_rows:
            predictions.append({
                'pit_number': row[0],
                'rank_prediction': row[1],
                'total_score': row[2],
                'confidence': row[3],
                'racer_name': row[4],
                'racer_number': row[5]
            })

        stats['total_predictions'] += 1

        top3 = predictions[:3]
        confidence = top3[0]['confidence']

        # 実際の結果を取得
        cursor.execute("""
            SELECT pit_number
            FROM results
            WHERE race_id = ?
            AND rank IN ('1', '2', '3')
            ORDER BY CAST(rank AS INTEGER)
        """, (race_id,))

        actual_results = cursor.fetchall()

        if len(actual_results) != 3:
            continue

        actual_top3 = [r[0] for r in actual_results]
        predicted_top3 = [p['pit_number'] for p in top3]

        is_hit = (predicted_top3 == actual_top3)

        if is_hit:
            stats['total_hits'] += 1

        # 信頼度別統計
        if confidence not in stats['by_confidence']:
            stats['by_confidence'][confidence] = {
                'total': 0, 'hits': 0, 'purchase': 0,
                'investment': 0, 'return': 0
            }

        stats['by_confidence'][confidence]['total'] += 1
        if is_hit:
            stats['by_confidence'][confidence]['hits'] += 1

        # 年別統計
        year = race_date[:4]
        if year not in stats['by_year']:
            stats['by_year'][year] = {
                'total': 0, 'hits': 0, 'purchase': 0,
                'investment': 0, 'return': 0
            }

        stats['by_year'][year]['total'] += 1
        if is_hit:
            stats['by_year'][year]['hits'] += 1

        # 月別統計
        month = race_date[:7]
        if month not in stats['by_month']:
            stats['by_month'][month] = {
                'total': 0, 'hits': 0, 'purchase': 0,
                'investment': 0, 'return': 0
            }

        stats['by_month'][month]['total'] += 1
        if is_hit:
            stats['by_month'][month]['hits'] += 1

        # 購入判定
        should_buy, reason = evaluator.evaluate_race(race_id, predictions)

        if should_buy:
            stats['purchase_count'] += 1
            stats['by_confidence'][confidence]['purchase'] += 1
            stats['by_year'][year]['purchase'] += 1
            stats['by_month'][month]['purchase'] += 1

            bet_amount = 400  # パターンH
            stats['total_investment'] += bet_amount
            stats['by_confidence'][confidence]['investment'] += bet_amount
            stats['by_year'][year]['investment'] += bet_amount
            stats['by_month'][month]['investment'] += bet_amount

            # 払戻を取得
            combination = f"{predicted_top3[0]}-{predicted_top3[1]}-{predicted_top3[2]}"

            cursor.execute("""
                SELECT amount
                FROM payouts
                WHERE race_id = ?
                AND bet_type = 'trifecta'
                AND combination = ?
            """, (race_id, combination))

            payout_row = cursor.fetchone()
            payout_amount = payout_row[0] if payout_row else 0

            stats['total_return'] += payout_amount
            stats['by_confidence'][confidence]['return'] += payout_amount
            stats['by_year'][year]['return'] += payout_amount
            stats['by_month'][month]['return'] += payout_amount

            # 購入詳細を記録
            stats['purchase_details'].append({
                'race_date': race_date,
                'venue_code': venue_code,
                'race_number': race_num,
                'confidence': confidence,
                'combination': combination,
                'is_hit': is_hit,
                'bet_amount': bet_amount,
                'payout': payout_amount,
                'profit': payout_amount - bet_amount
            })

    conn.close()

    return stats


def print_report(stats, start_date, end_date):
    """レポート表示"""
    print()
    print("=" * 80)
    print("バックテスト結果")
    print("=" * 80)
    print(f"対象期間: {start_date} ～ {end_date}")
    print()

    # 全体統計
    print("【全体統計】")
    print(f"対象レース: {stats['total_predictions']}件")
    print(f"3連単的中: {stats['total_hits']}件")
    if stats['total_predictions'] > 0:
        hit_rate = stats['total_hits'] / stats['total_predictions'] * 100
        print(f"的中率: {hit_rate:.2f}%")
    print()

    # 購入統計
    print("【購入統計】")
    print(f"購入レース数: {stats['purchase_count']}件")

    if stats['total_investment'] > 0:
        roi = stats['total_return'] / stats['total_investment'] * 100
        profit = stats['total_return'] - stats['total_investment']
        print(f"投資額: {stats['total_investment']:,}円")
        print(f"払戻額: {stats['total_return']:,}円")
        print(f"収支: {profit:+,}円")
        print(f"ROI: {roi:.1f}%")

        # 購入的中率
        purchase_hits = sum(1 for d in stats['purchase_details'] if d['is_hit'])
        purchase_hit_rate = purchase_hits / stats['purchase_count'] * 100 if stats['purchase_count'] > 0 else 0
        print(f"購入的中率: {purchase_hit_rate:.2f}% ({purchase_hits}/{stats['purchase_count']})")
    else:
        print("購入対象なし")

    print()

    # 信頼度別
    print("【信頼度別統計】")
    for conf in sorted(stats['by_confidence'].keys()):
        data = stats['by_confidence'][conf]
        hit_rate = data['hits'] / data['total'] * 100 if data['total'] > 0 else 0

        print(f"  信頼度{conf}:")
        print(f"    的中率: {data['hits']}/{data['total']} = {hit_rate:.1f}%")

        if data['purchase'] > 0:
            roi_val = data['return'] / data['investment'] * 100 if data['investment'] > 0 else 0
            profit = data['return'] - data['investment']
            print(f"    購入数: {data['purchase']}件")
            print(f"    投資額: {data['investment']:,}円")
            print(f"    払戻額: {data['return']:,}円")
            print(f"    収支: {profit:+,}円")
            print(f"    ROI: {roi_val:.1f}%")
        else:
            print(f"    購入数: 0件")

    print()

    # 年別統計
    if len(stats['by_year']) > 1:
        print("【年別統計】")
        for year in sorted(stats['by_year'].keys()):
            data = stats['by_year'][year]
            hit_rate = data['hits'] / data['total'] * 100 if data['total'] > 0 else 0

            print(f"  {year}年:")
            print(f"    的中率: {data['hits']}/{data['total']} = {hit_rate:.1f}%")

            if data['investment'] > 0:
                roi_val = data['return'] / data['investment'] * 100
                profit = data['return'] - data['investment']
                print(f"    購入数: {data['purchase']}件")
                print(f"    ROI: {roi_val:.1f}% (収支: {profit:+,}円)")

        print()

    print("=" * 80)


def save_report_to_file(stats, start_date, end_date, filepath):
    """レポートをファイルに保存"""
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"# バックテストレポート\n\n")
        f.write(f"**対象期間**: {start_date} ～ {end_date}\n")
        f.write(f"**生成日時**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("---\n\n")

        # 全体統計
        f.write("## 全体統計\n\n")
        f.write(f"- 対象レース: {stats['total_predictions']}件\n")
        f.write(f"- 3連単的中: {stats['total_hits']}件\n")
        if stats['total_predictions'] > 0:
            hit_rate = stats['total_hits'] / stats['total_predictions'] * 100
            f.write(f"- 的中率: {hit_rate:.2f}%\n")
        f.write("\n")

        # 購入統計
        f.write("## 購入統計\n\n")
        f.write(f"- 購入レース数: {stats['purchase_count']}件\n")

        if stats['total_investment'] > 0:
            roi = stats['total_return'] / stats['total_investment'] * 100
            profit = stats['total_return'] - stats['total_investment']
            f.write(f"- 投資額: {stats['total_investment']:,}円\n")
            f.write(f"- 払戻額: {stats['total_return']:,}円\n")
            f.write(f"- 収支: {profit:+,}円\n")
            f.write(f"- ROI: {roi:.1f}%\n")

            purchase_hits = sum(1 for d in stats['purchase_details'] if d['is_hit'])
            purchase_hit_rate = purchase_hits / stats['purchase_count'] * 100 if stats['purchase_count'] > 0 else 0
            f.write(f"- 購入的中率: {purchase_hit_rate:.2f}% ({purchase_hits}/{stats['purchase_count']})\n")
        else:
            f.write("- 購入対象なし\n")
        f.write("\n")

        # 信頼度別
        f.write("## 信頼度別統計\n\n")
        f.write("| 信頼度 | 的中率 | 購入数 | ROI | 収支 |\n")
        f.write("|--------|--------|--------|-----|------|\n")

        for conf in sorted(stats['by_confidence'].keys()):
            data = stats['by_confidence'][conf]
            hit_rate = data['hits'] / data['total'] * 100 if data['total'] > 0 else 0

            if data['investment'] > 0:
                roi_val = data['return'] / data['investment'] * 100
                profit = data['return'] - data['investment']
                f.write(f"| {conf} | {hit_rate:.1f}% ({data['hits']}/{data['total']}) | {data['purchase']}件 | {roi_val:.1f}% | {profit:+,}円 |\n")
            else:
                f.write(f"| {conf} | {hit_rate:.1f}% ({data['hits']}/{data['total']}) | 0件 | - | - |\n")

        f.write("\n")

        # 年別統計
        if len(stats['by_year']) > 1:
            f.write("## 年別統計\n\n")
            f.write("| 年 | 的中率 | 購入数 | ROI | 収支 |\n")
            f.write("|-----|--------|--------|-----|------|\n")

            for year in sorted(stats['by_year'].keys()):
                data = stats['by_year'][year]
                hit_rate = data['hits'] / data['total'] * 100 if data['total'] > 0 else 0

                if data['investment'] > 0:
                    roi_val = data['return'] / data['investment'] * 100
                    profit = data['return'] - data['investment']
                    f.write(f"| {year} | {hit_rate:.1f}% ({data['hits']}/{data['total']}) | {data['purchase']}件 | {roi_val:.1f}% | {profit:+,}円 |\n")
                else:
                    f.write(f"| {year} | {hit_rate:.1f}% ({data['hits']}/{data['total']}) | 0件 | - | - |\n")

            f.write("\n")

    print(f"\nレポートを保存しました: {filepath}")


def main():
    parser = argparse.ArgumentParser(
        description='予測データを使った汎用バックテスト',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 2025年全体
  python scripts/backtest_with_predictions.py --year 2025

  # 複数年度
  python scripts/backtest_with_predictions.py --years 2022,2023,2024,2025

  # 特定期間
  python scripts/backtest_with_predictions.py --start-date 2025-06-01 --end-date 2025-06-30

  # レポート出力
  python scripts/backtest_with_predictions.py --year 2025 --report output/backtest_2025.md
        """
    )

    # 期間指定
    parser.add_argument('--year', type=int, help='対象年度（例: 2025）')
    parser.add_argument('--years', type=str, help='複数年度（例: 2022,2023,2024,2025）')
    parser.add_argument('--start-date', type=str, help='開始日（YYYY-MM-DD）')
    parser.add_argument('--end-date', type=str, help='終了日（YYYY-MM-DD）')

    # オプション
    parser.add_argument('--prediction-type', type=str, default='advance',
                        choices=['advance', 'before'],
                        help='予測タイプ（デフォルト: advance）')
    parser.add_argument('--report', type=str, help='レポート出力先（Markdownファイル）')

    args = parser.parse_args()

    # 日付範囲を取得
    start_date, end_date = get_date_range(args)

    print("=" * 80)
    print("汎用バックテストスクリプト")
    print("=" * 80)
    print(f"対象期間: {start_date} ～ {end_date}")
    print(f"予測タイプ: {args.prediction_type}")
    print("=" * 80)
    print()

    # バックテスト実行
    stats = run_backtest(start_date, end_date, args.prediction_type)

    if stats is None:
        sys.exit(1)

    # レポート表示
    print_report(stats, start_date, end_date)

    # ファイル保存
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        save_report_to_file(stats, start_date, end_date, str(report_path))


if __name__ == "__main__":
    main()
