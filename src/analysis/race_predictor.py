"""
レース予想スコアリングモジュール

コース別傾向 + 選手成績 + モーター性能を統合して、
総合予想スコアと買い目推奨を提供
"""

import logging
from typing import Dict, List, Tuple, Optional
from .statistics_calculator import StatisticsCalculator
from .racer_analyzer import RacerAnalyzer
from .motor_analyzer import MotorAnalyzer
from .kimarite_scorer import KimariteScorer
from .grade_scorer import GradeScorer
from .first_place_lock import FirstPlaceLockAnalyzer
from .weather_adjuster import WeatherAdjuster
from .tide_adjuster import TideAdjuster
from .exhibition_analyzer import ExhibitionAnalyzer
from .extended_scorer import ExtendedScorer
from .compound_buff_system import CompoundBuffSystem
from .beforeinfo_scorer import BeforeInfoScorer
from .dynamic_integration import DynamicIntegrator
from .before_safe_scorer import BeforeSafeScorer
from .safe_integrator import SafeIntegrator
from .entry_prediction_model import EntryPredictionModel
from .probability_calibrator import ProbabilityCalibrator
from .beforeinfo_flag_adjuster import BeforeInfoFlagAdjuster
from .top3_scorer import Top3Scorer
from .pattern_priority_optimizer import PatternPriorityOptimizer
from .negative_pattern_checker import NegativePatternChecker
from .venue_pattern_optimizer import VenuePatternOptimizer
from .scorers.odds_calibrator import OddsCalibrator
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))
from src.utils.pattern_cache import RaceDataCache
from src.utils.scoring_config import ScoringConfig
from src.utils.db_connection_pool import get_connection
from src.prediction.rule_based_engine import RuleBasedEngine
from config.feature_flags import is_feature_enabled
# from config.optimized_pattern_multipliers import get_optimized_multiplier  # アーカイブ削除（2025-12-22）
from config.presets.loader import get_pattern_multiplier, get_dynamic_weights_config
from src.analysis.scorers import PatternScorer, BEFORE_PATTERNS_1ST, BEFORE_PATTERNS_2ND, BEFORE_PATTERNS_3RD, BEFORE_PATTERNS_TOP3
# 階層的確率モデル（条件付き確率）
try:
    from src.prediction.hierarchical_predictor import HierarchicalPredictor
    HIERARCHICAL_MODEL_AVAILABLE = True
except ImportError:
    HIERARCHICAL_MODEL_AVAILABLE = False

# 2着専用スコアリングモデル（アプローチ2）
try:
    from src.ml.second_place_specialized_model import (
        SecondPlaceSpecializedScorer,
        SecondPlaceIntegrator
    )
    SECOND_PLACE_MODEL_AVAILABLE = True
except ImportError:
    SECOND_PLACE_MODEL_AVAILABLE = False

# 信頼度ベース予測（アプローチ1）
try:
    from src.ml.confidence_based_rank_predictor import (
        ConfidenceBasedRankPredictor,
        ConfidenceBasedIntegrator,
        calculate_market_probs_from_odds
    )
    CONFIDENCE_BASED_MODEL_AVAILABLE = True
except ImportError:
    CONFIDENCE_BASED_MODEL_AVAILABLE = False

# ペアワイズ相対スコアリング（アプローチ3）
try:
    from src.ml.pairwise_rank_model import (
        PairwiseRankModel,
        PairwiseScoreIntegrator
    )
    PAIRWISE_MODEL_AVAILABLE = True
except ImportError:
    PAIRWISE_MODEL_AVAILABLE = False

# モンテカルロレースシミュレーション（アプローチ5）
try:
    from src.simulation.race_simulator import (
        MonteCarloRaceSimulator,
        SimulationScoreIntegrator
    )
    MONTE_CARLO_AVAILABLE = True
except ImportError:
    MONTE_CARLO_AVAILABLE = False

# P-3: 決まり手別展開予測
try:
    from src.prediction.kimarite_flow_predictor import KimariteFlowPredictor
    KIMARITE_FLOW_AVAILABLE = True
except ImportError:
    KIMARITE_FLOW_AVAILABLE = False

# P-6-2: まくりリスク評価
try:
    from src.prediction.makuri_risk_evaluator import MakuriRiskEvaluator
    MAKURI_RISK_AVAILABLE = True
except ImportError:
    MAKURI_RISK_AVAILABLE = False

# Phase3: ML コンセンサスフィルター（conditional_rank_v4）
try:
    from src.ml.conditional_rank_model import ConditionalRankModel as _ConditionalRankModel
    ML_CONSENSUS_MODEL_NAME = 'conditional_rank_v4b_20260413_160607'  # total_score除外・2025OOS検証済み
    CONDITIONAL_RANK_AVAILABLE = True
except ImportError:
    CONDITIONAL_RANK_AVAILABLE = False

from src.database.batch_data_loader import BatchDataLoader
from config.venue_characteristics import get_venue_adjustment, get_venue_course_adjustment
from config.settings import (
    get_dynamic_weights, get_venue_type, VENUE_IN1_RATES,
    HIGH_IN_VENUES, LOW_IN_VENUES, EXTENDED_SCORE_WEIGHTS,
    EXTENDED_SCORE_MAX, EXTENDED_SCORE_MIN
)
from config.venue_course_win_rates import get_venue_course_win_rate

# 予測戦略設定をロード
try:
    import yaml
    _PREDICTION_STRATEGY_PATH = Path(__file__).parent.parent.parent / 'config' / 'prediction_strategy.yaml'
    if _PREDICTION_STRATEGY_PATH.exists():
        with open(_PREDICTION_STRATEGY_PATH, 'r', encoding='utf-8') as f:
            PREDICTION_STRATEGY = yaml.safe_load(f)
    else:
        PREDICTION_STRATEGY = None
except Exception:
    PREDICTION_STRATEGY = None


# ==================================================
# BEFORE情報パターンボーナス定義
# ==================================================
# パターン定義はsrc/analysis/scorers/pattern_scorer.pyに移動
# BEFORE_PATTERNS_1ST, BEFORE_PATTERNS_2ND, BEFORE_PATTERNS_3RD, BEFORE_PATTERNS_TOP3
# はsrc.analysis.scorersからインポートされる


