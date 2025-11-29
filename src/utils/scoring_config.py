"""
スコアリング重み設定管理モジュール

モード:
- accuracy: 的中率重視（コース重視、イン有利を強調）
- value: 期待値重視（選手・モーター重視、回収率向上狙い）
"""

import json
from pathlib import Path
from typing import Dict, Optional


# モード別設定ファイルパス
MODE_CONFIG_PATHS = {
    'accuracy': 'config/scoring_weights_accuracy.json',
    'value': 'config/scoring_weights_value.json',
    'default': 'config/scoring_weights.json'
}

# デフォルト重み（モード別）
DEFAULT_WEIGHTS = {
    'accuracy': {
        'course_weight': 50.0,
        'racer_weight': 30.0,
        'motor_weight': 10.0,
        'kimarite_weight': 5.0,
        'grade_weight': 5.0
    },
    'value': {
        'course_weight': 25.0,
        'racer_weight': 35.0,
        'motor_weight': 20.0,
        'kimarite_weight': 15.0,
        'grade_weight': 5.0
    }
}


class ScoringConfig:
    """スコアリング重み設定の管理クラス"""

    def __init__(self, config_path: str = "config/scoring_weights.json", mode: Optional[str] = None):
        """
        Args:
            config_path: 設定ファイルパス（mode指定時は無視）
            mode: 'accuracy'（的中率重視）または 'value'（期待値重視）
        """
        self.mode = mode
        if mode and mode in MODE_CONFIG_PATHS:
            self.config_path = Path(MODE_CONFIG_PATHS[mode])
        else:
            self.config_path = Path(config_path)

    def load_weights(self) -> Dict[str, float]:
        """
        重み設定をロード

        Returns:
            {
                'course_weight': float,
                'racer_weight': float,
                'motor_weight': float,
                'kimarite_weight': float,
                'grade_weight': float
            }
        """
        # モード指定時はモード別デフォルト値を使用
        if self.mode and self.mode in DEFAULT_WEIGHTS:
            default = DEFAULT_WEIGHTS[self.mode]
        else:
            default = {
                'course_weight': 35.0,
                'racer_weight': 35.0,
                'motor_weight': 20.0,
                'kimarite_weight': 5.0,
                'grade_weight': 5.0
            }

        if not self.config_path.exists():
            return default

        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        return {
            'course_weight': float(config.get('course_weight', default['course_weight'])),
            'racer_weight': float(config.get('racer_weight', default['racer_weight'])),
            'motor_weight': float(config.get('motor_weight', default['motor_weight'])),
            'kimarite_weight': float(config.get('kimarite_weight', default['kimarite_weight'])),
            'grade_weight': float(config.get('grade_weight', default['grade_weight']))
        }

    @classmethod
    def for_mode(cls, mode: str) -> 'ScoringConfig':
        """
        モード指定でインスタンスを作成

        Args:
            mode: 'accuracy' または 'value'

        Returns:
            ScoringConfig インスタンス
        """
        return cls(mode=mode)

    def get_mode_description(self) -> str:
        """モードの説明を取得"""
        if self.mode == 'accuracy':
            return "的中率重視: コース有利を重視し、当てやすい予測"
        elif self.mode == 'value':
            return "期待値重視: 選手・モーター重視、回収率向上を狙う予測"
        else:
            return "標準モード"

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
