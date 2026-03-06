#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
race_conditions 一括補完スクリプト（CSV方式・高速版）

欠損している race_conditions（天気・風向・風速・波高・気温・水温）を
レース結果ページからスクレイピングして補完する。

CSV方式（Phase 1: 収集→CSV / Phase 2: CSV→DB）を採用。
weather1 要素だけを解析する軽量スクレイパーを使用して高速化。

使用例:
    # 2024年を補完（Phase 1 + 2 通しで実行）
    python scripts/data_collection/補完_race_conditions.py --start-date 2024-01-01 --end-date 2025-01-01

    # Phase 1のみ（CSVだけ生成）
    python scripts/data_collection/補完_race_conditions.py --start-date 2024-01-01 --end-date 2025-01-01 --csv-only

    # Phase 2のみ（既存CSVをDBに投入）
    python scripts/data_collection/補完_race_conditions.py --import-only --csv-dir data/csv/race_conditions

    # 欠損チェックのみ（DB変更なし）
    python scripts/data_collection/補完_race_conditions.py --check-only
"""
import sys
import os

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

os.environ['PYTHONUNBUFFERED'] = '1'

import csv
import time
import sqlite3
import argparse
import random
import requests
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
try:
    from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
except ImportError:
    from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "data" / "boatrace.db"
CSV_DIR = PROJECT_ROOT / "data" / "csv" / "race_conditions"

BOATRACE_URL = "https://www.boatrace.jp/owpc/pc/race/raceresult"

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
]

CSV_HEADER = ['race_id', 'weather', 'wind_direction', 'wind_speed', 'wave_height',
              'temperature', 'water_temperature']


# ---------------------------------------------------------------------------
# 軽量スクレイパー（weather1 要素だけ解析）
# ---------------------------------------------------------------------------

def _fetch_weather_from_page(venue_code: str, date_str: str, race_number: int) -> dict | None:
    """
    レース結果ページから weather1 要素だけ抽出（軽量版）。
    get_race_result_complete() より大幅に速い（不要な解析を全スキップ）。

    Returns:
        dict: {weather, wind_direction, wind_speed, wave_height, temperature, water_temperature}
        None: 取得失敗
    """
    params = {"rno": race_number, "jcd": venue_code, "hd": date_str}
    headers = {'User-Agent': random.choice(USER_AGENTS)}

    try:
        time.sleep(random.uniform(0.1, 0.25))   # delay 0.1〜0.25秒
        resp = requests.get(BOATRACE_URL, params=params, headers=headers, timeout=15)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, 'html.parser')

        # weather1 要素だけ取得（全ページ解析は不要）
        weather_elem = soup.find(class_='weather1')
        if not weather_elem:
            return None

        result = {
            'weather': None,
            'wind_direction': None,
            'wind_speed': None,
            'wave_height': None,
            'temperature': None,
            'water_temperature': None,
        }

        # 気温・風速・水温・波高
        for unit in weather_elem.find_all(class_='weather1_bodyUnit'):
            label_elem = unit.find(class_='weather1_bodyUnitLabelTitle')
            data_elem = unit.find(class_='weather1_bodyUnitLabelData')
            if not label_elem or not data_elem:
                continue
            label = label_elem.get_text(strip=True)
            raw = data_elem.get_text(strip=True)

            def to_float(s):
                import re
                m = re.search(r'[\d.]+', s)
                return float(m.group()) if m else None

            if '気温' in label:
                result['temperature'] = to_float(raw)
            elif '風' in label:
                result['wind_speed'] = to_float(raw)
            elif '水温' in label:
                result['water_temperature'] = to_float(raw)
            elif '波高' in label:
                val = to_float(raw)
                result['wave_height'] = int(val) if val is not None else None

        # 天気（beforeinfo_scraper / result_scraper と表記を統一）
        # is-weather クラスを持つ <div> 内の <p class="weather1_bodyUnitImage is-weatherN"> を見る
        weather_unit = weather_elem.find(class_='is-weather')
        if weather_unit:
            weather_p = weather_unit.find('p', class_='weather1_bodyUnitImage')
            if weather_p:
                weather_map = {'1': '晴', '2': '曇', '3': '雨', '4': '雪', '5': '霧', '6': '台風'}
                for cls in weather_p.get('class', []):
                    if cls.startswith('is-weather') and len(cls) > 10:
                        result['weather'] = weather_map.get(cls.replace('is-weather', ''), '不明')
                        break

        # 風向（16方位）
        wind_dir_elem = weather_elem.find(class_='is-windDirection')
        if wind_dir_elem:
            wind_img = wind_dir_elem.find('p')
            if wind_img:
                directions = ['北', '北北東', '北東', '東北東', '東', '東南東', '南東', '南南東',
                              '南', '南南西', '南西', '西南西', '西', '西北西', '北西', '北北西']
                for cls in wind_img.get('class', []):
                    if cls.startswith('is-wind') and not cls.startswith('is-windDirection') and len(cls) > 7:
                        try:
                            idx = int(cls.replace('is-wind', '')) - 1
                            if 0 <= idx < 16:
                                result['wind_direction'] = directions[idx]
                        except ValueError:
                            pass
                        break

        # 有効なデータが1つでもあれば返す
        if any(v is not None for v in result.values()):
            return result
        return None

    except Exception:
        return None


# ---------------------------------------------------------------------------
# DB クエリ
# ---------------------------------------------------------------------------

def get_races_needing_conditions(start_date: str, end_date: str) -> list:
    """race_conditions が欠損しているレースを取得。
    results が存在するレースのみを対象とする（results なし = 引き波・中止等は
    レース結果ページに weather1 が存在しないため取得不可）。
    """
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("""
        SELECT r.id, r.venue_code, r.race_date, r.race_number
        FROM races r
        LEFT JOIN race_conditions rc ON r.id = rc.race_id
        WHERE r.race_date >= ? AND r.race_date < ?
          AND rc.race_id IS NULL
          AND EXISTS (SELECT 1 FROM results res WHERE res.race_id = r.id)
        ORDER BY r.race_date, r.venue_code, r.race_number
    """, (start_date, end_date))
    rows = cur.fetchall()
    conn.close()
    return rows


def check_current_status(start_date: str, end_date: str):
    """現在の充足率を月別表示（results有りレースのみ分母）"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()
    rows = cur.execute("""
        SELECT substr(r.race_date,1,7) as ym,
               COUNT(DISTINCT r.id) as total,
               COUNT(DISTINCT rc.race_id) as have
        FROM races r
        JOIN (SELECT DISTINCT race_id FROM results) res ON r.id = res.race_id
        LEFT JOIN race_conditions rc ON r.id = rc.race_id
        WHERE r.race_date >= ? AND r.race_date < ?
        GROUP BY ym ORDER BY ym
    """, (start_date, end_date)).fetchall()
    conn.close()

    print(f"{'月':^8} | {'充足率':^8} | {'有り':^7} | {'対象':^7}")
    print("-" * 40)
    total_sum = have_sum = 0
    for r in rows:
        pct = r[2] * 100 / r[1] if r[1] else 0
        mark = " <-- 欠損" if pct < 95 else ""
        print(f"{r[0]:^8} | {pct:^7.1f}% | {r[2]:^7,} | {r[1]:^7,}{mark}")
        total_sum += r[1]; have_sum += r[2]
    if total_sum:
        print("-" * 40)
        print(f"{'合計':^8} | {have_sum*100/total_sum:^7.1f}% | {have_sum:^7,} | {total_sum:^7,}")
        print(f"  ※ 対象 = results が存在するレースのみ（中止等を除外）")


