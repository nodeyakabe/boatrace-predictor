"""
不足している潮位データをPyTides推定で補完

海水場のレースで潮位データが欠損しているものを
天文計算により推定して補完する
"""

import sqlite3
from datetime import datetime
from estimate_tide_pytides import TideEstimator


def fill_missing_tide_data(db_path="data/boatrace.db"):
    """
    潮位データが欠損しているレースを補完

    Args:
        db_path: データベースパス
    """
    print("="*80)
    print("潮位データ補完（PyTides推定）")
    print("="*80)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 不足データを確認
    cursor.execute("""
        SELECT COUNT(*)
        FROM races r
        LEFT JOIN race_tide_data rtd ON r.id = rtd.race_id
        WHERE r.venue_code IN ('15', '16', '17', '18', '20', '22', '24')
          AND rtd.race_id IS NULL
    """)
    missing_count = cursor.fetchone()[0]

    print(f"不足レース数: {missing_count:,}")

    if missing_count == 0:
        print("\n不足データはありません。処理を終了します。")
        conn.close()
        return

    # 会場別の不足状況
    cursor.execute("""
        SELECT
            r.venue_code,
            COUNT(*) as missing_count
        FROM races r
        LEFT JOIN race_tide_data rtd ON r.id = rtd.race_id
        WHERE r.venue_code IN ('15', '16', '17', '18', '20', '22', '24')
          AND rtd.race_id IS NULL
        GROUP BY r.venue_code
        ORDER BY missing_count DESC
    """)

    venue_stats = cursor.fetchall()
    venue_names = {
        '15': '丸亀', '16': '児島', '17': '宮島',
        '18': '徳山', '20': '若松', '22': '福岡', '24': '大村'
    }

    print("\n会場別不足数:")
    print("  会場  不足レース数")
    print("  " + "-"*25)
    for venue, count in venue_stats:
        name = venue_names[venue]
        print(f"  {name:4s}  {count:12,}")

    print("\n" + "="*80)
    print("補完処理開始")
    print("="*80)

    # 不足しているレースを取得
    cursor.execute("""
        SELECT
            r.id,
            r.venue_code,
            r.race_date,
            r.race_time
        FROM races r
        LEFT JOIN race_tide_data rtd ON r.id = rtd.race_id
        WHERE r.venue_code IN ('15', '16', '17', '18', '20', '22', '24')
          AND rtd.race_id IS NULL
        ORDER BY r.race_date, r.venue_code, r.race_number
    """)

    missing_races = cursor.fetchall()

    # PyTides推定で補完
    estimator = TideEstimator(db_path=db_path)

    filled = 0
    errors = 0

    print(f"\n補完中... (対象: {len(missing_races):,} レース)")

    for i, (race_id, venue_code, race_date, race_time) in enumerate(missing_races):
        try:
            # レース日時を生成
            if race_time:
                if len(race_time) == 5:  # HH:MM
                    dt = datetime.strptime(f"{race_date} {race_time}:00", "%Y-%m-%d %H:%M:%S")
                else:  # HH:MM:SS
                    dt = datetime.strptime(f"{race_date} {race_time}", "%Y-%m-%d %H:%M:%S")
            else:
                # 時刻がない場合は正午と仮定
                dt = datetime.strptime(f"{race_date} 12:00:00", "%Y-%m-%d %H:%M:%S")

            # 潮位を推定
            tide_level = estimator.estimate_tide_level(venue_code, dt)

            if tide_level is not None:
                # データベースに保存
                cursor.execute("""
                    INSERT INTO race_tide_data (
                        race_id,
                        sea_level_cm,
                        data_source,
                        created_at
                    ) VALUES (?, ?, ?, datetime('now'))
                """, (race_id, tide_level, 'pytides_filled'))

                filled += 1

                # 進捗表示（1000レースごと）
                if filled % 1000 == 0:
                    conn.commit()
                    print(f"  進捗: {filled:,}/{len(missing_races):,} ({filled/len(missing_races)*100:.1f}%)")
            else:
                errors += 1

        except Exception as e:
            print(f"  [ERROR] レースID {race_id}: {e}")
            errors += 1

    conn.commit()
    conn.close()

    # 結果表示
    print("\n" + "="*80)
    print("補完完了")
    print("="*80)
    print(f"対象レース数: {len(missing_races):,}")
    print(f"  補完成功: {filled:,} ({filled/len(missing_races)*100:.1f}%)")
    print(f"  エラー: {errors:,}")
    print("="*80)

    print("\n注意事項:")
    print("  - 補完データは天文計算による推定値です")
    print("  - data_source = 'pytides_filled' で識別できます")
    print("  - 気圧・風の影響は考慮されていません")
    print("  - 誤差: ±10-20cm程度")

    return filled, errors


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(
        description='不足している潮位データをPyTides推定で補完'
    )
    parser.add_argument('--db', default='data/boatrace.db', help='データベースパス')

    args = parser.parse_args()

    filled, errors = fill_missing_tide_data(db_path=args.db)

    if filled > 0:
        print("\n次のステップ:")
        print("  python analyze_tide_data.py  # データ状況確認")
        print("  python export_tide_for_production.py  # 本番DB用エクスポート")


if __name__ == '__main__':
    main()
