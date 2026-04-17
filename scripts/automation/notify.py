"""
Discord Webhook通知モジュール

レース締切前の通知を送信
"""

import os
import sys
import requests
from datetime import datetime
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

# 環境変数読み込み
load_dotenv()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")


def send_discord_notification(message: str) -> bool:
    """
    Discord Webhookでメッセージを送信

    Args:
        message: 送信するメッセージ

    Returns:
        bool: 送信成功ならTrue
    """
    if not DISCORD_WEBHOOK_URL:
        print("ERROR: DISCORD_WEBHOOK_URL が設定されていません")
        print("ガイド: docs/guides/DISCORD_WEBHOOK_SETUP.md を参照してください")
        return False

    # Discordの文字数制限は2000文字
    if len(message) > 2000:
        message = message[:1997] + "..."

    data = {"content": message}

    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=data, timeout=30)

        if response.status_code == 204:
            print(f"[OK] Discord通知送信成功: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            return True
        else:
            print(f"[ERROR] Discord通知送信失敗: {response.status_code}")
            print(f"レスポンス: {response.text}")
            return False

    except Exception as e:
        print(f"[ERROR] Discord通知送信エラー: {e}")
        return False


def calculate_bet_amount(confidence: float, odds: float, base_amount: int = 1000) -> int:
    """
    推奨購入額を計算（ケリー基準の簡易版）

    Args:
        confidence: 信頼度（0.0～1.0）
        odds: オッズ
        base_amount: 基本購入額（デフォルト1000円）

    Returns:
        int: 推奨購入額
    """
    # 信頼度が低い場合は最小額
    if confidence < 0.3:
        return base_amount

    # 期待値がプラスの場合のみ購入額を増やす
    expected_value = confidence * odds - 1.0
    if expected_value <= 0:
        return base_amount

    # ケリー基準の簡易版（最大で基本額の3倍まで）
    kelly_fraction = expected_value / (odds - 1)
    multiplier = min(1 + kelly_fraction * 2, 3.0)

    return int(base_amount * multiplier)


def format_race_notification(
    race_info: dict,
    prediction: dict,
    odds_info: dict,
    direct_info: dict = None
) -> str:
    """
    レース通知メッセージをフォーマット

    Args:
        race_info: {venue, race_number, deadline, race_id}
        prediction: {pit_numbers, confidence, pattern}
        odds_info: {trifecta_odds, expected_return}
        direct_info: 直前情報（オプショナル）

    Returns:
        str: フォーマットされたメッセージ
    """
    # 基本情報
    venue = race_info['venue']
    race_num = race_info['race_number']
    deadline = race_info['deadline']

    # 予想情報（pit_numbersは常にリストのリスト形式: [[1,2,3]] or [[1,2,3],[1,2,4],[1,2,5]]）
    pit_numbers = prediction['pit_numbers']

    # pit_numbersをリストのリスト形式に統一（2026-01-28修正）
    if not isinstance(pit_numbers[0], list):
        # 旧形式（リスト）の場合は変換
        pit_numbers = [pit_numbers]

    # 買い目を整形
    combinations = ['-'.join(map(str, combo)) for combo in pit_numbers]

    if len(combinations) > 1:
        # 複数点買い
        combination_str = '\n  '.join(combinations)
        bet_info = f"{len(combinations)}点買い\n  {combination_str}"
    else:
        # 1点買い
        bet_info = f"{combinations[0]}"

    confidence = prediction['confidence']

    # オッズ情報（2026-01-28修正: パターンH対応）
    odds = odds_info['trifecta_odds']
    multi_bets = odds_info.get('multi_bets', None)

    # オッズ文字列
    if multi_bets and len(multi_bets) > 1:
        odds_str = ' / '.join(f"{b['combination']}:{b['odds']:.1f}倍" for b in multi_bets)
    else:
        odds_str = f"{odds:.1f}倍"

    message = f"🎯 **{venue} {race_num}R** ({deadline}) [{confidence:.0%}]\n{bet_info} {odds_str}"

    return message


def send_race_notification(
    race_info: dict,
    prediction: dict,
    odds_info: dict,
    direct_info: dict = None
) -> bool:
    """
    レース通知を送信

    Args:
        race_info: レース情報
        prediction: 予想情報
        odds_info: オッズ情報
        direct_info: 直前情報（オプショナル）

    Returns:
        bool: 送信成功ならTrue
    """
    message = format_race_notification(race_info, prediction, odds_info, direct_info)
    return send_discord_notification(message)


def send_daily_summary(date: str, race_count: int, target_count: int, target_races: list = None, candidate_races: list = None) -> bool:
    """
    朝の予想生成完了通知

    Args:
        date: 日付（YYYY-MM-DD）
        race_count: 総レース数
        target_count: 購入対象レース数
        target_races: 購入対象レースリスト [{'venue': str, 'race_num': int, 'combination': str, 'odds': float}, ...]
        candidate_races: 候補レースリスト [{'venue': str, 'race_num': int, 'combination': str, 'reason': str}, ...]

    Returns:
        bool: 送信成功ならTrue
    """
    cand_count = len(candidate_races) if candidate_races else 0

    if target_count == 0 and cand_count == 0:
        message = f"📋 {date} 購入対象なし"
    else:
        message = f"📋 **{date} 予想完了** 購入{target_count}件 候補{cand_count}件\n"
        if target_races:
            for race in target_races:
                odds = race.get('odds', 0.0)
                odds_str = f" {odds:.1f}倍" if odds else ""
                message += f"- {race.get('venue')} {race.get('race_num')}R ({race.get('race_time')}): {race.get('combination')}{odds_str}\n"
        if candidate_races:
            message += "候補:"
            for race in candidate_races:
                message += f" {race.get('venue')}{race.get('race_num')}R({race.get('race_time')})"

    return send_discord_notification(message)


def send_error_notification(error_type: str, error_message: str) -> bool:
    """
    エラー通知を送信

    Args:
        error_type: エラー種別
        error_message: エラーメッセージ

    Returns:
        bool: 送信成功ならTrue
    """
    message = f"⚠️ **{error_type}** {datetime.now().strftime('%H:%M')}\n```\n{error_message[:200]}\n```"
    return send_discord_notification(message)


if __name__ == "__main__":
    # テスト実行
    print("Discord Webhook通知テスト")
    print("-" * 50)

    test_message = """**ボートレース予想システム**

通知テストメッセージです。
このメッセージが届けば設定完了です！

Discord Webhook連携成功
"""

    success = send_discord_notification(test_message)

    if success:
        print("\n[OK] テスト通知送信成功！")
        print("Discordを確認してください。")
    else:
        print("\n[ERROR] テスト通知送信失敗")
        print("docs/guides/DISCORD_WEBHOOK_SETUP.md を確認してください")
