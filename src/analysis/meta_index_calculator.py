# -*- coding: utf-8 -*-
"""
メタ指数計算モジュール

「当たる予想」ではなく「負けない予想環境」を作るための安全装置。
着順予測とは独立に「そのレースが予想可能か/回避すべきか」を判定する。

指数一覧:
1. 着順分布エントロピー（Stability Entropy）: 選手の着順分布の安定性
2. 展開依存度指数（Self-Driven Index）: 自力型/展開依存型の判定
3. 予測乖離指数（Prediction Deviation）: 予測と実績の乖離度
"""

import math
import sqlite3
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple
from pathlib import Path


@dataclass
class PlayerMetaIndex:
    """選手別メタ指数"""
    player_id: str
    stadium_id: Optional[str]  # None=全国
    total_races: int

    # 着順分布エントロピー
    stability_entropy: Optional[float]  # 0=安定, 1=不安定
    stability_entropy_raw: Optional[float]  # 正規化前

    # 上位独占率（Dominance Rate）
    dominance_rate: Optional[float]  # (1着+2着)/総数。高い=軸向き

    # 展開依存度指数（Self-Driven Index）
    self_driven_index: Optional[float]  # (1着-4着以下)/総数。正規化版も追加

    # 内訳データ
    rank_distribution: Dict[int, int]  # {1: 回数, 2: 回数, ...}
    first_place_count: int
    second_place_count: int
    bottom_count: int  # 4着以下

    period_start: str
    period_end: str


@dataclass
class RaceMetaIndex:
    """レース単位メタ指数"""
    race_id: int

    # 出走選手の平均指数
    avg_stability_entropy: Optional[float]
    avg_self_driven_index: Optional[float]

    # 予測乖離指数（予測データがある場合のみ）
    prediction_deviation: Optional[float]  # 平均乖離
    prediction_deviation_norm: Optional[float]  # 正規化（0-1）

    # 詳細
    player_count: int
    players_with_index: int  # 指数算出可能な選手数


