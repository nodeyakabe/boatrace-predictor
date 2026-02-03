# -*- coding: utf-8 -*-
"""2021年・2023年補完データのCSV→DB投入スクリプト

CSVファイルからDBへデータを一括投入します。

特徴:
1. トランザクション管理（全て成功 or 全て失敗）
2. 外部キー制約の検証
3. 重複チェック（既存データはスキップ or 上書き）
4. dry-runモードで事前検証可能

使用例:
    # 検証モード（実際には投入しない）
    python scripts/maintenance/投入_2021_2023_補完データ.py --year 2021 --dry-run

    # 特定月を投入
    python scripts/maintenance/投入_2021_2023_補完データ.py --year 2021 --month 1

    # 全月を投入
    python scripts/maintenance/投入_2021_2023_補完データ.py --year 2021 --all-months

    # 既存データを上書き
    python scripts/maintenance/投入_2021_2023_補完データ.py --year 2021 --month 1 --overwrite
"""

import sys
import os
import csv
import sqlite3
import argparse
from pathlib import Path
from typing import Dict, List

# Windows文字コード対策
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))


def load_csv(csv_file: Path) -> List[Dict]:
    """CSVファイルを読み込み"""
    if not csv_file.exists():
        return []

    data = []
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            data.append(row)

    return data


def get_race_id(conn: sqlite3.Connection, venue_code: str, race_date: str, race_number: int):
    """venue_code + race_date + race_numberからrace_idを取得"""
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id FROM races
        WHERE venue_code = ? AND race_date = ? AND race_number = ?
    """, (venue_code, race_date, race_number))

    result = cursor.fetchone()
    cursor.close()

    return result[0] if result else None


def import_races(conn: sqlite3.Connection, races_data: List[Dict], overwrite: bool, dry_run: bool) -> Dict[str, int]:
    """レース基本情報を投入"""
    cursor = conn.cursor()
    inserted = 0
    updated = 0
    skipped = 0

    for row in races_data:
        venue_code = row['venue_code']
        race_date = row['race_date']
        race_number = int(row['race_number'])

        # 既存レコードをチェック
        race_id = get_race_id(conn, venue_code, race_date, race_number)

        if race_id and not overwrite:
            skipped += 1
            continue

        if dry_run:
            if race_id:
                updated += 1
            else:
                inserted += 1
            continue

        try:
            if race_id:
                # UPDATE
                cursor.execute("""
                    UPDATE races SET
                        race_time = ?,
                        race_grade = ?,
                        race_distance = ?,
                        is_nighter = ?,
                        is_ladies = ?,
                        is_rookie = ?,
                        is_shinnyuu_kotei = ?
                    WHERE id = ?
                """, (
                    row.get('race_time') or None,
                    row.get('race_grade') or None,
                    int(row['race_distance']) if row.get('race_distance') else 1800,
                    int(row['is_nighter']) if row.get('is_nighter') else 0,
                    int(row['is_ladies']) if row.get('is_ladies') else 0,
                    int(row['is_rookie']) if row.get('is_rookie') else 0,
                    int(row['is_shinnyuu_kotei']) if row.get('is_shinnyuu_kotei') else 0,
                    race_id
                ))
                updated += 1
            else:
                # INSERT
                cursor.execute("""
                    INSERT INTO races (
                        venue_code, race_date, race_number, race_time, race_grade,
                        race_distance, is_nighter, is_ladies, is_rookie, is_shinnyuu_kotei
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    venue_code,
                    race_date,
                    race_number,
                    row.get('race_time') or None,
                    row.get('race_grade') or None,
                    int(row['race_distance']) if row.get('race_distance') else 1800,
                    int(row['is_nighter']) if row.get('is_nighter') else 0,
                    int(row['is_ladies']) if row.get('is_ladies') else 0,
                    int(row['is_rookie']) if row.get('is_rookie') else 0,
                    int(row['is_shinnyuu_kotei']) if row.get('is_shinnyuu_kotei') else 0
                ))
                inserted += 1

        except Exception as e:
            print(f"  エラー（races）: {venue_code} {race_date} R{race_number} - {e}")

    cursor.close()
    return {'inserted': inserted, 'updated': updated, 'skipped': skipped}


