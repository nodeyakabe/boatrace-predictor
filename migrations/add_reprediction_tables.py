"""
再予測機能のためのデータベーステーブル追加
"""

import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
from config.settings import DATABASE_PATH

def add_reprediction_tables():
    """再予測用のテーブルを追加"""

    print("=" * 80)
    print("再予測機能用テーブルの追加")
    print("=" * 80)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 1. 展示データテーブル
    print("\n1. exhibition_data テーブルを作成中...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exhibition_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            race_id INTEGER NOT NULL,
            pit_number INTEGER NOT NULL,
            exhibition_time REAL,           -- 展示タイム（秒）
            start_timing INTEGER,           -- スタートタイミング評価（1-5）
            turn_quality INTEGER,           -- ターン評価（1-5）
            weight_change REAL,             -- 体重変化（kg）
            boat_condition TEXT,            -- 艇の状態コメント
            collected_at TEXT,              -- データ取得日時
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(race_id, pit_number),
            FOREIGN KEY (race_id) REFERENCES races(id)
        )
    """)
    print("   ✓ exhibition_data テーブル作成完了")

    # 2. レース条件テーブル
    print("\n2. race_conditions テーブルを作成中...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS race_conditions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            race_id INTEGER NOT NULL UNIQUE,
            weather TEXT,                   -- 天候（晴、曇、雨など）
            wind_direction TEXT,            -- 風向（無風、向い風、追い風、横風）
            wind_speed REAL,                -- 風速（m/s）
            wave_height INTEGER,            -- 波高（cm）
            temperature REAL,               -- 気温（℃）
            water_temperature REAL,         -- 水温（℃）
            collected_at TEXT,              -- データ取得日時
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (race_id) REFERENCES races(id)
        )
    """)
    print("   ✓ race_conditions テーブル作成完了")

    # 3. 実際の進入コーステーブル
    print("\n3. actual_courses テーブルを作成中...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS actual_courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            race_id INTEGER NOT NULL,
            pit_number INTEGER NOT NULL,
            actual_course INTEGER NOT NULL, -- 実際の進入コース（1-6）
            collected_at TEXT,              -- データ取得日時
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(race_id, pit_number),
            FOREIGN KEY (race_id) REFERENCES races(id)
        )
    """)
    print("   ✓ actual_courses テーブル作成完了")

    # 4. 予測履歴テーブル
    print("\n4. prediction_history テーブルを作成中...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS prediction_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            race_id INTEGER NOT NULL,
            pit_number INTEGER NOT NULL,
            prediction_type TEXT NOT NULL,  -- 'initial' or 'updated'
            rank_prediction INTEGER,
            confidence TEXT,
            total_score REAL,
            course_score REAL,
            racer_score REAL,
            motor_score REAL,
            kimarite_score REAL,
            grade_score REAL,
            has_exhibition_data BOOLEAN DEFAULT 0,
            has_condition_data BOOLEAN DEFAULT 0,
            has_course_data BOOLEAN DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (race_id) REFERENCES races(id)
        )
    """)
    print("   ✓ prediction_history テーブル作成完了")

    # インデックス作成
    print("\n5. インデックスを作成中...")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_exhibition_race ON exhibition_data(race_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_conditions_race ON race_conditions(race_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_actual_courses_race ON actual_courses(race_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pred_history_race ON prediction_history(race_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pred_history_type ON prediction_history(prediction_type)")
    print("   ✓ インデックス作成完了")

    conn.commit()
    conn.close()

    print("\n" + "=" * 80)
    print("データベース拡張が完了しました")
    print("=" * 80)
    print("\n追加されたテーブル:")
    print("  • exhibition_data    - 展示データ（展示タイム、スタート評価など）")
    print("  • race_conditions    - レース条件（天候、風向、風速など）")
    print("  • actual_courses     - 実際の進入コース")
    print("  • prediction_history - 予測履歴（初期予測と更新予測の比較用）")
    print("=" * 80)


if __name__ == "__main__":
    add_reprediction_tables()
