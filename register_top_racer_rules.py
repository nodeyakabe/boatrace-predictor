"""
トップ選手の分析結果から法則を自動登録
"""
import sqlite3
import sys
import io

# Windows環境でのUTF-8出力対応
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def register_top_racer_rules():
    conn = sqlite3.connect('data/boatrace.db')
    c = conn.cursor()

    print("=" * 80)
    print("トップ選手法則 自動登録")
    print("=" * 80)
    print()

    # トップ選手を抽出（20レース以上、勝率上位30名）
    c.execute("""
        SELECT * FROM (
            SELECT
                e.racer_number,
                e.racer_name,
                COUNT(DISTINCT r.id) as race_count,
                AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) * 100 as win_rate
            FROM entries e
            JOIN races r ON e.race_id = r.id
            LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
            GROUP BY e.racer_number, e.racer_name
            HAVING race_count >= 20
            ORDER BY win_rate DESC
            LIMIT 30
        ) WHERE win_rate >= 25
    """)

    top_racers = c.fetchall()
    print(f"📊 対象選手: {len(top_racers)}名（20レース以上、勝率25%以上、上位30名）")
    print()

    registered_count = 0
    skipped_count = 0

    for racer_number, racer_name, race_count, overall_win_rate in top_racers:
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
        for venue_code, races, venue_win_rate in venue_data:
            diff = venue_win_rate - overall_win_rate
            if diff > 10:  # 全体より10%以上高い場合のみ登録
                effect = round(diff / 100, 2)
                description = f"{racer_name}：{venue_code}場で勝率{diff:+.1f}%"

                try:
                    c.execute("""
                        INSERT INTO racer_rules
                        (racer_number, racer_name, rule_type, venue_code, course_number,
                         condition_type, effect_type, effect_value, description)
                        VALUES (?, ?, 'venue_strong', ?, NULL, NULL, 'win_rate_boost', ?, ?)
                    """, (racer_number, racer_name, venue_code, effect, description))

                    print(f"✅ {description}")
                    registered_count += 1
                except sqlite3.IntegrityError:
                    skipped_count += 1

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
        for course, races, course_win_rate in course_data:
            if course:
                diff = course_win_rate - overall_win_rate
                if diff > 15:  # 全体より15%以上高い場合のみ登録
                    effect = round(diff / 100, 2)
                    description = f"{racer_name}：{course}コースで勝率{diff:+.1f}%"

                    try:
                        c.execute("""
                            INSERT INTO racer_rules
                            (racer_number, racer_name, rule_type, venue_code, course_number,
                             condition_type, effect_type, effect_value, description)
                            VALUES (?, ?, 'course_strong', NULL, ?, NULL, 'win_rate_boost', ?, ?)
                        """, (racer_number, racer_name, course, effect, description))

                        print(f"✅ {description}")
                        registered_count += 1
                    except sqlite3.IntegrityError:
                        skipped_count += 1

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
            if avg_st < 0.16:
                description = f"{racer_name}：STが速い（平均{avg_st:.3f}秒）"

                try:
                    c.execute("""
                        INSERT INTO racer_rules
                        (racer_number, racer_name, rule_type, venue_code, course_number,
                         condition_type, effect_type, effect_value, description)
                        VALUES (?, ?, 'st_fast', NULL, NULL, 'fast_st', 'win_rate_boost', 0.03, ?)
                    """, (racer_number, racer_name, description))

                    print(f"✅ {description}")
                    registered_count += 1
                except sqlite3.IntegrityError:
                    skipped_count += 1

    conn.commit()

    print()
    print(f"📝 登録完了: {registered_count}件")
    print(f"⏭️  スキップ（既存）: {skipped_count}件")
    print()

    # 登録結果を確認
    c.execute("SELECT COUNT(*) FROM racer_rules WHERE is_active = 1")
    total_count = c.fetchone()[0]
    print(f"📊 有効な選手別法則: {total_count}件")
    print()

    # 種類別集計
    c.execute("""
        SELECT rule_type, COUNT(*) as count
        FROM racer_rules
        WHERE is_active = 1
        GROUP BY rule_type
    """)

    print("【法則種類別】")
    for rule_type, count in c.fetchall():
        rule_type_name = {
            'venue_strong': '得意場',
            'course_strong': '得意コース',
            'st_fast': 'ST優位'
        }.get(rule_type, rule_type)
        print(f"  {rule_type_name}: {count}件")
    print()

    conn.close()
    print("=" * 80)

if __name__ == "__main__":
    register_top_racer_rules()
