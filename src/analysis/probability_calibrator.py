"""
確率キャリブレーションモジュール

予測スコアを実際の勝率に合わせてキャリブレーションする。
日次・週次で更新し、過補正を防ぐ。
"""

import sqlite3
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import math
import json
from pathlib import Path
from datetime import datetime, timedelta


@dataclass
class CalibrationBin:
    """キャリブレーションビン"""
    score_min: float
    score_max: float
    predicted_count: int
    actual_wins: int
    predicted_prob: float  # 予測確率（スコア中央値）
    actual_prob: float     # 実際の勝率


class ProbabilityCalibrator:
    """確率キャリブレータ"""

    # ビン数
    NUM_BINS = 10

    # キャリブレーションデータの保存先
    CALIBRATION_FILE = "data/calibration_data.json"

    def __init__(self, db_path: str = "data/boatrace.db"):
        self.db_path = db_path
        self.calibration_table: Dict[str, List[CalibrationBin]] = {}
        self._load_calibration_data()

    def _load_calibration_data(self):
        """保存されたキャリブレーションデータを読み込み"""
        path = Path(self.CALIBRATION_FILE)
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key, bins in data.items():
                        self.calibration_table[key] = [
                            CalibrationBin(**b) for b in bins
                        ]
            except Exception:
                pass

    def _save_calibration_data(self):
        """キャリブレーションデータを保存"""
        path = Path(self.CALIBRATION_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {}
        for key, bins in self.calibration_table.items():
            data[key] = [
                {
                    'score_min': b.score_min,
                    'score_max': b.score_max,
                    'predicted_count': b.predicted_count,
                    'actual_wins': b.actual_wins,
                    'predicted_prob': b.predicted_prob,
                    'actual_prob': b.actual_prob
                }
                for b in bins
            ]

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def update_calibration(
        self,
        venue_code: Optional[str] = None,
        days: int = 30
    ) -> Dict:
        """
        キャリブレーションテーブルを更新

        Args:
            venue_code: 会場コード（Noneで全会場）
            days: 集計期間（日数）

        Returns:
            更新結果
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

            # 予測スコアと実際の結果を取得
            # 注: 予測スコアは predictions テーブルに保存されている前提
            query = '''
                SELECT
                    p.pit_number,
                    p.total_score,
                    res.rank,
                    r.venue_code
                FROM predictions p
                JOIN races r ON p.race_id = r.id
                JOIN results res ON p.race_id = res.race_id AND p.pit_number = res.pit_number
                WHERE r.race_date BETWEEN ? AND ?
            '''
            params = [start_date, end_date]

            if venue_code:
                query += ' AND r.venue_code = ?'
                params.append(venue_code)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            if not rows:
                return {'status': 'no_data', 'rows': 0}

            # ビンに分類
            bins = self._create_bins(rows)

            # キャリブレーションテーブルを更新
            key = venue_code or 'all'
            self.calibration_table[key] = bins

            # 保存
            self._save_calibration_data()

            return {
                'status': 'updated',
                'rows': len(rows),
                'bins': len(bins),
                'key': key
            }

        finally:
            conn.close()

    def _create_bins(self, rows: List[Tuple]) -> List[CalibrationBin]:
        """
        データをビンに分類
        """
        bins = []
        bin_size = 100.0 / self.NUM_BINS

        for i in range(self.NUM_BINS):
            score_min = i * bin_size
            score_max = (i + 1) * bin_size

            # このビンに該当するデータ
            bin_data = [r for r in rows if score_min <= r[1] < score_max]

            if bin_data:
                predicted_count = len(bin_data)
                actual_wins = sum(1 for r in bin_data if r[2] == '1' or r[2] == 1)
                predicted_prob = (score_min + score_max) / 200.0  # スコアを確率に変換
                actual_prob = actual_wins / predicted_count if predicted_count > 0 else 0
            else:
                predicted_count = 0
                actual_wins = 0
                predicted_prob = (score_min + score_max) / 200.0
                actual_prob = predicted_prob  # データなしは予測と同じ

            bins.append(CalibrationBin(
                score_min=score_min,
                score_max=score_max,
                predicted_count=predicted_count,
                actual_wins=actual_wins,
                predicted_prob=predicted_prob,
                actual_prob=actual_prob
            ))

        return bins

    def calibrate_score(
        self,
        score: float,
        venue_code: Optional[str] = None
    ) -> float:
        """
        スコアをキャリブレーション

        Args:
            score: 元のスコア (0-100)
            venue_code: 会場コード

        Returns:
            キャリブレーション後のスコア
        """
        # キャリブレーションテーブルを取得
        key = venue_code or 'all'
        if key not in self.calibration_table:
            key = 'all'

        if key not in self.calibration_table:
            return score  # テーブルがなければ元のスコア

        bins = self.calibration_table[key]

        # 該当するビンを探す
        for b in bins:
            if b.score_min <= score < b.score_max:
                if b.predicted_prob > 0:
                    # キャリブレーション係数
                    calibration_factor = b.actual_prob / b.predicted_prob
                    # 元のスコアに係数を適用（緩やかに）
                    calibrated = score * (0.7 + 0.3 * calibration_factor)
                    return max(0, min(100, calibrated))
                return score

        return score

    def get_calibration_report(self, venue_code: Optional[str] = None) -> Dict:
        """
        キャリブレーションレポートを生成
        """
        key = venue_code or 'all'
        if key not in self.calibration_table:
            return {'status': 'no_data'}

        bins = self.calibration_table[key]

        # Brierスコアを計算
        brier_score = 0.0
        total_samples = 0

        report_bins = []
        for b in bins:
            if b.predicted_count > 0:
                # Brierスコア = (予測確率 - 実際の結果)^2 の平均
                brier_score += b.predicted_count * (b.predicted_prob - b.actual_prob) ** 2
                total_samples += b.predicted_count

            report_bins.append({
                'range': f"{b.score_min:.0f}-{b.score_max:.0f}",
                'count': b.predicted_count,
                'wins': b.actual_wins,
                'predicted_prob': round(b.predicted_prob * 100, 1),
                'actual_prob': round(b.actual_prob * 100, 1),
                'diff': round((b.actual_prob - b.predicted_prob) * 100, 1)
            })

        if total_samples > 0:
            brier_score /= total_samples

        return {
            'status': 'ok',
            'key': key,
            'total_samples': total_samples,
            'brier_score': round(brier_score, 4),
            'bins': report_bins
        }
