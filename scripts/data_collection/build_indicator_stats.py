# -*- coding: utf-8 -*-
"""
指標データ生成スクリプト

逃げ率・まくり率・差し率を計算してDBに保存

使用方法:
    # 全期間データを生成
    python scripts/data_collection/build_indicator_stats.py

    # 年別データを生成
    python scripts/data_collection/build_indicator_stats.py --yearly

    # 特定期間を指定
    python scripts/data_collection/build_indicator_stats.py --start 2024-01-01 --end 2024-12-31

    # テーブル再作成（データクリア）
    python scripts/data_collection/build_indicator_stats.py --recreate
"""

import argparse
import sys
import os
from datetime import datetime

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.database.indicator_tables import IndicatorTables
from src.analysis.escape_rate_calculator import EscapeRateCalculator
from src.analysis.attack_rate_calculator import AttackRateCalculator


def build_all_period(db_path: str):
    """全期間のデータを生成"""
    print("\n" + "=" * 70)
    print("全期間データ生成")
    print("=" * 70)

    escape_calc = EscapeRateCalculator(db_path)
    attack_calc = AttackRateCalculator(db_path)

    # 逃げ率（全国）
    print("\n[1] 全国逃げ率を計算中...")
    national_results = escape_calc.calculate_national_escape_rates()
    valid_national = [r for r in national_results if r.escape_rate is not None]
    print(f"   全選手数: {len(national_results)}")
    print(f"   母数充足: {len(valid_national)}")
    escape_calc.save_results(national_results)
    print("   [OK] 保存完了")

    # 逃げ率（当地）
    print("\n[2] 当地逃げ率を計算中...")
    local_results = escape_calc.calculate_local_escape_rates()
    valid_local = [r for r in local_results if r.escape_rate is not None]
    print(f"   全組合せ数: {len(local_results)}")
    print(f"   母数充足: {len(valid_local)}")
    escape_calc.save_results(local_results)
    print("   [OK] 保存完了")

    # まくり率・差し率
    print("\n[3] まくり率・差し率を計算中...")
    attack_results = attack_calc.calculate_stadium_attack_rates()
    print(f"   対象会場数: {len(attack_results)}")
    attack_calc.save_results(attack_results)
    print("   [OK] 保存完了")


def build_yearly(db_path: str, years: list = None):
    """年別データを生成"""
    print("\n" + "=" * 70)
    print("年別データ生成")
    print("=" * 70)

    if years is None:
        years = list(range(2020, 2026))

    escape_calc = EscapeRateCalculator(db_path)
    attack_calc = AttackRateCalculator(db_path)

    for year in years:
        period_start = f"{year}-01-01"
        period_end = f"{year}-12-31"

        print(f"\n[{year}]")

        # 逃げ率（全国）
        print(f"   全国逃げ率...")
        national_results = escape_calc.calculate_national_escape_rates(period_start, period_end)
        valid_national = [r for r in national_results if r.escape_rate is not None]
        print(f"     母数充足: {len(valid_national)}/{len(national_results)}")
        escape_calc.save_results(national_results)

        # 逃げ率（当地）
        print(f"   当地逃げ率...")
        local_results = escape_calc.calculate_local_escape_rates(period_start, period_end)
        valid_local = [r for r in local_results if r.escape_rate is not None]
        print(f"     母数充足: {len(valid_local)}/{len(local_results)}")
        escape_calc.save_results(local_results)

        # まくり率・差し率
        print(f"   まくり率・差し率...")
        attack_results = attack_calc.calculate_stadium_attack_rates(period_start, period_end)
        print(f"     会場数: {len(attack_results)}")
        attack_calc.save_results(attack_results)

        print(f"   [OK] {year}年 完了")


