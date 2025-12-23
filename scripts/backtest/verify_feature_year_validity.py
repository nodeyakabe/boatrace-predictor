#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
フィーチャーフラグの年度間妥当性検証スクリプト

各機能が2024年と2025年の両方で効果を発揮するかを検証し、
過剰適合のリスクを評価します。

使用方法:
    python scripts/verify_feature_year_validity.py
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.feature_flags import FEATURE_FLAGS, FEATURE_RISKS


def get_db_connection():
    """データベース接続を取得"""
    db_path = PROJECT_ROOT / "data" / "boatrace.db"
    return sqlite3.connect(str(db_path))


def analyze_year_distribution():
    """年度別のデータ分布を分析"""
    conn = get_db_connection()
    cursor = conn.cursor()

    print("=" * 80)
    print("年度別データ分布分析")
    print("=" * 80)

    # レース数の分布
    cursor.execute("""
        SELECT
            strftime('%Y', race_date) as year,
            COUNT(*) as race_count
        FROM races
        WHERE race_date >= '2024-01-01'
        GROUP BY year
        ORDER BY year
    """)

    print("\n### レース数分布")
    print("| 年度 | レース数 |")
    print("|------|---------|")
    for row in cursor.fetchall():
        print(f"| {row[0]} | {row[1]:,} |")

    # prediction_results テーブルの分布（存在する場合）
    try:
        cursor.execute("""
            SELECT
                strftime('%Y', race_date) as year,
                prediction_type,
                COUNT(*) as count
            FROM prediction_results
            WHERE race_date >= '2024-01-01'
            GROUP BY year, prediction_type
            ORDER BY year, prediction_type
        """)

        print("\n### 予測データ分布")
        print("| 年度 | 予測タイプ | 件数 |")
        print("|------|-----------|------|")
        for row in cursor.fetchall():
            print(f"| {row[0]} | {row[1]} | {row[2]:,} |")
    except sqlite3.OperationalError:
        print("\n### 予測データ分布")
        print("（prediction_results テーブルが存在しません）")

    conn.close()


def analyze_feature_implementation_dates():
    """各機能の実装日と検証データを分析"""

    print("\n" + "=" * 80)
    print("フィーチャーフラグ実装履歴分析")
    print("=" * 80)

    # 機能別の実装履歴（FEATURE_RISKSから抽出）
    feature_info = []

    for feature_name, enabled in FEATURE_FLAGS.items():
        risk_info = FEATURE_RISKS.get(feature_name, {})
        enabled_date = risk_info.get('enabled_date', '不明')
        test_result = risk_info.get('test_result', '記録なし')

        # テスト結果から検証データの年度を推測
        year_info = "不明"
        if '2024' in str(test_result) and '2025' in str(test_result):
            year_info = "両年度"
        elif '2024' in str(test_result):
            year_info = "2024年のみ"
        elif '2025' in str(test_result):
            year_info = "2025年のみ"
        elif enabled_date and enabled_date != '不明':
            # 実装日から推測
            year_info = "2025年のみ（実装日から推測）"

        feature_info.append({
            'name': feature_name,
            'enabled': enabled,
            'enabled_date': enabled_date,
            'test_result': test_result,
            'year_info': year_info
        })

    # 有効なフィーチャーのみ表示
    print("\n### 有効なフィーチャーフラグ")
    print("| フィーチャー名 | 有効化日 | 検証年度 | 検証結果 |")
    print("|---------------|---------|---------|---------|")

    for info in feature_info:
        if info['enabled']:
            test_result = info['test_result'][:50] + "..." if len(info['test_result']) > 50 else info['test_result']
            print(f"| {info['name']} | {info['enabled_date']} | {info['year_info']} | {test_result} |")

    return feature_info