class MetaIndexCalculator:
    """メタ指数計算クラス"""

    # 母数制限
    MIN_RACES_NATIONAL = 20  # 全国: 20走以上
    MIN_RACES_LOCAL = 15     # 当地: 15走以上

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = Path(__file__).parent.parent.parent / "data" / "boatrace.db"
        self.db_path = str(db_path)

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    # ========================================
    # 着順分布エントロピー（Stability Entropy）
    # ========================================

    def calculate_stability_entropy(self, rank_counts: Dict[int, int]) -> Tuple[Optional[float], Optional[float]]:
        """
        着順分布からエントロピーを計算

        Args:
            rank_counts: {1: 回数, 2: 回数, ..., 6: 回数}

        Returns:
            (正規化エントロピー, 生エントロピー)
            - 0に近い → 安定（特定着順に偏る）
            - 1に近い → 不安定（均等に分散）
        """
        total = sum(rank_counts.values())
        if total == 0:
            return None, None

        # 各着順の出現確率
        probabilities = [rank_counts.get(r, 0) / total for r in range(1, 7)]

        # エントロピー計算: H = -Σ(p * log(p))
        entropy = 0.0
        for p in probabilities:
            if p > 0:
                entropy -= p * math.log(p)

        # 正規化: H_norm = H / log(6)
        max_entropy = math.log(6)  # 最大エントロピー（完全均等分布）
        normalized = entropy / max_entropy if max_entropy > 0 else None

        return normalized, entropy

    # ========================================
    # 上位独占率（Dominance Rate）
    # ========================================

    def calculate_dominance_rate(self, first_count: int, second_count: int, total: int) -> Optional[float]:
        """
        上位独占率を計算

        Args:
            first_count: 1着回数
            second_count: 2着回数
            total: 総出走数

        Returns:
            上位独占率 = (1着 + 2着) / 総数
            - 高い → 軸向き・堅い構造
            - 低い → 分散構造・荒れやすい
        """
        if total == 0:
            return None
        return (first_count + second_count) / total

    # ========================================
    # 展開依存度指数（Self-Driven Index）
    # ========================================

    def calculate_self_driven_index(self, first_count: int, bottom_count: int, total: int) -> Optional[float]:
        """
        展開依存度を計算

        Args:
            first_count: 1着回数
            bottom_count: 4着以下回数
            total: 総出走数

        Returns:
            展開依存度 = (1着 - 4着以下) / 総数
            - 高い(+) → 自力型（再現性あり）
            - 低い/負 → 展開依存型（不安定）

        Note:
            平均的な選手はマイナスになる（1着率~17%, 4着以下率~50%）
            0以上 = 平均より自力型
        """
        if total == 0:
            return None
        return (first_count - bottom_count) / total

    # ========================================
    # 選手別メタ指数の計算
    # ========================================

    def get_player_meta_index(
        self,
        player_id: str,
        stadium_id: Optional[str] = None,
        period_start: str = "2000-01-01",
        period_end: str = "2099-12-31"
    ) -> Optional[PlayerMetaIndex]:
        """
        選手のメタ指数を計算

        Args:
            player_id: 選手ID
            stadium_id: 会場ID（None=全国）
            period_start: 集計開始日
            period_end: 集計終了日
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # 着順分布を取得
            sql = """
            SELECT
                CAST(r.rank AS INTEGER) as rank_int,
                COUNT(*) as cnt
            FROM results r
            JOIN races rc ON r.race_id = rc.id
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            WHERE e.racer_number = ?
              AND r.is_invalid = 0
              AND r.rank IN ('1', '2', '3', '4', '5', '6')
              AND rc.race_date BETWEEN ? AND ?
            """
            params = [player_id, period_start, period_end]

            if stadium_id:
                sql += " AND rc.venue_code = ?"
                params.append(stadium_id)

            sql += " GROUP BY rank_int"

            cursor.execute(sql, params)
            rows = cursor.fetchall()

            # 着順分布を辞書に変換
            rank_distribution = {r: 0 for r in range(1, 7)}
            for rank, count in rows:
                if 1 <= rank <= 6:
                    rank_distribution[rank] = count

            total_races = sum(rank_distribution.values())

            # 母数チェック
            min_races = self.MIN_RACES_LOCAL if stadium_id else self.MIN_RACES_NATIONAL
            if total_races < min_races:
                return None

            # メタ指数計算
            entropy_norm, entropy_raw = self.calculate_stability_entropy(rank_distribution)

            first_count = rank_distribution.get(1, 0)
            second_count = rank_distribution.get(2, 0)
            bottom_count = sum(rank_distribution.get(r, 0) for r in [4, 5, 6])

            dominance = self.calculate_dominance_rate(first_count, second_count, total_races)
            self_driven = self.calculate_self_driven_index(first_count, bottom_count, total_races)

            return PlayerMetaIndex(
                player_id=player_id,
                stadium_id=stadium_id,
                total_races=total_races,
                stability_entropy=entropy_norm,
                stability_entropy_raw=entropy_raw,
                dominance_rate=dominance,
                self_driven_index=self_driven,
                rank_distribution=rank_distribution,
                first_place_count=first_count,
                second_place_count=second_count,
                bottom_count=bottom_count,
                period_start=period_start,
                period_end=period_end
            )

        finally:
            conn.close()

    # ========================================
    # 予測乖離指数（Prediction Deviation）
    # ========================================

    def calculate_prediction_deviation(
        self,
        race_id: int,
        prediction_type: str = 'before'
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        予測と実着順の乖離を計算

        Args:
            race_id: レースID
            prediction_type: 予測タイプ ('advance' or 'before')

        Returns:
            (平均乖離, 正規化乖離)
            - 低い → 予測が当たっている
            - 高い → 予測が外れている
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # 予測と実績を結合
            cursor.execute("""
            SELECT
                p.rank_prediction,
                CAST(r.rank AS INTEGER) as actual_rank
            FROM race_predictions p
            JOIN results r ON p.race_id = r.race_id AND p.pit_number = r.pit_number
            WHERE p.race_id = ?
              AND p.prediction_type = ?
              AND r.is_invalid = 0
              AND r.rank IN ('1', '2', '3', '4', '5', '6')
            """, [race_id, prediction_type])

            rows = cursor.fetchall()

            if not rows:
                return None, None

            # 乖離計算
            deviations = [abs(pred - actual) for pred, actual in rows]
            avg_deviation = sum(deviations) / len(deviations)

            # 正規化（最大乖離は5）
            norm_deviation = avg_deviation / 5.0

            return avg_deviation, norm_deviation

        finally:
            conn.close()

    # ========================================
    # レース単位メタ指数
    # ========================================

    def get_race_meta_index(
        self,
        race_id: int,
        race_date: str,
        prediction_type: str = 'before'
    ) -> RaceMetaIndex:
        """
        レース全体のメタ指数を計算

        出走選手のメタ指数を集計し、レースの予測可能性を判定
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # 出走選手リストを取得
            cursor.execute("""
            SELECT e.racer_number
            FROM entries e
            WHERE e.race_id = ?
            """, [race_id])

            player_ids = [row[0] for row in cursor.fetchall() if row[0]]

            # 各選手のメタ指数を計算（レース日以前のデータで）
            entropy_values = []
            self_driven_values = []

            for pid in player_ids:
                meta = self.get_player_meta_index(
                    player_id=pid,
                    stadium_id=None,  # 全国
                    period_start="2000-01-01",
                    period_end=race_date
                )
                if meta:
                    if meta.stability_entropy is not None:
                        entropy_values.append(meta.stability_entropy)
                    if meta.self_driven_index is not None:
                        self_driven_values.append(meta.self_driven_index)

            # 予測乖離指数
            dev_avg, dev_norm = self.calculate_prediction_deviation(race_id, prediction_type)

            return RaceMetaIndex(
                race_id=race_id,
                avg_stability_entropy=sum(entropy_values) / len(entropy_values) if entropy_values else None,
                avg_self_driven_index=sum(self_driven_values) / len(self_driven_values) if self_driven_values else None,
                prediction_deviation=dev_avg,
                prediction_deviation_norm=dev_norm,
                player_count=len(player_ids),
                players_with_index=len(entropy_values)
            )

        finally:
            conn.close()

    # ========================================
    # バッチ計算・DB保存
    # ========================================

    def build_player_meta_stats(
        self,
        period_start: str = "2000-01-01",
        period_end: str = "2099-12-31",
        include_local: bool = False
    ) -> int:
        """
        全選手のメタ指数を計算してDBに保存

        Returns:
            保存件数
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # テーブル作成
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS player_meta_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id TEXT NOT NULL,
            stadium_id TEXT,
            total_races INTEGER NOT NULL,
            stability_entropy REAL,
            stability_entropy_raw REAL,
            self_driven_index REAL,
            first_place_count INTEGER,
            bottom_count INTEGER,
            period_start DATE NOT NULL,
            period_end DATE NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(player_id, stadium_id, period_start, period_end)
        )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_player_meta_player ON player_meta_stats(player_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_player_meta_entropy ON player_meta_stats(stability_entropy)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_player_meta_dominance ON player_meta_stats(dominance_rate)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_player_meta_selfdriven ON player_meta_stats(self_driven_index)")

        # 全選手リスト取得
        cursor.execute("SELECT DISTINCT racer_number FROM entries WHERE racer_number IS NOT NULL")
        players = [row[0] for row in cursor.fetchall()]

        print(f"選手数: {len(players)}")

        saved = 0
        for i, player_id in enumerate(players):
            if (i + 1) % 500 == 0:
                print(f"  処理中: {i + 1}/{len(players)}")

            # 全国指数
            meta = self.get_player_meta_index(player_id, None, period_start, period_end)
            if meta:
                cursor.execute("""
                INSERT OR REPLACE INTO player_meta_stats
                (player_id, stadium_id, total_races, stability_entropy, stability_entropy_raw,
                 dominance_rate, self_driven_index, first_place_count, second_place_count, bottom_count, period_start, period_end)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    meta.player_id, meta.stadium_id, meta.total_races,
                    meta.stability_entropy, meta.stability_entropy_raw,
                    meta.dominance_rate, meta.self_driven_index,
                    meta.first_place_count, meta.second_place_count, meta.bottom_count,
                    meta.period_start, meta.period_end
                ))
                saved += 1

        conn.commit()
        conn.close()

        print(f"保存完了: {saved}件")
        return saved


# 使用例
if __name__ == "__main__":
    calc = MetaIndexCalculator()

    # 単一選手のテスト
    print("=== 選手別メタ指数テスト ===")
    test_player = "4444"  # 峰竜太
    meta = calc.get_player_meta_index(test_player)
    if meta:
        print(f"選手: {meta.player_id}")
        print(f"出走数: {meta.total_races}")
        print(f"着順分布: {meta.rank_distribution}")
        print(f"安定度エントロピー: {meta.stability_entropy:.3f}" if meta.stability_entropy else "N/A")
        print(f"展開依存度: {meta.self_driven_index:.3f}" if meta.self_driven_index else "N/A")
