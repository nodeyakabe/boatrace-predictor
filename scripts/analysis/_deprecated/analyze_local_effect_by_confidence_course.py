# -*- coding: utf-8 -*-
"""
Phase 2-3: 局所的効果検証 - 信頼度×予測コース別分析

目的:
- 信頼度別・予測コース別のROI/的中率を詳細分析
- 全体では効果がなかった施策の局所的有効性を検証
- 最適な購入条件の発見

検証軸:
1. 信頼度（A, B, C, D, E）
2. 予測コース（1-6コース）
3. オッズ帯（20-30, 30-40, 40-50倍）

利用データ: 2020-2025年のbefore予測（約93,000件）
"""

import sys
import sqlite3
import numpy as np
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Tuple
from scipy import stats

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

DB_PATH = ROOT_DIR / "data" / "boatrace.db"


def get_races_with_conditions(
    conn: sqlite3.Connection,
    start_date: str = '2020-01-01',
    end_date: str = '2025-12-31'
) -> List[Dict]:
    """購入条件を満たすレースを取得"""
    cursor = conn.cursor()

    query = '''
        SELECT
            r.id as race_id,
            r.race_date,
            r.venue_code,
            r.race_number,
            rp.confidence,
            rp.top3_combo,
            rp.predicted_course,
            e.racer_rank as course1_rank,
            t.odds,
            res.actual_combo,
            p.amount as payout
        FROM races r
        JOIN (
            SELECT
                race_id,
                confidence,
                GROUP_CONCAT(pit_number, '-') as top3_combo,
                (SELECT pit_number FROM race_predictions
                 WHERE race_id = race_predictions.race_id
                   AND prediction_type = 'before'
                 ORDER BY rank_prediction LIMIT 1) as predicted_course
            FROM race_predictions
            WHERE prediction_type = 'before'
            GROUP BY race_id
        ) rp ON r.id = rp.race_id
        JOIN entries e ON r.id = e.race_id AND e.pit_number = 1
        LEFT JOIN trifecta_odds t ON r.id = t.race_id AND t.combination = rp.top3_combo
        LEFT JOIN (
            SELECT
                race_id,
                GROUP_CONCAT(pit_number, '-') as actual_combo
            FROM results
            WHERE is_invalid = 0 AND rank <= 3
            GROUP BY race_id
        ) res ON r.id = res.race_id
        LEFT JOIN payouts p ON r.id = p.race_id
            AND p.bet_type = 'trifecta'
            AND p.combination = res.actual_combo
        WHERE r.race_date >= ? AND r.race_date <= ?
          AND rp.confidence IN ('C', 'D')
          AND e.racer_rank = 'A1'
          AND t.odds IS NOT NULL
        ORDER BY r.race_date, r.venue_code, r.race_number
    '''

    cursor.execute(query, (start_date, end_date))

    results = []
    for row in cursor.fetchall():
        race_id, race_date, venue_code, race_number = row[0], row[1], row[2], row[3]
        confidence, top3_combo, predicted_course = row[4], row[5], row[6]
        course1_rank, odds, actual_combo, payout = row[7], row[8], row[9], row[10]

        # オッズ範囲チェック（戦略Bの条件）
        bet_amount = 0
        if confidence == 'C':
            if 20 <= odds < 60:
                bet_amount = 400 if odds < 40 else 500
        elif confidence == 'D':
            if 20 <= odds < 50:
                bet_amount = 300

        if bet_amount == 0:
            continue

        # 的中判定
        hit = (top3_combo == actual_combo) if actual_combo else False
        payout_amount = 0.0
        if hit and payout:
            payout_amount = (bet_amount / 100) * payout

        roi = (payout_amount / bet_amount) if bet_amount > 0 else 0.0

        # オッズ帯分類
        if 20 <= odds < 30:
            odds_range = '20-30'
        elif 30 <= odds < 40:
            odds_range = '30-40'
        elif 40 <= odds < 50:
            odds_range = '40-50'
        else:
            odds_range = '50+'

        results.append({
            'race_id': race_id,
            'race_date': race_date,
            'venue_code': venue_code,
            'confidence': confidence,
            'predicted_course': predicted_course,
            'odds': odds,
            'odds_range': odds_range,
            'bet_amount': bet_amount,
            'hit': hit,
            'payout': payout_amount,
            'roi': roi
        })

    return results


