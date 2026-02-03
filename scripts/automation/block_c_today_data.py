"""
Cブロック: 本日データ収集

実行時刻: 毎朝7:00
タスク:
1. 本日のレースデータ収集
2. 本日のオッズ収集
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.automation.fetch_today_races import fetch_todays_races
from scripts.automation.fetch_today_odds import fetch_todays_odds
from scripts.automation.notify import send_discord_notification, send_error_notification


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
                # レース休止日の場合はここで正常終了
                print("[INFO] 本日はレース休止日です\n")
                self._finalize(is_rest_day=True)
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

        # タスク2: オッズ収集（レースがある場合のみ）
        print(f"[タスク 2/2] 本日のオッズ収集...")
        task2_start = datetime.now()

        try:
            # OddsScraperはrequestsベースなのでheadlessパラメータは不要
            odds_count = fetch_todays_odds()
            elapsed = (datetime.now() - task2_start).total_seconds()

            self.results["オッズ収集"] = {
                "status": "OK",
                "count": odds_count,
                "elapsed": elapsed
            }

            print(f"  取得: {odds_count}レース")
            print(f"  所要時間: {int(elapsed // 60)}分{int(elapsed % 60)}秒")
            print(f"  [OK]\n")

        except Exception as e:
            elapsed = (datetime.now() - task2_start).total_seconds()
            error_msg = str(e)

            self.results["オッズ収集"] = {
                "status": "ERROR",
                "error": error_msg,
                "elapsed": elapsed
            }
            self.errors.append(f"オッズ収集: {error_msg}")

            print(f"  [ERROR] {error_msg[:100]}")
            print(f"  所要時間: {int(elapsed // 60)}分{int(elapsed % 60)}秒\n")

        self.end_time = datetime.now()
        return self._finalize()

    def _finalize(self, is_rest_day: bool = False) -> bool:
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

        # Discord通知
        self._send_notification(success_count, total_count, total_elapsed, is_rest_day)

        return len(self.errors) == 0

    def _send_notification(self, success_count: int, total_count: int, elapsed: float, is_rest_day: bool):
        """Discord通知送信"""
        today = datetime.now().strftime('%Y-%m-%d')

        if is_rest_day:
            message = f"""ℹ️ **Cブロック完了: 本日はレース休止日**

対象日: {today}
完了時刻: {self.end_time.strftime('%Y-%m-%d %H:%M:%S')}

本日はレースがありません。
次回は明日の予定です。
"""
        else:
            status_icon = "✅" if success_count == total_count else "⚠️"

            message = f"""{status_icon} **Cブロック完了: 本日データ収集**

対象日: {today}
完了時刻: {self.end_time.strftime('%Y-%m-%d %H:%M:%S')}

**結果:**
- 成功: {success_count}/{total_count}タスク
- 総所要時間: {int(elapsed // 60)}分{int(elapsed % 60)}秒

**タスク詳細:**
"""

            for name, result in self.results.items():
                if result["status"] == "OK":
                    message += f"✅ {name}: {result['count']}件\n"
                else:
                    message += f"❌ {name}: {result['error'][:50]}\n"

            if self.errors:
                message += f"\n⚠️ エラー {len(self.errors)}件発生"

        send_discord_notification(message)


def main():
    """メイン実行"""
    runner = BlockCRunner()
    success = runner.run_all()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
