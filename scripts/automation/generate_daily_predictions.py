"""
朝の予想生成モジュール

毎朝実行し、本日のレース予想を生成
UIの「今日の予想を生成」と同じ処理を実行
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.automation.notify import send_daily_summary, send_error_notification
from src.workflow.today_prediction import TodayPredictionWorkflow


def get_todays_target_count(db_path: str) -> int:
    """
    本日の購入対象レース数を取得

    Args:
        db_path: データベースパス

    Returns:
        int: 購入対象レース数
    """
    import sqlite3

    today = datetime.now().strftime('%Y-%m-%d')

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        query = """
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        JOIN race_predictions p ON r.id = p.race_id
        WHERE r.race_date = ?
            AND p.rank_prediction = 1
            AND p.prediction_type = 'advance'
        """
        cursor.execute(query, (today,))
        count = cursor.fetchone()[0]
        return count
    finally:
        conn.close()


def progress_callback(step: str, message: str, progress: int):
    """進捗表示用コールバック"""
    print(f"[{progress}%] {step}: {message}")


def generate_todays_predictions() -> bool:
    """
    本日のレース予想を生成（UIと同じワークフロー）

    Returns:
        bool: 成功ならTrue
    """
    today = datetime.now()
    today_str = today.strftime('%Y-%m-%d')

    print("=" * 60)
    print(f"本日の予想生成開始: {today_str}")
    print("=" * 60)

    # データベースパス
    db_path = project_root / "data" / "boatrace.db"

    if not db_path.exists():
        error_msg = f"データベースが見つかりません: {db_path}"
        print(f"[ERROR] {error_msg}")
        send_error_notification("予想生成失敗", error_msg)
        return False

    # TodayPredictionWorkflowを使用（UIと同じ処理）
    try:
        workflow = TodayPredictionWorkflow(
            db_path=str(db_path),
            project_root=str(project_root),
            progress_callback=progress_callback
        )

        result = workflow.run()

        if result['success']:
            print("\n[OK] 予想生成完了")
            print(f"  取得レース: {result['races_fetched']}")
            print(f"  予測生成: {result['predictions_generated']}")
            print(f"  オッズ取得: {result['odds_fetched']}")

            # 購入対象レース数を取得
            target_count = get_todays_target_count(str(db_path))

            print(f"  購入対象レース数: {target_count}件")

            # 完了通知送信
            send_daily_summary(
                date=today_str,
                race_count=result['races_fetched'],
                target_count=target_count
            )

            return True
        else:
            error_msg = f"予想生成失敗: {', '.join(result['errors'])}"
            print(f"[ERROR] {error_msg}")
            send_error_notification("予想生成失敗", error_msg)
            return False

    except Exception as e:
        error_msg = f"予想生成中にエラーが発生: {str(e)}"
        print(f"[ERROR] {error_msg}")
        send_error_notification("予想生成エラー", error_msg)
        return False


def main():
    """メイン処理"""
    print("\n" + "=" * 60)
    print("朝の予想生成")
    print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")

    success = generate_todays_predictions()

    print("\n" + "=" * 60)
    if success:
        print("[OK] 予想生成完了")
    else:
        print("[ERROR] 予想生成失敗")
    print("=" * 60)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
