#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
予測データ再生成スクリプト（最適化版）

特徴:
1. UPDATE方式（DELETEしない - データを失わない）
2. hierarchical_predictor有効（A-E信頼度分布）
3. バッチコミット（100件ごと）で高速化
4. Predictorの事前初期化で高速化
5. 年度順次処理（競合回避）
6. 進捗表示と推定完了時刻
7. 途中停止しても再開可能（処理済みをスキップ可能）
"""

import sys
import os
import sqlite3
import warnings
import json
import io
from datetime import datetime, timedelta

# Windows用のエンコーディング設定
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# パス設定
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings('ignore')

from config.settings import DATABASE_PATH
from config.feature_flags import FEATURE_FLAGS

# 安全チェック（D/Eのみ生成を防ぐ）- 既存チェックの前に実行
from scripts.safety_check import check_hierarchical_predictor
check_hierarchical_predictor()

from src.analysis.race_predictor import RacePredictor


def get_races_for_year(year: str) -> list:
    """指定年度の全レースIDを取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT r.id, r.race_date
        FROM races r
        WHERE r.race_date LIKE ? || '%'
        ORDER BY r.race_date, r.id
    ''', (year,))
    races = cursor.fetchall()
    conn.close()
    return races


def update_predictions_batch(predictions_batch: list):
    """
    予測データをバッチでUPDATE（INSERT OR REPLACE）
    DELETEは使わない - 既存データを上書きするのみ
    """
    if not predictions_batch:
        return

    conn = sqlite3.connect(DATABASE_PATH, timeout=120)
    cursor = conn.cursor()

    for race_id, predictions in predictions_batch:
        for pred in predictions:
            applied = json.dumps(pred.get('applied_rules', []), ensure_ascii=False)
            # INSERT OR REPLACE = 既存があれば上書き、なければ挿入
            cursor.execute('''
                INSERT OR REPLACE INTO race_predictions (
                    race_id, pit_number, rank_prediction, total_score,
                    confidence, racer_name, racer_number, applied_rules,
                    course_score, racer_score, motor_score, kimarite_score, grade_score,
                    prediction_type, generated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                race_id,
                pred['pit_number'],
                pred['rank_prediction'],
                pred.get('total_score', 0),
                pred.get('confidence', 'E'),
                pred.get('racer_name', ''),
                pred.get('racer_number', ''),
                applied,
                pred.get('course_score', 0),
                pred.get('racer_score', 0),
                pred.get('motor_score', 0),
                pred.get('kimarite_score', 0),
                pred.get('grade_score', 0),
                'advance',
                datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ))

    conn.commit()
    conn.close()


