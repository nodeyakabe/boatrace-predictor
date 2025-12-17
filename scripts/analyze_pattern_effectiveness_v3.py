#!/usr/bin/env python
"""
パターンボーナス効果分析スクリプト v3

信頼度別の分析を追加した最終版
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


def analyze_with_confidence():
    """信頼度を含めた分析"""
    conn = get_connection()
    cursor = conn.cursor()

    print("=" * 80)
    print("パターン効果分析（信頼度別）")
    print("=" * 80)

    # before予測データ + race_details + results を結合
    query = """
    WITH valid_predictions AS (
        SELECT
            rp.race_id,
            rp.pit_number,
            rp.rank_prediction,
            rp.confidence,
            rp.total_score
        FROM race_predictions rp
        INNER JOIN races r ON rp.race_id = r.id
        WHERE rp.prediction_type = 'before'
          AND r.race_date >= '2020-01-01'
          AND r.race_date <= '2024-12-31'
    ),
    combined_data AS (
        SELECT
            vp.race_id,
            vp.pit_number,
            vp.rank_prediction as pre_rank,
            vp.confidence,
            rd.exhibition_time,
            rd.st_time,
            res.rank as actual_rank
        FROM valid_predictions vp
        INNER JOIN race_details rd ON vp.race_id = rd.race_id AND vp.pit_number = rd.pit_number
        INNER JOIN results res ON vp.race_id = res.race_id AND vp.pit_number = res.pit_number
        WHERE rd.exhibition_time IS NOT NULL
          AND rd.st_time IS NOT NULL
          AND res.is_invalid = 0
    )
    SELECT * FROM combined_data
    ORDER BY race_id, pit_number
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    print(f"取得レコード数: {len(rows):,}")

    # レースごとにグループ化
    races = defaultdict(list)
    for row in rows:
        race_id = row[0]
        races[race_id].append({
            'pit_number': row[1],
            'pre_rank': row[2],
            'confidence': row[3],
            'exhibition_time': row[4],
            'st_time': row[5],
            'actual_rank': row[6]
        })

    # 6艇揃ったレースのみ
    valid_races = {k: v for k, v in races.items() if len(v) == 6}
    print(f"有効レース数: {len(valid_races):,}")

    # ランク計算
    for race_id, boats in valid_races.items():
        # 展示タイム順位
        boats_sorted = sorted(boats, key=lambda x: x['exhibition_time'])
        for rank, boat in enumerate(boats_sorted, 1):
            boat['ex_rank'] = rank

        # ST順位
        boats_sorted = sorted(boats, key=lambda x: abs(boat['st_time']))
        for rank, boat in enumerate(boats_sorted, 1):
            boat['st_rank'] = rank

    conn.close()
    return valid_races


