#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
変更追跡スクリプト

変更前後の性能差分を計算し、
docs/guides/PREDICTION_SYSTEM_STATUS.md の履歴セクションに追記する。

使用例:
    # ベースライン保存
    python scripts/benchmark_prediction_system.py --save-baseline

    # （フラグ変更）

    # 再測定＋比較
    python scripts/benchmark_prediction_system.py --compare

    # 履歴記録
    python scripts/maintenance/track_performance_change.py \
        --description "kimarite_flow_prediction を有効化"
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)


def get_benchmark_dir() -> Path:
    """ベンチマーク結果保存ディレクトリを取得"""
    return Path(PROJECT_ROOT) / 'data' / 'benchmark_results'


def load_baseline(year: str = '2025') -> dict:
    """ベースラインを読み込み"""
    benchmark_dir = get_benchmark_dir()
    baseline_path = benchmark_dir / f"baseline_{year}.json"
    if not baseline_path.exists():
        return None
    with open(baseline_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_latest_result(year: str = '2025') -> dict:
    """最新の結果を読み込み"""
    benchmark_dir = get_benchmark_dir()
    pattern = f"benchmark_{year}_*.json"
    files = sorted(benchmark_dir.glob(pattern), reverse=True)
    if not files:
        return None
    with open(files[0], 'r', encoding='utf-8') as f:
        return json.load(f)


def calculate_diff(current: dict, baseline: dict) -> dict:
    """差分を計算"""
    diff = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'baseline_date': baseline.get('timestamp', ''),
        'current_date': current.get('timestamp', ''),
        'flags_added': [],
        'flags_removed': [],
        'metrics_diff': {}
    }

    # フラグ差分
    baseline_flags = set(baseline.get('enabled_flags', []))
    current_flags = set(current.get('enabled_flags', []))
    diff['flags_added'] = list(current_flags - baseline_flags)
    diff['flags_removed'] = list(baseline_flags - current_flags)

    # 指標差分
    for metric_name in ['first_place', 'second_place', 'third_place', 'trifecta']:
        current_metrics = current['metrics'].get(metric_name, {})
        baseline_metrics = baseline['metrics'].get(metric_name, {})
        diff['metrics_diff'][metric_name] = {}

        for conf in ['A', 'B', 'C', 'D', 'E']:
            if conf in current_metrics and conf in baseline_metrics:
                curr_rate = current_metrics[conf]['rate']
                base_rate = baseline_metrics[conf]['rate']
                diff['metrics_diff'][metric_name][conf] = {
                    'current': curr_rate,
                    'baseline': base_rate,
                    'diff': round(curr_rate - base_rate, 2)
                }

    return diff


def format_effect(diff: dict) -> str:
    """効果を文字列にフォーマット"""
    effects = []

    # 主要指標の差分を集計
    for metric_name, display_name in [
        ('first_place', '1着'),
        ('trifecta', '三連単')
    ]:
        metric_diff = diff['metrics_diff'].get(metric_name, {})
        if 'B' in metric_diff:
            d = metric_diff['B']['diff']
            sign = '+' if d >= 0 else ''
            effects.append(f"{display_name}(B): {sign}{d:.1f}pt")

    if effects:
        return ', '.join(effects)
    return '測定中'


