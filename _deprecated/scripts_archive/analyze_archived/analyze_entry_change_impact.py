# -*- coding: utf-8 -*-
"""進入変化の影響分析

展示航走と本番の進入が変わった場合の予測精度への影響を調査
"""

import sys
import sqlite3
from pathlib import Path
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.analysis.race_predictor import RacePredictor


def analyze_entry_change_impact(db_path, limit=300):
    """
    進入変化の影響分析

    Args:
        db_path: データベースパス
        limit: 分析するレース数

    Returns:
        dict: 分析結果
    """
    predictor = RacePredictor(db_path, use_cache=False)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 2025年で直前情報が存在するレースを取得
    cursor.execute('''
        SELECT DISTINCT r.id, r.race_date, r.race_number
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        AND rd.exhibition_time IS NOT NULL
        ORDER BY r.race_date, r.race_number
        LIMIT ?
    ''', (limit,))
    races = cursor.fetchall()

    print(f"分析対象レース数: {len(races)}")
    print()

    # 統計情報
    stats = {
        'entry_match': {  # 進入一致レース
            'total': 0,
            'hit_1st': 0,
            'hit_3rd': 0,
            'rank_diffs': []
        },
        'entry_change': {  # 進入変化レース
            'total': 0,
            'hit_1st': 0,
            'hit_3rd': 0,
            'rank_diffs': []
        },
        'no_exhibition': {  # 展示航走データなし
            'total': 0,
            'hit_1st': 0,
            'hit_3rd': 0,
            'rank_diffs': []
        }
    }

    # 進入変化のパターン
    entry_change_patterns = defaultdict(int)

    for race_row in races:
        race_id = race_row['id']

        # 展示航走の進入コースを取得
        cursor.execute('''
            SELECT pit_number, exhibition_course
            FROM race_details
            WHERE race_id = ?
        ''', (race_id,))
        exhibition_entries = {row['pit_number']: row['exhibition_course'] for row in cursor.fetchall()}

        # 本番の進入コースを取得
        cursor.execute('''
            SELECT pit_number, actual_course
            FROM race_details
            WHERE race_id = ?
        ''', (race_id,))
        actual_entries = {row['pit_number']: row['actual_course'] for row in cursor.fetchall()}

        if not actual_entries or len(actual_entries) != 6:
            continue

        # 進入一致判定
        if not exhibition_entries or len(exhibition_entries) == 0:
            category = 'no_exhibition'
        else:
            # 進入が変わったかチェック
            entry_changed = False
            change_pattern = []
            for pit in range(1, 7):
                if pit in exhibition_entries and pit in actual_entries:
                    ex_course = exhibition_entries[pit]
                    actual_course = actual_entries[pit]
                    if ex_course != actual_course:
                        entry_changed = True
                        change_pattern.append(f"{pit}号艇: {ex_course}→{actual_course}")

            if entry_changed:
                category = 'entry_change'
                entry_change_patterns[', '.join(change_pattern)] += 1
            else:
                category = 'entry_match'

        # 予測実行
        try:
            predictions = predictor.predict_race(race_id)
        except Exception as e:
            continue

        if not predictions or len(predictions) < 6:
            continue

        # 実際の1着を取得
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank = 1
        ''', (race_id,))
        result = cursor.fetchone()

        if not result:
            continue

        actual_winner = result['pit_number']

        # 統計に追加
        stats[category]['total'] += 1

        # 予測順位を確認
        pred_ranks = {p['pit_number']: i+1 for i, p in enumerate(predictions)}
        actual_pred_rank = pred_ranks.get(actual_winner, 7)

        stats[category]['rank_diffs'].append(actual_pred_rank)

        # 1着的中
        if actual_pred_rank == 1:
            stats[category]['hit_1st'] += 1

        # 3着以内的中
        if actual_pred_rank <= 3:
            stats[category]['hit_3rd'] += 1

    conn.close()

    # 結果表示
    print("=" * 80)
    print("進入変化の影響分析")
    print("=" * 80)
    print()

    for category, label in [
        ('entry_match', '進入一致レース（展示=本番）'),
        ('entry_change', '進入変化レース（展示≠本番）'),
        ('no_exhibition', '展示航走データなし')
    ]:
        cat_stats = stats[category]
        if cat_stats['total'] == 0:
            continue

        hit_rate_1st = cat_stats['hit_1st'] / cat_stats['total'] * 100
        hit_rate_3rd = cat_stats['hit_3rd'] / cat_stats['total'] * 100
        avg_rank = sum(cat_stats['rank_diffs']) / len(cat_stats['rank_diffs'])

        print(f"【{label}】")
        print(f"  レース数: {cat_stats['total']}")
        print(f"  1着的中: {cat_stats['hit_1st']}回 ({hit_rate_1st:.2f}%)")
        print(f"  3着以内的中: {cat_stats['hit_3rd']}回 ({hit_rate_3rd:.2f}%)")
        print(f"  1着艇の平均予測順位: {avg_rank:.2f}位")
        print()

    # 進入一致 vs 進入変化の比較
    if stats['entry_match']['total'] > 0 and stats['entry_change']['total'] > 0:
        match_rate = stats['entry_match']['hit_1st'] / stats['entry_match']['total'] * 100
        change_rate = stats['entry_change']['hit_1st'] / stats['entry_change']['total'] * 100
        diff = match_rate - change_rate

        print("=" * 80)
        print("進入一致 vs 進入変化の比較")
        print("=" * 80)
        print()
        print(f"進入一致レースの1着的中率: {match_rate:.2f}%")
        print(f"進入変化レースの1着的中率: {change_rate:.2f}%")
        print(f"差分: {diff:+.2f}%")
        print()

        if diff > 5.0:
            print("[重要] 進入変化によって的中率が大幅に低下")
            print("  → 進入が変わるレースは信頼度を大幅に下げるべき")
            print(f"  → 予測的中率が{diff:.1f}%も悪化")
        elif diff > 2.0:
            print("[注意] 進入変化によって的中率が低下")
            print("  → 進入が変わるレースは信頼度を下げるべき")
        else:
            print("[OK] 進入変化の影響は限定的")

        print()

    # 進入変化のパターン
    if entry_change_patterns:
        print("=" * 80)
        print("進入変化パターン（上位10件）")
        print("=" * 80)
        print()

        sorted_patterns = sorted(entry_change_patterns.items(), key=lambda x: x[1], reverse=True)
        for i, (pattern, count) in enumerate(sorted_patterns[:10], 1):
            print(f"{i}. {pattern} ({count}回)")

        print()

    # 進入変化率
    total_with_exhibition = stats['entry_match']['total'] + stats['entry_change']['total']
    if total_with_exhibition > 0:
        change_ratio = stats['entry_change']['total'] / total_with_exhibition * 100
        print(f"進入変化率: {change_ratio:.1f}% ({stats['entry_change']['total']}/{total_with_exhibition})")
        print()

    print("=" * 80)
    print("推奨事項")
    print("=" * 80)
    print()

    if stats['entry_change']['total'] > 0 and stats['entry_match']['total'] > 0:
        match_rate = stats['entry_match']['hit_1st'] / stats['entry_match']['total'] * 100
        change_rate = stats['entry_change']['hit_1st'] / stats['entry_change']['total'] * 100
        diff = match_rate - change_rate

        if diff > 5.0:
            print("1. 進入変化レースのBEFORE信頼度を大幅に下げる（例: 0.5倍）")
            print("2. または進入変化レースを購入対象から除外する")
            print("3. 進入予測の精度向上を優先的に実施")
        elif diff > 2.0:
            print("1. 進入変化レースのBEFORE信頼度を下げる（例: 0.7倍）")
            print("2. 進入予測の精度向上を検討")
        else:
            print("進入変化の影響は小さく、現状の運用を継続")

    print()
    print("=" * 80)

    return stats


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"

    print("=" * 80)
    print("進入変化の影響分析")
    print("=" * 80)
    print()

    results = analyze_entry_change_impact(db_path, limit=300)

    print()
    print("分析完了")
    print()


if __name__ == '__main__':
    main()
