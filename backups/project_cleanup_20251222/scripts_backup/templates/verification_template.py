#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
検証スクリプトテンプレート
========================

作成日: YYYY-MM-DD
目的: [検証の目的]

検証対象: [全レース / 該当レースのみ]
ベースライン定義: [何と比較しているか]
本番実装との整合性: [一致 / 不一致（詳細）]

必須確認事項:
- [ ] 本番実装のコードを参照したか
- [ ] 測定ロジックは本番実装と同一か
- [ ] 検証対象（全レース vs 該当のみ）は明示されているか
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
# from src.analysis.scorers.pattern_scorer import PatternScorer
# from src.database.data_manager import DataManager


class VerificationConfig:
    """検証設定"""

    # 必須: 検証対象を明示
    TARGET_SCOPE = "全レース"  # "全レース" or "該当レースのみ"

    # 必須: ベースライン定義
    BASELINE_DEFINITION = "パターン適用なしでの1着予測精度"

    # 必須: 本番実装との整合性
    MATCHES_PRODUCTION = True
    PRODUCTION_DIFFERENCE = ""  # 不一致の場合は詳細を記載

    # データ設定
    DB_PATH = "data/boatrace.db"
    DATA_YEAR = 2024

    # 検証名
    VERIFICATION_NAME = "新規検証"


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


def load_data(db_path: str, year: int) -> List[Dict]:
    """
    データ読み込み

    Args:
        db_path: データベースパス
        year: 対象年

    Returns:
        レースデータのリスト
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # クエリ例（実際のクエリは検証内容に応じて変更）
    query = """
    SELECT
        r.id as race_id,
        rp.pit_number,
        rp.total_score,
        res.rank as actual_rank
    FROM races r
    INNER JOIN race_predictions rp ON r.id = rp.race_id
    LEFT JOIN results res ON res.race_id = r.id AND res.pit_number = rp.pit_number
    WHERE r.race_date >= ? AND r.race_date < ?
        AND rp.prediction_type = 'before'
        AND res.is_invalid = 0
        AND res.rank IS NOT NULL
    ORDER BY r.id, rp.pit_number
    """

    start_date = f"{year}-01-01"
    end_date = f"{year + 1}-01-01"

    cursor.execute(query, (start_date, end_date))
    rows = cursor.fetchall()
    conn.close()

    # レースごとにグループ化（実装例）
    races = []
    current_race = []
    current_race_id = None

    for row in rows:
        race_id = row[0]

        if current_race_id != race_id:
            if current_race:
                races.append(current_race)
            current_race = []
            current_race_id = race_id

        current_race.append({
            'race_id': row[0],
            'pit_number': row[1],
            'total_score': row[2],
            'actual_rank': row[3],
        })

    if current_race:
        races.append(current_race)

    return races


def verify_baseline(races: List[List[Dict]]) -> Dict:
    """
    ベースライン検証

    Args:
        races: レースデータ

    Returns:
        検証結果
    """
    total = 0
    correct = 0

    for race_data in races:
        if len(race_data) < 6:
            continue

        # 最高スコアの艇を予測
        pred_pit = max(race_data, key=lambda x: x['total_score'])['pit_number']

        # 実際の1着を取得
        actual_1st = [d for d in race_data if d['actual_rank'] == 1]
        if not actual_1st:
            continue

        total += 1
        if pred_pit == actual_1st[0]['pit_number']:
            correct += 1

    return {
        'total': total,
        'correct': correct,
        'accuracy': correct / total if total > 0 else 0.0
    }


def verify_with_production_logic(races: List[List[Dict]]) -> Dict:
    """
    本番実装ロジックを使用した検証

    Args:
        races: レースデータ

    Returns:
        検証結果
    """
    # ===================================================
    # ここで本番実装のコードを使用する
    # ===================================================
    # 例:
    # scorer = PatternScorer()
    # total = 0
    # correct = 0
    #
    # for race_data in races:
    #     predictions = scorer.apply_pattern_bonus(race_data, race_id)
    #     pred_pit = predictions[0]['pit_number']
    #     actual_1st_pit = ...
    #
    #     total += 1
    #     if pred_pit == actual_1st_pit:
    #         correct += 1
    #
    # return {
    #     'total': total,
    #     'correct': correct,
    #     'accuracy': correct / total if total > 0 else 0.0
    # }

    # テンプレートではベースラインと同じ結果を返す（実装時に修正）
    return verify_baseline(races)


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
    races = load_data(VerificationConfig.DB_PATH, VerificationConfig.DATA_YEAR)
    print(f"   総レース数: {len(races)}")
    print()

    # ベースライン検証
    print("[BASELINE] ベースライン測定中...")
    baseline_result = verify_baseline(races)
    result.baseline_accuracy = baseline_result['accuracy']
    result.sample_size = baseline_result['total']
    print(f"   ベースライン精度: {result.baseline_accuracy:.2%}")
    print()

    # 本番実装ロジックでの検証
    print("[TEST] 本番実装ロジックで検証中...")
    test_result = verify_with_production_logic(races)
    result.test_accuracy = test_result['accuracy']
    print(f"   検証精度: {result.test_accuracy:.2%}")
    print()

    # 差分計算
    result.calculate_diff()

    # 結果出力
    result.print_summary()


if __name__ == "__main__":
    main()
