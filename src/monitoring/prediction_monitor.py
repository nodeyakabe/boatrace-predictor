"""
予測モニタリングモジュール
Phase 3.4: リアルタイム予測システムの監視
"""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import deque
import json
import os


class PredictionMonitor:
    """
    予測パフォーマンスのリアルタイムモニタリング

    - 予測精度の追跡
    - 異常検知
    - パフォーマンス劣化の検出
    """

    def __init__(
        self,
        window_size: int = 100,
        alert_threshold_accuracy: float = 0.3,
        alert_threshold_roi: float = -0.15,
        log_dir: str = 'logs/monitoring'
    ):
        """
        Args:
            window_size: 監視ウィンドウサイズ（レース数）
            alert_threshold_accuracy: 精度警告閾値
            alert_threshold_roi: ROI警告閾値
            log_dir: ログ保存ディレクトリ
        """
        self.window_size = window_size
        self.alert_threshold_accuracy = alert_threshold_accuracy
        self.alert_threshold_roi = alert_threshold_roi
        self.log_dir = log_dir

        # 履歴データ（デック構造で固定サイズ）
        self.prediction_history = deque(maxlen=window_size)
        self.accuracy_history = deque(maxlen=window_size)
        self.roi_history = deque(maxlen=window_size)
        self.latency_history = deque(maxlen=window_size)

        # アラート履歴
        self.alerts = []

        # 統計情報
        self.total_predictions = 0
        self.total_hits = 0
        self.total_profit = 0.0

        # ベースラインメトリクス
        self.baseline_accuracy = None
        self.baseline_roi = None

        os.makedirs(log_dir, exist_ok=True)

    def record_prediction(
        self,
        race_id: str,
        predictions: Dict[str, float],
        actual_result: str,
        bet_amount: float,
        odds: Dict[str, float],
        latency_ms: float,
        metadata: Optional[Dict] = None
    ):
        """
        予測結果を記録

        Args:
            race_id: レースID
            predictions: 予測確率 {'1-2-3': 0.15, ...}
            actual_result: 実際の結果
            bet_amount: 賭け金
            odds: オッズデータ
            latency_ms: 予測処理時間（ミリ秒）
            metadata: 追加メタデータ
        """
        timestamp = datetime.now()

        # 的中判定
        top_prediction = max(predictions.items(), key=lambda x: x[1])[0]
        is_hit = top_prediction == actual_result

        # ROI計算
        if actual_result in predictions and actual_result in odds:
            if bet_amount > 0:
                profit = odds[actual_result] * bet_amount - bet_amount if is_hit else -bet_amount
                roi = profit / bet_amount
            else:
                profit = 0.0
                roi = 0.0
        else:
            profit = 0.0
            roi = 0.0

        # 記録
        record = {
            'timestamp': timestamp.isoformat(),
            'race_id': race_id,
            'top_prediction': top_prediction,
            'actual_result': actual_result,
            'is_hit': is_hit,
            'bet_amount': bet_amount,
            'profit': profit,
            'roi': roi,
            'latency_ms': latency_ms,
            'confidence': predictions.get(top_prediction, 0),
            'metadata': metadata or {}
        }

        self.prediction_history.append(record)
        self.accuracy_history.append(1 if is_hit else 0)
        self.roi_history.append(roi)
        self.latency_history.append(latency_ms)

        # 累積統計更新
        self.total_predictions += 1
        if is_hit:
            self.total_hits += 1
        self.total_profit += profit

        # アラートチェック
        self._check_alerts()

        # 定期的なログ保存
        if self.total_predictions % 50 == 0:
            self._save_checkpoint()

    def _check_alerts(self):
        """アラート条件をチェック"""
        if len(self.accuracy_history) < 10:
            return

        # 直近の精度
        recent_accuracy = np.mean(list(self.accuracy_history)[-20:])

        # 直近のROI
        recent_roi = np.mean(list(self.roi_history)[-20:])

        # 精度低下アラート
        if recent_accuracy < self.alert_threshold_accuracy:
            self._add_alert(
                'ACCURACY_DROP',
                f'直近20レースの精度が{recent_accuracy:.1%}に低下',
                'HIGH'
            )

        # ROI低下アラート
        if recent_roi < self.alert_threshold_roi:
            self._add_alert(
                'ROI_DROP',
                f'直近20レースのROIが{recent_roi:.1%}に低下',
                'HIGH'
            )

        # レイテンシー警告
        recent_latency = np.mean(list(self.latency_history)[-10:])
        if recent_latency > 1000:  # 1秒以上
            self._add_alert(
                'HIGH_LATENCY',
                f'予測レイテンシーが{recent_latency:.0f}msに上昇',
                'MEDIUM'
            )

        # 連続外れ検知
        recent_hits = list(self.accuracy_history)[-10:]
        if len(recent_hits) >= 10 and sum(recent_hits) == 0:
            self._add_alert(
                'CONSECUTIVE_MISS',
                '10レース連続で外れています',
                'CRITICAL'
            )

    def _add_alert(self, alert_type: str, message: str, severity: str):
        """アラートを追加"""
        alert = {
            'timestamp': datetime.now().isoformat(),
            'type': alert_type,
            'message': message,
            'severity': severity,
            'acknowledged': False
        }
        self.alerts.append(alert)

        # ログにも記録
        log_path = os.path.join(self.log_dir, 'alerts.log')
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"{alert['timestamp']} [{severity}] {alert_type}: {message}\n")

    def get_current_metrics(self) -> Dict:
        """現在のメトリクスを取得"""
        if len(self.accuracy_history) == 0:
            return {
                'total_predictions': 0,
                'accuracy': 0.0,
                'roi': 0.0,
                'avg_latency_ms': 0.0,
                'status': 'NO_DATA'
            }

        # ウィンドウ内の統計
        window_accuracy = np.mean(list(self.accuracy_history))
        window_roi = np.mean(list(self.roi_history))
        avg_latency = np.mean(list(self.latency_history))

        # 全体の統計
        overall_accuracy = self.total_hits / self.total_predictions if self.total_predictions > 0 else 0

        # トレンド分析
        if len(self.accuracy_history) >= 20:
            recent_20 = np.mean(list(self.accuracy_history)[-20:])
            older_20 = np.mean(list(self.accuracy_history)[-40:-20]) if len(self.accuracy_history) >= 40 else window_accuracy
            trend = recent_20 - older_20
        else:
            trend = 0.0

        # ステータス判定
        status = self._determine_status(window_accuracy, window_roi, avg_latency)

        return {
            'total_predictions': self.total_predictions,
            'window_size': len(self.accuracy_history),
            'window_accuracy': window_accuracy,
            'overall_accuracy': overall_accuracy,
            'window_roi': window_roi,
            'total_profit': self.total_profit,
            'avg_latency_ms': avg_latency,
            'accuracy_trend': trend,
            'status': status,
            'active_alerts': len([a for a in self.alerts if not a['acknowledged']])
        }

    def _determine_status(
        self,
        accuracy: float,
        roi: float,
        latency: float
    ) -> str:
        """システムステータスを判定"""
        if accuracy < 0.2 or roi < -0.3:
            return 'CRITICAL'
        elif accuracy < 0.3 or roi < -0.15 or latency > 1000:
            return 'WARNING'
        elif accuracy > 0.4 and roi > 0.1:
            return 'EXCELLENT'
        else:
            return 'NORMAL'

    def get_performance_report(self) -> Dict:
        """詳細なパフォーマンスレポートを生成"""
        if len(self.prediction_history) == 0:
            return {'error': 'データがありません'}

        # 時系列データの集約
        df = pd.DataFrame(list(self.prediction_history))

        # 時間帯別分析
        if 'timestamp' in df.columns:
            df['hour'] = pd.to_datetime(df['timestamp']).dt.hour
            hourly_performance = df.groupby('hour').agg({
                'is_hit': 'mean',
                'roi': 'mean',
                'latency_ms': 'mean'
            }).to_dict('index')
        else:
            hourly_performance = {}

        # 信頼度別分析
        df['confidence_bin'] = pd.cut(
            df['confidence'],
            bins=[0, 0.1, 0.15, 0.2, 1.0],
            labels=['low', 'medium', 'high', 'very_high']
        )
        confidence_performance = df.groupby('confidence_bin').agg({
            'is_hit': 'mean',
            'roi': 'mean'
        }).to_dict('index')

        # 最大ドローダウン
        cumulative_profit = np.cumsum(df['profit'].values)
        running_max = np.maximum.accumulate(cumulative_profit)
        drawdown = running_max - cumulative_profit
        max_drawdown = np.max(drawdown)

        # 連続的中/連続外れ
        hits = df['is_hit'].values
        max_consecutive_hits = self._max_consecutive(hits, True)
        max_consecutive_misses = self._max_consecutive(hits, False)

        return {
            'summary': self.get_current_metrics(),
            'hourly_performance': hourly_performance,
            'confidence_performance': confidence_performance,
            'max_drawdown': max_drawdown,
            'max_consecutive_hits': max_consecutive_hits,
            'max_consecutive_misses': max_consecutive_misses,
            'recent_alerts': self.alerts[-10:],
            'generated_at': datetime.now().isoformat()
        }

    def _max_consecutive(self, arr: np.ndarray, value: bool) -> int:
        """連続する値の最大長を計算"""
        max_count = 0
        current_count = 0

        for v in arr:
            if v == value:
                current_count += 1
                max_count = max(max_count, current_count)
            else:
                current_count = 0

        return max_count

    def detect_model_drift(self) -> Dict:
        """モデルドリフトを検出"""
        if len(self.accuracy_history) < 50:
            return {'drift_detected': False, 'message': 'データ不足'}

        # 前半と後半の比較
        mid_point = len(self.accuracy_history) // 2
        first_half = np.mean(list(self.accuracy_history)[:mid_point])
        second_half = np.mean(list(self.accuracy_history)[mid_point:])

        drift_magnitude = second_half - first_half

        # 統計的有意性（簡易版）
        significant = abs(drift_magnitude) > 0.05

        if significant and drift_magnitude < -0.05:
            return {
                'drift_detected': True,
                'drift_type': 'DEGRADATION',
                'magnitude': drift_magnitude,
                'recommendation': 'モデルの再学習を検討してください'
            }
        elif significant and drift_magnitude > 0.05:
            return {
                'drift_detected': True,
                'drift_type': 'IMPROVEMENT',
                'magnitude': drift_magnitude,
                'recommendation': '改善が見られます'
            }
        else:
            return {
                'drift_detected': False,
                'drift_type': 'STABLE',
                'magnitude': drift_magnitude,
                'recommendation': '安定しています'
            }

    def _save_checkpoint(self):
        """チェックポイントを保存"""
        checkpoint = {
            'timestamp': datetime.now().isoformat(),
            'metrics': self.get_current_metrics(),
            'recent_predictions': list(self.prediction_history)[-10:],
            'alerts': self.alerts[-20:]
        }

        checkpoint_path = os.path.join(
            self.log_dir,
            f'checkpoint_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        )

        with open(checkpoint_path, 'w', encoding='utf-8') as f:
            json.dump(checkpoint, f, indent=2, ensure_ascii=False)

    def acknowledge_alert(self, alert_index: int):
        """アラートを確認済みにする"""
        if 0 <= alert_index < len(self.alerts):
            self.alerts[alert_index]['acknowledged'] = True

    def reset_monitoring(self):
        """モニタリングをリセット"""
        self.prediction_history.clear()
        self.accuracy_history.clear()
        self.roi_history.clear()
        self.latency_history.clear()
        self.alerts.clear()
        self.total_predictions = 0
        self.total_hits = 0
        self.total_profit = 0.0


class SystemHealthMonitor:
    """
    システム全体の健全性監視

    - リソース使用状況
    - エラーレート
    - スループット
    """

    def __init__(self):
        self.error_count = 0
        self.request_count = 0
        self.last_error = None
        self.start_time = datetime.now()
        self.error_history = deque(maxlen=100)

    def record_request(self, success: bool, error_message: str = None):
        """リクエストを記録"""
        self.request_count += 1

        if not success:
            self.error_count += 1
            self.last_error = {
                'timestamp': datetime.now().isoformat(),
                'message': error_message or 'Unknown error'
            }
            self.error_history.append(self.last_error)

    def get_health_status(self) -> Dict:
        """健全性ステータスを取得"""
        uptime = (datetime.now() - self.start_time).total_seconds()
        error_rate = self.error_count / self.request_count if self.request_count > 0 else 0

        # ステータス判定
        if error_rate > 0.1:
            status = 'UNHEALTHY'
        elif error_rate > 0.05:
            status = 'DEGRADED'
        else:
            status = 'HEALTHY'

        return {
            'status': status,
            'uptime_seconds': uptime,
            'total_requests': self.request_count,
            'error_count': self.error_count,
            'error_rate': error_rate,
            'last_error': self.last_error,
            'recent_errors': list(self.error_history)[-5:]
        }

    def should_restart(self) -> bool:
        """再起動が必要かどうか"""
        health = self.get_health_status()

        if health['status'] == 'UNHEALTHY':
            return True

        # 連続エラーチェック
        if len(self.error_history) >= 5:
            recent_errors = list(self.error_history)[-5:]
            times = [datetime.fromisoformat(e['timestamp']) for e in recent_errors]
            if (times[-1] - times[0]).total_seconds() < 60:  # 1分以内に5エラー
                return True

        return False


class PredictionAuditLog:
    """
    予測の監査ログ

    - すべての予測を記録
    - 再現性の確保
    - コンプライアンス対応
    """

    def __init__(self, log_dir: str = 'logs/audit'):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)

    def log_prediction(
        self,
        race_id: str,
        input_features: Dict,
        model_version: str,
        predictions: Dict[str, float],
        selected_bets: List[Dict],
        metadata: Optional[Dict] = None
    ):
        """予測を監査ログに記録"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'race_id': race_id,
            'model_version': model_version,
            'input_features_hash': hash(str(sorted(input_features.items()))),
            'input_features_summary': self._summarize_features(input_features),
            'top_predictions': dict(sorted(predictions.items(), key=lambda x: x[1], reverse=True)[:10]),
            'selected_bets': selected_bets,
            'total_bet_amount': sum(b.get('amount', 0) for b in selected_bets),
            'metadata': metadata or {}
        }

        # 日付ごとのログファイル
        log_file = os.path.join(
            self.log_dir,
            f'audit_{datetime.now().strftime("%Y%m%d")}.jsonl'
        )

        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

    def _summarize_features(self, features: Dict) -> Dict:
        """特徴量の要約を生成"""
        summary = {}

        for key, value in features.items():
            if isinstance(value, (int, float)):
                summary[key] = value
            elif isinstance(value, list) and len(value) > 0:
                summary[key] = f'list[{len(value)}]'
            elif isinstance(value, dict):
                summary[key] = f'dict[{len(value)}]'
            else:
                summary[key] = str(type(value).__name__)

        return summary

    def get_audit_trail(self, race_id: str) -> List[Dict]:
        """特定レースの監査トレイルを取得"""
        trail = []

        for log_file in os.listdir(self.log_dir):
            if not log_file.endswith('.jsonl'):
                continue

            file_path = os.path.join(self.log_dir, log_file)

            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    entry = json.loads(line.strip())
                    if entry.get('race_id') == race_id:
                        trail.append(entry)

        return sorted(trail, key=lambda x: x['timestamp'])


if __name__ == "__main__":
    print("=" * 60)
    print("予測モニタリングモジュール テスト")
    print("=" * 60)

    # モニターの初期化
    monitor = PredictionMonitor(window_size=50)

    # サンプル予測データの記録
    print("\n【予測データの記録】")
    for i in range(30):
        race_id = f"R{i+1:04d}"

        # ランダムな予測結果
        predictions = {
            '1-2-3': np.random.uniform(0.1, 0.2),
            '1-3-2': np.random.uniform(0.08, 0.15),
            '2-1-3': np.random.uniform(0.05, 0.12),
        }

        # 実際の結果
        actual = np.random.choice(['1-2-3', '1-3-2', '2-1-3', '2-3-1'])

        odds = {
            '1-2-3': np.random.uniform(5, 15),
            '1-3-2': np.random.uniform(8, 20),
            '2-1-3': np.random.uniform(10, 25),
            '2-3-1': np.random.uniform(15, 30),
        }

        monitor.record_prediction(
            race_id=race_id,
            predictions=predictions,
            actual_result=actual,
            bet_amount=1000,
            odds=odds,
            latency_ms=np.random.uniform(50, 200)
        )

    print(f"  {monitor.total_predictions}件の予測を記録")

    print("\n【現在のメトリクス】")
    metrics = monitor.get_current_metrics()
    for key, value in metrics.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.4f}")
        else:
            print(f"  {key}: {value}")

    print("\n【モデルドリフト検出】")
    drift = monitor.detect_model_drift()
    print(f"  ドリフト検出: {drift['drift_detected']}")
    print(f"  タイプ: {drift['drift_type']}")
    print(f"  推奨: {drift['recommendation']}")

    print("\n【アラート履歴】")
    if monitor.alerts:
        for alert in monitor.alerts[-5:]:
            print(f"  [{alert['severity']}] {alert['type']}: {alert['message']}")
    else:
        print("  アラートなし")

    print("\n【システムヘルス】")
    health_monitor = SystemHealthMonitor()

    for i in range(20):
        success = np.random.random() > 0.05  # 5%のエラー率
        health_monitor.record_request(success, "Sample error" if not success else None)

    health = health_monitor.get_health_status()
    print(f"  ステータス: {health['status']}")
    print(f"  リクエスト数: {health['total_requests']}")
    print(f"  エラー率: {health['error_rate']:.1%}")

    print("\n" + "=" * 60)
    print("テスト完了")
    print("=" * 60)