def build_custom_period(db_path: str, start: str, end: str):
    """指定期間のデータを生成"""
    print("\n" + "=" * 70)
    print(f"指定期間データ生成: {start} ～ {end}")
    print("=" * 70)

    escape_calc = EscapeRateCalculator(db_path)
    attack_calc = AttackRateCalculator(db_path)

    # 逃げ率（全国）
    print("\n[1] 全国逃げ率を計算中...")
    national_results = escape_calc.calculate_national_escape_rates(start, end)
    valid_national = [r for r in national_results if r.escape_rate is not None]
    print(f"   母数充足: {len(valid_national)}/{len(national_results)}")
    escape_calc.save_results(national_results)

    # 逃げ率（当地）
    print("\n[2] 当地逃げ率を計算中...")
    local_results = escape_calc.calculate_local_escape_rates(start, end)
    valid_local = [r for r in local_results if r.escape_rate is not None]
    print(f"   母数充足: {len(valid_local)}/{len(local_results)}")
    escape_calc.save_results(local_results)

    # まくり率・差し率
    print("\n[3] まくり率・差し率を計算中...")
    attack_results = attack_calc.calculate_stadium_attack_rates(start, end)
    print(f"   会場数: {len(attack_results)}")
    attack_calc.save_results(attack_results)

    print("\n[OK] 完了")


def show_summary(db_path: str):
    """データサマリーを表示"""
    print("\n" + "=" * 70)
    print("データサマリー")
    print("=" * 70)

    tables = IndicatorTables(db_path)
    stats = tables.get_table_stats()

    print(f"\n[DATA] player_escape_stats: {stats['player_escape_stats']:,} 件")
    print(f"[DATA] stadium_attack_stats: {stats['stadium_attack_stats']:,} 件")

    # サンプルデータを表示
    escape_calc = EscapeRateCalculator(db_path)
    attack_calc = AttackRateCalculator(db_path)

    print("\n【逃げ率トップ5（全国・全期間）】")
    import sqlite3
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT player_id, escape_rate, races_1course, wins_1course
            FROM player_escape_stats
            WHERE stadium_id IS NULL AND escape_rate IS NOT NULL
            ORDER BY escape_rate DESC
            LIMIT 5
        ''')
        for row in cursor.fetchall():
            print(f"   選手{row[0]}: {row[1]:.1%} ({row[3]}/{row[2]})")

    print("\n【まくり率が高い会場トップ5（全期間）】")
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT s.stadium_id, v.venue_name, s.makuri_rate, s.total_races
            FROM stadium_attack_stats s
            LEFT JOIN venue_data v ON s.stadium_id = v.venue_code
            WHERE s.period_start = '2000-01-01'
            ORDER BY s.makuri_rate DESC
            LIMIT 5
        ''')
        for row in cursor.fetchall():
            name = row[1] if row[1] else f"会場{row[0]}"
            print(f"   {name}: {row[2]:.1%} ({row[3]:,}レース)")

    print("\n【差し率が高い会場トップ5（全期間）】")
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT s.stadium_id, v.venue_name, s.sashi_rate, s.total_races
            FROM stadium_attack_stats s
            LEFT JOIN venue_data v ON s.stadium_id = v.venue_code
            WHERE s.period_start = '2000-01-01'
            ORDER BY s.sashi_rate DESC
            LIMIT 5
        ''')
        for row in cursor.fetchall():
            name = row[1] if row[1] else f"会場{row[0]}"
            print(f"   {name}: {row[2]:.1%} ({row[3]:,}レース)")


def main():
    parser = argparse.ArgumentParser(description='指標データ生成スクリプト')
    parser.add_argument('--db', default='data/boatrace.db', help='DBパス')
    parser.add_argument('--recreate', action='store_true', help='テーブル再作成')
    parser.add_argument('--yearly', action='store_true', help='年別データを生成')
    parser.add_argument('--start', help='期間開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', help='期間終了日 (YYYY-MM-DD)')
    parser.add_argument('--summary', action='store_true', help='サマリー表示のみ')

    args = parser.parse_args()

    print("=" * 70)
    print("指標データ生成スクリプト")
    print("=" * 70)
    print(f"DB: {args.db}")

    # テーブル作成
    tables = IndicatorTables(args.db)

    if args.recreate:
        print("\n[WARN] テーブルを再作成します...")
        tables.drop_tables()

    tables.create_tables()

    if args.summary:
        show_summary(args.db)
        return

    # データ生成
    if args.start and args.end:
        build_custom_period(args.db, args.start, args.end)
    elif args.yearly:
        build_all_period(args.db)  # まず全期間
        build_yearly(args.db)       # 次に年別
    else:
        build_all_period(args.db)

    # サマリー表示
    show_summary(args.db)

    print("\n" + "=" * 70)
    print("[DONE] 全処理完了")
    print("=" * 70)


if __name__ == "__main__":
    main()
