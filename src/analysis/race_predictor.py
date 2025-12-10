"""
レース予想スコアリングモジュール

コース別傾向 + 選手成績 + モーター性能を統合して、
総合予想スコアと買い目推奨を提供
"""

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
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))
from src.utils.scoring_config import ScoringConfig
from src.utils.db_connection_pool import get_connection
from src.prediction.rule_based_engine import RuleBasedEngine
from config.feature_flags import is_feature_enabled
# 階層的確率モデル（条件付き確率）
try:
    from src.prediction.hierarchical_predictor import HierarchicalPredictor
    HIERARCHICAL_MODEL_AVAILABLE = True
except ImportError:
    HIERARCHICAL_MODEL_AVAILABLE = False
from src.database.batch_data_loader import BatchDataLoader
from config.venue_characteristics import get_venue_adjustment, get_venue_course_adjustment
from config.settings import (
    get_dynamic_weights, get_venue_type, VENUE_IN1_RATES,
    HIGH_IN_VENUES, LOW_IN_VENUES, EXTENDED_SCORE_WEIGHTS,
    EXTENDED_SCORE_MAX, EXTENDED_SCORE_MIN
)


# ==================================================
# BEFORE情報パターンボーナス定義
# ==================================================
# バックテスト検証済み（200レース、2025年データ）
# 基準: ベースライン55.5%を維持しつつ、該当時60-82%の高精度

BEFORE_PATTERNS_1ST = [
    # 1着予測用パターン（4パターン、全て55.5%維持確認済み）
    {
        'name': 'pre1_st1',
        'description': 'PRE1位 & ST1位',
        'multiplier': 1.411,
        'target_rank': 1,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank == 1,
    },
    {
        'name': 'pre1_ex1',
        'description': 'PRE1位 & 展示1位',
        'multiplier': 1.286,
        'target_rank': 1,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and ex_rank == 1,
    },
    {
        'name': 'pre1_ex1_3_st1_3',
        'description': 'PRE1位 & 展示1-3位 & ST1-3位',
        'multiplier': 1.328,
        'target_rank': 1,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and ex_rank <= 3 and st_rank <= 3,
    },
    {
        'name': 'pre1_st1_3',
        'description': 'PRE1位 & ST1-3位',
        'multiplier': 1.310,
        'target_rank': 1,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank <= 3,
    },
]

BEFORE_PATTERNS_2ND = [
    # 2着予測用パターン（7パターン、20%以上または+5%以上）
    {
        'name': 'pre2_3_ex1_2',
        'description': 'PRE2-3位 & 展示1-2位',
        'multiplier': 1.084,
        'target_rank': 2,
        'condition': lambda pre_rank, ex_rank, st_rank: 2 <= pre_rank <= 3 and ex_rank <= 2,
    },
    {
        'name': 'pre2_ex1_3_st1_3',
        'description': 'PRE2位 & 展示1-3位 & ST1-3位',
        'multiplier': 1.081,
        'target_rank': 2,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 2 and ex_rank <= 3 and st_rank <= 3,
    },
    {
        'name': 'ex1_3_pre2_3',
        'description': '展示1-3位 & PRE2-3位',
        'multiplier': 1.069,
        'target_rank': 2,
        'condition': lambda pre_rank, ex_rank, st_rank: ex_rank <= 3 and 2 <= pre_rank <= 3,
    },
    {
        'name': 'pre2_st1_3',
        'description': 'PRE2位 & ST1-3位',
        'multiplier': 1.064,
        'target_rank': 2,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 2 and st_rank <= 3,
    },
    {
        'name': 'pre2_ex1_3',
        'description': 'PRE2位 & 展示1-3位',
        'multiplier': 1.063,
        'target_rank': 2,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 2 and ex_rank <= 3,
    },
    {
        'name': 'ex_rank_2',
        'description': '展示2位',
        'multiplier': 1.035,
        'target_rank': 2,
        'condition': lambda pre_rank, ex_rank, st_rank: ex_rank == 2,
    },
    {
        'name': 'st_rank_2_3',
        'description': 'ST2-3位',
        'multiplier': 1.034,
        'target_rank': 2,
        'condition': lambda pre_rank, ex_rank, st_rank: 2 <= st_rank <= 3,
    },
]

