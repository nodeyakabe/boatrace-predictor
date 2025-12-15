# -*- coding: utf-8 -*-
"""
会場×コース別 実勝率分析スクリプト

データベースから各会場のコース別勝率を分析し、
全体平均との差分を計算して、デバフ/バフポイントを算出する。

出力:
- 各会場のコース別実勝率
- 全体平均勝率との差分
- 推奨調整ポイント（-20pt ～ +20pt）

使用方法:
    python scripts/analysis/analyze_venue_course_performance.py
"""

import sqlite3
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Any
import json

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))


def get_db_connection(db_path: str = None) -> sqlite3.Connection:
    """データベース接続を取得"""
    if db_path is None:
        db_path = project_root / "data" / "boatrace.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def analyze_venue_course_win_rates(
    conn: sqlite3.Connection,
    start_date: str = "2024-01-01",
    end_date: str = "2025-12-31",
    min_races: int = 100
) -> Dict[str, Dict[int, Dict]]:
    """
    各会場のコース別勝率を分析

    Args:
        conn: データベース接続
        start_date: 分析開始日
        end_date: 分析終了日
        min_races: 最低レース数の閾値（統計的有意性確保）

    Returns:
        {venue_code: {course: {win_rate, race_count, ...}}}
    """
    query = """
    SELECT
        r.venue_code,
        rd.actual_course as course,
        COUNT(*) as total_races,
        SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as win_rate,
        SUM(CASE WHEN res.rank IN ('1', '2') THEN 1 ELSE 0 END) as top2,
        ROUND(SUM(CASE WHEN res.rank IN ('1', '2') THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as top2_rate,
        SUM(CASE WHEN res.rank IN ('1', '2', '3') THEN 1 ELSE 0 END) as top3,
        ROUND(SUM(CASE WHEN res.rank IN ('1', '2', '3') THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as top3_rate
    FROM races r
    JOIN race_details rd ON r.id = rd.race_id
    JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
    WHERE r.race_date BETWEEN ? AND ?
      AND res.is_invalid = 0
      AND rd.actual_course IS NOT NULL
      AND rd.actual_course BETWEEN 1 AND 6
    GROUP BY r.venue_code, rd.actual_course
    ORDER BY r.venue_code, rd.actual_course
    """

    cursor = conn.execute(query, (start_date, end_date))
    rows = cursor.fetchall()

    venue_stats = {}
    for row in rows:
        venue_code = row['venue_code']
        course = row['course']

        if venue_code not in venue_stats:
            venue_stats[venue_code] = {}

        venue_stats[venue_code][course] = {
            'win_rate': row['win_rate'],
            'top2_rate': row['top2_rate'],
            'top3_rate': row['top3_rate'],
            'race_count': row['total_races'],
            'wins': row['wins'],
        }

    return venue_stats


def calculate_overall_averages(venue_stats: Dict) -> Dict[int, float]:
    """
    全会場平均の勝率を計算

    Args:
        venue_stats: 会場別コース別統計

    Returns:
        {course: average_win_rate}
    """
    course_totals = {i: {'wins': 0, 'races': 0} for i in range(1, 7)}

    for venue_code, courses in venue_stats.items():
        for course, stats in courses.items():
            course_totals[course]['wins'] += stats['wins']
            course_totals[course]['races'] += stats['race_count']

    averages = {}
    for course, totals in course_totals.items():
        if totals['races'] > 0:
            averages[course] = round(totals['wins'] * 100.0 / totals['races'], 2)
        else:
            averages[course] = 0.0

    return averages


