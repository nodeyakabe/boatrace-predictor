#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
パターン最適化修正の効果検証スクリプト

修正内容:
1. pre1_st4_6: 0.70 → 1.0（無効化）- 理由: 誤ブロック率44.6%
2. pre1_st5_6: 0.63 → 0.80（緩和）- 理由: 誤ブロック率40.7%

2024年データで修正前→修正後の効果を検証する。
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


def calculate_old_score(pre_rank, ex_rank, st_rank, original_score):
    """修正前のロジックでスコア調整"""
    multiplier = 1.0
    applied_patterns = []

    # 1着予測用パターン
    if pre_rank == 1:
        # 最強複合: PRE1位 & ST1位 & 展示1位
        if st_rank == 1 and ex_rank == 1:
            multiplier = max(multiplier, 1.50)
            applied_patterns.append(('pre1_st1_ex1', 1.50))
        # PRE1位 & ST1位
        elif st_rank == 1:
            multiplier = max(multiplier, 1.411)
            applied_patterns.append(('pre1_st1', 1.411))
        # ネガティブ: PRE1位 & ST6位
        if st_rank == 6:
            multiplier = min(multiplier, 0.53)
            applied_patterns.append(('pre1_st6', 0.53))
        # ネガティブ: PRE1位 & ST5位（修正前: 0.63）
        elif st_rank == 5:
            multiplier = min(multiplier, 0.63)
            applied_patterns.append(('pre1_st5_6', 0.63))
        # ネガティブ: PRE1位 & ST4位（修正前: 0.70）
        elif st_rank == 4:
            multiplier = min(multiplier, 0.70)
            applied_patterns.append(('pre1_st4_6', 0.70))
        # PRE1位 & 展示1位
        if ex_rank == 1:
            multiplier = max(multiplier, 1.286)
            applied_patterns.append(('pre1_ex1', 1.286))

    # 2着予測用パターン
    if pre_rank == 2:
        # PRE2位 & ST1-2位（強力）
        if st_rank <= 2:
            multiplier = max(multiplier, 1.12)
            applied_patterns.append(('pre2_st1_2', 1.12))

    # TOP3パターン
    # ST1-2位 & 展示1-2位（両方上位）
    if st_rank <= 2 and ex_rank <= 2:
        multiplier = max(multiplier, 1.35)
        applied_patterns.append(('st1_2_ex1_2_double_top', 1.35))

    # PRE1-3位 & ST1位（強力）
    if pre_rank <= 3 and st_rank == 1:
        multiplier = max(multiplier, 1.23)
        applied_patterns.append(('pre1_3_st1', 1.23))

    # ネガティブ: ST5-6位 & 展示5-6位
    if st_rank >= 5 and ex_rank >= 5:
        multiplier = min(multiplier, 0.60)
        applied_patterns.append(('st5_6_ex5_6_double_bottom', 0.60))

    return original_score * multiplier, multiplier, applied_patterns


def calculate_new_score(pre_rank, ex_rank, st_rank, original_score):
    """修正後のロジックでスコア調整"""
    multiplier = 1.0
    applied_patterns = []

    # 1着予測用パターン
    if pre_rank == 1:
        # 最強複合: PRE1位 & ST1位 & 展示1位
        if st_rank == 1 and ex_rank == 1:
            multiplier = max(multiplier, 1.50)
            applied_patterns.append(('pre1_st1_ex1', 1.50))
        # PRE1位 & ST1位
        elif st_rank == 1:
            multiplier = max(multiplier, 1.411)
            applied_patterns.append(('pre1_st1', 1.411))
        # ネガティブ: PRE1位 & ST6位
        if st_rank == 6:
            multiplier = min(multiplier, 0.53)
            applied_patterns.append(('pre1_st6', 0.53))
        # ネガティブ: PRE1位 & ST5位（修正後: 0.80）
        elif st_rank == 5:
            multiplier = min(multiplier, 0.80)
            applied_patterns.append(('pre1_st5_6', 0.80))
        # ネガティブ: PRE1位 & ST4位（修正後: 1.0 = 無効化）
        elif st_rank == 4:
            multiplier = min(multiplier, 1.0)
            applied_patterns.append(('pre1_st4_6', 1.0))
        # PRE1位 & 展示1位
        if ex_rank == 1:
            multiplier = max(multiplier, 1.286)
            applied_patterns.append(('pre1_ex1', 1.286))

    # 2着予測用パターン
    if pre_rank == 2:
        # PRE2位 & ST1-2位（強力）
        if st_rank <= 2:
            multiplier = max(multiplier, 1.12)
            applied_patterns.append(('pre2_st1_2', 1.12))

    # TOP3パターン
    # ST1-2位 & 展示1-2位（両方上位）
    if st_rank <= 2 and ex_rank <= 2:
        multiplier = max(multiplier, 1.35)
        applied_patterns.append(('st1_2_ex1_2_double_top', 1.35))

    # PRE1-3位 & ST1位（強力）
    if pre_rank <= 3 and st_rank == 1:
        multiplier = max(multiplier, 1.23)
        applied_patterns.append(('pre1_3_st1', 1.23))

    # ネガティブ: ST5-6位 & 展示5-6位
    if st_rank >= 5 and ex_rank >= 5:
        multiplier = min(multiplier, 0.60)
        applied_patterns.append(('st5_6_ex5_6_double_bottom', 0.60))

    return original_score * multiplier, multiplier, applied_patterns


