#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
データ補完の影響度分析
- 2021年・2023年のデータ欠損が各提案に与える影響を評価
"""
import sqlite3
import sys
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DATABASE_PATH = 'data/boatrace.db'

def analyze_data_completion_impact():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("="*80)
    print("データ補完の影響度分析")
    print("="*80)
    print()

    # 年度別のデータ充足状況
    print("【1】年度別データ充足状況")
    print("-"*80)

    cursor.execute('''
        SELECT
            substr(r.race_date, 1, 4) as year,
            COUNT(DISTINCT r.id) as total_races,
            COUNT(DISTINCT CASE WHEN rp.race_id IS NOT NULL THEN r.id END) as races_with_prediction,
            COUNT(DISTINCT CASE WHEN t.race_id IS NOT NULL THEN r.id END) as races_with_odds,
            COUNT(DISTINCT CASE WHEN res.race_id IS NOT NULL THEN r.id END) as races_with_results
        FROM races r
        LEFT JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
        LEFT JOIN (SELECT DISTINCT race_id FROM trifecta_odds) t ON r.id = t.race_id
        LEFT JOIN (SELECT DISTINCT race_id FROM results) res ON r.id = res.race_id
        WHERE r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
        GROUP BY year
        ORDER BY year
    ''')

    print(f"{'年度':<8} {'総レース':<12} {'予測あり':<12} {'オッズあり':<12} {'結果あり':<12} {'完全データ率':<12}")
    print("-"*80)

    year_data = {}
    for row in cursor.fetchall():
        year, total, pred, odds, results = row
        complete_rate = 100.0 * min(pred, odds, results) / total if total > 0 else 0
        year_data[year] = {
            'total': total,
            'prediction': pred,
            'odds': odds,
            'results': results,
            'complete_rate': complete_rate
        }
        print(f"{year:<8} {total:>6,}件      {pred:>6,}件      {odds:>6,}件      {results:>6,}件      {complete_rate:>5.1f}%")

    print()

    # 欠損データの推定
    print("【2】データ補完後の予測レース数")
    print("-"*80)

    # 2020年と2022年の平均を使って2021年・2023年を推定
    avg_2020_2022 = (year_data.get('2020', {}).get('prediction', 0) +
                     year_data.get('2022', {}).get('prediction', 0)) / 2

    current_2021 = year_data.get('2021', {}).get('prediction', 0)
    current_2023 = year_data.get('2023', {}).get('prediction', 0)

    estimated_2021 = avg_2020_2022
    estimated_2023 = avg_2020_2022

    additional_2021 = estimated_2021 - current_2021
    additional_2023 = estimated_2023 - current_2023
    total_additional = additional_2021 + additional_2023

    print(f"2021年: 現在 {current_2021:>6,}件 → 推定 {estimated_2021:>6,.0f}件 (+{additional_2021:>6,.0f}件)")
    print(f"2023年: 現在 {current_2023:>6,}件 → 推定 {estimated_2023:>6,.0f}件 (+{additional_2023:>6,.0f}件)")
    print(f"合計追加: {total_additional:>6,.0f}件（現在の{100*total_additional/(current_2021+current_2023):.1f}%増）")
    print()

    # 信頼度別のデータ分布
    print("【3】信頼度別データ分布（2021・2023年 vs 他年度）")
    print("-"*80)

    cursor.execute('''
        SELECT
            rp.confidence,
            COUNT(DISTINCT CASE WHEN substr(r.race_date, 1, 4) IN ('2021', '2023') THEN rp.race_id END) as races_2021_2023,
            COUNT(DISTINCT CASE WHEN substr(r.race_date, 1, 4) NOT IN ('2021', '2023') THEN rp.race_id END) as races_other,
            COUNT(DISTINCT rp.race_id) as races_total
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE rp.prediction_type = 'before'
        AND rp.rank_prediction = 1
        AND r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
        GROUP BY rp.confidence
        ORDER BY rp.confidence
    ''')

    print(f"{'信頼度':<8} {'2021/2023':<15} {'他年度':<15} {'合計':<12} {'2021/2023比率':<15}")
    print("-"*80)

    confidence_data = {}
    for row in cursor.fetchall():
        conf, races_2021_2023, races_other, races_total = row
        ratio = 100.0 * races_2021_2023 / races_total if races_total > 0 else 0
        confidence_data[conf] = {
            'races_2021_2023': races_2021_2023,
            'races_other': races_other,
            'races_total': races_total,
            'ratio': ratio
        }
        print(f"{conf:<8} {races_2021_2023:>8,}件      {races_other:>8,}件      {races_total:>6,}件      {ratio:>5.1f}%")

    print()

    # 提案への影響度評価
    print("【4】各提案へのデータ補完の影響度")
    print("="*80)
    print()

    proposals = [
        {
            'id': 1,
            'name': 'パターンH→1点買い切り替え',
            'impact': '影響なし',
            'reason': '既に運用中の最適化済み条件。データ補完による変更なし。',
            'action': '✅ 実施済み',
            'priority': '-'
        },
        {
            'id': 2,
            'name': '信頼度B中心戦略への移行',
            'impact': '影響大',
            'reason': f'''新規B条件の探索が必要。
  - 2021/2023年のBデータ: {confidence_data.get('B', {}).get('races_2021_2023', 0):,}件（全体の{confidence_data.get('B', {}).get('ratio', 0):.1f}%）
  - データ補完で約{total_additional*confidence_data.get('B', {}).get('ratio', 0)/100:,.0f}件追加予定
  - 新規条件の発見・検証精度が大幅向上''',
            'action': '⏸ データ補完後に実施推奨',
            'priority': '高'
        },
        {
            'id': 3,
            'name': 'オッズ10倍未満活用システム',
            'impact': '影響小～中',
            'reason': f'''オッズ傾向の分析は現状データで可能。
  - 信頼度AのROI傾向は既に判明（ROI 168～190%）
  - ただし、実装後の検証精度は向上
  - 2021/2023年のAデータ: {confidence_data.get('A', {}).get('races_2021_2023', 0):,}件''',
            'action': '✅ 今すぐ調査可能（傾向分析）',
            'priority': '中'
        },
        {
            'id': 4,
            'name': '信頼度A条件の拡充',
            'impact': '影響大',
            'reason': f'''新規A条件の探索が必要。
  - 2021/2023年のAデータ: {confidence_data.get('A', {}).get('races_2021_2023', 0):,}件（全体の{confidence_data.get('A', {}).get('ratio', 0):.1f}%）
  - データ補完で約{total_additional*confidence_data.get('A', {}).get('ratio', 0)/100:,.0f}件追加予定
  - 新規条件の信頼性が大幅向上''',
            'action': '⏸ データ補完後に実施推奨',
            'priority': '高'
        },
        {
            'id': 5,
            'name': '3着予測精度向上',
            'impact': '影響極大',
            'reason': f'''機械学習モデルの学習データとして必須。
  - 2021/2023年の全データ: {confidence_data.get('A', {}).get('races_2021_2023', 0) + confidence_data.get('B', {}).get('races_2021_2023', 0) + confidence_data.get('C', {}).get('races_2021_2023', 0) + confidence_data.get('D', {}).get('races_2021_2023', 0) + confidence_data.get('E', {}).get('races_2021_2023', 0):,}件
  - データ補完で約{total_additional:,.0f}件追加（+{100*total_additional/(current_2021+current_2023):.0f}%）
  - 学習データの偏りが大幅に改善
  - モデル精度に直結''',
            'action': '⏸ データ補完後に実施必須',
            'priority': '最高'
        },
    ]

    for p in proposals:
        print(f"提案{p['id']}: {p['name']}")
        print(f"  影響度: {p['impact']}")
        print(f"  理由:")
        for line in p['reason'].split('\n'):
            print(f"    {line}")
        print(f"  アクション: {p['action']}")
        print(f"  優先度: {p['priority']}")
        print()

    # サマリー
    print("="*80)
    print("【結論】")
    print("="*80)
    print()

    print("✅ 今すぐ調査可能（影響小）:")
    print("  - 提案3: オッズ10倍未満活用システム（傾向分析）")
    print("    → 既存データで傾向把握、実装設計可能")
    print()

    print("⏸ データ補完後に実施推奨（影響大）:")
    print("  - 提案2: 信頼度B中心戦略への移行")
    print("  - 提案4: 信頼度A条件の拡充")
    print("  - 提案5: 3着予測精度向上（最優先）")
    print()

    print(f"データ補完による追加レース数: 約{total_additional:,.0f}件")
    print(f"  → 現在の{100*total_additional/(current_2021+current_2023):.1f}%増")
    print(f"  → 統計的信頼性の大幅向上")
    print()

    conn.close()

if __name__ == '__main__':
    analyze_data_completion_impact()
