#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tier 1: 新規条件の簡易テスト（2年間、高速）

目的:
    新規購入条件を追加する前に、簡易的なテストを行う
    2年間（2024-2025）でバックテストを実行し、合格基準を満たすかチェック

合格基準:
    - ROI 150%以上
    - 1/2年黒字（2024年または2025年が黒字）
    - サンプル数 50件以上

使用方法:
    # 既存条件のテスト
    python scripts/backtest/quick_condition_test.py --condition-id "B_50_100"

    # カスタム条件のテスト（JSON形式）
    python scripts/backtest/quick_condition_test.py --condition-json '{"id": "TEST", "name": "テスト条件", ...}'

作成日: 2026-02-13
"""
import sqlite3
import sys
import io
import os
import json
import argparse
from datetime import datetime
from typing import Dict, Optional

# プロジェクトルート設定を先に実施
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from config.bet_conditions import STANDARD_BET_CONDITIONS, get_condition_by_id
from scripts.backtest.standard_backtest import (
    build_condition_query,
    analyze_condition,
    analyze_condition_yearly,
    VENUE_NAMES
)

# ============================================================
# Tier 1: 簡易テスト設定
# ============================================================
TIER1_YEARS = [2024, 2025]
TIER1_CRITERIA = {
    'roi_min': 150.0,
    'black_years_min': 1,  # 2年中1年以上黒字
    'sample_min': 50,
}


def run_tier1_test(cond: Dict) -> Dict:
    """Tier 1簡易テストを実行

    Args:
        cond: 条件定義

    Returns:
        テスト結果（合格判定含む）
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    results = {
        'condition_id': cond.get('id', 'CUSTOM'),
        'condition_name': cond['name'],
        'description': cond.get('description', ''),
        'test_type': 'Tier 1 (Quick Test)',
        'test_period': f"{TIER1_YEARS[0]}-{TIER1_YEARS[-1]}",
        'date': datetime.now().isoformat(),
        'criteria': TIER1_CRITERIA,
        'yearly': [],
        'total': {},
        'pass': False,
        'pass_details': {},
    }

    # 年度別テスト
    yearly_results = analyze_condition_yearly(cursor, cond, TIER1_YEARS)
    results['yearly'] = yearly_results

    # 合計集計
    total_bets = sum(y['bets'] for y in yearly_results)
    total_hits = sum(y['hits'] for y in yearly_results)
    total_investment = sum(y['investment'] for y in yearly_results)
    total_payout = sum(y['payout'] for y in yearly_results)

    if total_bets > 0:
        results['total'] = {
            'bets': total_bets,
            'hits': total_hits,
            'hit_rate': 100.0 * total_hits / total_bets,
            'investment': total_investment,
            'payout': total_payout,
            'roi': 100.0 * total_payout / total_investment if total_investment > 0 else 0,
            'profit': total_payout - total_investment,
        }
    else:
        results['total'] = {
            'bets': 0, 'hits': 0, 'hit_rate': 0,
            'investment': 0, 'payout': 0, 'roi': 0, 'profit': 0,
        }

    # 合格判定
    black_years = sum(1 for y in yearly_results if y['profit'] > 0)

    pass_roi = results['total']['roi'] >= TIER1_CRITERIA['roi_min']
    pass_black_years = black_years >= TIER1_CRITERIA['black_years_min']
    pass_sample = total_bets >= TIER1_CRITERIA['sample_min']

    results['pass'] = pass_roi and pass_black_years and pass_sample
    results['pass_details'] = {
        'roi': {
            'value': results['total']['roi'],
            'threshold': TIER1_CRITERIA['roi_min'],
            'pass': pass_roi,
        },
        'black_years': {
            'value': black_years,
            'threshold': TIER1_CRITERIA['black_years_min'],
            'total_years': len(TIER1_YEARS),
            'pass': pass_black_years,
        },
        'sample_size': {
            'value': total_bets,
            'threshold': TIER1_CRITERIA['sample_min'],
            'pass': pass_sample,
        },
    }

    conn.close()
    return results


