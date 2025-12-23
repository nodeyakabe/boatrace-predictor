"""
DB最適化 Phase 1 影響範囲分析スクリプト

races.grade と results.winning_technique カラムの削除前に
データの整合性と影響範囲を徹底的に確認する。
"""

import sqlite3
import sys
import io
from pathlib import Path

# 標準出力をUTF-8に設定
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

DB_PATH = project_root / 'data' / 'boatrace.db'


def analyze_races_grade_columns():
    """races.grade と races.race_grade の分析"""
    print("=" * 80)
    print("【1. races テーブル: grade vs race_grade 分析】")
    print("=" * 80)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 基本統計
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN grade IS NOT NULL AND grade != '' THEN 1 ELSE 0 END) as with_grade,
            SUM(CASE WHEN race_grade IS NOT NULL AND race_grade != '' THEN 1 ELSE 0 END) as with_race_grade,
            SUM(CASE WHEN (grade IS NULL OR grade = '') AND (race_grade IS NULL OR race_grade = '') THEN 1 ELSE 0 END) as both_null
        FROM races
    """)

    row = cursor.fetchone()
    print(f"\n総レース数: {row[0]:,}")
    print(f"grade にデータあり: {row[1]:,} ({row[1]/row[0]*100:.1f}%)")
    print(f"race_grade にデータあり: {row[2]:,} ({row[2]/row[0]*100:.1f}%)")
    print(f"両方とも NULL/空: {row[3]:,} ({row[3]/row[0]*100:.1f}%)")

    # 不一致データの確認
    cursor.execute("""
        SELECT COUNT(*)
        FROM races
        WHERE grade != race_grade
          AND grade IS NOT NULL AND grade != ''
          AND race_grade IS NOT NULL AND race_grade != ''
    """)

    mismatch_count = cursor.fetchone()[0]
    print(f"\n[WARNING] grade と race_grade が不一致: {mismatch_count:,}件")

    if mismatch_count > 0:
        print("\n【不一致の例】")
        cursor.execute("""
            SELECT id, venue_code, race_date, race_number, grade, race_grade
            FROM races
            WHERE grade != race_grade
              AND grade IS NOT NULL AND grade != ''
              AND race_grade IS NOT NULL AND race_grade != ''
            LIMIT 10
        """)

        for row in cursor.fetchall():
            print(f"  race_id={row[0]}, venue={row[1]}, date={row[2]}, race_num={row[3]}, "
                  f"grade='{row[4]}', race_grade='{row[5]}'")

    # パターン分析
    print("\n【データパターン分析】")
    cursor.execute("""
        SELECT
            CASE
                WHEN (grade IS NULL OR grade = '') AND (race_grade IS NOT NULL AND race_grade != '') THEN 'race_gradeのみ'
                WHEN (grade IS NOT NULL AND grade != '') AND (race_grade IS NULL OR race_grade = '') THEN 'gradeのみ'
                WHEN grade = race_grade THEN '一致'
                WHEN grade != race_grade THEN '不一致'
                ELSE '両方NULL'
            END as pattern,
            COUNT(*) as count
        FROM races
        GROUP BY pattern
        ORDER BY count DESC
    """)

    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]:,}件")

    # race_grade のみにデータがある場合の値
    print("\n【race_gradeのみにデータがある場合の値の分布】")
    cursor.execute("""
        SELECT race_grade, COUNT(*) as count
        FROM races
        WHERE (grade IS NULL OR grade = '')
          AND (race_grade IS NOT NULL AND race_grade != '')
        GROUP BY race_grade
        ORDER BY count DESC
        LIMIT 10
    """)

    for row in cursor.fetchall():
        print(f"  '{row[0]}': {row[1]:,}件")

    conn.close()


def analyze_results_winning_technique():
    """results.winning_technique と results.kimarite の分析"""
    print("\n\n" + "=" * 80)
    print("【2. results テーブル: winning_technique vs kimarite 分析】")
    print("=" * 80)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 基本統計（1着のみ）
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN winning_technique IS NOT NULL THEN 1 ELSE 0 END) as with_winning_technique,
            SUM(CASE WHEN kimarite IS NOT NULL AND kimarite != '' THEN 1 ELSE 0 END) as with_kimarite
        FROM results
        WHERE rank = '1'
    """)

    row = cursor.fetchone()
    print(f"\n1着の結果数: {row[0]:,}")
    print(f"winning_technique にデータあり: {row[1]:,} ({row[1]/row[0]*100:.1f}%)")
    print(f"kimarite にデータあり: {row[2]:,} ({row[2]/row[0]*100:.1f}%)")

    # winning_technique の値の分布
    print("\n【winning_technique の値の分布】")
    cursor.execute("""
        SELECT winning_technique, COUNT(*) as count
        FROM results
        WHERE rank = '1' AND winning_technique IS NOT NULL
        GROUP BY winning_technique
        ORDER BY count DESC
    """)

    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]:,}件")

    # kimarite の値の分布
    print("\n【kimarite の値の分布】")
    cursor.execute("""
        SELECT kimarite, COUNT(*) as count
        FROM results
        WHERE rank = '1' AND kimarite IS NOT NULL AND kimarite != ''
        GROUP BY kimarite
        ORDER BY count DESC
    """)

    for row in cursor.fetchall():
        print(f"  '{row[0]}': {row[1]:,}件")

    # 2着以降にデータがあるか確認
    cursor.execute("""
        SELECT COUNT(*)
        FROM results
        WHERE rank != '1'
          AND (winning_technique IS NOT NULL OR (kimarite IS NOT NULL AND kimarite != ''))
    """)

    non_first = cursor.fetchone()[0]
    print(f"\n[WARNING] 2着以降でデータあり: {non_first:,}件")

    if non_first > 0:
        cursor.execute("""
            SELECT race_id, pit_number, rank, winning_technique, kimarite
            FROM results
            WHERE rank != '1'
              AND (winning_technique IS NOT NULL OR (kimarite IS NOT NULL AND kimarite != ''))
            LIMIT 5
        """)

        print("【2着以降でデータがある例】")
        for row in cursor.fetchall():
            print(f"  race_id={row[0]}, pit={row[1]}, rank={row[2]}, "
                  f"winning_technique={row[3]}, kimarite='{row[4]}'")

    conn.close()