class RacePredictor:
    """レース予想クラス"""

    def __init__(self, db_path="data/boatrace.db", custom_weights: Dict[str, float] = None,
                 mode: Optional[str] = None, use_cache: bool = True):
        """
        レース予想クラスの初期化

        Args:
            db_path: データベースパス
            custom_weights: カスタム重み設定（指定時はmodeより優先）
            mode: 予測モード
                - 'accuracy': 的中率重視（コース重視）
                - 'value': 期待値重視（選手・モーター重視）
                - None: デフォルト設定
            use_cache: キャッシュを使用するかどうか
        """
        self.db_path = db_path
        self.mode = mode
        self.use_cache = use_cache

        # BatchDataLoaderの初期化（キャッシュ使用時のみ）
        self.batch_loader = BatchDataLoader(db_path) if use_cache else None

        # 各Analyzerにbatch_loaderを渡す
        self.stats_calc = StatisticsCalculator(db_path)
        self.racer_analyzer = RacerAnalyzer(db_path, batch_loader=self.batch_loader)
        self.motor_analyzer = MotorAnalyzer(db_path, batch_loader=self.batch_loader)
        self.kimarite_scorer = KimariteScorer(db_path, batch_loader=self.batch_loader)
        self.first_place_lock_analyzer = FirstPlaceLockAnalyzer()
        self.grade_scorer = GradeScorer(db_path, batch_loader=self.batch_loader)
        self.rule_engine = RuleBasedEngine(db_path)
        self.weather_adjuster = WeatherAdjuster()
        self.tide_adjuster = TideAdjuster(db_path)
        self.exhibition_analyzer = ExhibitionAnalyzer()
        self.extended_scorer = ExtendedScorer(db_path, batch_loader=self.batch_loader)
        self.compound_buff_system = CompoundBuffSystem(db_path)
        self.beforeinfo_scorer = BeforeInfoScorer(db_path)
        self.dynamic_integrator = DynamicIntegrator(db_path)
        self.beforeinfo_flag_adjuster = BeforeInfoFlagAdjuster(db_path)

        # Phase 4: ST/展示タイム統合フラグを使用
        use_st_exhibition = is_feature_enabled('before_safe_st_exhibition')
        self.before_safe_scorer = BeforeSafeScorer(db_path, use_st_exhibition=use_st_exhibition)
        self.safe_integrator = SafeIntegrator(before_safe_weight=0.15)  # Phase 5: 15%に引き上げ
        self.entry_prediction_model = EntryPredictionModel(db_path)
        self.probability_calibrator = ProbabilityCalibrator(db_path)
        self.top3_scorer = Top3Scorer(db_path)
        self.pattern_optimizer = PatternPriorityOptimizer()
        self.negative_pattern_checker = NegativePatternChecker()
        self.venue_pattern_optimizer = VenuePatternOptimizer(db_path)
        self.odds_calibrator = OddsCalibrator(db_path, alpha=0.5, temperature=4.0)  # オッズ校正（α=0.5, T=4.0）
        self.race_data_cache = RaceDataCache()

        # 階層的確率モデル（条件付き確率ベースの三連単予測）
        self._hierarchical_batch_cache = {}  # predict_races_batch用バッチキャッシュ
        self.hierarchical_predictor = None
        if HIERARCHICAL_MODEL_AVAILABLE:
            try:
                self.hierarchical_predictor = HierarchicalPredictor(db_path)
            except Exception as e:
                print(f"階層的予測モデル初期化エラー: {e}")

        # Phase3: ML コンセンサスフィルター（conditional_rank_v4）
        self._ml_consensus_model = None
        if CONDITIONAL_RANK_AVAILABLE and is_feature_enabled('ml_consensus_filter'):
            try:
                self._ml_consensus_model = _ConditionalRankModel()
                self._ml_consensus_model.load(ML_CONSENSUS_MODEL_NAME)
                print(f"ML コンセンサスモデル読み込み完了: {ML_CONSENSUS_MODEL_NAME}")
            except Exception as e:
                print(f"ML コンセンサスモデル初期化エラー: {e}")
                self._ml_consensus_model = None

        # 2着専用スコアリングモデル（アプローチ2: 差し・まくり差し特化）
        self.second_place_scorer = None
        self.second_place_integrator = None
        if SECOND_PLACE_MODEL_AVAILABLE and is_feature_enabled('second_place_specialized'):
            try:
                self.second_place_scorer = SecondPlaceSpecializedScorer(
                    model_dir='models',
                    db_path=db_path
                )
                # モデルが存在すれば読み込み
                import os
                model_path = os.path.join('models', 'second_place_specialized.txt')
                if os.path.exists(model_path):
                    self.second_place_scorer.load('second_place_specialized')
                    self.second_place_integrator = SecondPlaceIntegrator(
                        specialized_scorer=self.second_place_scorer,
                        integration_weight=0.5  # 専用モデルの重み
                    )
            except Exception as e:
                print(f"2着専用モデル初期化エラー: {e}")

        # 信頼度ベース予測（アプローチ1: 信頼度に応じた戦略切り替え）
        self.confidence_based_predictor = None
        self.confidence_based_integrator = None
        if CONFIDENCE_BASED_MODEL_AVAILABLE and is_feature_enabled('confidence_based_switching'):
            try:
                self.confidence_based_predictor = ConfidenceBasedRankPredictor(
                    high_threshold=0.7,
                    medium_threshold=0.5
                )
                self.confidence_based_integrator = ConfidenceBasedIntegrator(
                    predictor=self.confidence_based_predictor,
                    enable_logging=False
                )
            except Exception as e:
                print(f"信頼度ベース予測器初期化エラー: {e}")

        # ペアワイズ相対スコアリング（アプローチ3: 艇間の直接対決スコア）
        self.pairwise_model = None
        self.pairwise_integrator = None
        if PAIRWISE_MODEL_AVAILABLE and is_feature_enabled('pairwise_scoring'):
            try:
                self.pairwise_model = PairwiseRankModel(
                    model_dir='models',
                    db_path=db_path
                )
                # モデルが存在すれば読み込み
                import os
                model_path = os.path.join('models', 'pairwise_rank.txt')
                if os.path.exists(model_path):
                    self.pairwise_model.load('pairwise_rank')
                    self.pairwise_integrator = PairwiseScoreIntegrator(
                        pairwise_model=self.pairwise_model,
                        integration_weight=0.15  # ペアワイズモデルの重み（AUC=0.735相当、過大混合を防ぐため0.5→0.15）
                    )
            except Exception as e:
                print(f"ペアワイズモデル初期化エラー: {e}")

        # モンテカルロレースシミュレーション（アプローチ5: 確率的シミュレーション）
        self.monte_carlo_integrator = None
        if MONTE_CARLO_AVAILABLE and is_feature_enabled('monte_carlo_simulation'):
            try:
                self.monte_carlo_integrator = SimulationScoreIntegrator(
                    n_simulations=5000,  # 実行速度と精度のバランス
                    integration_weight=0.3,  # シミュレーションの影響度
                    use_for_rank23=True  # 2着・3着予測に使用
                )
            except Exception as e:
                print(f"モンテカルロシミュレーター初期化エラー: {e}")

        # P-3: 決まり手別展開予測（2025-12-20追加）
        self.kimarite_flow_predictor = None
        if KIMARITE_FLOW_AVAILABLE and is_feature_enabled('kimarite_flow_prediction'):
            try:
                self.kimarite_flow_predictor = KimariteFlowPredictor(db_path)
            except Exception as e:
                print(f"決まり手別展開予測初期化エラー: {e}")

        # P-6-2: まくりリスク評価（2025-12-20追加）
        self.makuri_risk_evaluator = None
        if MAKURI_RISK_AVAILABLE and is_feature_enabled('makuri_risk_adjustment'):
            try:
                self.makuri_risk_evaluator = MakuriRiskEvaluator(db_path)
            except Exception as e:
                print(f"まくりリスク評価初期化エラー: {e}")

        # 重み設定をロード（優先順位: custom_weights > mode > default）
        if custom_weights:
            self.weights = custom_weights
        elif mode:
            config = ScoringConfig.for_mode(mode)
            self.weights = config.load_weights()
        else:
            config = ScoringConfig()
            self.weights = config.load_weights()

        # デフォルトの重み設定（古い設定ファイルとの互換性）
        if 'kimarite_weight' not in self.weights:
            self.weights['kimarite_weight'] = 5.0
        if 'grade_weight' not in self.weights:
            self.weights['grade_weight'] = 5.0

        # 重みの合計が100になるように検証
        total_weight = sum(self.weights.values())
        if abs(total_weight - 100.0) > 0.1:
            # 警告をログに出力（100でない場合も動作は継続）
            import logging
            logging.warning(f"重みの合計が100ではありません: {total_weight}")

    # ========================================
    # 動的重み調整（回収率改善のため）
    # ========================================
    # 注: 会場分類は config/settings.py から読み込み

    # モーター差が極端に出る会場（足が勝負を左右する）
    # 唐津(23)、福岡(22)、徳山(18) - 海水で波が高く、足の差が出やすい
    HIGH_MOTOR_VENUES = ['23', '22', '18', '21']  # 唐津、福岡、徳山、芦屋

    # インコースが有利な会場
    HIGH_IN_VENUES = HIGH_IN_VENUES  # config.settingsからインポート

    # インコースが不利な会場（アウト勢が強い）
    LOW_IN_VENUES = LOW_IN_VENUES  # config.settingsからインポート

    def _adjust_weights_dynamically(
        self,
        venue_code: str,
        race_grade: str,
        data_quality: float
    ) -> Dict[str, float]:
        """
        会場・グレード・データ充実度に応じて重みを動的に調整

        2024年11月27日更新: config/settings.pyの動的配点設定を使用

        Args:
            venue_code: 会場コード
            race_grade: レースグレード（SG, G1, G2, G3, 一般）
            data_quality: データ充実度（0-100）

        Returns:
            調整後の重み辞書
        """
        # settings.pyの動的配点を基にする
        dynamic_weights = get_dynamic_weights(venue_code)
        venue_type = get_venue_type(venue_code)

        # 基本重みを初期化
        weights = {
            'course_weight': dynamic_weights['course'],
            'racer_weight': dynamic_weights['racer'],
            'motor_weight': dynamic_weights['motor'],
            'rank_weight': dynamic_weights['rank'],
            'kimarite_weight': self.weights.get('kimarite_weight', 5.0),
            'grade_weight': self.weights.get('grade_weight', 5.0),
        }

        # === モーター差が極端に出る会場 ===
        # ★ 最優先で処理（唐津/福岡/徳山はモーターが勝負を決める）
        if venue_code in self.HIGH_MOTOR_VENUES:
            # モーター重み +8〜10、コース重み -5
            weights['motor_weight'] = weights.get('motor_weight', 20) + 8
            weights['course_weight'] = weights.get('course_weight', 35) - 5
            weights['kimarite_weight'] = weights.get('kimarite_weight', 5) + 2

        # === 会場別調整（イン有利/不利） ===
        elif venue_code in self.HIGH_IN_VENUES:
            # インが強い会場: コース重視、モーター軽視
            weights['course_weight'] = weights.get('course_weight', 35) + 3
            weights['motor_weight'] = weights.get('motor_weight', 20) - 2
            weights['racer_weight'] = weights.get('racer_weight', 35) - 1

        elif venue_code in self.LOW_IN_VENUES:
            # インが弱い会場: モーター・選手重視、コース軽視
            weights['course_weight'] = weights.get('course_weight', 35) - 5
            weights['motor_weight'] = weights.get('motor_weight', 20) + 4
            weights['racer_weight'] = weights.get('racer_weight', 35) + 2

        # === グレード別調整 ===
        if race_grade in ['SG', 'G1']:
            # 重賞レース: グレード適性・選手実力重視
            weights['grade_weight'] = weights.get('grade_weight', 5) + 3
            weights['racer_weight'] = weights.get('racer_weight', 35) + 2
            weights['kimarite_weight'] = weights.get('kimarite_weight', 5) - 3
            weights['motor_weight'] = weights.get('motor_weight', 20) - 2

        elif race_grade in ['G2', 'G3']:
            # 準重賞: グレード適性をやや重視
            weights['grade_weight'] = weights.get('grade_weight', 5) + 2
            weights['kimarite_weight'] = weights.get('kimarite_weight', 5) - 2

        # === データ充実度による調整 ===
        if data_quality < 50:
            # データ不足時: モーター重視（選手データが信頼できない）
            weights['motor_weight'] = weights.get('motor_weight', 20) + 3
            weights['racer_weight'] = weights.get('racer_weight', 35) - 3

        # 重みの合計を100に正規化
        total = sum(weights.values())
        if total > 0 and abs(total - 100.0) > 0.1:
            factor = 100.0 / total
            for key in weights:
                weights[key] = weights[key] * factor

        return weights

    def _get_venue_info(self, venue_code: str) -> Dict:
        """
        会場情報を取得

        Args:
            venue_code: 会場コード

        Returns:
            {
                'type': 会場タイプ（solid/chaotic/normal）,
                'in1_rate': 1コース勝率,
                'is_high_in': 堅い会場か,
                'is_low_in': 荒れ会場か
            }
        """
        return {
            'type': get_venue_type(venue_code),
            'in1_rate': VENUE_IN1_RATES.get(venue_code, 57.0),
            'is_high_in': venue_code in HIGH_IN_VENUES,
            'is_low_in': venue_code in LOW_IN_VENUES,
        }

    def _calculate_data_quality(self, racer_analyses: List[Dict], motor_analyses: List[Dict]) -> float:
        """
        レース全体のデータ充実度を計算

        Args:
            racer_analyses: 選手分析データリスト
            motor_analyses: モーター分析データリスト

        Returns:
            データ充実度（0-100）
        """
        if not racer_analyses or not motor_analyses:
            return 0.0

        total_quality = 0.0

        for racer, motor in zip(racer_analyses, motor_analyses):
            # 選手データの充実度
            racer_races = racer.get('overall_stats', {}).get('total_races', 0)
            racer_quality = min(racer_races / 50.0, 1.0) * 50  # 50レースで満点

            # モーターデータの充実度
            motor_races = motor.get('motor_stats', {}).get('total_races', 0)
            motor_quality = min(motor_races / 30.0, 1.0) * 50  # 30レースで満点

            total_quality += (racer_quality + motor_quality) / 6  # 6艇で平均

        return total_quality

    # ========================================
    # コーススコア計算
    # ========================================

    # 全国平均コース別勝率（正規化の基準）
    NATIONAL_AVG_WIN_RATES = {
        1: 0.55,  # 1コース: 約55%
        2: 0.14,  # 2コース: 約14%
        3: 0.12,  # 3コース: 約12%
        4: 0.10,  # 4コース: 約10%
        5: 0.06,  # 5コース: 約6%
        6: 0.03,  # 6コース: 約3%
    }

    # コース×ランク別 実績勝率（過去データより算出）
    # これがスコアリングの基盤となる
    COURSE_RANK_WIN_RATES = {
        # (コース, ランク): 勝率
        (1, 'A1'): 0.715,  (1, 'A2'): 0.611,  (1, 'B1'): 0.424,  (1, 'B2'): 0.303,
        (2, 'A1'): 0.195,  (2, 'A2'): 0.167,  (2, 'B1'): 0.096,  (2, 'B2'): 0.081,
        (3, 'A1'): 0.182,  (3, 'A2'): 0.162,  (3, 'B1'): 0.091,  (3, 'B2'): 0.066,
        (4, 'A1'): 0.138,  (4, 'A2'): 0.119,  (4, 'B1'): 0.076,  (4, 'B2'): 0.039,
        (5, 'A1'): 0.100,  (5, 'A2'): 0.073,  (5, 'B1'): 0.044,  (5, 'B2'): 0.020,
        (6, 'A1'): 0.066,  (6, 'A2'): 0.034,  (6, 'B1'): 0.017,  (6, 'B2'): 0.006,
    }

    def calculate_course_score(self, venue_code: str, course: int) -> float:
        """
        コース別スコアを計算（正規化版・インコース優位性強化）

        改善点:
        - 1コースの圧倒的優位性を反映（基礎点＋勝率反映）
        - コース間のスコア差を拡大
        - 会場特性を適切に反映

        Args:
            venue_code: 競艇場コード
            course: コース番号（1-6）

        Returns:
            コーススコア（0〜course_weight）
        """
        # コース別勝率を取得
        course_stats = self.stats_calc.calculate_course_stats(venue_code)
        national_avg = self.NATIONAL_AVG_WIN_RATES.get(course, 0.10)

        if course not in course_stats:
            win_rate = national_avg
        else:
            stats = course_stats[course]
            win_rate = stats['win_rate']

        max_score = self.weights['course_weight']

        # === コース別基礎点システム（強化版） ===
        # ボートレースの現実を反映: 1コースが圧倒的に有利
        # 基礎点を主体とし、勝率・会場特性は微調整に留める
        COURSE_BASE_POINTS = {
            1: 1.00,  # 1コースは基礎点100%（圧倒的有利）
            2: 0.40,  # 2コースは基礎点40%
            3: 0.35,  # 3コースは基礎点35%
            4: 0.30,  # 4コースは基礎点30%
            5: 0.25,  # 5コースは基礎点25%
            6: 0.20,  # 6コースは基礎点20%
        }

        base_factor = COURSE_BASE_POINTS.get(course, 0.30)

        # 1. コース基礎点（70%の配分）
        # コースによる固定の優位性を強く反映
        base_score = max_score * 0.70 * base_factor

        # 2. 実際の勝率スコア（20%の配分）
        # 全コース共通の基準で評価（勝率が高いほど高スコア）
        # 1コース55%が基準、それ以上で満点
        win_rate_factor = min(win_rate / 0.55, 1.0)
        win_rate_score = max_score * 0.20 * win_rate_factor

        # 3. 会場特性スコア（10%の配分）
        # 全国平均との比較（影響を縮小）
        if national_avg > 0:
            ratio = win_rate / national_avg
        else:
            ratio = 1.0

        # ratioを0.8〜1.2の範囲に制限し、0〜1にマッピング
        ratio_clamped = max(0.8, min(1.2, ratio))
        venue_factor = (ratio_clamped - 0.8) / 0.4  # 0〜1
        venue_score = max_score * 0.10 * venue_factor

        score = base_score + win_rate_score + venue_score

        # 会場・コース別補正（全コースに適用）
        if course == 1:
            venue_adjustment = get_venue_adjustment(venue_code)
            score = score * venue_adjustment

        # 全コースに会場別勝率補正を適用
        course_adjustment = get_venue_course_adjustment(venue_code, course)
        # 補正係数が極端にならないよう制限（0.85〜1.15）
        course_adjustment = max(0.85, min(1.15, course_adjustment))
        score = score * course_adjustment

        return score

    def calculate_course_rank_score(self, course: int, racer_rank: str, venue_code: str) -> float:
        """
        コース×ランクの実績勝率に基づくスコアを計算（会場別期待勝率テーブル使用）

        実際のデータから算出した勝率をベースに、
        コースと選手ランクの相互作用、会場特性を正確に反映。

        更新履歴:
        - 2025-12-15: 会場別期待勝率テーブル（config/venue_course_win_rates.py）を統合

        Args:
            course: コース番号（1-6）
            racer_rank: 選手ランク（A1, A2, B1, B2）
            venue_code: 競艇場コード

        Returns:
            コース×ランクスコア（0〜course_weight）
        """
        max_score = self.weights['course_weight']

        # 【新規】会場別期待勝率テーブルからコース勝率を取得（2020年以降の実績ベース）
        venue_course_win_rate = get_venue_course_win_rate(venue_code, course)

        # コース×ランクの実績勝率を取得（全国平均）
        national_rank_win_rate = self.COURSE_RANK_WIN_RATES.get(
            (course, racer_rank),
            self.NATIONAL_AVG_WIN_RATES.get(course, 0.10)  # フォールバック
        )

        # ランク補正係数を計算
        # 全国平均コース勝率に対するランク別勝率の比率
        national_course_avg = self.NATIONAL_AVG_WIN_RATES.get(course, 0.10)
        rank_multiplier = national_rank_win_rate / national_course_avg if national_course_avg > 0 else 1.0

        # 会場別コース勝率にランク補正を適用
        adjusted_win_rate = venue_course_win_rate * rank_multiplier

        # 会場特性による追加補正（±20%程度）
        # 注: get_venue_course_adjustmentは独自のボーナス調整なので継続使用
        course_adjustment = get_venue_course_adjustment(venue_code, course)
        course_adjustment = max(0.80, min(1.20, course_adjustment))

        adjusted_win_rate = adjusted_win_rate * course_adjustment

        # 勝率をスコアに変換
        # 最大勝率（徳山1コースA1: 約75%程度）で満点になるよう正規化
        MAX_WIN_RATE = 0.75
        score = (adjusted_win_rate / MAX_WIN_RATE) * max_score

        return min(score, max_score)

    # ========================================
    # レース単位での総合予想
    # ========================================

    def predict_race_by_key(self, race_date: str, venue_code: str, race_number: int) -> List[Dict]:
        """
        レースキー（日付・会場・レース番号）から予想を実行

        Args:
            race_date: レース日付 (例: '2024-10-01')
            venue_code: 競艇場コード (例: '20')
            race_number: レース番号 (例: 1)

        Returns:
            predict_race() と同じ形式の予測結果
        """
        import sqlite3
        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        # race_id を取得
        cursor.execute("""
            SELECT id
            FROM races
            WHERE race_date = ? AND venue_code = ? AND race_number = ?
        """, (race_date, venue_code, race_number))

        row = cursor.fetchone()
        cursor.close()

        if not row:
            return []

        race_id = row[0]
        return self.predict_race(race_id)

    def get_applied_rules_by_key(self, race_date: str, venue_code: str, race_number: int) -> List[Dict]:
        """
        レースキーから適用法則を取得

        Args:
            race_date: レース日付
            venue_code: 競艇場コード
            race_number: レース番号

        Returns:
            適用される法則のリスト
        """
        import sqlite3
        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id
            FROM races
            WHERE race_date = ? AND venue_code = ? AND race_number = ?
        """, (race_date, venue_code, race_number))

        row = cursor.fetchone()
        cursor.close()

        if not row:
            return []

        race_id = row[0]
        return self.get_applied_rules(race_id)

    def predict_race(self, race_id: int, use_beforeinfo: bool = True) -> List[Dict]:
        """
        レースの総合予想を実行

        Args:
            race_id: レースID
            use_beforeinfo: 直前情報を使用するか（True: before予測, False: advance予測）

        Returns:
            [
                {
                    'pit_number': 1,
                    'racer_name': '山田太郎',
                    'course_score': 35.2,
                    'racer_score': 28.5,
                    'motor_score': 15.3,
                    'total_score': 79.0,
                    'confidence': 'A',  # A, B, C, D, E
                    'rank_prediction': 1
                },
                ...
            ]
        """
        logger = logging.getLogger(__name__)

        # キャッシュチェック（Phase 2.5: 予測結果キャッシュ）
        cached_prediction = self.race_data_cache.get_prediction(race_id, use_beforeinfo)
        if cached_prediction is not None:
            logger.debug(f"Race {race_id}: 予測結果キャッシュヒット")
            return cached_prediction

        # レース情報取得（キャッシュ優先、フォールバックでDB）
        import sqlite3
        _use_batch_cache = self.batch_loader and self.batch_loader._cache_loaded

        if _use_batch_cache:
            # BatchDataLoader キャッシュからレース情報を取得（DBクエリなし）
            _cached_race = self.batch_loader.get_race_info(race_id)
            if not _cached_race:
                return []
            venue_code = _cached_race['venue_code']
            race_grade = _cached_race.get('race_grade') or '一般'
            race_date = _cached_race['race_date']
            race_time = _cached_race.get('race_time')
        else:
            conn = get_connection(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT venue_code, race_grade, race_date, race_time FROM races WHERE id = ?", (race_id,))
            race_info = cursor.fetchone()
            if not race_info:
                cursor.close()
                return []
            venue_code = race_info['venue_code']
            race_grade = race_info['race_grade'] if race_info['race_grade'] else '一般'
            race_date = race_info['race_date']
            race_time = race_info['race_time']
            cursor.close()

        # 拡張スコア用にエントリー情報を取得（キャッシュ優先、フォールバックでDB）
        entry_data = {}
        race_entries_for_matchup = []

        if _use_batch_cache:
            # BatchDataLoader キャッシュから取得（DBクエリなし）
            _cached_entries = self.batch_loader.get_race_entries(race_id)
            for e in _cached_entries:
                entry_dict = {
                    'pit_number': e['pit_number'],
                    'racer_number': e['racer_number'],
                    'racer_name': e.get('racer_name'),
                    'racer_rank': e.get('racer_rank'),
                    'f_count': e.get('f_count'),
                    'l_count': e.get('l_count'),
                    'motor_number': e.get('motor_number'),
                    'win_rate': e.get('win_rate'),
                    'avg_st': e.get('avg_st')
                }
                entry_data[e['pit_number']] = entry_dict
                race_entries_for_matchup.append(entry_dict)
        else:
            conn = get_connection(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT pit_number, racer_number, racer_name, racer_rank,
                       f_count, l_count, motor_number, win_rate, avg_st
                FROM entries
                WHERE race_id = ?
                ORDER BY pit_number
            """, (race_id,))
            entry_rows = cursor.fetchall()
            for row in entry_rows:
                entry_dict = {
                    'pit_number': row['pit_number'],
                    'racer_number': row['racer_number'],
                    'racer_name': row['racer_name'],
                    'racer_rank': row['racer_rank'],
                    'f_count': row['f_count'],
                    'l_count': row['l_count'],
                    'motor_number': row['motor_number'],
                    'win_rate': row['win_rate'],
                    'avg_st': row['avg_st']
                }
                entry_data[row['pit_number']] = entry_dict
                race_entries_for_matchup.append(entry_dict)
            cursor.close()

        # 天候データを取得（race_conditions優先、fallbackでweather）
        wind_speed = None
        wave_height = None
        wind_direction = None
        temperature = None
        water_temperature = None
        weather_condition = None

        # まず race_conditions から取得を試みる（キャッシュ優先、フォールバックでDB）
        if _use_batch_cache:
            weather_row = self.batch_loader.get_race_conditions(race_id)
        else:
            conn = get_connection(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT wind_speed, wave_height, wind_direction, temperature, water_temperature, weather
                FROM race_conditions WHERE race_id = ?
            """, (race_id,))
            weather_row = cursor.fetchone()
            cursor.close()

        if weather_row and weather_row['wind_speed'] is not None:
            wind_speed = weather_row['wind_speed']
            wave_height = weather_row['wave_height']
            wind_direction = weather_row['wind_direction']
            temperature = weather_row['temperature']
            water_temperature = weather_row['water_temperature']
            weather_condition = weather_row['weather']
        else:
            # fallback: weather テーブルから取得
            conn = get_connection(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT wind_speed, wave_height, wind_direction, temperature, water_temperature, weather_condition
                FROM weather
                WHERE venue_code = ? AND weather_date = ?
            """, (venue_code, race_date))
            weather_row = cursor.fetchone()
            if weather_row:
                wind_speed = weather_row['wind_speed']
                wave_height = weather_row['wave_height']
                wind_direction = weather_row['wind_direction']
                temperature = weather_row['temperature']
                water_temperature = weather_row['water_temperature']
                weather_condition = weather_row['weather_condition']
            cursor.close()

        # 選手・モーター分析
        racer_analyses = self.racer_analyzer.analyze_race_entries(race_id)
        motor_analyses = self.motor_analyzer.analyze_race_motors(race_id)

        # データ充実度を計算
        data_quality = self._calculate_data_quality(racer_analyses, motor_analyses)

        # 動的重み調整（会場・グレード・データ充実度に応じて）
        adjusted_weights = self._adjust_weights_dynamically(
            venue_code,
            race_grade,
            data_quality
        )

        # 各艇のスコア計算
        predictions = []

        for racer_analysis, motor_analysis in zip(racer_analyses, motor_analyses):
            pit_number = racer_analysis['pit_number']
            racer_name = racer_analysis['racer_name']
            racer_rank = racer_analysis.get('racer_rank', 'B2')  # ランクを取得

            # 進入コース（レース前の予測では枠番を使用）
            # 注: actual_courseはレース終了後にしか取得できないため、
            # 予測時は枠番をコースとして使用（ボートレースでは枠番=進入コースが多い）
            course = pit_number

            # === コース×ランクスコア（新方式） ===
            # 実績勝率に基づくスコア計算で、コースと選手ランクの相互作用を正確に反映
            original_course_weight = self.weights['course_weight']
            self.weights['course_weight'] = adjusted_weights['course_weight']
            course_score = self.calculate_course_rank_score(course, racer_rank, venue_code)
            self.weights['course_weight'] = original_course_weight  # 元に戻す

            # 選手スコア（ランクは既にcourse_scoreで反映されているので、
            # ここでは実績ベースの補正のみ）
            # racer_score_raw: 8-40点（直近5走強化後）→ racer_weight に正規化
            racer_score_raw = self.racer_analyzer.calculate_racer_score(racer_analysis)
            motor_score_raw = self.motor_analyzer.calculate_motor_score(motor_analysis)
            racer_score = racer_score_raw * (adjusted_weights['racer_weight'] / 40.0)
            motor_score = motor_score_raw * (adjusted_weights['motor_weight'] / 20.0)

            # 決まり手適性スコアを計算（動的調整後の重みを使用）
            kimarite_result = self.kimarite_scorer.calculate_kimarite_affinity_score(
                racer_analysis['racer_number'],
                venue_code,
                course,
                days=180,
                max_score=adjusted_weights['kimarite_weight']
            )
            kimarite_score = kimarite_result['score']

            # 決まり手×環境連動補正を適用
            # 潮位情報を取得（後続の_apply_tide_adjustmentと共通化）- 機能フラグで制御
            tide_phase = None
            if is_feature_enabled('tide_adjustment') and venue_code in self.tide_adjuster.TIDE_DATA_VENUES:
                from datetime import datetime
                try:
                    if race_time:
                        race_datetime = datetime.strptime(f"{race_date} {race_time}", "%Y-%m-%d %H:%M")
                    else:
                        race_datetime = datetime.strptime(f"{race_date} 12:00", "%Y-%m-%d %H:%M")
                    tide_data = self.tide_adjuster.get_tide_level(venue_code, race_datetime)
                    if tide_data:
                        tide_phase = tide_data.get('phase')
                except Exception:
                    pass

            kimarite_score = self.kimarite_scorer.apply_environment_adjustment(
                kimarite_score,
                kimarite_result,
                wind_speed,
                wave_height,
                wind_direction,
                tide_phase,
                venue_code,
                course
            )

            # グレード適性スコアを計算（動的調整後の重みを使用）
            grade_result = self.grade_scorer.calculate_grade_affinity_score(
                racer_analysis['racer_number'],
                race_grade,
                days=365,
                max_score=adjusted_weights['grade_weight']
            )
            grade_score = grade_result['score']

            # ========================================
            # 拡張スコア計算（新規追加）
            # ========================================
            extended_score_detail = None
            extended_score = 0.0
            EXTENDED_WEIGHT = 20.0  # 拡張スコアの総合重み（新要素追加により増加）

            if pit_number in entry_data:
                entry = entry_data[pit_number]
                extended_result = self.extended_scorer.get_comprehensive_score(
                    entry,
                    venue_code,
                    race_date,
                    race_entries_for_matchup,
                    race_id=race_id  # 展示タイム・チルト取得用
                )
                extended_score_detail = extended_result

                # 拡張スコアの構成要素（更新版）：
                # - 級別スコア: 0-10点
                # - F/Lペナルティ: -10～0点
                # - 節間成績: 0-5点
                # - 前走レベル: 0-5点
                # - 進入傾向: 0-5点（新規）
                # - 選手間相性: 0-5点
                # - モーター特性: 0-5点
                # - 平均ST: 0-10点
                # - 展示タイム: 0-8点（新規）
                # - チルト角度: 0-3点（新規）
                # - 直近成績: 0-8点（新規）
                # 最大合計: 76点（place_rate=5含む）、最小: -10点
                # これを EXTENDED_WEIGHT (20点) に正規化

                raw_extended = extended_result['total_extended_score']
                max_possible = extended_result.get('max_possible_score', 76)
                # -10～76 を 0～20 に正規化
                normalized_extended = ((raw_extended + 10) / (max_possible + 10)) * EXTENDED_WEIGHT
                extended_score = max(0, min(EXTENDED_WEIGHT, normalized_extended))

            # 総合スコア計算（拡張スコアを含む）
            raw_total = (
                course_score + racer_score + motor_score +
                kimarite_score + grade_score + extended_score
            )

            # スコアを0-100範囲に正規化（動的調整後の重みを使用）
            # 最大可能スコア = 既存スコア + 拡張スコア
            max_possible_score = (
                adjusted_weights['course_weight'] +
                adjusted_weights['racer_weight'] +
                adjusted_weights['motor_weight'] +
                adjusted_weights['kimarite_weight'] +
                adjusted_weights['grade_weight'] +
                EXTENDED_WEIGHT
            )
            if max_possible_score > 0:
                total_score = (raw_total / max_possible_score) * 100.0
            else:
                total_score = raw_total

            # ========================================
            # 複合条件バフを計算・適用
            # ========================================
            compound_buff_result = self.compound_buff_system.calculate_compound_buff(
                venue_code=venue_code,
                course=course,
                racer_analysis=racer_analysis,
                motor_analysis=motor_analysis,
                tide_phase=tide_phase,
                wind_speed=wind_speed,
                wind_direction=wind_direction,
                wave_height=wave_height,
                kimarite_result=kimarite_result,
                max_total_buff=15.0,  # 最大15点のバフ/デバフ
                race_id=race_id,
                pit_number=pit_number
            )
            compound_buff = compound_buff_result['total_buff']

            # スコアにバフを適用（0-100範囲を維持）
            total_score = max(0.0, min(100.0, total_score + compound_buff))

            # 信頼度判定（A-E）
            confidence = self._calculate_confidence(total_score, racer_analysis, motor_analysis)

            # 各選手のデータ充実度を計算
            racer_races = racer_analysis.get('overall_stats', {}).get('total_races', 0)
            racer_quality = min(racer_races / 50.0, 1.0) * 50  # 50レースで50点
            motor_races = motor_analysis.get('motor_stats', {}).get('total_races', 0)
            motor_quality = min(motor_races / 30.0, 1.0) * 50  # 30レースで50点
            data_completeness_score = racer_quality + motor_quality  # 0-100

            prediction_entry = {
                'pit_number': pit_number,
                'racer_name': racer_name,
                'racer_number': racer_analysis['racer_number'],
                'motor_number': motor_analysis['motor_number'],
                'boat_number': motor_analysis['boat_number'],
                'course_score': round(course_score, 1),
                'racer_score': round(racer_score, 1),
                'motor_score': round(motor_score, 1),
                'kimarite_score': round(kimarite_score, 1),
                'grade_score': round(grade_score, 1),
                'extended_score': round(extended_score, 1),
                'compound_buff': round(compound_buff, 1),
                'total_score': round(total_score, 1),
                'confidence': confidence,
                'data_completeness_score': round(data_completeness_score, 1),
                # 詳細情報
                'kimarite_detail': kimarite_result,
                'grade_detail': grade_result,
                'compound_buff_detail': compound_buff_result,
            }

            # 拡張スコア詳細を追加（存在する場合）
            if extended_score_detail:
                prediction_entry['extended_detail'] = {
                    'class': extended_score_detail['class'],
                    'fl_penalty': extended_score_detail['fl_penalty'],
                    'capsizing_penalty': extended_score_detail.get('capsizing_penalty', {}),  # 転覆ペナルティ（新規）
                    'session': extended_score_detail['session'],
                    'prev_race': extended_score_detail['prev_race'],
                    'matchup': extended_score_detail['matchup'],
                    'motor_extended': extended_score_detail['motor'],
                    'course_prediction': extended_score_detail['course_prediction'],
                    'course_entry': extended_score_detail.get('course_entry', {}),  # 進入傾向（新規）
                    'start_timing': extended_score_detail.get('start_timing', {}),
                    'exhibition': extended_score_detail.get('exhibition', {}),  # 展示タイム（新規）
                    'tilt': extended_score_detail.get('tilt', {}),  # チルト角度（新規）
                    'chikusen_time': extended_score_detail.get('chikusen_time', {}),  # 直線タイム（新規）
                    'recent_form': extended_score_detail.get('recent_form', {}),  # 直近成績（新規）
                    'venue_affinity': extended_score_detail.get('venue_affinity', {}),  # 会場別勝率（新規）
                    'place_rate': extended_score_detail.get('place_rate', {})  # 連対率（新規）
                }

            predictions.append(prediction_entry)

        # 展示データ補正を適用
        # NOTE: ExtendedScorerで既に展示タイムスコアを加算しているため、
        # 重複加算を避けるためデフォルトで無効化（2025-12-15 バグ修正）
        if is_feature_enabled('legacy_exhibition_adjustment'):
            predictions = self._apply_exhibition_adjustment(
                predictions,
                race_id
            )

        # 法則ベース補正を適用
        predictions = self._apply_rule_based_adjustment(
            predictions,
            race_id,
            venue_code,
            racer_analyses
        )

        # 天候補正を適用（風速・波高・風向データがある場合）
        predictions = self._apply_weather_adjustment(
            predictions,
            venue_code,
            wind_speed,
            wave_height,
            wind_direction
        )

        # 潮位補正を適用（海水会場のみ）- 機能フラグで制御
        if is_feature_enabled('tide_adjustment'):
            predictions = self._apply_tide_adjustment(
                predictions,
                venue_code,
                race_date,
                race_time
            )

        # ========================================
        # 直前情報スコアリングと統合（FINAL_SCORE = PRE_SCORE * 0.6 + BEFORE_SCORE * 0.4）
        # use_beforeinfo=False の場合はスキップ（advance予測）
        # ========================================
        if use_beforeinfo:
            predictions = self._apply_beforeinfo_integration(
                predictions,
                race_id,
                venue_code
            )

        # ========================================
        # 進入予測モデルを適用（機能フラグで制御）
        # ========================================
        predictions = self._apply_entry_prediction(
            predictions,
            race_id,
            race_date
        )

        # ========================================
        # 確率キャリブレーション適用（機能フラグで制御）
        # ========================================
        predictions = self._apply_probability_calibration(predictions)

        # ========================================
        # オッズ校正適用（機能フラグで制御）
        # 1着予測: 市場確率とモデル確率の乖離を検出してスコアを補正
        # ========================================
        if is_feature_enabled('odds_calibration'):
            predictions = self.odds_calibrator.calibrate_predictions(predictions, race_id)

        # スコア順にソート（信頼度判定のため）
        predictions.sort(key=lambda x: x['total_score'], reverse=True)

        # ========================================
        # スコア差ベースの信頼度再計算（機能フラグで制御）
        # C,D予想精度向上: 混戦レースを適切に分類
        # ========================================
        if is_feature_enabled('score_gap_confidence'):
            predictions = self._recalculate_race_confidence(predictions)

        # ========================================
        # ML コンセンサスフィルター（Phase3: conditional_rank_v4）
        # MLがルールベースの1着予測に不同意なら信頼度を1段階下げる
        # ========================================
        if is_feature_enabled('ml_consensus_filter') and self._ml_consensus_model is not None:
            predictions = self._apply_ml_consensus_filter(race_id, predictions)

        # ========================================
        # 2着・3着オッズ校正適用（機能フラグで制御）
        # 市場の2着・3着条件付き確率とML予測を統合
        # 期待効果: 三連単的中率 +2.0pt
        # ========================================
        if is_feature_enabled('rank23_odds_calibration'):
            predictions = self.odds_calibrator.calibrate_rank23_predictions(
                predictions, race_id, alpha=0.3
            )

        # ========================================
        # 2着専用スコアリング適用（機能フラグで制御）
        # アプローチ2: 差し・まくり差し特化型特徴量
        # 期待効果: 2着的中率 +3pt
        # ========================================
        if (is_feature_enabled('second_place_specialized') and
            self.second_place_scorer is not None and
            self.second_place_scorer.model is not None):
            try:
                predictions = self._apply_second_place_specialized(
                    predictions, race_id
                )
            except Exception as e:
                logger.debug(f"Race {race_id}: 2着専用スコア適用エラー: {e}")

        # ========================================
        # 信頼度ベース戦略切り替え適用（機能フラグで制御）
        # アプローチ1: 1着予測の確信度に応じた2着・3着予測方法の切り替え
        # 期待効果: 2着・3着的中率の向上
        # ========================================
        if (is_feature_enabled('confidence_based_switching') and
            self.confidence_based_integrator is not None):
            try:
                predictions = self._apply_confidence_based_switching(
                    predictions, race_id
                )
            except Exception as e:
                logger.debug(f"Race {race_id}: 信頼度ベース戦略切り替えエラー: {e}")

        # ========================================
        # モンテカルロシミュレーション適用（機能フラグで制御）
        # アプローチ5: 確率的レース展開シミュレーションで順位分布を予測
        # 期待効果: 2着・3着的中率の向上（最高ポテンシャル）
        # ========================================
        if (is_feature_enabled('monte_carlo_simulation') and
            self.monte_carlo_integrator is not None):
            try:
                predictions = self._apply_monte_carlo_simulation(
                    predictions, race_id, wind_speed, wave_height, wind_direction
                )
            except Exception as e:
                logger.debug(f"Race {race_id}: モンテカルロシミュレーションエラー: {e}")

        # ========================================
        # P-3: 決まり手別展開予測によるスコア調整（機能フラグで制御）
        # 2025-12-20追加: 決まり手から2着・3着展開を予測
        # 期待効果: 2着・3着的中率の向上
        # ========================================
        if (is_feature_enabled('kimarite_flow_prediction') and
            self.kimarite_flow_predictor is not None):
            try:
                predictions = self._apply_kimarite_flow_prediction(
                    predictions, race_id
                )
            except Exception as e:
                logger.debug(f"Race {race_id}: 決まり手別展開予測エラー: {e}")

        # ========================================
        # P-6-2: まくりリスク評価によるスコア調整（機能フラグで制御）
        # 2025-12-20追加: 1コース敗北リスクを評価してスコア調整
        # 期待効果: まくり展開時の2着・3着精度向上
        # ========================================
        if (is_feature_enabled('makuri_risk_adjustment') and
            self.makuri_risk_evaluator is not None):
            try:
                predictions = self._apply_makuri_risk_adjustment(
                    predictions, race_id
                )
            except Exception as e:
                logger.debug(f"Race {race_id}: まくりリスク評価エラー: {e}")

        # ========================================
        # 三連対スコアを計算して追加（2着・3着予測の精度向上）
        # 信頼度Bレースのみに適用（固いレースを確実に的中させる戦略）
        # 信頼度C/Dは荒れレースも拾えるよう従来のスコアリングを維持
        # ========================================
        top_confidence = predictions[0]['confidence'] if predictions else 'E'
        if top_confidence == 'B':
            predictions = self._add_top3_scores(predictions, venue_code, race_date)

        # ========================================
        # ペアワイズ相対スコアリング適用（kimarite/makuri/top3処理の後）
        # アプローチ3: 艇間の直接対決スコアで順位予測
        # 期待効果: 2着・3着的中率の向上
        # ※ total_scoreが確定した後に適用することでintegrated_scoreが有効になる
        # ========================================
        if (is_feature_enabled('pairwise_scoring') and
            self.pairwise_integrator is not None):
            try:
                predictions = self._apply_pairwise_scoring(
                    predictions, race_id
                )
            except Exception as e:
                logger.debug(f"Race {race_id}: ペアワイズスコアリングエラー: {e}")

        # 再ソート（pairwise適用済みの場合は順序を維持、それ以外はtotal_score順）
        if not (is_feature_enabled('pairwise_scoring') and self.pairwise_integrator is not None):
            predictions.sort(key=lambda x: x['total_score'], reverse=True)

        # ========================================
        # 予測コース強制化（2025-12-16追加）
        # 非1コース予測の精度が低い問題への対策
        # ========================================
        predictions = self._apply_course_enforcement(predictions)

        # 順位予想を付与
        for rank, pred in enumerate(predictions, 1):
            pred['rank_prediction'] = rank

        # 階層的確率モデルによる三連単予測を追加（機能フラグとモデルがある場合のみ）
        if is_feature_enabled('hierarchical_predictor') and self.hierarchical_predictor is not None:
            try:
                # バッチキャッシュがある場合はそこから取得（predict_races_batch経由の呼び出し）
                _batch_cache = getattr(self, '_hierarchical_batch_cache', {})
                if race_id in _batch_cache:
                    hierarchical_result = _batch_cache[race_id]
                else:
                    hierarchical_result = self.hierarchical_predictor.predict_race(race_id)
                if 'error' not in hierarchical_result:
                    # 各予測に三連単確率情報を追加
                    rank_probs = hierarchical_result.get('rank_probs', {})
                    for pred in predictions:
                        pit = pred['pit_number']
                        if pit in rank_probs:
                            pred['hierarchical_1st_prob'] = round(rank_probs[pit].get(1, 0) * 100, 1)
                            pred['hierarchical_2nd_prob'] = round(rank_probs[pit].get(2, 0) * 100, 1)
                            pred['hierarchical_3rd_prob'] = round(rank_probs[pit].get(3, 0) * 100, 1)

                    # 上位三連単組み合わせを predictions に付与
                    top_trifecta = hierarchical_result.get('top_combinations', [])[:10]
                    # 最初の予測結果に三連単情報を追加
                    if predictions:
                        predictions[0]['trifecta_predictions'] = [
                            {'combination': comb, 'probability': round(prob * 100, 2)}
                            for comb, prob in top_trifecta
                        ]
            except Exception as e:
                # 階層的予測エラーは無視して従来の予測を返す
                pass

        # 予測結果をキャッシュに保存（Phase 2.5）
        self.race_data_cache.set_prediction(race_id, predictions, use_beforeinfo)
        logger.debug(f"Race {race_id}: 予測結果キャッシュ保存")

        # キャッシュ統計をログ出力（定期的に）
        cache_stats = self.race_data_cache.get_all_stats()
        total_requests = cache_stats['prediction']['hits'] + cache_stats['prediction']['misses']
        if total_requests > 0:
            logger.debug(
                f"キャッシュ統計: "
                f"BEFORE {cache_stats['before_info']['hit_rate']:.1%} | "
                f"予測 {cache_stats['prediction']['hit_rate']:.1%}"
            )

        return predictions

    def predict_races_batch(self, race_ids: List[int],
                            use_beforeinfo: bool = True) -> Dict[int, List[Dict]]:
        """
        複数レースの予測を一括処理（バッチ推論高速化版）

        1日分の全レースをまとめて処理し、以下の最適化を行う:
        - HierarchicalPredictor（LightGBM Stage1/2/3）の一括バッチ推論
        - 事前バッチ推論結果をキャッシュし、predict_race()内で再利用

        BatchDataLoaderが load_daily_data() で日次キャッシュ済みの前提。

        Args:
            race_ids: レースIDのリスト（同一日のレース群を想定）
            use_beforeinfo: 直前情報を使用するか

        Returns:
            {race_id: 予測結果リスト} の辞書
        """
        if not race_ids:
            return {}

        results = {}

        # ==== Phase 1: HierarchicalPredictor の一括バッチ推論 ====
        # predict_race() 内で呼ばれる hierarchical_predictor.predict_race() を
        # 事前にバッチ推論し、結果をキャッシュに保存しておく
        hierarchical_batch_results = {}
        if (self.hierarchical_predictor is not None and
                hasattr(self.hierarchical_predictor, 'predict_races_batch')):
            try:
                from config.feature_flags import is_feature_enabled as _ife
                if _ife('hierarchical_predictor'):
                    hierarchical_batch_results = self.hierarchical_predictor.predict_races_batch(race_ids)
            except Exception:
                pass

        # HierarchicalPredictor の結果をキャッシュに保存
        # predict_race() 内で hierarchical_predictor.predict_race() を呼ぶ代わりに
        # このキャッシュから取得する
        self._hierarchical_batch_cache = hierarchical_batch_results

        # ==== Phase 2: 各レースのスコアリング ====
        for race_id in race_ids:
            try:
                predictions = self.predict_race(race_id, use_beforeinfo=use_beforeinfo)
                results[race_id] = predictions
            except Exception:
                results[race_id] = []

        # キャッシュをクリア
        self._hierarchical_batch_cache = {}

        return results

    def _apply_rule_based_adjustment(
        self,
        predictions: List[Dict],
        race_id: int,
        venue_code: str,
        racer_analyses: List[Dict]
    ) -> List[Dict]:
        """
        法則ベースエンジンで予測確率を補正

        Args:
            predictions: 基本スコアによる予測結果
            race_id: レースID
            venue_code: 競艇場コード
            racer_analyses: 選手分析データ

        Returns:
            補正後の予測結果
        """
        # スコアを確率に変換（softmax）
        import numpy as np
        scores = np.array([p['total_score'] for p in predictions])

        # スコアが全て同じ場合は補正しない
        if np.std(scores) < 0.01:
            return predictions

        # 温度パラメータを使ったsoftmax（温度=10で緩やかな確率分布）
        temperature = 10.0
        exp_scores = np.exp(scores / temperature)
        base_probabilities = exp_scores / np.sum(exp_scores)

        # 基本確率を辞書形式に変換
        base_probs_dict = {
            p['pit_number']: float(base_probabilities[i])
            for i, p in enumerate(predictions)
        }

        # エントリー・コース情報を取得（キャッシュ優先）
        if self.batch_loader and self.batch_loader._cache_loaded:
            entries_data = [
                (e['pit_number'], e['racer_number'], e.get('racer_name', ''))
                for e in self.batch_loader.get_race_entries(race_id)
            ]
            _rd = self.batch_loader._cache.get('race_details', {}).get(race_id, {})
            course_data = {pit: data.get('actual_course') for pit, data in _rd.items()}
            _race_info = self.batch_loader.get_race_info(race_id)
            race_date = _race_info.get('race_date') if _race_info else None
        else:
            import sqlite3
            conn = get_connection(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT race_date FROM races WHERE id = ?", (race_id,))
            _race_date_row = cursor.fetchone()
            race_date = _race_date_row[0] if _race_date_row else None
            cursor.execute("""
                SELECT pit_number, racer_number, racer_name
                FROM entries WHERE race_id = ? ORDER BY pit_number
            """, (race_id,))
            entries_data = cursor.fetchall()
            cursor.execute("""
                SELECT pit_number, actual_course FROM race_details WHERE race_id = ?
            """, (race_id,))
            course_data = {row[0]: row[1] for row in cursor.fetchall()}
            cursor.close()

        # エントリー情報を構築
        entries = []
        for pit, racer_num, racer_name in entries_data:
            entries.append({
                'pit_number': pit,
                'racer_number': racer_num,
                'racer_name': racer_name,
                'actual_course': course_data.get(pit, pit)  # コース未確定ならピット番号
            })

        # 法則を適用
        race_info = {
            'venue_code': venue_code,
            'race_date': race_date
        }

        adjusted_probs = self.rule_engine.apply_rules(
            base_probs_dict,
            race_info,
            entries,
            damping_factor=0.5  # 法則の影響を調整（0.3は弱すぎ、0.7は強すぎ）
        )

        # 補正後の確率をスコアに反映（加算方式で影響を限定）
        # 法則補正の影響を最大±10点程度に抑える
        MAX_RULE_ADJUSTMENT = 10.0  # スコアへの最大影響

        for i, pred in enumerate(predictions):
            pit_number = pred['pit_number']
            original_score = pred['total_score']
            original_prob = base_probs_dict[pit_number]
            adjusted_prob = adjusted_probs[pit_number]

            # 確率の差分をスコアの補正値に変換
            # 確率差 ±0.1 (10%) → スコア補正 ±10点
            prob_diff = adjusted_prob - original_prob
            score_adjustment = prob_diff * 100.0  # 0.1 * 100 = 10点

            # 補正値を制限
            score_adjustment = max(-MAX_RULE_ADJUSTMENT,
                                  min(score_adjustment, MAX_RULE_ADJUSTMENT))

            # スコアを補正（加算方式）
            adjusted_score = original_score + score_adjustment

            # スコアを0-100範囲に制限
            adjusted_score = max(0.0, min(adjusted_score, 100.0))

            pred['total_score'] = round(adjusted_score, 1)
            pred['rule_adjustment'] = round(score_adjustment, 1)  # 実際の調整値

        return predictions

    def get_applied_rules(self, race_id: int) -> List[Dict]:
        """
        レースに適用される法則を取得

        Args:
            race_id: レースID

        Returns:
            適用される法則のリスト
        """
        # レース情報・風向を取得（キャッシュ優先）
        if self.batch_loader and self.batch_loader._cache_loaded:
            race_info = self.batch_loader.get_race_info(race_id)
            if not race_info:
                return []
            venue_code = race_info['venue_code']
            race_date = race_info['race_date']
            weather = self.batch_loader.get_race_conditions(race_id)
            wind_direction = weather['wind_direction'] if weather and weather.get('wind_direction') else ''
        else:
            import sqlite3
            conn = get_connection(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT venue_code, race_date FROM races WHERE id = ?",
                (race_id,)
            )
            race_row = cursor.fetchone()
            if not race_row:
                cursor.close()
                return []
            venue_code, race_date = race_row
            cursor.execute("""
                SELECT wind_direction FROM race_conditions WHERE race_id = ?
            """, (race_id,))
            wind_row = cursor.fetchone()
            wind_direction = wind_row[0] if wind_row and wind_row[0] else ''
            cursor.close()

        # 出走情報を取得（racer_rank, genderを含む・racersテーブルJOIN必要）
        import sqlite3
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT e.pit_number, e.racer_number, e.racer_name, e.racer_rank, rd.actual_course,
                   COALESCE(r.gender,
                   CASE WHEN e.racer_name LIKE '%子' OR e.racer_name LIKE '%美' OR e.racer_name LIKE '%香'
                        OR e.racer_name LIKE '%奈' OR e.racer_name LIKE '%恵' OR e.racer_name LIKE '%代'
                        THEN 'female' ELSE 'male' END) as gender
            FROM entries e
            LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
            LEFT JOIN racers r ON e.racer_number = r.racer_number
            WHERE e.race_id = ?
            ORDER BY e.pit_number
        """, (race_id,))
        entries_data = cursor.fetchall()
        cursor.close()

        # エントリー情報を構築
        entries = []
        for pit, racer_num, racer_name, racer_rank, course, gender in entries_data:
            # genderをルールエンジン用の形式に変換（female -> 女）
            gender_display = '女' if gender == 'female' else ''

            entries.append({
                'pit_number': pit,
                'racer_number': racer_num,
                'racer_name': racer_name,
                'racer_rank': racer_rank if racer_rank else '',
                'gender': gender_display,
                'actual_course': course if course else pit
            })

        # レース情報（風向を含む）
        race_info = {
            'venue_code': venue_code,
            'race_date': race_date,
            'wind_direction': wind_direction
        }

        # 法則エンジンから適用される法則を取得
        applied_rules = self.rule_engine.get_applied_rules(race_info, entries)

        return applied_rules

    def _calculate_confidence(self, total_score: float, racer_analysis: Dict, motor_analysis: Dict) -> str:
        """
        信頼度を判定（A-E）

        データ量に応じて段階的に信頼度上限を設定。
        データが豊富なほど高い信頼度を許可。

        Args:
            total_score: 総合スコア
            racer_analysis: 選手分析データ
            motor_analysis: モーター分析データ

        Returns:
            信頼度（'A', 'B', 'C', 'D', 'E'）
        """
        # データ量を多角的に評価
        racer_overall = racer_analysis['overall_stats']['total_races']
        racer_course = racer_analysis['course_stats']['total_races']
        racer_venue = racer_analysis['venue_stats']['total_races']
        motor_total = motor_analysis['motor_stats']['total_races']

        # データ充実度スコア（0-100点）
        data_quality = 0.0

        # 選手全国成績（0-40点）
        if racer_overall >= 100:
            data_quality += 40.0
        elif racer_overall >= 50:
            data_quality += 30.0
        elif racer_overall >= 20:
            data_quality += 20.0
        elif racer_overall >= 10:
            data_quality += 10.0
        else:
            data_quality += racer_overall  # 10未満は数値そのまま

        # 選手コース別成績（0-25点）
        if racer_course >= 15:
            data_quality += 25.0
        elif racer_course >= 10:
            data_quality += 20.0
        elif racer_course >= 5:
            data_quality += 15.0
        else:
            data_quality += racer_course * 2  # 5未満は×2

        # 選手当地成績（0-15点）
        if racer_venue >= 10:
            data_quality += 15.0
        elif racer_venue >= 5:
            data_quality += 10.0
        elif racer_venue >= 3:
            data_quality += 7.0
        else:
            data_quality += racer_venue * 2  # 3未満は×2

        # モーター成績（0-20点）
        if motor_total >= 30:
            data_quality += 20.0
        elif motor_total >= 20:
            data_quality += 15.0
        elif motor_total >= 10:
            data_quality += 10.0
        else:
            data_quality += motor_total * 0.5  # 10未満は×0.5

        # データ充実度に基づく信頼度上限
        if data_quality >= 80:
            max_confidence = 'A'  # 十分なデータ
        elif data_quality >= 60:
            max_confidence = 'B'  # やや十分
        elif data_quality >= 40:
            max_confidence = 'C'  # 標準的
        elif data_quality >= 20:
            max_confidence = 'D'  # 不足気味
        else:
            max_confidence = 'E'  # 大幅に不足

        # スコアに基づく判定
        # 信頼度Bを増やすため基準を緩和（70→65）
        if total_score >= 75:
            confidence = 'A'
        elif total_score >= 65:
            confidence = 'B'
        elif total_score >= 55:
            confidence = 'C'
        elif total_score >= 45:
            confidence = 'D'
        else:
            confidence = 'E'

        # NOTE: data_quality基準による上限制限は score_gap_confidence に置き換え済み
        return confidence

    def _recalculate_race_confidence(self, predictions: List[Dict]) -> List[Dict]:
        """
        レース全体の信頼度をスコア差ベースで再計算（改良版）

        従来: 各選手のスコアのみで信頼度を判定
        改良: 1位と2位のスコア差で「予測の確実性」を判定

        Args:
            predictions: ソート済みの予測リスト（スコア降順）

        Returns:
            信頼度が再計算された予測リスト
        """
        if len(predictions) < 2:
            return predictions

        # 上位2艇のスコア差を計算
        top1_score = predictions[0]['total_score']
        top2_score = predictions[1]['total_score']
        score_gap = top1_score - top2_score

        # 1コース予測かどうか（ボートレースでは1コースが圧倒的に有利）
        is_course1_prediction = predictions[0].get('pit_number', 0) == 1

        # スコア差ベースの信頼度判定
        # - スコア差が大きい = 予測が明確 = 高信頼度
        # - スコア差が小さい = 混戦 = 低信頼度
        if score_gap >= 15 and top1_score >= 70:
            race_confidence = 'A'  # 明確な本命（スコア差15点以上）
        elif score_gap >= 10 and top1_score >= 60:
            race_confidence = 'B'  # 本命優位（スコア差10-14点）
        elif score_gap >= 5 or (is_course1_prediction and top1_score >= 55):
            race_confidence = 'C'  # 混戦だが予測可能（スコア差5-9点）
        elif score_gap >= 2:
            race_confidence = 'D'  # 超混戦（スコア差2-4点）
        else:
            race_confidence = 'E'  # 予測困難（スコア差2点未満）

        # 1位選手の信頼度を更新（これがレース全体の信頼度として使用される）
        # 従来のスコアベース信頼度より低くなる場合のみ更新（安全側に倒す）
        confidence_order = {'A': 5, 'B': 4, 'C': 3, 'D': 2, 'E': 1}
        original_confidence = predictions[0]['confidence']

        if confidence_order[race_confidence] < confidence_order[original_confidence]:
            # スコア差ベースの方が低い → 混戦と判断
            predictions[0]['confidence'] = race_confidence
            predictions[0]['confidence_reason'] = f'score_gap:{score_gap:.1f}'
        else:
            predictions[0]['confidence_reason'] = 'original'

        return predictions

    def _get_ml_features_for_race(self, race_id: int):
        """
        MLコンセンサスフィルター用の特徴量をDBから取得。
        conditional_rank_v4 の feature_names と同一順序で返す。
        """
        import sqlite3
        import pandas as pd
        import numpy as np

        query = """
        SELECT
            e.pit_number,
            e.win_rate,
            e.second_rate,
            e.third_rate,
            e.local_win_rate,
            e.local_second_rate,
            e.motor_second_rate,
            e.boat_second_rate,
            e.avg_st,
            rd.exhibition_time,
            rd.st_time        as exhibition_st,
            rd.exhibition_course,
            rd.tilt_angle,
            rc.wind_speed,
            rc.wave_height,
            rc.temperature,
            rc.water_temperature,
            COALESCE(rp_b.total_score, rp_a.total_score) as total_score
        FROM entries e
        LEFT JOIN race_details rd
            ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
        LEFT JOIN race_conditions rc
            ON e.race_id = rc.race_id
        LEFT JOIN race_predictions rp_b
            ON e.race_id = rp_b.race_id
            AND rp_b.pit_number = e.pit_number
            AND rp_b.prediction_type = 'before'
        LEFT JOIN race_predictions rp_a
            ON e.race_id = rp_a.race_id
            AND rp_a.pit_number = e.pit_number
            AND rp_a.prediction_type = 'advance'
        WHERE e.race_id = ?
        ORDER BY e.pit_number
        """
        try:
            conn = sqlite3.connect(self.db_path)
            df = pd.read_sql_query(query, conn, params=(race_id,))
            conn.close()
            if len(df) != 6:
                return None
            # 欠損値を中央値で補完（簡易）
            numeric_cols = df.select_dtypes(include=[np.number]).columns
            for col in numeric_cols:
                if col != 'pit_number' and df[col].isnull().any():
                    df[col] = df[col].fillna(df[col].median())
            return df
        except Exception:
            return None

    def _apply_ml_consensus_filter(self, race_id: int, predictions: List[Dict]) -> List[Dict]:
        """
        MLコンセンサスフィルター:
        conditional_rank_v4 が予測1着と不同意なら信頼度を1段階下げる。
        """
        import numpy as np

        try:
            features = self._get_ml_features_for_race(race_id)
            if features is None or len(features) != 6:
                return predictions

            model = self._ml_consensus_model
            X_1st = features.drop(['pit_number'], axis=1, errors='ignore')
            for col in model.feature_names:
                if col not in X_1st.columns:
                    X_1st[col] = 0.0
            X_1st = X_1st[model.feature_names]

            first_probs = model.models['first'].predict_proba(X_1st)[:, 1]
            ml_first_pit = int(features.iloc[int(np.argmax(first_probs))]['pit_number'])
            rule_first_pit = int(predictions[0]['pit_number'])

            if ml_first_pit != rule_first_pit:
                # 不同意 → 信頼度を1段階下げる
                confidence_order = {'A': 5, 'B': 4, 'C': 3, 'D': 2, 'E': 1}
                order_to_conf = {5: 'A', 4: 'B', 3: 'C', 2: 'D', 1: 'E'}
                cur = predictions[0].get('confidence', 'C')
                new_level = max(1, confidence_order.get(cur, 3) - 1)
                predictions[0]['confidence'] = order_to_conf[new_level]
                predictions[0]['ml_consensus'] = False
                predictions[0]['ml_predicted_first'] = ml_first_pit
            else:
                predictions[0]['ml_consensus'] = True
        except Exception:
            pass

        return predictions

    # ========================================
    # 買い目推奨
    # ========================================

    def recommend_bets(self, predictions: List[Dict], bet_types: List[str] = None) -> Dict:
        """
        買い目を推奨

        Args:
            predictions: predict_race()の結果
            bet_types: 舟券種別リスト（['3tan', '3fuku', '2tan']など）

        Returns:
            {
                '3tan': [
                    {'combination': '1-2-3', 'confidence': 'A'},
                    {'combination': '1-2-4', 'confidence': 'B'},
                    ...
                ],
                '3fuku': [...],
                ...
            }
        """
        if bet_types is None:
            bet_types = ['3tan', '3fuku']

        recommendations = {}

        # 上位3艇を取得
        top3 = predictions[:3]
        top_numbers = [p['pit_number'] for p in top3]

        # 三連単
        if '3tan' in bet_types:
            recommendations['3tan'] = self._recommend_3tan(predictions, top_numbers)

        # 三連複
        if '3fuku' in bet_types:
            recommendations['3fuku'] = self._recommend_3fuku(predictions, top_numbers)

        # 二連単
        if '2tan' in bet_types:
            recommendations['2tan'] = self._recommend_2tan(predictions, top_numbers)

        # 二連複
        if '2fuku' in bet_types:
            recommendations['2fuku'] = self._recommend_2fuku(predictions, top_numbers)

        return recommendations

    def _recommend_3tan(self, predictions: List[Dict], top_numbers: List[int]) -> List[Dict]:
        """三連単の推奨買い目"""
        bets = []

        # 1位固定で2-3位を変動
        first = top_numbers[0]
        for second in top_numbers[1:]:
            for third in top_numbers:
                if third != first and third != second:
                    combination = f"{first}-{second}-{third}"
                    # 信頼度は1位の信頼度を継承
                    confidence = predictions[0]['confidence']
                    bets.append({
                        'combination': combination,
                        'confidence': confidence
                    })

        return bets[:5]  # 上位5点に絞る

    def _recommend_3fuku(self, predictions: List[Dict], top_numbers: List[int]) -> List[Dict]:
        """三連複の推奨買い目"""
        # 上位3艇のBOX
        combination = '-'.join(map(str, sorted(top_numbers)))
        confidence = predictions[0]['confidence']

        return [{
            'combination': combination,
            'confidence': confidence
        }]

    def _recommend_2tan(self, predictions: List[Dict], top_numbers: List[int]) -> List[Dict]:
        """二連単の推奨買い目"""
        bets = []

        # 1位-2位、1位-3位
        first = top_numbers[0]
        for second in top_numbers[1:3]:
            combination = f"{first}-{second}"
            confidence = predictions[0]['confidence']
            bets.append({
                'combination': combination,
                'confidence': confidence
            })

        return bets

    def _recommend_2fuku(self, predictions: List[Dict], top_numbers: List[int]) -> List[Dict]:
        """二連複の推奨買い目"""
        # 上位2艇
        combination = '-'.join(map(str, sorted(top_numbers[:2])))
        confidence = predictions[0]['confidence']

        return [{
            'combination': combination,
            'confidence': confidence
        }]

    def _apply_weather_adjustment(
        self,
        predictions: List[Dict],
        venue_code: str,
        wind_speed: Optional[float],
        wave_height: Optional[float],
        wind_direction: Optional[str] = None,
        weather_condition: Optional[str] = None
    ) -> List[Dict]:
        """
        天候に基づくスコア補正を適用

        強風時（6m以上）は1コースにペナルティ、外コースにボーナスを付与。
        風向による補正（向い風は1コース有利、追い風はまくり有利）。
        会場別の特性を考慮（常滑は強風の影響が特に大きい）。

        Args:
            predictions: 予測結果リスト
            venue_code: 会場コード
            wind_speed: 風速（m/s）
            wave_height: 波高（cm）
            wind_direction: 風向（16方位 例: 北、南西、など）

        Returns:
            天候補正後の予測結果
        """
        # 風速・波高・風向データがない場合は補正なし
        if wind_speed is None and wave_height is None and wind_direction is None:
            return predictions

        # 天候補正の最大影響を制限（過補正防止のため縮小）
        # 改善提案: 15→5 に縮小（回収率改善のため）
        MAX_WEATHER_ADJUSTMENT = 5.0  # スコアへの最大影響

        for pred in predictions:
            pit_number = pred['pit_number']
            original_score = pred['total_score']

            # 天候補正を計算（風向・天候条件も含む）
            adj_result = self.weather_adjuster.calculate_adjustment(
                venue_code,
                pit_number,  # pit_number = コース番号として使用
                wind_speed,
                wave_height,
                wind_direction,
                weather_condition  # NEW: 天候条件（晴/曇/雨など）
            )

            # 補正値を取得（パーセント → スコア補正値に変換）
            # adjustment は -0.3 ~ +0.05 の範囲
            adjustment_percent = adj_result['adjustment']
            score_adjustment = original_score * adjustment_percent

            # 補正値を制限
            score_adjustment = max(-MAX_WEATHER_ADJUSTMENT,
                                  min(score_adjustment, MAX_WEATHER_ADJUSTMENT))

            # スコアを補正
            adjusted_score = original_score + score_adjustment

            # スコアを0-100範囲に制限
            adjusted_score = max(0.0, min(adjusted_score, 100.0))

            pred['total_score'] = round(adjusted_score, 1)

            # 補正があった場合は情報を追加
            if adjustment_percent != 0:
                pred['weather_adjustment'] = round(score_adjustment, 1)
                pred['weather_reason'] = adj_result['reason']
                pred['wind_category'] = adj_result['wind_category']
                pred['wave_category'] = adj_result['wave_category']
                pred['wind_direction_category'] = adj_result['wind_direction_category']

        return predictions

    def _apply_tide_adjustment(
        self,
        predictions: List[Dict],
        venue_code: str,
        race_date: str,
        race_time: Optional[str]
    ) -> List[Dict]:
        """
        潮位に基づくスコア補正を適用

        満潮時は1コース有利、干潮時は荒れやすい。
        海水・汽水会場のみに適用。

        Args:
            predictions: 予測結果リスト
            venue_code: 会場コード
            race_date: レース日付（YYYY-MM-DD）
            race_time: レース時刻（HH:MM）

        Returns:
            潮位補正後の予測結果
        """
        from datetime import datetime

        # 海水会場でない場合は補正なし
        if venue_code not in self.tide_adjuster.SEAWATER_VENUES:
            return predictions

        # 潮位データがない会場は補正なし
        if venue_code not in self.tide_adjuster.TIDE_DATA_VENUES:
            return predictions

        # レース日時を構築
        race_datetime = None
        if race_date:
            try:
                if race_time:
                    race_datetime = datetime.strptime(f"{race_date} {race_time}", "%Y-%m-%d %H:%M")
                else:
                    # 時刻がない場合は12:00を仮定
                    race_datetime = datetime.strptime(f"{race_date} 12:00", "%Y-%m-%d %H:%M")
            except ValueError:
                pass

        if race_datetime is None:
            return predictions

        # 潮位データを取得
        tide_data = self.tide_adjuster.get_tide_level(venue_code, race_datetime)
        if tide_data is None:
            return predictions

        # 潮位補正の最大影響を制限
        MAX_TIDE_ADJUSTMENT = 5.0  # スコアへの最大影響

        for pred in predictions:
            pit_number = pred['pit_number']
            original_score = pred['total_score']

            # 潮位補正を計算
            adj_result = self.tide_adjuster.calculate_adjustment(
                venue_code,
                pit_number,
                tide_data=tide_data
            )

            # 補正値を取得（パーセント → スコア補正値に変換）
            adjustment_percent = adj_result['adjustment']
            if adjustment_percent != 0:
                score_adjustment = original_score * adjustment_percent

                # 補正値を制限
                score_adjustment = max(-MAX_TIDE_ADJUSTMENT,
                                      min(score_adjustment, MAX_TIDE_ADJUSTMENT))

                # スコアを補正
                adjusted_score = original_score + score_adjustment

                # スコアを0-100範囲に制限
                adjusted_score = max(0.0, min(adjusted_score, 100.0))

                pred['total_score'] = round(adjusted_score, 1)

                # 補正情報を追加
                pred['tide_adjustment'] = round(score_adjustment, 1)
                pred['tide_reason'] = adj_result['reason']
                pred['tide_phase'] = adj_result['tide_phase']

        return predictions

    def _apply_pattern_bonus(
        self,
        predictions: List[Dict],
        race_id: int
    ) -> List[Dict]:
        """
        BEFORE情報パターンボーナスを適用

        バックテスト検証済み（1000レース、2025年データ）:
        - 信頼度B: +9.5pt効果（65.3% vs 55.9%）
        - 信頼度C: +8.3pt効果（47.7% vs 39.4%）
        - 信頼度A: -6.5pt（逆効果のため適用しない）

        Args:
            predictions: 予測結果リスト（PRE_SCOREが格納されている）
            race_id: レースID

        Returns:
            パターンボーナス適用後の予測結果
        """
        logger = logging.getLogger(__name__)

        # 信頼度チェック: 信頼度A/Eではパターンを適用しない
        if predictions:
            top_confidence = predictions[0].get('confidence', 'C')

            if top_confidence in ['A', 'E']:
                # 信頼度Aは高精度なのでパターン不要、Eはデータ不足
                logger.info(f"Race {race_id}: パターンスキップ（信頼度{top_confidence}）")
                for pred in predictions:
                    pred['pre_score'] = round(pred['total_score'], 1)
                    pred['integration_mode'] = f'pattern_skipped_confidence_{top_confidence}'
                    pred['pattern_multiplier'] = 1.0
                    pred['matched_patterns'] = []
                return predictions

            # 信頼度Dは慎重モード（フィーチャーフラグで制御）
            if top_confidence == 'D':
                if not is_feature_enabled('apply_pattern_to_confidence_d'):
                    logger.info(f"Race {race_id}: パターンスキップ（信頼度D・フラグ無効）")
                    for pred in predictions:
                        pred['pre_score'] = round(pred['total_score'], 1)
                        pred['integration_mode'] = 'pattern_skipped_confidence_D'
                        pred['pattern_multiplier'] = 1.0
                        pred['matched_patterns'] = []
                    return predictions
                else:
                    logger.info(f"Race {race_id}: パターン適用（信頼度D・フラグ有効）")

        # 会場コードを取得（キャッシュ優先）
        if self.batch_loader and self.batch_loader._cache_loaded:
            race_info = self.batch_loader.get_race_info(race_id)
            venue_code = int(race_info['venue_code']) if race_info and race_info.get('venue_code') else None
        else:
            import sqlite3
            conn = get_connection(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT venue_code FROM races WHERE id = ?", (race_id,))
            venue_row = cursor.fetchone()
            venue_code = int(venue_row[0]) if venue_row and venue_row[0] else None
            cursor.close()

        # キャッシュから取得試行
        cached_before_info = self.race_data_cache.get_before_info(race_id)

        if cached_before_info is not None:
            before_data = cached_before_info
            logger.debug(f"Race {race_id}: BEFORE情報キャッシュヒット")
        elif self.batch_loader and self.batch_loader._cache_loaded:
            # BatchDataLoaderのキャッシュから取得
            _rd = self.batch_loader._cache.get('race_details', {}).get(race_id, {})
            before_data = [(pit, data.get('exhibition_time'), data.get('st_time'))
                           for pit, data in sorted(_rd.items())]
            if before_data and len(before_data) >= 6:
                self.race_data_cache.set_before_info(race_id, before_data)
                logger.debug(f"Race {race_id}: BEFORE情報バッチキャッシュから取得")
        else:
            # DBから取得
            import sqlite3
            conn = get_connection(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT pit_number, exhibition_time, st_time
                FROM race_details
                WHERE race_id = ?
                ORDER BY pit_number
            """, (race_id,))
            before_data = cursor.fetchall()
            cursor.close()

            # キャッシュに保存
            if before_data and len(before_data) >= 6:
                self.race_data_cache.set_before_info(race_id, before_data)
                logger.debug(f"Race {race_id}: BEFORE情報キャッシュ保存")

        if not before_data or len(before_data) < 6:
            # BEFORE情報がない場合はそのまま返す
            for pred in predictions:
                pred['pre_score'] = round(pred['total_score'], 1)
                pred['integration_mode'] = 'pattern_bonus_unavailable'
            return predictions

        # 展示タイム順位を計算
        exhibition_times = [(row[0], row[1]) for row in before_data if row[1] is not None]
        if len(exhibition_times) >= 6:
            exhibition_times_sorted = sorted(exhibition_times, key=lambda x: x[1])
            exhibition_rank_map = {pit: rank+1 for rank, (pit, _) in enumerate(exhibition_times_sorted)}
        else:
            exhibition_rank_map = {}

        # ST順位を計算（0に近いほど良い）
        st_times = [(row[0], row[2]) for row in before_data if row[2] is not None]
        if len(st_times) >= 6:
            st_times_sorted = sorted(st_times, key=lambda x: abs(x[1]))
            st_rank_map = {pit: rank+1 for rank, (pit, _) in enumerate(st_times_sorted)}
        else:
            st_rank_map = {}

        # PRE順位マップを作成（現在のtotal_scoreベース）
        predictions_sorted = sorted(predictions, key=lambda x: x['total_score'], reverse=True)
        pre_rank_map = {pred['pit_number']: rank+1 for rank, pred in enumerate(predictions_sorted)}

        # 信頼度を取得（トップ予測の信頼度を使用）
        top_confidence = predictions[0].get('confidence', 'C') if predictions else 'C'

        # 各艇にパターンボーナスを適用
        for pred in predictions:
            pit_number = pred['pit_number']
            pre_score = pred['total_score']

            # PRE順位、展示順位、ST順位を取得
            pre_rank = pre_rank_map.get(pit_number)
            ex_rank = exhibition_rank_map.get(pit_number)
            st_rank = st_rank_map.get(pit_number)

            # デフォルト値
            final_multiplier = 1.0
            matched_patterns = []

            if pre_rank is not None and ex_rank is not None and st_rank is not None:
                # 1着予測パターンをチェック
                for pattern in BEFORE_PATTERNS_1ST:
                    try:
                        if pattern['condition'](pre_rank, ex_rank, st_rank):
                            # 最適化倍率を適用（フィーチャーフラグで制御）
                            # optimized_pattern_multipliers アーカイブ削除（2025-12-22）
                            multiplier = pattern['multiplier']

                            matched_patterns.append({
                                'name': pattern['name'],
                                'description': pattern['description'],
                                'multiplier': multiplier,
                                'target_rank': pattern['target_rank']
                            })
                            # 最も高い倍率を使用
                            if multiplier > final_multiplier:
                                final_multiplier = multiplier
                    except Exception:
                        pass

                # 2着予測パターンをチェック（PRE2位周辺の艇用）
                if pre_rank in [2, 3]:
                    for pattern in BEFORE_PATTERNS_2ND:
                        try:
                            if pattern['condition'](pre_rank, ex_rank, st_rank):
                                matched_patterns.append({
                                    'name': pattern['name'],
                                    'description': pattern['description'],
                                    'multiplier': pattern['multiplier'],
                                    'target_rank': pattern['target_rank']
                                })
                                # 2着パターンのボーナスは加算方式
                                if pattern['multiplier'] > final_multiplier:
                                    final_multiplier = pattern['multiplier']
                        except Exception:
                            pass

                # 3着予測パターンをチェック（PRE3-4位周辺の艇用）
                if pre_rank in [3, 4]:
                    for pattern in BEFORE_PATTERNS_3RD:
                        try:
                            # outer_st1_2パターンは特別処理（pit_number必要）
                            if pattern['name'] == 'outer_st1_2':
                                if pit_number >= 4 and st_rank <= 2:
                                    matched_patterns.append({
                                        'name': pattern['name'],
                                        'description': pattern['description'],
                                        'multiplier': pattern['multiplier'],
                                        'target_rank': pattern['target_rank']
                                    })
                                    if pattern['multiplier'] > final_multiplier:
                                        final_multiplier = pattern['multiplier']
                            elif pattern['condition'](pre_rank, ex_rank, st_rank):
                                matched_patterns.append({
                                    'name': pattern['name'],
                                    'description': pattern['description'],
                                    'multiplier': pattern['multiplier'],
                                    'target_rank': pattern['target_rank']
                                })
                                if pattern['multiplier'] > final_multiplier:
                                    final_multiplier = pattern['multiplier']
                        except Exception:
                            pass

                # 3着以内予測パターンをチェック（全艇対象）
                for pattern in BEFORE_PATTERNS_TOP3:
                    try:
                        if pattern['condition'](pre_rank, ex_rank, st_rank):
                            # 最適化倍率を適用（フィーチャーフラグで制御）
                            # optimized_pattern_multipliers アーカイブ削除（2025-12-22）
                            multiplier = pattern['multiplier']

                            matched_patterns.append({
                                'name': pattern['name'],
                                'description': pattern['description'],
                                'multiplier': multiplier,
                                'target_rank': pattern['target_rank']
                            })
                            # TOP3パターンは他より優先度低め（既に1着/2着/3着パターンがあれば使わない）
                            if len([p for p in matched_patterns if p['target_rank'] != 'top3']) == 0:
                                if multiplier > final_multiplier:
                                    final_multiplier = multiplier
                    except Exception:
                        pass

                # 複数パターンマッチ時の処理
                if len(matched_patterns) > 1:
                    # フィーチャーフラグで複合ボーナスを制御
                    if is_feature_enabled('compound_pattern_bonus'):
                        # 複合パターンボーナス: 複数パターンの相乗効果
                        # トップ2パターンの倍率を掛け合わせ、過剰補正を防ぐため調整係数(0.95)を適用
                        sorted_patterns = sorted(matched_patterns, key=lambda p: p['multiplier'], reverse=True)
                        top_pattern = sorted_patterns[0]
                        second_pattern = sorted_patterns[1] if len(sorted_patterns) > 1 else None

                        if second_pattern:
                            # 複合ボーナス計算: (倍率1 × 倍率2) × 0.95
                            compound_multiplier = top_pattern['multiplier'] * second_pattern['multiplier'] * 0.95
                            # 上限を1.5に設定（過剰補正防止）
                            final_multiplier = min(compound_multiplier, 1.5)
                            pred['selected_pattern'] = f"{top_pattern['name']}+{second_pattern['name']}"
                            logger.debug(
                                f"Race {race_id} 艇{pit_number}: 複合ボーナス適用 → "
                                f"{top_pattern['name']}({top_pattern['multiplier']:.3f}) × "
                                f"{second_pattern['name']}({second_pattern['multiplier']:.3f}) × 0.95 = "
                                f"{final_multiplier:.3f}"
                            )
                        else:
                            final_multiplier = top_pattern['multiplier']
                            pred['selected_pattern'] = top_pattern['name']
                    else:
                        # 従来方式: PatternPriorityOptimizerで最優先パターンを選択
                        best_pattern = self.pattern_optimizer.select_best_pattern(
                            matched_patterns,
                            top_confidence,
                            venue_code
                        )
                        if best_pattern:
                            final_multiplier = best_pattern['multiplier']
                            pred['selected_pattern'] = best_pattern['name']
                            logger.debug(
                                f"Race {race_id} 艇{pit_number}: {len(matched_patterns)}個のパターンマッチ → "
                                f"選択: {best_pattern['name']} (倍率{best_pattern['multiplier']:.3f})"
                            )
                elif len(matched_patterns) == 1:
                    # 単一パターンの場合はそのまま使用
                    final_multiplier = matched_patterns[0]['multiplier']
                    pred['selected_pattern'] = matched_patterns[0]['name']

                # 会場別最適化を適用（フィーチャーフラグで制御）
                if is_feature_enabled('venue_pattern_optimization') and final_multiplier > 1.0:
                    pattern_name = pred.get('selected_pattern', 'unknown')
                    original_multiplier = final_multiplier
                    final_multiplier = self.venue_pattern_optimizer.optimize_pattern_multiplier(
                        final_multiplier,
                        venue_code,
                        pattern_name
                    )
                    if abs(final_multiplier - original_multiplier) > 0.001:
                        logger.debug(
                            f"Race {race_id} 艇{pit_number}: 会場別最適化適用 "
                            f"{original_multiplier:.3f} → {final_multiplier:.3f} (会場{venue_code})"
                        )

            # 最終スコア計算
            final_score = pre_score * final_multiplier

            # スコアを更新
            pred['pre_score'] = round(pre_score, 1)
            pred['total_score'] = round(final_score, 1)
            pred['integration_mode'] = 'pattern_bonus'
            pred['pattern_multiplier'] = round(final_multiplier, 3)
            pred['matched_patterns'] = matched_patterns
            pred['before_ranks'] = {
                'pre_rank': pre_rank,
                'ex_rank': ex_rank,
                'st_rank': st_rank
            }

        # スコア降順で再ソート
        predictions.sort(key=lambda x: x['total_score'], reverse=True)

        # ネガティブパターンチェック（フィーチャーフラグで制御）
        if is_feature_enabled('negative_patterns'):
            # before_ranksマップを作成
            before_ranks_map = {}
            for pred in predictions:
                pit_num = pred.get('pit_number')
                before_ranks_data = pred.get('before_ranks', {})
                if before_ranks_data:
                    before_ranks_map[pit_num] = before_ranks_data

            if before_ranks_map:
                predictions = self.negative_pattern_checker.apply_negative_adjustments(
                    predictions,
                    before_ranks_map
                )
                logger.debug(f"Race {race_id}: ネガティブパターンチェック完了")

        # サマリーログ
        if predictions:
            top_pred = predictions[0]
            logger.info(
                f"Race {race_id}: パターン適用完了 - "
                f"信頼度{top_confidence} | "
                f"トップ予測: 艇{top_pred.get('pit_number')} "
                f"倍率{top_pred.get('pattern_multiplier', 1.0):.3f} "
                f"({top_pred.get('selected_pattern', 'なし')})"
            )

        return predictions

    def _apply_beforeinfo_integration(
        self,
        predictions: List[Dict],
        race_id: int,
        venue_code: str
    ) -> List[Dict]:
        """
        直前情報スコアリングと統合を適用

        統合式:
        - パターンボーナス有効時: BEFORE条件パターンに応じてスコア乗算（最新・最推奨）
        - 階層的予測有効時: BEFORE順位に応じてPRE_SCOREにボーナス加算（推奨）
        - 正規化統合有効時: 同一レース内で正規化してから統合
        - 動的統合有効時: DynamicIntegratorが条件に応じて重みを決定
        - レガシーモード: FINAL_SCORE = PRE_SCORE * 0.6 + BEFORE_SCORE * 0.4

        Args:
            predictions: 予測結果リスト（PRE_SCOREが格納されている）
            race_id: レースID
            venue_code: 会場コード

        Returns:
            統合スコア適用後の予測結果
        """
        # パターンボーナス方式が有効かチェック（最新・最優先）
        use_pattern_bonus = is_feature_enabled('before_pattern_bonus')

        if use_pattern_bonus:
            return self._apply_pattern_bonus(predictions, race_id)

        # ============================================================
        # アーカイブ済み統合モード削除（2025-12-22）
        # ============================================================
        # 以下のフラグは検証の結果、効果なしまたは悪化のため削除されました。
        # - beforeinfo_flag_adjustment: -3.65%悪化
        # - gated_before_integration: 効果なし
        # - hierarchical_before_prediction: -0.5%悪化
        # - normalized_before_integration: -0.5%悪化
        # - dynamic_integration: 逆相関
        #
        # パターンボーナス方式（before_pattern_bonus）のみが有効です。
        # ============================================================

        # 正規化統合が有効かチェック
        use_normalized_integration = False  # アーカイブフラグ削除により常にFalse

        # 動的統合が有効かチェック
        use_dynamic_integration = False  # アーカイブフラグ削除により常にFalse

        # 直前情報データを収集（動的統合用）
        beforeinfo_data = self._collect_beforeinfo_data(race_id) if use_dynamic_integration else None

        # 動的重みを決定（動的統合有効時のみ）
        integration_weights = None
        if use_dynamic_integration and beforeinfo_data:
            integration_weights = self.dynamic_integrator.determine_weights(
                race_id=race_id,
                beforeinfo_data=beforeinfo_data,
                pre_predictions=predictions,
                venue_code=venue_code
            )

        # BeforeInfoScorerでスコア計算（全艇分を先に計算）
        before_scores = {}
        before_results = {}
        pre_scores_list = []
        before_scores_list = []

        for pred in predictions:
            pit_number = pred['pit_number']
            pre_score = pred['total_score']  # 既存の総合スコア = PRE_SCORE
            pre_scores_list.append(pre_score)

            # 直前情報スコアを計算（BeforeInfoScorerが内部でDBから取得）
            beforeinfo_result = self.beforeinfo_scorer.calculate_beforeinfo_score(
                race_id=race_id,
                pit_number=pit_number
            )

            before_score = beforeinfo_result['total_score']  # 0-100点
            before_scores[pit_number] = before_score
            before_results[pit_number] = beforeinfo_result
            before_scores_list.append(before_score)

        # 状態フラグ方式の処理（最優先） - アーカイブ済み（削除）
        if False:  # use_flag_adjustment - アーカイブフラグ削除により無効化
            for pred in predictions:
                pit_number = pred['pit_number']
                pre_score = pred['total_score']

                # 状態フラグによる調整係数を取得
                adjustment = self.beforeinfo_flag_adjuster.calculate_adjustment_factors(
                    race_id, pit_number
                )

                # PRE_SCOREに調整係数を適用
                adjusted_score = pre_score * adjustment['score_multiplier']

                # スコアを更新
                pred['pre_score'] = round(pre_score, 1)
                pred['total_score'] = round(adjusted_score, 1)
                pred['integration_mode'] = 'flag_adjustment'
                pred['score_multiplier'] = round(adjustment['score_multiplier'], 3)
                pred['confidence_multiplier'] = round(adjustment['confidence_multiplier'], 3)
                pred['beforeinfo_flags'] = adjustment['flags']
                pred['beforeinfo_reasons'] = adjustment['reasons']

            # スコア降順で再ソート
            predictions.sort(key=lambda x: x['total_score'], reverse=True)
            return predictions

        # ゲーティング方式の処理（PRE拮抗時のみBEFORE使用） - アーカイブ済み（削除）
        if False:  # use_gated_integration - アーカイブフラグ削除により無効化
            # BEFORE順位を算出（スコア降順）
            before_ranking = sorted(before_scores.items(), key=lambda x: x[1], reverse=True)
            before_rank_map = {pit: rank+1 for rank, (pit, score) in enumerate(before_ranking)}

            # PRE_SCOREでソート（total_scoreはまだPREのみ）
            predictions_sorted = sorted(predictions, key=lambda x: x['total_score'], reverse=True)

            # PRE 1位-2位の得点差を計算
            if len(predictions_sorted) >= 2:
                pre_margin = predictions_sorted[0]['total_score'] - predictions_sorted[1]['total_score']
            else:
                pre_margin = 999.9  # 艇数不足の場合は拮抗していないとみなす

            # 拮抗判定（閾値: 5.0点）
            GATING_THRESHOLD = 5.0
            is_contested = pre_margin < GATING_THRESHOLD

            # 各艇のスコアを更新
            for pred in predictions:
                pit_number = pred['pit_number']
                pre_score = pred['total_score']
                before_rank = before_rank_map[pit_number]
                before_result = before_results[pit_number]
                before_score = before_scores[pit_number]

                # 拮抗時のみBEFOREボーナスを適用
                if is_contested:
                    if before_rank == 1:
                        bonus_multiplier = 1.05  # BEFORE 1位: +5%
                    elif before_rank == 2:
                        bonus_multiplier = 1.02  # BEFORE 2位: +2%
                    else:
                        bonus_multiplier = 1.00  # それ以外: ボーナスなし
                else:
                    bonus_multiplier = 1.00  # 拮抗していない場合はボーナスなし

                # 最終スコア計算
                final_score = pre_score * bonus_multiplier

                # スコアを更新
                pred['pre_score'] = round(pre_score, 1)
                pred['total_score'] = round(final_score, 1)
                pred['integration_mode'] = 'gated'
                pred['before_rank'] = before_rank
                pred['gating_bonus'] = round(bonus_multiplier, 3)
                pred['is_contested'] = is_contested
                pred['pre_margin'] = round(pre_margin, 1)

                # 直前情報の詳細を追加
                pred['beforeinfo_score'] = round(before_score, 1)
                pred['beforeinfo_confidence'] = round(before_result['confidence'], 3)
                pred['beforeinfo_completeness'] = round(before_result['data_completeness'], 3)
                pred['beforeinfo_detail'] = {
                    'exhibition_time': round(before_result['exhibition_time_score'], 1),
                    'st': round(before_result['st_score'], 1),
                    'entry': round(before_result['entry_score'], 1),
                    'prev_race': round(before_result['prev_race_score'], 1),
                    'tilt_wind': round(before_result['tilt_wind_score'], 1),
                    'parts_weight': round(before_result['parts_weight_score'], 1)
                }

            # スコア降順で再ソート
            predictions.sort(key=lambda x: x['total_score'], reverse=True)
            return predictions

        # 階層的予測モードの処理 - アーカイブ済み（削除）
        if False:  # use_hierarchical_prediction - アーカイブフラグ削除により無効化
            # BEFORE順位を算出（スコア降順）
            before_ranking = sorted(before_scores.items(), key=lambda x: x[1], reverse=True)
            before_rank_map = {pit: rank+1 for rank, (pit, score) in enumerate(before_ranking)}

            # BEFORE順位に応じてPRE_SCOREにボーナスを加算
            for pred in predictions:
                pit_number = pred['pit_number']
                pre_score = pred['total_score']
                before_rank = before_rank_map[pit_number]
                before_result = before_results[pit_number]
                before_score = before_scores[pit_number]

                # ボーナス倍率を決定
                if before_rank == 1:
                    bonus_multiplier = 1.10  # BEFORE 1位: 10%ボーナス
                elif before_rank == 2:
                    bonus_multiplier = 1.05  # BEFORE 2位: 5%ボーナス
                else:
                    bonus_multiplier = 1.00  # それ以外: ボーナスなし

                # 最終スコア計算
                final_score = pre_score * bonus_multiplier

                # スコアを更新
                pred['pre_score'] = round(pre_score, 1)
                pred['total_score'] = round(final_score, 1)
                pred['integration_mode'] = 'hierarchical'
                pred['before_rank'] = before_rank
                pred['bonus_multiplier'] = round(bonus_multiplier, 3)

                # 直前情報の詳細を追加
                pred['beforeinfo_score'] = round(before_score, 1)
                pred['beforeinfo_confidence'] = round(before_result['confidence'], 3)
                pred['beforeinfo_completeness'] = round(before_result['data_completeness'], 3)
                pred['beforeinfo_detail'] = {
                    'exhibition_time': round(before_result['exhibition_time_score'], 1),
                    'st': round(before_result['st_score'], 1),
                    'entry': round(before_result['entry_score'], 1),
                    'prev_race': round(before_result['prev_race_score'], 1),
                    'tilt_wind': round(before_result['tilt_wind_score'], 1),
                    'parts_weight': round(before_result['parts_weight_score'], 1)
                }

            # スコア降順で再ソート
            predictions.sort(key=lambda x: x['total_score'], reverse=True)
            return predictions

        # 正規化統合モードの処理
        if use_normalized_integration and len(pre_scores_list) >= 2:
            # 同一レース内で正規化（0-100に正規化）
            pre_min, pre_max = min(pre_scores_list), max(pre_scores_list)
            before_min, before_max = min(before_scores_list), max(before_scores_list)

            # 正規化関数（0-100範囲に変換）
            def normalize(score, min_val, max_val):
                if max_val == min_val:
                    return 50.0  # 全艇同点の場合は中央値
                return (score - min_val) / (max_val - min_val) * 100.0

            # 統合重み（データ充実度に応じて調整）
            # デフォルト: PRE 60%, BEFORE 40%
            default_pre_weight = 0.6
            default_before_weight = 0.4

            for pred in predictions:
                pit_number = pred['pit_number']
                pre_score = pred['total_score']
                before_result = before_results[pit_number]
                before_score = before_scores[pit_number]

                # PRE・BEFOREスコアを正規化
                pre_normalized = normalize(pre_score, pre_min, pre_max)
                before_normalized = normalize(before_score, before_min, before_max)

                # データ充実度に応じて重みを調整
                data_completeness = before_result['data_completeness']
                if data_completeness >= 0.5:
                    # データ充実: デフォルト重み
                    pre_weight = default_pre_weight
                    before_weight = default_before_weight
                else:
                    # データ不足: BEFOREの重みを下げる
                    pre_weight = 0.8
                    before_weight = 0.2

                # 正規化スコアを統合
                final_score = pre_normalized * pre_weight + before_normalized * before_weight

                # スコアを更新
                pred['pre_score'] = round(pre_score, 1)
                pred['total_score'] = round(final_score, 1)
                pred['integration_mode'] = 'normalized'
                pred['pre_weight'] = round(pre_weight, 3)
                pred['before_weight'] = round(before_weight, 3)
                pred['pre_normalized'] = round(pre_normalized, 1)
                pred['before_normalized'] = round(before_normalized, 1)

                # 直前情報の詳細を追加
                pred['beforeinfo_score'] = round(before_score, 1)
                pred['beforeinfo_confidence'] = round(before_result['confidence'], 3)
                pred['beforeinfo_completeness'] = round(data_completeness, 3)
                pred['beforeinfo_detail'] = {
                    'exhibition_time': round(before_result['exhibition_time_score'], 1),
                    'st': round(before_result['st_score'], 1),
                    'entry': round(before_result['entry_score'], 1),
                    'prev_race': round(before_result['prev_race_score'], 1),
                    'tilt_wind': round(before_result['tilt_wind_score'], 1),
                    'parts_weight': round(before_result['parts_weight_score'], 1)
                }

            return predictions

        # 動的統合 or レガシーモードの処理（既存のまま）
        for pred in predictions:
            pit_number = pred['pit_number']
            pre_score = pred['total_score']
            before_result = before_results[pit_number]
            before_score = before_scores[pit_number]
            before_confidence = before_result['confidence']
            data_completeness = before_result['data_completeness']

            # 統合式を適用
            if use_dynamic_integration and integration_weights:
                # 動的統合モード
                final_score = self.dynamic_integrator.integrate_scores(
                    pre_score=pre_score,
                    before_score=before_score,
                    weights=integration_weights
                )
                # 統合情報を記録
                pred['integration_mode'] = 'dynamic'
                pred['integration_condition'] = integration_weights.condition.value
                pred['integration_reason'] = integration_weights.reason
                pred['pre_weight'] = round(integration_weights.pre_weight, 3)
                pred['before_weight'] = round(integration_weights.before_weight, 3)
            else:
                # レガシーモード
                # BEFORE_SAFE統合が有効かチェック
                use_before_safe = is_feature_enabled('before_safe_integration')

                if use_before_safe:
                    # BEFORE_SAFE統合モード（安全版直前情報統合）
                    # BEFORE_SAFEスコアを計算（進入コース + 部品交換のみ）
                    before_safe_result = self.before_safe_scorer.calculate_before_safe_score(
                        race_id=race_id,
                        pit_number=pit_number
                    )
                    before_safe_score = before_safe_result['total_score']

                    # 一時的にスコアリストを作成して統合
                    # （全艇のスコアが揃った後に一括統合する方が正確だが、簡易実装）
                    # ここでは単一艇として扱い、PRE/BEFORE_SAFEを正規化せずに統合
                    weights = self.safe_integrator.get_weights()
                    final_score = pre_score * weights['pre_weight'] + before_safe_score * weights['before_safe_weight']

                    pred['integration_mode'] = 'before_safe'
                    pred['pre_weight'] = round(weights['pre_weight'], 3)
                    pred['before_weight'] = round(weights['before_safe_weight'], 3)
                    pred['before_safe_score'] = round(before_safe_score, 1)
                    pred['before_safe_detail'] = {
                        'entry': round(before_safe_result['entry_score'], 1),
                        'parts': round(before_safe_result['parts_score'], 1),
                        'weight': round(before_safe_result['weight_score'], 1),
                        'confidence': round(before_safe_result['confidence'], 3)
                    }
                else:
                    # BEFORE完全停止モード
                    # BEFORE_SCOREは逆相関（的中率4.1%）のため完全停止
                    # PRE_SCORE単体で運用（43.3%的中率）
                    final_score = pre_score * 1.0 + before_score * 0.0
                    # 部品交換ペナルティのみ例外適用（2026-04-16）
                    # 全BEFOREスコアは無効だが、部品交換は明確なネガティブシグナルのため
                    # PRE_SCOREに乗算で反映する（重大:-15% / 中程度:-10% / 軽微:-3%）
                    parts_multiplier = self.beforeinfo_flag_adjuster.get_parts_penalty_multiplier(
                        race_id, pit_number
                    )
                    if parts_multiplier < 1.0:
                        final_score *= parts_multiplier
                        pred['parts_penalty_multiplier'] = parts_multiplier
                    pred['integration_mode'] = 'before_disabled'
                    pred['pre_weight'] = 1.0
                    pred['before_weight'] = 0.0

            # スコアを更新
            pred['pre_score'] = round(pre_score, 1)  # 統合前のスコアを保存
            pred['total_score'] = round(final_score, 1)  # 最終スコア

            # 直前情報の詳細を追加
            pred['beforeinfo_score'] = round(before_score, 1)
            pred['beforeinfo_confidence'] = round(before_confidence, 3)
            pred['beforeinfo_completeness'] = round(data_completeness, 3)
            pred['beforeinfo_detail'] = {
                'exhibition_time': round(beforeinfo_result['exhibition_time_score'], 1),
                'st': round(beforeinfo_result['st_score'], 1),
                'entry': round(beforeinfo_result['entry_score'], 1),
                'prev_race': round(beforeinfo_result['prev_race_score'], 1),
                'tilt_wind': round(beforeinfo_result['tilt_wind_score'], 1),
                'parts_weight': round(beforeinfo_result['parts_weight_score'], 1)
            }

        return predictions

    def _collect_beforeinfo_data(self, race_id: int) -> Dict:
        """
        動的統合に必要な直前情報データを収集

        Args:
            race_id: レースID

        Returns:
            直前情報データ辞書
        """
        import sqlite3

        beforeinfo_data = {
            'is_published': False,
            'exhibition_times': {},
            'start_timings': {},
            'exhibition_courses': {},
            'tilt_angles': {},
            'weather': {},
            'previous_race': {}
        }

        try:
            conn = get_connection(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 展示タイム、ST、進入コースを取得
            cursor.execute("""
                SELECT
                    pit_number,
                    exhibition_time,
                    start_timing,
                    exhibition_course,
                    tilt_angle
                FROM beforeinfo
                WHERE race_id = ?
            """, (race_id,))

            rows = cursor.fetchall()
            if rows:
                beforeinfo_data['is_published'] = True
                for row in rows:
                    pit = row['pit_number']
                    if row['exhibition_time']:
                        beforeinfo_data['exhibition_times'][pit] = row['exhibition_time']
                    if row['start_timing'] is not None:
                        beforeinfo_data['start_timings'][pit] = row['start_timing']
                    if row['exhibition_course']:
                        beforeinfo_data['exhibition_courses'][pit] = row['exhibition_course']
                    if row['tilt_angle'] is not None:
                        beforeinfo_data['tilt_angles'][pit] = row['tilt_angle']

            # 天候データを取得
            cursor.execute("""
                SELECT wind_speed, wave_height
                FROM races
                WHERE race_id = ?
            """, (race_id,))

            weather_row = cursor.fetchone()
            if weather_row:
                if weather_row['wind_speed']:
                    beforeinfo_data['weather']['wind_speed'] = weather_row['wind_speed']
                if weather_row['wave_height']:
                    beforeinfo_data['weather']['wave_height'] = weather_row['wave_height']

            cursor.close()

        except Exception as e:
            # エラーが発生しても空のデータで続行
            pass

        return beforeinfo_data

    def _apply_exhibition_adjustment(
        self,
        predictions: List[Dict],
        race_id: int
    ) -> List[Dict]:
        """
        展示データに基づくスコア補正を適用

        展示タイム、スタート展示、ターン評価などを考慮して
        モーター・選手スコアを補正する。

        Args:
            predictions: 予測結果リスト
            race_id: レースID

        Returns:
            展示補正後の予測結果
        """
        # 展示補正の最大影響を制限
        MAX_EXHIBITION_ADJUSTMENT = 10.0  # スコアへの最大影響

        for pred in predictions:
            pit_number = pred['pit_number']
            original_score = pred['total_score']

            try:
                # 展示補正を計算
                adj_result = self.exhibition_analyzer.calculate_exhibition_adjustment(
                    race_id,
                    pit_number
                )

                # モーター補正と選手補正を合算
                total_adjustment = (
                    adj_result['motor_adjustment'] +
                    adj_result['racer_adjustment']
                )

                if total_adjustment != 0:
                    # 補正値を制限
                    score_adjustment = max(-MAX_EXHIBITION_ADJUSTMENT,
                                          min(total_adjustment, MAX_EXHIBITION_ADJUSTMENT))

                    # スコアを補正
                    adjusted_score = original_score + score_adjustment

                    # スコアを0-100範囲に制限
                    adjusted_score = max(0.0, min(adjusted_score, 100.0))

                    pred['total_score'] = round(adjusted_score, 1)

                    # 補正情報を追加
                    pred['exhibition_adjustment'] = round(score_adjustment, 1)
                    pred['exhibition_reason'] = adj_result['reason']

            except Exception:
                # 展示データがない場合は補正なしで続行
                pass

        return predictions

    def _apply_entry_prediction(
        self,
        predictions: List[Dict],
        race_id: int,
        race_date: str = None
    ) -> List[Dict]:
        """
        進入予測モデルを適用してスコアを調整

        Args:
            predictions: 予測結果リスト
            race_id: レースID

        Returns:
            進入予測適用後の予測結果
        """
        # 機能フラグチェック
        if not is_feature_enabled('entry_prediction_model'):
            return predictions

        try:
            # エントリー情報を取得（キャッシュ優先）
            if self.batch_loader and self.batch_loader._cache_loaded:
                entries = [
                    {'pit_number': e['pit_number'], 'racer_number': e['racer_number']}
                    for e in self.batch_loader.get_race_entries(race_id)
                ]
            else:
                import sqlite3
                conn = get_connection(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT pit_number, racer_number
                    FROM entries
                    WHERE race_id = ?
                    ORDER BY pit_number
                """, (race_id,))
                entries = [dict(row) for row in cursor.fetchall()]
                cursor.close()

            if len(entries) < 6:
                return predictions

            # 進入予測を実行
            entry_predictions = self.entry_prediction_model.predict_race_entries(
                race_id=race_id,
                entries=entries,
                race_date=race_date
            )

            # 各予測に進入影響スコアを適用
            for pred in predictions:
                pit_number = pred['pit_number']

                if pit_number in entry_predictions:
                    entry_pred = entry_predictions[pit_number]

                    # 進入影響スコアを計算
                    impact = self.entry_prediction_model.calculate_entry_impact_score(
                        pit_number=pit_number,
                        prediction=entry_pred,
                        max_score=10.0  # 最大10点の影響
                    )

                    # スコアに反映
                    original_score = pred['total_score']
                    adjusted_score = original_score + impact['score']

                    # 0-100の範囲に制限
                    adjusted_score = max(0.0, min(adjusted_score, 100.0))

                    pred['total_score'] = round(adjusted_score, 1)
                    pred['entry_impact_score'] = round(impact['score'], 1)
                    pred['entry_impact_type'] = impact['impact_type']
                    pred['predicted_course'] = entry_pred.predicted_course
                    pred['entry_confidence'] = round(entry_pred.confidence, 3)
                    pred['is_front_entry_prone'] = entry_pred.is_front_entry_prone
                    pred['front_entry_rate'] = round(entry_pred.front_entry_rate, 3)

        except Exception as e:
            # エラーが発生しても処理を継続
            pass

        return predictions

    def _apply_probability_calibration(
        self,
        predictions: List[Dict]
    ) -> List[Dict]:
        """
        確率キャリブレーションを適用

        スコアを実際の勝率に較正する

        Args:
            predictions: 予測結果リスト

        Returns:
            キャリブレーション適用後の予測結果
        """
        # 機能フラグチェック
        if not is_feature_enabled('probability_calibration'):
            return predictions

        try:
            for pred in predictions:
                score = pred['total_score']

                # スコアを0-1の確率に変換してキャリブレーション
                raw_prob = score / 100.0
                calibrated_prob = self.probability_calibrator.calibrate(raw_prob)

                # キャリブレーション後の確率をスコアに戻す
                calibrated_score = calibrated_prob * 100.0

                pred['calibrated_score'] = round(calibrated_score, 1)
                pred['calibrated_probability'] = round(calibrated_prob, 4)
                pred['raw_probability'] = round(raw_prob, 4)

        except Exception as e:
            # エラーが発生しても処理を継続
            pass

        return predictions

    def _add_top3_scores(
        self,
        predictions: List[Dict],
        venue_code: str,
        race_date: str
    ) -> List[Dict]:
        """
        三連対スコアを計算して追加し、ハイブリッドスコアリングを適用

        1着予測: 現在のスコア（1着確率ベース）を維持
        2着・3着予測: 三連対スコア（3着以内確率ベース）を使用

        Args:
            predictions: 予測結果リスト
            venue_code: 会場コード
            race_date: レース日

        Returns:
            三連対スコア追加・調整後の予測結果
        """
        try:
            # 各艇の三連対スコアを計算
            for pred in predictions:
                top3_result = self.top3_scorer.calculate_top3_score(
                    racer_number=pred['racer_number'],
                    venue_code=venue_code,
                    course=pred['pit_number'],
                    motor_number=pred['motor_number'],
                    race_date=race_date
                )

                # 三連対スコアと詳細を追加
                pred['top3_score'] = top3_result['top3_score']
                pred['racer_top3_rate'] = top3_result['racer_top3_rate']
                pred['course_top3_rate'] = top3_result['course_top3_rate']
                pred['motor_top3_rate'] = top3_result['motor_top3_rate']
                pred['venue_top3_rate'] = top3_result['venue_top3_rate']

            # 現在のスコアでソートして仮順位を付与
            sorted_by_current = sorted(predictions, key=lambda x: x['total_score'], reverse=True)

            # 三連対スコアでソート
            sorted_by_top3 = sorted(predictions, key=lambda x: x['top3_score'], reverse=True)

            # ハイブリッドスコアリング適用
            # 1位予測: 現在のスコアの1位を維持
            # 2位・3位予測: 三連対スコアの上位を使用

            first_place_candidate = sorted_by_current[0]

            # 三連対スコアで1位候補を除いた上位2艇を抽出
            remaining_by_top3 = [p for p in sorted_by_top3 if p['pit_number'] != first_place_candidate['pit_number']]

            if len(remaining_by_top3) >= 2:
                second_place_candidate = remaining_by_top3[0]
                third_place_candidate = remaining_by_top3[1]

                # ハイブリッドスコアを計算（2着・3着予測の精度向上）
                # 1位: 現在のスコア重視（1着確率ベース）
                # 2位・3位: 三連対スコア重視（3着以内確率ベース）

                for pred in predictions:
                    pit = pred['pit_number']

                    if pit == first_place_candidate['pit_number']:
                        # 1位候補: 現在のスコア + ボーナス
                        pred['hybrid_score'] = pred['total_score'] + 10.0
                        pred['hybrid_reason'] = '1位候補（1着確率ベース）'
                    elif pit == second_place_candidate['pit_number']:
                        # 2位候補: 三連対スコア + ボーナス
                        pred['hybrid_score'] = pred['top3_score'] + 5.0
                        pred['hybrid_reason'] = '2位候補（三連対スコアベース）'
                    elif pit == third_place_candidate['pit_number']:
                        # 3位候補: 三連対スコア + 小ボーナス
                        pred['hybrid_score'] = pred['top3_score'] + 2.0
                        pred['hybrid_reason'] = '3位候補（三連対スコアベース）'
                    else:
                        # その他: 三連対スコアベース
                        pred['hybrid_score'] = pred['top3_score']
                        pred['hybrid_reason'] = 'その他（三連対スコアベース）'

                # ハイブリッドスコアでソート
                predictions.sort(key=lambda x: x['hybrid_score'], reverse=True)

                # total_scoreをハイブリッドスコアで上書き（既存ロジックとの互換性維持）
                for pred in predictions:
                    pred['original_total_score'] = pred['total_score']  # 元のスコアを保存
                    pred['total_score'] = pred['hybrid_score']  # ハイブリッドスコアを使用

        except Exception as e:
            # エラーが発生しても既存のスコアで継続
            pass

        return predictions

    def _apply_course_enforcement(
        self,
        predictions: List[Dict]
    ) -> List[Dict]:
        """
        予測コース強制化を適用

        2025年分析結果に基づく改善:
        - 1コース予測時: 精度60.5%（ベースライン55.1%を上回る）
        - 非1コース予測時: 精度24.8%（極めて低い）

        設定に基づき、低精度な非1コース予測を1コースに強制変更する

        Args:
            predictions: スコア降順にソートされた予測結果リスト

        Returns:
            コース強制化適用後の予測結果
        """
        logger = logging.getLogger(__name__)

        # 設定ファイルが読み込めていない場合は処理しない
        if PREDICTION_STRATEGY is None:
            return predictions

        # 設定を取得
        enforcement_config = PREDICTION_STRATEGY.get('course_enforcement', {})
        if not enforcement_config.get('enabled', False):
            return predictions

        mode = enforcement_config.get('mode', 'score_threshold')

        # 現在の1位予測を取得
        if not predictions:
            return predictions

        top_prediction = predictions[0]
        top_pit = top_prediction['pit_number']
        top_score = top_prediction['total_score']
        top_confidence = top_prediction['confidence']

        # 1コースが既に1位予測の場合は処理不要
        if top_pit == 1:
            return predictions

        # 1コースの予測データを取得
        course1_prediction = None
        for pred in predictions:
            if pred['pit_number'] == 1:
                course1_prediction = pred
                break

        if course1_prediction is None:
            return predictions

        course1_score = course1_prediction['total_score']
        score_diff = top_score - course1_score

        # 強制化判定
        should_enforce = False
        enforce_reason = ""

        if mode == 'all':
            # 全ての非1コース予測を強制
            should_enforce = True
            enforce_reason = "全件1コース強制モード"

        elif mode == 'confidence_threshold':
            # 信頼度による強制
            conf_settings = enforcement_config.get('confidence_threshold_settings', {})
            min_confidence = conf_settings.get('min_confidence', 'C')

            confidence_order = {'A': 5, 'B': 4, 'C': 3, 'D': 2, 'E': 1}
            min_conf_level = confidence_order.get(min_confidence, 3)
            top_conf_level = confidence_order.get(top_confidence, 3)

            if top_conf_level <= min_conf_level:
                should_enforce = True
                enforce_reason = f"信頼度{top_confidence}（閾値{min_confidence}以下）"

        elif mode == 'score_threshold':
            # スコア差による強制
            score_settings = enforcement_config.get('score_threshold_settings', {})
            min_score_diff = score_settings.get('min_score_difference', 8.0)

            if score_diff < min_score_diff:
                should_enforce = True
                enforce_reason = f"スコア差{score_diff:.1f}pt（閾値{min_score_diff}pt未満）"

        elif mode == 'combined':
            # 信頼度とスコア差の組み合わせ
            conf_settings = enforcement_config.get('confidence_threshold_settings', {})
            score_settings = enforcement_config.get('score_threshold_settings', {})

            min_confidence = conf_settings.get('min_confidence', 'C')
            min_score_diff = score_settings.get('min_score_difference', 8.0)

            confidence_order = {'A': 5, 'B': 4, 'C': 3, 'D': 2, 'E': 1}
            min_conf_level = confidence_order.get(min_confidence, 3)
            top_conf_level = confidence_order.get(top_confidence, 3)

            # どちらかの条件を満たせば強制
            if top_conf_level <= min_conf_level:
                should_enforce = True
                enforce_reason = f"信頼度{top_confidence}（閾値{min_confidence}以下）"
            elif score_diff < min_score_diff:
                should_enforce = True
                enforce_reason = f"スコア差{score_diff:.1f}pt（閾値{min_score_diff}pt未満）"

        # 強制化を適用
        if should_enforce:
            logger.info(
                f"コース強制化適用: {top_pit}コース → 1コースに変更 "
                f"（理由: {enforce_reason}, 元スコア差: {score_diff:.1f}pt）"
            )

            # 1コースのスコアを最大にする（元の1位より少し高く設定）
            course1_prediction['total_score'] = top_score + 0.1
            course1_prediction['course_enforcement_applied'] = True
            course1_prediction['enforcement_reason'] = enforce_reason
            course1_prediction['original_score'] = course1_score

            # 再ソート
            predictions.sort(key=lambda x: x['total_score'], reverse=True)

        return predictions

    def _apply_second_place_specialized(
        self,
        predictions: List[Dict],
        race_id: int
    ) -> List[Dict]:
        """
        2着専用スコアリングを適用

        差し・まくり差し特化型の特徴量を使用して
        2着予測の精度を向上させる。

        アプローチ2: 2着専用の機械学習モデルを使用
        - 1着予測艇を条件として2着確率を予測
        - 既存の順位予測と統合

        Args:
            predictions: 予測結果リスト（スコア順）
            race_id: レースID

        Returns:
            2着専用スコア適用後の予測結果
        """
        logger = logging.getLogger(__name__)

        if self.second_place_scorer is None or self.second_place_scorer.model is None:
            return predictions

        if len(predictions) < 2:
            return predictions

        try:
            # レース特徴量を取得
            import pandas as pd
            import sqlite3
            conn = get_connection(self.db_path)

            query = """
            SELECT
                e.pit_number,
                e.racer_number,
                e.racer_rank,
                e.win_rate,
                e.second_rate,
                e.third_rate,
                e.motor_number,
                e.motor_second_rate,
                e.motor_third_rate,
                e.boat_second_rate,
                e.avg_st,
                e.f_count,
                e.l_count,
                rd.exhibition_time,
                rd.st_time,
                rd.tilt_angle
            FROM entries e
            LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
            WHERE e.race_id = ?
            ORDER BY e.pit_number
            """

            race_features = pd.read_sql_query(query, conn, params=(race_id,))

            if len(race_features) != 6:
                return predictions

            # 予測結果からスコアを追加
            for pred in predictions:
                pit = pred['pit_number']
                idx = race_features[race_features['pit_number'] == pit].index
                if len(idx) > 0:
                    race_features.loc[idx[0], 'total_score'] = pred['total_score']

            # 予測1着艇
            predicted_first = predictions[0]['pit_number']

            # 2着専用モデルで予測
            specialized_probs = self.second_place_scorer.predict(
                race_features, predicted_first
            )

            if not specialized_probs:
                return predictions

            # 既存の2着確率（スコアベース）
            total_remaining_score = sum(
                p['total_score'] for p in predictions[1:]
            )
            baseline_probs = {}
            if total_remaining_score > 0:
                for p in predictions[1:]:
                    baseline_probs[p['pit_number']] = p['total_score'] / total_remaining_score

            # 統合（重み: 0.5 baseline, 0.5 specialized）
            integration_weight = 0.5
            integrated_probs = {}

            for pit in specialized_probs:
                baseline = baseline_probs.get(pit, 0.0)
                specialized = specialized_probs[pit]
                integrated_probs[pit] = (
                    (1 - integration_weight) * baseline +
                    integration_weight * specialized
                )

            # 正規化
            total_integrated = sum(integrated_probs.values())
            if total_integrated > 0:
                integrated_probs = {
                    pit: prob / total_integrated
                    for pit, prob in integrated_probs.items()
                }

            # 予測結果に追加
            for pred in predictions:
                pit = pred['pit_number']
                if pit == predicted_first:
                    pred['specialized_2nd_prob'] = 0.0
                    pred['integrated_2nd_prob'] = 0.0
                else:
                    pred['specialized_2nd_prob'] = round(
                        specialized_probs.get(pit, 0.0), 4
                    )
                    pred['integrated_2nd_prob'] = round(
                        integrated_probs.get(pit, 0.0), 4
                    )

            # 2着候補を統合確率で再順位付け
            first_pred = predictions[0]
            rest_preds = sorted(
                [p for p in predictions[1:]],
                key=lambda x: x.get('integrated_2nd_prob', 0.0),
                reverse=True
            )

            # スコア調整（2着候補のスコアを微調整）
            if rest_preds:
                # 統合確率に基づいてスコアを再調整
                max_rest_score = max(p['total_score'] for p in rest_preds)
                for i, pred in enumerate(rest_preds):
                    integrated_prob = pred.get('integrated_2nd_prob', 0.0)
                    # 統合確率に基づくスコア調整（最大5点）
                    adjustment = (integrated_prob - 0.2) * 25  # 0.2が基準
                    adjustment = max(-3.0, min(5.0, adjustment))
                    pred['second_place_adjustment'] = round(adjustment, 2)
                    pred['total_score'] = round(pred['total_score'] + adjustment, 1)

            # 再ソート
            predictions = [first_pred] + sorted(
                rest_preds,
                key=lambda x: x['total_score'],
                reverse=True
            )

            logger.debug(
                f"Race {race_id}: 2着専用スコア適用 - "
                f"予測1着: {predicted_first}号艇, "
                f"予測2着: {predictions[1]['pit_number']}号艇"
            )

        except Exception as e:
            logger.debug(f"Race {race_id}: 2着専用スコア計算エラー: {e}")

        return predictions

    def _apply_confidence_based_switching(
        self,
        predictions: List[Dict],
        race_id: int
    ) -> List[Dict]:
        """
        信頼度ベースの戦略切り替えを適用

        アプローチ1: 1着予測の確信度に応じた2着・3着予測方法の切り替え

        理論的根拠:
        - 1着予測が正しい場合: 2着的中率 31.67%（良好）
        - 1着予測が誤りの場合: 2着的中率 16.93%（ランダム20%以下）

        戦略:
        - 高信頼度: 条件付きモデル + 2着専用スコアリング
        - 中信頼度: 2着専用スコアリングのみ
        - 低信頼度: 独立予測（1着を条件としない全艇並列評価）

        Args:
            predictions: 予測結果リスト（スコア順）
            race_id: レースID

        Returns:
            信頼度ベース予測適用後の予測結果
        """
        logger = logging.getLogger(__name__)

        if self.confidence_based_integrator is None:
            return predictions

        if len(predictions) < 2:
            return predictions

        try:
            # 市場確率を取得（オッズから計算）
            market_probs = None
            try:
                trifecta_odds = self.odds_calibrator._get_trifecta_odds(race_id)
                if trifecta_odds:
                    market_probs = calculate_market_probs_from_odds(trifecta_odds)
            except Exception:
                pass

            # プリセットパターンを取得（適用された法則から）
            preset_pattern = None
            try:
                applied_rules = self.get_applied_rules(race_id)
                if applied_rules:
                    # 最も信頼度の高い法則名を取得
                    preset_pattern = applied_rules[0].get('rule_name', None)
            except Exception:
                pass

            # 2着専用モデルの確率を取得
            specialized_second_probs = None
            if self.second_place_scorer is not None and self.second_place_scorer.model is not None:
                try:
                    import pandas as pd
                    conn = get_connection(self.db_path)

                    query = """
                    SELECT
                        e.pit_number,
                        e.racer_number,
                        e.racer_rank,
                        e.win_rate,
                        e.second_rate,
                        e.third_rate,
                        e.motor_second_rate,
                        e.boat_second_rate,
                        e.avg_st,
                        e.f_count,
                        e.l_count,
                        rd.exhibition_time,
                        rd.st_time
                    FROM entries e
                    LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
                    WHERE e.race_id = ?
                    ORDER BY e.pit_number
                    """

                    race_features = pd.read_sql_query(query, conn, params=(race_id,))

                    if len(race_features) == 6:
                        # 予測結果からスコアを追加
                        for pred in predictions:
                            pit = pred['pit_number']
                            idx = race_features[race_features['pit_number'] == pit].index
                            if len(idx) > 0:
                                race_features.loc[idx[0], 'total_score'] = pred['total_score']

                        predicted_first = predictions[0]['pit_number']
                        specialized_second_probs = self.second_place_scorer.predict(
                            race_features, predicted_first
                        )
                except Exception:
                    pass

            # 条件付きモデルの確率を取得（既存の予測から）
            conditional_second_probs = None
            if predictions[0].get('integrated_2nd_prob', 0) > 0:
                conditional_second_probs = {
                    p['pit_number']: p.get('integrated_2nd_prob', 0.0)
                    for p in predictions if p['pit_number'] != predictions[0]['pit_number']
                }

            # 信頼度ベース予測を適用
            processed, confidence = self.confidence_based_integrator.process_predictions(
                predictions=predictions,
                market_probs=market_probs,
                preset_pattern=preset_pattern,
                conditional_second_probs=conditional_second_probs,
                specialized_second_probs=specialized_second_probs
            )

            logger.debug(
                f"Race {race_id}: 信頼度ベース戦略 - "
                f"レベル: {confidence.confidence_level}, "
                f"スコア: {confidence.total_confidence:.3f}"
            )

            return processed

        except Exception as e:
            logger.debug(f"Race {race_id}: 信頼度ベース戦略エラー: {e}")
            return predictions

    def _apply_pairwise_scoring(
        self,
        predictions: List[Dict],
        race_id: int
    ) -> List[Dict]:
        """
        ペアワイズ相対スコアリングを適用（案C: 1着固定・2-3着のみ最適化）

        1着はtotal_scoreで確定し信頼度判定に影響を与えない。
        2着・3着のみpairwiseの条件付き確率で最適化する。
        これにより件数変動なし・副作用最小で2-3着的中率の向上を狙う。

        Args:
            predictions: 予測結果リスト（スコア順）
            race_id: レースID

        Returns:
            ペアワイズスコア適用後の予測結果（1着固定・2-3着最適化済み）
        """
        logger = logging.getLogger(__name__)

        if self.pairwise_integrator is None:
            return predictions

        if len(predictions) != 6:
            return predictions

        try:
            # レース特徴量を取得
            import pandas as pd
            conn = get_connection(self.db_path)

            query = """
            SELECT
                e.pit_number,
                e.racer_number,
                e.racer_rank,
                e.win_rate,
                e.second_rate,
                e.third_rate,
                e.motor_number,
                e.motor_second_rate,
                e.motor_third_rate,
                e.boat_second_rate,
                e.avg_st,
                e.f_count,
                e.l_count,
                rd.exhibition_time,
                rd.st_time,
                rd.tilt_angle
            FROM entries e
            LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
            WHERE e.race_id = ?
            ORDER BY e.pit_number
            """

            race_features = pd.read_sql_query(query, conn, params=(race_id,))

            if len(race_features) != 6:
                return predictions

            # 予測結果からスコアを追加
            for pred in predictions:
                pit = pred['pit_number']
                idx = race_features[race_features['pit_number'] == pit].index
                if len(idx) > 0:
                    race_features.loc[idx[0], 'total_score'] = pred['total_score']

            # 1着はtotal_scoreで確定（kimarite/makuri調整後の順序を維持）
            predictions_sorted = sorted(predictions, key=lambda x: x['total_score'], reverse=True)
            first_pit = predictions_sorted[0]['pit_number']

            # 2着をpairwiseで決定（1着固定条件下）
            second_probs = self.pairwise_integrator.get_second_place_probs(
                predictions_sorted, race_features
            )
            if not second_probs:
                return predictions

            predicted_second = max(second_probs, key=second_probs.get)

            # 3着をpairwiseで決定（1着・2着固定条件下）
            third_probs = self.pairwise_integrator.get_third_place_probs(
                predictions_sorted, race_features, predicted_second
            )
            if not third_probs:
                return predictions

            predicted_third = max(third_probs, key=third_probs.get)

            # 順位を再構築（1-3着はpairwise決定、4-6着はtotal_score順）
            top3 = [first_pit, predicted_second, predicted_third]
            rest = [p['pit_number'] for p in predictions_sorted if p['pit_number'] not in top3]
            pred_dict = {p['pit_number']: p for p in predictions_sorted}
            reordered = [pred_dict[pit] for pit in top3 + rest]

            logger.debug(
                f"Race {race_id}: pairwise 2-3着最適化 - "
                f"1着: {first_pit}号艇, 2着: {predicted_second}号艇, 3着: {predicted_third}号艇"
            )

            return reordered

        except Exception as e:
            logger.debug(f"Race {race_id}: ペアワイズスコア計算エラー: {e}")

        return predictions

    def _apply_monte_carlo_simulation(
        self,
        predictions: List[Dict],
        race_id: int,
        wind_speed: Optional[float] = None,
        wave_height: Optional[float] = None,
        wind_direction: Optional[str] = None
    ) -> List[Dict]:
        """
        モンテカルロレースシミュレーションを適用

        アプローチ5: 確率的レース展開をシミュレーションして順位分布を予測

        理論的根拠:
        - 現在のモデルは各艇の絶対スコアを計算しているが、
          レースは確率的な要素（ST誤差、ターン成功率、追い上げ等）で決まる
        - 大量のシミュレーションで順位分布を算出することで、
          2着・3着の予測精度を向上できる可能性がある

        実装:
        - 各艇のパラメータ（速度、ST誤差、ターン成功率）をスコアから推定
        - レースを5000回シミュレーション
        - 順位分布から2着・3着確率を計算し、スコアに反映

        Args:
            predictions: 予測結果リスト（スコア順）
            race_id: レースID
            wind_speed: 風速
            wave_height: 波高
            wind_direction: 風向

        Returns:
            シミュレーション適用後の予測結果
        """
        logger = logging.getLogger(__name__)

        if self.monte_carlo_integrator is None:
            return predictions

        if len(predictions) != 6:
            return predictions

        try:
            # 級別情報を予測結果に追加（シミュレーションで使用）
            import sqlite3
            conn = get_connection(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT pit_number, racer_rank, avg_st
                FROM entries
                WHERE race_id = ?
                ORDER BY pit_number
            """, (race_id,))
            entry_data = {row['pit_number']: dict(row) for row in cursor.fetchall()}
            cursor.close()

            # 予測に級別情報を追加
            for pred in predictions:
                pit = pred['pit_number']
                if pit in entry_data:
                    if 'extended_detail' not in pred:
                        pred['extended_detail'] = {}
                    pred['extended_detail']['class'] = {
                        'class_name': entry_data[pit].get('racer_rank', 'B1')
                    }
                    pred['extended_detail']['start_timing'] = {
                        'avg_st': entry_data[pit].get('avg_st')
                    }
                    # racer_rank を直接追加
                    pred['racer_rank'] = entry_data[pit].get('racer_rank', 'B1')

            # シミュレーション適用
            predictions = self.monte_carlo_integrator.apply_simulation(
                predictions,
                wind_speed=wind_speed or 0.0,
                wave_height=wave_height or 0.0,
                wind_direction=wind_direction
            )

            # 再ソート
            predictions.sort(key=lambda x: x['total_score'], reverse=True)

            logger.debug(
                f"Race {race_id}: モンテカルロシミュレーション適用 - "
                f"予測1着: {predictions[0]['pit_number']}号艇, "
                f"シミュレーション1着確率: {predictions[0].get('simulation_1st_prob', 'N/A')}%"
            )

        except Exception as e:
            logger.debug(f"Race {race_id}: モンテカルロシミュレーションエラー: {e}")

        return predictions

    def _apply_kimarite_flow_prediction(
        self,
        predictions: List[Dict],
        race_id: int
    ) -> List[Dict]:
        """
        P-3: 決まり手別展開予測によるスコア調整

        決まり手（逃げ、差し、まくり等）のパターンから
        2着・3着展開を予測し、スコアを調整する。

        Args:
            predictions: 予測結果リスト（スコア順）
            race_id: レースID

        Returns:
            決まり手予測適用後の予測結果
        """
        logger = logging.getLogger(__name__)

        if self.kimarite_flow_predictor is None:
            return predictions

        if len(predictions) < 6:
            return predictions

        try:
            # 1着予測艇の決まり手を予測
            predicted_first = predictions[0]['pit_number']

            # 決まり手別の2着・3着候補を取得
            flow_result = self.kimarite_flow_predictor.predict_flow(
                race_id=race_id,
                predicted_first=predicted_first
            )

            if flow_result and 'scenarios' in flow_result:
                # 最も確率の高いシナリオを取得
                top_scenario = flow_result['scenarios'][0] if flow_result['scenarios'] else None

                if top_scenario:
                    # 2着・3着候補のスコアを調整
                    second_candidate = top_scenario.get('second_place')
                    third_candidate = top_scenario.get('third_place')
                    scenario_prob = top_scenario.get('probability', 0.0)

                    # 調整幅を決定（シナリオ確率に応じて）
                    adjustment_factor = min(scenario_prob * 0.1, 0.05)  # 最大5%調整

                    for pred in predictions:
                        pit = pred['pit_number']
                        original_score = pred['total_score']

                        if pit == second_candidate:
                            # 2着候補はスコアを上げる
                            pred['total_score'] = round(original_score * (1 + adjustment_factor), 1)
                            pred['kimarite_flow_adjustment'] = round(adjustment_factor * 100, 2)
                        elif pit == third_candidate:
                            # 3着候補はスコアを上げる
                            pred['total_score'] = round(original_score * (1 + adjustment_factor * 0.5), 1)
                            pred['kimarite_flow_adjustment'] = round(adjustment_factor * 50, 2)

                    logger.debug(
                        f"Race {race_id}: 決まり手別展開予測適用 - "
                        f"2着候補: {second_candidate}号艇, 3着候補: {third_candidate}号艇"
                    )

        except Exception as e:
            logger.debug(f"Race {race_id}: 決まり手別展開予測エラー: {e}")

        return predictions

    def _apply_makuri_risk_adjustment(
        self,
        predictions: List[Dict],
        race_id: int
    ) -> List[Dict]:
        """
        P-6-2: まくりリスク評価によるスコア調整

        1コース艇のまくられリスクを評価し、
        リスクが高い場合は外コース艇のスコアを調整する。

        Args:
            predictions: 予測結果リスト（スコア順）
            race_id: レースID

        Returns:
            まくりリスク調整後の予測結果
        """
        logger = logging.getLogger(__name__)

        if self.makuri_risk_evaluator is None:
            return predictions

        if len(predictions) < 6:
            return predictions

        try:
            # レースコンテキストを取得
            import sqlite3
            conn = get_connection(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # レース情報取得
            cursor.execute("""
                SELECT r.venue_code, e.racer_rank as c1_rank, rd.st_time as c1_st
                FROM races r
                JOIN entries e ON r.id = e.race_id AND e.pit_number = 1
                LEFT JOIN race_details rd ON r.id = rd.race_id AND rd.pit_number = 1
                WHERE r.id = ?
            """, (race_id,))
            race_info = cursor.fetchone()

            if not race_info:
                return predictions

            # エントリー情報取得
            cursor.execute("""
                SELECT e.pit_number, e.racer_rank, e.avg_st, rd.st_time
                FROM entries e
                LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
                WHERE e.race_id = ?
                ORDER BY e.pit_number
            """, (race_id,))
            entries = [dict(row) for row in cursor.fetchall()]
            cursor.close()

            # レースコンテキスト作成
            race_context = {
                'venue_code': race_info['venue_code'],
                'c1_rank': race_info['c1_rank'],
                'c1_st': race_info['c1_st']
            }

            # まくりリスク評価
            risk_assessment = self.makuri_risk_evaluator.evaluate_makuri_risk(
                race_context, entries
            )

            if risk_assessment and risk_assessment.risk_level in ['high', 'medium']:
                # リスクレベルに応じた調整
                if risk_assessment.risk_level == 'high':
                    adjustment = 0.05  # 5%調整
                else:
                    adjustment = 0.03  # 3%調整

                # まくり候補のスコアを上げる
                for course, prob, _ in risk_assessment.makuri_candidates[:2]:
                    for pred in predictions:
                        if pred['pit_number'] == course:
                            original_score = pred['total_score']
                            pred['total_score'] = round(original_score * (1 + adjustment), 1)
                            pred['makuri_risk_adjustment'] = round(adjustment * 100, 2)
                            break

                # 1コースのスコアを下げる（リスクが高い場合）
                if risk_assessment.risk_level == 'high':
                    for pred in predictions:
                        if pred['pit_number'] == 1:
                            original_score = pred['total_score']
                            pred['total_score'] = round(original_score * (1 - adjustment), 1)
                            pred['makuri_risk_penalty'] = round(-adjustment * 100, 2)
                            break

                logger.debug(
                    f"Race {race_id}: まくりリスク調整適用 - "
                    f"リスク: {risk_assessment.risk_level}, "
                    f"まくり確率: {risk_assessment.makuri_prob:.1%}"
                )

        except Exception as e:
            logger.debug(f"Race {race_id}: まくりリスク評価エラー: {e}")

        return predictions


if __name__ == "__main__":
    # テスト実行
    predictor = RacePredictor()

    print("=" * 60)
    print("レース予想テスト")
    print("=" * 60)

    # テスト用レースID（実際のデータがあれば）
    test_race_id = 1

    print(f"\n【レースID {test_race_id} の予想】")
    predictions = predictor.predict_race(test_race_id)

    if predictions:
        print("\n順位 | 枠 | 選手名 | コース | 選手 | モーター | 合計 | 信頼度")
        print("-" * 70)
        for pred in predictions:
            print(f" {pred['rank_prediction']}位 | "
                  f"{pred['pit_number']}号艇 | "
                  f"{pred['racer_name']:10s} | "
                  f"{pred['course_score']:5.1f} | "
                  f"{pred['racer_score']:5.1f} | "
                  f"{pred['motor_score']:5.1f} | "
                  f"{pred['total_score']:5.1f} | "
                  f"{pred['confidence']}")

        print("\n【推奨買い目】")
        recommendations = predictor.recommend_bets(predictions)
        for bet_type, bets in recommendations.items():
            print(f"\n{bet_type}:")
            for bet in bets:
                print(f"  {bet['combination']} (信頼度: {bet['confidence']})")
    else:
        print("  データなし")

    print("\n" + "=" * 60)
    print("テスト完了")
    print("=" * 60)
