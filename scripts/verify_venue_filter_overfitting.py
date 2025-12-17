# -*- coding: utf-8 -*-
"""
B-1: 会場フィルター過学習リスク検証

目的:
1. 2024年データでの会場別ROI分析
2. 2025年Tier分類を2024年に適用した場合のROI検証
3. 年度間の一貫性確認
4. 過学習リスクの評価

教訓:
- 2025年データのみでTier分類を決定している（過学習リスク）
- 統計的有意性（p<0.05）必須
- 現行ROI 167%を下回らないこと
"""

import sys
import sqlite3
import numpy as np
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from scipy import stats as scipy_stats

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

# 会場コードと名称のマッピング
VENUE_NAMES = {
    1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川', 6: '浜名湖',
    7: '蒲郡', 8: '常滑', 9: '津', 10: '三国', 11: '琵琶湖', 12: '住之江',
    13: '尼崎', 14: '鳴門', 15: '丸亀', 16: '児島', 17: '宮島', 18: '徳山',
    19: '下関', 20: '若松', 21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村'
}

# 2025年データで決定したTier分類
TIER1_2025 = [22, 11, 19, 21, 7]  # 福岡, 琵琶湖, 下関, 芦屋, 蒲郡
TIER3_2025 = [5, 3, 12, 2, 14, 4, 9, 8, 20, 23, 16, 17]  # 多摩川, 江戸川, 住之江, etc.


