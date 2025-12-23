# -*- coding: utf-8 -*-
"""BEFORE_SCORE逆相関問題の原因調査

直前情報スコアが予測精度に与える影響を詳細に分析し、
なぜ的中率4.1%という逆相関が発生したのかを解明する
"""

import sys
import sqlite3
from pathlib import Path
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.analysis.race_predictor import RacePredictor
from config.feature_flags import FEATURE_FLAGS


def analyze_beforeinfo_impact(db_path, race_ids, flag_setting):
    """
    指定されたfeature_flag設定で予測精度を検証

    Args:
        db_path: データベースパス
        race_ids: 検証するレースIDリスト
        flag_setting: feature_flags設定 ('disabled', 'before_safe', 'dynamic')

    Returns:
        dict: 検証結果
    """
    # feature_flagsを一時的に変更
    original_dynamic = FEATURE_FLAGS['dynamic_integration']
    original_safe = FEATURE_FLAGS['before_safe_integration']

    if flag_setting == 'disabled':
        FEATURE_FLAGS['dynamic_integration'] = False
        FEATURE_FLAGS['before_safe_integration'] = False
    elif flag_setting == 'before_safe':
        FEATURE_FLAGS['dynamic_integration'] = False
        FEATURE_FLAGS['before_safe_integration'] = True
    elif flag_setting == 'dynamic':
        FEATURE_FLAGS['dynamic_integration'] = True
        FEATURE_FLAGS['before_safe_integration'] = False

    predictor = RacePredictor(db_path, use_cache=False)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    stats = {
        'total': 0,
        'hit_1st': 0,
        'hit_3rd': 0,
        'score_diff': [],  # 1着艇と予測1位のスコア差
        'beforeinfo_score_1st': [],  # 1着艇のBEFOREスコア
        'beforeinfo_score_pred1': [],  # 予測1位のBEFOREスコア
    }

    for race_id in race_ids:
        # 予測実行
        try:
            predictions = predictor.predict_race(race_id)
        except Exception as e:
            continue

        if not predictions or len(predictions) < 6:
            continue

        # 実際の結果取得
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank = 1
        ''', (race_id,))
        result = cursor.fetchone()

        if not result:
            continue

        actual_winner = result['pit_number']
        pred_winner = predictions[0]['pit_number']

        stats['total'] += 1

        # 1着的中
        if actual_winner == pred_winner:
            stats['hit_1st'] += 1

        # 3着以内的中
        pred_top3 = [p['pit_number'] for p in predictions[:3]]
        if actual_winner in pred_top3:
            stats['hit_3rd'] += 1

        # スコア差分析
        actual_pred = next((p for p in predictions if p['pit_number'] == actual_winner), None)
        if actual_pred:
            score_diff = predictions[0]['total_score'] - actual_pred['total_score']
            stats['score_diff'].append(score_diff)

            # BEFOREスコア記録
            if 'beforeinfo_score' in actual_pred:
                stats['beforeinfo_score_1st'].append(actual_pred['beforeinfo_score'])
            if 'beforeinfo_score' in predictions[0]:
                stats['beforeinfo_score_pred1'].append(predictions[0]['beforeinfo_score'])

    conn.close()

    # feature_flagsを元に戻す
    FEATURE_FLAGS['dynamic_integration'] = original_dynamic
    FEATURE_FLAGS['before_safe_integration'] = original_safe

    # 結果計算
    if stats['total'] > 0:
        stats['hit_rate_1st'] = stats['hit_1st'] / stats['total'] * 100
        stats['hit_rate_3rd'] = stats['hit_3rd'] / stats['total'] * 100

        if stats['score_diff']:
            stats['avg_score_diff'] = sum(stats['score_diff']) / len(stats['score_diff'])

        if stats['beforeinfo_score_1st']:
            stats['avg_before_1st'] = sum(stats['beforeinfo_score_1st']) / len(stats['beforeinfo_score_1st'])
        if stats['beforeinfo_score_pred1']:
            stats['avg_before_pred1'] = sum(stats['beforeinfo_score_pred1']) / len(stats['beforeinfo_score_pred1'])

    return stats


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=" * 80)
    print("BEFORE_SCORE逆相関問題の原因調査")
    print("=" * 80)
    print()

    # 2025年で直前情報が存在するレースを抽出
    print("データ収集中...")
    cursor.execute('''
        SELECT DISTINCT r.id
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        AND rd.exhibition_time IS NOT NULL
        ORDER BY r.race_date, r.race_number
        LIMIT 500
    ''')
    race_ids = [row['id'] for row in cursor.fetchall()]

    print(f"検証レース数: {len(race_ids)}")
    print()

    conn.close()

    if len(race_ids) < 10:
        print("[NG] 直前情報付きレースが不足（{len(race_ids)}件）")
        print("検証には最低10レース必要です")
        return

    # 3パターンで検証
    print("=" * 80)
    print("パターン1: BEFORE完全無効（現在の運用）")
    print("=" * 80)

    stats_disabled = analyze_beforeinfo_impact(db_path, race_ids, 'disabled')

    print(f"検証レース: {stats_disabled['total']}")
    print(f"1着的中率: {stats_disabled.get('hit_rate_1st', 0):.1f}%")
    print(f"3着以内的中率: {stats_disabled.get('hit_rate_3rd', 0):.1f}%")
    print()

    print("=" * 80)
    print("パターン2: BEFORE_SAFE有効（進入コース + 部品交換のみ）")
    print("=" * 80)

    stats_safe = analyze_beforeinfo_impact(db_path, race_ids, 'before_safe')

    print(f"検証レース: {stats_safe['total']}")
    print(f"1着的中率: {stats_safe.get('hit_rate_1st', 0):.1f}%")
    print(f"3着以内的中率: {stats_safe.get('hit_rate_3rd', 0):.1f}%")

    if 'avg_before_1st' in stats_safe:
        print(f"1着艇の平均BEFOREスコア: {stats_safe['avg_before_1st']:.1f}")
        print(f"予測1位の平均BEFOREスコア: {stats_safe.get('avg_before_pred1', 0):.1f}")
    print()

    print("=" * 80)
    print("パターン3: 動的統合有効（フルBEFORE: 展示タイム + ST含む）")
    print("=" * 80)

    stats_dynamic = analyze_beforeinfo_impact(db_path, race_ids, 'dynamic')

    print(f"検証レース: {stats_dynamic['total']}")
    print(f"1着的中率: {stats_dynamic.get('hit_rate_1st', 0):.1f}%")
    print(f"3着以内的中率: {stats_dynamic.get('hit_rate_3rd', 0):.1f}%")

    if 'avg_before_1st' in stats_dynamic:
        print(f"1着艇の平均BEFOREスコア: {stats_dynamic['avg_before_1st']:.1f}")
        print(f"予測1位の平均BEFOREスコア: {stats_dynamic.get('avg_before_pred1', 0):.1f}")
    print()

    # 比較分析
    print("=" * 80)
    print("比較分析")
    print("=" * 80)
    print()

    print("1着的中率の比較:")
    print(f"  BEFORE無効: {stats_disabled.get('hit_rate_1st', 0):5.1f}% (ベースライン)")
    print(f"  BEFORE_SAFE: {stats_safe.get('hit_rate_1st', 0):5.1f}% (差分: {stats_safe.get('hit_rate_1st', 0) - stats_disabled.get('hit_rate_1st', 0):+.1f}%)")
    print(f"  動的統合: {stats_dynamic.get('hit_rate_1st', 0):5.1f}% (差分: {stats_dynamic.get('hit_rate_1st', 0) - stats_disabled.get('hit_rate_1st', 0):+.1f}%)")
    print()

    print("3着以内的中率の比較:")
    print(f"  BEFORE無効: {stats_disabled.get('hit_rate_3rd', 0):5.1f}%")
    print(f"  BEFORE_SAFE: {stats_safe.get('hit_rate_3rd', 0):5.1f}% (差分: {stats_safe.get('hit_rate_3rd', 0) - stats_disabled.get('hit_rate_3rd', 0):+.1f}%)")
    print(f"  動的統合: {stats_dynamic.get('hit_rate_3rd', 0):5.1f}% (差分: {stats_dynamic.get('hit_rate_3rd', 0) - stats_disabled.get('hit_rate_3rd', 0):+.1f}%)")
    print()

    # 判定
    print("=" * 80)
    print("結論")
    print("=" * 80)
    print()

    best_mode = 'BEFORE無効'
    best_rate = stats_disabled.get('hit_rate_1st', 0)

    if stats_safe.get('hit_rate_1st', 0) > best_rate:
        best_mode = 'BEFORE_SAFE'
        best_rate = stats_safe.get('hit_rate_1st', 0)

    if stats_dynamic.get('hit_rate_1st', 0) > best_rate:
        best_mode = '動的統合'
        best_rate = stats_dynamic.get('hit_rate_1st', 0)

    print(f"最良モード: {best_mode} (1着的中率: {best_rate:.1f}%)")
    print()

    # 逆相関の診断
    if 'avg_before_1st' in stats_dynamic and 'avg_before_pred1' in stats_dynamic:
        before_diff = stats_dynamic['avg_before_1st'] - stats_dynamic['avg_before_pred1']

        print("逆相関診断:")
        if before_diff < -2.0:
            print(f"  [警告] 逆相関検出: 1着艇のBEFOREスコアが予測1位より{abs(before_diff):.1f}点低い")
            print("  → BEFOREスコアが高い艇ほど負ける傾向")
            print()
            print("推定原因:")
            print("  1. 展示タイム・STのスコアリングロジックが不適切")
            print("  2. 直前情報の解釈が逆（例: 展示タイム遅い = スタート重視 = 有利）")
            print("  3. 進入コース変更による混乱（枠なり前提のスコアが実際と不一致）")
        elif before_diff > 2.0:
            print(f"  [OK] 正相関: 1着艇のBEFOREスコアが予測1位より{before_diff:.1f}点高い")
            print("  → BEFOREスコアは有効に機能している")
        else:
            print(f"  [注意] 相関弱い: BEFOREスコア差分{before_diff:+.1f}点（ほぼ無相関）")
            print("  → BEFOREスコアは予測精度にほとんど寄与していない")

    print()
    print("=" * 80)
    print("推奨アクション")
    print("=" * 80)
    print()

    if best_mode == 'BEFORE無効':
        print("[現状維持推奨] 直前情報は精度向上に寄与していない")
        print()
        print("次のステップ:")
        print("  1. BeforeInfoScorerのロジック見直し（特に展示タイム・ST）")
        print("  2. 進入コース実績との整合性確認")
        print("  3. 個別項目の相関分析（展示タイム単体、ST単体など）")
    elif best_mode == 'BEFORE_SAFE':
        print(f"[BEFORE_SAFE推奨] 的中率が{stats_safe.get('hit_rate_1st', 0) - stats_disabled.get('hit_rate_1st', 0):+.1f}%向上")
        print()
        print("ただし、展示タイム・STは未使用のまま")
        print("次のステップ:")
        print("  1. feature_flags: before_safe_integration = True (既に設定済み)")
        print("  2. 展示タイム・STの個別検証")
    else:
        print(f"[動的統合推奨] 的中率が{stats_dynamic.get('hit_rate_1st', 0) - stats_disabled.get('hit_rate_1st', 0):+.1f}%向上")
        print()
        print("次のステップ:")
        print("  1. feature_flags: dynamic_integration = True に変更")
        print("  2. 本番運用で1ヶ月テスト")
        print("  3. ROI・収支への影響を測定")

    print()
    print("=" * 80)


if __name__ == '__main__':
    main()
