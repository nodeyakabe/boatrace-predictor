#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
新規施策の検証結果を知見DBに登録
================================

使用例:
    python scripts/register_experiment.py \
        --id "new_scoring_method" \
        --name "新スコアリング手法" \
        --category "scoring" \
        --result "rejected" \
        --effect "-1.5pt" \
        --reason "2025年データで効果なし" \
        --keywords "スコア,計算方法,改善"
"""

import argparse
import sqlite3
import json
import sys
import io
from pathlib import Path
from datetime import datetime

# Windows環境でのUnicode出力対応
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

DB_PATH = Path(__file__).parent.parent / "knowledge.db"
INDEX_PATH = Path(__file__).parent.parent / "knowledge_index.json"


def register_to_db(args):
    """DBに登録"""
    if not DB_PATH.exists():
        print(f"[ERROR] 知見DBが見つかりません: {DB_PATH}")
        print("先に 'python scripts/setup_knowledge_db.py' を実行してください")
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 施策を登録
        cursor.execute("""
            INSERT INTO experiments (id, name, category, date_tested, result, effect_value,
                                     rejection_reason, lesson, doc_reference)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            args.id,
            args.name,
            args.category,
            args.date or datetime.now().strftime('%Y-%m-%d'),
            args.result,
            args.effect,
            args.reason,
            args.lesson,
            args.doc
        ))

        # キーワードを登録
        if args.keywords:
            for keyword in args.keywords.split(','):
                keyword = keyword.strip()
                cursor.execute("""
                    INSERT INTO experiment_keywords (experiment_id, keyword)
                    VALUES (?, ?)
                """, (args.id, keyword))

        # 関連ファイルを登録
        if args.files:
            for file_path in args.files.split(','):
                file_path = file_path.strip()
                cursor.execute("""
                    INSERT INTO experiment_files (experiment_id, file_path, file_type)
                    VALUES (?, ?, ?)
                """, (args.id, file_path, "implementation"))

        conn.commit()
        print(f"✅ DBに登録完了: {args.id}")
        return True

    except sqlite3.IntegrityError as e:
        print(f"[ERROR] 登録失敗: {e}")
        print(f"ID '{args.id}' は既に存在します")
        return False

    finally:
        conn.close()


def update_json_index(args):
    """JSONインデックスも更新"""

    with open(INDEX_PATH, 'r', encoding='utf-8') as f:
        index = json.load(f)

    # 新規実験を追加
    new_experiment = {
        "id": args.id,
        "name": args.name,
        "category": args.category,
        "keywords": [kw.strip() for kw in args.keywords.split(',')] if args.keywords else [],
        "date_tested": args.date or datetime.now().strftime('%Y-%m-%d'),
        "result": args.result,
        "effect": args.effect
    }

    if args.reason:
        new_experiment["rejection_reason"] = args.reason
    if args.lesson:
        new_experiment["lesson"] = args.lesson
    if args.doc:
        new_experiment["doc_reference"] = args.doc
    if args.files:
        new_experiment["related_files"] = [f.strip() for f in args.files.split(',')]

    # 既存のエントリーを確認
    experiments = index.get("experiments", [])
    existing = next((exp for exp in experiments if exp["id"] == args.id), None)

    if existing:
        # 更新
        experiments.remove(existing)
        experiments.append(new_experiment)
        print(f"⚠️  JSONインデックス更新: {args.id}")
    else:
        # 新規追加
        experiments.append(new_experiment)
        print(f"✅ JSONインデックス追加: {args.id}")

    index["experiments"] = experiments

    # メタデータ更新
    index["metadata"]["last_updated"] = datetime.now().strftime('%Y-%m-%d')
    index["metadata"]["total_experiments"] = len(experiments)
    index["metadata"]["accepted_count"] = sum(1 for e in experiments if e["result"] == "accepted")
    index["metadata"]["rejected_count"] = sum(1 for e in experiments if e["result"] == "rejected")

    # 保存
    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"✅ JSONインデックス保存完了")


def main():
    parser = argparse.ArgumentParser(description='新規施策を知見DBに登録')
    parser.add_argument('--id', required=True, help='施策ID（例: new_scoring_method）')
    parser.add_argument('--name', required=True, help='施策名（例: 新スコアリング手法）')
    parser.add_argument('--category', required=True, help='カテゴリ（例: scoring, odds_integration）')
    parser.add_argument('--result', required=True, choices=['accepted', 'rejected', 'pending'],
                        help='結果（accepted/rejected/pending）')
    parser.add_argument('--effect', help='効果（例: +2.5pt, -1.0pt）')
    parser.add_argument('--reason', help='不採用理由（resultがrejectedの場合）')
    parser.add_argument('--lesson', help='教訓・学び')
    parser.add_argument('--keywords', help='キーワード（カンマ区切り、例: スコア,計算方法）')
    parser.add_argument('--files', help='関連ファイル（カンマ区切り）')
    parser.add_argument('--doc', help='詳細ドキュメント（例: docs/improvement_attempts/xxx.md）')
    parser.add_argument('--date', help='実施日（YYYY-MM-DD、省略時は今日）')

    args = parser.parse_args()

    print("=" * 80)
    print("新規施策の登録")
    print("=" * 80)
    print(f"ID:       {args.id}")
    print(f"名前:     {args.name}")
    print(f"カテゴリ: {args.category}")
    print(f"結果:     {args.result}")
    print(f"効果:     {args.effect or 'なし'}")
    print("=" * 80)
    print()

    # DBに登録
    if not register_to_db(args):
        sys.exit(1)

    # JSONインデックスを更新
    update_json_index(args)

    print()
    print("=" * 80)
    print("✅ 登録完了")
    print("=" * 80)
    print()
    print("次のステップ:")
    if args.result == "rejected":
        print("1. docs/improvement_attempts/ に詳細ドキュメントを作成")
        print("2. 失敗事例の場合は docs/lessons_learned/ に教訓を記録")
    elif args.result == "accepted":
        print("1. config/feature_flags.py にフラグを追加")
        print("2. DAILY_REPORTに実装内容を記録")
    print()


if __name__ == "__main__":
    main()
