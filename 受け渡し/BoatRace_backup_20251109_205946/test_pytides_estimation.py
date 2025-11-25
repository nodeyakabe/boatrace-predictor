"""
PyTides潮位推定のテスト
実際にデータが生成できるか確認
"""

import sqlite3
from datetime import datetime, timedelta
from estimate_tide_pytides import TideEstimator


def test_pytides_estimation():
    """PyTides推定のテスト"""

    print("="*80)
    print("PyTides潮位推定テスト")
    print("="*80)
    print(f"テスト日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)

    # テストケース: 2015年11月（福岡・大村の数レース）
    test_start = "2015-11-01"
    test_end = "2015-11-30"
    test_venues = ['22', '24']  # 福岡、大村

    print(f"\n[テスト概要]")
    print(f"  期間: {test_start} ~ {test_end}")
    print(f"  会場: 福岡(22), 大村(24)")
    print(f"  方式: PyTides天文計算による推定")

    # データベース確認
    db_path = "data/boatrace.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 対象レース数を確認
    cursor.execute("""
        SELECT COUNT(*)
        FROM races
        WHERE race_date BETWEEN ? AND ?
          AND venue_code IN ('22', '24')
    """, (test_start, test_end))
    total_races = cursor.fetchone()[0]

    # インポート前の状態
    cursor.execute("""
        SELECT COUNT(*)
        FROM race_tide_data
        WHERE race_id IN (
            SELECT id FROM races
            WHERE race_date BETWEEN ? AND ?
              AND venue_code IN ('22', '24')
        )
        AND data_source = 'pytides_estimated'
    """, (test_start, test_end))
    before_count = cursor.fetchone()[0]

    conn.close()

    print(f"\nインポート前の状態:")
    print(f"  対象レース数: {total_races:,}")
    print(f"  推定潮位データ: {before_count:,}")

    # ステップ1: 推定値のサンプル生成テスト
    print("\n" + "="*80)
    print("[ステップ1] 推定アルゴリズムのテスト")
    print("="*80)

    estimator = TideEstimator(db_path=db_path)

    # 複数の日時でテスト
    test_dates = [
        ('22', '2015-11-08', '10:00:00', '福岡'),
        ('22', '2015-11-08', '14:30:00', '福岡'),
        ('24', '2015-11-15', '11:00:00', '大村'),
        ('24', '2015-11-15', '15:00:00', '大村'),
    ]

    print("\nサンプル推定:")
    print(f"  {'会場':6s} {'日時':20s} {'推定潮位(cm)':>12s}")
    print("  " + "-"*45)

    success_count = 0
    for venue, date, time, venue_name in test_dates:
        dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M:%S")
        tide_level = estimator.estimate_tide_level(venue, dt)

        if tide_level is not None:
            print(f"  {venue_name:6s} {date} {time:8s} {tide_level:12d}")
            success_count += 1
        else:
            print(f"  {venue_name:6s} {date} {time:8s} {'ERROR':>12s}")

    if success_count == len(test_dates):
        print("\n  [PASS] 推定アルゴリズムは正常に動作しています")
    else:
        print(f"\n  [ERROR] {len(test_dates) - success_count}/{len(test_dates)} 件で推定失敗")
        return False

    # 推定値の妥当性チェック
    print("\n推定値の妥当性チェック:")
    tide_levels = []
    for venue, date, time, _ in test_dates:
        dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M:%S")
        level = estimator.estimate_tide_level(venue, dt)
        if level:
            tide_levels.append(level)

    if tide_levels:
        min_level = min(tide_levels)
        max_level = max(tide_levels)
        avg_level = sum(tide_levels) / len(tide_levels)

        print(f"  最小値: {min_level} cm")
        print(f"  最大値: {max_level} cm")
        print(f"  平均値: {avg_level:.1f} cm")
        print(f"  変動幅: {max_level - min_level} cm")

        # 妥当性チェック（瀬戸内海の潮位は通常0-400cm程度）
        if 0 <= min_level <= 400 and 0 <= max_level <= 400:
            print("  [PASS] 潮位の値が妥当な範囲内です")
        else:
            print("  [WARN] 潮位の値が異常な可能性があります")

        if max_level - min_level >= 50:
            print("  [PASS] 潮位変動が観測されています（満干差あり）")
        else:
            print("  [WARN] 潮位変動が小さすぎる可能性があります")

    # ステップ2: 実際のレースデータへの適用テスト
    print("\n" + "="*80)
    print("[ステップ2] レースデータへの適用テスト")
    print("="*80)

    try:
        estimator.estimate_and_save(
            start_date=test_start,
            end_date=test_end,
            venues=test_venues
        )

    except Exception as e:
        print(f"\n[ERROR] 推定処理失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

    # ステップ3: 結果検証
    print("\n" + "="*80)
    print("[ステップ3] 結果検証")
    print("="*80)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # インポート後の状態
    cursor.execute("""
        SELECT COUNT(*)
        FROM race_tide_data
        WHERE race_id IN (
            SELECT id FROM races
            WHERE race_date BETWEEN ? AND ?
              AND venue_code IN ('22', '24')
        )
        AND data_source = 'pytides_estimated'
    """, (test_start, test_end))
    after_count = cursor.fetchone()[0]

    # 会場別統計
    cursor.execute("""
        SELECT
            r.venue_code,
            COUNT(*) as count,
            MIN(rtd.sea_level_cm) as min_level,
            MAX(rtd.sea_level_cm) as max_level,
            AVG(rtd.sea_level_cm) as avg_level
        FROM races r
        INNER JOIN race_tide_data rtd ON r.id = rtd.race_id
        WHERE r.race_date BETWEEN ? AND ?
          AND r.venue_code IN ('22', '24')
          AND rtd.data_source = 'pytides_estimated'
        GROUP BY r.venue_code
    """, (test_start, test_end))
    venue_stats = cursor.fetchall()

    # サンプルデータ表示
    cursor.execute("""
        SELECT
            r.venue_code,
            r.race_date,
            r.race_time,
            r.race_number,
            rtd.sea_level_cm
        FROM races r
        INNER JOIN race_tide_data rtd ON r.id = rtd.race_id
        WHERE r.race_date BETWEEN ? AND ?
          AND r.venue_code IN ('22', '24')
          AND rtd.data_source = 'pytides_estimated'
        ORDER BY r.race_date, r.venue_code, r.race_number
        LIMIT 20
    """, (test_start, test_end))
    samples = cursor.fetchall()

    conn.close()

    # 結果表示
    print(f"\nインポート結果:")
    print(f"  インポート前: {before_count:,} レコード")
    print(f"  インポート後: {after_count:,} レコード")
    print(f"  新規推定: {after_count - before_count:,} レコード")

    if venue_stats:
        print(f"\n会場別統計:")
        print(f"  {'会場':4s} {'レース数':>8s} {'最小(cm)':>9s} {'最大(cm)':>9s} {'平均(cm)':>9s} {'変動幅(cm)':>10s}")
        print("  " + "-"*60)
        for venue, count, min_l, max_l, avg_l in venue_stats:
            venue_name = "福岡" if venue == "22" else "大村"
            variation = max_l - min_l
            print(f"  {venue_name:4s} {count:8,} {min_l:9.0f} {max_l:9.0f} {avg_l:9.1f} {variation:10.0f}")

    if samples:
        print(f"\nサンプルデータ（先頭20件）:")
        print(f"  {'会場':4s} {'日付':12s} {'時刻':8s} {'R':3s} {'潮位(cm)':>10s}")
        print("  " + "-"*45)
        for venue, date, time, race_num, sea_level in samples[:15]:
            venue_name = "福岡" if venue == "22" else "大村"
            time_str = time if time else "不明"
            print(f"  {venue_name:4s} {date:12s} {time_str:8s} {race_num:3d} {sea_level:10d}")

        if len(samples) > 15:
            print(f"  ... (残り{len(samples)-15}件)")

    # データ妥当性チェック
    print("\n" + "="*80)
    print("[ステップ4] データ妥当性チェック")
    print("="*80)

    success = True

    # チェック1: データが生成できたか
    if after_count > before_count:
        print(f"[PASS] 新規データが生成できました ({after_count - before_count:,} レコード)")
    else:
        print("[ERROR] 新規データが生成できませんでした")
        success = False

    # チェック2: カバー率
    if total_races > 0:
        coverage = after_count / total_races * 100
        if coverage >= 95:
            print(f"[PASS] カバー率が十分です ({coverage:.1f}%)")
        elif coverage >= 50:
            print(f"[WARN] カバー率が低めです ({coverage:.1f}%)")
        else:
            print(f"[ERROR] カバー率が不十分です ({coverage:.1f}%)")
            success = False

    # チェック3: 潮位値の範囲
    if venue_stats:
        all_valid = True
        for venue, count, min_l, max_l, avg_l in venue_stats:
            if not (0 <= min_l <= 400 and 0 <= max_l <= 400):
                all_valid = False
                print(f"[ERROR] {venue}の潮位が異常範囲です ({min_l:.0f}-{max_l:.0f} cm)")
            elif max_l - min_l < 30:
                print(f"[WARN] {venue}の潮位変動が小さいです (変動幅: {max_l - min_l:.0f} cm)")

        if all_valid:
            print("[PASS] 全会場の潮位値が妥当な範囲内です")

    # チェック4: 時系列での潮位変動
    if samples and len(samples) >= 10:
        # 連続するレースで潮位が変化しているか
        levels = [s[4] for s in samples[:10]]
        level_changes = [abs(levels[i+1] - levels[i]) for i in range(len(levels)-1)]
        max_change = max(level_changes) if level_changes else 0

        if max_change > 10:
            print(f"[PASS] 時系列で潮位変動が観測されています (最大変化: {max_change} cm)")
        else:
            print(f"[WARN] 時系列での潮位変動が小さいです (最大変化: {max_change} cm)")

    # 総合評価
    print("\n" + "="*80)
    print("テスト結果")
    print("="*80)

    if success and after_count >= total_races * 0.95:
        print("[OK] テストに合格しました！")
        print("\nPyTides推定は正常に動作し、実用可能なデータが生成できます。")
        print("\n本格実行コマンド:")
        print("  python estimate_tide_pytides.py --start 2015-11-01 --end 2021-12-31")
        print("\n推定データの特徴:")
        print("  - 天文計算による潮位推定")
        print("  - 気圧・風の影響は考慮されない")
        print("  - 誤差: ±10-20cm程度")
        print("  - レース予想の特徴量としては十分利用可能")
    else:
        print("[ERROR] テストが失敗しました")
        if after_count < total_races * 0.95:
            print(f"  カバー率が不十分: {after_count}/{total_races} ({after_count/total_races*100:.1f}%)")

    print("="*80)

    return success


if __name__ == '__main__':
    try:
        success = test_pytides_estimation()
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nテストが中断されました")
        exit(1)
    except Exception as e:
        print(f"\n\n致命的エラー: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
