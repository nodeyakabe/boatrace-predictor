"""
オッズ整合性・校正モジュール
Phase 3.3: 予測確率とオッズの整合性検証
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from sklearn.isotonic import IsotonicRegression
from sklearn.calibration import calibration_curve
import warnings


class OddsCalibrator:
    """
    オッズベースの確率校正

    予測確率をオッズ逆算確率と整合させる
    """

    def __init__(self, takeout_rate: float = 0.25):
        """
        Args:
            takeout_rate: 控除率（25%がデフォルト）
        """
        self.takeout_rate = takeout_rate
        self.isotonic_model = None
        self.calibration_history = []

    def odds_to_implied_probability(self, odds: float) -> float:
        """
        オッズを暗黙確率に変換

        控除率を考慮した真の確率推定
        """
        # 控除率考慮前の確率
        raw_prob = 1.0 / odds

        # 控除率を考慮した補正
        # 実際の確率 = 表示確率 / (1 - 控除率)
        adjusted_prob = raw_prob * (1.0 - self.takeout_rate)

        return min(1.0, adjusted_prob)

    def calculate_overround(self, odds_list: List[float]) -> float:
        """
        オーバーラウンド（控除率の指標）を計算

        100%を超える分が控除率
        """
        total_implied = sum(1.0 / odds for odds in odds_list if odds > 0)
        return total_implied - 1.0

    def check_probability_consistency(
        self,
        predictions: Dict[str, float],
        odds_data: Dict[str, float]
    ) -> Dict:
        """
        予測確率とオッズの整合性を検証

        Args:
            predictions: 予測確率 {'1-2-3': 0.15, ...}
            odds_data: オッズ {'1-2-3': 8.5, ...}

        Returns:
            整合性チェック結果
        """
        results = {
            'total_pred_prob': 0.0,
            'total_implied_prob': 0.0,
            'overround': 0.0,
            'inconsistencies': [],
            'is_consistent': True
        }

        common_keys = set(predictions.keys()) & set(odds_data.keys())

        total_pred = sum(predictions.get(k, 0) for k in common_keys)
        results['total_pred_prob'] = total_pred

        # オーバーラウンド計算
        odds_list = [odds_data[k] for k in common_keys if odds_data[k] > 0]
        if odds_list:
            results['overround'] = self.calculate_overround(odds_list)

        # 各買い目の整合性チェック
        for combo in common_keys:
            pred_prob = predictions[combo]
            odds = odds_data[combo]
            implied_prob = self.odds_to_implied_probability(odds)

            # 予測とオッズの乖離
            divergence = abs(pred_prob - implied_prob) / implied_prob if implied_prob > 0 else 0

            if divergence > 0.5:  # 50%以上の乖離は異常
                results['inconsistencies'].append({
                    'combination': combo,
                    'pred_prob': pred_prob,
                    'implied_prob': implied_prob,
                    'divergence': divergence,
                    'type': 'high' if pred_prob > implied_prob else 'low'
                })

        # 総確率が100%を大きく超える/下回る場合
        if total_pred < 0.8 or total_pred > 1.2:
            results['is_consistent'] = False

        if len(results['inconsistencies']) > 5:
            results['is_consistent'] = False

        return results

    def calibrate_predictions(
        self,
        predictions: Dict[str, float],
        odds_data: Dict[str, float],
        method: str = 'blend'
    ) -> Dict[str, float]:
        """
        予測確率を校正

        Args:
            predictions: 予測確率
            odds_data: オッズ
            method: 校正方法
                - 'blend': 予測とオッズの加重平均
                - 'normalize': 正規化のみ
                - 'isotonic': Isotonic回帰（要事前学習）

        Returns:
            校正後の確率
        """
        if method == 'normalize':
            return self._normalize_predictions(predictions)
        elif method == 'blend':
            return self._blend_with_odds(predictions, odds_data)
        elif method == 'isotonic' and self.isotonic_model:
            return self._apply_isotonic(predictions)
        else:
            return self._normalize_predictions(predictions)

    def _normalize_predictions(
        self,
        predictions: Dict[str, float]
    ) -> Dict[str, float]:
        """確率を正規化（合計1.0に）"""
        total = sum(predictions.values())

        if total == 0:
            return predictions

        return {k: v / total for k, v in predictions.items()}

    def _blend_with_odds(
        self,
        predictions: Dict[str, float],
        odds_data: Dict[str, float],
        pred_weight: float = 0.7
    ) -> Dict[str, float]:
        """予測確率とオッズ逆算確率をブレンド"""
        blended = {}

        for combo, pred_prob in predictions.items():
            if combo in odds_data and odds_data[combo] > 0:
                implied_prob = self.odds_to_implied_probability(odds_data[combo])
                blended[combo] = pred_prob * pred_weight + implied_prob * (1 - pred_weight)
            else:
                blended[combo] = pred_prob

        # 正規化
        return self._normalize_predictions(blended)

    def _apply_isotonic(
        self,
        predictions: Dict[str, float]
    ) -> Dict[str, float]:
        """Isotonic回帰による校正"""
        if self.isotonic_model is None:
            return predictions

        combos = list(predictions.keys())
        probs = np.array([predictions[c] for c in combos])

        calibrated_probs = self.isotonic_model.predict(probs)

        result = dict(zip(combos, calibrated_probs))
        return self._normalize_predictions(result)

    def train_isotonic_calibrator(
        self,
        historical_predictions: np.ndarray,
        historical_actuals: np.ndarray
    ):
        """
        Isotonic回帰モデルを学習

        Args:
            historical_predictions: 過去の予測確率
            historical_actuals: 実際の結果（0/1）
        """
        self.isotonic_model = IsotonicRegression(
            out_of_bounds='clip',
            y_min=0.0,
            y_max=1.0
        )
        self.isotonic_model.fit(historical_predictions, historical_actuals)

    def calculate_calibration_error(
        self,
        predictions: np.ndarray,
        actuals: np.ndarray,
        n_bins: int = 10
    ) -> Dict:
        """
        校正誤差を計算

        Expected Calibration Error (ECE)
        """
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            prob_true, prob_pred = calibration_curve(
                actuals, predictions, n_bins=n_bins, strategy='uniform'
            )

        # ECE計算
        bin_sizes = np.histogram(predictions, bins=n_bins, range=(0, 1))[0]
        bin_sizes = bin_sizes[bin_sizes > 0]

        ece = 0.0
        for i in range(len(prob_true)):
            if i < len(bin_sizes):
                ece += (bin_sizes[i] / len(predictions)) * abs(prob_true[i] - prob_pred[i])

        # MCE (Maximum Calibration Error)
        mce = np.max(np.abs(prob_true - prob_pred)) if len(prob_true) > 0 else 0.0

        return {
            'ece': ece,
            'mce': mce,
            'prob_true': prob_true,
            'prob_pred': prob_pred,
            'n_bins': n_bins
        }

    def detect_arbitrage_opportunity(
        self,
        predictions: Dict[str, float],
        odds_data: Dict[str, float]
    ) -> List[Dict]:
        """
        アービトラージ機会を検出

        予測確率が高くオッズも高い（市場が過小評価）買い目
        """
        opportunities = []

        for combo, pred_prob in predictions.items():
            if combo not in odds_data:
                continue

            odds = odds_data[combo]
            implied_prob = self.odds_to_implied_probability(odds)

            # 予測 > オッズ暗黙 かつ EV > 0
            if pred_prob > implied_prob * 1.2:  # 20%以上の優位
                ev = pred_prob * odds - 1.0
                if ev > 0.1:  # 10%以上の期待値
                    opportunities.append({
                        'combination': combo,
                        'pred_prob': pred_prob,
                        'implied_prob': implied_prob,
                        'odds': odds,
                        'expected_value': ev,
                        'edge': (pred_prob - implied_prob) / implied_prob
                    })

        # 期待値順にソート
        opportunities.sort(key=lambda x: x['expected_value'], reverse=True)

        return opportunities


class ProbabilityAdjuster:
    """
    確率調整器

    様々な要因を考慮した確率の微調整
    """

    def __init__(self):
        self.adjustment_factors = {}

    def adjust_for_favorite_longshot_bias(
        self,
        predictions: Dict[str, float]
    ) -> Dict[str, float]:
        """
        本命-大穴バイアス補正

        一般的に本命は過大評価、大穴は過小評価される傾向
        """
        adjusted = {}

        # 確率でソート
        sorted_combos = sorted(predictions.items(), key=lambda x: x[1], reverse=True)

        for i, (combo, prob) in enumerate(sorted_combos):
            # 上位（本命）は少し下方修正
            if i < len(sorted_combos) * 0.1:  # 上位10%
                adjusted[combo] = prob * 0.95
            # 下位（大穴）は少し上方修正
            elif i > len(sorted_combos) * 0.9:  # 下位10%
                adjusted[combo] = prob * 1.05
            else:
                adjusted[combo] = prob

        # 正規化
        total = sum(adjusted.values())
        if total > 0:
            adjusted = {k: v / total for k, v in adjusted.items()}

        return adjusted

    def adjust_for_public_money(
        self,
        predictions: Dict[str, float],
        betting_percentages: Dict[str, float]
    ) -> Dict[str, float]:
        """
        パリミュチュエル方式の影響を考慮

        大衆が買っている買い目はオッズが下がる
        """
        if not betting_percentages:
            return predictions

        adjusted = {}

        for combo, prob in predictions.items():
            if combo in betting_percentages:
                bet_pct = betting_percentages[combo]

                # 大衆が過度に買っている場合は下方修正
                if bet_pct > prob * 1.5:
                    adjusted[combo] = prob * 0.9
                # 大衆が無視している場合は上方修正（機会）
                elif bet_pct < prob * 0.5:
                    adjusted[combo] = prob * 1.1
                else:
                    adjusted[combo] = prob
            else:
                adjusted[combo] = prob

        # 正規化
        total = sum(adjusted.values())
        if total > 0:
            adjusted = {k: v / total for k, v in adjusted.items()}

        return adjusted

    def smooth_probabilities(
        self,
        predictions: Dict[str, float],
        smoothing_factor: float = 0.01
    ) -> Dict[str, float]:
        """
        確率のスムージング

        ゼロ確率を避けて安定性を向上
        """
        n_combos = len(predictions)
        if n_combos == 0:
            return predictions

        # Laplace smoothing
        smoothed = {}
        total_original = sum(predictions.values())

        for combo, prob in predictions.items():
            smoothed[combo] = prob + smoothing_factor

        # 正規化
        total = sum(smoothed.values())
        if total > 0:
            smoothed = {k: v / total for k, v in smoothed.items()}

        return smoothed


class MarketEfficiencyAnalyzer:
    """
    市場効率性の分析

    オッズ市場がどれだけ効率的かを評価
    """

    def __init__(self):
        self.efficiency_history = []

    def calculate_market_efficiency(
        self,
        historical_odds: List[Dict[str, float]],
        historical_results: List[str]
    ) -> Dict:
        """
        市場効率性を計算

        完全効率市場では、オッズ逆算確率 ≈ 実際の的中率
        """
        if len(historical_odds) != len(historical_results):
            raise ValueError("オッズと結果のデータ数が一致しません")

        # 確率区間ごとの的中率
        bins = [0, 0.01, 0.05, 0.1, 0.15, 0.2, 0.3, 1.0]
        bin_hits = {i: [] for i in range(len(bins) - 1)}

        for odds_data, result in zip(historical_odds, historical_results):
            if result in odds_data:
                odds = odds_data[result]
                implied_prob = 1.0 / odds if odds > 0 else 0

                # 適切なビンに分類
                for i in range(len(bins) - 1):
                    if bins[i] <= implied_prob < bins[i + 1]:
                        bin_hits[i].append(1)
                        break

            # 外れた買い目も記録
            for combo, odds in odds_data.items():
                if combo != result and odds > 0:
                    implied_prob = 1.0 / odds
                    for i in range(len(bins) - 1):
                        if bins[i] <= implied_prob < bins[i + 1]:
                            bin_hits[i].append(0)
                            break

        # 各ビンの実際の的中率
        efficiency_scores = {}
        for i in range(len(bins) - 1):
            if bin_hits[i]:
                actual_hit_rate = np.mean(bin_hits[i])
                expected_mid = (bins[i] + bins[i + 1]) / 2

                efficiency_scores[f"{bins[i]:.2f}-{bins[i+1]:.2f}"] = {
                    'expected': expected_mid,
                    'actual': actual_hit_rate,
                    'efficiency': 1.0 - abs(actual_hit_rate - expected_mid) / expected_mid if expected_mid > 0 else 0,
                    'sample_size': len(bin_hits[i])
                }

        # 全体効率スコア
        total_efficiency = np.mean([
            v['efficiency'] for v in efficiency_scores.values()
            if v['sample_size'] > 10
        ]) if efficiency_scores else 0.0

        return {
            'overall_efficiency': total_efficiency,
            'bin_analysis': efficiency_scores,
            'interpretation': self._interpret_efficiency(total_efficiency)
        }

    def _interpret_efficiency(self, efficiency: float) -> str:
        """効率性スコアの解釈"""
        if efficiency > 0.9:
            return "非常に効率的な市場。優位性の発見は困難。"
        elif efficiency > 0.7:
            return "比較的効率的。一部に機会あり。"
        elif efficiency > 0.5:
            return "中程度の効率性。予測モデルの価値あり。"
        else:
            return "非効率的な市場。大きな機会が存在。"

    def detect_market_inefficiency(
        self,
        predictions: Dict[str, float],
        odds_data: Dict[str, float],
        threshold: float = 0.3
    ) -> List[Dict]:
        """
        市場の非効率性を検出

        予測とオッズが大きく乖離している買い目
        """
        inefficiencies = []

        for combo, pred_prob in predictions.items():
            if combo not in odds_data:
                continue

            odds = odds_data[combo]
            if odds <= 0:
                continue

            implied_prob = 1.0 / odds

            # 相対的な乖離
            relative_diff = abs(pred_prob - implied_prob) / implied_prob

            if relative_diff > threshold:
                inefficiencies.append({
                    'combination': combo,
                    'pred_prob': pred_prob,
                    'implied_prob': implied_prob,
                    'odds': odds,
                    'relative_diff': relative_diff,
                    'direction': 'undervalued' if pred_prob > implied_prob else 'overvalued'
                })

        inefficiencies.sort(key=lambda x: x['relative_diff'], reverse=True)
        return inefficiencies


if __name__ == "__main__":
    print("=" * 60)
    print("オッズ整合性・校正モジュール テスト")
    print("=" * 60)

    # オッズ校正器の初期化
    calibrator = OddsCalibrator(takeout_rate=0.25)

    # サンプルデータ
    predictions = {
        '1-2-3': 0.15,
        '1-3-2': 0.12,
        '2-1-3': 0.10,
        '1-2-4': 0.08,
        '2-3-1': 0.07,
        '3-1-2': 0.06,
    }

    odds_data = {
        '1-2-3': 8.5,
        '1-3-2': 12.3,
        '2-1-3': 15.8,
        '1-2-4': 18.2,
        '2-3-1': 22.5,
        '3-1-2': 28.0,
    }

    print("\n【オッズ→暗黙確率変換】")
    for combo, odds in odds_data.items():
        implied = calibrator.odds_to_implied_probability(odds)
        print(f"  {combo}: オッズ {odds:.1f} → 暗黙確率 {implied:.1%}")

    print("\n【整合性チェック】")
    consistency = calibrator.check_probability_consistency(predictions, odds_data)
    print(f"  総予測確率: {consistency['total_pred_prob']:.1%}")
    print(f"  オーバーラウンド: {consistency['overround']:.1%}")
    print(f"  整合性: {'OK' if consistency['is_consistent'] else 'NG'}")

    if consistency['inconsistencies']:
        print(f"  警告: {len(consistency['inconsistencies'])}件の乖離")
        for inc in consistency['inconsistencies'][:3]:
            print(f"    {inc['combination']}: 予測{inc['pred_prob']:.1%} vs 暗黙{inc['implied_prob']:.1%}")

    print("\n【確率校正】")
    calibrated = calibrator.calibrate_predictions(predictions, odds_data, method='blend')
    print("  正規化後の確率:")
    for combo in sorted(calibrated.keys(), key=lambda x: calibrated[x], reverse=True)[:5]:
        print(f"    {combo}: {predictions[combo]:.1%} → {calibrated[combo]:.1%}")

    print("\n【アービトラージ機会検出】")
    opportunities = calibrator.detect_arbitrage_opportunity(predictions, odds_data)
    if opportunities:
        for opp in opportunities[:3]:
            print(f"  {opp['combination']}:")
            print(f"    予測: {opp['pred_prob']:.1%}, 暗黙: {opp['implied_prob']:.1%}")
            print(f"    期待値: {opp['expected_value']:.1%}, エッジ: {opp['edge']:.1%}")
    else:
        print("  検出されませんでした")

    print("\n【確率調整】")
    adjuster = ProbabilityAdjuster()

    # 本命-大穴バイアス補正
    bias_adjusted = adjuster.adjust_for_favorite_longshot_bias(predictions)
    print("  本命-大穴バイアス補正:")
    for combo in sorted(predictions.keys(), key=lambda x: predictions[x], reverse=True)[:3]:
        print(f"    {combo}: {predictions[combo]:.1%} → {bias_adjusted[combo]:.1%}")

    # スムージング
    smoothed = adjuster.smooth_probabilities(predictions)
    print("  スムージング後:")
    total_smoothed = sum(smoothed.values())
    print(f"    総確率: {total_smoothed:.1%}")

    print("\n" + "=" * 60)
    print("テスト完了")
    print("=" * 60)
