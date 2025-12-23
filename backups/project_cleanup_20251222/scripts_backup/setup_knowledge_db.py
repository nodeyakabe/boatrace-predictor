#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
知見データベースのセットアップ
==============================

knowledge_index.json から SQLite DB を構築する。
"""

import json
import sqlite3
import sys
import io
from pathlib import Path
from datetime import datetime

# Windows環境でのUnicode出力対応
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

DB_PATH = Path(__file__).parent.parent / "knowledge.db"
INDEX_PATH = Path(__file__).parent.parent / "knowledge_index.json"


def create_tables(conn: sqlite3.Connection):
    """テーブル作成"""
    cursor = conn.cursor()

    # 施策テーブル
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS experiments (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT,
            date_tested DATE,
            result TEXT CHECK(result IN ('accepted', 'rejected', 'pending')),
            effect_value TEXT,
            rejection_reason TEXT,
            lesson TEXT,
            doc_reference TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # キーワードテーブル
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS experiment_keywords (
            experiment_id TEXT,
            keyword TEXT,
            FOREIGN KEY (experiment_id) REFERENCES experiments(id)
        )
    """)

    # 関連ファイルテーブル
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS experiment_files (
            experiment_id TEXT,
            file_path TEXT,
            file_type TEXT,
            FOREIGN KEY (experiment_id) REFERENCES experiments(id)
        )
    """)

    # 既知の落とし穴テーブル
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS known_pitfalls (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            symptom TEXT,
            root_cause TEXT,
            solution TEXT,
            performance_improvement TEXT,
            first_discovered DATE,
            occurrence_count INTEGER DEFAULT 1
        )
    """)

    # 実装済み機能テーブル
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS implemented_features (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT CHECK(status IN ('enabled', 'disabled', 'archived')),
            effect TEXT,
            enabled_date DATE,
            flag_name TEXT
        )
    """)

    # インデックス作成
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_experiments_category ON experiments(category)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_experiments_result ON experiments(result)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_keywords ON experiment_keywords(keyword)")

    conn.commit()


def import_from_json(conn: sqlite3.Connection):
    """JSONからデータをインポート"""

    if not INDEX_PATH.exists():
        print(f"[ERROR] {INDEX_PATH} が見つかりません")
        return

    with open(INDEX_PATH, 'r', encoding='utf-8') as f:
        index = json.load(f)

    cursor = conn.cursor()

    # 既存データをクリア
    cursor.execute("DELETE FROM experiment_keywords")
    cursor.execute("DELETE FROM experiment_files")
    cursor.execute("DELETE FROM experiments")
    cursor.execute("DELETE FROM known_pitfalls")
    cursor.execute("DELETE FROM implemented_features")

    # 実験結果をインポート
    for exp in index.get("experiments", []):
        # 効果値の統合
        effect = exp.get("effect")
        if not effect and "effect_2024" in exp:
            effect = f"2024: {exp['effect_2024']}, 2025: {exp.get('effect_2025', '未測定')}"

        cursor.execute("""
            INSERT INTO experiments (id, name, category, date_tested, result, effect_value,
                                     rejection_reason, lesson, doc_reference)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            exp["id"],
            exp["name"],
            exp.get("category"),
            exp.get("date_tested"),
            exp["result"],
            effect,
            exp.get("rejection_reason"),
            exp.get("lesson"),
            exp.get("doc_reference")
        ))

        # キーワード
        for keyword in exp.get("keywords", []):
            cursor.execute("""
                INSERT INTO experiment_keywords (experiment_id, keyword)
                VALUES (?, ?)
            """, (exp["id"], keyword))

        # 関連ファイル
        for file_path in exp.get("related_files", []):
            cursor.execute("""
                INSERT INTO experiment_files (experiment_id, file_path, file_type)
                VALUES (?, ?, ?)
            """, (exp["id"], file_path, "implementation"))

    # 既知の落とし穴をインポート
    for pitfall in index.get("known_pitfalls", []):
        cursor.execute("""
            INSERT INTO known_pitfalls (id, name, symptom, root_cause, solution,
                                        performance_improvement, first_discovered, occurrence_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            pitfall["id"],
            pitfall["name"],
            pitfall.get("symptom"),
            pitfall.get("root_cause"),
            pitfall.get("solution"),
            pitfall.get("performance_improvement"),
            pitfall.get("first_discovered"),
            pitfall.get("occurrence_count", 1)
        ))

    # 実装済み機能をインポート
    for feature in index.get("implemented_features", []):
        cursor.execute("""
            INSERT INTO implemented_features (id, name, status, effect, enabled_date, flag_name)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            feature["id"],
            feature["name"],
            feature["status"],
            feature.get("effect"),
            feature.get("enabled_date"),
            feature.get("flag_name")
        ))

    conn.commit()

    print(f"✅ インポート完了:")
    print(f"  - 実験結果: {len(index.get('experiments', []))} 件")
    print(f"  - 既知の落とし穴: {len(index.get('known_pitfalls', []))} 件")
    print(f"  - 実装済み機能: {len(index.get('implemented_features', []))} 件")


def main():
    """メイン処理"""
    print("知見データベースをセットアップします...")
    print(f"DB Path: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)

    try:
        create_tables(conn)
        print("✅ テーブル作成完了")

        import_from_json(conn)

        print(f"\n✅ 知見データベースのセットアップが完了しました: {DB_PATH}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
