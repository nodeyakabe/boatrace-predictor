#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
オッズ校正効果の検証スクリプト
========================

作成日: 2025-12-18
目的: オッズ校正による1着予測精度改善効果の測定

検証対象: 全レース
ベースライン定義: オッズ校正なしでの1着予測精度
本番実装との整合性: 一致（本番RacePredictorを直接使用）

必須確認事項:
- [x] 本番実装のコードを参照したか → RacePredictor.predict_race() を使用
- [x] 測定ロジックは本番実装と同一か → 同一
- [x] 検証対象（全レース vs 該当のみ）は明示されているか → 全レース
"""

import sys
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# ===================================================
# 本番実装をインポート（独自ロジックを書かない）
# ===================================================
from src.analysis.race_predictor import RacePredictor
from config.feature_flags import set_feature_flag


class VerificationConfig:
    """検証設定"""

    # 必須: 検証対象を明示
    TARGET_SCOPE = "全レース"  # "全レース" or "該当レースのみ"

    # 必須: ベースライン定義
    BASELINE_DEFINITION = "オッズ校正なしでの1着予測精度（本番RacePredictor使用）"

    # 必須: 本番実装との整合性
    MATCHES_PRODUCTION = True
    PRODUCTION_DIFFERENCE = ""  # 不一致の場合は詳細を記載

    # データ設定
    DB_PATH = "data/boatrace_backup_20251212_145413.db"
    DATA_YEAR = 2024

    # 検証名
    VERIFICATION_NAME = "オッズ校正効果検証"


class VerificationResult:
    """検証結果"""

    def __init__(self):
        self.baseline_accuracy = 0.0
        self.test_accuracy = 0.0
        self.sample_size = 0
        self.diff_pt = 0.0
        self.details = {}

    def calculate_diff(self):
        """差分計算"""
        self.diff_pt = (self.test_accuracy - self.baseline_accuracy) * 100

    def print_header(self):
        """ヘッダー出力"""
        print("=" * 80)
        print(f"検証名: {VerificationConfig.VERIFICATION_NAME}")
        print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        print()

    def print_config(self):
        """検証設定出力"""
        print("[CONFIG] 検証設定")
        print("-" * 80)
        print(f"検証対象: {VerificationConfig.TARGET_SCOPE}")
        print(f"ベースライン定義: {VerificationConfig.BASELINE_DEFINITION}")
        print(f"本番実装との整合性: {'一致' if VerificationConfig.MATCHES_PRODUCTION else '不一致'}")
        if not VerificationConfig.MATCHES_PRODUCTION:
            print(f"  差異詳細: {VerificationConfig.PRODUCTION_DIFFERENCE}")
        print(f"データ年: {VerificationConfig.DATA_YEAR}")
        print()

    def print_summary(self):
        """結果サマリー出力"""
        print("[RESULT] 検証結果サマリー")
        print("-" * 80)
        print(f"サンプル数: {self.sample_size:,}件")
        print(f"ベースライン精度: {self.baseline_accuracy:.2%}")
        print(f"検証精度: {self.test_accuracy:.2%}")
        print(f"差分: {self.diff_pt:+.2f}pt")
        print()

        # 判定
        if self.diff_pt > 1.0:
            print("[GOOD] 大幅改善（+1.0pt以上）")
        elif self.diff_pt > 0.5:
            print("[OK] わずかな改善（+0.5pt以上）")
        elif self.diff_pt > -0.5:
            print("[NEUTRAL] 効果は微小（±0.5pt以内）")
        elif self.diff_pt > -1.0:
            print("[WARN] わずかな悪化（-0.5pt以上）")
        else:
            print("[NG] 大幅悪化（-1.0pt以上）")

        print("=" * 80)


def load_race_ids(db_path: str, year: int) -> List[int]:
    """
    検証対象のレースIDを取得

    Args:
        db_path: データベースパス
        year: 対象年

    Returns:
        レースIDのリスト
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # オッズデータがあり、結果データもあるレースのみを対象
    query = """
    SELECT DISTINCT r.id
    FROM races r
    INNER JOIN results res ON res.race_id = r.id
    INNER JOIN trifecta_odds odds ON odds.race_id = r.id
    WHERE r.race_date >= ? AND r.race_date < ?
        AND res.is_invalid = 0
        AND res.rank = 1
    ORDER BY r.id
    """

    start_date = f"{year}-01-01"
    end_date = f"{year + 1}-01-01"

    cursor.execute(query, (start_date, end_date))
    race_ids = [row[0] for row in cursor.fetchall()]
    conn.close()

    return race_ids


