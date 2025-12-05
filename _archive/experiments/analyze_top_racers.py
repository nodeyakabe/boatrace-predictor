"""
トップ選手の分析と法則抽出
"""
import sqlite3
import sys
import io

# Windows環境でのUTF-8出力対応
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def analyze_top_racers():
    conn = sqlite3.connect('data/boatrace.db')
    c = conn.cursor()

    print("="*80)
    print("トップ選手分析 - 法則抽出")
    print("="*80)
    print()

    # 1. トップ選手を抽出（現在あるデータから上位20名）
    c.execute("""
        SELECT
            e.racer_number,
            e.racer_name,
            COUNT(DISTINCT r.id) as race_count,
            AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) * 100 as win_rate,
            AVG(CASE WHEN CAST(res.rank AS INTEGER) <= 2 THEN 1.0 ELSE 0.0 END) * 100 as place2_rate,
            AVG(CASE WHEN CAST(res.rank AS INTEGER) <= 3 THEN 1.0 ELSE 0.0 END) * 100 as place3_rate
        FROM entries e
        JOIN races r ON e.race_id = r.id
        LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
        GROUP BY e.racer_number, e.racer_name
        HAVING race_count >= 5
        ORDER BY win_rate DESC
        LIMIT 20
    """)

    top_racers = c.fetchall()

    if not top_racers:
        print("⚠️ 条件を満たすトップ選手が見つかりませんでした")
        conn.close()
        return

    print(f"【トップ選手20名】（5レース以上出場、勝率順）")
    print()
    for idx, racer in enumerate(top_racers, 1):
        print(f"{idx:2d}. {racer[1]:10s} (#{racer[0]:>6s})  勝率{racer[3]:5.1f}%  2連対{racer[4]:5.1f}%  3連対{racer[5]:5.1f}%  ({racer[2]:3d}レース)")

    print()
    print("="*80)
    print()

    # 2. 各選手の詳細分析
    analyzed_racers = []

    for racer in top_racers[:10]:  # 上位10名を詳細分析
        racer_number = racer[0]
        racer_name = racer[1]
        overall_win_rate = racer[3]

        print(f"【{racer_name} (#{racer_number}) 詳細分析】")
        print(f"全体勝率: {overall_win_rate:.1f}%")
        print()

        racer_data = {
            'number': racer_number,
            'name': racer_name,
            'overall_win_rate': overall_win_rate,
            'strong_venues': [],
            'strong_courses': [],
            'good_st': False,
            'favorite_kimarite': None
        }

        # 得意場分析
        c.execute("""
            SELECT
                r.venue_code,
                COUNT(*) as races,
                AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) * 100 as win_rate
            FROM entries e
            JOIN races r ON e.race_id = r.id
            LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
            WHERE e.racer_number = ?
            GROUP BY r.venue_code
            HAVING races >= 3
            ORDER BY win_rate DESC
            LIMIT 3
        """, (racer_number,))

        venue_data = c.fetchall()
        if venue_data:
            print("  得意場:")
            venue_names = {
                '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島',
                '05': '多摩川', '06': '浜名湖', '07': '蒲郡', '08': '常滑',
                '09': '津', '10': '三国', '11': 'びわこ', '12': '住之江',
                '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島',
                '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
                '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
            }

            for venue in venue_data:
                venue_name = venue_names.get(venue[0], f"場{venue[0]}")
                diff = venue[2] - overall_win_rate
                if diff > 5:  # 全体より5%以上高い
                    print(f"    {venue_name}({venue[0]}): 勝率{venue[2]:5.1f}% (全体+{diff:4.1f}%)  ({venue[1]:2d}レース)")
                    racer_data['strong_venues'].append({
                        'code': venue[0],
                        'name': venue_name,
                        'win_rate': venue[2],
                        'boost': diff
                    })

        # 得意コース分析
        c.execute("""
            SELECT
                rd.actual_course,
                COUNT(*) as races,
                AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) * 100 as win_rate
            FROM entries e
            JOIN races r ON e.race_id = r.id
            JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
            LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
            WHERE e.racer_number = ?
            GROUP BY rd.actual_course
            HAVING races >= 3
            ORDER BY win_rate DESC
        """, (racer_number,))

        course_data = c.fetchall()
        if course_data:
            print("  得意コース:")
            for course in course_data:
                if course[0]:
                    diff = course[2] - overall_win_rate
                    if diff > 5:
                        print(f"    {course[0]}コース: 勝率{course[2]:5.1f}% (全体+{diff:4.1f}%)  ({course[1]:2d}レース)")
                        racer_data['strong_courses'].append({
                            'course': course[0],
                            'win_rate': course[2],
                            'boost': diff
                        })

        # STタイミング分析
        c.execute("""
            SELECT
                AVG(rd.st_time) as avg_st,
                COUNT(*) as st_count
            FROM entries e
            JOIN races r ON e.race_id = r.id
            JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
            WHERE e.racer_number = ?
              AND rd.st_time IS NOT NULL
        """, (racer_number,))

        st_data = c.fetchone()
        if st_data and st_data[1] >= 10:
            avg_st = st_data[0]
            print(f"  平均ST: {avg_st:.3f}秒  ({st_data[1]}回)")

            if avg_st < 0.16:
                print(f"    💡 STが非常に速い（0.16秒未満） → スタート優位")
                racer_data['good_st'] = True

        # 得意決まり手
        c.execute("""
            SELECT
                res.kimarite,
                COUNT(*) as count
            FROM entries e
            JOIN races r ON e.race_id = r.id
            LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
            WHERE e.racer_number = ?
              AND res.rank = '1'
              AND res.kimarite IS NOT NULL
            GROUP BY res.kimarite
            ORDER BY count DESC
            LIMIT 1
        """, (racer_number,))

        kimarite_data = c.fetchone()
        if kimarite_data:
            print(f"  得意決まり手: {kimarite_data[0]} ({kimarite_data[1]}回)")
            racer_data['favorite_kimarite'] = kimarite_data[0]

        print()
        analyzed_racers.append(racer_data)

    # 3. 提案される法則
    print("="*80)
    print("【提案される選手別法則】")
    print("="*80)
    print()

    for racer in analyzed_racers:
        if racer['strong_venues'] or racer['strong_courses'] or racer['good_st']:
            print(f"■ {racer['name']} (#{racer['number']})")

            # 得意場の法則
            for venue in racer['strong_venues']:
                effect = round(venue['boost'] / 100, 2)
                print(f"  ✅ {venue['name']}で{racer['name']}が出場時、勝率{effect:+.2f}")
                print(f"     (根拠: {venue['name']}勝率{venue['win_rate']:.1f}% vs 全体{racer['overall_win_rate']:.1f}%)")

            # 得意コースの法則
            for course in racer['strong_courses']:
                effect = round(course['boost'] / 100, 2)
                print(f"  ✅ {course['course']}コースで{racer['name']}が出場時、勝率{effect:+.2f}")
                print(f"     (根拠: {course['course']}コース勝率{course['win_rate']:.1f}% vs 全体{racer['overall_win_rate']:.1f}%)")

            # STの法則
            if racer['good_st']:
                print(f"  ✅ {racer['name']}はSTが速い → スタート展示で0.16秒未満なら勝率+0.03")

            print()

    conn.close()
    print("="*80)

if __name__ == "__main__":
    analyze_top_racers()