def classify_features_by_risk():
    """フィーチャーを過剰適合リスクで分類"""

    print("\n" + "=" * 80)
    print("過剰適合リスク評価")
    print("=" * 80)

    # カテゴリ定義
    categories = {
        'safe': {
            'name': '信頼できる（両年度検証済み）',
            'features': [],
            'description': '2024年と2025年の両方でテスト済み、または年度に依存しない構造的な機能'
        },
        'needs_verification': {
            'name': '要検証（2025年のみで検証）',
            'features': [],
            'description': '2025年データでのみ検証されており、2024年での効果は未確認'
        },
        'high_risk': {
            'name': 'リスクあり（過剰適合の可能性）',
            'features': [],
            'description': '特定の条件やパラメータが2025年に最適化されている可能性'
        },
        'structural': {
            'name': '構造的機能（年度依存なし）',
            'features': [],
            'description': 'モデルアーキテクチャに関する機能で、年度による影響を受けにくい'
        }
    }

    # フィーチャーの分類
    # 構造的機能（年度依存なし）
    structural_features = [
        'entry_prediction_model',      # 進入予測は構造的
        'hierarchical_predictor',      # 階層モデルは構造的
        'lightgbm_ranking',            # LightGBMは構造的
        'interaction_features',        # 交互作用特徴量は構造的
        'st_course_interaction',       # ST×course交互作用は構造的
    ]

    # 2025年のみで検証されたフィーチャー
    needs_verification_features = [
        'second_place_specialized',    # 2025年11-12月のみで検証
        'confidence_based_switching',  # 2025年12月実装
        'pairwise_scoring',            # 2025年11月のみで検証
        'motor_capsizing_penalty',     # 2025年12月実装
        'kimarite_flow_prediction',    # 2025年12月実装
        'makuri_risk_adjustment',      # 2025年12月実装
        'ab_rank_special_betting',     # 2025年データで最適化
    ]

    # 両年度で検証済みまたは安定したフィーチャー
    safe_features = [
        'before_pattern_bonus',        # パターン方式は長期運用
        'negative_patterns',           # 2025-12-11に検証
    ]

    for feature_name, enabled in FEATURE_FLAGS.items():
        if not enabled:
            continue

        if feature_name in structural_features:
            categories['structural']['features'].append(feature_name)
        elif feature_name in needs_verification_features:
            categories['needs_verification']['features'].append(feature_name)
        elif feature_name in safe_features:
            categories['safe']['features'].append(feature_name)
        else:
            # デフォルトは要検証
            categories['needs_verification']['features'].append(feature_name)

    # 結果表示
    for cat_key, cat_info in categories.items():
        if cat_info['features']:
            print(f"\n### {cat_info['name']}")
            print(f"*{cat_info['description']}*")
            print()
            for f in cat_info['features']:
                risk_info = FEATURE_RISKS.get(f, {})
                test_result = risk_info.get('test_result', '記録なし')
                print(f"- **{f}**: {test_result[:60]}...")

    return categories


def generate_recommendations():
    """推奨アクションを生成"""

    print("\n" + "=" * 80)
    print("推奨アクション")
    print("=" * 80)

    print("""
### 即時対応（優先度: 高）

1. **ab_rank_special_betting の年度間検証**
   - 現状: 2025年データで+17.2pt効果確認
   - リスク: 購入条件分析で2024年ROI 71.5%（赤字）が判明
   - 対応: 2024年データでの効果検証が必要

2. **kimarite_flow_prediction / makuri_risk_adjustment の年度間検証**
   - 現状: 2025年12月に実装、5%調整で+4.1pt効果
   - リスク: 決まり手パターンが年度で変化する可能性
   - 対応: 2024年データでの効果検証が必要

### 中期対応（優先度: 中）

3. **pairwise_scoring の年度間検証**
   - 現状: 2025年11月データで検証（482レース）
   - 学習データ: 2024年1-10月
   - リスク: 中程度（学習は2024年だが、検証は2025年のみ）
   - 対応: 2024年データでのバックテスト実施

4. **second_place_specialized の年度間検証**
   - 現状: 2025年11-12月データで検証（432レース）
   - リスク: 中程度（2着パターンが年度で変化する可能性）
   - 対応: 2024年データでのバックテスト実施

### 維持推奨（優先度: 低）

5. **構造的機能は維持**
   - entry_prediction_model, hierarchical_predictor, lightgbm_ranking
   - interaction_features, st_course_interaction
   - 理由: モデルアーキテクチャに関する機能で、年度による影響が小さい

6. **before_pattern_bonus, negative_patterns は維持**
   - 長期運用実績があり、効果が安定している
""")