def analyze_venue_roi_by_year(conn, start_date, end_date, year_label):
    """指定期間の会場別ROIを分析"""
    cursor = conn.cursor()

    # 対象レースを取得
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= ? AND r.race_date <= ?
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''', (start_date, end_date))
    races = cursor.fetchall()

    print(f"\n[{year_label}] 対象レース数: {len(races):,}件")

    # 会場別統計初期化
    venue_stats = defaultdict(lambda: {
        'purchase_count': 0,
        'hit_count': 0,
        'total_bet': 0,
        'total_payout': 0.0,
        'rois_per_race': []
    })

    for race in races:
        race_id = race['race_id']
        venue_code = int(race['venue_code']) if race['venue_code'] else 0

        if venue_code == 0:
            continue

        # 1コース級別を取得
        cursor.execute('''
            SELECT racer_rank FROM entries
            WHERE race_id = ? AND pit_number = 1
        ''', (race_id,))
        c1 = cursor.fetchone()
        c1_rank = c1['racer_rank'] if c1 else 'B1'

        # A1以外は除外
        if c1_rank != 'A1':
            continue

        # 予測情報を取得
        cursor.execute('''
            SELECT pit_number, confidence
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'before'
            ORDER BY rank_prediction
        ''', (race_id,))
        preds = cursor.fetchall()

        if len(preds) < 6:
            continue

        confidence = preds[0]['confidence']

        # 対象信頼度のみ
        if confidence not in ['C', 'D']:
            continue

        top3 = [p['pit_number'] for p in preds[:3]]
        combo = f"{top3[0]}-{top3[1]}-{top3[2]}"

        # オッズ取得
        cursor.execute('''
            SELECT combination, odds FROM trifecta_odds
            WHERE race_id = ? AND combination = ?
        ''', (race_id, combo))
        odds_row = cursor.fetchone()

        if not odds_row:
            continue

        odds = odds_row['odds']

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

        # 購入対象
        venue_stats[venue_code]['purchase_count'] += 1
        venue_stats[venue_code]['total_bet'] += bet_amount

        # 実際の結果を取得
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        results = cursor.fetchall()

        race_roi = 0.0
        if len(results) >= 3:
            actual_combo = f"{results[0]['pit_number']}-{results[1]['pit_number']}-{results[2]['pit_number']}"

            if combo == actual_combo:
                # 的中
                cursor.execute('''
                    SELECT amount FROM payouts
                    WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                ''', (race_id, actual_combo))
                payout_row = cursor.fetchone()

                if payout_row:
                    payout = (bet_amount / 100) * payout_row['amount']
                    venue_stats[venue_code]['hit_count'] += 1
                    venue_stats[venue_code]['total_payout'] += payout
                    race_roi = payout / bet_amount

        venue_stats[venue_code]['rois_per_race'].append(race_roi)

    return venue_stats


def apply_tier_filter(venue_stats, tier1_venues, tier3_venues, multipliers):
    """Tier分類に基づいてフィルター効果を計算"""
    adjusted_bet = 0
    adjusted_payout = 0
    no_filter_bet = 0
    no_filter_payout = 0

    for venue_code, stats in venue_stats.items():
        if stats['purchase_count'] == 0:
            continue

        # フィルターなし
        no_filter_bet += stats['total_bet']
        no_filter_payout += stats['total_payout']

        # フィルターあり
        if venue_code in tier1_venues:
            multiplier = multipliers.get('tier1', 1.5)
        elif venue_code in tier3_venues:
            multiplier = multipliers.get('tier3', 0.5)
        else:
            multiplier = multipliers.get('tier2', 1.0)

        adjusted_bet += stats['total_bet'] * multiplier
        adjusted_payout += stats['total_payout'] * multiplier

    no_filter_roi = (no_filter_payout / no_filter_bet * 100) if no_filter_bet > 0 else 0
    adjusted_roi = (adjusted_payout / adjusted_bet * 100) if adjusted_bet > 0 else 0

    return {
        'no_filter': {
            'bet': no_filter_bet,
            'payout': no_filter_payout,
            'roi': no_filter_roi,
            'profit': no_filter_payout - no_filter_bet
        },
        'with_filter': {
            'bet': adjusted_bet,
            'payout': adjusted_payout,
            'roi': adjusted_roi,
            'profit': adjusted_payout - adjusted_bet
        }
    }


def calculate_tier_roi(venue_stats, tier_venues, tier_name):
    """特定Tierの会場群のROIを計算"""
    total_bet = 0
    total_payout = 0
    count = 0

    for venue_code in tier_venues:
        if venue_code in venue_stats:
            stats = venue_stats[venue_code]
            total_bet += stats['total_bet']
            total_payout += stats['total_payout']
            count += stats['purchase_count']

    roi = (total_payout / total_bet * 100) if total_bet > 0 else 0
    profit = total_payout - total_bet

    return {
        'tier_name': tier_name,
        'venues': tier_venues,
        'count': count,
        'bet': total_bet,
        'payout': total_payout,
        'roi': roi,
        'profit': profit
    }


def statistical_test_filter_effect(baseline_rois, treatment_rois):
    """フィルター効果の統計的有意性検定"""
    if len(baseline_rois) < 30 or len(treatment_rois) < 30:
        return {
            't_statistic': np.nan,
            'p_value': np.nan,
            'is_significant': False,
            'note': 'サンプルサイズ不足（30件未満）'
        }

    # Welchのt検定
    t_stat, p_value = scipy_stats.ttest_ind(treatment_rois, baseline_rois, equal_var=False)

    return {
        't_statistic': t_stat,
        'p_value': p_value,
        'is_significant': p_value < 0.05,
        'note': '有意' if p_value < 0.05 else '有意差なし'
    }


def main():
    """メイン処理"""
    db_path = ROOT_DIR / "data" / "boatrace.db"

    print("=" * 100)
    print("B-1: 会場フィルター過学習リスク検証")
    print("=" * 100)
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("【検証目的】")
    print("  1. 2024年データでの会場別ROI分析")
    print("  2. 2025年Tier分類を2024年に適用した場合のROI検証")
    print("  3. 年度間の一貫性確認")
    print("  4. 過学習リスクの評価")
    print()
    print("【2025年で決定したTier分類】")
    print(f"  Tier1 (購入1.5倍): {[VENUE_NAMES[v] for v in TIER1_2025]}")
    print(f"  Tier3 (購入0.5倍): {[VENUE_NAMES[v] for v in TIER3_2025]}")
    print()
    print("=" * 100)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        # ========================================
        # 1. 2024年データでの会場別ROI分析
        # ========================================
        print("\n" + "=" * 100)
        print("【1. 2024年データでの会場別ROI分析】")
        print("=" * 100)

        venue_stats_2024 = analyze_venue_roi_by_year(
            conn,
            start_date='2024-01-01',
            end_date='2024-12-31',
            year_label='2024年'
        )

        # 結果をROI順にソート
        sorted_venues_2024 = sorted(
            [(code, stats) for code, stats in venue_stats_2024.items() if stats['purchase_count'] > 0],
            key=lambda x: (x[1]['total_payout'] / x[1]['total_bet'] * 100) if x[1]['total_bet'] > 0 else 0,
            reverse=True
        )

        if len(sorted_venues_2024) == 0:
            print("\n[警告] 2024年のデータが見つかりませんでした。")
            print("2024年のrace_predictionsテーブルにデータがあるか確認してください。")
        else:
            print(f"\n{'順位':<4} {'会場':<8} {'購入':>8} {'的中':>6} {'賭け金':>12} {'払戻':>12} {'収支':>12} {'ROI':>8}")
            print("-" * 80)

            for rank, (code, stats) in enumerate(sorted_venues_2024, 1):
                roi = (stats['total_payout'] / stats['total_bet'] * 100) if stats['total_bet'] > 0 else 0
                profit = stats['total_payout'] - stats['total_bet']
                print(f"{rank:>3}  {VENUE_NAMES.get(code, f'会場{code}'):<8} {stats['purchase_count']:>8,} {stats['hit_count']:>6} "
                      f"{stats['total_bet']:>12,.0f} {stats['total_payout']:>12,.0f} {profit:>+12,.0f} {roi:>7.1f}%")

        # ========================================
        # 2. 2025年データでの会場別ROI分析（比較用）
        # ========================================
        print("\n" + "=" * 100)
        print("【2. 2025年データでの会場別ROI分析（比較用）】")
        print("=" * 100)

        venue_stats_2025 = analyze_venue_roi_by_year(
            conn,
            start_date='2025-01-01',
            end_date='2025-11-30',
            year_label='2025年'
        )

        sorted_venues_2025 = sorted(
            [(code, stats) for code, stats in venue_stats_2025.items() if stats['purchase_count'] > 0],
            key=lambda x: (x[1]['total_payout'] / x[1]['total_bet'] * 100) if x[1]['total_bet'] > 0 else 0,
            reverse=True
        )

        if len(sorted_venues_2025) > 0:
            print(f"\n{'順位':<4} {'会場':<8} {'購入':>8} {'的中':>6} {'賭け金':>12} {'払戻':>12} {'収支':>12} {'ROI':>8}")
            print("-" * 80)

            for rank, (code, stats) in enumerate(sorted_venues_2025, 1):
                roi = (stats['total_payout'] / stats['total_bet'] * 100) if stats['total_bet'] > 0 else 0
                profit = stats['total_payout'] - stats['total_bet']
                print(f"{rank:>3}  {VENUE_NAMES.get(code, f'会場{code}'):<8} {stats['purchase_count']:>8,} {stats['hit_count']:>6} "
                      f"{stats['total_bet']:>12,.0f} {stats['total_payout']:>12,.0f} {profit:>+12,.0f} {roi:>7.1f}%")

        # ========================================
        # 3. 年度間のTier一貫性分析
        # ========================================
        print("\n" + "=" * 100)
        print("【3. 年度間のTier一貫性分析】")
        print("=" * 100)

        print("\n▼ Tier1会場（2025年でROI 200%以上）の年度別ROI:")
        print()
        print(f"{'会場':<10} {'2024年ROI':>12} {'2025年ROI':>12} {'差分':>10} {'一貫性':>10}")
        print("-" * 60)

        tier1_consistency = []
        for venue_code in TIER1_2025:
            roi_2024 = 0
            roi_2025 = 0

            if venue_code in venue_stats_2024 and venue_stats_2024[venue_code]['total_bet'] > 0:
                roi_2024 = venue_stats_2024[venue_code]['total_payout'] / venue_stats_2024[venue_code]['total_bet'] * 100

            if venue_code in venue_stats_2025 and venue_stats_2025[venue_code]['total_bet'] > 0:
                roi_2025 = venue_stats_2025[venue_code]['total_payout'] / venue_stats_2025[venue_code]['total_bet'] * 100

            diff = roi_2025 - roi_2024
            consistent = "OK" if roi_2024 >= 120 else "NG"
            tier1_consistency.append(roi_2024 >= 120)

            print(f"{VENUE_NAMES.get(venue_code, f'会場{venue_code}'):<10} {roi_2024:>11.1f}% {roi_2025:>11.1f}% {diff:>+9.1f}pt {consistent:>10}")

        print("\n▼ Tier3会場（2025年でROI 80%未満）の年度別ROI:")
        print()
        print(f"{'会場':<10} {'2024年ROI':>12} {'2025年ROI':>12} {'差分':>10} {'一貫性':>10}")
        print("-" * 60)

        tier3_consistency = []
        for venue_code in TIER3_2025:
            roi_2024 = 0
            roi_2025 = 0

            if venue_code in venue_stats_2024 and venue_stats_2024[venue_code]['total_bet'] > 0:
                roi_2024 = venue_stats_2024[venue_code]['total_payout'] / venue_stats_2024[venue_code]['total_bet'] * 100

            if venue_code in venue_stats_2025 and venue_stats_2025[venue_code]['total_bet'] > 0:
                roi_2025 = venue_stats_2025[venue_code]['total_payout'] / venue_stats_2025[venue_code]['total_bet'] * 100

            diff = roi_2025 - roi_2024
            consistent = "OK" if roi_2024 < 100 else "NG"
            tier3_consistency.append(roi_2024 < 100)

            print(f"{VENUE_NAMES.get(venue_code, f'会場{venue_code}'):<10} {roi_2024:>11.1f}% {roi_2025:>11.1f}% {diff:>+9.1f}pt {consistent:>10}")

        # ========================================
        # 4. 2025年Tier分類を2024年に適用した場合の検証
        # ========================================
        print("\n" + "=" * 100)
        print("【4. 2025年Tier分類を2024年に適用した場合のROI】")
        print("=" * 100)

        multipliers = {'tier1': 1.5, 'tier2': 1.0, 'tier3': 0.5}

        if len(venue_stats_2024) > 0:
            # 2024年データに2025年Tier分類を適用
            filter_result_2024 = apply_tier_filter(
                venue_stats_2024, TIER1_2025, TIER3_2025, multipliers
            )

            print("\n▼ 2024年データでの結果:")
            print(f"  フィルターなし: ROI {filter_result_2024['no_filter']['roi']:.1f}%, "
                  f"収支 {filter_result_2024['no_filter']['profit']:+,.0f}円")
            print(f"  フィルターあり: ROI {filter_result_2024['with_filter']['roi']:.1f}%, "
                  f"収支 {filter_result_2024['with_filter']['profit']:+,.0f}円")
            print(f"  ROI改善: {filter_result_2024['with_filter']['roi'] - filter_result_2024['no_filter']['roi']:+.1f}pt")
        else:
            print("\n[警告] 2024年データが不足しているため、検証できません。")

        if len(venue_stats_2025) > 0:
            # 2025年データに2025年Tier分類を適用（元の結果）
            filter_result_2025 = apply_tier_filter(
                venue_stats_2025, TIER1_2025, TIER3_2025, multipliers
            )

            print("\n▼ 2025年データでの結果（元のバックテスト）:")
            print(f"  フィルターなし: ROI {filter_result_2025['no_filter']['roi']:.1f}%, "
                  f"収支 {filter_result_2025['no_filter']['profit']:+,.0f}円")
            print(f"  フィルターあり: ROI {filter_result_2025['with_filter']['roi']:.1f}%, "
                  f"収支 {filter_result_2025['with_filter']['profit']:+,.0f}円")
            print(f"  ROI改善: {filter_result_2025['with_filter']['roi'] - filter_result_2025['no_filter']['roi']:+.1f}pt")

        # ========================================
        # 5. Tier別ROI分析
        # ========================================
        print("\n" + "=" * 100)
        print("【5. Tier別ROI分析（過学習検証）】")
        print("=" * 100)

        if len(venue_stats_2024) > 0:
            tier1_2024 = calculate_tier_roi(venue_stats_2024, TIER1_2025, "Tier1")
            tier3_2024 = calculate_tier_roi(venue_stats_2024, TIER3_2025, "Tier3")

            print("\n▼ 2024年データでのTier別ROI:")
            print(f"  Tier1 ({len(TIER1_2025)}会場): ROI {tier1_2024['roi']:.1f}%, 購入 {tier1_2024['count']}件, 収支 {tier1_2024['profit']:+,.0f}円")
            print(f"  Tier3 ({len(TIER3_2025)}会場): ROI {tier3_2024['roi']:.1f}%, 購入 {tier3_2024['count']}件, 収支 {tier3_2024['profit']:+,.0f}円")

        if len(venue_stats_2025) > 0:
            tier1_2025 = calculate_tier_roi(venue_stats_2025, TIER1_2025, "Tier1")
            tier3_2025 = calculate_tier_roi(venue_stats_2025, TIER3_2025, "Tier3")

            print("\n▼ 2025年データでのTier別ROI:")
            print(f"  Tier1 ({len(TIER1_2025)}会場): ROI {tier1_2025['roi']:.1f}%, 購入 {tier1_2025['count']}件, 収支 {tier1_2025['profit']:+,.0f}円")
            print(f"  Tier3 ({len(TIER3_2025)}会場): ROI {tier3_2025['roi']:.1f}%, 購入 {tier3_2025['count']}件, 収支 {tier3_2025['profit']:+,.0f}円")

        # ========================================
        # 6. 統計的有意性検定
        # ========================================
        print("\n" + "=" * 100)
        print("【6. 統計的有意性検定】")
        print("=" * 100)

        # 2025年データでのフィルターあり/なしの比較
        if len(venue_stats_2025) > 0:
            # 全レースのROIを収集
            all_rois_baseline = []
            all_rois_treatment = []

            for venue_code, stats in venue_stats_2025.items():
                if stats['purchase_count'] > 0:
                    if venue_code in TIER1_2025:
                        multiplier = 1.5
                    elif venue_code in TIER3_2025:
                        multiplier = 0.5
                    else:
                        multiplier = 1.0

                    for roi in stats['rois_per_race']:
                        all_rois_baseline.append(roi)
                        all_rois_treatment.append(roi * multiplier)

            print(f"\n▼ サンプルサイズ:")
            print(f"  ベースライン（フィルターなし）: {len(all_rois_baseline)}件")
            print(f"  フィルターあり: {len(all_rois_treatment)}件")

            test_result = statistical_test_filter_effect(all_rois_baseline, all_rois_treatment)

            print(f"\n▼ t検定結果:")
            print(f"  ベースライン平均ROI: {np.mean(all_rois_baseline) * 100:.2f}%")
            print(f"  フィルター適用平均ROI: {np.mean(all_rois_treatment) * 100:.2f}%")
            print(f"  t値: {test_result['t_statistic']:.4f}" if not np.isnan(test_result['t_statistic']) else "  t値: N/A")
            print(f"  p値: {test_result['p_value']:.6f}" if not np.isnan(test_result['p_value']) else "  p値: N/A")
            print(f"  判定: {test_result['note']}")

            # 95%信頼区間
            if len(all_rois_baseline) >= 30 and len(all_rois_treatment) >= 30:
                ci_baseline = scipy_stats.t.interval(
                    0.95, len(all_rois_baseline)-1,
                    loc=np.mean(all_rois_baseline),
                    scale=scipy_stats.sem(all_rois_baseline)
                )
                ci_treatment = scipy_stats.t.interval(
                    0.95, len(all_rois_treatment)-1,
                    loc=np.mean(all_rois_treatment),
                    scale=scipy_stats.sem(all_rois_treatment)
                )
                print(f"\n▼ 95%信頼区間:")
                print(f"  ベースライン: [{ci_baseline[0]*100:.2f}%, {ci_baseline[1]*100:.2f}%]")
                print(f"  フィルター適用: [{ci_treatment[0]*100:.2f}%, {ci_treatment[1]*100:.2f}%]")

        # ========================================
        # 7. 過学習リスク評価
        # ========================================
        print("\n" + "=" * 100)
        print("【7. 過学習リスク評価】")
        print("=" * 100)

        overfitting_risk = "低"
        risk_factors = []

        # リスク要因チェック
        if len(venue_stats_2024) > 0 and len(venue_stats_2025) > 0:
            # Tier1会場の一貫性
            tier1_consistent_count = sum(tier1_consistency)
            if tier1_consistent_count < len(TIER1_2025) * 0.6:
                risk_factors.append(f"Tier1会場の一貫性が低い（{tier1_consistent_count}/{len(TIER1_2025)}会場のみ2024年もROI 120%以上）")
                overfitting_risk = "高"

            # Tier3会場の一貫性
            tier3_consistent_count = sum(tier3_consistency)
            if tier3_consistent_count < len(TIER3_2025) * 0.6:
                risk_factors.append(f"Tier3会場の一貫性が低い（{tier3_consistent_count}/{len(TIER3_2025)}会場のみ2024年もROI 100%未満）")
                overfitting_risk = "高"

            # 2024年でのフィルター効果
            if 'filter_result_2024' in locals():
                roi_improvement_2024 = filter_result_2024['with_filter']['roi'] - filter_result_2024['no_filter']['roi']
                if roi_improvement_2024 < 0:
                    risk_factors.append(f"2024年データではフィルター効果がマイナス（ROI {roi_improvement_2024:+.1f}pt）")
                    overfitting_risk = "高"
        else:
            risk_factors.append("2024年データが不足しているため、年度間一貫性を検証できない")
            overfitting_risk = "中"

        # サンプルサイズ
        total_samples_2025 = sum(stats['purchase_count'] for stats in venue_stats_2025.values())
        if total_samples_2025 < 500:
            risk_factors.append(f"サンプルサイズが少ない（{total_samples_2025}件 < 500件）")
            if overfitting_risk == "低":
                overfitting_risk = "中"

        print(f"\n▼ 過学習リスク判定: 【{overfitting_risk}】")
        print()
        if risk_factors:
            print("▼ リスク要因:")
            for i, factor in enumerate(risk_factors, 1):
                print(f"  {i}. {factor}")
        else:
            print("▼ リスク要因: なし")

        # ========================================
        # 8. 最終判定
        # ========================================
        print("\n" + "=" * 100)
        print("【8. 最終判定】")
        print("=" * 100)

        print("\n▼ B-1（会場フィルター）の採用判定:")

        if overfitting_risk == "高":
            print("  ❌ 【不採用推奨】過学習リスクが高い")
            print("     - 2024年データとの一貫性が確認できない")
            print("     - 2025年データに過剰適合している可能性が高い")
            print("     - 実運用でROIが低下するリスクがある")
        elif overfitting_risk == "中":
            print("  △ 【保留推奨】慎重な検証が必要")
            print("     - 追加データでの検証を推奨")
            print("     - 段階的導入（まずTier1のみ1.2倍から）を検討")
        else:
            print("  ✅ 【採用検討可】過学習リスクは低い")
            print("     - ただし、現行ROI 167%を下回らないか確認が必要")

        print("\n▼ 現行ROI 167%との比較:")
        if len(venue_stats_2025) > 0 and 'filter_result_2025' in locals():
            current_roi = 167.0
            filtered_roi = filter_result_2025['with_filter']['roi']
            if filtered_roi < current_roi:
                print(f"  ❌ フィルター適用後ROI {filtered_roi:.1f}% < 現行ROI {current_roi:.1f}%")
                print("     → 現行システムを維持すべき")
            else:
                print(f"  ✅ フィルター適用後ROI {filtered_roi:.1f}% >= 現行ROI {current_roi:.1f}%")

    finally:
        conn.close()

    print()
    print("=" * 100)
    print("過学習リスク検証完了")
    print("=" * 100)


if __name__ == '__main__':
    main()
