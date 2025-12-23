"""
パターンスコアラー

BEFORE情報（展示タイム、ST）に基づくパターンボーナスを適用する。
race_predictor.pyから分離（2025-12-15）

バックテスト検証済み（1000レース、2025年データ）:
- 信頼度B: +9.5pt効果（65.3% vs 55.9%）
- 信頼度C: +8.3pt効果（47.7% vs 39.4%）
"""

import logging
from typing import Dict, List, Optional

from config.feature_flags import is_feature_enabled
# from config.optimized_pattern_multipliers import get_optimized_multiplier  # アーカイブ削除（2025-12-22）
from config.presets.loader import get_pattern_multiplier
from src.utils.db_connection_pool import get_connection


# ==================================================
# BEFORE情報パターンボーナス定義
# ==================================================
# 倍率はconfig/presets/scoring_weights.yamlから読み込み可能

BEFORE_PATTERNS_1ST = [
    # 1着予測用パターン（4パターン + ネガティブ3パターン）
    {
        'name': 'pre1_st1_ex1',
        'description': 'PRE1位 & ST1位 & 展示1位（最強複合）',
        'multiplier': get_pattern_multiplier('pre1_st1_ex1', 1.50),  # +193%効果（分析結果より）
        'target_rank': 1,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank == 1 and ex_rank == 1,
    },
    {
        'name': 'pre1_st1',
        'description': 'PRE1位 & ST1位',
        'multiplier': get_pattern_multiplier('pre1_st1', 1.411),
        'target_rank': 1,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank == 1 and ex_rank != 1,  # 展示1位は上のパターンで処理
    },
    # ネガティブパターン: ST遅い場合のペナルティ
    {
        'name': 'pre1_st6',
        'description': 'PRE1位 & ST6位（大幅ペナルティ）',
        'multiplier': get_pattern_multiplier('pre1_st6', 0.53),  # -24.84%効果
        'target_rank': 1,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank == 6,
    },
    {
        'name': 'pre1_st5_6',
        'description': 'PRE1位 & ST5-6位（ペナルティ緩和）',
        'multiplier': get_pattern_multiplier('pre1_st5_6', 0.80),  # 緊急修正: 0.63→0.80（誤ブロック率40.7%のため緩和）
        'target_rank': 1,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank >= 5 and st_rank != 6,  # ST6は上のパターンで処理
    },
    {
        'name': 'pre1_st4_6',
        'description': 'PRE1位 & ST4-6位（無効化）',
        'multiplier': get_pattern_multiplier('pre1_st4_6', 1.0),  # 緊急修正: 0.70→1.0（誤ブロック率44.6%のため無効化）
        'target_rank': 1,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank >= 4 and st_rank not in [5, 6],  # ST5-6は上のパターンで処理
    },
    {
        'name': 'pre1_ex1',
        'description': 'PRE1位 & 展示1位',
        'multiplier': get_pattern_multiplier('pre1_ex1', 1.286),
        'target_rank': 1,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and ex_rank == 1,
    },
    {
        'name': 'pre1_ex1_3_st1_3',
        'description': 'PRE1位 & 展示1-3位 & ST1-3位',
        'multiplier': get_pattern_multiplier('pre1_ex1_3_st1_3', 1.328),
        'target_rank': 1,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and ex_rank <= 3 and st_rank <= 3,
    },
    {
        'name': 'pre1_st1_3',
        'description': 'PRE1位 & ST1-3位',
        'multiplier': get_pattern_multiplier('pre1_st1_3', 1.310),
        'target_rank': 1,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank <= 3,
    },
]