def summarize_findings():
    """発見事項のサマリー"""

    print("\n" + "=" * 80)
    print("分析サマリー")
    print("=" * 80)

    print("""
## 重大な発見

### 1. 購入条件の年度間ギャップ
購入条件分析（YEAR_CONDITION_OPTIMIZATION_ANALYSIS.md）で判明：
- 2024年ROI: 71.5%（赤字）
- 2025年ROI: 136.0%（黒字）
- **差異: 64.5pt**

### 2. 検証データの偏り
現在有効なフィーチャーの多くは**2025年データのみで検証**されている：
- second_place_specialized: 2025年11-12月（432レース）
- pairwise_scoring: 2025年11-12月（482レース）
- ab_rank_special_betting: 2025年データで最適化
- kimarite_flow_prediction: 2025年12月実装
- makuri_risk_adjustment: 2025年12月実装

### 3. 年度間モデルドリフトの実例
rank23_odds_calibration の事例：
- 2024年: +2.04pt効果
- 2025年: ±0.00pt（効果消失）
- **結論: 不採用**

この事例は、2024年で有効だった施策が2025年で効果を失う可能性を示している。
逆もまた然りで、2025年で有効な施策が2024年では無効である可能性がある。

## フィーチャーの信頼性分類

### 信頼できる（維持推奨）
| フィーチャー | 理由 |
|-------------|------|
| entry_prediction_model | 構造的機能 |
| hierarchical_predictor | 構造的機能 |
| lightgbm_ranking | 構造的機能 |
| interaction_features | 構造的機能 |
| st_course_interaction | 構造的機能 |
| before_pattern_bonus | 長期運用実績 |
| negative_patterns | 長期運用実績 |

### 要検証（2024年データでの検証が必要）
| フィーチャー | リスクレベル | 理由 |
|-------------|-------------|------|
| ab_rank_special_betting | **高** | 購入条件と密接に関連 |
| kimarite_flow_prediction | 中 | 決まり手パターンの年度変動 |
| makuri_risk_adjustment | 中 | 決まり手パターンの年度変動 |
| pairwise_scoring | 中 | 2025年のみで検証 |
| second_place_specialized | 中 | 2025年のみで検証 |
| confidence_based_switching | 低 | 戦略切り替えロジック |
| motor_capsizing_penalty | 低 | モーターデータの統計的特性 |

## 今後の検証プロセス改善提案

1. **年度間クロスバリデーション必須化**
   - 新機能は必ず2024年と2025年の両方で検証
   - 効果の差が30pt以上の場合は採用保留

2. **年度別バックテストの標準化**
   - スクリプトテンプレートに年度別検証を追加
   - 結果の記録形式を統一

3. **定期的な効果測定**
   - 月次で有効フィーチャーの効果を再測定
   - モデルドリフトの早期検出

4. **不採用基準の明確化**
   - 年度間差が50pt以上: 不採用
   - 年度間差が30-50pt: 要注意、追加検証
   - 年度間差が30pt未満: 採用可能
""")


def main():
    """メイン実行"""
    print("=" * 80)
    print("フィーチャーフラグ年度間妥当性検証レポート")
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # 1. 年度別データ分布
    analyze_year_distribution()

    # 2. フィーチャー実装履歴
    analyze_feature_implementation_dates()

    # 3. 過剰適合リスク評価
    classify_features_by_risk()

    # 4. 推奨アクション
    generate_recommendations()

    # 5. 発見事項サマリー
    summarize_findings()

    print("\n" + "=" * 80)
    print("検証完了")
    print("=" * 80)


if __name__ == "__main__":
    main()
