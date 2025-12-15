"""
補正値統一管理モジュール（AdjustmentManager）

全ての補正を加算・減算方式で統一管理し、
補正履歴の完全トレースを可能にする。

使用例:
    from src.analysis.adjustment_manager import AdjustmentManager

    manager = AdjustmentManager()

    # 補正を適用
    final_score, records = manager.apply_all_adjustments(
        base_score=50.0,
        context=RaceContext(
            venue_code='24',
            course=1,
            racer_rank='A1',
            wind_speed=8.0,
            wave_height=3,
            wind_direction='北',
            tide_phase='rising'
        )
    )

    # 補正履歴を確認
    for record in records:
        print(f"{record.category}: {record.adjustment:+.1f} ({record.reason})")
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# プリセットローダーをインポート
try:
    from src.utils.preset_loader import get_preset_loader
    PRESET_AVAILABLE = True
except ImportError:
    PRESET_AVAILABLE = False


@dataclass
class RaceContext:
    """レースコンテキスト（補正計算に必要な情報）"""
    venue_code: str
    course: int
    racer_rank: str = 'B1'
    pit_number: Optional[int] = None

    # 天候情報
    wind_speed: Optional[float] = None
    wave_height: Optional[float] = None
    wind_direction: Optional[str] = None
    temperature: Optional[float] = None
    water_temperature: Optional[float] = None

    # 潮位情報
    tide_phase: Optional[str] = None  # 'rising', 'falling', 'high', 'low'
    sea_level_cm: Optional[float] = None

    # レース情報
    race_grade: str = '一般'
    race_date: Optional[str] = None
    race_time: Optional[str] = None


@dataclass
class AdjustmentRecord:
    """補正記録"""
    category: str          # カテゴリ（'venue', 'weather', 'tide', 'compound'）
    subcategory: str       # サブカテゴリ（'course_1_bonus', 'strong_wind_penalty'等）
    adjustment: float      # 補正値（点）
    reason: str            # 補正理由
    score_before: float    # 補正前スコア
    score_after: float     # 補正後スコア
    confidence: float = 1.0  # 信頼度（0-1）
    source: str = 'preset'   # 補正値のソース（'preset', 'calculated', 'override'）


class AdjustmentManager:
    """補正値統一管理クラス"""

    # 補正値の範囲制限
    MIN_SINGLE_ADJUSTMENT = -20.0  # 単一補正の最小値
    MAX_SINGLE_ADJUSTMENT = 20.0   # 単一補正の最大値
    MAX_TOTAL_ADJUSTMENT = 30.0    # 合計補正の最大値
    MIN_TOTAL_ADJUSTMENT = -30.0   # 合計補正の最小値

    # スコア範囲
    MIN_SCORE = 0.0
    MAX_SCORE = 100.0

    def __init__(self, use_preset: bool = True):
        """
        初期化

        Args:
            use_preset: プリセットを使用するか（False時はデフォルト値）
        """
        self.use_preset = use_preset and PRESET_AVAILABLE
        self._loader = get_preset_loader() if self.use_preset else None

    def apply_all_adjustments(
        self,
        base_score: float,
        context: RaceContext
    ) -> Tuple[float, List[AdjustmentRecord]]:
        """
        全補正を適用

        Args:
            base_score: ベーススコア
            context: レースコンテキスト

        Returns:
            (最終スコア, 補正記録リスト)
        """
        records = []
        score = base_score

        # 1. 会場特性補正
        score, venue_records = self._apply_venue_adjustment(score, context)
        records.extend(venue_records)

        # 2. 天候補正
        score, weather_records = self._apply_weather_adjustment(score, context)
        records.extend(weather_records)

        # 3. 潮位補正
        score, tide_records = self._apply_tide_adjustment(score, context)
        records.extend(tide_records)

        # 4. 複合条件補正（将来拡張用）
        # score, compound_records = self._apply_compound_adjustment(score, context)
        # records.extend(compound_records)

        # スコア範囲を制限
        final_score = max(self.MIN_SCORE, min(self.MAX_SCORE, score))

        # 範囲制限による調整を記録
        if final_score != score:
            records.append(AdjustmentRecord(
                category='system',
                subcategory='score_clamp',
                adjustment=final_score - score,
                reason=f'スコア範囲制限({self.MIN_SCORE}-{self.MAX_SCORE})',
                score_before=score,
                score_after=final_score,
                source='system'
            ))

        return final_score, records

    def _apply_venue_adjustment(
        self,
        score: float,
        context: RaceContext
    ) -> Tuple[float, List[AdjustmentRecord]]:
        """会場特性補正を適用"""
        records = []

        if not self.use_preset:
            return score, records

        # 1コース基本ボーナス
        if context.course == 1:
            bonus = self._loader.get_venue_adjustment(
                context.venue_code,
                'course_1_base_bonus',
                default=0.0
            )
            if bonus != 0:
                new_score = score + bonus
                records.append(AdjustmentRecord(
                    category='venue',
                    subcategory='course_1_base_bonus',
                    adjustment=bonus,
                    reason=f'1コース基本ボーナス（会場{context.venue_code}）',
                    score_before=score,
                    score_after=new_score
                ))
                score = new_score

        # A1選手の1コースボーナス
        if context.course == 1 and context.racer_rank == 'A1':
            bonus = self._loader.get_venue_adjustment(
                context.venue_code,
                'course_1_a1_bonus',
                default=0.0
            )
            if bonus != 0:
                new_score = score + bonus
                records.append(AdjustmentRecord(
                    category='venue',
                    subcategory='course_1_a1_bonus',
                    adjustment=bonus,
                    reason='1コースA1選手ボーナス',
                    score_before=score,
                    score_after=new_score
                ))
                score = new_score

        # B級選手の1コースペナルティ
        if context.course == 1 and context.racer_rank in ['B1', 'B2']:
            penalty = self._loader.get_venue_adjustment(
                context.venue_code,
                'course_1_b_penalty',
                default=0.0
            )
            if penalty != 0:
                new_score = score + penalty
                records.append(AdjustmentRecord(
                    category='venue',
                    subcategory='course_1_b_penalty',
                    adjustment=penalty,
                    reason='1コースB級選手ペナルティ',
                    score_before=score,
                    score_after=new_score
                ))
                score = new_score

        # アウトコース基本ペナルティ（大村等）
        if context.course >= 4:
            penalty = self._loader.get_venue_adjustment(
                context.venue_code,
                'outer_course_base_penalty',
                default=0.0
            )
            if penalty != 0:
                new_score = score + penalty
                records.append(AdjustmentRecord(
                    category='venue',
                    subcategory='outer_course_base_penalty',
                    adjustment=penalty,
                    reason=f'{context.course}コース基本ペナルティ',
                    score_before=score,
                    score_after=new_score
                ))
                score = new_score

        return score, records

    def _apply_weather_adjustment(
        self,
        score: float,
        context: RaceContext
    ) -> Tuple[float, List[AdjustmentRecord]]:
        """天候補正を適用"""
        records = []

        if not self.use_preset:
            return score, records

        if context.wind_speed is None:
            return score, records

        # 風速カテゴリを取得
        wind_category = self._loader.get_wind_category(context.wind_speed)

        # 波高カテゴリを取得
        wave_category = None
        if context.wave_height is not None:
            wave_category = self._loader.get_wave_category(context.wave_height)

        # 天候補正を取得
        weather_adj = self._loader.get_weather_adjustment(
            context.venue_code,
            wind_category,
            wave_category,
            context.wind_direction
        )

        # コース別の補正を適用
        course_key = f'course_{context.course}_penalty'
        if course_key in weather_adj:
            penalty = weather_adj[course_key]
            new_score = score + penalty
            records.append(AdjustmentRecord(
                category='weather',
                subcategory=course_key,
                adjustment=penalty,
                reason=f'{wind_category}風{context.course}コースペナルティ',
                score_before=score,
                score_after=new_score
            ))
            score = new_score

        course_bonus_key = f'course_{context.course}_bonus'
        if course_bonus_key in weather_adj:
            bonus = weather_adj[course_bonus_key]
            new_score = score + bonus
            records.append(AdjustmentRecord(
                category='weather',
                subcategory=course_bonus_key,
                adjustment=bonus,
                reason=f'{wind_category}風{context.course}コースボーナス',
                score_before=score,
                score_after=new_score
            ))
            score = new_score

        # 暴風時の特殊補正
        if 'storm_course_1_adjustment' in weather_adj and context.course == 1:
            storm_adj = weather_adj['storm_course_1_adjustment']
            new_score = score + storm_adj
            records.append(AdjustmentRecord(
                category='weather',
                subcategory='storm_venue_wind',
                adjustment=storm_adj,
                reason=f'暴風{context.wind_direction}（会場{context.venue_code}）',
                score_before=score,
                score_after=new_score,
                confidence=0.9
            ))
            score = new_score

        return score, records

    def _apply_tide_adjustment(
        self,
        score: float,
        context: RaceContext
    ) -> Tuple[float, List[AdjustmentRecord]]:
        """潮位補正を適用"""
        records = []

        if not self.use_preset:
            return score, records

        if context.tide_phase is None:
            return score, records

        # 潮位補正が適用される会場かチェック
        if not self._loader.is_tide_applicable(context.venue_code):
            return score, records

        # 潮位補正を取得
        adj = self._loader.get_tide_adjustment(
            context.venue_code,
            context.tide_phase,
            context.course
        )

        if adj != 0:
            new_score = score + adj
            records.append(AdjustmentRecord(
                category='tide',
                subcategory=f'{context.tide_phase}_course_{context.course}',
                adjustment=adj,
                reason=f'{context.tide_phase}{context.course}コース補正',
                score_before=score,
                score_after=new_score
            ))
            score = new_score

        return score, records

    def get_adjustment_summary(
        self,
        records: List[AdjustmentRecord]
    ) -> Dict:
        """
        補正記録のサマリーを取得

        Args:
            records: 補正記録リスト

        Returns:
            カテゴリ別の補正合計と詳細
        """
        summary = {
            'total_adjustment': 0.0,
            'by_category': {},
            'record_count': len(records)
        }

        for record in records:
            summary['total_adjustment'] += record.adjustment

            if record.category not in summary['by_category']:
                summary['by_category'][record.category] = {
                    'total': 0.0,
                    'details': []
                }

            summary['by_category'][record.category]['total'] += record.adjustment
            summary['by_category'][record.category]['details'].append({
                'subcategory': record.subcategory,
                'adjustment': record.adjustment,
                'reason': record.reason
            })

        return summary

    def format_adjustment_log(
        self,
        records: List[AdjustmentRecord],
        initial_score: float,
        final_score: float
    ) -> str:
        """
        補正ログをフォーマット

        Args:
            records: 補正記録リスト
            initial_score: 初期スコア
            final_score: 最終スコア

        Returns:
            フォーマットされたログ文字列
        """
        lines = [
            f"=== 補正ログ ===",
            f"初期スコア: {initial_score:.1f}",
            ""
        ]

        for record in records:
            lines.append(
                f"[{record.category}] {record.reason}: "
                f"{record.adjustment:+.1f} "
                f"({record.score_before:.1f} → {record.score_after:.1f})"
            )

        lines.extend([
            "",
            f"合計補正: {final_score - initial_score:+.1f}",
            f"最終スコア: {final_score:.1f}"
        ])

        return "\n".join(lines)


# 便利関数
def create_context_from_race_data(
    venue_code: str,
    course: int,
    racer_rank: str,
    weather_data: Optional[Dict] = None,
    tide_data: Optional[Dict] = None
) -> RaceContext:
    """
    レースデータからRaceContextを作成

    Args:
        venue_code: 会場コード
        course: コース番号
        racer_rank: 選手ランク
        weather_data: 天候データ（任意）
        tide_data: 潮位データ（任意）

    Returns:
        RaceContext
    """
    context = RaceContext(
        venue_code=venue_code,
        course=course,
        racer_rank=racer_rank
    )

    if weather_data:
        context.wind_speed = weather_data.get('wind_speed')
        context.wave_height = weather_data.get('wave_height')
        context.wind_direction = weather_data.get('wind_direction')
        context.temperature = weather_data.get('temperature')
        context.water_temperature = weather_data.get('water_temperature')

    if tide_data:
        context.tide_phase = tide_data.get('tide_phase')
        context.sea_level_cm = tide_data.get('sea_level_cm')

    return context


# テスト用
if __name__ == "__main__":
    print("=" * 80)
    print("AdjustmentManager テスト")
    print("=" * 80)

    manager = AdjustmentManager()

    # テストケース
    test_cases = [
        {
            'name': '大村1コースA1',
            'base_score': 50.0,
            'context': RaceContext(
                venue_code='24',
                course=1,
                racer_rank='A1',
                tide_phase='rising'
            )
        },
        {
            'name': '戸田1コースB1・暴風北',
            'base_score': 50.0,
            'context': RaceContext(
                venue_code='02',
                course=1,
                racer_rank='B1',
                wind_speed=8.5,
                wind_direction='北'
            )
        },
        {
            'name': '徳山4コース・下げ潮',
            'base_score': 45.0,
            'context': RaceContext(
                venue_code='17',
                course=4,
                racer_rank='A2',
                tide_phase='falling'
            )
        },
        {
            'name': '桐生1コース（淡水・補正なし）',
            'base_score': 50.0,
            'context': RaceContext(
                venue_code='01',
                course=1,
                racer_rank='A1',
                tide_phase='rising'
            )
        }
    ]

    for case in test_cases:
        print(f"\n{'='*40}")
        print(f"Test: {case['name']}")
        print(f"{'='*40}")

        final_score, records = manager.apply_all_adjustments(
            case['base_score'],
            case['context']
        )

        print(f"Base Score: {case['base_score']:.1f}")
        print(f"Final Score: {final_score:.1f}")
        print(f"Total Adjustment: {final_score - case['base_score']:+.1f}")
        print(f"Records: {len(records)}")
        for r in records:
            print(f"  [{r.category}] {r.subcategory}: {r.adjustment:+.1f}")

    print("\n" + "=" * 80)
    print("テスト完了")
    print("=" * 80)
