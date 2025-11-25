"""
データベース内部整合性チェックスクリプト

公式サイトではなく、DB内部のテーブル間整合性をチェック:
- races ⇔ entries の紐付け
- races ⇔ results の紐付け
- races ⇔ race_details の紐付け
- エントリー数 vs 結果数の整合性
- ST時間の妥当性チェック
"""

import sqlite3
from datetime import datetime


class DBIntegrityChecker:
    """データベース整合性チェッカー"""

    def __init__(self, db_path="data/boatrace.db"):
        """
        初期化

        Args:
            db_path: データベースパス
        """
        self.db_path = db_path

    def check_db_integrity(self, start_date: str, end_date: str, venue_codes: list = None):
        """
        指定期間のDB整合性チェック

        Args:
            start_date: 開始日 (YYYY-MM-DD)
            end_date: 終了日 (YYYY-MM-DD)
            venue_codes: チェック対象会場コード（Noneの場合は全会場）
        """
        print("="*80)
        print("データベース整合性チェック")
        print("="*80)
        print(f"期間: {start_date} ～ {end_date}")
        print("="*80)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # チェック対象のレースを取得
        if venue_codes:
            placeholders = ','.join('?' * len(venue_codes))
            query = f"""
                SELECT
                    r.id,
                    r.venue_code,
                    r.race_date,
                    r.race_number
                FROM races r
                WHERE r.race_date >= ? AND r.race_date <= ?
                  AND r.venue_code IN ({placeholders})
                ORDER BY r.race_date, r.venue_code, r.race_number
            """
            cursor.execute(query, [start_date, end_date] + venue_codes)
        else:
            cursor.execute("""
                SELECT
                    r.id,
                    r.venue_code,
                    r.race_date,
                    r.race_number
                FROM races r
                WHERE r.race_date >= ? AND r.race_date <= ?
                ORDER BY r.race_date, r.venue_code, r.race_number
            """, (start_date, end_date))

        races = cursor.fetchall()
        print(f"\\nチェック対象レース数: {len(races):,}")

        if len(races) == 0:
            print("チェック対象のレースがありません")
            conn.close()
            return

        # 統計情報
        total_checked = 0
        issues = []

        # 問題カテゴリ別カウント
        missing_entries = 0
        missing_results = 0
        missing_st_times = 0
        entry_count_mismatch = 0
        result_count_mismatch = 0
        invalid_st_times = 0
        orphan_results = 0

        print("\\nチェック中...")

        for i, (race_id, venue_code, race_date, race_number) in enumerate(races):
            try:
                # 進捗表示
                if (i + 1) % 100 == 0:
                    print(f"  進捗: {i+1}/{len(races)} ({(i+1)/len(races)*100:.1f}%)")

                # 1. entriesテーブルのチェック
                cursor.execute("SELECT COUNT(*) FROM entries WHERE race_id = ?", (race_id,))
                entry_count = cursor.fetchone()[0]

                # 2. resultsテーブルのチェック
                cursor.execute("SELECT COUNT(*) FROM results WHERE race_id = ?", (race_id,))
                result_count = cursor.fetchone()[0]

                # 3. race_detailsテーブルのST時間チェック
                cursor.execute("""
                    SELECT COUNT(*), COUNT(st_time)
                    FROM race_details
                    WHERE race_id = ?
                """, (race_id,))
                detail_count, st_time_count = cursor.fetchone()

                # エントリーが0件
                if entry_count == 0:
                    missing_entries += 1
                    issues.append({
                        'type': 'missing_entries',
                        'race_id': race_id,
                        'venue': venue_code,
                        'date': race_date,
                        'race_num': race_number,
                        'detail': f'エントリーデータなし'
                    })

                # 結果が0件（エントリーがある場合のみ）
                if entry_count > 0 and result_count == 0:
                    missing_results += 1
                    issues.append({
                        'type': 'missing_results',
                        'race_id': race_id,
                        'venue': venue_code,
                        'date': race_date,
                        'race_num': race_number,
                        'detail': f'結果データなし (エントリー{entry_count}件あり)'
                    })

                # エントリー数と結果数が不一致
                if entry_count > 0 and result_count > 0 and entry_count != result_count:
                    entry_count_mismatch += 1
                    issues.append({
                        'type': 'count_mismatch',
                        'race_id': race_id,
                        'venue': venue_code,
                        'date': race_date,
                        'race_num': race_number,
                        'detail': f'エントリー{entry_count}件 vs 結果{result_count}件'
                    })

                # ST時間データ不足（結果がある場合のみ）
                if result_count > 0 and st_time_count < result_count:
                    missing_st_times += 1
                    issues.append({
                        'type': 'missing_st_times',
                        'race_id': race_id,
                        'venue': venue_code,
                        'date': race_date,
                        'race_num': race_number,
                        'detail': f'ST時間{st_time_count}/{result_count}件のみ'
                    })

                # ST時間の妥当性チェック
                cursor.execute("""
                    SELECT st_time FROM race_details WHERE race_id = ? AND st_time IS NOT NULL
                """, (race_id,))
                st_times = cursor.fetchall()

                for (st_time,) in st_times:
                    # 異常な値チェック（-1.0 ～ 3.0の範囲外）
                    if st_time < -1.0 or st_time > 3.0:
                        invalid_st_times += 1
                        issues.append({
                            'type': 'invalid_st_time',
                            'race_id': race_id,
                            'venue': venue_code,
                            'date': race_date,
                            'race_num': race_number,
                            'detail': f'異常なST時間: {st_time}'
                        })
                        break  # 同じレースで複数カウントしない

                # 孤立した結果（エントリーがない結果）
                if result_count > 0 and entry_count == 0:
                    orphan_results += 1
                    issues.append({
                        'type': 'orphan_results',
                        'race_id': race_id,
                        'venue': venue_code,
                        'date': race_date,
                        'race_num': race_number,
                        'detail': f'エントリーなしで結果{result_count}件あり'
                    })

                total_checked += 1

            except Exception as e:
                print(f"\\n  [ERROR] レースID {race_id}: {e}")

        conn.close()

        # 結果表示
        print("\\n" + "="*80)
        print("チェック結果")
        print("="*80)
        print(f"チェック済みレース数: {total_checked:,}/{len(races):,}")
        print()
        print("【問題サマリー】")
        print(f"  エントリーデータなし: {missing_entries:,}")
        print(f"  結果データなし: {missing_results:,}")
        print(f"  ST時間不足: {missing_st_times:,}")
        print(f"  エントリー数不一致: {entry_count_mismatch:,}")
        print(f"  異常なST時間: {invalid_st_times:,}")
        print(f"  孤立した結果: {orphan_results:,}")
        print()

        total_issues = len(issues)
        print(f"【総合評価】")
        if total_issues == 0:
            print("  [OK] 問題なし - データは正常です")
        else:
            print(f"  [WARN] {total_issues:,} 件の問題が見つかりました")

        print("="*80)

        # 問題の詳細表示（最大30件）
        if issues:
            print(f"\\n問題の詳細（最大30件表示）:")
            print("-"*80)

            # タイプ別にグループ化
            by_type = {}
            for issue in issues:
                issue_type = issue['type']
                if issue_type not in by_type:
                    by_type[issue_type] = []
                by_type[issue_type].append(issue)

            shown = 0
            for issue_type, type_issues in by_type.items():
                type_name = {
                    'missing_entries': 'エントリーデータなし',
                    'missing_results': '結果データなし',
                    'missing_st_times': 'ST時間不足',
                    'count_mismatch': 'エントリー数不一致',
                    'invalid_st_time': '異常なST時間',
                    'orphan_results': '孤立した結果'
                }.get(issue_type, issue_type)

                print(f"\\n■ {type_name} ({len(type_issues)}件)")
                for issue in type_issues[:10]:  # 各タイプ最大10件
                    print(f"  - 会場{issue['venue']} {issue['date']} {issue['race_num']}R: {issue['detail']}")
                    shown += 1
                    if shown >= 30:
                        break

                if shown >= 30:
                    break

            if total_issues > 30:
                print(f"\\n... 他 {total_issues - 30} 件の問題")

        print("\\n" + "="*80)

        return {
            'total': len(races),
            'checked': total_checked,
            'missing_entries': missing_entries,
            'missing_results': missing_results,
            'missing_st_times': missing_st_times,
            'entry_count_mismatch': entry_count_mismatch,
            'invalid_st_times': invalid_st_times,
            'orphan_results': orphan_results,
            'total_issues': total_issues,
            'issues': issues
        }


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(
        description='データベース整合性チェック'
    )
    parser.add_argument('--start', default='2024-04-01', help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', default='2024-04-30', help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--venues', nargs='+', help='対象会場コード（例: 01 02 03）')
    parser.add_argument('--db', default='data/boatrace.db', help='データベースパス')

    args = parser.parse_args()

    checker = DBIntegrityChecker(db_path=args.db)

    result = checker.check_db_integrity(
        start_date=args.start,
        end_date=args.end,
        venue_codes=args.venues
    )

    print("\\n整合性チェック完了")


if __name__ == '__main__':
    main()
