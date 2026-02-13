"""
Dブロック: 本日予想生成

実行時刻: 毎朝8:00
タスク:
1. 本日の予想生成
2. レース通知スケジュール登録（スケジューラー本体で実施）
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.automation.generate_daily_predictions import generate_todays_predictions
from scripts.automation.fetch_today_races import fetch_todays_races
from scripts.automation.fetch_today_odds import fetch_todays_odds
from scripts.automation.notify import send_discord_notification, send_error_notification
import sqlite3


class BlockDRunner:
    """Dブロック実行クラス"""

    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.success = False

    def run_all(self) -> bool:
        """予想生成を実行"""
        self.start_time = datetime.now()
        today = datetime.now().strftime('%Y-%m-%d')

        print("\n" + "=" * 80)
        print(f"[{self.start_time.strftime('%Y-%m-%d %H:%M:%S')}] Dブロック開始: 本日予想生成")
        print(f"対象日: {today}")
        print("=" * 80 + "\n")

        # Cブロックで0件だった場合、データ再収集を試みる
        self._check_and_collect_data_if_needed(today)

        print(f"[タスク 1/1] 本日の予想生成...")
        task_start = datetime.now()

        try:
            # 予想生成（内部でDiscord通知も送信される）
            self.success = generate_todays_predictions()
            elapsed = (datetime.now() - task_start).total_seconds()

            if self.success:
                print(f"  所要時間: {int(elapsed // 60)}分{int(elapsed % 60)}秒")
                print(f"  [OK]\n")
            else:
                print(f"  [WARNING] 予想生成失敗（レースなしの可能性）")
                print(f"  所要時間: {int(elapsed // 60)}分{int(elapsed % 60)}秒\n")

        except Exception as e:
            elapsed = (datetime.now() - task_start).total_seconds()
            error_msg = str(e)

            print(f"  [ERROR] {error_msg[:100]}")
            print(f"  所要時間: {int(elapsed // 60)}分{int(elapsed % 60)}秒\n")

            # エラー通知
            send_error_notification("Dブロックエラー", error_msg)
            self.success = False

        self.end_time = datetime.now()
        return self._finalize()

    def _check_and_collect_data_if_needed(self, today: str) -> None:
        """
        本日のレース数を確認し、0件の場合はデータ再収集を試みる
        Cブロック（7:00）でデータ公開前だった場合の救済措置
        """
        try:
            db_path = project_root / 'data' / 'boatrace.db'
            conn = sqlite3.connect(db_path, timeout=30.0)
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM races WHERE race_date = ?", (today,))
            race_count = cursor.fetchone()[0]
            conn.close()

            if race_count == 0:
                print("[INFO] 本日のレースデータが0件です。データ再収集を試みます...\n")

                # レースデータ収集
                print("[追加収集] レースデータ...")
                race_count = fetch_todays_races(headless=True)
                print(f"  収集: {race_count}レース\n")

                if race_count > 0:
                    # オッズ収集
                    print("[追加収集] オッズデータ...")
                    odds_count = fetch_todays_odds()
                    print(f"  収集: {odds_count}レース\n")

                    print("[SUCCESS] データ再収集が完了しました\n")
                else:
                    print("[INFO] データ再収集でも0件でした。本日は休止日の可能性があります\n")
            else:
                print(f"[INFO] 本日のレースデータ: {race_count}レース（再収集不要）\n")

        except Exception as e:
            print(f"[WARNING] データ確認/再収集中にエラー: {e}\n")
            # エラーでも予想生成は続行

    def _finalize(self) -> bool:
        """最終結果をサマリー表示"""
        total_elapsed = (self.end_time - self.start_time).total_seconds()

        print("=" * 80)
        print(f"[{self.end_time.strftime('%Y-%m-%d %H:%M:%S')}] Dブロック完了")
        print(f"  ステータス: {'成功' if self.success else '失敗'}")
        print(f"  総所要時間: {int(total_elapsed // 60)}分{int(total_elapsed % 60)}秒")
        print("=" * 80 + "\n")

        # 注: Discord通知はgenerate_todays_predictions()内で送信される

        return self.success


def main():
    """メイン実行"""
    runner = BlockDRunner()
    success = runner.run_all()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
