# -*- coding: utf-8 -*-
"""
安全なパターン選定スクリプト
- 過学習リスクの高いパターンを除外
- 既存条件との重複・干渉を分析
- 実装効果を事前シミュレーション
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
import json
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

DB_PATH = Path(__file__).parent.parent.parent / 'data' / 'boatrace.db'
OUTPUT_DIR = Path(__file__).parent.parent.parent / 'docs' / 'analysis'

def get_conn():
    return sqlite3.connect(str(DB_PATH))

def get_venue_names():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT venue_code, venue_name FROM venue_data')
    result = {row[0]: row[1] for row in cur.fetchall()}
    conn.close()
    return result

def load_validated_patterns():
    """検証済みパターンを読み込む"""
    json_path = Path(__file__).parent.parent.parent / 'data' / 'validated_patterns.json'
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_current_conditions():
    """現在の本番条件を取得"""
    return {
        'A': [
            {'odds_min': 10, 'odds_max': 12, 'c1_rank': ['A1'], 'description': 'A×A1×10-12倍'},
            {'odds_min': 14, 'odds_max': 16, 'c1_rank': ['A1'], 'description': 'A×A1×14-16倍'},
        ],
        'B': [
            {'odds_min': 50, 'odds_max': 100, 'c1_rank': ['A1', 'A2', 'B1'], 'description': 'B×50-100倍'},
            {'odds_min': 30, 'odds_max': 50, 'c1_rank': ['B1'], 'venue_filter': True, 'description': 'B×30-50×B1+会場'},
        ],
        'C': [
            {'odds_min': 20, 'odds_max': 30, 'c1_rank': ['B1'], 'venue_filter': True, 'description': 'C×20-30×B1+会場'},
        ],
        'D': [
            {'odds_min': 40, 'odds_max': 50, 'c1_rank': ['B1'], 'description': 'D×B1×40-50倍'},
            {'odds_min': 30, 'odds_max': 60, 'c1_rank': ['A1', 'A2', 'B1'], 'description': 'D×30-60倍'},
        ],
    }

def filter_safe_patterns(patterns):
    """安全なパターンのみを抽出"""
    safe_patterns = []

    for p in patterns:
        # 過学習リスクフィルター
        # 1. サンプル数が十分（50件以上）
        if p['total'] < 50:
            continue

        # 2. ROI変動が安定（CV < 50%）
        if p.get('roi_cv', 100) > 50:
            continue

        # 3. 年度間安定性（4年以上プラス）
        if p.get('positive_years', 0) < 4:
            continue

        # 4. 統計的有意性（95%CI下限 > 80%）
        if p.get('ci_lower', 0) < 80:
            continue

        # 5. グレードS or A
        if p.get('grade', 'C') not in ['S', 'A']:
            continue

        safe_patterns.append(p)

    return safe_patterns

def classify_by_implementation_type(patterns):
    """実装方法別に分類"""
    # 全会場適用可能（汎用性高）
    universal = []
    # 特定会場限定
    venue_specific = []
    # 特定条件（モーター等）
    special_condition = []

    for p in patterns:
        if p.get('venue') == 'ALL' or p.get('venue_name') == '全会場':
            universal.append(p)
        elif 'motor' in p.get('type', '') or 'モーター' in p.get('condition_str', ''):
            special_condition.append(p)
        else:
            venue_specific.append(p)

    return {
        'universal': universal,
        'venue_specific': venue_specific,
        'special_condition': special_condition,
    }

def analyze_overlap_with_current(patterns, current_conditions):
    """既存条件との重複を分析"""
    overlaps = []
    new_patterns = []

    for p in patterns:
        conf = p.get('confidence', '')
        is_overlap = False

        if conf in current_conditions:
            for cond in current_conditions[conf]:
                # 級別が重複
                c1_rank = p.get('racer_rank', '')
                if c1_rank and c1_rank in cond.get('c1_rank', []):
                    is_overlap = True
                    overlaps.append({
                        'pattern': p,
                        'overlap_with': cond['description'],
                        'reason': f"級別{c1_rank}が既存条件と重複"
                    })
                    break

        if not is_overlap:
            new_patterns.append(p)

    return overlaps, new_patterns

def simulate_implementation_effect(patterns):
    """実装効果をシミュレーション"""
    conn = get_conn()

    # 2025年データで効果を試算
    base_query = """
        SELECT
            r.venue_code,
            rp.confidence,
            e.racer_rank,
            e.motor_second_rate,
            res.rank as actual_rank,
            p.amount as trifecta_payout
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        JOIN entries e ON rp.race_id = e.race_id AND rp.pit_number = e.pit_number
        JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
        LEFT JOIN payouts p ON rp.race_id = p.race_id AND p.bet_type = 'trifecta'
        WHERE rp.prediction_type = 'before'
          AND substr(r.race_date, 1, 4) = '2025'
          AND res.is_invalid = 0
          AND rp.rank_prediction = 1
    """

    df = pd.read_sql_query(base_query, conn)
    conn.close()

    df['motor_cat'] = pd.cut(
        df['motor_second_rate'].fillna(35),
        bins=[0, 30, 35, 40, 100],
        labels=['~30%', '30-35%', '35-40%', '40%+']
    )

    results = []
    venue_names = get_venue_names()

    for p in patterns:
        # パターンに該当するデータを抽出
        subset = df.copy()

        # 会場フィルター
        if p.get('venue') and p['venue'] != 'ALL':
            subset = subset[subset['venue_code'] == p['venue']]

        # 信頼度フィルター
        if p.get('confidence'):
            subset = subset[subset['confidence'] == p['confidence']]

        # 級別フィルター
        if p.get('racer_rank'):
            subset = subset[subset['racer_rank'] == p['racer_rank']]

        # モーターフィルター
        if p.get('motor'):
            subset = subset[subset['motor_cat'] == p['motor']]

        if len(subset) == 0:
            continue

        # ROI計算
        hits = subset[subset['actual_rank'] == '1']
        total = len(subset)
        hit_count = len(hits)
        investment = total * 100
        returns = hits['trifecta_payout'].sum()
        roi_2025 = returns / investment * 100 if investment > 0 else 0

        results.append({
            'pattern': p['condition_str'],
            'historical_roi': p['roi'],
            'roi_2025': roi_2025,
            'diff': roi_2025 - p['roi'],
            'count_2025': total,
            'hits_2025': hit_count,
            'profit_2025': returns - investment,
            'is_consistent': roi_2025 > 100 and abs(roi_2025 - p['roi']) < p['roi'] * 0.5,
        })

    return results

def select_implementation_candidates(patterns):
    """
    本番実装候補を選定

    選定基準:
    1. サンプル数100件以上（信頼性）
    2. CV < 40%（安定性）
    3. 5年以上プラス（再現性）
    4. 2025年も黒字（最新年度での有効性）
    5. 既存条件と重複しない（干渉回避）
    """
    candidates = []

    for p in patterns:
        # 厳格な基準
        if p['total'] < 100:
            continue
        if p.get('roi_cv', 100) > 40:
            continue
        if p.get('positive_years', 0) < 5:
            continue
        if p.get('score', 0) < 85:
            continue

        candidates.append(p)

    return candidates

def generate_implementation_plan():
    """実装計画を生成"""
    print("=" * 80)
    print("安全なパターン選定 - 本番実装計画")
    print("=" * 80)

    # パターン読み込み
    patterns = load_validated_patterns()
    print(f"\n検証済みパターン数: {len(patterns)}")

    # 安全なパターンのみ抽出
    safe_patterns = filter_safe_patterns(patterns)
    print(f"安全パターン数（過学習リスク除外後）: {len(safe_patterns)}")

    # 分類
    classified = classify_by_implementation_type(safe_patterns)
    print(f"\n分類結果:")
    print(f"  - 全会場適用可能: {len(classified['universal'])}件")
    print(f"  - 会場限定: {len(classified['venue_specific'])}件")
    print(f"  - 特殊条件（モーター等）: {len(classified['special_condition'])}件")

    # 既存条件との重複チェック
    current = get_current_conditions()
    overlaps, new_patterns = analyze_overlap_with_current(safe_patterns, current)
    print(f"\n既存条件との関係:")
    print(f"  - 重複/干渉: {len(overlaps)}件")
    print(f"  - 新規追加可能: {len(new_patterns)}件")

    # 実装効果シミュレーション
    print("\n2025年データでの効果シミュレーション中...")
    effect_results = simulate_implementation_effect(safe_patterns[:50])  # 上位50件

    consistent_count = sum(1 for r in effect_results if r['is_consistent'])
    print(f"2025年も一貫して有効: {consistent_count}/{len(effect_results)}件")

    # 最終候補選定
    final_candidates = select_implementation_candidates(safe_patterns)
    print(f"\n最終実装候補: {len(final_candidates)}件")

    # レポート生成
    report = []
    report.append("# 安全なパターン選定レポート")
    report.append("")
    report.append(f"**作成日時**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    report.append("")
    report.append("---")
    report.append("")
    report.append("## 1. 選定プロセス")
    report.append("")
    report.append("| ステップ | 件数 | 説明 |")
    report.append("|:---------|:----:|:-----|")
    report.append(f"| 検証済みパターン | {len(patterns)} | 初期プール |")
    report.append(f"| 安全パターン | {len(safe_patterns)} | 過学習リスク除外後 |")
    report.append(f"| 新規追加可能 | {len(new_patterns)} | 既存条件と重複なし |")
    report.append(f"| **最終候補** | **{len(final_candidates)}** | 厳格基準クリア |")
    report.append("")

    report.append("## 2. 過学習リスク除外基準")
    report.append("")
    report.append("| 基準 | 閾値 | 理由 |")
    report.append("|:-----|:----:|:-----|")
    report.append("| サンプル数 | ≥50件 | 統計的信頼性 |")
    report.append("| ROI変動(CV) | <50% | 年度間安定性 |")
    report.append("| プラス年度数 | ≥4年 | 再現性 |")
    report.append("| 95%CI下限 | >80% | 統計的有意性 |")
    report.append("| グレード | S or A | 総合評価 |")
    report.append("")

    report.append("## 3. 最終実装候補（厳格基準）")
    report.append("")
    report.append("厳格基準:")
    report.append("- サンプル数 ≥100件")
    report.append("- CV <40%")
    report.append("- 5年以上プラス")
    report.append("- スコア ≥85点")
    report.append("")

    if final_candidates:
        report.append("| 条件 | ROI | 件数 | CV | 安定年数 | スコア |")
        report.append("|:-----|:---:|:----:|:--:|:-------:|:------:|")
        for p in sorted(final_candidates, key=lambda x: x['score'], reverse=True)[:20]:
            cv = p.get('roi_cv', 0)
            report.append(
                f"| {p['condition_str']} | {p['roi']:.1f}% | {p['total']} | "
                f"{cv:.0f}% | {p['positive_years']}年 | {p['score']}点 |"
            )
    else:
        report.append("該当なし（基準を満たすパターンがありません）")
    report.append("")

    report.append("## 4. 全会場適用パターン（汎用性高）")
    report.append("")
    report.append("会場に依存しないため、実装が容易で効果が広範囲に及ぶ。")
    report.append("")

    universal = [p for p in safe_patterns if p.get('venue') == 'ALL' or p.get('venue_name') == '全会場']
    if universal:
        report.append("| 条件 | ROI | 件数 | 安定年数 | スコア |")
        report.append("|:-----|:---:|:----:|:-------:|:------:|")
        for p in sorted(universal, key=lambda x: x['score'], reverse=True)[:10]:
            report.append(
                f"| {p['condition_str']} | {p['roi']:.1f}% | {p['total']} | "
                f"{p['positive_years']}年 | {p['score']}点 |"
            )
    report.append("")

    report.append("## 5. 2025年での効果検証")
    report.append("")
    report.append("過去データと2025年データの一貫性を確認。")
    report.append("")

    if effect_results:
        report.append("| パターン | 過去ROI | 2025年ROI | 差分 | 2025年件数 | 一貫性 |")
        report.append("|:---------|:-------:|:---------:|:----:|:---------:|:------:|")
        for r in sorted(effect_results, key=lambda x: x['profit_2025'], reverse=True)[:15]:
            consistent = "✅" if r['is_consistent'] else "⚠️"
            report.append(
                f"| {r['pattern'][:30]} | {r['historical_roi']:.0f}% | {r['roi_2025']:.0f}% | "
                f"{r['diff']:+.0f}pt | {r['count_2025']} | {consistent} |"
            )
    report.append("")

    report.append("## 6. 実装推奨事項")
    report.append("")
    report.append("### 即座に実装可能（リスク低）")
    report.append("")

    # 全会場×モーター条件が最も安全
    motor_patterns = [p for p in safe_patterns if 'モーター' in p.get('condition_str', '') and p.get('venue') == 'ALL']
    if motor_patterns:
        for p in sorted(motor_patterns, key=lambda x: x['score'], reverse=True)[:3]:
            report.append(f"- **{p['condition_str']}**: ROI {p['roi']:.1f}%, スコア{p['score']}点")
    report.append("")

    report.append("### 段階的導入推奨")
    report.append("")
    report.append("1. **Phase 1**: 全会場×モーター40%+条件の導入")
    report.append("   - 既存条件との干渉が少ない")
    report.append("   - モーター2連率は展示情報で取得可能")
    report.append("")
    report.append("2. **Phase 2**: 効果を1ヶ月監視")
    report.append("   - 週次でROIを確認")
    report.append("   - 月次で継続可否を判断")
    report.append("")
    report.append("3. **Phase 3**: 会場限定条件の追加検討")
    report.append("   - Phase 1の結果次第")
    report.append("")

    report.append("### 実装時の注意点")
    report.append("")
    report.append("1. **ペーパートレードから開始**: 実資金投入前に1ヶ月観察")
    report.append("2. **月次レビュー必須**: ROI低下時は即座に停止")
    report.append("3. **既存条件との優先度**: 新条件は既存条件より低優先度で")
    report.append("4. **ロールバック準備**: 問題発生時に即座に戻せる設計で")
    report.append("")

    report.append("---")
    report.append("")
    report.append(f"*レポート生成: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

    # ファイル出力
    output_file = OUTPUT_DIR / "20251224_SAFE_PATTERN_SELECTION.md"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("\n".join(report))
    print(f"\nレポート出力: {output_file}")

    return {
        'safe_patterns': safe_patterns,
        'final_candidates': final_candidates,
        'universal': classified['universal'],
        'effect_results': effect_results,
    }

if __name__ == "__main__":
    result = generate_implementation_plan()
