"""
DB最適化の効果測定テスト

最適化前後の処理時間を比較
"""

import time
import sqlite3
from src.analysis.race_predictor import RacePredictor

def main():
    print("=" * 80)
    print("DB最適化効果測定テスト")
    print("=" * 80)
    print()

    # テスト用レースIDを取得（最新10レース）
    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT r.id
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        JOIN results res ON r.id = res.race_id
        WHERE rd.exhibition_course IS NOT NULL
        AND res.rank IS NOT NULL
        AND res.is_invalid = 0
        ORDER BY r.race_date DESC, r.id DESC
        LIMIT 10
    """)
    test_race_ids = [row[0] for row in cursor.fetchall()]
    conn.close()

    print(f"テスト対象: {len(test_race_ids)}レース")
    print()

    # 1レースあたりの平均処理時間を測定
    predictor = RacePredictor(db_path='data/boatrace.db')

    times = []
    for i, race_id in enumerate(test_race_ids, 1):
        print(f"レース {i}/{len(test_race_ids)} (race_id: {race_id})", end='')

        start = time.time()
        try:
            predictions = predictor.predict_race(race_id)
            elapsed = time.time() - start
            times.append(elapsed)
            print(f" - {elapsed:.2f}秒")
        except Exception as e:
            print(f" - エラー: {e}")

    print()
    print("=" * 80)
    print("測定結果")
    print("=" * 80)

    if times:
        avg_time = sum(times) / len(times)
        min_time = min(times)
        max_time = max(times)

        print(f"成功レース数: {len(times)}/{len(test_race_ids)}")
        print(f"平均処理時間: {avg_time:.2f}秒/レース")
        print(f"最速: {min_time:.2f}秒")
        print(f"最遅: {max_time:.2f}秒")
        print()

        # 100レースの推定時間
        est_100 = avg_time * 100 / 60
        print(f"100レース予測の推定時間: {est_100:.1f}分")
        print()

        # 最適化前との比較
        print("【最適化前との比較】")
        print(f"最適化前: 約32秒/レース (100レース = 53分)")
        print(f"最適化後: {avg_time:.2f}秒/レース (100レース = {est_100:.1f}分)")

        if avg_time < 32:
            improvement = ((32 - avg_time) / 32) * 100
            time_saved = 53 - est_100
            print(f"改善率: {improvement:.1f}%削減")
            print(f"時間短縮: {time_saved:.1f}分短縮")
            print()

            if avg_time <= 5:
                print("✅ 目標達成！（1レース3-5秒以内）")
            elif avg_time <= 10:
                print("⚠️ 目標に近づいています（1レース10秒以内）")
            else:
                print("❌ まだ目標未達（目標: 1レース3-5秒）")
        else:
            print("⚠️ 最適化効果が見られません")
    else:
        print("エラー: すべてのレースで予測に失敗しました")

    print()
    print("=" * 80)

if __name__ == "__main__":
    main()
