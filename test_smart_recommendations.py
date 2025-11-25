"""
スマート予想レコメンド機能のテストスクリプト
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.betting.bet_generator import BetGenerator, BetTicket
from src.betting.race_scorer import RaceScorer, RaceScore
from datetime import datetime
import numpy as np

def test_bet_generator():
    """買い目生成のテスト"""
    print("=== 買い目生成テスト ===\n")

    generator = BetGenerator()

    # テスト用の予測データ
    predictions = {
        "1": 0.35,  # 1号艇 35%
        "2": 0.25,  # 2号艇 25%
        "3": 0.18,  # 3号艇 18%
        "4": 0.12,  # 4号艇 12%
        "5": 0.07,  # 5号艇 7%
        "6": 0.03   # 6号艇 3%
    }

    # テスト用のオッズデータ
    odds_data = {
        "単勝": {
            "1": 2.1,
            "2": 3.5,
            "3": 5.8,
            "4": 9.2,
            "5": 15.3,
            "6": 38.5
        }
    }

    # 買い目生成
    bets = generator.generate_bets(predictions, odds_data)

    print(f"生成された買い目数: {len(bets)}\n")

    for i, bet in enumerate(bets[:5], 1):
        print(f"{i}. {bet.bet_type} {bet.format_combination()}")
        print(f"   信頼度: {bet.confidence:.1%}")
        print(f"   期待値: {bet.expected_value:.2f}")
        print(f"   推定オッズ: {bet.estimated_odds:.1f}倍")
        print(f"   推奨度: {'★' * bet.recommendation_level}")
        print()

def test_race_scorer():
    """レーススコアリングのテスト"""
    print("=== レーススコアリングテスト ===\n")

    scorer = RaceScorer()

    # テスト用のデータ
    race_id = "2024-11-14_桐生_1R"
    predictions = {
        "1": 0.42,  # 1号艇 42%（本命）
        "2": 0.28,  # 2号艇 28%
        "3": 0.15,  # 3号艇 15%
        "4": 0.08,  # 4号艇 8%
        "5": 0.05,  # 5号艇 5%
        "6": 0.02   # 6号艇 2%
    }

    feature_importance = {
        "勝率": 0.25,
        "コース別1着率": 0.20,
        "モーター勝率": 0.15,
        "平均ST": 0.10,
        "連対率": 0.10,
        "3連対率": 0.08,
        "前走成績": 0.07,
        "天候": 0.05
    }

    odds_data = {
        "単勝": {
            "1": 1.8,
            "2": 3.2,
            "3": 7.5,
            "4": 12.0,
            "5": 22.0,
            "6": 55.0
        }
    }

    # スコアリング実行
    race_score = scorer.score_race(
        race_id=race_id,
        predictions=predictions,
        feature_importance=feature_importance,
        odds_data=odds_data,
        historical_accuracy=0.68
    )

    print(f"レースID: {race_score.race_id}")
    print(f"会場: {race_score.venue}")
    print(f"レース番号: {race_score.race_no}R")
    print()
    print(f"本命: {race_score.favorite_boat}号艇（勝率 {race_score.favorite_prob:.1%}）")
    print()
    print(f"的中率スコア: {race_score.accuracy_score:.1f}/100")
    print(f"期待値スコア: {race_score.value_score:.1f}/100")
    print(f"安定性スコア: {race_score.stability_score:.1f}/100")
    print()
    print(f"オッズ乖離度: {race_score.odds_discrepancy:.2f}")
    print(f"期待リターン: {race_score.expected_return:.2f}倍")
    print()
    print("予測理由:")
    for reason in race_score.prediction_reasons[:3]:
        print(f"  - {reason}")

def test_race_ranking():
    """レースランキングのテスト"""
    print("\n=== レースランキングテスト ===\n")

    scorer = RaceScorer()
    race_scores = []

    # 複数のレースをシミュレート
    test_races = [
        {
            "race_id": "2024-11-14_桐生_1R",
            "predictions": {"1": 0.45, "2": 0.25, "3": 0.15, "4": 0.08, "5": 0.05, "6": 0.02},
            "odds": {"単勝": {"1": 1.9, "2": 3.8, "3": 8.2, "4": 15.0, "5": 25.0, "6": 60.0}}
        },
        {
            "race_id": "2024-11-14_戸田_3R",
            "predictions": {"1": 0.28, "2": 0.22, "3": 0.20, "4": 0.15, "5": 0.10, "6": 0.05},
            "odds": {"単勝": {"1": 2.8, "2": 4.5, "3": 5.0, "4": 8.0, "5": 12.0, "6": 20.0}}
        },
        {
            "race_id": "2024-11-14_浜名湖_12R",
            "predictions": {"1": 0.65, "2": 0.18, "3": 0.08, "4": 0.05, "5": 0.03, "6": 0.01},
            "odds": {"単勝": {"1": 1.3, "2": 6.0, "3": 13.0, "4": 22.0, "5": 40.0, "6": 100.0}}
        },
        {
            "race_id": "2024-11-14_常滑_8R",
            "predictions": {"3": 0.35, "1": 0.30, "2": 0.15, "4": 0.10, "5": 0.07, "6": 0.03},
            "odds": {"単勝": {"3": 7.2, "1": 3.5, "2": 8.0, "4": 12.0, "5": 18.0, "6": 45.0}}
        }
    ]

    # 各レースをスコアリング
    for race_data in test_races:
        feature_importance = {
            "勝率": np.random.uniform(0.15, 0.30),
            "コース別1着率": np.random.uniform(0.10, 0.25),
            "モーター勝率": np.random.uniform(0.05, 0.20),
            "平均ST": np.random.uniform(0.05, 0.15),
            "連対率": np.random.uniform(0.05, 0.15)
        }

        race_score = scorer.score_race(
            race_id=race_data["race_id"],
            predictions=race_data["predictions"],
            feature_importance=feature_importance,
            odds_data=race_data["odds"]
        )
        race_scores.append(race_score)

    # 的中率重視でランキング
    print("【的中率重視ランキング】")
    accuracy_ranked = scorer.rank_races(race_scores, mode="accuracy")
    for i, race in enumerate(accuracy_ranked, 1):
        score = race.accuracy_score * 0.7 + race.stability_score * 0.3
        print(f"{i}位: {race.venue} {race.race_no}R - スコア {score:.1f}")
        print(f"     本命: {race.favorite_boat}号艇（{race.favorite_prob:.1%}）")

    print()

    # 期待値重視でランキング
    print("【期待値重視ランキング】")
    value_ranked = scorer.rank_races(race_scores, mode="value")
    for i, race in enumerate(value_ranked, 1):
        score = race.value_score * 0.6 + race.accuracy_score * 0.4
        print(f"{i}位: {race.venue} {race.race_no}R - スコア {score:.1f}")
        print(f"     期待値: {race.expected_return:.2f}倍")

def test_integration():
    """統合テスト"""
    print("\n=== 統合テスト ===\n")

    generator = BetGenerator()
    scorer = RaceScorer()

    # レースデータ
    race_id = "2024-11-14_蒲郡_12R"
    predictions = {
        "1": 0.52,  # 1号艇が圧倒的本命
        "2": 0.20,
        "3": 0.12,
        "4": 0.08,
        "5": 0.05,
        "6": 0.03
    }

    odds_data = {
        "単勝": {"1": 1.5, "2": 5.0, "3": 9.0, "4": 14.0, "5": 23.0, "6": 45.0},
        "3連単": {
            "1-2-3": 8.5,
            "1-3-2": 12.0,
            "1-2-4": 18.5,
            "1-3-4": 25.0,
            "1-4-2": 35.0,
            "1-4-3": 40.0
        }
    }

    feature_importance = {
        "勝率": 0.30,
        "コース別1着率": 0.25,
        "モーター勝率": 0.20,
        "平均ST": 0.15,
        "連対率": 0.10
    }

    # レーススコアリング
    race_score = scorer.score_race(
        race_id=race_id,
        predictions=predictions,
        feature_importance=feature_importance,
        odds_data=odds_data
    )

    # 推奨情報取得
    recommendation = scorer.get_race_recommendation(race_score, mode="accuracy")

    print(f"【レース情報】 {race_score.venue} {race_score.race_no}R")
    print(f"推奨レベル: {recommendation['level']} {'★' * recommendation['stars']}")
    print(f"総合スコア: {recommendation['score']:.1f}")
    print(f"メッセージ: {recommendation['message']}")
    print()

    # 買い目生成
    bets = generator.generate_bets(predictions, odds_data, max_total_tickets=8)

    print("【推奨買い目】")
    for i, bet in enumerate(bets, 1):
        stars = "★" * bet.recommendation_level
        print(f"{i}. {bet.bet_type:4s} {bet.format_combination():8s} "
              f"信頼度:{bet.confidence:5.1%} "
              f"期待値:{bet.expected_value:4.2f} "
              f"{stars}")

    print()

    # 購入シミュレーション
    budget = 3000  # 3000円の予算
    print(f"【購入シミュレーション】予算: {budget}円")

    top_bets = bets[:5]  # 上位5点を購入
    total_confidence = sum(b.confidence for b in top_bets)

    total_investment = 0
    total_expected_return = 0

    for bet in top_bets:
        amount = int(budget * bet.confidence / total_confidence / 100) * 100
        if amount > 0:
            expected_return = amount * bet.expected_value
            total_investment += amount
            total_expected_return += expected_return
            print(f"  {bet.bet_type} {bet.format_combination()}: {amount}円 → 期待{expected_return:.0f}円")

    print(f"\n投資合計: {total_investment}円")
    print(f"期待リターン: {total_expected_return:.0f}円")
    print(f"期待収支: {total_expected_return - total_investment:+.0f}円")

if __name__ == "__main__":
    print("スマート予想レコメンド機能テスト")
    print("=" * 50)

    # 各機能をテスト
    test_bet_generator()
    print("\n" + "=" * 50)
    test_race_scorer()
    print("\n" + "=" * 50)
    test_race_ranking()
    print("\n" + "=" * 50)
    test_integration()

    print("\n" + "=" * 50)
    print("テスト完了！")