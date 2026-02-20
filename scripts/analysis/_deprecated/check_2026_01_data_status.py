#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2026年1月のデータ不足状況調査スクリプト
各テーブルのデータ充足率を確認
"""

import sqlite3
import pandas as pd
from pathlib import Path

def check_data_status():
    """2026年1月のデータ状況を確認"""

    # データベース接続
    db_path = Path(__file__).resolve().parents[2] / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)

    print("=" * 80)
    print("2026年1月 データ不足状況調査")
    print("=" * 80)
    print()

    # 1. 基準となるレース数を取得
    query_races = """
    SELECT
        COUNT(*) as total_races,
        COUNT(DISTINCT venue_code) as venues,
        MIN(race_date) as start_date,
        MAX(race_date) as end_date
    FROM races
    WHERE race_date >= '2026-01-01'
      AND race_date < '2026-02-01'
    """

    df_races = pd.read_sql_query(query_races, conn)
    total_races = df_races['total_races'].iloc[0]

    if total_races == 0:
        print("[警告] 2026年1月のレースデータが存在しません")
        conn.close()
        return

    print(f"対象期間: {df_races['start_date'].iloc[0]} ～ {df_races['end_date'].iloc[0]}")
    print(f"総レース数: {total_races:,} レース")
    print(f"開催会場数: {df_races['venues'].iloc[0]} 会場")
    print()

    # 2. 各テーブルのデータ充足状況を確認
    tables_info = [
        {
            'name': 'entries',
            'description': '出走情報',
            'query': """
                SELECT COUNT(*) as count
                FROM entries e
                JOIN races r ON e.race_id = r.id
                WHERE r.race_date >= '2026-01-01'
                  AND r.race_date < '2026-02-01'
            """,
            'expected_multiplier': 6,  # 1レース6艇
            'importance': '★★★'
        },
        {
            'name': 'results',
            'description': 'レース結果',
            'query': """
                SELECT COUNT(*) as count
                FROM results res
                JOIN races r ON res.race_id = r.id
                WHERE r.race_date >= '2026-01-01'
                  AND r.race_date < '2026-02-01'
            """,
            'expected_multiplier': 6,  # 1レース6艇
            'importance': '★★★'
        },
        {
            'name': 'race_predictions',
            'description': '予測データ',
            'query': """
                SELECT COUNT(*) as count
                FROM race_predictions rp
                JOIN races r ON rp.race_id = r.id
                WHERE r.race_date >= '2026-01-01'
                  AND r.race_date < '2026-02-01'
                  AND rp.prediction_type = 'before'
            """,
            'expected_multiplier': 6,  # 1レース6艇
            'importance': '★★★'
        },
        {
            'name': 'trifecta_odds',
            'description': '3連単オッズ',
            'query': """
                SELECT COUNT(*) as count
                FROM trifecta_odds t
                JOIN races r ON t.race_id = r.id
                WHERE r.race_date >= '2026-01-01'
                  AND r.race_date < '2026-02-01'
            """,
            'expected_multiplier': 120,  # 6P3 = 120通り
            'importance': '★★★'
        },
        {
            'name': 'race_details',
            'description': '展示タイム等',
            'query': """
                SELECT COUNT(*) as count
                FROM race_details rd
                JOIN races r ON rd.race_id = r.id
                WHERE r.race_date >= '2026-01-01'
                  AND r.race_date < '2026-02-01'
            """,
            'expected_multiplier': 6,  # 1レース6艇
            'importance': '★★'
        },
        {
            'name': 'race_conditions',
            'description': '天候・風・波',
            'query': """
                SELECT COUNT(*) as count
                FROM race_conditions rc
                JOIN races r ON rc.race_id = r.id
                WHERE r.race_date >= '2026-01-01'
                  AND r.race_date < '2026-02-01'
            """,
            'expected_multiplier': 1,  # 1レース1件
            'importance': '★★'
        },
        {
            'name': 'payouts',
            'description': '払戻金',
            'query': """
                SELECT COUNT(*) as count
                FROM payouts p
                JOIN races r ON p.race_id = r.id
                WHERE r.race_date >= '2026-01-01'
                  AND r.race_date < '2026-02-01'
            """,
            'expected_multiplier': 1,  # 1レース1件（3連単）
            'importance': '★★'
        },
        {
            'name': 'exhibition_data',
            'description': 'オリジナル展示',
            'query': """
                SELECT COUNT(*) as count
                FROM exhibition_data ed
                JOIN races r ON ed.race_id = r.id
                WHERE r.race_date >= '2026-01-01'
                  AND r.race_date < '2026-02-01'
            """,
            'expected_multiplier': 6,  # 1レース6艇
            'importance': '★'
        }
    ]

    print("=" * 80)
    print("テーブル別データ充足状況")
    print("=" * 80)
    print()

    results = []

    for table_info in tables_info:
        df = pd.read_sql_query(table_info['query'], conn)
        actual_count = df['count'].iloc[0]
        expected_count = total_races * table_info['expected_multiplier']

        if expected_count > 0:
            fill_rate = (actual_count / expected_count) * 100
        else:
            fill_rate = 0

        missing_count = expected_count - actual_count

        # ステータス判定
        if fill_rate >= 95:
            status = "[OK] 良好"
        elif fill_rate >= 80:
            status = "[注意] やや不足"
        elif fill_rate >= 50:
            status = "[注意] 不足"
        elif fill_rate > 0:
            status = "[警告] 大幅不足"
        else:
            status = "[警告] データなし"

        results.append({
            'テーブル': table_info['name'],
            '説明': table_info['description'],
            '重要度': table_info['importance'],
            '実際': f"{actual_count:,}",
            '期待値': f"{expected_count:,}",
            '不足': f"{missing_count:,}",
            '充足率': f"{fill_rate:.1f}%",
            'ステータス': status
        })

        print(f"{table_info['importance']} {table_info['name']:<20} ({table_info['description']})")
        print(f"   実際: {actual_count:,} / 期待値: {expected_count:,} ({fill_rate:.1f}%)  {status}")
        if missing_count > 0:
            print(f"   不足: {missing_count:,} 件")
        print()

    # 3. 日別のデータ状況を確認
    print("=" * 80)
    print("日別データ状況（レース数）")
    print("=" * 80)
    print()

    query_daily = """
    SELECT
        race_date,
        COUNT(*) as races,
        COUNT(DISTINCT venue_code) as venues
    FROM races
    WHERE race_date >= '2026-01-01'
      AND race_date < '2026-02-01'
    GROUP BY race_date
    ORDER BY race_date
    """

    df_daily = pd.read_sql_query(query_daily, conn)

    if len(df_daily) > 0:
        for _, row in df_daily.iterrows():
            print(f"{row['race_date']}: {row['races']:3}レース ({row['venues']}会場)")
        print()
        print(f"平均: {df_daily['races'].mean():.1f}レース/日")
        print(f"合計: {df_daily['races'].sum()}レース")

    print()

    # 4. 予測データの詳細確認
    print("=" * 80)
    print("予測データ詳細")
    print("=" * 80)
    print()

    query_prediction_detail = """
    WITH race_counts AS (
        SELECT
            r.race_date,
            COUNT(DISTINCT r.id) as total_races
        FROM races r
        WHERE r.race_date >= '2026-01-01'
          AND r.race_date < '2026-02-01'
        GROUP BY r.race_date
    ),
    prediction_counts AS (
        SELECT
            r.race_date,
            COUNT(DISTINCT rp.race_id) as predicted_races
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE r.race_date >= '2026-01-01'
          AND r.race_date < '2026-02-01'
          AND rp.prediction_type = 'before'
        GROUP BY r.race_date
    )
    SELECT
        rc.race_date,
        rc.total_races,
        COALESCE(pc.predicted_races, 0) as predicted_races,
        rc.total_races - COALESCE(pc.predicted_races, 0) as missing_races
    FROM race_counts rc
    LEFT JOIN prediction_counts pc ON rc.race_date = pc.race_date
    ORDER BY rc.race_date
    """

    df_pred_detail = pd.read_sql_query(query_prediction_detail, conn)

    if len(df_pred_detail) > 0:
        for _, row in df_pred_detail.iterrows():
            if row['missing_races'] > 0:
                print(f"{row['race_date']}: 予測あり {row['predicted_races']}/{row['total_races']}レース (不足: {row['missing_races']})")

        total_missing = df_pred_detail['missing_races'].sum()
        if total_missing == 0:
            print("[OK] すべてのレースに予測データがあります")
        else:
            print(f"\n[注意] 合計 {total_missing} レースの予測データが不足")

    print()

    # 5. オッズデータの詳細確認
    print("=" * 80)
    print("オッズデータ詳細")
    print("=" * 80)
    print()

    query_odds_detail = """
    WITH race_counts AS (
        SELECT
            r.race_date,
            COUNT(DISTINCT r.id) as total_races
        FROM races r
        WHERE r.race_date >= '2026-01-01'
          AND r.race_date < '2026-02-01'
        GROUP BY r.race_date
    ),
    odds_counts AS (
        SELECT
            r.race_date,
            COUNT(DISTINCT t.race_id) as odds_races
        FROM trifecta_odds t
        JOIN races r ON t.race_id = r.id
        WHERE r.race_date >= '2026-01-01'
          AND r.race_date < '2026-02-01'
        GROUP BY r.race_date
    )
    SELECT
        rc.race_date,
        rc.total_races,
        COALESCE(oc.odds_races, 0) as odds_races,
        rc.total_races - COALESCE(oc.odds_races, 0) as missing_races
    FROM race_counts rc
    LEFT JOIN odds_counts oc ON rc.race_date = oc.race_date
    ORDER BY rc.race_date
    """

    df_odds_detail = pd.read_sql_query(query_odds_detail, conn)

    if len(df_odds_detail) > 0:
        for _, row in df_odds_detail.iterrows():
            if row['missing_races'] > 0:
                print(f"{row['race_date']}: オッズあり {row['odds_races']}/{row['total_races']}レース (不足: {row['missing_races']})")

        total_missing = df_odds_detail['missing_races'].sum()
        if total_missing == 0:
            print("[OK] すべてのレースにオッズデータがあります")
        else:
            print(f"\n[注意] 合計 {total_missing} レースのオッズデータが不足")

    print()

    # 6. サマリー
    print("=" * 80)
    print("サマリー")
    print("=" * 80)
    print()

    df_summary = pd.DataFrame(results)

    # 重要度★★★のテーブルで充足率が低いものを抽出
    critical_issues = df_summary[
        (df_summary['重要度'] == '★★★') &
        (df_summary['充足率'].str.rstrip('%').astype(float) < 95)
    ]

    if len(critical_issues) > 0:
        print("[注意] 重要なデータの不足があります:")
        for _, row in critical_issues.iterrows():
            print(f"   - {row['テーブル']} ({row['説明']}): {row['充足率']}")
    else:
        print("[OK] 重要なテーブルのデータは十分です")

    print()

    # データなしのテーブル
    no_data = df_summary[df_summary['充足率'] == '0.0%']
    if len(no_data) > 0:
        print("[警告] データが存在しないテーブル:")
        for _, row in no_data.iterrows():
            print(f"   - {row['テーブル']} ({row['説明']})")

    conn.close()

    print()
    print("=" * 80)
    print("調査完了")
    print("=" * 80)

if __name__ == "__main__":
    check_data_status()
