"""
スコアリング重み設定管理モジュール
"""

import json
from pathlib import Path
from typing import Dict


class ScoringConfig:
    """スコアリング重み設定の管理クラス"""

    def __init__(self, config_path: str = "config/scoring_weights.json"):
        self.config_path = Path(config_path)

    def load_weights(self) -> Dict[str, float]:
        """
        重み設定をロード

        Returns:
            {
                'course_weight': 40.0,
                'racer_weight': 40.0,
                'motor_weight': 20.0
            }
        """
        if not self.config_path.exists():
            # デフォルト値を返す
            return {
                'course_weight': 40.0,
                'racer_weight': 40.0,
                'motor_weight': 20.0
            }

        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        return {
            'course_weight': float(config.get('course_weight', 40.0)),
            'racer_weight': float(config.get('racer_weight', 40.0)),
            'motor_weight': float(config.get('motor_weight', 20.0))
        }

    def save_weights(self, course_weight: float, racer_weight: float, motor_weight: float) -> bool:
        """
        重み設定を保存

        Args:
            course_weight: コーススコアの重み
            racer_weight: 選手スコアの重み
            motor_weight: モータースコアの重み

        Returns:
            保存成功: True, 失敗: False
        """
        total = course_weight + racer_weight + motor_weight

        if abs(total - 100.0) > 0.1:
            raise ValueError(f"重みの合計は100である必要があります（現在: {total}）")

        config = {
            'course_weight': course_weight,
            'racer_weight': racer_weight,
            'motor_weight': motor_weight,
            'total': 100,
            'description': f"Custom scoring weights: Course={course_weight}, Racer={racer_weight}, Motor={motor_weight}"
        }

        # ディレクトリが存在しない場合は作成
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        return True

    def reset_to_default(self) -> Dict[str, float]:
        """
        デフォルト値にリセット

        Returns:
            デフォルト重み設定
        """
        self.save_weights(40.0, 40.0, 20.0)
        return self.load_weights()


if __name__ == "__main__":
    # テスト
    config = ScoringConfig()

    print("=== 現在の設定 ===")
    weights = config.load_weights()
    print(f"コース: {weights['course_weight']}点")
    print(f"選手: {weights['racer_weight']}点")
    print(f"モーター: {weights['motor_weight']}点")
    print(f"合計: {sum(weights.values())}点")
