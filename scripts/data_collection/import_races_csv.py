"""
fetch_to_csv_parallel_improved.py が生成した CSV を DB に投入するスクリプト

【対象CSVファイル（1ディレクトリに格納）】
  races.csv         - レース基本情報
  entries.csv       - 出走表（選手・モーター・ボート）
  results.csv       - レース結果（着順・決まり手）
  race_details.csv  - 展示情報（展示タイム・チルト・実際のコース）
  race_conditions.csv - レース条件（天候・風・波）
  payouts.csv       - 払戻金（オプション、通常はimport_payouts_csv.pyで投入）

【使用例】
  # ドライランで件数確認のみ
  python scripts/data_collection/import_races_csv.py --dir data/csv/2024_補完 --dry-run

  # 投入実行
  python scripts/data_collection/import_races_csv.py --dir data/csv/2024_補完

  # 複数ディレクトリ
  python scripts/data_collection/import_races_csv.py \\
    --dir data/csv/2024_01 --dir data/csv/2024_08 --dir data/csv/2024_09

【投入順序】
  1. races        → ON CONFLICT(venue_code, race_date, race_number) DO UPDATE
  2. entries      → race_idルックアップ後 DELETE + INSERT
  3. results      → race_idルックアップ後 DELETE + INSERT（UNIQUE: race_id, pit_number）
  4. race_details → race_idルックアップ後 INSERT OR REPLACE（UNIQUE: race_id, pit_number）
  5. race_conditions → race_idルックアップ後 DELETE + INSERT

【日付形式】
  CSV内のrace_date: YYYYMMDD形式（例: 20240101）
  DB内のrace_date: YYYY-MM-DD形式（例: 2024-01-01）
  → このスクリプトで自動変換します
"""
import sys
import io
import os
import csv
import argparse
import sqlite3
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

DB_PATH = "data/boatrace.db"
BATCH_SIZE = 500


def fmt_date(race_date_str: str) -> str:
    """YYYYMMDD → YYYY-MM-DD 変換（既に変換済みの場合はそのまま）"""
    s = str(race_date_str).strip()
    if len(s) == 8 and '-' not in s:
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s  # 既にYYYY-MM-DD形式


def safe_int(v):
    try:
        return int(v) if v not in (None, '', 'None') else None
    except (ValueError, TypeError):
        return None


def safe_float(v):
    try:
        return float(v) if v not in (None, '', 'None') else None
    except (ValueError, TypeError):
        return None


def safe_str(v):
    s = str(v).strip() if v not in (None, '', 'None') else None
    return s if s else None


def read_csv(csv_path: Path) -> list:
    """CSVファイルを読み込む"""
    if not csv_path.exists():
        return []
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            return list(csv.DictReader(f))
    except Exception as e:
        print(f"  [!] CSV読み込みエラー {csv_path.name}: {e}")
        return []


def build_race_id_map(conn, rows: list) -> dict:
    """
    (venue_code, race_date_YYYYMMDD, race_number) → race_id のマップを構築
    DBから一括ルックアップ
    """
    if not rows:
        return {}

    # ユニークな(venue_code, race_date, race_number)を収集
    keys = set()
    for row in rows:
        vc = row.get('venue_code', '')
        rd = fmt_date(row.get('race_date', ''))
        rn = safe_int(row.get('race_number'))
        if vc and rd and rn is not None:
            keys.add((vc, rd, rn))

    if not keys:
        return {}

    # バッチクエリ
    race_id_map = {}
    cur = conn.cursor()
    keys_list = list(keys)

    # SQLiteのIN句の制限を回避するため500件ずつ
    for i in range(0, len(keys_list), BATCH_SIZE):
        batch = keys_list[i:i + BATCH_SIZE]
        placeholders = ','.join(['(?,?,?)'] * len(batch))
        flat_params = []
        for vc, rd, rn in batch:
            flat_params.extend([vc, rd, rn])

        cur.execute(f"""
            SELECT id, venue_code, race_date, race_number
            FROM races
            WHERE (venue_code, race_date, race_number) IN ({placeholders})
        """, flat_params)

        for race_id, vc, rd, rn in cur.fetchall():
            # race_dateはDB内でYYYY-MM-DD形式
            race_id_map[(vc, rd, rn)] = race_id

    return race_id_map


