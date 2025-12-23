#!/usr/bin/env python
"""
パターンボーナス効果分析スクリプト v2

より大規模なデータで分析を行う改良版。
race_detailsの展示タイム・ST情報に加え、
entriesテーブルの勝率情報を用いてPRE順位を計算する。
"""

import sqlite3
import json
from collections import defaultdict
from datetime import datetime
import math
import sys
import os

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "boatrace.db")


def get_connection():
    """データベース接続を取得"""
    return sqlite3.connect(DB_PATH)


def check_data_availability():
    """データの利用可能性を確認"""
    conn = get_connection()
    cursor = conn.cursor()

    print("=" * 80)
    print("データ利用可能性チェック")
    print("=" * 80)

    # レース数
    cursor.execute("""
        SELECT COUNT(DISTINCT id) FROM races
        WHERE race_date >= '2020-01-01' AND race_date <= '2024-12-31'
    """)
    total_races = cursor.fetchone()[0]
    print(f"2020-2024年のレース数: {total_races:,}")

    # 結果があるレース
    cursor.execute("""
        SELECT COUNT(DISTINCT race_id) FROM results
        WHERE race_id IN (
            SELECT id FROM races WHERE race_date >= '2020-01-01' AND race_date <= '2024-12-31'
        )
    """)
    with_results = cursor.fetchone()[0]
    print(f"結果データがあるレース数: {with_results:,}")

    # BEFORE情報があるレース
    cursor.execute("""
        SELECT COUNT(DISTINCT race_id) FROM race_details
        WHERE exhibition_time IS NOT NULL
          AND st_time IS NOT NULL
          AND race_id IN (
              SELECT id FROM races WHERE race_date >= '2020-01-01' AND race_date <= '2024-12-31'
          )
    """)
    with_before = cursor.fetchone()[0]
    print(f"BEFORE情報があるレース数: {with_before:,}")

    # 完全なBEFORE情報（6艇全員）
    cursor.execute("""
        SELECT race_id, COUNT(*) as cnt
        FROM race_details
        WHERE exhibition_time IS NOT NULL
          AND st_time IS NOT NULL
          AND race_id IN (
              SELECT id FROM races WHERE race_date >= '2020-01-01' AND race_date <= '2024-12-31'
          )
        GROUP BY race_id
        HAVING cnt = 6
    """)
    complete_before = len(cursor.fetchall())
    print(f"完全なBEFORE情報（6艇）があるレース数: {complete_before:,}")

    # entries情報
    cursor.execute("""
        SELECT COUNT(DISTINCT race_id) FROM entries
        WHERE race_id IN (
            SELECT id FROM races WHERE race_date >= '2020-01-01' AND race_date <= '2024-12-31'
        )
    """)
    with_entries = cursor.fetchone()[0]
    print(f"entriesデータがあるレース数: {with_entries:,}")

    conn.close()
    return complete_before