BEFORE_PATTERNS_3RD = [
    # 3着予測用パターン（4パターン、20%以上または+3%以上）
    {
        'name': 'pre3_4_ex2_4',
        'description': 'PRE3-4位 & 展示2-4位',
        'multiplier': 1.032,
        'target_rank': 3,
        'condition': lambda pre_rank, ex_rank, st_rank: 3 <= pre_rank <= 4 and 2 <= ex_rank <= 4,
    },
    {
        'name': 'pre3_ex1_3',
        'description': 'PRE3位 & 展示1-3位',
        'multiplier': 1.031,
        'target_rank': 3,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 3 and ex_rank <= 3,
    },
    {
        'name': 'outer_st1_2',
        'description': 'アウトコース(4-6枠) & ST1-2位',
        'multiplier': 1.022,
        'target_rank': 3,
        'condition': lambda pre_rank, ex_rank, st_rank, pit_number=None: pit_number >= 4 and st_rank <= 2 if pit_number is not None else False,
    },
    {
        'name': 'pre3_4_ex1_3_st1_3',
        'description': 'PRE3-4位 & 展示1-3位 & ST1-3位',
        'multiplier': 1.020,
        'target_rank': 3,
        'condition': lambda pre_rank, ex_rank, st_rank: 3 <= pre_rank <= 4 and ex_rank <= 3 and st_rank <= 3,
    },
]

