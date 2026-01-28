"""
パターンH（3点買い）のオッズ表示テスト

締切前通知で全買い目のオッズが表示されることを確認
"""

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.automation.notify import format_race_notification


def test_pattern_h_with_all_odds():
    """パターンH: 全買い目のオッズ表示テスト"""
    print("=" * 60)
    print("パターンH: 全買い目のオッズ表示テスト")
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

    # パターンH用のオッズ情報（全買い目を含む）
    odds_info = {
        'trifecta_odds': 45.3,
        'multi_bets': [
            {'combination': '1-2-3', 'odds': 45.3},
            {'combination': '1-2-4', 'odds': 52.1},
            {'combination': '1-2-5', 'odds': 38.7},
        ]
    }

    message = format_race_notification(race_info, prediction, odds_info)
    print(message)
    print()

    # 確認ポイント
    print("【確認ポイント】")
    print("1. 3点買いと表示されているか")
    print("2. 全買い目（1-2-3, 1-2-4, 1-2-5）のオッズが表示されているか")
    print("3. オッズが個別に表示されているか（45.3倍, 52.1倍, 38.7倍）")


def test_single_bet_odds():
    """1点買い: オッズ表示テスト"""
    print("\n" + "=" * 60)
    print("1点買い: オッズ表示テスト")
    print("=" * 60)

    race_info = {
        'venue': '大村',
        'race_number': 8,
        'deadline': '15:45',
        'race_id': 12346
    }

    # 1点買い: リストのリスト形式（1要素のみ）
    prediction = {
        'pit_numbers': [[1, 2, 3]],  # 1点買い
        'confidence': 0.82
    }

    # 1点買い用のオッズ情報
    odds_info = {
        'trifecta_odds': 25.8,
    }

    message = format_race_notification(race_info, prediction, odds_info)
    print(message)
    print()

    # 確認ポイント
    print("【確認ポイント】")
    print("1. 1点買い（1-2-3）と表示されているか")
    print("2. オッズが「3連単: 25.8倍」と表示されているか")


if __name__ == "__main__":
    test_pattern_h_with_all_odds()
    test_single_bet_odds()

    print("\n" + "=" * 60)
    print("テスト完了")
    print("=" * 60)
