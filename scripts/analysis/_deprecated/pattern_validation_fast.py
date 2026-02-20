# -*- coding: utf-8 -*-
"""
パターン信頼性検証スクリプト（高速版）
- 統計的有意性の検証
- サンプルサイズの妥当性
- 年度間安定性の詳細分析
- 過学習リスクの評価
- 本番採用候補の選定
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

def get_base_data():
    """before予測の基礎データを取得"""
    conn = get_conn()

    df = pd.read_sql_query("""
        SELECT
            r.venue_code,
            substr(r.race_date, 1, 4) as year,
            r.race_date,
            rp.race_id,
            rp.pit_number,
            rp.confidence,
            rp.rank_prediction,
            rp.total_score,
            e.racer_rank,
            e.racer_age,
            e.motor_second_rate,
            e.avg_st,
            rd.actual_course,
            rc.wind_speed,
            rc.wind_direction,
            rc.wave_height,
            res.rank as actual_rank,
            res.kimarite,
            p.amount as trifecta_payout
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        JOIN entries e ON rp.race_id = e.race_id AND rp.pit_number = e.pit_number
        LEFT JOIN race_details rd ON rp.race_id = rd.race_id AND rp.pit_number = rd.pit_number
        LEFT JOIN race_conditions rc ON rp.race_id = rc.race_id
        JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
        LEFT JOIN payouts p ON rp.race_id = p.race_id AND p.bet_type = 'trifecta'
        WHERE rp.prediction_type = 'before'
          AND substr(r.race_date, 1, 4) >= '2020'
          AND res.is_invalid = 0
          AND rp.rank_prediction = 1
    """, conn)

    conn.close()
    return df

def calculate_roi_simple(df, investment=100):
    """ROI計算（シンプル版）"""
    if len(df) == 0:
        return {'roi': 0, 'hits': 0, 'total': 0, 'hit_rate': 0, 'payout_mean': 0, 'payout_std': 0}

    hits = df[df['actual_rank'] == '1']
    hit_count = len(hits)
    total = len(df)
    hit_rate = hit_count / total * 100 if total > 0 else 0

    total_investment = total * investment
    total_return = hits['trifecta_payout'].sum() if hit_count > 0 else 0
    roi = (total_return / total_investment * 100) if total_investment > 0 else 0

    if hit_count > 0:
        payouts = hits['trifecta_payout'].values
        payout_mean = np.mean(payouts)
        payout_std = np.std(payouts)
    else:
        payout_mean = payout_std = 0

    return {
        'roi': roi,
        'hits': hit_count,
        'total': total,
        'hit_rate': hit_rate,
        'payout_mean': payout_mean,
        'payout_std': payout_std
    }

def calculate_confidence_interval(roi, hits, total, payouts_sum, investment=100):
    """信頼区間の近似計算（正規近似）"""
    if total < 30 or hits < 3:
        return roi, roi, False

    # 平均リターンとその分散
    mean_return = payouts_sum / total if total > 0 else 0
    p = hits / total  # 的中確率

    # 二項分布の標準誤差
    se = np.sqrt(p * (1 - p) / total) * (payouts_sum / hits if hits > 0 else 0)

    # 95%信頼区間
    z = 1.96
    ci_lower = (mean_return - z * se) / investment * 100
    ci_upper = (mean_return + z * se) / investment * 100

    is_significant = ci_lower > 100

    return ci_lower, ci_upper, is_significant

def analyze_yearly_stability(df, condition_func):
    """年度別安定性分析"""
    years = ['2020', '2021', '2022', '2023', '2024', '2025']
    yearly_stats = {}
    positive_years = 0
    all_rois = []

    for year in years:
        year_data = df[df['year'] == year]
        subset = condition_func(year_data)
        if len(subset) >= 5:
            stats_result = calculate_roi_simple(subset)
            yearly_stats[year] = stats_result
            all_rois.append(stats_result['roi'])
            if stats_result['roi'] > 100:
                positive_years += 1
        else:
            yearly_stats[year] = None

    if len(all_rois) >= 3:
        roi_std = np.std(all_rois)
        roi_mean = np.mean(all_rois)
        roi_cv = roi_std / roi_mean * 100 if roi_mean > 0 else float('inf')
        min_roi = min(all_rois)
        max_roi = max(all_rois)
    else:
        roi_std = roi_cv = 0
        min_roi = max_roi = all_rois[0] if all_rois else 0

    return {
        'yearly_stats': yearly_stats,
        'positive_years': positive_years,
        'roi_std': roi_std,
        'roi_cv': roi_cv,
        'min_roi': min_roi,
        'max_roi': max_roi
    }

def evaluate_reliability(stats, yearly, total, hits, payouts_sum):
    """信頼性評価"""
    score = 0
    reasons = []
    warnings = []

    # 信頼区間計算
    ci_lower, ci_upper, is_significant = calculate_confidence_interval(
        stats['roi'], hits, total, payouts_sum
    )

    # 1. サンプルサイズ
    if total >= 100:
        score += 30
        reasons.append(f"十分なサンプル数({total}件)")
    elif total >= 50:
        score += 20
        reasons.append(f"中程度のサンプル数({total}件)")
    elif total >= 30:
        score += 10
        warnings.append(f"サンプル数がやや少ない({total}件)")
    else:
        warnings.append(f"サンプル数不足({total}件)")

    # 2. 統計的有意性
    if is_significant:
        score += 25
        reasons.append("統計的に有意(95%CI下限>100%)")
    else:
        warnings.append("統計的有意性なし")

    # 3. 年度間安定性
    positive_years = yearly['positive_years']
    if positive_years >= 5:
        score += 25
        reasons.append(f"高安定性({positive_years}年プラス)")
    elif positive_years >= 4:
        score += 20
        reasons.append(f"良好な安定性({positive_years}年プラス)")
    elif positive_years >= 3:
        score += 10
        warnings.append(f"安定性やや不足({positive_years}年プラス)")
    else:
        warnings.append(f"安定性不足({positive_years}年プラス)")

    # 4. ROI変動
    roi_cv = yearly['roi_cv']
    if roi_cv < 30:
        score += 10
        reasons.append(f"ROI変動小(CV={roi_cv:.1f}%)")
    elif roi_cv < 50:
        score += 5
    else:
        warnings.append(f"ROI変動大(CV={roi_cv:.1f}%)")

    # 5. 最悪年度
    min_roi = yearly['min_roi']
    if min_roi >= 80:
        score += 10
        reasons.append(f"最悪年度良好(最低ROI={min_roi:.1f}%)")
    elif min_roi >= 50:
        score += 5
    else:
        warnings.append(f"最悪年度低い(最低ROI={min_roi:.1f}%)")

    # グレード判定
    if score >= 80:
        grade = 'S'
        recommendation = '本番採用推奨'
    elif score >= 60:
        grade = 'A'
        recommendation = '本番採用可能（監視必要）'
    elif score >= 40:
        grade = 'B'
        recommendation = '参考情報として活用'
    else:
        grade = 'C'
        recommendation = '採用非推奨'

    return {
        'score': score,
        'grade': grade,
        'recommendation': recommendation,
        'ci_lower': ci_lower,
        'ci_upper': ci_upper,
        'is_significant': is_significant,
        'reasons': reasons,
        'warnings': warnings
    }

def validate_patterns():
    """パターン検証"""
    print("=" * 80)
    print("パターン信頼性検証（高速版）")
    print("=" * 80)

    venue_names = get_venue_names()

    print("\nデータ読み込み中...")
    df = get_base_data()
    print(f"総レコード数: {len(df):,}")

    # カテゴリ変数作成
    df['motor_cat'] = pd.cut(
        df['motor_second_rate'].fillna(35),
        bins=[0, 30, 35, 40, 100],
        labels=['~30%', '30-35%', '35-40%', '40%+']
    )

    df['age_cat'] = pd.cut(
        df['racer_age'].fillna(35),
        bins=[0, 30, 40, 50, 100],
        labels=['~30', '31-40', '41-50', '51+']
    )

    validated_patterns = []

    # パターン1: 会場×信頼度×級別（主要パターン）
    print("\n検証中: 会場×信頼度×級別...")
    pattern_count = 0
    for venue in df['venue_code'].unique():
        for conf in ['A', 'B', 'C', 'D']:
            for rank in ['A1', 'A2', 'B1', 'B2']:
                subset = df[(df['venue_code'] == venue) &
                           (df['confidence'] == conf) &
                           (df['racer_rank'] == rank)]

                if len(subset) >= 30:
                    stats = calculate_roi_simple(subset)

                    if stats['roi'] > 100:
                        # 年度別分析
                        condition_func = lambda d, v=venue, c=conf, r=rank: d[
                            (d['venue_code'] == v) & (d['confidence'] == c) & (d['racer_rank'] == r)
                        ]
                        yearly = analyze_yearly_stability(df, condition_func)

                        # 配当合計
                        hits_df = subset[subset['actual_rank'] == '1']
                        payouts_sum = hits_df['trifecta_payout'].sum()

                        # 信頼性評価
                        reliability = evaluate_reliability(
                            stats, yearly, len(subset), stats['hits'], payouts_sum
                        )

                        validated_patterns.append({
                            'type': 'venue_conf_rank',
                            'venue': venue,
                            'venue_name': venue_names.get(venue, venue),
                            'confidence': conf,
                            'racer_rank': rank,
                            'condition_str': f"{venue_names.get(venue, venue)} × 信頼度{conf} × {rank}",
                            **stats,
                            **yearly,
                            **reliability
                        })
                        pattern_count += 1

    print(f"  発見: {pattern_count}件")

    # パターン2: 会場×信頼度×モーター40%+
    print("検証中: 会場×信頼度×モーター40%+...")
    pattern_count = 0
    for venue in df['venue_code'].unique():
        for conf in ['A', 'B', 'C', 'D']:
            subset = df[(df['venue_code'] == venue) &
                       (df['confidence'] == conf) &
                       (df['motor_cat'] == '40%+')]

            if len(subset) >= 30:
                stats = calculate_roi_simple(subset)

                if stats['roi'] > 100:
                    condition_func = lambda d, v=venue, c=conf: d[
                        (d['venue_code'] == v) & (d['confidence'] == c) & (d['motor_cat'] == '40%+')
                    ]
                    yearly = analyze_yearly_stability(df, condition_func)

                    hits_df = subset[subset['actual_rank'] == '1']
                    payouts_sum = hits_df['trifecta_payout'].sum()

                    reliability = evaluate_reliability(
                        stats, yearly, len(subset), stats['hits'], payouts_sum
                    )

                    validated_patterns.append({
                        'type': 'venue_conf_motor',
                        'venue': venue,
                        'venue_name': venue_names.get(venue, venue),
                        'confidence': conf,
                        'motor': '40%+',
                        'condition_str': f"{venue_names.get(venue, venue)} × 信頼度{conf} × モーター40%+",
                        **stats,
                        **yearly,
                        **reliability
                    })
                    pattern_count += 1

    print(f"  発見: {pattern_count}件")

    # パターン3: 全会場×信頼度×級別×モーター（汎用パターン）
    print("検証中: 全会場×信頼度×級別×モーター...")
    pattern_count = 0
    for conf in ['A', 'B', 'C', 'D']:
        for rank in ['A1', 'A2', 'B1', 'B2']:
            subset = df[(df['confidence'] == conf) &
                       (df['racer_rank'] == rank) &
                       (df['motor_cat'] == '40%+')]

            if len(subset) >= 50:
                stats = calculate_roi_simple(subset)

                if stats['roi'] > 100:
                    condition_func = lambda d, c=conf, r=rank: d[
                        (d['confidence'] == c) & (d['racer_rank'] == r) & (d['motor_cat'] == '40%+')
                    ]
                    yearly = analyze_yearly_stability(df, condition_func)

                    hits_df = subset[subset['actual_rank'] == '1']
                    payouts_sum = hits_df['trifecta_payout'].sum()

                    reliability = evaluate_reliability(
                        stats, yearly, len(subset), stats['hits'], payouts_sum
                    )

                    validated_patterns.append({
                        'type': 'conf_rank_motor',
                        'venue': 'ALL',
                        'venue_name': '全会場',
                        'confidence': conf,
                        'racer_rank': rank,
                        'motor': '40%+',
                        'condition_str': f"全会場 × 信頼度{conf} × {rank} × モーター40%+",
                        **stats,
                        **yearly,
                        **reliability
                    })
                    pattern_count += 1

    print(f"  発見: {pattern_count}件")

    # パターン4: 会場×信頼度（シンプル）
    print("検証中: 会場×信頼度...")
    pattern_count = 0
    for venue in df['venue_code'].unique():
        for conf in ['A', 'B', 'C', 'D']:
            subset = df[(df['venue_code'] == venue) & (df['confidence'] == conf)]

            if len(subset) >= 50:
                stats = calculate_roi_simple(subset)

                if stats['roi'] > 100:
                    condition_func = lambda d, v=venue, c=conf: d[
                        (d['venue_code'] == v) & (d['confidence'] == c)
                    ]
                    yearly = analyze_yearly_stability(df, condition_func)

                    hits_df = subset[subset['actual_rank'] == '1']
                    payouts_sum = hits_df['trifecta_payout'].sum()

                    reliability = evaluate_reliability(
                        stats, yearly, len(subset), stats['hits'], payouts_sum
                    )

                    validated_patterns.append({
                        'type': 'venue_conf',
                        'venue': venue,
                        'venue_name': venue_names.get(venue, venue),
                        'confidence': conf,
                        'condition_str': f"{venue_names.get(venue, venue)} × 信頼度{conf}",
                        **stats,
                        **yearly,
                        **reliability
                    })
                    pattern_count += 1

    print(f"  発見: {pattern_count}件")

    print(f"\n検証完了: 合計{len(validated_patterns)}パターン")
    return validated_patterns, df

def generate_report(patterns):
    """レポート生成"""
    grade_s = [p for p in patterns if p['grade'] == 'S']
    grade_a = [p for p in patterns if p['grade'] == 'A']
    grade_b = [p for p in patterns if p['grade'] == 'B']
    grade_c = [p for p in patterns if p['grade'] == 'C']

    report = []
    report.append("# パターン信頼性検証レポート")
    report.append("")
    report.append(f"**検証日時**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    report.append(f"**検証パターン数**: {len(patterns)}")
    report.append("")
    report.append("---")
    report.append("")
    report.append("## 1. サマリー")
    report.append("")
    report.append("| グレード | 件数 | 説明 |")
    report.append("|:------:|:----:|:-----|")
    report.append(f"| **S** | {len(grade_s)} | 本番採用推奨 |")
    report.append(f"| **A** | {len(grade_a)} | 本番採用可能（監視必要） |")
    report.append(f"| **B** | {len(grade_b)} | 参考情報として活用 |")
    report.append(f"| **C** | {len(grade_c)} | 採用非推奨 |")
    report.append("")

    report.append("### 評価基準")
    report.append("")
    report.append("| 項目 | 配点 | 基準 |")
    report.append("|:-----|:----:|:-----|")
    report.append("| サンプルサイズ | 30点 | 100件以上=30点, 50件以上=20点, 30件以上=10点 |")
    report.append("| 統計的有意性 | 25点 | 95%信頼区間下限>100% |")
    report.append("| 年度間安定性 | 25点 | 5年以上プラス=25点, 4年=20点, 3年=10点 |")
    report.append("| ROI変動安定性 | 10点 | CV<30%=10点, CV<50%=5点 |")
    report.append("| 最悪年度ROI | 10点 | 最低ROI>=80%=10点, >=50%=5点 |")
    report.append("")
    report.append("**グレード判定**: S(80点以上), A(60点以上), B(40点以上), C(40点未満)")
    report.append("")

    report.append("---")
    report.append("")
    report.append("## 2. グレードS: 本番採用推奨パターン")
    report.append("")

    if grade_s:
        report.append("| 条件 | ROI | 的中 | 件数 | 95%CI | 安定年数 | スコア |")
        report.append("|:-----|:---:|:----:|:----:|:-----:|:-------:|:------:|")
        for p in sorted(grade_s, key=lambda x: x['roi'], reverse=True):
            ci_str = f"{p['ci_lower']:.0f}-{p['ci_upper']:.0f}%"
            report.append(
                f"| {p['condition_str']} | {p['roi']:.1f}% | {p['hits']}/{p['total']} | "
                f"{p['total']} | {ci_str} | {p['positive_years']}年 | {p['score']}点 |"
            )
        report.append("")

        report.append("### グレードS詳細")
        report.append("")
        for i, p in enumerate(sorted(grade_s, key=lambda x: x['roi'], reverse=True)[:10], 1):
            report.append(f"#### {i}. {p['condition_str']}")
            report.append("")
            report.append(f"- **ROI**: {p['roi']:.1f}%")
            report.append(f"- **的中率**: {p['hit_rate']:.2f}% ({p['hits']}/{p['total']})")
            report.append(f"- **95%信頼区間**: {p['ci_lower']:.1f}% - {p['ci_upper']:.1f}%")
            report.append(f"- **平均配当**: {p['payout_mean']:.0f}円")
            report.append(f"- **評価スコア**: {p['score']}点")
            report.append("")
            report.append("**年度別ROI**:")
            report.append("")
            report.append("| 年度 | ROI | 的中/件数 | 判定 |")
            report.append("|:----:|:---:|:---------:|:----:|")
            for year in ['2020', '2021', '2022', '2023', '2024', '2025']:
                ys = p['yearly_stats'].get(year)
                if ys:
                    mark = "✅" if ys['roi'] > 100 else "❌"
                    report.append(f"| {year} | {ys['roi']:.1f}% | {ys['hits']}/{ys['total']} | {mark} |")
                else:
                    report.append(f"| {year} | - | データなし | - |")
            report.append("")
            report.append("**採用理由**: " + " / ".join(p['reasons']))
            if p['warnings']:
                report.append("")
                report.append("**注意点**: " + " / ".join(p['warnings']))
            report.append("")
    else:
        report.append("該当パターンなし")
        report.append("")

    report.append("---")
    report.append("")
    report.append("## 3. グレードA: 本番採用可能パターン")
    report.append("")

    if grade_a:
        report.append("| 条件 | ROI | 的中 | 件数 | 95%CI | 安定年数 | スコア |")
        report.append("|:-----|:---:|:----:|:----:|:-----:|:-------:|:------:|")
        for p in sorted(grade_a, key=lambda x: x['roi'], reverse=True)[:30]:
            ci_str = f"{p['ci_lower']:.0f}-{p['ci_upper']:.0f}%"
            report.append(
                f"| {p['condition_str']} | {p['roi']:.1f}% | {p['hits']}/{p['total']} | "
                f"{p['total']} | {ci_str} | {p['positive_years']}年 | {p['score']}点 |"
            )
        if len(grade_a) > 30:
            report.append(f"| ... | 他{len(grade_a)-30}件 | | | | | |")
    else:
        report.append("該当パターンなし")
    report.append("")

    report.append("---")
    report.append("")
    report.append("## 4. グレードB: 参考パターン（TOP20）")
    report.append("")

    if grade_b:
        report.append("| 条件 | ROI | 的中/件数 | スコア | 主な注意点 |")
        report.append("|:-----|:---:|:---------:|:------:|:----------|")
        for p in sorted(grade_b, key=lambda x: x['roi'], reverse=True)[:20]:
            warn = p['warnings'][0] if p['warnings'] else "-"
            report.append(
                f"| {p['condition_str']} | {p['roi']:.1f}% | "
                f"{p['hits']}/{p['total']} | {p['score']}点 | {warn} |"
            )
    else:
        report.append("該当パターンなし")
    report.append("")

    report.append("---")
    report.append("")
    report.append("## 5. 過学習リスク分析")
    report.append("")

    high_risk = [p for p in patterns if
                 p['total'] < 50 or p['roi_cv'] > 50 or p['positive_years'] <= 2]

    report.append(f"### 過学習リスクが高いパターン: {len(high_risk)}件")
    report.append("")
    report.append("以下の特徴を持つパターンは過学習の可能性が高い:")
    report.append("")
    report.append("1. サンプル数が少ない (50件未満)")
    report.append("2. 年度間のROI変動が大きい (CV > 50%)")
    report.append("3. 特定年度のみ高ROI (2年以下のみプラス)")
    report.append("")

    if high_risk:
        report.append("| 条件 | ROI | 件数 | リスク要因 |")
        report.append("|:-----|:---:|:----:|:----------|")
        for p in sorted(high_risk, key=lambda x: x['roi'], reverse=True)[:15]:
            risks = []
            if p['total'] < 50:
                risks.append(f"サンプル少({p['total']}件)")
            if p['roi_cv'] > 50:
                risks.append(f"変動大(CV={p['roi_cv']:.0f}%)")
            if p['positive_years'] <= 2:
                risks.append(f"安定性低({p['positive_years']}年)")
            report.append(f"| {p['condition_str']} | {p['roi']:.1f}% | {p['total']} | {'; '.join(risks)} |")
    report.append("")

    report.append("---")
    report.append("")
    report.append("## 6. 本番実装推奨事項")
    report.append("")

    if grade_s:
        report.append("### 即座に採用可能（グレードS）")
        report.append("")
        for p in sorted(grade_s, key=lambda x: x['roi'], reverse=True)[:10]:
            report.append(f"- **{p['condition_str']}**: ROI {p['roi']:.1f}%, {p['positive_years']}年安定")
        report.append("")

    if grade_a:
        report.append("### 監視付きで採用可能（グレードA上位）")
        report.append("")
        for p in sorted(grade_a, key=lambda x: x['score'], reverse=True)[:10]:
            report.append(f"- **{p['condition_str']}**: ROI {p['roi']:.1f}%, スコア{p['score']}点")
        report.append("")

    report.append("### 実装時の注意事項")
    report.append("")
    report.append("1. **段階的導入**: まずは小額での運用を推奨")
    report.append("2. **月次監視**: 月単位でROIを監視し、低下傾向があれば見直し")
    report.append("3. **複合条件の注意**: 条件を複雑にしすぎると過学習リスク増大")
    report.append("4. **市場変化**: 公開情報が広まると収益性が低下する可能性あり")
    report.append("")

    report.append("---")
    report.append("")
    report.append(f"*レポート生成: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

    return "\n".join(report)

def main():
    # 検証実行
    patterns, df = validate_patterns()

    # 結果表示
    print("\n" + "=" * 80)
    print("【グレード別集計】")
    print("=" * 80)

    for grade in ['S', 'A', 'B', 'C']:
        grade_patterns = [p for p in patterns if p['grade'] == grade]
        print(f"\nグレード{grade}: {len(grade_patterns)}件")

        if grade in ['S', 'A'] and grade_patterns:
            print("-" * 60)
            for p in sorted(grade_patterns, key=lambda x: x['roi'], reverse=True)[:5]:
                print(f"  {p['condition_str']}")
                print(f"    ROI: {p['roi']:.1f}% | 的中: {p['hits']}/{p['total']} | "
                      f"スコア: {p['score']}点 | 安定: {p['positive_years']}年")

    # レポート生成
    print("\n" + "=" * 80)
    print("レポート生成中...")

    report = generate_report(patterns)
    output_file = OUTPUT_DIR / "20251224_PATTERN_VALIDATION_REPORT.md"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"レポート出力: {output_file}")

    # JSON出力
    json_file = Path(__file__).parent.parent.parent / 'data' / 'validated_patterns.json'
    patterns_for_json = []
    for p in patterns:
        p_copy = p.copy()
        if 'yearly_stats' in p_copy and p_copy['yearly_stats']:
            p_copy['yearly_stats'] = {
                str(k): v for k, v in p_copy['yearly_stats'].items() if v
            }
        patterns_for_json.append(p_copy)
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(patterns_for_json, f, ensure_ascii=False, indent=2, default=str)
    print(f"JSON出力: {json_file}")

    return patterns

if __name__ == "__main__":
    patterns = main()