def check_code_impact():
    """コードへの影響範囲の確認"""
    print("\n\n" + "=" * 80)
    print("【3. コードへの影響範囲サマリー】")
    print("=" * 80)

    print("\n[A] races.grade カラム削除の影響:")
    print("  [OK] src/database/data_manager.py:214 - INSERT/UPDATE処理でgradeを使用")
    print("       -> race_grade に統一する必要あり")
    print("  [OK] src/database/models.py - テーブル定義でgradeカラムを定義")
    print("       -> 削除する必要あり")
    print("  影響ファイル数: 約26ファイルで'grade'キーワードを使用")
    print("    (ただし、ほとんどはrace_gradeまたは無関係な用語)")

    print("\n[B] results.winning_technique カラム削除の影響:")
    print("  [OK] src/database/data_manager.py:568,573 - INSERT処理でwinning_techniqueを使用")
    print("       -> 削除する必要あり(kimariteのみ保存)")
    print("  影響ファイル数: 約29ファイルで'winning_technique'キーワードを使用")
    print("    (ほとんどはデータ保存・読み取り処理)")


def generate_recommendations():
    """推奨対策の提示"""
    print("\n\n" + "=" * 80)
    print("【4. 推奨対策】")
    print("=" * 80)

    print("\n【Phase 1-1: races.grade カラムの削除】")
    print("  1. データマージ: race_grade が NULL/空の場合、grade の値をコピー")
    print("  2. コード修正:")
    print("     - data_manager.py:214 の grade 参照を削除")
    print("     - models.py のテーブル定義から grade カラムを削除")
    print("  3. テーブル再作成:")
    print("     - grade カラムを除外した新テーブル作成")
    print("     - データ移行")
    print("     - インデックス再作成")

    print("\n【Phase 1-2: results.winning_technique カラムの削除】")
    print("  1. コード修正:")
    print("     - data_manager.py:568,573 の winning_technique 参照を削除")
    print("  2. テーブル再作成:")
    print("     - winning_technique カラムを除外した新テーブル作成")
    print("     - データ移行")
    print("     - インデックス再作成")

    print("\n【重要な注意事項】")
    print("  [!] SQLiteはALTER TABLE DROP COLUMN非対応(直接削除不可)")
    print("  [!] テーブル再作成が必要(CREATE -> INSERT -> DROP -> RENAME)")
    print("  [!] インデックスも再作成が必要")
    print("  [!] バックアップ必須(data/boatrace_backup_YYYYMMDD.db)")


def main():
    """メイン処理"""
    print("DB最適化 Phase 1 影響範囲分析")
    print("分析対象: races.grade, results.winning_technique")
    print()

    # 分析実行
    analyze_races_grade_columns()
    analyze_results_winning_technique()
    check_code_impact()
    generate_recommendations()

    print("\n" + "=" * 80)
    print("分析完了")
    print("=" * 80)


if __name__ == "__main__":
    main()
