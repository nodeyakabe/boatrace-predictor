"""
会場特性分析 - 歴史的データから会場の特徴を抽出
"""

import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from config.settings import DATABASE_PATH
from collections import defaultdict

def analyze_venue_characteristics():
    print("=" * 80)
    print("会場特性分析 - 歴史的データ")
    print("=" * 80)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

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

    # 全結果データから会場別の統計を取得
    cursor.execute("""
        SELECT
            r.venue_code,
            res.pit_number,
            COUNT(*) as count
        FROM results res
        JOIN races r ON res.race_id = r.id
        WHERE CAST(res.rank AS INTEGER) = 1
        GROUP BY r.venue_code, res.pit_number
        ORDER BY r.venue_code, res.pit_number
    """)

    venue_stats = defaultdict(lambda: {'total': 0, 'by_pit': defaultdict(int)})

    for venue, pit, count in cursor.fetchall():
        venue_stats[venue]['total'] += count
        venue_stats[venue]['by_pit'][pit] = count

    print("\n会場別1着率（全データ）:")
    print("=" * 80)

    venue_characteristics = {}

    for venue in sorted(venue_stats.keys()):
        stats = venue_stats[venue]
        venue_name = venue_names.get(venue, '不明')
        total = stats['total']

        print(f"\n【会場{venue} - {venue_name}】 ({total}レース)")
        print("  号艇 | 1着回数 | 1着率")
        print("  " + "-" * 40)

        pit1_rate = 0
        for pit in range(1, 7):
            count = stats['by_pit'].get(pit, 0)
            rate = (count / total * 100) if total > 0 else 0
            if pit == 1:
                pit1_rate = rate
            print(f"  {pit}号艇 | {count:4d}   | {rate:5.1f}%")

        # 会場特性を分類
        if pit1_rate >= 65:
            characteristic = "インが非常に強い"
            adjustment = 1.1  # 1号艇スコアを10%増
        elif pit1_rate >= 55:
            characteristic = "インが強い"
            adjustment = 1.05  # 1号艇スコアを5%増
        elif pit1_rate >= 45:
            characteristic = "標準的"
            adjustment = 1.0  # 補正なし
        else:
            characteristic = "インが弱い"
            adjustment = 0.9  # 1号艇スコアを10%減

        venue_characteristics[venue] = {
            'name': venue_name,
            'pit1_rate': pit1_rate,
            'characteristic': characteristic,
            'pit1_adjustment': adjustment,
            'total_races': total
        }

        print(f"\n  特性: {characteristic} (1号艇勝率: {pit1_rate:.1f}%)")
        print(f"  推奨補正係数: {adjustment:.2f}")

    # 会場特性サマリー
    print("\n" + "=" * 80)
    print("会場特性サマリー")
    print("=" * 80)
    print("\n会場コード | 会場名   | 1号艇勝率 | 特性              | 補正係数 | レース数")
    print("-" * 80)

    for venue in sorted(venue_characteristics.keys()):
        char = venue_characteristics[venue]
        print(f"    {venue}     | {char['name']:8s} |   {char['pit1_rate']:5.1f}%  | {char['characteristic']:16s} |  {char['pit1_adjustment']:.2f}   | {char['total_races']:4d}")

    # 設定ファイルとして出力するためのデータ
    print("\n" + "=" * 80)
    print("設定ファイル用データ (config/venue_characteristics.py)")
    print("=" * 80)
    print("\n```python")
    print('"""')
    print("会場特性データ")
    print('"""')
    print("\nVENUE_CHARACTERISTICS = {")
    for venue in sorted(venue_characteristics.keys()):
        char = venue_characteristics[venue]
        print(f"    '{venue}': {{")
        print(f"        'name': '{char['name']}',")
        print(f"        'pit1_rate': {char['pit1_rate']:.1f},")
        print(f"        'characteristic': '{char['characteristic']}',")
        print(f"        'pit1_adjustment': {char['pit1_adjustment']},")
        print(f"    }},")
    print("}")
    print("```")

    conn.close()

    print("\n" + "=" * 80)
    print("分析完了")
    print("=" * 80)

    return venue_characteristics


if __name__ == "__main__":
    analyze_venue_characteristics()
