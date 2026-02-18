"""
統計指標の信頼性検証スクリプト
DB内の各統計指標が正確かつ信頼できるかを確認する
"""
import sys
import os
import sqlite3

# Windows環境でのUTF-8出力設定
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = r"c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\data\boatrace.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def print_section(title):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_subsection(title):
    print()
    print(f"--- {title} ---")


# -----------------------------------------------------------------------
# 2-1. 選手成績統計の精度検証
# -----------------------------------------------------------------------
def check_racer_win_rate_accuracy():
    print_section("2-1. 選手成績統計の精度検証（win_rate vs 実際の勝率）")

    conn = get_connection()
    cur = conn.cursor()

    # テーブル存在確認
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='racers'")
    has_racers = cur.fetchone() is not None

    if has_racers:
        cur.execute("SELECT COUNT(*) FROM racers")
        cnt = cur.fetchone()[0]
        print(f"racersテーブル: {cnt:,}件")

        # racersのカラム確認
        cur.execute("PRAGMA table_info(racers)")
        cols = [r[1] for r in cur.fetchall()]
        print(f"racersカラム: {cols}")
    else:
        print("[情報] racersテーブルが存在しません。entriesテーブルのwin_rateを使用します。")

    # entriesテーブルのカラム確認
    cur.execute("PRAGMA table_info(entries)")
    entry_cols = [r[1] for r in cur.fetchall()]
    print(f"\nentriesカラム（関連）: win_rate={'win_rate' in entry_cols}, "
          f"second_rate={'second_rate' in entry_cols}, "
          f"racer_number={'racer_number' in entry_cols}")

    if 'win_rate' not in entry_cols:
        print("[警告] entriesテーブルにwin_rateカラムがありません")
        conn.close()
        return

    print_subsection("選手別の実際の勝率 vs 記録済み勝率（2024年、20試合以上）")

    sql = """
    SELECT
        e.racer_number,
        strftime('%Y', r.race_date) as year,
        COUNT(*) as race_count,
        ROUND(100.0 * SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) / COUNT(*), 2) as actual_win_rate,
        MAX(e.win_rate) as stored_win_rate,
        ROUND(ABS(
            ROUND(100.0 * SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) / COUNT(*), 2)
            - MAX(e.win_rate)
        ), 2) as diff
    FROM entries e
    JOIN races r ON e.race_id = r.id
    JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
    WHERE r.race_date BETWEEN '2024-01-01' AND '2024-12-31'
      AND e.win_rate IS NOT NULL
    GROUP BY e.racer_number, year
    HAVING race_count >= 20
    ORDER BY diff DESC
    LIMIT 20
    """

    try:
        cur.execute(sql)
        rows = cur.fetchall()

        if not rows:
            print("[情報] 対象データなし（2024年、20試合以上、win_rate有り）")
        else:
            print(f"{'選手番号':>10} {'年':>6} {'試合数':>8} {'実際勝率':>10} {'記録勝率':>10} {'差':>8}")
            print("-" * 60)
            large_diff_count = 0
            for row in rows:
                marker = " [!]" if row['diff'] > 5.0 else ""
                print(f"{row['racer_number']:>10} {row['year']:>6} {row['race_count']:>8} "
                      f"{row['actual_win_rate']:>10.2f}% {row['stored_win_rate']:>10.2f}% "
                      f"{row['diff']:>8.2f}%{marker}")
                if row['diff'] > 5.0:
                    large_diff_count += 1

            print()
            if large_diff_count > 0:
                print(f"[警告] 差異5%超の選手: {large_diff_count}人")
                print("  → win_rateは「当該期間の累計成績」ではなく「直近の公式成績」の可能性があります")
            else:
                print("[正常] 全選手の差異が5%以内")

            # 統計サマリー
            diffs = [row['diff'] for row in rows]
            avg_diff = sum(diffs) / len(diffs)
            max_diff = max(diffs)
            print(f"\n差異統計（上位20選手）:")
            print(f"  平均差異: {avg_diff:.2f}%")
            print(f"  最大差異: {max_diff:.2f}%")

            # 差異の分布
            bins = [0, 1, 3, 5, 10, float('inf')]
            labels = ["0-1%", "1-3%", "3-5%", "5-10%", "10%超"]
            for i in range(len(labels)):
                cnt = sum(1 for d in diffs if bins[i] <= d < bins[i+1])
                print(f"  {labels[i]}: {cnt}人")

    except Exception as e:
        print(f"[エラー] {e}")

    # 追加: win_rateの基本統計
    print_subsection("entriesテーブル win_rate の基本統計")
    try:
        cur.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(win_rate) as non_null,
            ROUND(100.0 * COUNT(win_rate) / COUNT(*), 2) as fill_rate,
            MIN(win_rate) as min_val,
            MAX(win_rate) as max_val,
            ROUND(AVG(win_rate), 2) as avg_val
        FROM entries
        """)
        row = cur.fetchone()
        print(f"  総レコード数: {row['total']:,}")
        print(f"  非NULL件数:  {row['non_null']:,}")
        print(f"  充足率:      {row['fill_rate']}%")
        print(f"  最小値:      {row['min_val']}")
        print(f"  最大値:      {row['max_val']}")
        print(f"  平均値:      {row['avg_val']}")

        if row['fill_rate'] >= 95:
            print("[正常] win_rate充足率は95%以上")
        elif row['fill_rate'] >= 80:
            print("[注意] win_rate充足率が80-95%")
        else:
            print("[警告] win_rate充足率が80%未満 → 予測精度に影響する可能性")

        # 異常値チェック
        cur.execute("""
        SELECT COUNT(*) FROM entries
        WHERE win_rate IS NOT NULL AND (win_rate < 0 OR win_rate > 100)
        """)
        abnormal = cur.fetchone()[0]
        if abnormal > 0:
            print(f"[警告] win_rate異常値（<0 or >100）: {abnormal}件")
        else:
            print("[正常] win_rate異常値なし")

    except Exception as e:
        print(f"[エラー] {e}")

    conn.close()


# -----------------------------------------------------------------------
# 2-2. motor_second_rate の分布と信頼性
# -----------------------------------------------------------------------
def check_motor_second_rate():
    print_section("2-2. motor_second_rate の分布と信頼性")

    conn = get_connection()
    cur = conn.cursor()

    # カラム存在確認
    cur.execute("PRAGMA table_info(entries)")
    entry_cols = [r[1] for r in cur.fetchall()]

    if 'motor_second_rate' not in entry_cols:
        print("[情報] entriesテーブルにmotor_second_rateカラムがありません")
        conn.close()
        return

    print_subsection("基本統計")
    cur.execute("""
    SELECT
        COUNT(*) as total,
        COUNT(motor_second_rate) as non_null,
        ROUND(100.0 * COUNT(motor_second_rate) / COUNT(*), 2) as fill_rate,
        MIN(motor_second_rate) as min_val,
        MAX(motor_second_rate) as max_val,
        ROUND(AVG(motor_second_rate), 2) as avg_val,
        ROUND(
            (SELECT motor_second_rate FROM entries WHERE motor_second_rate IS NOT NULL
             ORDER BY motor_second_rate
             LIMIT 1 OFFSET (SELECT COUNT(*) FROM entries WHERE motor_second_rate IS NOT NULL) / 2),
            2
        ) as median_approx
    FROM entries
    """)
    row = cur.fetchone()
    print(f"  総レコード数: {row['total']:,}")
    print(f"  非NULL件数:  {row['non_null']:,}")
    print(f"  充足率:      {row['fill_rate']}%")
    print(f"  最小値:      {row['min_val']}")
    print(f"  最大値:      {row['max_val']}")
    print(f"  平均値:      {row['avg_val']}")
    print(f"  中央値(近似):{row['median_approx']}")

    fill_rate = row['fill_rate']
    if fill_rate >= 90:
        print("[正常] motor_second_rate充足率は90%以上")
    elif fill_rate >= 70:
        print("[注意] motor_second_rate充足率が70-90% → バックテストへの部分的影響")
    else:
        print("[警告] motor_second_rate充足率が70%未満 → バックテストへの重大な影響")

    print_subsection("ヒストグラム（分布）")
    cur.execute("""
    SELECT
        CASE
            WHEN motor_second_rate = 0   THEN '0%（完全0）'
            WHEN motor_second_rate < 10  THEN '0-10%'
            WHEN motor_second_rate < 20  THEN '10-20%'
            WHEN motor_second_rate < 30  THEN '20-30%'
            WHEN motor_second_rate < 40  THEN '30-40%'
            WHEN motor_second_rate < 50  THEN '40-50%'
            WHEN motor_second_rate < 60  THEN '50-60%'
            WHEN motor_second_rate < 70  THEN '60-70%'
            WHEN motor_second_rate < 80  THEN '70-80%'
            WHEN motor_second_rate < 90  THEN '80-90%'
            WHEN motor_second_rate < 100 THEN '90-100%'
            WHEN motor_second_rate = 100 THEN '100%（完全100）'
            ELSE 'その他'
        END as bucket,
        COUNT(*) as cnt,
        ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) as pct
    FROM entries
    WHERE motor_second_rate IS NOT NULL
    GROUP BY bucket
    ORDER BY MIN(motor_second_rate)
    """)
    rows = cur.fetchall()
    for row in rows:
        bar = "#" * int(row['pct'] / 2)
        print(f"  {row['bucket']:12}: {row['cnt']:8,}件 ({row['pct']:5.1f}%) {bar}")

    print_subsection("異常値チェック")
    # 0%の件数
    cur.execute("SELECT COUNT(*) FROM entries WHERE motor_second_rate = 0")
    zero_cnt = cur.fetchone()[0]

    # 100%の件数
    cur.execute("SELECT COUNT(*) FROM entries WHERE motor_second_rate = 100")
    hundred_cnt = cur.fetchone()[0]

    # 0未満・100超
    cur.execute("SELECT COUNT(*) FROM entries WHERE motor_second_rate < 0 OR motor_second_rate > 100")
    out_of_range = cur.fetchone()[0]

    total_non_null = row['cnt']  # 最後のbucket使用は不正確なので再計算
    cur.execute("SELECT COUNT(*) FROM entries WHERE motor_second_rate IS NOT NULL")
    total_non_null = cur.fetchone()[0]

    print(f"  0%（使用0回？）: {zero_cnt:,}件 ({100.0*zero_cnt/max(total_non_null,1):.1f}%)")
    print(f"  100%（全て的中？）: {hundred_cnt:,}件 ({100.0*hundred_cnt/max(total_non_null,1):.1f}%)")
    print(f"  範囲外（<0 or >100）: {out_of_range:,}件")

    if out_of_range > 0:
        print("[警告] motor_second_rateに範囲外の値あり")
    else:
        print("[正常] motor_second_rate範囲外の値なし")

    if zero_cnt > total_non_null * 0.1:
        print(f"[注意] motor_second_rate=0が{100.0*zero_cnt/total_non_null:.1f}%を占める → 新モーターや欠損の可能性")

    print_subsection("年度別の充足率")
    cur.execute("""
    SELECT
        strftime('%Y', r.race_date) as year,
        COUNT(*) as total,
        COUNT(e.motor_second_rate) as non_null,
        ROUND(100.0 * COUNT(e.motor_second_rate) / COUNT(*), 1) as fill_rate,
        ROUND(AVG(e.motor_second_rate), 2) as avg_rate
    FROM entries e
    JOIN races r ON e.race_id = r.id
    WHERE r.race_date >= '2020-01-01'
    GROUP BY year
    ORDER BY year
    """)
    rows = cur.fetchall()
    print(f"  {'年度':>6} {'総数':>10} {'非NULL':>10} {'充足率':>8} {'平均値':>8}")
    print("  " + "-" * 46)
    for row in rows:
        flag = " [!]" if row['fill_rate'] < 80 else ""
        print(f"  {row['year']:>6} {row['total']:>10,} {row['non_null']:>10,} "
              f"{row['fill_rate']:>8.1f}% {row['avg_rate']:>8.2f}%{flag}")

    conn.close()


# -----------------------------------------------------------------------
# 2-3. local_win_rate の充足率確認
# -----------------------------------------------------------------------
def check_local_win_rate():
    print_section("2-3. local_win_rate の充足率確認（entriesテーブル）")

    conn = get_connection()
    cur = conn.cursor()

    # entriesカラム確認
    cur.execute("PRAGMA table_info(entries)")
    entry_cols = {r[1]: r for r in cur.fetchall()}

    target_cols = [
        'local_win_rate',
        'local_second_rate',
        'f_count',
        'l_count',
        'motor_second_rate',
        'boat_second_rate',
        'win_rate',
        'second_rate',
    ]

    print_subsection("entriesテーブル 各カラムの充足率")
    print(f"  {'カラム名':25} {'充足率':>8} {'非NULL件数':>12} {'最小':>8} {'最大':>8} {'平均':>8} 判定")
    print("  " + "-" * 90)

    for col in target_cols:
        if col not in entry_cols:
            print(f"  {col:25} {'N/A（カラム不存在）':>20}")
            continue

        cur.execute(f"""
        SELECT
            COUNT(*) as total,
            COUNT({col}) as non_null,
            ROUND(100.0 * COUNT({col}) / COUNT(*), 1) as fill_rate,
            MIN({col}) as min_val,
            MAX({col}) as max_val,
            ROUND(AVG({col}), 2) as avg_val
        FROM entries
        """)
        row = cur.fetchone()

        if row['fill_rate'] >= 90:
            status = "[正常]"
        elif row['fill_rate'] >= 70:
            status = "[注意]"
        else:
            status = "[警告]"

        min_val = f"{row['min_val']:.1f}" if row['min_val'] is not None else "NULL"
        max_val = f"{row['max_val']:.1f}" if row['max_val'] is not None else "NULL"
        avg_val = f"{row['avg_val']:.2f}" if row['avg_val'] is not None else "NULL"

        print(f"  {col:25} {row['fill_rate']:>8.1f}% {row['non_null']:>12,} "
              f"{min_val:>8} {max_val:>8} {avg_val:>8} {status}")

    # race_detailsのexhibition_courseも確認
    print_subsection("race_detailsテーブル 各カラムの充足率")
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='race_details'")
    if cur.fetchone():
        cur.execute("PRAGMA table_info(race_details)")
        rd_cols = {r[1]: r for r in cur.fetchall()}

        rd_target = ['exhibition_course', 'exhibition_time', 'st_time', 'actual_course']
        print(f"  {'カラム名':25} {'充足率':>8} {'非NULL件数':>12} {'最小':>8} {'最大':>8} 判定")
        print("  " + "-" * 75)

        for col in rd_target:
            if col not in rd_cols:
                print(f"  {col:25} {'N/A（カラム不存在）':>20}")
                continue

            cur.execute(f"""
            SELECT
                COUNT(*) as total,
                COUNT({col}) as non_null,
                ROUND(100.0 * COUNT({col}) / COUNT(*), 1) as fill_rate,
                MIN({col}) as min_val,
                MAX({col}) as max_val
            FROM race_details
            """)
            row = cur.fetchone()

            if row['fill_rate'] >= 90:
                status = "[正常]"
            elif row['fill_rate'] >= 70:
                status = "[注意]"
            else:
                status = "[警告]"

            min_val = str(row['min_val'])[:8] if row['min_val'] is not None else "NULL"
            max_val = str(row['max_val'])[:8] if row['max_val'] is not None else "NULL"

            print(f"  {col:25} {row['fill_rate']:>8.1f}% {row['non_null']:>12,} "
                  f"{min_val:>8} {max_val:>8} {status}")
    else:
        print("  [情報] race_detailsテーブルが存在しません")

    # local_win_rateの年度別充足率
    if 'local_win_rate' in entry_cols:
        print_subsection("local_win_rate の年度別充足率")
        cur.execute("""
        SELECT
            strftime('%Y', r.race_date) as year,
            COUNT(*) as total,
            COUNT(e.local_win_rate) as non_null,
            ROUND(100.0 * COUNT(e.local_win_rate) / COUNT(*), 1) as fill_rate,
            ROUND(AVG(e.local_win_rate), 2) as avg_rate
        FROM entries e
        JOIN races r ON e.race_id = r.id
        WHERE r.race_date >= '2020-01-01'
        GROUP BY year
        ORDER BY year
        """)
        rows = cur.fetchall()
        print(f"  {'年度':>6} {'総数':>10} {'非NULL':>10} {'充足率':>8} {'平均':>8}")
        print("  " + "-" * 46)
        for row in rows:
            flag = " [!]" if row['fill_rate'] < 70 else ""
            print(f"  {row['year']:>6} {row['total']:>10,} {row['non_null']:>10,} "
                  f"{row['fill_rate']:>8.1f}% {row['avg_rate']:>8.2f}%{flag}")

    conn.close()


# -----------------------------------------------------------------------
# 2-4. 異常値の検出
# -----------------------------------------------------------------------
def check_anomalies():
    print_section("2-4. 異常値の検出")

    conn = get_connection()
    cur = conn.cursor()

    # trifecta_oddsテーブルのオッズ異常値
    print_subsection("オッズ異常値（trifecta_odds）")
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trifecta_odds'")
    if cur.fetchone():
        cur.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(odds) as non_null,
            SUM(CASE WHEN odds < 1.0 THEN 1 ELSE 0 END) as below_1,
            SUM(CASE WHEN odds > 5000 THEN 1 ELSE 0 END) as above_5000,
            MIN(odds) as min_odds,
            MAX(odds) as max_odds,
            ROUND(AVG(odds), 2) as avg_odds
        FROM trifecta_odds
        """)
        row = cur.fetchone()
        print(f"  総件数:        {row['total']:>12,}")
        print(f"  非NULL件数:    {row['non_null']:>12,}")
        print(f"  オッズ<1.0:    {row['below_1']:>12,}件")
        print(f"  オッズ>5000:   {row['above_5000']:>12,}件")
        print(f"  最小オッズ:    {row['min_odds']}")
        print(f"  最大オッズ:    {row['max_odds']}")
        print(f"  平均オッズ:    {row['avg_odds']}")

        if row['below_1'] > 0:
            print(f"[警告] オッズ<1.0が{row['below_1']}件存在 → データ入力ミスの可能性")
        else:
            print("[正常] オッズ<1.0なし")

        if row['above_5000'] > 0:
            print(f"[注意] オッズ>5000が{row['above_5000']}件存在（競艇では理論上有り得る）")
            # サンプル表示
            cur.execute("""
            SELECT race_id, combination, odds
            FROM trifecta_odds
            WHERE odds > 5000
            LIMIT 5
            """)
            samples = cur.fetchall()
            for s in samples:
                print(f"      race_id={s['race_id']}, 組合={s['combination']}, オッズ={s['odds']}")
    else:
        # win_oddsテーブルを確認
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%odds%'")
        odds_tables = [r[0] for r in cur.fetchall()]
        print(f"  [情報] trifecta_oddsテーブルなし。存在するoddsテーブル: {odds_tables}")

        for tbl in odds_tables[:2]:
            cur.execute(f"PRAGMA table_info({tbl})")
            cols = [r[1] for r in cur.fetchall()]
            odds_col = next((c for c in cols if 'odds' in c.lower()), None)
            if odds_col:
                try:
                    cur.execute(f"""
                    SELECT COUNT(*) as total,
                           SUM(CASE WHEN {odds_col} < 1.0 THEN 1 ELSE 0 END) as below_1,
                           SUM(CASE WHEN {odds_col} > 5000 THEN 1 ELSE 0 END) as above_5000,
                           MIN({odds_col}) as min_val, MAX({odds_col}) as max_val
                    FROM {tbl}
                    """)
                    row = cur.fetchone()
                    print(f"  {tbl}.{odds_col}: 総数={row['total']:,}, "
                          f"<1.0:{row['below_1']}, >5000:{row['above_5000']}, "
                          f"min={row['min_val']}, max={row['max_val']}")
                except:
                    pass

    # win_rateの異常値
    print_subsection("win_rate 異常値（entriesテーブル）")
    cur.execute("PRAGMA table_info(entries)")
    entry_cols = {r[1] for r in cur.fetchall()}

    for col in ['win_rate', 'second_rate', 'local_win_rate', 'local_second_rate']:
        if col not in entry_cols:
            continue
        cur.execute(f"""
        SELECT
            SUM(CASE WHEN {col} < 0 THEN 1 ELSE 0 END) as below_0,
            SUM(CASE WHEN {col} > 100 THEN 1 ELSE 0 END) as above_100,
            COUNT({col}) as non_null
        FROM entries
        """)
        row = cur.fetchone()
        abnormal = (row['below_0'] or 0) + (row['above_100'] or 0)
        if abnormal > 0:
            print(f"  [警告] {col}: <0が{row['below_0']}件, >100が{row['above_100']}件")
        else:
            print(f"  [正常] {col}: 異常値なし（非NULL={row['non_null']:,}件）")

    # motor_second_rateの異常値
    if 'motor_second_rate' in entry_cols:
        cur.execute("""
        SELECT
            SUM(CASE WHEN motor_second_rate < 0 THEN 1 ELSE 0 END) as below_0,
            SUM(CASE WHEN motor_second_rate > 100 THEN 1 ELSE 0 END) as above_100
        FROM entries
        """)
        row = cur.fetchone()
        if (row['below_0'] or 0) + (row['above_100'] or 0) > 0:
            print(f"  [警告] motor_second_rate: <0が{row['below_0']}件, >100が{row['above_100']}件")
        else:
            print(f"  [正常] motor_second_rate: 異常値なし")

    # st_timeの異常値（race_details）
    print_subsection("st_time 異常値（race_detailsテーブル）")
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='race_details'")
    if cur.fetchone():
        cur.execute("PRAGMA table_info(race_details)")
        rd_cols = {r[1] for r in cur.fetchall()}

        if 'st_time' in rd_cols:
            cur.execute("""
            SELECT
                COUNT(st_time) as non_null,
                SUM(CASE WHEN st_time < -0.20 THEN 1 ELSE 0 END) as below_neg020,
                SUM(CASE WHEN st_time > 0.40 THEN 1 ELSE 0 END) as above_040,
                MIN(st_time) as min_val,
                MAX(st_time) as max_val,
                ROUND(AVG(st_time), 4) as avg_val
            FROM race_details
            WHERE st_time IS NOT NULL
            """)
            row = cur.fetchone()
            print(f"  st_time非NULL件数: {row['non_null']:,}")
            print(f"  st_time < -0.20:  {row['below_neg020']:,}件")
            print(f"  st_time > 0.40:   {row['above_040']:,}件")
            print(f"  最小値: {row['min_val']}, 最大値: {row['max_val']}, 平均: {row['avg_val']}")

            abnormal_cnt = (row['below_neg020'] or 0) + (row['above_040'] or 0)
            if abnormal_cnt > 0:
                pct = 100.0 * abnormal_cnt / max(row['non_null'], 1)
                print(f"[警告] st_time異常値: {abnormal_cnt:,}件 ({pct:.2f}%)")
                # サンプル
                cur.execute("""
                SELECT rd.race_id, rd.pit_number, rd.st_time
                FROM race_details rd
                WHERE rd.st_time < -0.20 OR rd.st_time > 0.40
                LIMIT 5
                """)
                samples = cur.fetchall()
                for s in samples:
                    print(f"    race_id={s['race_id']}, pit={s['pit_number']}, st_time={s['st_time']}")
            else:
                print("[正常] st_time範囲内（-0.20 ～ 0.40）")

            # st_time分布
            print_subsection("st_time ヒストグラム")
            cur.execute("""
            SELECT
                CASE
                    WHEN st_time < -0.20 THEN '< -0.20（F？）'
                    WHEN st_time < -0.10 THEN '-0.20～-0.10'
                    WHEN st_time < 0.00  THEN '-0.10～0.00'
                    WHEN st_time < 0.10  THEN '0.00～0.10'
                    WHEN st_time < 0.20  THEN '0.10～0.20'
                    WHEN st_time < 0.30  THEN '0.20～0.30'
                    WHEN st_time < 0.40  THEN '0.30～0.40'
                    ELSE '>= 0.40（遅延？）'
                END as bucket,
                COUNT(*) as cnt,
                ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) as pct
            FROM race_details
            WHERE st_time IS NOT NULL
            GROUP BY bucket
            ORDER BY MIN(st_time)
            """)
            rows = cur.fetchall()
            for row in rows:
                bar = "#" * int(row['pct'] / 2)
                print(f"  {row['bucket']:18}: {row['cnt']:8,}件 ({row['pct']:5.1f}%) {bar}")
        else:
            print("  [情報] st_timeカラムがrace_detailsに存在しません")
    else:
        print("  [情報] race_detailsテーブルが存在しません")

    conn.close()


