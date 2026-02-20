"""
多条件複合パターン探索スクリプト
================================

4条件以上の複合パターンを効率的に探索する。
段階的に有望なパターンを拡張していく方式。

使用例:
    # 基本実行（4条件まで）
    python scripts/analysis/multi_condition_explorer.py

    # 5条件まで探索
    python scripts/analysis/multi_condition_explorer.py --max-level 5

    # 特定条件を必須にする
    python scripts/analysis/multi_condition_explorer.py --must-include venue_code:08

    # 最小サンプル数を変更
    python scripts/analysis/multi_condition_explorer.py --min-samples 50
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from itertools import combinations
import json
import argparse
from collections import defaultdict


# 探索対象の条件軸と値
CONDITION_AXES = {
    'venue_code': None,  # 動的に取得
    'confidence': ['A', 'B', 'C', 'D', 'E'],
    'course1_rank': ['A1', 'A2', 'B1', 'B2'],
    'odds_band': ['10-20', '20-30', '30-50', '50-100', '100+'],
    'predicted_pit': ['1', '2', '3', '4', '5', '6'],
    'motor_band': ['30-', '30-40', '40+'],
    'wind_band': ['0-2', '2-4', '4+'],
    'wind_direction_group': None,  # 追い風/向かい風/横風
    'score_diff_band': ['0-5', '5-10', '10-20', '20+'],
}


def load_data(db_path: str, prediction_type: str = 'before') -> pd.DataFrame:
    """データ読み込みと前処理"""

    conn = sqlite3.connect(db_path)

    query = """
        SELECT
            maf.*,
            -- 風向グループ（追い風/向かい風/横風）
            CASE
                WHEN maf.wind_direction IN ('北', '北北東', '北東', '北北西', '北西') THEN 'north'
                WHEN maf.wind_direction IN ('南', '南南東', '南東', '南南西', '南西') THEN 'south'
                WHEN maf.wind_direction IN ('東', '東北東', '東南東') THEN 'east'
                WHEN maf.wind_direction IN ('西', '西北西', '西南西') THEN 'west'
                ELSE 'unknown'
            END as wind_direction_group
        FROM ml_analysis_features maf
        WHERE maf.prediction_type = ?
    """

    df = pd.read_sql_query(query, conn, params=[prediction_type])
    conn.close()

    # predicted_pitを文字列に変換
    df['predicted_pit'] = df['predicted_pit'].astype(str).str.replace('.0', '', regex=False)

    print(f"データ読み込み: {len(df):,}件 ({prediction_type})")
    return df


def get_condition_values(df: pd.DataFrame) -> dict:
    """データから条件値を動的に取得"""

    axes = CONDITION_AXES.copy()

    # venue_codeを動的取得
    axes['venue_code'] = sorted(df['venue_code'].dropna().unique().tolist())

    # wind_direction_groupを設定
    axes['wind_direction_group'] = ['north', 'south', 'east', 'west']

    return axes


def evaluate_pattern(df: pd.DataFrame, conditions: dict) -> dict:
    """パターンを評価してROI等を計算"""

    mask = pd.Series([True] * len(df), index=df.index)

    for col, val in conditions.items():
        if col in df.columns:
            mask &= (df[col] == val)

    subset = df[mask]

    if len(subset) == 0:
        return None

    hits = subset['is_trifecta_hit'].sum()
    total = len(subset)
    payout = subset['trifecta_payout'].sum()

    roi = payout / (total * 100) * 100 if total > 0 else 0
    hit_rate = hits / total * 100 if total > 0 else 0

    # 年度別ROI
    yearly_roi = {}
    for year in sorted(subset['year'].unique()):
        year_subset = subset[subset['year'] == year]
        if len(year_subset) > 0:
            year_payout = year_subset['trifecta_payout'].sum()
            year_roi = year_payout / (len(year_subset) * 100) * 100
            yearly_roi[year] = round(year_roi, 1)

    positive_years = sum(1 for r in yearly_roi.values() if r > 100)

    return {
        'conditions': conditions,
        'condition_str': ' × '.join([f"{k}:{v}" for k, v in conditions.items()]),
        'total': total,
        'hits': hits,
        'hit_rate': round(hit_rate, 2),
        'roi': round(roi, 1),
        'yearly_roi': yearly_roi,
        'positive_years': positive_years,
        'total_years': len(yearly_roi),
    }


def explore_patterns(df: pd.DataFrame, max_level: int = 4,
                     min_samples: int = 100, min_roi: float = 100.0,
                     must_include: dict = None) -> list:
    """
    段階的にパターンを探索

    Args:
        df: データフレーム
        max_level: 最大条件数
        min_samples: 最小サンプル数
        min_roi: 最小ROI（%）
        must_include: 必須条件 {'col': 'val'}
    """

    axes = get_condition_values(df)
    all_patterns = []

    # 必須条件があれば初期条件として設定
    if must_include:
        initial_conditions = [must_include]
        start_level = len(must_include) + 1
    else:
        initial_conditions = [{}]
        start_level = 1

    print(f"\n探索開始: 最大{max_level}条件, 最小サンプル{min_samples}件, 最小ROI{min_roi}%")

    # Level 1から探索
    previous_patterns = initial_conditions

    for level in range(start_level, max_level + 1):
        print(f"\n=== Level {level} ({level}条件) ===")

        level_patterns = []

        # 前レベルのパターンを拡張
        for base_pattern in previous_patterns:
            # 既存条件のキーを取得
            used_cols = set(base_pattern.keys())

            # 追加可能な条件軸
            available_cols = [c for c in axes.keys() if c not in used_cols]

            for col in available_cols:
                values = axes.get(col, [])
                if values is None:
                    continue

                for val in values:
                    # 新しい条件を追加
                    new_conditions = base_pattern.copy()
                    new_conditions[col] = val

                    # 評価
                    result = evaluate_pattern(df, new_conditions)

                    if result is None:
                        continue

                    if result['total'] >= min_samples and result['roi'] >= min_roi:
                        level_patterns.append(result)

        # 重複除去（条件の順序に依存しない）
        seen = set()
        unique_patterns = []
        for p in level_patterns:
            key = tuple(sorted(p['conditions'].items()))
            if key not in seen:
                seen.add(key)
                unique_patterns.append(p)

        # ROI順にソート
        unique_patterns = sorted(unique_patterns, key=lambda x: x['roi'], reverse=True)

        print(f"  発見パターン: {len(unique_patterns)}件")

        # 上位を表示
        for p in unique_patterns[:10]:
            stability = f"{p['positive_years']}/{p['total_years']}年+"
            print(f"    {p['condition_str']}: ROI {p['roi']:.1f}%, {p['total']}件, {stability}")

        all_patterns.extend(unique_patterns)

        # 次レベルへ（上位パターンのみ拡張）
        if level < max_level:
            # ROI上位100件を次レベルの候補に
            previous_patterns = [p['conditions'] for p in unique_patterns[:100]]

            if len(previous_patterns) == 0:
                print("  これ以上の拡張は有意でない")
                break

    return all_patterns


def find_specific_patterns(df: pd.DataFrame, pattern_templates: list,
                           min_samples: int = 50) -> list:
    """
    特定のパターンテンプレートを探索

    Args:
        pattern_templates: 探索するパターンのテンプレート
            例: [('venue_code', 'wind_direction_group', 'wind_band', 'predicted_pit')]
    """

    axes = get_condition_values(df)
    results = []

    for template in pattern_templates:
        print(f"\n=== テンプレート: {' × '.join(template)} ===")

        # このテンプレートの全組み合わせを生成
        value_lists = []
        for col in template:
            values = axes.get(col, [])
            if values:
                value_lists.append([(col, v) for v in values])

        if not all(value_lists):
            continue

        # 組み合わせを生成
        from itertools import product
        combinations_list = list(product(*value_lists))

        template_results = []

        for combo in combinations_list:
            conditions = dict(combo)
            result = evaluate_pattern(df, conditions)

            if result and result['total'] >= min_samples:
                template_results.append(result)

        # ROI順にソート
        template_results = sorted(template_results, key=lambda x: x['roi'], reverse=True)

        print(f"  有効パターン: {len(template_results)}件")

        for p in template_results[:10]:
            stability = f"{p['positive_years']}/{p['total_years']}年+"
            print(f"    {p['condition_str']}: ROI {p['roi']:.1f}%, {p['total']}件, {stability}")

        results.extend(template_results)

    return results


def main():
    parser = argparse.ArgumentParser(description='多条件複合パターン探索')
    parser.add_argument('--max-level', type=int, default=4, help='最大条件数')
    parser.add_argument('--min-samples', type=int, default=100, help='最小サンプル数')
    parser.add_argument('--min-roi', type=float, default=100.0, help='最小ROI')
    parser.add_argument('--must-include', default=None,
                        help='必須条件 (例: venue_code:08,confidence:E)')
    parser.add_argument('--specific', action='store_true',
                        help='特定パターンテンプレートを探索')
    parser.add_argument('--output', default=None, help='結果出力先')
    args = parser.parse_args()

    db_path = Path(__file__).parent.parent.parent / "data" / "boatrace.db"

    # データ読み込み
    df = load_data(str(db_path))

    results = {
        'generated_at': datetime.now().isoformat(),
        'params': {
            'max_level': args.max_level,
            'min_samples': args.min_samples,
            'min_roi': args.min_roi,
        },
        'patterns': [],
    }

    # 必須条件のパース
    must_include = None
    if args.must_include:
        must_include = {}
        for item in args.must_include.split(','):
            col, val = item.split(':')
            must_include[col] = val

    if args.specific:
        # 特定パターンテンプレートを探索
        templates = [
            # 会場×風向×風速×コース
            ('venue_code', 'wind_direction_group', 'wind_band', 'predicted_pit'),
            # 会場×信頼度×オッズ×級別
            ('venue_code', 'confidence', 'odds_band', 'course1_rank'),
            # 信頼度×コース×モーター×風
            ('confidence', 'predicted_pit', 'motor_band', 'wind_band'),
            # 会場×信頼度×モーター×風
            ('venue_code', 'confidence', 'motor_band', 'wind_band'),
        ]

        patterns = find_specific_patterns(df, templates, min_samples=args.min_samples)
    else:
        # 段階的探索
        patterns = explore_patterns(
            df,
            max_level=args.max_level,
            min_samples=args.min_samples,
            min_roi=args.min_roi,
            must_include=must_include
        )

    results['patterns'] = patterns

    # 統計サマリー
    print("\n" + "=" * 60)
    print("探索結果サマリー")
    print("=" * 60)

    total_patterns = len(patterns)
    stable_patterns = [p for p in patterns if p['positive_years'] >= 4]
    high_roi_patterns = [p for p in patterns if p['roi'] >= 200]

    print(f"発見パターン総数: {total_patterns}件")
    print(f"安定パターン（4年+プラス）: {len(stable_patterns)}件")
    print(f"高ROIパターン（200%+）: {len(high_roi_patterns)}件")

    # 最も安定したパターン
    if stable_patterns:
        print("\n--- 最安定パターン TOP10 ---")
        stable_sorted = sorted(stable_patterns,
                               key=lambda x: (x['positive_years'], x['roi']),
                               reverse=True)
        for p in stable_sorted[:10]:
            print(f"  {p['condition_str']}")
            print(f"    → ROI {p['roi']:.1f}%, {p['positive_years']}/{p['total_years']}年+, {p['total']}件")
            yearly = ', '.join([f"{y}:{r:.0f}%" for y, r in p['yearly_roi'].items()])
            print(f"    → 年度別: {yearly}")

    # 結果保存
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = Path(__file__).parent.parent.parent / "data" / "multi_condition_patterns.json"

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n結果を保存: {output_path}")


if __name__ == "__main__":
    main()
