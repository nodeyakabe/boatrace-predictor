#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
展示タイム条件別加点ルールバックテスト

アプローチ:
1. 既存のrace_predictionsから信頼度A-Eのレースを取得
2. 各レースで展示タイム関連のバフルールを適用
3. バフ値を総合スコアに加算
4. 順位予測を更新して的中率を測定
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
from datetime import datetime
from collections import defaultdict

from src.analysis.compound_buff_system import CompoundBuffSystem
from src.analysis.exhibition_buff_rules import get_exhibition_buff_rules
from src.analysis.exhibition_context_builder import build_exhibition_context

DB_PATH = "data/boatrace.db"

# ベースライン（v2での精度）
BASELINE = {
    'A': {'total': 896, 'first_rate': 72.88, 'trifecta_rate': 10.22},
    'B': {'total': 5658, 'first_rate': 65.39, 'trifecta_rate': 9.06},
    'C': {'total': 8451, 'first_rate': 46.27, 'trifecta_rate': 5.86},
    'D': {'total': 2067, 'first_rate': 33.62, 'trifecta_rate': 3.90},
    'E': {'total': 72, 'first_rate': 34.72, 'trifecta_rate': 4.17}
}

def get_race_base_context(race_id, pit_number):
    """レースの基本コンテキスト取得"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            r.venue_code,
            rd.actual_course,
            e.racer_rank,
            rd.st_time
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id AND rd.pit_number = ?
        JOIN entries e ON rd.race_id = e.race_id AND rd.pit_number = ?
        WHERE r.id = ?
    """, (pit_number, pit_number, race_id))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return {}

    venue_code, course, racer_rank, st_time = row

    context = {
        'venue': venue_code,
        'course': course,
        'racer_rank': racer_rank,
    }

    # ST評価
    if st_time is not None:
        if st_time <= 0.15:
            context['start_timing'] = 'good'
        elif st_time <= 0.20:
            context['start_timing'] = 'normal'
        else:
            context['start_timing'] = 'poor'

    return context

def apply_exhibition_buffs(race_id, pit_number, buff_system):
    """展示タイムバフを計算"""
    # 基本コンテキスト
    context = get_race_base_context(race_id, pit_number)

    # 展示コンテキスト追加
    exh_context = build_exhibition_context(race_id, pit_number)
    context.update(exh_context)

    # バフルール適用
    total_buff = 0.0
    applied_rules = []

    for rule in buff_system.rules:
        buff_value = rule.get_applied_buff(context)
        if buff_value is not None:
            total_buff += buff_value
            applied_rules.append((rule.rule_id, buff_value))

    return total_buff, applied_rules, context

