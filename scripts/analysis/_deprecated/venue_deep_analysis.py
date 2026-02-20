# -*- coding: utf-8 -*-
"""
会場別深掘り分析スクリプト
- 環境要因（潮位、風向、風速）の影響
- 選手情報（地元、年齢、級別）の影響
- コース・オッズ傾向
- 24会場×6年間の完全分析
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
import json
from datetime import datetime
from collections import defaultdict

# データベース接続
DB_PATH = Path(__file__).parent.parent.parent / 'data' / 'boatrace.db'

def get_connection():
    return sqlite3.connect(str(DB_PATH))

def analyze_venue_basic():
    """会場基本情報の取得"""
    conn = get_connection()

    # 会場マスタ
    venues_df = pd.read_sql_query("""
        SELECT
            vd.venue_code,
            vd.venue_name,
            vd.water_type,
            vd.tidal_range,
            vd.course_1_win_rate,
            vd.course_2_win_rate,
            vd.course_3_win_rate,
            vd.course_4_win_rate,
            vd.course_5_win_rate,
            vd.course_6_win_rate,
            vs.course_tendency,
            vs.kimarite_tendency,
            vs.wind_tendency,
            vs.tide_impact,
            vs.special_notes
        FROM venue_data vd
        LEFT JOIN venue_strategies vs ON vd.venue_code = vs.venue_code
        ORDER BY vd.venue_code
    """, conn)

    conn.close()
    return venues_df

def analyze_race_conditions_by_venue():
    """会場別のレースコンディション分析（風向・風速・波高）"""
    conn = get_connection()

    # 2020-2025年のレースコンディション
    conditions_df = pd.read_sql_query("""
        SELECT
            r.venue_code,
            substr(r.race_date, 1, 4) as year,
            rc.wind_direction,
            rc.wind_speed,
            rc.wave_height,
            rc.temperature,
            rc.water_temperature,
            res.pit_number as winner_pit,
            res.kimarite
        FROM races r
        JOIN race_conditions rc ON r.id = rc.race_id
        JOIN results res ON r.id = res.race_id AND res.rank = '1'
        WHERE substr(r.race_date, 1, 4) >= '2020'
          AND res.is_invalid = 0
    """, conn)

    conn.close()
    return conditions_df

def analyze_predictions_vs_results():
    """予測と結果の比較分析"""
    conn = get_connection()

    # advance予測
    advance_df = pd.read_sql_query("""
        SELECT
            r.venue_code,
            r.race_date,
            substr(r.race_date, 1, 4) as year,
            rp.race_id,
            rp.pit_number,
            rp.rank_prediction,
            rp.confidence,
            rp.total_score,
            res.rank as actual_rank,
            res.kimarite,
            p.amount as trifecta_payout
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
        LEFT JOIN payouts p ON rp.race_id = p.race_id AND p.bet_type = 'trifecta'
        WHERE rp.prediction_type = 'advance'
          AND substr(r.race_date, 1, 4) >= '2020'
          AND res.is_invalid = 0
    """, conn)

    # before予測
    before_df = pd.read_sql_query("""
        SELECT
            r.venue_code,
            r.race_date,
            substr(r.race_date, 1, 4) as year,
            rp.race_id,
            rp.pit_number,
            rp.rank_prediction,
            rp.confidence,
            rp.total_score,
            res.rank as actual_rank,
            res.kimarite,
            p.amount as trifecta_payout
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
        LEFT JOIN payouts p ON rp.race_id = p.race_id AND p.bet_type = 'trifecta'
        WHERE rp.prediction_type = 'before'
          AND substr(r.race_date, 1, 4) >= '2020'
          AND res.is_invalid = 0
    """, conn)

    conn.close()
    return advance_df, before_df

def analyze_entries_by_venue():
    """会場別の出走選手分析（地元・年齢・級別）"""
    conn = get_connection()

    entries_df = pd.read_sql_query("""
        SELECT
            r.venue_code,
            r.race_date,
            substr(r.race_date, 1, 4) as year,
            e.pit_number,
            e.racer_number,
            e.racer_name,
            e.racer_rank,
            e.racer_home,
            e.racer_age,
            e.win_rate,
            e.motor_number,
            e.motor_second_rate,
            e.avg_st,
            e.f_count,
            e.l_count,
            res.rank as actual_rank,
            res.kimarite
        FROM entries e
        JOIN races r ON e.race_id = r.id
        JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
        WHERE substr(r.race_date, 1, 4) >= '2020'
          AND res.is_invalid = 0
    """, conn)

    conn.close()
    return entries_df

def analyze_course_win_rates():
    """コース別勝率の詳細分析"""
    conn = get_connection()

    course_df = pd.read_sql_query("""
        SELECT
            r.venue_code,
            substr(r.race_date, 1, 4) as year,
            rd.actual_course,
            res.rank,
            res.kimarite,
            COUNT(*) as count
        FROM race_details rd
        JOIN races r ON rd.race_id = r.id
        JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
        WHERE substr(r.race_date, 1, 4) >= '2020'
          AND res.is_invalid = 0
          AND rd.actual_course IS NOT NULL
        GROUP BY r.venue_code, year, rd.actual_course, res.rank, res.kimarite
    """, conn)

    conn.close()
    return course_df

def analyze_odds_distribution():
    """オッズ分布の分析"""
    conn = get_connection()

    odds_df = pd.read_sql_query("""
        SELECT
            r.venue_code,
            substr(r.race_date, 1, 4) as year,
            p.amount as payout,
            p.popularity
        FROM payouts p
        JOIN races r ON p.race_id = r.id
        WHERE p.bet_type = 'trifecta'
          AND substr(r.race_date, 1, 4) >= '2020'
    """, conn)

    conn.close()
    return odds_df

def get_venue_name_map():
    """会場コードと名前のマッピング"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT venue_code, venue_name FROM venue_data")
    result = {row[0]: row[1] for row in cur.fetchall()}
    conn.close()
    return result