def analyze_by_conditions(
    races: List[Dict],
    group_by: List[str]
) -> Dict[tuple, Dict]:
    """
    指定条件でグループ化して分析

    Args:
        races: レースデータ
        group_by: グループ化キー（例: ['confidence', 'predicted_course']）

    Returns:
        {(条件値1, 条件値2, ...): {統計情報}}
    """
    groups = defaultdict(lambda: {
        'count': 0,
        'hit_count': 0,
        'total_bet': 0,
        'total_payout': 0.0,
        'rois': []
    })

    for race in races:
        key = tuple(race.get(k, 'N/A') for k in group_by)

        groups[key]['count'] += 1
        groups[key]['total_bet'] += race['bet_amount']
        groups[key]['total_payout'] += race['payout']
        groups[key]['rois'].append(race['roi'])

        if race['hit']:
            groups[key]['hit_count'] += 1

    # 統計量計算
    results = {}
    for key, data in groups.items():
        if data['count'] == 0:
            continue

        roi = (data['total_payout'] / data['total_bet'] * 100) if data['total_bet'] > 0 else 0
        hit_rate = (data['hit_count'] / data['count'] * 100) if data['count'] > 0 else 0
        profit = data['total_payout'] - data['total_bet']

        # 95%信頼区間（ブートストラップ）
        rois_array = np.array(data['rois'])
        if len(rois_array) >= 30:
            n_bootstrap = 1000
            bootstrap_rois = []
            for _ in range(n_bootstrap):
                sample = np.random.choice(rois_array, size=len(rois_array), replace=True)
                bootstrap_rois.append(np.mean(sample) * 100)
            ci_lower = np.percentile(bootstrap_rois, 2.5)
            ci_upper = np.percentile(bootstrap_rois, 97.5)
        else:
            ci_lower, ci_upper = np.nan, np.nan

        results[key] = {
            'count': data['count'],
            'hit_count': data['hit_count'],
            'hit_rate': hit_rate,
            'total_bet': data['total_bet'],
            'total_payout': data['total_payout'],
            'roi': roi,
            'profit': profit,
            'ci_lower': ci_lower,
            'ci_upper': ci_upper,
            'rois': data['rois']
        }

    return results


def print_analysis_table(
    results: Dict[tuple, Dict],
    group_names: List[str],
    title: str
):
    """分析結果をテーブル形式で出力"""
    print(f"\n{'='*100}")
    print(f"{title}")
    print(f"{'='*100}")

    # ヘッダー
    header_parts = []
    for name in group_names:
        header_parts.append(f"{name:<12}")
    header_parts.extend([
        "サンプル", "的中", "的中率", "賭け金", "払戻", "収支", "ROI", "95%CI"
    ])
    print("  ".join(header_parts))
    print("-" * 100)

    # ROI順にソート
    sorted_results = sorted(results.items(), key=lambda x: x[1]['roi'], reverse=True)

    for key, data in sorted_results:
        if data['count'] < 10:  # 10件未満は表示しない
            continue

        row_parts = []
        for val in key:
            row_parts.append(f"{str(val):<12}")

        ci_str = f"[{data['ci_lower']:.1f}, {data['ci_upper']:.1f}]" if not np.isnan(data['ci_lower']) else "N/A"

        row_parts.extend([
            f"{data['count']:>7}",
            f"{data['hit_count']:>5}",
            f"{data['hit_rate']:>6.1f}%",
            f"{data['total_bet']:>10,.0f}",
            f"{data['total_payout']:>10,.0f}",
            f"{data['profit']:>+10,.0f}",
            f"{data['roi']:>7.1f}%",
            ci_str
        ])
        print("  ".join(row_parts))


