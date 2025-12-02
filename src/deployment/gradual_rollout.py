"""
Gradual Rollout System

段階的導入システム: 10% → 50% → 100%
A/Bテスト方式で新機能を段階的にロールアウト
"""

import hashlib
import json
from typing import Dict, Optional
from pathlib import Path
from datetime import datetime


class GradualRollout:
    """段階的導入管理"""

    def __init__(self, config_path: str = "config/rollout_config.json"):
        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        """ロールアウト設定を読み込み"""
        config_file = Path(self.config_path)

        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            # デフォルト設定
            default_config = {
                'rollout_stage': 'disabled',  # disabled, 10%, 50%, 100%
                'feature_rollouts': {
                    'dynamic_integration': {
                        'stage': '100%',  # 既に全展開済み
                        'enabled_at': '2025-11-01',
                    },
                    'entry_prediction_model': {
                        'stage': '100%',  # 既に全展開済み
                        'enabled_at': '2025-11-15',
                    },
                    'probability_calibration': {
                        'stage': 'disabled',  # これから段階導入
                        'enabled_at': None,
                    },
                },
                'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            }
            self._save_config(default_config)
            return default_config

    def _save_config(self, config: Dict):
        """設定を保存"""
        config['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        config_file = Path(self.config_path)
        config_file.parent.mkdir(parents=True, exist_ok=True)

        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    def should_enable_feature(
        self,
        feature_name: str,
        race_id: int
    ) -> bool:
        """
        指定されたレースで機能を有効にすべきか判定

        Parameters:
        -----------
        feature_name : str
            機能名
        race_id : int
            レースID

        Returns:
        --------
        bool: 機能を有効にする場合True
        """
        if feature_name not in self.config['feature_rollouts']:
            return False

        rollout = self.config['feature_rollouts'][feature_name]
        stage = rollout['stage']

        # ステージごとの判定
        if stage == 'disabled':
            return False
        elif stage == '100%':
            return True
        elif stage in ['10%', '50%']:
            # ハッシュベースの決定的な割り当て
            percentage = int(stage.rstrip('%'))
            return self._hash_based_assignment(race_id, percentage)
        else:
            return False

    def _hash_based_assignment(self, race_id: int, percentage: int) -> bool:
        """
        ハッシュベースでレースを割り当て

        Parameters:
        -----------
        race_id : int
            レースID
        percentage : int
            有効化パーセンテージ (10 or 50)

        Returns:
        --------
        bool: 有効化する場合True
        """
        # race_idのハッシュ値を計算
        hash_value = int(hashlib.md5(str(race_id).encode()).hexdigest(), 16)

        # 0-99の範囲に正規化
        bucket = hash_value % 100

        # パーセンテージ以下なら有効化
        return bucket < percentage

    def update_rollout_stage(
        self,
        feature_name: str,
        stage: str
    ):
        """
        ロールアウトステージを更新

        Parameters:
        -----------
        feature_name : str
            機能名
        stage : str
            新しいステージ ('disabled', '10%', '50%', '100%')
        """
        if feature_name not in self.config['feature_rollouts']:
            self.config['feature_rollouts'][feature_name] = {}

        self.config['feature_rollouts'][feature_name]['stage'] = stage

        if stage != 'disabled' and not self.config['feature_rollouts'][feature_name].get('enabled_at'):
            self.config['feature_rollouts'][feature_name]['enabled_at'] = datetime.now().strftime('%Y-%m-%d')

        self._save_config(self.config)

        print(f"[Rollout] {feature_name} のステージを {stage} に更新しました")

    def get_rollout_status(self) -> Dict:
        """
        全機能のロールアウト状況を取得

        Returns:
        --------
        Dict: ロールアウト状況
        """
        return {
            'feature_rollouts': self.config['feature_rollouts'],
            'updated_at': self.config.get('updated_at'),
        }

    def get_feature_stage(self, feature_name: str) -> Optional[str]:
        """
        機能の現在のステージを取得

        Parameters:
        -----------
        feature_name : str
            機能名

        Returns:
        --------
        str: ステージ ('disabled', '10%', '50%', '100%')
        """
        if feature_name not in self.config['feature_rollouts']:
            return None

        return self.config['feature_rollouts'][feature_name]['stage']

    def rollout_plan(self, feature_name: str) -> Dict:
        """
        ロールアウト計画を生成

        Parameters:
        -----------
        feature_name : str
            機能名

        Returns:
        --------
        Dict: ロールアウト計画
        """
        today = datetime.now()

        plan = {
            'feature_name': feature_name,
            'stages': [
                {
                    'stage': 'disabled',
                    'duration': '開発・テスト期間',
                    'description': '開発環境でのテストを実施',
                },
                {
                    'stage': '10%',
                    'duration': '1週間',
                    'description': '10%のレースで試験運用。モニタリングを強化し、問題がないか確認',
                    'target_date': (today).strftime('%Y-%m-%d'),
                },
                {
                    'stage': '50%',
                    'duration': '1週間',
                    'description': '50%に拡大。より広範囲でのデータ収集と検証',
                    'target_date': (today).strftime('%Y-%m-%d'),
                },
                {
                    'stage': '100%',
                    'duration': '継続運用',
                    'description': '全レースで有効化。継続的にモニタリング',
                    'target_date': (today).strftime('%Y-%m-%d'),
                },
            ],
            'rollback_criteria': [
                '1着的中率が15%未満に低下',
                '3連単的中率が5%未満に低下',
                'スコア精度が0.6未満に低下',
                '予測エラーが頻発 (エラー率10%以上)',
            ],
        }

        return plan

    def check_rollout_health(
        self,
        feature_name: str,
        metrics: Dict
    ) -> Dict:
        """
        ロールアウトの健全性チェック

        Parameters:
        -----------
        feature_name : str
            機能名
        metrics : Dict
            パフォーマンスメトリクス
            {
                'hit_rate_1st': float,
                'hit_rate_top3': float,
                'avg_score_accuracy': float,
                'error_rate': float,
            }

        Returns:
        --------
        Dict: 健全性チェック結果
        """
        issues = []
        warnings = []
        recommendations = []

        # 閾値チェック
        if metrics.get('hit_rate_1st', 0) < 0.15:
            issues.append('1着的中率が15%未満')
            recommendations.append('ロールバックを検討してください')

        if metrics.get('hit_rate_top3', 0) < 0.05:
            issues.append('3連単的中率が5%未満')
            recommendations.append('ロールバックを検討してください')

        if metrics.get('avg_score_accuracy', 0) < 0.6:
            issues.append('スコア精度が0.6未満')
            recommendations.append('パラメータ調整が必要です')

        if metrics.get('error_rate', 0) > 0.1:
            issues.append('エラー率が10%以上')
            recommendations.append('即座にロールバックしてください')

        # 警告レベル
        if metrics.get('hit_rate_1st', 0) < 0.20:
            warnings.append('1着的中率が20%未満 (注意)')

        if metrics.get('avg_score_accuracy', 0) < 0.65:
            warnings.append('スコア精度が0.65未満 (注意)')

        # 総合評価
        if issues:
            status = 'CRITICAL'
            action = 'ロールバック推奨'
        elif warnings:
            status = 'WARNING'
            action = '継続モニタリング'
        else:
            status = 'HEALTHY'
            action = '次のステージへ進行可能'

        return {
            'feature_name': feature_name,
            'status': status,
            'action': action,
            'issues': issues,
            'warnings': warnings,
            'recommendations': recommendations,
            'metrics': metrics,
            'checked_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }


def print_rollout_plan(feature_name: str = 'probability_calibration'):
    """ロールアウト計画を表示"""
    rollout = GradualRollout()
    plan = rollout.rollout_plan(feature_name)

    print("=" * 70)
    print(f"ロールアウト計画: {plan['feature_name']}")
    print("=" * 70)
    print()

    for i, stage in enumerate(plan['stages'], 1):
        print(f"【ステージ {i}: {stage['stage']}】")
        print(f"  期間: {stage['duration']}")
        print(f"  内容: {stage['description']}")
        if 'target_date' in stage:
            print(f"  目標日: {stage['target_date']}")
        print()

    print("【ロールバック基準】")
    for criterion in plan['rollback_criteria']:
        print(f"  - {criterion}")
    print()


if __name__ == "__main__":
    print_rollout_plan()