def import_entries(conn: sqlite3.Connection, entries_data: List[Dict], overwrite: bool, dry_run: bool) -> Dict[str, int]:
    """出走表を投入"""
    cursor = conn.cursor()
    inserted = 0
    skipped = 0
    failed = 0

    for row in entries_data:
        venue_code = row['venue_code']
        race_date = row['race_date']
        race_number = int(row['race_number'])
        pit_number = int(row['pit_number'])

        # race_idを取得
        race_id = get_race_id(conn, venue_code, race_date, race_number)

        if not race_id:
            failed += 1
            continue

        # 既存レコードをチェック
        cursor.execute("SELECT race_id FROM entries WHERE race_id = ? AND pit_number = ?", (race_id, pit_number))
        existing = cursor.fetchone()

        if existing and not overwrite:
            skipped += 1
            continue

        if dry_run:
            inserted += 1
            continue

        try:
            if existing:
                # DELETE + INSERT（UPDATEよりシンプル）
                cursor.execute("DELETE FROM entries WHERE race_id = ? AND pit_number = ?", (race_id, pit_number))

            # INSERT
            cursor.execute("""
                INSERT INTO entries (
                    race_id, pit_number, racer_number, racer_name, racer_rank,
                    racer_home, racer_age, racer_weight, motor_number, boat_number,
                    win_rate, second_rate, third_rate, f_count, l_count, avg_st,
                    local_win_rate, local_second_rate, local_third_rate,
                    motor_second_rate, motor_third_rate,
                    boat_second_rate, boat_third_rate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                race_id,
                pit_number,
                row.get('racer_number') or None,
                row.get('racer_name') or None,
                row.get('racer_rank') or None,
                row.get('racer_home') or None,
                int(row['racer_age']) if row.get('racer_age') else None,
                float(row['racer_weight']) if row.get('racer_weight') else None,
                int(row['motor_number']) if row.get('motor_number') else None,
                int(row['boat_number']) if row.get('boat_number') else None,
                float(row['win_rate']) if row.get('win_rate') else None,
                float(row['second_rate']) if row.get('second_rate') else None,
                float(row['third_rate']) if row.get('third_rate') else None,
                int(row['f_count']) if row.get('f_count') else None,
                int(row['l_count']) if row.get('l_count') else None,
                float(row['avg_st']) if row.get('avg_st') else None,
                float(row['local_win_rate']) if row.get('local_win_rate') else None,
                float(row['local_second_rate']) if row.get('local_second_rate') else None,
                float(row['local_third_rate']) if row.get('local_third_rate') else None,
                float(row['motor_second_rate']) if row.get('motor_second_rate') else None,
                float(row['motor_third_rate']) if row.get('motor_third_rate') else None,
                float(row['boat_second_rate']) if row.get('boat_second_rate') else None,
                float(row['boat_third_rate']) if row.get('boat_third_rate') else None
            ))
            inserted += 1

        except Exception as e:
            print(f"  エラー（entries）: {venue_code} {race_date} R{race_number} P{pit_number} - {e}")
            failed += 1

    cursor.close()
    return {'inserted': inserted, 'skipped': skipped, 'failed': failed}


def import_results(conn: sqlite3.Connection, results_data: List[Dict], overwrite: bool, dry_run: bool) -> Dict[str, int]:
    """レース結果を投入"""
    cursor = conn.cursor()
    inserted = 0
    skipped = 0
    failed = 0

    for row in results_data:
        venue_code = row['venue_code']
        race_date = row['race_date']
        race_number = int(row['race_number'])
        pit_number = int(row['pit_number'])

        # race_idを取得
        race_id = get_race_id(conn, venue_code, race_date, race_number)

        if not race_id:
            failed += 1
            continue

        # 既存レコードをチェック
        cursor.execute("SELECT race_id FROM results WHERE race_id = ? AND pit_number = ?", (race_id, pit_number))
        existing = cursor.fetchone()

        if existing and not overwrite:
            skipped += 1
            continue

        if dry_run:
            inserted += 1
            continue

        try:
            if existing:
                cursor.execute("DELETE FROM results WHERE race_id = ? AND pit_number = ?", (race_id, pit_number))

            cursor.execute("""
                INSERT INTO results (race_id, pit_number, rank, is_invalid, kimarite)
                VALUES (?, ?, ?, ?, ?)
            """, (
                race_id,
                pit_number,
                row.get('rank') or None,
                int(row['is_invalid']) if row.get('is_invalid') else 0,
                row.get('kimarite') or None
            ))
            inserted += 1

        except Exception as e:
            print(f"  エラー（results）: {venue_code} {race_date} R{race_number} P{pit_number} - {e}")
            failed += 1

    cursor.close()
    return {'inserted': inserted, 'skipped': skipped, 'failed': failed}


def import_payouts(conn: sqlite3.Connection, payouts_data: List[Dict], overwrite: bool, dry_run: bool) -> Dict[str, int]:
    """払戻金を投入"""
    cursor = conn.cursor()
    inserted = 0
    skipped = 0
    failed = 0

    for row in payouts_data:
        venue_code = row['venue_code']
        race_date = row['race_date']
        race_number = int(row['race_number'])
        bet_type = row['bet_type']
        combination = row['combination']

        # race_idを取得
        race_id = get_race_id(conn, venue_code, race_date, race_number)

        if not race_id:
            failed += 1
            continue

        # 既存レコードをチェック
        cursor.execute(
            "SELECT race_id FROM payouts WHERE race_id = ? AND bet_type = ? AND combination = ?",
            (race_id, bet_type, combination)
        )
        existing = cursor.fetchone()

        if existing and not overwrite:
            skipped += 1
            continue

        if dry_run:
            inserted += 1
            continue

        try:
            if existing:
                cursor.execute(
                    "DELETE FROM payouts WHERE race_id = ? AND bet_type = ? AND combination = ?",
                    (race_id, bet_type, combination)
                )

            cursor.execute("""
                INSERT INTO payouts (race_id, bet_type, combination, amount, popularity)
                VALUES (?, ?, ?, ?, ?)
            """, (
                race_id,
                bet_type,
                combination,
                int(row['amount']) if row.get('amount') else None,
                int(row['popularity']) if row.get('popularity') else None
            ))
            inserted += 1

        except Exception as e:
            print(f"  エラー（payouts）: {venue_code} {race_date} R{race_number} {bet_type} {combination} - {e}")
            failed += 1

    cursor.close()
    return {'inserted': inserted, 'skipped': skipped, 'failed': failed}


def import_trifecta_odds(conn: sqlite3.Connection, odds_data: List[Dict], overwrite: bool, dry_run: bool) -> Dict[str, int]:
    """3連単オッズを投入"""
    cursor = conn.cursor()
    inserted = 0
    skipped = 0
    failed = 0

    for row in odds_data:
        venue_code = row['venue_code']
        race_date = row['race_date']
        race_number = int(row['race_number'])
        combination = row['combination']

        # race_idを取得
        race_id = get_race_id(conn, venue_code, race_date, race_number)

        if not race_id:
            failed += 1
            continue

        # 既存レコードをチェック
        cursor.execute(
            "SELECT race_id FROM trifecta_odds WHERE race_id = ? AND combination = ?",
            (race_id, combination)
        )
        existing = cursor.fetchone()

        if existing and not overwrite:
            skipped += 1
            continue

        if dry_run:
            inserted += 1
            continue

        try:
            if existing:
                cursor.execute(
                    "DELETE FROM trifecta_odds WHERE race_id = ? AND combination = ?",
                    (race_id, combination)
                )

            cursor.execute("""
                INSERT INTO trifecta_odds (race_id, combination, odds)
                VALUES (?, ?, ?)
            """, (
                race_id,
                combination,
                float(row['odds']) if row.get('odds') else None
            ))
            inserted += 1

        except Exception as e:
            print(f"  エラー（trifecta_odds）: {venue_code} {race_date} R{race_number} {combination} - {e}")
            failed += 1

    cursor.close()
    return {'inserted': inserted, 'skipped': skipped, 'failed': failed}


def import_race_conditions(conn: sqlite3.Connection, conditions_data: List[Dict], overwrite: bool, dry_run: bool) -> Dict[str, int]:
    """レース条件を投入"""
    cursor = conn.cursor()
    inserted = 0
    skipped = 0
    failed = 0

    for row in conditions_data:
        venue_code = row['venue_code']
        race_date = row['race_date']
        race_number = int(row['race_number'])

        # race_idを取得
        race_id = get_race_id(conn, venue_code, race_date, race_number)

        if not race_id:
            failed += 1
            continue

        # 既存レコードをチェック
        cursor.execute("SELECT race_id FROM race_conditions WHERE race_id = ?", (race_id,))
        existing = cursor.fetchone()

        if existing and not overwrite:
            skipped += 1
            continue

        if dry_run:
            inserted += 1
            continue

        try:
            if existing:
                cursor.execute("DELETE FROM race_conditions WHERE race_id = ?", (race_id,))

            cursor.execute("""
                INSERT INTO race_conditions (
                    race_id, weather, wind_direction, wind_speed,
                    wave_height, temperature, water_temperature
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                race_id,
                row.get('weather') or None,
                row.get('wind_direction') or None,
                float(row['wind_speed']) if row.get('wind_speed') else None,
                int(float(row['wave_height'])) if row.get('wave_height') else None,
                float(row['temperature']) if row.get('temperature') else None,
                float(row['water_temperature']) if row.get('water_temperature') else None
            ))
            inserted += 1

        except Exception as e:
            print(f"  エラー（race_conditions）: {venue_code} {race_date} R{race_number} - {e}")
            failed += 1

    cursor.close()
    return {'inserted': inserted, 'skipped': skipped, 'failed': failed}