def main():
    # UTF-8出力設定
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("=" * 80)
    print("展示タイム条件別加点ルールバックテスト")
    print("=" * 80)
    print()
    print("方法: 展示タイム関連の条件別加点ルールを適用")
    print("対象期間: 2025年1月1日～12月31日")
    print()

    # バフシステム初期化
    buff_system = CompoundBuffSystem()

    # 展示タイムルールを追加
    exhibition_rules = get_exhibition_buff_rules()
    buff_system.rules.extend(exhibition_rules)

    print(f"展示タイムルール数: {len(exhibition_rules)}")
    print()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("[1/3] 予測データ取得中...")

    # 信頼度別のレースリスト取得
    cursor.execute("""
        SELECT DISTINCT
            rp.race_id,
            rp.confidence
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        AND rp.prediction_type = 'advance'
        AND rp.rank_prediction = 1
        ORDER BY r.race_date, rp.race_id
        LIMIT 1000
    """)

    race_confidences = {}
    for row in cursor.fetchall():
        race_id, confidence = row
        race_confidences[race_id] = confidence

    print(f"OK {len(race_confidences)}レース取得完了")
    print()

    print("[2/3] 展示バフ適用と予測更新中...")

    confidence_stats = defaultdict(lambda: {
        'total': 0,
        'v2_first_correct': 0,
        'v3_first_correct': 0,
        'total_buff_applied': 0.0,
        'buff_count': 0,
        'v2_correct_v3_wrong': 0,  # v2的中→v3外れ（改悪）
        'v2_wrong_v3_correct': 0,  # v2外れ→v3的中（改善）
        'rule_application_count': defaultdict(int),  # ルール別適用回数
        'rule_impact_negative': defaultdict(int),  # ルール別改悪回数
        'rule_impact_positive': defaultdict(int)   # ルール別改善回数
    })

    processed = 0
    for race_id, confidence in race_confidences.items():
        processed += 1
        if processed % 100 == 0:
            print(f"  処理中: {processed}/{len(race_confidences)}")

        # 元の予測取得
        cursor.execute("""
            SELECT
                rp.pit_number,
                rp.total_score,
                res.rank as finish_rank
            FROM race_predictions rp
            LEFT JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
            WHERE rp.race_id = ?
            AND rp.prediction_type = 'advance'
            ORDER BY rp.pit_number
        """, (race_id,))

        predictions = []
        for row in cursor.fetchall():
            pit, v2_total_score, finish_rank = row

            # 展示バフ適用
            buff_value, applied_rules, context = apply_exhibition_buffs(race_id, pit, buff_system)

            # v3総合スコア = v2総合スコア + 展示バフ
            v3_total_score = v2_total_score + buff_value

            predictions.append({
                'pit': pit,
                'v2_total_score': v2_total_score,
                'v3_total_score': v3_total_score,
                'buff_value': buff_value,
                'finish_rank': int(finish_rank) if finish_rank else None,
                'applied_rules': applied_rules,
                'context': context
            })

            # バフ統計
            if buff_value != 0:
                confidence_stats[confidence]['total_buff_applied'] += abs(buff_value)
                confidence_stats[confidence]['buff_count'] += 1

        if len(predictions) != 6:
            continue

        # v2予測（元の順位）
        v2_sorted = sorted(predictions, key=lambda x: x['v2_total_score'], reverse=True)
        v2_predicted_pit = v2_sorted[0]['pit']

        # v3予測（展示バフ適用後）
        v3_sorted = sorted(predictions, key=lambda x: x['v3_total_score'], reverse=True)
        v3_predicted_pit = v3_sorted[0]['pit']

        # 実際の1着
        actual_winner_pit = next((p['pit'] for p in predictions if p['finish_rank'] == 1), None)

        # 統計更新
        confidence_stats[confidence]['total'] += 1

        v2_correct = (v2_predicted_pit == actual_winner_pit)
        v3_correct = (v3_predicted_pit == actual_winner_pit)

        if v2_correct:
            confidence_stats[confidence]['v2_first_correct'] += 1
        if v3_correct:
            confidence_stats[confidence]['v3_first_correct'] += 1

        # 改善・改悪パターンの記録
        if v2_correct and not v3_correct:
            # v2的中→v3外れ（改悪）
            confidence_stats[confidence]['v2_correct_v3_wrong'] += 1

            # どのルールが原因かを特定
            for p in predictions:
                if len(p['applied_rules']) > 0:
                    for rule_id, buff_val in p['applied_rules']:
                        confidence_stats[confidence]['rule_impact_negative'][rule_id] += 1

        elif not v2_correct and v3_correct:
            # v2外れ→v3的中（改善）
            confidence_stats[confidence]['v2_wrong_v3_correct'] += 1

            # どのルールが原因かを特定
            for p in predictions:
                if len(p['applied_rules']) > 0:
                    for rule_id, buff_val in p['applied_rules']:
                        confidence_stats[confidence]['rule_impact_positive'][rule_id] += 1

        # ルール適用回数の記録
        for p in predictions:
            for rule_id, buff_val in p['applied_rules']:
                confidence_stats[confidence]['rule_application_count'][rule_id] += 1

    print(f"OK {processed}レース処理完了")
    print()

    print("[3/3] 結果集計...")

    # 的中率計算
    results = {}
    for conf, stats in confidence_stats.items():
        total = stats['total']
        if total > 0:
            results[conf] = {
                'total': total,
                'v2_first_rate': stats['v2_first_correct'] / total * 100,
                'v3_first_rate': stats['v3_first_correct'] / total * 100,
                'avg_buff': stats['total_buff_applied'] / max(1, stats['buff_count'])
            }

    print()
    print("=" * 80)
    print("【バックテスト結果】")
    print("=" * 80)
    print()

    print(f"{'信頼度':<8} {'レース数':>10} {'v2的中率':>12} {'v3的中率':>12} {'改善幅':>10} {'平均バフ':>10}")
    print("-" * 80)

    total_improvement = 0
    valid_confidences = 0

    for conf in ['A', 'B', 'C', 'D', 'E']:
        if conf in results:
            stat = results[conf]
            improvement = stat['v3_first_rate'] - stat['v2_first_rate']

            print(f"{conf:<8} {stat['total']:>10} "
                  f"{stat['v2_first_rate']:>11.2f}% "
                  f"{stat['v3_first_rate']:>11.2f}% "
                  f"{improvement:>9.2f}pt "
                  f"{stat['avg_buff']:>9.2f}pt")

            total_improvement += improvement
            valid_confidences += 1
        else:
            print(f"{conf:<8} {'N/A':>10} {'N/A':>12} {'N/A':>12} {'N/A':>10} {'N/A':>10}")

    print()
    print("=" * 80)
    print("【総合評価】")
    print("=" * 80)

    if valid_confidences > 0:
        avg_improvement = total_improvement / valid_confidences

        print(f"平均改善幅: {avg_improvement:+.2f}pt")
        print()

        if avg_improvement > 3.0:
            print("[評価] ★★★ 大幅改善 - 展示タイム条件別加点の本番導入を強く推奨")
        elif avg_improvement > 1.0:
            print("[評価] ★★☆ 明確な改善 - 展示タイム条件別加点の本番導入を推奨")
        elif avg_improvement > 0:
            print("[評価] ★☆☆ 小幅改善 - 展示タイム条件別加点の導入を検討")
        else:
            print("[評価] ☆☆☆ 改善なし - 現状維持")

        print()
        print("【特記事項】")

        # 信頼度A・Bの改善状況
        if 'A' in results and 'B' in results:
            a_improvement = results['A']['v3_first_rate'] - results['A']['v2_first_rate']
            b_improvement = results['B']['v3_first_rate'] - results['B']['v2_first_rate']

            print(f"- 信頼度A改善: {a_improvement:+.2f}pt")
            print(f"- 信頼度B改善: {b_improvement:+.2f}pt")

            if a_improvement > 0 and b_improvement > 0:
                print("- 主力信頼度（A・B）で改善確認 → ROI向上が期待できる")

    print()
    print("=" * 80)
    print("【詳細分析: 信頼度B】")
    print("=" * 80)

    if 'B' in confidence_stats:
        b_stats = confidence_stats['B']
        print(f"信頼度B レース数: {b_stats['total']}")
        print(f"v2的中→v3外れ（改悪）: {b_stats['v2_correct_v3_wrong']} レース")
        print(f"v2外れ→v3的中（改善）: {b_stats['v2_wrong_v3_correct']} レース")
        print(f"純粋な改悪数: {b_stats['v2_correct_v3_wrong'] - b_stats['v2_wrong_v3_correct']}")
        print()

        print("【ルール別影響分析（信頼度B）】")
        print(f"{'ルールID':<35} {'適用回数':>10} {'改善':>8} {'改悪':>8} {'純効果':>8}")
        print("-" * 80)

        all_rules = set(b_stats['rule_application_count'].keys())
        all_rules.update(b_stats['rule_impact_positive'].keys())
        all_rules.update(b_stats['rule_impact_negative'].keys())

        rule_impacts = []
        for rule_id in all_rules:
            count = b_stats['rule_application_count'][rule_id]
            positive = b_stats['rule_impact_positive'][rule_id]
            negative = b_stats['rule_impact_negative'][rule_id]
            net = positive - negative
            rule_impacts.append((rule_id, count, positive, negative, net))

        # 純効果でソート（改悪が多い順）
        rule_impacts.sort(key=lambda x: x[4])

        for rule_id, count, positive, negative, net in rule_impacts:
            print(f"{rule_id:<35} {count:>10} {positive:>8} {negative:>8} {net:>+8}")

    print()
    print("=" * 80)

    conn.close()

if __name__ == '__main__':
    main()
