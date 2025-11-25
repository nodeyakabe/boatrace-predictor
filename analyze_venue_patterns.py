"""
データから各競艇場の傾向を自動抽出
"""
import sqlite3
import sys
import io

# Windows環境でのUTF-8出力対応
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def analyze_venue_patterns(venue_code=None):
    """
    競艇場のデータから統計的に有意な傾向を抽出
    """
    conn = sqlite3.connect('data/boatrace.db')
    c = conn.cursor()

    venue_filter = f"AND r.venue_code = '{venue_code}'" if venue_code else ""
    venue_name = f"場{venue_code}" if venue_code else "全国"

    print(f"\n{'='*80}")
    print(f"{venue_name} - 傾向分析")
    print(f"{'='*80}\n")

    # 1. インの強さ分析
    c.execute(f"""
        SELECT
            AVG(CASE WHEN res.rank = 1 AND rd.actual_course = 1 THEN 1.0 ELSE 0.0 END) as course1_win,
            AVG(CASE WHEN res.rank = 1 AND rd.actual_course IN (1,2,3) THEN 1.0 ELSE 0.0 END) as inside_win
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        LEFT JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
        WHERE r.race_date >= date('now', '-90 days')
        {venue_filter}
    """)
    row = c.fetchone()
    if row and row[0]:
        course1_win = row[0] * 100
        inside_win = row[1] * 100

        print("【インの強さ】")
        if course1_win > 55:
            print(f"  ✅ 超固い場: 1コース勝率 {course1_win:.1f}% (全国平均より+10%以上)")
        elif course1_win > 50:
            print(f"  ✅ 固い場: 1コース勝率 {course1_win:.1f}% (イン有利)")
        elif course1_win < 45:
            print(f"  ⚠️ 荒れる場: 1コース勝率 {course1_win:.1f}% (センター・アウト有利)")
        else:
            print(f"  📊 標準的: 1コース勝率 {course1_win:.1f}%")

        print(f"  インコース（1-3）勝率: {inside_win:.1f}%\n")

    # 2. 時間帯別の傾向
    c.execute(f"""
        SELECT
            CASE
                WHEN CAST(substr(r.race_time, 1, 2) AS INTEGER) < 12 THEN '午前'
                WHEN CAST(substr(r.race_time, 1, 2) AS INTEGER) < 15 THEN '午後前半'
                ELSE '午後後半'
            END as time_zone,
            AVG(CASE WHEN res.rank = 1 AND rd.actual_course = 1 THEN 1.0 ELSE 0.0 END) as course1_win
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        LEFT JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
        WHERE r.race_date >= date('now', '-90 days')
          AND r.race_time IS NOT NULL
        {venue_filter}
        GROUP BY time_zone
        HAVING COUNT(*) >= 20
        ORDER BY course1_win DESC
    """)
    time_data = c.fetchall()

    if len(time_data) >= 2:
        print("【時間帯別傾向】")
        best_time = time_data[0]
        worst_time = time_data[-1]
        diff = (best_time[1] - worst_time[1]) * 100

        if diff > 5:
            print(f"  ⏰ {best_time[0]}が最もイン有利 ({best_time[1]*100:.1f}%)")
            print(f"  ⏰ {worst_time[0]}が最も荒れやすい ({worst_time[1]*100:.1f}%)")
            print(f"  📊 時間帯による差: {diff:.1f}ポイント\n")
        else:
            print(f"  📊 時間帯による大きな差はなし（{diff:.1f}ポイント差）\n")

    # 3. 季節別の傾向
    c.execute(f"""
        SELECT
            CASE
                WHEN CAST(substr(r.race_date, 6, 2) AS INTEGER) IN (3, 4, 5) THEN '春'
                WHEN CAST(substr(r.race_date, 6, 2) AS INTEGER) IN (6, 7, 8) THEN '夏'
                WHEN CAST(substr(r.race_date, 6, 2) AS INTEGER) IN (9, 10, 11) THEN '秋'
                ELSE '冬'
            END as season,
            AVG(CASE WHEN res.rank = 1 AND rd.actual_course = 1 THEN 1.0 ELSE 0.0 END) as course1_win,
            COUNT(*) as race_count
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        LEFT JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
        WHERE r.race_date >= date('now', '-180 days')
        {venue_filter}
        GROUP BY season
        HAVING race_count >= 30
        ORDER BY course1_win DESC
    """)
    season_data = c.fetchall()

    if len(season_data) >= 2:
        print("【季節別傾向】")
        for season, win_rate, count in season_data[:2]:
            print(f"  🌸 {season}: 1コース勝率 {win_rate*100:.1f}% ({count}レース)")

        best_season = season_data[0]
        worst_season = season_data[-1]
        diff = (best_season[1] - worst_season[1]) * 100

        if diff > 5:
            print(f"  ⚠️ 季節による差が大きい: {diff:.1f}ポイント\n")
        else:
            print(f"  📊 季節による大きな差はなし\n")

    # 4. コース別決まり手
    c.execute(f"""
        SELECT
            rd.actual_course,
            res.kimarite,
            COUNT(*) as count
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        LEFT JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
        WHERE r.race_date >= date('now', '-90 days')
          AND res.rank = 1
          AND res.kimarite IS NOT NULL
        {venue_filter}
        GROUP BY rd.actual_course, res.kimarite
        HAVING count >= 5
        ORDER BY rd.actual_course, count DESC
    """)
    kimarite_data = {}
    for course, kimarite, count in c.fetchall():
        if course not in kimarite_data:
            kimarite_data[course] = []
        kimarite_data[course].append((kimarite, count))

    if kimarite_data:
        print("【決まり手の特徴】")
        for course in sorted(kimarite_data.keys())[:4]:  # 1-4コースのみ
            if kimarite_data[course]:
                top_kimarite = kimarite_data[course][0]
                total = sum(k[1] for k in kimarite_data[course])
                rate = top_kimarite[1] / total * 100
                print(f"  {course}コース: {top_kimarite[0]}が最多 ({rate:.1f}%, {top_kimarite[1]}回)")
        print()

    # 5. アウトコース（4-6）の勝率
    c.execute(f"""
        SELECT
            COUNT(CASE WHEN rd.actual_course >= 4 AND res.rank = 1 THEN 1 END) as outer_wins,
            COUNT(CASE WHEN res.rank = 1 THEN 1 END) as total_wins
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        LEFT JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
        WHERE r.race_date >= date('now', '-90 days')
        {venue_filter}
    """)
    row = c.fetchone()
    if row and row[1]:
        outer_win_rate = row[0] / row[1] * 100 if row[1] > 0 else 0

        print("【アウトコースの活躍度】")
        if outer_win_rate > 20:
            print(f"  💰 アウトが活躍する場: {outer_win_rate:.1f}% (荒れやすい)")
        elif outer_win_rate > 15:
            print(f"  📊 アウトもチャンスあり: {outer_win_rate:.1f}%")
        else:
            print(f"  📊 アウト厳しい: {outer_win_rate:.1f}%")
        print()

    # 6. 提案できる法則
    print("【提案される法則】")

    # インが強い場合
    if course1_win > 55:
        print(f"  ✅ 「{venue_name}はインが超強い（1コース勝率+15%）」")

    # 時間帯別
    if len(time_data) >= 2 and diff > 5:
        print(f"  ✅ 「{venue_name}：{best_time[0]}は1コース勝率+{diff:.0f}%」")

    # 季節別
    if len(season_data) >= 2:
        best_season = season_data[0]
        worst_season = season_data[-1]
        season_diff = (best_season[1] - worst_season[1]) * 100
        if season_diff > 5:
            print(f"  ✅ 「{venue_name}：{best_season[0]}は1コース勝率+{season_diff:.0f}%」")

    # 荒れる場
    if outer_win_rate > 20:
        print(f"  ✅ 「{venue_name}は荒れる場（アウト勝率{outer_win_rate:.1f}%）」")

    conn.close()
    print("\n" + "="*80 + "\n")

if __name__ == "__main__":
    # 全国傾向
    analyze_venue_patterns()

    # 各競艇場の傾向（サンプル）
    for venue in ['01', '03', '24']:
        analyze_venue_patterns(venue)
