"""
バックテストエンジン

機能:
- 時系列データ分割（80:20）
- 過去データでの検証
- 詳細な精度レポート生成
- ルール検証機能
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timedelta
from pathlib import Path
import json
import sqlite3

from .evaluation_metrics import ComprehensiveEvaluator, evaluate_model


class BacktestEngine:
    """バックテストエンジン"""

    def __init__(self, db_path: str = "boatrace.db"):
        """
        初期化

        Args:
            db_path: データベースパス
        """
        self.db_path = db_path
        self.evaluator = ComprehensiveEvaluator()

    def get_time_split_dates(
        self,
        train_ratio: float = 0.8
    ) -> Tuple[str, str, str]:
        """
        時系列分割の日付を取得

        Args:
            train_ratio: 訓練データの割合

        Returns:
            (min_date, split_date, max_date)
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 日付範囲を取得
            cursor.execute("""
                SELECT MIN(race_date), MAX(race_date), COUNT(DISTINCT race_date)
                FROM races
            """)
            min_date, max_date, total_days = cursor.fetchone()

            if not min_date or not max_date:
                raise ValueError("データベースにレースデータがありません")

            # 分割日を計算
            min_dt = datetime.strptime(min_date, "%Y-%m-%d")
            max_dt = datetime.strptime(max_date, "%Y-%m-%d")

            split_days = int((max_dt - min_dt).days * train_ratio)
            split_dt = min_dt + timedelta(days=split_days)
            split_date = split_dt.strftime("%Y-%m-%d")

            return min_date, split_date, max_date

    def load_backtest_data(
        self,
        split_date: str,
        include_weather: bool = True,
        include_tide: bool = True,
        include_exhibition: bool = True
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        バックテスト用データを読み込み

        Args:
            split_date: 分割日
            include_weather: 天候データを含む
            include_tide: 潮汐データを含む
            include_exhibition: 展示データを含む

        Returns:
            (train_df, test_df)
        """
        with sqlite3.connect(self.db_path) as conn:
            # 基本クエリ（実際のDBスキーマに合わせて修正）
            query = """
                SELECT
                    r.id AS race_id,
                    r.race_date,
                    r.venue_code,
                    r.race_number,
                    e.pit_number,
                    e.racer_number,
                    e.racer_name,
                    e.racer_rank,
                    e.motor_number,
                    e.boat_number,
                    e.win_rate AS nation_win_rate,
                    e.second_rate AS nation_2ren_rate,
                    e.local_win_rate,
                    e.local_second_rate AS local_2ren_rate,
                    e.motor_second_rate AS motor_2ren_rate,
                    e.boat_second_rate AS boat_2ren_rate,
                    CAST(res.rank AS INTEGER) AS result_place
                FROM races r
                JOIN entries e ON r.id = e.race_id
                LEFT JOIN results res ON r.id = res.race_id
                    AND e.pit_number = res.pit_number
                WHERE res.rank IS NOT NULL
                    AND res.rank != ''
                    AND res.is_invalid = 0
            """

            df = pd.read_sql_query(query, conn)

            # 天候データを結合
            if include_weather:
                weather_query = """
                    SELECT venue_code, weather_date AS race_date,
                           temperature, weather_condition AS weather,
                           wind_direction, wind_speed,
                           water_temperature AS water_temp, wave_height
                    FROM weather
                """
                weather_df = pd.read_sql_query(weather_query, conn)
                if not weather_df.empty:
                    df = df.merge(
                        weather_df,
                        on=['venue_code', 'race_date'],
                        how='left'
                    )

            # 潮汐データを結合
            if include_tide:
                tide_query = """
                    SELECT venue_code, tide_date AS race_date,
                           tide_type AS tide_status, tide_level
                    FROM tide
                """
                tide_df = pd.read_sql_query(tide_query, conn)
                if not tide_df.empty:
                    df = df.merge(
                        tide_df,
                        on=['venue_code', 'race_date'],
                        how='left'
                    )

            # 展示データを結合（race_detailsから取得）
            if include_exhibition:
                try:
                    exhibition_query = """
                        SELECT race_id, pit_number,
                               exhibition_time, st_time AS start_timing
                        FROM race_details
                        WHERE exhibition_time IS NOT NULL
                    """
                    exhibition_df = pd.read_sql_query(exhibition_query, conn)
                    if not exhibition_df.empty:
                        df = df.merge(
                            exhibition_df,
                            on=['race_id', 'pit_number'],
                            how='left'
                        )
                except Exception:
                    pass  # テーブルが存在しない場合はスキップ

        # 時系列分割
        train_df = df[df['race_date'] < split_date].copy()
        test_df = df[df['race_date'] >= split_date].copy()

        return train_df, test_df

    def run_backtest(
        self,
        model,
        feature_columns: List[str],
        target_column: str = 'is_winner',
        train_ratio: float = 0.8
    ) -> Dict[str, Any]:
        """
        バックテストを実行

        Args:
            model: 学習済みモデル（predict_proba対応）
            feature_columns: 特徴量カラム
            target_column: 目的変数カラム
            train_ratio: 訓練データ割合

        Returns:
            バックテスト結果
        """
        # 日付分割を取得
        min_date, split_date, max_date = self.get_time_split_dates(train_ratio)

        # データ読み込み
        train_df, test_df = self.load_backtest_data(split_date)

        # 勝者フラグ作成
        train_df['is_winner'] = (train_df['result_place'] == 1).astype(int)
        test_df['is_winner'] = (test_df['result_place'] == 1).astype(int)

        # 特徴量が存在するかチェック
        available_features = [f for f in feature_columns if f in test_df.columns]

        if not available_features:
            return {
                'error': '使用可能な特徴量がありません',
                'requested_features': feature_columns,
                'available_columns': list(test_df.columns)
            }

        # NaN処理
        test_df_clean = test_df[available_features + [target_column]].dropna()

        if len(test_df_clean) == 0:
            return {'error': 'テストデータが空です'}

        # 予測
        X_test = test_df_clean[available_features]
        y_test = test_df_clean[target_column]

        try:
            y_pred_prob = model.predict_proba(X_test)[:, 1]
        except Exception as e:
            return {'error': f'予測エラー: {str(e)}'}

        # 評価
        metrics = self.evaluator.evaluate_binary_classification(y_test.values, y_pred_prob)

        # レース単位の評価
        test_df_clean = test_df_clean.copy()
        test_df_clean['pred_prob'] = y_pred_prob

        race_results = []
        for race_id in test_df_clean['race_id'].unique() if 'race_id' in test_df_clean.columns else []:
            race_data = test_df_clean[test_df_clean['race_id'] == race_id]
            if len(race_data) == 6:  # 6艇揃っている場合
                race_results.append({
                    'true_rank': race_data['result_place'].tolist(),
                    'pred_probs': race_data['pred_prob'].tolist(),
                    'pred_scores': race_data['pred_prob'].tolist()
                })

        if race_results:
            race_metrics = self.evaluator.evaluate_race_predictions(race_results)
            metrics.update(race_metrics)

        return {
            'split_info': {
                'min_date': min_date,
                'split_date': split_date,
                'max_date': max_date,
                'train_races': len(train_df['race_id'].unique()) if 'race_id' in train_df.columns else 0,
                'test_races': len(test_df['race_id'].unique()) if 'race_id' in test_df.columns else 0
            },
            'metrics': metrics,
            'feature_importance': self._get_feature_importance(model, available_features)
        }

    def _get_feature_importance(
        self,
        model,
        feature_names: List[str]
    ) -> Dict[str, float]:
        """特徴量重要度を取得"""
        try:
            if hasattr(model, 'feature_importances_'):
                importance = model.feature_importances_
                return dict(zip(feature_names, importance.tolist()))
        except Exception:
            pass
        return {}

    def generate_report(self, results: Dict[str, Any]) -> str:
        """
        バックテスト結果のレポートを生成

        Args:
            results: バックテスト結果

        Returns:
            フォーマットされたレポート
        """
        lines = [
            "=" * 60,
            "バックテストレポート",
            "=" * 60,
            f"生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            ""
        ]

        if 'error' in results:
            lines.append(f"エラー: {results['error']}")
            return "\n".join(lines)

        # 分割情報
        if 'split_info' in results:
            info = results['split_info']
            lines.extend([
                "【データ分割】",
                f"  訓練期間: {info.get('min_date', 'N/A')} - {info.get('split_date', 'N/A')}",
                f"  テスト期間: {info.get('split_date', 'N/A')} - {info.get('max_date', 'N/A')}",
                f"  訓練レース数: {info.get('train_races', 0):,}",
                f"  テストレース数: {info.get('test_races', 0):,}",
                ""
            ])

        # 評価指標
        if 'metrics' in results:
            metrics = results['metrics']

            lines.extend([
                "【予測精度】",
                f"  AUC:         {metrics.get('auc', 0):.4f}",
                f"  Brier Score: {metrics.get('brier_score', 0):.4f}",
                f"  Log Loss:    {metrics.get('log_loss', 0):.4f}",
                ""
            ])

            if 'ece' in metrics:
                lines.extend([
                    "【確率校正】",
                    f"  ECE: {metrics.get('ece', 0):.4f}",
                    f"  MCE: {metrics.get('mce', 0):.4f}",
                    ""
                ])

            if 'top_1_accuracy' in metrics:
                lines.extend([
                    "【Top-N正解率】",
                    f"  Top-1: {metrics.get('top_1_accuracy', 0):.2%}",
                    f"  Top-2: {metrics.get('top_2_accuracy', 0):.2%}",
                    f"  Top-3: {metrics.get('top_3_accuracy', 0):.2%}",
                    ""
                ])

            if 'spearman_correlation' in metrics:
                lines.extend([
                    "【順位相関】",
                    f"  Spearman: {metrics.get('spearman_correlation', 0):.4f}",
                    f"  Kendall:  {metrics.get('kendall_correlation', 0):.4f}",
                    ""
                ])

        # 特徴量重要度（上位10）
        if 'feature_importance' in results and results['feature_importance']:
            importance = results['feature_importance']
            sorted_features = sorted(
                importance.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]

            lines.extend([
                "【特徴量重要度 TOP10】"
            ])
            for i, (name, value) in enumerate(sorted_features, 1):
                lines.append(f"  {i:2d}. {name}: {value:.4f}")
            lines.append("")

        lines.append("=" * 60)

        return "\n".join(lines)

    def save_results(
        self,
        results: Dict[str, Any],
        output_path: str = "backtest_results.json"
    ):
        """
        結果をJSONファイルに保存

        Args:
            results: バックテスト結果
            output_path: 出力パス
        """
        # numpy/datetime型の変換
        def convert(obj):
            if isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, datetime):
                return obj.isoformat()
            return obj

        results_serializable = json.loads(
            json.dumps(results, default=convert)
        )

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results_serializable, f, ensure_ascii=False, indent=2)


class RuleValidator:
    """ルール検証クラス"""

    def __init__(self, db_path: str = "boatrace.db"):
        self.db_path = db_path
        self.backtest_engine = BacktestEngine(db_path)

    def validate_rule(
        self,
        condition: Dict[str, Any],
        adjustment: float,
        split_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        ルールをバックテストで検証

        Args:
            condition: 条件（例: {'venue_code': '01', 'pit_number': 1, 'wind_direction': '追'}）
            adjustment: 加算値（例: 0.10 = 10%加算）
            split_date: 分割日（Noneなら自動計算）

        Returns:
            検証結果
        """
        if split_date is None:
            _, split_date, _ = self.backtest_engine.get_time_split_dates()

        # データ読み込み
        _, test_df = self.backtest_engine.load_backtest_data(split_date)

        # 条件に合致するデータを抽出
        mask = pd.Series([True] * len(test_df))
        for key, value in condition.items():
            if key in test_df.columns:
                mask &= (test_df[key] == value)

        matched_df = test_df[mask].copy()

        if len(matched_df) == 0:
            return {
                'condition': condition,
                'adjustment': adjustment,
                'sample_size': 0,
                'error': '条件に合致するデータがありません'
            }

        # 勝率計算
        matched_df['is_winner'] = (matched_df['result_place'] == 1).astype(int)

        # 全体の勝率（ベースライン）
        baseline_win_rate = test_df[test_df['result_place'].notna()]['result_place'].apply(
            lambda x: 1 if x == 1 else 0
        ).mean()

        # 条件下での勝率
        actual_win_rate = matched_df['is_winner'].mean()

        # 期待勝率（ベースライン + 加算値）
        expected_win_rate = baseline_win_rate + adjustment

        # 誤差
        error = actual_win_rate - expected_win_rate

        return {
            'condition': condition,
            'adjustment': adjustment,
            'sample_size': len(matched_df),
            'baseline_win_rate': baseline_win_rate,
            'expected_win_rate': expected_win_rate,
            'actual_win_rate': actual_win_rate,
            'error': error,
            'is_valid': abs(error) < 0.05  # 5%以内なら有効
        }


if __name__ == "__main__":
    # テスト
    print("バックテストエンジン テスト")
    print("-" * 40)

    engine = BacktestEngine()

    try:
        # 日付分割を確認
        min_date, split_date, max_date = engine.get_time_split_dates()
        print(f"データ期間: {min_date} - {max_date}")
        print(f"分割日: {split_date}")

        # データ読み込みテスト
        train_df, test_df = engine.load_backtest_data(split_date)
        print(f"\n訓練データ: {len(train_df):,}行")
        print(f"テストデータ: {len(test_df):,}行")

        if 'race_id' in train_df.columns:
            print(f"訓練レース数: {train_df['race_id'].nunique():,}")
            print(f"テストレース数: {test_df['race_id'].nunique():,}")

    except Exception as e:
        print(f"エラー: {e}")
