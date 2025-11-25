"""
法則移行・バックテスト統合スクリプト

機能:
1. extracted_rules から venue_rules へ法則を移行
2. バックテストで各法則の有効性を検証
3. 現予想ロジックでの精度テスト
"""

import sqlite3
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Tuple
import numpy as np
from config.settings import DATABASE_PATH


class RuleMigrationAndBacktest:
    """法則移行・バックテスト統合クラス"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or DATABASE_PATH

    def migrate_extracted_to_venue_rules(self, min_confidence: float = 0.3) -> int:
        """
        extracted_rules から venue_rules へ移行

        Args:
            min_confidence: 最小信頼度

        Returns:
            移行した法則数
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 既存データをクリア
        cursor.execute("DELETE FROM venue_rules")

        # extracted_rules から有効な法則を取得
        cursor.execute("""
            SELECT rule_name, condition_json, adjustment, sample_size, confidence
            FROM extracted_rules
            WHERE is_valid = 1 AND confidence >= ?
        """, (min_confidence,))

        migrated_count = 0

        for row in cursor.fetchall():
            rule_name, condition_json, adjustment, sample_size, confidence = row
            condition = json.loads(condition_json)

            # 条件から各フィールドを抽出
            venue_code = condition.get('venue_code')
            pit_number = condition.get('pit_number')

            if pit_number is None:
                continue

            # wind_direction や tide_status がある場合は condition_type に設定
            condition_type = None
            condition_value = None

            if 'wind_direction' in condition:
                condition_type = 'wind'
                condition_value = condition['wind_direction']
            elif 'tide_status' in condition:
                condition_type = 'tide'
                condition_value = condition['tide_status']
            elif 'racer_rank' in condition:
                condition_type = 'rank'
                condition_value = condition['racer_rank']

            # effect_type を決定
            effect_type = 'win_rate_boost' if adjustment > 0 else 'win_rate_penalty'

            # 説明文を生成
            description = f"{rule_name} (n={sample_size}, conf={confidence:.2f})"

            try:
                cursor.execute("""
                    INSERT INTO venue_rules
                    (venue_code, rule_type, condition_type, condition_value,
                     target_pit, effect_type, effect_value, description, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, (
                    venue_code,
                    'extracted',  # rule_type
                    condition_type,
                    condition_value,
                    pit_number,
                    effect_type,
                    adjustment,
                    description
                ))
                migrated_count += 1
            except Exception as e:
                print(f"移行エラー ({rule_name}): {e}")

        conn.commit()
        conn.close()

        print(f"[OK] {migrated_count}件の法則を venue_rules に移行しました")
        return migrated_count

    def get_time_split_dates(self, train_ratio: float = 0.8) -> Tuple[str, str, str]:
        """時系列分割の日付を取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT MIN(race_date), MAX(race_date)
            FROM races
        """)
        min_date, max_date = cursor.fetchone()
        conn.close()

        if not min_date or not max_date:
            raise ValueError("データがありません")

        min_dt = datetime.strptime(min_date, "%Y-%m-%d")
        max_dt = datetime.strptime(max_date, "%Y-%m-%d")

        split_days = int((max_dt - min_dt).days * train_ratio)
        split_dt = min_dt + timedelta(days=split_days)
        split_date = split_dt.strftime("%Y-%m-%d")

        return min_date, split_date, max_date

    def backtest_rules(self, split_date: str = None) -> Dict[str, Any]:
        """
        バックテストで法則の有効性を検証

        Args:
            split_date: 分割日（Noneなら自動計算）

        Returns:
            検証結果
        """
        if split_date is None:
            _, split_date, _ = self.get_time_split_dates()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        print(f"[INFO] バックテスト分割日: {split_date}")

        # テストデータを取得（分割日以降）
        cursor.execute("""
            SELECT
                r.id AS race_id,
                r.venue_code,
                r.race_number,
                e.pit_number,
                e.racer_rank,
                CAST(res.rank AS INTEGER) AS result_place
            FROM races r
            JOIN entries e ON r.id = e.race_id
            LEFT JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
            WHERE r.race_date >= ?
                AND res.rank IS NOT NULL
                AND res.rank != ''
                AND res.is_invalid = 0
        """, (split_date,))

        test_data = cursor.fetchall()
        print(f"[INFO] テストデータ: {len(test_data)}件")

        # venue_rules を取得
        cursor.execute("""
            SELECT id, venue_code, condition_type, condition_value,
                   target_pit, effect_value, description
            FROM venue_rules
            WHERE is_active = 1
        """)

        rules = cursor.fetchall()
        print(f"[INFO] 検証対象法則: {len(rules)}件")

        # 各法則をバックテスト
        results = []

        for rule in rules:
            rule_id, venue_code, condition_type, condition_value, target_pit, effect_value, description = rule

            # 条件に合致するデータを抽出
            matched_data = []
            for row in test_data:
                race_id, r_venue, race_num, pit_num, racer_rank, result_place = row

                # 基本条件チェック
                if pit_num != target_pit:
                    continue

                # 会場チェック（Noneなら全会場）
                if venue_code and r_venue != venue_code:
                    continue

                # 追加条件チェック
                if condition_type == 'rank' and condition_value:
                    if not racer_rank or condition_value not in str(racer_rank).upper():
                        continue

                matched_data.append(result_place)

            if len(matched_data) < 10:
                continue

            # 勝率計算
            win_count = sum(1 for r in matched_data if r == 1)
            actual_win_rate = win_count / len(matched_data)

            # ベースライン勝率（コース別平均）
            baseline = {1: 0.555, 2: 0.137, 3: 0.118, 4: 0.099, 5: 0.056, 6: 0.035}
            expected_rate = baseline.get(target_pit, 1/6) + effect_value

            # 誤差計算
            error = actual_win_rate - expected_rate

            results.append({
                'rule_id': rule_id,
                'description': description,
                'sample_size': len(matched_data),
                'effect_value': effect_value,
                'expected_rate': expected_rate,
                'actual_rate': actual_win_rate,
                'error': error,
                'is_valid': abs(error) < 0.05  # 5%以内なら有効
            })

        conn.close()

        # 結果集計
        valid_count = sum(1 for r in results if r['is_valid'])

        print(f"\n[結果] 有効な法則: {valid_count}/{len(results)}件")

        return {
            'split_date': split_date,
            'total_rules': len(results),
            'valid_rules': valid_count,
            'results': results
        }

    def test_prediction_accuracy(self, test_races: int = 100) -> Dict[str, Any]:
        """
        現予想ロジックでの精度テスト

        Args:
            test_races: テストするレース数

        Returns:
            精度結果
        """
        from src.analysis.race_predictor import RacePredictor

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 結果があるレースをランダムに取得
        cursor.execute("""
            SELECT DISTINCT r.id, r.venue_code, r.race_number, r.race_date
            FROM races r
            JOIN results res ON r.id = res.race_id
            WHERE res.rank IS NOT NULL
                AND res.rank != ''
                AND res.is_invalid = 0
            ORDER BY RANDOM()
            LIMIT ?
        """, (test_races,))

        races = cursor.fetchall()

        predictor = RacePredictor()

        top1_correct = 0
        top2_correct = 0
        top3_correct = 0
        total_tested = 0

        print(f"\n[INFO] {len(races)}レースで予想精度をテスト中...")

        for i, (race_id, venue_code, race_number, race_date) in enumerate(races):
            try:
                # 予想生成
                predictions = predictor.predict_race(race_id)

                if not predictions or len(predictions) < 3:
                    continue

                # 実際の1着を取得
                cursor.execute("""
                    SELECT pit_number FROM results
                    WHERE race_id = ? AND rank = '1'
                """, (race_id,))
                result = cursor.fetchone()

                if not result:
                    continue

                actual_winner = result[0]

                # 予想順位を取得
                pred_ranks = [p['pit_number'] for p in predictions]

                # Top-N正解率
                if pred_ranks[0] == actual_winner:
                    top1_correct += 1
                if actual_winner in pred_ranks[:2]:
                    top2_correct += 1
                if actual_winner in pred_ranks[:3]:
                    top3_correct += 1

                total_tested += 1

                if (i + 1) % 20 == 0:
                    print(f"  進捗: {i+1}/{len(races)}")

            except Exception as e:
                continue

        conn.close()

        if total_tested == 0:
            return {'error': 'テスト可能なレースがありません'}

        results = {
            'total_tested': total_tested,
            'top1_accuracy': top1_correct / total_tested,
            'top2_accuracy': top2_correct / total_tested,
            'top3_accuracy': top3_correct / total_tested
        }

        print(f"\n=== 予想精度結果 ===")
        print(f"テストレース数: {total_tested}")
        print(f"Top-1 正解率: {results['top1_accuracy']*100:.1f}%")
        print(f"Top-2 正解率: {results['top2_accuracy']*100:.1f}%")
        print(f"Top-3 正解率: {results['top3_accuracy']*100:.1f}%")

        return results

    def run_full_pipeline(self):
        """
        フルパイプライン実行
        1. 法則移行
        2. バックテスト検証
        3. 精度テスト
        """
        print("=" * 60)
        print("法則移行・バックテスト統合パイプライン")
        print("=" * 60)
        print()

        # Step 1: 法則移行
        print("Step 1: extracted_rules から venue_rules へ移行")
        print("-" * 40)
        migrated = self.migrate_extracted_to_venue_rules(min_confidence=0.3)
        print()

        # Step 2: バックテスト
        print("Step 2: バックテストで法則を検証")
        print("-" * 40)
        backtest_results = self.backtest_rules()

        # 有効な法則のみを残す
        if backtest_results['results']:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            invalid_count = 0
            for result in backtest_results['results']:
                if not result['is_valid']:
                    cursor.execute(
                        "UPDATE venue_rules SET is_active = 0 WHERE id = ?",
                        (result['rule_id'],)
                    )
                    invalid_count += 1

            conn.commit()
            conn.close()

            print(f"[INFO] {invalid_count}件の法則を無効化しました")
        print()

        # Step 3: 精度テスト
        print("Step 3: 現予想ロジックで精度テスト")
        print("-" * 40)
        accuracy_results = self.test_prediction_accuracy(test_races=200)
        print()

        print("=" * 60)
        print("パイプライン完了")
        print("=" * 60)

        return {
            'migrated_rules': migrated,
            'backtest': backtest_results,
            'accuracy': accuracy_results
        }


def main():
    """メイン実行"""
    pipeline = RuleMigrationAndBacktest()
    results = pipeline.run_full_pipeline()

    # 結果サマリー
    print("\n" + "=" * 60)
    print("結果サマリー")
    print("=" * 60)
    print(f"移行法則数: {results['migrated_rules']}")
    print(f"有効法則数: {results['backtest']['valid_rules']}/{results['backtest']['total_rules']}")
    if 'accuracy' in results and 'top1_accuracy' in results['accuracy']:
        print(f"Top-1正解率: {results['accuracy']['top1_accuracy']*100:.1f}%")
        print(f"Top-3正解率: {results['accuracy']['top3_accuracy']*100:.1f}%")


if __name__ == "__main__":
    main()
