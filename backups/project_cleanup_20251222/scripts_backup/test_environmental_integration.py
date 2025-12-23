"""
環境要因減点システム統合テスト

ConfidenceBFilterとEnvironmentalPenaltySystemの統合をテスト
"""

import sys
import os
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'src'))

from analysis.confidence_filter import ConfidenceBFilter
from datetime import datetime


def print_section(title):
    """セクションヘッダーを表示"""
    print(f"\n{'=' * 80}")
    print(f" {title}")
    print(f"{'=' * 80}\n")


def test_high_risk_scenario():
    """高リスクシナリオテスト: 戸田×午前×悪天候"""
    print_section("テスト1: 高リスクシナリオ（戸田×午前×雨×北東風）")

    filter_system = ConfidenceBFilter(use_environmental_penalty=True)

    result = filter_system.should_accept_bet(
        venue_code=2,  # 戸田
        race_date='2025-01-15',
        confidence_score=110.0,  # 元スコア高い
        race_time='10:30',  # 午前
        wind_direction='北東',
        wind_speed=5.0,  # 強風
        wave_height=8.0,  # 中波
        weather='雨'
    )

    print(f"会場: 戸田（02）")
    print(f"時間帯: 10:30（午前）")
    print(f"天候: 雨")
    print(f"風: 北東 5.0m/s")
    print(f"波: 8.0cm")
    print(f"元スコア: 110.0")
    print(f"\n【結果】")
    print(f"受け入れ: {result['accept']}")
    print(f"環境減点: {result['environmental_penalty']}pt")
    print(f"調整後スコア: {result['adjusted_score']:.1f}")
    print(f"調整後信頼度: {result['adjusted_confidence']}")
    print(f"理由: {result['reason']}")

    if result['applied_env_rules']:
        print(f"\n適用された減点ルール:")
        for rule in result['applied_env_rules']:
            print(f"  - {rule['description']}: {rule['penalty']}pt")

    return result


def test_low_risk_scenario():
    """低リスクシナリオテスト: 優良会場×好条件"""
    print_section("テスト2: 低リスクシナリオ（桐生×午後×晴れ×微風）")

    filter_system = ConfidenceBFilter(use_environmental_penalty=True)

    result = filter_system.should_accept_bet(
        venue_code=1,  # 桐生
        race_date='2025-01-15',
        confidence_score=105.0,
        race_time='14:00',  # 午後
        wind_direction='南',
        wind_speed=2.0,  # 微風
        wave_height=1.0,  # 穏やか
        weather='晴れ'
    )

    print(f"会場: 桐生（01）")
    print(f"時間帯: 14:00（午後）")
    print(f"天候: 晴れ")
    print(f"風: 南 2.0m/s")
    print(f"波: 1.0cm")
    print(f"元スコア: 105.0")
    print(f"\n【結果】")
    print(f"受け入れ: {result['accept']}")
    print(f"環境減点: {result['environmental_penalty']}pt")
    print(f"調整後スコア: {result['adjusted_score']:.1f}")
    print(f"調整後信頼度: {result['adjusted_confidence']}")
    print(f"理由: {result['reason']}")

    if result['applied_env_rules']:
        print(f"\n適用された減点ルール:")
        for rule in result['applied_env_rules']:
            print(f"  - {rule['description']}: {rule['penalty']}pt")

    return result


def test_borderline_scenario():
    """ボーダーラインシナリオテスト: 調整後スコア約80付近"""
    print_section("テスト3: ボーダーラインシナリオ（江戸川×夕方）")

    filter_system = ConfidenceBFilter(use_environmental_penalty=True)

    result = filter_system.should_accept_bet(
        venue_code=3,  # 江戸川
        race_date='2025-01-15',
        confidence_score=100.0,
        race_time='16:30',  # 夕方
        wind_direction='東',
        wind_speed=7.0,  # 暴風
        wave_height=6.0,  # 小波
        weather='曇り'
    )

    print(f"会場: 江戸川（03）")
    print(f"時間帯: 16:30（夕方）")
    print(f"天候: 曇り")
    print(f"風: 東 7.0m/s")
    print(f"波: 6.0cm")
    print(f"元スコア: 100.0")
    print(f"\n【結果】")
    print(f"受け入れ: {result['accept']}")
    print(f"環境減点: {result['environmental_penalty']}pt")
    print(f"調整後スコア: {result['adjusted_score']:.1f}")
    print(f"調整後信頼度: {result['adjusted_confidence']}")
    print(f"理由: {result['reason']}")

    if result['applied_env_rules']:
        print(f"\n適用された減点ルール:")
        for rule in result['applied_env_rules']:
            print(f"  - {rule['description']}: {rule['penalty']}pt")

    return result


