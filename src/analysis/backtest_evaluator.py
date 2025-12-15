"""
バックテスト評価器 V2

新予測システム（PreInfoScorer, BeforeInfoScorer, ScoreIntegrator, AdjustmentManager）
と連携してパラメータ最適化のためのバックテスト評価を行う。

作成日: 2025-12-15
"""

import sqlite3
import logging
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
import sys

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DATABASE_PATH
from src.utils.db_connection_pool import get_connection


# ============================================================
# データクラス定義
# ============================================================

@dataclass
class BacktestConfig:
    """バックテスト設定"""
    start_date: str = None           # 開始日（YYYY-MM-DD形式）
    end_date: str = None             # 終了日（YYYY-MM-DD形式）
    period_days: int = 90            # 期間（日数）
    venue_codes: List[str] = None    # 対象会場（Noneで全会場）
    race_grades: List[str] = None    # 対象グレード（Noneで全グレード）
    min_races: int = 100             # 最低評価レース数
    include_odds: bool = True        # オッズを使用した回収率計算


@dataclass
class BacktestResult:
    """バックテスト結果"""
    # 基本統計
    total_races: int = 0
    predicted_races: int = 0

    # 的中率
    hit_count: int = 0
    hit_rate: float = 0.0

    # 2連・3連的中
    exacta_hit_count: int = 0       # 2連複的中
    exacta_hit_rate: float = 0.0
    trifecta_hit_count: int = 0     # 3連複的中
    trifecta_hit_rate: float = 0.0

    # 回収率
    total_bet: float = 0.0
    total_return: float = 0.0
    recovery_rate: float = 0.0

    # 詳細
    by_venue: Dict[str, Dict[str, float]] = field(default_factory=dict)
    by_grade: Dict[str, Dict[str, float]] = field(default_factory=dict)
    by_confidence: Dict[str, Dict[str, float]] = field(default_factory=dict)

    # メタ情報
    evaluation_time: float = 0.0
    params_used: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RaceEvaluationData:
    """レース評価用データ"""
    race_id: int
    race_date: str
    venue_code: str
    race_number: int
    race_grade: str

    # 結果
    actual_winner: int = 0           # 実際の1着艇番
    actual_second: int = 0           # 実際の2着艇番
    actual_third: int = 0            # 実際の3着艇番

    # オッズ
    win_odds: Dict[int, float] = field(default_factory=dict)  # 単勝オッズ

    # 出走情報（6艇分）
    entries: List[Dict[str, Any]] = field(default_factory=list)

    # 天候・潮位
    wind_speed: Optional[float] = None
    wave_height: Optional[float] = None
    tide_phase: Optional[str] = None


# ============================================================
# バックテスト評価器
# ============================================================

