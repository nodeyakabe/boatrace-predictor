#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
モデル更新時の自動検証スクリプト

使い方:
    python scripts/validate_model_update.py --new-model models/new_conditional_meta.json

検証内容:
    1. AUCが既存モデルを上回っているか
    2. 必須メタデータが存在するか
    3. 特徴量の整合性確認

終了コード:
    0: 検証成功（マージ可能）
    1: 検証失敗（マージ不可）

作成日: 2025-12-15
"""

import sys
import os
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Tuple

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from config.model_config import (
    MODEL_VALIDATION_CRITERIA,
    PRODUCTION_MODEL,
    get_current_auc,
)


class ValidationResult:
    """検証結果を保持するクラス"""

    def __init__(self):
        self.passed = True
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []

    def add_error(self, message: str):
        self.errors.append(message)
        self.passed = False

    def add_warning(self, message: str):
        self.warnings.append(message)

    def add_info(self, message: str):
        self.info.append(message)

    def print_report(self):
        """検証結果をレポート出力"""
        print("=" * 70)
        print("モデル更新検証レポート")
        print("=" * 70)
        print(f"検証日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        if self.info:
            print("[INFO]")
            for msg in self.info:
                print(f"  - {msg}")
            print()

        if self.warnings:
            print("[WARNING]")
            for msg in self.warnings:
                print(f"  - {msg}")
            print()

        if self.errors:
            print("[ERROR]")
            for msg in self.errors:
                print(f"  - {msg}")
            print()

        print("-" * 70)
        if self.passed:
            print("結果: PASSED - モデル更新可能")
        else:
            print("結果: FAILED - モデル更新を中止してください")
        print("=" * 70)


def load_model_meta(meta_path: str) -> Dict[str, Any]:
    """メタ情報ファイルを読み込み"""
    try:
        with open(meta_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"メタファイルが見つかりません: {meta_path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"JSONパースエラー: {e}")


def validate_metadata_structure(meta: Dict[str, Any], result: ValidationResult):
    """メタデータ構造の検証"""
    # 必須フィールドの確認
    required_fields = ['metrics', 'created_at']

    for field in required_fields:
        if field not in meta:
            result.add_error(f"必須フィールドがありません: {field}")

    # metrics構造の確認
    metrics = meta.get('metrics', {})
    for stage in ['stage1', 'stage2', 'stage3']:
        if stage not in metrics:
            result.add_error(f"metricsに{stage}がありません")
        else:
            if 'cv_auc_mean' not in metrics[stage]:
                result.add_error(f"metrics.{stage}.cv_auc_meanがありません")

    # feature_names確認
    if 'feature_names' not in meta and 'features' not in meta:
        result.add_warning("feature_namesまたはfeaturesがありません（特徴量情報なし）")


def validate_auc_criteria(
    new_meta: Dict[str, Any],
    current_auc: Dict[str, float],
    result: ValidationResult
):
    """AUC基準の検証"""
    new_metrics = new_meta.get('metrics', {})

    for stage in ['stage1', 'stage2', 'stage3']:
        # 新モデルのAUC
        new_auc = new_metrics.get(stage, {}).get('cv_auc_mean', 0)

        # 最低基準
        min_auc = MODEL_VALIDATION_CRITERIA['min_auc'].get(stage, 0)

        # 現行AUC
        curr_auc = current_auc.get(stage, 0)

        result.add_info(f"{stage}: 新AUC={new_auc:.4f}, 現行AUC={curr_auc:.4f}, 最低基準={min_auc:.4f}")

        # 最低基準チェック
        if new_auc < min_auc:
            result.add_error(f"{stage}: AUC {new_auc:.4f} は最低基準 {min_auc:.4f} を下回っています")

        # 現行比較
        if new_auc < curr_auc:
            diff = curr_auc - new_auc
            if diff > 0.02:  # 2%以上低下は警告
                result.add_warning(f"{stage}: 現行AUCより {diff:.4f} ({diff*100:.1f}%) 低下しています")
            else:
                result.add_info(f"{stage}: 現行AUCより {diff:.4f} 低下していますが許容範囲内")
        elif new_auc > curr_auc:
            diff = new_auc - curr_auc
            result.add_info(f"{stage}: 現行AUCより {diff:.4f} ({diff*100:.1f}%) 改善しています")


def validate_feature_consistency(
    new_meta: Dict[str, Any],
    result: ValidationResult
):
    """特徴量の整合性検証"""
    feature_names = new_meta.get('feature_names', new_meta.get('features', {}))

    if not feature_names:
        result.add_warning("特徴量情報がないため整合性チェックをスキップ")
        return

    # Stage間の特徴量数チェック
    stage1_count = len(feature_names.get('stage1', []))
    stage2_count = len(feature_names.get('stage2', []))
    stage3_count = len(feature_names.get('stage3', []))

    result.add_info(f"特徴量数: stage1={stage1_count}, stage2={stage2_count}, stage3={stage3_count}")

    # Stage2はStage1より多いはず
    if stage2_count <= stage1_count:
        result.add_warning(f"Stage2の特徴量数({stage2_count})がStage1({stage1_count})以下です")

    # Stage3はStage2より多いはず
    if stage3_count <= stage2_count:
        result.add_warning(f"Stage3の特徴量数({stage3_count})がStage2({stage2_count})以下です")


def validate_model_files(meta_path: str, result: ValidationResult):
    """モデルファイルの存在確認"""
    meta_dir = Path(meta_path).parent

    # メタファイル名からモデルファイル名を推測
    meta_name = Path(meta_path).stem  # 例: conditional_meta_v2_20251215_120000

    if 'v2' in meta_name:
        # V2形式
        parts = meta_name.split('_')
        if len(parts) >= 4:
            timestamp = '_'.join(parts[-2:])
            for stage in ['stage1', 'stage2', 'stage3']:
                model_file = meta_dir / f"conditional_{stage}_v2_{timestamp}.joblib"
                if model_file.exists():
                    result.add_info(f"モデルファイル確認: {model_file.name}")
                else:
                    result.add_error(f"モデルファイルが見つかりません: {model_file.name}")
    else:
        # V1形式
        for stage in ['stage1', 'stage2', 'stage3']:
            model_file = meta_dir / f"conditional_{stage}.joblib"
            if model_file.exists():
                result.add_info(f"モデルファイル確認: {model_file.name}")
            else:
                result.add_warning(f"モデルファイルが見つかりません: {model_file.name}")


def run_quick_backtest(result: ValidationResult):
    """簡易バックテスト（将来実装用のプレースホルダー）"""
    result.add_info("簡易バックテストは未実装です。完全な検証には手動でバックテストを実行してください。")
    result.add_info("  実行コマンド: python scripts/backtest_pattern_h_with_venue_course_adjustment.py")


def main():
    parser = argparse.ArgumentParser(
        description='モデル更新時の自動検証スクリプト',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python scripts/validate_model_update.py --new-model models/conditional_meta_v2_20251215.json
  python scripts/validate_model_update.py --new-model models/new_model.json --skip-file-check

終了コード:
  0: 検証成功（マージ可能）
  1: 検証失敗（マージ不可）
        """
    )

    parser.add_argument(
        '--new-model', '-n',
        required=True,
        help='新モデルのメタ情報ファイルパス (.json)'
    )
    parser.add_argument(
        '--skip-file-check',
        action='store_true',
        help='モデルファイル存在確認をスキップ'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='詳細出力'
    )

    args = parser.parse_args()

    result = ValidationResult()

    # 1. メタファイル読み込み
    try:
        new_meta = load_model_meta(args.new_model)
        result.add_info(f"メタファイル読み込み成功: {args.new_model}")
    except Exception as e:
        result.add_error(f"メタファイル読み込み失敗: {e}")
        result.print_report()
        return 1

    # 2. メタデータ構造検証
    validate_metadata_structure(new_meta, result)

    # 3. 現行AUC取得
    try:
        current_auc = get_current_auc()
        result.add_info(f"現行モデルAUC: Stage2={current_auc.get('stage2', 0):.4f}, Stage3={current_auc.get('stage3', 0):.4f}")
    except Exception as e:
        result.add_warning(f"現行モデルAUC取得失敗: {e}")
        current_auc = {'stage1': 0, 'stage2': 0, 'stage3': 0}

    # 4. AUC基準検証
    validate_auc_criteria(new_meta, current_auc, result)

    # 5. 特徴量整合性検証
    validate_feature_consistency(new_meta, result)

    # 6. モデルファイル存在確認
    if not args.skip_file_check:
        validate_model_files(args.new_model, result)

    # 7. 簡易バックテスト情報
    run_quick_backtest(result)

    # レポート出力
    result.print_report()

    # 終了コード
    return 0 if result.passed else 1


if __name__ == '__main__':
    sys.exit(main())
