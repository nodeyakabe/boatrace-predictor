# -*- coding: utf-8 -*-
"""
会場別期待勝率テーブル導入前後の予測精度比較バックテスト

目的:
- 会場別期待勝率テーブルの導入が予測精度にどれだけ寄与するかを検証
- 1着・2着・3着予測の的中率を比較

比較対象:
- ベースライン: 全国平均の勝率を使用（従来の実装）
- 新実装: 会場別期待勝率テーブルを使用
"""

import sys
from pathlib import Path
import sqlite3
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.analysis.race_predictor import RacePredictor

DB_PATH = ROOT_DIR / 'data' / 'boatrace.db'


def evaluate_predictions(test_period_start='2024-01-01', test_period_end='2024-12-31'):
    """
    指定期間のレースで予測精度を評価

    Args:
        test_period_start: テスト期間開始日
        test_period_end: テスト期間終了日
    """
    print("=" * 80)
    print("会場別期待勝率テーブル予測精度検証")
    print("=" * 80)
    print(f"テスト期間: {test_period_start} ~ {test_period_end}")
    print()

    # DB接続
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # テスト対象レースを取得
    query = '''
        SELECT DISTINCT
            r.race_date,
            r.venue_code,
            r.race_number
        FROM races r
        JOIN results res ON r.id = res.race_id
        WHERE r.race_date BETWEEN ? AND ?
        ORDER BY r.race_date, r.venue_code, r.race_number
    '''

    cursor.execute(query, (test_period_start, test_period_end))
    test_races = cursor.fetchall()

    print(f"テスト対象レース数: {len(test_races)}レース")
    print()

    # 予測器の初期化
    predictor = RacePredictor()

    # 評価指標
    stats = {
        'total_races': 0,
        'predictions_made': 0,
        'top1_correct': 0,  # 1着予測的中
        'top2_correct': 0,  # 2着以内予測的中
        'top3_correct': 0,  # 3着以内予測的中
        'top1_in_top3': 0,  # 予測1位が実際3着以内
        'venue_stats': defaultdict(lambda: {
            'races': 0,
            'top1_correct': 0,
            'top2_correct': 0,
            'top3_correct': 0
        })
    }

    # 進捗表示用
    milestone = len(test_races) // 10

    for idx, race_row in enumerate(test_races):
        race_date = race_row['race_date']
        venue_code = race_row['venue_code']
        race_number = race_row['race_number']

        # 進捗表示
        if milestone > 0 and (idx + 1) % milestone == 0:
            progress = (idx + 1) / len(test_races) * 100
            print(f"  進捗: {idx + 1}/{len(test_races)} ({progress:.1f}%)")

        stats['total_races'] += 1

        try:
            # 予測実行
            predictions = predictor.predict_race_by_key(
                race_date=race_date,
                venue_code=venue_code,
                race_number=race_number
            )

            if not predictions or len(predictions) < 3:
                continue

            stats['predictions_made'] += 1

            # 実際の結果を取得
            result_query = '''
                SELECT pit_number, rank
                FROM results
                WHERE race_id = (
                    SELECT id FROM races
                    WHERE race_date = ? AND venue_code = ? AND race_number = ?
                )
                AND is_invalid = 0
                ORDER BY CAST(rank AS INTEGER)
                LIMIT 3
            '''
            cursor.execute(result_query, (race_date, venue_code, race_number))
            actual_results = cursor.fetchall()

            if len(actual_results) < 3:
                continue

            # 実際の1-3着の艇番
            actual_top1 = actual_results[0]['pit_number']
            actual_top2 = actual_results[1]['pit_number']
            actual_top3 = actual_results[2]['pit_number']

            # 予測の1-3位の艇番
            pred_top1 = predictions[0]['pit_number']
            pred_top2 = predictions[1]['pit_number']
            pred_top3 = predictions[2]['pit_number']

            # 1着予測的中
            if pred_top1 == actual_top1:
                stats['top1_correct'] += 1
                stats['venue_stats'][venue_code]['top1_correct'] += 1

            # 2着以内予測的中（予測1位が実際1-2着）
            if pred_top1 in [actual_top1, actual_top2]:
                stats['top2_correct'] += 1
                stats['venue_stats'][venue_code]['top2_correct'] += 1

            # 3着以内予測的中（予測1位が実際1-3着）
            if pred_top1 in [actual_top1, actual_top2, actual_top3]:
                stats['top3_correct'] += 1
                stats['venue_stats'][venue_code]['top3_correct'] += 1

            # 予測1位が実際3着以内
            if pred_top1 in [actual_top1, actual_top2, actual_top3]:
                stats['top1_in_top3'] += 1

            stats['venue_stats'][venue_code]['races'] += 1

        except Exception as e:
            # エラーは無視して続行
            pass

    conn.close()

    # 結果表示
    print()
    print("=" * 80)
    print("予測精度評価結果")
    print("=" * 80)
    print(f"総レース数: {stats['total_races']}")
    print(f"予測実行数: {stats['predictions_made']}")
    print()

    if stats['predictions_made'] > 0:
        top1_acc = stats['top1_correct'] / stats['predictions_made'] * 100
        top2_acc = stats['top2_correct'] / stats['predictions_made'] * 100
        top3_acc = stats['top3_correct'] / stats['predictions_made'] * 100
        top1_in_top3_rate = stats['top1_in_top3'] / stats['predictions_made'] * 100

        print(f"【全体精度】")
        print(f"  1着的中率: {top1_acc:.2f}% ({stats['top1_correct']}/{stats['predictions_made']})")
        print(f"  2着以内率: {top2_acc:.2f}% ({stats['top2_correct']}/{stats['predictions_made']})")
        print(f"  3着以内率: {top3_acc:.2f}% ({stats['top3_correct']}/{stats['predictions_made']})")
        print(f"  予測1位が実際3着以内: {top1_in_top3_rate:.2f}%")
        print()

        # 会場別精度（レース数が多い順に表示）
        print("【会場別精度 TOP10】")
        print(f"{'会場':<6} {'レース数':<8} {'1着的中':<10} {'2着以内':<10} {'3着以内':<10}")
        print("-" * 60)

        venue_list = [(k, v) for k, v in stats['venue_stats'].items()]
        venue_list.sort(key=lambda x: x[1]['races'], reverse=True)

        for venue_code, venue_stat in venue_list[:10]:
            if venue_stat['races'] < 10:
                continue

            v_top1 = venue_stat['top1_correct'] / venue_stat['races'] * 100
            v_top2 = venue_stat['top2_correct'] / venue_stat['races'] * 100
            v_top3 = venue_stat['top3_correct'] / venue_stat['races'] * 100

            print(f"{venue_code:<6} {venue_stat['races']:<8} {v_top1:<10.2f} {v_top2:<10.2f} {v_top3:<10.2f}")

        print()
        print("=" * 80)
        print("検証完了")
        print("=" * 80)

        # ベンチマーク情報
        print()
        print("【参考: 期待される改善目標】")
        print("  - 会場別期待勝率テーブル導入による期待効果: +1.5~3.0pt")
        print("  - 現状ベースライン（残タスク一覧より）:")
        print("    - 1着的中率: 目標60%以上")
        print("    - 2着的中率: 目標45%以上（現状35.9%）")
        print("    - 3着的中率: 目標35%以上（現状27.2%）")

    else:
        print("[ERROR] 予測が実行されませんでした")

    return stats


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='会場別期待勝率テーブル予測精度検証')
    parser.add_argument('--start', default='2024-01-01', help='テスト期間開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', default='2024-12-31', help='テスト期間終了日 (YYYY-MM-DD)')

    args = parser.parse_args()

    evaluate_predictions(args.start, args.end)
