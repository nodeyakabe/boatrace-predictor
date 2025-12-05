# -*- coding: utf-8 -*-
"""
新スコアリングシステムの検証テスト
複数レースで予測結果をチェックし、コース×ランクの相互作用が正しく機能しているか確認
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import sqlite3
from datetime import datetime

# パス設定
sys.path.insert(0, 'c:\\Users\\seizo\\Desktop\\BoatRace')

from src.analysis.race_predictor import RacePredictor
from config.settings import DATABASE_PATH

def validate_scoring():
    """スコアリングの妥当性を検証"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 本日のレースを取得
    today = datetime.now().strftime('%Y-%m-%d')

    cursor.execute("""
        SELECT DISTINCT r.race_date, r.venue_code, r.race_number, r.race_time
        FROM races r
        JOIN entries e ON r.id = e.race_id
        WHERE r.race_date = ?
        ORDER BY r.venue_code, r.race_number
        LIMIT 15
    """, (today,))

    races = cursor.fetchall()

    if not races:
        print("本日のレースデータがありません")
        conn.close()
        return

    predictor = RacePredictor()

    print("=" * 80)
    print("新スコアリングシステム検証テスト")
    print("=" * 80)

    # 統計
    course1_first_count = 0
    total_races = 0
    rank_distribution = {'A1': 0, 'A2': 0, 'B1': 0, 'B2': 0}

    for race_date, venue_code, race_number, race_time in races:
        print(f"\n【{venue_code} {race_number}R】({race_time})")

        # 出走表取得
        cursor.execute("""
            SELECT
                e.pit_number,
                e.racer_name,
                e.racer_rank,
                e.win_rate,
                e.motor_number,
                e.motor_second_rate
            FROM entries e
            JOIN races r ON e.race_id = r.id
            WHERE r.race_date = ? AND r.venue_code = ? AND r.race_number = ?
            ORDER BY e.pit_number
        """, (race_date, venue_code, race_number))

        entries = cursor.fetchall()

        if not entries:
            print("  出走表なし")
            continue

        # 出走表表示
        print("  出走表:")
        for pit, name, rank, win_rate, motor_number, motor_rate in entries:
            rank_str = rank if rank else '不明'
            win_str = f"{win_rate:.2f}" if win_rate else "-"
            motor_str = f"{motor_rate:.1f}%" if motor_rate else "-"
            print(f"    {pit}号艇: {name} ({rank_str}) 勝率{win_str} M{motor_number}({motor_str})")
            if rank in rank_distribution:
                rank_distribution[rank] += 1

        # 予測
        try:
            predictions = predictor.predict_race_by_key(race_date, venue_code, race_number)

            if predictions:
                print("  予測結果:")
                for i, pred in enumerate(predictions[:3], 1):
                    pit = pred['pit_number']
                    name = pred.get('racer_name', '不明')
                    course_score = pred.get('course_score', 0)
                    racer_score = pred.get('racer_score', 0)
                    motor_score = pred.get('motor_score', 0)
                    total = pred['total_score']

                    # スコア内訳
                    print(f"    {i}位: {pit}号艇 {name}")
                    print(f"         コース:{course_score:.1f} 選手:{racer_score:.1f} モーター:{motor_score:.1f} → 合計:{total:.1f}")

                # 1号艇が1位かどうか
                total_races += 1
                if predictions[0]['pit_number'] == 1:
                    course1_first_count += 1

        except Exception as e:
            print(f"  予測エラー: {e}")

    conn.close()

    # 統計表示
    print("\n" + "=" * 80)
    print("統計サマリー")
    print("=" * 80)

    if total_races > 0:
        course1_rate = course1_first_count / total_races * 100
        print(f"検証レース数: {total_races}")
        print(f"1号艇1位予測: {course1_first_count}回 ({course1_rate:.1f}%)")

        # 期待値との比較（実データでは1号艇勝率は約52%）
        print(f"\n※参考: 競艇全体の1号艇勝率は約52%")

        if course1_rate > 80:
            print("⚠️ 1号艇の予測が高すぎる可能性あり")
        elif course1_rate < 30:
            print("⚠️ 1号艇の予測が低すぎる可能性あり")
        else:
            print("✅ 1号艇予測率は妥当な範囲")

    print(f"\n出走選手ランク分布: {rank_distribution}")


if __name__ == "__main__":
    validate_scoring()
