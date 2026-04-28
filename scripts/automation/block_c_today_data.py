"""
Cブロック: 本日データ収集

実行時刻: 毎朝6:00
タスク:
1. 本日のレースデータ収集
2. 当日advance予測生成（Dブロックでのタイムアウト回避のため）

※ オッズ収集は08:00のEブロックに移動（6:00時点では公式サイト未公開のため）
"""

import os
import sys
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.automation.fetch_today_races import fetch_todays_races


class BlockCRunner:
    """Cブロック実行クラス"""

    def __init__(self):
        self.results = {}
        self.errors = []
        self.start_time = None
        self.end_time = None

    def run_all(self) -> bool:
        """全タスクを順次実行"""
        self.start_time = datetime.now()
        today = datetime.now().strftime('%Y-%m-%d')

        print("\n" + "=" * 80)
        print(f"[{self.start_time.strftime('%Y-%m-%d %H:%M:%S')}] Cブロック開始: 本日データ収集")
        print(f"対象日: {today}")
        print("=" * 80 + "\n")

        # タスク1: レースデータ収集
        print(f"[タスク 1/2] 本日のレースデータ収集...")
        task1_start = datetime.now()

        try:
            race_count = fetch_todays_races(headless=True)
            elapsed = (datetime.now() - task1_start).total_seconds()

            self.results["レースデータ収集"] = {
                "status": "OK",
                "count": race_count,
                "elapsed": elapsed
            }

            print(f"  取得: {race_count}レース")
            print(f"  所要時間: {int(elapsed // 60)}分{int(elapsed % 60)}秒")
            print(f"  [OK]\n")

            if race_count == 0:
                # 0レースの場合、データ取得失敗の可能性
                print("[WARNING] レースデータ未取得（0件）")
                print("[INFO] ネットワークエラーまたは一時的な取得失敗の可能性があります。")
                print("[INFO] 8:00のDブロック実行時に再度データ収集を試みます。\n")

                self.results["レースデータ収集"]["warning"] = "データ取得失敗（再試行予定）"
                # 休止日通知は送らず、エラー警告として扱う
                self._finalize(is_rest_day=False, data_fetch_failed=True)
                return True

        except Exception as e:
            elapsed = (datetime.now() - task1_start).total_seconds()
            error_msg = str(e)

            self.results["レースデータ収集"] = {
                "status": "ERROR",
                "error": error_msg,
                "elapsed": elapsed
            }
            self.errors.append(f"レースデータ収集: {error_msg}")

            print(f"  [ERROR] {error_msg[:100]}")
            print(f"  所要時間: {int(elapsed // 60)}分{int(elapsed % 60)}秒\n")

            # レースデータ取得失敗の場合、オッズ取得はスキップ
            self._finalize()
            return False

        # タスク2: 当日advance予測生成
        # Dブロック（07:30）でのタイムアウトを回避するため、Cブロックで事前生成
        print(f"[タスク 2/2] 当日advance予測生成...")
        task2_start = datetime.now()

        try:
            pred_count = self._task_advance_predictions(race_count)
            elapsed = (datetime.now() - task2_start).total_seconds()

            self.results["advance予測生成"] = {
                "status": "OK",
                "count": pred_count,
                "elapsed": elapsed
            }

            print(f"  生成: {pred_count}レース")
            print(f"  所要時間: {int(elapsed // 60)}分{int(elapsed % 60)}秒")
            print(f"  [OK]\n")

        except Exception as e:
            elapsed = (datetime.now() - task2_start).total_seconds()
            error_msg = str(e)

            self.results["advance予測生成"] = {
                "status": "ERROR",
                "error": error_msg,
                "elapsed": elapsed
            }
            self.errors.append(f"advance予測生成: {error_msg}")

            print(f"  [ERROR] {error_msg[:100]}")
            print(f"  所要時間: {int(elapsed // 60)}分{int(elapsed % 60)}秒\n")

        self.end_time = datetime.now()
        return self._finalize()

    def _task_advance_predictions(self, race_count: int) -> int:
        """当日advance予測生成（fast_prediction_generator.py使用）"""
        if race_count == 0:
            print("  [SKIP] レース0件のためスキップ")
            return 0

        script_path = project_root / 'scripts' / 'prediction' / 'fast_prediction_generator.py'
        today = datetime.now().strftime('%Y-%m-%d')

        # タイムアウト: レース数×15秒、最低2400秒（40分）
        timeout = max(2400, race_count * 15)
        print(f"  対象日: {today}, タイムアウト: {timeout}秒")

        result = subprocess.run(
            [sys.executable, str(script_path), '--date', today, '--type', 'advance'],
            cwd=str(project_root),
            timeout=timeout,
            capture_output=True,
            encoding='utf-8',
            errors='replace'
        )

        if result.stdout:
            for line in result.stdout.splitlines()[-10:]:  # 最後10行のみ表示
                if line.strip():
                    print(f"  {line}", flush=True)

        if result.returncode != 0:
            stderr_short = result.stderr[:200] if result.stderr else '(なし)'
            raise Exception(f"exit={result.returncode}: {stderr_short}")

        # 生成件数をDBから取得
        db_path = project_root / 'data' / 'boatrace.db'
        conn = sqlite3.connect(str(db_path), timeout=30.0)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(DISTINCT rp.race_id)
            FROM race_predictions rp
            JOIN races r ON rp.race_id = r.id
            WHERE r.race_date = ? AND rp.prediction_type = 'advance'
        """, (today,))
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def _finalize(self, is_rest_day: bool = False, data_fetch_failed: bool = False) -> bool:
        """最終結果をサマリー表示・通知"""
        self.end_time = datetime.now()
        total_elapsed = (self.end_time - self.start_time).total_seconds()
        success_count = sum(1 for r in self.results.values() if r["status"] == "OK")
        total_count = len(self.results)

        print("=" * 80)
        print(f"[{self.end_time.strftime('%Y-%m-%d %H:%M:%S')}] Cブロック完了")
        print(f"  成功: {success_count}/{total_count}タスク")
        print(f"  総所要時間: {int(total_elapsed // 60)}分{int(total_elapsed % 60)}秒")
        print("=" * 80 + "\n")

        return len(self.errors) == 0


def main():
    """メイン実行"""
    runner = BlockCRunner()
    success = runner.run_all()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
