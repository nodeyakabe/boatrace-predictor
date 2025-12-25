# -*- coding: utf-8 -*-
"""
スコア100点パターンを抽出し、既存条件との重複を除外するスクリプト

目的:
- validated_patterns.jsonからスコア100点のパターンを抽出
- 既存のbet_target_evaluator.pyの条件と重複するパターンを除外
- 本番採用候補をリストアップ
"""

import json
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def load_patterns():
    """validated_patterns.jsonからパターンを読み込む"""
    patterns_file = project_root / "data" / "validated_patterns.json"
    with open(patterns_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_existing_conditions():
    """既存の購入条件を取得"""
    # bet_target_evaluator.pyの条件を手動で定義
    existing = {
        # 既存のC条件
        'C': [
            {'odds_range': (20, 30), 'c1_rank': ['B1'], 'venues': [23, 18, 5, 4, 9, 15, 8, 24, 20, 17]},
        ],
        # 既存のD条件
        'D': [
            {'odds_range': (40, 50), 'c1_rank': ['B1']},
            {'odds_range': (30, 60), 'c1_rank': ['A1', 'A2', 'B1']},
        ],
        # 既存のA条件
        'A': [
            {'odds_range': (10, 12), 'c1_rank': ['A1']},
            {'odds_range': (14, 16), 'c1_rank': ['A1']},
            {'c1_rank': ['B1'], 'motor_min': 40},  # モーター条件
        ],
        # 既存のB条件
        'B': [
            {'odds_range': (50, 100), 'c1_rank': ['A1', 'A2', 'B1']},
            {'odds_range': (30, 50), 'c1_rank': ['B1'], 'venues': [10, 6, 16, 21, 9, 13, 20, 24, 7, 8]},
        ],
    }
    return existing


def is_overlapping(pattern, existing_conditions):
    """
    パターンが既存条件と重複するかチェック

    完全な重複のみをチェック（部分的な重複は許容）
    """
    confidence = pattern.get('confidence')
    if confidence not in existing_conditions:
        return False

    conditions = existing_conditions[confidence]

    # パターンの属性を取得
    pattern_rank = pattern.get('racer_rank')
    pattern_venue = pattern.get('venue')
    pattern_motor = 'motor' in pattern.get('type', '')

    # venue が 'ALL' や None の場合は全会場扱い
    is_all_venue = not pattern_venue or str(pattern_venue).upper() == 'ALL'

    for cond in conditions:
        # ランク条件のチェック
        if 'c1_rank' in cond:
            if pattern_rank and pattern_rank in cond['c1_rank']:
                # モーター条件の場合
                if 'motor_min' in cond and pattern_motor:
                    return True
                # 会場フィルターありの条件の場合
                if 'venues' in cond:
                    if not is_all_venue:
                        try:
                            venue_code = int(pattern_venue)
                            if venue_code in cond['venues']:
                                return True
                        except (ValueError, TypeError):
                            pass
                # 汎用条件の場合
                if 'venues' not in cond and 'motor_min' not in cond:
                    # venue指定なしのパターン（全会場）は既存の全会場条件と重複
                    if is_all_venue:
                        return True

    return False


def filter_score100_patterns(patterns, existing_conditions):
    """
    スコア100点のパターンをフィルタリング

    条件:
    - スコア100点
    - 既存条件と重複しない
    - サンプル数100件以上
    - 最低年ROI > 100%
    """
    score100_patterns = []

    for pattern in patterns:
        if pattern.get('score') != 100:
            continue

        # 基本フィルター
        total = pattern.get('total', 0)
        min_roi = pattern.get('min_roi', 0)

        if total < 100:
            continue

        if min_roi <= 100:
            continue

        # 重複チェック
        if is_overlapping(pattern, existing_conditions):
            continue

        score100_patterns.append(pattern)

    return score100_patterns


def analyze_patterns(patterns):
    """パターンを分析してカテゴリ別に整理"""
    categories = {
        'venue_conf_rank': [],      # 会場×信頼度×級別
        'venue_conf_motor': [],     # 会場×信頼度×モーター
        'conf_rank_motor': [],      # 信頼度×級別×モーター（全会場）
        'venue_conf': [],           # 会場×信頼度
        'other': [],                # その他
    }

    for pattern in patterns:
        pattern_type = pattern.get('type', '')

        if 'motor' in pattern_type:
            if pattern.get('venue') and pattern.get('venue') != 'all':
                categories['venue_conf_motor'].append(pattern)
            else:
                categories['conf_rank_motor'].append(pattern)
        elif 'rank' in pattern_type:
            categories['venue_conf_rank'].append(pattern)
        elif pattern.get('venue') and pattern.get('venue') != 'all':
            categories['venue_conf'].append(pattern)
        else:
            categories['other'].append(pattern)

    return categories


def print_top_patterns(patterns, title, top_n=10):
    """上位パターンを表示"""
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")

    # ROI降順でソート
    sorted_patterns = sorted(patterns, key=lambda x: x.get('roi', 0), reverse=True)

    for i, p in enumerate(sorted_patterns[:top_n], 1):
        print(f"\n{i}. {p.get('condition_str', 'N/A')}")
        print(f"   ROI: {p.get('roi', 0):.1f}%")
        print(f"   サンプル数: {p.get('total', 0)}件")
        print(f"   的中率: {p.get('hit_rate', 0):.1f}%")
        print(f"   安定年数: {p.get('positive_years', 0)}年")
        print(f"   最低年ROI: {p.get('min_roi', 0):.1f}%")
        print(f"   信頼度: {p.get('confidence', 'N/A')}")
        if p.get('venue_name'):
            print(f"   会場: {p.get('venue_name')}")


def main():
    print("=" * 60)
    print(" スコア100点パターン抽出・分析")
    print("=" * 60)

    # パターン読み込み
    patterns = load_patterns()
    print(f"\n総パターン数: {len(patterns)}件")

    # スコア100点のパターン数
    score100_all = [p for p in patterns if p.get('score') == 100]
    print(f"スコア100点パターン: {len(score100_all)}件")

    # 既存条件取得
    existing = get_existing_conditions()

    # フィルタリング
    filtered = filter_score100_patterns(patterns, existing)
    print(f"\n抽出結果（重複除外・サンプル100件以上・最低年ROI>100%）: {len(filtered)}件")

    # カテゴリ別分析
    categories = analyze_patterns(filtered)

    print(f"\n--- カテゴリ別件数 ---")
    for cat, pats in categories.items():
        print(f"  {cat}: {len(pats)}件")

    # 各カテゴリの上位パターンを表示
    if categories['conf_rank_motor']:
        print_top_patterns(
            categories['conf_rank_motor'],
            "全会場×信頼度×級別×モーター（新規追加候補・最優先）",
            top_n=10
        )

    if categories['venue_conf_rank']:
        print_top_patterns(
            categories['venue_conf_rank'],
            "会場×信頼度×級別（会場限定条件）",
            top_n=10
        )

    if categories['venue_conf_motor']:
        print_top_patterns(
            categories['venue_conf_motor'],
            "会場×信頼度×モーター（会場×モーター条件）",
            top_n=10
        )

    # 全会場のモーター条件を詳細分析
    print("\n" + "=" * 60)
    print(" 【注目】全会場×信頼度×級別×モーター条件の詳細")
    print("=" * 60)

    motor_patterns = categories['conf_rank_motor']
    if motor_patterns:
        # 信頼度別に分類
        by_confidence = {}
        for p in motor_patterns:
            conf = p.get('confidence', 'N/A')
            if conf not in by_confidence:
                by_confidence[conf] = []
            by_confidence[conf].append(p)

        for conf in ['A', 'B', 'C', 'D']:
            if conf in by_confidence:
                print(f"\n--- 信頼度{conf} ---")
                for p in sorted(by_confidence[conf], key=lambda x: x.get('roi', 0), reverse=True):
                    print(f"  {p.get('condition_str')}")
                    print(f"    ROI: {p.get('roi', 0):.1f}%, サンプル: {p.get('total', 0)}件, 最低年: {p.get('min_roi', 0):.1f}%")

    # JSON出力（後続処理用）
    output_file = project_root / "data" / "score100_candidates.json"
    output_data = {
        'summary': {
            'total_patterns': len(patterns),
            'score100_count': len(score100_all),
            'filtered_count': len(filtered),
        },
        'categories': {k: len(v) for k, v in categories.items()},
        'conf_rank_motor': categories['conf_rank_motor'],
        'top_venue_conf_rank': sorted(categories['venue_conf_rank'], key=lambda x: x.get('roi', 0), reverse=True)[:20],
        'top_venue_conf_motor': sorted(categories['venue_conf_motor'], key=lambda x: x.get('roi', 0), reverse=True)[:20],
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"\n\n候補パターンを {output_file} に出力しました")

    return filtered


if __name__ == "__main__":
    main()
