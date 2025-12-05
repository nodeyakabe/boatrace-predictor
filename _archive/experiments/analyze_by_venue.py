"""
会場別の的中率分析
"""

import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from config.settings import DATABASE_PATH
from collections import defaultdict

def analyze_by_venue(target_date='2025-11-17'):
    print("=" * 80)
    print(f"会場別的中率分析: {target_date}")
    print("=" * 80)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 会場別の予測と結果を取得
    cursor.execute("""
        SELECT
            r.venue_code,
            rp.pit_number as predicted_pit,
            rp.confidence,
            res.pit_number as actual_pit
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        LEFT JOIN results res ON rp.race_id = res.race_id AND CAST(res.rank AS INTEGER) = 1
        WHERE r.race_date = ?
          AND rp.rank_prediction = 1
        ORDER BY r.venue_code
    """, (target_date,))

    predictions = cursor.fetchall()

    # 会場名マッピング
    venue_names = {
        '02': '戸田',
        '03': '江戸川',
        '07': 'がまかつ',
        '10': '三国',
        '12': '住之江',
        '14': '鳴門',
        '15': '丸亀',
        '17': '宮島',
        '18': '徳山',
        '20': '若松',
        '22': '福岡'
    }

    # 会場ごとの統計
    by_venue = defaultdict(lambda: {
        'total': 0,
        'correct': 0,
        'by_confidence': defaultdict(lambda: {'total': 0, 'correct': 0}),
        'pit1_predictions': 0,
        'pit1_correct': 0
    })

    for venue, pred_pit, conf, actual_pit in predictions:
        stats = by_venue[venue]
        stats['total'] += 1

        is_correct = (pred_pit == actual_pit) if actual_pit else False
        if is_correct:
            stats['correct'] += 1

        # 信頼度別
        stats['by_confidence'][conf]['total'] += 1
        if is_correct:
            stats['by_confidence'][conf]['correct'] += 1

        # 1号艇予測
        if pred_pit == 1:
            stats['pit1_predictions'] += 1
            if is_correct:
                stats['pit1_correct'] += 1

    # 会場別サマリー
    print("\n会場別的中率サマリー:")
    print("-" * 80)
    print("会場コード | 会場名   | レース数 | 的中数 | 的中率 | 1号艇予測率 | 1号艇的中率")
    print("-" * 80)

    venue_stats = []
    for venue in sorted(by_venue.keys()):
        stats = by_venue[venue]
        venue_name = venue_names.get(venue, '不明')
        accuracy = (stats['correct'] / stats['total'] * 100) if stats['total'] > 0 else 0
        pit1_rate = (stats['pit1_predictions'] / stats['total'] * 100) if stats['total'] > 0 else 0
        pit1_acc = (stats['pit1_correct'] / stats['pit1_predictions'] * 100) if stats['pit1_predictions'] > 0 else 0

        venue_stats.append((venue, venue_name, stats['total'], stats['correct'], accuracy, pit1_rate, pit1_acc))

        print(f"    {venue}     | {venue_name:8s} |    {stats['total']:2d}   |   {stats['correct']:2d}   | {accuracy:5.1f}% |    {pit1_rate:5.1f}%   |   {pit1_acc:5.1f}%")

    # 会場別の信頼度分布
    print("\n" + "=" * 80)
    print("会場別の信頼度別的中率")
    print("=" * 80)

    for venue in sorted(by_venue.keys()):
        stats = by_venue[venue]
        venue_name = venue_names.get(venue, '不明')

        print(f"\n【会場{venue} - {venue_name}】")
        print("  信頼度 | レース数 | 的中数 | 的中率")
        print("  " + "-" * 45)

        for conf in ['A', 'B', 'C', 'D', 'E']:
            if conf in stats['by_confidence']:
                conf_stats = stats['by_confidence'][conf]
                conf_acc = (conf_stats['correct'] / conf_stats['total'] * 100) if conf_stats['total'] > 0 else 0
                print(f"  {conf:4s}   | {conf_stats['total']:4d}     | {conf_stats['correct']:4d}   | {conf_acc:5.1f}%")

    # 実際の会場別1着分布
    print("\n" + "=" * 80)
    print("実際の会場別1着分布")
    print("=" * 80)

    for venue in sorted(by_venue.keys()):
        venue_name = venue_names.get(venue, '不明')

        cursor.execute("""
            SELECT res.pit_number, COUNT(*) as count
            FROM results res
            JOIN races r ON res.race_id = r.id
            WHERE r.race_date = ?
              AND r.venue_code = ?
              AND CAST(res.rank AS INTEGER) = 1
            GROUP BY res.pit_number
            ORDER BY res.pit_number
        """, (target_date, venue))

        results = cursor.fetchall()
        total = sum(r[1] for r in results)

        print(f"\n【会場{venue} - {venue_name}】 ({total}レース)")
        for pit, count in results:
            pct = (count / total * 100) if total > 0 else 0
            print(f"  {pit}号艇: {count:2d}回 ({pct:5.1f}%)")

    conn.close()

    # ハイライト
    print("\n" + "=" * 80)
    print("分析ハイライト")
    print("=" * 80)

    # 最高的中率の会場
    best_venue = max(venue_stats, key=lambda x: x[4])
    print(f"\n最高的中率: 会場{best_venue[0]} ({best_venue[1]}) - {best_venue[4]:.1f}% ({best_venue[3]}/{best_venue[2]})")

    # 最低的中率の会場
    worst_venue = min(venue_stats, key=lambda x: x[4])
    print(f"最低的中率: 会場{worst_venue[0]} ({worst_venue[1]}) - {worst_venue[4]:.1f}% ({worst_venue[3]}/{worst_venue[2]})")

    # 1号艇予測率が最も高い会場
    most_pit1 = max(venue_stats, key=lambda x: x[5])
    print(f"\n1号艇予測率が最も高い: 会場{most_pit1[0]} ({most_pit1[1]}) - {most_pit1[5]:.1f}%")

    # 1号艇予測率が最も低い会場
    least_pit1 = min(venue_stats, key=lambda x: x[5])
    print(f"1号艇予測率が最も低い: 会場{least_pit1[0]} ({least_pit1[1]}) - {least_pit1[5]:.1f}%")

    print("\n" + "=" * 80)
    print("分析完了")
    print("=" * 80)


if __name__ == "__main__":
    import sys
    target_date = sys.argv[1] if len(sys.argv) > 1 else '2025-11-17'
    analyze_by_venue(target_date)
