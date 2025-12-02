"""
進捗トラッカー - 統一された進捗管理とレポート機能

全ワークフローで使用する共通の進捗管理を提供
"""
import time
from datetime import datetime, timedelta
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass, field


@dataclass
class ProgressStats:
    """進捗統計情報"""
    total: int = 0
    completed: int = 0
    errors: int = 0
    skipped: int = 0
    start_time: float = field(default_factory=time.time)

    @property
    def success_count(self) -> int:
        """成功件数"""
        return self.completed - self.errors - self.skipped

    @property
    def progress_percent(self) -> float:
        """進捗率（%）"""
        if self.total == 0:
            return 0.0
        return (self.completed / self.total) * 100

    @property
    def elapsed_time(self) -> float:
        """経過時間（秒）"""
        return time.time() - self.start_time

    @property
    def average_time_per_item(self) -> float:
        """1件あたりの平均処理時間（秒）"""
        if self.completed == 0:
            return 0.0
        return self.elapsed_time / self.completed

    @property
    def estimated_remaining_time(self) -> float:
        """残り推定時間（秒）"""
        if self.completed == 0 or self.total == 0:
            return 0.0
        remaining = self.total - self.completed
        return remaining * self.average_time_per_item

    @property
    def success_rate(self) -> float:
        """成功率（%）"""
        if self.completed == 0:
            return 0.0
        return (self.success_count / self.completed) * 100

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            'total': self.total,
            'completed': self.completed,
            'success': self.success_count,
            'errors': self.errors,
            'skipped': self.skipped,
            'progress_percent': round(self.progress_percent, 1),
            'elapsed_seconds': round(self.elapsed_time, 1),
            'remaining_seconds': round(self.estimated_remaining_time, 1),
            'success_rate': round(self.success_rate, 1)
        }


class ProgressTracker:
    """
    進捗トラッカー

    使用例:
        tracker = ProgressTracker(
            total=100,
            name="データ取得",
            callback=lambda msg, pct: print(f"[{pct}%] {msg}")
        )

        for item in items:
            try:
                process(item)
                tracker.increment_success()
            except Exception:
                tracker.increment_error()

        report = tracker.get_report()
    """

    def __init__(
        self,
        total: int,
        name: str = "処理",
        callback: Optional[Callable[[str, int], None]] = None,
        report_interval: int = 10
    ):
        """
        Args:
            total: 総処理数
            name: 処理名
            callback: 進捗コールバック関数 (message, progress_percent) -> None
            report_interval: 進捗報告間隔（N件ごと）
        """
        self.stats = ProgressStats(total=total)
        self.name = name
        self.callback = callback
        self.report_interval = report_interval
        self.last_report_count = 0

    def increment_success(self, message: Optional[str] = None):
        """成功をカウント"""
        self.stats.completed += 1
        self._maybe_report(message)

    def increment_error(self, message: Optional[str] = None):
        """エラーをカウント"""
        self.stats.completed += 1
        self.stats.errors += 1
        self._maybe_report(message or "エラー発生")

    def increment_skip(self, message: Optional[str] = None):
        """スキップをカウント"""
        self.stats.completed += 1
        self.stats.skipped += 1
        self._maybe_report(message or "スキップ")

    def _maybe_report(self, message: Optional[str] = None):
        """進捗報告（間隔に達した場合）"""
        if self.callback is None:
            return

        # 報告間隔に達したか、完了した場合
        if (self.stats.completed - self.last_report_count >= self.report_interval or
            self.stats.completed == self.stats.total):

            self.last_report_count = self.stats.completed
            progress_msg = self._format_progress_message(message)
            progress_pct = int(self.stats.progress_percent)

            self.callback(progress_msg, progress_pct)

    def _format_progress_message(self, custom_message: Optional[str] = None) -> str:
        """進捗メッセージをフォーマット"""
        base = f"{self.name}: {self.stats.completed}/{self.stats.total}"

        if custom_message:
            base += f" - {custom_message}"

        # 残り時間を追加
        if self.stats.completed > 0 and self.stats.completed < self.stats.total:
            remaining = self.stats.estimated_remaining_time
            if remaining > 60:
                remaining_str = f"{int(remaining/60)}分{int(remaining%60)}秒"
            else:
                remaining_str = f"{int(remaining)}秒"
            base += f" (残り約{remaining_str})"

        return base

    def get_report(self) -> str:
        """詳細レポートを取得"""
        elapsed = self.stats.elapsed_time
        elapsed_str = f"{int(elapsed/60)}分{int(elapsed%60)}秒" if elapsed > 60 else f"{int(elapsed)}秒"

        lines = [
            f"{'='*60}",
            f"{self.name} - 完了レポート",
            f"{'='*60}",
            f"総処理数: {self.stats.total}件",
            f"完了: {self.stats.completed}件",
            f"成功: {self.stats.success_count}件 ({self.stats.success_rate:.1f}%)",
            f"エラー: {self.stats.errors}件",
            f"スキップ: {self.stats.skipped}件",
            f"処理時間: {elapsed_str}",
            f"平均速度: {1/self.stats.average_time_per_item:.1f}件/秒" if self.stats.average_time_per_item > 0 else "平均速度: N/A",
            f"{'='*60}"
        ]

        return '\n'.join(lines)

    def get_stats(self) -> ProgressStats:
        """統計情報を取得"""
        return self.stats


