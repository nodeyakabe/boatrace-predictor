# -*- coding: utf-8 -*-
"""簡易スコアリングテスト - コース×ランクスコアのみテスト"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, 'c:\\Users\\seizo\\Desktop\\BoatRace')

import sqlite3
from datetime import datetime
from config.settings import DATABASE_PATH

# 直接スコア計算
COURSE_RANK_WIN_RATES = {
    (1, 'A1'): 0.715, (1, 'A2'): 0.611, (1, 'B1'): 0.424, (1, 'B2'): 0.303,
    (2, 'A1'): 0.195, (2, 'A2'): 0.167, (2, 'B1'): 0.096, (2, 'B2'): 0.081,
    (3, 'A1'): 0.182, (3, 'A2'): 0.162, (3, 'B1'): 0.091, (3, 'B2'): 0.066,
    (4, 'A1'): 0.138, (4, 'A2'): 0.119, (4, 'B1'): 0.076, (4, 'B2'): 0.039,
    (5, 'A1'): 0.100, (5, 'A2'): 0.073, (5, 'B1'): 0.044, (5, 'B2'): 0.020,
    (6, 'A1'): 0.066, (6, 'A2'): 0.034, (6, 'B1'): 0.017, (6, 'B2'): 0.006,
}

def get_course_rank_score(course: int, rank: str) -> float:
    """コース×ランクから期待勝率ベーススコアを計算"""
    win_rate = COURSE_RANK_WIN_RATES.get((course, rank), 0.05)
    # 55点満点、最大勝率71.5%で正規化
    return (win_rate / 0.715) * 55

def simple_test():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')

    # 30レース取得
    cursor.execute("""
        SELECT r.id, r.venue_code, r.race_number
        FROM races r
        WHERE r.race_date = ?
        ORDER BY r.venue_code, r.race_number
        LIMIT 30
    """, (today,))

    races = cursor.fetchall()

    results = []
    course1_first = 0

    for race_id, venue_code, race_number in races:
        # エントリー取得
        cursor.execute("""
            SELECT pit_number, racer_name, racer_rank, win_rate
            FROM entries
            WHERE race_id = ?
            ORDER BY pit_number
        """, (race_id,))

        entries = cursor.fetchall()
        if len(entries) < 6:
            continue

        # 各艇のスコア計算（コース×ランクのみ）
        scores = []
        for pit, name, rank, win_rate in entries:
            if not rank:
                rank = 'B2'
            cs = get_course_rank_score(pit, rank)
            # 勝率ボーナス（最大10点）
            win_bonus = min((win_rate or 0) * 1.5, 10) if win_rate else 0
            total = cs + win_bonus
            scores.append((pit, name[:4], rank, cs, win_bonus, total))

        # スコア順でソート
        scores.sort(key=lambda x: x[5], reverse=True)
        winner_pit = scores[0][0]

        # 結果記録
        if winner_pit == 1:
            course1_first += 1

        # 詳細表示（最初の5レースのみ）
        if len(results) < 5:
            print(f"\n【{venue_code} {race_number}R】")
            for i, (pit, name, rank, cs, wb, total) in enumerate(scores[:3], 1):
                print(f"  {i}位: {pit}艇 {name} ({rank}) C:{cs:.1f} W:{wb:.1f} = {total:.1f}")

        results.append({
            'venue': venue_code,
            'race': race_number,
            'winner': winner_pit,
            '1号艇rank': entries[0][2]
        })

    conn.close()

    # 統計
    total = len(results)
    if total > 0:
        rate = course1_first / total * 100
        print(f"\n{'='*50}")
        print(f"統計: {total}レース中、1号艇1位予測 = {course1_first}回 ({rate:.1f}%)")
        print(f"※実際の1号艇勝率は約52%なので、{40}-{65}%程度が妥当")

        # 1号艇のランク別内訳
        a1_races = [r for r in results if r['1号艇rank'] == 'A1']
        b1_races = [r for r in results if r['1号艇rank'] == 'B1']
        b2_races = [r for r in results if r['1号艇rank'] == 'B2']

        a1_win = sum(1 for r in a1_races if r['winner'] == 1)
        b1_win = sum(1 for r in b1_races if r['winner'] == 1)
        b2_win = sum(1 for r in b2_races if r['winner'] == 1)

        print(f"\n1号艇ランク別予測:")
        if a1_races:
            print(f"  A1: {a1_win}/{len(a1_races)} ({a1_win/len(a1_races)*100:.0f}%) 期待72%")
        if b1_races:
            print(f"  B1: {b1_win}/{len(b1_races)} ({b1_win/len(b1_races)*100:.0f}%) 期待42%")
        if b2_races:
            print(f"  B2: {b2_win}/{len(b2_races)} ({b2_win/len(b2_races)*100:.0f}%) 期待30%")

if __name__ == "__main__":
    simple_test()
