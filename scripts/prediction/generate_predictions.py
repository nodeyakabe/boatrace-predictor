#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
予測データ統合生成スクリプト

全ての予測生成タスクをこの1つのスクリプトで実行できます。

使用例:
    # ドライラン（10件サンプル生成で信頼度分布を確認）
    python scripts/generate_predictions.py --dry-run

    # 2024年のadvance予測を再生成
    python scripts/generate_predictions.py --years 2024 --type advance

    # 2022-2025年の全予測を再生成
    python scripts/generate_predictions.py --years 2022,2023,2024,2025 --type both

    # 未生成分のみ生成
    python scripts/generate_predictions.py --years 2024 --type advance --skip-existing

機能:
    - hierarchical_predictor 自動チェック（D/Eのみ生成を防止）
    - ドライラン機能（--dry-run）
    - UPSERT方式（既存データを削除しない）
    - バッチコミット（高速化）
    - 進捗表示と推定完了時刻
    - ロックファイル（並列実行制御）
"""

import sys
import os
import io
import sqlite3
import warnings
import json
import argparse
import random
from datetime import datetime, timedelta
from pathlib import Path

# Windows用のエンコーディング設定
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# パス設定
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)
warnings.filterwarnings('ignore')

from config.settings import DATABASE_PATH
from config.feature_flags import FEATURE_FLAGS

# 安全チェック（D/Eのみ生成を防ぐ）
from scripts.safety_check import check_hierarchical_predictor
check_hierarchical_predictor()

from src.analysis.race_predictor import RacePredictor


# ========================================
# ロックファイル管理
# ========================================

def acquire_lock(year: str) -> bool:
    """
    ロックファイルを取得（並列実行制御）

    Args:
        year: 対象年度

    Returns:
        bool: ロック取得成功
    """
    lock_dir = Path("data")
    lock_dir.mkdir(exist_ok=True)
    lock_file = lock_dir / f".lock_prediction_{year}"

    if lock_file.exists():
        print(f"❌ {year}年は既に処理中です（ロックファイル: {lock_file}）")
        print(f"   他のプロセスが実行中か、前回の処理が異常終了した可能性があります。")
        print(f"   確認して問題なければロックファイルを手動削除してください: del {lock_file}")
        return False

    # ロック取得
    with open(lock_file, 'w') as f:
        f.write(f"{os.getpid()}\n{datetime.now()}\n")

    print(f"✅ {year}年のロックを取得しました（PID: {os.getpid()}）")
    return True


def release_lock(year: str):
    """
    ロックファイルを解放

    Args:
        year: 対象年度
    """
    lock_file = Path("data") / f".lock_prediction_{year}"
    if lock_file.exists():
        lock_file.unlink()
        print(f"✅ {year}年のロックを解放しました")


# ========================================
# データベース操作
# ========================================

def get_races_for_year(year: str, skip_existing: bool = False, prediction_type: str = 'advance') -> list:
    """
    指定年度のレースIDを取得

    Args:
        year: 対象年度
        skip_existing: 既存予測をスキップするか
        prediction_type: 予測タイプ（advance/before）

    Returns:
        list: (race_id, race_date) のリスト
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    if skip_existing:
        # 未生成のレースのみ
        cursor.execute('''
            SELECT r.id, r.race_date
            FROM races r
            WHERE r.race_date LIKE ? || '%'
            AND r.id NOT IN (
                SELECT DISTINCT race_id FROM race_predictions
                WHERE prediction_type = ?
            )
            ORDER BY r.race_date, r.id
        ''', (year, prediction_type))
    else:
        # 全レース
        cursor.execute('''
            SELECT r.id, r.race_date
            FROM races r
            WHERE r.race_date LIKE ? || '%'
            ORDER BY r.race_date, r.id
        ''', (year,))

    races = cursor.fetchall()
    conn.close()
    return races


