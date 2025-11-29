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
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))
from src.utils.scoring_config import ScoringConfig
from src.prediction.rule_based_engine import RuleBasedEngine
from src.database.batch_data_loader import BatchDataLoader
from config.venue_characteristics import get_venue_adjustment, get_venue_course_adjustment
from config.settings import (
    get_dynamic_weights, get_venue_type, VENUE_IN1_RATES,
    HIGH_IN_VENUES, LOW_IN_VENUES, EXTENDED_SCORE_WEIGHTS,
    EXTENDED_SCORE_MAX, EXTENDED_SCORE_MIN
)


class RacePredictor:
    """レース予想クラス"""

    def __init__(self, db_path="data/boatrace.db", custom_weights: Dict[str, float] = None,
                 mode: Optional[str] = None, use_cache: bool = False):
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

<<<<<<< Updated upstream
        weights = {
            'course_weight': dynamic_weights['course'],
            'racer_weight': dynamic_weights['racer'],
            'motor_weight': dynamic_weights['motor'],
            'rank_weight': dynamic_weights['rank'],
            'kimarite_weight': self.weights.get('kimarite_weight', 5.0),
            'grade_weight': self.weights.get('grade_weight', 5.0),
        }
=======
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
>>>>>>> Stashed changes

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
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # race_id を取得
        cursor.execute("""
            SELECT id
            FROM races
            WHERE race_date = ? AND venue_code = ? AND race_number = ?
        """, (race_date, venue_code, race_number))

        row = cursor.fetchone()
        conn.close()

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
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id
            FROM races
            WHERE race_date = ? AND venue_code = ? AND race_number = ?
        """, (race_date, venue_code, race_number))

        row = cursor.fetchone()
        conn.close()

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
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT venue_code, race_grade, race_date, race_time FROM races WHERE id = ?", (race_id,))
        race_info = cursor.fetchone()

        if not race_info:
            conn.close()
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

        conn.close()

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

        # スコア順にソート
        predictions.sort(key=lambda x: x['total_score'], reverse=True)

        # 順位予想を付与
        for rank, pred in enumerate(predictions, 1):
            pred['rank_prediction'] = rank

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
        conn = sqlite3.connect(self.db_path)
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
        conn.close()

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
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # レース情報を取得
        cursor.execute(
            "SELECT venue_code, race_date FROM races WHERE id = ?",
            (race_id,)
        )
        race_row = cursor.fetchone()
        if not race_row:
            conn.close()
            return []

        venue_code, race_date = race_row

        # 出走情報を取得
        cursor.execute("""
            SELECT e.pit_number, e.racer_number, e.racer_name, rd.actual_course
            FROM entries e
            LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
            WHERE e.race_id = ?
            ORDER BY e.pit_number
        """, (race_id,))
        entries_data = cursor.fetchall()
        conn.close()

        # エントリー情報を構築
        entries = []
        for pit, racer_num, racer_name, course in entries_data:
            entries.append({
                'pit_number': pit,
                'racer_number': racer_num,
                'racer_name': racer_name,
                'actual_course': course if course else pit
            })

        # レース情報
        race_info = {
            'venue_code': venue_code,
            'race_date': race_date
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
