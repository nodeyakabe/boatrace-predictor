"""
予測エンジン V2 (プロトタイプ)

新設計の予測エンジン。以下の原則に基づく：
1. 事前予想をベースとして、各要素を「加算・減算」で調整
2. プリセットや補正値を個別に管理・検証可能
3. 値の最適化を体系的に実施できる仕組み

構造:
    事前予想スコア（ベース）
    + 直前情報補正
    + 法則性補正（プリセット）
    + 会場特性補正
    = 最終スコア
"""

import sqlite3
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
import logging
import os
import sys

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from src.utils.db_connection_pool import get_connection


# ============================================================
# データクラス定義
# ============================================================

@dataclass
class RaceContext:
    """レースコンテキスト（予測に必要な全情報）"""
    race_id: int
    race_date: str
    venue_code: str
    race_number: int
    race_grade: str
    race_time: Optional[str] = None

    # 天候情報
    wind_speed: Optional[float] = None
    wind_direction: Optional[str] = None
    wave_height: Optional[float] = None
    weather_condition: Optional[str] = None
    temperature: Optional[float] = None
    water_temperature: Optional[float] = None

    # 潮位情報
    tide_phase: Optional[str] = None  # "high", "rising", "low", "falling"
    tide_level: Optional[float] = None


@dataclass
class EntryContext:
    """出走艇コンテキスト"""
    pit_number: int
    racer_number: str
    racer_name: str
    racer_rank: str  # A1, A2, B1, B2

    # 事前情報
    overall_win_rate: float = 0.0
    course_win_rate: float = 0.0
    venue_win_rate: float = 0.0
    avg_st: float = 0.0
    f_count: int = 0
    l_count: int = 0

    # モーター情報
    motor_number: Optional[str] = None
    motor_win_rate: float = 0.0
    motor_2nd_rate: float = 0.0

    # 直前情報
    exhibition_time: Optional[float] = None
    exhibition_st: Optional[float] = None
    exhibition_course: Optional[int] = None
    tilt_angle: Optional[float] = None
    prev_race_result: Optional[int] = None


@dataclass
class AdjustmentRecord:
    """補正記録"""
    category: str       # "venue", "weather", "tide", "compound", etc.
    name: str           # 補正名
    value: float        # 補正値（加算される点数）
    score_before: float # 補正前スコア
    score_after: float  # 補正後スコア
    reason: str = ""    # 補正理由


@dataclass
class PredictionResult:
    """予測結果"""
    pit_number: int
    racer_name: str
    racer_number: str

    # スコア詳細
    base_score: float           # 事前予想ベーススコア
    before_adjustment: float    # 直前情報による補正
    preset_adjustment: float    # プリセットによる補正
    venue_adjustment: float     # 会場特性による補正
    total_adjustment: float     # 全補正の合計
    final_score: float          # 最終スコア

    # 詳細記録
    adjustments: List[AdjustmentRecord] = field(default_factory=list)

    # メタ情報
    confidence: str = "C"       # A, B, C, D, E
    rank_prediction: int = 0


# ============================================================
# 予測エンジン V2
# ============================================================