def calculate_adjustments(
    venue_stats: Dict,
    overall_averages: Dict[int, float],
    min_races: int = 100,
    max_adjustment: int = 20
) -> Dict[str, Dict[int, Dict]]:
    """
    勝率差分に基づいてポイント調整値を算出

    調整ロジック:
    - 勝率差分1%につき1pt調整
    - 最大±20pt
    - 最低レース数を満たさない場合は調整なし（0pt）

    Args:
        venue_stats: 会場別コース別統計
        overall_averages: 全体平均勝率
        min_races: 最低レース数閾値
        max_adjustment: 最大調整ポイント

    Returns:
        {venue_code: {course: {adjustment, diff, ...}}}
    """
    adjustments = {}

    for venue_code, courses in venue_stats.items():
        adjustments[venue_code] = {}

        for course, stats in courses.items():
            avg = overall_averages.get(course, 50.0)
            win_rate = stats['win_rate']
            diff = win_rate - avg

            # 統計的有意性の確保
            if stats['race_count'] < min_races:
                # サンプル数が少ない場合は調整なし
                adjustment = 0
                is_significant = False
            else:
                # 勝率差分1%につき1ptの調整
                # 例: 差分+10% → +10pt、差分-5% → -5pt
                raw_adjustment = round(diff)
                adjustment = max(-max_adjustment, min(max_adjustment, raw_adjustment))
                is_significant = True

            adjustments[venue_code][course] = {
                'adjustment': adjustment,
                'diff': round(diff, 2),
                'venue_win_rate': win_rate,
                'overall_avg': avg,
                'race_count': stats['race_count'],
                'is_significant': is_significant,
            }

    return adjustments


def get_venue_names(conn: sqlite3.Connection) -> Dict[str, str]:
    """会場名を取得"""
    query = """
    SELECT DISTINCT venue_code,
           CASE venue_code
               WHEN '01' THEN '桐生'
               WHEN '02' THEN '戸田'
               WHEN '03' THEN '江戸川'
               WHEN '04' THEN '平和島'
               WHEN '05' THEN '多摩川'
               WHEN '06' THEN '浜名湖'
               WHEN '07' THEN '蒲郡'
               WHEN '08' THEN '常滑'
               WHEN '09' THEN '津'
               WHEN '10' THEN '三国'
               WHEN '11' THEN 'びわこ'
               WHEN '12' THEN '住之江'
               WHEN '13' THEN '尼崎'
               WHEN '14' THEN '鳴門'
               WHEN '15' THEN '丸亀'
               WHEN '16' THEN '児島'
               WHEN '17' THEN '宮島'
               WHEN '18' THEN '徳山'
               WHEN '19' THEN '下関'
               WHEN '20' THEN '若松'
               WHEN '21' THEN '芦屋'
               WHEN '22' THEN '福岡'
               WHEN '23' THEN '唐津'
               WHEN '24' THEN '大村'
               ELSE '不明'
           END as venue_name
    FROM races
    """
    cursor = conn.execute(query)
    return {row['venue_code']: row['venue_name'] for row in cursor.fetchall()}


