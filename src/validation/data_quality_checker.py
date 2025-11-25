"""
データ品質検証モジュール
Phase 1.1: データ整合性チェック、欠損値処理、異常値検出
"""
import sqlite3
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Any
from datetime import datetime


class DataQualityChecker:
    """データ品質を検証するクラス"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.report = {}

    def run_full_check(self) -> Dict[str, Any]:
        """全品質チェックを実行"""
        print("=== データ品質検証開始 ===")

        # 1. スキーマ整合性チェック
        self.report['schema'] = self._check_schema_integrity()

        # 2. 外部キー制約チェック
        self.report['foreign_keys'] = self._check_foreign_key_constraints()

        # 3. データ範囲チェック
        self.report['data_ranges'] = self._check_data_ranges()

        # 4. 欠損値分析
        self.report['missing_values'] = self._analyze_missing_values()

        # 5. 異常値検出
        self.report['outliers'] = self._detect_outliers()

        # 6. レース整合性チェック
        self.report['race_integrity'] = self._check_race_integrity()

        # 7. 品質スコア計算
        self.report['quality_score'] = self._calculate_quality_score()

        print(f"\n品質スコア: {self.report['quality_score']:.2f}%")
        return self.report

    def _check_schema_integrity(self) -> Dict[str, Any]:
        """スキーマ整合性チェック"""
        print("1. スキーマ整合性チェック...")

        required_tables = [
            'venues', 'races', 'entries', 'results',
            'race_details', 'payouts', 'weather'
        ]

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = [row[0] for row in cursor.fetchall()]

        missing = [t for t in required_tables if t not in existing_tables]

        return {
            'status': 'PASS' if not missing else 'FAIL',
            'existing_tables': existing_tables,
            'missing_tables': missing
        }

    def _check_foreign_key_constraints(self) -> Dict[str, Any]:
        """外部キー制約チェック"""
        print("2. 外部キー制約チェック...")

        issues = []

        with sqlite3.connect(self.db_path) as conn:
            # entriesがracesを参照しているかチェック
            query = """
                SELECT COUNT(*) FROM entries e
                WHERE NOT EXISTS (SELECT 1 FROM races r WHERE r.id = e.race_id)
            """
            orphan_entries = pd.read_sql_query(query, conn).iloc[0, 0]
            if orphan_entries > 0:
                issues.append(f"entries: {orphan_entries}件の孤立レコード")

            # resultsがracesを参照しているかチェック
            query = """
                SELECT COUNT(*) FROM results r
                WHERE NOT EXISTS (SELECT 1 FROM races rc WHERE rc.id = r.race_id)
            """
            orphan_results = pd.read_sql_query(query, conn).iloc[0, 0]
            if orphan_results > 0:
                issues.append(f"results: {orphan_results}件の孤立レコード")

            # race_detailsがracesを参照しているかチェック
            query = """
                SELECT COUNT(*) FROM race_details rd
                WHERE NOT EXISTS (SELECT 1 FROM races r WHERE r.id = rd.race_id)
            """
            orphan_details = pd.read_sql_query(query, conn).iloc[0, 0]
            if orphan_details > 0:
                issues.append(f"race_details: {orphan_details}件の孤立レコード")

        return {
            'status': 'PASS' if not issues else 'WARN',
            'issues': issues
        }

    def _check_data_ranges(self) -> Dict[str, Any]:
        """データ範囲チェック"""
        print("3. データ範囲チェック...")

        issues = []

        with sqlite3.connect(self.db_path) as conn:
            # 枠番チェック (1-6)
            query = "SELECT COUNT(*) FROM entries WHERE pit_number < 1 OR pit_number > 6"
            invalid_pit = pd.read_sql_query(query, conn).iloc[0, 0]
            if invalid_pit > 0:
                issues.append(f"枠番範囲外: {invalid_pit}件")

            # 勝率チェック (0-10)
            query = "SELECT COUNT(*) FROM entries WHERE win_rate < 0 OR win_rate > 10"
            invalid_rate = pd.read_sql_query(query, conn).iloc[0, 0]
            if invalid_rate > 0:
                issues.append(f"勝率範囲外: {invalid_rate}件")

            # STタイムチェック (-1.0 ~ 1.0)
            query = """
                SELECT COUNT(*) FROM race_details
                WHERE st_time IS NOT NULL AND (st_time < -1.0 OR st_time > 1.0)
            """
            invalid_st = pd.read_sql_query(query, conn).iloc[0, 0]
            if invalid_st > 0:
                issues.append(f"STタイム範囲外: {invalid_st}件")

            # 展示タイムチェック (5.0 ~ 8.0)
            query = """
                SELECT COUNT(*) FROM race_details
                WHERE exhibition_time IS NOT NULL AND (exhibition_time < 5.0 OR exhibition_time > 8.0)
            """
            invalid_ex = pd.read_sql_query(query, conn).iloc[0, 0]
            if invalid_ex > 0:
                issues.append(f"展示タイム範囲外: {invalid_ex}件")

        return {
            'status': 'PASS' if not issues else 'WARN',
            'issues': issues
        }

    def _analyze_missing_values(self) -> Dict[str, Any]:
        """欠損値分析"""
        print("4. 欠損値分析...")

        missing_stats = {}

        with sqlite3.connect(self.db_path) as conn:
            # entries テーブル
            query = """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN racer_number IS NULL THEN 1 ELSE 0 END) as racer_number_null,
                    SUM(CASE WHEN win_rate IS NULL THEN 1 ELSE 0 END) as win_rate_null,
                    SUM(CASE WHEN motor_number IS NULL THEN 1 ELSE 0 END) as motor_null
                FROM entries
            """
            df = pd.read_sql_query(query, conn)
            total = df['total'].iloc[0]
            missing_stats['entries'] = {
                'racer_number': (df['racer_number_null'].iloc[0] / total * 100) if total > 0 else 0,
                'win_rate': (df['win_rate_null'].iloc[0] / total * 100) if total > 0 else 0,
                'motor_number': (df['motor_null'].iloc[0] / total * 100) if total > 0 else 0
            }

            # race_details テーブル
            query = """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN exhibition_time IS NULL THEN 1 ELSE 0 END) as exhibition_null,
                    SUM(CASE WHEN st_time IS NULL THEN 1 ELSE 0 END) as st_null,
                    SUM(CASE WHEN actual_course IS NULL THEN 1 ELSE 0 END) as course_null
                FROM race_details
            """
            df = pd.read_sql_query(query, conn)
            total = df['total'].iloc[0]
            missing_stats['race_details'] = {
                'exhibition_time': (df['exhibition_null'].iloc[0] / total * 100) if total > 0 else 0,
                'st_time': (df['st_null'].iloc[0] / total * 100) if total > 0 else 0,
                'actual_course': (df['course_null'].iloc[0] / total * 100) if total > 0 else 0
            }

        # 欠損率が高いもの(10%以上)を警告
        warnings = []
        for table, cols in missing_stats.items():
            for col, rate in cols.items():
                if rate > 10:
                    warnings.append(f"{table}.{col}: {rate:.1f}%欠損")

        return {
            'status': 'PASS' if not warnings else 'WARN',
            'stats': missing_stats,
            'warnings': warnings
        }

    def _detect_outliers(self) -> Dict[str, Any]:
        """異常値検出"""
        print("5. 異常値検出...")

        outliers = {}

        with sqlite3.connect(self.db_path) as conn:
            # 勝率の異常値 (IQR法)
            df = pd.read_sql_query("SELECT win_rate FROM entries WHERE win_rate IS NOT NULL", conn)
            if len(df) > 0:
                Q1 = df['win_rate'].quantile(0.25)
                Q3 = df['win_rate'].quantile(0.75)
                IQR = Q3 - Q1
                lower = Q1 - 1.5 * IQR
                upper = Q3 + 1.5 * IQR
                outlier_count = ((df['win_rate'] < lower) | (df['win_rate'] > upper)).sum()
                outliers['win_rate'] = {
                    'count': int(outlier_count),
                    'percentage': outlier_count / len(df) * 100
                }

            # 展示タイムの異常値
            df = pd.read_sql_query(
                "SELECT exhibition_time FROM race_details WHERE exhibition_time IS NOT NULL", conn
            )
            if len(df) > 0:
                Q1 = df['exhibition_time'].quantile(0.25)
                Q3 = df['exhibition_time'].quantile(0.75)
                IQR = Q3 - Q1
                lower = Q1 - 1.5 * IQR
                upper = Q3 + 1.5 * IQR
                outlier_count = ((df['exhibition_time'] < lower) | (df['exhibition_time'] > upper)).sum()
                outliers['exhibition_time'] = {
                    'count': int(outlier_count),
                    'percentage': outlier_count / len(df) * 100
                }

        return {
            'status': 'PASS' if all(v['percentage'] < 5 for v in outliers.values()) else 'WARN',
            'outliers': outliers
        }

    def _check_race_integrity(self) -> Dict[str, Any]:
        """レース整合性チェック"""
        print("6. レース整合性チェック...")

        issues = []

        with sqlite3.connect(self.db_path) as conn:
            # 6艇未満のレースチェック
            query = """
                SELECT rc.id, COUNT(e.id) as entry_count
                FROM races rc
                LEFT JOIN entries e ON rc.id = e.race_id
                GROUP BY rc.id
                HAVING entry_count != 6
            """
            df = pd.read_sql_query(query, conn)
            if len(df) > 0:
                issues.append(f"6艇未満のレース: {len(df)}件")

            # 結果が6件未満のレースチェック
            query = """
                SELECT rc.id, COUNT(r.id) as result_count
                FROM races rc
                LEFT JOIN results r ON rc.id = r.race_id
                GROUP BY rc.id
                HAVING result_count > 0 AND result_count != 6
            """
            df = pd.read_sql_query(query, conn)
            if len(df) > 0:
                issues.append(f"結果不完全なレース: {len(df)}件")

            # 重複着順チェック
            query = """
                SELECT race_id, rank, COUNT(*) as cnt
                FROM results
                WHERE rank IN ('1', '2', '3', '4', '5', '6')
                GROUP BY race_id, rank
                HAVING cnt > 1
            """
            df = pd.read_sql_query(query, conn)
            if len(df) > 0:
                issues.append(f"重複着順: {len(df)}件")

        return {
            'status': 'PASS' if not issues else 'WARN',
            'issues': issues
        }

    def _calculate_quality_score(self) -> float:
        """品質スコアを計算 (0-100)"""
        score = 100.0

        # スキーマ整合性 (-20 if fail)
        if self.report['schema']['status'] == 'FAIL':
            score -= 20

        # 外部キー制約 (-5 per issue)
        score -= len(self.report['foreign_keys']['issues']) * 5

        # データ範囲 (-3 per issue)
        score -= len(self.report['data_ranges']['issues']) * 3

        # 欠損値 (-2 per warning)
        score -= len(self.report['missing_values']['warnings']) * 2

        # 異常値 (-2 if warn)
        if self.report['outliers']['status'] == 'WARN':
            score -= 2

        # レース整合性 (-5 per issue)
        score -= len(self.report['race_integrity']['issues']) * 5

        return max(0, min(100, score))

    def generate_report(self, output_path: str = None) -> str:
        """品質レポートを生成"""
        if not self.report:
            self.run_full_check()

        report_text = f"""