class PredictionEngineV2:
    """
    新設計の予測エンジン

    構造:
        事前予想スコア（ベース）
        + 直前情報補正
        + 法則性補正（プリセット）
        + 会場特性補正
        = 最終スコア
    """

    # スコアリング定数
    MAX_SCORE = 100.0
    MIN_SCORE = 0.0

    # 補正の最大影響範囲
    MAX_BEFORE_ADJUSTMENT = 15.0    # 直前情報補正の最大値
    MAX_PRESET_ADJUSTMENT = 10.0    # プリセット補正の最大値
    MAX_VENUE_ADJUSTMENT = 10.0     # 会場補正の最大値
    MAX_TOTAL_ADJUSTMENT = 30.0     # 全補正合計の最大値

    def __init__(self, db_path: str = None, preset_loader=None):
        """
        初期化

        Args:
            db_path: データベースパス
            preset_loader: プリセットローダー（None時は内部実装を使用）
        """
        self.db_path = db_path or DATABASE_PATH
        self.preset_loader = preset_loader
        self.logger = logging.getLogger(__name__)

    # ========================================
    # メイン予測メソッド
    # ========================================

    def predict_race(self, race_id: int) -> List[PredictionResult]:
        """
        レースの予測を実行

        Args:
            race_id: レースID

        Returns:
            予測結果のリスト（スコア降順）
        """
        # 1. コンテキスト構築
        race_context = self._build_race_context(race_id)
        if race_context is None:
            return []

        entry_contexts = self._build_entry_contexts(race_id)
        if not entry_contexts:
            return []

        # 2. 各艇の予測を実行
        results = []
        for entry in entry_contexts:
            result = self._predict_entry(race_context, entry)
            results.append(result)

        # 3. スコア順にソート
        results.sort(key=lambda x: x.final_score, reverse=True)

        # 4. 順位付与
        for rank, result in enumerate(results, 1):
            result.rank_prediction = rank
            result.confidence = self._calculate_confidence(
                result.final_score,
                result.adjustments
            )

        return results

    def _predict_entry(
        self,
        race_context: RaceContext,
        entry: EntryContext
    ) -> PredictionResult:
        """
        単一出走艇の予測を実行

        Args:
            race_context: レースコンテキスト
            entry: 出走艇コンテキスト

        Returns:
            予測結果
        """
        adjustments = []

        # ========================================
        # Step 1: 事前予想ベーススコア計算
        # ========================================
        base_score = self.calculate_base_score(
            entry,
            race_context.venue_code
        )

        current_score = base_score

        # ========================================
        # Step 2: 直前情報補正
        # ========================================
        before_adj, before_records = self.apply_realtime_adjustment(
            current_score,
            entry
        )
        current_score += before_adj
        adjustments.extend(before_records)

        # ========================================
        # Step 3: プリセット・法則性補正
        # ========================================
        preset_adj, preset_records = self.apply_preset_rules(
            current_score,
            race_context,
            entry
        )
        current_score += preset_adj
        adjustments.extend(preset_records)

        # ========================================
        # Step 4: 会場特性補正
        # ========================================
        venue_adj, venue_records = self.apply_venue_adjustment(
            current_score,
            race_context.venue_code,
            entry.pit_number,
            entry.racer_rank
        )
        current_score += venue_adj
        adjustments.extend(venue_records)

        # ========================================
        # Step 5: 最終スコア計算
        # ========================================
        total_adjustment = before_adj + preset_adj + venue_adj

        # 全体の補正上限を適用
        if abs(total_adjustment) > self.MAX_TOTAL_ADJUSTMENT:
            scale = self.MAX_TOTAL_ADJUSTMENT / abs(total_adjustment)
            total_adjustment *= scale
            current_score = base_score + total_adjustment

        # スコア範囲を制限
        final_score = max(self.MIN_SCORE, min(self.MAX_SCORE, current_score))

        return PredictionResult(
            pit_number=entry.pit_number,
            racer_name=entry.racer_name,
            racer_number=entry.racer_number,
            base_score=round(base_score, 1),
            before_adjustment=round(before_adj, 1),
            preset_adjustment=round(preset_adj, 1),
            venue_adjustment=round(venue_adj, 1),
            total_adjustment=round(total_adjustment, 1),
            final_score=round(final_score, 1),
            adjustments=adjustments
        )

    # ========================================
    # スコア計算メソッド
    # ========================================

    def calculate_base_score(
        self,
        entry: EntryContext,
        venue_code: str
    ) -> float:
        """
        事前予想スコア（展示前の情報のみ）

        Args:
            entry: 出走艇コンテキスト
            venue_code: 会場コード

        Returns:
            ベーススコア（0-100）
        """
        score = 0.0

        # ========================================
        # 1. コーススコア（30点満点）
        # ========================================
        COURSE_BASE_SCORES = {
            1: 30.0,  # 1コースは最大30点
            2: 12.0,
            3: 10.0,
            4: 8.0,
            5: 5.0,
            6: 3.0,
        }
        course_score = COURSE_BASE_SCORES.get(entry.pit_number, 5.0)
        score += course_score

        # ========================================
        # 2. 選手スコア（35点満点）
        # ========================================
        # 級別スコア（15点）
        RANK_SCORES = {
            'A1': 15.0,
            'A2': 10.5,
            'B1': 6.0,
            'B2': 1.5,
        }
        rank_score = RANK_SCORES.get(entry.racer_rank, 6.0)
        score += rank_score

        # 勝率スコア（10点）
        # 勝率7%以上で満点
        win_rate_score = min(entry.overall_win_rate / 0.07, 1.0) * 10.0
        score += win_rate_score

        # コース別勝率スコア（5点）
        course_win_score = min(entry.course_win_rate / 0.10, 1.0) * 5.0
        score += course_win_score

        # 当地勝率スコア（5点）
        venue_win_score = min(entry.venue_win_rate / 0.08, 1.0) * 5.0
        score += venue_win_score

        # ========================================
        # 3. モータースコア（15点満点）
        # ========================================
        # モーター2連率スコア（10点）
        # 2連率40%以上で満点
        motor_2nd_score = min(entry.motor_2nd_rate / 0.40, 1.0) * 10.0
        score += motor_2nd_score

        # モーター勝率スコア（5点）
        motor_win_score = min(entry.motor_win_rate / 0.15, 1.0) * 5.0
        score += motor_win_score

        # ========================================
        # 4. ST関連スコア（10点満点）
        # ========================================
        # 平均STスコア（早いほど高得点）
        # ST 0.12秒が最適、0.20秒以上で大幅減点
        if entry.avg_st and entry.avg_st > 0:
            if entry.avg_st <= 0.12:
                st_score = 10.0
            elif entry.avg_st <= 0.15:
                st_score = 8.0
            elif entry.avg_st <= 0.18:
                st_score = 6.0
            elif entry.avg_st <= 0.20:
                st_score = 4.0
            else:
                st_score = 2.0
        else:
            st_score = 5.0  # データなしは中間値

        score += st_score

        # ========================================
        # 5. F/Lペナルティ（最大-10点）
        # ========================================
        fl_penalty = 0.0
        fl_penalty -= entry.f_count * 3.0  # F1回で-3点
        fl_penalty -= entry.l_count * 1.5  # L1回で-1.5点
        fl_penalty = max(-10.0, fl_penalty)

        score += fl_penalty

        return score

    def apply_realtime_adjustment(
        self,
        base_score: float,
        entry: EntryContext
    ) -> Tuple[float, List[AdjustmentRecord]]:
        """
        直前情報による補正

        Args:
            base_score: 現在のスコア
            entry: 出走艇コンテキスト

        Returns:
            (補正値, 補正記録リスト)
        """
        total_adj = 0.0
        records = []

        current_score = base_score

        # ========================================
        # 展示タイム補正
        # ========================================
        if entry.exhibition_time is not None:
            # 展示タイムが良い（速い）ほど加点
            # 6.70秒を基準、0.01秒ごとに±0.5点
            STANDARD_TIME = 6.70
            time_diff = STANDARD_TIME - entry.exhibition_time
            ex_adj = time_diff * 50.0  # 0.1秒差で5点
            ex_adj = max(-5.0, min(5.0, ex_adj))

            if ex_adj != 0:
                total_adj += ex_adj
                records.append(AdjustmentRecord(
                    category="before",
                    name="展示タイム補正",
                    value=ex_adj,
                    score_before=current_score,
                    score_after=current_score + ex_adj,
                    reason=f"展示タイム {entry.exhibition_time:.2f}秒"
                ))
                current_score += ex_adj

        # ========================================
        # 展示ST補正
        # ========================================
        if entry.exhibition_st is not None:
            # 展示STが早いほど加点
            # 0.10秒以下: +4点, 0.15秒以下: +2点, 0.20秒以上: -2点
            if entry.exhibition_st <= 0.10:
                st_adj = 4.0
            elif entry.exhibition_st <= 0.15:
                st_adj = 2.0
            elif entry.exhibition_st <= 0.18:
                st_adj = 0.0
            elif entry.exhibition_st <= 0.22:
                st_adj = -2.0
            else:
                st_adj = -4.0

            if st_adj != 0:
                total_adj += st_adj
                records.append(AdjustmentRecord(
                    category="before",
                    name="展示ST補正",
                    value=st_adj,
                    score_before=current_score,
                    score_after=current_score + st_adj,
                    reason=f"展示ST {entry.exhibition_st:.2f}秒"
                ))
                current_score += st_adj

        # ========================================
        # 前走成績補正
        # ========================================
        if entry.prev_race_result is not None:
            # 前走1着: +3点, 2着: +1点, 5-6着: -1点
            if entry.prev_race_result == 1:
                prev_adj = 3.0
            elif entry.prev_race_result == 2:
                prev_adj = 1.0
            elif entry.prev_race_result >= 5:
                prev_adj = -1.0
            else:
                prev_adj = 0.0

            if prev_adj != 0:
                total_adj += prev_adj
                records.append(AdjustmentRecord(
                    category="before",
                    name="前走成績補正",
                    value=prev_adj,
                    score_before=current_score,
                    score_after=current_score + prev_adj,
                    reason=f"前走{entry.prev_race_result}着"
                ))
                current_score += prev_adj

        # 補正上限を適用
        if abs(total_adj) > self.MAX_BEFORE_ADJUSTMENT:
            scale = self.MAX_BEFORE_ADJUSTMENT / abs(total_adj)
            total_adj *= scale

        return total_adj, records

    def apply_preset_rules(
        self,
        base_score: float,
        race_context: RaceContext,
        entry: EntryContext
    ) -> Tuple[float, List[AdjustmentRecord]]:
        """
        プリセット・法則性による補正

        Args:
            base_score: 現在のスコア
            race_context: レースコンテキスト
            entry: 出走艇コンテキスト

        Returns:
            (補正値, 補正記録リスト)
        """
        total_adj = 0.0
        records = []
        current_score = base_score

        # ========================================
        # 天候補正
        # ========================================
        weather_adj = self._apply_weather_preset(
            race_context.venue_code,
            entry.pit_number,
            race_context.wind_speed,
            race_context.wind_direction,
            race_context.wave_height
        )
        if weather_adj != 0:
            total_adj += weather_adj
            records.append(AdjustmentRecord(
                category="preset",
                name="天候補正",
                value=weather_adj,
                score_before=current_score,
                score_after=current_score + weather_adj,
                reason=f"風速{race_context.wind_speed}m, 波高{race_context.wave_height}cm"
            ))
            current_score += weather_adj

        # ========================================
        # 潮位補正
        # ========================================
        tide_adj = self._apply_tide_preset(
            race_context.venue_code,
            entry.pit_number,
            race_context.tide_phase
        )
        if tide_adj != 0:
            total_adj += tide_adj
            records.append(AdjustmentRecord(
                category="preset",
                name="潮位補正",
                value=tide_adj,
                score_before=current_score,
                score_after=current_score + tide_adj,
                reason=f"潮位: {race_context.tide_phase}"
            ))
            current_score += tide_adj

        # ========================================
        # 複合条件補正
        # ========================================
        compound_adj, compound_name = self._apply_compound_preset(
            race_context,
            entry
        )
        if compound_adj != 0:
            total_adj += compound_adj
            records.append(AdjustmentRecord(
                category="preset",
                name="複合条件補正",
                value=compound_adj,
                score_before=current_score,
                score_after=current_score + compound_adj,
                reason=compound_name
            ))
            current_score += compound_adj

        # 補正上限を適用
        if abs(total_adj) > self.MAX_PRESET_ADJUSTMENT:
            scale = self.MAX_PRESET_ADJUSTMENT / abs(total_adj)
            total_adj *= scale

        return total_adj, records

    def apply_venue_adjustment(
        self,
        base_score: float,
        venue_code: str,
        course: int,
        racer_rank: str
    ) -> Tuple[float, List[AdjustmentRecord]]:
        """
        会場特性による補正

        Args:
            base_score: 現在のスコア
            venue_code: 会場コード
            course: コース番号
            racer_rank: 選手ランク

        Returns:
            (補正値, 補正記録リスト)
        """
        total_adj = 0.0
        records = []
        current_score = base_score

        # ========================================
        # 会場別イン強度補正
        # ========================================
        # イン強会場: 大村(24), 徳山(18), 宮島(17), 下関(19), 尼崎(13), 蒲郡(07)
        # イン弱会場: 戸田(02), 平和島(04), 江戸川(03)
        IN_STRONG_VENUES = ['24', '18', '17', '19', '13', '07', '16', '12', '08', '09']
        IN_WEAK_VENUES = ['02', '04', '03', '14']

        if course == 1:
            if venue_code in IN_STRONG_VENUES:
                in_adj = 5.0  # イン強会場では1コースに+5点
                reason = "イン強会場ボーナス"
            elif venue_code in IN_WEAK_VENUES:
                in_adj = -3.0  # イン弱会場では1コースに-3点
                reason = "イン弱会場ペナルティ"
            else:
                in_adj = 0.0
                reason = ""

            if in_adj != 0:
                total_adj += in_adj
                records.append(AdjustmentRecord(
                    category="venue",
                    name="会場イン強度補正",
                    value=in_adj,
                    score_before=current_score,
                    score_after=current_score + in_adj,
                    reason=reason
                ))
                current_score += in_adj

        # ========================================
        # 会場別ランク補正
        # ========================================
        # 特定会場ではランクの影響が異なる
        # 例: 大村ではB級でもインなら期待できる
        if venue_code == '24' and course == 1 and racer_rank in ['B1', 'B2']:
            rank_adj = 3.0
            total_adj += rank_adj
            records.append(AdjustmentRecord(
                category="venue",
                name="大村B級イン補正",
                value=rank_adj,
                score_before=current_score,
                score_after=current_score + rank_adj,
                reason="大村はB級でもインなら期待できる"
            ))
            current_score += rank_adj

        # 例: 戸田ではB級のインは厳しい
        elif venue_code == '02' and course == 1 and racer_rank in ['B1', 'B2']:
            rank_adj = -4.0
            total_adj += rank_adj
            records.append(AdjustmentRecord(
                category="venue",
                name="戸田B級イン補正",
                value=rank_adj,
                score_before=current_score,
                score_after=current_score + rank_adj,
                reason="戸田はB級のインが不利"
            ))
            current_score += rank_adj

        # 補正上限を適用
        if abs(total_adj) > self.MAX_VENUE_ADJUSTMENT:
            scale = self.MAX_VENUE_ADJUSTMENT / abs(total_adj)
            total_adj *= scale

        return total_adj, records

    # ========================================
    # プリセット適用ヘルパー
    # ========================================

    def _apply_weather_preset(
        self,
        venue_code: str,
        course: int,
        wind_speed: Optional[float],
        wind_direction: Optional[str],
        wave_height: Optional[float]
    ) -> float:
        """天候プリセットによる補正値を計算"""
        if wind_speed is None:
            return 0.0

        adj = 0.0

        # 強風補正（6m/s以上）
        if wind_speed >= 6:
            if course == 1:
                # 会場別ペナルティ
                WIND_PENALTIES = {
                    '08': -10.0,  # 常滑（風の影響大）
                    '02': -6.0,   # 戸田
                    '10': -5.0,   # 三国
                    '03': -5.0,   # 江戸川
                }
                adj += WIND_PENALTIES.get(venue_code, -3.0)
            elif course >= 4:
                # アウトコースはボーナス
                adj += 2.0

        # 高波補正（6cm以上）
        if wave_height and wave_height >= 6:
            if course == 1:
                adj -= 2.0
            elif course >= 4:
                adj += 1.0

        # 風向補正
        if wind_direction:
            HEADWIND = ['北', '北北西', '北西', '北北東', '北東']
            TAILWIND = ['南', '南南西', '南西', '南南東', '南東']

            if wind_direction in HEADWIND:
                # 向かい風はイン有利
                if course == 1:
                    adj += 1.0
            elif wind_direction in TAILWIND:
                # 追い風はまくり有利
                if course == 1:
                    adj -= 1.0
                elif course in [3, 4]:
                    adj += 1.0

        return adj

    def _apply_tide_preset(
        self,
        venue_code: str,
        course: int,
        tide_phase: Optional[str]
    ) -> float:
        """潮位プリセットによる補正値を計算"""
        if tide_phase is None:
            return 0.0

        # 海水会場のみ適用
        SEAWATER_VENUES = [
            '04', '08', '09', '12', '13', '14', '15', '16',
            '17', '18', '19', '20', '21', '22', '23', '24'
        ]

        if venue_code not in SEAWATER_VENUES:
            return 0.0

        adj = 0.0

        if tide_phase in ['high', 'rising']:
            # 満潮/上げ潮はイン有利
            if course == 1:
                adj += 2.0
            elif course >= 4:
                adj -= 0.5
        elif tide_phase in ['low', 'falling']:
            # 干潮/下げ潮はまくり有利
            if course == 1:
                adj -= 1.5
            elif course in [3, 4]:
                adj += 1.0

        # 会場別特殊補正
        if venue_code == '18' and tide_phase == 'high' and course == 1:
            adj += 2.0  # 徳山は満潮時のインが特に強い

        return adj

    def _apply_compound_preset(
        self,
        race_context: RaceContext,
        entry: EntryContext
    ) -> Tuple[float, str]:
        """
        複合条件プリセットによる補正値を計算

        Returns:
            (補正値, ルール名)
        """
        # ========================================
        # 徳山満潮A1イン（鉄板パターン）
        # ========================================
        if (race_context.venue_code == '18' and
            race_context.tide_phase in ['high', 'rising'] and
            entry.pit_number == 1 and
            entry.racer_rank == 'A1'):
            return 8.0, "徳山満潮A1イン"

        # ========================================
        # 大村アウトA1（厳しいパターン）
        # ========================================
        if (race_context.venue_code == '24' and
            entry.pit_number >= 5 and
            entry.racer_rank == 'A1'):
            return -4.0, "大村アウトA1"

        # ========================================
        # 戸田2コース差し有利
        # ========================================
        if (race_context.venue_code == '02' and
            entry.pit_number == 2 and
            entry.racer_rank in ['A1', 'A2']):
            return 3.0, "戸田2コースA級"

        return 0.0, ""

    # ========================================
    # ユーティリティメソッド
    # ========================================

    def _calculate_confidence(
        self,
        final_score: float,
        adjustments: List[AdjustmentRecord]
    ) -> str:
        """信頼度を計算"""
        if final_score >= 75:
            return 'A'
        elif final_score >= 65:
            return 'B'
        elif final_score >= 55:
            return 'C'
        elif final_score >= 45:
            return 'D'
        else:
            return 'E'

    def _build_race_context(self, race_id: int) -> Optional[RaceContext]:
        """レースコンテキストを構築"""
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            # レース基本情報
            cursor.execute("""
                SELECT venue_code, race_number, race_grade, race_date, race_time
                FROM races WHERE id = ?
            """, (race_id,))
            race_row = cursor.fetchone()

            if not race_row:
                return None

            context = RaceContext(
                race_id=race_id,
                race_date=race_row['race_date'],
                venue_code=race_row['venue_code'],
                race_number=race_row['race_number'],
                race_grade=race_row['race_grade'] or '一般',
                race_time=race_row['race_time']
            )

            # 天候情報
            cursor.execute("""
                SELECT wind_speed, wind_direction, wave_height, weather, temperature, water_temperature
                FROM race_conditions WHERE race_id = ?
            """, (race_id,))
            weather_row = cursor.fetchone()

            if weather_row:
                context.wind_speed = weather_row['wind_speed']
                context.wind_direction = weather_row['wind_direction']
                context.wave_height = weather_row['wave_height']
                context.weather_condition = weather_row['weather']
                context.temperature = weather_row['temperature']
                context.water_temperature = weather_row['water_temperature']

            return context

        finally:
            cursor.close()

    def _build_entry_contexts(self, race_id: int) -> List[EntryContext]:
        """出走艇コンテキストを構築"""
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            # 出走情報
            cursor.execute("""
                SELECT e.pit_number, e.racer_number, e.racer_name, e.racer_rank,
                       e.win_rate, e.avg_st, e.f_count, e.l_count, e.motor_number
                FROM entries e
                WHERE e.race_id = ?
                ORDER BY e.pit_number
            """, (race_id,))
            entry_rows = cursor.fetchall()

            contexts = []
            for row in entry_rows:
                ctx = EntryContext(
                    pit_number=row['pit_number'],
                    racer_number=str(row['racer_number']),
                    racer_name=row['racer_name'] or '',
                    racer_rank=row['racer_rank'] or 'B1',
                    overall_win_rate=row['win_rate'] or 0.0,
                    avg_st=row['avg_st'] or 0.0,
                    f_count=row['f_count'] or 0,
                    l_count=row['l_count'] or 0,
                    motor_number=row['motor_number']
                )

                # 直前情報（race_details）を取得
                cursor.execute("""
                    SELECT exhibition_time, st_time
                    FROM race_details
                    WHERE race_id = ? AND pit_number = ?
                """, (race_id, row['pit_number']))
                detail_row = cursor.fetchone()

                if detail_row:
                    ctx.exhibition_time = detail_row['exhibition_time']
                    ctx.exhibition_st = detail_row['st_time']

                contexts.append(ctx)

            return contexts

        finally:
            cursor.close()

    # ========================================
    # デバッグ・可視化メソッド
    # ========================================

    def get_prediction_breakdown(self, race_id: int) -> Dict[str, Any]:
        """
        予測の詳細な内訳を取得（デバッグ用）

        Args:
            race_id: レースID

        Returns:
            予測内訳の辞書
        """
        results = self.predict_race(race_id)

        breakdown = {
            'race_id': race_id,
            'predictions': []
        }

        for result in results:
            entry_breakdown = {
                'pit_number': result.pit_number,
                'racer_name': result.racer_name,
                'final_score': result.final_score,
                'confidence': result.confidence,
                'rank_prediction': result.rank_prediction,
                'score_breakdown': {
                    'base_score': result.base_score,
                    'before_adjustment': result.before_adjustment,
                    'preset_adjustment': result.preset_adjustment,
                    'venue_adjustment': result.venue_adjustment,
                    'total_adjustment': result.total_adjustment
                },
                'adjustments': [
                    {
                        'category': adj.category,
                        'name': adj.name,
                        'value': adj.value,
                        'reason': adj.reason
                    }
                    for adj in result.adjustments
                ]
            }
            breakdown['predictions'].append(entry_breakdown)

        return breakdown


