import sqlite3
import sys

# Windows環境でのUTF-8出力設定
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def check_2024_data():
    """2024年予測生成に必要なデータを確認"""
    db_path = r"C:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\data\boatrace.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("=" * 80)
    print("2024年予測データ生成の準備状況確認")
    print("=" * 80)

    # 2024年のレース数を確認
    cursor.execute("""
        SELECT COUNT(*)
        FROM races
        WHERE race_date >= '2024-01-01' AND race_date < '2025-01-01'
    """)
    total_races_2024 = cursor.fetchone()[0]

    print(f"\n【2024年レース総数】: {total_races_2024:,} レース")

    # 各テーブルのデータカバー率を確認
    tables_to_check = [
        ("entries", "出走表", "race_id"),
        ("race_details", "直前情報", "race_id"),
        ("results", "レース結果", "race_id"),
        ("payouts", "払戻金", "race_id"),
        ("trifecta_odds", "3連単オッズ", "race_id"),
        ("race_conditions", "レース条件（天候等）", "race_id"),
    ]

    print("\n" + "=" * 80)
    print("必須データのカバー率")
    print("=" * 80)

    results = []
    for table_name, description, join_column in tables_to_check:
        cursor.execute(f"""
            SELECT COUNT(DISTINCT r.id)
            FROM races r
            LEFT JOIN {table_name} t ON r.id = t.{join_column}
            WHERE r.race_date >= '2024-01-01' AND r.race_date < '2025-01-01'
              AND t.{join_column} IS NOT NULL
        """)
        covered_races = cursor.fetchone()[0]
        coverage = (covered_races / total_races_2024 * 100) if total_races_2024 > 0 else 0

        status = "✅" if coverage >= 80 else "⚠️" if coverage >= 50 else "🔴"

        results.append({
            'table': table_name,
            'description': description,
            'covered': covered_races,
            'coverage': coverage,
            'status': status
        })

        print(f"\n{status} {description} ({table_name})")
        print(f"  カバー: {covered_races:,} / {total_races_2024:,} レース ({coverage:.1f}%)")

    # 既存の予測データを確認
    cursor.execute("""
        SELECT COUNT(DISTINCT race_id)
        FROM race_predictions
        WHERE race_id IN (
            SELECT id FROM races
            WHERE race_date >= '2024-01-01' AND race_date < '2025-01-01'
        )
    """)
    existing_predictions = cursor.fetchone()[0]

    print("\n" + "=" * 80)
    print("現在の予測データ")
    print("=" * 80)
    print(f"\n既存予測レース数: {existing_predictions:,} / {total_races_2024:,}")
    print(f"予測カバー率: {(existing_predictions / total_races_2024 * 100):.1f}%")

    # 月別のデータカバー率を確認
    print("\n" + "=" * 80)
    print("月別データカバー率")
    print("=" * 80)

    cursor.execute("""
        SELECT
            strftime('%Y-%m', race_date) as month,
            COUNT(*) as total_races,
            SUM(CASE WHEN entries_count > 0 THEN 1 ELSE 0 END) as with_entries,
            SUM(CASE WHEN details_count > 0 THEN 1 ELSE 0 END) as with_details,
            SUM(CASE WHEN results_count > 0 THEN 1 ELSE 0 END) as with_results
        FROM (
            SELECT
                r.race_date,
                (SELECT COUNT(*) FROM entries WHERE race_id = r.id) as entries_count,
                (SELECT COUNT(*) FROM race_details WHERE race_id = r.id) as details_count,
                (SELECT COUNT(*) FROM results WHERE race_id = r.id) as results_count
            FROM races r
            WHERE r.race_date >= '2024-01-01' AND r.race_date < '2025-01-01'
        )
        GROUP BY month
        ORDER BY month
    """)

    print("\n月 | レース数 | 出走表 | 直前情報 | 結果")
    print("-" * 80)

    for row in cursor.fetchall():
        month, total, entries, details, results_data = row
        entries_pct = (entries / total * 100) if total > 0 else 0
        details_pct = (details / total * 100) if total > 0 else 0
        results_pct = (results_data / total * 100) if total > 0 else 0

        print(f"{month} | {total:4} | {entries_pct:5.1f}% | {details_pct:5.1f}% | {results_pct:5.1f}%")

    # 判定
    print("\n" + "=" * 80)
    print("実行可能性判定")
    print("=" * 80)

    # 必須データ: entries（出走表）とresults（結果）
    entries_coverage = next(r['coverage'] for r in results if r['table'] == 'entries')
    results_coverage = next(r['coverage'] for r in results if r['table'] == 'results')

    if entries_coverage >= 80 and results_coverage >= 80:
        print("\n✅ **実行可能**: 必須データ（出走表、結果）が十分に揃っています")
        print("\n【推奨実行コマンド】:")
        print("python scripts/generate_predictions_2024_all.py --type advance")
        can_execute = True
    elif entries_coverage >= 50 or results_coverage >= 50:
        print("\n⚠️ **一部実行可能**: データが不足していますが、部分的に実行できます")
        print(f"\n不足データ:")
        if entries_coverage < 80:
            print(f"  - 出走表: {entries_coverage:.1f}% (推奨: 80%以上)")
        if results_coverage < 80:
            print(f"  - 結果: {results_coverage:.1f}% (推奨: 80%以上)")
        can_execute = True
    else:
        print("\n🔴 **実行不可**: 必須データが大幅に不足しています")
        print("\n先にデータ収集が必要です:")
        print("python scripts/bulk_missing_data_fetch_parallel.py --start-date 2024-01-01 --end-date 2024-12-31")
        can_execute = False

    # オプションデータの状況
    print("\n【オプションデータ】:")
    for result in results:
        if result['table'] not in ['entries', 'results']:
            print(f"  - {result['description']}: {result['coverage']:.1f}%")

    conn.close()

    print("\n" + "=" * 80)
    return can_execute

if __name__ == "__main__":
    check_2024_data()