# ---------------------------------------------------------------------------
# Phase 1: 収集 → CSV
# ---------------------------------------------------------------------------

def _collect_one(args: tuple) -> dict:
    race_id, venue_code, race_date, race_number = args
    date_str = race_date.replace('-', '')
    venue_str = f"{int(venue_code):02d}"

    wd = _fetch_weather_from_page(venue_str, date_str, race_number)
    return {
        'race_id': race_id,
        'race_date': race_date,
        'success': wd is not None,
        'data': wd,
    }


def phase1_collect_to_csv(races: list, csv_dir: Path, workers: int) -> dict:
    """
    Phase 1: 欠損レースの気象データをスクレイピングして日付別CSVに書き出す。
    既存CSVがある日付は追記（重複はPhase 2側でON CONFLICTが処理）。
    """
    csv_dir.mkdir(parents=True, exist_ok=True)

    stats = {'total': len(races), 'success': 0, 'no_data': 0, 'error': 0}
    completed = 0
    current_month = None
    start_time = time.time()

    # CSVファイルハンドラキャッシュ（日付 → writer）
    csv_files = {}
    csv_writers = {}

    def get_writer(race_date: str):
        if race_date not in csv_files:
            path = csv_dir / f"{race_date}.csv"
            is_new = not path.exists()
            fh = open(path, 'a', newline='', encoding='utf-8')
            w = csv.DictWriter(fh, fieldnames=CSV_HEADER)
            if is_new:
                w.writeheader()
            csv_files[race_date] = fh
            csv_writers[race_date] = w
        return csv_writers[race_date]

    try:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_collect_one, race): race for race in races}

            for future in as_completed(futures):
                completed += 1
                try:
                    res = future.result()
                    month = res['race_date'][:7]
                    if month != current_month:
                        if current_month:
                            print()
                        current_month = month
                        print(f"[{month}] ", end='', flush=True)

                    if res['success']:
                        w = get_writer(res['race_date'])
                        row = {'race_id': res['race_id']}
                        row.update(res['data'])
                        w.writerow(row)
                        # 即フラッシュして中断時のデータ損失を防ぐ
                        csv_files[res['race_date']].flush()
                        stats['success'] += 1
                        print('.', end='', flush=True)
                    else:
                        stats['no_data'] += 1

                except Exception:
                    stats['error'] += 1

                if completed % 500 == 0:
                    elapsed = time.time() - start_time
                    rate = completed / elapsed if elapsed > 0 else 0
                    remaining = (stats['total'] - completed) / rate / 60 if rate > 0 else 0
                    print(f"\n  進捗: {completed}/{stats['total']} ({completed/stats['total']*100:.1f}%)"
                          f"  成功:{stats['success']}  残り約{remaining:.1f}分", flush=True)
    finally:
        for fh in csv_files.values():
            fh.close()

    if current_month:
        print()
    return stats