class MultiStageProgressTracker:
    """
    複数ステージ対応の進捗トラッカー

    使用例:
        tracker = MultiStageProgressTracker(
            stages=["データ取得", "処理", "保存"],
            callback=lambda stage, msg, pct: print(f"[{stage}] {msg} ({pct}%)")
        )

        # ステージ1
        tracker.start_stage(0, total=100)
        for item in items:
            process(item)
            tracker.increment()

        # ステージ2
        tracker.start_stage(1, total=100)
        ...
    """

    def __init__(
        self,
        stages: list[str],
        callback: Optional[Callable[[str, str, int], None]] = None
    ):
        """
        Args:
            stages: ステージ名のリスト
            callback: コールバック関数 (stage_name, message, overall_progress) -> None
        """
        self.stages = stages
        self.callback = callback
        self.current_stage_index = -1
        self.current_tracker: Optional[ProgressTracker] = None
        self.stage_trackers: list[Optional[ProgressTracker]] = [None] * len(stages)

    def start_stage(self, stage_index: int, total: int):
        """ステージを開始"""
        if stage_index >= len(self.stages):
            raise ValueError(f"無効なステージインデックス: {stage_index}")

        self.current_stage_index = stage_index
        stage_name = self.stages[stage_index]

        # ステージごとのトラッカーを作成
        def stage_callback(message: str, stage_progress: int):
            if self.callback:
                overall_progress = self._calculate_overall_progress(stage_index, stage_progress)
                self.callback(stage_name, message, overall_progress)

        self.current_tracker = ProgressTracker(
            total=total,
            name=stage_name,
            callback=stage_callback
        )
        self.stage_trackers[stage_index] = self.current_tracker

    def _calculate_overall_progress(self, stage_index: int, stage_progress: int) -> int:
        """全体進捗を計算"""
        if len(self.stages) == 0:
            return 0

        # 各ステージの重みを均等とする
        stage_weight = 100 / len(self.stages)

        # 完了したステージの進捗
        completed_stages_progress = stage_index * stage_weight

        # 現在ステージの進捗
        current_stage_progress = (stage_progress / 100) * stage_weight

        return int(completed_stages_progress + current_stage_progress)

    def increment_success(self, message: Optional[str] = None):
        """現在ステージの成功をカウント"""
        if self.current_tracker:
            self.current_tracker.increment_success(message)

    def increment_error(self, message: Optional[str] = None):
        """現在ステージのエラーをカウント"""
        if self.current_tracker:
            self.current_tracker.increment_error(message)

    def increment_skip(self, message: Optional[str] = None):
        """現在ステージのスキップをカウント"""
        if self.current_tracker:
            self.current_tracker.increment_skip(message)

    def get_overall_report(self) -> str:
        """全ステージの総合レポート"""
        lines = [
            f"{'='*60}",
            "全ステージ - 総合レポート",
            f"{'='*60}"
        ]

        for i, tracker in enumerate(self.stage_trackers):
            if tracker:
                lines.append(f"\n[ステージ{i+1}: {self.stages[i]}]")
                stats = tracker.get_stats()
                lines.append(f"  完了: {stats.completed}/{stats.total}件")
                lines.append(f"  成功率: {stats.success_rate:.1f}%")
                lines.append(f"  処理時間: {int(stats.elapsed_time)}秒")

        lines.append(f"{'='*60}")
        return '\n'.join(lines)