def update_predictions_batch(predictions_batch: list, prediction_type: str):
    """
    予測データをバッチでUPDATE（INSERT OR REPLACE）

    Args:
        predictions_batch: [(race_id, predictions), ...] のリスト
        prediction_type: 予測タイプ（advance/before）
    """
    if not predictions_batch:
        return

    conn = sqlite3.connect(DATABASE_PATH, timeout=120)
    cursor = conn.cursor()

    for race_id, predictions in predictions_batch:
        for pred in predictions:
            applied = json.dumps(pred.get('applied_rules', []), ensure_ascii=False)
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
                prediction_type,
                datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ))

    conn.commit()
    conn.close()


def check_confidence_distribution(year: str, prediction_type: str = 'advance') -> dict:
    """
    信頼度分布を確認

    Args:
        year: 対象年度
        prediction_type: 予測タイプ

    Returns:
        dict: {信頼度: レース数} の辞書
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT rp.confidence, COUNT(DISTINCT rp.race_id)
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE r.race_date LIKE ? || '%'
        AND rp.prediction_type = ? AND rp.rank_prediction = 1
        GROUP BY rp.confidence
    ''', (year, prediction_type))
    result = dict(cursor.fetchall())
    conn.close()
    return result


# ========================================
# ドライラン（サンプル生成検証）
# ========================================

def dry_run_validation(year: str, predictor: RacePredictor, sample_size: int = 10,
                      prediction_type: str = 'advance') -> bool:
    """
    ドライラン: サンプル生成して信頼度分布を検証

    Args:
        year: 対象年度
        predictor: RacePredictor インスタンス
        sample_size: サンプル数
        prediction_type: 予測タイプ

    Returns:
        bool: 検証成功（A-E全て存在）

    Raises:
        SystemExit: 検証失敗時
    """
    print("\n" + "="*70)
    print(f"🔍 DRY RUN: {year}年 {prediction_type} 予測のサンプル生成検証（{sample_size}件）")
    print("="*70)

    races = get_races_for_year(year)
    if not races:
        print(f"❌ {year}年のレースが見つかりません")
        return False

    # ランダムにサンプリング
    sample_races = random.sample(races, min(sample_size, len(races)))

    confidence_counts = {}
    success = 0

    use_beforeinfo = (prediction_type == 'before')

    for race_id, race_date in sample_races:
        try:
            predictions = predictor.predict_race(race_id, use_beforeinfo=use_beforeinfo)
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


# ========================================
# 予測生成（メイン処理）
# ========================================

def generate_predictions_for_year(year: str, predictor: RacePredictor,
                                   prediction_type: str = 'advance',
                                   skip_existing: bool = False,
                                   batch_size: int = 100) -> tuple:
    """
    指定年度の予測を生成

    Args:
        year: 対象年度
        predictor: RacePredictor インスタンス
        prediction_type: 予測タイプ（advance/before）
        skip_existing: 既存予測をスキップするか
        batch_size: バッチサイズ

    Returns:
        tuple: (成功件数, 失敗件数)
    """
    # ロック取得
    if not acquire_lock(year):
        return 0, 0

    try:
        print(f"\n{'='*70}")
        print(f"{year}年 {prediction_type} 予測生成開始")
        print(f"hierarchical_predictor: {FEATURE_FLAGS.get('hierarchical_predictor', False)}")
        print(f"スキップモード: {'ON（未生成のみ）' if skip_existing else 'OFF（全件再生成）'}")
        print(f"バッチサイズ: {batch_size}")
        print(f"{'='*70}")

        races = get_races_for_year(year, skip_existing=skip_existing, prediction_type=prediction_type)
        total = len(races)
        print(f"対象レース数: {total:,}件")

        # 現在の信頼度分布
        current_dist = check_confidence_distribution(year, prediction_type)
        print(f"現在の信頼度分布: {current_dist}")

        success = 0
        failed = 0
        start_time = datetime.now()
        last_date = ""
        batch = []

        use_beforeinfo = (prediction_type == 'before')

        for i, (race_id, race_date) in enumerate(races, 1):
            try:
                predictions = predictor.predict_race(race_id, use_beforeinfo=use_beforeinfo)
                if predictions:
                    batch.append((race_id, predictions))
                    success += 1
                else:
                    failed += 1
            except Exception as e:
                failed += 1

            # バッチコミット
            if len(batch) >= batch_size:
                update_predictions_batch(batch, prediction_type)
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
            update_predictions_batch(batch, prediction_type)

        elapsed = (datetime.now() - start_time).total_seconds()

        # 完了後の信頼度分布
        final_dist = check_confidence_distribution(year, prediction_type)

        print(f"\n{year}年 完了")
        print(f"成功: {success:,}件 / 失敗: {failed}件")
        print(f"所要時間: {elapsed/60:.1f}分")
        print(f"信頼度分布: {final_dist}")

        return success, failed

    finally:
        # ロック解放（必ず実行）
        release_lock(year)


# ========================================
# メイン関数
# ========================================

def main():
    parser = argparse.ArgumentParser(
        description='予測データ統合生成スクリプト',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # ドライラン（10件サンプル生成で信頼度分布を確認）
  python scripts/generate_predictions.py --dry-run

  # 2024年のadvance予測を再生成
  python scripts/generate_predictions.py --years 2024 --type advance

  # 2022-2025年の全予測を再生成
  python scripts/generate_predictions.py --years 2022,2023,2024,2025 --type both

  # 未生成分のみ生成
  python scripts/generate_predictions.py --years 2024 --type advance --skip-existing
        """
    )

    parser.add_argument('--years', type=str, default='2022,2023,2024,2025',
                        help='対象年度（カンマ区切り、デフォルト: 2022,2023,2024,2025）')
    parser.add_argument('--type', type=str, default='advance',
                        choices=['advance', 'before', 'both'],
                        help='予測タイプ（advance/before/both、デフォルト: advance）')
    parser.add_argument('--skip-existing', action='store_true',
                        help='既存予測をスキップして未生成分のみ処理')
    parser.add_argument('--dry-run', action='store_true',
                        help='ドライラン: サンプル生成のみ実行して信頼度分布を確認')
    parser.add_argument('--dry-run-size', type=int, default=10,
                        help='ドライランのサンプル数（デフォルト: 10）')
    parser.add_argument('--batch-size', type=int, default=100,
                        help='バッチコミットサイズ（デフォルト: 100）')

    args = parser.parse_args()

    print("="*70)
    print("予測データ統合生成スクリプト")
    if args.dry_run:
        print("モード: DRY RUN（サンプル生成のみ）")
    else:
        print(f"モード: 本実行（{args.type}）")
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    # フィーチャーフラグ確認
    print("\n現在のフィーチャーフラグ:")
    important_flags = [
        'hierarchical_predictor',
        'lightgbm_ranking',
        'pairwise_scoring',
    ]
    for flag in important_flags:
        value = FEATURE_FLAGS.get(flag, False)
        status = "✓" if value else "✗"
        print(f"  [{status}] {flag}: {value}")

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

        types = ['advance', 'before'] if args.type == 'both' else [args.type]

        for year in years:
            for pred_type in types:
                dry_run_validation(year, predictor, sample_size=args.dry_run_size, prediction_type=pred_type)

        print("\n" + "="*70)
        print("✅ 全年度・全タイプの検証完了")
        print("問題がなければ --dry-run なしで本実行してください。")
        print("="*70)
        return

    # 本実行モード
    types = ['advance', 'before'] if args.type == 'both' else [args.type]
    results = {}

    for year in years:
        results[year] = {}
        for pred_type in types:
            success, failed = generate_predictions_for_year(
                year, predictor,
                prediction_type=pred_type,
                skip_existing=args.skip_existing,
                batch_size=args.batch_size
            )
            results[year][pred_type] = {'success': success, 'failed': failed}

    # 最終サマリー
    print("\n" + "="*70)
    print("全年度・全タイプ 完了サマリー")
    print("="*70)

    total_success = 0
    total_failed = 0

    for year in years:
        for pred_type in types:
            s = results[year][pred_type]['success']
            f = results[year][pred_type]['failed']
            dist = check_confidence_distribution(year, pred_type)
            print(f"{year}年 {pred_type}: 成功={s:,} 失敗={f} 信頼度分布={dist}")
            total_success += s
            total_failed += f

    print(f"\n合計: 成功={total_success:,}件 失敗={total_failed}件")
    print(f"完了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == '__main__':
    main()
