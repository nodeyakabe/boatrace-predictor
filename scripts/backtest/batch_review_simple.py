#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
不採用案の一括検証スクリプト（修正版）"""
import sys
import io

# Windows環境での文字化け対策
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

"""

概要:
- config/review_conditions.jsonから9件の不採用案を読み込み
- 各条件を順次（逐次）検証
- 結果をCSV/Markdown形式で出力

使用方法:
    # 全9条件を検証
    python scripts/backtest/batch_review_simple.py

    # 特定の条件のみ検証
    python scripts/backtest/batch_review_simple.py --condition RJ-1

    # 優先度指定
    python scripts/backtest/batch_review_simple.py --priority 超高,高

特徴:
- 並列化なし（安全性重視）
- standard_backtest.pyを使用
- Claude Code可読な出力形式（CSV + Markdown）
"""

import argparse
import json
import subprocess
import sys
import re
from pathlib import Path
from datetime import datetime
import csv

def load_conditions(config_path):
    """review_conditions.jsonを読み込み"""
    with open(config_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data['review_conditions'], data['metadata']

def run_standard_backtest(rj_condition_id=None):
    """standard_backtest.py --fullを実行して結果を取得

    Args:
        rj_condition_id: RJ条件ID（例: 'RJ-3', 'RJ-4-A1'）
    """
    cmd = [sys.executable, 'scripts/backtest/standard_backtest.py', '--full']
    if rj_condition_id:
        cmd.extend(['--rj-condition', rj_condition_id])

    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    return result.stdout, result.stderr, result.returncode

def parse_backtest_output(output):
    """標準バックテストの出力を解析

    Args:
        output: standard_backtest.py --full の stdout

    Returns:
        dict: 検証結果（total_bets, total_hits, total_roi, total_profit, profitable_years）
    """
    results = {
        'total_bets': 0,
        'total_hits': 0,
        'total_roi': 0.0,
        'total_profit': 0,
        'profitable_years': '0/6'
    }

    # 購入レース数を抽出
    match = re.search(r'購入レース数:\s*([\d,]+)件', output)
    if match:
        results['total_bets'] = int(match.group(1).replace(',', ''))

    # 的中数を抽出
    match = re.search(r'的中数:\s*([\d,]+)件', output)
    if match:
        results['total_hits'] = int(match.group(1).replace(',', ''))

    # ROIを抽出
    match = re.search(r'ROI:\s*([\d.]+)%', output)
    if match:
        results['total_roi'] = float(match.group(1))

    # 収支を抽出
    match = re.search(r'収支:\s*([+\-][\d,]+)円', output)
    if match:
        profit_str = match.group(1).replace(',', '')
        results['total_profit'] = int(profit_str)

    # 黒字年数を抽出
    match = re.search(r'黒字年数:\s*(\d+)/(\d+)年', output)
    if match:
        results['profitable_years'] = f"{match.group(1)}/{match.group(2)}"

    return results

def get_rj_condition_id(condition_id):
    """条件IDに対応するRJ条件IDを返す

    Args:
        condition_id: 条件ID（例: 'RJ-1', 'RJ-3', 'RJ-4'）

    Returns:
        str or None: RJ条件ID（例: 'RJ-3', 'RJ-4-A1'）、または None（検証不可）
    """
    # RJ-3, RJ-5: 単一条件
    if condition_id in ['RJ-3', 'RJ-5']:
        return condition_id

    # RJ-4: 2つの条件（A1とA2）→とりあえずA1のみ
    if condition_id == 'RJ-4':
        return 'RJ-4-A1'  # 後でRJ-4-A2も実行する必要がある

    # その他の条件は現時点で検証不可
    return None


def review_condition(condition, metadata):
    """1つの条件を検証"""
    print(f"\n{'='*80}")
    print(f"検証開始: {condition['id']} - {condition['name']}")
    print(f"優先度: {condition['priority']}")
    print(f"{'='*80}")

    # 条件情報の表示
    print(f"\n【不採用理由】{condition['不採用理由']}")
    print(f"【再検証理由】{condition['再検証理由']}")
    print(f"【期待効果】{condition['期待効果']}")

    # RJ条件IDを取得
    rj_condition_id = get_rj_condition_id(condition['id'])

    if rj_condition_id is None:
        print(f"\n⚠️ 警告: {condition['id']} は現時点で自動検証不可")
        print(f"理由: 新しいスコアリング方法や分析スクリプトが必要")
        return {
            'id': condition['id'],
            'name': condition['name'],
            'priority': condition['priority'],
            'category': condition['category'],
            'total_bets': 0,
            'total_hits': 0,
            'total_roi': 0.0,
            'total_profit': 0,
            'profitable_years': '0/6',
            'status': '検証不可（手動検証必要）',
            '不採用理由': condition['不採用理由'],
            '再検証理由': condition['再検証理由'],
            '期待効果': condition['期待効果']
        }

    # 標準バックテストを実行
    print(f"\n標準バックテスト実行中（--rj-condition {rj_condition_id}）...")

    stdout, stderr, returncode = run_standard_backtest(rj_condition_id)

    if returncode != 0:
        print(f"エラー: バックテスト実行に失敗しました")
        print(f"stderr: {stderr}")
        return {
            'id': condition['id'],
            'name': condition['name'],
            'priority': condition['priority'],
            'category': condition['category'],
            'total_bets': 0,
            'total_hits': 0,
            'total_roi': 0.0,
            'total_profit': 0,
            'profitable_years': '0/6',
            'status': 'エラー',
            '不採用理由': condition['不採用理由'],
            '再検証理由': condition['再検証理由'],
            '期待効果': condition['期待効果'],
            'error': stderr
        }

    # 結果を解析
    results = parse_backtest_output(stdout)

    # 採用判定（auto_register.pyと同じロジックを使用）
    status = '要手動確認'  # デフォルト

    print(f"\n【結果サマリー】")
    print(f"購入数: {results['total_bets']}件")
    print(f"的中数: {results['total_hits']}件")
    print(f"ROI: {results['total_roi']:.1f}%")
    print(f"収支: {results['total_profit']:+,}円")
    print(f"黒字年数: {results['profitable_years']}")
    print(f"判定: {status}")

    return {
        'id': condition['id'],
        'name': condition['name'],
        'priority': condition['priority'],
        'category': condition['category'],
        'total_bets': results['total_bets'],
        'total_hits': results['total_hits'],
        'total_roi': results['total_roi'],
        'total_profit': results['total_profit'],
        'profitable_years': results['profitable_years'],
        'status': status,
        '不採用理由': condition['不採用理由'],
        '再検証理由': condition['再検証理由'],
        '期待効果': condition['期待効果']
    }

def save_results_csv(results, output_path):
    """結果をCSVで保存"""
    fieldnames = [
        'id', 'name', 'priority', 'category',
        'total_bets', 'total_hits', 'total_roi', 'total_profit',
        'profitable_years', 'status',
        '不採用理由', '再検証理由', '期待効果'
    ]

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nCSV保存: {output_path}")

def save_results_markdown(results, output_path, metadata):
    """結果をMarkdownで保存"""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(f"# 不採用案一括検証結果\n\n")
        f.write(f"**検証日時**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**検証件数**: {len(results)}件\n\n")

        f.write(f"## データ補完効果\n\n")
        f.write(f"- {metadata['データ補完効果']}\n\n")

        f.write(f"## 検証基準\n\n")
        for key, value in metadata['検証基準'].items():
            f.write(f"- **{key}**: {value}\n")
        f.write(f"\n")

        f.write(f"## 結果サマリー\n\n")
        f.write(f"| ID | 条件名 | 優先度 | 購入数 | ROI | 収支 | 黒字年数 | 判定 |\n")
        f.write(f"|:--:|--------|:------:|:------:|:---:|:----:|:--------:|:----:|\n")

        for r in results:
            f.write(f"| {r['id']} | {r['name']} | {r['priority']} | ")
            f.write(f"{r['total_bets']} | {r['total_roi']:.1f}% | ")
            f.write(f"{r['total_profit']:+,}円 | {r['profitable_years']} | ")
            f.write(f"{r['status']} |\n")

        f.write(f"\n## 詳細\n\n")

        for r in results:
            f.write(f"### {r['id']}: {r['name']}\n\n")
            f.write(f"| 項目 | 内容 |\n")
            f.write(f"|------|------|\n")
            f.write(f"| **優先度** | {r['priority']} |\n")
            f.write(f"| **カテゴリ** | {r['category']} |\n")
            f.write(f"| **購入数** | {r['total_bets']}件 |\n")
            f.write(f"| **ROI** | {r['total_roi']:.1f}% |\n")
            f.write(f"| **収支** | {r['total_profit']:+,}円 |\n")
            f.write(f"| **黒字年数** | {r['profitable_years']} |\n")
            f.write(f"| **判定** | {r['status']} |\n")
            f.write(f"| **不採用理由** | {r['不採用理由']} |\n")
            f.write(f"| **再検証理由** | {r['再検証理由']} |\n")
            f.write(f"| **期待効果** | {r['期待効果']} |\n")
            f.write(f"\n")

    print(f"Markdown保存: {output_path}")

def main():
    parser = argparse.ArgumentParser(
        description='不採用案の一括検証（修正版：並列化なし）'
    )
    parser.add_argument(
        '--condition',
        help='特定の条件のみ検証（例: RJ-1）'
    )
    parser.add_argument(
        '--priority',
        help='優先度指定（例: 超高,高）'
    )
    parser.add_argument(
        '--output-dir',
        default='data/batch_review_results',
        help='出力ディレクトリ（デフォルト: data/batch_review_results）'
    )

    args = parser.parse_args()

    # 設定ファイルを読み込み
    config_path = Path('config/review_conditions.json')
    if not config_path.exists():
        print(f"エラー: {config_path} が見つかりません")
        sys.exit(1)

    conditions, metadata = load_conditions(config_path)

    # フィルタリング
    if args.condition:
        conditions = [c for c in conditions if c['id'] == args.condition]
        if not conditions:
            print(f"エラー: 条件 {args.condition} が見つかりません")
            sys.exit(1)

    if args.priority:
        priorities = [p.strip() for p in args.priority.split(',')]
        conditions = [c for c in conditions if c['priority'] in priorities]

    print(f"\n{'='*80}")
    print(f"不採用案一括検証（修正版）")
    print(f"{'='*80}")
    print(f"検証対象: {len(conditions)}件")
    print(f"実行方式: 逐次実行（並列化なし）")
    print(f"{'='*80}\n")

    # 出力ディレクトリ作成
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 各条件を順次検証
    results = []
    for i, condition in enumerate(conditions, 1):
        print(f"\n進捗: {i}/{len(conditions)}")
        result = review_condition(condition, metadata)
        results.append(result)

    # 結果を保存
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_path = output_dir / f'batch_review_{timestamp}.csv'
    md_path = output_dir / f'batch_review_{timestamp}.md'

    save_results_csv(results, csv_path)
    save_results_markdown(results, md_path, metadata)

    print(f"\n{'='*80}")
    print(f"検証完了")
    print(f"{'='*80}")
    print(f"CSV: {csv_path}")
    print(f"Markdown: {md_path}")
    print(f"{'='*80}\n")

if __name__ == '__main__':
    main()