BEFORE_PATTERNS_2ND = [
    # 2着予測用パターン（7パターン + 新規強力パターン）
    # 新規強力パターン: PRE2位 & ST1-2位（+2.90%効果）
    {
        'name': 'pre2_st1_2',
        'description': 'PRE2位 & ST1-2位（強力）',
        'multiplier': get_pattern_multiplier('pre2_st1_2', 1.12),  # +2.90%効果
        'target_rank': 2,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 2 and st_rank <= 2,
    },
    {
        'name': 'pre2_3_ex1_2',
        'description': 'PRE2-3位 & 展示1-2位',
        'multiplier': get_pattern_multiplier('pre2_3_ex1_2', 1.0),  # 修正: 1.084 → 1.0 (逆効果のため無効化)
        'target_rank': 2,
        'condition': lambda pre_rank, ex_rank, st_rank: 2 <= pre_rank <= 3 and ex_rank <= 2,
    },
    {
        'name': 'pre2_ex1_3_st1_3',
        'description': 'PRE2位 & 展示1-3位 & ST1-3位',
        'multiplier': get_pattern_multiplier('pre2_ex1_3_st1_3', 1.081),
        'target_rank': 2,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 2 and ex_rank <= 3 and st_rank <= 3,
    },
    {
        'name': 'ex1_3_pre2_3',
        'description': '展示1-3位 & PRE2-3位',
        'multiplier': get_pattern_multiplier('ex1_3_pre2_3', 1.0),  # 修正: 1.069 → 1.0 (逆効果のため無効化)
        'target_rank': 2,
        'condition': lambda pre_rank, ex_rank, st_rank: ex_rank <= 3 and 2 <= pre_rank <= 3,
    },
    {
        'name': 'pre2_st1_3',
        'description': 'PRE2位 & ST1-3位',
        'multiplier': get_pattern_multiplier('pre2_st1_3', 1.064),
        'target_rank': 2,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 2 and st_rank <= 3,
    },
    {
        'name': 'pre2_ex1_3',
        'description': 'PRE2位 & 展示1-3位',
        'multiplier': get_pattern_multiplier('pre2_ex1_3', 1.063),
        'target_rank': 2,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 2 and ex_rank <= 3,
    },
    {
        'name': 'ex_rank_2',
        'description': '展示2位',
        'multiplier': get_pattern_multiplier('ex_rank_2', 1.0),  # 修正: 1.035 → 1.0 (逆効果-6.0%のため無効化)
        'target_rank': 2,
        'condition': lambda pre_rank, ex_rank, st_rank: ex_rank == 2,
    },
    {
        'name': 'st_rank_2_3',
        'description': 'ST2-3位',
        'multiplier': get_pattern_multiplier('st_rank_2_3', 1.034),
        'target_rank': 2,
        'condition': lambda pre_rank, ex_rank, st_rank: 2 <= st_rank <= 3,
    },
]

BEFORE_PATTERNS_3RD = [
    # 3着予測用パターン（4パターン）
    {
        'name': 'pre3_4_ex2_4',
        'description': 'PRE3-4位 & 展示2-4位',
        'multiplier': get_pattern_multiplier('pre3_4_ex2_4', 1.032),
        'target_rank': 3,
        'condition': lambda pre_rank, ex_rank, st_rank: 3 <= pre_rank <= 4 and 2 <= ex_rank <= 4,
    },
    {
        'name': 'pre3_ex1_3',
        'description': 'PRE3位 & 展示1-3位',
        'multiplier': get_pattern_multiplier('pre3_ex1_3', 1.031),
        'target_rank': 3,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 3 and ex_rank <= 3,
    },
    {
        'name': 'outer_st1_2',
        'description': 'アウトコース(4-6枠) & ST1-2位',
        'multiplier': get_pattern_multiplier('outer_st1_2', 1.022),
        'target_rank': 3,
        'condition': lambda pre_rank, ex_rank, st_rank, pit_number=None: pit_number >= 4 and st_rank <= 2 if pit_number is not None else False,
    },
    {
        'name': 'pre3_4_ex1_3_st1_3',
        'description': 'PRE3-4位 & 展示1-3位 & ST1-3位',
        'multiplier': get_pattern_multiplier('pre3_4_ex1_3_st1_3', 1.020),
        'target_rank': 3,
        'condition': lambda pre_rank, ex_rank, st_rank: 3 <= pre_rank <= 4 and ex_rank <= 3 and st_rank <= 3,
    },
]