# -----------------------------------------------------------------------
# 追加: resultsテーブルのrank異常値
# -----------------------------------------------------------------------
def check_results_anomalies():
    print_section("補足: resultsテーブル rank の異常値・分布")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='results'")
    if not cur.fetchone():
        print("[情報] resultsテーブルが存在しません")
        conn.close()
        return

    cur.execute("PRAGMA table_info(results)")
    res_cols = {r[1] for r in cur.fetchall()}

    if 'rank' not in res_cols:
        print("[情報] resultsにrankカラムがありません")
        conn.close()
        return

    cur.execute("""
    SELECT rank, COUNT(*) as cnt
    FROM results
    GROUP BY rank
    ORDER BY CAST(rank AS INTEGER)
    """)
    rows = cur.fetchall()
    print(f"  {'rank値':>8} {'件数':>12}")
    print("  " + "-" * 22)
    for row in rows:
        print(f"  {str(row['rank']):>8} {row['cnt']:>12,}")

    # 1-6以外のrank
    cur.execute("""
    SELECT COUNT(*) FROM results
    WHERE rank NOT IN ('1','2','3','4','5','6')
      AND rank IS NOT NULL
    """)
    abnormal = cur.fetchone()[0]
    if abnormal > 0:
        print(f"\n[注意] rank値が1-6以外: {abnormal:,}件（失格・棄権等の可能性）")
        cur.execute("""
        SELECT DISTINCT rank FROM results
        WHERE rank NOT IN ('1','2','3','4','5','6')
          AND rank IS NOT NULL
        LIMIT 10
        """)
        vals = [r[0] for r in cur.fetchall()]
        print(f"  異常なrank値の例: {vals}")
    else:
        print("[正常] rank値は全て1-6の範囲内")

    conn.close()