def lookup_race_id(race_id_map: dict, row: dict) -> int | None:
    """rowからrace_idを取得"""
    vc = row.get('venue_code', '')
    rd = fmt_date(row.get('race_date', ''))
    rn = safe_int(row.get('race_number'))
    return race_id_map.get((vc, rd, rn))


# ─── 各テーブルの投入処理 ───────────────────────────────────────────────────

def import_races(conn, rows: list, dry_run: bool) -> dict:
    """races テーブルへの UPSERT"""
    if not rows:
        return {'rows': 0, 'inserted': 0, 'errors': 0}

    if dry_run:
        return {'rows': len(rows), 'inserted': 0, 'errors': 0}

    sql = """
        INSERT INTO races
            (venue_code, race_date, race_number, race_time, race_grade,
             race_distance, is_nighter, is_ladies, is_rookie, is_shinnyuu_kotei)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(venue_code, race_date, race_number) DO UPDATE SET
            race_time         = excluded.race_time,
            race_grade        = excluded.race_grade,
            race_distance     = excluded.race_distance,
            is_nighter        = excluded.is_nighter,
            is_ladies         = excluded.is_ladies,
            is_rookie         = excluded.is_rookie,
            is_shinnyuu_kotei = excluded.is_shinnyuu_kotei
    """
    cur = conn.cursor()
    inserted = 0
    errors = 0

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        values_list = []
        for row in batch:
            try:
                values_list.append((
                    row['venue_code'],
                    fmt_date(row['race_date']),
                    safe_int(row['race_number']),
                    safe_str(row.get('race_time')),
                    safe_str(row.get('race_grade')),
                    safe_int(row.get('race_distance')),
                    safe_int(row.get('is_nighter', 0)),
                    safe_int(row.get('is_ladies', 0)),
                    safe_int(row.get('is_rookie', 0)),
                    safe_int(row.get('is_shinnyuu_kotei', 0)),
                ))
            except Exception:
                errors += 1

        try:
            cur.executemany(sql, values_list)
            inserted += len(values_list)
        except Exception as e:
            errors += len(values_list)
            print(f"  [!] races UPSERT エラー: {e}")

    conn.commit()
    return {'rows': len(rows), 'inserted': inserted, 'errors': errors}


