"""
統合テスト - データフロー全体の動作確認
各モジュールが連携して正しく動作することを検証
"""
import pytest
import sqlite3
from datetime import datetime, timedelta
import pandas as pd
from config.settings import DATABASE_PATH


class TestDataFlow:
    """データフロー全体のテスト"""

    @pytest.fixture
    def sample_race_data(self):
        """テスト用レースデータ"""
        return {
            'venue_code': '07',  # 蒲郡
            'race_date': '2025-01-01',
            'race_number': 1,
            'expected_entries': 6
        }

    def test_database_integrity(self):
        """データベース整合性テスト"""
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        # テスト1: 外部キー制約チェック
        cursor.execute("""
            SELECT COUNT(*) FROM entries e
            LEFT JOIN races r ON e.race_id = r.id
            WHERE r.id IS NULL
        """)
        orphan_entries = cursor.fetchone()[0]
        assert orphan_entries == 0, f"孤立したエントリーが{orphan_entries}件存在"

        # テスト2: 結果データの整合性
        cursor.execute("""
            SELECT COUNT(*) FROM results res
            LEFT JOIN races r ON res.race_id = r.id
            WHERE r.id IS NULL
        """)
        orphan_results = cursor.fetchone()[0]
        assert orphan_results == 0, f"孤立した結果データが{orphan_results}件存在"

        # テスト3: 1レース = 6艇の確認
        cursor.execute("""
            SELECT race_id, COUNT(*) as entry_count
            FROM entries
            GROUP BY race_id
            HAVING COUNT(*) != 6
            LIMIT 10
        """)
        invalid_races = cursor.fetchall()
        assert len(invalid_races) == 0, f"6艇でないレースが存在: {invalid_races}"

        conn.close()

    def test_feature_generation_pipeline(self, sample_race_data):
        """特徴量生成パイプラインのテスト"""
        from src.features.optimized_features import OptimizedFeatureGenerator

        generator = OptimizedFeatureGenerator()

        conn = sqlite3.connect(DATABASE_PATH)

        # レースデータ取得
        query = """
            SELECT * FROM races r
            JOIN entries e ON r.id = e.race_id
            WHERE r.venue_code = ? AND r.race_date = ? AND r.race_number = ?
            LIMIT 1
        """
        race_data = pd.read_sql_query(
            query, conn,
            params=(
                sample_race_data['venue_code'],
                sample_race_data['race_date'],
                sample_race_data['race_number']
            )
        )

        if len(race_data) == 0:
            pytest.skip("テスト用データが存在しません")

        # 特徴量生成
        features = generator.generate(race_data)

        # 検証1: 必須カラムの存在確認
        required_columns = ['pit_number', 'win_rate', 'motor_number']
        for col in required_columns:
            assert col in features.columns, f"必須カラム '{col}' が欠落"

        # 検証2: データ型チェック
        assert features['pit_number'].dtype in ['int64', 'int32'], "pit_numberの型が不正"
        assert features['win_rate'].dtype in ['float64', 'float32'], "win_rateの型が不正"

        # 検証3: 値の範囲チェック
        assert (features['pit_number'] >= 1).all(), "pit_numberが1未満"
        assert (features['pit_number'] <= 6).all(), "pit_numberが6超過"
        assert (features['win_rate'] >= 0).all(), "win_rateが負数"
        assert (features['win_rate'] <= 10).all(), "win_rateが異常値（10超過）"

        conn.close()

    def test_prediction_probability_sum(self, sample_race_data):
        """予測確率の合計が1になることを確認"""
        # モデルが存在する場合のみテスト
        try:
            from src.prediction.integrated_predictor import IntegratedPredictor

            predictor = IntegratedPredictor()

            # ダミーの特徴量で予測
            import numpy as np
            dummy_features = pd.DataFrame({
                'pit_number': [1, 2, 3, 4, 5, 6],
                'win_rate': [6.5, 5.8, 5.2, 4.9, 4.3, 3.8],
                'motor_number': [10, 20, 30, 40, 50, 60],
            })

            predictions = []
            for idx, row in dummy_features.iterrows():
                pred = predictor.predict_single(row)
                predictions.append(pred)

            # 確率合計チェック（許容誤差5%）
            total_prob = sum(predictions)
            assert 0.95 <= total_prob <= 1.05, f"確率の合計が異常: {total_prob}"

        except ImportError:
            pytest.skip("予測モデルが未実装")

    def test_kelly_calculation_validity(self):
        """Kelly基準計算の妥当性テスト"""
        from src.betting.kelly_strategy import KellyBettingStrategy

        strategy = KellyBettingStrategy(bankroll=10000, kelly_fraction=0.25)

        # テストケース1: 正の期待値
        pred_prob = 0.20
        odds = 6.0
        ev = strategy.calculate_expected_value(pred_prob, odds)

        assert ev > 0, "正の期待値が期待されるがゼロ以下"
        assert 0 < ev < 1, f"期待値が異常: {ev}"

        kelly_f, bet_amount = strategy.calculate_kelly_bet(pred_prob, odds)

        assert 0 <= kelly_f <= 0.2, f"Kelly分数が異常: {kelly_f}"
        assert 0 <= bet_amount <= 2000, f"賭け金が異常: {bet_amount}"

        # テストケース2: 負の期待値（賭けない）
        pred_prob = 0.10
        odds = 3.0
        ev = strategy.calculate_expected_value(pred_prob, odds)

        assert ev < 0, "負の期待値が期待される"

        kelly_f, bet_amount = strategy.calculate_kelly_bet(pred_prob, odds)

        assert kelly_f == 0.0, "負の期待値では賭けないはず"
        assert bet_amount == 0.0, "負の期待値では賭け金0のはず"


