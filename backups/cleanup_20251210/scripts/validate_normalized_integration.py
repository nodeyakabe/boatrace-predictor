# -*- coding: utf-8 -*-
"""正規化統合の効果検証

BEFORE無効 vs 正規化統合の的中率・ROIを比較し、
実際に改善が得られるかを検証する
"""

import sys
import sqlite3
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.analysis.race_predictor import RacePredictor
from config.feature_flags import FEATURE_FLAGS


def validate_with_flag_setting(db_path, race_ids, use_normalized):
    """
    指定されたフラグ設定で予測精度を検証

    Args:
        db_path: データベースパス
        race_ids: 検証するレースIDリスト
        use_normalized: 正規化統合を使用するか

    Returns:
        dict: 検証結果
    """
    # feature_flagsを一時的に変更
    original = FEATURE_FLAGS['normalized_before_integration']
    FEATURE_FLAGS['normalized_before_integration'] = use_normalized

    predictor = RacePredictor(db_path, use_cache=False)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    stats = {
        'total': 0,
        'hit_1st': 0,
        'hit_3rd': 0,
        'rank_diffs': []  # 実際の1着艇の予測順位
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
        stats['total'] += 1

        # 予測順位を確認
        pred_ranks = {p['pit_number']: i+1 for i, p in enumerate(predictions)}
        actual_pred_rank = pred_ranks.get(actual_winner, 7)

        stats['rank_diffs'].append(actual_pred_rank)

        # 1着的中
        if actual_pred_rank == 1:
            stats['hit_1st'] += 1

        # 3着以内的中
        if actual_pred_rank <= 3:
            stats['hit_3rd'] += 1

    conn.close()

    # feature_flagsを元に戻す
    FEATURE_FLAGS['normalized_before_integration'] = original

    # 結果計算
    if stats['total'] > 0:
        stats['hit_rate_1st'] = stats['hit_1st'] / stats['total'] * 100
        stats['hit_rate_3rd'] = stats['hit_3rd'] / stats['total'] * 100
        stats['avg_rank'] = sum(stats['rank_diffs']) / len(stats['rank_diffs'])

    return stats


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=" * 80)
    print("正規化統合の効果検証")
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
        LIMIT 200
    ''')
    race_ids = [row['id'] for row in cursor.fetchall()]

    print(f"検証レース数: {len(race_ids)}")
    print()

    conn.close()

    if len(race_ids) < 10:
        print(f"[NG] 直前情報付きレースが不足（{len(race_ids)}件）")
        print("検証には最低10レース必要です")
        return

    # パターン1: BEFORE無効（before_safe_integrationも無効）
    print("=" * 80)
    print("パターン1: BEFORE無効（ベースライン）")
    print("=" * 80)

    # before_safe_integrationを一時的に無効化
    original_safe = FEATURE_FLAGS['before_safe_integration']
    FEATURE_FLAGS['before_safe_integration'] = False

    stats_disabled = validate_with_flag_setting(db_path, race_ids, use_normalized=False)

    FEATURE_FLAGS['before_safe_integration'] = original_safe

    print(f"検証レース: {stats_disabled['total']}")
    print(f"1着的中: {stats_disabled['hit_1st']}回")
    print(f"1着的中率: {stats_disabled.get('hit_rate_1st', 0):.2f}%")
    print(f"3着以内的中: {stats_disabled['hit_3rd']}回")
    print(f"3着以内的中率: {stats_disabled.get('hit_rate_3rd', 0):.2f}%")
    print(f"1着艇の平均予測順位: {stats_disabled.get('avg_rank', 0):.2f}位")
    print()

    # パターン2: 正規化統合有効
    print("=" * 80)
    print("パターン2: 正規化統合有効")
    print("=" * 80)

    stats_normalized = validate_with_flag_setting(db_path, race_ids, use_normalized=True)

    print(f"検証レース: {stats_normalized['total']}")
    print(f"1着的中: {stats_normalized['hit_1st']}回")
    print(f"1着的中率: {stats_normalized.get('hit_rate_1st', 0):.2f}%")
    print(f"3着以内的中: {stats_normalized['hit_3rd']}回")
    print(f"3着以内的中率: {stats_normalized.get('hit_rate_3rd', 0):.2f}%")
    print(f"1着艇の平均予測順位: {stats_normalized.get('avg_rank', 0):.2f}位")
    print()

    # 比較分析
    print("=" * 80)
    print("比較分析")
    print("=" * 80)
    print()

    hit_rate_diff = stats_normalized.get('hit_rate_1st', 0) - stats_disabled.get('hit_rate_1st', 0)
    hit_3rd_diff = stats_normalized.get('hit_rate_3rd', 0) - stats_disabled.get('hit_rate_3rd', 0)
    rank_diff = stats_disabled.get('avg_rank', 0) - stats_normalized.get('avg_rank', 0)

    print("1着的中率の比較:")
    print(f"  BEFORE無効: {stats_disabled.get('hit_rate_1st', 0):6.2f}%")
    print(f"  正規化統合: {stats_normalized.get('hit_rate_1st', 0):6.2f}% (差分: {hit_rate_diff:+.2f}%)")
    print()

    print("3着以内的中率の比較:")
    print(f"  BEFORE無効: {stats_disabled.get('hit_rate_3rd', 0):6.2f}%")
    print(f"  正規化統合: {stats_normalized.get('hit_rate_3rd', 0):6.2f}% (差分: {hit_3rd_diff:+.2f}%)")
    print()

    print("1着艇の平均予測順位:")
    print(f"  BEFORE無効: {stats_disabled.get('avg_rank', 0):.2f}位")
    print(f"  正規化統合: {stats_normalized.get('avg_rank', 0):.2f}位 (改善: {rank_diff:+.2f}位)")
    print()

    # 判定
    print("=" * 80)
    print("結論")
    print("=" * 80)
    print()

    if hit_rate_diff > 1.0:
        print(f"[推奨] 正規化統合により1着的中率が{hit_rate_diff:.2f}%向上")
        print(f"  → normalized_before_integration = True を本番運用推奨")
        print()
        print("期待効果:")
        print(f"  - 戦略A年間的中回数: 52回 → 約{int(52 * (1 + hit_rate_diff/100))}回")
        print(f"  - ROI向上: 約+{hit_rate_diff * 3:.0f}%")
    elif hit_rate_diff > 0:
        print(f"[OK] 正規化統合により1着的中率が{hit_rate_diff:.2f}%向上")
        print(f"  → 効果は限定的だが、改悪はない")
    elif hit_rate_diff > -0.5:
        print(f"[中立] 正規化統合の効果はほぼなし（差分: {hit_rate_diff:.2f}%）")
        print(f"  → BEFORE無効のまま運用継続")
    else:
        print(f"[NG] 正規化統合により的中率が{abs(hit_rate_diff):.2f}%悪化")
        print(f"  → normalized_before_integration = False に戻すべき")
        print()
        print("原因調査が必要:")
        print("  - 正規化関数の実装確認")
        print("  - 統合重みの妥当性検証")

    print()
    print("=" * 80)


if __name__ == '__main__':
    main()