def import_entries(conn, rows: list, race_id_map: dict, dry_run: bool) -> dict:
    """entries テーブルへの投入（race_id単位でDELETE+INSERT）"""
    if not rows:
        return {'rows': 0, 'inserted': 0, 'errors': 0}

    if dry_run:
        return {'rows': len(rows), 'inserted': 0, 'errors': 0}

    # race_idごとにグループ化（pit_numberで重複排除：後勝ち）
    by_race = {}
    for row in rows:
        rid = lookup_race_id(race_id_map, row)
        if rid is None:
            continue
        pit = row.get('pit_number')
        if rid not in by_race:
            by_race[rid] = {}
        by_race[rid][pit] = row

    cur = conn.cursor()
    inserted = 0
    errors = 0

    race_ids = list(by_race.keys())
    for i in range(0, len(race_ids), BATCH_SIZE):
        batch_ids = race_ids[i:i + BATCH_SIZE]

        # 既存データを削除
        placeholders = ','.join(['?'] * len(batch_ids))
        cur.execute(f"DELETE FROM entries WHERE race_id IN ({placeholders})", batch_ids)

        # 新データを挿入
        values_list = []
        for rid in batch_ids:
            for row in by_race[rid].values():
                try:
                    values_list.append((
                        rid,
                        safe_int(row.get('pit_number')),
                        safe_str(row.get('racer_number')),
                        safe_str(row.get('racer_name')),
                        safe_str(row.get('racer_rank')),
                        safe_str(row.get('racer_home')),
                        safe_int(row.get('racer_age')),
                        safe_float(row.get('racer_weight')),
                        safe_int(row.get('motor_number')),
                        safe_int(row.get('boat_number')),
                        safe_float(row.get('win_rate')),
                        safe_float(row.get('second_rate')),
                        safe_float(row.get('third_rate')),
                        safe_int(row.get('f_count')),
                        safe_int(row.get('l_count')),
                        safe_float(row.get('avg_st')),
                        safe_float(row.get('local_win_rate')),
                        safe_float(row.get('local_second_rate')),
                        safe_float(row.get('local_third_rate')),
                        safe_float(row.get('motor_second_rate')),
                        safe_float(row.get('motor_third_rate')),
                        safe_float(row.get('boat_second_rate')),
                        safe_float(row.get('boat_third_rate')),
                    ))
                except Exception:
                    errors += 1

        try:
            cur.executemany("""
                INSERT INTO entries (
                    race_id, pit_number, racer_number, racer_name,
                    racer_rank, racer_home, racer_age, racer_weight,
                    motor_number, boat_number,
                    win_rate, second_rate, third_rate,
                    f_count, l_count, avg_st,
                    local_win_rate, local_second_rate, local_third_rate,
                    motor_second_rate, motor_third_rate,
                    boat_second_rate, boat_third_rate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, values_list)
            inserted += len(values_list)
        except Exception as e:
            errors += len(values_list)
            print(f"  [!] entries INSERT エラー: {e}")

    conn.commit()
    return {'rows': len(rows), 'inserted': inserted, 'errors': errors}


def import_results(conn, rows: list, race_id_map: dict, dry_run: bool) -> dict:
    """results テーブルへの投入（race_id単位でDELETE+INSERT）"""
    if not rows:
        return {'rows': 0, 'inserted': 0, 'errors': 0}

    if dry_run:
        return {'rows': len(rows), 'inserted': 0, 'errors': 0}

    # race_idごとにグループ化（pit_numberで重複排除：後勝ち）
    by_race = {}
    for row in rows:
        rid = lookup_race_id(race_id_map, row)
        if rid is None:
            continue
        pit = row.get('pit_number')
        if rid not in by_race:
            by_race[rid] = {}
        by_race[rid][pit] = row

    cur = conn.cursor()
    inserted = 0
    errors = 0

    race_ids = list(by_race.keys())
    for i in range(0, len(race_ids), BATCH_SIZE):
        batch_ids = race_ids[i:i + BATCH_SIZE]

        # 既存データを削除
        placeholders = ','.join(['?'] * len(batch_ids))
        cur.execute(f"DELETE FROM results WHERE race_id IN ({placeholders})", batch_ids)

        # 新データを挿入
        values_list = []
        for rid in batch_ids:
            for row in by_race[rid].values():
                try:
                    values_list.append((
                        rid,
                        safe_int(row.get('pit_number')),
                        safe_str(row.get('rank')),
                        safe_int(row.get('is_invalid', 0)),
                        safe_str(row.get('kimarite')),
                    ))
                except Exception:
                    errors += 1

        try:
            cur.executemany("""
                INSERT INTO results (race_id, pit_number, rank, is_invalid, kimarite)
                VALUES (?, ?, ?, ?, ?)
            """, values_list)
            inserted += len(values_list)
        except Exception as e:
            errors += len(values_list)
            print(f"  [!] results INSERT エラー: {e}")

    conn.commit()
    return {'rows': len(rows), 'inserted': inserted, 'errors': errors}


def import_race_details(conn, rows: list, race_id_map: dict, dry_run: bool) -> dict:
    """race_details テーブルへの投入（INSERT OR REPLACE）"""
    if not rows:
        return {'rows': 0, 'inserted': 0, 'errors': 0}

    if dry_run:
        return {'rows': len(rows), 'inserted': 0, 'errors': 0}

    cur = conn.cursor()
    inserted = 0
    errors = 0

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        values_list = []
        for row in batch:
            rid = lookup_race_id(race_id_map, row)
            if rid is None:
                continue
            try:
                values_list.append((
                    rid,
                    safe_int(row.get('pit_number')),
                    safe_float(row.get('exhibition_time')),
                    safe_float(row.get('tilt_angle')),
                    safe_str(row.get('parts_replacement')),
                    safe_int(row.get('actual_course')),
                    safe_float(row.get('st_time')),
                ))
            except Exception:
                errors += 1

        if not values_list:
            continue

        try:
            cur.executemany("""
                INSERT INTO race_details
                    (race_id, pit_number, exhibition_time, tilt_angle,
                     parts_replacement, actual_course, st_time)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(race_id, pit_number) DO UPDATE SET
                    actual_course     = COALESCE(excluded.actual_course, actual_course),
                    st_time           = COALESCE(excluded.st_time, st_time),
                    exhibition_time   = COALESCE(excluded.exhibition_time, exhibition_time),
                    tilt_angle        = COALESCE(excluded.tilt_angle, tilt_angle),
                    parts_replacement = CASE
                        WHEN excluded.parts_replacement IS NOT NULL AND excluded.parts_replacement != ''
                        THEN excluded.parts_replacement
                        ELSE parts_replacement
                    END
            """, values_list)
            inserted += len(values_list)
        except Exception as e:
            errors += len(values_list)
            print(f"  [!] race_details INSERT エラー: {e}")

    conn.commit()
    return {'rows': len(rows), 'inserted': inserted, 'errors': errors}


def import_race_conditions(conn, rows: list, race_id_map: dict, dry_run: bool) -> dict:
    """race_conditions テーブルへの投入（race_id単位でDELETE+INSERT）"""
    if not rows:
        return {'rows': 0, 'inserted': 0, 'errors': 0}

    if dry_run:
        return {'rows': len(rows), 'inserted': 0, 'errors': 0}

    # race_idごとにグループ化（1レース1行のはず）
    by_race = {}
    for row in rows:
        rid = lookup_race_id(race_id_map, row)
        if rid is None:
            continue
        by_race[rid] = row  # 最後の行を使用

    cur = conn.cursor()
    inserted = 0
    errors = 0

    race_ids = list(by_race.keys())
    for i in range(0, len(race_ids), BATCH_SIZE):
        batch_ids = race_ids[i:i + BATCH_SIZE]

        # 既存データを削除
        placeholders = ','.join(['?'] * len(batch_ids))
        cur.execute(f"DELETE FROM race_conditions WHERE race_id IN ({placeholders})", batch_ids)

        values_list = []
        for rid in batch_ids:
            row = by_race[rid]
            try:
                values_list.append((
                    rid,
                    safe_str(row.get('weather')),
                    safe_str(row.get('wind_direction')),
                    safe_float(row.get('wind_speed')),
                    safe_float(row.get('wave_height')),
                    safe_float(row.get('temperature')),
                    safe_float(row.get('water_temperature')),
                ))
            except Exception:
                errors += 1

        try:
            cur.executemany("""
                INSERT INTO race_conditions
                    (race_id, weather, wind_direction, wind_speed,
                     wave_height, temperature, water_temperature)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, values_list)
            inserted += len(values_list)
        except Exception as e:
            errors += len(values_list)
            print(f"  [!] race_conditions INSERT エラー: {e}")

    conn.commit()
    return {'rows': len(rows), 'inserted': inserted, 'errors': errors}


