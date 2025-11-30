"""
全モデル統合学習スクリプト
Phase 1-7の全モデルを順次学習

使用方法:
    python scripts/train_all_models.py --db data/boatrace.db --start-date 2024-01-01
"""
import os
import sys
import argparse
from datetime import datetime

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


def train_phase1_entry_model(db_path: str, start_date: str, end_date: str, model_dir: str):
    """Phase 1: 進入予測モデル"""
    print("\n" + "=" * 60)
    print("Phase 1: 進入予測モデル学習")
    print("=" * 60)

    try:
        from src.entry_model.entry_trainer import EntryModelTrainer

        trainer = EntryModelTrainer(db_path, model_dir)
        df = trainer.load_training_data(start_date, end_date)

        if len(df) > 0:
            trainer.train(df)
            trainer.save('entry_model')
            print("Phase 1 完了: 進入予測モデル")
        else:
            print("Phase 1 スキップ: データ不足")

    except Exception as e:
        print(f"Phase 1 エラー: {e}")


def train_phase2_conditional_models(db_path: str, start_date: str, end_date: str, model_dir: str):
    """Phase 2: 条件付き着順モデル（Stage1/2/3）"""
    print("\n" + "=" * 60)
    print("Phase 2: 条件付き着順モデル学習")
    print("=" * 60)

    try:
        from src.ml.train_conditional_models import ConditionalModelTrainer

        trainer = ConditionalModelTrainer(db_path, model_dir)
        df = trainer.load_training_data(start_date, end_date)

        if len(df) > 0:
            trainer.train_all(df, 'xgboost')
            trainer.save('conditional')
            print("Phase 2 完了: 条件付き着順モデル")
        else:
            print("Phase 2 スキップ: データ不足")

    except Exception as e:
        print(f"Phase 2 エラー: {e}")


def train_phase3_style_clustering(db_path: str, target_date: str, model_dir: str):
    """Phase 3: 走法クラスタリング"""
    print("\n" + "=" * 60)
    print("Phase 3: 走法クラスタリング")
    print("=" * 60)

    try:
        from src.style_cluster.style_clustering import train_style_clustering

        clusterer, result_df = train_style_clustering(
            db_path, model_dir, n_clusters=8, target_date=target_date
        )

        if clusterer is not None:
            print(f"Phase 3 完了: {len(result_df)}選手を8クラスタに分類")
        else:
            print("Phase 3 スキップ: データ不足")

    except Exception as e:
        print(f"Phase 3 エラー: {e}")


def train_phase4_st_sequence(db_path: str, start_date: str, end_date: str, model_dir: str):
    """Phase 4: ST時系列モデル"""
    print("\n" + "=" * 60)
    print("Phase 4: ST時系列モデル学習")
    print("=" * 60)

    try:
        from src.st_sequence.st_trainer import STModelTrainer

        trainer = STModelTrainer(db_path, model_dir)
        X, y = trainer.load_training_data(start_date, end_date)

        if len(X) > 0:
            trainer.train(X, y, epochs=30)
            trainer.save('st_sequence')
            print("Phase 4 完了: ST時系列モデル")
        else:
            print("Phase 4 スキップ: データ不足")

    except Exception as e:
        print(f"Phase 4 エラー: {e}")


def train_phase5_type_models(db_path: str, start_date: str, end_date: str, model_dir: str):
    """Phase 5: レースタイプ別モデル"""
    print("\n" + "=" * 60)
    print("Phase 5: レースタイプ別モデル学習")
    print("=" * 60)

    try:
        from src.race_type_model.type_specific_models import TypeSpecificModelManager
        from src.features.feature_transforms import create_training_dataset_with_relative_features
        import sqlite3

        # 学習データ読み込み
        conn = sqlite3.connect(db_path)
        df = create_training_dataset_with_relative_features(conn, start_date, end_date)
        conn.close()

        if len(df) > 0:
            manager = TypeSpecificModelManager(model_dir)
            metrics = manager.train_all_types(df)
            manager.save('type_models')
            print(f"Phase 5 完了: {len(metrics)}タイプのモデル学習")
        else:
            print("Phase 5 スキップ: データ不足")

    except Exception as e:
        print(f"Phase 5 エラー: {e}")


def run_phase7_backtest(db_path: str, start_date: str, end_date: str, model_dir: str):
    """Phase 7: バックテスト"""
    print("\n" + "=" * 60)
    print("Phase 7: バックテスト評価")
    print("=" * 60)

    try:
        from scripts.backtest_enhanced_model import EnhancedBacktester

        backtester = EnhancedBacktester(db_path, model_dir)
        df = backtester.load_test_races(start_date, end_date)

        if len(df) > 0:
            results = backtester.run_backtest(df)
            comparison = backtester.compare_with_baseline(df)
            backtester.save_results()
            print("Phase 7 完了: バックテスト評価")
        else:
            print("Phase 7 スキップ: テストデータ不足")

    except Exception as e:
        print(f"Phase 7 エラー: {e}")


def main():
    """メイン実行"""
    parser = argparse.ArgumentParser(description='全モデル統合学習')
    parser.add_argument('--db', default='data/boatrace.db', help='DBパス')
    parser.add_argument('--start-date', default='2024-01-01', help='学習開始日')
    parser.add_argument('--end-date', default=None, help='学習終了日')
    parser.add_argument('--test-start', default='2024-10-01', help='テスト開始日')
    parser.add_argument('--test-end', default='2024-11-30', help='テスト終了日')
    parser.add_argument('--model-dir', default='models', help='モデル保存先')
    parser.add_argument('--phases', default='1,2,3,4,5,7', help='実行するフェーズ（カンマ区切り）')

    args = parser.parse_args()

    phases = [int(p) for p in args.phases.split(',')]

    print("\n" + "=" * 60)
    print("高精度モデル統合学習システム")
    print("=" * 60)
    print(f"DB: {args.db}")
    print(f"学習期間: {args.start_date} ~ {args.end_date or '現在'}")
    print(f"テスト期間: {args.test_start} ~ {args.test_end}")
    print(f"実行フェーズ: {phases}")
    print(f"モデル保存先: {args.model_dir}")

    # モデルディレクトリ作成
    os.makedirs(args.model_dir, exist_ok=True)

    start_time = datetime.now()

    # Phase 1: 進入予測モデル
    if 1 in phases:
        train_phase1_entry_model(args.db, args.start_date, args.end_date, args.model_dir)

    # Phase 2: 条件付き着順モデル
    if 2 in phases:
        train_phase2_conditional_models(args.db, args.start_date, args.end_date, args.model_dir)

    # Phase 3: 走法クラスタリング
    if 3 in phases:
        train_phase3_style_clustering(args.db, args.end_date or args.test_start, args.model_dir)

    # Phase 4: ST時系列モデル
    if 4 in phases:
        train_phase4_st_sequence(args.db, args.start_date, args.end_date, args.model_dir)

    # Phase 5: レースタイプ別モデル
    if 5 in phases:
        train_phase5_type_models(args.db, args.start_date, args.end_date, args.model_dir)

    # Phase 7: バックテスト
    if 7 in phases:
        run_phase7_backtest(args.db, args.test_start, args.test_end, args.model_dir)

    elapsed = datetime.now() - start_time

    print("\n" + "=" * 60)
    print("全フェーズ完了")
    print("=" * 60)
    print(f"実行時間: {elapsed}")


if __name__ == '__main__':
    main()
