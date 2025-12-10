#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2025年全レースの予想再生成（並列版・ハイブリッドスコアリング適用）

ProcessPoolExecutorで並列処理し、高速化を実現。
"""
import sys
import os
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

os.environ['PYTHONUNBUFFERED'] = '1'

import time
import sqlite3
import warnings
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count

warnings.filterwarnings('ignore')

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def process_single_day(args):
    """
    1日分の予想を生成（ワーカープロセス用）

    Args:
        args: (race_date, db_path)

    Returns:
        dict: 処理結果
    """
    race_date, db_path = args

    # ワーカー内でインポート（プロセス分離のため）
    import sqlite3
    import warnings
    warnings.filterwarnings('ignore')

    sys.path.insert(0, str(PROJECT_ROOT))
    from src.analysis.race_predictor import RacePredictor

    result = {
        'date': race_date,
        'total_races': 0,
        'succeeded': 0,
        'failed': 0,
        'predictions': []  # 予測結果を一時保存
    }

    try:
        # Predictorを初期化（各ワーカーで1回のみ）
        predictor = RacePredictor(use_cache=True)

        # その日のレースを取得
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT r.id, r.venue_code, r.race_number
            FROM races r
            WHERE r.race_date = ?
            ORDER BY r.venue_code, r.race_number
        """, (race_date,))

        races = cursor.fetchall()
        conn.close()

        if not races:
            return result

        result['total_races'] = len(races)

        for race_id, venue_code, race_num in races:
            try:
                predictions = predictor.predict_race(race_id)
                if predictions and len(predictions) >= 6:
                    result['predictions'].append({
                        'race_id': race_id,
                        'data': predictions
                    })
                    result['succeeded'] += 1
                else:
                    result['failed'] += 1
            except:
                result['failed'] += 1

    except Exception as e:
        result['failed'] = result['total_races']

    return result


def save_predictions_batch(predictions_list, db_path):
    """
    予測結果をバッチでDBに保存（メインプロセスで実行）
    """
    if not predictions_list:
        return 0

    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()
    saved = 0

    try:
        generated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        for item in predictions_list:
            race_id = item['race_id']
            predictions = item['data']

            # 既存データを削除
            cursor.execute('DELETE FROM race_predictions WHERE race_id = ?', (race_id,))

            for pred in predictions:
                cursor.execute("""
                    INSERT OR REPLACE INTO race_predictions (
                        race_id, pit_number, rank_prediction, total_score,
                        confidence, racer_name, racer_number, applied_rules,
                        course_score, racer_score, motor_score, kimarite_score,
                        grade_score, prediction_type, generated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    race_id,
                    pred.get('pit_number'),
                    pred.get('rank_prediction'),
                    pred.get('total_score', 0),
                    pred.get('confidence', 'E'),
                    pred.get('racer_name', ''),
                    pred.get('racer_number', ''),
                    str(pred.get('applied_rules', '')),
                    pred.get('course_score', 0),
                    pred.get('racer_score', 0),
                    pred.get('motor_score', 0),
                    pred.get('kimarite_score', 0),
                    pred.get('grade_score', 0),
                    'after',
                    generated_at
                ))
                saved += 1

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"DB保存エラー: {e}")
    finally:
        conn.close()

    return saved


def main():
    print("=" * 80)
    print("2025年全レース予想再生成（並列版・ハイブリッドスコアリング適用）")
    print("=" * 80)
    print()
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    db_path = PROJECT_ROOT / "data" / "boatrace.db"

    # 2025年の全日付を生成
    start = datetime.strptime('2025-01-01', '%Y-%m-%d')
    end = datetime.strptime('2025-12-31', '%Y-%m-%d')

    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)

    # ワーカー数（CPUコア数）
    workers = min(cpu_count(), 8)  # 最大8並列

    print(f"対象期間: 2025-01-01 ～ 2025-12-31")
    print(f"対象日数: {len(dates)}日間")
    print(f"並列ワーカー: {workers}")
    print()

    start_time = time.time()

    # 統計
    total_stats = {
        'total_races': 0,
        'succeeded': 0,
        'failed': 0
    }

    # タスクを準備
    tasks = [(date, str(db_path)) for date in dates]

    completed = 0

    # 並列処理
    with ProcessPoolExecutor(max_workers=workers) as executor:
        # フューチャーを送信
        futures = {executor.submit(process_single_day, task): task[0] for task in tasks}

        for future in as_completed(futures):
            date = futures[future]
            completed += 1

            try:
                result = future.result()

                # 統計更新
                total_stats['total_races'] += result['total_races']
                total_stats['succeeded'] += result['succeeded']
                total_stats['failed'] += result['failed']

                # 予測結果をDBに保存（メインプロセスで安全に）
                if result['predictions']:
                    save_predictions_batch(result['predictions'], str(db_path))

                # 進捗表示
                elapsed = time.time() - start_time
                races_per_min = total_stats['total_races'] / (elapsed / 60) if elapsed > 0 else 0
                remaining_days = len(dates) - completed
                eta_min = remaining_days / (completed / (elapsed / 60)) if completed > 0 else 0

                print(f"[{completed:3}/{len(dates)}] {result['date']}: {result['total_races']:3}R "
                      f"(成功:{result['succeeded']:3} 失敗:{result['failed']:2}) "
                      f"[{elapsed/60:.1f}分経過, {races_per_min:.1f}R/分, 残り{eta_min:.1f}分]", flush=True)

            except Exception as e:
                elapsed = time.time() - start_time
                print(f"[{completed:3}/{len(dates)}] {date}: エラー - {str(e)[:30]} [{elapsed/60:.1f}分経過]", flush=True)

    elapsed = time.time() - start_time

    # 結果サマリー
    print()
    print("=" * 80)
    print("再生成完了")
    print("=" * 80)
    print()
    print(f"終了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"所要時間: {elapsed/3600:.2f}時間 ({elapsed/60:.1f}分)")
    print()
    print(f"総レース数: {total_stats['total_races']:,}件")
    print(f"成功: {total_stats['succeeded']:,}件")
    print(f"失敗: {total_stats['failed']:,}件")
    print(f"成功率: {total_stats['succeeded']/total_stats['total_races']*100:.1f}%" if total_stats['total_races'] > 0 else "成功率: 0%")
    print()

    # 速度
    if elapsed > 0:
        races_per_min = total_stats['total_races'] / (elapsed / 60)
        print(f"処理速度: {races_per_min:.1f} レース/分")
        print()

    # 生成されたデータの確認
    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT COUNT(*)
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE r.race_date >= '2025-01-01'
          AND r.race_date < '2026-01-01'
          AND rp.prediction_type = 'after'
    ''')
    new_count = cursor.fetchone()[0]

    cursor.execute('''
        SELECT
            rp.confidence,
            COUNT(DISTINCT rp.race_id) as race_count
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE r.race_date >= '2025-01-01'
          AND r.race_date < '2026-01-01'
          AND rp.prediction_type = 'after'
        GROUP BY rp.confidence
        ORDER BY rp.confidence
    ''')

    print("生成データ:")
    print(f"  総件数: {new_count:,}件")
    print(f"  信頼度別レース数:")
    for confidence, count in cursor.fetchall():
        print(f"    信頼度{confidence}: {count:,}レース")

    conn.close()

    print()
    print("=" * 80)
    print("次のステップ:")
    print("  1. 比較分析: python scripts/compare_before_after_hybrid.py")
    print("  2. 性能分析: python scripts/analyze_2025_fast.py")
    print("=" * 80)


if __name__ == "__main__":
    main()
