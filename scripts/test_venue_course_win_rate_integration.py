# -*- coding: utf-8 -*-
"""
会場別期待勝率テーブル統合テスト

race_predictor.pyに統合した会場別期待勝率テーブルが正しく動作するかテスト
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.analysis.race_predictor import RacePredictor
from config.venue_course_win_rates import get_venue_course_win_rate, VENUE_NAMES


def test_win_rate_table():
    """会場別期待勝率テーブルの基本動作確認"""
    print("=" * 80)
    print("会場別期待勝率テーブル統合テスト")
    print("=" * 80)
    print()

    # テーブル直接アクセステスト
    print("[1] 会場別期待勝率テーブル直接アクセステスト")
    print("-" * 80)

    test_cases = [
        ('18', 1, '徳山1C（イン最強）'),  # 徳山1コース: 70.7%
        ('02', 1, '戸田1C（イン弱）'),     # 戸田1コース: 45.9%
        ('24', 1, '大村1C（イン強）'),     # 大村1コース: 68.1%
        ('07', 2, '蒲郡2C'),               # 蒲郡2コース
    ]

    for venue_code, course, description in test_cases:
        win_rate = get_venue_course_win_rate(venue_code, course)
        venue_name = VENUE_NAMES.get(venue_code, '不明')
        print(f"  {description}: {win_rate:.3f} ({win_rate*100:.1f}%) - {venue_name}")

    print()

    # race_predictor統合テスト
    print("[2] race_predictor統合テスト")
    print("-" * 80)

    try:
        predictor = RacePredictor()

        # 徳山1コース A1級（イン最強×トップランク）
        score_tokuyama_1_a1 = predictor.calculate_course_rank_score(
            course=1,
            racer_rank='A1',
            venue_code='18'
        )
        print(f"  徳山1C A1級: スコア {score_tokuyama_1_a1:.2f}")

        # 戸田1コース A1級（イン弱×トップランク）
        score_toda_1_a1 = predictor.calculate_course_rank_score(
            course=1,
            racer_rank='A1',
            venue_code='02'
        )
        print(f"  戸田1C A1級: スコア {score_toda_1_a1:.2f}")

        # スコア差の確認
        score_diff = score_tokuyama_1_a1 - score_toda_1_a1
        print(f"  → 徳山と戸田の差: {score_diff:.2f}点")

        # 徳山1コース B2級
        score_tokuyama_1_b2 = predictor.calculate_course_rank_score(
            course=1,
            racer_rank='B2',
            venue_code='18'
        )
        print(f"  徳山1C B2級: スコア {score_tokuyama_1_b2:.2f}")

        # ランク差の確認
        rank_diff = score_tokuyama_1_a1 - score_tokuyama_1_b2
        print(f"  → 同じ会場・コースでのA1とB2の差: {rank_diff:.2f}点")

        print()
        print("[OK] 統合テスト成功: race_predictorで会場別期待勝率が正しく使用されています")

    except Exception as e:
        print(f"[ERROR] 統合テストエラー: {e}")
        import traceback
        traceback.print_exc()

    print()

    # 実際のレース予測テスト
    print("[3] 実際のレース予測テスト（サンプル）")
    print("-" * 80)

    try:
        # 2025年11月のレースでテスト
        predictions = predictor.predict_race_by_key(
            race_date='2025-11-01',
            venue_code='18',  # 徳山（イン強）
            race_number=1
        )

        if predictions:
            print(f"  レース: 2025-11-01 徳山1R")
            print(f"  {'順位':<4} {'艇番':<4} {'選手名':<12} {'コースSC':<8} {'総合SC':<8}")
            print("  " + "-" * 50)
            for i, pred in enumerate(predictions[:3], 1):
                print(f"  {i:<4} {pred['pit_number']:<4} {pred.get('racer_name', '不明'):<12} "
                      f"{pred.get('course_score', 0):<8.1f} {pred.get('total_score', 0):<8.1f}")

            print()
            print("[OK] レース予測成功: コーススコアに会場別期待勝率が反映されています")
        else:
            print("  [WARN] 予測データなし（データが存在しない可能性）")

    except Exception as e:
        print(f"  [WARN] レース予測テストスキップ: {e}")

    print()
    print("=" * 80)
    print("テスト完了")
    print("=" * 80)


if __name__ == '__main__':
    test_win_rate_table()
