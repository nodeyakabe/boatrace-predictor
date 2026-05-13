"""
Aブロック: 前日データ完全収集

実行時刻: 毎朝5:00
タスク:
1. 前日レース結果収集
2. 前日確定オッズ取得
3. 前日直前情報収集
4. 前日オリジナル展示データ収集
5. 前日直前予想生成
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.automation.fetch_yesterday_results import fetch_yesterday_results
from scripts.automation.fetch_yesterday_final_odds import fetch_yesterday_final_odds
from scripts.automation.fetch_yesterday_beforeinfo import fetch_yesterday_beforeinfo
from scripts.automation.daily_tenji_collector import collect_previous_day_tenji
from scripts.automation.generate_yesterday_before_predictions import generate_yesterday_before_predictions
from scripts.automation.reconcile_yesterday_bets import reconcile_yesterday_bets
from scripts.automation.notify import send_discord_notification, send_error_notification, send_reconcile_notification


class BlockARunner:
    """Aブロック実行クラス"""

    def __init__(self):
        self.results = {}
        self.errors = []
        self.start_time = None
        self.end_time = None
        self._reconcile_result = None

    def run_all(self) -> bool:
        """全タスクを順次実行"""
        self.start_time = datetime.now()
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

        print("\n" + "=" * 80)
        print(f"[{self.start_time.strftime('%Y-%m-%d %H:%M:%S')}] Aブロック開始: 前日データ完全収集")
        print(f"対象日: {yesterday}")
        print("=" * 80 + "\n")

        tasks = [
            ("前日レース結果収集", self._task_results),
            ("前日直前情報収集", self._task_beforeinfo),
            ("前日展示データ収集", self._task_tenji),
            ("前日直前予想生成", self._task_before_predictions),
            # 突合せはfinal_odds上書き前に実行（pre-race oddsで条件判定するため）
            ("前日予想結果突合せ", self._task_reconcile),
            ("前日確定オッズ取得", self._task_final_odds),
        ]

        for idx, (name, task_func) in enumerate(tasks, 1):
            print(f"[タスク {idx}/{len(tasks)}] {name}...")
            task_start = datetime.now()

            try:
                count = task_func() or 0
                elapsed = (datetime.now() - task_start).total_seconds()

                self.results[name] = {
                    "status": "OK",
                    "count": count,
                    "elapsed": elapsed
                }

                print(f"  取得: {count}件")
                print(f"  所要時間: {int(elapsed // 60)}分{int(elapsed % 60)}秒")
                print(f"  [OK]\n")

            except Exception as e:
                elapsed = (datetime.now() - task_start).total_seconds()
                error_msg = str(e)

                self.results[name] = {
                    "status": "ERROR",
                    "error": error_msg,
                    "elapsed": elapsed
                }
                self.errors.append(f"{name}: {error_msg}")

                print(f"  [ERROR] {error_msg[:100]}")
                print(f"  所要時間: {int(elapsed // 60)}分{int(elapsed % 60)}秒\n")

                # エラーでも後続タスクは続行

        self.end_time = datetime.now()
        return self._finalize()

    def _task_results(self) -> int:
        """前日レース結果収集"""
        return fetch_yesterday_results(headless=True)

    def _task_final_odds(self) -> int:
        """前日確定オッズ取得"""
        return fetch_yesterday_final_odds(headless=True)

    def _task_beforeinfo(self) -> int:
        """前日直前情報収集"""
        return fetch_yesterday_beforeinfo(headless=True)

    def _task_tenji(self) -> int:
        """前日オリジナル展示データ収集"""
        return collect_previous_day_tenji(headless=True, update_existing=True)

    def _task_before_predictions(self) -> int:
        """前日直前予想生成"""
        return generate_yesterday_before_predictions(force=False)

    def _task_reconcile(self) -> int:
        """前日予想結果突合せ"""
        db_path = str(project_root / 'data' / 'boatrace.db')
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        result = reconcile_yesterday_bets(db_path=db_path, target_date=yesterday)
        self._reconcile_result = result

        # 購入対象件数を返す（タスク件数カウント用）
        return result['target_count']

    def _finalize(self) -> bool:
        """最終結果をサマリー表示・通知"""
        total_elapsed = (self.end_time - self.start_time).total_seconds()
        success_count = sum(1 for r in self.results.values() if r["status"] == "OK")
        total_count = len(self.results)

        print("=" * 80)
        print(f"[{self.end_time.strftime('%Y-%m-%d %H:%M:%S')}] Aブロック完了")
        print(f"  成功: {success_count}/{total_count}タスク")
        print(f"  総所要時間: {int(total_elapsed // 60)}分{int(total_elapsed % 60)}秒")
        print("=" * 80 + "\n")

        # Discord通知
        self._send_notification(success_count, total_count, total_elapsed)

        return len(self.errors) == 0

    def _send_notification(self, success_count: int, total_count: int, elapsed: float):
        """Discord通知送信"""
        status_icon = "✅" if success_count == total_count else "⚠️"
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%m/%d')
        elapsed_str = f"{int(elapsed // 60)}分{int(elapsed % 60)}秒"

        message = f"{status_icon} **A完了** {yesterday}  {success_count}/{total_count}タスク  {elapsed_str}"

        # タスク別取得件数を表示
        TASK_SHORT = {
            "前日レース結果収集": "結果",
            "前日確定オッズ取得": "オッズ",
            "前日直前情報収集": "直前情報",
            "前日展示データ収集": "展示",
            "前日直前予想生成": "before予測",
            "前日予想結果突合せ": "突合せ",
        }
        task_parts = []
        for name, res in self.results.items():
            short = TASK_SHORT.get(name, name)
            if res["status"] == "OK":
                task_parts.append(f"{short}:{res['count']:,}件")
            else:
                task_parts.append(f"❌{short}")
        if task_parts:
            message += "\n" + " / ".join(task_parts)

        if self.errors:
            message += "\n" + "\n".join(f"❌ {e[:80]}" for e in self.errors)

        # 突合せ結果を別通知で送信（alert: 1行要約 / log: 詳細）
        if self._reconcile_result is not None:
            send_reconcile_notification(self._reconcile_result)

        send_discord_notification(message, channel='log')


def main():
    """メイン実行"""
    runner = BlockARunner()
    success = runner.run_all()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
