"""
事前予想と直前予想の両方保存テスト
"""

import sqlite3
from datetime import datetime

def test_dual_prediction_types():
    """事前予想と直前予想が両方保存できることを確認"""

    db_path = "data/boatrace.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("=" * 60)
    print("事前予想・直前予想の両方保存テスト")
    print("=" * 60)
    print()

    # テスト用レースを探す（今日のレース）
    cursor.execute("""
        SELECT id, venue_code, race_date, race_number
        FROM races
        WHERE race_date = ?
        LIMIT 1
    """, (datetime.now().strftime('%Y-%m-%d'),))

    race = cursor.fetchone()

    if not race:
        print("[SKIP] 今日のレースが見つかりません")
        conn.close()
        return

    race_id, venue_code, race_date, race_number = race
    print(f"[TEST] テストレース: {venue_code} {race_date} {race_number}R (race_id: {race_id})")
    print()

    # 既存の予想を確認
    cursor.execute("""
        SELECT prediction_type, COUNT(*)
        FROM race_predictions
        WHERE race_id = ?
        GROUP BY prediction_type
    """, (race_id,))

    existing = cursor.fetchall()
    print("[BEFORE] 既存の予想:")
    for ptype, count in existing:
        print(f"   - {ptype}: {count}件")

    if not existing:
        print("   (予想なし)")
    print()

    # テスト1: 事前予想を保存
    print("[TEST 1] 事前予想(advance)を保存...")
    cursor.execute("""
        DELETE FROM race_predictions WHERE race_id = ? AND prediction_type = 'advance'
    """, (race_id,))

    for pit in range(1, 7):
        cursor.execute("""
            INSERT INTO race_predictions (
                race_id, pit_number, rank_prediction, total_score,
                confidence, prediction_type, generated_at
            ) VALUES (?, ?, ?, ?, ?, 'advance', ?)
        """, (race_id, pit, pit, 70.0 + pit, 'B', datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

    conn.commit()
    print("[OK] 事前予想を6件保存しました")
    print()

    # テスト2: 直前予想を保存（事前予想が消えないことを確認）
    print("[TEST 2] 直前予想(before)を保存...")
    cursor.execute("""
        DELETE FROM race_predictions WHERE race_id = ? AND prediction_type = 'before'
    """, (race_id,))

    for pit in range(1, 7):
        cursor.execute("""
            INSERT INTO race_predictions (
                race_id, pit_number, rank_prediction, total_score,
                confidence, prediction_type, generated_at
            ) VALUES (?, ?, ?, ?, ?, 'before', ?)
        """, (race_id, pit, 7 - pit, 75.0 + pit, 'A', datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

    conn.commit()
    print("[OK] 直前予想を6件保存しました")
    print()

    # 結果確認
    print("[RESULT] 保存後の予想:")
    cursor.execute("""
        SELECT prediction_type, COUNT(*)
        FROM race_predictions
        WHERE race_id = ?
        GROUP BY prediction_type
    """, (race_id,))

    result = cursor.fetchall()
    result_dict = {ptype: count for ptype, count in result}

    for ptype, count in result:
        print(f"   - {ptype}: {count}件")
    print()

    # テスト結果判定
    success = True

    if result_dict.get('advance', 0) != 6:
        print("[FAIL] 事前予想が正しく保存されていません")
        success = False
    else:
        print("[PASS] 事前予想(advance): 6件保存 OK")

    if result_dict.get('before', 0) != 6:
        print("[FAIL] 直前予想が正しく保存されていません")
        success = False
    else:
        print("[PASS] 直前予想(before): 6件保存 OK")

    print()

    # 詳細表示
    print("[DETAIL] 予想の内容:")
    cursor.execute("""
        SELECT prediction_type, pit_number, rank_prediction, total_score, confidence
        FROM race_predictions
        WHERE race_id = ?
        ORDER BY prediction_type, pit_number
    """, (race_id,))

    current_type = None
    for ptype, pit, rank, score, conf in cursor.fetchall():
        if ptype != current_type:
            print(f"\n  {ptype}:")
            current_type = ptype
        print(f"    艇{pit}: 順位{rank}着予想, スコア{score:.1f}, 信頼度{conf}")

    print()
    print("=" * 60)

    if success:
        print("[SUCCESS] 事前予想と直前予想の両方保存テスト: 成功 OK")
    else:
        print("[FAILED] 事前予想と直前予想の両方保存テスト: 失敗 NG")

    print("=" * 60)

    conn.close()
    return success


if __name__ == "__main__":
    import sys
    success = test_dual_prediction_types()
    sys.exit(0 if success else 1)