# ---------------------------------------------------------------------------
# Phase 2: CSV → DB
# ---------------------------------------------------------------------------

def phase2_import_csv(csv_dir: Path, dry_run: bool = False) -> dict:
    """
    Phase 2: 日付別CSVを読み込み、race_conditions テーブルに UPSERT。
    INSERT OR REPLACE で既存行も上書き。
    """
    csv_files = sorted(csv_dir.glob("*.csv"))
    if not csv_files:
        print(f"CSVファイルが見つかりません: {csv_dir}")
        return {'files': 0, 'rows': 0, 'errors': 0}

    stats = {'files': len(csv_files), 'rows': 0, 'errors': 0}
    conn = sqlite3.connect(str(DB_PATH), timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()

    for csv_path in csv_files:
        try:
            with open(csv_path, encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            if not rows:
                continue

            if not dry_run:
                cur.executemany("""
                    INSERT INTO race_conditions
                        (race_id, weather, wind_direction, wind_speed,
                         wave_height, temperature, water_temperature,
                         collected_at)
                    VALUES (:race_id, :weather, :wind_direction, :wind_speed,
                            :wave_height, :temperature, :water_temperature,
                            datetime('now', 'localtime'))
                    ON CONFLICT(race_id) DO UPDATE SET
                        weather = excluded.weather,
                        wind_direction = excluded.wind_direction,
                        wind_speed = excluded.wind_speed,
                        wave_height = excluded.wave_height,
                        temperature = excluded.temperature,
                        water_temperature = excluded.water_temperature,
                        collected_at = excluded.collected_at
                """, rows)
                conn.commit()

            stats['rows'] += len(rows)
            print(f"  {csv_path.name}: {len(rows)}件 {'(dry-run)' if dry_run else '投入済み'}")

        except Exception as e:
            stats['errors'] += 1
            print(f"  {csv_path.name}: エラー - {e}")

    conn.close()
    return stats


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='race_conditions 一括補完（CSV方式）')
    parser.add_argument('--start-date', default='2020-01-01')
    parser.add_argument('--end-date', default='2026-01-01')
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--csv-dir', default=str(CSV_DIR))
    parser.add_argument('--check-only', action='store_true', help='欠損チェックのみ')
    parser.add_argument('--csv-only', action='store_true', help='Phase 1のみ（CSVに書き出し）')
    parser.add_argument('--import-only', action='store_true', help='Phase 2のみ（CSV→DB）')
    parser.add_argument('--dry-run', action='store_true', help='Phase 2をdry-runで実行')
    args = parser.parse_args()

    csv_dir = Path(args.csv_dir)

    print("=" * 70)
    print("race_conditions 一括補完（CSV方式・軽量スクレイパー）")
    print("=" * 70)
    print(f"期間: {args.start_date} ～ {args.end_date}")
    print(f"CSV出力先: {csv_dir}")
    print(f"ワーカー数: {args.workers}")
    print()

    # --check-only
    if args.check_only:
        print("【現在の充足状況】")
        check_current_status(args.start_date, args.end_date)
        return

    # --import-only（Phase 2のみ）
    if args.import_only:
        print(f"Phase 2: CSV → DB ({csv_dir})")
        s = phase2_import_csv(csv_dir, dry_run=args.dry_run)
        print(f"\n完了: {s['files']}ファイル / {s['rows']:,}件投入 / エラー{s['errors']}件")
        print("\n【投入後の充足状況】")
        check_current_status(args.start_date, args.end_date)
        return

    # Phase 1: 収集 → CSV
    print("【現在の充足状況】")
    check_current_status(args.start_date, args.end_date)
    print()

    races = get_races_needing_conditions(args.start_date, args.end_date)
    if not races:
        print("欠損なし。処理不要です。")
        return

    print(f"Phase 1: 補完対象 {len(races):,}件 → {csv_dir} にCSV書き出し")
    print()

    try:
        if sys.stdin.isatty():
            resp = input("開始しますか？ (y/N): ")
            if resp.lower() != 'y':
                print("キャンセルしました")
                return
    except (EOFError, OSError):
        print("（バックグラウンド実行: 自動開始）")

    print()
    t0 = time.time()
    s1 = phase1_collect_to_csv(races, csv_dir, args.workers)
    elapsed1 = time.time() - t0

    print()
    print(f"Phase 1 完了: {elapsed1/60:.1f}分")
    print(f"  成功:{s1['success']:,}件 / データなし:{s1['no_data']:,}件 / エラー:{s1['error']:,}件")
    print()

    if args.csv_only:
        print(f"（--csv-only のためDB投入はスキップ）")
        print(f"投入するには: python ... --import-only --csv-dir {csv_dir}")
        return

    # Phase 2: CSV → DB
    print(f"Phase 2: CSV → DB 投入 ({csv_dir}/*.csv)")
    t1 = time.time()
    s2 = phase2_import_csv(csv_dir)
    elapsed2 = time.time() - t1

    print()
    print(f"Phase 2 完了: {elapsed2:.1f}秒 / {s2['rows']:,}件投入")
    print()
    print("【補完後の充足状況】")
    check_current_status(args.start_date, args.end_date)

    total_elapsed = time.time() - t0
    print()
    print(f"総所要時間: {total_elapsed/60:.1f}分")


if __name__ == "__main__":
    main()
