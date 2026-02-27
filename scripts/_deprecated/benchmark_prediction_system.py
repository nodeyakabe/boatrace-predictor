#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
予測システムベンチマークスクリプト

標準テストセット（2025年before予測）で性能を測定し、
結果をJSONで保存・前回との差分を表示する。

使用例:
    # 標準ベンチマーク
    python scripts/benchmark_prediction_system.py

    # 前回比較
    python scripts/benchmark_prediction_system.py --compare

    # ベースライン保存
    python scripts/benchmark_prediction_system.py --save-baseline

    # 特定年度でベンチマーク
    python scripts/benchmark_prediction_system.py --year 2024
"""
import argparse
import json
import os
import sys
import sqlite3
from datetime import datetime
from pathlib import Path

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.feature_flags import FEATURE_FLAGS, get_enabled_features


def get_benchmark_dir() -> Path:
    """ベンチマーク結果保存ディレクトリを取得"""
    benchmark_dir = Path(PROJECT_ROOT) / 'data' / 'benchmark_results'
    benchmark_dir.mkdir(parents=True, exist_ok=True)
    return benchmark_dir


def run_benchmark(db_path: str, year: str = '2025', prediction_type: str = 'before') -> dict:
    """
    ベンチマーク実行

    Args:
        db_path: データベースパス
        year: 対象年度
        prediction_type: 予測タイプ（before/advance）

    Returns:
        dict: ベンチマーク結果
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    result = {
        'timestamp': datetime.now().isoformat(),
        'year': year,
        'prediction_type': prediction_type,
        'enabled_flags': get_enabled_features(),
        'metrics': {}
    }

    # 基本統計
    cursor.execute(f'''
        SELECT
            COUNT(DISTINCT rp.race_id) as total_races,
            MIN(r.race_date) as min_date,
            MAX(r.race_date) as max_date
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE r.race_date LIKE '{year}%'
          AND rp.prediction_type = ?
          AND rp.rank_prediction = 1
    ''', (prediction_type,))
    row = cursor.fetchone()
    result['total_races'] = row[0] or 0
    result['period'] = {'start': row[1], 'end': row[2]}

    if result['total_races'] == 0:
        conn.close()
        return result

    # 信頼度別レース数
    cursor.execute(f'''
        SELECT
            rp.confidence,
            COUNT(DISTINCT rp.race_id) as race_count
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE r.race_date LIKE '{year}%'
          AND rp.prediction_type = ?
          AND rp.rank_prediction = 1
        GROUP BY rp.confidence
        ORDER BY rp.confidence
    ''', (prediction_type,))
    result['confidence_distribution'] = {row[0]: row[1] for row in cursor.fetchall() if row[0]}

    # 1着的中率
    cursor.execute(f'''
        WITH predictions AS (
            SELECT
                rp.race_id,
                rp.confidence,
                rp.pit_number as pred_pit
            FROM race_predictions rp
            JOIN races r ON rp.race_id = r.id
            WHERE r.race_date LIKE '{year}%'
              AND rp.prediction_type = ?
              AND rp.rank_prediction = 1
        )
        SELECT
            p.confidence,
            COUNT(*) as total,
            SUM(CASE WHEN p.pred_pit = res.pit_number THEN 1 ELSE 0 END) as correct
        FROM predictions p
        LEFT JOIN results res ON p.race_id = res.race_id AND res.rank = '1'
        WHERE p.confidence IS NOT NULL
        GROUP BY p.confidence
        ORDER BY p.confidence
    ''', (prediction_type,))
    result['metrics']['first_place'] = {}
    for row in cursor.fetchall():
        result['metrics']['first_place'][row[0]] = {
            'total': row[1],
            'correct': row[2],
            'rate': round(100.0 * row[2] / row[1], 2) if row[1] > 0 else 0
        }

    # 2着的中率
    cursor.execute(f'''
        WITH predictions AS (
            SELECT
                rp.race_id,
                MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.confidence END) as confidence,
                MAX(CASE WHEN rp.rank_prediction = 2 THEN rp.pit_number END) as pred_2nd
            FROM race_predictions rp
            JOIN races r ON rp.race_id = r.id
            WHERE r.race_date LIKE '{year}%'
              AND rp.prediction_type = ?
              AND rp.rank_prediction <= 2
            GROUP BY rp.race_id
        )
        SELECT
            p.confidence,
            COUNT(*) as total,
            SUM(CASE WHEN p.pred_2nd = res.pit_number THEN 1 ELSE 0 END) as correct
        FROM predictions p
        LEFT JOIN results res ON p.race_id = res.race_id AND res.rank = '2'
        WHERE p.confidence IS NOT NULL
        GROUP BY p.confidence
        ORDER BY p.confidence
    ''', (prediction_type,))
    result['metrics']['second_place'] = {}
    for row in cursor.fetchall():
        result['metrics']['second_place'][row[0]] = {
            'total': row[1],
            'correct': row[2],
            'rate': round(100.0 * row[2] / row[1], 2) if row[1] > 0 else 0
        }

    # 3着的中率
    cursor.execute(f'''
        WITH predictions AS (
            SELECT
                rp.race_id,
                MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.confidence END) as confidence,
                MAX(CASE WHEN rp.rank_prediction = 3 THEN rp.pit_number END) as pred_3rd
            FROM race_predictions rp
            JOIN races r ON rp.race_id = r.id
            WHERE r.race_date LIKE '{year}%'
              AND rp.prediction_type = ?
              AND rp.rank_prediction <= 3
            GROUP BY rp.race_id
        )
        SELECT
            p.confidence,
            COUNT(*) as total,
            SUM(CASE WHEN p.pred_3rd = res.pit_number THEN 1 ELSE 0 END) as correct
        FROM predictions p
        LEFT JOIN results res ON p.race_id = res.race_id AND res.rank = '3'
        WHERE p.confidence IS NOT NULL
        GROUP BY p.confidence
        ORDER BY p.confidence
    ''', (prediction_type,))
    result['metrics']['third_place'] = {}
    for row in cursor.fetchall():
        result['metrics']['third_place'][row[0]] = {
            'total': row[1],
            'correct': row[2],
            'rate': round(100.0 * row[2] / row[1], 2) if row[1] > 0 else 0
        }

    # 三連単的中率
    cursor.execute(f'''
        WITH trifecta_predictions AS (
            SELECT
                rp.race_id,
                MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.confidence END) as confidence,
                MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.pit_number END) as pred_1st,
                MAX(CASE WHEN rp.rank_prediction = 2 THEN rp.pit_number END) as pred_2nd,
                MAX(CASE WHEN rp.rank_prediction = 3 THEN rp.pit_number END) as pred_3rd
            FROM race_predictions rp
            JOIN races r ON rp.race_id = r.id
            WHERE r.race_date LIKE '{year}%'
              AND rp.prediction_type = ?
              AND rp.rank_prediction <= 3
            GROUP BY rp.race_id
        ),
        actual_trifecta AS (
            SELECT
                race_id,
                MAX(CASE WHEN rank = '1' THEN pit_number END) as actual_1st,
                MAX(CASE WHEN rank = '2' THEN pit_number END) as actual_2nd,
                MAX(CASE WHEN rank = '3' THEN pit_number END) as actual_3rd
            FROM results
            WHERE rank IN ('1', '2', '3')
            GROUP BY race_id
        )
        SELECT
            tp.confidence,
            COUNT(*) as total,
            SUM(CASE
                WHEN tp.pred_1st = at.actual_1st
                AND tp.pred_2nd = at.actual_2nd
                AND tp.pred_3rd = at.actual_3rd
                THEN 1 ELSE 0 END) as correct
        FROM trifecta_predictions tp
        JOIN actual_trifecta at ON tp.race_id = at.race_id
        WHERE tp.confidence IS NOT NULL
        GROUP BY tp.confidence
        ORDER BY tp.confidence
    ''', (prediction_type,))
    result['metrics']['trifecta'] = {}
    for row in cursor.fetchall():
        result['metrics']['trifecta'][row[0]] = {
            'total': row[1],
            'correct': row[2],
            'rate': round(100.0 * row[2] / row[1], 2) if row[1] > 0 else 0
        }

    conn.close()
    return result


