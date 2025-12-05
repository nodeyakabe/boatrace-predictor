"""
法則再解析スクリプト
過去データから法則を抽出し、venue_rulesテーブルを更新
"""

import sys
import os

# Windows コンソールでのUnicodeエラー回避
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# パス設定
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import DATABASE_PATH
from src.ml.rule_extractor import RuleExtractor
import sqlite3


def migrate_to_venue_rules(db_path: str):
    """
    extracted_rulesテーブルからvenue_rulesテーブルへ変換
    """
    import json

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # venue_rulesテーブルが存在しない場合は作成
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS venue_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venue_code TEXT,
            rule_type TEXT NOT NULL,
            condition_type TEXT,
            target_pit INTEGER,
            effect_type TEXT NOT NULL,
            effect_value REAL NOT NULL,
            description TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 既存のvenue_rulesをクリア
    cursor.execute("DELETE FROM venue_rules")

    # extracted_rulesからデータを取得（実際のスキーマに合わせる）
    cursor.execute("""
        SELECT rule_name, condition_json, adjustment, sample_size, confidence
        FROM extracted_rules
        WHERE is_valid = 1
    """)

    rules = cursor.fetchall()
    migrated = 0

    for rule in rules:
        rule_name, condition_json, adjustment, sample_size, confidence = rule

        # JSONをパース
        try:
            conditions = json.loads(condition_json)
        except (json.JSONDecodeError, TypeError):
            conditions = {}

        venue_code = conditions.get('venue_code')
        pit_number = conditions.get('pit_number')
        wind_direction = conditions.get('wind_direction')

        # 効果値を調整（加算方式のため、大きすぎる値は制限）
        adjusted_value = max(-0.15, min(0.15, adjustment))

        # condition_typeを決定
        condition_type = None
        if wind_direction:
            condition_type = 'wind'
        elif venue_code:
            condition_type = 'venue'
        else:
            condition_type = 'general'

        # effect_typeを決定
        effect_type = 'win_rate_boost' if adjustment >= 0 else 'win_rate_penalty'

        # descriptionを生成
        description = rule_name

        cursor.execute("""
            INSERT INTO venue_rules
            (venue_code, rule_type, condition_type, target_pit, effect_type, effect_value, description, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            venue_code,
            'course_advantage',
            condition_type,
            pit_number,
            effect_type,
            adjusted_value,
            description
        ))
        migrated += 1

    conn.commit()
    conn.close()

    return migrated


def main():
    print("=" * 60)
    print("法則再解析")
    print("=" * 60)

    db_path = DATABASE_PATH

    # 1. 法則抽出
    print("\n[1/2] 過去データから法則を抽出中...")
    try:
        extractor = RuleExtractor(db_path)
        rules = extractor.extract_all_rules(min_confidence=0.3)

        if rules:
            print(f"  抽出された法則: {len(rules)}件")

            # DBに保存
            extractor.save_rules_to_db(rules)
            print("  extracted_rulesテーブルに保存完了")
        else:
            print("  抽出された法則はありませんでした")

    except Exception as e:
        print(f"  法則抽出エラー: {e}")
        import traceback
        traceback.print_exc()

    # 2. venue_rulesへの変換
    print("\n[2/2] venue_rulesテーブルへ変換中...")
    try:
        migrated = migrate_to_venue_rules(db_path)
        print(f"  変換完了: {migrated}件")
    except Exception as e:
        print(f"  変換エラー: {e}")
        import traceback
        traceback.print_exc()

    # 結果確認
    print("\n" + "=" * 60)
    print("再解析完了")
    print("=" * 60)

    # 統計表示
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM extracted_rules WHERE is_valid = 1")
    extracted_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM venue_rules WHERE is_active = 1")
    venue_count = cursor.fetchone()[0]

    conn.close()

    print(f"\n結果:")
    print(f"  extracted_rules: {extracted_count}件")
    print(f"  venue_rules: {venue_count}件（予測に使用）")

    return 0


if __name__ == "__main__":
    sys.exit(main())