def main():
    print("=" * 80)
    print("会場別深掘り分析 開始")
    print("対象: 全24会場 × 6年間 (2020-2025)")
    print("=" * 80)

    # 会場名マッピング
    venue_names = get_venue_name_map()
    print(f"\n会場数: {len(venue_names)}")
    for code, name in sorted(venue_names.items()):
        print(f"  {code}: {name}")

    # 1. 会場基本情報
    print("\n" + "=" * 60)
    print("【1】会場基本情報")
    print("=" * 60)
    venues_df = analyze_venue_basic()
    print(venues_df.to_string())

    # 2. レースコンディション分析
    print("\n" + "=" * 60)
    print("【2】レースコンディション分析（風向・風速・波高）")
    print("=" * 60)
    conditions_df = analyze_race_conditions_by_venue()
    print(f"総レコード数: {len(conditions_df)}")

    # 風向別勝ちコース
    print("\n--- 風向別1着コース分布 ---")
    wind_course = conditions_df.groupby(['wind_direction', 'winner_pit']).size().unstack(fill_value=0)
    print(wind_course)

    # 風速別勝ちコース（0-2m, 2-4m, 4m以上）
    print("\n--- 風速別1着コース分布 ---")
    conditions_df['wind_category'] = pd.cut(
        conditions_df['wind_speed'].fillna(0),
        bins=[0, 2, 4, 100],
        labels=['弱風(0-2m)', '中風(2-4m)', '強風(4m+)']
    )
    wind_speed_course = conditions_df.groupby(['wind_category', 'winner_pit']).size().unstack(fill_value=0)
    print(wind_speed_course)

    # 3. 予測精度分析
    print("\n" + "=" * 60)
    print("【3】予測精度分析（advance vs before）")
    print("=" * 60)
    advance_df, before_df = analyze_predictions_vs_results()
    print(f"advance予測レコード: {len(advance_df)}")
    print(f"before予測レコード: {len(before_df)}")

    # 4. 選手情報分析
    print("\n" + "=" * 60)
    print("【4】選手情報分析（地元・年齢・級別）")
    print("=" * 60)
    entries_df = analyze_entries_by_venue()
    print(f"総エントリー数: {len(entries_df)}")

    # 地元選手の勝率
    print("\n--- 地元選手の勝率分析準備完了 ---")

    # 5. コース別勝率
    print("\n" + "=" * 60)
    print("【5】コース別勝率分析")
    print("=" * 60)
    course_df = analyze_course_win_rates()
    print(f"総レコード数: {len(course_df)}")

    # 6. オッズ分布
    print("\n" + "=" * 60)
    print("【6】オッズ分布分析")
    print("=" * 60)
    odds_df = analyze_odds_distribution()
    print(f"総レコード数: {len(odds_df)}")

    print("\n" + "=" * 80)
    print("データ取得完了")
    print("=" * 80)

    return {
        'venues': venues_df,
        'conditions': conditions_df,
        'advance': advance_df,
        'before': before_df,
        'entries': entries_df,
        'course': course_df,
        'odds': odds_df,
        'venue_names': venue_names
    }

if __name__ == "__main__":
    data = main()