BEFORE_PATTERNS_TOP3 = [
    # 3着以内予測用パターン（5パターン、三連単・三連複に最適）
    {
        'name': 'pre1_3_st1_3',
        'description': 'PRE1-3位 & ST1-3位',
        'multiplier': 1.130,
        'target_rank': 'top3',
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank <= 3 and st_rank <= 3,
    },
    {
        'name': 'pre1_3_ex1_3',
        'description': 'PRE1-3位 & 展示1-3位',
        'multiplier': 1.123,
        'target_rank': 'top3',
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank <= 3 and ex_rank <= 3,
    },
    {
        'name': 'ex1_3_st1_3',
        'description': '展示1-3位 & ST1-3位',
        'multiplier': 1.108,
        'target_rank': 'top3',
        'condition': lambda pre_rank, ex_rank, st_rank: ex_rank <= 3 and st_rank <= 3,
    },
    {
        'name': 'pre1_4_ex1_2',
        'description': 'PRE1-4位 & 展示1-2位',
        'multiplier': 1.104,
        'target_rank': 'top3',
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank <= 4 and ex_rank <= 2,
    },
    {
        'name': 'ex_rank_1_2',
        'description': '展示1-2位',
        'multiplier': 1.051,
        'target_rank': 'top3',
        'condition': lambda pre_rank, ex_rank, st_rank: ex_rank <= 2,
    },
]


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

        # 階層的確率モデル（条件付き確率ベースの三連単予測）
        self.hierarchical_predictor = None
        if HIERARCHICAL_MODEL_AVAILABLE:
            try:
                self.hierarchical_predictor = HierarchicalPredictor(db_path)
            except Exception as e:
                print(f"階層的予測モデル初期化エラー: {e}")

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
        コース×ランクの実績勝率に基づくスコアを計算

        実際のデータから算出した勝率をベースに、
        コースと選手ランクの相互作用を正確に反映。

        Args:
            course: コース番号（1-6）
            racer_rank: 選手ランク（A1, A2, B1, B2）
            venue_code: 競艇場コード

        Returns:
            コース×ランクスコア（0〜course_weight）
        """
        max_score = self.weights['course_weight']

        # コース×ランクの実績勝率を取得
        base_win_rate = self.COURSE_RANK_WIN_RATES.get(
            (course, racer_rank),
            self.NATIONAL_AVG_WIN_RATES.get(course, 0.10)  # フォールバック
        )

        # 会場特性による補正（±20%程度）
        course_adjustment = get_venue_course_adjustment(venue_code, course)
        course_adjustment = max(0.80, min(1.20, course_adjustment))

        adjusted_win_rate = base_win_rate * course_adjustment

        # 勝率をスコアに変換
        # 最大勝率（1コースA1: 71.5%）で満点になるよう正規化
        MAX_WIN_RATE = 0.72
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

    def predict_race(self, race_id: int) -> List[Dict]:
        """
        レースの総合予想を実行

        Args:
            race_id: レースID

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
        # レース情報取得
        import sqlite3
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

        # 拡張スコア用にエントリー情報を取得（racer_rank, f_count, l_count, avg_st）
        cursor.execute("""
            SELECT pit_number, racer_number, racer_name, racer_rank,
                   f_count, l_count, motor_number, win_rate, avg_st
            FROM entries
            WHERE race_id = ?
            ORDER BY pit_number
        """, (race_id,))
        entry_rows = cursor.fetchall()
        entry_data = {}
        race_entries_for_matchup = []
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
                'avg_st': row['avg_st']  # 平均STを追加
            }
            entry_data[row['pit_number']] = entry_dict
            race_entries_for_matchup.append(entry_dict)

        # 天候データを取得（race_conditions または weather テーブルから）
        wind_speed = None
        wave_height = None
        wind_direction = None

        # まず race_conditions から取得を試みる（風向データを含む）
        cursor.execute("""
            SELECT wind_speed, wave_height, wind_direction FROM race_conditions WHERE race_id = ?
        """, (race_id,))
        weather_row = cursor.fetchone()

        if weather_row and weather_row['wind_speed'] is not None:
            wind_speed = weather_row['wind_speed']
            wave_height = weather_row['wave_height']
            wind_direction = weather_row['wind_direction']
        else:
            # weather テーブルから取得（wind_directionは未対応の場合あり）
            cursor.execute("""
                SELECT wind_speed, wave_height FROM weather
                WHERE venue_code = ? AND weather_date = ?
            """, (venue_code, race_date))
            weather_row = cursor.fetchone()
            if weather_row:
                wind_speed = weather_row['wind_speed']
                wave_height = weather_row['wave_height']

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
            # 潮位情報を取得（後続の_apply_tide_adjustmentと共通化）
            tide_phase = None
            if venue_code in self.tide_adjuster.TIDE_DATA_VENUES:
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
                # - 平均ST: 0-8点
                # - 展示タイム: 0-8点（新規）
                # - チルト角度: 0-3点（新規）
                # - 直近成績: 0-8点（新規）
                # 最大合計: 62点、最小: -10点
                # これを EXTENDED_WEIGHT (20点) に正規化

                raw_extended = extended_result['total_extended_score']
                max_possible = extended_result.get('max_possible_score', 62)
                # -10～62 を 0～20 に正規化
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
                max_total_buff=15.0  # 最大15点のバフ/デバフ
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
                    'session': extended_score_detail['session'],
                    'prev_race': extended_score_detail['prev_race'],
                    'matchup': extended_score_detail['matchup'],
                    'motor_extended': extended_score_detail['motor'],
                    'course_prediction': extended_score_detail['course_prediction'],
                    'course_entry': extended_score_detail.get('course_entry', {}),  # 進入傾向（新規）
                    'start_timing': extended_score_detail.get('start_timing', {}),
                    'exhibition': extended_score_detail.get('exhibition', {}),  # 展示タイム（新規）
                    'tilt': extended_score_detail.get('tilt', {}),  # チルト角度（新規）
                    'recent_form': extended_score_detail.get('recent_form', {}),  # 直近成績（新規）
                    'venue_affinity': extended_score_detail.get('venue_affinity', {}),  # 会場別勝率（新規）
                    'place_rate': extended_score_detail.get('place_rate', {})  # 連対率（新規）
                }

            predictions.append(prediction_entry)

        # 展示データ補正を適用
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

        # 潮位補正を適用（海水会場のみ）
        predictions = self._apply_tide_adjustment(
            predictions,
            venue_code,
            race_date,
            race_time
        )

        # ========================================
        # 直前情報スコアリングと統合（FINAL_SCORE = PRE_SCORE * 0.6 + BEFORE_SCORE * 0.4）
        # ========================================
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
            race_id
        )

        # ========================================
        # 確率キャリブレーション適用（機能フラグで制御）
        # ========================================
        predictions = self._apply_probability_calibration(predictions)

        # スコア順にソート（信頼度判定のため）
        predictions.sort(key=lambda x: x['total_score'], reverse=True)

        # ========================================
        # 三連対スコアを計算して追加（2着・3着予測の精度向上）
        # 信頼度Bレースのみに適用（固いレースを確実に的中させる戦略）
        # 信頼度C/Dは荒れレースも拾えるよう従来のスコアリングを維持
        # ========================================
        top_confidence = predictions[0]['confidence'] if predictions else 'E'
        if top_confidence == 'B':
            predictions = self._add_top3_scores(predictions, venue_code, race_date)

        # 再ソート（ハイブリッドスコア適用後）
        predictions.sort(key=lambda x: x['total_score'], reverse=True)

        # 順位予想を付与
        for rank, pred in enumerate(predictions, 1):
            pred['rank_prediction'] = rank

        # 階層的確率モデルによる三連単予測を追加（機能フラグとモデルがある場合のみ）
        if is_feature_enabled('hierarchical_predictor') and self.hierarchical_predictor is not None:
            try:
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

        return predictions

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

        # レース情報を取得
        import sqlite3
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT race_date FROM races WHERE id = ?",
            (race_id,)
        )
        race_date_row = cursor.fetchone()
        race_date = race_date_row[0] if race_date_row else None

        # 出走情報を準備
        cursor.execute("""
            SELECT pit_number, racer_number, racer_name
            FROM entries
            WHERE race_id = ?
            ORDER BY pit_number
        """, (race_id,))
        entries_data = cursor.fetchall()

        # actual_courseを取得
        cursor.execute("""
            SELECT pit_number, actual_course
            FROM race_details
            WHERE race_id = ?
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
        import sqlite3
        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        # レース情報を取得
        cursor.execute(
            "SELECT venue_code, race_date FROM races WHERE id = ?",
            (race_id,)
        )
        race_row = cursor.fetchone()
        if not race_row:
            cursor.close()
            return []

        venue_code, race_date = race_row

        # 風向データを取得
        cursor.execute("""
            SELECT wind_direction FROM race_conditions WHERE race_id = ?
        """, (race_id,))
        wind_row = cursor.fetchone()
        wind_direction = wind_row[0] if wind_row and wind_row[0] else ''

        # 出走情報を取得（racer_rank, genderを含む）
        # racersテーブルから性別を取得、なければ名前から推測
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

        # データ量による制限（より厳密に）
        confidence_levels = {'A': 5, 'B': 4, 'C': 3, 'D': 2, 'E': 1}
        if confidence_levels[confidence] > confidence_levels[max_confidence]:
            confidence = max_confidence

        return confidence

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
        wind_direction: Optional[str] = None
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

            # 天候補正を計算（風向も含む）
            adj_result = self.weather_adjuster.calculate_adjustment(
                venue_code,
                pit_number,  # pit_number = コース番号として使用
                wind_speed,
                wave_height,
                wind_direction
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

        バックテスト検証済み（200レース）:
        - ベースライン55.5%を維持
        - 該当時60-82%の高精度

        Args:
            predictions: 予測結果リスト（PRE_SCOREが格納されている）
            race_id: レースID

        Returns:
            パターンボーナス適用後の予測結果
        """
        import sqlite3
        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        # BEFORE情報を取得
        cursor.execute("""
            SELECT pit_number, exhibition_time, st_time
            FROM race_details
            WHERE race_id = ?
            ORDER BY pit_number
        """, (race_id,))
        before_data = cursor.fetchall()
        cursor.close()

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
                            matched_patterns.append({
                                'name': pattern['name'],
                                'description': pattern['description'],
                                'multiplier': pattern['multiplier'],
                                'target_rank': pattern['target_rank']
                            })
                            # 最も高い倍率を使用
                            if pattern['multiplier'] > final_multiplier:
                                final_multiplier = pattern['multiplier']
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
                            matched_patterns.append({
                                'name': pattern['name'],
                                'description': pattern['description'],
                                'multiplier': pattern['multiplier'],
                                'target_rank': pattern['target_rank']
                            })
                            # TOP3パターンは他より優先度低め（既に1着/2着/3着パターンがあれば使わない）
                            if len([p for p in matched_patterns if p['target_rank'] != 'top3']) == 0:
                                if pattern['multiplier'] > final_multiplier:
                                    final_multiplier = pattern['multiplier']
                    except Exception:
                        pass

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

        # 状態フラグ方式が有効かチェック（新モード・最推奨）
        use_flag_adjustment = is_feature_enabled('beforeinfo_flag_adjustment')

        # ゲーティング方式が有効かチェック（新方式：PRE拮抗時のみBEFORE使用）
        use_gated_integration = is_feature_enabled('gated_before_integration')

        # 階層的予測が有効かチェック
        use_hierarchical_prediction = is_feature_enabled('hierarchical_before_prediction')

        # 正規化統合が有効かチェック
        use_normalized_integration = is_feature_enabled('normalized_before_integration')

        # 動的統合が有効かチェック
        use_dynamic_integration = is_feature_enabled('dynamic_integration')

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

        # 状態フラグ方式の処理（最優先）
        if use_flag_adjustment:
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

        # ゲーティング方式の処理（PRE拮抗時のみBEFORE使用）
        if use_gated_integration:
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

        # 階層的予測モードの処理
        if use_hierarchical_prediction:
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
        race_id: int
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
            # エントリー情報を取得
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
                entries=entries
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