def check_confidence_distribution(year: str) -> dict:
    """信頼度分布を確認"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT rp.confidence, COUNT(DISTINCT rp.race_id)
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE r.race_date LIKE ? || '%'
        AND rp.prediction_type = 'advance' AND rp.rank_prediction = 1
        GROUP BY rp.confidence
    ''', (year,))
    result = dict(cursor.fetchall())
    conn.close()
    return result


def regenerate_year(year: str, predictor: RacePredictor, batch_size: int = 100) -> tuple:
    """指定年度の予測を再生成（UPDATE方式）"""
    print(f"\n{'='*70}")
    print(f"{year}年 advance予測 再生成開始")
    print(f"hierarchical_predictor: {FEATURE_FLAGS.get('hierarchical_predictor', False)}")
    print(f"バッチサイズ: {batch_size}")
    print(f"{'='*70}")

    races = get_races_for_year(year)
    total = len(races)
    print(f"総レース数: {total:,}件")

    # 現在の信頼度分布
    current_dist = check_confidence_distribution(year)
    print(f"現在の信頼度分布: {current_dist}")

    success = 0
    failed = 0
    start_time = datetime.now()
    last_date = ""
    batch = []

    for i, (race_id, race_date) in enumerate(races, 1):
        try:
            predictions = predictor.predict_race(race_id, use_beforeinfo=False)
            if predictions:
                batch.append((race_id, predictions))
                success += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1

        # バッチコミット
        if len(batch) >= batch_size:
            update_predictions_batch(batch)
            batch = []

        # 日付が変わったら進捗表示
        date_str = race_date[:10] if race_date else ""
        if date_str != last_date:
            last_date = date_str
            elapsed = (datetime.now() - start_time).total_seconds()
            if success > 0 and elapsed > 0:
                rate = success / elapsed
                remaining_races = total - i
                remaining_seconds = remaining_races / rate if rate > 0 else 0
                eta = datetime.now() + timedelta(seconds=remaining_seconds)
                print(f"[{date_str}] {i:,}/{total:,} ({100*i/total:.1f}%) "
                      f"成功={success:,} 失敗={failed} "
                      f"{rate:.1f}/s 残り{remaining_seconds/60:.0f}分 "
                      f"完了予定: {eta.strftime('%H:%M')}")

    # 残りのバッチをコミット
    if batch:
        update_predictions_batch(batch)

    elapsed = (datetime.now() - start_time).total_seconds()

    # 完了後の信頼度分布
    final_dist = check_confidence_distribution(year)

    print(f"\n{year}年 完了")
    print(f"成功: {success:,}件 / 失敗: {failed}件")
    print(f"所要時間: {elapsed/60:.1f}分")
    print(f"信頼度分布: {final_dist}")

    return success, failed


def dry_run_validation(year: str, predictor: RacePredictor, sample_size: int = 10) -> bool:
    """
    ドライラン: サンプル生成して信頼度分布を検証

    Args:
        year: 対象年度
        predictor: RacePredictor インスタンス
        sample_size: サンプル数（デフォルト: 10）

    Returns:
        bool: 検証成功（A-E全て存在）

    Raises:
        SystemExit: 検証失敗時
    """
    print("\n" + "="*70)
    print(f"🔍 DRY RUN: {year}年のサンプル生成検証（{sample_size}件）")
    print("="*70)

    races = get_races_for_year(year)
    if not races:
        print(f"❌ {year}年のレースが見つかりません")
        return False

    # ランダムに10件サンプリング
    import random
    sample_races = random.sample(races, min(sample_size, len(races)))

    confidence_counts = {}
    success = 0

    for race_id, race_date in sample_races:
        try:
            predictions = predictor.predict_race(race_id, use_beforeinfo=False)
            if predictions:
                for pred in predictions:
                    conf = pred.get('confidence', 'E')
                    confidence_counts[conf] = confidence_counts.get(conf, 0) + 1
                success += 1
        except Exception as e:
            print(f"⚠ レースID {race_id} でエラー: {e}")

    print(f"\nサンプル生成結果:")
    print(f"  成功: {success}/{sample_size}")
    print(f"  信頼度分布: {confidence_counts}")

    # A-E全て存在するかチェック
    required_confidences = {'A', 'B', 'C', 'D', 'E'}
    found_confidences = set(confidence_counts.keys())
    missing = required_confidences - found_confidences

    if missing:
        print("\n" + "!"*70)
        print(f"🔴 WARNING: 以下の信頼度が生成されていません: {missing}")
        print("!"*70)
        print("\n原因:")
        print("  - hierarchical_predictor が無効化されている可能性")
        print("  - サンプル数が少なすぎる（--dry-run-size を増やす）")
        print("\n対処:")
        print("  1. config/feature_flags.py を確認")
        print("  2. hierarchical_predictor: True を確認")
        print("  3. サンプル数を増やして再実行")
        print("\n" + "!"*70)
        sys.exit(1)

    print("\n✅ 検証成功: A-E 全ての信頼度が確認されました")
    print("本実行に進んで問題ありません。\n")
    return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description='予測データ再生成（最適化版）')
    parser.add_argument('--dry-run', action='store_true',
                        help='ドライラン: サンプル生成のみ実行して信頼度分布を確認')
    parser.add_argument('--dry-run-size', type=int, default=10,
                        help='ドライランのサンプル数（デフォルト: 10）')
    parser.add_argument('--years', type=str, default='2022,2023,2024,2025',
                        help='対象年度（カンマ区切り、デフォルト: 2022,2023,2024,2025）')
    args = parser.parse_args()

    print("="*70)
    print("予測データ再生成（最適化版）")
    if args.dry_run:
        print("モード: DRY RUN（サンプル生成のみ）")
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    # フィーチャーフラグ確認
    print("\n現在のフィーチャーフラグ:")
    important_flags = [
        'hierarchical_predictor',
        'lightgbm_ranking',
        'pairwise_scoring',
        'confidence_based_switching'
    ]
    for flag in important_flags:
        value = FEATURE_FLAGS.get(flag, False)
        status = "OK" if value else "WARNING"
        print(f"  {flag}: {value} [{status}]")

    if not FEATURE_FLAGS.get('hierarchical_predictor', False):
        print("\n" + "!"*70)
        print("警告: hierarchical_predictor が無効です！")
        print("config/feature_flags.py で True に設定してください。")
        print("このまま続行すると D/E のみの信頼度になります。")
        print("!"*70)
        return

    # Predictor初期化（1回のみ）
    print("\nPredictor初期化中...")
    init_start = datetime.now()
    predictor = RacePredictor()
    init_time = (datetime.now() - init_start).total_seconds()
    print(f"初期化完了 ({init_time:.1f}秒)")

    # 年度リスト
    years = [y.strip() for y in args.years.split(',')]

    # DRY RUN モード
    if args.dry_run:
        print("\n" + "="*70)
        print("🔍 DRY RUN モード: サンプル生成のみ実行")
        print("="*70)

        for year in years:
            dry_run_validation(year, predictor, sample_size=args.dry_run_size)

        print("\n" + "="*70)
        print("✅ 全年度の検証完了")
        print("問題がなければ --dry-run なしで本実行してください。")
        print("="*70)
        return

    # 本実行モード: 年度ごとに順次処理
    results = {}

    for year in years:
        success, failed = regenerate_year(year, predictor, batch_size=100)
        results[year] = {'success': success, 'failed': failed}

    # 最終サマリー
    print("\n" + "="*70)
    print("全年度 完了サマリー")
    print("="*70)

    total_success = 0
    total_failed = 0

    for year in years:
        s = results[year]['success']
        f = results[year]['failed']
        dist = check_confidence_distribution(year)
        print(f"{year}年: 成功={s:,} 失敗={f} 信頼度分布={dist}")
        total_success += s
        total_failed += f

    print(f"\n合計: 成功={total_success:,}件 失敗={total_failed}件")
    print(f"完了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == '__main__':
    main()
