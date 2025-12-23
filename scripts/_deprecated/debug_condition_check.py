"""条件判定デバッグスクリプト"""
import sqlite3
import statistics

def should_buy_trio_insurance(cursor, race_id):
    """3連複を購入するか判定"""
    reasons = []

    # 条件1: 進入変動あり
    cursor.execute("""
        SELECT pit_number, actual_course
        FROM race_details
        WHERE race_id = ?
        AND actual_course IS NOT NULL
    """, (race_id,))
    entries = cursor.fetchall()

    has_course_change = False
    if entries:
        for pit, course in entries:
            if pit != course:
                has_course_change = True
                break

    if has_course_change:
        reasons.append("進入変動あり")

    # 条件2: ST/展示のバラつき大
    cursor.execute("""
        SELECT
            exhibition_time,
            st_time
        FROM race_details
        WHERE race_id = ?
        AND exhibition_time IS NOT NULL
        AND st_time IS NOT NULL
    """, (race_id,))

    timing_data = cursor.fetchall()

    if len(timing_data) >= 4:
        exhibition_times = [float(t[0]) for t in timing_data if t[0] and float(t[0]) > 0]
        st_timings = [float(t[1]) for t in timing_data if t[1]]

        if len(exhibition_times) >= 4:
            try:
                ex_std = statistics.stdev(exhibition_times)
                if ex_std >= 0.15:
                    reasons.append(f"展示バラつき大(σ={ex_std:.3f})")
            except:
                pass

        if len(st_timings) >= 4:
            try:
                st_std = statistics.stdev(st_timings)
                if st_std >= 0.08:
                    reasons.append(f"STバラつき大(σ={st_std:.3f})")
            except:
                pass

    # 条件3: 1号艇のモーター指数が弱い
    # motorsテーブルは存在しないので、motor_2rateのみで判定
    cursor.execute("""
        SELECT motor_2rate
        FROM race_details
        WHERE race_id = ?
        AND pit_number = 1
    """, (race_id,))

    pit1_motor = cursor.fetchone()

    if pit1_motor:
        motor_2rate = pit1_motor[0]
        if motor_2rate and float(motor_2rate) < 30.0:
            reasons.append(f"1号艇モーター弱(2連率={motor_2rate}%)")

    return len(reasons) > 0, reasons


conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

# バックテスト対象のレースから最初の100件をチェック
cursor.execute("""
    SELECT r.id, r.race_date
    FROM races r
    WHERE EXISTS (
        SELECT 1 FROM results res
        WHERE res.race_id = r.id AND res.rank IS NOT NULL AND res.is_invalid = 0
    )
    AND EXISTS (
        SELECT 1 FROM race_details rd
        WHERE rd.race_id = r.id
    )
    AND EXISTS (
        SELECT 1 FROM payouts p
        WHERE p.race_id = r.id AND p.bet_type = 'trio'
    )
    AND r.race_date >= date('now', '-6 months')
    ORDER BY r.race_date DESC, r.id DESC
    LIMIT 100
""")
races = cursor.fetchall()

print(f"チェック対象: {len(races)}レース\n")

condition_met_count = 0
condition_details = {}

for race_id, race_date in races:
    should_buy, reasons = should_buy_trio_insurance(cursor, race_id)
    if should_buy:
        condition_met_count += 1
        for reason in reasons:
            condition_details[reason] = condition_details.get(reason, 0) + 1
        if condition_met_count <= 10:
            print(f"race_id={race_id}, date={race_date}: {reasons}")

print(f"\n条件該当レース数: {condition_met_count}/{len(races)} ({condition_met_count/len(races)*100:.1f}%)")
print("\n条件別発生回数:")
for reason, count in sorted(condition_details.items(), key=lambda x: x[1], reverse=True):
    print(f"  {reason}: {count}回")

conn.close()
