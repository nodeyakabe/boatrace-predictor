"""
モーター指数加重移動平均（EWMA）評価
直近のレース結果に大きな重みを付けてモーター調子を評価
"""

import sqlite3
import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from config.settings import DATABASE_PATH


class MotorEWMA:
    """モーター指数加重移動平均評価クラス"""

    def __init__(self, db_path: str = None, config_path: Optional[str] = None):
        if db_path is None:
            db_path = DATABASE_PATH
        self.db_path = db_path

        # 設定読み込み
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / 'config' / 'prediction_improvements.json'

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        self.enabled = config['motor_ewma']['enabled']
        self.alpha = config['motor_ewma']['alpha']  # デフォルト 0.3

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def calculate_motor_ewma(
        self,
        venue_code: str,
        motor_number: int,
        max_races: int = 30
    ) -> Dict[str, float]:
        """
        モーターのEWMA（指数加重移動平均）を計算

        Args:
            venue_code: 会場コード
            motor_number: モーター番号
            max_races: 集計する最大レース数

        Returns:
            {
                'ewma_score': EWMA スコア（0-100）,
                'recent_trend': 直近傾向（'上昇' / '安定' / '下降'）,
                'total_races': 集計レース数,
                'latest_performance': 最新レースの成績
            }
        """
        if not self.enabled:
            return {
                'ewma_score': 50.0,
                'recent_trend': '不明',
                'total_races': 0,
                'latest_performance': 0.0
            }

        conn = self._connect()
        cursor = conn.cursor()

        # モーターの直近レース結果を取得（新しい順）
        cursor.execute("""
            SELECT
                ra.race_date,
                res.rank,
                e.pit_number
            FROM entries e
            JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
            JOIN races ra ON e.race_id = ra.id
            WHERE ra.venue_code = ?
              AND e.motor_number = ?
            ORDER BY ra.race_date DESC, ra.race_number DESC
            LIMIT ?
        """, (venue_code, motor_number, max_races))

        results = cursor.fetchall()
        conn.close()

        if len(results) == 0:
            return {
                'ewma_score': 50.0,
                'recent_trend': '不明',
                'total_races': 0,
                'latest_performance': 0.0
            }

        # 各レースの成績をスコア化（1着=100, 2着=80, 3着=60, 4着=40, 5着=20, 6着=0）
        race_scores = []
        for race_date, rank, pit_number in results:
            if rank == 1:
                score = 100.0
            elif rank == 2:
                score = 80.0
            elif rank == 3:
                score = 60.0
            elif rank == 4:
                score = 40.0
            elif rank == 5:
                score = 20.0
            else:
                score = 0.0

            race_scores.append(score)

        # EWMAを計算（新しいレースから古いレースへ）
        ewma = race_scores[0]  # 最新レースから開始

        for score in race_scores[1:]:
            ewma = self.alpha * score + (1 - self.alpha) * ewma

        # 直近傾向を判定（最新5レースと過去5レースの平均を比較）
        if len(race_scores) >= 10:
            recent_avg = sum(race_scores[:5]) / 5
            past_avg = sum(race_scores[5:10]) / 5

            if recent_avg > past_avg + 10:
                trend = '上昇'
            elif recent_avg < past_avg - 10:
                trend = '下降'
            else:
                trend = '安定'
        else:
            trend = '不明'

        return {
            'ewma_score': ewma,
            'recent_trend': trend,
            'total_races': len(race_scores),
            'latest_performance': race_scores[0]
        }

    def calculate_motor_score_with_ewma(
        self,
        venue_code: str,
        motor_number: int,
        base_score: float
    ) -> Dict[str, float]:
        """
        EWMAを考慮したモータースコアを計算

        Args:
            venue_code: 会場コード
            motor_number: モーター番号
            base_score: ベーススコア（従来の方法で計算したスコア）

        Returns:
            {
                'adjusted_score': EWMA調整後のスコア,
                'ewma_adjustment': 調整値,
                'ewma_info': EWMA情報
            }
        """
        ewma_info = self.calculate_motor_ewma(venue_code, motor_number)

        if not self.enabled or ewma_info['total_races'] < 5:
            # データ不足または無効の場合はベーススコアをそのまま使用
            return {
                'adjusted_score': base_score,
                'ewma_adjustment': 0.0,
                'ewma_info': ewma_info
            }

        # EWMAスコアを-10～+10点の調整に変換
        # EWMA 50が基準（ニュートラル）
        ewma_score = ewma_info['ewma_score']
        ewma_adjustment = (ewma_score - 50) * 0.2  # 50→0, 60→+2, 40→-2

        # 直近傾向による追加調整
        if ewma_info['recent_trend'] == '上昇':
            ewma_adjustment += 2.0
        elif ewma_info['recent_trend'] == '下降':
            ewma_adjustment -= 2.0

        # 調整値を-10～+10に制限
        ewma_adjustment = max(-10.0, min(10.0, ewma_adjustment))

        adjusted_score = base_score + ewma_adjustment

        return {
            'adjusted_score': adjusted_score,
            'ewma_adjustment': ewma_adjustment,
            'ewma_info': ewma_info
        }

    def get_motor_condition_summary(
        self,
        venue_code: str,
        motor_number: int
    ) -> str:
        """
        モーター状態のサマリー文字列を生成

        Args:
            venue_code: 会場コード
            motor_number: モーター番号

        Returns:
            サマリー文字列
        """
        ewma_info = self.calculate_motor_ewma(venue_code, motor_number)

        if ewma_info['total_races'] == 0:
            return "データ不足"

        ewma_score = ewma_info['ewma_score']
        trend = ewma_info['recent_trend']

        # スコアによる評価
        if ewma_score >= 70:
            condition = "好調"
        elif ewma_score >= 55:
            condition = "やや好調"
        elif ewma_score >= 45:
            condition = "普通"
        elif ewma_score >= 30:
            condition = "やや不調"
        else:
            condition = "不調"

        return f"{condition}（EWMA: {ewma_score:.1f}, 傾向: {trend}）"
