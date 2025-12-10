# -*- coding: utf-8 -*-
"""
攻略パターンテーブル用のインデックスを追加

パフォーマンス向上のため、よく使われるクエリに対してインデックスを作成
"""

import sqlite3

def add_indexes():
    """攻略パターンテーブルにインデックスを追加"""

    db_path = 'data/boatrace.db'

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        print("=" * 70)
        print("攻略パターンテーブルにインデックスを追加中...")
        print("=" * 70)

        # venue_racer_patternsテーブル用のインデックス
        # 会場コードでの検索が頻繁に行われるため
        try:
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_venue_racer_venue
                ON venue_racer_patterns(venue_code)
            ''')
            print("[OK] idx_venue_racer_venue を作成しました")
        except Exception as e:
            print(f"[NG] idx_venue_racer_venue の作成に失敗: {e}")

        # 選手番号での検索用
        try:
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_venue_racer_racer
                ON venue_racer_patterns(racer_number)
            ''')
            print("[OK] idx_venue_racer_racer を作成しました")
        except Exception as e:
            print(f"[NG] idx_venue_racer_racer の作成に失敗: {e}")

        # racer_attack_patternsテーブル用
        # ランクでの絞り込み用
        try:
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_racer_patterns_rank
                ON racer_attack_patterns(rank)
            ''')
            print("[OK] idx_racer_patterns_rank を作成しました")
        except Exception as e:
            print(f"[NG] idx_racer_patterns_rank の作成に失敗: {e}")

        # venue_attack_patternsテーブル用
        # 荒れ率でのソート用
        try:
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_venue_patterns_upset
                ON venue_attack_patterns(upset_rate)
            ''')
            print("[OK] idx_venue_patterns_upset を作成しました")
        except Exception as e:
            print(f"[NG] idx_venue_patterns_upset の作成に失敗: {e}")

        conn.commit()

        print("=" * 70)
        print("インデックスの追加が完了しました")
        print("=" * 70)

        # 作成されたインデックスを確認
        cursor.execute('''
            SELECT name FROM sqlite_master
            WHERE type='index'
            AND (name LIKE '%attack%' OR name LIKE '%racer_patterns%' OR name LIKE '%venue_racer%')
            ORDER BY name
        ''')

        indexes = cursor.fetchall()
        print("\n現在のインデックス一覧:")
        for idx in indexes:
            print(f"  - {idx[0]}")

        print()

if __name__ == "__main__":
    add_indexes()
