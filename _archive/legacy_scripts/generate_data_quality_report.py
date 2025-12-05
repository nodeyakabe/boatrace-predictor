"""
データ品質検証レポート作成スクリプト

取得済みデータの完全性、品質、カバレッジを詳細に分析
"""

import sqlite3
from datetime import datetime, timedelta

def main():
    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    print("=" * 100)
    print("データ品質検証レポート")
    print(f"作成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)

    # 1. 基本統計
    print("\n【1. 基本統計】")
    cursor.execute('SELECT COUNT(*) FROM races')
    total_races = cursor.fetchone()[0]
    print(f"  総レース数: {total_races:,}")

    cursor.execute('SELECT COUNT(*) FROM entries')
    print(f"  出走表エントリ数: {cursor.fetchone()[0]:,}")

    cursor.execute('SELECT COUNT(*) FROM results')
    total_results = cursor.fetchone()[0]
    print(f"  レース結果データ数: {total_results:,}")

    cursor.execute('SELECT COUNT(*) FROM payouts')
    total_payouts = cursor.fetchone()[0]
    print(f"  払戻金データ数: {total_payouts:,}")

    cursor.execute('SELECT COUNT(*) FROM weather')
    print(f"  天気データ数: {cursor.fetchone()[0]:,}")

    # 2. データカバレッジ
    print("\n【2. データカバレッジ】")

    # レース結果のカバレッジ
    cursor.execute("""
        SELECT COUNT(DISTINCT race_id) FROM results
    """)
    races_with_results = cursor.fetchone()[0]
    result_coverage = (races_with_results / total_races * 100) if total_races > 0 else 0
    print(f"  レース結果: {races_with_results:,}/{total_races:,} ({result_coverage:.1f}%)")

    # 払戻金のカバレッジ
    cursor.execute("""
        SELECT COUNT(DISTINCT race_id) FROM payouts
    """)
    races_with_payouts = cursor.fetchone()[0]
    payout_coverage = (races_with_payouts / races_with_results * 100) if races_with_results > 0 else 0
    print(f"  払戻金データ: {races_with_payouts:,}/{races_with_results:,} ({payout_coverage:.1f}%)")

    # 展示タイムのカバレッジ
    cursor.execute("""
        SELECT COUNT(DISTINCT race_id) FROM race_details WHERE exhibition_time IS NOT NULL
    """)
    races_with_exhibition = cursor.fetchone()[0]
    exhibition_coverage = (races_with_exhibition / total_races * 100) if total_races > 0 else 0
    print(f"  展示タイム: {races_with_exhibition:,}/{total_races:,} ({exhibition_coverage:.1f}%)")

    # 進入コースのカバレッジ
    cursor.execute("""
        SELECT COUNT(DISTINCT race_id) FROM race_details WHERE actual_course IS NOT NULL
    """)
    races_with_course = cursor.fetchone()[0]
    course_coverage = (races_with_course / total_races * 100) if total_races > 0 else 0
    print(f"  進入コース: {races_with_course:,}/{total_races:,} ({course_coverage:.1f}%)")

    # STタイムのカバレッジ
    cursor.execute("""
        SELECT COUNT(DISTINCT race_id) FROM race_details WHERE st_time IS NOT NULL
    """)
    races_with_st = cursor.fetchone()[0]
    st_coverage = (races_with_st / races_with_course * 100) if races_with_course > 0 else 0
    print(f"  STタイム: {races_with_st:,}/{races_with_course:,} ({st_coverage:.1f}%)")

    # 3. 払戻金データの内訳
    print("\n【3. 払戻金データの内訳】")
    cursor.execute("""
        SELECT bet_type, COUNT(*) as cnt
        FROM payouts
        GROUP BY bet_type
        ORDER BY cnt DESC
    """)
    bet_type_map = {
        'trifecta': '3連単',
        'trio': '3連複',
        'exacta': '2連単',
        'quinella': '2連複',
        'quinella_place': '拡連複',
        'win': '単勝',
        'place': '複勝'
    }
    for bet_type, count in cursor.fetchall():
        jp_name = bet_type_map.get(bet_type, bet_type)
        print(f"  {jp_name}: {count:,}件")

    # 4. 決まり手の分布
    print("\n【4. 決まり手の分布】")
    cursor.execute("""
        SELECT kimarite, COUNT(*) as cnt
        FROM results
        WHERE kimarite IS NOT NULL AND kimarite != ''
        GROUP BY kimarite
        ORDER BY cnt DESC
    """)
    kimarite_total = 0
    for kimarite, count in cursor.fetchall():
        print(f"  {kimarite}: {count}件")
        kimarite_total += count
    print(f"  合計: {kimarite_total}件")

    # 5. 日付別データ充実度
    print("\n【5. 最近の日付別データ充実度（直近10日）】")
    cursor.execute("""
        SELECT
            r.race_date,
            COUNT(DISTINCT r.id) as total,
            COUNT(DISTINCT CASE WHEN res.id IS NOT NULL THEN r.id END) as with_results,
            COUNT(DISTINCT CASE WHEN p.id IS NOT NULL THEN r.id END) as with_payouts,
            COUNT(DISTINCT CASE WHEN rd.exhibition_time IS NOT NULL THEN r.id END) as with_exhibition,
            COUNT(DISTINCT CASE WHEN rd.actual_course IS NOT NULL THEN r.id END) as with_course
        FROM races r
        LEFT JOIN results res ON r.id = res.race_id
        LEFT JOIN payouts p ON r.id = p.race_id
        LEFT JOIN race_details rd ON r.id = rd.race_id
        GROUP BY r.race_date
        ORDER BY r.race_date DESC
        LIMIT 10
    """)

    print(f"  {'日付':<12} {'総数':>6} {'結果':>6} {'払戻':>6} {'展示':>6} {'進入':>6}")
    print("  " + "-" * 48)
    for row in cursor.fetchall():
        date, total, results, payouts, exhibition, course = row
        print(f"  {date:<12} {total:>6} {results:>6} {payouts:>6} {exhibition:>6} {course:>6}")

    # 6. 競艇場別データ充実度
    print("\n【6. 競艇場別データ充実度（上位15場）】")
    cursor.execute("""
        SELECT
            v.name,
            COUNT(DISTINCT r.id) as total,
            COUNT(DISTINCT CASE WHEN res.id IS NOT NULL THEN r.id END) as with_results,
            COUNT(DISTINCT CASE WHEN p.id IS NOT NULL THEN r.id END) as with_payouts
        FROM venues v
        LEFT JOIN races r ON v.code = r.venue_code
        LEFT JOIN results res ON r.id = res.race_id
        LEFT JOIN payouts p ON r.id = p.race_id
        GROUP BY v.code, v.name
        HAVING total > 0
        ORDER BY total DESC
        LIMIT 15
    """)

    print(f"  {'競艇場':<10} {'総数':>6} {'結果':>6} {'払戻':>6} {'カバレッジ':>10}")
    print("  " + "-" * 48)
    for row in cursor.fetchall():
        venue, total, results, payouts = row
        coverage = (payouts / total * 100) if total > 0 else 0
        print(f"  {venue:<10} {total:>6} {results:>6} {payouts:>6} {coverage:>9.1f}%")

    # 7. データ品質スコア
    print("\n【7. データ品質スコア】")

    scores = {
        'レース結果カバレッジ': result_coverage,
        '払戻金カバレッジ': payout_coverage,
        '展示タイムカバレッジ': exhibition_coverage,
        '進入コースカバレッジ': course_coverage,
        'STタイムカバレッジ': st_coverage
    }

    total_score = sum(scores.values()) / len(scores)

    for metric, score in scores.items():
        status = "優" if score >= 80 else "良" if score >= 60 else "可" if score >= 40 else "要改善"
        print(f"  {metric:<25} {score:>6.1f}% [{status}]")

    print(f"\n  総合スコア: {total_score:.1f}%")

    # 8. 不足データの推定
    print("\n【8. 不足データの推定】")

    # 払戻金が不足しているレース
    cursor.execute("""
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        INNER JOIN results res ON r.id = res.race_id
        WHERE NOT EXISTS (SELECT 1 FROM payouts p WHERE p.race_id = r.id)
    """)
    missing_payouts = cursor.fetchone()[0]
    print(f"  払戻金不足: {missing_payouts:,}レース")

    # 決まり手が不足しているレース
    cursor.execute("""
        SELECT COUNT(*)
        FROM results
        WHERE rank = 1 AND (kimarite IS NULL OR kimarite = '')
    """)
    missing_kimarite = cursor.fetchone()[0]
    print(f"  決まり手不足: {missing_kimarite:,}レース")

    # STタイムが不足しているレース
    cursor.execute("""
        SELECT COUNT(DISTINCT race_id)
        FROM race_details
        WHERE actual_course IS NOT NULL AND (st_time IS NULL OR st_time = 0)
    """)
    missing_st = cursor.fetchone()[0]
    print(f"  STタイム不足: {missing_st:,}レース")

    # 9. 推奨アクション
    print("\n【9. 推奨アクション】")

    if missing_payouts > 0:
        print(f"  - 払戻金データの追加取得が必要 ({missing_payouts}レース)")

    if missing_kimarite > 0:
        print(f"  - 決まり手データの追加取得が必要 ({missing_kimarite}レース)")

    if missing_st > 0:
        print(f"  - STタイムデータの追加取得が必要 ({missing_st}レース)")

    if total_score >= 80:
        print("  - データ品質は良好です")
    elif total_score >= 60:
        print("  - データ品質は許容範囲内ですが、改善の余地があります")
    else:
        print("  - データ品質の改善が必要です")

    # フェーズ3（予想精度検証）への準備状況
    print("\n【10. フェーズ3（予想精度検証）への準備状況】")

    # バックテストに必要な最低限のデータがあるか確認
    cursor.execute("""
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        INNER JOIN results res ON r.id = res.race_id
        INNER JOIN payouts p ON r.id = p.race_id
        INNER JOIN race_details rd ON r.id = rd.race_id
        WHERE rd.exhibition_time IS NOT NULL
        AND rd.actual_course IS NOT NULL
    """)
    backtestable_races = cursor.fetchone()[0]

    print(f"  バックテスト可能なレース数: {backtestable_races:,}")

    if backtestable_races >= 100:
        print("  準備状況: 準備完了 - バックテストを開始できます")
    elif backtestable_races >= 50:
        print("  準備状況: ほぼ準備完了 - 追加データ取得後にバックテスト可能")
    else:
        print("  準備状況: データ不足 - さらなるデータ収集が必要")

    conn.close()

    print("\n" + "=" * 100)
    print("レポート作成完了")
    print("=" * 100)

if __name__ == "__main__":
    main()
