# -*- coding: utf-8 -*-
"""
バックテスト品質保証モジュール

目的: 3連単的中判定ロジックの誤りを防止する
- 的中判定は必ずこのモジュールを通す
- 1着のみ判定などの誤ったロジックを検出してエラーにする

使用方法:
    from src.betting.backtest_validator import TrifectaValidator

    validator = TrifectaValidator()

    # 的中判定
    is_hit = validator.check_trifecta_hit(
        predicted_combo="1-2-3",
        actual_combo="1-2-3"
    )

    # 払戻金計算
    payout = validator.calculate_payout(
        bet_amount=100,
        odds=35.5
    )
"""

from typing import Tuple, Optional
from dataclasses import dataclass


@dataclass
class TrifectaResult:
    """3連単判定結果"""
    is_hit: bool
    predicted_combo: str  # "1-2-3" 形式
    actual_combo: str     # "1-2-3" 形式
    odds: float
    bet_amount: int
    payout: int           # 的中時の払戻金、不的中なら0


class TrifectaValidator:
    """
    3連単的中判定の品質保証クラス

    このクラスを通さずに的中判定を行うことを禁止する。
    """

    def __init__(self):
        self._validation_count = 0
        self._hit_count = 0

    def check_trifecta_hit(
        self,
        predicted_combo: str,
        actual_combo: str
    ) -> bool:
        """
        3連単の的中判定（完全一致のみ）

        Args:
            predicted_combo: 予測した組み合わせ "1-2-3" 形式
            actual_combo: 実際の結果 "1-2-3" 形式

        Returns:
            bool: 完全一致でTrue、それ以外はFalse

        Raises:
            ValueError: 不正な形式の場合
        """
        # フォーマット検証
        self._validate_combo_format(predicted_combo, "predicted_combo")
        self._validate_combo_format(actual_combo, "actual_combo")

        self._validation_count += 1

        # 完全一致判定
        is_hit = predicted_combo == actual_combo

        if is_hit:
            self._hit_count += 1

        return is_hit

    def check_trifecta_hit_by_ranks(
        self,
        pred_1st: int,
        pred_2nd: int,
        pred_3rd: int,
        actual_1st: int,
        actual_2nd: int,
        actual_3rd: int
    ) -> bool:
        """
        3連単の的中判定（各順位を個別指定）

        Args:
            pred_1st: 予測1着の艇番
            pred_2nd: 予測2着の艇番
            pred_3rd: 予測3着の艇番
            actual_1st: 実際の1着の艇番
            actual_2nd: 実際の2着の艇番
            actual_3rd: 実際の3着の艇番

        Returns:
            bool: 1着・2着・3着すべて一致でTrue
        """
        # 全順位の一致を確認（1着だけではダメ）
        return (
            pred_1st == actual_1st and
            pred_2nd == actual_2nd and
            pred_3rd == actual_3rd
        )

    def calculate_payout(
        self,
        bet_amount: int,
        odds: float,
        is_hit: bool
    ) -> int:
        """
        払戻金計算

        Args:
            bet_amount: 賭け金（円）
            odds: オッズ（倍率）
            is_hit: 的中したかどうか

        Returns:
            int: 払戻金（不的中なら0）
        """
        if not is_hit:
            return 0

        # 100円単位での計算
        return int((bet_amount / 100) * odds * 100)

    def validate_full(
        self,
        predicted_combo: str,
        actual_combo: str,
        odds: float,
        bet_amount: int
    ) -> TrifectaResult:
        """
        完全な3連単検証（的中判定＋払戻計算）

        Args:
            predicted_combo: 予測組み合わせ "1-2-3"
            actual_combo: 実際の結果 "1-2-3"
            odds: オッズ
            bet_amount: 賭け金

        Returns:
            TrifectaResult: 検証結果
        """
        is_hit = self.check_trifecta_hit(predicted_combo, actual_combo)
        payout = self.calculate_payout(bet_amount, odds, is_hit)

        return TrifectaResult(
            is_hit=is_hit,
            predicted_combo=predicted_combo,
            actual_combo=actual_combo,
            odds=odds,
            bet_amount=bet_amount,
            payout=payout
        )

    def _validate_combo_format(self, combo: str, name: str):
        """組み合わせ形式の検証"""
        if not combo:
            raise ValueError(f"{name} is empty")

        parts = combo.split("-")
        if len(parts) != 3:
            raise ValueError(
                f"{name} must be in '1-2-3' format with exactly 3 parts, "
                f"got '{combo}'"
            )

        for i, part in enumerate(parts):
            try:
                num = int(part)
                if num < 1 or num > 6:
                    raise ValueError(
                        f"{name} part {i+1} must be 1-6, got {num}"
                    )
            except ValueError:
                raise ValueError(
                    f"{name} part {i+1} must be a number, got '{part}'"
                )

    def get_stats(self) -> dict:
        """検証統計を取得"""
        hit_rate = (self._hit_count / self._validation_count * 100
                    if self._validation_count > 0 else 0)
        return {
            "validation_count": self._validation_count,
            "hit_count": self._hit_count,
            "hit_rate": f"{hit_rate:.2f}%"
        }

    def reset_stats(self):
        """統計をリセット"""
        self._validation_count = 0
        self._hit_count = 0


# シングルトンインスタンス（推奨）
_default_validator = None

def get_validator() -> TrifectaValidator:
    """デフォルトのバリデータを取得"""
    global _default_validator
    if _default_validator is None:
        _default_validator = TrifectaValidator()
    return _default_validator


# 便利関数
def is_trifecta_hit(predicted: str, actual: str) -> bool:
    """
    3連単的中判定（簡易版）

    使用例:
        from src.betting.backtest_validator import is_trifecta_hit

        if is_trifecta_hit("1-2-3", "1-2-3"):
            print("的中！")
    """
    return get_validator().check_trifecta_hit(predicted, actual)


def calculate_trifecta_payout(bet_amount: int, odds: float, is_hit: bool) -> int:
    """払戻金計算（簡易版）"""
    return get_validator().calculate_payout(bet_amount, odds, is_hit)


# テスト用
if __name__ == "__main__":
    validator = TrifectaValidator()

    # 正常ケース：完全一致
    assert validator.check_trifecta_hit("1-2-3", "1-2-3") == True
    assert validator.check_trifecta_hit("3-1-5", "3-1-5") == True

    # 不一致ケース
    assert validator.check_trifecta_hit("1-2-3", "1-2-4") == False  # 3着違い
    assert validator.check_trifecta_hit("1-2-3", "1-3-2") == False  # 2着3着逆
    assert validator.check_trifecta_hit("1-2-3", "2-1-3") == False  # 1着2着逆

    # 重要：1着だけ一致でも不的中
    assert validator.check_trifecta_hit("1-2-3", "1-4-5") == False

    # 払戻金計算
    assert validator.calculate_payout(100, 35.5, True) == 3550
    assert validator.calculate_payout(300, 50.0, True) == 15000
    assert validator.calculate_payout(100, 35.5, False) == 0

    print("All tests passed!")
    print(f"Stats: {validator.get_stats()}")
