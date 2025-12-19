"""
モンテカルロレースシミュレーター

大量のレースシミュレーションを実行し、
順位分布（1着確率、2着確率、3着確率）を算出する。

性能最適化:
- NumPyベクトル演算
- 並列処理（multiprocessing）
- 早期終了による効率化
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import time
import logging

from .race_physics import RacePhysicsModel


@dataclass
class SimulationResult:
    """シミュレーション結果"""
    rank_distribution: Dict[int, Dict[int, float]]  # {pit: {rank: probability}}
    win_probs: Dict[int, float]  # {pit: 1着確率}
    place_probs: Dict[int, float]  # {pit: 2着確率}
    show_probs: Dict[int, float]  # {pit: 3着確率}
    trifecta_probs: Dict[Tuple[int, int, int], float]  # {(1着,2着,3着): 確率}
    simulation_count: int
    execution_time_ms: float


class MonteCarloRaceSimulator:
    """
    モンテカルロレースシミュレーター

    レースを大量にシミュレーションし、確率分布を算出。
    """

    def __init__(
        self,
        n_simulations: int = 10000,
        seed: Optional[int] = None,
        use_parallel: bool = False,
        n_workers: int = 4
    ):
        """
        シミュレーターの初期化

        Args:
            n_simulations: シミュレーション回数
            seed: 乱数シード（再現性のため）
            use_parallel: 並列処理を使用するか
            n_workers: 並列処理のワーカー数
        """
        self.n_simulations = n_simulations
        self.seed = seed
        self.use_parallel = use_parallel
        self.n_workers = n_workers
        self.logger = logging.getLogger(__name__)

    def simulate_race(
        self,
        predictions: List[Dict],
        wind_speed: float = 0.0,
        wave_height: float = 0.0,
        wind_direction: Optional[str] = None
    ) -> SimulationResult:
        """
        レースをシミュレート

        Args:
            predictions: 予測結果リスト（各艇のスコア・情報）
            wind_speed: 風速
            wave_height: 波高
            wind_direction: 風向

        Returns:
            SimulationResult: シミュレーション結果
        """
        start_time = time.time()

        # 物理モデルを初期化
        physics = RacePhysicsModel(
            wind_speed=wind_speed,
            wave_height=wave_height,
            wind_direction=wind_direction
        )

        # 各艇のパラメータを推定
        boat_params = []
        for pred in predictions:
            pit_number = pred['pit_number']
            total_score = pred.get('total_score', 50.0)
            motor_score = pred.get('motor_score', 10.0)

            # 級別を取得（extended_detailから、なければデフォルト）
            grade = 'B1'  # デフォルト
            if 'extended_detail' in pred:
                class_info = pred['extended_detail'].get('class', {})
                grade = class_info.get('class_name', 'B1')
            elif 'racer_rank' in pred:
                grade = pred.get('racer_rank', 'B1')

            # 平均STを取得
            avg_st = None
            if 'extended_detail' in pred:
                st_info = pred['extended_detail'].get('start_timing', {})
                avg_st = st_info.get('avg_st')

            params = physics.estimate_boat_parameters(
                total_score=total_score,
                grade=grade,
                avg_st=avg_st,
                motor_score=motor_score
            )
            params['pit_number'] = pit_number
            params['course'] = pit_number  # 予測時は枠番=コース
            boat_params.append(params)

        # シミュレーション実行
        if self.use_parallel:
            result = self._simulate_parallel(physics, boat_params)
        else:
            result = self._simulate_sequential(physics, boat_params)

        # 実行時間を記録
        result.execution_time_ms = (time.time() - start_time) * 1000

        return result

    def _simulate_sequential(
        self,
        physics: RacePhysicsModel,
        boat_params: List[Dict]
    ) -> SimulationResult:
        """
        逐次シミュレーション

        Args:
            physics: 物理モデル
            boat_params: 艇パラメータリスト

        Returns:
            シミュレーション結果
        """
        # 乱数生成器
        rng = np.random.default_rng(self.seed)

        # カウンター初期化
        n_boats = len(boat_params)
        rank_counts = {i + 1: {r: 0 for r in range(1, 7)} for i in range(n_boats)}
        trifecta_counts: Dict[Tuple[int, int, int], int] = {}

        # シミュレーション実行
        for _ in range(self.n_simulations):
            result = physics.simulate_race(boat_params, rng)

            # 順位をカウント
            for rank, pit in enumerate(result, 1):
                if rank <= 6 and pit in rank_counts:
                    rank_counts[pit][rank] += 1

            # 三連単をカウント
            if len(result) >= 3:
                trifecta = tuple(result[:3])
                trifecta_counts[trifecta] = trifecta_counts.get(trifecta, 0) + 1

        return self._calculate_probabilities(
            rank_counts, trifecta_counts, self.n_simulations
        )

    def _simulate_parallel(
        self,
        physics: RacePhysicsModel,
        boat_params: List[Dict]
    ) -> SimulationResult:
        """
        並列シミュレーション

        Args:
            physics: 物理モデル
            boat_params: 艇パラメータリスト

        Returns:
            シミュレーション結果
        """
        # チャンクに分割
        chunk_size = self.n_simulations // self.n_workers
        chunks = []
        for i in range(self.n_workers):
            seed = self.seed + i if self.seed else None
            chunks.append((physics, boat_params, chunk_size, seed))

        # 並列実行（ThreadPoolを使用、ProcessPoolはpickle問題を回避）
        n_boats = len(boat_params)
        total_rank_counts = {i + 1: {r: 0 for r in range(1, 7)} for i in range(n_boats)}
        total_trifecta_counts: Dict[Tuple[int, int, int], int] = {}

        with ThreadPoolExecutor(max_workers=self.n_workers) as executor:
            futures = [
                executor.submit(self._run_chunk, *chunk)
                for chunk in chunks
            ]

            for future in futures:
                rank_counts, trifecta_counts = future.result()
                # 結果を統合
                for pit in total_rank_counts:
                    for rank in total_rank_counts[pit]:
                        total_rank_counts[pit][rank] += rank_counts.get(pit, {}).get(rank, 0)
                for trifecta, count in trifecta_counts.items():
                    total_trifecta_counts[trifecta] = total_trifecta_counts.get(trifecta, 0) + count

        return self._calculate_probabilities(
            total_rank_counts, total_trifecta_counts, self.n_simulations
        )

    def _run_chunk(
        self,
        physics: RacePhysicsModel,
        boat_params: List[Dict],
        n_sims: int,
        seed: Optional[int]
    ) -> Tuple[Dict, Dict]:
        """
        チャンクを実行

        Args:
            physics: 物理モデル
            boat_params: 艇パラメータ
            n_sims: シミュレーション回数
            seed: 乱数シード

        Returns:
            (順位カウント, 三連単カウント)
        """
        rng = np.random.default_rng(seed)
        n_boats = len(boat_params)
        rank_counts = {i + 1: {r: 0 for r in range(1, 7)} for i in range(n_boats)}
        trifecta_counts: Dict[Tuple[int, int, int], int] = {}

        for _ in range(n_sims):
            result = physics.simulate_race(boat_params, rng)

            for rank, pit in enumerate(result, 1):
                if rank <= 6 and pit in rank_counts:
                    rank_counts[pit][rank] += 1

            if len(result) >= 3:
                trifecta = tuple(result[:3])
                trifecta_counts[trifecta] = trifecta_counts.get(trifecta, 0) + 1

        return rank_counts, trifecta_counts

    def _calculate_probabilities(
        self,
        rank_counts: Dict[int, Dict[int, int]],
        trifecta_counts: Dict[Tuple[int, int, int], int],
        total_sims: int
    ) -> SimulationResult:
        """
        カウントから確率を計算

        Args:
            rank_counts: 順位カウント
            trifecta_counts: 三連単カウント
            total_sims: 総シミュレーション数

        Returns:
            SimulationResult
        """
        rank_distribution = {}
        win_probs = {}
        place_probs = {}
        show_probs = {}

        for pit, counts in rank_counts.items():
            rank_distribution[pit] = {
                rank: count / total_sims
                for rank, count in counts.items()
            }
            win_probs[pit] = counts.get(1, 0) / total_sims
            place_probs[pit] = counts.get(2, 0) / total_sims
            show_probs[pit] = counts.get(3, 0) / total_sims

        # 三連単確率（上位のみ）
        trifecta_probs = {}
        sorted_trifecta = sorted(
            trifecta_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:50]  # 上位50件

        for trifecta, count in sorted_trifecta:
            trifecta_probs[trifecta] = count / total_sims

        return SimulationResult(
            rank_distribution=rank_distribution,
            win_probs=win_probs,
            place_probs=place_probs,
            show_probs=show_probs,
            trifecta_probs=trifecta_probs,
            simulation_count=total_sims,
            execution_time_ms=0.0  # 後で設定
        )

    def integrate_with_ml_predictions(
        self,
        ml_predictions: List[Dict],
        sim_result: SimulationResult,
        delta: float = 0.5
    ) -> List[Dict]:
        """
        MLの予測結果とシミュレーション結果を統合

        Args:
            ml_predictions: ML予測結果
            sim_result: シミュレーション結果
            delta: MLの重み（0-1、1に近いほどML重視）

        Returns:
            統合後の予測結果
        """
        predictions = [pred.copy() for pred in ml_predictions]

        # 予測をスコア順にソート
        predictions.sort(key=lambda x: x['total_score'], reverse=True)

        # MLの順位から確率を推定（softmax）
        ml_scores = np.array([p['total_score'] for p in predictions])
        temperature = 10.0
        exp_scores = np.exp(ml_scores / temperature)
        ml_probs = exp_scores / np.sum(exp_scores)

        # 統合
        for i, pred in enumerate(predictions):
            pit = pred['pit_number']

            # ML確率
            ml_win_prob = ml_probs[i] if i == 0 else ml_probs[i] * 0.5
            ml_place_prob = ml_probs[i] * 0.8
            ml_show_prob = ml_probs[i] * 0.9

            # シミュレーション確率
            sim_win_prob = sim_result.win_probs.get(pit, 0.0)
            sim_place_prob = sim_result.place_probs.get(pit, 0.0)
            sim_show_prob = sim_result.show_probs.get(pit, 0.0)

            # 統合確率
            integrated_win_prob = delta * ml_win_prob + (1 - delta) * sim_win_prob
            integrated_place_prob = delta * ml_place_prob + (1 - delta) * sim_place_prob
            integrated_show_prob = delta * ml_show_prob + (1 - delta) * sim_show_prob

            # 順位分布を追加
            pred['simulation_1st_prob'] = round(sim_win_prob * 100, 1)
            pred['simulation_2nd_prob'] = round(sim_place_prob * 100, 1)
            pred['simulation_3rd_prob'] = round(sim_show_prob * 100, 1)

            pred['integrated_1st_prob'] = round(integrated_win_prob * 100, 1)
            pred['integrated_2nd_prob'] = round(integrated_place_prob * 100, 1)
            pred['integrated_3rd_prob'] = round(integrated_show_prob * 100, 1)

            # スコア調整（シミュレーション結果を反映）
            # 2着・3着確率が高い艇はスコアを微調整
            place_adjustment = (sim_place_prob + sim_show_prob) * 5.0  # 最大5点
            pred['simulation_adjustment'] = round(place_adjustment, 1)

        return predictions

    def get_simulation_stats(self, sim_result: SimulationResult) -> Dict:
        """
        シミュレーション結果の統計を取得

        Args:
            sim_result: シミュレーション結果

        Returns:
            統計情報
        """
        stats = {
            'simulation_count': sim_result.simulation_count,
            'execution_time_ms': round(sim_result.execution_time_ms, 1),
            'top_trifecta': [],
            'rank_summary': {}
        }

        # 三連単上位5件
        sorted_trifecta = sorted(
            sim_result.trifecta_probs.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        stats['top_trifecta'] = [
            {'combination': list(t), 'probability': round(p * 100, 2)}
            for t, p in sorted_trifecta
        ]

        # 各艇の順位サマリー
        for pit, probs in sim_result.rank_distribution.items():
            stats['rank_summary'][pit] = {
                '1st': round(probs.get(1, 0) * 100, 1),
                '2nd': round(probs.get(2, 0) * 100, 1),
                '3rd': round(probs.get(3, 0) * 100, 1),
                'top3': round((probs.get(1, 0) + probs.get(2, 0) + probs.get(3, 0)) * 100, 1),
            }

        return stats


class SimulationScoreIntegrator:
    """
    シミュレーション結果をスコアに統合するクラス
    """

    def __init__(
        self,
        n_simulations: int = 5000,
        integration_weight: float = 0.3,
        use_for_rank23: bool = True
    ):
        """
        初期化

        Args:
            n_simulations: シミュレーション回数
            integration_weight: シミュレーションの統合重み（0-1）
            use_for_rank23: 2着・3着予測に使用するか
        """
        self.simulator = MonteCarloRaceSimulator(
            n_simulations=n_simulations,
            use_parallel=False  # 高速化のためシングルスレッド
        )
        self.integration_weight = integration_weight
        self.use_for_rank23 = use_for_rank23
        self.logger = logging.getLogger(__name__)

    def apply_simulation(
        self,
        predictions: List[Dict],
        wind_speed: float = 0.0,
        wave_height: float = 0.0,
        wind_direction: Optional[str] = None
    ) -> List[Dict]:
        """
        シミュレーション結果を予測に適用

        Args:
            predictions: 予測結果リスト
            wind_speed: 風速
            wave_height: 波高
            wind_direction: 風向

        Returns:
            シミュレーション適用後の予測結果
        """
        if not predictions:
            return predictions

        try:
            # シミュレーション実行
            sim_result = self.simulator.simulate_race(
                predictions,
                wind_speed=wind_speed,
                wave_height=wave_height,
                wind_direction=wind_direction
            )

            # 統合
            integrated = self.simulator.integrate_with_ml_predictions(
                predictions,
                sim_result,
                delta=1.0 - self.integration_weight  # ML重視側のdelta
            )

            # 2着・3着予測に使用する場合、スコアを調整
            if self.use_for_rank23:
                integrated = self._adjust_rank23_scores(integrated, sim_result)

            # 統計情報を最初の予測に追加
            if integrated:
                stats = self.simulator.get_simulation_stats(sim_result)
                integrated[0]['simulation_stats'] = stats

            return integrated

        except Exception as e:
            self.logger.warning(f"シミュレーション適用エラー: {e}")
            return predictions

    def _adjust_rank23_scores(
        self,
        predictions: List[Dict],
        sim_result: SimulationResult
    ) -> List[Dict]:
        """
        2着・3着予測のためにスコアを調整

        Args:
            predictions: 予測結果
            sim_result: シミュレーション結果

        Returns:
            調整後の予測結果
        """
        # 1着予測は維持し、2着・3着候補のスコアを調整
        predictions.sort(key=lambda x: x['total_score'], reverse=True)

        for pred in predictions[1:]:  # 1着候補以外
            pit = pred['pit_number']

            # シミュレーションの2着・3着確率
            sim_2nd = sim_result.place_probs.get(pit, 0.0)
            sim_3rd = sim_result.show_probs.get(pit, 0.0)

            # 2着・3着確率が高い艇はボーナス
            # 最大3点のボーナス
            rank23_bonus = (sim_2nd + sim_3rd) * 3.0
            pred['total_score'] = min(100.0, pred['total_score'] + rank23_bonus)
            pred['simulation_rank23_bonus'] = round(rank23_bonus, 1)

        return predictions
