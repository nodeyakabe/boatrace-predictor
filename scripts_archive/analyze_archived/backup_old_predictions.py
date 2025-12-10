"""
ハイブリッド実装前の予想データをバックアップ

再生成前に既存のrace_predictionsをバックアップテーブルに退避。
ハイブリッド実装前後の性能比較に使用。
"""

import sys
from pathlib import Path
import sqlite3
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main():
    print("=" * 80)
    print("ハイブリッド実装前予想データのバックアップ")
    print("=" * 80)
    print()

    db_path = PROJECT_ROOT / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # バックアップテーブルが既に存在する場合は削除
    print("既存のバックアップテーブルをクリーンアップ中...")
    cursor.execute('DROP TABLE IF EXISTS race_predictions_before_hybrid')
    conn.commit()
    print("完了")
    print()

    # race_predictionsテーブルの構造をコピーしてバックアップテーブル作成
    print("バックアップテーブルを作成中...")
    cursor.execute('''
        CREATE TABLE race_predictions_before_hybrid AS
        SELECT * FROM race_predictions WHERE 1=0
    ''')
    conn.commit()
    print("完了")
    print()

    # 2025年のデータをバックアップ
    print("2025年の予想データをバックアップ中...")
    cursor.execute('''
        INSERT INTO race_predictions_before_hybrid
        SELECT rp.*
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE r.race_date >= '2025-01-01'
          AND r.race_date < '2026-01-01'
    ''')
    backed_up_count = cursor.rowcount
    conn.commit()
    print(f"完了: {backed_up_count:,}件バックアップ")
    print()

    # バックアップデータの確認
    cursor.execute('''
        SELECT COUNT(DISTINCT rp.race_id) as race_count
        FROM race_predictions_before_hybrid rp
    ''')
    race_count = cursor.fetchone()[0]

    cursor.execute('''
        SELECT
            rp.confidence,
            COUNT(DISTINCT rp.race_id) as count
        FROM race_predictions_before_hybrid rp
        GROUP BY rp.confidence
        ORDER BY rp.confidence
    ''')

    print("=" * 80)
    print("バックアップ完了")
    print("=" * 80)
    print()
    print(f"バックアップテーブル: race_predictions_before_hybrid")
    print(f"総レース数: {race_count:,}レース")
    print(f"総レコード数: {backed_up_count:,}件")
    print()
    print("信頼度別レース数:")
    for confidence, count in cursor.fetchall():
        print(f"  信頼度{confidence}: {count:,}レース")
    print()

    # 生成日時の範囲を確認
    cursor.execute('''
        SELECT MIN(generated_at), MAX(generated_at)
        FROM race_predictions_before_hybrid
    ''')
    min_date, max_date = cursor.fetchone()
    print(f"生成日時範囲: {min_date} ～ {max_date}")
    print()

    conn.close()

    print("=" * 80)
    print("次のステップ:")
    print("  1. 予想再生成: python scripts/regenerate_predictions_2025.py")
    print("  2. 比較分析: python scripts/compare_before_after_hybrid.py")
    print("=" * 80)


if __name__ == "__main__":
    main()
