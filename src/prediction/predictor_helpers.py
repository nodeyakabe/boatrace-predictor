#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
予測器ヘルパー関数

予測器の生成を統一し、設定の一貫性を保証する軽量ヘルパー
機能フラグの変更時に修正箇所を1箇所に集約

Created: 2026-02-13
"""
from typing import Optional
from src.analysis.race_predictor import RacePredictor


def create_standard_predictor(
    use_cache: bool = True,
    db_path: str = "data/boatrace.db"
) -> RacePredictor:
    """
    標準設定のRacePredictorを生成

    本日の予測生成、Discord通知、UI表示など、通常の予測に使用

    Args:
        use_cache: キャッシュ使用フラグ（デフォルト: True）
        db_path: データベースパス（デフォルト: "data/boatrace.db"）

    Returns:
        RacePredictor: 標準設定の予測器

    Example:
        >>> predictor = create_standard_predictor()
        >>> prediction = predictor.predict(race_id, entries, conditions, beforeinfo, odds)
    """
    return RacePredictor(db_path=db_path, use_cache=use_cache)


def create_backtest_predictor(
    use_cache: bool = False,
    db_path: str = "data/boatrace.db"
) -> RacePredictor:
    """
    バックテスト用のRacePredictorを生成

    過去データの検証、条件評価など、再現性が重要な分析に使用
    キャッシュは無効化（各実行で同一結果を保証）

    Args:
        use_cache: キャッシュ使用フラグ（デフォルト: False）
        db_path: データベースパス（デフォルト: "data/boatrace.db"）

    Returns:
        RacePredictor: バックテスト用設定の予測器

    Example:
        >>> predictor = create_backtest_predictor()
        >>> # 過去データで検証
    """
    return RacePredictor(db_path=db_path, use_cache=use_cache)


def create_accuracy_predictor(
    use_cache: bool = True,
    db_path: str = "data/boatrace.db"
) -> RacePredictor:
    """
    精度検証用のRacePredictorを生成

    予測精度の測定、モデル評価など、統計的分析に使用

    Args:
        use_cache: キャッシュ使用フラグ（デフォルト: True）
        db_path: データベースパス（デフォルト: "data/boatrace.db"）

    Returns:
        RacePredictor: 精度検証用設定の予測器

    Example:
        >>> predictor = create_accuracy_predictor()
        >>> # 的中率を測定
    """
    return RacePredictor(db_path=db_path, use_cache=use_cache)


def create_value_predictor(
    use_cache: bool = True,
    db_path: str = "data/boatrace.db"
) -> RacePredictor:
    """
    価値分析用のRacePredictorを生成

    ROI計算、期待値分析など、収益性評価に使用

    Args:
        use_cache: キャッシュ使用フラグ（デフォルト: True）
        db_path: データベースパス（デフォルト: "data/boatrace.db"）

    Returns:
        RacePredictor: 価値分析用設定の予測器

    Example:
        >>> predictor = create_value_predictor()
        >>> # ROIを計算
    """
    return RacePredictor(db_path=db_path, use_cache=use_cache)


# 将来の拡張用（機能フラグが増えた場合）
def create_custom_predictor(
    use_cache: bool = True,
    db_path: str = "data/boatrace.db",
    **kwargs
) -> RacePredictor:
    """
    カスタム設定のRacePredictorを生成

    特殊な用途や実験的機能のテストに使用

    Args:
        use_cache: キャッシュ使用フラグ
        db_path: データベースパス（デフォルト: "data/boatrace.db"）
        **kwargs: 将来の拡張パラメータ

    Returns:
        RacePredictor: カスタム設定の予測器

    Example:
        >>> predictor = create_custom_predictor(use_cache=False)
    """
    # 現時点ではuse_cache, db_pathのみだが、将来的に他のパラメータを追加可能
    return RacePredictor(db_path=db_path, use_cache=use_cache, **kwargs)
