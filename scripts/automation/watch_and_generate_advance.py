#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
データ補完完了を自動検知 → advance予想・before予想を自動生成

バックグラウンドで動かしておくと、データ補完が終わり次第
advance予想 → before予想 の順に自動生成する。

使い方:
    python scripts/automation/watch_and_generate_advance.py
    python scripts/automation/watch_and_generate_advance.py --check-interval 10
    python scripts/automation/watch_and_generate_advance.py --stable-minutes 20
    python scripts/automation/watch_and_generate_advance.py --skip-advance  # advance完了済みならスキップ
"""
import sys
import io
import os
import sqlite3
import subprocess
import time
import argparse
from datetime import datetime
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "boatrace.db"
ADVANCE_SCRIPT = PROJECT_ROOT / "scripts" / "prediction" / "generate_advance_fast.py"
YEAR_PRED_SCRIPT = PROJECT_ROOT / "scripts" / "automation" / "generate_year_predictions_fast.py"


def get_target_years():
    """DBに存在するレース年度を動的に取得（2020年以降）"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT CAST(substr(race_date, 1, 4) AS INTEGER) AS yr
        FROM races
        WHERE race_date >= '2020-01-01'
        ORDER BY yr
    """)
    years = [row[0] for row in cursor.fetchall()]
    conn.close()
    return years


def get_collection_metrics():
    """DBの現在の補完状況を取得"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    metrics = {}

    # 2022年エントリー数
    cursor.execute("SELECT COUNT(*) FROM entries e JOIN races r ON e.race_id = r.id WHERE r.race_date LIKE '2022%'")
    metrics['entries_2022'] = cursor.fetchone()[0]

    # 決まり手データ数（2021, 2023, 2024年）
    for yr in ['2021', '2023', '2024']:
        cursor.execute(
            "SELECT COUNT(*) FROM results res"
            " JOIN races r ON res.race_id = r.id"
            " WHERE r.race_date LIKE ? AND res.kimarite IS NOT NULL AND res.kimarite != ''",
            (f'{yr}%',)
        )
        metrics[f'kimarite_{yr}'] = cursor.fetchone()[0]

    # 2024年 race_conditions数
    cursor.execute("""
        SELECT COUNT(*) FROM race_conditions rc
        JOIN races r ON rc.race_id = r.id
        WHERE r.race_date LIKE '2024%'
    """)
    metrics['conditions_2024'] = cursor.fetchone()[0]

    conn.close()
    return metrics


def metrics_stable(history, stable_minutes):
    """直近stable_minutes分間、メトリクスが変化していないか確認"""
    if len(history) < 2:
        return False
    cutoff_time = time.time() - stable_minutes * 60
    old_entries = [(ts, m) for ts, m in history if ts <= cutoff_time]
    if not old_entries:
        return False
    _, old_metrics = old_entries[-1]
    _, current_metrics = history[-1]
    return old_metrics == current_metrics


def get_prediction_stats():
    """年度別の予想生成状況を取得"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            substr(r.race_date, 1, 4) AS year,
            COUNT(DISTINCT r.id) AS total,
            SUM(CASE WHEN rp_a.race_id IS NOT NULL THEN 1 ELSE 0 END) AS advance_done,
            SUM(CASE WHEN rp_b.race_id IS NOT NULL THEN 1 ELSE 0 END) AS before_done
        FROM races r
        LEFT JOIN (
            SELECT DISTINCT race_id FROM race_predictions WHERE prediction_type = 'advance'
        ) rp_a ON r.id = rp_a.race_id
        LEFT JOIN (
            SELECT DISTINCT race_id FROM race_predictions WHERE prediction_type = 'before'
        ) rp_b ON r.id = rp_b.race_id
        WHERE r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
        GROUP BY year ORDER BY year
    """)
    rows = cursor.fetchall()
    conn.close()
    return {
        row[0]: {
            'total': row[1],
            'advance_done': row[2],
            'before_done': row[3],
            'advance_remaining': row[1] - row[2],
            'before_remaining': row[1] - row[3],
        }
        for row in rows
    }


def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    print(f"[{ts}] {msg}", flush=True)


