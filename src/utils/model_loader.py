# -*- coding: utf-8 -*-
"""
統一モデル読み込みインターフェース

全てのモデル読み込みをこのクラス経由にすることで:
- 重複コード削減
- モデル切り替えの容易化
- AUC検証の自動化

作成日: 2025-12-15
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

import joblib

logger = logging.getLogger(__name__)


class ModelValidationError(Exception):
    """モデル検証エラー"""
    pass


class ModelNotFoundError(Exception):
    """モデルが見つからないエラー"""
    pass


@dataclass
class ModelMetadata:
    """モデルメタデータ"""
    version: str
    created_at: str
    feature_names: Dict[str, list]
    metrics: Dict[str, Dict[str, float]]
    training_period: Optional[Dict[str, str]] = None
    description: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ModelMetadata':
        """辞書からModelMetadataを作成"""
        return cls(
            version=data.get('version', 'unknown'),
            created_at=data.get('created_at', 'unknown'),
            feature_names=data.get('feature_names', data.get('features', {})),
            metrics=data.get('metrics', {}),
            training_period=data.get('training_period'),
            description=data.get('description'),
        )


class ModelLoader:
    """
    統一モデル読み込みインターフェース

    使用例:
        loader = ModelLoader(model_dir='models')

        # V1モデル読み込み（本番推奨）
        models, meta = loader.load_conditional_rank_model(version='v1')

        # AUC検証付き読み込み
        models, meta = loader.load_conditional_rank_model(
            version='v1',
            validate_auc=True,
            min_auc_stage2=0.72,
            min_auc_stage3=0.65
        )
    """

    # デフォルトAUC基準値
    DEFAULT_MIN_AUC_STAGE1 = 0.85
    DEFAULT_MIN_AUC_STAGE2 = 0.72
    DEFAULT_MIN_AUC_STAGE3 = 0.65

    # 本番推奨モデル設定
    PRODUCTION_MODEL = {
        'version': 'v1',
        'type': 'lightgbm',
        'pattern': 'conditional_stage{stage}.joblib',
        'meta_file': 'conditional_meta.json',
    }

    def __init__(self, model_dir: str = 'models'):
        """
        初期化

        Args:
            model_dir: モデルディレクトリのパス
        """
        self.model_dir = Path(model_dir)

        if not self.model_dir.exists():
            raise ModelNotFoundError(f"モデルディレクトリが存在しません: {model_dir}")

    def load_conditional_rank_model(
        self,
        version: str = 'v1',
        validate_auc: bool = True,
        min_auc_stage1: float = None,
        min_auc_stage2: float = None,
        min_auc_stage3: float = None,
    ) -> Tuple[Dict[str, Any], ModelMetadata]:
        """
        条件付き順位予測モデルを読み込み

        Args:
            version: 'v1' (本番推奨) or 'v2' (実験) or 'latest'
            validate_auc: True時、最低AUC基準を満たすか検証
            min_auc_stage1: Stage1最低AUC（None時はデフォルト値）
            min_auc_stage2: Stage2最低AUC（None時はデフォルト値）
            min_auc_stage3: Stage3最低AUC（None時はデフォルト値）

        Returns:
            (models_dict, metadata)

        Raises:
            ModelValidationError: AUC基準未達時
            ModelNotFoundError: モデルファイルが見つからない時
        """
        min_auc_stage1 = min_auc_stage1 or self.DEFAULT_MIN_AUC_STAGE1
        min_auc_stage2 = min_auc_stage2 or self.DEFAULT_MIN_AUC_STAGE2
        min_auc_stage3 = min_auc_stage3 or self.DEFAULT_MIN_AUC_STAGE3

        if version == 'v1':
            models, metadata = self._load_v1_models()
        elif version == 'v2':
            models, metadata = self._load_v2_models()
        elif version == 'latest':
            # v2があればv2、なければv1
            try:
                models, metadata = self._load_v2_models()
            except ModelNotFoundError:
                models, metadata = self._load_v1_models()
        else:
            raise ValueError(f"不明なバージョン: {version}")

        # AUC検証
        if validate_auc:
            self._validate_auc(
                metadata,
                min_stage1=min_auc_stage1,
                min_stage2=min_auc_stage2,
                min_stage3=min_auc_stage3,
            )

        logger.info(f"モデル読み込み完了: version={version}")

        return models, metadata

    def _load_v1_models(self) -> Tuple[Dict[str, Any], ModelMetadata]:
        """V1モデル（LightGBM/本番）を読み込み"""
        models = {}

        # メタ情報読み込み
        meta_path = self.model_dir / 'conditional_meta.json'
        if not meta_path.exists():
            raise ModelNotFoundError(f"メタ情報ファイルが見つかりません: {meta_path}")

        with open(meta_path, 'r', encoding='utf-8') as f:
            meta_dict = json.load(f)

        metadata = ModelMetadata.from_dict(meta_dict)

        # 各Stageモデル読み込み
        for stage in ['stage1', 'stage2', 'stage3']:
            model_path = self.model_dir / f'conditional_{stage}.joblib'

            if not model_path.exists():
                raise ModelNotFoundError(f"モデルファイルが見つかりません: {model_path}")

            models[stage] = joblib.load(model_path)
            logger.debug(f"V1モデル読み込み: {stage}")

        return models, metadata

    def _load_v2_models(self) -> Tuple[Dict[str, Any], ModelMetadata]:
        """V2モデル（最新版を自動検索）を読み込み"""
        # 最新のV2モデルファイルを検索
        v2_files = list(self.model_dir.glob("conditional_stage2_v2_*.joblib"))

        if not v2_files:
            raise ModelNotFoundError("V2モデルが見つかりません")

        # 最新ファイルを取得
        latest = sorted(v2_files)[-1]
        parts = latest.stem.split('_')
        timestamp = '_'.join(parts[-2:])

        logger.info(f"V2モデルタイムスタンプ: {timestamp}")

        models = {}

        # 各Stageモデル読み込み
        for stage in ['stage1', 'stage2', 'stage3']:
            model_path = self.model_dir / f"conditional_{stage}_v2_{timestamp}.joblib"

            if not model_path.exists():
                raise ModelNotFoundError(f"V2モデルファイルが見つかりません: {model_path}")

            models[stage] = joblib.load(model_path)
            logger.debug(f"V2モデル読み込み: {stage}")

        # メタ情報読み込み
        meta_path = self.model_dir / f"conditional_meta_v2_{timestamp}.json"

        if not meta_path.exists():
            raise ModelNotFoundError(f"V2メタ情報が見つかりません: {meta_path}")

        with open(meta_path, 'r', encoding='utf-8') as f:
            meta_dict = json.load(f)

        metadata = ModelMetadata.from_dict(meta_dict)

        return models, metadata

    def _validate_auc(
        self,
        metadata: ModelMetadata,
        min_stage1: float,
        min_stage2: float,
        min_stage3: float,
    ):
        """AUC検証"""
        metrics = metadata.metrics

        validations = [
            ('stage1', min_stage1, metrics.get('stage1', {}).get('cv_auc_mean')),
            ('stage2', min_stage2, metrics.get('stage2', {}).get('cv_auc_mean')),
            ('stage3', min_stage3, metrics.get('stage3', {}).get('cv_auc_mean')),
        ]

        for stage, min_auc, actual_auc in validations:
            if actual_auc is None:
                logger.warning(f"{stage} のAUC情報がありません")
                continue

            if actual_auc < min_auc:
                raise ModelValidationError(
                    f"{stage} AUC検証失敗: {actual_auc:.4f} < {min_auc:.4f}"
                )

            logger.debug(f"{stage} AUC検証OK: {actual_auc:.4f} >= {min_auc:.4f}")

    def get_model_info(self, version: str = 'v1') -> Dict[str, Any]:
        """
        モデル情報を取得（読み込まずにメタ情報のみ）

        Args:
            version: 'v1' or 'v2'

        Returns:
            モデルメタ情報の辞書
        """
        if version == 'v1':
            meta_path = self.model_dir / 'conditional_meta.json'
        elif version == 'v2':
            # 最新のV2メタファイルを検索
            v2_meta_files = list(self.model_dir.glob("conditional_meta_v2_*.json"))
            if not v2_meta_files:
                return {'error': 'V2モデルが見つかりません'}
            meta_path = sorted(v2_meta_files)[-1]
        else:
            return {'error': f'不明なバージョン: {version}'}

        if not meta_path.exists():
            return {'error': f'メタファイルが見つかりません: {meta_path}'}

        with open(meta_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def list_available_models(self) -> Dict[str, list]:
        """
        利用可能なモデル一覧を取得

        Returns:
            {'v1': [...], 'v2': [...], 'deprecated': [...]}
        """
        result = {
            'v1': [],
            'v2': [],
            'deprecated': [],
        }

        # V1モデル
        v1_files = list(self.model_dir.glob("conditional_stage*.joblib"))
        if v1_files:
            result['v1'] = [str(f.name) for f in v1_files]

        # V2モデル
        v2_files = list(self.model_dir.glob("conditional_*_v2_*.joblib"))
        if v2_files:
            result['v2'] = [str(f.name) for f in v2_files]

        # 非推奨モデル
        deprecated_dir = self.model_dir / 'deprecated_v2_20251209'
        if deprecated_dir.exists():
            deprecated_files = list(deprecated_dir.glob("*.joblib"))
            result['deprecated'] = [str(f.name) for f in deprecated_files]

        return result

    def compare_models(self, version1: str = 'v1', version2: str = 'v2') -> Dict[str, Any]:
        """
        2つのモデルバージョンを比較

        Args:
            version1: 比較元バージョン
            version2: 比較先バージョン

        Returns:
            比較結果の辞書
        """
        info1 = self.get_model_info(version1)
        info2 = self.get_model_info(version2)

        if 'error' in info1 or 'error' in info2:
            return {
                'version1': info1,
                'version2': info2,
                'comparison': 'error',
            }

        metrics1 = info1.get('metrics', {})
        metrics2 = info2.get('metrics', {})

        comparison = {}
        for stage in ['stage1', 'stage2', 'stage3']:
            auc1 = metrics1.get(stage, {}).get('cv_auc_mean', 0)
            auc2 = metrics2.get(stage, {}).get('cv_auc_mean', 0)
            diff = auc2 - auc1

            comparison[stage] = {
                f'{version1}_auc': auc1,
                f'{version2}_auc': auc2,
                'diff': diff,
                'better': version2 if diff > 0 else version1,
            }

        return {
            'version1': version1,
            'version2': version2,
            'comparison': comparison,
        }


def get_production_model(model_dir: str = 'models') -> Tuple[Dict[str, Any], ModelMetadata]:
    """
    本番モデルを取得するショートカット関数

    Args:
        model_dir: モデルディレクトリ

    Returns:
        (models_dict, metadata)
    """
    loader = ModelLoader(model_dir)
    return loader.load_conditional_rank_model(version='v1', validate_auc=True)


def validate_model_file(model_path: str, min_auc_stage2: float = 0.72) -> bool:
    """
    モデルファイルの検証

    Args:
        model_path: モデルファイルパス（メタJSONのパス）
        min_auc_stage2: Stage2最低AUC

    Returns:
        検証成功時True
    """
    try:
        with open(model_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)

        metrics = meta.get('metrics', {})
        stage2_auc = metrics.get('stage2', {}).get('cv_auc_mean', 0)

        if stage2_auc < min_auc_stage2:
            logger.warning(f"Stage2 AUC不足: {stage2_auc:.4f} < {min_auc_stage2:.4f}")
            return False

        return True

    except Exception as e:
        logger.error(f"モデル検証エラー: {e}")
        return False


if __name__ == "__main__":
    # 動作確認
    logging.basicConfig(level=logging.DEBUG)

    loader = ModelLoader('models')

    # モデル一覧
    print("=== 利用可能なモデル ===")
    print(loader.list_available_models())

    # V1モデル情報
    print("\n=== V1モデル情報 ===")
    print(json.dumps(loader.get_model_info('v1'), indent=2, ensure_ascii=False))

    # モデル比較
    print("\n=== モデル比較 ===")
    comparison = loader.compare_models('v1', 'v2')
    print(json.dumps(comparison, indent=2, ensure_ascii=False))