def generate_config_file(
    adjustments: Dict,
    venue_names: Dict,
    output_path: Path
):
    """
    調整設定ファイルを生成

    Args:
        adjustments: 調整値
        venue_names: 会場名
        output_path: 出力先パス
    """
    lines = [
        "# -*- coding: utf-8 -*-",
        '"""',
        "会場×コース別 ポイント調整設定",
        "",
        "2024-2025年データから算出",
        "各コースの全国平均勝率との差分に基づくデバフ/バフポイント",
        "",
        "使用方法:",
        "    from config.venue_course_adjustments import VENUE_COURSE_ADJUSTMENTS, get_adjustment",
        "",
        "    # 調整ポイントを取得",
        "    adj = get_adjustment(venue_code='01', course=1)  # -6 など",
        "",
        "    # 予測スコアに適用",
        "    adjusted_score = base_score + adj",
        '"""',
        "",
        "from typing import Dict, Optional",
        "",
        "",
        "# ==============================================================================",
        "# 会場×コース別 調整ポイント",
        "# 正の値 = バフ（勝率が平均より高い）",
        "# 負の値 = デバフ（勝率が平均より低い）",
        "# ==============================================================================",
        "VENUE_COURSE_ADJUSTMENTS: Dict[str, Dict[int, int]] = {",
    ]

    # 会場コード順にソート
    sorted_venues = sorted(adjustments.keys())

    for venue_code in sorted_venues:
        courses = adjustments[venue_code]
        venue_name = venue_names.get(venue_code, '不明')

        # 各コースの調整値を取得
        course_adjs = []
        for c in range(1, 7):
            if c in courses:
                adj = courses[c]['adjustment']
                course_adjs.append(f"{c}: {adj:+d}")
            else:
                course_adjs.append(f"{c}: 0")

        line = f"    '{venue_code}': {{{', '.join(course_adjs)}}},  # {venue_name}"
        lines.append(line)

    lines.extend([
        "}",
        "",
        "",
        "# ==============================================================================",
        "# 全体平均勝率（参考）",
        "# ==============================================================================",
        "OVERALL_WIN_RATES = {",
    ])

    lines.extend([
        "}",
        "",
        "",
        "# ==============================================================================",
        "# ヘルパー関数",
        "# ==============================================================================",
        "",
        "def get_adjustment(venue_code: str, course: int) -> int:",
        '    """',
        "    会場×コース別の調整ポイントを取得",
        "",
        "    Args:",
        "        venue_code: 会場コード ('01'-'24')",
        "        course: コース番号 (1-6)",
        "",
        "    Returns:",
        "        int: 調整ポイント (-20 ～ +20)",
        '    """',
        "    venue_adjs = VENUE_COURSE_ADJUSTMENTS.get(venue_code, {})",
        "    return venue_adjs.get(course, 0)",
        "",
        "",
        "def get_all_adjustments(venue_code: str) -> Dict[int, int]:",
        '    """',
        "    会場の全コース調整ポイントを取得",
        "",
        "    Args:",
        "        venue_code: 会場コード",
        "",
        "    Returns:",
        "        {course: adjustment}",
        '    """',
        "    return VENUE_COURSE_ADJUSTMENTS.get(venue_code, {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0})",
        "",
        "",
        "def apply_adjustment(base_score: float, venue_code: str, course: int) -> float:",
        '    """',
        "    予測スコアに調整を適用",
        "",
        "    Args:",
        "        base_score: 元の予測スコア",
        "        venue_code: 会場コード",
        "        course: コース番号",
        "",
        "    Returns:",
        "        float: 調整後スコア",
        '    """',
        "    adjustment = get_adjustment(venue_code, course)",
        "    return base_score + adjustment",
        "",
    ])

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def print_analysis_report(
    venue_stats: Dict,
    overall_averages: Dict[int, float],
    adjustments: Dict,
    venue_names: Dict
):
    """分析レポートを出力"""
    print("=" * 100)
    print("会場×コース別 実勝率分析レポート")
    print(f"分析日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)

    print("\n" + "-" * 50)
    print("1. 全体平均勝率")
    print("-" * 50)
    for course in range(1, 7):
        print(f"  {course}コース: {overall_averages[course]:.2f}%")

    print("\n" + "-" * 50)
    print("2. 会場別コース勝率差分（平均との比較）")
    print("-" * 50)

    # インが弱い会場を特定
    weak_in_venues = []
    strong_in_venues = []

    for venue_code in sorted(adjustments.keys()):
        courses = adjustments[venue_code]
        venue_name = venue_names.get(venue_code, '不明')

        if 1 in courses:
            c1_data = courses[1]
            if c1_data['diff'] < -5:
                weak_in_venues.append((venue_code, venue_name, c1_data['diff']))
            elif c1_data['diff'] > 5:
                strong_in_venues.append((venue_code, venue_name, c1_data['diff']))

    print("\n[インが弱い会場（1コース勝率が平均より-5%以上低い）]")
    for code, name, diff in sorted(weak_in_venues, key=lambda x: x[2]):
        print(f"  {name}({code}): {diff:+.2f}%")

    print("\n[インが強い会場（1コース勝率が平均より+5%以上高い）]")
    for code, name, diff in sorted(strong_in_venues, key=lambda x: x[2], reverse=True):
        print(f"  {name}({code}): {diff:+.2f}%")

    print("\n" + "-" * 50)
    print("3. 会場別 調整ポイント一覧")
    print("-" * 50)
    print(f"{'会場':>8} | " + " | ".join([f"{i}コース" for i in range(1, 7)]))
    print("-" * 100)

    for venue_code in sorted(adjustments.keys()):
        courses = adjustments[venue_code]
        venue_name = venue_names.get(venue_code, '不明')

        adj_strs = []
        for c in range(1, 7):
            if c in courses:
                adj = courses[c]['adjustment']
                if adj > 0:
                    adj_strs.append(f" {adj:+d}pt")
                elif adj < 0:
                    adj_strs.append(f" {adj:+d}pt")
                else:
                    adj_strs.append("  0pt")
            else:
                adj_strs.append("  -  ")

        print(f"{venue_name:>8} | " + " | ".join(adj_strs))

    print("\n" + "-" * 50)
    print("4. 特筆すべきパターン")
    print("-" * 50)

    # 極端な調整が必要なパターンを抽出
    extreme_patterns = []
    for venue_code, courses in adjustments.items():
        for course, data in courses.items():
            if abs(data['adjustment']) >= 10:
                venue_name = venue_names.get(venue_code, '不明')
                extreme_patterns.append({
                    'venue': venue_name,
                    'code': venue_code,
                    'course': course,
                    'adjustment': data['adjustment'],
                    'diff': data['diff'],
                    'race_count': data['race_count'],
                })

    if extreme_patterns:
        print("\n[大幅調整が必要なパターン（±10pt以上）]")
        for p in sorted(extreme_patterns, key=lambda x: abs(x['adjustment']), reverse=True):
            sign = "強い" if p['adjustment'] > 0 else "弱い"
            print(f"  {p['venue']}({p['code']}) {p['course']}コース: {p['adjustment']:+d}pt "
                  f"（{sign}、勝率差{p['diff']:+.2f}%、n={p['race_count']}）")
    else:
        print("  極端な調整が必要なパターンはありません")

    print("\n" + "=" * 100)


def export_to_json(
    venue_stats: Dict,
    overall_averages: Dict,
    adjustments: Dict,
    venue_names: Dict,
    output_path: Path
):
    """JSON形式でエクスポート"""
    export_data = {
        'generated_at': datetime.now().isoformat(),
        'overall_averages': overall_averages,
        'venue_stats': {},
        'adjustments': {},
    }

    for venue_code, courses in venue_stats.items():
        export_data['venue_stats'][venue_code] = {
            'name': venue_names.get(venue_code, '不明'),
            'courses': courses,
        }

    for venue_code, courses in adjustments.items():
        export_data['adjustments'][venue_code] = {
            'name': venue_names.get(venue_code, '不明'),
            'courses': courses,
        }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)


