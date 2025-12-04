"""
展示タイム（Exhibition Time）スコアラー v2
会場別標準化と順位重視の改善版

仕様:
- 速い展示タイム（6.70秒など）は有利、遅い展示タイム（7.00+）は不利
- 会場ごとの平均・標準偏差で標準化（Zスコア）
- 順位ベーススコア（1位が最も有利）
- 1位との差分も考慮
- 級別補正（A1/A2は信頼度が高い）

目標: 現在21.6%の的中率を改善
"""

import json
import os
import sqlite3
from typing import Dict, List, Optional


class ExhibitionScorerV2:
    """展示タイムスコアラー v2"""

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

        # 級別信頼度係数
        self.rank_reliability = {
            'A1': 1.2,
            'A2': 1.1,
            'B1': 1.0,
            'B2': 0.9
        }

        # スコアリングパラメータ
        self.RANK_SCORE_BASE = [20.0, 12.0, 6.0, 0.0, -6.0, -12.0]  # 順位別基本スコア
        self.Z_SCORE_WEIGHT = 0.4      # Zスコアの重み
        self.RANK_SCORE_WEIGHT = 0.6   # 順位スコアの重み
        self.MAX_SCORE = 30.0
        self.MIN_SCORE = -30.0

    def _load_venue_stats(self) -> Dict:
        """会場別展示タイム統計を読み込み"""
        if not os.path.exists(self.stats_path):
            raise FileNotFoundError(f"展示タイム統計ファイルが見つかりません: {self.stats_path}")

        with open(self.stats_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def calculate_exhibition_score(
        self,
        venue_code: str,
        pit_number: int,
        beforeinfo_data: Dict,
        racer_data: Optional[Dict] = None
    ) -> Dict:
        """
        展示タイムスコアを計算

        Args:
            venue_code: 会場コード（"01"-"24"）
            pit_number: 艇番（1-6）
            beforeinfo_data: 直前情報辞書
            racer_data: 選手情報辞書（級別取得用、オプション）

        Returns:
            {'exhibition_score': float, 'rank': int, 'z_score': float, ...}
        """
        # 展示タイムを取得
        exhibition_times = beforeinfo_data.get('exhibition_times', {})
        if pit_number not in exhibition_times:
            return {
                'exhibition_score': 0.0,
                'rank': None,
                'z_score': 0.0,
                'rank_adjusted': False,
                'reason': 'exhibition_data_missing'
            }

        exhibition_time = exhibition_times[pit_number]

        # 会場統計を取得
        if venue_code not in self.venue_stats:
            return {
                'exhibition_score': 0.0,
                'rank': None,
                'z_score': 0.0,
                'rank_adjusted': False,
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

        # 級別補正
        rank_adjusted = False
        if racer_data and 'rank' in racer_data:
            racer_rank = racer_data['rank']
            reliability = self.rank_reliability.get(racer_rank, 1.0)
            base_score *= reliability
            rank_adjusted = True

        # スコアをクリップ
        final_score = max(min(base_score, self.MAX_SCORE), self.MIN_SCORE)

        return {
            'exhibition_score': round(final_score, 1),
            'rank': rank,
            'z_score': round(z_score, 2),
            'rank_adjusted': rank_adjusted,
            'exhibition_time': exhibition_time,
            'venue_mean': venue_mean,
            'venue_std': venue_std,
            'gap_from_first': round(gap_from_first, 3) if gap_from_first is not None else None
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

    def calculate_race_exhibition_scores(
        self,
        race_id: str,
        beforeinfo_data: Dict
    ) -> Dict[int, Dict]:
        """
        レース全体の展示タイムスコアを計算

        Args:
            race_id: レースID（例: "202412041201"）
            beforeinfo_data: 直前情報辞書

        Returns:
            {pit_number: exhibition_score_dict, ...}
        """
        # レースIDから会場コードを抽出
        venue_code = race_id[8:10]

        # 選手情報を取得（級別補正用）
        racer_data_dict = self._get_racer_data(race_id)

        # 各艇の展示タイムスコアを計算
        results = {}
        for pit_number in range(1, 7):
            racer_data = racer_data_dict.get(pit_number)
            exhibition_result = self.calculate_exhibition_score(
                venue_code=venue_code,
                pit_number=pit_number,
                beforeinfo_data=beforeinfo_data,
                racer_data=racer_data
            )
            results[pit_number] = exhibition_result

        return results

    def _get_racer_data(self, race_id: str) -> Dict[int, Dict]:
        """
        レースの選手情報を取得（級別補正用）

        Args:
            race_id: レースID

        Returns:
            {pit_number: {'rank': 'A1', ...}, ...}
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            query = """
                SELECT pit_number, racer_rank
                FROM race_entries
                WHERE race_id = ?
            """
            cursor.execute(query, (race_id,))
            rows = cursor.fetchall()
            conn.close()

            result = {}
            for row in rows:
                pit_number, racer_rank = row
                if racer_rank:
                    result[pit_number] = {'rank': racer_rank}

            return result
        except Exception as e:
            print(f"Warning: 選手データ取得エラー: {e}")
            return {}

    def get_venue_stats_summary(self) -> Dict:
        """
        会場統計のサマリーを取得

        Returns:
            統計サマリー辞書
        """
        summary = {
            'total_venues': len(self.venue_stats),
            'mean_range': (
                min(v['mean'] for v in self.venue_stats.values()),
                max(v['mean'] for v in self.venue_stats.values())
            ),
            'std_range': (
                min(v['std'] for v in self.venue_stats.values()),
                max(v['std'] for v in self.venue_stats.values())
            )
        }
        return summary


if __name__ == '__main__':
    # テスト実行
    scorer = ExhibitionScorerV2()

    print("=== 展示タイムスコアラーv2 テスト ===")
    print(f"会場統計サマリー: {scorer.get_venue_stats_summary()}")

    # サンプルデータでテスト
    test_beforeinfo = {
        'exhibition_times': {
            1: 6.75,  # 2位
            2: 6.70,  # 1位（最速）
            3: 6.95,  # 5位
            4: 6.80,  # 3位
            5: 6.85,  # 4位
            6: 7.00   # 6位（最遅）
        }
    }

    test_racer_data = {
        'rank': 'A1'
    }

    # 会場01でテスト
    for pit in range(1, 7):
        result = scorer.calculate_exhibition_score(
            venue_code='01',
            pit_number=pit,
            beforeinfo_data=test_beforeinfo,
            racer_data=test_racer_data
        )
        ex_time = result.get('exhibition_time', 0)
        ex_rank = result.get('rank', '?')
        ex_score = result.get('exhibition_score', 0)
        z_score = result.get('z_score', 0)
        gap = result.get('gap_from_first', 0)
        print(f"艇{pit}: 展示={ex_time:.2f}秒 順位={ex_rank}位 差={gap:.3f}秒 → Zスコア={z_score:.2f} → 展示スコア={ex_score:.1f}点")