class TestDataExport:
    """AI解析用エクスポート機能のテスト"""

    def test_export_query_execution(self):
        """エクスポートクエリが正常に実行できるか"""
        conn = sqlite3.connect(DATABASE_PATH)

        # 日付範囲取得
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(race_date) FROM races")
        max_date_str = cursor.fetchone()[0]

        if not max_date_str:
            pytest.skip("レースデータが存在しません")

        # 日付フォーマット判定
        if '-' in max_date_str:
            date_format = '%Y-%m-%d'
        else:
            date_format = '%Y%m%d'

        max_date = datetime.strptime(max_date_str, date_format).date()
        start_date = max_date - timedelta(days=30)

        start_date_str = start_date.strftime(date_format)
        end_date_str = max_date.strftime(date_format)

        # エクスポートクエリ実行（サンプル100件）
        query = """
            SELECT
                r.id as race_id,
                r.race_date,
                r.venue_code,
                v.name as venue_name,
                r.race_number,
                e.pit_number,
                e.racer_name,
                e.racer_rank as racer_class,
                e.win_rate,
                res.rank,
                res.winning_technique as kimarite
            FROM races r
            LEFT JOIN venues v ON r.venue_code = v.code
            LEFT JOIN entries e ON r.id = e.race_id
            LEFT JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
            LEFT JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
            WHERE r.race_date BETWEEN ? AND ?
            ORDER BY r.race_date, r.venue_code, r.race_number, e.pit_number
            LIMIT 100
        """

        df = pd.read_sql_query(query, conn, params=(start_date_str, end_date_str))

        # 検証1: データが取得できているか
        assert len(df) > 0, "エクスポートデータが0件"

        # 検証2: 必須カラムの存在確認
        required_columns = [
            'race_id', 'race_date', 'venue_code', 'pit_number',
            'racer_name', 'racer_class', 'win_rate'
        ]
        for col in required_columns:
            assert col in df.columns, f"必須カラム '{col}' が欠落"

        # 検証3: データ型チェック
        assert df['race_id'].dtype in ['int64', 'int32'], "race_idの型が不正"
        assert df['pit_number'].dtype in ['int64', 'int32'], "pit_numberの型が不正"

        # 検証4: 値の範囲チェック
        assert (df['pit_number'] >= 1).all(), "pit_numberが1未満"
        assert (df['pit_number'] <= 6).all(), "pit_numberが6超過"

        conn.close()

    def test_csv_export_size_estimation(self):
        """CSVサイズ推定の精度テスト"""
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT MAX(race_date) FROM races")
        max_date_str = cursor.fetchone()[0]

        if not max_date_str:
            pytest.skip("レースデータが存在しません")

        if '-' in max_date_str:
            date_format = '%Y-%m-%d'
        else:
            date_format = '%Y%m%d'

        max_date = datetime.strptime(max_date_str, date_format).date()
        start_date = max_date - timedelta(days=30)

        start_date_str = start_date.strftime(date_format)
        end_date_str = max_date.strftime(date_format)

        # レコード数取得
        query_count = """
            SELECT COUNT(*)
            FROM races r
            JOIN entries e ON r.id = e.race_id
            WHERE r.race_date BETWEEN ? AND ?
        """
        cursor.execute(query_count, (start_date_str, end_date_str))
        total_records = cursor.fetchone()[0]

        # 推定サイズ計算
        estimated_size_bytes = total_records * 500
        estimated_size_mb = estimated_size_bytes / (1024 * 1024)

        # 検証: 推定サイズが妥当な範囲内か
        assert estimated_size_mb > 0, "推定サイズが0以下"
        assert estimated_size_mb < 1000, "推定サイズが異常に大きい（1GB超過）"

        conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