# -----------------------------------------------------------------------
# まとめ
# -----------------------------------------------------------------------
def print_summary():
    print_section("まとめ・バックテストへの影響評価")

    print("""
推奨アクション（検証結果に基づいて評価してください）:

1. win_rate / second_rate（entries）
   - 充足率が95%以上なら: [正常] 予測への影響なし
   - 実際の勝率との差が大きい場合: 「当該シーズンの公式成績」を格納している可能性
     → 予測に使う場合は同期タイミングに注意

2. motor_second_rate（entries）
   - 充足率が70%未満の年度が多い場合: 現在max_score=0.0で無効化済みのため影響なし
   - 将来的に有効化を検討する場合は充足率改善が必要

3. local_win_rate / local_second_rate（entries）
   - 充足率が低い場合: 地元会場での会場相性スコア計算に影響
   - 現状のバックテストでは直接使用していなければ影響なし

4. st_time（race_details）
   - 異常値が0.5%以上ある場合: [注意] データ品質に懸念
   - 現在のスコアリングでst_timeを使用している場合は再確認が必要

5. オッズ（trifecta_odds）
   - <1.0のオッズが存在する場合: データ入力ミスの可能性が高い
   - バックテストのROI計算に直接影響するため要確認
""")


# -----------------------------------------------------------------------
# メイン
# -----------------------------------------------------------------------
def main():
    print("=" * 70)
    print("  統計指標の信頼性検証レポート")
    print(f"  DB: {DB_PATH}")
    print("=" * 70)

    if not os.path.exists(DB_PATH):
        print(f"[エラー] DBファイルが見つかりません: {DB_PATH}")
        sys.exit(1)

    check_racer_win_rate_accuracy()
    check_motor_second_rate()
    check_local_win_rate()
    check_anomalies()
    check_results_anomalies()
    print_summary()

    print()
    print("=" * 70)
    print("  検証完了")
    print("=" * 70)


if __name__ == "__main__":
    main()
