"""
全会場のパターン分析を実行し、結果をDBに保存するスクリプト
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import json
from datetime import datetime
from src.analysis.pattern_discovery import PatternDiscovery


def create_pattern_tables(db_path: str):
    """パターン保存用テーブルを作成"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 発見されたパターンを保存するテーブル
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS discovered_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_id TEXT UNIQUE,
            pattern_type TEXT,
            venue_code TEXT,
            description TEXT,
            conditions TEXT,
            sample_count INTEGER,
            win_rate REAL,
            baseline_rate REAL,
            lift REAL,
            confidence_interval_low REAL,
            confidence_interval_high REAL,
            p_value REAL,
            effect_size REAL,
            reliability_score REAL,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 反証条件を保存するテーブル
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pattern_counter_conditions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_id TEXT,
            condition_type TEXT,
            condition_value TEXT,
            description TEXT,
            win_rate REAL,
            sample_count INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (pattern_id) REFERENCES discovered_patterns(pattern_id)
        )
    """)

    conn.commit()
    conn.close()


def save_patterns_to_db(db_path: str, patterns: list, venue_code: str, pattern_type: str):
    """パターンをDBに保存"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for p in patterns:
        cursor.execute("""
            INSERT OR REPLACE INTO discovered_patterns
            (pattern_id, pattern_type, venue_code, description, conditions,
             sample_count, win_rate, baseline_rate, lift,
             confidence_interval_low, confidence_interval_high,
             p_value, effect_size, reliability_score, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            p.pattern_id,
            pattern_type,
            venue_code,
            p.description,
            json.dumps(p.conditions, ensure_ascii=False),
            p.sample_count,
            p.win_rate,
            p.baseline_win_rate,
            p.lift,
            p.confidence_interval[0],
            p.confidence_interval[1],
            p.p_value,
            p.effect_size,
            p.reliability_score,
            datetime.now().isoformat()
        ))

    conn.commit()
    conn.close()


def main():
    db_path = "data/boatrace.db"
    discovery = PatternDiscovery(db_path)

    # テーブル作成
    print("パターン保存用テーブルを作成...")
    create_pattern_tables(db_path)

    print("=" * 70)
    print("全会場パターン分析")
    print("=" * 70)
    print()

    venue_names = discovery.VENUE_NAMES
    total_patterns = 0

    for venue_code, venue_name in venue_names.items():
        print(f"【{venue_name}({venue_code})】を分析中...")

        # 決まり手パターン
        kimarite_patterns = discovery.analyze_venue_course_kimarite(venue_code, days=365)
        if kimarite_patterns:
            save_patterns_to_db(db_path, kimarite_patterns, venue_code, 'kimarite')
            print(f"  決まり手パターン: {len(kimarite_patterns)}件")

            # 上位3件を表示
            for p in kimarite_patterns[:3]:
                print(f"    - {p.description}: 信頼性{p.reliability_score:.0f}")

            total_patterns += len(kimarite_patterns)

        # 潮位パターン（海水会場のみ）
        if venue_code in discovery.SEAWATER_VENUES:
            tide_patterns = discovery.analyze_venue_tide_patterns(venue_code, days=365)
            if tide_patterns:
                save_patterns_to_db(db_path, tide_patterns, venue_code, 'tide')
                print(f"  潮位パターン: {len(tide_patterns)}件")

                for p in tide_patterns[:3]:
                    print(f"    - {p.description}: 信頼性{p.reliability_score:.0f}")

                total_patterns += len(tide_patterns)

            # 潮位×決まり手複合パターン
            compound_patterns = discovery.analyze_venue_tide_kimarite_patterns(venue_code, days=365)
            if compound_patterns:
                save_patterns_to_db(db_path, compound_patterns, venue_code, 'tide_kimarite')
                print(f"  潮位×決まり手複合パターン: {len(compound_patterns)}件")

                for p in compound_patterns[:3]:
                    print(f"    - {p.description}: 信頼性{p.reliability_score:.0f}")

                total_patterns += len(compound_patterns)

        print()

    print("=" * 70)
    print(f"合計パターン数: {total_patterns}件")
    print("=" * 70)

    # 信頼性の高いパターンTOP10を表示
    print()
    print("【信頼性の高いパターン TOP10】")
    print("-" * 70)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT description, sample_count, win_rate, baseline_rate,
               reliability_score, effect_size
        FROM discovered_patterns
        ORDER BY reliability_score DESC
        LIMIT 10
    """)

    for i, row in enumerate(cursor.fetchall(), 1):
        desc, samples, win_rate, baseline, reliability, effect = row
        print(f"{i:2d}. {desc}")
        print(f"    勝率: {win_rate*100:.1f}% (基準: {baseline*100:.1f}%), "
              f"サンプル: {samples}, 信頼性: {reliability:.0f}")
        if effect > 5:
            print(f"    推奨バフ: +{effect:.1f}点")
        print()

    conn.close()


if __name__ == "__main__":
    main()
