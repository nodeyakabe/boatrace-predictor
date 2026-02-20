#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
パターンH ゴールデンルール抽出

プラス月の成功パターンを分析し、最も勝ちやすい条件の組み合わせを抽出する。

目的:
1. 最も勝ちやすい条件の組み合わせ（ゴールデンルール）を特定
2. 積極的に狙うべき条件を抽出
3. 取りこぼしを減らすための追加条件を提案
4. 実装優先度を決定
"""
import sys
from pathlib import Path
import json
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

# 分析データを読み込み
DATA_PATH = ROOT_DIR / 'scripts' / 'analysis' / 'pattern_h_winning_analysis.json'


def load_analysis_data():
    """分析データを読み込む"""
    if not DATA_PATH.exists():
        print("警告: 分析データが存在しません。先にanalyze_pattern_h_winning_months.pyを実行してください。")
        return None
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def extract_golden_rules(data):
    """ゴールデンルールを抽出"""
    rules = {
        'priority_1': [],  # 即座に実装すべき条件
        'priority_2': [],  # テスト後に実装すべき条件
        'priority_3': [],  # 長期的に検討すべき条件
        'avoid': [],       # 避けるべき条件
    }

    print("=" * 100)
    print("パターンH ゴールデンルール抽出")
    print("=" * 100)
    print()

    # 1. 会場分析
    print("### 1. 会場別分析 ###")
    print()

    venue_analysis = []
    for v, s in data['venue'].items():
        plus = s['plus']
        minus = s['minus']
        if plus['count'] >= 5:  # サンプル数5以上
            venue_analysis.append({
                'venue_code': v,
                'venue_name': s['name'],
                'plus_count': plus['count'],
                'plus_hits': plus['hits'],
                'plus_roi': plus['roi'],
                'plus_balance': plus['balance'],
                'minus_count': minus['count'],
                'minus_roi': minus['roi'],
                'roi_diff': plus['roi'] - minus['roi'] if minus['count'] > 0 else plus['roi'] - 100,
            })

    # プラス月ROIでソート
    venue_analysis.sort(key=lambda x: x['plus_roi'], reverse=True)

    print("【プラス月で高ROIの会場】")
    print(f"{'会場':<8} {'件数':>6} {'的中':>4} {'ROI':>8} {'収支':>12} {'ROI差':>8}")
    print("-" * 50)
    for v in venue_analysis[:10]:
        print(f"{v['venue_name']:<8} {v['plus_count']:>6} {v['plus_hits']:>4} {v['plus_roi']:>7.1f}% {v['plus_balance']:>+11,} {v['roi_diff']:>+7.1f}")

    # 高ROI会場（ROI 150%以上、収支プラス、サンプル10以上）をゴールデンルールに
    for v in venue_analysis:
        if v['plus_roi'] >= 150 and v['plus_balance'] > 0 and v['plus_count'] >= 10:
            rules['priority_1'].append({
                'type': 'venue',
                'condition': f"会場={v['venue_name']}({v['venue_code']})",
                'roi': v['plus_roi'],
                'balance': v['plus_balance'],
                'sample': v['plus_count'],
                'recommendation': f"会場{v['venue_name']}は積極的に狙う（ROI {v['plus_roi']:.1f}%）",
            })
        elif v['plus_roi'] >= 130 and v['plus_balance'] > 0:
            rules['priority_2'].append({
                'type': 'venue',
                'condition': f"会場={v['venue_name']}({v['venue_code']})",
                'roi': v['plus_roi'],
                'balance': v['plus_balance'],
                'sample': v['plus_count'],
            })

    # 低ROI会場は避けるべき
    print("\n【避けるべき会場（プラス月でもROI低い）】")
    for v in venue_analysis:
        if v['plus_roi'] < 80 and v['plus_count'] >= 5:
            print(f"  {v['venue_name']}: ROI {v['plus_roi']:.1f}%, 収支 {v['plus_balance']:+,}")
            rules['avoid'].append({
                'type': 'venue',
                'condition': f"会場={v['venue_name']}({v['venue_code']})",
                'roi': v['plus_roi'],
                'reason': f"プラス月でもROI低い（{v['plus_roi']:.1f}%）",
            })

    # 2. 信頼度 x 級別分析
    print("\n### 2. 信頼度 x 1コース級別分析 ###")
    print()

    cross_analysis = []
    for key, s in data['cross_analysis'].items():
        parts = key.split('_')
        conf = parts[0]
        rank = parts[1]
        odds_r = parts[2]
        plus = s['plus']
        minus = s['minus']

        if plus['count'] >= 3:  # サンプル数3以上
            cross_analysis.append({
                'key': key,
                'confidence': conf,
                'c1_rank': rank,
                'odds_range': odds_r,
                'plus_count': plus['count'],
                'plus_hits': plus['hits'],
                'plus_roi': plus['roi'],
                'plus_balance': plus['balance'],
                'minus_count': minus['count'],
                'minus_roi': minus['roi'],
            })

    # プラス月収支でソート
    cross_analysis.sort(key=lambda x: x['plus_balance'], reverse=True)

    print("【高収益条件TOP15】")
    print(f"{'条件':<25} {'件数':>6} {'的中':>4} {'ROI':>8} {'収支':>12}")
    print("-" * 60)
    for c in cross_analysis[:15]:
        cond_str = f"{c['confidence']} x {c['c1_rank']} x {c['odds_range']}倍"
        print(f"{cond_str:<25} {c['plus_count']:>6} {c['plus_hits']:>4} {c['plus_roi']:>7.1f}% {c['plus_balance']:>+11,}")

        # 高収益条件をゴールデンルールに追加
        if c['plus_roi'] >= 150 and c['plus_balance'] >= 5000:
            rules['priority_1'].append({
                'type': 'cross_condition',
                'condition': cond_str,
                'confidence': c['confidence'],
                'c1_rank': c['c1_rank'],
                'odds_range': c['odds_range'],
                'roi': c['plus_roi'],
                'balance': c['plus_balance'],
                'sample': c['plus_count'],
                'recommendation': f"条件「{cond_str}」は最優先で狙う（収支 +{c['plus_balance']:,}円）",
            })
        elif c['plus_roi'] >= 120 and c['plus_balance'] >= 3000:
            rules['priority_2'].append({
                'type': 'cross_condition',
                'condition': cond_str,
                'roi': c['plus_roi'],
                'balance': c['plus_balance'],
                'sample': c['plus_count'],
            })

    # 3. 風速分析
    print("\n### 3. 風速別分析 ###")
    print()

    print(f"{'風速':<10} {'プラス月件数':>10} {'プラス月ROI':>10} {'マイナス月ROI':>10}")
    print("-" * 50)
    best_wind = None
    for wind_r, s in data['wind_range'].items():
        plus = s['plus']
        minus = s['minus']
        print(f"{wind_r:<10} {plus['count']:>10} {plus['roi']:>9.1f}% {minus['roi']:>9.1f}%")

        if plus['roi'] > 130 and plus['count'] >= 20:
            if best_wind is None or plus['roi'] > best_wind['plus_roi']:
                best_wind = {
                    'wind_range': wind_r,
                    'plus_roi': plus['roi'],
                    'plus_balance': plus['balance'],
                    'plus_count': plus['count'],
                }

    if best_wind:
        rules['priority_2'].append({
            'type': 'wind',
            'condition': f"風速={best_wind['wind_range']}",
            'roi': best_wind['plus_roi'],
            'balance': best_wind['plus_balance'],
            'sample': best_wind['plus_count'],
            'recommendation': f"風速{best_wind['wind_range']}の条件は優先的に狙う",
        })

    # 4. オッズ範囲分析
    print("\n### 4. オッズ範囲別分析 ###")
    print()

    print(f"{'オッズ範囲':<12} {'プラス月件数':>10} {'プラス月ROI':>10} {'マイナス月ROI':>10}")
    print("-" * 55)
    for odds_r, s in data['odds_range'].items():
        plus = s['plus']
        minus = s['minus']
        if plus['count'] > 0:
            print(f"{odds_r}倍{'':<6} {plus['count']:>10} {plus['roi']:>9.1f}% {minus['roi']:>9.1f}%")

            if plus['roi'] >= 150 and plus['count'] >= 10:
                rules['priority_1'].append({
                    'type': 'odds_range',
                    'condition': f"オッズ範囲={odds_r}倍",
                    'roi': plus['roi'],
                    'balance': plus['balance'],
                    'sample': plus['count'],
                    'recommendation': f"オッズ{odds_r}倍は高ROI（{plus['roi']:.1f}%）",
                })

    # 5. レース番号分析
    print("\n### 5. レース番号別分析 ###")
    print()

    rn_analysis = []
    for rn, s in data['race_number'].items():
        plus = s['plus']
        minus = s['minus']
        if plus['count'] >= 5:
            rn_analysis.append({
                'race_number': rn,
                'plus_count': plus['count'],
                'plus_roi': plus['roi'],
                'plus_balance': plus['balance'],
                'minus_roi': minus['roi'],
            })

    rn_analysis.sort(key=lambda x: x['plus_roi'], reverse=True)

    print("【高ROIレース番号TOP5】")
    print(f"{'R番号':<8} {'件数':>6} {'ROI':>8} {'収支':>12}")
    print("-" * 40)
    for r in rn_analysis[:5]:
        print(f"R{r['race_number']:<7} {r['plus_count']:>6} {r['plus_roi']:>7.1f}% {r['plus_balance']:>+11,}")

    print("\n【低ROIレース番号（避けるべき）】")
    for r in rn_analysis:
        if r['plus_roi'] < 80:
            print(f"  R{r['race_number']}: ROI {r['plus_roi']:.1f}%")
            rules['avoid'].append({
                'type': 'race_number',
                'condition': f"レース番号=R{r['race_number']}",
                'roi': r['plus_roi'],
                'reason': f"プラス月でもROI低い（{r['plus_roi']:.1f}%）",
            })

    # 6. 買い目パターン分析
    print("\n### 6. 買い目パターン分析 ###")
    print()

    print("【どの買い目が的中したか】")
    for pattern, s in data['hit_bet_pattern'].items():
        plus_count = s['plus']['count']
        minus_count = s['minus']['count']
        if pattern != 'miss':
            print(f"  {pattern}: プラス月 {plus_count}件, マイナス月 {minus_count}件")

    # 7. 曜日分析
    print("\n### 7. 曜日別分析 ###")
    print()

    wd_analysis = []
    for wd, s in data['weekday'].items():
        plus = s['plus']
        minus = s['minus']
        wd_analysis.append({
            'weekday': wd,
            'plus_count': plus['count'],
            'plus_roi': plus['roi'],
            'plus_balance': plus['balance'],
            'minus_roi': minus['roi'],
        })

    wd_analysis.sort(key=lambda x: x['plus_roi'], reverse=True)

    print(f"{'曜日':<8} {'件数':>6} {'ROI':>8} {'収支':>12}")
    print("-" * 40)
    for w in wd_analysis:
        print(f"{w['weekday']:<8} {w['plus_count']:>6} {w['plus_roi']:>7.1f}% {w['plus_balance']:>+11,}")

    # 高ROI曜日をルールに追加
    for w in wd_analysis:
        if w['plus_roi'] >= 150 and w['plus_count'] >= 10:
            rules['priority_2'].append({
                'type': 'weekday',
                'condition': f"曜日={w['weekday']}",
                'roi': w['plus_roi'],
                'balance': w['plus_balance'],
                'sample': w['plus_count'],
            })

    # 8. グレード分析
    print("\n### 8. グレード別分析 ###")
    print()

    for grade, s in data['race_grade'].items():
        plus = s['plus']
        minus = s['minus']
        if plus['count'] >= 3:
            print(f"  {grade}: プラス月 {plus['count']}件, ROI {plus['roi']:.1f}%, マイナス月 {minus['count']}件, ROI {minus['roi']:.1f}%")

    return rules


def generate_report(data, rules):
    """最終レポートを生成"""
    report = []

    report.append("# パターンH 2025年プラス月 勝ちパターン分析レポート")
    report.append("")
    report.append("## エグゼクティブサマリー")
    report.append("")

    # サマリー統計
    summary = data['summary']
    report.append("### 全体統計")
    report.append(f"- 全体: {summary['total']['count']}件, ROI {summary['total']['roi']:.1f}%, 収支 {summary['total']['balance']:+,}円")
    report.append(f"- プラス月: {summary['plus_months']['count']}件, ROI {summary['plus_months']['roi']:.1f}%, 収支 {summary['plus_months']['balance']:+,}円")
    report.append(f"- マイナス月: {summary['minus_months']['count']}件, ROI {summary['minus_months']['roi']:.1f}%, 収支 {summary['minus_months']['balance']:+,}円")
    report.append(f"- 高ROI月（6,9,10月）: {summary['high_roi_months']['count']}件, ROI {summary['high_roi_months']['roi']:.1f}%, 収支 {summary['high_roi_months']['balance']:+,}円")
    report.append("")

    # 主要な成功要因
    report.append("### 主要な成功要因TOP3")
    if rules['priority_1']:
        for i, rule in enumerate(rules['priority_1'][:3], 1):
            report.append(f"{i}. **{rule['condition']}**: ROI {rule['roi']:.1f}%, 収支 {rule['balance']:+,}円 (サンプル{rule['sample']}件)")
    report.append("")

    # 推奨実装案サマリー
    report.append("### 推奨実装案サマリー")
    report.append(f"- Priority 1（即実装）: {len(rules['priority_1'])}条件")
    report.append(f"- Priority 2（テスト後）: {len(rules['priority_2'])}条件")
    report.append(f"- Priority 3（長期検討）: {len(rules['priority_3'])}条件")
    report.append(f"- 避けるべき条件: {len(rules['avoid'])}条件")
    report.append("")

    # 月別詳細分析
    report.append("## 1. 月別詳細分析")
    report.append("")

    for month in ['2025-06', '2025-09', '2025-10']:
        if month in data['monthly']:
            m = data['monthly'][month]
            report.append(f"### {month}（ROI {m['roi']:.1f}%）")
            report.append(f"- 購入件数: {m['count']}件")
            report.append(f"- 的中数: {m['hits']}件")
            report.append(f"- 的中率: {m['hit_rate']:.1f}%")
            report.append(f"- 投資額: {m['investment']:,}円")
            report.append(f"- 払戻額: {m['return']:,.0f}円")
            report.append(f"- 収支: {m['balance']:+,}円")
            report.append("")

            if 'hit_races' in m:
                report.append("#### 的中レース詳細")
                for hr in m['hit_races']:
                    report.append(f"- {hr['date']} {hr['venue']} R{hr['race_number']}: "
                                  f"信頼度{hr['confidence']} {hr['c1_rank']} オッズ{hr['odds']:.1f}倍 "
                                  f"払戻{hr['return']:,.0f}円 風速{hr['wind_range']}")
            report.append("")

    # 共通成功パターン
    report.append("## 2. 共通成功パターン")
    report.append("")

    report.append("### 会場")
    report.append("プラス月で高ROIを記録した会場:")
    for v, s in sorted(data['venue'].items(), key=lambda x: x[1]['plus']['roi'], reverse=True)[:5]:
        plus = s['plus']
        if plus['count'] >= 5 and plus['roi'] > 100:
            report.append(f"- **{s['name']}**: ROI {plus['roi']:.1f}%, 収支 {plus['balance']:+,}円")
    report.append("")

    report.append("### 気象条件")
    for wind_r, s in data['wind_range'].items():
        plus = s['plus']
        if plus['count'] >= 10:
            report.append(f"- 風速{wind_r}: ROI {plus['roi']:.1f}%")
    report.append("")

    report.append("### 予測精度（信頼度別）")
    for conf, s in data['confidence'].items():
        plus = s['plus']
        report.append(f"- 信頼度{conf}: {plus['count']}件, 的中率 {plus['hit_rate']:.1f}%, ROI {plus['roi']:.1f}%")
    report.append("")

    report.append("### 買い目パターン")
    for pattern, s in data['hit_bet_pattern'].items():
        if pattern != 'miss':
            report.append(f"- {pattern}: プラス月 {s['plus']['count']}件的中")
    report.append("")

    # プラス月 vs マイナス月 比較
    report.append("## 3. プラス月 vs マイナス月 比較")
    report.append("")

    report.append("| 項目 | プラス月 | マイナス月 | 差 |")
    report.append("|------|----------|------------|-----|")
    report.append(f"| 件数 | {summary['plus_months']['count']} | {summary['minus_months']['count']} | - |")
    report.append(f"| 的中数 | {summary['plus_months']['hits']} | {summary['minus_months']['hits']} | - |")
    report.append(f"| 的中率 | {summary['plus_months']['hit_rate']:.1f}% | {summary['minus_months']['hit_rate']:.1f}% | {summary['plus_months']['hit_rate'] - summary['minus_months']['hit_rate']:+.1f}% |")
    report.append(f"| ROI | {summary['plus_months']['roi']:.1f}% | {summary['minus_months']['roi']:.1f}% | {summary['plus_months']['roi'] - summary['minus_months']['roi']:+.1f}% |")
    report.append(f"| 収支 | {summary['plus_months']['balance']:+,}円 | {summary['minus_months']['balance']:+,}円 | - |")
    report.append("")

    # ゴールデンルール
    report.append("## 4. ゴールデンルール")
    report.append("")
    report.append("### 最も勝ちやすい条件の組み合わせ")
    for i, rule in enumerate(rules['priority_1'][:5], 1):
        report.append(f"{i}. **{rule['condition']}**")
        report.append(f"   - ROI: {rule['roi']:.1f}%")
        report.append(f"   - 収支: {rule['balance']:+,}円")
        report.append(f"   - サンプル数: {rule['sample']}件")
        if 'recommendation' in rule:
            report.append(f"   - 推奨: {rule['recommendation']}")
    report.append("")

    report.append("### 避けるべき条件")
    for rule in rules['avoid'][:5]:
        report.append(f"- **{rule['condition']}**: {rule['reason']}")
    report.append("")

    # 実装推奨案
    report.append("## 5. 実装推奨案")
    report.append("")

    report.append("### Priority 1（即実装）")
    for rule in rules['priority_1']:
        report.append(f"- {rule['condition']}: ROI {rule['roi']:.1f}%, 収支 {rule['balance']:+,}円")
    report.append("")

    report.append("### Priority 2（テスト後）")
    for rule in rules['priority_2']:
        report.append(f"- {rule['condition']}: ROI {rule['roi']:.1f}%")
    report.append("")

    report.append("### Priority 3（長期検討）")
    for rule in rules['priority_3']:
        report.append(f"- {rule['condition']}")
    report.append("")

    # 期待効果
    report.append("## 6. 期待効果")
    report.append("")

    total_expected_improvement = sum(r['balance'] for r in rules['priority_1'] if r['balance'] > 0)
    report.append(f"### Priority 1条件の期待収支改善額")
    report.append(f"- 総期待改善額: +{total_expected_improvement:,}円（年間）")
    report.append("")

    report.append("### リスク評価")
    report.append("- サンプル数が少ない条件は過学習のリスクあり")
    report.append("- 2024年データでの追加検証を推奨")
    report.append("- 段階的な導入（1ヶ月テスト運用後に本格導入）を推奨")
    report.append("")

    report.append("---")
    report.append("*分析日: 2025年12月*")

    return "\n".join(report)


def main():
    # 分析データ読み込み
    data = load_analysis_data()
    if data is None:
        print("データが存在しないため、先に分析スクリプトを実行します...")
        import subprocess
        subprocess.run([sys.executable, str(ROOT_DIR / 'scripts' / 'analysis' / 'analyze_pattern_h_winning_months.py')])
        data = load_analysis_data()
        if data is None:
            print("データの読み込みに失敗しました。")
            return

    # ゴールデンルール抽出
    rules = extract_golden_rules(data)

    # レポート生成
    report = generate_report(data, rules)

    # レポート保存
    output_path = ROOT_DIR / 'docs' / 'PATTERN_H_WINNING_ANALYSIS_2025.md'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)

    print()
    print("=" * 100)
    print(f"レポートを保存しました: {output_path}")
    print("=" * 100)

    # ゴールデンルールをJSON保存
    rules_output_path = ROOT_DIR / 'scripts' / 'analysis' / 'pattern_h_golden_rules.json'
    with open(rules_output_path, 'w', encoding='utf-8') as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)
    print(f"ゴールデンルールを保存しました: {rules_output_path}")


if __name__ == '__main__':
    main()
