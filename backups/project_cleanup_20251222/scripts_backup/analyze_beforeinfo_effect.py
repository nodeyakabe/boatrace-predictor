# -*- coding: utf-8 -*-
"""
直前情報の活用状況検証

目的:
1. advance（事前情報）vs before（直前情報）の予測精度比較
2. 直前情報による改善効果の定量測定
3. 信頼度別の直前情報効果分析
"""
import sys
import sqlite3
from pathlib import Path
from datetime import datetime
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


def main():
    """メイン処理"""
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=" * 120)
    print("直前情報の活用状況検証: advance vs before")
    print("=" * 120)
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 2025年のレースを取得
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code, r.race_date
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')
    races = cursor.fetchall()

    # 統計用データ構造
    stats = {
        'advance': {
            'total': 0,
            'first_hit': 0, 'second_hit': 0, 'third_hit': 0, 'trifecta_hit': 0,
            'by_confidence': defaultdict(lambda: {
                'total': 0, 'first_hit': 0, 'second_hit': 0, 'third_hit': 0, 'trifecta_hit': 0
            })
        },
        'before': {
            'total': 0,
            'first_hit': 0, 'second_hit': 0, 'third_hit': 0, 'trifecta_hit': 0,
            'by_confidence': defaultdict(lambda: {
                'total': 0, 'first_hit': 0, 'second_hit': 0, 'third_hit': 0, 'trifecta_hit': 0
            })
        },
        'both': 0,  # 両方のデータがあるレース数
        'advance_only': 0,
        'before_only': 0,
        'neither': 0
    }

    # 信頼度の変化を追跡
    confidence_changes = defaultdict(int)  # (before_conf, advance_conf) -> count

    for race in races:
        race_id = race['race_id']

        # 実際の結果を取得
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        results = cursor.fetchall()

        if len(results) < 3:
            stats['neither'] += 1
            continue

        actual_1st = results[0]['pit_number']
        actual_2nd = results[1]['pit_number']
        actual_3rd = results[2]['pit_number']
        actual_combo = f"{actual_1st}-{actual_2nd}-{actual_3rd}"

        # advance予測を取得
        cursor.execute('''
            SELECT pit_number, confidence, rank_prediction
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'advance'
            ORDER BY rank_prediction
        ''', (race_id,))
        advance_preds = cursor.fetchall()

        # before予測を取得
        cursor.execute('''
            SELECT pit_number, confidence, rank_prediction
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'before'
            ORDER BY rank_prediction
        ''', (race_id,))
        before_preds = cursor.fetchall()

        has_advance = len(advance_preds) >= 6
        has_before = len(before_preds) >= 6

        if has_advance and has_before:
            stats['both'] += 1
        elif has_advance:
            stats['advance_only'] += 1
        elif has_before:
            stats['before_only'] += 1
        else:
            stats['neither'] += 1
            continue

        # advance予測の精度評価
        if has_advance:
            adv_top3 = [p['pit_number'] for p in advance_preds[:3]]
            adv_conf = advance_preds[0]['confidence']
            adv_combo = f"{adv_top3[0]}-{adv_top3[1]}-{adv_top3[2]}"

            stats['advance']['total'] += 1
            stats['advance']['by_confidence'][adv_conf]['total'] += 1

            if adv_top3[0] == actual_1st:
                stats['advance']['first_hit'] += 1
                stats['advance']['by_confidence'][adv_conf]['first_hit'] += 1
            if adv_top3[1] == actual_2nd:
                stats['advance']['second_hit'] += 1
                stats['advance']['by_confidence'][adv_conf]['second_hit'] += 1
            if adv_top3[2] == actual_3rd:
                stats['advance']['third_hit'] += 1
                stats['advance']['by_confidence'][adv_conf]['third_hit'] += 1
            if adv_combo == actual_combo:
                stats['advance']['trifecta_hit'] += 1
                stats['advance']['by_confidence'][adv_conf]['trifecta_hit'] += 1

        # before予測の精度評価
        if has_before:
            bef_top3 = [p['pit_number'] for p in before_preds[:3]]
            bef_conf = before_preds[0]['confidence']
            bef_combo = f"{bef_top3[0]}-{bef_top3[1]}-{bef_top3[2]}"

            stats['before']['total'] += 1
            stats['before']['by_confidence'][bef_conf]['total'] += 1

            if bef_top3[0] == actual_1st:
                stats['before']['first_hit'] += 1
                stats['before']['by_confidence'][bef_conf]['first_hit'] += 1
            if bef_top3[1] == actual_2nd:
                stats['before']['second_hit'] += 1
                stats['before']['by_confidence'][bef_conf]['second_hit'] += 1
            if bef_top3[2] == actual_3rd:
                stats['before']['third_hit'] += 1
                stats['before']['by_confidence'][bef_conf]['third_hit'] += 1
            if bef_combo == actual_combo:
                stats['before']['trifecta_hit'] += 1
                stats['before']['by_confidence'][bef_conf]['trifecta_hit'] += 1

        # 信頼度の変化を追跡（両方ある場合）
        if has_advance and has_before:
            confidence_changes[(bef_conf, adv_conf)] += 1

    conn.close()

    # 結果出力
    print(f"総レース数: {len(races):,}")
    print(f"両方の予測あり: {stats['both']:,}")
    print(f"advance のみ: {stats['advance_only']:,}")
    print(f"before のみ: {stats['before_only']:,}")
    print(f"予測なし: {stats['neither']:,}")
    print()

    # 全体比較
    print("=" * 120)
    print("Part 1: 全体精度比較（advance vs before）")
    print("=" * 120)
    print(f"{'項目':<20} {'advance':<25} {'before':<25} {'差分':<15}")
    print("-" * 100)

    for pred_type in ['advance', 'before']:
        s = stats[pred_type]
        total = s['total']
        if total > 0:
            first_rate = s['first_hit'] / total * 100
            second_rate = s['second_hit'] / total * 100
            third_rate = s['third_hit'] / total * 100
            trifecta_rate = s['trifecta_hit'] / total * 100
            print(f"対象レース数: {total:,}")
            print(f"  1着的中率: {first_rate:.2f}%")
            print(f"  2着的中率: {second_rate:.2f}%")
            print(f"  3着的中率: {third_rate:.2f}%")
            print(f"  3連単完全一致率: {trifecta_rate:.2f}%")
            print()

    # 差分計算
    adv_total = stats['advance']['total']
    bef_total = stats['before']['total']
    if adv_total > 0 and bef_total > 0:
        diff_1st = stats['before']['first_hit']/bef_total*100 - stats['advance']['first_hit']/adv_total*100
        diff_2nd = stats['before']['second_hit']/bef_total*100 - stats['advance']['second_hit']/adv_total*100
        diff_3rd = stats['before']['third_hit']/bef_total*100 - stats['advance']['third_hit']/adv_total*100
        diff_tri = stats['before']['trifecta_hit']/bef_total*100 - stats['advance']['trifecta_hit']/adv_total*100

        print(f"\n【直前情報による改善効果】")
        print(f"  1着的中率: {diff_1st:+.2f}pt")
        print(f"  2着的中率: {diff_2nd:+.2f}pt")
        print(f"  3着的中率: {diff_3rd:+.2f}pt")
        print(f"  3連単完全一致率: {diff_tri:+.2f}pt")

    # 信頼度別精度
    print()
    print("=" * 120)
    print("Part 2: 信頼度別精度比較")
    print("=" * 120)

    for pred_type in ['advance', 'before']:
        print(f"\n--- {pred_type.upper()} 予測 ---")
        print(f"{'信頼度':<10} {'レース数':<12} {'1着的中':<12} {'2着的中':<12} {'3着的中':<12} {'3連単一致':<12}")
        print("-" * 80)

        by_conf = stats[pred_type]['by_confidence']
        for conf in ['A', 'B', 'C', 'D', 'E']:
            s = by_conf[conf]
            if s['total'] > 0:
                first_rate = s['first_hit'] / s['total'] * 100
                second_rate = s['second_hit'] / s['total'] * 100
                third_rate = s['third_hit'] / s['total'] * 100
                trifecta_rate = s['trifecta_hit'] / s['total'] * 100
                print(f"{conf:<10} {s['total']:<12} {first_rate:>8.2f}%    {second_rate:>8.2f}%    "
                      f"{third_rate:>8.2f}%    {trifecta_rate:>8.2f}%")

    # 信頼度の変化
    print()
    print("=" * 120)
    print("Part 3: 信頼度の変化（before -> advance）")
    print("=" * 120)

    print(f"\n{'変化パターン':<20} {'レース数':<15}")
    print("-" * 50)

    sorted_changes = sorted(confidence_changes.items(), key=lambda x: x[1], reverse=True)
    for (bef, adv), count in sorted_changes[:20]:
        change_str = f"{bef} -> {adv}" if bef != adv else f"{bef} (維持)"
        print(f"{change_str:<20} {count:,}")

    # 信頼度別の改善効果
    print()
    print("=" * 120)
    print("Part 4: 信頼度別の直前情報効果（before - advance）")
    print("=" * 120)

    print(f"{'信頼度':<10} {'1着的中差':<15} {'2着的中差':<15} {'3着的中差':<15} {'3連単差':<15}")
    print("-" * 80)

    for conf in ['A', 'B', 'C', 'D', 'E']:
        adv = stats['advance']['by_confidence'][conf]
        bef = stats['before']['by_confidence'][conf]

        if adv['total'] > 0 and bef['total'] > 0:
            diff_1 = bef['first_hit']/bef['total']*100 - adv['first_hit']/adv['total']*100
            diff_2 = bef['second_hit']/bef['total']*100 - adv['second_hit']/adv['total']*100
            diff_3 = bef['third_hit']/bef['total']*100 - adv['third_hit']/adv['total']*100
            diff_t = bef['trifecta_hit']/bef['total']*100 - adv['trifecta_hit']/adv['total']*100

            print(f"{conf:<10} {diff_1:>+10.2f}pt    {diff_2:>+10.2f}pt    "
                  f"{diff_3:>+10.2f}pt    {diff_t:>+10.2f}pt")

    print("=" * 120)

    return stats


if __name__ == '__main__':
    main()
