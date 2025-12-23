# -*- coding: utf-8 -*-
"""直前情報パターンのバックテスト検証

抽出された法則性（パターン）を個別にバックテストし、
実際に55.5%以上の的中率を維持できるかを確認する。

フェーズ2: 個別バックテスト
- パターン1: PRE1位 & ST1位 (該当47レース, 85.11%, x1.411)
- パターン2: PRE1位 & 展示1位 (該当56レース, 64.29%, x1.286)
- パターン3: 展示1位のみ (該当194レース, 26.29%, x1.096)
- パターン4: PRE1位 & 展示1-3位 & ST1-3位 (該当87レース, 71.26%, x1.328)
- パターン5: PRE1位 & ST1-3位 (該当123レース, 68.29%, x1.310)
"""

import sys
import sqlite3
from pathlib import Path
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.analysis.race_predictor import RacePredictor


# パターン定義（抽出結果から）
PATTERNS = [
    {
        'name': 'pre1_st1',
        'description': 'PRE1位 & ST1位',
        'multiplier': 1.411,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank == 1,
    },
    {
        'name': 'pre1_ex1',
        'description': 'PRE1位 & 展示1位',
        'multiplier': 1.286,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and ex_rank == 1,
    },
    {
        'name': 'exhibition_rank_1',
        'description': '展示1位のみ',
        'multiplier': 1.096,
        'condition': lambda pre_rank, ex_rank, st_rank: ex_rank == 1,
    },
    {
        'name': 'pre1_ex1_3_st1_3',
        'description': 'PRE1位 & 展示1-3位 & ST1-3位',
        'multiplier': 1.328,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and ex_rank <= 3 and st_rank <= 3,
    },
    {
        'name': 'pre1_st1_3',
        'description': 'PRE1位 & ST1-3位',
        'multiplier': 1.310,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank <= 3,
    },
]


