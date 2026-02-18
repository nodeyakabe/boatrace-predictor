#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
全年度 advance予想 一括生成スクリプト

2020〜2025年のadvance予想を順次生成する。
既存分はスキップするので、途中から再開しても安全。

使い方:
    python scripts/automation/generate_advance_all_years.py
    python scripts/automation/generate_advance_all_years.py --years 2020 2021 2022  # 年度指定
    python scripts/automation/generate_advance_all_years.py --start-year 2023       # 途中から
"""
import sys
import io
import os
import subprocess
import sqlite3
import argparse
from datetime import datetime
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "boatrace.db"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "prediction" / "generate_advance_fast.py"


def get_advance_stats():
    """年度別advance予想の現状を取得"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            substr(r.race_date, 1, 4) AS year,
            COUNT(DISTINCT r.id) AS total_races,
            COUNT(DISTINCT rp.race_id) AS predicted_races
        FROM races r
        LEFT JOIN race_predictions rp
            ON r.id = rp.race_id AND rp.prediction_type = 'advance'
        WHERE r.race_date >= '2020-01-01'
        GROUP BY year
        ORDER BY year
    """)
    rows = cursor.fetchall()
    conn.close()

    return {row[0]: {'total': row[1], 'done': row[2], 'remaining': row[1] - row[2]} for row in rows}


def main():
    parser = argparse.ArgumentParser(description='全年度advance予想を一括生成')
    parser.add_argument('--years', type=int, nargs='+', help='対象年度（例: 2020 2021 2022）')
    parser.add_argument('--start-year', type=int, help='開始年度（この年度から2025年まで）')
    args = parser.parse_args()

    # 対象年度の決定
    if args.years:
        target_years = sorted(args.years)
    elif args.start_year:
        # DBに存在する年度を動的に取得（指定年度以降）
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT CAST(substr(race_date,1,4) AS INTEGER) FROM races"
            " WHERE race_date >= ? ORDER BY 1",
            (f'{args.start_year}-01-01',)
        )
        target_years = [row[0] for row in cur.fetchall()]
        conn.close()
    else:
        # DBに存在する2020年以降の全年度を動的に取得
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT CAST(substr(race_date,1,4) AS INTEGER) FROM races"
            " WHERE race_date >= '2020-01-01' ORDER BY 1"
        )
        target_years = [row[0] for row in cur.fetchall()]
        conn.close()

    print("=" * 70)
    print("全年度 advance予想 一括生成")
    print("=" * 70)
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"対象年度: {target_years}")
    print()

    # 現状サマリーを表示
    print("【現状サマリー】")
    stats = get_advance_stats()
    for year in target_years:
        year_str = str(year)
        if year_str in stats:
            s = stats[year_str]
            pct = 100 * s['done'] / s['total'] if s['total'] > 0 else 0
            print(f"  {year}年: {s['done']:,}/{s['total']:,}件 ({pct:.1f}%) 残り{s['remaining']:,}件")
        else:
            print(f"  {year}年: データなし")
    print()

    total_remaining = sum(
        stats.get(str(y), {}).get('remaining', 0) for y in target_years
    )
    if total_remaining == 0:
        print("✅ 全年度のadvance予想が生成済みです。")
        return 0

    print(f"合計残り: {total_remaining:,}件")
    print()

    # 年度ごとに順次生成
    results = {}
    overall_start = datetime.now()

    for year in target_years:
        year_str = str(year)
        remaining = stats.get(year_str, {}).get('remaining', 0)

        if remaining == 0:
            print(f"\n[{year}年] ✅ 生成済み（スキップ）")
            results[year] = 'skipped'
            continue

        print(f"\n{'='*70}")
        print(f"[{year}年] advance予想生成開始 (残り{remaining:,}件)")
        print(f"{'='*70}")
        year_start = datetime.now()

        cmd = [sys.executable, str(SCRIPT_PATH), "--year", str(year)]

        try:
            proc = subprocess.run(
                cmd,
                encoding='utf-8',
                errors='replace',
                timeout=None  # タイムアウトなし（大量データのため）
            )

            elapsed = (datetime.now() - year_start).total_seconds()
            if proc.returncode == 0:
                print(f"\n[{year}年] ✅ 完了 ({elapsed/60:.1f}分)")
                results[year] = 'success'
            else:
                print(f"\n[{year}年] ❌ エラー（終了コード: {proc.returncode}）")
                results[year] = 'error'

        except KeyboardInterrupt:
            print(f"\n[{year}年] ⚠️ 中断（Ctrl+C）")
            print("次回は同じコマンドで再開できます（既存分はスキップされます）")
            break
        except Exception as e:
            print(f"\n[{year}年] ❌ 例外: {e}")
            results[year] = 'error'

    # 最終サマリー
    total_elapsed = (datetime.now() - overall_start).total_seconds()
    print(f"\n\n{'='*70}")
    print("完了サマリー")
    print(f"{'='*70}")
    print(f"完了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"総処理時間: {total_elapsed/60:.1f}分")
    print()

    print("【最終状態】")
    stats_final = get_advance_stats()
    for year in target_years:
        year_str = str(year)
        if year_str in stats_final:
            s = stats_final[year_str]
            pct = 100 * s['done'] / s['total'] if s['total'] > 0 else 0
            status = results.get(year, '-')
            mark = {'success': '✅', 'skipped': '⏭️', 'error': '❌'}.get(status, '?')
            print(f"  {mark} {year}年: {s['done']:,}/{s['total']:,}件 ({pct:.1f}%)")
    print(f"{'='*70}")

    return 0 if all(v in ('success', 'skipped') for v in results.values()) else 1


if __name__ == '__main__':
    sys.exit(main())
