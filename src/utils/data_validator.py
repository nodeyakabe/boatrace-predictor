"""
データ整合性チェックモジュール
収集したデータの妥当性を検証し、誤ったデータを検出
"""

import sqlite3
from typing import Dict, List
from datetime import datetime
from src.utils.db_connection_pool import get_connection


class DataValidator:
    """データ検証クラス"""

    def __init__(self, db_path: str = "data/boatrace.db"):
        self.db_path = db_path

    def _connect(self):
        """データベース接続（接続プールから取得）"""
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def validate_st_timing(self) -> Dict:
        """
        STタイミングの妥当性を検証
        展示タイムとSTタイミングの混同を検出

        STタイミングの正常範囲: 0.00～0.30秒程度
        展示タイムの正常範囲: 6.00～7.50秒程度

        Returns:
            {
                'total_records': 1000,
                'invalid_st': 5,
                'likely_exhibition_time': [
                    {'race_id': 123, 'pit_number': 1, 'avg_st': 6.78},
                    ...
                ]
            }
        """
        conn = self._connect()
        cursor = conn.cursor()

        # STタイミングを取得
        cursor.execute("""
            SELECT race_id, pit_number, avg_st
            FROM entries
            WHERE avg_st IS NOT NULL
        """)

        rows = cursor.fetchall()
        cursor.close()

        total_records = len(rows)
        invalid_st = []

        for row in rows:
            avg_st = row['avg_st']

            # STタイミングが異常な範囲にある場合
            # 正常: 0.00～0.30
            # 異常: 6.0以上（展示タイムの可能性）
            if avg_st > 3.0:
                invalid_st.append({
                    'race_id': row['race_id'],
                    'pit_number': row['pit_number'],
                    'avg_st': avg_st,
                    'suspected_issue': 'exhibition_time'
                })
            elif avg_st < 0:
                invalid_st.append({
                    'race_id': row['race_id'],
                    'pit_number': row['pit_number'],
                    'avg_st': avg_st,
                    'suspected_issue': 'negative_value'
                })

        return {
            'total_records': total_records,
            'invalid_count': len(invalid_st),
            'invalid_rate': len(invalid_st) / total_records * 100 if total_records > 0 else 0,
            'invalid_records': invalid_st
        }

    def validate_win_rate(self) -> Dict:
        """
        勝率の妥当性を検証

        正常範囲: 0.00～10.00

        Returns:
            {
                'total_records': 1000,
                'invalid_count': 2,
                'invalid_records': [...]
            }
        """
        conn = self._connect()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT race_id, pit_number, win_rate
            FROM entries
            WHERE win_rate IS NOT NULL
        """)

        rows = cursor.fetchall()
        cursor.close()

        total_records = len(rows)
        invalid_records = []

        for row in rows:
            win_rate = row['win_rate']

            if win_rate < 0 or win_rate > 10.0:
                invalid_records.append({
                    'race_id': row['race_id'],
                    'pit_number': row['pit_number'],
                    'win_rate': win_rate,
                    'suspected_issue': 'out_of_range'
                })

        return {
            'total_records': total_records,
            'invalid_count': len(invalid_records),
            'invalid_rate': len(invalid_records) / total_records * 100 if total_records > 0 else 0,
            'invalid_records': invalid_records
        }

    def validate_racer_number(self) -> Dict:
        """
        選手登録番号の妥当性を検証

        正常範囲: 1000～9999 (4桁)

        Returns:
            {
                'total_records': 1000,
                'invalid_count': 0,
                'invalid_records': [...]
            }
        """
        conn = self._connect()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT race_id, pit_number, racer_number
            FROM entries
            WHERE racer_number IS NOT NULL
        """)

        rows = cursor.fetchall()
        cursor.close()

        total_records = len(rows)
        invalid_records = []

        for row in rows:
            try:
                racer_number = int(row['racer_number']) if row['racer_number'] else 0
            except (ValueError, TypeError):
                racer_number = 0

            if racer_number < 1000 or racer_number > 9999:
                invalid_records.append({
                    'race_id': row['race_id'],
                    'pit_number': row['pit_number'],
                    'racer_number': racer_number,
                    'suspected_issue': 'invalid_format'
                })

        return {
            'total_records': total_records,
            'invalid_count': len(invalid_records),
            'invalid_rate': len(invalid_records) / total_records * 100 if total_records > 0 else 0,
            'invalid_records': invalid_records
        }

    def validate_motor_stats(self) -> Dict:
        """
        モーター2連率・3連率の妥当性を検証

        正常範囲: 0.00～100.00

        Returns:
            {
                'total_records': 1000,
                'invalid_count': 1,
                'invalid_records': [...]
            }
        """
        conn = self._connect()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT race_id, pit_number, motor_second_rate, motor_third_rate
            FROM entries
            WHERE motor_second_rate IS NOT NULL OR motor_third_rate IS NOT NULL
        """)

        rows = cursor.fetchall()
        cursor.close()

        total_records = len(rows)
        invalid_records = []

        for row in rows:
            motor_second_rate = row['motor_second_rate']
            motor_third_rate = row['motor_third_rate']

            issues = []

            if motor_second_rate is not None and (motor_second_rate < 0 or motor_second_rate > 100):
                issues.append('motor_second_rate_out_of_range')

            if motor_third_rate is not None and (motor_third_rate < 0 or motor_third_rate > 100):
                issues.append('motor_third_rate_out_of_range')

            if issues:
                invalid_records.append({
                    'race_id': row['race_id'],
                    'pit_number': row['pit_number'],
                    'motor_second_rate': motor_second_rate,
                    'motor_third_rate': motor_third_rate,
                    'suspected_issues': issues
                })

        return {
            'total_records': total_records,
            'invalid_count': len(invalid_records),
            'invalid_rate': len(invalid_records) / total_records * 100 if total_records > 0 else 0,
            'invalid_records': invalid_records
        }

    def validate_results(self) -> Dict:
        """
        結果データの妥当性を検証

        - 着順は1～6
        - 1レースに6艇の結果が存在
        - 着順に重複がない

        Returns:
            {
                'total_races': 100,
                'incomplete_races': 2,
                'duplicate_ranks': 1,
                'invalid_ranks': 0
            }
        """
        conn = self._connect()
        cursor = conn.cursor()

        # レースごとに結果を集計
        cursor.execute("""
            SELECT race_id, COUNT(*) as result_count, GROUP_CONCAT(rank) as ranks
            FROM results
            WHERE is_invalid = 0
            GROUP BY race_id
        """)

        rows = cursor.fetchall()
        cursor.close()

        total_races = len(rows)
        incomplete_races = []
        duplicate_ranks = []
        invalid_ranks = []

        for row in rows:
            race_id = row['race_id']
            result_count = row['result_count']
            ranks = [int(r) for r in row['ranks'].split(',') if r]

            # 結果が6艇分ない
            if result_count != 6:
                incomplete_races.append({
                    'race_id': race_id,
                    'result_count': result_count
                })

            # 着順に重複がある
            if len(ranks) != len(set(ranks)):
                duplicate_ranks.append({
                    'race_id': race_id,
                    'ranks': ranks
                })

            # 着順が1～6の範囲外
            for rank in ranks:
                if rank < 1 or rank > 6:
                    invalid_ranks.append({
                        'race_id': race_id,
                        'invalid_rank': rank
                    })

        return {
            'total_races': total_races,
            'incomplete_races_count': len(incomplete_races),
            'duplicate_ranks_count': len(duplicate_ranks),
            'invalid_ranks_count': len(invalid_ranks),
            'incomplete_races': incomplete_races,
            'duplicate_ranks': duplicate_ranks,
            'invalid_ranks': invalid_ranks
        }

    def run_full_validation(self) -> Dict:
        """
        全ての検証を実行

        Returns:
            {
                'st_timing': {...},
                'win_rate': {...},
                'racer_number': {...},
                'motor_stats': {...},
                'results': {...},
                'summary': {
                    'total_issues': 10,
                    'critical_issues': 2
                }
            }
        """
        st_result = self.validate_st_timing()
        win_rate_result = self.validate_win_rate()
        racer_number_result = self.validate_racer_number()
        motor_stats_result = self.validate_motor_stats()
        results_result = self.validate_results()

        # 重大な問題をカウント
        critical_issues = (
            st_result['invalid_count'] +
            results_result['incomplete_races_count'] +
            results_result['duplicate_ranks_count']
        )

        # 全問題をカウント
        total_issues = (
            st_result['invalid_count'] +
            win_rate_result['invalid_count'] +
            racer_number_result['invalid_count'] +
            motor_stats_result['invalid_count'] +
            results_result['incomplete_races_count'] +
            results_result['duplicate_ranks_count'] +
            results_result['invalid_ranks_count']
        )

        return {
            'st_timing': st_result,
            'win_rate': win_rate_result,
            'racer_number': racer_number_result,
            'motor_stats': motor_stats_result,
            'results': results_result,
            'summary': {
                'total_issues': total_issues,
                'critical_issues': critical_issues
            }
        }


if __name__ == "__main__":
    # テスト
    validator = DataValidator()

    print("=" * 80)
    print("データ整合性チェック")
    print("=" * 80)

    # 全検証を実行
    results = validator.run_full_validation()

    print("\n【サマリー】")
    print(f"総問題数: {results['summary']['total_issues']}")
    print(f"重大な問題: {results['summary']['critical_issues']}")

    print("\n【STタイミング】")
    st = results['st_timing']
    print(f"総レコード数: {st['total_records']}")
    print(f"異常データ: {st['invalid_count']}件 ({st['invalid_rate']:.1f}%)")

    if st['invalid_count'] > 0:
        print("異常データ例:")
        for record in st['invalid_records'][:3]:
            print(f"  レースID={record['race_id']}, 艇={record['pit_number']}, "
                  f"ST={record['avg_st']}, 問題={record['suspected_issue']}")

    print("\n【勝率】")
    wr = results['win_rate']
    print(f"総レコード数: {wr['total_records']}")
    print(f"異常データ: {wr['invalid_count']}件 ({wr['invalid_rate']:.1f}%)")

    print("\n【選手登録番号】")
    rn = results['racer_number']
    print(f"総レコード数: {rn['total_records']}")
    print(f"異常データ: {rn['invalid_count']}件 ({rn['invalid_rate']:.1f}%)")

    print("\n【モーター統計（2連率・3連率）】")
    ms = results['motor_stats']
    print(f"総レコード数: {ms['total_records']}")
    print(f"異常データ: {ms['invalid_count']}件 ({ms['invalid_rate']:.1f}%)")

    print("\n【結果データ】")
    res = results['results']
    print(f"総レース数: {res['total_races']}")
    print(f"不完全なレース: {res['incomplete_races_count']}件")
    print(f"着順重複: {res['duplicate_ranks_count']}件")
    print(f"不正な着順: {res['invalid_ranks_count']}件")

    print("\n" + "=" * 80)
