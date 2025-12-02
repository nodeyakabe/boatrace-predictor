"""
Performance Monitoring Dashboard

日次精度推移を記録・可視化するモニタリングシステム
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
from pathlib import Path


class PerformanceMonitor:
    """予測精度モニタリング"""

    def __init__(self, db_path: str = "data/boatrace.db", monitor_db: str = "data/monitor.db"):
        self.db_path = db_path
        self.monitor_db = monitor_db
        self._init_monitor_db()

    def _init_monitor_db(self):
        """モニタリング用DBを初期化"""
        conn = sqlite3.connect(self.monitor_db)
        cursor = conn.cursor()

        # 日次パフォーマンステーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_performance (
                date DATE PRIMARY KEY,
                total_races INTEGER DEFAULT 0,
                hit_count_1st INTEGER DEFAULT 0,
                hit_count_top3 INTEGER DEFAULT 0,
                hit_rate_1st REAL DEFAULT 0.0,
                hit_rate_top3 REAL DEFAULT 0.0,
                avg_score_accuracy REAL DEFAULT 0.0,
                feature_flags TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # レース単位の詳細ログ
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS race_predictions (
                race_id INTEGER,
                race_date DATE,
                venue_code TEXT,
                race_number INTEGER,
                predicted_1st INTEGER,
                predicted_top3 TEXT,
                actual_1st INTEGER,
                actual_top3 TEXT,
                hit_1st INTEGER,
                hit_top3 INTEGER,
                score_accuracy REAL,
                integration_mode TEXT,
                feature_flags TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (race_id)
            )
        """)

        # アラートログ
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE,
                alert_type TEXT,
                message TEXT,
                metric_value REAL,
                threshold REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()

    def log_prediction(
        self,
        race_id: int,
        race_date: str,
        venue_code: str,
        race_number: int,
        predictions: List[Dict],
        actual_results: List[Dict],
        integration_mode: str = "UNKNOWN",
        feature_flags: Optional[Dict] = None
    ):
        """
        予測結果をログに記録

        Parameters:
        -----------
        race_id : int
            レースID
        race_date : str
            レース日付
        venue_code : str
            会場コード
        race_number : int
            レース番号
        predictions : List[Dict]
            予測結果
        actual_results : List[Dict]
            実際の結果
        integration_mode : str
            統合モード
        feature_flags : Dict
            機能フラグの状態
        """
        if not predictions or not actual_results:
            return

        # 予測と実際の結果
        predicted_1st = predictions[0]['pit_number']
        predicted_top3 = [p['pit_number'] for p in predictions[:3]]
        actual_1st = actual_results[0]['pit_number']
        actual_top3 = [r['pit_number'] for r in actual_results[:3]]

        # 的中判定
        hit_1st = 1 if predicted_1st == actual_1st else 0
        hit_top3 = 1 if set(predicted_top3) == set(actual_top3) else 0

        # スコア精度
        score_accuracy = self._calculate_score_accuracy(predictions, actual_results)

        # DBに記録
        conn = sqlite3.connect(self.monitor_db)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO race_predictions (
                race_id, race_date, venue_code, race_number,
                predicted_1st, predicted_top3,
                actual_1st, actual_top3,
                hit_1st, hit_top3, score_accuracy,
                integration_mode, feature_flags
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            race_id, race_date, venue_code, race_number,
            predicted_1st, json.dumps(predicted_top3),
            actual_1st, json.dumps(actual_top3),
            hit_1st, hit_top3, score_accuracy,
            integration_mode, json.dumps(feature_flags) if feature_flags else None
        ))

        conn.commit()
        conn.close()

    def calculate_daily_stats(self, date: str) -> Dict:
        """
        指定日の統計を計算

        Parameters:
        -----------
        date : str
            対象日 (YYYY-MM-DD)

        Returns:
        --------
        Dict: 日次統計
        """
        conn = sqlite3.connect(self.monitor_db)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                COUNT(*) as total_races,
                SUM(hit_1st) as hit_count_1st,
                SUM(hit_top3) as hit_count_top3,
                AVG(score_accuracy) as avg_score_accuracy
            FROM race_predictions
            WHERE race_date = ?
        """, (date,))

        row = cursor.fetchone()

        if row and row[0] > 0:
            total_races = row[0]
            hit_count_1st = row[1] or 0
            hit_count_top3 = row[2] or 0
            avg_score_accuracy = row[3] or 0.0

            stats = {
                'date': date,
                'total_races': total_races,
                'hit_count_1st': hit_count_1st,
                'hit_count_top3': hit_count_top3,
                'hit_rate_1st': hit_count_1st / total_races if total_races > 0 else 0.0,
                'hit_rate_top3': hit_count_top3 / total_races if total_races > 0 else 0.0,
                'avg_score_accuracy': avg_score_accuracy,
            }

            # 日次統計を保存
            cursor.execute("""
                INSERT OR REPLACE INTO daily_performance (
                    date, total_races, hit_count_1st, hit_count_top3,
                    hit_rate_1st, hit_rate_top3, avg_score_accuracy
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                date, stats['total_races'], stats['hit_count_1st'], stats['hit_count_top3'],
                stats['hit_rate_1st'], stats['hit_rate_top3'], stats['avg_score_accuracy']
            ))

            conn.commit()
        else:
            stats = None

        conn.close()
        return stats

    def get_performance_trend(self, days: int = 30) -> List[Dict]:
        """
        過去N日間のパフォーマンス推移を取得

        Parameters:
        -----------
        days : int
            取得する日数

        Returns:
        --------
        List[Dict]: 日次パフォーマンス一覧
        """
        conn = sqlite3.connect(self.monitor_db)
        cursor = conn.cursor()

        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        cursor.execute("""
            SELECT
                date, total_races, hit_count_1st, hit_count_top3,
                hit_rate_1st, hit_rate_top3, avg_score_accuracy
            FROM daily_performance
            WHERE date >= ? AND date <= ?
            ORDER BY date
        """, (start_date, end_date))

        trend = []
        for row in cursor.fetchall():
            trend.append({
                'date': row[0],
                'total_races': row[1],
                'hit_count_1st': row[2],
                'hit_count_top3': row[3],
                'hit_rate_1st': row[4],
                'hit_rate_top3': row[5],
                'avg_score_accuracy': row[6],
            })

        conn.close()
        return trend

    def check_alerts(self, date: str, stats: Dict):
        """
        アラート条件をチェック

        Parameters:
        -----------
        date : str
            対象日
        stats : Dict
            日次統計
        """
        conn = sqlite3.connect(self.monitor_db)
        cursor = conn.cursor()

        # アラート条件
        alerts = []

        # 1. 的中率が低下
        if stats['hit_rate_1st'] < 0.15:  # 15%未満
            alerts.append({
                'alert_type': 'LOW_HIT_RATE_1ST',
                'message': f"1着的中率が低い: {stats['hit_rate_1st']:.2%}",
                'metric_value': stats['hit_rate_1st'],
                'threshold': 0.15,
            })

        if stats['hit_rate_top3'] < 0.05:  # 5%未満
            alerts.append({
                'alert_type': 'LOW_HIT_RATE_TOP3',
                'message': f"3連単的中率が低い: {stats['hit_rate_top3']:.2%}",
                'metric_value': stats['hit_rate_top3'],
                'threshold': 0.05,
            })

        # 2. スコア精度が低下
        if stats['avg_score_accuracy'] < 0.6:
            alerts.append({
                'alert_type': 'LOW_SCORE_ACCURACY',
                'message': f"スコア精度が低い: {stats['avg_score_accuracy']:.4f}",
                'metric_value': stats['avg_score_accuracy'],
                'threshold': 0.6,
            })

        # 3. レース数が少ない
        if stats['total_races'] < 10:
            alerts.append({
                'alert_type': 'LOW_RACE_COUNT',
                'message': f"評価レース数が少ない: {stats['total_races']}",
                'metric_value': stats['total_races'],
                'threshold': 10,
            })

        # アラートを記録
        for alert in alerts:
            cursor.execute("""
                INSERT INTO alerts (date, alert_type, message, metric_value, threshold)
                VALUES (?, ?, ?, ?, ?)
            """, (
                date, alert['alert_type'], alert['message'],
                alert['metric_value'], alert['threshold']
            ))

        conn.commit()
        conn.close()

        return alerts

    def generate_report(self, days: int = 7, output_path: str = "temp/monitor/report.txt"):
        """
        パフォーマンスレポートを生成

        Parameters:
        -----------
        days : int
            レポート対象日数
        output_path : str
            出力ファイルパス
        """
        trend = self.get_performance_trend(days)

        if not trend:
            print("データがありません")
            return

        # 出力ディレクトリ作成
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("=" * 70 + "\n")
            f.write(f"パフォーマンスレポート (過去{days}日間)\n")
            f.write("=" * 70 + "\n\n")

            # 全体統計
            total_races = sum(d['total_races'] for d in trend)
            total_hits_1st = sum(d['hit_count_1st'] for d in trend)
            total_hits_top3 = sum(d['hit_count_top3'] for d in trend)
            avg_score_accuracy = sum(d['avg_score_accuracy'] for d in trend) / len(trend)

            f.write("【全体統計】\n")
            f.write(f"  期間: {trend[0]['date']} ~ {trend[-1]['date']}\n")
            f.write(f"  総レース数: {total_races}\n")
            f.write(f"  1着的中率: {total_hits_1st / total_races:.2%}\n")
            f.write(f"  3連単的中率: {total_hits_top3 / total_races:.2%}\n")
            f.write(f"  平均スコア精度: {avg_score_accuracy:.4f}\n\n")

            # 日次詳細
            f.write("【日次詳細】\n")
            for day in trend:
                f.write(f"\n{day['date']}:\n")
                f.write(f"  レース数: {day['total_races']}\n")
                f.write(f"  1着的中率: {day['hit_rate_1st']:.2%} ({day['hit_count_1st']}/{day['total_races']})\n")
                f.write(f"  3連単的中率: {day['hit_rate_top3']:.2%} ({day['hit_count_top3']}/{day['total_races']})\n")
                f.write(f"  スコア精度: {day['avg_score_accuracy']:.4f}\n")

        print(f"レポートを生成しました: {output_path}")

    def _calculate_score_accuracy(
        self,
        predictions: List[Dict],
        actual_results: List[Dict]
    ) -> float:
        """スコアと実際の順位の相関を計算"""
        actual_ranks = {r['pit_number']: r['rank'] for r in actual_results}

        total_diff = 0
        count = 0

        for pred_rank, pred in enumerate(predictions, 1):
            pit_number = pred['pit_number']
            if pit_number in actual_ranks:
                actual_rank = actual_ranks[pit_number]
                total_diff += abs(pred_rank - actual_rank)
                count += 1

        if count == 0:
            return 0.0

        max_diff = 5 * count
        accuracy = 1.0 - (total_diff / max_diff)

        return max(0.0, accuracy)