def print_tier1_results(data: Dict):
    """Tier 1テスト結果を表示"""
    print("=" * 90)
    print("Tier 1: 新規条件の簡易テスト（2年間）")
    print("=" * 90)
    print(f"実行日時: {data['date'][:19]}")
    print(f"テスト期間: {data['test_period']}")
    print()

    # 条件情報
    print(f"[テスト条件]")
    print(f"  ID: {data['condition_id']}")
    print(f"  名称: {data['condition_name']}")
    print(f"  説明: {data['description']}")
    print()

    # 全体サマリー
    total = data['total']
    print("[全体サマリー]")
    print("-" * 60)
    print(f"  購入レース数: {total['bets']:,}件")
    print(f"  的中数: {total['hits']:,}件")
    print(f"  的中率: {total['hit_rate']:.2f}%")
    print(f"  総投資額: {total['investment']:,}円")
    print(f"  総払戻額: {total['payout']:,.0f}円")
    print(f"  ROI: {total['roi']:.1f}%")
    print(f"  収支: {total['profit']:+,.0f}円")
    print()

    # 年度別結果
    print("[年度別パフォーマンス]")
    print("-" * 70)
    print(f"{'年度':>6} {'件数':>8} {'的中':>5} {'的中率':>8} {'ROI':>9} {'収支':>14} {'判定'}")
    print("-" * 70)

    black_years = 0
    for y in data['yearly']:
        status = "○黒字" if y['profit'] > 0 else "×赤字"
        if y['profit'] > 0:
            black_years += 1
        print(f"{y['year']:>6} {y['bets']:>8} {y['hits']:>5} {y['hit_rate']:>7.1f}% {y['roi']:>8.1f}% {y['profit']:>+14,.0f} {status}")

    print("-" * 70)
    print(f"黒字年数: {black_years}/{len(data['yearly'])}年")
    print()

    # 合格判定
    print("[合格判定]")
    print("-" * 70)

    criteria = data['criteria']
    details = data['pass_details']

    # ROI
    roi_status = "✅ PASS" if details['roi']['pass'] else "❌ FAIL"
    print(f"  ROI:          {details['roi']['value']:>7.1f}% (基準: {criteria['roi_min']:>7.1f}%以上) {roi_status}")

    # 黒字年数
    black_years_status = "✅ PASS" if details['black_years']['pass'] else "❌ FAIL"
    print(f"  黒字年数:     {details['black_years']['value']:>2}年/{details['black_years']['total_years']}年 (基準: {criteria['black_years_min']}年以上)      {black_years_status}")

    # サンプル数
    sample_status = "✅ PASS" if details['sample_size']['pass'] else "❌ FAIL"
    print(f"  サンプル数:   {details['sample_size']['value']:>7}件 (基準: {criteria['sample_min']:>7}件以上)   {sample_status}")

    print("-" * 70)

    if data['pass']:
        print("  総合判定: ✅ 合格（Tier 2標準テストへ進んでください）")
        print()
        print("  【次のステップ】")
        print("    1. config/bet_conditions.py に条件を追加")
        print("    2. python scripts/backtest/standard_backtest.py --full で Tier 2標準テスト実行")
        print("    3. Tier 2合格後、Tier 3実環境確認へ")
    else:
        print("  総合判定: ❌ 不合格（条件の見直しが必要です）")
        print()
        print("  【推奨アクション】")
        print("    - 会場フィルター、オッズ範囲、級別条件などを調整")
        print("    - データ期間を広げて再分析")
        print("    - 不採用案として docs/improvement_attempts/REJECTED_IDEAS.md に記録")

    print()


def main():
    parser = argparse.ArgumentParser(
        description='Tier 1: 新規条件の簡易テスト（2年間、高速）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
使用例:
  # 既存条件のテスト
  python scripts/backtest/quick_condition_test.py --condition-id "B_50_100"

  # カスタム条件のテスト（JSON形式）
  python scripts/backtest/quick_condition_test.py --condition-json '{
    "id": "TEST",
    "name": "テスト条件",
    "confidence": "B",
    "c1_rank": ["A1", "B1"],
    "odds_min": 50,
    "odds_max": 100,
    "venue_filter": [1, 2, 3],
    "use_pattern_h": true
  }'

合格基準:
  - ROI 150%以上
  - 1/2年黒字（2024年または2025年が黒字）
  - サンプル数 50件以上
        '''
    )
    parser.add_argument('--condition-id', type=str, help='テスト対象の条件ID（例: B_50_100）')
    parser.add_argument('--condition-json', type=str, help='カスタム条件（JSON形式）')
    args = parser.parse_args()

    # 条件の取得
    if args.condition_id:
        cond = get_condition_by_id(args.condition_id)
        if not cond:
            print(f"エラー: 条件ID '{args.condition_id}' が見つかりません")
            print(f"利用可能な条件ID:")
            for c in STANDARD_BET_CONDITIONS:
                print(f"  - {c['id']}: {c['name']}")
            sys.exit(1)
    elif args.condition_json:
        try:
            cond = json.loads(args.condition_json)
        except json.JSONDecodeError as e:
            print(f"エラー: JSONのパースに失敗しました: {e}")
            sys.exit(1)
    else:
        print("エラー: --condition-id または --condition-json のいずれかを指定してください")
        sys.exit(1)

    print(f"Tier 1簡易テストを実行中... ({TIER1_YEARS[0]}-{TIER1_YEARS[-1]})")
    data = run_tier1_test(cond)
    print_tier1_results(data)


if __name__ == '__main__':
    main()
