# -*- coding: utf-8 -*-
"""
予測バイアス指数計算モジュール

選手の「予測されやすさ」と「実際の結果」のズレを測定する。
- Bias Index: 予想より上に来やすいか、下に来やすいか
- Error Variance: 外れる時のブレ幅

これらは「精度向上そのもの」に直結する指数。
"""

import sqlite3
import math
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple
from pathlib import Path


@dataclass
class PlayerBiasIndex:
    """選手別バイアス指数"""
    player_id: str
    stadium_id: Optional[str]  # None=全国
    total_races: int

    # 順位誤差の方向性（Bias Index）
    # 誤差 = 実着順 - 予想順位
    # マイナス → 予想より上に来やすい（穴源）
    # プラス → 過大評価されがち
    bias_index: Optional[float]

    # 着順差の分散（Error Variance）
    # 分散小 → 外れても2~3着（安定）
    # 分散大 → 4~6着に飛ぶ（不安定）
    error_variance: Optional[float]
    error_std: Optional[float]  # 標準偏差

    # 詳細統計
    avg_predicted_rank: float  # 平均予想順位
    avg_actual_rank: float     # 平均実着順
    hit_rate_top3: float       # 3着以内率

    period_start: str
    period_end: str


class PredictionBiasCalculator:
    """予測バイアス計算クラス"""

    MIN_RACES = 20  # 母数制限

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = Path(__file__).parent.parent.parent / "data" / "boatrace.db"
        self.db_path = str(db_path)

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def get_player_bias_index(
        self,
        player_id: str,
        stadium_id: Optional[str] = None,
        prediction_type: str = 'before',
        period_start: str = "2000-01-01",
        period_end: str = "2099-12-31"
    ) -> Optional[PlayerBiasIndex]:
        """
        選手のバイアス指数を計算

        Args:
            player_id: 選手ID
            stadium_id: 会場ID（None=全国）
            prediction_type: 予測タイプ ('advance' or 'before')
            period_start: 集計開始日
            period_end: 集計終了日
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # 予測と実績を結合
            sql = """
            SELECT
                rp.rank_prediction,
                CAST(r.rank AS INTEGER) as actual_rank
            FROM race_predictions rp
            JOIN results r ON rp.race_id = r.race_id AND rp.pit_number = r.pit_number
            JOIN races rc ON rp.race_id = rc.id
            WHERE rp.racer_number = ?
              AND rp.prediction_type = ?
              AND r.rank IN ('1', '2', '3', '4', '5', '6')
              AND rc.race_date BETWEEN ? AND ?
            """
            params = [player_id, prediction_type, period_start, period_end]

            if stadium_id:
                sql += " AND rc.venue_code = ?"
                params.append(stadium_id)

            cursor.execute(sql, params)
            rows = cursor.fetchall()

            if len(rows) < self.MIN_RACES:
                return None

            # 統計計算
            errors = [actual - pred for pred, actual in rows]
            predictions = [pred for pred, actual in rows]
            actuals = [actual for pred, actual in rows]

            # Bias Index（平均誤差）
            bias_index = sum(errors) / len(errors)

            # Error Variance（誤差の分散）
            mean_error = bias_index
            variance = sum((e - mean_error) ** 2 for e in errors) / len(errors)
            std_dev = math.sqrt(variance)

            # その他統計
            avg_pred = sum(predictions) / len(predictions)
            avg_actual = sum(actuals) / len(actuals)
            top3_rate = sum(1 for a in actuals if a <= 3) / len(actuals)

            return PlayerBiasIndex(
                player_id=player_id,
                stadium_id=stadium_id,
                total_races=len(rows),
                bias_index=bias_index,
                error_variance=variance,
                error_std=std_dev,
                avg_predicted_rank=avg_pred,
                avg_actual_rank=avg_actual,
                hit_rate_top3=top3_rate,
                period_start=period_start,
                period_end=period_end
            )

        finally:
            conn.close()

    def build_player_bias_stats(
        self,
        prediction_type: str = 'before',
        period_start: str = "2000-01-01",
        period_end: str = "2099-12-31"
    ) -> int:
        """
        全選手のバイアス指数を計算してDBに保存
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # テーブル作成
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS player_bias_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id TEXT NOT NULL,
            stadium_id TEXT,
            total_races INTEGER NOT NULL,
            bias_index REAL,
            error_variance REAL,
            error_std REAL,
            avg_predicted_rank REAL,
            avg_actual_rank REAL,
            hit_rate_top3 REAL,
            prediction_type TEXT NOT NULL,
            period_start DATE NOT NULL,
            period_end DATE NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(player_id, stadium_id, prediction_type, period_start, period_end)
        )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bias_player ON player_bias_stats(player_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bias_bias ON player_bias_stats(bias_index)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bias_variance ON player_bias_stats(error_variance)")

        # 予測データがある選手リスト取得
        cursor.execute("""
        SELECT DISTINCT racer_number
        FROM race_predictions
        WHERE prediction_type = ?
          AND racer_number IS NOT NULL
        """, [prediction_type])
        players = [row[0] for row in cursor.fetchall()]

        print(f"選手数: {len(players)}")

        saved = 0
        for i, player_id in enumerate(players):
            if (i + 1) % 500 == 0:
                print(f"  処理中: {i + 1}/{len(players)}")

            bias = self.get_player_bias_index(
                player_id, None, prediction_type, period_start, period_end
            )
            if bias:
                cursor.execute("""
                INSERT OR REPLACE INTO player_bias_stats
                (player_id, stadium_id, total_races, bias_index, error_variance, error_std,
                 avg_predicted_rank, avg_actual_rank, hit_rate_top3, prediction_type, period_start, period_end)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    bias.player_id, bias.stadium_id, bias.total_races,
                    bias.bias_index, bias.error_variance, bias.error_std,
                    bias.avg_predicted_rank, bias.avg_actual_rank, bias.hit_rate_top3,
                    prediction_type, bias.period_start, bias.period_end
                ))
                saved += 1

        conn.commit()
        conn.close()

        print(f"保存完了: {saved}件")
        return saved


# テスト
if __name__ == "__main__":
    calc = PredictionBiasCalculator()

    # サンプルテスト
    print("=== バイアス指数テスト ===")
    test_players = ['4444', '4320', '4024']

    for pid in test_players:
        bias = calc.get_player_bias_index(pid)
        if bias:
            print(f"\n選手 {pid}:")
            print(f"  サンプル数: {bias.total_races}")
            print(f"  Bias Index: {bias.bias_index:+.3f}")
            print(f"    → {'予想より上に来やすい' if bias.bias_index < 0 else '過大評価されがち'}")
            print(f"  誤差分散: {bias.error_variance:.3f} (SD={bias.error_std:.3f})")
            print(f"  平均予想: {bias.avg_predicted_rank:.2f}位")
            print(f"  平均実着: {bias.avg_actual_rank:.2f}位")
            print(f"  3着内率: {bias.hit_rate_top3:.1%}")
