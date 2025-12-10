#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
信頼度別パターン適用の統合テスト

実際のレースデータを使用して、信頼度別のパターン適用が正しく動作することを確認
"""

import sys
import os
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import sqlite3
from src.analysis.race_predictor import RacePredictor
from config.feature_flags import FEATURE_FLAGS


def test_real_race_confidence_patterns():
    """実レースデータで信頼度別パターン適用をテスト"""

    print("=" * 80)
    print("信頼度別パターン適用 統合テスト")
    print("=" * 80)
    print()

    # データベース接続
    db_path = os.path.join(project_root, 'data', 'boatrace.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 2025年の最新50レースを取得（BEFORE情報完備）
    cursor.execute("""
        SELECT r.id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= '2025-01-01'
          AND r.race_date < '2026-01-01'
          AND EXISTS (
              SELECT 1 FROM results res
              WHERE res.race_id = r.id AND res.rank IS NOT NULL
          )
          AND EXISTS (
              SELECT 1 FROM race_details rd
              WHERE rd.race_id = r.id
                AND rd.exhibition_time IS NOT NULL
                AND rd.st_time IS NOT NULL
          )
        ORDER BY r.race_date DESC, r.race_number DESC
        LIMIT 50
    """)

    races = cursor.fetchall()

    print(f"[テスト対象] {len(races)}レース\n")

    # 予測器初期化
    predictor = RacePredictor()

    # 信頼度別の統計
    confidence_stats = {
        'A': {'total': 0, 'pattern_applied': 0, 'pattern_skipped': 0},
        'B': {'total': 0, 'pattern_applied': 0, 'pattern_skipped': 0},
        'C': {'total': 0, 'pattern_applied': 0, 'pattern_skipped': 0},
        'D': {'total': 0, 'pattern_applied': 0, 'pattern_skipped': 0},
        'E': {'total': 0, 'pattern_applied': 0, 'pattern_skipped': 0},
    }

    test_cases = []

    for race_id, venue_code, race_date, race_number in races[:20]:  # 最初の20レースでテスト
        try:
            predictions = predictor.predict_race(race_id)

            if not predictions:
                continue

            top_pred = predictions[0]
            confidence = top_pred.get('confidence', 'C')
            integration_mode = top_pred.get('integration_mode', 'unknown')
            pattern_multiplier = top_pred.get('pattern_multiplier', 1.0)
            matched_patterns = top_pred.get('matched_patterns', [])

            # 統計更新
            if confidence in confidence_stats:
                confidence_stats[confidence]['total'] += 1

                if integration_mode.startswith('pattern_skipped'):
                    confidence_stats[confidence]['pattern_skipped'] += 1
                elif pattern_multiplier > 1.0 or matched_patterns:
                    confidence_stats[confidence]['pattern_applied'] += 1

            # テストケース記録
            test_cases.append({
                'race_id': race_id,
                'date': race_date,
                'venue': venue_code,
                'race_num': race_number,
                'confidence': confidence,
                'mode': integration_mode,
                'multiplier': pattern_multiplier,
                'patterns': len(matched_patterns)
            })

        except Exception as e:
            print(f"[警告] レース{race_id}でエラー: {e}")
            continue

    conn.close()

    # 結果表示
    print("=" * 80)
    print("【テスト結果】")
    print("=" * 80)
    print()

    # 信頼度別サマリー
    print("信頼度別パターン適用状況:")
    print("-" * 80)
    for conf in ['A', 'B', 'C', 'D', 'E']:
        stats = confidence_stats[conf]
        total = stats['total']
        applied = stats['pattern_applied']
        skipped = stats['pattern_skipped']

        if total > 0:
            apply_rate = 100 * applied / total
            skip_rate = 100 * skipped / total

            status = "✓ OK" if (
                (conf == 'A' and skip_rate >= 90) or
                (conf == 'E' and skip_rate >= 90) or
                (conf in ['B', 'C'] and apply_rate >= 80) or
                (conf == 'D' and skip_rate >= 80)  # フラグ無効時
            ) else "⚠ 要確認"

            print(f"信頼度{conf}: {total:2d}レース | "
                  f"適用:{applied:2d} ({apply_rate:5.1f}%) | "
                  f"スキップ:{skipped:2d} ({skip_rate:5.1f}%) | {status}")

    print()
    print("-" * 80)
    print()

    # 詳細ケース表示（最初の10件）
    print("【詳細ケース】（最初の10件）")
    print("-" * 80)
    print(f"{'日付':<12} {'会場':>4} {'R':>2} {'信頼度':>4} {'統合モード':<30} {'倍率':>6} {'パターン数':>4}")
    print("-" * 80)

    for case in test_cases[:10]:
        print(f"{case['date']:<12} {case['venue']:>4} {case['race_num']:>2} "
              f"{case['confidence']:>4} {case['mode']:<30} "
              f"{case['multiplier']:>6.3f} {case['patterns']:>4}")

    print()
    print("=" * 80)
    print("【検証項目】")
    print("=" * 80)
    print()

    # 検証項目チェック
    checks = []

    # 1. 信頼度Aでパターンがスキップされているか
    a_stats = confidence_stats['A']
    if a_stats['total'] > 0:
        a_skip_rate = 100 * a_stats['pattern_skipped'] / a_stats['total']
        check1 = a_skip_rate >= 90
        checks.append(("信頼度Aでパターンスキップ", check1, f"{a_skip_rate:.1f}%"))

    # 2. 信頼度Eでパターンがスキップされているか
    e_stats = confidence_stats['E']
    if e_stats['total'] > 0:
        e_skip_rate = 100 * e_stats['pattern_skipped'] / e_stats['total']
        check2 = e_skip_rate >= 90
        checks.append(("信頼度Eでパターンスキップ", check2, f"{e_skip_rate:.1f}%"))

    # 3. 信頼度Bでパターンが適用されているか
    b_stats = confidence_stats['B']
    if b_stats['total'] > 0:
        b_apply_rate = 100 * b_stats['pattern_applied'] / b_stats['total']
        check3 = b_apply_rate >= 80
        checks.append(("信頼度Bでパターン適用", check3, f"{b_apply_rate:.1f}%"))

    # 4. 信頼度Cでパターンが適用されているか
    c_stats = confidence_stats['C']
    if c_stats['total'] > 0:
        c_apply_rate = 100 * c_stats['pattern_applied'] / c_stats['total']
        check4 = c_apply_rate >= 80
        checks.append(("信頼度Cでパターン適用", check4, f"{c_apply_rate:.1f}%"))

    # 5. 信頼度D（フラグ無効）でパターンがスキップされているか
    d_stats = confidence_stats['D']
    flag_d_enabled = FEATURE_FLAGS.get('apply_pattern_to_confidence_d', False)
    if d_stats['total'] > 0:
        d_skip_rate = 100 * d_stats['pattern_skipped'] / d_stats['total']
        if not flag_d_enabled:
            check5 = d_skip_rate >= 80
            checks.append(("信頼度D（フラグ無効）でスキップ", check5, f"{d_skip_rate:.1f}%"))

    # チェック結果表示
    all_passed = True
    for check_name, passed, detail in checks:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {check_name} ({detail})")
        if not passed:
            all_passed = False

    print()
    print("=" * 80)

    if all_passed:
        print("✓ 統合テスト成功: 信頼度別パターン適用が正しく動作しています")
    else:
        print("⚠ 統合テスト警告: 一部の検証項目が期待値を満たしていません")

    print("=" * 80)
    print()

    return all_passed


if __name__ == "__main__":
    success = test_real_race_confidence_patterns()
    sys.exit(0 if success else 1)
