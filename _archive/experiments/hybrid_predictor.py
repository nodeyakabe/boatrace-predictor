"""
ハイブリッド予測システム

実験結果を基に、会場ごとに最適なモデルを自動選択して予測を行う。
- 会場特化モデルが優秀な会場: 会場専用モデル使用
- その他の会場: 統合モデル使用
"""

import os
import xgboost as xgb
import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')


class HybridPredictor:
    """ハイブリッド予測システム"""

    # 会場特化モデルが統合モデルより優れている会場と性能
    VENUE_SPECIFIC_SUPERIOR = {
        '07': {'auc': 0.9341, 'delta': +0.0845, 'model': 'models/stage2_venue_07.json'},
        '11': {'auc': 0.9173, 'delta': +0.0677, 'model': 'models/stage2_venue_11.json'},
        '18': {'auc': 0.8989, 'delta': +0.0493, 'model': 'models/stage2_venue_18.json'},
        '21': {'auc': 0.8746, 'delta': +0.0250, 'model': 'models/stage2_venue_21.json'},
        '08': {'auc': 0.8715, 'delta': +0.0219, 'model': 'models/stage2_venue_08.json'},
        '09': {'auc': 0.8679, 'delta': +0.0183, 'model': 'models/stage2_venue_09.json'},
        '13': {'auc': 0.8570, 'delta': +0.0074, 'model': 'models/stage2_venue_13.json'},
        '24': {'auc': 0.8604, 'delta': +0.0108, 'model': 'models/stage2_venue_24.json'},
        '05': {'auc': 0.8512, 'delta': +0.0016, 'model': 'models/stage2_venue_05.json'},
    }

    # 統合モデル（ベースライン）
    UNIFIED_MODEL = {
        'auc': 0.8496,
        'model': 'models/stage2_optimized.json'
    }

    def __init__(self):
        """初期化"""
        self.models: Dict[str, xgb.XGBClassifier] = {}
        self.unified_model: Optional[xgb.XGBClassifier] = None

    def load_models(self, preload_all: bool = False):
        """
        モデルのロード

        Args:
            preload_all: True の場合、全モデルを事前ロード（メモリ使用大）
                        False の場合、必要に応じて遅延ロード（推奨）
        """
        # 統合モデルは常にロード
        if not os.path.exists(self.UNIFIED_MODEL['model']):
            raise FileNotFoundError(f"統合モデルが見つかりません: {self.UNIFIED_MODEL['model']}")

        self.unified_model = xgb.XGBClassifier()
        self.unified_model.load_model(self.UNIFIED_MODEL['model'])
        print(f"✅ 統合モデルをロード: {self.UNIFIED_MODEL['model']}")

        if preload_all:
            # 全会場モデルを事前ロード
            for venue_code, info in self.VENUE_SPECIFIC_SUPERIOR.items():
                if os.path.exists(info['model']):
                    model = xgb.XGBClassifier()
                    model.load_model(info['model'])
                    self.models[venue_code] = model
                    print(f"✅ 会場{venue_code}モデルをロード: {info['model']}")
                else:
                    print(f"⚠️  会場{venue_code}モデルが見つかりません: {info['model']}")

    def _load_venue_model(self, venue_code: str) -> xgb.XGBClassifier:
        """
        会場専用モデルを遅延ロード

        Args:
            venue_code: 会場コード（例: '07'）

        Returns:
            ロードされたモデル
        """
        if venue_code not in self.models:
            info = self.VENUE_SPECIFIC_SUPERIOR[venue_code]
            if not os.path.exists(info['model']):
                raise FileNotFoundError(f"会場{venue_code}モデルが見つかりません: {info['model']}")

            model = xgb.XGBClassifier()
            model.load_model(info['model'])
            self.models[venue_code] = model
            print(f"✅ 会場{venue_code}モデルをロード: {info['model']}")

        return self.models[venue_code]

    def get_best_model_for_venue(self, venue_code: str) -> Tuple[xgb.XGBClassifier, str, float]:
        """
        会場に応じて最適なモデルを取得

        Args:
            venue_code: 会場コード（例: '07', '01'）

        Returns:
            (モデル, モデルタイプ, 期待AUC)
        """
        # 会場コードを2桁にフォーマット
        venue_code_formatted = f"{int(venue_code):02d}"

        if venue_code_formatted in self.VENUE_SPECIFIC_SUPERIOR:
            # 会場特化モデルが優秀な場合
            info = self.VENUE_SPECIFIC_SUPERIOR[venue_code_formatted]
            model = self._load_venue_model(venue_code_formatted)
            return model, f"venue_{venue_code_formatted}", info['auc']
        else:
            # 統合モデルを使用
            return self.unified_model, "unified", self.UNIFIED_MODEL['auc']

    def predict(self, X: pd.DataFrame, venue_code: str) -> np.ndarray:
        """
        予測実行（確率を返す）

        Args:
            X: 特徴量データフレーム（35次元）
            venue_code: 会場コード

        Returns:
            勝利確率（0-1）
        """
        model, model_type, expected_auc = self.get_best_model_for_venue(venue_code)
        probas = model.predict_proba(X)[:, 1]

        return probas

    def predict_with_info(
        self,
        X: pd.DataFrame,
        venue_code: str
    ) -> Dict:
        """
        詳細情報付きで予測実行

        Args:
            X: 特徴量データフレーム
            venue_code: 会場コード

        Returns:
            {
                'probabilities': 勝利確率配列,
                'model_type': 使用モデルタイプ,
                'expected_auc': 期待AUC,
                'venue_code': 会場コード,
                'is_venue_specific': 会場特化モデルか
            }
        """
        model, model_type, expected_auc = self.get_best_model_for_venue(venue_code)
        probas = model.predict_proba(X)[:, 1]

        venue_code_formatted = f"{int(venue_code):02d}"

        return {
            'probabilities': probas,
            'model_type': model_type,
            'expected_auc': expected_auc,
            'venue_code': venue_code_formatted,
            'is_venue_specific': venue_code_formatted in self.VENUE_SPECIFIC_SUPERIOR
        }

    def get_venue_info(self, venue_code: str) -> Dict:
        """
        会場の情報を取得

        Args:
            venue_code: 会場コード

        Returns:
            会場情報辞書
        """
        venue_code_formatted = f"{int(venue_code):02d}"

        if venue_code_formatted in self.VENUE_SPECIFIC_SUPERIOR:
            info = self.VENUE_SPECIFIC_SUPERIOR[venue_code_formatted].copy()
            info['recommendation'] = '会場特化モデル使用推奨'
            info['is_superior'] = True
        else:
            info = {
                'auc': self.UNIFIED_MODEL['auc'],
                'delta': 0.0,
                'model': self.UNIFIED_MODEL['model'],
                'recommendation': '統合モデル使用',
                'is_superior': False
            }

        info['venue_code'] = venue_code_formatted
        return info

    def print_model_info(self):
        """モデル情報を表示"""
        print("=" * 80)
        print("ハイブリッド予測システム - モデル情報")
        print("=" * 80)
        print(f"\n統合モデル（ベースライン）:")
        print(f"  AUC: {self.UNIFIED_MODEL['auc']}")
        print(f"  ファイル: {self.UNIFIED_MODEL['model']}")

        print(f"\n会場特化モデル（統合モデルより優秀な9会場）:")
        for venue_code, info in sorted(
            self.VENUE_SPECIFIC_SUPERIOR.items(),
            key=lambda x: x[1]['auc'],
            reverse=True
        ):
            print(f"  会場{venue_code}: AUC {info['auc']:.4f} (統合比 {info['delta']:+.4f})")

        print(f"\nその他15会場: 統合モデル使用（AUC {self.UNIFIED_MODEL['auc']}）")
        print("=" * 80)