def run_backtest():
    """バックテストを実行"""
    conn = get_db_connection()
    cursor = conn.cursor()

    print("=" * 80)
    print("パターン最適化修正の効果検証")
    print("=" * 80)
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("修正内容:")
    print("  1. pre1_st4_6: 0.70 → 1.0（無効化）- 理由: 誤ブロック率44.6%")
    print("  2. pre1_st5_6: 0.63 → 0.80（緩和）- 理由: 誤ブロック率40.7%")
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
    print()

    # 結果収集
    results = {
        'new': {'correct': 0, 'total': 0, 'top3_correct': 0},
        'old': {'correct': 0, 'total': 0, 'top3_correct': 0},
        'baseline': {'correct': 0, 'total': 0, 'top3_correct': 0}
    }

    # パターン別統計
    pattern_stats = defaultdict(lambda: {'applied': 0, 'correct': 0, 'total_mult': 0.0})

    # 信頼度別統計
    confidence_stats = {
        'new': defaultdict(lambda: {'correct': 0, 'total': 0}),
        'old': defaultdict(lambda: {'correct': 0, 'total': 0}),
        'baseline': defaultdict(lambda: {'correct': 0, 'total': 0})
    }

    # 会場別統計
    venue_stats = {
        'new': defaultdict(lambda: {'correct': 0, 'total': 0}),
        'old': defaultdict(lambda: {'correct': 0, 'total': 0})
    }

    # ネガティブパターンの効果（修正前・修正後）
    negative_pattern_effect = {
        'old': {
            'pre1_st6': {'blocked': 0, 'would_have_hit': 0},
            'pre1_st5_6': {'blocked': 0, 'would_have_hit': 0},
            'pre1_st4_6': {'blocked': 0, 'would_have_hit': 0},
            'st5_6_ex5_6_double_bottom': {'blocked': 0, 'would_have_hit': 0}
        },
        'new': {
            'pre1_st6': {'blocked': 0, 'would_have_hit': 0},
            'pre1_st5_6': {'blocked': 0, 'would_have_hit': 0},
            'pre1_st4_6': {'blocked': 0, 'would_have_hit': 0},
            'st5_6_ex5_6_double_bottom': {'blocked': 0, 'would_have_hit': 0}
        }
    }

    processed = 0

    for race_id, venue_code, race_date in races:
        # 予測を取得
        cursor.execute('''
            SELECT pit_number, total_score, confidence, rank_prediction
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'before'
            ORDER BY total_score DESC
        ''', (race_id,))
        predictions = cursor.fetchall()

        if not predictions or len(predictions) < 6:
            continue

        # 実際の結果（1着艇番）
        cursor.execute('''
            SELECT pit_number FROM results WHERE race_id = ? AND rank = '1'
        ''', (race_id,))
        result_row = cursor.fetchone()
        if not result_row:
            continue
        actual_first = result_row[0]

        # 3着以内の艇番を取得
        cursor.execute('''
            SELECT pit_number FROM results WHERE race_id = ? AND rank IN ('1', '2', '3')
        ''', (race_id,))
        top3_actual = [r[0] for r in cursor.fetchall()]

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

        # 信頼度を取得
        confidence = predictions[0][2] if predictions else 'D'

        # 信頼度A/Eはパターンをスキップ
        if confidence in ['A', 'E']:
            continue

        # ベースライン（パターンなし）の1着予測
        baseline_first_pred = predictions[0][0]

        # 予測順位マップを作成
        pred_sorted = sorted(predictions, key=lambda x: x[1], reverse=True)
        pre_rank_map = {p[0]: i+1 for i, p in enumerate(pred_sorted)}

        # 新ロジックでスコア再計算
        new_scores = []
        for pred in predictions:
            pit, score, conf, rank_pred = pred
            pre_rank = pre_rank_map.get(pit, 6)
            ex_rank = ex_rank_map.get(pit, 6)
            st_rank = st_rank_map.get(pit, 6)

            new_score, new_mult, new_patterns = calculate_new_score(pre_rank, ex_rank, st_rank, score)
            new_scores.append((pit, new_score, new_mult, new_patterns))

            # ネガティブパターンの効果チェック（新）
            for pattern_name, mult in new_patterns:
                if pattern_name in negative_pattern_effect['new']:
                    if pre_rank == 1:  # PRE1位だった艇に適用された場合
                        negative_pattern_effect['new'][pattern_name]['blocked'] += 1
                        if pit == actual_first:
                            negative_pattern_effect['new'][pattern_name]['would_have_hit'] += 1

        new_sorted = sorted(new_scores, key=lambda x: x[1], reverse=True)
        new_first_pred = new_sorted[0][0]
        new_top3_pred = [x[0] for x in new_sorted[:3]]

        # 旧ロジックでスコア再計算
        old_scores = []
        for pred in predictions:
            pit, score, conf, rank_pred = pred
            pre_rank = pre_rank_map.get(pit, 6)
            ex_rank = ex_rank_map.get(pit, 6)
            st_rank = st_rank_map.get(pit, 6)

            old_score, old_mult, old_patterns = calculate_old_score(pre_rank, ex_rank, st_rank, score)
            old_scores.append((pit, old_score, old_mult, old_patterns))

            # ネガティブパターンの効果チェック（旧）
            for pattern_name, mult in old_patterns:
                if pattern_name in negative_pattern_effect['old']:
                    if pre_rank == 1:
                        negative_pattern_effect['old'][pattern_name]['blocked'] += 1
                        if pit == actual_first:
                            negative_pattern_effect['old'][pattern_name]['would_have_hit'] += 1

            # パターン統計を更新
            for pattern_name, mult in old_patterns:
                pattern_stats[pattern_name]['applied'] += 1
                pattern_stats[pattern_name]['total_mult'] += mult

        old_sorted = sorted(old_scores, key=lambda x: x[1], reverse=True)
        old_first_pred = old_sorted[0][0]
        old_top3_pred = [x[0] for x in old_sorted[:3]]

        # 的中判定
        results['baseline']['total'] += 1
        results['new']['total'] += 1
        results['old']['total'] += 1

        confidence_stats['baseline'][confidence]['total'] += 1
        confidence_stats['new'][confidence]['total'] += 1
        confidence_stats['old'][confidence]['total'] += 1

        venue_stats['new'][venue_code]['total'] += 1
        venue_stats['old'][venue_code]['total'] += 1

        # 1着的中
        if baseline_first_pred == actual_first:
            results['baseline']['correct'] += 1
            confidence_stats['baseline'][confidence]['correct'] += 1

        if new_first_pred == actual_first:
            results['new']['correct'] += 1
            confidence_stats['new'][confidence]['correct'] += 1
            venue_stats['new'][venue_code]['correct'] += 1
            # パターン的中も記録
            for pattern_name, _ in new_sorted[0][3]:
                pattern_stats[pattern_name]['correct'] += 1

        if old_first_pred == actual_first:
            results['old']['correct'] += 1
            confidence_stats['old'][confidence]['correct'] += 1
            venue_stats['old'][venue_code]['correct'] += 1

        # 3着以内的中
        if baseline_first_pred in top3_actual:
            results['baseline']['top3_correct'] += 1
        if new_first_pred in top3_actual:
            results['new']['top3_correct'] += 1
        if old_first_pred in top3_actual:
            results['old']['top3_correct'] += 1

        processed += 1
        if processed % 1000 == 0:
            print(f"処理中... {processed}/{len(races)}")

    print(f"\n処理完了: {processed}レース")
    print()

    # === 結果出力 ===

    print("=" * 80)
    print("1. 全体的中率比較")
    print("=" * 80)

    for name, label in [('baseline', 'ベースライン（パターンなし）'),
                        ('old', '修正前ロジック'),
                        ('new', '修正後ロジック')]:
        total = results[name]['total']
        correct = results[name]['correct']
        top3 = results[name]['top3_correct']
        rate = (correct / total * 100) if total > 0 else 0
        top3_rate = (top3 / total * 100) if total > 0 else 0
        print(f"{label}:")
        print(f"  1着的中: {correct}/{total} ({rate:.2f}%)")
        print(f"  3着以内: {top3}/{total} ({top3_rate:.2f}%)")
        print()

    # 差分
    new_rate = (results['new']['correct'] / results['new']['total'] * 100)
    old_rate = (results['old']['correct'] / results['old']['total'] * 100)
    baseline_rate = (results['baseline']['correct'] / results['baseline']['total'] * 100)

    print(f"【重要】差分（修正後-修正前）: {new_rate - old_rate:+.2f}pt")
    print(f"       差分（修正後-ベースライン）: {new_rate - baseline_rate:+.2f}pt")
    print(f"       差分（修正前-ベースライン）: {old_rate - baseline_rate:+.2f}pt")
    print()

    # === ネガティブパターンの効果比較 ===

    print("=" * 80)
    print("2. ネガティブパターンの効果（修正前 vs 修正後）")
    print("=" * 80)

    for name in ['pre1_st6', 'pre1_st5_6', 'pre1_st4_6', 'st5_6_ex5_6_double_bottom']:
        old_stats = negative_pattern_effect['old'][name]
        new_stats = negative_pattern_effect['new'][name]

        print(f"{name}:")

        # 修正前
        old_blocked = old_stats['blocked']
        old_hit = old_stats['would_have_hit']
        old_miss_rate = old_hit / old_blocked * 100 if old_blocked > 0 else 0
        print(f"  修正前（倍率）:")
        if name == 'pre1_st4_6':
            print(f"    倍率: 0.70")
        elif name == 'pre1_st5_6':
            print(f"    倍率: 0.63")
        else:
            print(f"    倍率: 変更なし")
        print(f"    適用回数: {old_blocked}")
        print(f"    そのうち実際に1着だった: {old_hit} ({old_miss_rate:.1f}%)")
        print(f"    → 正しくブロックした: {old_blocked - old_hit} ({100 - old_miss_rate:.1f}%)")

        # 修正後
        new_blocked = new_stats['blocked']
        new_hit = new_stats['would_have_hit']
        new_miss_rate = new_hit / new_blocked * 100 if new_blocked > 0 else 0
        print(f"  修正後（倍率）:")
        if name == 'pre1_st4_6':
            print(f"    倍率: 1.0（無効化）")
        elif name == 'pre1_st5_6':
            print(f"    倍率: 0.80（緩和）")
        else:
            print(f"    倍率: 変更なし")
        print(f"    適用回数: {new_blocked}")
        print(f"    そのうち実際に1着だった: {new_hit} ({new_miss_rate:.1f}%)")
        print(f"    → 正しくブロックした: {new_blocked - new_hit} ({100 - new_miss_rate:.1f}%)")

        # 改善幅
        if old_blocked > 0 and new_blocked > 0:
            improvement = old_miss_rate - new_miss_rate
            print(f"  誤ブロック率の改善: {improvement:+.1f}pt （{old_miss_rate:.1f}% → {new_miss_rate:.1f}%）")

        print()

    # === パターン別効果 ===

    print("=" * 80)
    print("3. 主要パターンの効果維持確認")
    print("=" * 80)

    key_patterns = [
        'pre1_st1_ex1',
        'st1_2_ex1_2_double_top',
        'pre1_3_st1',
        'st5_6_ex5_6_double_bottom'
    ]

    for name in key_patterns:
        if name in pattern_stats:
            stats = pattern_stats[name]
            applied = stats['applied']
            correct = stats['correct']
            rate = (correct / applied * 100) if applied > 0 else 0
            avg_mult = stats['total_mult'] / applied if applied > 0 else 1.0

            # 期待値チェック
            if name == 'pre1_st1_ex1':
                expected = 65.0
                verdict = "良好" if rate >= expected else f"要確認（期待{expected}%以上）"
            elif name == 'st1_2_ex1_2_double_top':
                expected = 60.0
                verdict = "良好" if rate >= expected else f"要確認（期待{expected}%以上）"
            elif name == 'pre1_3_st1':
                expected = 50.0
                verdict = "良好" if rate >= expected else f"要確認（期待{expected}%以上）"
            else:
                verdict = "確認"

            print(f"  {name}:")
            print(f"    適用: {applied}回 | 的中: {correct}回 ({rate:.2f}%) | 平均倍率: {avg_mult:.3f}")
            print(f"    → {verdict}")
            print()

    # === 信頼度別効果 ===

    print("=" * 80)
    print("4. 信頼度別効果")
    print("=" * 80)

    confidence_results = []
    for conf in ['B', 'C', 'D']:
        new_stats = confidence_stats['new'][conf]
        old_stats = confidence_stats['old'][conf]
        base_stats = confidence_stats['baseline'][conf]

        if new_stats['total'] > 0:
            new_rate = new_stats['correct'] / new_stats['total'] * 100
            old_rate = old_stats['correct'] / old_stats['total'] * 100 if old_stats['total'] > 0 else 0
            base_rate = base_stats['correct'] / base_stats['total'] * 100 if base_stats['total'] > 0 else 0

            confidence_results.append({
                'confidence': conf,
                'new_correct': new_stats['correct'],
                'new_total': new_stats['total'],
                'new_rate': new_rate,
                'old_correct': old_stats['correct'],
                'old_total': old_stats['total'],
                'old_rate': old_rate,
                'base_rate': base_rate,
                'diff_vs_old': new_rate - old_rate,
                'diff_vs_base': new_rate - base_rate
            })

            print(f"  信頼度{conf}: n={new_stats['total']}")
            print(f"    修正後: {new_rate:.2f}%")
            print(f"    修正前: {old_rate:.2f}%")
            print(f"    ベースライン: {base_rate:.2f}%")
            print(f"    差分（修正後-修正前）: {new_rate - old_rate:+.2f}pt")
            print()

    # === 会場別効果（トップ10・ワースト5） ===

    print("=" * 80)
    print("5. 会場別効果（改善幅が大きい順トップ10・ワースト5）")
    print("=" * 80)

    venue_results = []
    for venue in venue_stats['new'].keys():
        new_stats = venue_stats['new'][venue]
        old_stats = venue_stats['old'][venue]

        if new_stats['total'] >= 50:  # 最低50レース以上
            new_rate = new_stats['correct'] / new_stats['total'] * 100
            old_rate = old_stats['correct'] / old_stats['total'] * 100 if old_stats['total'] > 0 else 0
            diff = new_rate - old_rate
            venue_results.append({
                'venue': venue,
                'new_correct': new_stats['correct'],
                'new_total': new_stats['total'],
                'new_rate': new_rate,
                'old_rate': old_rate,
                'diff': diff
            })

    venue_results.sort(key=lambda x: x['diff'], reverse=True)

    print("【改善トップ10】")
    for v in venue_results[:10]:
        print(f"  会場{v['venue']}: 修正後={v['new_rate']:.1f}% | 修正前={v['old_rate']:.1f}% | 差分={v['diff']:+.1f}pt (n={v['new_total']})")

    print()
    print("【悪化ワースト5】")
    for v in venue_results[-5:]:
        print(f"  会場{v['venue']}: 修正後={v['new_rate']:.1f}% | 修正前={v['old_rate']:.1f}% | 差分={v['diff']:+.1f}pt (n={v['new_total']})")

    print()

    # === 統計的有意性 ===

    print("=" * 80)
    print("6. 統計的有意性の検証")
    print("=" * 80)

    n1 = results['new']['total']
    n2 = results['old']['total']
    p1 = results['new']['correct'] / n1
    p2 = results['old']['correct'] / n2

    # プールされた比率
    p_pool = (results['new']['correct'] + results['old']['correct']) / (n1 + n2)

    # 標準誤差
    se = math.sqrt(p_pool * (1 - p_pool) * (1/n1 + 1/n2))

    if se > 0:
        z_score = (p1 - p2) / se

        # p値の近似計算
        p_value = 2 * (1 - 0.5 * (1 + math.erf(abs(z_score) / math.sqrt(2))))

        # 効果量（Cohen's h）
        phi1 = 2 * math.asin(math.sqrt(p1))
        phi2 = 2 * math.asin(math.sqrt(p2))
        cohens_h = abs(phi1 - phi2)

        effect_size = '大' if cohens_h >= 0.8 else ('中' if cohens_h >= 0.5 else ('小' if cohens_h >= 0.2 else '微小'))

        print(f"  サンプルサイズ: 修正後={n1}, 修正前={n2}")
        print(f"  1着的中率: 修正後={p1*100:.2f}%, 修正前={p2*100:.2f}%")
        print(f"  Z-Score: {z_score:.4f}")
        print(f"  p-value: {p_value:.4f}")
        print(f"  有意水準0.05: {'有意差あり' if p_value < 0.05 else '有意差なし'}")
        print(f"  Cohen's h: {cohens_h:.4f} ({effect_size})")

        # 95%信頼区間
        se_diff = math.sqrt(p1*(1-p1)/n1 + p2*(1-p2)/n2)
        ci_lower = (p1 - p2) - 1.96 * se_diff
        ci_upper = (p1 - p2) + 1.96 * se_diff
        print(f"  差分の95%信頼区間: [{ci_lower*100:.2f}%, {ci_upper*100:.2f}%]")

    print()

    # === 推奨事項 ===

    print("=" * 80)
    print("7. 実装の推奨事項")
    print("=" * 80)

    diff_vs_old = new_rate - old_rate

    if diff_vs_old >= 0.5:
        recommendation = "適用推奨"
        reason = "修正により的中率が+0.5pt以上改善しており、効果が認められる"
    elif diff_vs_old >= 0.0:
        recommendation = "適用可"
        reason = "修正により的中率が改善傾向にあり、悪影響はない"
    elif diff_vs_old >= -0.5:
        recommendation = "要検討"
        reason = "修正による改善幅が微小であり、さらなる調整を検討すべき"
    else:
        recommendation = "要再検討"
        reason = "修正により的中率が悪化しており、実装の見直しが必要"

    print(f"  推奨: {recommendation}")
    print(f"  理由: {reason}")
    print()

    # 個別パターンの推奨
    print("  個別パターンの評価:")
    print(f"    pre1_st4_6（無効化）: 誤ブロック率改善効果を確認")
    print(f"    pre1_st5_6（緩和）: 誤ブロック率改善効果を確認")
    print()

    # === ファイル出力 ===

    output_dir = project_root / 'temp' / 'pattern_verification'
    output_dir.mkdir(parents=True, exist_ok=True)

    # 信頼度別効果CSV
    confidence_csv = output_dir / 'confidence_effects_fix.csv'
    with open(confidence_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['confidence', 'new_correct', 'new_total', 'new_rate',
                                                'old_correct', 'old_total', 'old_rate', 'base_rate',
                                                'diff_vs_old', 'diff_vs_base'])
        writer.writeheader()
        writer.writerows(confidence_results)
    print(f"信頼度別効果: {confidence_csv}")

    # 会場別効果CSV
    venue_csv = output_dir / 'venue_effects_fix.csv'
    with open(venue_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['venue', 'new_correct', 'new_total', 'new_rate', 'old_rate', 'diff'])
        writer.writeheader()
        writer.writerows(venue_results)
    print(f"会場別効果: {venue_csv}")

    # ネガティブパターン効果CSV
    negative_csv = output_dir / 'negative_pattern_effects_fix.csv'
    with open(negative_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['pattern', 'version', 'multiplier', 'blocked', 'would_have_hit', 'miss_rate'])
        for name in ['pre1_st6', 'pre1_st5_6', 'pre1_st4_6', 'st5_6_ex5_6_double_bottom']:
            old_stats = negative_pattern_effect['old'][name]
            new_stats = negative_pattern_effect['new'][name]

            # 倍率を記録
            old_mult = '0.53' if name == 'pre1_st6' else ('0.63' if name == 'pre1_st5_6' else ('0.70' if name == 'pre1_st4_6' else '0.60'))
            new_mult = '0.53' if name == 'pre1_st6' else ('0.80' if name == 'pre1_st5_6' else ('1.0' if name == 'pre1_st4_6' else '0.60'))

            old_miss = old_stats['would_have_hit'] / old_stats['blocked'] * 100 if old_stats['blocked'] > 0 else 0
            new_miss = new_stats['would_have_hit'] / new_stats['blocked'] * 100 if new_stats['blocked'] > 0 else 0

            writer.writerow([name, 'old', old_mult, old_stats['blocked'], old_stats['would_have_hit'], f"{old_miss:.2f}"])
            writer.writerow([name, 'new', new_mult, new_stats['blocked'], new_stats['would_have_hit'], f"{new_miss:.2f}"])

    print(f"ネガティブパターン効果: {negative_csv}")

    conn.close()

    return {
        'results': results,
        'confidence_results': confidence_results,
        'venue_results': venue_results,
        'negative_pattern_effect': negative_pattern_effect,
        'recommendation': recommendation
    }


if __name__ == '__main__':
    results = run_backtest()
