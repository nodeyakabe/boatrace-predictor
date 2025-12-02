"""
今日の予測生成機能のテスト

並列処理（DBビュー更新、直前情報、オッズ取得）の動作確認
"""
import sys
import time
from datetime import datetime

sys.path.insert(0, 'src')

from src.workflow.today_prediction import TodayPredictionWorkflow
from config.settings import DATABASE_PATH

def test_today_prediction():
    """今日の予測生成をテスト"""

    print("今日の予測生成機能のテスト")
    print("=" * 60)

    start_time = time.time()

    workflow = TodayPredictionWorkflow(
        db_path=DATABASE_PATH,
        progress_callback=lambda step, msg, pct: print(f"[{pct}%] {step}: {msg}")
    )

    try:
        result = workflow.run()

        elapsed = time.time() - start_time

        print()
        print("=" * 60)
        print("テスト結果:")
        print(f"- 成功: {result.get('success', False)}")
        print(f"- スケジュール取得: {result.get('schedule_fetched', 0)}会場")
        print(f"- 直前情報取得: {result.get('beforeinfo_fetched', 0)}件")
        print(f"- オッズ取得: {result.get('odds_fetched', 0)}件")
        print(f"- 予測生成: {result.get('predictions_generated', 0)}件")
        print(f"- 実行時間: {elapsed:.1f}秒")
        print("=" * 60)

        if result.get('success'):
            print("\n✅ テスト成功：並列処理が正常に動作しています")
        else:
            print(f"\n❌ テスト失敗：エラーが発生しました")

    except Exception as e:
        elapsed = time.time() - start_time
        print()
        print("=" * 60)
        print("❌ テスト失敗")
        print(f"エラー: {e}")
        print(f"実行時間: {elapsed:.1f}秒")
        print("=" * 60)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_today_prediction()
