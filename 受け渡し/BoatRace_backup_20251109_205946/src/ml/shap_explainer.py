"""
SHAP による説明可能性解析モジュール
"""
import shap
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import matplotlib.pyplot as plt
import io
import base64


class SHAPExplainer:
    """SHAP 説明可能性解析クラス"""

    def __init__(self, model, feature_names: List[str]):
        """
        初期化

        Args:
            model: XGBoost Booster オブジェクト
            feature_names: 特徴量名リスト
        """
        self.model = model
        self.feature_names = feature_names
        self.explainer = shap.TreeExplainer(model)
        self.shap_values = None
        self.base_value = None

    def calculate_shap_values(
        self,
        X: pd.DataFrame,
        check_additivity: bool = False
    ) -> np.ndarray:
        """
        SHAP値を計算

        Args:
            X: 特徴量データ
            check_additivity: 加法性チェック

        Returns:
            np.ndarray: SHAP値
        """
        self.shap_values = self.explainer.shap_values(
            X,
            check_additivity=check_additivity
        )
        self.base_value = self.explainer.expected_value

        return self.shap_values

    def get_global_importance(
        self,
        X: pd.DataFrame,
        top_n: int = 20
    ) -> pd.DataFrame:
        """
        グローバル特徴量重要度を取得

        Args:
            X: 特徴量データ
            top_n: 上位N件

        Returns:
            pd.DataFrame: 重要度データ
        """
        if self.shap_values is None:
            self.calculate_shap_values(X)

        # 絶対値の平均を取得
        mean_abs_shap = np.abs(self.shap_values).mean(axis=0)

        df_importance = pd.DataFrame({
            'feature': self.feature_names,
            'importance': mean_abs_shap
        })

        df_importance = df_importance.sort_values('importance', ascending=False)

        return df_importance.head(top_n)

    def get_local_explanation(
        self,
        X: pd.DataFrame,
        index: int
    ) -> Dict:
        """
        個別データの説明を取得

        Args:
            X: 特徴量データ
            index: データインデックス

        Returns:
            Dict: 説明データ
        """
        if self.shap_values is None:
            self.calculate_shap_values(X)

        shap_values_single = self.shap_values[index]
        feature_values = X.iloc[index]

        # SHAP値と特徴量値をペア化
        explanation = []
        for fname, fval, sval in zip(self.feature_names, feature_values, shap_values_single):
            explanation.append({
                'feature': fname,
                'value': float(fval),
                'shap_value': float(sval)
            })

        # SHAP値の絶対値で降順ソート
        explanation = sorted(explanation, key=lambda x: abs(x['shap_value']), reverse=True)

        return {
            'base_value': float(self.base_value),
            'prediction': float(self.base_value + shap_values_single.sum()),
            'features': explanation
        }

    def plot_summary(
        self,
        X: pd.DataFrame,
        max_display: int = 20,
        plot_type: str = 'dot'
    ) -> bytes:
        """
        サマリープロットを生成（PNG バイト列）

        Args:
            X: 特徴量データ
            max_display: 表示する特徴量数
            plot_type: プロットタイプ ('dot', 'bar', 'violin')

        Returns:
            bytes: PNG画像データ
        """
        if self.shap_values is None:
            self.calculate_shap_values(X)

        plt.figure(figsize=(10, 8))
        shap.summary_plot(
            self.shap_values,
            X,
            max_display=max_display,
            plot_type=plot_type,
            show=False
        )

        # PNG に変換
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', dpi=100)
        plt.close()
        buf.seek(0)

        return buf.getvalue()

    def plot_dependence(
        self,
        X: pd.DataFrame,
        feature: str,
        interaction_feature: Optional[str] = None
    ) -> bytes:
        """
        依存性プロットを生成（PNG バイト列）

        Args:
            X: 特徴量データ
            feature: 対象特徴量
            interaction_feature: 交互作用特徴量

        Returns:
            bytes: PNG画像データ
        """
        if self.shap_values is None:
            self.calculate_shap_values(X)

        plt.figure(figsize=(10, 6))
        shap.dependence_plot(
            feature,
            self.shap_values,
            X,
            interaction_index=interaction_feature,
            show=False
        )

        # PNG に変換
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', dpi=100)
        plt.close()
        buf.seek(0)

        return buf.getvalue()

    def plot_waterfall(
        self,
        X: pd.DataFrame,
        index: int,
        max_display: int = 20
    ) -> bytes:
        """
        ウォーターフォールプロットを生成（個別説明）

        Args:
            X: 特徴量データ
            index: データインデックス
            max_display: 表示する特徴量数

        Returns:
            bytes: PNG画像データ
        """
        if self.shap_values is None:
            self.calculate_shap_values(X)

        plt.figure(figsize=(10, 8))

        # shap.Explanation オブジェクトを作成
        explanation = shap.Explanation(
            values=self.shap_values[index],
            base_values=self.base_value,
            data=X.iloc[index].values,
            feature_names=self.feature_names
        )

        shap.plots.waterfall(explanation, max_display=max_display, show=False)

        # PNG に変換
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', dpi=100)
        plt.close()
        buf.seek(0)

        return buf.getvalue()

    def get_feature_contributions(
        self,
        X: pd.DataFrame,
        top_n: int = 10
    ) -> pd.DataFrame:
        """
        各特徴量の寄与（正・負）を集計

        Args:
            X: 特徴量データ
            top_n: 上位N件

        Returns:
            pd.DataFrame: 寄与集計データ
        """
        if self.shap_values is None:
            self.calculate_shap_values(X)

        contributions = []

        for i, fname in enumerate(self.feature_names):
            shap_col = self.shap_values[:, i]

            contributions.append({
                'feature': fname,
                'mean_abs_shap': np.abs(shap_col).mean(),
                'mean_positive_shap': shap_col[shap_col > 0].mean() if (shap_col > 0).any() else 0,
                'mean_negative_shap': shap_col[shap_col < 0].mean() if (shap_col < 0).any() else 0,
                'positive_count': int((shap_col > 0).sum()),
                'negative_count': int((shap_col < 0).sum())
            })

        df_contrib = pd.DataFrame(contributions)
        df_contrib = df_contrib.sort_values('mean_abs_shap', ascending=False)

        return df_contrib.head(top_n)

    def explain_race(
        self,
        X: pd.DataFrame,
        race_indices: List[int]
    ) -> List[Dict]:
        """
        レース全体の説明を取得（全出走艇の説明）

        Args:
            X: 特徴量データ
            race_indices: レース内のデータインデックスリスト

        Returns:
            List[Dict]: 各艇の説明リスト
        """
        if self.shap_values is None:
            self.calculate_shap_values(X)

        explanations = []

        for idx in race_indices:
            exp = self.get_local_explanation(X, idx)
            explanations.append(exp)

        return explanations
