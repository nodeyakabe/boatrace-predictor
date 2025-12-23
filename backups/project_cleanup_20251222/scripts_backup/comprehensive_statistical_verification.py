# -*- coding: utf-8 -*-
"""
B-1/A-2 包括的統計検証スクリプト

目的:
1. B-1（会場フィルター）の統計的有意性を厳密に検証
2. A-2（特徴量A/Bテスト）の再検証
3. 過学習リスクの総合評価
4. 現行ROI 167%との比較

重要な制約:
- 統計的有意性（p<0.05）必須
- 現行ROI 167%を下回る施策は不採用
- 過学習が疑われる場合は慎重に
"""

import sys
import sqlite3
import numpy as np
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from scipy import stats as scipy_stats
import hashlib

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

# 会場コードと名称のマッピング
VENUE_NAMES = {
    1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川', 6: '浜名湖',
    7: '蒲郡', 8: '常滑', 9: '津', 10: '三国', 11: '琵琶湖', 12: '住之江',
    13: '尼崎', 14: '鳴門', 15: '丸亀', 16: '児島', 17: '宮島', 18: '徳山',
    19: '下関', 20: '若松', 21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村'
}

# 2025年で決定したTier分類
TIER1_2025 = [22, 11, 19, 21, 7]
TIER3_2025 = [5, 3, 12, 2, 14, 4, 9, 8, 20, 23, 16, 17]