def analyze_patterns_large_scale():
    """
    大規模データでパターン分析を実行

    PRE順位はentriesのwin_rateから計算
    """
    conn = get_connection()
    cursor = conn.cursor()

    print("\n" + "=" * 80)
    print("大規模パターン分析開始")
    print("=" * 80)

    # 分析に必要なデータを一括取得
    query = """
    WITH valid_races AS (
        -- 2020-2024年で結果があるレース
        SELECT DISTINCT r.id as race_id, r.race_date
        FROM races r
        INNER JOIN results res ON r.id = res.race_id
        WHERE r.race_date >= '2020-01-01'
          AND r.race_date <= '2024-12-31'
          AND res.is_invalid = 0
    ),
    race_data AS (
        SELECT
            vr.race_id,
            vr.race_date,
            rd.pit_number,
            rd.exhibition_time,
            rd.st_time,
            e.win_rate,
            e.motor_second_rate,
            res.rank as actual_rank
        FROM valid_races vr
        INNER JOIN race_details rd ON vr.race_id = rd.race_id
        INNER JOIN entries e ON vr.race_id = e.race_id AND rd.pit_number = e.pit_number
        INNER JOIN results res ON vr.race_id = res.race_id AND rd.pit_number = res.pit_number
        WHERE rd.exhibition_time IS NOT NULL
          AND rd.st_time IS NOT NULL
          AND e.win_rate IS NOT NULL
    )
    SELECT * FROM race_data
    ORDER BY race_id, pit_number
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    print(f"取得したレコード数: {len(rows):,}")

    # レースごとにグループ化
    races = defaultdict(list)
    for row in rows:
        race_id = row[0]
        races[race_id].append({
            'race_date': row[1],
            'pit_number': row[2],
            'exhibition_time': row[3],
            'st_time': row[4],
            'win_rate': row[5],
            'motor_2rate': row[6],
            'actual_rank': row[7]
        })

    # 6艇すべて揃っているレースのみ
    valid_races = {k: v for k, v in races.items() if len(v) == 6}
    print(f"分析対象レース数（6艇揃い）: {len(valid_races):,}")

    # 各レースについてランク情報を計算
    for race_id, boats in valid_races.items():
        # PRE順位（勝率ベース、高い順）
        boats_sorted = sorted(boats, key=lambda x: x['win_rate'], reverse=True)
        for rank, boat in enumerate(boats_sorted, 1):
            boat['pre_rank'] = rank

        # 展示タイム順位（低い順）
        boats_sorted = sorted(boats, key=lambda x: x['exhibition_time'])
        for rank, boat in enumerate(boats_sorted, 1):
            boat['ex_rank'] = rank

        # ST順位（0に近い順）
        boats_sorted = sorted(boats, key=lambda x: abs(boat['st_time']))
        for rank, boat in enumerate(boats_sorted, 1):
            boat['st_rank'] = rank

    # パターン定義
    all_patterns = [
        # 1着用パターン
        {'name': 'pre1_st1', 'description': 'PRE1位 & ST1位', 'multiplier': 1.411, 'target_rank': 1,
         'condition': lambda b: b['pre_rank'] == 1 and b['st_rank'] == 1},
        {'name': 'pre1_ex1', 'description': 'PRE1位 & 展示1位', 'multiplier': 1.286, 'target_rank': 1,
         'condition': lambda b: b['pre_rank'] == 1 and b['ex_rank'] == 1},
        {'name': 'pre1_ex1_3_st1_3', 'description': 'PRE1位 & 展示1-3位 & ST1-3位', 'multiplier': 1.328, 'target_rank': 1,
         'condition': lambda b: b['pre_rank'] == 1 and b['ex_rank'] <= 3 and b['st_rank'] <= 3},
        {'name': 'pre1_st1_3', 'description': 'PRE1位 & ST1-3位', 'multiplier': 1.310, 'target_rank': 1,
         'condition': lambda b: b['pre_rank'] == 1 and b['st_rank'] <= 3},

        # 2着用パターン
        {'name': 'pre2_3_ex1_2', 'description': 'PRE2-3位 & 展示1-2位', 'multiplier': 1.084, 'target_rank': 2,
         'condition': lambda b: 2 <= b['pre_rank'] <= 3 and b['ex_rank'] <= 2},
        {'name': 'pre2_ex1_3_st1_3', 'description': 'PRE2位 & 展示1-3位 & ST1-3位', 'multiplier': 1.081, 'target_rank': 2,
         'condition': lambda b: b['pre_rank'] == 2 and b['ex_rank'] <= 3 and b['st_rank'] <= 3},
        {'name': 'ex1_3_pre2_3', 'description': '展示1-3位 & PRE2-3位', 'multiplier': 1.069, 'target_rank': 2,
         'condition': lambda b: b['ex_rank'] <= 3 and 2 <= b['pre_rank'] <= 3},
        {'name': 'pre2_st1_3', 'description': 'PRE2位 & ST1-3位', 'multiplier': 1.064, 'target_rank': 2,
         'condition': lambda b: b['pre_rank'] == 2 and b['st_rank'] <= 3},
        {'name': 'pre2_ex1_3', 'description': 'PRE2位 & 展示1-3位', 'multiplier': 1.063, 'target_rank': 2,
         'condition': lambda b: b['pre_rank'] == 2 and b['ex_rank'] <= 3},
        {'name': 'ex_rank_2', 'description': '展示2位', 'multiplier': 1.035, 'target_rank': 2,
         'condition': lambda b: b['ex_rank'] == 2},
        {'name': 'st_rank_2_3', 'description': 'ST2-3位', 'multiplier': 1.034, 'target_rank': 2,
         'condition': lambda b: 2 <= b['st_rank'] <= 3},

        # 3着用パターン
        {'name': 'pre3_4_ex2_4', 'description': 'PRE3-4位 & 展示2-4位', 'multiplier': 1.032, 'target_rank': 3,
         'condition': lambda b: 3 <= b['pre_rank'] <= 4 and 2 <= b['ex_rank'] <= 4},
        {'name': 'pre3_ex1_3', 'description': 'PRE3位 & 展示1-3位', 'multiplier': 1.031, 'target_rank': 3,
         'condition': lambda b: b['pre_rank'] == 3 and b['ex_rank'] <= 3},
        {'name': 'outer_st1_2', 'description': 'アウトコース(4-6枠) & ST1-2位', 'multiplier': 1.022, 'target_rank': 3,
         'condition': lambda b: b['pit_number'] >= 4 and b['st_rank'] <= 2},
        {'name': 'pre3_4_ex1_3_st1_3', 'description': 'PRE3-4位 & 展示1-3位 & ST1-3位', 'multiplier': 1.020, 'target_rank': 3,
         'condition': lambda b: 3 <= b['pre_rank'] <= 4 and b['ex_rank'] <= 3 and b['st_rank'] <= 3},

        # 3着以内用パターン
        {'name': 'pre1_3_st1_3', 'description': 'PRE1-3位 & ST1-3位', 'multiplier': 1.130, 'target_rank': 'top3',
         'condition': lambda b: b['pre_rank'] <= 3 and b['st_rank'] <= 3},
        {'name': 'pre1_3_ex1_3', 'description': 'PRE1-3位 & 展示1-3位', 'multiplier': 1.123, 'target_rank': 'top3',
         'condition': lambda b: b['pre_rank'] <= 3 and b['ex_rank'] <= 3},
        {'name': 'ex1_3_st1_3', 'description': '展示1-3位 & ST1-3位', 'multiplier': 1.108, 'target_rank': 'top3',
         'condition': lambda b: b['ex_rank'] <= 3 and b['st_rank'] <= 3},
        {'name': 'pre1_4_ex1_2', 'description': 'PRE1-4位 & 展示1-2位', 'multiplier': 1.104, 'target_rank': 'top3',
         'condition': lambda b: b['pre_rank'] <= 4 and b['ex_rank'] <= 2},
        {'name': 'ex_rank_1_2', 'description': '展示1-2位', 'multiplier': 1.051, 'target_rank': 'top3',
         'condition': lambda b: b['ex_rank'] <= 2},
    ]

    # パターン統計の初期化
    pattern_stats = {}
    for p in all_patterns:
        pattern_stats[p['name']] = {
            'description': p['description'],
            'multiplier': p['multiplier'],
            'target_rank': p['target_rank'],
            'match_count': 0,
            'hit_count': 0,
            'by_year': {str(y): {'match': 0, 'hit': 0} for y in range(2020, 2025)},
        }

    # ベースライン統計
    baseline_stats = {
        '1st': {'total': 0, 'hit': 0},
        '2nd': {'total': 0, 'hit': 0},
        '3rd': {'total': 0, 'hit': 0},
        'top3': {'total': 0, 'hit': 0},
        'by_year': {str(y): {'total': 0, 'hit': 0} for y in range(2020, 2025)},
    }

    # 各レースを処理
    for race_id, boats in valid_races.items():
        year = boats[0]['race_date'][:4]

        for boat in boats:
            pre_rank = boat['pre_rank']
            actual_rank = boat['actual_rank']

            # ベースライン（PRE順位と実際の順位の一致）
            if pre_rank == 1:
                baseline_stats['1st']['total'] += 1
                baseline_stats['by_year'][year]['total'] += 1
                if actual_rank == '1':
                    baseline_stats['1st']['hit'] += 1
                    baseline_stats['by_year'][year]['hit'] += 1

            if pre_rank == 2:
                baseline_stats['2nd']['total'] += 1
                if actual_rank == '2':
                    baseline_stats['2nd']['hit'] += 1

            if pre_rank == 3:
                baseline_stats['3rd']['total'] += 1
                if actual_rank == '3':
                    baseline_stats['3rd']['hit'] += 1

            if pre_rank <= 3:
                baseline_stats['top3']['total'] += 1
                if actual_rank in ['1', '2', '3']:
                    baseline_stats['top3']['hit'] += 1

            # 各パターンをチェック
            for p in all_patterns:
                try:
                    if p['condition'](boat):
                        # パターンにマッチ
                        pattern_stats[p['name']]['match_count'] += 1
                        pattern_stats[p['name']]['by_year'][year]['match'] += 1

                        # 的中判定
                        target = p['target_rank']
                        if target == 1 and actual_rank == '1':
                            pattern_stats[p['name']]['hit_count'] += 1
                            pattern_stats[p['name']]['by_year'][year]['hit'] += 1
                        elif target == 2 and actual_rank == '2':
                            pattern_stats[p['name']]['hit_count'] += 1
                            pattern_stats[p['name']]['by_year'][year]['hit'] += 1
                        elif target == 3 and actual_rank == '3':
                            pattern_stats[p['name']]['hit_count'] += 1
                            pattern_stats[p['name']]['by_year'][year]['hit'] += 1
                        elif target == 'top3' and actual_rank in ['1', '2', '3']:
                            pattern_stats[p['name']]['hit_count'] += 1
                            pattern_stats[p['name']]['by_year'][year]['hit'] += 1
                except Exception:
                    pass

    conn.close()
    return pattern_stats, baseline_stats


def calculate_p_value(hit_rate, baseline_rate, n):
    """二項検定のp値を計算（簡易版）"""
    if n == 0:
        return 1.0

    if baseline_rate == 0 or baseline_rate == 1:
        return 1.0

    se = math.sqrt(baseline_rate * (1 - baseline_rate) / n)
    if se == 0:
        return 1.0

    z = (hit_rate - baseline_rate) / se

    # 標準正規分布のp値（近似）
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))

    return p


def generate_report(pattern_stats, baseline_stats):
    """分析レポートを生成"""

    report = []
    report.append("# パターンボーナス効果分析レポート")
    report.append(f"\n**生成日時**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"**分析期間**: 2020年1月〜2024年12月")
    report.append(f"**分析方法**: race_detailsの展示タイム・ST情報とentriesの勝率から各ランクを計算")
    report.append("")

    # ベースライン
    report.append("## 1. ベースライン（パターン非適用時の的中率）")
    report.append("")
    report.append("PRE順位（勝率による予測順位）と実際の着順の一致率をベースラインとして算出。")
    report.append("")
    report.append("| 予測対象 | 的中数 | 総数 | 的中率 |")
    report.append("|----------|--------|------|--------|")

    for target, label in [('1st', '1着予測（PRE1位の1着率）'), ('2nd', '2着予測（PRE2位の2着率）'),
                          ('3rd', '3着予測（PRE3位の3着率）'), ('top3', '3着以内予測（PRE1-3位の3着以内率）')]:
        stats = baseline_stats[target]
        rate = stats['hit'] / stats['total'] if stats['total'] > 0 else 0
        report.append(f"| {label} | {stats['hit']:,} | {stats['total']:,} | {rate:.2%} |")

    # 年別ベースライン
    report.append("\n### 年別ベースライン（1着予測）")
    report.append("")
    report.append("| 年 | 的中数 | 総数 | 的中率 |")
    report.append("|----|--------|------|--------|")

    for year in ['2020', '2021', '2022', '2023', '2024']:
        stats = baseline_stats['by_year'][year]
        rate = stats['hit'] / stats['total'] if stats['total'] > 0 else 0
        report.append(f"| {year} | {stats['hit']:,} | {stats['total']:,} | {rate:.2%} |")

    # ベースライン的中率を取得
    baseline_1st = baseline_stats['1st']['hit'] / baseline_stats['1st']['total'] if baseline_stats['1st']['total'] > 0 else 0
    baseline_2nd = baseline_stats['2nd']['hit'] / baseline_stats['2nd']['total'] if baseline_stats['2nd']['total'] > 0 else 0
    baseline_3rd = baseline_stats['3rd']['hit'] / baseline_stats['3rd']['total'] if baseline_stats['3rd']['total'] > 0 else 0
    baseline_top3 = baseline_stats['top3']['hit'] / baseline_stats['top3']['total'] if baseline_stats['top3']['total'] > 0 else 0

    def get_baseline_for_target(target):
        if target == 1:
            return baseline_1st
        elif target == 2:
            return baseline_2nd
        elif target == 3:
            return baseline_3rd
        else:
            return baseline_top3

    # パターンごとの効果を計算
    pattern_effects = []
    for name, stats in pattern_stats.items():
        if stats['match_count'] > 0:
            hit_rate = stats['hit_count'] / stats['match_count']
            baseline = get_baseline_for_target(stats['target_rank'])
            effect = hit_rate - baseline
            p_value = calculate_p_value(hit_rate, baseline, stats['match_count'])

            pattern_effects.append({
                'name': name,
                'description': stats['description'],
                'multiplier': stats['multiplier'],
                'target_rank': stats['target_rank'],
                'match_count': stats['match_count'],
                'hit_count': stats['hit_count'],
                'hit_rate': hit_rate,
                'baseline': baseline,
                'effect': effect,
                'p_value': p_value,
                'by_year': stats['by_year']
            })

    # 効果の高い順にソート
    pattern_effects.sort(key=lambda x: x['effect'], reverse=True)

    # パターン別効果一覧
    report.append("\n## 2. パターン別効果一覧（効果の高い順）")
    report.append("")
    report.append("| パターン名 | 説明 | 倍率 | 対象 | サンプル数 | 的中率 | ベースライン | 効果 | p値 | 判定 |")
    report.append("|------------|------|------|------|------------|--------|--------------|------|-----|------|")

    for p in pattern_effects:
        target_label = f"{p['target_rank']}着" if isinstance(p['target_rank'], int) else "3着以内"
        effect_str = f"+{p['effect']:.1%}" if p['effect'] >= 0 else f"{p['effect']:.1%}"

        # 判定
        if p['p_value'] < 0.01 and p['effect'] > 0.02:
            judgment = "**有効**"
        elif p['p_value'] < 0.01 and p['effect'] < -0.02:
            judgment = "**逆効果**"
        elif p['p_value'] < 0.05 and p['effect'] > 0:
            judgment = "有効(弱)"
        elif p['p_value'] < 0.05 and p['effect'] < 0:
            judgment = "逆効果(弱)"
        elif p['match_count'] < 1000:
            judgment = "サンプル不足"
        else:
            judgment = "効果なし"

        report.append(f"| {p['name']} | {p['description']} | {p['multiplier']:.3f} | {target_label} | {p['match_count']:,} | {p['hit_rate']:.2%} | {p['baseline']:.2%} | {effect_str} | {p['p_value']:.4f} | {judgment} |")

    # 年別推移（主要パターン）
    report.append("\n## 3. 年別効果推移（1着用パターン）")
    report.append("")
    report.append("各パターンの年別的中率の推移を確認します。")
    report.append("")

    first_patterns = [p for p in pattern_effects if p['target_rank'] == 1]

    report.append("| パターン | 2020年 | 2021年 | 2022年 | 2023年 | 2024年 | 全期間 |")
    report.append("|----------|--------|--------|--------|--------|--------|--------|")

    for p in first_patterns:
        row = [p['name']]
        for year in ['2020', '2021', '2022', '2023', '2024']:
            year_stats = p['by_year'][year]
            if year_stats['match'] > 0:
                rate = year_stats['hit'] / year_stats['match']
                row.append(f"{rate:.1%} (n={year_stats['match']})")
            else:
                row.append("-")
        row.append(f"{p['hit_rate']:.1%}")
        report.append("| " + " | ".join(row) + " |")

    # 逆効果パターン
    report.append("\n## 4. 逆効果パターンの特定")
    report.append("")

    negative_patterns = [p for p in pattern_effects if p['effect'] < 0]

    if negative_patterns:
        report.append("### 統計的に有意な逆効果パターン")
        report.append("")

        significant_negative = [p for p in negative_patterns if p['p_value'] < 0.01]
        if significant_negative:
            for p in significant_negative:
                report.append(f"- **{p['name']}** ({p['description']})")
                report.append(f"  - 的中率: {p['hit_rate']:.2%} vs ベースライン: {p['baseline']:.2%}")
                report.append(f"  - 効果: {p['effect']:.1%} (p値: {p['p_value']:.4f})")
                report.append(f"  - サンプル数: {p['match_count']:,}")
                report.append(f"  - 現在の倍率: {p['multiplier']:.3f}")
                report.append("")
        else:
            report.append("p < 0.01 の有意な逆効果パターンはありません。")
            report.append("")

        report.append("### 軽度の逆効果パターン（p < 0.05）")
        report.append("")

        weak_negative = [p for p in negative_patterns if 0.01 <= p['p_value'] < 0.05]
        if weak_negative:
            for p in weak_negative:
                report.append(f"- **{p['name']}**: 効果 {p['effect']:.1%} (p={p['p_value']:.3f}, n={p['match_count']:,})")
        else:
            report.append("軽度の逆効果パターンはありません。")

    # 効果が不明確なパターン
    report.append("\n### 効果が不明確なパターン（|効果| < 2%）")
    report.append("")

    marginal = [p for p in pattern_effects if abs(p['effect']) < 0.02 and p['match_count'] >= 1000]
    if marginal:
        for p in marginal:
            report.append(f"- **{p['name']}**: 効果 {p['effect']:.1%} (倍率 {p['multiplier']:.3f})")
    else:
        report.append("該当するパターンはありません。")

    # 改善提案
    report.append("\n## 5. 具体的な改善提案")
    report.append("")

    # 無効化すべきパターン
    report.append("### 5.1 無効化を推奨するパターン")
    report.append("")

    disable_patterns = [p for p in pattern_effects if p['effect'] < -0.02 and p['p_value'] < 0.05]
    if disable_patterns:
        for p in disable_patterns:
            report.append(f"1. **{p['name']}** ({p['description']})")
            report.append(f"   - 理由: ベースラインより {abs(p['effect']):.1%} 低い的中率（p={p['p_value']:.4f}）")
            report.append(f"   - 現在の倍率: {p['multiplier']:.3f}")
            report.append(f"   - 提案: 倍率を1.0に設定するか、パターン自体を無効化")
            report.append("")
    else:
        report.append("無効化を推奨するパターンはありません。")
        report.append("")

    # 倍率下方修正
    report.append("### 5.2 倍率の下方修正を推奨するパターン")
    report.append("")

    overrated = [p for p in pattern_effects if p['effect'] > 0 and p['multiplier'] > 1.0 + p['effect'] * 2]
    if overrated:
        for p in overrated:
            recommended = 1.0 + max(0, p['effect'] * 1.5)  # 効果の1.5倍程度を推奨
            report.append(f"1. **{p['name']}**: 現在 {p['multiplier']:.3f} → 推奨 {recommended:.3f}")
            report.append(f"   - 実効果: +{p['effect']:.1%}、現在の倍率が効果に対して過大")
    else:
        report.append("該当するパターンはありません。")
    report.append("")

    # 有効なパターン
    report.append("### 5.3 有効と確認されたパターン（維持推奨）")
    report.append("")

    effective = [p for p in pattern_effects if p['effect'] > 0.02 and p['p_value'] < 0.01]
    if effective:
        for p in effective:
            report.append(f"- **{p['name']}** ({p['description']}): +{p['effect']:.1%} (p={p['p_value']:.4f})")
    else:
        report.append("統計的に有意な有効パターンはありません。")

    # サマリー
    report.append("\n## 6. サマリー")
    report.append("")

    effective_count = len([p for p in pattern_effects if p['effect'] > 0.02 and p['p_value'] < 0.05])
    negative_count = len([p for p in pattern_effects if p['effect'] < -0.02 and p['p_value'] < 0.05])
    neutral_count = len(pattern_effects) - effective_count - negative_count

    report.append(f"- **統計的に有効なパターン**: {effective_count} 個")
    report.append(f"- **統計的に逆効果のパターン**: {negative_count} 個")
    report.append(f"- **効果不明確/中立**: {neutral_count} 個")
    report.append("")

    total_samples = sum(p['match_count'] for p in pattern_effects)
    report.append(f"**総サンプル数**: {total_samples:,}")
    report.append("")

    if negative_count > 0:
        report.append("### 緊急対応推奨")
        report.append("")
        report.append("以下のパターンは統計的に逆効果が確認されています。早急な対応を推奨します：")
        report.append("")
        for p in [p for p in pattern_effects if p['effect'] < -0.02 and p['p_value'] < 0.05]:
            report.append(f"- {p['name']}: 効果 {p['effect']:.1%}")
    else:
        report.append("現時点で緊急対応が必要なパターンはありません。")

    return "\n".join(report)


def main():
    """メイン処理"""
    print("パターンボーナス効果分析 v2 を開始します...")
    print("")

    # データ利用可能性チェック
    check_data_availability()

    # 大規模分析実行
    pattern_stats, baseline_stats = analyze_patterns_large_scale()

    # レポート生成
    report = generate_report(pattern_stats, baseline_stats)

    # ファイルに保存
    output_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "docs",
        "PATTERN_EFFECTIVENESS_ANALYSIS_20251217.md"
    )

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"\n\nレポートを保存しました: {output_path}")


if __name__ == "__main__":
    main()