def validate_pattern(db_path, pattern, limit=200):
    """
    個別パターンのバックテスト検証

    Args:
        db_path: データベースパス
        pattern: パターン定義辞書
        limit: 検証するレース数

    Returns:
        dict: 検証結果
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 2025年で直前情報が存在するレースを取得
    cursor.execute('''
        SELECT DISTINCT r.id
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        AND rd.exhibition_time IS NOT NULL
        ORDER BY r.race_date, r.race_number
        LIMIT ?
    ''', (limit,))
    race_ids = [row[0] for row in cursor.fetchall()]

    predictor = RacePredictor(db_path)

    # ベースライン（PRE単独）の結果
    baseline_correct = 0
    baseline_total = 0

    # パターン適用後の結果
    pattern_correct = 0
    pattern_total = 0

    # パターン該当レースの統計
    pattern_applied_count = 0
    pattern_applied_correct = 0

    # 各レースを走査
    for race_id in race_ids:
        # レース内の全艇データを取得
        cursor.execute('''
            SELECT
                rd.pit_number,
                CAST(res.rank AS INTEGER) as finish_position,
                rd.exhibition_time,
                rd.st_time
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            WHERE rd.race_id = ?
            ORDER BY rd.pit_number
        ''', (race_id,))

        race_data = cursor.fetchall()

        if len(race_data) < 6:
            continue

        # 展示タイム順位を計算
        exhibition_times = [(row[0], row[2]) for row in race_data if row[2] is not None]
        if len(exhibition_times) >= 6:
            exhibition_times_sorted = sorted(exhibition_times, key=lambda x: x[1])
            exhibition_rank_map = {pit: rank+1 for rank, (pit, _) in enumerate(exhibition_times_sorted)}
        else:
            exhibition_rank_map = {}

        # ST順位を計算
        st_times = [(row[0], row[3]) for row in race_data if row[3] is not None]
        if len(st_times) >= 6:
            st_times_sorted = sorted(st_times, key=lambda x: abs(x[1]))
            st_rank_map = {pit: rank+1 for rank, (pit, _) in enumerate(st_times_sorted)}
        else:
            st_rank_map = {}

        # PRE予測を取得
        try:
            predictions = predictor.predict_race(race_id)
            if not predictions or len(predictions) < 6:
                continue
        except:
            continue

        # PRE順位マップ
        pre_rank_map = {pred['pit_number']: i+1 for i, pred in enumerate(predictions)}

        # 実際の1着艇を取得
        actual_winner = next((row[0] for row in race_data if row[1] == 1), None)
        if actual_winner is None:
            continue

        # ベースライン: PRE 1位が実際の1着か
        baseline_total += 1
        baseline_prediction = predictions[0]['pit_number']
        if baseline_prediction == actual_winner:
            baseline_correct += 1

        # パターン適用: 各艇にボーナスを適用してスコアを再計算
        adjusted_predictions = []
        for pred in predictions:
            pit_number = pred['pit_number']
            score = pred.get('total_score', 0.0)  # 'total_score'を使用

            pre_rank = pre_rank_map.get(pit_number)
            ex_rank = exhibition_rank_map.get(pit_number)
            st_rank = st_rank_map.get(pit_number)

            # パターン条件チェック
            pattern_applied = False
            if ex_rank is not None and st_rank is not None and pre_rank is not None:
                if pattern['condition'](pre_rank, ex_rank, st_rank):
                    score *= pattern['multiplier']
                    pattern_applied = True

            adjusted_predictions.append({
                'pit_number': pit_number,
                'score': score,
                'pattern_applied': pattern_applied
            })

        # スコアで再ソート
        adjusted_predictions.sort(key=lambda x: x['score'], reverse=True)

        # パターン適用後の1位予測
        pattern_total += 1
        pattern_prediction = adjusted_predictions[0]['pit_number']
        if pattern_prediction == actual_winner:
            pattern_correct += 1

        # パターンが適用されたレースかどうか
        if any(p['pattern_applied'] for p in adjusted_predictions):
            pattern_applied_count += 1
            if pattern_prediction == actual_winner:
                pattern_applied_correct += 1

    conn.close()

    # 結果を計算
    baseline_accuracy = baseline_correct / baseline_total * 100 if baseline_total > 0 else 0.0
    pattern_accuracy = pattern_correct / pattern_total * 100 if pattern_total > 0 else 0.0
    improvement = pattern_accuracy - baseline_accuracy

    pattern_applied_accuracy = (pattern_applied_correct / pattern_applied_count * 100
                                if pattern_applied_count > 0 else 0.0)

    return {
        'pattern_name': pattern['name'],
        'pattern_description': pattern['description'],
        'baseline_total': baseline_total,
        'baseline_correct': baseline_correct,
        'baseline_accuracy': baseline_accuracy,
        'pattern_total': pattern_total,
        'pattern_correct': pattern_correct,
        'pattern_accuracy': pattern_accuracy,
        'improvement': improvement,
        'pattern_applied_count': pattern_applied_count,
        'pattern_applied_correct': pattern_applied_correct,
        'pattern_applied_accuracy': pattern_applied_accuracy,
    }


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"
    limit = 200

    print("=" * 80)
    print("直前情報パターンのバックテスト検証")
    print("=" * 80)
    print()
    print(f"検証対象レース数: {limit}")
    print()

    # 各パターンを個別に検証
    results = []

    for pattern in PATTERNS:
        print(f"検証中: {pattern['description']} (ボーナス倍率: x{pattern['multiplier']:.3f})...")
        result = validate_pattern(db_path, pattern, limit)
        results.append(result)
        print(f"  完了")
        print()

    # 結果表示
    print("=" * 80)
    print("検証結果")
    print("=" * 80)
    print()

    # ベースライン表示
    if results:
        baseline_result = results[0]
        print(f"ベースライン (PRE単独):")
        print(f"  対象レース数: {baseline_result['baseline_total']}")
        print(f"  的中数: {baseline_result['baseline_correct']}")
        print(f"  的中率: {baseline_result['baseline_accuracy']:.2f}%")
        print()

    print("=" * 80)
    print("パターン別検証結果")
    print("=" * 80)
    print()

    for result in results:
        print(f"パターン: {result['pattern_description']}")
        print(f"  全体的中率: {result['pattern_accuracy']:.2f}% ({result['pattern_correct']}/{result['pattern_total']})")
        print(f"  改善度: {result['improvement']:+.2f}%")
        print(f"  パターン該当レース数: {result['pattern_applied_count']}")
        print(f"  パターン該当時的中率: {result['pattern_applied_accuracy']:.2f}% ({result['pattern_applied_correct']}/{result['pattern_applied_count']})")

        # 判定
        if result['pattern_accuracy'] >= 55.5:
            print(f"  判定: 採用推奨 (55.5%以上達成)")
        elif result['improvement'] >= 0:
            print(f"  判定: 悪化なし (改善度{result['improvement']:+.2f}%)")
        else:
            print(f"  判定: 不採用 (的中率悪化)")

        print()

    # サマリー
    print("=" * 80)
    print("サマリー")
    print("=" * 80)
    print()

    # 採用推奨パターン
    recommended = [r for r in results if r['pattern_accuracy'] >= 55.5]
    no_degradation = [r for r in results if r['improvement'] >= 0 and r['pattern_accuracy'] < 55.5]
    rejected = [r for r in results if r['improvement'] < 0]

    print(f"採用推奨 (55.5%以上): {len(recommended)}パターン")
    for r in recommended:
        print(f"  - {r['pattern_description']}: {r['pattern_accuracy']:.2f}% (改善度{r['improvement']:+.2f}%)")
    print()

    print(f"悪化なし (55.5%未満だが改善度0%以上): {len(no_degradation)}パターン")
    for r in no_degradation:
        print(f"  - {r['pattern_description']}: {r['pattern_accuracy']:.2f}% (改善度{r['improvement']:+.2f}%)")
    print()

    print(f"不採用 (的中率悪化): {len(rejected)}パターン")
    for r in rejected:
        print(f"  - {r['pattern_description']}: {r['pattern_accuracy']:.2f}% (改善度{r['improvement']:+.2f}%)")
    print()

    # 次のステップ
    print("=" * 80)
    print("次のステップ")
    print("=" * 80)
    print()

    if recommended:
        print("フェーズ3: 実装")
        print("以下のパターンを race_predictor.py に実装することを推奨:")
        print()
        for r in recommended:
            print(f"  - {r['pattern_description']}")
            print(f"    期待的中率: {r['pattern_accuracy']:.2f}%")
            print(f"    該当レース: {r['pattern_applied_count']}レース")
        print()
    else:
        print("採用推奨パターンなし")
        print("理由を分析し、以下を検討:")
        print("  1. ボーナス倍率の調整")
        print("  2. パターン条件の見直し")
        print("  3. 他のパターンの探索")
        print()


if __name__ == '__main__':
    main()