def statistical_comparison(
    baseline_rois: List[float],
    treatment_rois: List[float],
    baseline_name: str,
    treatment_name: str
):
    """統計的検定（Welchのt検定）"""
    if len(baseline_rois) < 30 or len(treatment_rois) < 30:
        return None

    baseline_mean = np.mean(baseline_rois) * 100
    treatment_mean = np.mean(treatment_rois) * 100

    t_stat, p_value = stats.ttest_ind(treatment_rois, baseline_rois, equal_var=False)

    roi_diff = treatment_mean - baseline_mean

    # Cohen's d
    pooled_std = np.sqrt((np.var(baseline_rois, ddof=1) + np.var(treatment_rois, ddof=1)) / 2)
    cohens_d = (np.mean(treatment_rois) - np.mean(baseline_rois)) / pooled_std if pooled_std > 0 else 0

    print(f"\n統計的検定: {baseline_name} vs {treatment_name}")
    print(f"  Baseline平均ROI: {baseline_mean:.2f}%")
    print(f"  Treatment平均ROI: {treatment_mean:.2f}%")
    print(f"  ROI差: {roi_diff:+.2f}pt")
    print(f"  t値: {t_stat:.4f}")
    print(f"  p値: {p_value:.6f}")
    print(f"  Cohen's d: {cohens_d:.3f}")
    print(f"  判定: {'有意（p<0.05）' if p_value < 0.05 else '有意差なし'}")

    return {
        'baseline_mean': baseline_mean,
        'treatment_mean': treatment_mean,
        'roi_diff': roi_diff,
        't_stat': t_stat,
        'p_value': p_value,
        'cohens_d': cohens_d,
        'significant': p_value < 0.05
    }