def run_b1_statistical_verification(conn):
    """B-1（会場フィルター）の統計的有意性検証"""
    print("\n" + "=" * 100)
    print("【B-1: 会場フィルター統計的有意性検証】")
    print("=" * 100)

    cursor = conn.cursor()

    # 購入対象レースを取得
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code, r.race_date,
               rp.pit_number, rp.confidence, rp.rank_prediction
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id
        JOIN entries e ON r.id = e.race_id AND e.pit_number = 1
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-11-30'
        AND rp.prediction_type = 'before'
        AND rp.rank_prediction <= 3
        AND rp.confidence IN ('C', 'D')
        AND e.racer_rank = 'A1'
        ORDER BY r.id, rp.rank_prediction
    ''')
    preds = cursor.fetchall()

    # race_id単位で集約
    race_preds = defaultdict(list)
    for row in preds:
        race_preds[row['race_id']].append({
            'venue_code': int(row['venue_code']) if row['venue_code'] else 0,
            'pit_number': row['pit_number'],
            'confidence': row['confidence'],
            'rank_prediction': row['rank_prediction'],
            'race_date': row['race_date']
        })

    print(f"\n対象レース数（予測あり）: {len(race_preds):,}件")

    # 各レースのROIを計算
    race_data = []

    for race_id, pred_list in race_preds.items():
        if len(pred_list) < 3:
            continue

        pred_list = sorted(pred_list, key=lambda x: x['rank_prediction'])
        venue_code = pred_list[0]['venue_code']
        confidence = pred_list[0]['confidence']

        if venue_code == 0:
            continue

        # 予測組み合わせ
        top3 = [p['pit_number'] for p in pred_list[:3]]
        combo = f"{top3[0]}-{top3[1]}-{top3[2]}"

        # オッズ取得
        cursor.execute('''
            SELECT odds FROM trifecta_odds
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

        # 実際の結果を取得
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        results = cursor.fetchall()

        payout = 0
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

        # Tier判定
        if venue_code in TIER1_2025:
            tier = 'Tier1'
            multiplier = 1.5
        elif venue_code in TIER3_2025:
            tier = 'Tier3'
            multiplier = 0.5
        else:
            tier = 'Tier2'
            multiplier = 1.0

        roi_baseline = payout / bet_amount if bet_amount > 0 else 0
        adjusted_bet = int(bet_amount * multiplier / 100) * 100
        adjusted_bet = max(100, min(2000, adjusted_bet))
        adjusted_payout = (payout / bet_amount * adjusted_bet) if bet_amount > 0 else 0
        roi_filtered = adjusted_payout / adjusted_bet if adjusted_bet > 0 else 0

        race_data.append({
            'race_id': race_id,
            'venue_code': venue_code,
            'tier': tier,
            'bet_baseline': bet_amount,
            'bet_filtered': adjusted_bet,
            'payout_baseline': payout,
            'payout_filtered': adjusted_payout,
            'roi_baseline': roi_baseline,
            'roi_filtered': roi_filtered,
            'hit': 1 if payout > 0 else 0
        })

    print(f"バックテスト対象レース: {len(race_data):,}件")

    # 統計的検証
    rois_baseline = [d['roi_baseline'] for d in race_data]
    rois_filtered = [d['roi_filtered'] for d in race_data]

    total_bet_baseline = sum(d['bet_baseline'] for d in race_data)
    total_payout_baseline = sum(d['payout_baseline'] for d in race_data)
    total_bet_filtered = sum(d['bet_filtered'] for d in race_data)
    total_payout_filtered = sum(d['payout_filtered'] for d in race_data)

    overall_roi_baseline = (total_payout_baseline / total_bet_baseline * 100) if total_bet_baseline > 0 else 0
    overall_roi_filtered = (total_payout_filtered / total_bet_filtered * 100) if total_bet_filtered > 0 else 0

    print(f"\n【結果サマリー】")
    print(f"  フィルターなし:")
    print(f"    総賭け金: {total_bet_baseline:,.0f}円")
    print(f"    総払戻: {total_payout_baseline:,.0f}円")
    print(f"    収支: {total_payout_baseline - total_bet_baseline:+,.0f}円")
    print(f"    ROI: {overall_roi_baseline:.1f}%")

    print(f"  フィルターあり:")
    print(f"    総賭け金: {total_bet_filtered:,.0f}円")
    print(f"    総払戻: {total_payout_filtered:,.0f}円")
    print(f"    収支: {total_payout_filtered - total_bet_filtered:+,.0f}円")
    print(f"    ROI: {overall_roi_filtered:.1f}%")

    print(f"\n  ROI改善: {overall_roi_filtered - overall_roi_baseline:+.1f}pt")

    # t検定
    print(f"\n【t検定（Welch）】")
    print(f"  サンプルサイズ: {len(rois_baseline)}件")

    if len(rois_baseline) >= 30:
        t_stat, p_value = scipy_stats.ttest_ind(rois_filtered, rois_baseline, equal_var=False)

        print(f"  ベースライン平均ROI: {np.mean(rois_baseline) * 100:.2f}%")
        print(f"  フィルター適用平均ROI: {np.mean(rois_filtered) * 100:.2f}%")
        print(f"  t値: {t_stat:.4f}")
        print(f"  p値: {p_value:.6f}")
        print(f"  判定: {'有意' if p_value < 0.05 else '有意差なし'}")

        # 95%信頼区間
        ci_baseline = scipy_stats.t.interval(
            0.95, len(rois_baseline)-1,
            loc=np.mean(rois_baseline),
            scale=scipy_stats.sem(rois_baseline)
        )
        ci_filtered = scipy_stats.t.interval(
            0.95, len(rois_filtered)-1,
            loc=np.mean(rois_filtered),
            scale=scipy_stats.sem(rois_filtered)
        )

        print(f"\n【95%信頼区間】")
        print(f"  ベースライン: [{ci_baseline[0]*100:.2f}%, {ci_baseline[1]*100:.2f}%]")
        print(f"  フィルター適用: [{ci_filtered[0]*100:.2f}%, {ci_filtered[1]*100:.2f}%]")

        # 効果量（Cohen's d）
        pooled_std = np.sqrt((np.var(rois_baseline) + np.var(rois_filtered)) / 2)
        cohens_d = (np.mean(rois_filtered) - np.mean(rois_baseline)) / pooled_std if pooled_std > 0 else 0

        print(f"\n【効果量】")
        print(f"  Cohen's d: {cohens_d:.4f}")
        if abs(cohens_d) < 0.2:
            print(f"  解釈: ごく小さい効果")
        elif abs(cohens_d) < 0.5:
            print(f"  解釈: 小さい効果")
        elif abs(cohens_d) < 0.8:
            print(f"  解釈: 中程度の効果")
        else:
            print(f"  解釈: 大きな効果")

        return {
            'p_value': p_value,
            'is_significant': p_value < 0.05,
            'roi_baseline': overall_roi_baseline,
            'roi_filtered': overall_roi_filtered,
            'cohens_d': cohens_d,
            'sample_size': len(rois_baseline)
        }

    else:
        print(f"  エラー: サンプルサイズ不足（30件未満）")
        return {
            'p_value': np.nan,
            'is_significant': False,
            'roi_baseline': overall_roi_baseline,
            'roi_filtered': overall_roi_filtered,
            'cohens_d': np.nan,
            'sample_size': len(rois_baseline)
        }