class BacktestEvaluatorV2:
    """
    V2バックテスト評価器

    新予測システムと連携してパラメータの評価を行う。
    """

    def __init__(
        self,
        db_path: str = None,
        config: BacktestConfig = None
    ):
        """
        初期化

        Args:
            db_path: データベースパス
            config: バックテスト設定
        """
        self.db_path = db_path or DATABASE_PATH
        self.config = config or BacktestConfig()
        self.logger = logging.getLogger(__name__)

        # 評価データのキャッシュ
        self._race_data_cache: List[RaceEvaluationData] = []
        self._cache_loaded = False

    # ========================================
    # データ読み込み
    # ========================================

    def load_test_data(self, force_reload: bool = False) -> int:
        """
        テスト用データを読み込む

        Args:
            force_reload: 強制再読み込み

        Returns:
            読み込んだレース数
        """
        if self._cache_loaded and not force_reload:
            return len(self._race_data_cache)

        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            # 期間の決定
            if self.config.start_date and self.config.end_date:
                date_condition = "r.race_date BETWEEN ? AND ?"
                date_params = [self.config.start_date, self.config.end_date]
            else:
                date_condition = "r.race_date >= date('now', ?)"
                date_params = [f'-{self.config.period_days} days']

            # 会場フィルター
            venue_condition = ""
            if self.config.venue_codes:
                placeholders = ','.join(['?' for _ in self.config.venue_codes])
                venue_condition = f"AND r.venue_code IN ({placeholders})"
                date_params.extend(self.config.venue_codes)

            # レース結果を取得
            query = f"""
                SELECT
                    r.id as race_id,
                    r.race_date,
                    r.venue_code,
                    r.race_number,
                    r.race_grade,
                    rc.wind_speed,
                    rc.wave_height
                FROM races r
                LEFT JOIN race_conditions rc ON r.id = rc.race_id
                WHERE {date_condition}
                  {venue_condition}
                  AND EXISTS (
                      SELECT 1 FROM results res
                      WHERE res.race_id = r.id AND res.rank = 1
                  )
                ORDER BY r.race_date DESC, r.race_number
            """

            cursor.execute(query, date_params)
            race_rows = cursor.fetchall()

            self.logger.info(f"Loading {len(race_rows)} races for backtest...")

            self._race_data_cache = []

            for row in race_rows:
                race_data = RaceEvaluationData(
                    race_id=row['race_id'],
                    race_date=row['race_date'],
                    venue_code=row['venue_code'],
                    race_number=row['race_number'],
                    race_grade=row['race_grade'] or '一般',
                    wind_speed=row['wind_speed'],
                    wave_height=row['wave_height']
                )

                # 結果を取得
                cursor.execute("""
                    SELECT pit_number, rank
                    FROM results
                    WHERE race_id = ?
                    ORDER BY CAST(rank AS INTEGER)
                    LIMIT 3
                """, (row['race_id'],))

                for res_row in cursor.fetchall():
                    # rank は文字列の可能性があるため int 変換
                    rank_val = int(res_row['rank']) if res_row['rank'] else 0
                    pit_val = int(res_row['pit_number']) if res_row['pit_number'] else 0
                    if rank_val == 1:
                        race_data.actual_winner = pit_val
                    elif rank_val == 2:
                        race_data.actual_second = pit_val
                    elif rank_val == 3:
                        race_data.actual_third = pit_val

                # オッズを取得（win_oddsテーブル）
                if self.config.include_odds:
                    cursor.execute("""
                        SELECT pit_number, odds
                        FROM win_odds
                        WHERE race_id = ?
                    """, (row['race_id'],))

                    for odds_row in cursor.fetchall():
                        race_data.win_odds[odds_row['pit_number']] = odds_row['odds'] or 0.0

                # 出走情報を取得
                cursor.execute("""
                    SELECT
                        e.pit_number,
                        e.racer_number,
                        e.racer_name,
                        e.racer_rank,
                        e.win_rate,
                        e.avg_st,
                        e.f_count,
                        e.l_count,
                        e.motor_number,
                        rd.exhibition_time,
                        rd.st_time as exhibition_st
                    FROM entries e
                    LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
                    WHERE e.race_id = ?
                    ORDER BY e.pit_number
                """, (row['race_id'],))

                for entry_row in cursor.fetchall():
                    race_data.entries.append({
                        'pit_number': entry_row['pit_number'],
                        'racer_number': entry_row['racer_number'],
                        'racer_name': entry_row['racer_name'],
                        'racer_rank': entry_row['racer_rank'],
                        'win_rate': entry_row['win_rate'] or 0.0,
                        'avg_st': entry_row['avg_st'] or 0.0,
                        'f_count': entry_row['f_count'] or 0,
                        'l_count': entry_row['l_count'] or 0,
                        'motor_number': entry_row['motor_number'],
                        'exhibition_time': entry_row['exhibition_time'],
                        'exhibition_st': entry_row['exhibition_st']
                    })

                self._race_data_cache.append(race_data)

            self._cache_loaded = True
            self.logger.info(f"Loaded {len(self._race_data_cache)} races")

            return len(self._race_data_cache)

        finally:
            cursor.close()

    # ========================================
    # 評価メソッド
    # ========================================

    def evaluate_with_predictor(
        self,
        predict_func: Callable[[RaceEvaluationData], int],
        params: Dict[str, Any] = None
    ) -> BacktestResult:
        """
        予測関数を使って評価を実行

        Args:
            predict_func: 予測関数（RaceEvaluationData -> 予測1着艇番）
            params: 使用パラメータ（記録用）

        Returns:
            バックテスト結果
        """
        if not self._cache_loaded:
            self.load_test_data()

        import time
        start_time = time.time()

        result = BacktestResult()
        result.params_used = params or {}
        result.total_races = len(self._race_data_cache)

        # 会場別・グレード別・信頼度別の集計用
        venue_stats = {}
        grade_stats = {}

        for race_data in self._race_data_cache:
            if not race_data.entries:
                continue

            result.predicted_races += 1

            # 予測実行
            try:
                predicted_winner = predict_func(race_data)
            except Exception as e:
                self.logger.warning(f"Prediction error for race {race_data.race_id}: {e}")
                continue

            # 的中判定
            is_hit = (predicted_winner == race_data.actual_winner)

            if is_hit:
                result.hit_count += 1

            # 回収率計算
            result.total_bet += 100  # 1レース100円

            if is_hit and race_data.win_odds.get(predicted_winner):
                odds = race_data.win_odds[predicted_winner]
                result.total_return += 100 * odds

            # 会場別集計
            venue = race_data.venue_code
            if venue not in venue_stats:
                venue_stats[venue] = {'hits': 0, 'total': 0, 'return': 0.0, 'bet': 0.0}
            venue_stats[venue]['total'] += 1
            venue_stats[venue]['bet'] += 100
            if is_hit:
                venue_stats[venue]['hits'] += 1
                if race_data.win_odds.get(predicted_winner):
                    venue_stats[venue]['return'] += 100 * race_data.win_odds[predicted_winner]

            # グレード別集計
            grade = race_data.race_grade
            if grade not in grade_stats:
                grade_stats[grade] = {'hits': 0, 'total': 0, 'return': 0.0, 'bet': 0.0}
            grade_stats[grade]['total'] += 1
            grade_stats[grade]['bet'] += 100
            if is_hit:
                grade_stats[grade]['hits'] += 1
                if race_data.win_odds.get(predicted_winner):
                    grade_stats[grade]['return'] += 100 * race_data.win_odds[predicted_winner]

        # 結果集計
        if result.predicted_races > 0:
            result.hit_rate = result.hit_count / result.predicted_races

        if result.total_bet > 0:
            result.recovery_rate = result.total_return / result.total_bet

        # 会場別結果
        for venue, stats in venue_stats.items():
            if stats['total'] > 0:
                result.by_venue[venue] = {
                    'hit_rate': stats['hits'] / stats['total'],
                    'recovery_rate': stats['return'] / stats['bet'] if stats['bet'] > 0 else 0.0,
                    'sample_size': stats['total']
                }

        # グレード別結果
        for grade, stats in grade_stats.items():
            if stats['total'] > 0:
                result.by_grade[grade] = {
                    'hit_rate': stats['hits'] / stats['total'],
                    'recovery_rate': stats['return'] / stats['bet'] if stats['bet'] > 0 else 0.0,
                    'sample_size': stats['total']
                }

        result.evaluation_time = time.time() - start_time

        return result

    def evaluate_with_scores(
        self,
        score_func: Callable[[RaceEvaluationData], List[Tuple[int, float]]],
        params: Dict[str, Any] = None
    ) -> BacktestResult:
        """
        スコア関数を使って評価を実行

        Args:
            score_func: スコア関数（RaceEvaluationData -> [(艇番, スコア), ...]）
            params: 使用パラメータ（記録用）

        Returns:
            バックテスト結果
        """
        def predict_func(race_data: RaceEvaluationData) -> int:
            scores = score_func(race_data)
            if not scores:
                return 1  # デフォルトは1号艇
            # スコア最高の艇番を返す
            scores.sort(key=lambda x: x[1], reverse=True)
            return scores[0][0]

        return self.evaluate_with_predictor(predict_func, params)

    # ========================================
    # 簡易評価（パラメータ直接指定）
    # ========================================

    def evaluate_params(
        self,
        params: Dict[str, float]
    ) -> BacktestResult:
        """
        パラメータを直接指定して評価

        新予測システムの各コンポーネントにパラメータを適用して評価。

        Args:
            params: 評価するパラメータ
                - venue系: course_1_base_bonus, in_strong_bonus, etc.
                - weather系: wind_threshold_strong, strong_wind_course_1_penalty, etc.
                - tide系: rising_course_1_bonus, falling_course_1_penalty, etc.
                - integration系: pre_weight, before_factor, etc.

        Returns:
            バックテスト結果
        """
        def score_func(race_data: RaceEvaluationData) -> List[Tuple[int, float]]:
            scores = []

            for entry in race_data.entries:
                score = self._calculate_score_with_params(
                    entry,
                    race_data,
                    params
                )
                scores.append((entry['pit_number'], score))

            return scores

        return self.evaluate_with_scores(score_func, params)

    def _calculate_score_with_params(
        self,
        entry: Dict[str, Any],
        race_data: RaceEvaluationData,
        params: Dict[str, float]
    ) -> float:
        """
        パラメータを適用してスコアを計算

        Args:
            entry: 出走艇情報
            race_data: レース情報
            params: 適用パラメータ

        Returns:
            計算されたスコア
        """
        score = 0.0
        pit = entry['pit_number']

        # ========================================
        # 1. ベーススコア（コース＋選手）
        # ========================================
        COURSE_SCORES = {1: 30.0, 2: 12.0, 3: 10.0, 4: 8.0, 5: 5.0, 6: 3.0}
        score += COURSE_SCORES.get(pit, 5.0)

        # 1コースボーナス
        if pit == 1:
            score += params.get('course_1_base_bonus', 5.0)

        # 級別スコア
        RANK_SCORES = {'A1': 15.0, 'A2': 10.5, 'B1': 6.0, 'B2': 1.5}
        rank = entry.get('racer_rank', 'B1')
        score += RANK_SCORES.get(rank, 6.0)

        # 1コースA1ボーナス
        if pit == 1 and rank == 'A1':
            score += params.get('course_1_a1_bonus', 5.0)

        # 1コースB級ペナルティ
        if pit == 1 and rank in ['B1', 'B2']:
            score += params.get('course_1_b_penalty', -3.0)

        # アウトコースペナルティ
        if pit >= 4:
            score += params.get('outer_course_base_penalty', -2.0)

        # 勝率スコア（win_rateは7.34のような値で7.34%を意味する）
        win_rate = entry.get('win_rate', 0.0)
        # 勝率7%以上で満点（10点）
        score += min(win_rate / 7.0, 1.0) * 10.0

        # F/Lペナルティ
        f_count = entry.get('f_count', 0)
        l_count = entry.get('l_count', 0)
        score -= f_count * 3.0 + l_count * 1.5

        # ========================================
        # 2. 会場特性補正
        # ========================================
        IN_STRONG = ['24', '18', '17', '19', '13', '07', '16', '12', '08', '09']
        IN_WEAK = ['02', '04', '03', '14']

        if pit == 1:
            if race_data.venue_code in IN_STRONG:
                score += params.get('in_strong_venue_bonus', 10.0)
            elif race_data.venue_code in IN_WEAK:
                score += params.get('in_weak_venue_penalty', -5.0)

        # ========================================
        # 3. 天候補正
        # ========================================
        wind = race_data.wind_speed or 0
        wave = race_data.wave_height or 0

        wind_threshold = params.get('wind_threshold_strong', 6.0)

        if wind >= wind_threshold:
            if pit == 1:
                score += params.get('strong_wind_course_1_penalty', -5.0)
            elif pit >= 4:
                score += params.get('strong_wind_outer_bonus', 2.5)

        wave_threshold = params.get('wave_threshold', 6)

        if wave >= wave_threshold:
            if pit == 1:
                score += params.get('high_wave_course_1_penalty', -3.0)

        # ========================================
        # 4. 潮位補正（海水会場のみ）
        # ========================================
        SEAWATER_VENUES = ['04', '08', '09', '12', '13', '14', '15', '16',
                          '17', '18', '19', '20', '21', '22', '23', '24']

        if race_data.venue_code in SEAWATER_VENUES:
            tide = race_data.tide_phase

            if tide in ['high', 'rising']:
                if pit == 1:
                    score += params.get('rising_course_1_bonus', 2.0)
                elif pit >= 4:
                    score += params.get('rising_outer_penalty', -0.5)
            elif tide in ['low', 'falling']:
                if pit == 1:
                    score += params.get('falling_course_1_penalty', -2.0)
                elif pit >= 4:
                    score += params.get('falling_outer_bonus', 1.0)

        # ========================================
        # 5. 複合条件補正
        # ========================================
        # 徳山満潮A1イン
        if (race_data.venue_code == '18' and
            race_data.tide_phase in ['high', 'rising'] and
            pit == 1 and rank == 'A1'):
            score += params.get('tokuyama_high_tide_a1_bonus', 8.0)

        # 大村B級イン
        if (race_data.venue_code == '24' and
            pit == 1 and rank in ['B1', 'B2']):
            score += params.get('omura_b_in_bonus', 3.0)

        # 戸田B級イン
        if (race_data.venue_code == '02' and
            pit == 1 and rank in ['B1', 'B2']):
            score += params.get('toda_b_in_penalty', -4.0)

        # ========================================
        # 6. 直前情報補正（あれば）
        # ========================================
        ex_time = entry.get('exhibition_time')
        if ex_time and ex_time > 0:
            STANDARD_TIME = 6.70
            time_diff = STANDARD_TIME - ex_time
            ex_adj = time_diff * 50.0  # 0.1秒差で5点
            ex_adj = max(-5.0, min(5.0, ex_adj))

            before_factor = params.get('before_factor', 1.0)
            score += ex_adj * before_factor

        return max(0.0, min(100.0, score))

    # ========================================
    # ユーティリティ
    # ========================================

    def get_race_count(self) -> int:
        """キャッシュされたレース数を取得"""
        return len(self._race_data_cache)

    def clear_cache(self):
        """キャッシュをクリア"""
        self._race_data_cache = []
        self._cache_loaded = False

    def get_summary(self, result: BacktestResult) -> str:
        """結果のサマリーを文字列で取得"""
        lines = [
            "=" * 50,
            "Backtest Result Summary",
            "=" * 50,
            f"Races: {result.predicted_races}/{result.total_races}",
            f"Hit Rate: {result.hit_rate:.2%} ({result.hit_count}/{result.predicted_races})",
            f"Recovery Rate: {result.recovery_rate:.2%}",
            f"Total Bet: {result.total_bet:,.0f}",
            f"Total Return: {result.total_return:,.0f}",
            f"Profit/Loss: {result.total_return - result.total_bet:,.0f}",
            f"Eval Time: {result.evaluation_time:.2f}s",
        ]

        if result.by_venue:
            lines.append("")
            lines.append("[By Venue]")
            for venue, stats in sorted(result.by_venue.items()):
                lines.append(
                    f"  {venue}: Hit {stats['hit_rate']:.1%}, "
                    f"Rec {stats['recovery_rate']:.1%} "
                    f"(n={stats['sample_size']})"
                )

        if result.by_grade:
            lines.append("")
            lines.append("[By Grade]")
            for grade, stats in sorted(result.by_grade.items()):
                lines.append(
                    f"  {grade}: Hit {stats['hit_rate']:.1%}, "
                    f"Rec {stats['recovery_rate']:.1%} "
                    f"(n={stats['sample_size']})"
                )

        return "\n".join(lines)