# ============================================================
# テスト用コード
# ============================================================

if __name__ == "__main__":
    # 簡易テスト
    engine = PredictionEngineV2()

    # 最新のレースIDを取得してテスト
    conn = get_connection(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM races ORDER BY race_date DESC, race_number DESC LIMIT 1")
    row = cursor.fetchone()
    cursor.close()

    if row:
        race_id = row[0]
        print(f"Testing with race_id: {race_id}")

        results = engine.predict_race(race_id)

        print("\n=== 予測結果 ===")
        for result in results:
            print(f"{result.rank_prediction}位予測: {result.pit_number}号艇 "
                  f"{result.racer_name} "
                  f"スコア: {result.final_score} "
                  f"(ベース: {result.base_score}, "
                  f"補正: {result.total_adjustment:+.1f}) "
                  f"信頼度: {result.confidence}")

        # 詳細内訳
        breakdown = engine.get_prediction_breakdown(race_id)
        print("\n=== 詳細内訳（1位予測艇） ===")
        top = breakdown['predictions'][0]
        print(f"ベーススコア: {top['score_breakdown']['base_score']}")
        print(f"直前情報補正: {top['score_breakdown']['before_adjustment']:+.1f}")
        print(f"プリセット補正: {top['score_breakdown']['preset_adjustment']:+.1f}")
        print(f"会場補正: {top['score_breakdown']['venue_adjustment']:+.1f}")
        print("適用された補正:")
        for adj in top['adjustments']:
            print(f"  - {adj['name']}: {adj['value']:+.1f} ({adj['reason']})")
