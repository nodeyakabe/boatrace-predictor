# -*- coding: utf-8 -*-
"""
購入対象判定モジュール

最終運用戦略に基づいて、レースが購入対象かどうかを判定する
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict, Any
import sqlite3
from .multi_bet_generator import MultiBetGenerator, MultiBetPattern, MultiBetResult
from .venue_evaluator import VenueEvaluator
from .venue_course_adjuster import VenueCourseAdjuster, AdjustmentResult
from config.venue_wind_adjustments import should_exclude_race
from config.bet_conditions import STANDARD_BET_CONDITIONS, GLOBAL_VENUE_MONTH_EXCLUDES, GLOBAL_MONTH_EXCLUDES


class BetStatus(Enum):
    """購入判定状態"""
    TARGET_ADVANCE = "対象（事前）"      # 事前情報のみで購入条件を満たす
    CANDIDATE = "候補"                   # 直前情報次第で対象に入る可能性
    TARGET_CONFIRMED = "対象（確定）"    # 直前情報取得後、最終的に購入対象
    EXCLUDED = "対象外"                  # 購入条件を満たさない


@dataclass
class BetTarget:
    """購入対象情報"""
    status: BetStatus
    confidence: str                      # 信頼度 (A/B/C/D)
    method: str                          # 方式 (従来/新方式)
    combination: str                     # 買い目 (例: "1-2-3")
    odds: Optional[float]                # オッズ
    odds_range: str                      # オッズ範囲条件
    c1_rank: str                         # 1コース選手の級別
    expected_roi: float                  # 期待回収率
    bet_amount: int                      # 推奨賭け金
    reason: str                          # 判定理由
    needs_beforeinfo: bool = False       # 直前情報が必要か
    bet_type: str = 'trifecta'           # 賭け式 (trifecta/exacta)
    multi_bet_result: Optional[MultiBetResult] = None  # 複数点買い情報
    venue_course_adjustment: Optional[AdjustmentResult] = None  # 会場コース調整情報
    use_pattern_h: bool = True           # パターンH（3点買い）を使用するか（2026-01-07追加）
    pattern_h_exclude_p5: bool = False   # p5軸を除外して2点にするか（2026-04-08追加）


@dataclass
class ExactaBetTarget:
    """2連単購入対象情報"""
    status: BetStatus
    confidence: str                      # 信頼度 (A/B/C/D)
    combination: str                     # 買い目 (例: "1-2")
    c1_rank: str                         # 1コース選手の級別
    expected_roi: float                  # 期待回収率
    bet_amount: int                      # 推奨賭け金
    reason: str                          # 判定理由


class BetTargetEvaluator:
    """購入対象判定クラス"""

    # ============================================================
    # 購入条件定義（2026年1月7日更新 - パターンH適用範囲最適化版）
    # ============================================================
    # Opus分析: 2024年・2025年両方でROI 100%以上の条件のみ採用
    # - 2024年ROI 71.5% → 目標120%（赤字解消）
    # - 2025年ROI 136.0% → 目標130%維持
    # - 年度差が小さく安定した条件を優先
    # 参照: docs/YEAR_CONDITION_OPTIMIZATION_ANALYSIS.md
    #
    # 【2026-01-07追加】パターンH適用範囲最適化
    # - use_pattern_h: True=パターンH（3点買い400円）、False=1点買い（100円）
    # - 分析結果: ハイブリッドROI 131.4%, 収支+232,170円 vs 全パターンH 104.5%
    # - 低オッズ帯（10-30倍）は1点買い、高オッズ帯（30倍以上）はパターンH推奨

    # 除外条件
    # 【2026-02-12更新】B2級を除外から撤回（条件付きで活用可能）
    # - B1級は高配当範囲で超優秀なため使用
    # - B2級は特別条件で活用
    EXCLUDED_C1_RANKS = []  # 除外なし

    def __init__(
        self,
        use_multi_bet: bool = True,
        multi_bet_pattern: MultiBetPattern = MultiBetPattern.PATTERN_H,
        enable_venue_wind_filter: bool = True,
        enable_venue_course_adjustment: bool = True,
        venue_course_adjustment_scale: float = 1.0,
        db_path: str = 'data/boatrace.db',
    ):
        """
        初期化

        Args:
            use_multi_bet: 複数点買いを使用するか（デフォルト: True）
            multi_bet_pattern: 複数点買いパターン（デフォルト: PATTERN_H - 収支最大）
            enable_venue_wind_filter: 風速・会場フィルターを有効化するか（デフォルト: True）
            enable_venue_course_adjustment: 会場×コース別調整を有効化するか（デフォルト: True）
            venue_course_adjustment_scale: 調整値のスケール（デフォルト: 1.0 = 100%適用）
            db_path: データベースパス（デフォルト: 'data/boatrace.db'）
        """
        self.use_multi_bet = use_multi_bet
        self.multi_bet_generator = MultiBetGenerator(default_pattern=multi_bet_pattern) if use_multi_bet else None
        self.enable_venue_wind_filter = enable_venue_wind_filter
        self.venue_evaluator = VenueEvaluator() if enable_venue_wind_filter else None
        self.db_path = db_path

        # 会場×コース別調整
        self.enable_venue_course_adjustment = enable_venue_course_adjustment
        self.venue_course_adjuster = VenueCourseAdjuster(
            enabled=enable_venue_course_adjustment,
            adjustment_scale=venue_course_adjustment_scale,
        ) if enable_venue_course_adjustment else None

        # 会場別指標データのキャッシュ（2026-01-09追加）
        self._stadium_attack_stats_cache = None

        # 選手バイアス指数キャッシュ（2026-01-13追加）
        self._player_bias_stats_cache = None

        # 購入条件を config/bet_conditions.py から読み込み（2026-02-13統一化）
        self.BET_CONDITIONS = self._convert_conditions_to_dict(STANDARD_BET_CONDITIONS)

    def _convert_conditions_to_dict(self, conditions_list: List[Dict]) -> Dict[str, List[Dict]]:
        """
        STANDARD_BET_CONDITIONS（リスト形式）を信頼度別の辞書に変換

        Args:
            conditions_list: config/bet_conditions.py の STANDARD_BET_CONDITIONS

        Returns:
            信頼度をキーとした辞書 {'A': [...], 'B': [...], ...}
        """
        result = {}
        for cond in conditions_list:
            confidence = cond.get('confidence')
            # B2条件（confidence=None）は全信頼度に適用
            if confidence is None:
                # B2条件を全信頼度に追加
                for conf in ['A', 'B', 'C', 'D', 'E']:
                    if conf not in result:
                        result[conf] = []
                    result[conf].append(self._convert_condition_format(cond))
            else:
                if confidence not in result:
                    result[confidence] = []
                result[confidence].append(self._convert_condition_format(cond))
        return result

    def _convert_condition_format(self, cond: Dict) -> Dict:
        """
        config/bet_conditions.py の形式を BetTargetEvaluator の形式に変換

        Args:
            cond: config/bet_conditions.py の条件

        Returns:
            BetTargetEvaluator の形式の条件
        """
        # 必須フィールド
        result = {
            'method': '両方式',  # 固定
            'odds_min': cond['odds_min'],
            'odds_max': cond['odds_max'],
            'c1_rank': cond['c1_rank'],
            'expected_roi': cond.get('backtest_roi', 100.0),
            'bet_amount': 100,  # 固定
            'priority': 1,  # 固定
            'description': cond['description'],
            'paper_trade': False,  # 本番運用
            'use_pattern_h': cond.get('use_pattern_h', False),
        }

        # オプショナルフィールド（Noneでない場合のみ追加）
        optional_fields = [
            'venue_filter', 'month_exclude', 'escape_rate_min', 'predicted_course',
            'bias_max', 'c1_second_rate_min', 'c1_second_rate_max',
            'predicted_rank_has_class', 'predicted_rank_range',
        ]
        for field in optional_fields:
            value = cond.get(field)
            if value is not None:
                result[field] = value

        return result

    def _get_stadium_attack_stats(self, venue_code: str) -> Optional[Dict[str, float]]:
        """
        会場のまくり率・差し率を取得

        Args:
            venue_code: 会場コード（'01'-'24'形式）

        Returns:
            {'makuri_rate': float, 'sashi_rate': float} または None
        """
        # キャッシュがあれば使用
        if self._stadium_attack_stats_cache is None:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT stadium_id, makuri_rate, sashi_rate
                    FROM stadium_attack_stats
                    WHERE period_start = '2000-01-01'
                ''')
                self._stadium_attack_stats_cache = {
                    row[0]: {'makuri_rate': row[1], 'sashi_rate': row[2]}
                    for row in cursor.fetchall()
                }
                conn.close()
            except Exception:
                self._stadium_attack_stats_cache = {}

        return self._stadium_attack_stats_cache.get(venue_code)

    def _get_player_escape_rate(self, player_id: str) -> Optional[float]:
        """
        選手の全国逃げ率を取得

        Args:
            player_id: 選手登録番号

        Returns:
            逃げ率（0-1）または None（データなし/母数不足）
        """
        # キャッシュがあれば使用
        if not hasattr(self, '_player_escape_stats_cache'):
            self._player_escape_stats_cache = None

        if self._player_escape_stats_cache is None:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                # 2026-02-16: 重複レコード対策（最新1件のみ取得）
                cursor.execute('''
                    SELECT player_id, escape_rate
                    FROM player_escape_stats
                    WHERE stadium_id IS NULL AND escape_rate IS NOT NULL
                    AND id IN (
                        SELECT MAX(id)
                        FROM player_escape_stats
                        WHERE stadium_id IS NULL AND escape_rate IS NOT NULL
                        GROUP BY player_id
                    )
                ''')
                self._player_escape_stats_cache = {
                    row[0]: row[1]
                    for row in cursor.fetchall()
                }
                conn.close()
            except Exception:
                self._player_escape_stats_cache = {}

        return self._player_escape_stats_cache.get(player_id)

    def _get_player_bias_index(self, player_id: str) -> Optional[float]:
        """
        選手のバイアス指数を取得

        Args:
            player_id: 選手登録番号

        Returns:
            バイアス指数（マイナス=予想より上に来やすい穴源）またはNone
        """
        # キャッシュがあれば使用（2026-02-16重複レコード対策：最新1件のみ）
        if self._player_bias_stats_cache is None:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                # 2026-02-16: 重複レコード対策（最新1件のみ取得）
                cursor.execute('''
                    SELECT player_id, bias_index
                    FROM player_bias_stats
                    WHERE stadium_id IS NULL AND bias_index IS NOT NULL
                    AND id IN (
                        SELECT MAX(id)
                        FROM player_bias_stats
                        WHERE stadium_id IS NULL AND bias_index IS NOT NULL
                        GROUP BY player_id
                    )
                ''')
                self._player_bias_stats_cache = {
                    row[0]: row[1]
                    for row in cursor.fetchall()
                }
                conn.close()
            except Exception:
                self._player_bias_stats_cache = {}

        return self._player_bias_stats_cache.get(player_id)

    def evaluate(
        self,
        confidence: str,
        c1_rank: str,
        old_combo: str,
        new_combo: str,
        old_odds: Optional[float] = None,
        new_odds: Optional[float] = None,
        has_beforeinfo: bool = False,
        venue_code: Optional[int] = None,
        motor_second_rate: Optional[float] = None,
        race_number: Optional[int] = None,
        predicted_course: Optional[int] = None,
        c1_second_rate: Optional[float] = None,
        sashi_rate: Optional[float] = None,
        makuri_rate: Optional[float] = None,
        race_month: Optional[int] = None,  # レース月（1-12）- 2026-01-09追加
        escape_rate: Optional[float] = None,  # 1着予測選手の逃げ率（0-1）- 2026-01-09追加
        bias_index: Optional[float] = None,  # 1着予測選手のバイアス指数 - 2026-01-13追加
        odds_data: Optional[Dict] = None,  # 全オッズデータ（パターンH用）- 2026-02-13追加
        old_prediction: Optional[List[int]] = None,  # 予測順位（ピット番号のリスト、パターンH用）- 2026-02-16追加
        wave_height: Optional[float] = None  # 波高フィルター用（cm）- 2026-04-06追加
    ) -> BetTarget:
        """
        購入対象を判定する

        Args:
            confidence: 信頼度 (A/B/C/D)
            c1_rank: 1コース選手の級別 (A1/A2/B1/B2)
            old_combo: 従来方式の買い目 (例: "1-2-3")
            new_combo: 新方式の買い目 (例: "1-2-3")
            old_odds: 従来方式買い目のオッズ
            new_odds: 新方式買い目のオッズ
            has_beforeinfo: 直前情報が取得済みか
            venue_code: 会場コード（イン強会場条件チェック用）
            motor_second_rate: 1コース選手のモーター2連率（%）
            race_number: レース番号（1-12）
            predicted_course: 1着予測のコース番号（1-6）
            c1_second_rate: 1コース選手の全国2連率（%）
            sashi_rate: 会場の差し率（0-1、2026-01-09追加）
            makuri_rate: 会場のまくり率（0-1、2026-01-09追加）
            race_month: レース月（1-12、2026-01-09追加）
            escape_rate: 1着予測選手の逃げ率（0-1、2026-01-09追加）
            bias_index: 1着予測選手のバイアス指数（2026-01-13追加）
            odds_data: 全オッズデータ（パターンH用、2026-02-13追加）
            old_prediction: 予測順位（ピット番号のリスト、パターンH用、2026-02-16追加）
            wave_height: 波高（cm）。wave_height_max/wave_height_min 条件チェックに使用（2026-04-06追加）

        Returns:
            BetTarget: 購入対象情報
        """
        # A・Bランクは特別条件をチェック（feature_flagで制御）
        from config.feature_flags import is_feature_enabled

        # 【2026-02-13統一化】A/B/C/Dすべてconfig/bet_conditions.pyから取得
        if confidence in ['A', 'B']:
            if not is_feature_enabled('ab_rank_special_betting'):
                return BetTarget(
                    status=BetStatus.EXCLUDED,
                    confidence=confidence,
                    method='-',
                    combination='-',
                    odds=None,
                    odds_range='-',
                    c1_rank=c1_rank,
                    expected_roi=0,
                    bet_amount=0,
                    reason=f'信頼度{confidence}は購入対象外（フラグ無効）'
                )

        # 信頼度に応じた条件をチェック（統一設定から取得）
        conditions = self.BET_CONDITIONS.get(confidence, [])

        # 1コース級別チェック（条件定義で許可されている級別かチェック）
        # 条件定義に合致する級別があるかを先に確認
        has_matching_rank = any(c1_rank in cond.get('c1_rank', []) for cond in conditions)

        # デフォルトの除外条件（条件定義にない場合のみ適用）
        if not has_matching_rank and (c1_rank in self.EXCLUDED_C1_RANKS or c1_rank not in ['A1', 'A2', 'B1', 'B2']):
            return BetTarget(
                status=BetStatus.EXCLUDED,
                confidence=confidence,
                method='-',
                combination='-',
                odds=None,
                odds_range='-',
                c1_rank=c1_rank,
                expected_roi=0,
                bet_amount=0,
                reason=f'1コース{c1_rank}級は購入対象外（回収率低）'
            )

        if not conditions:
            return BetTarget(
                status=BetStatus.EXCLUDED,
                confidence=confidence,
                method='-',
                combination='-',
                odds=None,
                odds_range='-',
                c1_rank=c1_rank,
                expected_roi=0,
                bet_amount=0,
                reason=f'信頼度{confidence}は購入対象外'
            )

        # 各条件をチェック（優先度順にソート）
        sorted_conditions = sorted(conditions, key=lambda x: x.get('priority', 999))

        # オッズ未取得時のCANDIDATE候補（全条件チェック後に返すため）
        first_candidate_target = None

        for i, cond in enumerate(sorted_conditions):
            # 級別チェック
            if c1_rank not in cond['c1_rank']:
                continue

            # 会場コードチェック（venue_codes が指定されている場合）
            if 'venue_codes' in cond:
                if venue_code is None or venue_code not in cond['venue_codes']:
                    continue

            # 会場フィルターチェック（venue_filter が指定されている場合）
            if 'venue_filter' in cond:
                if venue_code is None or venue_code not in cond['venue_filter']:
                    continue

            # モーター2連率チェック（motor_min が指定されている場合）
            if 'motor_min' in cond:
                if motor_second_rate is None or motor_second_rate < cond['motor_min']:
                    continue

            # 会場除外チェック（venue_exclude が指定されている場合）- 2025-12-25追加
            if 'venue_exclude' in cond:
                if venue_code is not None and venue_code in cond['venue_exclude']:
                    continue

            # レース番号除外チェック（race_exclude が指定されている場合）- 2025-12-25追加
            if 'race_exclude' in cond:
                if race_number is not None and race_number in cond['race_exclude']:
                    continue

            # 予測コースチェック（predicted_course が指定されている場合）- 2026-01-05追加
            if 'predicted_course' in cond:
                if predicted_course is None or predicted_course != cond['predicted_course']:
                    continue

            # 1コース選手の全国2連率チェック（c1_second_rate_min/max が指定されている場合）- 2026-01-06追加
            if 'c1_second_rate_min' in cond or 'c1_second_rate_max' in cond:
                if c1_second_rate is None:
                    continue
                if 'c1_second_rate_min' in cond and c1_second_rate < cond['c1_second_rate_min']:
                    continue
                if 'c1_second_rate_max' in cond and c1_second_rate >= cond['c1_second_rate_max']:
                    continue

            # 差し率チェック（sashi_rate_min が指定されている場合）- 2026-01-09追加
            if 'sashi_rate_min' in cond:
                if sashi_rate is None:
                    continue
                if sashi_rate < cond['sashi_rate_min']:
                    continue

            # まくり率チェック（makuri_rate_min が指定されている場合）- 2026-01-09追加
            if 'makuri_rate_min' in cond:
                if makuri_rate is None:
                    continue
                if makuri_rate < cond['makuri_rate_min']:
                    continue

            # 月除外チェック（条件個別 + グローバル月除外）- 2026-01-09追加、2026-03-18グローバル拡張
            if race_month is not None:
                month_excludes = list(cond.get('month_exclude') or []) + list(GLOBAL_MONTH_EXCLUDES or [])
                if race_month in month_excludes:
                    continue

            # グローバル会場×月除外チェック（2026-02-17追加）
            # 全条件共通: 6年間で一貫して赤字の会場×月組み合わせを除外
            if GLOBAL_VENUE_MONTH_EXCLUDES and venue_code is not None and race_month is not None:
                skip = False
                for exc_venue, exc_month in GLOBAL_VENUE_MONTH_EXCLUDES:
                    if isinstance(exc_venue, int):
                        exc_venue_code = exc_venue
                    else:
                        exc_venue_code = int(exc_venue)
                    if venue_code == exc_venue_code and race_month == exc_month:
                        skip = True
                        break
                if skip:
                    continue

            # 逃げ率チェック（escape_rate_min が指定されている場合）- 2026-01-09追加
            # A×A1×10-12条件で逃げ率>=70%フィルター（低逃げ率選手を除外）
            # 【2026-02-16修正】Tier 2と同じく、データなしの場合はチェックをスキップ
            if 'escape_rate_min' in cond:
                if escape_rate is not None and escape_rate < cond['escape_rate_min']:
                    continue  # 逃げ率がある場合のみチェック

            # バイアス指数チェック（bias_max が指定されている場合）- 2026-01-13追加
            # B×10-30×穴源条件で bias_index < -0.3 の選手のみ（予想より上に来やすい穴源）
            if 'bias_max' in cond:
                if bias_index is None:
                    continue  # バイアスデータがない場合は除外
                if bias_index >= cond['bias_max']:
                    continue  # bias_index が閾値以上なら除外

            # 波高フィルターチェック（2026-04-06追加）
            # wave_height_max: この値を超える波高の場合は除外（荒れレース除外が主用途）
            # wave_height_min: この値未満の波高の場合は除外（荒れレース専用条件が主用途）
            if 'wave_height_max' in cond:
                if wave_height is not None and wave_height > cond['wave_height_max']:
                    continue
            if 'wave_height_min' in cond:
                if wave_height is None or wave_height < cond['wave_height_min']:
                    continue

            # 方式と買い目の決定
            if cond['method'] == '従来':
                combo = old_combo
                odds = old_odds
            elif cond['method'] == '新方式':
                combo = new_combo
                odds = new_odds
            else:  # '両方式'の場合、オッズが高い方を選択
                if old_odds and new_odds:
                    if old_odds >= new_odds:
                        combo = old_combo
                        odds = old_odds
                    else:
                        combo = new_combo
                        odds = new_odds
                elif old_odds:
                    combo = old_combo
                    odds = old_odds
                elif new_odds:
                    combo = new_combo
                    odds = new_odds
                else:
                    combo = old_combo
                    odds = old_odds

            odds_min = cond['odds_min']
            odds_max = cond['odds_max']
            odds_range = f"{odds_min}倍+" if odds_max >= 9999 else f"{odds_min}-{odds_max}倍"

            # オッズが不明な場合
            if odds is None or odds == 0:
                # 直前情報がまだなら「候補」として記録（全条件チェック後に返す）
                if not has_beforeinfo and first_candidate_target is None:
                    first_candidate_target = BetTarget(
                        status=BetStatus.CANDIDATE,
                        confidence=confidence,
                        method=cond['method'],
                        combination=combo,
                        odds=None,
                        odds_range=odds_range,
                        c1_rank=c1_rank,
                        expected_roi=cond['expected_roi'],
                        bet_amount=cond['bet_amount'],
                        reason=f'オッズ未取得。{odds_range}なら購入対象',
                        needs_beforeinfo=True
                    )
                # 他の条件もチェックするためcontinue
                continue

            # オッズ範囲チェック（パターンH対応）
            use_pattern_h = cond.get('use_pattern_h', True)
            exclude_p5 = cond.get('pattern_h_exclude_p5', False)

            # パターンH条件だが4位までの予測がない場合は対象外（Tier 2のINNER JOINと同じ動作）
            if use_pattern_h and (not old_prediction or len(old_prediction) < 4):
                continue
            # p5使用時は5位まで必要
            if use_pattern_h and not exclude_p5 and len(old_prediction) < 5:
                continue

            # パターンH条件の場合、各点の買い目をチェック
            if use_pattern_h and odds_data and old_prediction and len(old_prediction) >= 4:
                # 予測順位から買い目を生成
                combo_123 = f"{old_prediction[0]}-{old_prediction[1]}-{old_prediction[2]}"
                combo_124 = f"{old_prediction[0]}-{old_prediction[1]}-{old_prediction[3]}"

                # オッズを取得
                odds_123 = odds_data.get(combo_123)
                odds_124 = odds_data.get(combo_124)

                # いずれかがオッズ範囲内なら購入対象
                matched_combos = []
                if odds_123 and odds_min <= odds_123 < odds_max:
                    matched_combos.append((combo_123, odds_123))
                if odds_124 and odds_min <= odds_124 < odds_max:
                    matched_combos.append((combo_124, odds_124))

                # p5除外でない場合は1-2-5も確認
                if not exclude_p5 and len(old_prediction) >= 5:
                    combo_125 = f"{old_prediction[0]}-{old_prediction[1]}-{old_prediction[4]}"
                    odds_125 = odds_data.get(combo_125)
                    if odds_125 and odds_min <= odds_125 < odds_max:
                        matched_combos.append((combo_125, odds_125))

                if matched_combos:
                    # 最もオッズが高い買い目を選択
                    combo, odds = max(matched_combos, key=lambda x: x[1])
                else:
                    # 全点が範囲外なら次の条件へ
                    continue
            else:
                # パターンH以外、または条件が揃わない場合は1点のみチェック
                if not (odds_min <= odds < odds_max):
                    continue

            # 購入対象として返す
            status = BetStatus.TARGET_CONFIRMED if has_beforeinfo else BetStatus.TARGET_ADVANCE
            # 理由の構築
            reason_parts = [f'信頼度{confidence}', cond['method'], odds_range, f'1コース{c1_rank}']
            if 'venue_codes' in cond:
                reason_parts.append('イン強会場')
            if 'venue_filter' in cond:
                reason_parts.append('高ROI会場')
            if 'motor_min' in cond:
                reason_parts.append(f'モーター{motor_second_rate:.1f}%')
            if 'predicted_course' in cond:
                reason_parts.append(f'{cond["predicted_course"]}コース予測')
            # パターンH適用有無を理由に追加
            _exclude_p5 = exclude_p5 if use_pattern_h else False
            bet_mode = 'パターンH2' if (use_pattern_h and _exclude_p5) else ('パターンH' if use_pattern_h else '1点買い')
            reason_parts.append(bet_mode)
            reason = ' + '.join(reason_parts)

            return BetTarget(
                status=status,
                confidence=confidence,
                method=cond['method'],
                combination=combo,
                odds=odds,
                odds_range=odds_range,
                c1_rank=c1_rank,
                expected_roi=cond['expected_roi'],
                bet_amount=cond['bet_amount'],
                reason=reason,
                use_pattern_h=use_pattern_h,
                pattern_h_exclude_p5=_exclude_p5
            )

        # オッズ未取得でCANDIDATE候補がある場合（全条件確認済み）
        if first_candidate_target is not None:
            return first_candidate_target

        # オッズが範囲外の場合、候補として返す（直前情報でオッズが変動する可能性）
        if not has_beforeinfo and (old_odds or new_odds):
            # 最も近い条件を探す
            best_cond = conditions[0]
            method = best_cond['method']
            combo = old_combo if method == '従来' else new_combo
            odds = old_odds if method == '従来' else new_odds
            odds_range = f"{best_cond['odds_min']}倍+" if best_cond['odds_max'] >= 9999 else f"{best_cond['odds_min']}-{best_cond['odds_max']}倍"

            if odds and odds < best_cond['odds_min']:
                return BetTarget(
                    status=BetStatus.CANDIDATE,
                    confidence=confidence,
                    method=method,
                    combination=combo,
                    odds=odds,
                    odds_range=odds_range,
                    c1_rank=c1_rank,
                    expected_roi=best_cond['expected_roi'],
                    bet_amount=best_cond['bet_amount'],
                    reason=f'オッズ{odds:.1f}倍（{odds_range}で対象）。直前情報で変動の可能性',
                    needs_beforeinfo=True
                )

        # 条件を満たさない
        return BetTarget(
            status=BetStatus.EXCLUDED,
            confidence=confidence,
            method='-',
            combination='-',
            odds=old_odds or new_odds,
            odds_range='-',
            c1_rank=c1_rank,
            expected_roi=0,
            bet_amount=0,
            reason='オッズ範囲外または条件不一致'
        )

    def evaluate_race(
        self,
        race_data: Dict[str, Any],
        predictions: Dict[str, Any],
        odds_data: Optional[Dict[str, float]] = None,
        has_beforeinfo: bool = False,
        advance_top3: Optional[List[int]] = None,  # advance予測の1-2-3位ピット番号（2026-04-07追加）
    ) -> BetTarget:
        """
        レースデータから購入対象を判定する

        Args:
            race_data: レース情報（entries含む）
            predictions: 予測情報（confidence, old_pred, new_pred）
            odds_data: オッズデータ {combination: odds}
            has_beforeinfo: 直前情報が取得済みか

        Returns:
            BetTarget: 購入対象情報
        """
        # 1コース選手の級別、モーター2連率、全国2連率を取得
        entries = race_data.get('entries', [])
        c1_entry = next((e for e in entries if e.get('pit_number') == 1), None)
        c1_rank = c1_entry.get('racer_rank', 'B1') if c1_entry else 'B1'
        motor_second_rate = c1_entry.get('motor_second_rate') if c1_entry else None
        c1_second_rate = c1_entry.get('second_rate') if c1_entry else None

        # 会場コードを取得（文字列 '01'-'24' を整数 1-24 に統一）
        # DBのvenue_codeはTEXT型で'01', '02'形式で保存されているが、
        # config/bet_conditions.pyのvenue_filterは整数リスト [1, 2, ...]
        # → 比較のため整数に変換
        venue_code_raw = race_data.get('venue_code')
        venue_code = None
        if venue_code_raw is not None:
            # 文字列の場合は整数に変換（'02' → 2）
            if isinstance(venue_code_raw, str):
                try:
                    venue_code = int(venue_code_raw)
                except ValueError:
                    venue_code = venue_code_raw
            else:
                venue_code = venue_code_raw

        # 気象データを取得
        wind_speed = race_data.get('wind_speed', 0.0)
        wave_height = race_data.get('wave_height')  # 波高フィルター用（2026-04-06追加）

        # 予測情報
        confidence = predictions.get('confidence', 'D')
        old_pred = predictions.get('old_prediction', [1, 2, 3])
        new_pred = predictions.get('new_prediction', [1, 2, 3])

        # 風速・会場フィルター（2024-2025年分析ベース）
        if self.enable_venue_wind_filter and venue_code and wind_speed is not None:
            # venue_codeを文字列化（'01'-'24'形式）
            venue_code_str = f"{venue_code:02d}" if isinstance(venue_code, int) else str(venue_code).zfill(2)

            # 除外判定
            should_exclude, exclude_reason = should_exclude_race(
                venue_code=venue_code_str,
                wind_speed=wind_speed,
                confidence=confidence
            )

            if should_exclude:
                return BetTarget(
                    status=BetStatus.EXCLUDED,
                    confidence=confidence,
                    method='-',
                    combination='-',
                    odds=0,
                    odds_range='-',
                    c1_rank=c1_rank,
                    expected_roi=0,
                    bet_amount=0,
                    reason=f'風速・会場除外: {exclude_reason}'
                )

        # レース番号を取得（2025-12-25追加）
        race_number = race_data.get('race_number')

        # レース月を取得（2026-01-09追加：冬季除外フィルター用）
        race_month = None
        race_date = race_data.get('race_date')
        if race_date:
            # race_dateは 'YYYY-MM-DD' 形式の文字列
            try:
                if isinstance(race_date, str):
                    race_month = int(race_date.split('-')[1])
                elif hasattr(race_date, 'month'):
                    race_month = race_date.month
            except (IndexError, ValueError):
                pass

        # 買い目
        old_combo = f"{old_pred[0]}-{old_pred[1]}-{old_pred[2]}"
        new_combo = f"{new_pred[0]}-{new_pred[1]}-{new_pred[2]}"

        # 1着予測のコース（predicted_course条件用）
        predicted_first_course = old_pred[0]

        # オッズ
        old_odds = odds_data.get(old_combo, 0) if odds_data else 0
        new_odds = odds_data.get(new_combo, 0) if odds_data else 0

        # 会場の差し率・まくり率を取得（2026-01-09追加）
        sashi_rate = None
        makuri_rate = None
        if venue_code:
            venue_code_str = f"{venue_code:02d}" if isinstance(venue_code, int) else str(venue_code).zfill(2)
            stats = self._get_stadium_attack_stats(venue_code_str)
            if stats:
                sashi_rate = stats.get('sashi_rate')
                makuri_rate = stats.get('makuri_rate')

        # 1着予測選手の逃げ率を取得（2026-01-09追加）
        escape_rate = None
        if predicted_first_course == 1:
            # 1コース予測時のみ逃げ率をチェック
            first_pred_racer = predictions.get('first_racer_number')
            if first_pred_racer:
                escape_rate = self._get_player_escape_rate(str(first_pred_racer))

        # 1着予測選手のバイアス指数を取得（2026-01-28追加）
        bias_index = None
        first_pred_racer = predictions.get('first_racer_number')
        if first_pred_racer:
            bias_index = self._get_player_bias_index(str(first_pred_racer))

        # ============================================================
        # advance/before 完全一致フィルタ（2026-04-07追加）
        # びわこ(venue_code=11)はフィルタ不適用
        # advance_top3=Noneはパススルー（advance予測欠損）
        # advance/before不一致の場合はEXCLUDED
        # ============================================================
        BIWAKO_VENUE_CODE = 11
        if venue_code != BIWAKO_VENUE_CODE and advance_top3 is not None:
            before_top3 = old_pred[:3]
            if list(advance_top3[:3]) != list(before_top3):
                return BetTarget(
                    status=BetStatus.EXCLUDED,
                    confidence=confidence,
                    method='-',
                    combination='-',
                    odds=None,
                    odds_range='-',
                    c1_rank=c1_rank,
                    expected_roi=0,
                    bet_amount=0,
                    reason=f'advance/before不一致: adv={advance_top3[:3]} bef={before_top3}'
                )

        # ============================================================
        # B2級特別条件チェック（2026-02-12追加、2026-02-13一時無効化）
        # ============================================================
        # 【2026-02-13】B2条件はconfig/bet_conditions.pyでコメントアウトされているため
        # この処理も無効化しています。
        # ============================================================
        # （無効化済み）

        # ============================================================
        # 通常の購入対象判定（B2条件に該当しない場合）
        # ============================================================
        # 基本的な購入対象判定
        bet_target = self.evaluate(
            confidence=confidence,
            c1_rank=c1_rank,
            old_combo=old_combo,
            new_combo=new_combo,
            old_odds=old_odds,
            new_odds=new_odds,
            has_beforeinfo=has_beforeinfo,
            venue_code=venue_code,
            motor_second_rate=motor_second_rate,
            race_number=race_number,
            predicted_course=predicted_first_course,
            c1_second_rate=c1_second_rate,
            sashi_rate=sashi_rate,
            makuri_rate=makuri_rate,
            race_month=race_month,  # 冬季除外フィルター用（2026-01-09追加）
            escape_rate=escape_rate,  # 逃げ率フィルター用（2026-01-09追加）
            bias_index=bias_index,  # バイアス指数フィルター用（2026-01-28追加）
            odds_data=odds_data,  # パターンH用全オッズ（2026-02-13追加）
            old_prediction=old_pred,  # パターンH用予測順位（2026-02-16追加）
            wave_height=wave_height  # 波高フィルター用（2026-04-06追加）
        )

        # 会場×コース別調整を適用
        venue_course_adj_result = None
        if self.enable_venue_course_adjustment and self.venue_course_adjuster and venue_code:
            venue_code_str = f"{venue_code:02d}" if isinstance(venue_code, int) else str(venue_code).zfill(2)

            # 1着予測のコースに対する調整を計算
            first_course = old_pred[0] if old_pred else 1
            venue_course_adj_result = self.venue_course_adjuster.apply_adjustment_with_details(
                base_score=0,  # 調整量のみを取得
                venue_code=venue_code_str,
                course=first_course
            )

            # 理由に会場コース調整情報を追加
            if bet_target.status in [BetStatus.TARGET_CONFIRMED, BetStatus.TARGET_ADVANCE]:
                if venue_course_adj_result.adjustment != 0:
                    adj_str = f"+{venue_course_adj_result.adjustment}" if venue_course_adj_result.adjustment > 0 else str(venue_course_adj_result.adjustment)
                    bet_target.reason = f"{bet_target.reason} | 会場調整: {venue_course_adj_result.venue_name}{first_course}コース{adj_str}pt"

            bet_target.venue_course_adjustment = venue_course_adj_result

        # 購入対象の場合、複数点買いを生成（use_pattern_hがTrueの場合のみ）
        # 【2026-01-07更新】条件別にパターンH/1点買いを切り替え
        # 【2026-04-08更新】pattern_h_exclude_p5=TrueならPATTERN_H2（2点）を使用
        if self.use_multi_bet and bet_target.status in [BetStatus.TARGET_CONFIRMED, BetStatus.TARGET_ADVANCE]:
            # use_pattern_hフラグをチェック（デフォルトはTrue）
            if bet_target.use_pattern_h:
                # 予測の全順位を取得（最低4艇必要）
                full_prediction = predictions.get('full_prediction')
                if full_prediction is None:
                    # old_predictionから推測（拡張が必要な場合）
                    full_prediction = list(old_pred)
                    # 不足分は1-6から補填
                    for i in range(1, 7):
                        if i not in full_prediction:
                            full_prediction.append(i)
                    full_prediction = full_prediction[:6]

                if len(full_prediction) >= 4 and odds_data:
                    # パターンH用の全買い目のオッズを取得（2026-01-28追加）
                    odds_dict_complete = self._fetch_pattern_h_odds(
                        race_id=race_data.get('id'),
                        predictions=full_prediction,
                        existing_odds=odds_data
                    )

                    # p5除外フラグに応じてパターンを選択
                    _pattern = MultiBetPattern.PATTERN_H2 if bet_target.pattern_h_exclude_p5 else MultiBetPattern.PATTERN_H

                    try:
                        multi_bet_result = self.multi_bet_generator.generate(
                            predictions=full_prediction,
                            odds_dict=odds_dict_complete,
                            pattern=_pattern
                        )
                        bet_target.multi_bet_result = multi_bet_result
                    except Exception as e:
                        # 複数点買い生成失敗時は1点買いのまま継続（2026-01-28修正）
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.warning(f"パターンH生成失敗 (レースID: {race_data.get('id', 'unknown')}): {str(e)}")
                        logger.debug(f"  full_prediction: {full_prediction}, odds_data: {odds_dict_complete}")
            # else: use_pattern_h=Falseの場合は1点買いのまま（multi_bet_result=None）

        return bet_target

    def _fetch_pattern_h_odds(
        self,
        race_id: Optional[int],
        predictions: List[int],
        existing_odds: Dict[str, float]
    ) -> Dict[str, float]:
        """
        パターンH用の全買い目のオッズを取得

        Args:
            race_id: レースID
            predictions: 予測順位リスト（最低4艇必要）
            existing_odds: 既存のオッズ辞書

        Returns:
            補完されたオッズ辞書
        """
        if not race_id or len(predictions) < 4:
            return existing_odds

        # パターンHの買い目を計算（1-2軸固定、3着は3-5位）
        p1, p2 = predictions[0], predictions[1]
        third_candidates = [predictions[2], predictions[3], predictions[4]]

        # 必要な買い目リストを作成
        needed_combinations = []
        for third in third_candidates:
            if third != p1 and third != p2:
                combo = f"{p1}-{p2}-{third}"
                if combo not in existing_odds:
                    needed_combinations.append(combo)

        # 追加取得が不要ならそのまま返す
        if not needed_combinations:
            return existing_odds

        # DBから不足分のオッズを取得
        try:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # IN句用のプレースホルダー
            placeholders = ','.join(['?' for _ in needed_combinations])
            query = f"""
                SELECT combination, odds
                FROM trifecta_odds
                WHERE race_id = ? AND combination IN ({placeholders})
            """

            cursor.execute(query, [race_id] + needed_combinations)
            fetched_odds = {row[0]: row[1] for row in cursor.fetchall()}
            conn.close()

            # 既存のオッズと統合
            complete_odds = dict(existing_odds)
            complete_odds.update(fetched_odds)

            return complete_odds

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"パターンH用オッズ取得失敗 (レースID: {race_id}): {str(e)}")
            return existing_odds

    def get_summary(self, targets: List[BetTarget]) -> Dict[str, Any]:
        """
        複数レースの購入対象サマリーを取得

        Args:
            targets: BetTargetのリスト

        Returns:
            サマリー情報
        """
        summary = {
            'total': len(targets),
            'target_advance': 0,
            'candidate': 0,
            'target_confirmed': 0,
            'excluded': 0,
            'total_bet': 0,
            'expected_return': 0,
        }

        for t in targets:
            if t.status == BetStatus.TARGET_ADVANCE:
                summary['target_advance'] += 1
                summary['total_bet'] += t.bet_amount
                summary['expected_return'] += t.bet_amount * t.expected_roi / 100
            elif t.status == BetStatus.CANDIDATE:
                summary['candidate'] += 1
            elif t.status == BetStatus.TARGET_CONFIRMED:
                summary['target_confirmed'] += 1
                summary['total_bet'] += t.bet_amount
                summary['expected_return'] += t.bet_amount * t.expected_roi / 100
            else:
                summary['excluded'] += 1

        return summary

    def evaluate_exacta(
        self,
        confidence: str,
        c1_rank: str,
        pred_1st: int,
        pred_2nd: int,
    ) -> ExactaBetTarget:
        """
        2連単の購入対象を判定する

        Args:
            confidence: 信頼度 (A/B/C/D)
            c1_rank: 1コース選手の級別 (A1/A2/B1/B2)
            pred_1st: 1着予測の艇番
            pred_2nd: 2着予測の艇番

        Returns:
            ExactaBetTarget: 2連単購入対象情報
        """
        combination = f"{pred_1st}-{pred_2nd}"

        # 2連単の条件をチェック
        cond = self.EXACTA_CONDITIONS.get(confidence)
        if not cond:
            return ExactaBetTarget(
                status=BetStatus.EXCLUDED,
                confidence=confidence,
                combination=combination,
                c1_rank=c1_rank,
                expected_roi=0,
                bet_amount=0,
                reason=f'信頼度{confidence}は2連単対象外'
            )

        # 級別チェック
        if c1_rank not in cond['c1_rank']:
            return ExactaBetTarget(
                status=BetStatus.EXCLUDED,
                confidence=confidence,
                combination=combination,
                c1_rank=c1_rank,
                expected_roi=0,
                bet_amount=0,
                reason=f'1コース{c1_rank}級は2連単対象外'
            )

        # 条件を満たす
        return ExactaBetTarget(
            status=BetStatus.TARGET_ADVANCE,
            confidence=confidence,
            combination=combination,
            c1_rank=c1_rank,
            expected_roi=cond['expected_roi'],
            bet_amount=cond['bet_amount'],
            reason=f'信頼度{confidence} × 1コース{c1_rank} × 2連単'
        )

    def evaluate_race_exacta(
        self,
        race_data: Dict[str, Any],
        predictions: Dict[str, Any],
    ) -> ExactaBetTarget:
        """
        レースデータから2連単の購入対象を判定する

        Args:
            race_data: レース情報（entries含む）
            predictions: 予測情報（confidence, old_pred）

        Returns:
            ExactaBetTarget: 2連単購入対象情報
        """
        # 1コース選手の級別を取得
        entries = race_data.get('entries', [])
        c1_entry = next((e for e in entries if e.get('pit_number') == 1), None)
        c1_rank = c1_entry.get('racer_rank', 'B1') if c1_entry else 'B1'

        # 予測情報
        confidence = predictions.get('confidence', 'D')
        old_pred = predictions.get('old_prediction', [1, 2, 3])

        return self.evaluate_exacta(
            confidence=confidence,
            c1_rank=c1_rank,
            pred_1st=old_pred[0],
            pred_2nd=old_pred[1],
        )

    def evaluate_all(
        self,
        race_data: Dict[str, Any],
        predictions: Dict[str, Any],
        odds_data: Optional[Dict[str, float]] = None,
        has_beforeinfo: bool = False
    ) -> Dict[str, Any]:
        """
        レースの全購入対象を判定する（3連単 + 2連単）

        Args:
            race_data: レース情報（entries含む）
            predictions: 予測情報
            odds_data: オッズデータ
            has_beforeinfo: 直前情報が取得済みか

        Returns:
            {'trifecta': BetTarget, 'exacta': ExactaBetTarget}
        """
        trifecta = self.evaluate_race(race_data, predictions, odds_data, has_beforeinfo)
        exacta = self.evaluate_race_exacta(race_data, predictions)

        return {
            'trifecta': trifecta,
            'exacta': exacta,
        }