def run_a2_statistical_verification(conn):
    """A-2（特徴量A/Bテスト）の統計的有意性検証"""
    print("\n" + "=" * 100)
    print("【A-2: 特徴量A/Bテスト統計的有意性検証】")
    print("=" * 100)

    cursor = conn.cursor()

    # ハッシュベースのグループ分け関数
    def assign_group(race_id):
        hash_obj = hashlib.md5(str(race_id).encode())
        hash_int = int(hash_obj.hexdigest(), 16)
        hash_val = (hash_int % 10000) / 10000
        if hash_val < 0.50:
            return 'control'
        elif hash_val < 0.75:
            return 'treatment_a'
        else:
            return 'treatment_b'

    # 購入対象レースを取得
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code, r.race_date,
               rp.pit_number, rp.confidence, rp.rank_prediction
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id
        JOIN entries e ON r.id = e.race_id AND e.pit_number = 1
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-11-30'
        AND rp.prediction_type = 'before'
        AND rp.rank_prediction <= 3
        AND rp.confidence IN ('C', 'D')
        AND e.racer_rank = 'A1'
        ORDER BY r.id, rp.rank_prediction
    ''')
    preds = cursor.fetchall()

    # race_id単位で集約
    race_preds = defaultdict(list)
    for row in preds:
        race_preds[row['race_id']].append({
            'pit_number': row['pit_number'],
            'confidence': row['confidence'],
            'rank_prediction': row['rank_prediction']
        })

    # グループ別統計
    group_data = {
        'control': {'rois': [], 'total_bet': 0, 'total_payout': 0, 'hit': 0},
        'treatment_a': {'rois': [], 'total_bet': 0, 'total_payout': 0, 'hit': 0},
        'treatment_b': {'rois': [], 'total_bet': 0, 'total_payout': 0, 'hit': 0}
    }

    for race_id, pred_list in race_preds.items():
        if len(pred_list) < 3:
            continue

        pred_list = sorted(pred_list, key=lambda x: x['rank_prediction'])
        confidence = pred_list[0]['confidence']

        # グループ割り当て
        group = assign_group(race_id)

        # 予測組み合わせ
        top3 = [p['pit_number'] for p in pred_list[:3]]
        combo = f"{top3[0]}-{top3[1]}-{top3[2]}"

        # オッズ取得
        cursor.execute('''
            SELECT odds FROM trifecta_odds
            WHERE race_id = ? AND combination = ?
        ''', (race_id, combo))
        odds_row = cursor.fetchone()

        if not odds_row:
            continue

        odds = odds_row['odds']

        # オッズ範囲チェック
        bet_amount = 0
        if confidence == 'C':
            if 20 <= odds < 60:
                bet_amount = 400 if odds < 40 else 500
        elif confidence == 'D':
            if 20 <= odds < 50:
                bet_amount = 300

        if bet_amount == 0:
            continue

        # 実際の結果を取得
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        results = cursor.fetchall()

        payout = 0
        if len(results) >= 3:
            actual_combo = f"{results[0]['pit_number']}-{results[1]['pit_number']}-{results[2]['pit_number']}"

            if combo == actual_combo:
                cursor.execute('''
                    SELECT amount FROM payouts
                    WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                ''', (race_id, actual_combo))
                payout_row = cursor.fetchone()

                if payout_row:
                    payout = (bet_amount / 100) * payout_row['amount']

        roi = payout / bet_amount if bet_amount > 0 else 0
        group_data[group]['rois'].append(roi)
        group_data[group]['total_bet'] += bet_amount
        group_data[group]['total_payout'] += payout
        if payout > 0:
            group_data[group]['hit'] += 1

    # 結果サマリー
    print(f"\n【グループ別結果】")
    print(f"{'グループ':<30} {'サンプル数':>10} {'的中':>8} {'賭け金':>12} {'払戻':>12} {'ROI':>8}")
    print("-" * 90)

    for group_name, data in group_data.items():
        if data['total_bet'] > 0:
            roi = data['total_payout'] / data['total_bet'] * 100
            if group_name == 'control':
                label = 'Control（基本特徴量のみ）'
            elif group_name == 'treatment_a':
                label = 'Treatment A（+会場xコース）'
            else:
                label = 'Treatment B（+天候強化）'
            print(f"{label:<30} {len(data['rois']):>10} {data['hit']:>8} "
                  f"{data['total_bet']:>12,.0f} {data['total_payout']:>12,.0f} {roi:>7.1f}%")

    # 統計的検定
    print(f"\n【統計的検定】")

    results = {}

    control_rois = group_data['control']['rois']

    for treatment_name in ['treatment_a', 'treatment_b']:
        treatment_rois = group_data[treatment_name]['rois']

        if len(control_rois) >= 30 and len(treatment_rois) >= 30:
            t_stat, p_value = scipy_stats.ttest_ind(treatment_rois, control_rois, equal_var=False)

            if treatment_name == 'treatment_a':
                label = 'Treatment A（会場xコース）'
            else:
                label = 'Treatment B（天候強化）'

            print(f"\n  Control vs {label}:")
            print(f"    Control平均ROI: {np.mean(control_rois) * 100:.2f}%")
            print(f"    Treatment平均ROI: {np.mean(treatment_rois) * 100:.2f}%")
            print(f"    差分: {(np.mean(treatment_rois) - np.mean(control_rois)) * 100:+.2f}pt")
            print(f"    t値: {t_stat:.4f}")
            print(f"    p値: {p_value:.6f}")
            print(f"    判定: {'有意' if p_value < 0.05 else '有意差なし'}")

            results[treatment_name] = {
                'p_value': p_value,
                'is_significant': p_value < 0.05,
                'roi_diff': (np.mean(treatment_rois) - np.mean(control_rois)) * 100,
                'sample_size': len(treatment_rois)
            }
        else:
            print(f"\n  {treatment_name}: サンプルサイズ不足（30件未満）")
            results[treatment_name] = {
                'p_value': np.nan,
                'is_significant': False,
                'roi_diff': np.nan,
                'sample_size': len(treatment_rois)
            }

    # 検出力分析
    print(f"\n【検出力分析】")
    print(f"  Control サンプル数: {len(control_rois)}件")
    print(f"  Treatment A サンプル数: {len(group_data['treatment_a']['rois'])}件")
    print(f"  Treatment B サンプル数: {len(group_data['treatment_b']['rois'])}件")

    # 必要サンプル数の推定（効果量0.3を検出するため）
    # n = 2 * ((z_alpha + z_beta) / d)^2
    # 80%検出力、5%有意水準、効果量0.3の場合
    required_n = 2 * ((1.96 + 0.84) / 0.3) ** 2
    print(f"\n  効果量0.3を80%の検出力で検出するための必要サンプル数: 約{int(required_n)}件/グループ")

    if len(control_rois) < required_n:
        print(f"  [警告] 現在のサンプル数では中程度の効果を検出する検出力が不足")

    return results


def comprehensive_evaluation(b1_result, a2_results):
    """総合評価"""
    print("\n" + "=" * 100)
    print("【総合評価】")
    print("=" * 100)

    print("\n" + "-" * 50)
    print("【B-1: 会場フィルター】")
    print("-" * 50)

    if b1_result['is_significant']:
        if b1_result['roi_filtered'] > b1_result['roi_baseline']:
            print("  判定: [採用検討可] 統計的に有意にROI改善")
        else:
            print("  判定: [不採用] 統計的に有意にROI悪化")
    else:
        print("  判定: [保留] 統計的有意性なし（p={:.4f} >= 0.05）".format(b1_result['p_value']))
        print("  理由:")
        print("    1. p値が有意水準を超えている")
        print("    2. ROI改善効果がノイズの範囲内である可能性")
        print("    3. 2024年データでの検証ができない（before予測データがほぼない）")

    print(f"\n  ROI: {b1_result['roi_baseline']:.1f}% -> {b1_result['roi_filtered']:.1f}% ({b1_result['roi_filtered'] - b1_result['roi_baseline']:+.1f}pt)")

    # 現行ROI 167%との比較
    current_roi = 167.0
    print(f"\n  現行ROI 167%との比較:")
    if b1_result['roi_filtered'] < current_roi:
        print(f"    [NG] フィルター適用後ROI {b1_result['roi_filtered']:.1f}% < 現行ROI {current_roi:.1f}%")
        print(f"    -> 現行システムを維持すべき")
    else:
        print(f"    [OK] フィルター適用後ROI {b1_result['roi_filtered']:.1f}% >= 現行ROI {current_roi:.1f}%")

    print("\n" + "-" * 50)
    print("【A-2: 特徴量A/Bテスト】")
    print("-" * 50)

    for treatment_name, result in a2_results.items():
        if treatment_name == 'treatment_a':
            label = 'Treatment A（会場xコース）'
        else:
            label = 'Treatment B（天候強化）'

        if result['is_significant']:
            if result['roi_diff'] > 0:
                print(f"  {label}: [有効] 統計的に有意にROI改善（{result['roi_diff']:+.2f}pt）")
            else:
                print(f"  {label}: [無効] 統計的に有意にROI悪化（{result['roi_diff']:+.2f}pt）")
        else:
            print(f"  {label}: [判定保留] 統計的有意性なし")
            print(f"    - サンプル数: {result['sample_size']}件")
            if not np.isnan(result['p_value']):
                print(f"    - p値: {result['p_value']:.4f}")

    # 過学習リスク評価
    print("\n" + "-" * 50)
    print("【過学習リスク評価】")
    print("-" * 50)

    risk_level = "中"
    risk_factors = []

    # 2024年データでの検証不能
    risk_factors.append("2024年のbefore予測データがほぼない（66件）ため、年度間一貫性を検証できない")

    # B-1の統計的有意性なし
    if not b1_result['is_significant']:
        risk_factors.append("B-1会場フィルターの効果は統計的に有意ではない")
        risk_level = "高"

    # サンプルサイズ
    if b1_result['sample_size'] < 500:
        risk_factors.append(f"サンプルサイズが少ない（{b1_result['sample_size']}件）")

    # 効果量が小さい
    if not np.isnan(b1_result['cohens_d']) and abs(b1_result['cohens_d']) < 0.2:
        risk_factors.append(f"効果量が非常に小さい（Cohen's d = {b1_result['cohens_d']:.4f}）")

    print(f"\n  過学習リスクレベル: 【{risk_level}】")
    print("\n  リスク要因:")
    for i, factor in enumerate(risk_factors, 1):
        print(f"    {i}. {factor}")

    # 最終推奨
    print("\n" + "-" * 50)
    print("【最終推奨】")
    print("-" * 50)

    print("\n  ▼ B-1（会場フィルター）:")
    if not b1_result['is_significant']:
        print("    [不採用] 統計的有意性が確認できないため")
        print("    - p値: {:.4f} (要件: p < 0.05)".format(b1_result['p_value']))
        print("    - 過学習リスクが高い")
        print("    - 2024年データでの検証ができない")
    elif b1_result['roi_filtered'] < current_roi:
        print("    [不採用] 現行ROI 167%を下回るため")
    else:
        print("    [採用検討可] ただし慎重に")

    print("\n  ▼ A-2（特徴量A/Bテスト）:")
    for treatment_name, result in a2_results.items():
        if treatment_name == 'treatment_a':
            label = 'Treatment A（会場xコース）'
        else:
            label = 'Treatment B（天候強化）'

        if result['is_significant'] and result['roi_diff'] > 0:
            print(f"    {label}: [維持推奨]")
        elif result['is_significant'] and result['roi_diff'] < 0:
            print(f"    {label}: [除去推奨]")
        else:
            print(f"    {label}: [判定保留] サンプル追加後に再検証")


def main():
    """メイン処理"""
    db_path = ROOT_DIR / "data" / "boatrace.db"

    print("=" * 100)
    print("B-1/A-2 包括的統計検証")
    print("=" * 100)
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("【検証条件】")
    print("  - 期間: 2025年1月-11月")
    print("  - 予測タイプ: before（直前情報あり）")
    print("  - 対象信頼度: C, D")
    print("  - 1コース級別: A1のみ")
    print()
    print("【重要な制約】")
    print("  - 統計的有意性（p<0.05）必須")
    print("  - 現行ROI 167%を下回る施策は不採用")
    print("  - 過学習が疑われる場合は慎重に")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        # B-1検証
        b1_result = run_b1_statistical_verification(conn)

        # A-2検証
        a2_results = run_a2_statistical_verification(conn)

        # 総合評価
        comprehensive_evaluation(b1_result, a2_results)

    finally:
        conn.close()

    print()
    print("=" * 100)
    print("検証完了")
    print("=" * 100)


if __name__ == '__main__':
    main()
