"""
重み配分最適化バックテスト

複数の重み配分パターンで精度を比較
"""

import sqlite3
import sys
from src.analysis.race_predictor import RacePredictor
from src.analysis.dynamic_integration import DynamicIntegrator

def test_weight_pattern(pre_weight, before_weight, test_races, conn):
    """指定された重み配分でバックテストを実施"""

    # DynamicIntegratorの重みを一時的に変更
    integrator = DynamicIntegrator()
    original_pre = integrator.DEFAULT_PRE_WEIGHT
    original_before = integrator.DEFAULT_BEFORE_WEIGHT

    # クラス定数を変更（注意: 全インスタンスに影響）
    DynamicIntegrator.DEFAULT_PRE_WEIGHT = pre_weight
    DynamicIntegrator.DEFAULT_BEFORE_WEIGHT = before_weight

    predictor = RacePredictor(db_path='data/boatrace.db')
    predictor.dynamic_integrator = integrator

    cursor = conn.cursor()

    # 統計
    integrated_win = 0
    pre_only_win = 0
    total = 0
    errors = 0
    different_predictions = 0

    for race_id, race_date, venue, race_no in test_races:
        try:
            # 実際の結果
            cursor.execute("""
                SELECT pit_number FROM results
                WHERE race_id = ? AND rank = 1 AND is_invalid = 0
            """, (race_id,))
            result = cursor.fetchone()
            if not result:
                continue
            actual_winner = result[0]

            # 統合スコアで予測
            predictions = predictor.predict_race(race_id)
            if not predictions or len(predictions) == 0:
                errors += 1
                continue

            integrated_pred = predictions[0]['pit_number']

            # PRE単体での予測
            pre_only = sorted(predictions, key=lambda x: x.get('pre_score', 0), reverse=True)
            pre_pred = pre_only[0]['pit_number']

            # 予測が異なる場合をカウント
            if integrated_pred != pre_pred:
                different_predictions += 1

            # 的中判定
            if integrated_pred == actual_winner:
                integrated_win += 1
            if pre_pred == actual_winner:
                pre_only_win += 1

            total += 1

        except Exception as e:
            errors += 1
            continue

    # 重みを元に戻す
    DynamicIntegrator.DEFAULT_PRE_WEIGHT = original_pre
    DynamicIntegrator.DEFAULT_BEFORE_WEIGHT = original_before

    return {
        'total': total,
        'integrated_win': integrated_win,
        'pre_only_win': pre_only_win,
        'errors': errors,
        'different_predictions': different_predictions,
        'integrated_rate': (integrated_win / total * 100) if total > 0 else 0,
        'pre_rate': (pre_only_win / total * 100) if total > 0 else 0,
        'diff': ((integrated_win - pre_only_win) / total * 100) if total > 0 else 0
    }

def main():
    print("=" * 80)
    print("重み配分最適化バックテスト")
    print("=" * 80)
    print()

    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    # 最新200レース取得
    cursor.execute("""
        SELECT r.id, r.race_date, r.venue_code, r.race_number
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        JOIN results res ON r.id = res.race_id
        WHERE rd.exhibition_course IS NOT NULL
        AND res.rank IS NOT NULL
        AND res.is_invalid = 0
        ORDER BY r.race_date DESC, r.id DESC
        LIMIT 200
    """)
    test_races = cursor.fetchall()

    print(f"テスト対象: {len(test_races)}レース")
    print()

    # テストする重み配分パターン
    weight_patterns = [
        (0.85, 0.15, "現在の設定（保守的）"),
        (0.70, 0.30, "バランス重視"),
        (0.60, 0.40, "直前情報重視"),
        (0.50, 0.50, "均等配分")
    ]

    results = []

    for pre_w, before_w, description in weight_patterns:
        print(f"テスト中: PRE {int(pre_w*100)}% / BEFORE {int(before_w*100)}% ({description})")
        result = test_weight_pattern(pre_w, before_w, test_races, conn)
        result['pre_weight'] = pre_w
        result['before_weight'] = before_w
        result['description'] = description
        results.append(result)

        print(f"  統合予測: {result['integrated_win']}/{result['total']} ({result['integrated_rate']:.2f}%)")
        print(f"  PRE単体: {result['pre_only_win']}/{result['total']} ({result['pre_rate']:.2f}%)")
        print(f"  差分: {result['diff']:+.2f}ポイント")
        print(f"  予測変化: {result['different_predictions']}レース ({result['different_predictions']/result['total']*100:.1f}%)")
        print()

    conn.close()

    print("=" * 80)
    print("結果サマリー")
    print("=" * 80)
    print()

    # 最良の設定を特定
    best = max(results, key=lambda x: x['integrated_rate'])

    print("【全パターン比較】")
    print(f"{'設定':<25} | {'統合的中率':>10} | {'PRE的中率':>10} | {'差分':>8} | {'予測変化':>8}")
    print("-" * 80)

    for r in results:
        setting = f"PRE {int(r['pre_weight']*100)}% / BEFORE {int(r['before_weight']*100)}%"
        print(f"{setting:<25} | {r['integrated_rate']:>9.2f}% | {r['pre_rate']:>9.2f}% | {r['diff']:>+7.2f}% | {r['different_predictions']:>7}件")

    print()
    print(f"【最良の設定】")
    print(f"PRE {int(best['pre_weight']*100)}% / BEFORE {int(best['before_weight']*100)}%")
    print(f"的中率: {best['integrated_rate']:.2f}%")
    print(f"改善幅: {best['diff']:+.2f}ポイント")
    print()

    # 推奨判定
    if best['diff'] > 1.0:
        print("推奨: 最良の設定に変更すべき（+1.0%以上の改善）")
    elif best['diff'] > 0.5:
        print("推奨: 最良の設定に変更を検討（+0.5%以上の改善）")
    elif best['diff'] > 0:
        print("判定: 現状維持を推奨（改善幅が小さい）")
    else:
        print("判定: 現在の設定が最良")

    print()
    print("=" * 80)

if __name__ == "__main__":
    main()
