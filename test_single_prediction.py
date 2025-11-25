"""
1レースだけ予測をテストして修正内容を確認
"""

import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from config.settings import DATABASE_PATH
from src.analysis.race_predictor import RacePredictor

def test_single():
    print("=" * 60)
    print("1レース予測テスト")
    print("=" * 60)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 1レースだけ取得
    target_date = '2025-11-19'
    cursor.execute("""
        SELECT id, venue_code, race_number
        FROM races
        WHERE race_date = ?
        ORDER BY venue_code, race_number
        LIMIT 1
    """, (target_date,))

    race = cursor.fetchone()
    if not race:
        print("レースが見つかりません")
        return

    race_id, venue_code, race_number = race
    print(f"\nテスト対象: 会場{venue_code} {race_number}R (race_id={race_id})")

    conn.close()

    # 予測実行
    print("\n予測実行中...")
    predictor = RacePredictor()

    try:
        predictions = predictor.predict_race(race_id)

        if predictions:
            print(f"\n✓ 予測成功 ({len(predictions)}艇)")
            print("\n結果:")
            print("  順位 | 枠 | スコア | 信頼度")
            print("  " + "-" * 40)
            for pred in predictions:
                print(f"  {pred['rank_prediction']:2d}位 | {pred['pit_number']}号艇 | {pred['total_score']:5.1f} | {pred['confidence']}")

            # スコアの範囲チェック
            scores = [p['total_score'] for p in predictions]
            print(f"\nスコア範囲: {min(scores):.1f} - {max(scores):.1f}")
            if all(0 <= s <= 100 for s in scores):
                print("✓ スコアは0-100の範囲内です")
            else:
                print("✗ スコアが範囲外のものがあります！")

        else:
            print("✗ 予測失敗")

    except Exception as e:
        print(f"✗ エラー: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("完了")
    print("=" * 60)


if __name__ == "__main__":
    test_single()