def demo_usage():
    """使用例デモ"""
    print("=" * 80)
    print("ハイブリッド予測システム - 使用例")
    print("=" * 80)

    # 初期化
    predictor = HybridPredictor()
    predictor.load_models()

    # モデル情報表示
    predictor.print_model_info()

    # 会場情報取得例
    print("\n【会場情報取得例】")
    for venue in ['07', '01', '18']:
        info = predictor.get_venue_info(venue)
        print(f"\n会場{venue}:")
        print(f"  推奨: {info['recommendation']}")
        print(f"  期待AUC: {info['auc']:.4f}")
        if info['is_superior']:
            print(f"  統合モデル比: {info['delta']:+.4f}")

    # 予測例（ダミーデータ）
    print("\n【予測例】")
    print("※ 実際の使用時は、35次元の特徴量データを用意してください")

    # ダミー特徴量データ（35次元）
    dummy_features = pd.DataFrame(
        np.random.randn(6, 35),  # 6艇分
        columns=[
            'actual_course', 'actual_course_1', 'actual_course_2', 'actual_course_3',
            'actual_course_4', 'actual_course_5', 'actual_course_6', 'avg_st',
            'boat_number', 'boat_second_rate', 'boat_third_rate', 'exhibition_time',
            'f_count', 'l_count', 'motor_number', 'motor_second_rate', 'motor_third_rate',
            'pit_course_diff', 'pit_number', 'pit_number_1', 'pit_number_2',
            'pit_number_3', 'pit_number_4', 'pit_number_5', 'pit_number_6',
            'race_number', 'racer_age', 'racer_weight', 'second_rate', 'st_time',
            'temperature', 'third_rate', 'tilt_angle', 'water_temperature',
            'wave_height', 'win_rate', 'wind_speed'
        ]
    )

    # 会場07での予測（会場特化モデル使用）
    result_07 = predictor.predict_with_info(dummy_features, '07')
    print(f"\n会場07の予測:")
    print(f"  使用モデル: {result_07['model_type']}")
    print(f"  期待AUC: {result_07['expected_auc']:.4f}")
    print(f"  予測確率（上位3艇）: {result_07['probabilities'][:3]}")

    # 会場01での予測（統合モデル使用）
    result_01 = predictor.predict_with_info(dummy_features, '01')
    print(f"\n会場01の予測:")
    print(f"  使用モデル: {result_01['model_type']}")
    print(f"  期待AUC: {result_01['expected_auc']:.4f}")
    print(f"  予測確率（上位3艇）: {result_01['probabilities'][:3]}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    demo_usage()