BEFORE_PATTERNS_TOP3 = [
    # 3着以内予測用パターン（5パターン + 新規強力パターン + ネガティブパターン）
    # 最強複合パターン: ST1-2位 & 展示1-2位（+123%効果）
    {
        'name': 'st1_2_ex1_2_double_top',
        'description': 'ST1-2位 & 展示1-2位（両方上位、超強力）',
        'multiplier': get_pattern_multiplier('st1_2_ex1_2_double_top', 1.35),  # +123%効果
        'target_rank': 'top3',
        'condition': lambda pre_rank, ex_rank, st_rank: st_rank <= 2 and ex_rank <= 2,
    },
    # 新規強力パターン: PRE1-3位 & ST1位（+15.07%効果、34,985サンプル）
    {
        'name': 'pre1_3_st1',
        'description': 'PRE1-3位 & ST1位（強力）',
        'multiplier': get_pattern_multiplier('pre1_3_st1', 1.23),  # +15.07%効果
        'target_rank': 'top3',
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank <= 3 and st_rank == 1,
    },
    # ネガティブパターン: ST5-6位 & 展示5-6位（-75.75%効果）
    {
        'name': 'st5_6_ex5_6_double_bottom',
        'description': 'ST5-6位 & 展示5-6位（両方下位、大幅ペナルティ）',
        'multiplier': get_pattern_multiplier('st5_6_ex5_6_double_bottom', 0.60),  # -75.75%効果
        'target_rank': 'top3',
        'condition': lambda pre_rank, ex_rank, st_rank: st_rank >= 5 and ex_rank >= 5,
    },
    {
        'name': 'pre1_3_st1_3',
        'description': 'PRE1-3位 & ST1-3位',
        'multiplier': get_pattern_multiplier('pre1_3_st1_3', 1.130),
        'target_rank': 'top3',
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank <= 3 and st_rank <= 3 and st_rank != 1,  # ST1は上のパターンで処理
    },
    {
        'name': 'pre1_3_ex1_3',
        'description': 'PRE1-3位 & 展示1-3位',
        'multiplier': get_pattern_multiplier('pre1_3_ex1_3', 1.123),
        'target_rank': 'top3',
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank <= 3 and ex_rank <= 3,
    },
    {
        'name': 'ex1_3_st1_3',
        'description': '展示1-3位 & ST1-3位',
        'multiplier': get_pattern_multiplier('ex1_3_st1_3', 1.108),
        'target_rank': 'top3',
        'condition': lambda pre_rank, ex_rank, st_rank: ex_rank <= 3 and st_rank <= 3,
    },
    {
        'name': 'pre1_4_ex1_2',
        'description': 'PRE1-4位 & 展示1-2位',
        'multiplier': get_pattern_multiplier('pre1_4_ex1_2', 1.0),  # 修正: 1.104 → 1.0 (逆効果-2.6%のため無効化)
        'target_rank': 'top3',
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank <= 4 and ex_rank <= 2,
    },
    {
        'name': 'ex_rank_1_2',
        'description': '展示1-2位',
        'multiplier': get_pattern_multiplier('ex_rank_1_2', 1.0),  # 修正: 1.051 → 1.0 (逆効果-4.1%のため無効化)
        'target_rank': 'top3',
        'condition': lambda pre_rank, ex_rank, st_rank: ex_rank <= 2,
    },
]


