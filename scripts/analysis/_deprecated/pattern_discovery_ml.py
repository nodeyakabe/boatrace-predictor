"""
複合条件パターン発見スクリプト（機械学習 + 逆引き分析）
=======================================================

Phase A: 結果ベース逆引き - 的中レースの共通パターン抽出
Phase B: 機械学習 - 重要度分析と交互作用検出

使用例:
    # 全分析実行
    python scripts/analysis/pattern_discovery_ml.py

    # Phase Aのみ（逆引き分析）
    python scripts/analysis/pattern_discovery_ml.py --phase A

    # Phase Bのみ（機械学習）
    python scripts/analysis/pattern_discovery_ml.py --phase B

    # beforeデータのみ
    python scripts/analysis/pattern_discovery_ml.py --prediction-type before

    # 特定年度範囲
    python scripts/analysis/pattern_discovery_ml.py --years 2022-2025
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from collections import Counter
import json
import argparse
import warnings
warnings.filterwarnings('ignore')

# 機械学習ライブラリ
try:
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.model_selection import cross_val_score
    from sklearn.preprocessing import LabelEncoder
    import shap
    HAS_ML = True
except ImportError:
    HAS_ML = False
    print("警告: sklearn/shap がインストールされていません。Phase Bは実行できません。")


# 分析対象の条件軸
FEATURE_COLUMNS = [
    'venue_code',
    'confidence',
    'course1_rank',
    'odds_band',
    'score_diff_band',
    'motor_band',
    'wind_band',
    'predicted_pit',  # 予測コース
    'race_grade',
    'is_nighter',
    'weather',
]


def load_data(db_path: str, prediction_type: str = 'before',
              years: tuple = None) -> pd.DataFrame:
    """統合分析テーブルからデータ読み込み"""

    conn = sqlite3.connect(db_path)

    query = """
        SELECT *
        FROM ml_analysis_features
        WHERE prediction_type = ?
    """
    params = [prediction_type]

    if years:
        query += f" AND year BETWEEN ? AND ?"
        params.extend([str(years[0]), str(years[1])])

    df = pd.read_sql_query(query, conn, params=params)
    conn.close()

    print(f"データ読み込み: {len(df):,}件 ({prediction_type}, {years or '全年度'})")
    return df


# =============================================================================
# Phase A: 結果ベース逆引き分析
# =============================================================================

def analyze_hit_patterns(df: pd.DataFrame, min_samples: int = 100) -> dict:
    """
    的中レースの共通パターンを分析

    Returns:
        分析結果の辞書
    """
    print("\n" + "=" * 60)
    print("Phase A: 結果ベース逆引き分析")
    print("=" * 60)

    results = {
        'high_roi_patterns': [],
        'stable_patterns': [],
        'short_term_patterns': [],
        'condition_frequencies': {},
    }

    # 的中/不的中のデータ分離
    hits = df[df['is_trifecta_hit'] == 1].copy()
    misses = df[df['is_trifecta_hit'] == 0].copy()

    print(f"\n的中レース: {len(hits):,}件 ({len(hits)/len(df)*100:.2f}%)")
    print(f"不的中レース: {len(misses):,}件")

    # 高配当的中の抽出（50倍以上）
    high_payout = hits[hits['trifecta_payout'] >= 5000]
    print(f"高配当的中（50倍+）: {len(high_payout):,}件")

    # -----------------------------------------
    # 1. 各条件の的中率比較（単一条件）
    # -----------------------------------------
    print("\n--- 単一条件の的中率 ---")

    for col in FEATURE_COLUMNS:
        if col not in df.columns:
            continue

        analysis = df.groupby(col).agg({
            'is_trifecta_hit': ['sum', 'count', 'mean'],
            'trifecta_payout': 'sum'
        }).round(4)

        analysis.columns = ['hits', 'total', 'hit_rate', 'total_payout']
        analysis['roi'] = (analysis['total_payout'] / (analysis['total'] * 100) * 100).round(1)
        analysis = analysis[analysis['total'] >= min_samples]
        analysis = analysis.sort_values('roi', ascending=False)

        results['condition_frequencies'][col] = analysis.to_dict('index')

        # 上位3件を表示
        print(f"\n{col}:")
        for idx, row in analysis.head(3).iterrows():
            print(f"  {idx}: ROI {row['roi']:.1f}%, 的中率 {row['hit_rate']*100:.2f}% ({int(row['total'])}件)")

    # -----------------------------------------
    # 2. 2条件の組み合わせ分析
    # -----------------------------------------
    print("\n--- 2条件の組み合わせ（上位20件） ---")

    two_cond_results = []

    # 主要な条件ペアを分析
    key_pairs = [
        ('confidence', 'odds_band'),
        ('confidence', 'course1_rank'),
        ('confidence', 'venue_code'),
        ('odds_band', 'course1_rank'),
        ('confidence', 'motor_band'),
        ('venue_code', 'odds_band'),
        ('confidence', 'predicted_pit'),
        ('venue_code', 'course1_rank'),
    ]

    for col1, col2 in key_pairs:
        if col1 not in df.columns or col2 not in df.columns:
            continue

        grouped = df.groupby([col1, col2]).agg({
            'is_trifecta_hit': ['sum', 'count'],
            'trifecta_payout': 'sum'
        })
        grouped.columns = ['hits', 'total', 'total_payout']
        grouped['roi'] = (grouped['total_payout'] / (grouped['total'] * 100) * 100).round(1)
        grouped['hit_rate'] = (grouped['hits'] / grouped['total'] * 100).round(2)
        grouped = grouped[grouped['total'] >= min_samples]
        grouped = grouped.reset_index()

        for _, row in grouped.iterrows():
            two_cond_results.append({
                'conditions': f"{col1}:{row[col1]} × {col2}:{row[col2]}",
                'col1': col1, 'val1': row[col1],
                'col2': col2, 'val2': row[col2],
                'roi': row['roi'],
                'hit_rate': row['hit_rate'],
                'total': int(row['total']),
                'hits': int(row['hits']),
            })

    # ROI順にソート
    two_cond_results = sorted(two_cond_results, key=lambda x: x['roi'], reverse=True)

    for item in two_cond_results[:20]:
        print(f"  {item['conditions']}: ROI {item['roi']:.1f}%, 的中率 {item['hit_rate']:.2f}% ({item['total']}件)")

    results['high_roi_patterns'] = two_cond_results[:50]

    # -----------------------------------------
    # 3. 3条件の組み合わせ分析
    # -----------------------------------------
    print("\n--- 3条件の組み合わせ（上位20件） ---")

    three_cond_results = []

    # 有望な2条件から拡張
    promising_pairs = two_cond_results[:30]  # 上位30ペアを拡張

    extension_cols = ['motor_band', 'wind_band', 'predicted_pit', 'venue_code', 'course1_rank']

    for pair in promising_pairs:
        col1, val1 = pair['col1'], pair['val1']
        col2, val2 = pair['col2'], pair['val2']

        subset = df[(df[col1] == val1) & (df[col2] == val2)]

        for col3 in extension_cols:
            if col3 in [col1, col2] or col3 not in df.columns:
                continue

            grouped = subset.groupby(col3).agg({
                'is_trifecta_hit': ['sum', 'count'],
                'trifecta_payout': 'sum'
            })
            grouped.columns = ['hits', 'total', 'total_payout']
            grouped['roi'] = (grouped['total_payout'] / (grouped['total'] * 100) * 100).round(1)
            grouped['hit_rate'] = (grouped['hits'] / grouped['total'] * 100).round(2)
            grouped = grouped[grouped['total'] >= min_samples]
            grouped = grouped.reset_index()

            for _, row in grouped.iterrows():
                three_cond_results.append({
                    'conditions': f"{col1}:{val1} × {col2}:{val2} × {col3}:{row[col3]}",
                    'cols': [col1, col2, col3],
                    'vals': [val1, val2, row[col3]],
                    'roi': row['roi'],
                    'hit_rate': row['hit_rate'],
                    'total': int(row['total']),
                    'hits': int(row['hits']),
                })

    # 重複除去とソート
    seen = set()
    unique_results = []
    for item in three_cond_results:
        key = tuple(sorted(zip(item['cols'], [str(v) for v in item['vals']])))
        if key not in seen:
            seen.add(key)
            unique_results.append(item)

    three_cond_results = sorted(unique_results, key=lambda x: x['roi'], reverse=True)

    for item in three_cond_results[:20]:
        print(f"  {item['conditions']}: ROI {item['roi']:.1f}%, 的中率 {item['hit_rate']:.2f}% ({item['total']}件)")

    results['high_roi_patterns'].extend(three_cond_results[:50])

    # -----------------------------------------
    # 4. 年度別安定性分析
    # -----------------------------------------
    print("\n--- 年度別安定パターン（6年間プラスROI） ---")

    stable_patterns = []

    for pattern in (two_cond_results + three_cond_results)[:100]:
        if 'cols' in pattern:
            cols, vals = pattern['cols'], pattern['vals']
        else:
            cols = [pattern['col1'], pattern['col2']]
            vals = [pattern['val1'], pattern['val2']]

        # 条件でフィルタ
        mask = pd.Series([True] * len(df))
        for c, v in zip(cols, vals):
            mask &= (df[c] == v)
        subset = df[mask]

        if len(subset) < min_samples:
            continue

        # 年度別集計
        yearly = subset.groupby('year').agg({
            'is_trifecta_hit': 'sum',
            'trifecta_payout': 'sum',
            'race_id': 'count'
        })
        yearly.columns = ['hits', 'payout', 'total']
        yearly['roi'] = (yearly['payout'] / (yearly['total'] * 100) * 100).round(1)

        positive_years = (yearly['roi'] > 100).sum()
        total_years = len(yearly)

        if positive_years >= 4:  # 4年以上プラス
            stable_patterns.append({
                'conditions': pattern['conditions'],
                'positive_years': positive_years,
                'total_years': total_years,
                'total_roi': pattern['roi'],
                'total_samples': pattern['total'],
                'yearly_roi': yearly['roi'].to_dict(),
            })

    stable_patterns = sorted(stable_patterns, key=lambda x: x['positive_years'], reverse=True)

    for item in stable_patterns[:15]:
        yearly_str = ', '.join([f"{y}:{r:.0f}%" for y, r in item['yearly_roi'].items()])
        print(f"  {item['conditions']}")
        print(f"    → {item['positive_years']}/{item['total_years']}年プラス, 総合ROI {item['total_roi']:.1f}% ({item['total_samples']}件)")
        print(f"    → 年度別: {yearly_str}")

    results['stable_patterns'] = stable_patterns

    # -----------------------------------------
    # 5. 短期効果パターン（直近2年で高ROI）
    # -----------------------------------------
    print("\n--- 短期効果パターン（2024-2025で高ROI） ---")

    recent_df = df[df['year'].isin(['2024', '2025'])].reset_index(drop=True)

    short_term_results = []

    for pattern in (two_cond_results + three_cond_results)[:100]:
        if 'cols' in pattern:
            cols, vals = pattern['cols'], pattern['vals']
        else:
            cols = [pattern['col1'], pattern['col2']]
            vals = [pattern['val1'], pattern['val2']]

        # 直近2年でフィルタ
        mask = pd.Series([True] * len(recent_df), index=recent_df.index)
        for c, v in zip(cols, vals):
            mask &= (recent_df[c] == v)
        subset = recent_df[mask]

        if len(subset) < min_samples // 2:  # 直近なのでサンプル数基準を緩和
            continue

        hits = subset['is_trifecta_hit'].sum()
        payout = subset['trifecta_payout'].sum()
        roi = payout / (len(subset) * 100) * 100

        if roi > 150:  # 150%以上
            short_term_results.append({
                'conditions': pattern['conditions'],
                'roi': round(roi, 1),
                'samples': len(subset),
                'hits': int(hits),
            })

    short_term_results = sorted(short_term_results, key=lambda x: x['roi'], reverse=True)

    for item in short_term_results[:15]:
        print(f"  {item['conditions']}: ROI {item['roi']:.1f}% ({item['samples']}件, {item['hits']}的中)")

    results['short_term_patterns'] = short_term_results

    return results


# =============================================================================
# Phase B: 機械学習重要度分析
# =============================================================================

def ml_feature_importance(df: pd.DataFrame) -> dict:
    """
    機械学習による特徴量重要度と交互作用分析

    Returns:
        分析結果の辞書
    """
    if not HAS_ML:
        print("sklearn/shapがインストールされていません")
        return {}

    print("\n" + "=" * 60)
    print("Phase B: 機械学習重要度分析")
    print("=" * 60)

    results = {
        'feature_importance': {},
        'shap_importance': {},
        'interactions': [],
    }

    # 特徴量の準備
    feature_cols = [c for c in FEATURE_COLUMNS if c in df.columns]
    X = df[feature_cols].copy()
    y = df['is_trifecta_hit'].values

    # カテゴリ変数をエンコード
    encoders = {}
    for col in feature_cols:
        if X[col].dtype == 'object':
            le = LabelEncoder()
            X[col] = X[col].fillna('unknown')
            X[col] = le.fit_transform(X[col].astype(str))
            encoders[col] = le
        else:
            X[col] = X[col].fillna(-1)

    X = X.values

    print(f"\n特徴量数: {len(feature_cols)}")
    print(f"サンプル数: {len(X):,}")

    # -----------------------------------------
    # 1. GradientBoosting で重要度分析
    # -----------------------------------------
    print("\n--- Gradient Boosting 特徴量重要度 ---")

    model = GradientBoostingClassifier(
        n_estimators=100,
        max_depth=5,
        min_samples_leaf=50,
        random_state=42,
        verbose=0
    )

    # サンプリング（計算時間短縮）
    if len(X) > 50000:
        sample_idx = np.random.choice(len(X), 50000, replace=False)
        X_sample, y_sample = X[sample_idx], y[sample_idx]
    else:
        X_sample, y_sample = X, y

    model.fit(X_sample, y_sample)

    # 交差検証スコア
    cv_scores = cross_val_score(model, X_sample, y_sample, cv=5, scoring='roc_auc')
    print(f"ROC-AUC (CV): {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")

    # 特徴量重要度
    importance = dict(zip(feature_cols, model.feature_importances_))
    importance = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True))

    print("\n特徴量重要度:")
    for feat, imp in importance.items():
        bar = "#" * int(imp * 50)
        print(f"  {feat:20s}: {imp:.4f} {bar}")

    results['feature_importance'] = importance

    # -----------------------------------------
    # 2. SHAP値による詳細分析
    # -----------------------------------------
    print("\n--- SHAP値分析 ---")

    try:
        # 計算時間短縮のためサンプリング
        shap_sample_size = min(5000, len(X_sample))
        shap_idx = np.random.choice(len(X_sample), shap_sample_size, replace=False)

        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X_sample[shap_idx])

        # SHAP重要度
        shap_importance = np.abs(shap_values).mean(axis=0)
        shap_imp_dict = dict(zip(feature_cols, shap_importance))
        shap_imp_dict = dict(sorted(shap_imp_dict.items(), key=lambda x: x[1], reverse=True))

        print("\nSHAP重要度:")
        for feat, imp in shap_imp_dict.items():
            bar = "#" * int(imp * 100)
            print(f"  {feat:20s}: {imp:.4f} {bar}")

        results['shap_importance'] = shap_imp_dict

        # -----------------------------------------
        # 3. 交互作用の検出
        # -----------------------------------------
        print("\n--- 交互作用検出 ---")

        # SHAP交互作用値（計算コストが高いので上位特徴量のみ）
        top_features = list(importance.keys())[:5]
        top_indices = [feature_cols.index(f) for f in top_features]

        interactions = []

        # 上位特徴量間の交互作用を計算
        for i, feat1 in enumerate(top_features):
            for feat2 in top_features[i+1:]:
                idx1 = feature_cols.index(feat1)
                idx2 = feature_cols.index(feat2)

                # 条件別のROI差で交互作用を推定
                df_temp = df.copy()
                df_temp[f'{feat1}_enc'] = encoders.get(feat1, lambda x: x).transform(df_temp[feat1].fillna('unknown').astype(str)) if feat1 in encoders else df_temp[feat1].fillna(-1)
                df_temp[f'{feat2}_enc'] = encoders.get(feat2, lambda x: x).transform(df_temp[feat2].fillna('unknown').astype(str)) if feat2 in encoders else df_temp[feat2].fillna(-1)

                # 中央値で分割
                med1 = df_temp[f'{feat1}_enc'].median()
                med2 = df_temp[f'{feat2}_enc'].median()

                groups = {
                    'low_low': df_temp[(df_temp[f'{feat1}_enc'] <= med1) & (df_temp[f'{feat2}_enc'] <= med2)],
                    'low_high': df_temp[(df_temp[f'{feat1}_enc'] <= med1) & (df_temp[f'{feat2}_enc'] > med2)],
                    'high_low': df_temp[(df_temp[f'{feat1}_enc'] > med1) & (df_temp[f'{feat2}_enc'] <= med2)],
                    'high_high': df_temp[(df_temp[f'{feat1}_enc'] > med1) & (df_temp[f'{feat2}_enc'] > med2)],
                }

                rois = {}
                for name, grp in groups.items():
                    if len(grp) > 100:
                        payout = grp['trifecta_payout'].sum()
                        roi = payout / (len(grp) * 100) * 100
                        rois[name] = roi

                if len(rois) == 4:
                    # 交互作用の強さ = (high_high + low_low) - (high_low + low_high)
                    interaction_effect = (rois['high_high'] + rois['low_low']) - (rois['high_low'] + rois['low_high'])

                    interactions.append({
                        'features': f"{feat1} × {feat2}",
                        'interaction_effect': round(interaction_effect, 1),
                        'rois': rois,
                    })

        interactions = sorted(interactions, key=lambda x: abs(x['interaction_effect']), reverse=True)

        print("\n交互作用効果（ROI差）:")
        for item in interactions[:10]:
            effect = item['interaction_effect']
            direction = "正" if effect > 0 else "負"
            print(f"  {item['features']}: {effect:+.1f}pt ({direction}の交互作用)")
            rois = item['rois']
            print(f"    low×low: {rois.get('low_low', 0):.1f}%, high×high: {rois.get('high_high', 0):.1f}%")
            print(f"    low×high: {rois.get('low_high', 0):.1f}%, high×low: {rois.get('high_low', 0):.1f}%")

        results['interactions'] = interactions

    except Exception as e:
        print(f"SHAP分析エラー: {e}")

    return results


# =============================================================================
# メイン処理
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='複合条件パターン発見')
    parser.add_argument('--phase', choices=['A', 'B', 'all'], default='all',
                        help='実行フェーズ (A=逆引き, B=ML, all=両方)')
    parser.add_argument('--prediction-type', choices=['before', 'advance'], default='before',
                        help='予測タイプ')
    parser.add_argument('--years', default=None,
                        help='年度範囲 (例: 2022-2025)')
    parser.add_argument('--min-samples', type=int, default=100,
                        help='最小サンプル数')
    parser.add_argument('--output', default=None,
                        help='結果出力先 (JSON)')
    args = parser.parse_args()

    # 年度パース
    years = None
    if args.years:
        parts = args.years.split('-')
        years = (int(parts[0]), int(parts[1]))

    db_path = Path(__file__).parent.parent.parent / "data" / "boatrace.db"

    # データ読み込み
    df = load_data(str(db_path), args.prediction_type, years)

    results = {
        'generated_at': datetime.now().isoformat(),
        'prediction_type': args.prediction_type,
        'years': args.years,
        'total_records': len(df),
    }

    # Phase A: 逆引き分析
    if args.phase in ['A', 'all']:
        phase_a_results = analyze_hit_patterns(df, min_samples=args.min_samples)
        results['phase_a'] = phase_a_results

    # Phase B: 機械学習
    if args.phase in ['B', 'all']:
        phase_b_results = ml_feature_importance(df)
        results['phase_b'] = phase_b_results

    # 結果保存
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = Path(__file__).parent.parent.parent / "data" / "pattern_discovery_results.json"

    # NaN対応
    def convert_nan(obj):
        if isinstance(obj, float) and np.isnan(obj):
            return None
        elif isinstance(obj, dict):
            return {k: convert_nan(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_nan(v) for v in obj]
        return obj

    results = convert_nan(results)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n結果を保存: {output_path}")

    # サマリー
    print("\n" + "=" * 60)
    print("発見サマリー")
    print("=" * 60)

    if 'phase_a' in results:
        pa = results['phase_a']
        print(f"\n[Phase A] 逆引き分析")
        print(f"  高ROIパターン: {len(pa.get('high_roi_patterns', []))}件")
        print(f"  安定パターン（4年+プラス）: {len(pa.get('stable_patterns', []))}件")
        print(f"  短期効果パターン: {len(pa.get('short_term_patterns', []))}件")

    if 'phase_b' in results:
        pb = results['phase_b']
        print(f"\n[Phase B] 機械学習分析")
        if pb.get('feature_importance'):
            top3 = list(pb['feature_importance'].items())[:3]
            print(f"  重要特徴量Top3: {', '.join([f[0] for f in top3])}")
        if pb.get('interactions'):
            print(f"  検出した交互作用: {len(pb['interactions'])}件")


if __name__ == "__main__":
    main()