def main():
    print("="*100)
    print("Phase 2-3: 局所的効果検証 - 信頼度×予測コース×オッズ帯別分析")
    print("="*100)
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        # データ取得
        print("データ取得中...")
        all_races = get_races_with_conditions(conn, '2020-01-01', '2025-12-31')
        print(f"対象レース数: {len(all_races):,}件")

        # 年度別分割
        races_2020_2024 = [r for r in all_races if r['race_date'] < '2025-01-01']
        races_2025 = [r for r in all_races if r['race_date'] >= '2025-01-01']

        print(f"  2020-2024年: {len(races_2020_2024):,}件")
        print(f"  2025年: {len(races_2025):,}件")

        # ========================================
        # 分析1: 信頼度別
        # ========================================
        results_conf = analyze_by_conditions(all_races, ['confidence'])
        print_analysis_table(results_conf, ['信頼度'], "【分析1】信頼度別ROI")

        # ========================================
        # 分析2: 予測コース別
        # ========================================
        results_course = analyze_by_conditions(all_races, ['predicted_course'])
        print_analysis_table(results_course, ['予測コース'], "【分析2】予測コース別ROI")

        # ========================================
        # 分析3: オッズ帯別
        # ========================================
        results_odds = analyze_by_conditions(all_races, ['odds_range'])
        print_analysis_table(results_odds, ['オッズ帯'], "【分析3】オッズ帯別ROI")

        # ========================================
        # 分析4: 信頼度×予測コース
        # ========================================
        results_conf_course = analyze_by_conditions(all_races, ['confidence', 'predicted_course'])
        print_analysis_table(results_conf_course, ['信頼度', '予測コース'], "【分析4】信頼度×予測コース別ROI")

        # ========================================
        # 分析5: 信頼度×オッズ帯
        # ========================================
        results_conf_odds = analyze_by_conditions(all_races, ['confidence', 'odds_range'])
        print_analysis_table(results_conf_odds, ['信頼度', 'オッズ帯'], "【分析5】信頼度×オッズ帯別ROI")

        # ========================================
        # 分析6: 予測コース×オッズ帯
        # ========================================
        results_course_odds = analyze_by_conditions(all_races, ['predicted_course', 'odds_range'])
        print_analysis_table(results_course_odds, ['予測コース', 'オッズ帯'], "【分析6】予測コース×オッズ帯別ROI")

        # ========================================
        # 年度間一貫性検証
        # ========================================
        print(f"\n{'='*100}")
        print("【年度間一貫性検証】")
        print(f"{'='*100}")

        # 信頼度別の年度間比較
        results_conf_2024 = analyze_by_conditions(races_2020_2024, ['confidence'])
        results_conf_2025 = analyze_by_conditions(races_2025, ['confidence'])

        print("\n信頼度別ROI（年度比較）:")
        print(f"{'信頼度':<10} {'2020-2024':<15} {'2025':<15} {'一貫性':<10}")
        print("-" * 60)
        for conf in ['C', 'D']:
            roi_2024 = results_conf_2024.get((conf,), {}).get('roi', 0)
            roi_2025 = results_conf_2025.get((conf,), {}).get('roi', 0)
            consistent = "OK" if abs(roi_2024 - roi_2025) < 30 else "NG"
            print(f"{conf:<10} {roi_2024:>13.1f}% {roi_2025:>13.1f}% {consistent:<10}")

        # ========================================
        # 重要な発見の抽出
        # ========================================
        print(f"\n{'='*100}")
        print("【重要な発見】")
        print(f"{'='*100}")

        baseline_roi = results_conf[('C',)]['roi']  # 信頼度C全体をベースライン

        findings = []
        for key, data in results_conf_course.items():
            if data['count'] < 30:
                continue
            roi_diff = data['roi'] - baseline_roi
            if abs(roi_diff) > 20:  # ±20pt以上の差
                findings.append({
                    'condition': f"{key[0]} × {key[1]}コース",
                    'roi': data['roi'],
                    'roi_diff': roi_diff,
                    'count': data['count'],
                    'profit': data['profit']
                })

        findings.sort(key=lambda x: x['roi_diff'], reverse=True)

        if findings:
            print("\nROI ±20pt以上の条件:")
            for f in findings[:10]:  # 上位10件
                print(f"  {f['condition']}: ROI {f['roi']:.1f}% ({f['roi_diff']:+.1f}pt), "
                      f"サンプル {f['count']:,}件, 収支 {f['profit']:+,.0f}円")
        else:
            print("\nROI ±20pt以上の条件は見つかりませんでした")

        # ========================================
        # 推奨アクション
        # ========================================
        print(f"\n{'='*100}")
        print("【推奨アクション】")
        print(f"{'='*100}")

        recommendations = []

        # 6コース予測の除外判定
        if (6,) in results_course:
            course6_data = results_course[(6,)]
            if course6_data['roi'] < 50:  # ROI 50%未満
                recommendations.append(
                    f"✓ 6コース予測を除外（現状ROI {course6_data['roi']:.1f}%、"
                    f"サンプル {course6_data['count']}件）"
                )

        # 3コース予測の強化判定
        if (3,) in results_course:
            course3_data = results_course[(3,)]
            if course3_data['roi'] > 200:  # ROI 200%超
                recommendations.append(
                    f"✓ 3コース予測の購入額を増やす（現状ROI {course3_data['roi']:.1f}%、"
                    f"サンプル {course3_data['count']}件）"
                )

        # オッズ帯最適化
        best_odds_range = max(results_odds.items(), key=lambda x: x[1]['roi'] if x[1]['count'] >= 30 else 0)
        if best_odds_range[1]['count'] >= 30:
            recommendations.append(
                f"✓ オッズ範囲を{best_odds_range[0][0]}倍に集中"
                f"（ROI {best_odds_range[1]['roi']:.1f}%）"
            )

        if recommendations:
            for rec in recommendations:
                print(f"  {rec}")
        else:
            print("  現状の条件を維持することを推奨")

    finally:
        conn.close()

    print()
    print("="*100)
    print("分析完了")
    print("="*100)


if __name__ == '__main__':
    main()