def import_payouts(conn, rows: list, race_id_map: dict, dry_run: bool) -> dict:
    """payouts テーブルへの投入（ON CONFLICT DO UPDATE）"""
    if not rows:
        return {'rows': 0, 'inserted': 0, 'errors': 0}

    if dry_run:
        return {'rows': len(rows), 'inserted': 0, 'errors': 0}

    sql = """
        INSERT INTO payouts (race_id, bet_type, combination, amount, popularity)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(race_id, bet_type, combination) DO UPDATE SET
            amount     = excluded.amount,
            popularity = excluded.popularity
    """
    cur = conn.cursor()
    inserted = 0
    errors = 0

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        values_list = []
        for row in batch:
            rid = lookup_race_id(race_id_map, row)
            if rid is None:
                continue
            try:
                values_list.append((
                    rid,
                    safe_str(row.get('bet_type')),
                    safe_str(row.get('combination')),
                    safe_int(row.get('amount')),
                    safe_int(row.get('popularity')),
                ))
            except Exception:
                errors += 1

        if not values_list:
            continue

        try:
            cur.executemany(sql, values_list)
            inserted += len(values_list)
        except Exception as e:
            errors += len(values_list)
            print(f"  [!] payouts UPSERT エラー: {e}")

    conn.commit()
    return {'rows': len(rows), 'inserted': inserted, 'errors': errors}


# ─── メイン処理 ───────────────────────────────────────────────────────────────