========================================
データ品質レポート
生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
========================================

総合品質スコア: {self.report['quality_score']:.2f}%

1. スキーマ整合性: {self.report['schema']['status']}
   - 既存テーブル数: {len(self.report['schema']['existing_tables'])}
   - 欠落テーブル: {self.report['schema']['missing_tables'] or 'なし'}

2. 外部キー制約: {self.report['foreign_keys']['status']}
   - 問題: {self.report['foreign_keys']['issues'] or 'なし'}

3. データ範囲: {self.report['data_ranges']['status']}
   - 問題: {self.report['data_ranges']['issues'] or 'なし'}

4. 欠損値: {self.report['missing_values']['status']}
   - 警告: {self.report['missing_values']['warnings'] or 'なし'}

5. 異常値: {self.report['outliers']['status']}
   - 検出: {self.report['outliers']['outliers']}

6. レース整合性: {self.report['race_integrity']['status']}
   - 問題: {self.report['race_integrity']['issues'] or 'なし'}

========================================
"""

        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report_text)
            print(f"レポートを {output_path} に保存しました")

        return report_text


class DataValidator:
    """データ検証用のユーティリティクラス"""

    @staticmethod
    def validate_race_data(data: Dict) -> Tuple[bool, List[str]]:
        """レースデータの検証"""
        errors = []

        required_fields = ['venue_code', 'race_date', 'race_number']
        for field in required_fields:
            if field not in data or data[field] is None:
                errors.append(f"必須フィールド欠落: {field}")

        if 'race_number' in data and data['race_number'] is not None:
            if not (1 <= data['race_number'] <= 12):
                errors.append(f"レース番号範囲外: {data['race_number']}")

        return len(errors) == 0, errors

    @staticmethod
    def validate_entry_data(data: Dict) -> Tuple[bool, List[str]]:
        """エントリーデータの検証"""
        errors = []

        if 'pit_number' in data:
            if not (1 <= data['pit_number'] <= 6):
                errors.append(f"枠番範囲外: {data['pit_number']}")

        if 'win_rate' in data and data['win_rate'] is not None:
            if not (0 <= data['win_rate'] <= 10):
                errors.append(f"勝率範囲外: {data['win_rate']}")

        if 'racer_age' in data and data['racer_age'] is not None:
            if not (18 <= data['racer_age'] <= 70):
                errors.append(f"年齢範囲外: {data['racer_age']}")

        return len(errors) == 0, errors

    @staticmethod
    def validate_probabilities(probs: List[float]) -> Tuple[bool, str]:
        """確率の検証（合計が1.0になるか）"""
        if len(probs) != 6:
            return False, f"確率の数が6でない: {len(probs)}"

        total = sum(probs)
        if abs(total - 1.0) > 0.01:
            return False, f"確率の合計が1.0でない: {total:.4f}"

        for i, p in enumerate(probs):
            if not (0 <= p <= 1):
                return False, f"確率{i+1}が範囲外: {p:.4f}"

        return True, "OK"