def analyze_patterns_with_confidence(valid_races):
    """信頼度別のパターン分析"""

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

    # 信頼度リスト
    confidences = ['A', 'B', 'C', 'D', 'E']

    # 統計初期化
    pattern_stats = {}
    for p in all_patterns:
        pattern_stats[p['name']] = {
            'description': p['description'],
            'multiplier': p['multiplier'],
            'target_rank': p['target_rank'],
            'total': {'match': 0, 'hit': 0},
            'by_confidence': {c: {'match': 0, 'hit': 0} for c in confidences}
        }

    # ベースライン統計（PRE1位の1着率など）
    baseline_stats = {
        '1st': {'total': {'match': 0, 'hit': 0}, 'by_confidence': {c: {'match': 0, 'hit': 0} for c in confidences}},
        '2nd': {'total': {'match': 0, 'hit': 0}, 'by_confidence': {c: {'match': 0, 'hit': 0} for c in confidences}},
        '3rd': {'total': {'match': 0, 'hit': 0}, 'by_confidence': {c: {'match': 0, 'hit': 0} for c in confidences}},
        'top3': {'total': {'match': 0, 'hit': 0}, 'by_confidence': {c: {'match': 0, 'hit': 0} for c in confidences}},
    }

    # 各レースを処理
    for race_id, boats in valid_races.items():
        # 信頼度を取得（1着予測から）
        top_pred = next((b for b in boats if b['pre_rank'] == 1), None)
        confidence = top_pred['confidence'] if top_pred else 'C'

        for boat in boats:
            pre_rank = boat['pre_rank']
            actual_rank = boat['actual_rank']

            # ベースライン更新
            if pre_rank == 1:
                baseline_stats['1st']['total']['match'] += 1
                baseline_stats['1st']['by_confidence'][confidence]['match'] += 1
                if actual_rank == '1':
                    baseline_stats['1st']['total']['hit'] += 1
                    baseline_stats['1st']['by_confidence'][confidence]['hit'] += 1

            if pre_rank == 2:
                baseline_stats['2nd']['total']['match'] += 1
                baseline_stats['2nd']['by_confidence'][confidence]['match'] += 1
                if actual_rank == '2':
                    baseline_stats['2nd']['total']['hit'] += 1
                    baseline_stats['2nd']['by_confidence'][confidence]['hit'] += 1

            if pre_rank == 3:
                baseline_stats['3rd']['total']['match'] += 1
                baseline_stats['3rd']['by_confidence'][confidence]['match'] += 1
                if actual_rank == '3':
                    baseline_stats['3rd']['total']['hit'] += 1
                    baseline_stats['3rd']['by_confidence'][confidence]['hit'] += 1

            if pre_rank <= 3:
                baseline_stats['top3']['total']['match'] += 1
                baseline_stats['top3']['by_confidence'][confidence]['match'] += 1
                if actual_rank in ['1', '2', '3']:
                    baseline_stats['top3']['total']['hit'] += 1
                    baseline_stats['top3']['by_confidence'][confidence]['hit'] += 1

            # 各パターンをチェック
            for p in all_patterns:
                try:
                    if p['condition'](boat):
                        target = p['target_rank']
                        pattern_stats[p['name']]['total']['match'] += 1
                        pattern_stats[p['name']]['by_confidence'][confidence]['match'] += 1

                        # 的中判定
                        hit = False
                        if target == 1 and actual_rank == '1':
                            hit = True
                        elif target == 2 and actual_rank == '2':
                            hit = True
                        elif target == 3 and actual_rank == '3':
                            hit = True
                        elif target == 'top3' and actual_rank in ['1', '2', '3']:
                            hit = True

                        if hit:
                            pattern_stats[p['name']]['total']['hit'] += 1
                            pattern_stats[p['name']]['by_confidence'][confidence]['hit'] += 1
                except Exception:
                    pass

    return pattern_stats, baseline_stats


def calculate_p_value(hit_rate, baseline_rate, n):
    """二項検定のp値を計算"""
    if n == 0:
        return 1.0
    if baseline_rate == 0 or baseline_rate == 1:
        return 1.0

    se = math.sqrt(baseline_rate * (1 - baseline_rate) / n)
    if se == 0:
        return 1.0

    z = (hit_rate - baseline_rate) / se
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return p


