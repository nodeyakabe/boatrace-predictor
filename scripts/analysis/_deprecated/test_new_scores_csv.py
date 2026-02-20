#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
新スコア（motor_second_rate、venue_affinity、chikusen_time）の効果確認スクリプト

CSV出力方式でDB競合を回避しながら、新スコアの影響を確認します。
"""
import sys
import os
import io
import csv
import json
from datetime import datetime, timedelta

# Windows環境でのstdout/stderrエンコーディングをUTF-8に設定
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.analysis.race_predictor import RacePredictor
from config.settings import DATABASE_PATH
import sqlite3


def generate_predictions_to_csv(start_date: str, end_date: str, output_csv: str):
    """
    指定期間の予測を生成してCSVに出力

    Args:
        start_date: 開始日（YYYY-MM-DD）
        end_date: 終了日（YYYY-MM-DD）
        output_csv: 出力CSVファイルパス
    """
    print(f'='*80)
    print(f'新スコア効果確認テスト（CSV出力）')
    print(f'='*80)
    print(f'期間: {start_date} 〜 {end_date}')
    print(f'出力: {output_csv}')
    print(f'='*80)

    # RacePredictorを初期化（キャッシュ有効）
    predictor = RacePredictor(use_cache=True)

    # 対象レースを取得
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, race_date, venue_code, race_number
        FROM races
        WHERE race_date BETWEEN ? AND ?
        ORDER BY race_date, venue_code, race_number
    """, (start_date, end_date))

    races = cursor.fetchall()
    conn.close()

    print(f'\n対象レース数: {len(races)}件')

    # CSV出力準備
    fieldnames = [
        'race_date', 'venue_code', 'race_number', 'race_id',
        'pit_number', 'racer_name', 'rank_prediction', 'total_score',
        'extended_score', 'motor_second_rate_score', 'motor_second_rate_value',
        'venue_affinity_score', 'local_win_rate', 'win_rate', 'affinity_diff',
        'chikusen_time_score', 'chikusen_time_value', 'chikusen_time_rank'
    ]

    csv_data = []
    success_count = 0
    error_count = 0

    # 日次データを一括ロード（高速化）
    # NOTE: 事前ロードは無効化（大量データで問題発生のため）
    # if predictor.batch_loader:
    #     print('\n日次データを一括ロード中...')
    #     # 各日付ごとにロード
    #     current_date = datetime.strptime(start_date, '%Y-%m-%d')
    #     end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    #
    #     while current_date <= end_dt:
    #         date_str = current_date.strftime('%Y-%m-%d')
    #         predictor.batch_loader.load_daily_data(date_str)
    #         current_date += timedelta(days=1)
    #
    #     print('データロード完了')

    # 予測生成
    print(f'\n予測生成中...')
    for idx, (race_id, race_date, venue_code, race_number) in enumerate(races, 1):
        if idx % 10 == 0:
            print(f'  [{idx}/{len(races)}] {race_date} {venue_code} {race_number}R', end='\r')

        try:
            # before予測を生成（直前情報使用）
            predictions = predictor.predict_race(race_id, use_beforeinfo=True)

            if not predictions:
                error_count += 1
                continue

            # 各艇の予測結果を抽出
            for pred in predictions:
                # extended_detail から新スコア情報を取得（extended_scoreはfloat値）
                ext_detail = pred.get('extended_detail', {})

                # motor_extended から second_rate 情報を取得
                motor_extended = ext_detail.get('motor_extended', {})
                motor_second_rate_value = motor_extended.get('second_rate')
                # motor_extended自体のスコアを使用
                motor_second_rate_score = motor_extended.get('score', 0)

                # venue_affinity
                venue_affinity = ext_detail.get('venue_affinity', {})
                venue_affinity_score = venue_affinity.get('score', 0)
                local_win_rate = venue_affinity.get('local_win_rate')
                national_win_rate = venue_affinity.get('national_win_rate')
                affinity_diff = venue_affinity.get('affinity_diff')

                # chikusen_time（extended_detailに含まれていない場合は0）
                chikusen_time = ext_detail.get('chikusen_time', {})
                chikusen_time_score = chikusen_time.get('score', 0) if isinstance(chikusen_time, dict) else 0
                chikusen_time_value = chikusen_time.get('chikusen_time') if isinstance(chikusen_time, dict) else None
                chikusen_time_rank = chikusen_time.get('rank') if isinstance(chikusen_time, dict) else None

                csv_data.append({
                    'race_date': race_date,
                    'venue_code': venue_code,
                    'race_number': race_number,
                    'race_id': race_id,
                    'pit_number': pred.get('pit_number'),
                    'racer_name': pred.get('racer_name', ''),
                    'rank_prediction': pred.get('rank_prediction'),
                    'total_score': pred.get('total_score', 0),
                    'extended_score': pred.get('extended_score', 0),  # これはfloat値
                    'motor_second_rate_score': motor_second_rate_score,
                    'motor_second_rate_value': motor_second_rate_value,
                    'venue_affinity_score': venue_affinity_score,
                    'local_win_rate': local_win_rate,
                    'win_rate': national_win_rate,
                    'affinity_diff': affinity_diff,
                    'chikusen_time_score': chikusen_time_score,
                    'chikusen_time_value': chikusen_time_value,
                    'chikusen_time_rank': chikusen_time_rank
                })

            success_count += 1

        except Exception as e:
            error_count += 1
            print(f'\n  エラー (race_id={race_id}): {str(e)[:50]}')

    print(f'\n\n予測生成完了: 成功={success_count}件, エラー={error_count}件')

    # CSVに書き込み
    print(f'\nCSVファイルに書き込み中: {output_csv}')
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_data)

    print(f'書き込み完了: {len(csv_data)}行')

    # 統計情報を表示
    print(f'\n{"="*80}')
    print(f'新スコア統計情報')
    print(f'{"="*80}')

    # motor_second_rate の統計
    motor_scores = [row['motor_second_rate_score'] for row in csv_data if row['motor_second_rate_value'] is not None]
    motor_values = [row['motor_second_rate_value'] for row in csv_data if row['motor_second_rate_value'] is not None]

    if motor_scores:
        print(f'\nモーター2連対率:')
        print(f'  データ有り: {len(motor_scores)}/{len(csv_data)} ({len(motor_scores)*100/len(csv_data):.1f}%)')
        print(f'  スコア平均: {sum(motor_scores)/len(motor_scores):.2f}')
        print(f'  スコア範囲: {min(motor_scores):.2f} 〜 {max(motor_scores):.2f}')
        print(f'  値の平均: {sum(motor_values)/len(motor_values):.1f}%')

    # venue_affinity の統計
    affinity_scores = [row['venue_affinity_score'] for row in csv_data if row['affinity_diff'] is not None]
    affinity_diffs = [row['affinity_diff'] for row in csv_data if row['affinity_diff'] is not None]

    if affinity_scores:
        print(f'\n会場相性:')
        print(f'  データ有り: {len(affinity_scores)}/{len(csv_data)} ({len(affinity_scores)*100/len(csv_data):.1f}%)')
        print(f'  スコア平均: {sum(affinity_scores)/len(affinity_scores):.2f}')
        print(f'  スコア範囲: {min(affinity_scores):.2f} 〜 {max(affinity_scores):.2f}')
        print(f'  相性差平均: {sum(affinity_diffs)/len(affinity_diffs):.2f}pt')

    # chikusen_time の統計
    chikusen_scores = [row['chikusen_time_score'] for row in csv_data if row['chikusen_time_value'] is not None]
    chikusen_values = [row['chikusen_time_value'] for row in csv_data if row['chikusen_time_value'] is not None]

    if chikusen_scores:
        print(f'\n直線タイム:')
        print(f'  データ有り: {len(chikusen_scores)}/{len(csv_data)} ({len(chikusen_scores)*100/len(csv_data):.1f}%)')
        print(f'  スコア平均: {sum(chikusen_scores)/len(chikusen_scores):.2f}')
        print(f'  スコア範囲: {min(chikusen_scores):.2f} 〜 {max(chikusen_scores):.2f}')
        print(f'  値の平均: {sum(chikusen_values)/len(chikusen_values):.2f}秒')
    else:
        print(f'\n直線タイム:')
        print(f'  データ有り: 0/{len(csv_data)} (0.0%)')

    print(f'\n{"="*80}')
    print(f'CSV出力完了: {output_csv}')
    print(f'{"="*80}')


if __name__ == '__main__':
    # 2025年1-10月でテスト（11月以降でバッチローダー問題発生のため）
    output_dir = os.path.join(PROJECT_ROOT, 'temp')
    os.makedirs(output_dir, exist_ok=True)

    output_csv = os.path.join(output_dir, 'new_scores_test_2025_01_10.csv')

    generate_predictions_to_csv('2025-01-01', '2025-10-31', output_csv)
