"""
ML パイプライン統合実行スクリプト

機能:
1. ルール抽出
2. バックテスト
3. モデル最適化
4. 予測説明生成
"""

import sys
import argparse
from pathlib import Path

# パス設定
sys.path.insert(0, str(Path(__file__).parent))

from src.ml import (
    RuleExtractor,
    BacktestEngine,
    PredictionExplainer,
    OptimizationLoop,
    run_full_optimization
)


def extract_rules(db_path: str = "boatrace.db"):
    """ルール抽出"""
    print("=" * 60)
    print("ルール抽出")
    print("=" * 60)

    extractor = RuleExtractor(db_path)
    rules = extractor.extract_all_rules(min_confidence=0.3)

    # レポート表示
    print(extractor.generate_report(rules))

    # DBに保存
    extractor.save_rules_to_db(rules)

    return rules


def run_backtest(db_path: str = "boatrace.db"):
    """バックテスト"""
    print("\n" + "=" * 60)
    print("バックテスト")
    print("=" * 60)

    engine = BacktestEngine(db_path)

    # 日付分割を確認
    min_date, split_date, max_date = engine.get_time_split_dates()
    print(f"データ期間: {min_date} - {max_date}")
    print(f"分割日: {split_date}")

    # データ読み込み
    train_df, test_df = engine.load_backtest_data(split_date)

    print(f"\n訓練データ: {len(train_df):,}行")
    print(f"テストデータ: {len(test_df):,}行")

    if 'race_id' in train_df.columns:
        print(f"訓練レース数: {train_df['race_id'].nunique():,}")
        print(f"テストレース数: {test_df['race_id'].nunique():,}")

    return train_df, test_df


def optimize_models(db_path: str = "boatrace.db", quick: bool = False):
    """モデル最適化"""
    print("\n" + "=" * 60)
    print("モデル最適化")
    print("=" * 60)

    optimizer = OptimizationLoop(db_path)

    models = ['xgboost', 'lightgbm']

    for model_type in models:
        try:
            result = optimizer.run_optimization_cycle(
                model_type=model_type,
                optimize_params=not quick
            )
        except ImportError as e:
            print(f"{model_type}をスキップ: {e}")
        except Exception as e:
            print(f"{model_type}でエラー: {e}")

    # 比較レポート
    print("\n")
    print(optimizer.compare_models())

    # 結果保存
    optimizer.save_results("optimization_results.json")

    return optimizer.results_history


def demo_explanation(db_path: str = "boatrace.db"):
    """予測説明デモ"""
    print("\n" + "=" * 60)
    print("予測説明デモ")
    print("=" * 60)

    explainer = PredictionExplainer(db_path)

    # サンプルデータ
    test_cases = [
        {
            'venue_code': '01',
            'pit_number': 1,
            'racer_name': '山田太郎',
            'racer_rank': 'A1',
            'nation_win_rate': 7.5,
            'motor_2ren_rate': 45.0,
            'wind_direction': '追',
            'tide_status': '満潮'
        },
        {
            'venue_code': '12',
            'pit_number': 4,
            'racer_name': '鈴木次郎',
            'racer_rank': 'B1',
            'nation_win_rate': 5.2,
            'motor_2ren_rate': 32.0,
            'wind_direction': '向',
            'tide_status': '干潮'
        }
    ]

    for i, test_data in enumerate(test_cases, 1):
        print(f"\n--- ケース {i} ---")

        # モデル予測確率（仮）
        model_prob = 0.35 if test_data['pit_number'] == 1 else 0.12

        # 説明生成
        explanation = explainer.explain_prediction(test_data, model_prob)

        # UI表示
        print(explainer.format_for_ui(explanation))


def main():
    parser = argparse.ArgumentParser(description="ML パイプライン実行")
    parser.add_argument('--db', default='boatrace.db', help='データベースパス')
    parser.add_argument('--rules', action='store_true', help='ルール抽出を実行')
    parser.add_argument('--backtest', action='store_true', help='バックテストを実行')
    parser.add_argument('--optimize', action='store_true', help='モデル最適化を実行')
    parser.add_argument('--demo', action='store_true', help='予測説明デモ')
    parser.add_argument('--all', action='store_true', help='全て実行')
    parser.add_argument('--quick', action='store_true', help='高速モード（最適化スキップ）')

    args = parser.parse_args()

    # 引数がない場合は全て実行
    run_all = args.all or not any([args.rules, args.backtest, args.optimize, args.demo])

    if run_all or args.rules:
        extract_rules(args.db)

    if run_all or args.backtest:
        run_backtest(args.db)

    if run_all or args.optimize:
        optimize_models(args.db, args.quick)

    if run_all or args.demo:
        demo_explanation(args.db)

    print("\n完了しました")


if __name__ == "__main__":
    main()
