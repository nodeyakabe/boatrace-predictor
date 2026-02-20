#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
データ収集完了確認スクリプト

2021年・2023年のデータ収集が本当に完了しているかを包括的に検証します。
"""
import sys
import io
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple

# Windows文字コード対策
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DATABASE_PATH


def check_monthly_races(cursor: sqlite3.Cursor, year: int) -> List[Tuple[str, int]]:
    """月別レース数を取得"""
    cursor.execute("""
        SELECT
            SUBSTR(race_date, 1, 7) as month,
            COUNT(*) as race_count
        FROM races
        WHERE race_date LIKE ?
        GROUP BY month
        ORDER BY month
    """, (f'{year}-%',))
    return cursor.fetchall()


def check_data_coverage(cursor: sqlite3.Cursor, year: int) -> Dict[str, dict]:
    """各データ種別のカバレッジを確認"""

    # 対象レース数
    cursor.execute("""
        SELECT COUNT(*) FROM races WHERE race_date LIKE ?
    """, (f'{year}-%',))
    total_races = cursor.fetchone()[0]

    if total_races == 0:
        return {'total_races': 0}

    # entries（出走表）
    cursor.execute("""
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        WHERE r.race_date LIKE ?
        AND EXISTS (
            SELECT 1 FROM entries e WHERE e.race_id = r.id
        )
    """, (f'{year}-%',))
    races_with_entries = cursor.fetchone()[0]

    # results（結果）
    cursor.execute("""
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        WHERE r.race_date LIKE ?
        AND EXISTS (
            SELECT 1 FROM results res WHERE res.race_id = r.id
        )
    """, (f'{year}-%',))
    races_with_results = cursor.fetchone()[0]

    # trifecta_odds（3連単オッズ）
    cursor.execute("""
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        WHERE r.race_date LIKE ?
        AND EXISTS (
            SELECT 1 FROM trifecta_odds t WHERE t.race_id = r.id
        )
    """, (f'{year}-%',))
    races_with_odds = cursor.fetchone()[0]

    # race_conditions（レース条件）
    cursor.execute("""
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        WHERE r.race_date LIKE ?
        AND EXISTS (
            SELECT 1 FROM race_conditions rc WHERE rc.race_id = r.id
        )
    """, (f'{year}-%',))
    races_with_conditions = cursor.fetchone()[0]

    # race_details（レース詳細）
    cursor.execute("""
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        WHERE r.race_date LIKE ?
        AND EXISTS (
            SELECT 1 FROM race_details rd WHERE rd.race_id = r.id
        )
    """, (f'{year}-%',))
    races_with_details = cursor.fetchone()[0]

    # payouts（払戻）
    cursor.execute("""
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        WHERE r.race_date LIKE ?
        AND EXISTS (
            SELECT 1 FROM payouts p WHERE p.race_id = r.id
        )
    """, (f'{year}-%',))
    races_with_payouts = cursor.fetchone()[0]

    return {
        'total_races': total_races,
        'entries': {
            'count': races_with_entries,
            'coverage': races_with_entries / total_races * 100
        },
        'results': {
            'count': races_with_results,
            'coverage': races_with_results / total_races * 100
        },
        'trifecta_odds': {
            'count': races_with_odds,
            'coverage': races_with_odds / total_races * 100
        },
        'race_conditions': {
            'count': races_with_conditions,
            'coverage': races_with_conditions / total_races * 100
        },
        'race_details': {
            'count': races_with_details,
            'coverage': races_with_details / total_races * 100
        },
        'payouts': {
            'count': races_with_payouts,
            'coverage': races_with_payouts / total_races * 100
        }
    }


def find_missing_data(cursor: sqlite3.Cursor, year: int) -> Dict[str, List[Tuple]]:
    """欠損データを検出"""

    missing = {}

    # entriesが欠けているレース
    cursor.execute("""
        SELECT r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date LIKE ?
        AND NOT EXISTS (
            SELECT 1 FROM entries e WHERE e.race_id = r.id
        )
        ORDER BY r.race_date, r.venue_code, r.race_number
        LIMIT 10
    """, (f'{year}-%',))
    missing['entries'] = cursor.fetchall()

    # resultsが欠けているレース
    cursor.execute("""
        SELECT r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date LIKE ?
        AND NOT EXISTS (
            SELECT 1 FROM results res WHERE res.race_id = r.id
        )
        ORDER BY r.race_date, r.venue_code, r.race_number
        LIMIT 10
    """, (f'{year}-%',))
    missing['results'] = cursor.fetchall()

    # trifecta_oddsが欠けているレース
    cursor.execute("""
        SELECT r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date LIKE ?
        AND NOT EXISTS (
            SELECT 1 FROM trifecta_odds t WHERE t.race_id = r.id
        )
        ORDER BY r.race_date, r.venue_code, r.race_number
        LIMIT 10
    """, (f'{year}-%',))
    missing['trifecta_odds'] = cursor.fetchall()

    # race_conditionsが欠けているレース
    cursor.execute("""
        SELECT r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date LIKE ?
        AND NOT EXISTS (
            SELECT 1 FROM race_conditions rc WHERE rc.race_id = r.id
        )
        ORDER BY r.race_date, r.venue_code, r.race_number
        LIMIT 10
    """, (f'{year}-%',))
    missing['race_conditions'] = cursor.fetchall()

    # race_detailsが欠けているレース
    cursor.execute("""
        SELECT r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date LIKE ?
        AND NOT EXISTS (
            SELECT 1 FROM race_details rd WHERE rd.race_id = r.id
        )
        ORDER BY r.race_date, r.venue_code, r.race_number
        LIMIT 10
    """, (f'{year}-%',))
    missing['race_details'] = cursor.fetchall()

    return missing


def check_date_format_consistency(cursor: sqlite3.Cursor) -> Dict[str, int]:
    """日付形式の一貫性を確認"""
    cursor.execute("""
        SELECT
            CASE
                WHEN race_date LIKE '____-__-__' THEN 'YYYY-MM-DD'
                WHEN LENGTH(race_date) = 8 THEN 'YYYYMMDD'
                ELSE 'その他'
            END as format,
            COUNT(*) as cnt
        FROM races
        GROUP BY format
    """)
    return {fmt: cnt for fmt, cnt in cursor.fetchall()}


def main():
    print("=" * 80)
    print("データ収集完了確認レポート")
    print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print()

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 日付形式の一貫性チェック
    print("=== 1. 日付形式の確認 ===")
    date_formats = check_date_format_consistency(cursor)
    for fmt, cnt in date_formats.items():
        print(f"{fmt}: {cnt:,}件")

    if 'YYYYMMDD' in date_formats:
        print("\n⚠️ WARNING: YYYYMMDD形式のデータが残っています！")
    else:
        print("\n✅ OK: 全データがYYYY-MM-DD形式で統一されています")
    print()

    # 2021年・2023年のチェック
    for year in [2021, 2023]:
        print("=" * 80)
        print(f"=== {year}年のデータ状況 ===")
        print("=" * 80)
        print()

        # 月別レース数
        print(f"--- {year}年 月別レース数 ---")
        monthly_races = check_monthly_races(cursor, year)

        if not monthly_races:
            print(f"❌ {year}年のデータが存在しません！")
            print()
            continue

        total_races = 0
        all_months_present = len(monthly_races) == 12

        for month, count in monthly_races:
            total_races += count
            print(f"{month}: {count:,}件")

        print(f"\n合計: {total_races:,}件")

        if all_months_present:
            print(f"✅ {year}年は全12ヶ月のデータが存在します")
        else:
            print(f"⚠️ {year}年は{len(monthly_races)}ヶ月分のみ存在します（12ヶ月期待）")
        print()

        # データカバレッジ
        print(f"--- {year}年 データカバレッジ ---")
        coverage = check_data_coverage(cursor, year)

        if coverage['total_races'] == 0:
            print(f"❌ {year}年のレースデータが存在しません")
            print()
            continue

        data_types = [
            ('出走表 (entries)', 'entries'),
            ('結果 (results)', 'results'),
            ('3連単オッズ (trifecta_odds)', 'trifecta_odds'),
            ('レース条件 (race_conditions)', 'race_conditions'),
            ('レース詳細 (race_details)', 'race_details'),
            ('払戻 (payouts)', 'payouts')
        ]

        all_complete = True
        for label, key in data_types:
            data = coverage[key]
            status = "✅" if data['coverage'] >= 99.9 else "⚠️"
            print(f"{status} {label}: {data['count']:,}/{coverage['total_races']:,}件 ({data['coverage']:.1f}%)")
            if data['coverage'] < 99.9:
                all_complete = False

        print()

        if all_complete:
            print(f"✅ {year}年の全データ種別が完備されています")
        else:
            print(f"⚠️ {year}年に欠損データがあります")

            # 欠損データの詳細
            print(f"\n--- {year}年 欠損データの例（最大10件） ---")
            missing = find_missing_data(cursor, year)

            for data_type, records in missing.items():
                if records:
                    print(f"\n{data_type}が欠けているレース:")
                    for venue, date, race_no in records[:10]:
                        print(f"  会場{venue}, {date}, R{race_no}")

        print()

    # 全体サマリー
    print("=" * 80)
    print("=== 総合判定 ===")
    print("=" * 80)
    print()

    # 2021年
    coverage_2021 = check_data_coverage(cursor, 2021)
    monthly_2021 = check_monthly_races(cursor, 2021)

    # 2023年
    coverage_2023 = check_data_coverage(cursor, 2023)
    monthly_2023 = check_monthly_races(cursor, 2023)

    all_ok = True

    # チェック項目
    checks = [
        ("日付形式の統一", 'YYYYMMDD' not in date_formats),
        ("2021年: 12ヶ月のデータ存在", len(monthly_2021) == 12),
        ("2021年: 出走表カバレッジ", coverage_2021.get('entries', {}).get('coverage', 0) >= 99.9),
        ("2021年: 結果カバレッジ", coverage_2021.get('results', {}).get('coverage', 0) >= 99.9),
        ("2021年: オッズカバレッジ", coverage_2021.get('trifecta_odds', {}).get('coverage', 0) >= 99.9),
        ("2021年: レース条件カバレッジ", coverage_2021.get('race_conditions', {}).get('coverage', 0) >= 99.9),
        ("2021年: レース詳細カバレッジ", coverage_2021.get('race_details', {}).get('coverage', 0) >= 99.9),
        ("2023年: 12ヶ月のデータ存在", len(monthly_2023) == 12),
        ("2023年: 出走表カバレッジ", coverage_2023.get('entries', {}).get('coverage', 0) >= 99.9),
        ("2023年: 結果カバレッジ", coverage_2023.get('results', {}).get('coverage', 0) >= 99.9),
        ("2023年: オッズカバレッジ", coverage_2023.get('trifecta_odds', {}).get('coverage', 0) >= 99.9),
        ("2023年: レース条件カバレッジ", coverage_2023.get('race_conditions', {}).get('coverage', 0) >= 99.9),
        ("2023年: レース詳細カバレッジ", coverage_2023.get('race_details', {}).get('coverage', 0) >= 99.9),
    ]

    for check_name, result in checks:
        status = "✅" if result else "❌"
        print(f"{status} {check_name}")
        if not result:
            all_ok = False

    print()
    print("=" * 80)

    if all_ok:
        print("🎉 データ収集完了！")
        print("   2021年・2023年の全データが正常に収集・投入されています。")
        print("   予測処理やバックテストの実行が可能です。")
    else:
        print("⚠️ データ収集が未完了です")
        print("   上記の❌項目を確認してください。")

    print("=" * 80)
    print()

    conn.close()
    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())
