"""
通知機能テストスクリプト

Discord Webhook通知が正しく動作するかテストします
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.automation.notify import (
    send_discord_notification,
    send_daily_summary,
    send_race_notification,
    send_error_notification
)
from datetime import datetime


def test_basic_notification():
    """基本通知テスト"""
    print("\n" + "=" * 60)
    print("1. 基本通知テスト")
    print("=" * 60)

    message = """🚤 **ボートレース予想システム**

通知テストメッセージです。
このメッセージが届けば設定完了です！

OK Discord Webhook連携成功
"""

    success = send_discord_notification(message)

    if success:
        print("OK 基本通知テスト成功")
        print("  Discordを確認してください")
    else:
        print("NG 基本通知テスト失敗")

    return success


def test_daily_summary():
    """朝の予想生成完了通知テスト"""
    print("\n" + "=" * 60)
    print("2. 朝の予想生成完了通知テスト")
    print("=" * 60)

    today = datetime.now().strftime('%Y-%m-%d')

    success = send_daily_summary(
        date=today,
        race_count=144,
        target_count=8
    )

    if success:
        print("OK 朝の予想生成完了通知テスト成功")
    else:
        print("NG 朝の予想生成完了通知テスト失敗")

    return success


def test_race_notification():
    """レース締切通知テスト"""
    print("\n" + "=" * 60)
    print("3. レース締切通知テスト")
    print("=" * 60)

    # テストデータ
    race_info = {
        'venue': '桐生',
        'race_number': 12,
        'deadline': '15:30',
        'race_id': '20260113011012'
    }

    prediction = {
        'pit_numbers': [1, 2, 3],
        'confidence': 0.65,
        'pattern': 'パターンH'
    }

    odds_info = {
        'trifecta_odds': 15.2,
        'expected_return': 9.88
    }

    direct_info = {
        'weather_change': '晴れ → 曇り',
        'wind_change': '無風 → 向かい風2m',
        'exhibition_notes': '1号艇が好タイム'
    }

    success = send_race_notification(race_info, prediction, odds_info, direct_info)

    if success:
        print("OK レース締切通知テスト成功")
    else:
        print("NG レース締切通知テスト失敗")

    return success


def test_error_notification():
    """エラー通知テスト"""
    print("\n" + "=" * 60)
    print("4. エラー通知テスト")
    print("=" * 60)

    success = send_error_notification(
        error_type="テスト用エラー",
        error_message="これはテスト用のエラー通知です。\n実際のエラーではありません。"
    )

    if success:
        print("OK エラー通知テスト成功")
    else:
        print("NG エラー通知テスト失敗")

    return success


def main():
    """メイン処理"""
    print("\n" + "=" * 60)
    print("Discord Webhook 通知テスト")
    print("=" * 60)
    print("\n注意:")
    print("  - .env ファイルに DISCORD_WEBHOOK_URL を設定してください")
    print("  - 設定方法: docs/guides/DISCORD_WEBHOOK_SETUP.md を参照")
    print("  - テストを実行すると4つの通知がDiscordに届きます")
    print("\n" + "=" * 60)

    input("\nEnterキーを押すとテスト開始します...")

    results = []

    # テスト1: 基本通知
    results.append(("基本通知", test_basic_notification()))

    input("\nEnterキーを押すと次のテストに進みます...")

    # テスト2: 朝の予想生成完了通知
    results.append(("朝の予想生成完了通知", test_daily_summary()))

    input("\nEnterキーを押すと次のテストに進みます...")

    # テスト3: レース締切通知
    results.append(("レース締切通知", test_race_notification()))

    input("\nEnterキーを押すと次のテストに進みます...")

    # テスト4: エラー通知
    results.append(("エラー通知", test_error_notification()))

    # 結果サマリー
    print("\n" + "=" * 60)
    print("テスト結果サマリー")
    print("=" * 60)

    all_success = True
    for test_name, success in results:
        status = "OK 成功" if success else "NG 失敗"
        print(f"  {test_name}: {status}")
        if not success:
            all_success = False

    print("\n" + "=" * 60)
    if all_success:
        print("OK すべてのテストが成功しました！")
        print("\n次のステップ:")
        print("  python scripts/automation/daily_scheduler.py")
    else:
        print("NG 一部のテストが失敗しました")
        print("\nトラブルシューティング:")
        print("  1. .env ファイルに DISCORD_WEBHOOK_URL が設定されているか確認")
        print("  2. URLが正しいか確認（余分なスペースがないか）")
        print("  3. docs/guides/DISCORD_WEBHOOK_SETUP.md を参照")
    print("=" * 60)

    return 0 if all_success else 1


if __name__ == "__main__":
    sys.exit(main())