def test_extreme_penalty_scenario():
    """極端な減点シナリオテスト: 常滑×北北西×微風（減点13pt）"""
    print_section("テスト4: 極端減点シナリオ（常滑×北北西×微風）")

    filter_system = ConfidenceBFilter(use_environmental_penalty=True)

    result = filter_system.should_accept_bet(
        venue_code=8,  # 常滑
        race_date='2025-01-15',
        confidence_score=105.0,
        race_time='13:00',
        wind_direction='北北西',
        wind_speed=3.0,  # 微風
        wave_height=3.0,
        weather='晴れ'
    )

    print(f"会場: 常滑（08）")
    print(f"時間帯: 13:00")
    print(f"天候: 晴れ")
    print(f"風: 北北西 3.0m/s（微風）")
    print(f"波: 3.0cm")
    print(f"元スコア: 105.0")
    print(f"\n【結果】")
    print(f"受け入れ: {result['accept']}")
    print(f"環境減点: {result['environmental_penalty']}pt")
    print(f"調整後スコア: {result['adjusted_score']:.1f}")
    print(f"調整後信頼度: {result['adjusted_confidence']}")
    print(f"理由: {result['reason']}")

    if result['applied_env_rules']:
        print(f"\n適用された減点ルール:")
        for rule in result['applied_env_rules']:
            print(f"  - {rule['description']}: {rule['penalty']}pt")

    return result


def test_disabled_penalty_system():
    """減点システム無効化テスト"""
    print_section("テスト5: 減点システム無効化（後方互換性確認）")

    filter_system = ConfidenceBFilter(use_environmental_penalty=False)

    result = filter_system.should_accept_bet(
        venue_code=2,  # 戸田（本来は高リスク）
        race_date='2025-01-15',
        confidence_score=110.0,
        race_time='10:30',
        wind_direction='北東',
        wind_speed=5.0,
        wave_height=8.0,
        weather='雨'
    )

    print(f"会場: 戸田（02）- 高リスク会場だが減点システムOFF")
    print(f"元スコア: 110.0")
    print(f"\n【結果】")
    print(f"受け入れ: {result['accept']}")
    print(f"環境減点: {result['environmental_penalty']}pt")
    print(f"調整後スコア: {result['adjusted_score']:.1f}")
    print(f"調整後信頼度: {result['adjusted_confidence']}")
    print(f"理由: {result['reason']}")

    return result


def test_confidence_downgrade():
    """信頼度ダウングレードテスト: B→C→D"""
    print_section("テスト6: 信頼度ダウングレード（B→C→D）")

    filter_system = ConfidenceBFilter(use_environmental_penalty=True)

    scenarios = [
        {'score': 105.0, 'penalty_expected': 0, 'expected_conf': 'B'},
        {'score': 95.0, 'penalty_expected': 10, 'expected_conf': 'C'},
        {'score': 90.0, 'penalty_expected': 15, 'expected_conf': 'D'},
    ]

    for i, scenario in enumerate(scenarios, 1):
        print(f"\nシナリオ {i}: 元スコア {scenario['score']}")

        # 戸田×午前で減点7pt、雨で減点6pt = 合計13pt程度の減点を期待
        result = filter_system.should_accept_bet(
            venue_code=2,  # 戸田
            race_date='2025-01-15',
            confidence_score=scenario['score'],
            race_time='10:30',  # 午前
            wind_direction='北',
            wind_speed=4.0,
            wave_height=5.0,
            weather='雨'
        )

        print(f"  減点: {result['environmental_penalty']}pt")
        print(f"  調整後スコア: {result['adjusted_score']:.1f}")
        print(f"  調整後信頼度: {result['adjusted_confidence']}")
        print(f"  受け入れ: {result['accept']}")


def main():
    """メインテスト実行"""
    print("\n" + "=" * 80)
    print(" 環境要因減点システム 統合テスト")
    print("=" * 80)

    try:
        # 各テストシナリオを実行
        test_high_risk_scenario()
        test_low_risk_scenario()
        test_borderline_scenario()
        test_extreme_penalty_scenario()
        test_disabled_penalty_system()
        test_confidence_downgrade()

        print_section("統合テスト完了")
        print("✓ 全てのテストシナリオが正常に実行されました")
        print("\n【確認ポイント】")
        print("1. 高リスク会場×悪天候で適切に減点されているか")
        print("2. 低リスク会場×好条件で減点が少ない/無いか")
        print("3. ボーダーライン付近で適切に判定されているか")
        print("4. 極端な減点ルールが正しく適用されているか")
        print("5. 減点システムOFFで従来の動作を維持しているか")
        print("6. スコアに応じて信頼度が適切にダウングレードされているか (B→C→D)")

    except Exception as e:
        print(f"\n❌ エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == '__main__':
    exit(main())
