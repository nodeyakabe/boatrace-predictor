"""
確率較正（Probability Calibration）
予測確率を実際の頻度に合わせて調整
"""

import numpy as np
import pickle
from typing import List, Tuple, Optional
from pathlib import Path
from sklearn.isotonic import IsotonicRegression


class ProbabilityCalibrator:
    """確率較正クラス"""

    def __init__(self, calibration_file: Optional[str] = None):
        """
        Args:
            calibration_file: 較正モデルの保存ファイル
        """
        if calibration_file is None:
            calibration_file = Path(__file__).parent.parent.parent / 'data' / 'calibration_model.pkl'

        self.calibration_file = calibration_file
        self.calibrator = None
        self.is_fitted = False

    def fit(
        self,
        predicted_probs: List[float],
        actual_results: List[int]
    ):
        """
        較正モデルを学習

        Args:
            predicted_probs: 予測確率のリスト [0.55, 0.14, ...]
            actual_results: 実際の結果（1着=1, それ以外=0） [1, 0, ...]

        使用例:
            # 過去1000レースのデータで学習
            calibrator.fit(all_predicted_probs, all_actual_results)
            calibrator.save_model()
        """
        if len(predicted_probs) < 10:
            raise ValueError("較正には最低10サンプル必要です")

        # Isotonic Regression を使用
        # 単調性を保ちつつ、予測確率を実際の頻度に合わせる
        self.calibrator = IsotonicRegression(out_of_bounds='clip')
        self.calibrator.fit(predicted_probs, actual_results)
        self.is_fitted = True

        print(f"較正モデルを学習しました（サンプル数: {len(predicted_probs)}）")

    def calibrate(
        self,
        predicted_prob: float
    ) -> float:
        """
        予測確率を較正

        Args:
            predicted_prob: 元の予測確率

        Returns:
            較正された確率
        """
        if not self.is_fitted:
            # 較正モデルが未学習の場合は元の確率をそのまま返す
            return predicted_prob

        calibrated = self.calibrator.predict([predicted_prob])[0]
        return float(calibrated)

    def calibrate_predictions(
        self,
        predictions: List[Dict]
    ) -> List[Dict]:
        """
        予測リスト全体を較正

        Args:
            predictions: 予測結果リスト
                [
                    {'pit_number': 1, 'estimated_win_rate': 0.55, ...},
                    ...
                ]

        Returns:
            較正された予測リスト
        """
        if not self.is_fitted:
            print("警告: 較正モデルが未学習です。元の確率を使用します。")
            return predictions

        calibrated_predictions = []

        for pred in predictions:
            calibrated_pred = pred.copy()

            # 推定勝率を較正
            if 'estimated_win_rate' in pred:
                original_prob = pred['estimated_win_rate']
                calibrated_prob = self.calibrate(original_prob)

                calibrated_pred['estimated_win_rate'] = calibrated_prob
                calibrated_pred['original_win_rate'] = original_prob
                calibrated_pred['calibration_applied'] = True

            calibrated_predictions.append(calibrated_pred)

        return calibrated_predictions

    def save_model(self):
        """較正モデルを保存"""
        if not self.is_fitted:
            raise ValueError("較正モデルが未学習です")

        # ディレクトリが存在しない場合は作成
        Path(self.calibration_file).parent.mkdir(parents=True, exist_ok=True)

        with open(self.calibration_file, 'wb') as f:
            pickle.dump(self.calibrator, f)

        print(f"較正モデルを保存しました: {self.calibration_file}")

    def load_model(self) -> bool:
        """
        較正モデルを読み込み

        Returns:
            成功したかどうか
        """
        if not Path(self.calibration_file).exists():
            print(f"較正モデルが見つかりません: {self.calibration_file}")
            return False

        try:
            with open(self.calibration_file, 'rb') as f:
                self.calibrator = pickle.load(f)

            self.is_fitted = True
            print(f"較正モデルを読み込みました: {self.calibration_file}")
            return True

        except Exception as e:
            print(f"較正モデルの読み込みエラー: {e}")
            return False

    def retrain_with_new_data(
        self,
        new_predicted_probs: List[float],
        new_actual_results: List[int],
        keep_old_data: bool = True
    ):
        """
        新しいデータで再学習

        Args:
            new_predicted_probs: 新しい予測確率
            new_actual_results: 新しい実際の結果
            keep_old_data: 既存データを保持するか

        使用例:
            # 月次で再学習
            calibrator.load_model()
            calibrator.retrain_with_new_data(
                last_month_probs,
                last_month_results,
                keep_old_data=False  # 最新データのみで学習
            )
            calibrator.save_model()
        """
        if keep_old_data and self.is_fitted:
            # 既存の較正曲線のデータポイントを取得
            # （Isotonic Regressionから直接は取得できないため、新しいデータで上書き）
            pass

        # 新しいデータで学習
        self.fit(new_predicted_probs, new_actual_results)


def create_calibration_training_data(db_path: str) -> Tuple[List[float], List[int]]:
    """
    データベースから較正用の学習データを作成

    Args:
        db_path: データベースパス

    Returns:
        (predicted_probs, actual_results)
    """
    import sqlite3

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 予測と結果を取得
    cursor.execute("""
        SELECT
            rp.estimated_win_rate,
            CASE WHEN CAST(r.rank AS INTEGER) = 1 THEN 1 ELSE 0 END as is_first
        FROM race_predictions rp
        JOIN results r ON rp.race_id = r.race_id AND rp.pit_number = r.pit_number
        WHERE rp.estimated_win_rate IS NOT NULL
          AND r.rank IS NOT NULL
        ORDER BY rp.race_id DESC
        LIMIT 1000
    """)

    data = cursor.fetchall()
    conn.close()

    if len(data) == 0:
        return [], []

    predicted_probs = [row[0] for row in data]
    actual_results = [row[1] for row in data]

    return predicted_probs, actual_results


# 使用例
"""
# 1. 較正モデルを初回学習
from config.settings import DATABASE_PATH

calibrator = ProbabilityCalibrator()

# 過去データから学習データを作成
predicted_probs, actual_results = create_calibration_training_data(DATABASE_PATH)

if len(predicted_probs) >= 100:
    calibrator.fit(predicted_probs, actual_results)
    calibrator.save_model()
else:
    print("学習データ不足")


# 2. 予測時に較正を適用
calibrator = ProbabilityCalibrator()
if calibrator.load_model():
    # 予測を較正
    calibrated_predictions = calibrator.calibrate_predictions(predictions)
else:
    # 較正モデルがない場合は元の予測を使用
    calibrated_predictions = predictions


# 3. 月次で再学習
calibrator = ProbabilityCalibrator()
calibrator.load_model()

# 先月のデータで再学習
last_month_probs, last_month_results = get_last_month_data()
calibrator.retrain_with_new_data(last_month_probs, last_month_results)
calibrator.save_model()
"""
