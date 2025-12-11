"""
展示タイムスコアラー v3
2025年詳細分析結果を反映した最適化版

改善点:
1. コース別展示タイムスコア係数（1コース×1.5倍、2-3コース×1.2倍、4-6コース×0.8倍）
2. 展示タイム差ボーナス（1位と2位の差0.1-0.2秒で最大+10点）
3. 級別×展示の複合ボーナス（A1級×展示TOP2で+20点）
4. 三重複合ボーナス（展示×ST×進入で最大+25点）

分析根拠:
- 展示1位×1コース: 64.5%（vs 展示1位×6コース: 3.5%、18.4倍の差）
- 展示TOP2×ST良好×イン: 36.6%（vs 展示3位以下×ST普通×アウト: 2.6%、14.1倍の差）
- 展示1位×A1級: 42.3%（vs 展示1位×B2級: 7.5%、5.6倍の差）
- 展示タイム差0.1-0.2秒: 36.5%（vs 差0.1秒未満: 30.0%）
"""

import json
import os
import sqlite3
from typing import Dict, List, Optional


class ExhibitionScorerV3:
    """展示タイムスコアラー v3 - 詳細分析結果反映版"""

    def __init__(self, db_path: str = "data/boatrace.db", stats_path: str = "data/venue_exhibition_stats.json"):
        """
        初期化

        Args:
            db_path: データベースパス
            stats_path: 会場別展示タイム統計ファイルパス
        """
        self.db_path = db_path
        self.stats_path = stats_path

        # 会場別展示タイム統計を読み込み
        self.venue_stats = self._load_venue_stats()

        # コース別展示タイムスコア係数（分析結果より）
        self.COURSE_COEFFICIENTS = {
            1: 1.5,    # 1コース: 展示1位で64.5%
            2: 1.2,    # 2コース: 展示の影響が中程度
            3: 1.2,    # 3コース: 展示の影響が中程度
            4: 0.8,    # 4コース: 展示の影響が小さい
            5: 0.8,    # 5コース: 展示の影響が小さい
            6: 0.8     # 6コース: 展示1位でも3.5%
        }

        # 級別信頼度係数（v2から継承）
        self.rank_reliability = {
            'A1': 1.2,
            'A2': 1.1,
            'B1': 1.0,
            'B2': 0.9
        }

        # 級別×展示の複合ボーナス（分析結果より）
        self.RANK_EXHIBITION_BONUS = {
            ('A1', 1): 20.0,  # A1級×展示1位: 42.3%
            ('A1', 2): 15.0,  # A1級×展示2位
            ('A2', 1): 15.0,  # A2級×展示1位: 35.7%
            ('A2', 2): 10.0,  # A2級×展示2位
            ('B1', 1): 10.0,  # B1級×展示1位: 21.3%
            ('B1', 2): 5.0,   # B1級×展示2位
            ('B2', 1): 5.0,   # B2級×展示1位: 7.5%
            ('B2', 2): 3.0    # B2級×展示2位
        }

        # スコアリングパラメータ
        self.RANK_SCORE_BASE = [25.0, 15.0, 8.0, 0.0, -8.0, -15.0]  # 順位別基本スコア（強化）
        self.Z_SCORE_WEIGHT = 0.4      # Zスコアの重み
        self.RANK_SCORE_WEIGHT = 0.6   # 順位スコアの重み
        self.MAX_SCORE = 50.0          # 最大スコア拡大（複合ボーナス対応）
        self.MIN_SCORE = -30.0

    def _load_venue_stats(self) -> Dict:
        """会場別展示タイム統計を読み込み"""
        if not os.path.exists(self.stats_path):
            raise FileNotFoundError(f"展示タイム統計ファイルが見つかりません: {self.stats_path}")

        with open(self.stats_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def calculate_time_gap_bonus(self, gap_from_first: Optional[float]) -> float:
        """
        展示タイム差ボーナスを計算

        分析結果:
        - 0.1-0.2秒差: 36.5%（最高）
        - 0.1秒未満: 30.0%
        - 0.2秒以上: 31.2%

        Args:
            gap_from_first: 1位との差（秒）

        Returns:
            ボーナススコア
        """
        if gap_from_first is None or gap_from_first < 0.001:
            # 1位の場合
            return 5.0

        if 0.1 <= gap_from_first < 0.2:
            # 最適な差（明確な優位性）
            return 10.0
        elif gap_from_first < 0.1:
            # 僅差
            return 5.0
        elif gap_from_first < 0.3:
            # やや大きい差
            return 3.0
        else:
            # 大差
            return 0.0

    def calculate_triple_bonus(
        self,
        exh_rank: Optional[int],
        st_time: Optional[float],
        course: Optional[int]
    ) -> float:
        """
        三重複合ボーナス（展示×ST×進入）を計算

        分析結果:
        - 展示TOP2 × ST良好(0.15以下) × イン(1-2コース): 36.6%
        - 展示TOP2 × ST普通 × イン: 22.3%
        - 展示3位以下 × ST良好 × イン: 26.2%
        - 展示3位以下 × ST普通 × アウト: 2.6%

        Args:
            exh_rank: 展示タイム順位
            st_time: STタイム
            course: コース（1-6）

        Returns:
            ボーナススコア
        """
        if exh_rank is None or st_time is None or course is None:
            return 0.0

        exh_top2 = (exh_rank <= 2)
        st_good = (st_time <= 0.15)
        is_inner = (course <= 2)

        # 三重複合ボーナス
        if exh_top2 and st_good and is_inner:
            # 最強組み合わせ: 36.6%
            return 25.0
        elif exh_top2 and is_inner:
            # 展示TOP2×イン（ST普通）: 22.3%
            return 15.0
        elif exh_top2 and st_good:
            # 展示TOP2×ST良好（アウト）: 7.9%
            return 10.0
        elif st_good and is_inner:
            # ST良好×イン（展示3位以下）: 26.2%
            return 10.0
        elif exh_top2:
            # 展示TOP2のみ
            return 5.0
        else:
            return 0.0

    def calculate_exhibition_score(
        self,
        venue_code: str,
        pit_number: int,
        beforeinfo_data: Dict,
        racer_data: Optional[Dict] = None,
        actual_course: Optional[int] = None,
        st_time: Optional[float] = None
    ) -> Dict:
        """
        展示タイムスコアを計算（v3拡張版）

        Args:
            venue_code: 会場コード（"01"-"24"）
            pit_number: 艇番（1-6）
            beforeinfo_data: 直前情報辞書
            racer_data: 選手情報辞書（級別取得用、オプション）
            actual_course: 実際のコース（1-6、オプション）
            st_time: STタイム（オプション）

        Returns:
            {'exhibition_score': float, 'rank': int, ...}
        """
        # 展示タイムを取得
        exhibition_times = beforeinfo_data.get('exhibition_times', {})
        if pit_number not in exhibition_times:
            return {
                'exhibition_score': 0.0,
                'rank': None,
                'z_score': 0.0,
                'bonuses': {},
                'reason': 'exhibition_data_missing'
            }

        exhibition_time = exhibition_times[pit_number]

        # 会場統計を取得
        if venue_code not in self.venue_stats:
            return {
                'exhibition_score': 0.0,
                'rank': None,
                'z_score': 0.0,
                'bonuses': {},
                'reason': 'venue_stats_missing'
            }

        venue_mean = self.venue_stats[venue_code]['mean']
        venue_std = self.venue_stats[venue_code]['std']

        # Zスコア計算（速いほど良い → 符号反転）
        if venue_std < 0.001:
            z_score = 0.0
        else:
            z_score = (venue_mean - exhibition_time) / venue_std

        # Z_scoreベーススコア
        z_based_score = z_score * 15.0

        # 順位計算（全艇のタイムから）
        rank, gap_from_first = self._calculate_rank_and_gap(
            pit_number, exhibition_times
        )

        # 順位ベーススコア
        rank_based_score = 0.0
        if rank is not None and 1 <= rank <= 6:
            rank_based_score = self.RANK_SCORE_BASE[rank - 1]

        # 統合スコア（Zスコア40% + 順位スコア60%）
        base_score = (
            z_based_score * self.Z_SCORE_WEIGHT +
            rank_based_score * self.RANK_SCORE_WEIGHT
        )

        # ボーナス集計用
        bonuses = {}

        # コース別係数（actual_courseがある場合）
        course_coefficient = 1.0
        if actual_course is not None and 1 <= actual_course <= 6:
            course_coefficient = self.COURSE_COEFFICIENTS.get(actual_course, 1.0)
            bonuses['course_coefficient'] = course_coefficient

        # コース係数を適用
        adjusted_score = base_score * course_coefficient

        # 展示タイム差ボーナス
        time_gap_bonus = 0.0
        if rank == 1:
            # 1位の場合は、2位との差を計算
            sorted_times = sorted(
                [(pit, time) for pit, time in exhibition_times.items() if time is not None],
                key=lambda x: x[1]
            )
            if len(sorted_times) >= 2:
                gap_to_second = sorted_times[1][1] - sorted_times[0][1]
                time_gap_bonus = self.calculate_time_gap_bonus(gap_to_second)
                bonuses['time_gap_bonus'] = time_gap_bonus
        elif gap_from_first is not None:
            time_gap_bonus = self.calculate_time_gap_bonus(gap_from_first)
            if time_gap_bonus > 0:
                bonuses['time_gap_bonus'] = time_gap_bonus

        # 級別×展示の複合ボーナス
        rank_exh_bonus = 0.0
        if racer_data and 'rank' in racer_data and rank is not None:
            racer_rank = racer_data['rank']
            bonus_key = (racer_rank, rank)
            if bonus_key in self.RANK_EXHIBITION_BONUS:
                rank_exh_bonus = self.RANK_EXHIBITION_BONUS[bonus_key]
                bonuses['rank_exhibition_bonus'] = rank_exh_bonus

        # 三重複合ボーナス（展示×ST×進入）
        triple_bonus = self.calculate_triple_bonus(rank, st_time, actual_course)
        if triple_bonus > 0:
            bonuses['triple_bonus'] = triple_bonus

        # 全ボーナスを加算
        final_score = adjusted_score + time_gap_bonus + rank_exh_bonus + triple_bonus

        # スコアをクリップ
        final_score = max(min(final_score, self.MAX_SCORE), self.MIN_SCORE)

        return {
            'exhibition_score': round(final_score, 1),
            'rank': rank,
            'z_score': round(z_score, 2),
            'exhibition_time': exhibition_time,
            'venue_mean': venue_mean,
            'venue_std': venue_std,
            'gap_from_first': round(gap_from_first, 3) if gap_from_first is not None else None,
            'base_score': round(base_score, 1),
            'bonuses': bonuses,
            'final_score_breakdown': {
                'base': round(base_score, 1),
                'after_course_coef': round(adjusted_score, 1),
                'time_gap': round(time_gap_bonus, 1),
                'rank_exh': round(rank_exh_bonus, 1),
                'triple': round(triple_bonus, 1),
                'total': round(final_score, 1)
            }
        }

    def _calculate_rank_and_gap(
        self,
        pit_number: int,
        exhibition_times: Dict[int, float]
    ) -> tuple:
        """
        展示タイム順位と1位との差分を計算

        Args:
            pit_number: 艇番
            exhibition_times: {pit_number: time, ...}

        Returns:
            (rank, gap_from_first)
        """
        if pit_number not in exhibition_times:
            return None, None

        # 有効なタイムをソート
        valid_times = [(pit, time) for pit, time in exhibition_times.items() if time is not None]
        if not valid_times:
            return None, None

        sorted_times = sorted(valid_times, key=lambda x: x[1])

        # 順位を計算
        rank = None
        for idx, (pit, time) in enumerate(sorted_times):
            if pit == pit_number:
                rank = idx + 1
                break

        # 1位との差分
        first_time = sorted_times[0][1]
        my_time = exhibition_times[pit_number]
        gap_from_first = my_time - first_time

        return rank, gap_from_first


if __name__ == '__main__':
    # テスト実行
    scorer = ExhibitionScorerV3()

    print("=== 展示タイムスコアラーv3 テスト ===")
    print("\n【テストケース1】展示1位×1コース×A1級×ST良好（最強組み合わせ）")

    test_beforeinfo = {
        'exhibition_times': {
            1: 6.70,  # 1位（最速）
            2: 6.85,  # 2位（差0.15秒）
            3: 6.95,
            4: 7.00,
            5: 7.05,
            6: 7.10
        }
    }

    test_racer = {'rank': 'A1'}

    result1 = scorer.calculate_exhibition_score(
        venue_code='01',
        pit_number=1,
        beforeinfo_data=test_beforeinfo,
        racer_data=test_racer,
        actual_course=1,
        st_time=0.12
    )

    print(f"展示タイム: {result1['exhibition_time']}秒（{result1['rank']}位）")
    print(f"基本スコア: {result1['base_score']}点")
    print(f"ボーナス: {result1['bonuses']}")
    print(f"最終スコア: {result1['exhibition_score']}点")
    print(f"内訳: {result1['final_score_breakdown']}")

    print("\n【テストケース2】展示3位以下×アウトコース×B2級×ST普通（最弱組み合わせ）")

    result2 = scorer.calculate_exhibition_score(
        venue_code='01',
        pit_number=6,
        beforeinfo_data=test_beforeinfo,
        racer_data={'rank': 'B2'},
        actual_course=6,
        st_time=0.20
    )

    print(f"展示タイム: {result2['exhibition_time']}秒（{result2['rank']}位）")
    print(f"基本スコア: {result2['base_score']}点")
    print(f"ボーナス: {result2['bonuses']}")
    print(f"最終スコア: {result2['exhibition_score']}点")
    print(f"内訳: {result2['final_score_breakdown']}")

    print("\n【テストケース3】展示1位×2位の差0.15秒（最適差分）")

    result3 = scorer.calculate_exhibition_score(
        venue_code='01',
        pit_number=1,
        beforeinfo_data=test_beforeinfo,
        racer_data={'rank': 'A2'},
        actual_course=2,
        st_time=0.14
    )

    print(f"展示タイム: {result3['exhibition_time']}秒（{result3['rank']}位）")
    print(f"1位と2位の差: 0.15秒")
    print(f"基本スコア: {result3['base_score']}点")
    print(f"ボーナス: {result3['bonuses']}")
    print(f"最終スコア: {result3['exhibition_score']}点")
    print(f"内訳: {result3['final_score_breakdown']}")
