#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
不採用案の自動記録スクリプト"""
import sys
import io

# Windows環境での文字化け対策
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

"""

概要:
- batch_review_simple.pyの出力CSVを読み込み
- 採用/不採用を判定
- REJECTED_IDEAS.mdへの追記内容を生成

使用方法:
    # 最新の検証結果を処理
    python scripts/backtest/auto_register.py

    # 特定のCSVファイルを指定
    python scripts/backtest/auto_register.py --input data/batch_review_results/batch_review_20260205_120000.csv

    # REJECTED_IDEAS.mdに自動追記（--auto-appendオプション）
    python scripts/backtest/auto_register.py --auto-append

特徴:
- 採用基準に基づく自動判定
- Markdown形式で出力（REJECTED_IDEAS.mdに追記可能な形式）
- 安全性重視（デフォルトでは追記せず、内容を出力のみ）
"""

import argparse
import csv
import sys
from pathlib import Path
from datetime import datetime

# 採用基準
CRITERIA = {
    'min_profitable_years': 4,  # 最低4/6年黒字
    'min_roi': 100.0,           # 最低ROI 100%
    'min_samples': 100,         # 最低サンプル数100件
    'min_profit': 0             # 累計収支プラス
}

def load_review_results(csv_path):
    """検証結果CSVを読み込み"""
    results = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 数値型に変換
            row['total_bets'] = int(row['total_bets']) if row['total_bets'] else 0
            row['total_hits'] = int(row['total_hits']) if row['total_hits'] else 0
            row['total_roi'] = float(row['total_roi']) if row['total_roi'] else 0.0
            row['total_profit'] = int(row['total_profit']) if row['total_profit'] else 0
            results.append(row)
    return results

def parse_profitable_years(years_str):
    """黒字年数文字列（例: "4/6"）を解析"""
    try:
        profitable, total = years_str.split('/')
        return int(profitable), int(total)
    except:
        return 0, 6

def judge_condition(result):
    """採用/不採用を判定"""
    profitable, total_years = parse_profitable_years(result['profitable_years'])

    # 採用基準チェック
    checks = {
        '黒字年数': profitable >= CRITERIA['min_profitable_years'],
        'ROI': result['total_roi'] >= CRITERIA['min_roi'],
        'サンプル数': result['total_bets'] >= CRITERIA['min_samples'],
        '累計収支': result['total_profit'] > CRITERIA['min_profit']
    }

    # 全て満たせば採用
    if all(checks.values()):
        status = '✅ 採用推奨'
        reason = '採用基準を全て満たしています'
    else:
        status = '❌ 不採用'
        failed_criteria = [k for k, v in checks.items() if not v]
        reason = f"採用基準未達: {', '.join(failed_criteria)}"

    return status, reason, checks

def generate_rejected_idea_entry(result, status, reason, checks):
    """REJECTED_IDEAS.md用のエントリを生成"""
    entry = []

    entry.append(f"### {result['id']}-再検証. {result['name']}（データ補完後再検証）")
    entry.append(f"")
    entry.append(f"| 項目 | 内容 |")
    entry.append(f"|------|------|")
    entry.append(f"| **施策ID** | `{result.get('id', 'N/A')}` |")
    entry.append(f"| **カテゴリ** | {result['category']} |")
    entry.append(f"| **検証日** | {datetime.now().strftime('%Y-%m-%d')} |")
    entry.append(f"| **判定** | {status} |")
    entry.append(f"")
    entry.append(f"#### 概要")
    entry.append(f"")
    entry.append(f"データ補完後（2021年・2023年データ100%化）の再検証。")
    entry.append(f"")
    entry.append(f"**元の不採用理由**: {result['不採用理由']}")
    entry.append(f"")
    entry.append(f"**再検証理由**: {result['再検証理由']}")
    entry.append(f"")
    entry.append(f"#### 再検証結果（6年間、データ補完後）")
    entry.append(f"")
    entry.append(f"| 指標 | 値 |")
    entry.append(f"|------|---:|")
    entry.append(f"| **購入数** | {result['total_bets']}件 |")
    entry.append(f"| **的中数** | {result['total_hits']}件 |")
    entry.append(f"| **ROI** | {result['total_roi']:.1f}% |")
    entry.append(f"| **収支** | {result['total_profit']:+,}円 |")
    entry.append(f"| **黒字年数** | {result['profitable_years']} |")
    entry.append(f"")
    entry.append(f"#### 採用基準チェック")
    entry.append(f"")
    entry.append(f"| 基準 | 判定 | 値 |")
    entry.append(f"|------|:----:|---:|")

    check_mark = {True: '✅', False: '❌'}
    entry.append(f"| 黒字年数 ≧ 4/6年 | {check_mark[checks['黒字年数']]} | {result['profitable_years']} |")
    entry.append(f"| ROI ≧ 100% | {check_mark[checks['ROI']]} | {result['total_roi']:.1f}% |")
    entry.append(f"| サンプル数 ≧ 100件 | {check_mark[checks['サンプル数']]} | {result['total_bets']}件 |")
    entry.append(f"| 累計収支 > 0円 | {check_mark[checks['累計収支']]} | {result['total_profit']:+,}円 |")
    entry.append(f"")

    if status == '✅ 採用推奨':
        entry.append(f"#### 採用推奨理由")
        entry.append(f"")
        entry.append(f"採用基準を全て満たしています。")
        entry.append(f"")
        entry.append(f"**次のアクション**:")
        entry.append(f"1. 詳細な月別・会場別分析")
        entry.append(f"2. 既存条件との重複チェック")
        entry.append(f"3. BetTargetEvaluatorへの実装")
        entry.append(f"4. 本番採用前のペーパートレード")
        entry.append(f"")
    else:
        entry.append(f"#### 不採用理由（データ補完後も維持）")
        entry.append(f"")
        entry.append(f"{reason}")
        entry.append(f"")

    entry.append(f"#### 教訓")
    entry.append(f"")
    entry.append(f"- データ補完によるサンプル数増加: {result['期待効果']}")

    if status == '❌ 不採用':
        entry.append(f"- データ量が増えても採用基準を満たさないため、根本的な問題がある")

    entry.append(f"")
    entry.append(f"---")
    entry.append(f"")

    return "\n".join(entry)

def main():
    parser = argparse.ArgumentParser(
        description='不採用案の自動記録（REJECTED_IDEAS.md用）'
    )
    parser.add_argument(
        '--input',
        help='検証結果CSVファイル（指定しない場合は最新ファイル）'
    )
    parser.add_argument(
        '--auto-append',
        action='store_true',
        help='REJECTED_IDEAS.mdに自動追記（デフォルト: 出力のみ）'
    )
    parser.add_argument(
        '--output',
        help='出力ファイル（指定しない場合は標準出力）'
    )

    args = parser.parse_args()

    # 入力ファイル決定
    if args.input:
        csv_path = Path(args.input)
    else:
        # 最新のCSVファイルを取得
        results_dir = Path('data/batch_review_results')
        csv_files = sorted(results_dir.glob('batch_review_*.csv'), reverse=True)
        if not csv_files:
            print("エラー: 検証結果CSVが見つかりません")
            sys.exit(1)
        csv_path = csv_files[0]

    if not csv_path.exists():
        print(f"エラー: {csv_path} が見つかりません")
        sys.exit(1)

    print(f"入力ファイル: {csv_path}")

    # 検証結果を読み込み
    results = load_review_results(csv_path)

    print(f"検証対象: {len(results)}件\n")

    # 全エントリを生成
    entries = []
    summary = {
        '採用推奨': [],
        '不採用': []
    }

    for result in results:
        status, reason, checks = judge_condition(result)

        print(f"\n{'='*80}")
        print(f"{result['id']}: {result['name']}")
        print(f"判定: {status}")
        print(f"理由: {reason}")
        print(f"{'='*80}")

        entry = generate_rejected_idea_entry(result, status, reason, checks)
        entries.append(entry)

        if status == '✅ 採用推奨':
            summary['採用推奨'].append(result)
        else:
            summary['不採用'].append(result)

    # サマリー表示
    print(f"\n{'='*80}")
    print(f"検証結果サマリー")
    print(f"{'='*80}")
    print(f"採用推奨: {len(summary['採用推奨'])}件")
    print(f"不採用: {len(summary['不採用'])}件")
    print(f"{'='*80}\n")

    # 出力
    full_content = "\n".join(entries)

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(full_content, encoding='utf-8')
        print(f"出力ファイル: {output_path}")
    else:
        print(full_content)

    # 自動追記（オプション）
    if args.auto_append:
        rejected_ideas_path = Path('docs/improvement_attempts/REJECTED_IDEAS.md')
        if not rejected_ideas_path.exists():
            print(f"エラー: {rejected_ideas_path} が見つかりません")
            sys.exit(1)

        # ファイル末尾に追記
        with open(rejected_ideas_path, 'a', encoding='utf-8') as f:
            f.write(f"\n\n## データ補完後の再検証結果（{datetime.now().strftime('%Y-%m-%d')}）\n\n")
            f.write(full_content)

        print(f"\nREJECTED_IDEAS.mdに追記しました: {rejected_ideas_path}")
    else:
        print(f"\n注意: REJECTED_IDEAS.mdへの追記は行われていません")
        print(f"追記するには --auto-append オプションを使用してください")

if __name__ == '__main__':
    main()
