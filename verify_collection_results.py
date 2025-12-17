#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
データ収集完了後の検証スクリプト

収集前後の比較:
- 展示タイム（beforeinfo）のカバー率改善
- 払戻金（payouts）のカバー率改善
- 2024年10月の出走表・結果データ改善
"""
import sys
import os
import io
import sqlite3

# Windows環境でのUTF-8出力設定
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

def check_2024_data_coverage():
    """2024年データのカバー率を確認"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("=" * 80)
    print("2024年データ収集結果検証")
    print("=" * 80)

    # 全体統計
    cursor.execute("""
        SELECT COUNT(*)
        FROM races
        WHERE race_date >= '2024-01-01' AND race_date < '2025-01-01'
    """)
    total_races = cursor.fetchone()[0]

    print(f"\n総レース数: {total_races:,}")

    # 月別カバー率
    print("\n" + "=" * 80)
    print("月別データカバー率")
    print("=" * 80)
    print(f"{'月':<10} {'レース数':>8} {'出走表':>8} {'結果':>8} {'直前情報':>10} {'払戻金':>8}")
    print("-" * 80)

    cursor.execute("""
        SELECT
            SUBSTR(r.race_date, 1, 7) as month,
            COUNT(DISTINCT r.id) as race_count,
            COUNT(DISTINCT CASE WHEN e.race_id IS NOT NULL THEN r.id END) as with_entries,
            COUNT(DISTINCT CASE WHEN res.race_id IS NOT NULL THEN r.id END) as with_results,
            COUNT(DISTINCT CASE WHEN rd.race_id IS NOT NULL THEN r.id END) as with_beforeinfo,
            COUNT(DISTINCT CASE WHEN p.race_id IS NOT NULL THEN r.id END) as with_payouts
        FROM races r
        LEFT JOIN (SELECT DISTINCT race_id FROM entries) e ON r.id = e.race_id
        LEFT JOIN (SELECT DISTINCT race_id FROM results) res ON r.id = res.race_id
        LEFT JOIN (SELECT DISTINCT race_id FROM race_details WHERE exhibition_time IS NOT NULL) rd ON r.id = rd.race_id
        LEFT JOIN (SELECT DISTINCT race_id FROM payouts) p ON r.id = p.race_id
        WHERE r.race_date >= '2024-01-01' AND r.race_date < '2025-01-01'
        GROUP BY month
        ORDER BY month
    """)

    monthly_stats = []
    for row in cursor.fetchall():
        month, races, entries, results, beforeinfo, payouts = row
        monthly_stats.append({
            'month': month,
            'races': races,
            'entries_pct': (entries / races * 100) if races > 0 else 0,
            'results_pct': (results / races * 100) if races > 0 else 0,
            'beforeinfo_pct': (beforeinfo / races * 100) if races > 0 else 0,
            'payouts_pct': (payouts / races * 100) if races > 0 else 0
        })

        print(f"{month:<10} {races:>8} {entries/races*100:>7.1f}% {results/races*100:>7.1f}% "
              f"{beforeinfo/races*100:>9.1f}% {payouts/races*100:>7.1f}%")

    # 全体カバー率
    cursor.execute("""
        SELECT
            COUNT(DISTINCT r.id) as total,
            COUNT(DISTINCT CASE WHEN e.race_id IS NOT NULL THEN r.id END) as with_entries,
            COUNT(DISTINCT CASE WHEN res.race_id IS NOT NULL THEN r.id END) as with_results,
            COUNT(DISTINCT CASE WHEN rd.race_id IS NOT NULL THEN r.id END) as with_beforeinfo,
            COUNT(DISTINCT CASE WHEN p.race_id IS NOT NULL THEN r.id END) as with_payouts
        FROM races r
        LEFT JOIN (SELECT DISTINCT race_id FROM entries) e ON r.id = e.race_id
        LEFT JOIN (SELECT DISTINCT race_id FROM results) res ON r.id = res.race_id
        LEFT JOIN (SELECT DISTINCT race_id FROM race_details WHERE exhibition_time IS NOT NULL) rd ON r.id = rd.race_id
        LEFT JOIN (SELECT DISTINCT race_id FROM payouts) p ON r.id = p.race_id
        WHERE r.race_date >= '2024-01-01' AND r.race_date < '2025-01-01'
    """)

    total, entries, results, beforeinfo, payouts = cursor.fetchone()

    print("-" * 80)
    print(f"{'全体':<10} {total:>8} {entries/total*100:>7.1f}% {results/total*100:>7.1f}% "
          f"{beforeinfo/total*100:>9.1f}% {payouts/total*100:>7.1f}%")

    # 改善が必要な月をハイライト
    print("\n" + "=" * 80)
    print("要改善箇所")
    print("=" * 80)

    issues = []
    for stat in monthly_stats:
        if stat['entries_pct'] < 95:
            issues.append(f"  {stat['month']}: 出走表 {stat['entries_pct']:.1f}% (目標: 95%)")
        if stat['results_pct'] < 95:
            issues.append(f"  {stat['month']}: 結果 {stat['results_pct']:.1f}% (目標: 95%)")
        if stat['beforeinfo_pct'] < 90:
            issues.append(f"  {stat['month']}: 直前情報 {stat['beforeinfo_pct']:.1f}% (目標: 90%)")
        if stat['payouts_pct'] < 95:
            issues.append(f"  {stat['month']}: 払戻金 {stat['payouts_pct']:.1f}% (目標: 95%)")

    if issues:
        for issue in issues:
            print(issue)
    else:
        print("  ✅ 全ての月で目標カバー率を達成")

    # 予測データの生成状況
    print("\n" + "=" * 80)
    print("予測データ生成状況")
    print("=" * 80)

    cursor.execute("""
        SELECT
            prediction_type,
            COUNT(DISTINCT race_id) as race_count,
            COUNT(*) as prediction_count
        FROM race_predictions
        WHERE race_id IN (
            SELECT id FROM races
            WHERE race_date >= '2024-01-01' AND race_date < '2025-01-01'
        )
        GROUP BY prediction_type
    """)

    pred_stats = cursor.fetchall()
    if pred_stats:
        for pred_type, race_count, pred_count in pred_stats:
            coverage = race_count / total * 100 if total > 0 else 0
            print(f"  {pred_type}: {race_count:,}レース ({coverage:.1f}%), {pred_count:,}予測")
    else:
        print("  予測データなし")

    # バックテスト準備状況
    print("\n" + "=" * 80)
    print("バックテスト実行可否判定")
    print("=" * 80)

    entries_ok = (entries / total * 100) >= 95
    results_ok = (results / total * 100) >= 95
    payouts_ok = (payouts / total * 100) >= 95

    cursor.execute("""
        SELECT COUNT(DISTINCT race_id)
        FROM race_predictions
        WHERE prediction_type = 'advance'
        AND race_id IN (
            SELECT id FROM races
            WHERE race_date >= '2024-01-01' AND race_date < '2025-01-01'
        )
    """)
    advance_predictions = cursor.fetchone()[0]
    predictions_ok = (advance_predictions / total * 100) >= 95

    print(f"  出走表データ: {'✅ OK' if entries_ok else '🔴 不足'} ({entries/total*100:.1f}%)")
    print(f"  結果データ: {'✅ OK' if results_ok else '🔴 不足'} ({results/total*100:.1f}%)")
    print(f"  払戻金データ: {'✅ OK' if payouts_ok else '🔴 不足'} ({payouts/total*100:.1f}%)")
    print(f"  advance予測: {'✅ OK' if predictions_ok else '🔴 不足'} ({advance_predictions/total*100:.1f}%)")

    print("\n" + "=" * 80)

    if entries_ok and results_ok and payouts_ok and predictions_ok:
        print("✅ バックテスト実行可能")
        print("\n次のステップ:")
        print("  python scripts/run_2024_backtest.py")
    else:
        print("⚠️ バックテスト実行には追加データ収集が必要")
        if not entries_ok or not results_ok:
            print("\n  追加収集が必要:")
            print("  python scripts/collect_2024_missing_data.py")
        if not predictions_ok:
            print("\n  予測データ生成を完了させてください:")
            print("  python scripts/generate_predictions_2024_all.py --type advance")

    print("=" * 80)

    conn.close()

    return {
        'entries_ok': entries_ok,
        'results_ok': results_ok,
        'payouts_ok': payouts_ok,
        'predictions_ok': predictions_ok
    }

