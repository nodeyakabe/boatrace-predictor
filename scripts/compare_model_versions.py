# -*- coding: utf-8 -*-
"""
モデルバージョン比較スクリプト

目的:
- v1 (改善前) vs v2 (改善後) の予測精度を比較
- 1着・2着・3着的中率 + 3連単的中率を検証
"""

import sys
from pathlib import Path
import sqlite3
from collections import defaultdict
import itertools

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.analysis.race_predictor import RacePredictor

DB_PATH = ROOT_DIR / 'data' / 'boatrace.db'


def calculate_trifecta_accuracy(predictions, actual_results):
    """
    3連単的中率を計算

    Args:
        predictions: 予測結果（上位3艇）
        actual_results: 実際の結果（上位3着）

    Returns:
        bool: 3連単が的中したかどうか
    """
    if len(predictions) < 3 or len(actual_results) < 3:
        return False

    pred_top3 = [predictions[i]['pit_number'] for i in range(3)]
    actual_top3 = [actual_results[i]['pit_number'] for i in range(3)]

    return pred_top3 == actual_top3


def evaluate_model(model_version, test_period_start='2024-01-01', test_period_end='2024-12-31'):
    """
    指定モデルバージョンで予測精度を評価

    Args:
        model_version: 'v1' または 'v2'
        test_period_start: テスト期間開始日
        test_period_end: テスト期間終了日

    Returns:
        dict: 評価結果
    """
    print(f"\n{'='*80}")
    print(f"モデル {model_version.upper()} 評価中...")
    print(f"{'='*80}")

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

    # HierarchicalPredictorで直接予測
    from src.prediction.hierarchical_predictor import HierarchicalPredictor
    use_v2 = (model_version == 'v2')
    predictor_hp = HierarchicalPredictor(
        db_path=str(DB_PATH),
        model_dir='models',
        use_v2=use_v2,
        use_optimized=True
    )
    predictor_hp.load_models()

    # 評価指標
    stats = {
        'total_races': 0,
        'predictions_made': 0,
        'top1_correct': 0,
        'top2_correct': 0,
        'top3_correct': 0,
        'trifecta_correct': 0,  # 3連単的中
        'quinella_place_correct': 0,  # ワイド的中（予測1-2位が実際3着以内）
    }

    # 進捗表示用
    milestone = len(test_races) // 20

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
            # race_idを取得
            race_id_query = '''
                SELECT id FROM races
                WHERE race_date = ? AND venue_code = ? AND race_number = ?
            '''
            cursor.execute(race_id_query, (race_date, venue_code, race_number))
            race_id_row = cursor.fetchone()
            if not race_id_row:
                continue

            race_id = race_id_row['id']

            # 予測実行（HierarchicalPredictor使用）
            pred_result = predictor_hp.predict_race(
                race_id=race_id,
                use_conditional_model=True
            )

            if not pred_result or 'top_combinations' not in pred_result:
                continue

            # top_combinationsから上位3艇を抽出
            top_combs = pred_result['top_combinations']
            if not top_combs or len(top_combs) == 0:
                continue

            # 最も確率が高い組み合わせを取得
            # 形式: ('1-3-2', 0.097...)
            best_comb = top_combs[0]
            if len(best_comb) < 2:
                continue

            # 文字列 '1-3-2' をパース
            comb_str = best_comb[0]
            pit_numbers = comb_str.split('-')
            if len(pit_numbers) < 3:
                continue

            predictions = [int(pit_numbers[0]), int(pit_numbers[1]), int(pit_numbers[2])]  # [1位予測, 2位予測, 3位予測]

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

            # 予測の1-3位の艇番（リスト形式）
            pred_top1 = predictions[0]
            pred_top2 = predictions[1]
            pred_top3 = predictions[2]

            # 1着予測的中
            if pred_top1 == actual_top1:
                stats['top1_correct'] += 1

            # 2着以内予測的中
            if pred_top1 in [actual_top1, actual_top2]:
                stats['top2_correct'] += 1

            # 3着以内予測的中
            if pred_top1 in [actual_top1, actual_top2, actual_top3]:
                stats['top3_correct'] += 1

            # 3連単的中
            if (pred_top1 == actual_top1 and
                pred_top2 == actual_top2 and
                pred_top3 == actual_top3):
                stats['trifecta_correct'] += 1

            # ワイド的中（予測1-2位が両方とも実際3着以内）
            actual_top3_set = {actual_top1, actual_top2, actual_top3}
            if pred_top1 in actual_top3_set and pred_top2 in actual_top3_set:
                stats['quinella_place_correct'] += 1

        except Exception as e:
            # エラーは無視して続行
            import traceback
            if idx < 10:  # 最初の10エラーのみ表示
                print(f"[DEBUG] Error at race {race_date}/{venue_code}/{race_number}: {e}")
                traceback.print_exc()
            pass

    conn.close()

    return stats