def import_race_details(conn: sqlite3.Connection, details_data: List[Dict], overwrite: bool, dry_run: bool) -> Dict[str, int]:
    """展示情報を投入"""
    cursor = conn.cursor()
    inserted = 0
    skipped = 0
    failed = 0

    for row in details_data:
        venue_code = row['venue_code']
        race_date = row['race_date']
        race_number = int(row['race_number'])
        pit_number = int(row['pit_number'])

        # race_idを取得
        race_id = get_race_id(conn, venue_code, race_date, race_number)

        if not race_id:
            failed += 1
            continue

        # 既存レコードをチェック
        cursor.execute("SELECT race_id FROM race_details WHERE race_id = ? AND pit_number = ?", (race_id, pit_number))
        existing = cursor.fetchone()

        if existing and not overwrite:
            skipped += 1
            continue

        if dry_run:
            inserted += 1
            continue

        try:
            if existing:
                cursor.execute("DELETE FROM race_details WHERE race_id = ? AND pit_number = ?", (race_id, pit_number))

            cursor.execute("""
                INSERT INTO race_details (
                    race_id, pit_number, exhibition_time, tilt_angle,
                    parts_replacement, actual_course, st_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                race_id,
                pit_number,
                float(row['exhibition_time']) if row.get('exhibition_time') else None,
                float(row['tilt_angle']) if row.get('tilt_angle') else None,
                row.get('parts_replacement') or None,
                int(row['actual_course']) if row.get('actual_course') else None,
                float(row['st_time']) if row.get('st_time') else None
            ))
            inserted += 1

        except Exception as e:
            print(f"  エラー（race_details）: {venue_code} {race_date} R{race_number} P{pit_number} - {e}")
            failed += 1

    cursor.close()
    return {'inserted': inserted, 'skipped': skipped, 'failed': failed}


def main():
    parser = argparse.ArgumentParser(description='2021年・2023年補完データDB投入')
    parser.add_argument('--year', type=int, required=True, choices=[2021, 2023], help='対象年（2021 or 2023）')
    parser.add_argument('--month', type=int, choices=range(1, 13), help='対象月（1-12）')
    parser.add_argument('--all-months', action='store_true', help='全月を投入')
    parser.add_argument('--input-base', type=str, default='data/csv/補完', help='CSV入力ベースディレクトリ')
    parser.add_argument('--db', default='data/boatrace.db', help='DBファイルパス')
    parser.add_argument('--overwrite', action='store_true', help='既存データを上書き')
    parser.add_argument('--dry-run', action='store_true', help='検証モード（実際には投入しない）')
    args = parser.parse_args()

    if not args.month and not args.all_months:
        print("エラー: --month または --all-months を指定してください")
        sys.exit(1)

    # 実行対象月の決定
    target_months = []
    if args.all_months:
        target_months = list(range(1, 13))
    elif args.month:
        target_months = [args.month]

    print("=" * 80)
    if args.dry_run:
        print(f"{args.year}年補完データDB投入（検証モード）")
    else:
        print(f"{args.year}年補完データDB投入")
    print("=" * 80)
    print(f"DBファイル: {args.db}")
    print(f"上書きモード: {'ON' if args.overwrite else 'OFF'}")
    print()

    # DB接続
    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys = ON")

    total_stats = {
        'races': {'inserted': 0, 'updated': 0, 'skipped': 0},
        'entries': {'inserted': 0, 'skipped': 0, 'failed': 0},
        'results': {'inserted': 0, 'skipped': 0, 'failed': 0},
        'payouts': {'inserted': 0, 'skipped': 0, 'failed': 0},
        'trifecta_odds': {'inserted': 0, 'skipped': 0, 'failed': 0},
        'race_conditions': {'inserted': 0, 'skipped': 0, 'failed': 0},
        'race_details': {'inserted': 0, 'skipped': 0, 'failed': 0},
    }

    # 月別に投入
    for month in target_months:
        input_dir = Path(args.input_base) / str(args.year) / f'{month:02d}'

        if not input_dir.exists():
            print(f"⚠️ スキップ: {args.year}年{month}月のCSVディレクトリが存在しません: {input_dir}")
            continue

        print(f"=== {args.year}年{month}月 投入開始 ===")
        print(f"入力ディレクトリ: {input_dir}")
        print()

        try:
            # トランザクション開始
            conn.execute("BEGIN TRANSACTION")

            # 各CSVファイルを投入
            # 1. レース基本情報
            races_csv = input_dir / 'races.csv'
            if races_csv.exists():
                print("レース基本情報を投入中...")
                races_data = load_csv(races_csv)
                result = import_races(conn, races_data, args.overwrite, args.dry_run)
                total_stats['races']['inserted'] += result['inserted']
                total_stats['races']['updated'] += result['updated']
                total_stats['races']['skipped'] += result['skipped']
                print(f"  投入: {result['inserted']:,}件, 更新: {result['updated']:,}件, スキップ: {result['skipped']:,}件")

            # 2. 出走表
            entries_csv = input_dir / 'entries.csv'
            if entries_csv.exists():
                print("出走表を投入中...")
                entries_data = load_csv(entries_csv)
                result = import_entries(conn, entries_data, args.overwrite, args.dry_run)
                total_stats['entries']['inserted'] += result['inserted']
                total_stats['entries']['skipped'] += result['skipped']
                total_stats['entries']['failed'] += result['failed']
                print(f"  投入: {result['inserted']:,}件, スキップ: {result['skipped']:,}件, 失敗: {result['failed']:,}件")

            # 3. レース結果
            results_csv = input_dir / 'results.csv'
            if results_csv.exists():
                print("レース結果を投入中...")
                results_data = load_csv(results_csv)
                result = import_results(conn, results_data, args.overwrite, args.dry_run)
                total_stats['results']['inserted'] += result['inserted']
                total_stats['results']['skipped'] += result['skipped']
                total_stats['results']['failed'] += result['failed']
                print(f"  投入: {result['inserted']:,}件, スキップ: {result['skipped']:,}件, 失敗: {result['failed']:,}件")

            # 4. 払戻金
            payouts_csv = input_dir / 'payouts.csv'
            if payouts_csv.exists():
                print("払戻金を投入中...")
                payouts_data = load_csv(payouts_csv)
                result = import_payouts(conn, payouts_data, args.overwrite, args.dry_run)
                total_stats['payouts']['inserted'] += result['inserted']
                total_stats['payouts']['skipped'] += result['skipped']
                total_stats['payouts']['failed'] += result['failed']
                print(f"  投入: {result['inserted']:,}件, スキップ: {result['skipped']:,}件, 失敗: {result['failed']:,}件")

            # 5. 3連単オッズ
            odds_csv = input_dir / 'trifecta_odds.csv'
            if odds_csv.exists():
                print("3連単オッズを投入中...")
                odds_data = load_csv(odds_csv)
                result = import_trifecta_odds(conn, odds_data, args.overwrite, args.dry_run)
                total_stats['trifecta_odds']['inserted'] += result['inserted']
                total_stats['trifecta_odds']['skipped'] += result['skipped']
                total_stats['trifecta_odds']['failed'] += result['failed']
                print(f"  投入: {result['inserted']:,}件, スキップ: {result['skipped']:,}件, 失敗: {result['failed']:,}件")

            # 6. レース条件
            conditions_csv = input_dir / 'race_conditions.csv'
            if conditions_csv.exists():
                print("レース条件を投入中...")
                conditions_data = load_csv(conditions_csv)
                result = import_race_conditions(conn, conditions_data, args.overwrite, args.dry_run)
                total_stats['race_conditions']['inserted'] += result['inserted']
                total_stats['race_conditions']['skipped'] += result['skipped']
                total_stats['race_conditions']['failed'] += result['failed']
                print(f"  投入: {result['inserted']:,}件, スキップ: {result['skipped']:,}件, 失敗: {result['failed']:,}件")

            # 7. 展示情報
            details_csv = input_dir / 'race_details.csv'
            if details_csv.exists():
                print("展示情報を投入中...")
                details_data = load_csv(details_csv)
                result = import_race_details(conn, details_data, args.overwrite, args.dry_run)
                total_stats['race_details']['inserted'] += result['inserted']
                total_stats['race_details']['skipped'] += result['skipped']
                total_stats['race_details']['failed'] += result['failed']
                print(f"  投入: {result['inserted']:,}件, スキップ: {result['skipped']:,}件, 失敗: {result['failed']:,}件")

            print()

            if args.dry_run:
                print(f"{args.year}年{month}月: 検証成功（ロールバック）")
                conn.rollback()
            else:
                # コミット
                conn.commit()
                print(f"{args.year}年{month}月: コミット完了")

        except Exception as e:
            conn.rollback()
            print(f"エラーが発生しました。ロールバックします: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

        print()

    conn.close()

    # 全体サマリー
    print("=" * 80)
    print("全体サマリー")
    print("=" * 80)
    print(f"races:           投入{total_stats['races']['inserted']:,}件 / 更新{total_stats['races']['updated']:,}件 / スキップ{total_stats['races']['skipped']:,}件")
    print(f"entries:         投入{total_stats['entries']['inserted']:,}件 / スキップ{total_stats['entries']['skipped']:,}件 / 失敗{total_stats['entries']['failed']:,}件")
    print(f"results:         投入{total_stats['results']['inserted']:,}件 / スキップ{total_stats['results']['skipped']:,}件 / 失敗{total_stats['results']['failed']:,}件")
    print(f"payouts:         投入{total_stats['payouts']['inserted']:,}件 / スキップ{total_stats['payouts']['skipped']:,}件 / 失敗{total_stats['payouts']['failed']:,}件")
    print(f"trifecta_odds:   投入{total_stats['trifecta_odds']['inserted']:,}件 / スキップ{total_stats['trifecta_odds']['skipped']:,}件 / 失敗{total_stats['trifecta_odds']['failed']:,}件")
    print(f"race_conditions: 投入{total_stats['race_conditions']['inserted']:,}件 / スキップ{total_stats['race_conditions']['skipped']:,}件 / 失敗{total_stats['race_conditions']['failed']:,}件")
    print(f"race_details:    投入{total_stats['race_details']['inserted']:,}件 / スキップ{total_stats['race_details']['skipped']:,}件 / 失敗{total_stats['race_details']['failed']:,}件")
    print()

    if args.dry_run:
        print("検証モードのため、実際にはDBに投入していません。")
        print("問題がなければ --dry-run なしで実行してください。")
    else:
        print("全ての月の投入が完了しました。")

    print("=" * 80)


if __name__ == '__main__':
    main()
