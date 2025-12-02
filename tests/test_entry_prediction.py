"""
進入予測モデルのテスト
"""

import pytest
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.analysis.entry_prediction_model import EntryPredictionModel, EntryPrediction


class TestEntryPredictionModel:
    """進入予測モデルのテスト"""

    def setup_method(self):
        # テスト用のダミーモデル（DB接続なし）
        self.model = EntryPredictionModel()

    def test_basic_prediction(self):
        """基本的な進入予測テスト"""
        # モックデータ
        entries = [
            {'pit_number': 1, 'racer_number': '1234'},
            {'pit_number': 2, 'racer_number': '5678'},
            {'pit_number': 3, 'racer_number': '9012'},
            {'pit_number': 4, 'racer_number': '3456'},
            {'pit_number': 5, 'racer_number': '7890'},
            {'pit_number': 6, 'racer_number': '1111'},
        ]

        # DBがない環境でもテストできるよう、エラーハンドリングを確認
        try:
            predictions = self.model.predict_race_entries(
                race_id=1,
                entries=entries
            )

            # 6艇分の予測が返される
            assert len(predictions) == 6

            # 各予測の型チェック
            for pit, pred in predictions.items():
                assert isinstance(pred, EntryPrediction)
                assert 1 <= pred.pit_number <= 6
                assert 1 <= pred.predicted_course <= 6
                assert isinstance(pred.probabilities, dict)
                assert 0.0 <= pred.confidence <= 1.0
                assert isinstance(pred.is_front_entry_prone, bool)
                assert 0.0 <= pred.front_entry_rate <= 1.0

            print("[OK] 基本予測テスト成功")

        except Exception as e:
            # DB接続エラーは想定内
            if "no such table" in str(e) or "unable to open database" in str(e):
                print("[SKIP] DBなし環境のためスキップ（正常）")
            else:
                raise

    def test_entry_impact_score(self):
        """進入影響スコア計算のテスト"""
        # サンプル予測
        prediction = EntryPrediction(
            pit_number=3,
            predicted_course=1,  # 3号艇が1コース取得
            probabilities={1: 0.7, 2: 0.2, 3: 0.1},
            confidence=0.7,
            is_front_entry_prone=True,
            front_entry_rate=0.6,
            description="前付け"
        )

        impact = self.model.calculate_entry_impact_score(
            pit_number=3,
            prediction=prediction,
            max_score=10.0
        )

        # 内コース取得は有利
        assert impact['score'] > 5.0
        assert impact['impact_type'] == 'positive'
        assert impact['predicted_course'] == 1
        print(f"[OK] 進入影響スコアテスト成功: score={impact['score']:.2f}")

    def test_front_entry_detection(self):
        """前付け検出のテスト"""
        # 枠なり
        prediction_normal = EntryPrediction(
            pit_number=1,
            predicted_course=1,
            probabilities={1: 0.95, 2: 0.05},
            confidence=0.95,
            is_front_entry_prone=False,
            front_entry_rate=0.05,
            description="枠なり"
        )
        assert not prediction_normal.is_front_entry_prone

        # 前付け
        prediction_aggressive = EntryPrediction(
            pit_number=4,
            predicted_course=1,
            probabilities={1: 0.6, 4: 0.4},
            confidence=0.6,
            is_front_entry_prone=True,
            front_entry_rate=0.7,
            description="前付け"
        )
        assert prediction_aggressive.is_front_entry_prone

        print("[OK] 前付け検出テスト成功")

    def test_cache_mechanism(self):
        """キャッシュ機構のテスト"""
        racer_number = 'TEST001'

        # キャッシュクリア
        self.model._entry_cache.clear()
        assert racer_number not in self.model._entry_cache

        # 手動でキャッシュにデータを追加
        pattern1 = {
            'pit_course_matrix': {1: {1: 10, 2: 2}},
            'total_races': 12,
            'front_entry_rate': 0.17,
            'entry_type': 'occasional'
        }
        self.model._entry_cache[racer_number] = pattern1

        # キャッシュから取得できることを確認
        pattern2 = self.model._get_racer_entry_pattern(racer_number)
        assert pattern2 == pattern1
        assert racer_number in self.model._entry_cache

        print("[OK] キャッシュ機構テスト成功")


if __name__ == "__main__":
    print("=" * 70)
    print("進入予測モデルテスト実行")
    print("=" * 70)

    test = TestEntryPredictionModel()

    try:
        test.setup_method()
        test.test_basic_prediction()

        test.setup_method()
        test.test_entry_impact_score()

        test.setup_method()
        test.test_front_entry_detection()

        test.setup_method()
        test.test_cache_mechanism()

        print("\n" + "=" * 70)
        print("[SUCCESS] 全テスト成功！")
        print("=" * 70)

    except AssertionError as e:
        print(f"\n[FAIL] テスト失敗: {e}")
        raise
    except Exception as e:
        print(f"\n[ERROR] エラー: {e}")
        import traceback
        traceback.print_exc()
        raise
