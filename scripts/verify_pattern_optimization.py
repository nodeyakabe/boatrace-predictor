#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直前情報最適化の効果検証スクリプト

2024年データでのバックテストを実施し、以下を検証:
1. パターン適用頻度と効果
2. 信頼度別の効果
3. 会場別の効果
4. 統計的有意性
"""

import sqlite3
import sys
import os
from pathlib import Path
from collections import defaultdict
from datetime import datetime
import json
import csv
import math

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def get_db_connection():
    """データベース接続を取得"""
    db_path = project_root / 'data' / 'boatrace.db'
    return sqlite3.connect(str(db_path))


def calculate_ranks(before_data):
    """展示タイム・ST順位を計算"""
    if not before_data or len(before_data) < 6:
        return {}, {}

    # 展示タイム順位
    exhibition_times = [(row[0], row[1]) for row in before_data if row[1] is not None]
    if len(exhibition_times) >= 6:
        exhibition_sorted = sorted(exhibition_times, key=lambda x: x[1])
        exhibition_rank_map = {pit: rank+1 for rank, (pit, _) in enumerate(exhibition_sorted)}
    else:
        exhibition_rank_map = {}

    # ST順位
    st_times = [(row[0], row[2]) for row in before_data if row[2] is not None]
    if len(st_times) >= 6:
        st_sorted = sorted(st_times, key=lambda x: abs(x[1]))
        st_rank_map = {pit: rank+1 for rank, (pit, _) in enumerate(st_sorted)}
    else:
        st_rank_map = {}

    return exhibition_rank_map, st_rank_map


# =============================================================================
# 新しいパターン定義（最適化後）
# =============================================================================

# 1着パターン（新ロジック）
NEW_PATTERNS_1ST = [
    {
        'name': 'pre1_st1_ex1',
        'description': 'PRE1位 & ST1位 & 展示1位（最強複合）',
        'multiplier': 1.50,
        'condition': lambda pre, ex, st: pre == 1 and st == 1 and ex == 1,
    },
    {
        'name': 'pre1_st1',
        'description': 'PRE1位 & ST1位',
        'multiplier': 1.411,
        'condition': lambda pre, ex, st: pre == 1 and st == 1 and ex != 1,
    },
    {
        'name': 'pre1_st6',
        'description': 'PRE1位 & ST6位（大幅ペナルティ）',
        'multiplier': 0.53,
        'condition': lambda pre, ex, st: pre == 1 and st == 6,
    },
    {
        'name': 'pre1_st5_6',
        'description': 'PRE1位 & ST5-6位（ペナルティ）',
        'multiplier': 0.63,
        'condition': lambda pre, ex, st: pre == 1 and st == 5,
    },
    {
        'name': 'pre1_st4_6',
        'description': 'PRE1位 & ST4-6位（ペナルティ）',
        'multiplier': 0.70,
        'condition': lambda pre, ex, st: pre == 1 and st == 4,
    },
    {
        'name': 'pre1_ex1',
        'description': 'PRE1位 & 展示1位',
        'multiplier': 1.286,
        'condition': lambda pre, ex, st: pre == 1 and ex == 1,
    },
]

# 2着パターン（新ロジック）
NEW_PATTERNS_2ND = [
    {
        'name': 'pre2_st1_2',
        'description': 'PRE2位 & ST1-2位（強力）',
        'multiplier': 1.12,
        'condition': lambda pre, ex, st: pre == 2 and st <= 2,
    },
    {
        'name': 'pre2_3_ex1_2',
        'description': 'PRE2-3位 & 展示1-2位',
        'multiplier': 1.0,  # 無効化
        'condition': lambda pre, ex, st: 2 <= pre <= 3 and ex <= 2,
    },
    {
        'name': 'ex1_3_pre2_3',
        'description': '展示1-3位 & PRE2-3位',
        'multiplier': 1.0,  # 無効化
        'condition': lambda pre, ex, st: ex <= 3 and 2 <= pre <= 3,
    },
    {
        'name': 'ex_rank_2',
        'description': '展示2位',
        'multiplier': 1.0,  # 無効化
        'condition': lambda pre, ex, st: ex == 2,
    },
]

# TOP3パターン（新ロジック）
NEW_PATTERNS_TOP3 = [
    {
        'name': 'st1_2_ex1_2_double_top',
        'description': 'ST1-2位 & 展示1-2位（両方上位）',
        'multiplier': 1.35,
        'condition': lambda pre, ex, st: st <= 2 and ex <= 2,
    },
    {
        'name': 'pre1_3_st1',
        'description': 'PRE1-3位 & ST1位（強力）',
        'multiplier': 1.23,
        'condition': lambda pre, ex, st: pre <= 3 and st == 1,
    },
    {
        'name': 'st5_6_ex5_6_double_bottom',
        'description': 'ST5-6位 & 展示5-6位（両方下位、ペナルティ）',
        'multiplier': 0.60,
        'condition': lambda pre, ex, st: st >= 5 and ex >= 5,
    },
    {
        'name': 'pre1_4_ex1_2',
        'description': 'PRE1-4位 & 展示1-2位',
        'multiplier': 1.0,  # 無効化
        'condition': lambda pre, ex, st: pre <= 4 and ex <= 2,
    },
    {
        'name': 'ex_rank_1_2',
        'description': '展示1-2位',
        'multiplier': 1.0,  # 無効化
        'condition': lambda pre, ex, st: ex <= 2,
    },
]

# =============================================================================
# 旧パターン定義（比較用）
# =============================================================================

OLD_PATTERNS_1ST = [
    {
        'name': 'pre1_st1',
        'description': 'PRE1位 & ST1位',
        'multiplier': 1.411,
        'condition': lambda pre, ex, st: pre == 1 and st == 1,
    },
    {
        'name': 'pre1_ex1',
        'description': 'PRE1位 & 展示1位',
        'multiplier': 1.286,
        'condition': lambda pre, ex, st: pre == 1 and ex == 1,
    },
]

OLD_PATTERNS_2ND = [
    {
        'name': 'pre2_3_ex1_2',
        'description': 'PRE2-3位 & 展示1-2位',
        'multiplier': 1.084,
        'condition': lambda pre, ex, st: 2 <= pre <= 3 and ex <= 2,
    },
    {
        'name': 'ex1_3_pre2_3',
        'description': '展示1-3位 & PRE2-3位',
        'multiplier': 1.069,
        'condition': lambda pre, ex, st: ex <= 3 and 2 <= pre <= 3,
    },
    {
        'name': 'ex_rank_2',
        'description': '展示2位',
        'multiplier': 1.035,
        'condition': lambda pre, ex, st: ex == 2,
    },
]

OLD_PATTERNS_TOP3 = [
    {
        'name': 'pre1_4_ex1_2',
        'description': 'PRE1-4位 & 展示1-2位',
        'multiplier': 1.104,
        'condition': lambda pre, ex, st: pre <= 4 and ex <= 2,
    },
    {
        'name': 'ex_rank_1_2',
        'description': '展示1-2位',
        'multiplier': 1.051,
        'condition': lambda pre, ex, st: ex <= 2,
    },
]


def check_pattern_match(pre_rank, ex_rank, st_rank, patterns, target_rank_filter=None):
    """パターンマッチをチェック"""
    matched = []
    for pattern in patterns:
        try:
            if pattern['condition'](pre_rank, ex_rank, st_rank):
                if target_rank_filter is None or pattern.get('target_rank', target_rank_filter) == target_rank_filter:
                    matched.append(pattern)
        except Exception:
            pass
    return matched


def run_backtest():
    """バックテストを実行"""
    conn = get_db_connection()
    cursor = conn.cursor()

    print("=" * 80)
    print("直前情報最適化の効果検証")
    print("=" * 80)
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 2024年のレースを取得
    cursor.execute('''
        SELECT DISTINCT r.id, r.venue_code, r.race_date
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id
        JOIN results res ON r.id = res.race_id
        JOIN race_details rd ON r.id = rd.race_id
        WHERE r.race_date BETWEEN '2024-01-01' AND '2024-12-31'
        AND rp.prediction_type = 'before'
        AND res.rank = '1'
        AND rd.exhibition_time IS NOT NULL
        AND rd.st_time IS NOT NULL
        ORDER BY r.race_date
    ''')
    races = cursor.fetchall()
    print(f"分析対象レース数: {len(races)}")

    # 結果を収集
    results_new = defaultdict(lambda: {'correct': 0, 'total': 0, 'patterns': defaultdict(lambda: {'correct': 0, 'total': 0})})
    results_old = defaultdict(lambda: {'correct': 0, 'total': 0, 'patterns': defaultdict(lambda: {'correct': 0, 'total': 0})})

    # パターン別統計
    pattern_stats_new = defaultdict(lambda: {'applied': 0, 'correct': 0, 'ranks': []})
    pattern_stats_old = defaultdict(lambda: {'applied': 0, 'correct': 0, 'ranks': []})

    # 会場別統計
    venue_stats_new = defaultdict(lambda: {'correct': 0, 'total': 0})
    venue_stats_old = defaultdict(lambda: {'correct': 0, 'total': 0})

    # 信頼度別統計
    confidence_stats_new = defaultdict(lambda: {'correct': 0, 'total': 0})
    confidence_stats_old = defaultdict(lambda: {'correct': 0, 'total': 0})

    processed = 0

    for race_id, venue_code, race_date in races:
        # 予測を取得
        cursor.execute('''
            SELECT pit_number, total_score, confidence, rank_prediction
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'before'
            ORDER BY rank_prediction
        ''', (race_id,))
        predictions = cursor.fetchall()

        if not predictions:
            continue

        # 実際の結果（1着艇番）
        cursor.execute('''
            SELECT pit_number FROM results WHERE race_id = ? AND rank = '1'
        ''', (race_id,))
        result_row = cursor.fetchone()
        if not result_row:
            continue
        actual_first = result_row[0]

        # BEFORE情報を取得
        cursor.execute('''
            SELECT pit_number, exhibition_time, st_time
            FROM race_details
            WHERE race_id = ?
            ORDER BY pit_number
        ''', (race_id,))
        before_data = cursor.fetchall()

        if len(before_data) < 6:
            continue

        ex_rank_map, st_rank_map = calculate_ranks(before_data)
        if not ex_rank_map or not st_rank_map:
            continue

        # 予測順位マップを作成
        pred_sorted = sorted(predictions, key=lambda x: x[1], reverse=True)
        pre_rank_map = {p[0]: i+1 for i, p in enumerate(pred_sorted)}

        # 信頼度を取得
        confidence = predictions[0][2] if predictions else 'D'

        # 信頼度A/Eはパターンをスキップ
        if confidence in ['A', 'E']:
            continue

        # 各艇を分析
        for pred in predictions:
            pit, score, conf, rank_pred = pred
            pre_rank = pre_rank_map.get(pit)
            ex_rank = ex_rank_map.get(pit)
            st_rank = st_rank_map.get(pit)

            if pre_rank is None or ex_rank is None or st_rank is None:
                continue

            is_first = (actual_first == pit)

            # 新ロジックのパターンマッチ
            new_multiplier = 1.0
            new_matched = []

            if pre_rank == 1:
                new_matched = check_pattern_match(pre_rank, ex_rank, st_rank, NEW_PATTERNS_1ST)
            elif pre_rank in [2, 3]:
                new_matched = check_pattern_match(pre_rank, ex_rank, st_rank, NEW_PATTERNS_2ND)

            # TOP3パターンも追加
            new_matched.extend(check_pattern_match(pre_rank, ex_rank, st_rank, NEW_PATTERNS_TOP3))

            if new_matched:
                new_multiplier = max(p['multiplier'] for p in new_matched)
                for pattern in new_matched:
                    pattern_stats_new[pattern['name']]['applied'] += 1
                    if is_first:
                        pattern_stats_new[pattern['name']]['correct'] += 1
                    if pre_rank == 1:
                        pattern_stats_new[pattern['name']]['ranks'].append(1 if is_first else 0)

            # 旧ロジックのパターンマッチ
            old_multiplier = 1.0
            old_matched = []

            if pre_rank == 1:
                old_matched = check_pattern_match(pre_rank, ex_rank, st_rank, OLD_PATTERNS_1ST)
            elif pre_rank in [2, 3]:
                old_matched = check_pattern_match(pre_rank, ex_rank, st_rank, OLD_PATTERNS_2ND)

            old_matched.extend(check_pattern_match(pre_rank, ex_rank, st_rank, OLD_PATTERNS_TOP3))

            if old_matched:
                old_multiplier = max(p['multiplier'] for p in old_matched)
                for pattern in old_matched:
                    pattern_stats_old[pattern['name']]['applied'] += 1
                    if is_first:
                        pattern_stats_old[pattern['name']]['correct'] += 1
                    if pre_rank == 1:
                        pattern_stats_old[pattern['name']]['ranks'].append(1 if is_first else 0)

            # 1着予測（PRE1位）の的中率を計算
            if pre_rank == 1:
                # 新ロジック
                if new_multiplier != 1.0:
                    results_new['all']['total'] += 1
                    confidence_stats_new[confidence]['total'] += 1
                    venue_stats_new[venue_code]['total'] += 1
                    if is_first:
                        results_new['all']['correct'] += 1
                        confidence_stats_new[confidence]['correct'] += 1
                        venue_stats_new[venue_code]['correct'] += 1

                # 旧ロジック
                if old_multiplier != 1.0:
                    results_old['all']['total'] += 1
                    confidence_stats_old[confidence]['total'] += 1
                    venue_stats_old[venue_code]['total'] += 1
                    if is_first:
                        results_old['all']['correct'] += 1
                        confidence_stats_old[confidence]['correct'] += 1
                        venue_stats_old[venue_code]['correct'] += 1

        processed += 1
        if processed % 1000 == 0:
            print(f"処理中... {processed}/{len(races)}")

    print(f"\n処理完了: {processed}レース")
    print()

    # 結果出力
    print("=" * 80)
    print("1. 全体結果比較")
    print("=" * 80)

    new_total = results_new['all']['total']
    new_correct = results_new['all']['correct']
    old_total = results_old['all']['total']
    old_correct = results_old['all']['correct']

    new_rate = (new_correct / new_total * 100) if new_total > 0 else 0
    old_rate = (old_correct / old_total * 100) if old_total > 0 else 0

    print(f"新ロジック: {new_correct}/{new_total} ({new_rate:.2f}%)")
    print(f"旧ロジック: {old_correct}/{old_total} ({old_rate:.2f}%)")
    print(f"差分: {new_rate - old_rate:+.2f}pt")
    print()

    # パターン別効果
    print("=" * 80)
    print("2. パターン別効果（新ロジック）")
    print("=" * 80)

    pattern_results = []
    for name, stats in sorted(pattern_stats_new.items(), key=lambda x: x[1]['applied'], reverse=True):
        applied = stats['applied']
        correct = stats['correct']
        rate = (correct / applied * 100) if applied > 0 else 0
        pattern_results.append({
            'pattern': name,
            'applied': applied,
            'correct': correct,
            'rate': rate
        })
        print(f"  {name}: {correct}/{applied} ({rate:.2f}%)")

    print()

    # 新規パターンのみをハイライト
    print("=" * 80)
    print("3. 新規追加パターンの効果")
    print("=" * 80)

    new_patterns = ['pre1_st1_ex1', 'pre1_st6', 'pre1_st5_6', 'pre1_st4_6',
                    'pre2_st1_2', 'pre1_3_st1', 'st1_2_ex1_2_double_top', 'st5_6_ex5_6_double_bottom']

    for name in new_patterns:
        if name in pattern_stats_new:
            stats = pattern_stats_new[name]
            applied = stats['applied']
            correct = stats['correct']
            rate = (correct / applied * 100) if applied > 0 else 0
            print(f"  {name}: {correct}/{applied} ({rate:.2f}%)")
        else:
            print(f"  {name}: 適用なし")

    print()

    # 無効化パターンの効果確認
    print("=" * 80)
    print("4. 無効化パターンの旧効果（参考）")
    print("=" * 80)

    disabled_patterns = ['pre2_3_ex1_2', 'ex1_3_pre2_3', 'ex_rank_2', 'pre1_4_ex1_2', 'ex_rank_1_2']
    for name in disabled_patterns:
        if name in pattern_stats_old:
            stats = pattern_stats_old[name]
            applied = stats['applied']
            correct = stats['correct']
            rate = (correct / applied * 100) if applied > 0 else 0
            print(f"  {name}: {correct}/{applied} ({rate:.2f}%) [旧]")

    print()

    # 信頼度別効果
    print("=" * 80)
    print("5. 信頼度別効果")
    print("=" * 80)

    confidence_results = []
    for conf in ['A', 'B', 'C', 'D', 'E']:
        new_stats = confidence_stats_new[conf]
        old_stats = confidence_stats_old[conf]

        new_rate = (new_stats['correct'] / new_stats['total'] * 100) if new_stats['total'] > 0 else 0
        old_rate = (old_stats['correct'] / old_stats['total'] * 100) if old_stats['total'] > 0 else 0

        if new_stats['total'] > 0 or old_stats['total'] > 0:
            print(f"  {conf}: 新={new_stats['correct']}/{new_stats['total']} ({new_rate:.2f}%) | 旧={old_stats['correct']}/{old_stats['total']} ({old_rate:.2f}%) | 差分={new_rate - old_rate:+.2f}pt")
            confidence_results.append({
                'confidence': conf,
                'new_correct': new_stats['correct'],
                'new_total': new_stats['total'],
                'new_rate': new_rate,
                'old_correct': old_stats['correct'],
                'old_total': old_stats['total'],
                'old_rate': old_rate,
                'diff': new_rate - old_rate
            })

    print()

    # 会場別効果（TOP10）
    print("=" * 80)
    print("6. 会場別効果 (TOP10)")
    print("=" * 80)

    venue_results = []
    for venue in sorted(venue_stats_new.keys()):
        new_stats = venue_stats_new[venue]
        old_stats = venue_stats_old[venue]

        if new_stats['total'] >= 10:  # 最低10レース以上
            new_rate = (new_stats['correct'] / new_stats['total'] * 100)
            old_rate = (old_stats['correct'] / old_stats['total'] * 100) if old_stats['total'] > 0 else 0
            diff = new_rate - old_rate
            venue_results.append({
                'venue': venue,
                'new_correct': new_stats['correct'],
                'new_total': new_stats['total'],
                'new_rate': new_rate,
                'old_correct': old_stats['correct'],
                'old_total': old_stats['total'],
                'old_rate': old_rate,
                'diff': diff
            })

    venue_results.sort(key=lambda x: x['diff'], reverse=True)
    for v in venue_results[:10]:
        print(f"  会場{v['venue']}: 新={v['new_rate']:.1f}% | 旧={v['old_rate']:.1f}% | 差分={v['diff']:+.1f}pt")

    print()

    # 統計的有意性の検証
    print("=" * 80)
    print("7. 統計的有意性の検証")
    print("=" * 80)

    if new_total > 0 and old_total > 0:
        # Z検定（2比率の検定）
        p1 = new_correct / new_total
        p2 = old_correct / old_total
        n1 = new_total
        n2 = old_total

        # プールされた比率
        p_pool = (new_correct + old_correct) / (n1 + n2)

        # 標準誤差
        se = math.sqrt(p_pool * (1 - p_pool) * (1/n1 + 1/n2))

        if se > 0:
            z_score = (p1 - p2) / se

            # p値の近似計算（正規分布）
            from math import erf
            p_value = 2 * (1 - 0.5 * (1 + erf(abs(z_score) / math.sqrt(2))))

            print(f"  Z-Score: {z_score:.4f}")
            print(f"  p-value: {p_value:.4f}")
            print(f"  有意水準0.05: {'有意差あり' if p_value < 0.05 else '有意差なし'}")

            # 効果量（Cohen's h）
            phi1 = 2 * math.asin(math.sqrt(p1))
            phi2 = 2 * math.asin(math.sqrt(p2))
            cohens_h = abs(phi1 - phi2)

            effect_size = '大' if cohens_h >= 0.8 else ('中' if cohens_h >= 0.5 else ('小' if cohens_h >= 0.2 else '微小'))
            print(f"  Cohen's h: {cohens_h:.4f} ({effect_size})")

    print()

    # CSVファイル出力
    print("=" * 80)
    print("8. 結果ファイル出力")
    print("=" * 80)

    output_dir = project_root / 'temp' / 'pattern_verification'
    output_dir.mkdir(parents=True, exist_ok=True)

    # パターン別効果CSV
    pattern_csv = output_dir / 'pattern_effects.csv'
    with open(pattern_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['pattern', 'applied', 'correct', 'rate'])
        writer.writeheader()
        writer.writerows(pattern_results)
    print(f"  パターン別効果: {pattern_csv}")

    # 信頼度別効果CSV
    confidence_csv = output_dir / 'confidence_effects.csv'
    with open(confidence_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['confidence', 'new_correct', 'new_total', 'new_rate',
                                                'old_correct', 'old_total', 'old_rate', 'diff'])
        writer.writeheader()
        writer.writerows(confidence_results)
    print(f"  信頼度別効果: {confidence_csv}")

    # 会場別効果CSV
    venue_csv = output_dir / 'venue_effects.csv'
    with open(venue_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['venue', 'new_correct', 'new_total', 'new_rate',
                                                'old_correct', 'old_total', 'old_rate', 'diff'])
        writer.writeheader()
        writer.writerows(venue_results)
    print(f"  会場別効果: {venue_csv}")

    conn.close()

    return {
        'new_total': new_total,
        'new_correct': new_correct,
        'old_total': old_total,
        'old_correct': old_correct,
        'pattern_results': pattern_results,
        'confidence_results': confidence_results,
        'venue_results': venue_results
    }


if __name__ == '__main__':
    results = run_backtest()