def main():
    """メイン処理"""
    print("会場×コース別 実勝率分析を開始します...")

    conn = get_db_connection()

    try:
        # 会場名を取得
        venue_names = get_venue_names(conn)

        # 会場別コース別勝率を分析
        print("データベースを分析中...")
        venue_stats = analyze_venue_course_win_rates(
            conn,
            start_date="2024-01-01",
            end_date="2025-12-31",
            min_races=100
        )

        # 全体平均を計算
        overall_averages = calculate_overall_averages(venue_stats)

        # 調整値を算出
        adjustments = calculate_adjustments(
            venue_stats,
            overall_averages,
            min_races=100,
            max_adjustment=20
        )

        # レポート出力
        print_analysis_report(venue_stats, overall_averages, adjustments, venue_names)

        # 設定ファイル生成
        config_path = project_root / "config" / "venue_course_adjustments.py"
        generate_config_file(adjustments, venue_names, config_path)
        print(f"\n設定ファイルを生成しました: {config_path}")

        # JSONエクスポート
        json_path = project_root / "data" / "venue_course_analysis.json"
        export_to_json(venue_stats, overall_averages, adjustments, venue_names, json_path)
        print(f"JSON分析結果を出力しました: {json_path}")

    finally:
        conn.close()

    print("\n分析完了！")


if __name__ == "__main__":
    main()
