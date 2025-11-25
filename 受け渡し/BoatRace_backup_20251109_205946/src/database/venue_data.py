"""
会場データ管理モジュール

BOAT RACE公式サイトから取得した会場データをデータベースに保存・取得
"""

import sqlite3
from typing import Dict, List, Optional
from datetime import datetime
import json


class VenueDataManager:
    """会場データの保存・取得を管理"""

    def __init__(self, db_path: str):
        """
        初期化

        Args:
            db_path: データベースファイルのパス
        """
        self.db_path = db_path
        self._create_table()

    def _create_table(self):
        """
        venue_dataテーブルを作成（存在しない場合）
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS venue_data (
                venue_code TEXT PRIMARY KEY,  -- '01'〜'24'
                venue_name TEXT NOT NULL,      -- '桐生', '戸田', ...
                water_type TEXT,                -- '淡水', '海水', '汽水'
                tidal_range TEXT,               -- '干満差あり' or 'なし'
                motor_type TEXT,                -- 'モーター種別'
                course_1_win_rate REAL,         -- 1コース1着率（%）
                course_2_win_rate REAL,         -- 2コース1着率（%）
                course_3_win_rate REAL,         -- 3コース1着率（%）
                course_4_win_rate REAL,         -- 4コース1着率（%）
                course_5_win_rate REAL,         -- 5コース1着率（%）
                course_6_win_rate REAL,         -- 6コース1着率（%）
                record_time TEXT,               -- レコード時間（例: '1.42.8'）
                record_holder TEXT,             -- レコードホルダー名
                record_date TEXT,               -- レコード日付（例: '2004/10/27'）
                characteristics TEXT,           -- 水面特性の説明文
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP  -- 最終更新日時
            )
        """)

        conn.commit()
        conn.close()

        # print(f"venue_dataテーブル確認完了: {self.db_path}")

    def save_venue_data(self, venue_data: Dict) -> bool:
        """
        会場データを保存（UPSERT）

        Args:
            venue_data: {
                'venue_code': '01',
                'venue_name': '桐生',
                ...
            }

        Returns:
            成功: True, 失敗: False
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # UPSERT（INSERT or REPLACE）
            cursor.execute("""
                INSERT OR REPLACE INTO venue_data (
                    venue_code, venue_name, water_type, tidal_range, motor_type,
                    course_1_win_rate, course_2_win_rate, course_3_win_rate,
                    course_4_win_rate, course_5_win_rate, course_6_win_rate,
                    record_time, record_holder, record_date, characteristics,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                venue_data.get('venue_code'),
                venue_data.get('venue_name'),
                venue_data.get('water_type'),
                venue_data.get('tidal_range'),
                venue_data.get('motor_type'),
                venue_data.get('course_1_win_rate'),
                venue_data.get('course_2_win_rate'),
                venue_data.get('course_3_win_rate'),
                venue_data.get('course_4_win_rate'),
                venue_data.get('course_5_win_rate'),
                venue_data.get('course_6_win_rate'),
                venue_data.get('record_time'),
                venue_data.get('record_holder'),
                venue_data.get('record_date'),
                venue_data.get('characteristics'),
                datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ))

            conn.commit()
            conn.close()

            return True

        except Exception as e:
            print(f"[ERROR] 保存エラー: {venue_data.get('venue_code')} - {e}")
            return False

    def save_all_venues(self, all_venue_data: Dict[str, Dict]) -> int:
        """
        全会場データを一括保存

        Args:
            all_venue_data: {'01': {...}, '02': {...}, ...}

        Returns:
            保存成功件数
        """
        success_count = 0

        for venue_code, data in all_venue_data.items():
            if self.save_venue_data(data):
                success_count += 1

        print(f"[OK] 会場データ保存完了: {success_count}/{len(all_venue_data)}件")
        return success_count

    def get_venue_data(self, venue_code: str) -> Optional[Dict]:
        """
        指定会場のデータを取得

        Args:
            venue_code: '01'〜'24'

        Returns:
            会場データ辞書 or None
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # 辞書形式で取得
            cursor = conn.cursor()

            cursor.execute("""
                SELECT * FROM venue_data WHERE venue_code = ?
            """, (venue_code,))

            row = cursor.fetchone()
            conn.close()

            if row:
                return dict(row)
            else:
                return None

        except Exception as e:
            print(f"[ERROR] 取得エラー: {venue_code} - {e}")
            return None

    def get_all_venues(self) -> List[Dict]:
        """
        全会場データを取得

        Returns:
            [{...}, {...}, ...] （会場コード順）
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT * FROM venue_data ORDER BY venue_code
            """)

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]

        except Exception as e:
            print(f"[ERROR] 全取得エラー: {e}")
            return []

    def get_venue_win_rates(self) -> Dict[str, List[float]]:
        """
        全会場のコース別勝率を取得

        Returns:
            {
                '01': [47.6, 15.2, 12.1, 10.3, 8.5, 6.3],  # 1〜6コース勝率
                '02': [...],
                ...
            }
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT venue_code,
                       course_1_win_rate, course_2_win_rate, course_3_win_rate,
                       course_4_win_rate, course_5_win_rate, course_6_win_rate
                FROM venue_data
                ORDER BY venue_code
            """)

            rows = cursor.fetchall()
            conn.close()

            result = {}
            for row in rows:
                win_rates = [
                    row['course_1_win_rate'] or 0.0,
                    row['course_2_win_rate'] or 0.0,
                    row['course_3_win_rate'] or 0.0,
                    row['course_4_win_rate'] or 0.0,
                    row['course_5_win_rate'] or 0.0,
                    row['course_6_win_rate'] or 0.0
                ]
                result[row['venue_code']] = win_rates

            return result

        except Exception as e:
            print(f"[ERROR] 勝率取得エラー: {e}")
            return {}

    def count_venues(self) -> int:
        """
        保存されている会場数を取得

        Returns:
            会場数
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM venue_data")
            count = cursor.fetchone()[0]

            conn.close()
            return count

        except Exception as e:
            print(f"[ERROR] カウントエラー: {e}")
            return 0


if __name__ == "__main__":
    # テスト実行
    from config.settings import DATABASE_PATH

    print("="*70)
    print("会場データ管理モジュール テスト")
    print("="*70)

    manager = VenueDataManager(DATABASE_PATH)

    # テストデータ
    test_data = {
        'venue_code': '01',
        'venue_name': '桐生',
        'water_type': '淡水',
        'tidal_range': 'なし',
        'motor_type': '減音',
        'course_1_win_rate': 47.6,
        'course_2_win_rate': 15.2,
        'course_3_win_rate': 12.1,
        'course_4_win_rate': 10.3,
        'course_5_win_rate': 8.5,
        'course_6_win_rate': 6.3,
        'record_time': '1.42.8',
        'record_holder': '石田章央',
        'record_date': '2004/10/27',
        'characteristics': 'テスト用の特性説明'
    }

    print("\n【テスト1: データ保存】")
    if manager.save_venue_data(test_data):
        print("  ✓ 保存成功")

    print("\n【テスト2: データ取得】")
    data = manager.get_venue_data('01')
    if data:
        print("  ✓ 取得成功:")
        print(f"    会場名: {data['venue_name']}")
        print(f"    水質: {data['water_type']}")
        print(f"    1コース勝率: {data['course_1_win_rate']}%")

    print("\n【テスト3: 全会場数カウント】")
    count = manager.count_venues()
    print(f"  保存されている会場数: {count}件")

    print("\n" + "="*70)
    print("テスト完了")
    print("="*70)