def print_comparison(v1_stats, v2_stats):
    """比較結果を表示"""
    print("\n" + "="*80)
    print("モデルバージョン比較結果")
    print("="*80)

    if v1_stats['predictions_made'] == 0 or v2_stats['predictions_made'] == 0:
        print("[ERROR] 予測が実行されませんでした")
        return

    # v1結果
    v1_top1 = v1_stats['top1_correct'] / v1_stats['predictions_made'] * 100
    v1_top2 = v1_stats['top2_correct'] / v1_stats['predictions_made'] * 100
    v1_top3 = v1_stats['top3_correct'] / v1_stats['predictions_made'] * 100
    v1_trifecta = v1_stats['trifecta_correct'] / v1_stats['predictions_made'] * 100
    v1_wide = v1_stats['quinella_place_correct'] / v1_stats['predictions_made'] * 100

    # v2結果
    v2_top1 = v2_stats['top1_correct'] / v2_stats['predictions_made'] * 100
    v2_top2 = v2_stats['top2_correct'] / v2_stats['predictions_made'] * 100
    v2_top3 = v2_stats['top3_correct'] / v2_stats['predictions_made'] * 100
    v2_trifecta = v2_stats['trifecta_correct'] / v2_stats['predictions_made'] * 100
    v2_wide = v2_stats['quinella_place_correct'] / v2_stats['predictions_made'] * 100

    # 表形式で表示
    print(f"\n{'指標':<20} {'V1 (改善前)':<15} {'V2 (改善後)':<15} {'差分':<15}")
    print("-" * 70)
    print(f"{'対象レース数':<20} {v1_stats['predictions_made']:<15} {v2_stats['predictions_made']:<15} {v2_stats['predictions_made'] - v1_stats['predictions_made']:<15}")
    print()
    print(f"{'1着的中率':<20} {v1_top1:<14.2f}% {v2_top1:<14.2f}% {v2_top1 - v1_top1:+14.2f}pt")
    print(f"{'2着以内率':<20} {v1_top2:<14.2f}% {v2_top2:<14.2f}% {v2_top2 - v1_top2:+14.2f}pt")
    print(f"{'3着以内率':<20} {v1_top3:<14.2f}% {v2_top3:<14.2f}% {v2_top3 - v1_top3:+14.2f}pt")
    print()
    print(f"{'3連単的中率':<20} {v1_trifecta:<14.2f}% {v2_trifecta:<14.2f}% {v2_trifecta - v1_trifecta:+14.2f}pt")
    print(f"{'ワイド的中率':<20} {v1_wide:<14.2f}% {v2_wide:<14.2f}% {v2_wide - v1_wide:+14.2f}pt")
    print()
    print(f"{'3連単的中数':<20} {v1_stats['trifecta_correct']:<15} {v2_stats['trifecta_correct']:<15} {v2_stats['trifecta_correct'] - v1_stats['trifecta_correct']:+15}")

    print("\n" + "="*80)
    print("改善効果サマリー")
    print("="*80)

    improvements = []
    if v2_top1 > v1_top1:
        improvements.append(f"[+] 1着的中率: {v2_top1 - v1_top1:+.2f}pt 向上")
    else:
        improvements.append(f"[-] 1着的中率: {v2_top1 - v1_top1:+.2f}pt 低下")

    if v2_trifecta > v1_trifecta:
        improvements.append(f"[+] 3連単的中率: {v2_trifecta - v1_trifecta:+.2f}pt 向上")
    else:
        improvements.append(f"[-] 3連単的中率: {v2_trifecta - v1_trifecta:+.2f}pt 低下")

    if v2_wide > v1_wide:
        improvements.append(f"[+] ワイド的中率: {v2_wide - v1_wide:+.2f}pt 向上")
    else:
        improvements.append(f"[-] ワイド的中率: {v2_wide - v1_wide:+.2f}pt 低下")

    for imp in improvements:
        print(imp)

    print("\n【参考情報】")
    print(f"- 3連単平均配当を3,000円と仮定した場合:")
    print(f"  V1: {v1_stats['trifecta_correct']}的中 × 3,000円 = {v1_stats['trifecta_correct'] * 3000:,}円")
    print(f"  V2: {v2_stats['trifecta_correct']} 的中 × 3,000円 = {v2_stats['trifecta_correct'] * 3000:,}円")
    print(f"  差分: {(v2_stats['trifecta_correct'] - v1_stats['trifecta_correct']) * 3000:+,}円")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='モデルバージョン比較')
    parser.add_argument('--start', default='2024-01-01', help='テスト期間開始日')
    parser.add_argument('--end', default='2024-12-31', help='テスト期間終了日')

    args = parser.parse_args()

    # V1評価
    v1_stats = evaluate_model('v1', args.start, args.end)

    # V2評価
    v2_stats = evaluate_model('v2', args.start, args.end)

    # 比較結果表示
    print_comparison(v1_stats, v2_stats)