def save_result(result: dict, filename: str = None) -> str:
    """結果をJSONで保存"""
    benchmark_dir = get_benchmark_dir()
    if filename is None:
        filename = f"benchmark_{result['year']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = benchmark_dir / filename
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return str(filepath)


def load_latest_result(year: str = '2025') -> dict:
    """最新の結果を読み込み"""
    benchmark_dir = get_benchmark_dir()
    pattern = f"benchmark_{year}_*.json"
    files = sorted(benchmark_dir.glob(pattern), reverse=True)
    if not files:
        return None
    with open(files[0], 'r', encoding='utf-8') as f:
        return json.load(f)


def load_baseline(year: str = '2025') -> dict:
    """ベースラインを読み込み"""
    benchmark_dir = get_benchmark_dir()
    baseline_path = benchmark_dir / f"baseline_{year}.json"
    if not baseline_path.exists():
        return None
    with open(baseline_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_baseline(result: dict) -> str:
    """ベースラインとして保存"""
    benchmark_dir = get_benchmark_dir()
    filepath = benchmark_dir / f"baseline_{result['year']}.json"
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return str(filepath)


def print_result(result: dict):
    """結果を表示"""
    print("\n" + "=" * 70)
    print("ベンチマーク結果")
    print("=" * 70)
    print(f"実行時刻: {result['timestamp']}")
    print(f"対象年度: {result['year']}")
    print(f"予測タイプ: {result['prediction_type']}")
    print(f"対象レース数: {result['total_races']:,}")
    print(f"期間: {result['period']['start']} 〜 {result['period']['end']}")
    print(f"有効フラグ数: {len(result['enabled_flags'])}")

    print("\n--- 信頼度分布 ---")
    for conf, count in sorted(result.get('confidence_distribution', {}).items()):
        print(f"  {conf}: {count:,}")

    for metric_name, display_name in [
        ('first_place', '1着的中率'),
        ('second_place', '2着的中率'),
        ('third_place', '3着的中率'),
        ('trifecta', '三連単的中率')
    ]:
        print(f"\n--- {display_name} ---")
        metrics = result['metrics'].get(metric_name, {})
        for conf in ['A', 'B', 'C', 'D', 'E']:
            if conf in metrics:
                data = metrics[conf]
                print(f"  {conf}: {data['correct']:,}/{data['total']:,} = {data['rate']:.2f}%")


def print_comparison(current: dict, baseline: dict):
    """比較結果を表示"""
    print("\n" + "=" * 70)
    print("前回比較")
    print("=" * 70)
    print(f"ベースライン: {baseline['timestamp']}")
    print(f"現在: {current['timestamp']}")

    # フラグ差分
    baseline_flags = set(baseline.get('enabled_flags', []))
    current_flags = set(current.get('enabled_flags', []))
    added = current_flags - baseline_flags
    removed = baseline_flags - current_flags

    if added:
        print(f"\n[新規有効化] {', '.join(added)}")
    if removed:
        print(f"\n[無効化] {', '.join(removed)}")

    # 指標比較
    for metric_name, display_name in [
        ('first_place', '1着的中率'),
        ('second_place', '2着的中率'),
        ('third_place', '3着的中率'),
        ('trifecta', '三連単的中率')
    ]:
        print(f"\n--- {display_name} ---")
        current_metrics = current['metrics'].get(metric_name, {})
        baseline_metrics = baseline['metrics'].get(metric_name, {})

        for conf in ['A', 'B', 'C', 'D', 'E']:
            if conf in current_metrics and conf in baseline_metrics:
                curr_rate = current_metrics[conf]['rate']
                base_rate = baseline_metrics[conf]['rate']
                diff = curr_rate - base_rate
                sign = '+' if diff >= 0 else ''
                print(f"  {conf}: {curr_rate:.2f}% (ベースライン: {base_rate:.2f}%, 差分: {sign}{diff:.2f}pt)")
            elif conf in current_metrics:
                print(f"  {conf}: {current_metrics[conf]['rate']:.2f}% (ベースラインなし)")


def main():
    parser = argparse.ArgumentParser(description='予測システムベンチマーク')
    parser.add_argument('--year', default='2025', help='対象年度（デフォルト: 2025）')
    parser.add_argument('--type', default='before', choices=['before', 'advance'],
                        help='予測タイプ（デフォルト: before）')
    parser.add_argument('--compare', action='store_true', help='前回（ベースライン）と比較')
    parser.add_argument('--save-baseline', action='store_true', help='ベースラインとして保存')
    parser.add_argument('--output', help='出力ファイル名')

    args = parser.parse_args()

    print("=" * 70)
    print("予測システムベンチマーク")
    print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # データベースパス
    db_path = os.path.join(PROJECT_ROOT, 'data', 'boatrace.db')
    if not os.path.exists(db_path):
        print(f"[ERROR] データベースが見つかりません: {db_path}")
        sys.exit(1)

    # ベンチマーク実行
    print(f"\n[1/3] {args.year}年 {args.type}予測でベンチマーク実行中...")
    result = run_benchmark(db_path, args.year, args.type)

    if result['total_races'] == 0:
        print(f"[ERROR] {args.year}年の{args.type}予測データがありません")
        sys.exit(1)

    # 結果表示
    print_result(result)

    # 結果保存
    print(f"\n[2/3] 結果を保存中...")
    saved_path = save_result(result, args.output)
    print(f"  保存先: {saved_path}")

    # ベースライン保存
    if args.save_baseline:
        baseline_path = save_baseline(result)
        print(f"  ベースライン保存: {baseline_path}")

    # 比較
    if args.compare:
        print(f"\n[3/3] ベースラインと比較中...")
        baseline = load_baseline(args.year)
        if baseline:
            print_comparison(result, baseline)
        else:
            print(f"  [WARN] ベースラインが見つかりません。--save-baseline で保存してください。")

    print("\n" + "=" * 70)
    print("ベンチマーク完了")
    print("=" * 70)


if __name__ == '__main__':
    main()
