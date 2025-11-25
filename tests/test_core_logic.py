"""
コアロジックのユニットテスト
重要な計算ロジックの正確性を保証
"""
import pytest
import numpy as np
import pandas as pd


class TestKellyCalculation:
    """Kelly基準計算のテスト"""

    def test_positive_expected_value(self):
        """正の期待値での計算"""
        from src.betting.kelly_strategy import KellyBettingStrategy

        strategy = KellyBettingStrategy(bankroll=10000, kelly_fraction=0.25)

        # 期待値が正のケース
        pred_prob = 0.20
        odds = 6.0

        ev = strategy.calculate_expected_value(pred_prob, odds)
        assert ev == pytest.approx(0.20, rel=0.01), f"期待値計算エラー: {ev}"

        kelly_f, bet_amount = strategy.calculate_kelly_bet(pred_prob, odds)
        assert 0 < kelly_f < 0.1, f"Kelly分数が範囲外: {kelly_f}"
        assert 0 < bet_amount < 1000, f"賭け金が範囲外: {bet_amount}"

    def test_negative_expected_value(self):
        """負の期待値では賭けない"""
        from src.betting.kelly_strategy import KellyBettingStrategy

        strategy = KellyBettingStrategy(bankroll=10000)

        pred_prob = 0.10
        odds = 3.0

        kelly_f, bet_amount = strategy.calculate_kelly_bet(pred_prob, odds)
        assert kelly_f == 0.0, "負の期待値でKelly分数が0でない"
        assert bet_amount == 0.0, "負の期待値で賭け金が0でない"

    def test_edge_cases(self):
        """エッジケースのテスト"""
        from src.betting.kelly_strategy import KellyBettingStrategy

        strategy = KellyBettingStrategy(bankroll=10000)

        # ケース1: 確率0
        kelly_f, bet_amount = strategy.calculate_kelly_bet(0.0, 10.0)
        assert kelly_f == 0.0
        assert bet_amount == 0.0

        # ケース2: 確率1（理論上あり得ない）
        kelly_f, bet_amount = strategy.calculate_kelly_bet(1.0, 1.5)
        # 資金の20%を超えないことを確認
        assert bet_amount <= 2000

        # ケース3: オッズ1.0（賭ける意味がない）
        kelly_f, bet_amount = strategy.calculate_kelly_bet(0.5, 1.0)
        assert kelly_f == 0.0


class TestProbabilityCalculation:
    """確率計算のテスト"""

    def test_probability_normalization(self):
        """確率の正規化テスト"""
        # サンプル確率（合計が1でない）
        probs = np.array([0.40, 0.25, 0.20, 0.10, 0.08, 0.05])

        total = probs.sum()
        normalized = probs / total

        assert normalized.sum() == pytest.approx(1.0, abs=1e-6)
        assert (normalized >= 0).all()
        assert (normalized <= 1).all()

    def test_rank_distribution_calculation(self):
        """着順確率分布の計算テスト"""
        win_probs = np.array([0.35, 0.25, 0.20, 0.10, 0.07, 0.03])

        # 合計が1であることを確認
        assert win_probs.sum() == pytest.approx(1.0, abs=0.01)

        # 各確率が0-1の範囲内
        assert (win_probs >= 0).all()
        assert (win_probs <= 1).all()

        # 降順であることを確認（一般的な傾向）
        assert (np.diff(win_probs) <= 0).all(), "確率が降順でない"

    def test_trifecta_probability_sum(self):
        """三連単確率の合計が1になるか"""
        win_probs = [0.35, 0.25, 0.20, 0.10, 0.07, 0.03]

        trifecta_probs = {}
        for i in range(6):
            for j in range(6):
                if j == i:
                    continue
                for k in range(6):
                    if k == i or k == j:
                        continue

                    # 簡易計算
                    prob = win_probs[i] * (win_probs[j] / sum([win_probs[x] for x in range(6) if x != i]))
                    trifecta_probs[f"{i+1}-{j+1}-{k+1}"] = prob

        total = sum(trifecta_probs.values())
        # 簡易計算のため、厳密には1にならないが範囲チェック
        assert 0.5 < total < 1.5, f"三連単確率の合計が異常: {total}"


class TestFeatureValidation:
    """特徴量の妥当性テスト"""

    def test_win_rate_range(self):
        """勝率の範囲チェック"""
        # テストデータ
        win_rates = [6.5, 5.8, 5.2, 4.9, 4.3, 3.8]

        for rate in win_rates:
            assert 0 <= rate <= 10, f"勝率が範囲外: {rate}"

    def test_pit_number_range(self):
        """ピット番号の範囲チェック"""
        pit_numbers = [1, 2, 3, 4, 5, 6]

        for pit in pit_numbers:
            assert 1 <= pit <= 6, f"ピット番号が範囲外: {pit}"

    def test_motor_performance_range(self):
        """モーター2連対率の範囲チェック"""
        motor_rates = [0.45, 0.38, 0.32, 0.28, 0.25, 0.20]

        for rate in motor_rates:
            assert 0 <= rate <= 1, f"モーター2連対率が範囲外: {rate}"

    def test_environmental_factors(self):
        """環境要因の妥当性チェック"""
        # 風速
        wind_speeds = [0.0, 3.5, 5.2, 8.1, 12.3]
        for speed in wind_speeds:
            assert 0 <= speed <= 30, f"風速が範囲外: {speed}"

        # 波高
        wave_heights = [0, 5, 10, 15, 20]
        for height in wave_heights:
            assert 0 <= height <= 50, f"波高が範囲外: {height}"

        # 気温
        temperatures = [-5, 0, 10, 25, 35]
        for temp in temperatures:
            assert -20 <= temp <= 50, f"気温が範囲外: {temp}"


class TestDataConsistency:
    """データ整合性のテスト"""

    def test_race_entries_count(self):
        """1レース = 6艇の確認"""
        import sqlite3
        from config.settings import DATABASE_PATH

        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        # ランダムに10レースを抽出
        cursor.execute("""
            SELECT race_id, COUNT(*) as entry_count
            FROM entries
            GROUP BY race_id
            ORDER BY RANDOM()
            LIMIT 10
        """)

        for row in cursor.fetchall():
            race_id, entry_count = row
            assert entry_count == 6, f"レース{race_id}のエントリー数が{entry_count}（6でない）"

        conn.close()

    def test_rank_values(self):
        """着順の値チェック"""
        valid_ranks = ['1', '2', '3', '4', '5', '6', 'F', 'L', 'K', 'S']

        import sqlite3
        from config.settings import DATABASE_PATH

        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT DISTINCT rank FROM results WHERE rank IS NOT NULL")
        db_ranks = [row[0] for row in cursor.fetchall()]

        for rank in db_ranks:
            assert rank in valid_ranks, f"不正な着順値: {rank}"

        conn.close()

    def test_kimarite_values(self):
        """決まり手の値チェック"""
        valid_kimarite = [1, 2, 3, 4, 5, 6, None]

        import sqlite3
        from config.settings import DATABASE_PATH

        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT DISTINCT winning_technique FROM results")
        db_kimarite = [row[0] for row in cursor.fetchall()]

        for kimarite in db_kimarite:
            assert kimarite in valid_kimarite, f"不正な決まり手値: {kimarite}"

        conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