def run_year(script, year_str, type_name):
    """年度単位で予想生成を実行（subprocess）"""
    cmd = [sys.executable, str(script), "--year", year_str]
    year_start = time.time()
    try:
        proc = subprocess.run(cmd, encoding='utf-8', errors='replace')
        elapsed = time.time() - year_start
        if proc.returncode == 0:
            log(f"[{year_str}年/{type_name}] ✅ 完了 ({elapsed/60:.1f}分)")
            return True
        else:
            log(f"[{year_str}年/{type_name}] ❌ エラー（終了コード: {proc.returncode}）")
            return False
    except KeyboardInterrupt:
        raise
    except Exception as e:
        log(f"[{year_str}年/{type_name}] ❌ 例外: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='データ補完完了を監視 → advance・before予想を自動生成')
    parser.add_argument('--check-interval', type=int, default=5, help='チェック間隔（分）デフォルト: 5')
    parser.add_argument('--stable-minutes', type=int, default=15, help='変化なし判定の分数。デフォルト: 15')
    parser.add_argument('--skip-advance', action='store_true', help='advance生成をスキップ（before生成のみ実行）')
    parser.add_argument('--skip-before', action='store_true', help='before生成をスキップ（advance生成のみ実行）')
    args = parser.parse_args()

    print("=" * 70)
    print("データ補完 完了監視 → advance・before予想 自動生成")
    print("=" * 70)
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"チェック間隔: {args.check_interval}分 | 完了判定: {args.stable_minutes}分間変化なし")
    if args.skip_advance:
        print("※ advance生成はスキップ")
    if args.skip_before:
        print("※ before生成はスキップ")
    print("（Ctrl+C で停止）")
    print()

    # ── 1. データ補完完了を待機 ──────────────────────────────
    metrics_history = []

    try:
        while True:
            current_metrics = get_collection_metrics()
            now = time.time()
            metrics_history.append((now, current_metrics))

            cutoff = now - args.stable_minutes * 60 * 2
            metrics_history = [(ts, m) for ts, m in metrics_history if ts > cutoff]

            log(f"エントリー2022:{current_metrics['entries_2022']:,} | "
                f"決まり手 2021:{current_metrics['kimarite_2021']:,} "
                f"2023:{current_metrics['kimarite_2023']:,} "
                f"2024:{current_metrics['kimarite_2024']:,} | "
                f"条件2024:{current_metrics['conditions_2024']:,}")

            if metrics_stable(metrics_history, args.stable_minutes):
                log(f"✅ {args.stable_minutes}分間変化なし → データ補完完了と判定")
                break

            log(f"補完進行中... {args.check_interval}分後に再確認")
            time.sleep(args.check_interval * 60)

    except KeyboardInterrupt:
        print("\n[!] 手動停止。予想生成をスキップします。")
        return 1

    # ── 2. 現状表示 ─────────────────────────────────────────
    print()
    print("=" * 70)
    target_years = get_target_years()
    stats = get_prediction_stats()
    print(f"【予想生成の現状】対象年度: {target_years}")
    print(f"{'年度':^6} | {'全レース':^8} | {'advance残':^9} | {'before残':^9}")
    print("-" * 45)
    for yr in target_years:
        s = stats.get(str(yr), {'total': 0, 'advance_remaining': 0, 'before_remaining': 0})
        print(f"{yr}年 | {s['total']:>8,} | {s['advance_remaining']:>9,} | {s['before_remaining']:>9,}")
    print("=" * 70)
    print()

    # ── 3. advance予想生成 ───────────────────────────────────
    if not args.skip_advance:
        print("【STEP 1】 advance予想生成")
        print("-" * 70)
        try:
            for yr in target_years:
                s = stats.get(str(yr), {})
                remaining = s.get('advance_remaining', 0)
                if remaining <= 0:
                    log(f"[{yr}年/advance] ✅ 生成済み（スキップ）")
                    continue
                log(f"[{yr}年/advance] 開始（残り{remaining:,}件）")
                run_year(ADVANCE_SCRIPT, str(yr), "advance")
        except KeyboardInterrupt:
            print("\n[!] advance生成を中断しました。次回再開可能です。")
            return 1
        print()

    # ── 4. before予想生成 ────────────────────────────────────
    if not args.skip_before:
        print("【STEP 2】 before予想生成")
        print("-" * 70)
        # 統計を再取得（advanceが終わった後なので）
        stats = get_prediction_stats()
        try:
            for yr in target_years:
                s = stats.get(str(yr), {})
                remaining = s.get('before_remaining', 0)
                if remaining <= 0:
                    log(f"[{yr}年/before] ✅ 生成済み（スキップ）")
                    continue
                log(f"[{yr}年/before] 開始（残り{remaining:,}件）")
                cmd = [sys.executable, str(YEAR_PRED_SCRIPT), "--year", str(yr), "--type", "before"]
                year_start = time.time()
                try:
                    proc = subprocess.run(cmd, encoding='utf-8', errors='replace')
                    elapsed = time.time() - year_start
                    if proc.returncode == 0:
                        log(f"[{yr}年/before] ✅ 完了 ({elapsed/60:.1f}分)")
                    else:
                        log(f"[{yr}年/before] ❌ エラー（終了コード: {proc.returncode}）")
                except KeyboardInterrupt:
                    raise
        except KeyboardInterrupt:
            print("\n[!] before生成を中断しました。次回 --skip-advance で再開できます。")
            return 1
        print()

    # ── 5. 最終サマリー ──────────────────────────────────────
    print("=" * 70)
    print("🎉 全予想生成完了！")
    stats_final = get_prediction_stats()
    print(f"{'年度':^6} | {'全レース':^8} | {'advance':^9} | {'before':^9}")
    print("-" * 45)
    for yr in target_years:
        s = stats_final.get(str(yr), {'total': 0, 'advance_done': 0, 'before_done': 0})
        adv_pct = 100 * s['advance_done'] / s['total'] if s['total'] > 0 else 0
        bef_pct = 100 * s['before_done'] / s['total'] if s['total'] > 0 else 0
        print(f"{yr}年 | {s['total']:>8,} | {s['advance_done']:>7,}({adv_pct:4.1f}%) | {s['before_done']:>7,}({bef_pct:4.1f}%)")
    print("=" * 70)
    return 0


if __name__ == '__main__':
    sys.exit(main())
