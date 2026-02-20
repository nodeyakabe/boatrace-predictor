#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
新スコアのウェイト最適化スクリプト

複数のウェイトパターンで予測を生成し、ROIを比較して最適なウェイトを見つける。
"""
import sys
import os
import io
import subprocess
import json
from datetime import datetime

# Windows環境でのstdout/stderrエンコーディングをUTF-8に設定
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)


def modify_extended_scorer_weights(motor_weight, venue_weight):
    """
    extended_scorer.pyのウェイトを変更

    Args:
        motor_weight: motor_second_rateのmax_score
        venue_weight: venue_affinityのmax_score（weightsデフォルト値）
    """
    scorer_path = os.path.join(PROJECT_ROOT, 'src', 'analysis', 'extended_scorer.py')

    print(f'\nウェイト変更中: motor_second_rate={motor_weight}, venue_affinity={venue_weight}')

    # ファイルを読み込む
    with open(scorer_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # motor_second_rate のmax_scoreを変更
    # motor_second_rate_result = self.calculate_motor_second_rate_score(
    #     motor_second_rate,
    #     max_score=5.0
    # )
    import re

    # motor_second_rate のmax_score変更
    pattern1 = r'(motor_second_rate_result = self\.calculate_motor_second_rate_score\(\s+motor_second_rate,\s+max_score=)[\d.]+(\s+\))'
    replacement1 = f'\\g<1>{motor_weight}\\g<2>'
    content = re.sub(pattern1, replacement1, content)

    # venue_affinity のmax_score変更（weightsのデフォルト値）
    # max_score=float(weights.get('venue_affinity', 8))
    pattern2 = r"(max_score=float\(weights\.get\('venue_affinity', )[\d.]+(\)\))"
    replacement2 = f'\\g<1>{venue_weight}\\g<2>'
    content = re.sub(pattern2, replacement2, content)

    # 書き込む
    with open(scorer_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f'  ✅ extended_scorer.py を更新しました')


def generate_predictions_csv(output_csv):
    """
    予測CSVを生成（高速版を使用）
    """
    print(f'\n予測CSV生成中: {output_csv}')

    # 高速版のgenerate_predictions_to_csv_fastをインポート
    from scripts.analysis.test_new_scores_csv_fast import generate_predictions_to_csv_fast

    # 高速版を実行（2025年1-10月）
    try:
        generate_predictions_to_csv_fast('2025-01-01', '2025-10-31', output_csv)

        # 成功/エラー数を概算（CSVファイルから推定）
        import csv
        with open(output_csv, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            total_rows = sum(1 for _ in reader)

        # 6艇/レースで割って推定
        success_count = total_rows // 6
        error_count = 0  # 高速版はエラーカウント非対応

        print(f'  ✅ CSV出力完了: {total_rows}行（約{success_count}レース）')

        return success_count, error_count

    except Exception as e:
        print(f'  ❌ CSV生成エラー: {str(e)}')
        return 0, 1


def run_backtest(csv_path):
    """
    バックテストを実行してROIを取得
    """
    print(f'\nバックテスト実行中: {csv_path}')

    from scripts.analysis.backtest_old_vs_new_2025 import (
        load_csv_predictions,
        load_trifecta_odds_and_results,
        simulate_betting
    )
    from config.settings import DATABASE_PATH
    import sqlite3

    # CSVから予測を読み込む
    predictions = load_csv_predictions(csv_path)

    # DBに接続
    conn = sqlite3.connect(DATABASE_PATH)

    # オッズと結果を読み込む
    race_ids = list(predictions.keys())
    race_data = load_trifecta_odds_and_results(conn, race_ids)

    # バックテスト実行
    result = simulate_betting(predictions, race_data, 'テスト')

    conn.close()

    return result


def main():
    """
    メイン処理: 複数のウェイトパターンをテスト
    """
    print('='*80)
    print('新スコアのウェイト最適化')
    print('='*80)

    # テストパターン（重要な4パターンに絞る）
    # (motor_second_rate_max_score, venue_affinity_default)
    weight_patterns = [
        (0.0, 0.0),    # 新スコア無効化（ベースライン比較用）
        (5.0, 8.0),    # 現在（デフォルト）
        (10.0, 6.0),   # motor重視
        (3.0, 12.0),   # venue重視
    ]

    results = []
    temp_dir = os.path.join(PROJECT_ROOT, 'temp', 'weight_optimization')
    os.makedirs(temp_dir, exist_ok=True)

    # 元のextended_scorer.pyをバックアップ
    scorer_path = os.path.join(PROJECT_ROOT, 'src', 'analysis', 'extended_scorer.py')
    backup_path = scorer_path + '.backup_' + datetime.now().strftime('%Y%m%d_%H%M%S')
    import shutil
    shutil.copy2(scorer_path, backup_path)
    print(f'\n✅ extended_scorer.pyをバックアップ: {backup_path}')

    try:
        for idx, (motor_w, venue_w) in enumerate(weight_patterns, 1):
            print(f'\n{"="*80}')
            print(f'パターン {idx}/{len(weight_patterns)}: motor={motor_w}, venue={venue_w}')
            print(f'{"="*80}')

            # ウェイト変更
            modify_extended_scorer_weights(motor_w, venue_w)

            # CSV生成
            csv_filename = f'predictions_motor{motor_w}_venue{venue_w}.csv'
            csv_path = os.path.join(temp_dir, csv_filename)

            success, error = generate_predictions_csv(csv_path)

            # バックテスト実行
            backtest_result = run_backtest(csv_path)

            # 結果を記録
            results.append({
                'pattern_id': idx,
                'motor_weight': motor_w,
                'venue_weight': venue_w,
                'roi': backtest_result['roi'],
                'profit': backtest_result['profit'],
                'hit_rate': backtest_result['hit_rate'],
                'total_races': backtest_result['total_races'],
                'hit_count': backtest_result['hit_count']
            })

            print(f'\n結果: ROI={backtest_result["roi"]:.2f}%, 収支={backtest_result["profit"]:+.0f}円')

    finally:
        # 元のextended_scorer.pyを復元
        shutil.copy2(backup_path, scorer_path)
        print(f'\n✅ extended_scorer.pyを復元しました')

    # 結果をソートして表示
    print(f'\n{"="*80}')
    print('最適化結果サマリー（ROI順）')
    print(f'{"="*80}')

    results_sorted = sorted(results, key=lambda x: x['roi'], reverse=True)

    print(f'\n{"順位":<4} | {"motor":<6} | {"venue":<6} | {"ROI":>10} | {"収支":>12} | {"的中率":>8} | {"購入数":>6}')
    print('-'*80)

    for rank, r in enumerate(results_sorted, 1):
        print(f'{rank:<4} | {r["motor_weight"]:<6.1f} | {r["venue_weight"]:<6.1f} | {r["roi"]:>9.2f}% | {r["profit"]:>+11.0f}円 | {r["hit_rate"]:>7.2f}% | {r["total_races"]:>6}')

    # 結果をJSONで保存
    result_json_path = os.path.join(temp_dir, 'optimization_results.json')
    with open(result_json_path, 'w', encoding='utf-8') as f:
        json.dump(results_sorted, f, indent=2, ensure_ascii=False)

    print(f'\n✅ 最適化結果を保存: {result_json_path}')

    # 最適パターンを表示
    best = results_sorted[0]
    print(f'\n{"="*80}')
    print('最適ウェイト')
    print(f'{"="*80}')
    print(f'motor_second_rate: {best["motor_weight"]}')
    print(f'venue_affinity: {best["venue_weight"]}')
    print(f'ROI: {best["roi"]:.2f}%')
    print(f'収支: {best["profit"]:+.0f}円')
    print(f'的中率: {best["hit_rate"]:.2f}%')


if __name__ == '__main__':
    main()
