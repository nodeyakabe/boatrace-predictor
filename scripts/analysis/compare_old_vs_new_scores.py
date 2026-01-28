#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
旧版予測（DB）vs 新スコア版（CSV）の精度比較

旧版: race_predictionsテーブル（2026-01-08生成、Phase 2前）
新版: new_scores_test_2025_01_10.csv（Phase 2後、motor_second_rate/venue_affinity追加）
"""
import sys
import os
import io
import pandas as pd
import sqlite3
from collections import defaultdict

# Windows環境でのstdout/stderrエンコーディングをUTF-8に設定
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH


def load_csv_predictions(csv_path):
    """CSVから新スコア版予測を読み込む"""
    print(f'\nCSVから新スコア版予測を読み込み中: {csv_path}')
    df = pd.read_csv(csv_path)

    # race_id, pit_number ごとに予測順位を取得
    predictions = {}
    for _, row in df.iterrows():
        race_id = row['race_id']
        pit_number = row['pit_number']
        rank_pred = row['rank_prediction']

        if race_id not in predictions:
            predictions[race_id] = {}
        predictions[race_id][pit_number] = rank_pred

    print(f'  読み込み完了: {len(predictions)}レース')
    return predictions


def load_db_predictions(conn, race_ids):
    """DBから旧版予測を読み込む"""
    print(f'\nDBから旧版予測を読み込み中...')

    # race_idsをチャンクに分割（SQLiteのパラメータ制限対策）
    chunk_size = 500
    all_predictions = {}

    for i in range(0, len(race_ids), chunk_size):
        chunk_ids = race_ids[i:i+chunk_size]
        placeholders = ','.join(['?'] * len(chunk_ids))

        query = f"""
            SELECT race_id, pit_number, rank_prediction
            FROM race_predictions
            WHERE race_id IN ({placeholders})
            AND prediction_type = 'before'
        """

        cursor = conn.cursor()
        cursor.execute(query, chunk_ids)

        for race_id, pit_number, rank_pred in cursor.fetchall():
            if race_id not in all_predictions:
                all_predictions[race_id] = {}
            all_predictions[race_id][pit_number] = rank_pred

    print(f'  読み込み完了: {len(all_predictions)}レース')
    return all_predictions


def load_actual_results(conn, race_ids):
    """実結果を読み込む"""
    print(f'\n実結果を読み込み中...')

    chunk_size = 500
    all_results = {}

    for i in range(0, len(race_ids), chunk_size):
        chunk_ids = race_ids[i:i+chunk_size]
        placeholders = ','.join(['?'] * len(chunk_ids))

        query = f"""
            SELECT race_id, pit_number, rank
            FROM results
            WHERE race_id IN ({placeholders})
            AND rank IS NOT NULL
            AND is_invalid = 0
        """

        cursor = conn.cursor()
        cursor.execute(query, chunk_ids)

        for race_id, pit_number, rank in cursor.fetchall():
            if race_id not in all_results:
                all_results[race_id] = {}
            # rankはTEXT型なのでint変換
            try:
                all_results[race_id][pit_number] = int(rank)
            except (ValueError, TypeError):
                pass

    print(f'  読み込み完了: {len(all_results)}レース')
    return all_results


def calculate_accuracy(predictions, actual_results):
    """精度指標を計算"""

    # 各順位の的中数をカウント
    rank_matches = defaultdict(int)
    rank_totals = defaultdict(int)

    # 順位誤差の累積
    rank_errors = []

    # 3連単的中数（1-2-3順位完全一致）
    trifecta_match = 0
    total_races = 0

    for race_id, pred_ranks in predictions.items():
        if race_id not in actual_results:
            continue

        actual_ranks = actual_results[race_id]

        # 6艇すべてに予測と実結果がある場合のみカウント
        if len(pred_ranks) != 6 or len(actual_ranks) != 6:
            continue

        total_races += 1

        # 予測順位ごとに実結果を確認
        for pit, pred_rank in pred_ranks.items():
            if pit not in actual_ranks:
                continue

            actual_rank = actual_ranks[pit]

            # 完全一致カウント
            if pred_rank == actual_rank:
                rank_matches[pred_rank] += 1
            rank_totals[pred_rank] += 1

            # 順位誤差を記録
            rank_errors.append(abs(pred_rank - actual_rank))

        # 3連単チェック（1位、2位、3位すべて一致）
        pred_top3_pits = sorted(pred_ranks.items(), key=lambda x: x[1])[:3]
        actual_top3_pits = sorted(actual_ranks.items(), key=lambda x: x[1])[:3]

        pred_top3 = tuple(sorted([p[0] for p in pred_top3_pits]))
        actual_top3 = tuple(sorted([p[0] for p in actual_top3_pits]))

        if pred_top3 == actual_top3:
            # 順位も完全一致するか確認
            match = True
            for pit in pred_top3:
                if pred_ranks[pit] != actual_ranks[pit]:
                    match = False
                    break
            if match:
                trifecta_match += 1

    # 結果集計
    results = {
        'total_races': total_races,
        'rank_accuracy': {},
        'avg_rank_error': sum(rank_errors) / len(rank_errors) if rank_errors else 0,
        'trifecta_accuracy': trifecta_match / total_races * 100 if total_races > 0 else 0,
        'trifecta_matches': trifecta_match
    }

    for rank in range(1, 7):
        if rank in rank_totals and rank_totals[rank] > 0:
            results['rank_accuracy'][rank] = rank_matches[rank] / rank_totals[rank] * 100
        else:
            results['rank_accuracy'][rank] = 0.0

    return results


def print_comparison(old_results, new_results):
    """比較結果を表示"""
    print('\n' + '='*80)
    print('予測精度比較: 旧版（DB） vs 新スコア版（CSV）')
    print('='*80)

    print(f'\n対象レース数:')
    print(f'  旧版: {old_results["total_races"]}レース')
    print(f'  新版: {new_results["total_races"]}レース')

    print(f'\n平均順位誤差（小さいほど良い）:')
    print(f'  旧版: {old_results["avg_rank_error"]:.3f}')
    print(f'  新版: {new_results["avg_rank_error"]:.3f}')
    diff = old_results["avg_rank_error"] - new_results["avg_rank_error"]
    print(f'  差分: {diff:+.3f} {"✅ 改善" if diff > 0 else "❌ 悪化"}')

    print(f'\n3連単的中率:')
    print(f'  旧版: {old_results["trifecta_accuracy"]:.2f}% ({old_results["trifecta_matches"]}回)')
    print(f'  新版: {new_results["trifecta_accuracy"]:.2f}% ({new_results["trifecta_matches"]}回)')
    diff = new_results["trifecta_accuracy"] - old_results["trifecta_accuracy"]
    print(f'  差分: {diff:+.2f}pt {"✅ 改善" if diff > 0 else "❌ 悪化"}')

    print(f'\n順位別的中率:')
    print(f'  順位 | 旧版    | 新版    | 差分')
    print(f'  -----|---------|---------|--------')
    for rank in range(1, 7):
        old_acc = old_results['rank_accuracy'][rank]
        new_acc = new_results['rank_accuracy'][rank]
        diff = new_acc - old_acc
        symbol = "✅" if diff > 0 else "❌" if diff < 0 else "="
        print(f'  {rank}位  | {old_acc:6.2f}% | {new_acc:6.2f}% | {diff:+6.2f}pt {symbol}')

    print('\n' + '='*80)
    print('総合評価')
    print('='*80)

    improvements = 0
    if diff > 0:  # 平均順位誤差の改善
        improvements += 1
    if new_results["trifecta_accuracy"] > old_results["trifecta_accuracy"]:
        improvements += 1

    rank_improvements = sum(1 for rank in range(1, 7)
                           if new_results['rank_accuracy'][rank] > old_results['rank_accuracy'][rank])

    print(f'\n改善指標数: {improvements + rank_improvements} / 8')

    if improvements >= 1 and rank_improvements >= 3:
        print('\n✅ 新スコアによる改善効果が確認されました')
        print('   → DB反映を推奨')
    elif improvements >= 1 or rank_improvements >= 2:
        print('\n⚠️  一部改善が見られますが、効果は限定的です')
        print('   → 慎重に判断してください')
    else:
        print('\n❌ 改善効果が確認できませんでした')
        print('   → DB反映は非推奨')


if __name__ == '__main__':
    csv_path = os.path.join(PROJECT_ROOT, 'temp', 'new_scores_test_2025_01_10.csv')

    print('='*80)
    print('旧版予測 vs 新スコア版予測 精度比較')
    print('='*80)
    print(f'旧版: race_predictions (2026-01-08生成)')
    print(f'新版: {csv_path}')

    # CSVから新スコア版予測を読み込む
    new_predictions = load_csv_predictions(csv_path)

    # DBに接続
    conn = sqlite3.connect(DATABASE_PATH)

    # 対象race_idリスト
    race_ids = list(new_predictions.keys())

    # DBから旧版予測を読み込む
    old_predictions = load_db_predictions(conn, race_ids)

    # 実結果を読み込む
    actual_results = load_actual_results(conn, race_ids)

    # 精度計算
    print('\n旧版予測の精度を計算中...')
    old_results = calculate_accuracy(old_predictions, actual_results)

    print('新スコア版予測の精度を計算中...')
    new_results = calculate_accuracy(new_predictions, actual_results)

    # 比較結果を表示
    print_comparison(old_results, new_results)

    conn.close()

    print('\n処理完了')
