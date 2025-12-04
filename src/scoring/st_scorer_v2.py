"""
ST（スタート）スコアラー v2
会場別標準化と級別補正を実装した改善版

仕様:
- 速いST（0.10など）は有利、遅いST（0.20+）は不利
- 会場ごとの平均・標準偏差で標準化（Zスコア）
- A1/A2の信頼度補正
- 風向との相互作用（オプション）

目標: 現在0%の的中率を改善
"""

import json
import os
import sqlite3
from typing import Dict, Optional


class STScorerV2:
    """ST（スタート）スコアラー v2"""

    def __init__(self, db_path: str = "data/boatrace.db", stats_path: str = "data/venue_st_stats.json"):
        """
        初期化

        Args:
            db_path: データベースパス
            stats_path: 会場別ST統計ファイルパス
        """
        self.db_path = db_path
        self.stats_path = stats_path

        # 会場別ST統計を読み込み
        self.venue_stats = self._load_venue_stats()

        # 級別信頼度係数
        self.rank_reliability = {
            'A1': 1.2,  # A1は安定性が高い
            'A2': 1.1,
            'B1': 1.0,
            'B2': 0.9   # B2は不安定
        }

        # スコアリングパラメータ
        self.SCORE_MULTIPLIER = 15.0  # Zスコア → 点数変換係数
        self.MAX_SCORE = 30.0         # 最大スコア
        self.MIN_SCORE = -30.0        # 最小スコア

    def _load_venue_stats(self) -> Dict:
        """会場別ST統計を読み込み"""
        if not os.path.exists(self.stats_path):
            raise FileNotFoundError(f"ST統計ファイルが見つかりません: {self.stats_path}")

        with open(self.stats_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def calculate_st_score(
        self,
        venue_code: str,
        pit_number: int,
        beforeinfo_data: Dict,
        racer_data: Optional[Dict] = None
    ) -> Dict:
        """
        ST（スタート）スコアを計算

        Args:
            venue_code: 会場コード（"01"-"24"）
            pit_number: 艇番（1-6）
            beforeinfo_data: 直前情報辞書
            racer_data: 選手情報辞書（級別取得用、オプション）

        Returns:
            {'st_score': float, 'z_score': float, 'rank_adjusted': bool}
        """
        # ST値を取得
        st_times = beforeinfo_data.get('st_times', {})
        if pit_number not in st_times:
            return {'st_score': 0.0, 'z_score': 0.0, 'rank_adjusted': False, 'reason': 'st_data_missing'}

        st_value = st_times[pit_number]

        # 会場統計を取得
        if venue_code not in self.venue_stats:
            return {'st_score': 0.0, 'z_score': 0.0, 'rank_adjusted': False, 'reason': 'venue_stats_missing'}

        venue_mean = self.venue_stats[venue_code]['mean']
        venue_std = self.venue_stats[venue_code]['std']

        # Zスコア計算（標準化）
        # 速いST（平均より小さい）は負のZスコア → 正のスコアにする必要がある
        # → 符号を反転: z_score = -(st_value - mean) / std = (mean - st_value) / std
        if venue_std < 0.001:
            z_score = 0.0
        else:
            z_score = (venue_mean - st_value) / venue_std

        # 基本スコア計算
        base_score = z_score * self.SCORE_MULTIPLIER

        # 級別補正（選手情報があれば）
        rank_adjusted = False
        if racer_data and 'rank' in racer_data:
            rank = racer_data['rank']
            reliability = self.rank_reliability.get(rank, 1.0)
            base_score *= reliability
            rank_adjusted = True

        # スコアをクリップ
        final_score = max(min(base_score, self.MAX_SCORE), self.MIN_SCORE)

        return {
            'st_score': round(final_score, 1),
            'z_score': round(z_score, 2),
            'rank_adjusted': rank_adjusted,
            'st_value': st_value,
            'venue_mean': venue_mean,
            'venue_std': venue_std
        }

    def calculate_race_st_scores(
        self,
        race_id: str,
        beforeinfo_data: Dict
    ) -> Dict[int, Dict]:
        """
        レース全体のSTスコアを計算

        Args:
            race_id: レースID（例: "202412041201"）
            beforeinfo_data: 直前情報辞書

        Returns:
            {pit_number: st_score_dict, ...}
        """
        # レースIDから会場コードを抽出（YYYYMMDDVVRR形式）
        venue_code = race_id[8:10]

        # 選手情報を取得（級別補正用）
        racer_data_dict = self._get_racer_data(race_id)

        # 各艇のSTスコアを計算
        results = {}
        for pit_number in range(1, 7):
            racer_data = racer_data_dict.get(pit_number)
            st_result = self.calculate_st_score(
                venue_code=venue_code,
                pit_number=pit_number,
                beforeinfo_data=beforeinfo_data,
                racer_data=racer_data
            )
            results[pit_number] = st_result

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
    scorer = STScorerV2()

    print("=== STスコアラーv2 テスト ===")
    print(f"会場統計サマリー: {scorer.get_venue_stats_summary()}")

    # サンプルデータでテスト
    test_beforeinfo = {
        'st_times': {
            1: 0.10,  # 速いST
            2: 0.17,  # 平均的
            3: 0.25,  # 遅いST
            4: 0.15,
            5: 0.18,
            6: 0.20
        }
    }

    test_racer_data = {
        'rank': 'A1'
    }

    # 会場01でテスト
    for pit in range(1, 7):
        result = scorer.calculate_st_score(
            venue_code='01',
            pit_number=pit,
            beforeinfo_data=test_beforeinfo,
            racer_data=test_racer_data
        )
        st_val = result.get('st_value', 0)
        st_score = result.get('st_score', 0)
        z_score = result.get('z_score', 0)
        print(f"艇{pit}: ST={st_val:.2f}秒 → Zスコア={z_score:.2f} → STスコア={st_score:.1f}点")
