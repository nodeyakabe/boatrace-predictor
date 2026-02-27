"""
パターンH（3点買い）の通知テスト

朝の通知と締切前の通知でパターンHが正しく表示されるかテスト
"""

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.automation.notify import format_race_notification, send_daily_summary

def test_pattern_h_race_notification():
    """締切前の通知（パターンH）"""
    print("=" * 60)
    print("テスト1: 締切前の通知（パターンH・3点買い）")
    print("=" * 60)

    race_info = {
        'venue': '鳴門',
        'race_number': 5,
        'deadline': '14:30',
        'race_id': 12345
    }

    # パターンH: リストのリスト形式
    prediction = {
        'pit_numbers': [[1, 2, 3], [1, 2, 4], [1, 2, 5]],  # 3点買い
        'confidence': 0.75
    }

    odds_info = {
        'trifecta_odds': 45.3,
    }

    message = format_race_notification(race_info, prediction, odds_info)
    print(message)
    print()


def test_single_bet_race_notification():
    """締切前の通知（1点買い）"""
    print("=" * 60)
    print("テスト2: 締切前の通知（1点買い）")
    print("=" * 60)

    race_info = {
        'venue': '大村',
        'race_number': 8,
        'deadline': '15:45',
        'race_id': 12346
    }

    # 1点買い: 通常のリスト形式
    prediction = {
        'pit_numbers': [1, 2, 3],  # 1点買い
        'confidence': 0.82
    }

    odds_info = {
        'trifecta_odds': 25.8,
    }

    message = format_race_notification(race_info, prediction, odds_info)
    print(message)
    print()


def test_daily_summary_with_pattern_h():
    """朝の通知（パターンH含む）"""
    print("=" * 60)
    print("テスト3: 朝の通知（パターンH含む）")
    print("=" * 60)

    target_races = [
        {
            'venue': '鳴門',
            'race_num': 5,
            'race_time': '14:30',
            'combination': '3点買い: 1-2-3, 1-2-4, 1-2-5',  # パターンH
            'odds': 45.3
        },
        {
            'venue': '大村',
            'race_num': 8,
            'race_time': '15:45',
            'combination': '1-2-3',  # 1点買い
            'odds': 25.8
        },
        {
            'venue': '児島',
            'race_num': 10,
            'race_time': '16:20',
            'combination': '3点買い: 1-3-2, 1-3-4, 1-3-5',  # パターンH
            'odds': 38.2
        },
    ]

    candidate_races = [
        {
            'venue': '津',
            'race_num': 7,
            'race_time': '13:50',
            'combination': '1-2-4',
            'reason': 'オッズ次第で購入'
        }
    ]

    # Discord送信はしない（テストモード）
    # send_daily_summary('2026-01-28', 48, len(target_races), target_races, candidate_races)

    # メッセージだけ生成して表示
    message = f"""**本日の予想生成完了**

日付: 2026-01-28
総レース数: 48レース
購入対象: {len(target_races)}レース
候補: {len(candidate_races)}レース

システムは自動監視を開始しました。
締切10分前に個別通知を送信します。
"""

    message += "\n**【購入対象レース】**\n"
    for race in target_races:
        venue = race.get('venue', '不明')
        race_num = race.get('race_num', 0)
        race_time = race.get('race_time', '??:??')
        combination = race.get('combination', '?-?-?')
        odds = race.get('odds', 0.0)
        message += f"- {venue} {race_num}R ({race_time}): {combination} ({odds:.1f}倍)\n"

    message += "\n**【候補レース（直前情報次第）】**\n"
    for race in candidate_races:
        venue = race.get('venue', '不明')
        race_num = race.get('race_num', 0)
        race_time = race.get('race_time', '??:??')
        combination = race.get('combination', '?-?-?')
        reason = race.get('reason', '条件付き')
        message += f"- {venue} {race_num}R ({race_time}): {combination} - {reason}\n"

    print(message)
    print()


if __name__ == "__main__":
    test_pattern_h_race_notification()
    test_single_bet_race_notification()
    test_daily_summary_with_pattern_h()

    print("=" * 60)
    print("テスト完了")
    print("=" * 60)
    print("\n【確認ポイント】")
    print("1. テスト1で「3点買い」と表示されているか")
    print("2. テスト2で単一の買い目のみ表示されているか")
    print("3. テスト3で「3点買い:」という表記があるか")