class PatternScorer:
    """
    パターンボーナスを適用するスコアラー

    BEFORE情報（展示タイム、STタイム）に基づいて
    予測スコアにパターンボーナスを適用する。
    """

    def __init__(
        self,
        db_path: str,
        race_data_cache=None,
        pattern_optimizer=None,
        venue_pattern_optimizer=None,
        negative_pattern_checker=None
    ):
        """
        Args:
            db_path: データベースパス
            race_data_cache: レースデータキャッシュ
            pattern_optimizer: パターン優先度オプティマイザー
            venue_pattern_optimizer: 会場別パターンオプティマイザー
            negative_pattern_checker: ネガティブパターンチェッカー
        """
        self.db_path = db_path
        self.race_data_cache = race_data_cache
        self.pattern_optimizer = pattern_optimizer
        self.venue_pattern_optimizer = venue_pattern_optimizer
        self.negative_pattern_checker = negative_pattern_checker
        self.logger = logging.getLogger(__name__)

    def apply_pattern_bonus(
        self,
        predictions: List[Dict],
        race_id: int
    ) -> List[Dict]:
        """
        BEFORE情報パターンボーナスを適用

        Args:
            predictions: 予測結果リスト
            race_id: レースID

        Returns:
            パターンボーナス適用後の予測結果
        """
        # 信頼度チェック
        if predictions:
            top_confidence = predictions[0].get('confidence', 'C')

            if top_confidence in ['A', 'E']:
                self.logger.info(f"Race {race_id}: パターンスキップ（信頼度{top_confidence}）")
                for pred in predictions:
                    pred['pre_score'] = round(pred['total_score'], 1)
                    pred['integration_mode'] = f'pattern_skipped_confidence_{top_confidence}'
                    pred['pattern_multiplier'] = 1.0
                    pred['matched_patterns'] = []
                return predictions

            if top_confidence == 'D':
                if not is_feature_enabled('apply_pattern_to_confidence_d'):
                    self.logger.info(f"Race {race_id}: パターンスキップ（信頼度D・フラグ無効）")
                    for pred in predictions:
                        pred['pre_score'] = round(pred['total_score'], 1)
                        pred['integration_mode'] = 'pattern_skipped_confidence_D'
                        pred['pattern_multiplier'] = 1.0
                        pred['matched_patterns'] = []
                    return predictions

        conn = get_connection(self.db_path)

        # 会場コードを取得
        cursor = conn.cursor()
        cursor.execute("SELECT venue_code FROM races WHERE id = ?", (race_id,))
        venue_row = cursor.fetchone()
        venue_code = venue_row[0] if venue_row else None
        cursor.close()

        # BEFORE情報を取得
        before_data = self._get_before_data(race_id, conn)

        if not before_data or len(before_data) < 6:
            for pred in predictions:
                pred['pre_score'] = round(pred['total_score'], 1)
                pred['integration_mode'] = 'pattern_bonus_unavailable'
            return predictions

        # ランクマップを作成
        exhibition_rank_map = self._build_exhibition_rank_map(before_data)
        st_rank_map = self._build_st_rank_map(before_data)
        pre_rank_map = self._build_pre_rank_map(predictions)

        # 信頼度を取得
        top_confidence = predictions[0].get('confidence', 'C') if predictions else 'C'

        # 各艇にパターンボーナスを適用
        for pred in predictions:
            self._apply_bonus_to_prediction(
                pred, pre_rank_map, exhibition_rank_map, st_rank_map,
                race_id, venue_code, top_confidence
            )

        # スコア降順で再ソート
        predictions.sort(key=lambda x: x['total_score'], reverse=True)

        # ネガティブパターンチェック
        if is_feature_enabled('negative_patterns') and self.negative_pattern_checker:
            predictions = self._apply_negative_patterns(predictions, race_id)

        # サマリーログ
        if predictions:
            top_pred = predictions[0]
            self.logger.info(
                f"Race {race_id}: パターン適用完了 - "
                f"信頼度{top_confidence} | "
                f"トップ予測: 艇{top_pred.get('pit_number')} "
                f"倍率{top_pred.get('pattern_multiplier', 1.0):.3f}"
            )

        return predictions

    def _get_before_data(self, race_id: int, conn) -> Optional[List]:
        """BEFORE情報を取得"""
        if self.race_data_cache:
            cached = self.race_data_cache.get_before_info(race_id)
            if cached is not None:
                return cached

        cursor = conn.cursor()
        cursor.execute("""
            SELECT pit_number, exhibition_time, st_time
            FROM race_details
            WHERE race_id = ?
            ORDER BY pit_number
        """, (race_id,))
        before_data = cursor.fetchall()
        cursor.close()

        if self.race_data_cache and before_data and len(before_data) >= 6:
            self.race_data_cache.set_before_info(race_id, before_data)

        return before_data

    def _build_exhibition_rank_map(self, before_data: List) -> Dict[int, int]:
        """展示タイム順位マップを作成"""
        exhibition_times = [(row[0], row[1]) for row in before_data if row[1] is not None]
        if len(exhibition_times) >= 6:
            exhibition_times_sorted = sorted(exhibition_times, key=lambda x: x[1])
            return {pit: rank+1 for rank, (pit, _) in enumerate(exhibition_times_sorted)}
        return {}

    def _build_st_rank_map(self, before_data: List) -> Dict[int, int]:
        """ST順位マップを作成"""
        st_times = [(row[0], row[2]) for row in before_data if row[2] is not None]
        if len(st_times) >= 6:
            st_times_sorted = sorted(st_times, key=lambda x: abs(x[1]))
            return {pit: rank+1 for rank, (pit, _) in enumerate(st_times_sorted)}
        return {}

    def _build_pre_rank_map(self, predictions: List[Dict]) -> Dict[int, int]:
        """PRE順位マップを作成"""
        predictions_sorted = sorted(predictions, key=lambda x: x['total_score'], reverse=True)
        return {pred['pit_number']: rank+1 for rank, pred in enumerate(predictions_sorted)}

    def _apply_bonus_to_prediction(
        self,
        pred: Dict,
        pre_rank_map: Dict[int, int],
        exhibition_rank_map: Dict[int, int],
        st_rank_map: Dict[int, int],
        race_id: int,
        venue_code: str,
        top_confidence: str
    ):
        """個別の予測にパターンボーナスを適用"""
        pit_number = pred['pit_number']
        pre_score = pred['total_score']

        pre_rank = pre_rank_map.get(pit_number)
        ex_rank = exhibition_rank_map.get(pit_number)
        st_rank = st_rank_map.get(pit_number)

        final_multiplier = 1.0
        matched_patterns = []

        if pre_rank is not None and ex_rank is not None and st_rank is not None:
            # 各パターンをチェック
            matched_patterns = self._check_patterns(pre_rank, ex_rank, st_rank, pit_number)

            # 倍率を決定
            final_multiplier = self._determine_multiplier(
                matched_patterns, pred, race_id, pit_number, venue_code, top_confidence
            )

        # スコア更新
        final_score = pre_score * final_multiplier
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

    def _check_patterns(
        self,
        pre_rank: int,
        ex_rank: int,
        st_rank: int,
        pit_number: int
    ) -> List[Dict]:
        """全パターンをチェック"""
        matched = []

        # 1着パターン
        for pattern in BEFORE_PATTERNS_1ST:
            try:
                if pattern['condition'](pre_rank, ex_rank, st_rank):
                    multiplier = self._get_pattern_multiplier(pattern)
                    matched.append({
                        'name': pattern['name'],
                        'description': pattern['description'],
                        'multiplier': multiplier,
                        'target_rank': pattern['target_rank']
                    })
            except Exception:
                pass

        # 2着パターン
        if pre_rank in [2, 3]:
            for pattern in BEFORE_PATTERNS_2ND:
                try:
                    if pattern['condition'](pre_rank, ex_rank, st_rank):
                        matched.append({
                            'name': pattern['name'],
                            'description': pattern['description'],
                            'multiplier': pattern['multiplier'],
                            'target_rank': pattern['target_rank']
                        })
                except Exception:
                    pass

        # 3着パターン
        if pre_rank in [3, 4]:
            for pattern in BEFORE_PATTERNS_3RD:
                try:
                    if pattern['name'] == 'outer_st1_2':
                        if pit_number >= 4 and st_rank <= 2:
                            matched.append({
                                'name': pattern['name'],
                                'description': pattern['description'],
                                'multiplier': pattern['multiplier'],
                                'target_rank': pattern['target_rank']
                            })
                    elif pattern['condition'](pre_rank, ex_rank, st_rank):
                        matched.append({
                            'name': pattern['name'],
                            'description': pattern['description'],
                            'multiplier': pattern['multiplier'],
                            'target_rank': pattern['target_rank']
                        })
                except Exception:
                    pass

        # TOP3パターン
        for pattern in BEFORE_PATTERNS_TOP3:
            try:
                if pattern['condition'](pre_rank, ex_rank, st_rank):
                    multiplier = self._get_pattern_multiplier(pattern)
                    matched.append({
                        'name': pattern['name'],
                        'description': pattern['description'],
                        'multiplier': multiplier,
                        'target_rank': pattern['target_rank']
                    })
            except Exception:
                pass

        return matched

    def _get_pattern_multiplier(self, pattern: Dict) -> float:
        """パターン倍率を取得（最適化考慮）"""
        # optimized_pattern_multipliers アーカイブ削除（2025-12-22）
        return pattern['multiplier']

    def _determine_multiplier(
        self,
        matched_patterns: List[Dict],
        pred: Dict,
        race_id: int,
        pit_number: int,
        venue_code: str,
        top_confidence: str
    ) -> float:
        """最終倍率を決定"""
        if not matched_patterns:
            return 1.0

        # 最高倍率を取得
        final_multiplier = max(p['multiplier'] for p in matched_patterns)

        if len(matched_patterns) > 1:
            if is_feature_enabled('compound_pattern_bonus'):
                # 複合ボーナス
                sorted_patterns = sorted(matched_patterns, key=lambda p: p['multiplier'], reverse=True)
                if len(sorted_patterns) >= 2:
                    compound = sorted_patterns[0]['multiplier'] * sorted_patterns[1]['multiplier'] * 0.95
                    final_multiplier = min(compound, 1.5)
                    pred['selected_pattern'] = f"{sorted_patterns[0]['name']}+{sorted_patterns[1]['name']}"
            elif self.pattern_optimizer:
                # パターン優先度オプティマイザー
                best = self.pattern_optimizer.select_best_pattern(
                    matched_patterns, top_confidence, venue_code
                )
                if best:
                    final_multiplier = best['multiplier']
                    pred['selected_pattern'] = best['name']
        elif len(matched_patterns) == 1:
            pred['selected_pattern'] = matched_patterns[0]['name']

        # 会場別最適化
        if is_feature_enabled('venue_pattern_optimization') and self.venue_pattern_optimizer:
            if final_multiplier > 1.0:
                pattern_name = pred.get('selected_pattern', 'unknown')
                final_multiplier = self.venue_pattern_optimizer.optimize_pattern_multiplier(
                    final_multiplier, venue_code, pattern_name
                )

        return final_multiplier

    def _apply_negative_patterns(
        self,
        predictions: List[Dict],
        race_id: int
    ) -> List[Dict]:
        """ネガティブパターンを適用"""
        before_ranks_map = {}
        for pred in predictions:
            pit_num = pred.get('pit_number')
            before_ranks_data = pred.get('before_ranks', {})
            if before_ranks_data:
                before_ranks_map[pit_num] = before_ranks_data

        if before_ranks_map:
            predictions = self.negative_pattern_checker.apply_negative_adjustments(
                predictions, before_ranks_map
            )
            self.logger.debug(f"Race {race_id}: ネガティブパターンチェック完了")

        return predictions