def verify_baseline(predictor: RacePredictor, race_ids: List[int], db_path: str) -> Dict:
    """
    ベースライン検証（オッズ校正なし）

    Args:
        predictor: 予測器
        race_ids: レースIDリスト
        db_path: データベースパス

    Returns:
        検証結果
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    total = 0
    correct = 0

    for race_id in race_ids:
        try:
            # 本番実装を使用
            predictions = predictor.predict_race(race_id, use_beforeinfo=True)

            if not predictions or len(predictions) == 0:
                continue

            # 最高スコアの艇を予測
            pred_pit = predictions[0]['pit_number']

            # 実際の1着を取得
            cursor.execute("""
                SELECT pit_number FROM results
                WHERE race_id = ? AND rank = 1 AND is_invalid = 0
            """, (race_id,))
            actual_row = cursor.fetchone()

            if not actual_row:
                continue

            actual_pit = actual_row[0]

            total += 1
            if pred_pit == actual_pit:
                correct += 1

        except Exception as e:
            # エラーは無視してスキップ
            continue

    conn.close()

    return {
        'total': total,
        'correct': correct,
        'accuracy': correct / total if total > 0 else 0.0
    }


def verify_with_odds_calibration(predictor: RacePredictor, race_ids: List[int], db_path: str) -> Dict:
    """
    オッズ校正適用時の検証

    Args:
        predictor: 予測器
        race_ids: レースIDリスト
        db_path: データベースパス

    Returns:
        検証結果
    """
    # オッズ校正を有効化
    set_feature_flag('odds_calibration', True)

    # 新しいpredictor作成（フラグが反映される）
    calibrated_predictor = RacePredictor(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    total = 0
    correct = 0

    for race_id in race_ids:
        try:
            # 本番実装を使用（オッズ校正あり）
            predictions = calibrated_predictor.predict_race(race_id, use_beforeinfo=True)

            if not predictions or len(predictions) == 0:
                continue

            # 最高スコアの艇を予測
            pred_pit = predictions[0]['pit_number']

            # 実際の1着を取得
            cursor.execute("""
                SELECT pit_number FROM results
                WHERE race_id = ? AND rank = 1 AND is_invalid = 0
            """, (race_id,))
            actual_row = cursor.fetchone()

            if not actual_row:
                continue

            actual_pit = actual_row[0]

            total += 1
            if pred_pit == actual_pit:
                correct += 1

        except Exception as e:
            # エラーは無視してスキップ
            continue

    conn.close()

    # フラグを元に戻す
    set_feature_flag('odds_calibration', False)

    return {
        'total': total,
        'correct': correct,
        'accuracy': correct / total if total > 0 else 0.0
    }


def main():
    """メイン処理"""

    # 結果オブジェクト作成
    result = VerificationResult()

    # ヘッダー出力
    result.print_header()

    # 検証設定出力
    result.print_config()

    # データ読み込み
    print("[DATA] データ読み込み中...")
    race_ids = load_race_ids(VerificationConfig.DB_PATH, VerificationConfig.DATA_YEAR)
    print(f"   総レース数: {len(race_ids)}")
    print()

    # 予測器作成
    print("[INIT] 予測器初期化中...")
    predictor = RacePredictor(VerificationConfig.DB_PATH)
    print()

    # ベースライン検証
    print("[BASELINE] ベースライン測定中（オッズ校正なし）...")
    baseline_result = verify_baseline(predictor, race_ids, VerificationConfig.DB_PATH)
    result.baseline_accuracy = baseline_result['accuracy']
    result.sample_size = baseline_result['total']
    print(f"   ベースライン精度: {result.baseline_accuracy:.2%} ({baseline_result['correct']}/{baseline_result['total']})")
    print()

    # オッズ校正適用時の検証
    print("[TEST] オッズ校正適用時の測定中...")
    test_result = verify_with_odds_calibration(predictor, race_ids, VerificationConfig.DB_PATH)
    result.test_accuracy = test_result['accuracy']
    print(f"   検証精度: {result.test_accuracy:.2%} ({test_result['correct']}/{test_result['total']})")
    print()

    # 差分計算
    result.calculate_diff()

    # 結果出力
    result.print_summary()


if __name__ == "__main__":
    main()