def update_status_document(diff: dict, description: str):
    """PREDICTION_SYSTEM_STATUS.md の履歴セクションを更新"""
    status_path = Path(PROJECT_ROOT) / 'docs' / 'guides' / 'PREDICTION_SYSTEM_STATUS.md'

    if not status_path.exists():
        print(f"[ERROR] ステータスファイルが見つかりません: {status_path}")
        return False

    with open(status_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 履歴セクションを探す
    history_pattern = r'(## 4\. 性能推移履歴\n\n\| 変更日 \| 内容 \| 効果 \| フラグ \|\n\|.*?\|.*?\|.*?\|.*?\|\n)'
    match = re.search(history_pattern, content)

    if not match:
        print("[WARN] 履歴セクションが見つかりません。手動で追加してください。")
        return False

    # 新しいエントリを作成
    effect = format_effect(diff)
    flags = ', '.join(diff['flags_added']) if diff['flags_added'] else '-'

    new_entry = f"| {diff['date']} | {description} | {effect} | `{flags}` |\n"

    # 履歴テーブルの末尾に追加
    header_end = match.end()
    new_content = content[:header_end] + new_entry + content[header_end:]

    with open(status_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f"[完了] 履歴を追記しました: {status_path}")
    return True


def save_change_log(diff: dict, description: str):
    """変更ログをJSONで保存"""
    log_dir = get_benchmark_dir() / 'change_logs'
    log_dir.mkdir(parents=True, exist_ok=True)

    log_entry = {
        'date': diff['date'],
        'description': description,
        'diff': diff
    }

    filename = f"change_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = log_dir / filename

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(log_entry, f, ensure_ascii=False, indent=2)

    print(f"[完了] 変更ログを保存しました: {filepath}")
    return str(filepath)


def print_diff(diff: dict, description: str):
    """差分を表示"""
    print("\n" + "=" * 70)
    print("変更追跡レポート")
    print("=" * 70)
    print(f"変更内容: {description}")
    print(f"日付: {diff['date']}")
    print(f"ベースライン: {diff['baseline_date']}")
    print(f"現在: {diff['current_date']}")

    if diff['flags_added']:
        print(f"\n[新規有効化] {', '.join(diff['flags_added'])}")
    if diff['flags_removed']:
        print(f"\n[無効化] {', '.join(diff['flags_removed'])}")

    print("\n--- 指標差分 ---")
    for metric_name, display_name in [
        ('first_place', '1着的中率'),
        ('second_place', '2着的中率'),
        ('third_place', '3着的中率'),
        ('trifecta', '三連単的中率')
    ]:
        print(f"\n{display_name}:")
        metric_diff = diff['metrics_diff'].get(metric_name, {})
        for conf in ['A', 'B', 'C', 'D', 'E']:
            if conf in metric_diff:
                data = metric_diff[conf]
                sign = '+' if data['diff'] >= 0 else ''
                print(f"  {conf}: {data['current']:.2f}% (差分: {sign}{data['diff']:.2f}pt)")


def main():
    parser = argparse.ArgumentParser(description='変更追跡スクリプト')
    parser.add_argument('--description', '-d', required=True, help='変更内容の説明')
    parser.add_argument('--year', default='2025', help='対象年度（デフォルト: 2025）')
    parser.add_argument('--no-update', action='store_true', help='ステータスファイルを更新しない')

    args = parser.parse_args()

    print("=" * 70)
    print("変更追跡スクリプト")
    print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # ベースライン読み込み
    print(f"\n[1/4] ベースラインを読み込み中...")
    baseline = load_baseline(args.year)
    if not baseline:
        print(f"[ERROR] ベースラインが見つかりません。")
        print("  先に以下を実行してください:")
        print("  python scripts/benchmark_prediction_system.py --save-baseline")
        sys.exit(1)
    print(f"  ベースライン日時: {baseline.get('timestamp', 'N/A')}")

    # 最新結果読み込み
    print(f"\n[2/4] 最新のベンチマーク結果を読み込み中...")
    current = load_latest_result(args.year)
    if not current:
        print(f"[ERROR] 最新のベンチマーク結果が見つかりません。")
        print("  先に以下を実行してください:")
        print("  python scripts/benchmark_prediction_system.py")
        sys.exit(1)
    print(f"  現在の日時: {current.get('timestamp', 'N/A')}")

    # 差分計算
    print(f"\n[3/4] 差分を計算中...")
    diff = calculate_diff(current, baseline)

    # 表示
    print_diff(diff, args.description)

    # 保存
    print(f"\n[4/4] 結果を保存中...")
    save_change_log(diff, args.description)

    if not args.no_update:
        update_status_document(diff, args.description)

    print("\n" + "=" * 70)
    print("変更追跡完了")
    print("=" * 70)


if __name__ == '__main__':
    main()
