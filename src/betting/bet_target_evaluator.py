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
    # イン強会場定義（2025年12月8日 Opus分析結果）
    # ============================================================
    # 1コース勝率が高い会場（大村/下関/徳山）
    # 信頼度D × イン強会場で ROI +53.1% を確認
    HIGH_IN_VENUES = [24, 19, 18]  # 大村、下関、徳山

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
    # ============================================================
    BET_CONDITIONS = {
        # 信頼度C: C×20-30×B1+会場フィルター（6年間ROI 144.8%）
        # ※ 本番運用開始（2025-12-24承認）
        # ※ 6年間ROI 146.9%、5/6年黒字で安定性確認済み
        # ※ 1点買い推奨（ROI 143.2% vs パターンH 102.0%）
        # 【2026-01-13更新】唐津(23)を除外（唐津×C×B1×20-30条件と完全重複のため）
        'C': [
            {
                'method': '両方式',
                'odds_min': 20, 'odds_max': 30,
                'c1_rank': ['B1'],  # B1級限定
                'expected_roi': 144.8,
                'bet_amount': 100,
                'priority': 1,
                'description': 'C×20-30倍×B1級（6年間ROI 144.8%）',
                'paper_trade': False,  # 本番運用（2025-12-24承認）
                # 会場フィルター: 徳山,多摩川,平和島,津,丸亀,常滑,大村,若松,宮島（唐津除外）
                'venue_filter': [18, 5, 4, 9, 15, 8, 24, 20, 17],  # 唐津(23)除外（2026-01-13）
                'use_pattern_h': False,  # 1点買い推奨（ROI差: -41.2pt）
            },
            # 【2025-12-25追加】鳴門×C×A2×30-80倍（S-1グレードSパターン選定で発見）
            # 6年間バックテスト: 186件, ROI 215.6%, 収支 +21,510円
            # 直近4年連続黒字（2022年ROI 225%, 2023年252%, 2024年321%, 2025年238%）
            # ※ 既存C条件（B1級×20-30倍）との重複なし
            # ※ パターンH推奨（収支+54,540円）
            {
                'method': '両方式',
                'odds_min': 30, 'odds_max': 80,
                'c1_rank': ['A2'],  # A2級限定
                'expected_roi': 215.6,
                'bet_amount': 100,
                'priority': 2,
                'description': '鳴門×C×A2級×30-80倍（直近4年連続黒字）',
                'paper_trade': False,  # 本番運用（2025-12-25承認）
                'venue_filter': [14],  # 鳴門のみ
                'use_pattern_h': True,  # パターンH推奨（収支+54,540円）
            },
            # 【2026-01-08追加】唐津×C×B1×20-30倍
            # 探索結果: ROI 175.5%, +9,290円, 直近4年連続黒字
            {
                'method': '両方式',
                'odds_min': 20, 'odds_max': 30,
                'c1_rank': ['B1'],  # B1級限定
                'expected_roi': 175.5,
                'bet_amount': 100,
                'priority': 3,
                'description': '唐津×C×B1級×20-30倍（直近4年連続黒字）',
                'paper_trade': False,
                'venue_filter': [23],  # 唐津のみ
                'use_pattern_h': False,  # 1点買い（低オッズ帯）
            },
            # 【2026-01-08追加】児島×C×B1×30-50倍
            # 探索結果: ROI 184.3%, +13,650円, 直近3年連続黒字
            {
                'method': '両方式',
                'odds_min': 30, 'odds_max': 50,
                'c1_rank': ['B1'],  # B1級限定
                'expected_roi': 184.3,
                'bet_amount': 100,
                'priority': 4,
                'description': '児島×C×B1級×30-50倍（直近3年連続黒字）',
                'paper_trade': False,
                'venue_filter': [16],  # 児島のみ
                'use_pattern_h': True,  # パターンH（高オッズ帯）
            },
        ],
        # 信頼度D
        'D': [
            # D × B1 × 40-50倍 × 1コース2連率20-30%（2026-01-06最適化）
            # 【変更前】606件, ROI 110.8%, +6,570円（4/6年黒字）
            # 【変更後】306件, ROI 147.4%, +14,500円（4/6年黒字）
            # 効果: ROI +36.6pt, 収支 +7,930円改善
            # 年度別: 2020:+5,540円, 2021:-2,900円, 2022:-8,160円, 2023:+1,710円, 2024:+14,220円, 2025:+4,090円
            # ※ 1点買い推奨（ROI 134.6% vs パターンH 94.9%）
            {
                'method': '両方式',
                'odds_min': 40, 'odds_max': 50,
                'c1_rank': ['B1'],
                'expected_roi': 147.4,
                'bet_amount': 100,
                'priority': 1,
                'description': 'D×B1級×40-50倍×2連率20-30%（最適化版）',
                'c1_second_rate_min': 20,  # 1コース選手の全国2連率下限
                'c1_second_rate_max': 30,  # 1コース選手の全国2連率上限
                'use_pattern_h': False,  # 1点買い推奨（ROI差: -39.7pt）
            },
            # 【2026-01-07 無効化】D × A1/A2/B1 × 35-60倍
            # ※ 6年間バックテスト検証の結果、採用基準を満たさないため無効化
            # 実績: 2/6年黒字（2020年+260円、2025年+30,770円のみ）
            # 6年間累計: -34,290円（赤字）
            # 採用基準「直近4年で3年以上黒字」を満たさない（実際は1/4年）
            # 旧コメント「6年連続黒字」は誤記
            # {
            #     'method': '両方式',
            #     'odds_min': 35, 'odds_max': 60,
            #     'c1_rank': ['A1', 'A2', 'B1'],
            #     'expected_roi': 189.8,
            #     'bet_amount': 100,
            #     'priority': 2,
            #     'description': 'D×35-60倍（無効化・6年間赤字）',
            #     'race_exclude': [9],
            #     'venue_exclude': [10],
            # },
            # 【2026-01-05追加】D × 5コース予測（6年連続黒字・最安定）
            # 【2026-01-13更新】A2級を除外（6年間ROI 23.8%, -19,800円の大赤字）
            # 変更前: 全級別, 493件, ROI 142.9%, 収支+50,530円, 5/6年黒字
            # 変更後: A2除外, 379件, ROI 176.6%, 収支+70,330円, 5/6年黒字
            # 効果: ROI +33.7pt, 収支+19,800円
            # ※ パターンH推奨
            {
                'method': '両方式',
                'odds_min': 10, 'odds_max': 200,  # オッズ制限なし
                'c1_rank': ['A1', 'B1', 'B2'],  # A2除外（2026-01-13）
                'expected_roi': 176.6,  # 更新: 144.5%→176.6%（A2除外後）
                'bet_amount': 100,
                'priority': 3,
                'description': 'D×5コース予測×A2除外（ROI 176.6%）',
                'predicted_course': 5,  # 5コース予測限定
                'use_pattern_h': True,  # パターンH推奨
            },
            # 【2026-01-05追加→削除】浜名湖(06)×D×50-100倍×B1
            # ※ standard_backtest検証で該当レース0件のため削除
            # ml_analysis_featuresとrace_predictionsでデータ差異あり
        ],
    }

    # ============================================================
    # A・Bランク特別条件（2026年1月7日更新 - パターンH適用範囲最適化版）
    # ============================================================
    # before予測での6年間バックテスト結果を反映
    # B × 30-50 × B1 + 会場フィルター: ROI 333.6%（最有力）
    # B × 50-100: ROI 201.1%（安定）
    # A × A1 × 10-12倍: ROI 115.1%（黒字帯のみ採用）
    # A × A1 × 14-16倍: ROI 137.0%（黒字帯のみ採用）
    # ※ A×10-20全体はROI 89.0%で赤字のため、黒字オッズ帯のみに限定
    #
    # 【2025-12-24追加】モーター40%+条件（6年間安定性検証済み）
    # - A × B1 × モーター40%+: 6年間ROI 2044%, 6/6年プラス → 新規追加
    # - A × A2 × モーター40%+: 6年間ROI 1644%, 6/6年プラス → 新規追加
    # ※ 既存A条件（A1級）との干渉なし、新規セグメント
    #
    # 【2026-01-07追加】パターンH適用範囲最適化
    # - A条件（10-16倍）: 1点買い推奨（ROI差: -7〜-13pt）
    # - B条件（30倍以上）: パターンH推奨（高オッズで有利）
    # ============================================================
    AB_RANK_SPECIAL_CONDITIONS = {
        # Bランク条件
        'B': [
            # 優先度1: B × 50-100倍（安定）- A2級除外（6年間+5,900円改善）
            # 【2026-01-09追加】冬除外フィルター（12,1,2月除外）
            # 【2026-01-13追加】4月除外フィルター（6年間的中0回の完全赤字月）
            # 効果: 1180件→1082件(-8.3%), ROI 168.2%→183.6%(+15.4pt), 収支+15,300円改善
            # 理由: 4月は6年間で的中0回、3月はROI 315%で黒字なので除外しない
            # ※ パターンH推奨
            {
                'method': '両方式',
                'odds_min': 50, 'odds_max': 100,
                'c1_rank': ['A1', 'B1'],  # B2除外、A2除外（2025-12-25）
                'expected_roi': 183.6,  # 更新: 168.2%→183.6%（4月除外後）
                'bet_amount': 100,
                'priority': 1,
                'description': 'B×50-100倍×冬+4月除外（ROI 183.6%）',
                'use_pattern_h': True,  # パターンH推奨
                'month_exclude': [12, 1, 2, 4],  # 冬季+4月除外（2026-01-13追加）
            },
            # 優先度2: B × 30-50 × B1 + 会場フィルター
            # 【2026-01-13更新】会場を高ROI上位4会場に限定（蒲郡,常滑,尼崎,児島,若松,大村を除外）
            # 変更前: 10会場, ROI 130.7%, 4/6年黒字, 2025年-11,680円
            # 変更後: 4会場, ROI 196.7%, 6/6年黒字, 2025年+1,220円
            # 効果: ROI +66pt、全年黒字化
            # ※ パターンH推奨
            {
                'method': '両方式',
                'odds_min': 30, 'odds_max': 50,
                'c1_rank': ['B1'],  # B1級限定
                'expected_roi': 196.7,  # 更新: 333.6%→196.7%（4会場限定後）
                'bet_amount': 100,
                'priority': 2,
                'description': 'B×30-50倍×B1級×4会場（ROI 196.7%）',
                # 会場フィルター: 津,三国,芦屋,浜名湖（高ROI上位4会場のみ）
                'venue_filter': [9, 10, 21, 6],
                'use_pattern_h': True,  # パターンH推奨
            },
            # 【2025-12-25検証→不採用】B × 10-30倍 × A1/A2 × モーター35%+
            # A-2調査結果: 6年間884件, ROI 104.2%だが、
            # 2025年単体バックテスト: 162件, ROI 59.0%, 収支 -6,640円 → 赤字
            # 年度安定性がないため不採用

            # 【2026-01-13追加】B × 10-30倍 × 穴源(bias<-0.3) × 黒字会場
            # バイアス指数分析で発見: 予想より上に来やすい選手（穴源）を狙う
            # 検証結果: 202件, ROI 168.8%, +13,890円, 4/6年黒字
            # 黒字会場: 浜名湖(06),蒲郡(07),常滑(08),三国(10),丸亀(15),下関(19)
            {
                'method': '両方式',
                'odds_min': 10, 'odds_max': 30,
                'c1_rank': ['A1', 'A2', 'B1'],
                'expected_roi': 168.8,
                'bet_amount': 100,
                'priority': 3,
                'description': 'B×10-30倍×穴源×会場（ROI 168.8%）',
                'venue_filter': [6, 7, 8, 10, 15, 19],  # 黒字6会場限定
                'bias_max': -0.3,  # バイアス指数<-0.3（穴源選手）
                'use_pattern_h': False,  # 1点買い（低オッズ帯）
            },
        ],
        # Aランク条件
        'A': [
            # 【2026-01-07改善】A × A1 × 10-12倍 + 会場フィルター
            # 【2026-01-09追加】逃げ率>=70%フィルター
            # 改善前: 6年間ROI 98.1%, -2,330円（赤字）
            # 改善後（会場フィルター）: 6年間ROI 144.8%, +18,270円（黒字）
            # 追加改善（逃げ率>=70%）: ROI 105.3%→採用、逃げ率<70%はROI 75.7%で除外
            # 効果: 低逃げ率除外で+9,370円改善
            # 黒字会場: 三国(10),鳴門(14),芦屋(21),徳山(18),常滑(08),下関(19),びわこ(12)
            {
                'method': '両方式',
                'odds_min': 10, 'odds_max': 12,
                'c1_rank': ['A1'],
                'expected_roi': 144.8,
                'bet_amount': 100,
                'priority': 1,
                'description': 'A×A1級×10-12倍+会場+逃げ率70%+',
                'use_pattern_h': False,  # 1点買い推奨
                'venue_filter': [10, 14, 21, 18, 8, 19, 12],  # 黒字7会場限定
                'escape_rate_min': 0.70,  # 逃げ率70%以上（2026-01-09追加）
                'predicted_course': 1,  # 1コース予測時のみ適用
            },
            # 【2026-01-07廃止】A × A1 × 14-16倍
            # 廃止理由: 6年間ROI 64.2%, -19,990円（大幅赤字）
            # 会場フィルターでも黒字化困難（下関のみ149.5%、サンプル少）
            # {
            #     'method': '両方式',
            #     'odds_min': 14, 'odds_max': 16,
            #     'c1_rank': ['A1'],
            #     'expected_roi': 137.0,
            #     'bet_amount': 100,
            #     'priority': 2,
            #     'description': 'A×A1級×14-16倍（廃止・6年間赤字）',
            #     'use_pattern_h': False,
            # },
            # 【2026-01-07廃止】A × B1 × モーター40%+
            # 廃止理由: 6年間ROI 92.2%, -3,580円（赤字）、黒字年1/6年のみ
            # 採用経緯: 2025年単年でROI 196.6%だったが、6年間では不安定
            # 年度別: 2020:-1,210円, 2021:-370円, 2022:-620円, 2023:-1,110円, 2024:-640円, 2025:+370円
            # {
            #     'method': '両方式',
            #     'odds_min': 10, 'odds_max': 100,
            #     'c1_rank': ['B1'],
            #     'expected_roi': 92.2,
            #     'bet_amount': 100,
            #     'priority': 2,
            #     'description': 'A×B1級×モーター40%+（廃止・6年間赤字）',
            #     'motor_min': 40,
            #     'use_pattern_h': False,
            # },
        ],
    }

    # 除外条件
    # - B2級のみ除外（B1級は高配当範囲で超優秀なため使用）
    EXCLUDED_C1_RANKS = ['B2']

    # ============================================================
    # 2連単 購入条件定義（2025年12月追加）
    # ============================================================
    # バックテスト検証結果:
    # - D × A1 × 2連単: 的中率14.6%, ROI 106.7%
    # - 月間的中数を増やし、収支安定化を図る補助戦略
    # ============================================================
    EXACTA_CONDITIONS = {
        'D': {
            'c1_rank': ['A1'],
            'expected_roi': 106.7,
            'bet_amount': 100,  # 一律100円
            'sample_count': 907,
            'hit_rate': 14.6,
        },
    }

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
                cursor.execute('''
                    SELECT player_id, escape_rate
                    FROM player_escape_stats
                    WHERE stadium_id IS NULL AND escape_rate IS NOT NULL
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
        # キャッシュがあれば使用
        if self._player_bias_stats_cache is None:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT player_id, bias_index
                    FROM player_bias_stats
                    WHERE stadium_id IS NULL AND bias_index IS NOT NULL
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
        bias_index: Optional[float] = None  # 1着予測選手のバイアス指数 - 2026-01-13追加
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

        Returns:
            BetTarget: 購入対象情報
        """
        # A・Bランクは特別条件をチェック（feature_flagで制御）
        from config.feature_flags import is_feature_enabled

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
            # 特別条件をチェック
            conditions = self.AB_RANK_SPECIAL_CONDITIONS.get(confidence, [])
        else:
            # 信頼度に応じた条件をチェック（C, D）
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

            # 月除外チェック（month_exclude が指定されている場合）- 2026-01-09追加
            # 冬季（12,1,2月）はROI 47.4%で大幅赤字のため、B×50-100条件で除外
            if 'month_exclude' in cond:
                if race_month is not None and race_month in cond['month_exclude']:
                    continue

            # 逃げ率チェック（escape_rate_min が指定されている場合）- 2026-01-09追加
            # A×A1×10-12条件で逃げ率>=70%フィルター（低逃げ率選手を除外）
            if 'escape_rate_min' in cond:
                if escape_rate is None:
                    continue  # 逃げ率データがない場合は除外
                if escape_rate < cond['escape_rate_min']:
                    continue

            # バイアス指数チェック（bias_max が指定されている場合）- 2026-01-13追加
            # B×10-30×穴源条件で bias_index < -0.3 の選手のみ（予想より上に来やすい穴源）
            if 'bias_max' in cond:
                if bias_index is None:
                    continue  # バイアスデータがない場合は除外
                if bias_index >= cond['bias_max']:
                    continue  # bias_index が閾値以上なら除外

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
                # 直前情報がまだなら「候補」
                if not has_beforeinfo:
                    return BetTarget(
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
                else:
                    # 直前情報取得後もオッズ不明なら対象外
                    continue

            # オッズ範囲チェック
            if odds_min <= odds < odds_max:
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
                use_pattern_h = cond.get('use_pattern_h', True)  # デフォルトはTrue
                bet_mode = 'パターンH' if use_pattern_h else '1点買い'
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
                    use_pattern_h=use_pattern_h
                )

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
        has_beforeinfo: bool = False
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

        # 会場コードを取得
        venue_code = race_data.get('venue_code')

        # 気象データを取得
        wind_speed = race_data.get('wind_speed', 0.0)

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
            escape_rate=escape_rate  # 逃げ率フィルター用（2026-01-09追加）
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
                    try:
                        multi_bet_result = self.multi_bet_generator.generate(
                            predictions=full_prediction,
                            odds_dict=odds_data
                        )
                        bet_target.multi_bet_result = multi_bet_result
                    except Exception as e:
                        # 複数点買い生成失敗時は1点買いのまま継続
                        pass
            # else: use_pattern_h=Falseの場合は1点買いのまま（multi_bet_result=None）

        return bet_target

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