# ============================================================
# 評価関数（最適化用）
# ============================================================

class ObjectiveFunction:
    """
    最適化用の目的関数

    回収率を最大化しつつ、的中率の制約を満たすパラメータを探索。
    """

    def __init__(
        self,
        evaluator: BacktestEvaluatorV2,
        min_hit_rate: float = 0.55,
        recovery_weight: float = 0.7,
        hit_rate_weight: float = 0.3
    ):
        """
        初期化

        Args:
            evaluator: バックテスト評価器
            min_hit_rate: 最低的中率制約
            recovery_weight: 回収率の重み
            hit_rate_weight: 的中率の重み
        """
        self.evaluator = evaluator
        self.min_hit_rate = min_hit_rate
        self.recovery_weight = recovery_weight
        self.hit_rate_weight = hit_rate_weight

    def __call__(self, params: Dict[str, float]) -> float:
        """
        目的関数を計算

        Args:
            params: 評価するパラメータ

        Returns:
            目的関数値（高いほど良い）
        """
        result = self.evaluator.evaluate_params(params)

        # 制約ペナルティ
        penalty = 0.0
        if result.hit_rate < self.min_hit_rate:
            # 的中率制約を満たさない場合は大きなペナルティ
            penalty = (self.min_hit_rate - result.hit_rate) * 100

        # 目的関数 = 重み付き和 - ペナルティ
        objective = (
            self.recovery_weight * result.recovery_rate +
            self.hit_rate_weight * result.hit_rate -
            penalty
        )

        return objective

    def evaluate_detailed(self, params: Dict[str, float]) -> Dict[str, Any]:
        """
        詳細な評価結果を返す

        Args:
            params: 評価するパラメータ

        Returns:
            詳細な評価結果
        """
        result = self.evaluator.evaluate_params(params)

        constraint_satisfied = result.hit_rate >= self.min_hit_rate
        objective = self(params)

        return {
            'objective': objective,
            'hit_rate': result.hit_rate,
            'recovery_rate': result.recovery_rate,
            'constraint_satisfied': constraint_satisfied,
            'sample_size': result.predicted_races,
            'profit_loss': result.total_return - result.total_bet
        }


# ============================================================
# テスト用コード
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # テスト実行
    config = BacktestConfig(period_days=30)
    evaluator = BacktestEvaluatorV2(config=config)

    print("Loading test data...")
    count = evaluator.load_test_data()
    print(f"Loaded {count} races")

    # デフォルトパラメータで評価
    default_params = {
        'course_1_base_bonus': 5.0,
        'course_1_a1_bonus': 5.0,
        'course_1_b_penalty': -3.0,
        'outer_course_base_penalty': -2.0,
        'in_strong_venue_bonus': 10.0,
        'in_weak_venue_penalty': -5.0,
        'wind_threshold_strong': 6.0,
        'strong_wind_course_1_penalty': -5.0,
        'strong_wind_outer_bonus': 2.5,
    }

    print("\nEvaluating with default parameters...")
    result = evaluator.evaluate_params(default_params)

    print(evaluator.get_summary(result))