def generate_final_report(pattern_stats, baseline_stats):
    """最終レポート生成"""

    report = []
    report.append("# パターンボーナス効果詳細分析レポート")
    report.append(f"\n**生成日時**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"**分析期間**: 2020年1月〜2024年12月")
    report.append(f"**データソース**: before予測 + race_details + results")
    report.append("")

    # セクション1: ベースライン
    report.append("## 1. ベースライン（パターン非適用時の的中率）")
    report.append("")
    report.append("### 全体ベースライン")
    report.append("")
    report.append("| 予測対象 | 的中数 | 総数 | 的中率 |")
    report.append("|----------|--------|------|--------|")

    for target, label in [('1st', '1着予測'), ('2nd', '2着予測'), ('3rd', '3着予測'), ('top3', '3着以内予測')]:
        stats = baseline_stats[target]['total']
        rate = stats['hit'] / stats['match'] if stats['match'] > 0 else 0
        report.append(f"| {label} | {stats['hit']:,} | {stats['match']:,} | {rate:.2%} |")

    # 信頼度別ベースライン
    report.append("\n### 信頼度別ベースライン（1着予測）")
    report.append("")
    report.append("| 信頼度 | 的中数 | 総数 | 的中率 |")
    report.append("|--------|--------|------|--------|")

    for conf in ['A', 'B', 'C', 'D', 'E']:
        stats = baseline_stats['1st']['by_confidence'][conf]
        rate = stats['hit'] / stats['match'] if stats['match'] > 0 else 0
        report.append(f"| {conf} | {stats['hit']:,} | {stats['match']:,} | {rate:.2%} |")

    # ベースライン取得用関数
    def get_baseline(target):
        stats = baseline_stats[target]['total']
        return stats['hit'] / stats['match'] if stats['match'] > 0 else 0

    def get_baseline_by_conf(target, conf):
        stats = baseline_stats[target]['by_confidence'][conf]
        return stats['hit'] / stats['match'] if stats['match'] > 0 else 0

    # セクション2: パターン別効果
    report.append("\n## 2. パターン別効果一覧（効果の高い順）")
    report.append("")

    pattern_effects = []
    for name, stats in pattern_stats.items():
        total = stats['total']
        if total['match'] > 0:
            hit_rate = total['hit'] / total['match']
            target_key = '1st' if stats['target_rank'] == 1 else \
                         '2nd' if stats['target_rank'] == 2 else \
                         '3rd' if stats['target_rank'] == 3 else 'top3'
            baseline = get_baseline(target_key)
            effect = hit_rate - baseline
            p_value = calculate_p_value(hit_rate, baseline, total['match'])

            pattern_effects.append({
                'name': name,
                'description': stats['description'],
                'multiplier': stats['multiplier'],
                'target_rank': stats['target_rank'],
                'match_count': total['match'],
                'hit_count': total['hit'],
                'hit_rate': hit_rate,
                'baseline': baseline,
                'effect': effect,
                'p_value': p_value,
                'by_confidence': stats['by_confidence']
            })

    pattern_effects.sort(key=lambda x: x['effect'], reverse=True)

    report.append("| パターン名 | 説明 | 倍率 | 対象 | サンプル数 | 的中率 | ベースライン | 効果 | p値 | 判定 |")
    report.append("|------------|------|------|------|------------|--------|--------------|------|-----|------|")

    for p in pattern_effects:
        target_label = f"{p['target_rank']}着" if isinstance(p['target_rank'], int) else "3着以内"
        effect_str = f"+{p['effect']:.1%}" if p['effect'] >= 0 else f"{p['effect']:.1%}"

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

    # セクション3: 信頼度×パターンのクロス分析
    report.append("\n## 3. 信頼度×パターンのクロス分析")
    report.append("")
    report.append("### 1着用パターン")
    report.append("")

    first_patterns = [p for p in pattern_effects if p['target_rank'] == 1]

    report.append("| パターン | 信頼度A | 信頼度B | 信頼度C | 信頼度D | 信頼度E |")
    report.append("|----------|---------|---------|---------|---------|---------|")

    for p in first_patterns:
        row = [p['name']]
        for conf in ['A', 'B', 'C', 'D', 'E']:
            conf_stats = p['by_confidence'][conf]
            if conf_stats['match'] >= 30:
                rate = conf_stats['hit'] / conf_stats['match']
                baseline_conf = get_baseline_by_conf('1st', conf)
                effect = rate - baseline_conf
                effect_str = f"+{effect:.0%}" if effect >= 0 else f"{effect:.0%}"
                row.append(f"{rate:.1%} ({effect_str}, n={conf_stats['match']})")
            else:
                row.append(f"- (n={conf_stats['match']})")
        report.append("| " + " | ".join(row) + " |")

    report.append("\n### 2着用パターン")
    report.append("")

    second_patterns = [p for p in pattern_effects if p['target_rank'] == 2]

    report.append("| パターン | 信頼度A | 信頼度B | 信頼度C | 信頼度D | 信頼度E |")
    report.append("|----------|---------|---------|---------|---------|---------|")

    for p in second_patterns:
        row = [p['name']]
        for conf in ['A', 'B', 'C', 'D', 'E']:
            conf_stats = p['by_confidence'][conf]
            if conf_stats['match'] >= 30:
                rate = conf_stats['hit'] / conf_stats['match']
                baseline_conf = get_baseline_by_conf('2nd', conf)
                effect = rate - baseline_conf
                effect_str = f"+{effect:.0%}" if effect >= 0 else f"{effect:.0%}"
                row.append(f"{rate:.1%} ({effect_str}, n={conf_stats['match']})")
            else:
                row.append(f"- (n={conf_stats['match']})")
        report.append("| " + " | ".join(row) + " |")

    report.append("\n### 3着用パターン")
    report.append("")

    third_patterns = [p for p in pattern_effects if p['target_rank'] == 3]

    report.append("| パターン | 信頼度A | 信頼度B | 信頼度C | 信頼度D | 信頼度E |")
    report.append("|----------|---------|---------|---------|---------|---------|")

    for p in third_patterns:
        row = [p['name']]
        for conf in ['A', 'B', 'C', 'D', 'E']:
            conf_stats = p['by_confidence'][conf]
            if conf_stats['match'] >= 30:
                rate = conf_stats['hit'] / conf_stats['match']
                baseline_conf = get_baseline_by_conf('3rd', conf)
                effect = rate - baseline_conf
                effect_str = f"+{effect:.0%}" if effect >= 0 else f"{effect:.0%}"
                row.append(f"{rate:.1%} ({effect_str}, n={conf_stats['match']})")
            else:
                row.append(f"- (n={conf_stats['match']})")
        report.append("| " + " | ".join(row) + " |")

    report.append("\n### 3着以内用パターン")
    report.append("")

    top3_patterns = [p for p in pattern_effects if p['target_rank'] == 'top3']

    report.append("| パターン | 信頼度A | 信頼度B | 信頼度C | 信頼度D | 信頼度E |")
    report.append("|----------|---------|---------|---------|---------|---------|")

    for p in top3_patterns:
        row = [p['name']]
        for conf in ['A', 'B', 'C', 'D', 'E']:
            conf_stats = p['by_confidence'][conf]
            if conf_stats['match'] >= 30:
                rate = conf_stats['hit'] / conf_stats['match']
                baseline_conf = get_baseline_by_conf('top3', conf)
                effect = rate - baseline_conf
                effect_str = f"+{effect:.0%}" if effect >= 0 else f"{effect:.0%}"
                row.append(f"{rate:.1%} ({effect_str}, n={conf_stats['match']})")
            else:
                row.append(f"- (n={conf_stats['match']})")
        report.append("| " + " | ".join(row) + " |")

    # セクション4: 逆効果パターン
    report.append("\n## 4. 逆効果パターンの特定")
    report.append("")

    # 全体で逆効果
    report.append("### 4.1 全体で逆効果のパターン")
    report.append("")

    negative_all = [p for p in pattern_effects if p['effect'] < -0.01 and p['p_value'] < 0.05]
    if negative_all:
        for p in negative_all:
            report.append(f"- **{p['name']}** ({p['description']})")
            report.append(f"  - 的中率: {p['hit_rate']:.2%} vs ベースライン: {p['baseline']:.2%}")
            report.append(f"  - 効果: {p['effect']:.1%} (p値: {p['p_value']:.4f})")
            report.append(f"  - サンプル数: {p['match_count']:,}")
            report.append(f"  - 現在の倍率: {p['multiplier']:.3f}")
            report.append("")
    else:
        report.append("全体で逆効果のパターンはありません。")

    # 特定信頼度で逆効果
    report.append("\n### 4.2 特定信頼度で逆効果のパターン")
    report.append("")

    negative_by_conf = []
    for p in pattern_effects:
        target_key = '1st' if p['target_rank'] == 1 else \
                     '2nd' if p['target_rank'] == 2 else \
                     '3rd' if p['target_rank'] == 3 else 'top3'
        for conf in ['A', 'B', 'C', 'D', 'E']:
            conf_stats = p['by_confidence'][conf]
            if conf_stats['match'] >= 50:
                rate = conf_stats['hit'] / conf_stats['match']
                baseline_conf = get_baseline_by_conf(target_key, conf)
                effect = rate - baseline_conf
                if effect < -0.05:  # 5%以上の逆効果
                    negative_by_conf.append({
                        'name': p['name'],
                        'confidence': conf,
                        'rate': rate,
                        'baseline': baseline_conf,
                        'effect': effect,
                        'n': conf_stats['match']
                    })

    if negative_by_conf:
        # 効果の小さい（逆効果の大きい）順にソート
        negative_by_conf.sort(key=lambda x: x['effect'])
        for item in negative_by_conf[:20]:  # 上位20件のみ表示
            report.append(f"- **{item['name']}** @ 信頼度{item['confidence']}: 的中率 {item['rate']:.1%} vs ベースライン {item['baseline']:.1%} (効果: {item['effect']:.1%}, n={item['n']})")
    else:
        report.append("特定信頼度で大きな逆効果のパターンはありません。")

    # セクション5: 改善提案
    report.append("\n## 5. 具体的な改善提案")
    report.append("")

    report.append("### 5.1 無効化を推奨するパターン")
    report.append("")

    disable_patterns = [p for p in pattern_effects if p['effect'] < -0.02 and p['p_value'] < 0.01]
    if disable_patterns:
        for p in disable_patterns:
            report.append(f"1. **{p['name']}** ({p['description']})")
            report.append(f"   - 理由: ベースラインより {abs(p['effect']):.1%} 低い的中率（p={p['p_value']:.4f}）")
            report.append(f"   - 現在の倍率: {p['multiplier']:.3f}")
            report.append(f"   - 提案: 倍率を1.0に設定するか、パターン自体を無効化")
            report.append("")
    else:
        report.append("無効化を推奨するパターンはありません。")

    report.append("\n### 5.2 信頼度別の適用制限を推奨するパターン")
    report.append("")

    if negative_by_conf:
        # パターンごとにまとめる
        by_pattern = defaultdict(list)
        for item in negative_by_conf:
            by_pattern[item['name']].append(item['confidence'])

        for pattern_name, confs in by_pattern.items():
            report.append(f"- **{pattern_name}**: 信頼度 {', '.join(sorted(set(confs)))} では適用を控える")
    else:
        report.append("信頼度別の制限が必要なパターンはありません。")

    report.append("\n### 5.3 倍率調整を推奨するパターン")
    report.append("")

    # 倍率が効果に対して過大なパターン
    overrated = []
    for p in pattern_effects:
        if p['effect'] > 0:
            # 推奨倍率 = 1 + 効果 * 1.2（控えめに設定）
            recommended = 1.0 + p['effect'] * 1.2
            if p['multiplier'] > recommended + 0.05:  # 5%以上乖離
                overrated.append({
                    'name': p['name'],
                    'description': p['description'],
                    'current': p['multiplier'],
                    'recommended': recommended,
                    'effect': p['effect']
                })

    if overrated:
        overrated.sort(key=lambda x: x['current'] - x['recommended'], reverse=True)
        for item in overrated:
            report.append(f"- **{item['name']}**: 現在 {item['current']:.3f} → 推奨 {item['recommended']:.3f}")
            report.append(f"  - 実効果: +{item['effect']:.1%}（現在の倍率が過大）")
    else:
        report.append("倍率調整が必要なパターンはありません。")

    report.append("\n### 5.4 有効と確認されたパターン（維持推奨）")
    report.append("")

    effective = [p for p in pattern_effects if p['effect'] > 0.03 and p['p_value'] < 0.01]
    if effective:
        effective.sort(key=lambda x: x['effect'], reverse=True)
        for p in effective:
            report.append(f"- **{p['name']}** ({p['description']}): +{p['effect']:.1%} (p={p['p_value']:.4f})")
    else:
        report.append("統計的に有意な有効パターンはありません。")

    # セクション6: サマリー
    report.append("\n## 6. サマリー")
    report.append("")

    effective_count = len([p for p in pattern_effects if p['effect'] > 0.02 and p['p_value'] < 0.01])
    negative_count = len([p for p in pattern_effects if p['effect'] < -0.02 and p['p_value'] < 0.01])
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
        for p in [p for p in pattern_effects if p['effect'] < -0.02 and p['p_value'] < 0.01]:
            report.append(f"- **{p['name']}**: 効果 {p['effect']:.1%}")

    return "\n".join(report)


def main():
    """メイン処理"""
    print("パターンボーナス効果分析 v3 を開始します...")
    print("")

    # データ取得
    valid_races = analyze_with_confidence()

    # 信頼度別分析
    pattern_stats, baseline_stats = analyze_patterns_with_confidence(valid_races)

    # レポート生成
    report = generate_final_report(pattern_stats, baseline_stats)

    # ファイルに保存
    output_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "docs",
        "PATTERN_EFFECTIVENESS_ANALYSIS_20251217.md"
    )

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"\nレポートを保存しました: {output_path}")


if __name__ == "__main__":
    main()