def process_directory(conn, csv_dir: Path, dry_run: bool) -> dict:
    """1ディレクトリのCSVを投入"""
    print(f"\n  ディレクトリ: {csv_dir}")

    # CSVファイル読み込み
    races_rows    = read_csv(csv_dir / 'races.csv')
    entries_rows  = read_csv(csv_dir / 'entries.csv')
    results_rows  = read_csv(csv_dir / 'results.csv')
    details_rows  = read_csv(csv_dir / 'race_details.csv')
    cond_rows     = read_csv(csv_dir / 'race_conditions.csv')
    payouts_rows  = read_csv(csv_dir / 'payouts.csv')

    print(f"  races: {len(races_rows)}行 / entries: {len(entries_rows)}行 / "
          f"results: {len(results_rows)}行 / details: {len(details_rows)}行 / "
          f"conditions: {len(cond_rows)}行 / payouts: {len(payouts_rows)}行")

    if not races_rows:
        print("  [!] races.csv が空またはなし → スキップ")
        return {}

    # Step 1: races 投入
    r_result = import_races(conn, races_rows, dry_run)
    print(f"  [1/5] races:          {r_result['inserted']:,}件投入 / {r_result['errors']:,}件エラー")

    # race_idマップ構築（投入後にDBから取得）
    if dry_run:
        race_id_map = {}
    else:
        # races + entries + results + details + conditions + payouts 全てのrowからrace_idを逆引き
        all_rows = entries_rows + results_rows + details_rows + cond_rows + payouts_rows
        race_id_map = build_race_id_map(conn, all_rows)

    # Step 2: entries 投入
    e_result = import_entries(conn, entries_rows, race_id_map, dry_run)
    print(f"  [2/5] entries:        {e_result['inserted']:,}件投入 / {e_result['errors']:,}件エラー")

    # Step 3: results 投入
    res_result = import_results(conn, results_rows, race_id_map, dry_run)
    print(f"  [3/5] results:        {res_result['inserted']:,}件投入 / {res_result['errors']:,}件エラー")

    # Step 4: race_details 投入
    det_result = import_race_details(conn, details_rows, race_id_map, dry_run)
    print(f"  [4/5] race_details:   {det_result['inserted']:,}件投入 / {det_result['errors']:,}件エラー")

    # Step 5: race_conditions 投入
    con_result = import_race_conditions(conn, cond_rows, race_id_map, dry_run)
    print(f"  [5/6] race_conditions:{con_result['inserted']:,}件投入 / {con_result['errors']:,}件エラー")

    # Step 6: payouts 投入（payouts.csvが存在する場合のみ）
    pay_result = import_payouts(conn, payouts_rows, race_id_map, dry_run)
    print(f"  [6/6] payouts:        {pay_result['inserted']:,}件投入 / {pay_result['errors']:,}件エラー")

    return {
        'races':           r_result,
        'entries':         e_result,
        'results':         res_result,
        'race_details':    det_result,
        'race_conditions': con_result,
        'payouts':         pay_result,
    }


def main():
    parser = argparse.ArgumentParser(
        description='fetch_to_csv_parallel_improved.py 生成CSVをDBに投入',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--dir', action='append', metavar='CSV_DIR', dest='dirs',
                        help='CSVが格納されたディレクトリ（複数指定可）')
    parser.add_argument('--dry-run', action='store_true',
                        help='DB投入せず件数確認のみ')
    args = parser.parse_args()

    if not args.dirs:
        parser.print_help()
        sys.exit(1)

    # ディレクトリ確認
    csv_dirs = []
    for d in args.dirs:
        p = Path(d)
        if not p.is_dir():
            print(f"[!] ディレクトリが存在しません: {d}")
            sys.exit(1)
        csv_dirs.append(p)

    print("=" * 80)
    print("races/entries/results/race_details/race_conditions CSV → DB 投入")
    print(f"{'[DRY-RUN] ' if args.dry_run else ''}対象ディレクトリ: {len(csv_dirs)}個")
    print("=" * 80)
    if args.dry_run:
        print("[DRY-RUN] DB投入はしません。件数確認のみ。")

    conn = None
    if not args.dry_run:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

    import time
    start_time = time.time()

    totals = {
        'races': 0, 'entries': 0, 'results': 0,
        'race_details': 0, 'race_conditions': 0, 'payouts': 0
    }

    for csv_dir in csv_dirs:
        result = process_directory(conn, csv_dir, args.dry_run)
        for key in totals:
            if key in result:
                totals[key] += result[key].get('inserted', result[key].get('rows', 0))

    if conn:
        conn.close()

    elapsed = time.time() - start_time

    print("\n" + "=" * 80)
    print(f"{'[DRY-RUN] ' if args.dry_run else ''}処理完了")
    print("=" * 80)
    print(f"races:           {totals['races']:,}件")
    print(f"entries:         {totals['entries']:,}件")
    print(f"results:         {totals['results']:,}件")
    print(f"race_details:    {totals['race_details']:,}件")
    print(f"race_conditions: {totals['race_conditions']:,}件")
    print(f"payouts:         {totals['payouts']:,}件")
    print(f"処理時間:        {elapsed:.1f}秒")
    print("=" * 80)


if __name__ == "__main__":
    main()