def check_prediction_quality():
    """予測データの品質チェック"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("\n" + "=" * 80)
    print("予測データ品質チェック")
    print("=" * 80)

    # 予測タイプ別の統計
    cursor.execute("""
        SELECT
            rp.prediction_type,
            COUNT(DISTINCT rp.race_id) as race_count,
            COUNT(*) as prediction_count
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE r.race_date >= '2024-01-01' AND r.race_date < '2025-01-01'
        GROUP BY rp.prediction_type
    """)

    for row in cursor.fetchall():
        pred_type, race_count, pred_count = row
        print(f"\n{pred_type}予測:")
        print(f"  レース数: {race_count:,}")
        print(f"  予測件数: {pred_count:,}")

        # 信頼度分布を取得
        cursor.execute("""
            SELECT confidence, COUNT(*) as count
            FROM race_predictions rp
            JOIN races r ON rp.race_id = r.id
            WHERE r.race_date >= '2024-01-01' AND r.race_date < '2025-01-01'
            AND rp.prediction_type = ?
            GROUP BY confidence
            ORDER BY confidence
        """, (pred_type,))

        conf_dist = cursor.fetchall()
        if conf_dist:
            print(f"  信頼度分布:")
            for conf, count in conf_dist:
                print(f"    {conf}: {count:,}件 ({count/pred_count*100:.1f}%)")

    conn.close()

if __name__ == "__main__":
    try:
        results = check_2024_data_coverage()
        check_prediction_quality()

        # 全てOKならバックテスト準備完了
        if all(results.values()):
            sys.exit(0)
        else:
            sys.exit(1)

    except Exception as e:
        print(f"\n🔴 エラー: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
