"""
場攻略情報ページ - ボーターズ情報 + データ分析 + 検証
"""
import streamlit as st
import sqlite3
import pandas as pd
import sys
import os


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH


def get_venue_boaters_info(venue_code):
    """
    ボーターズサイトから抜き出した場攻略情報を取得

    Args:
        venue_code: 会場コード

    Returns:
        dict: 場攻略情報
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            name,
            water_type,
            course_tendency,
            kimarite_tendency,
            wind_tendency,
            tide_impact,
            special_notes
        FROM venue_strategies
        WHERE venue_code = ?
    """, (venue_code,))

    row = cursor.fetchone()

    if not row:
        conn.close()
        return None

    info = {
        'name': row[0],
        'water_type': row[1],
        'course_tendency': row[2],
        'kimarite_tendency': row[3],
        'wind_tendency': row[4],
        'tide_impact': row[5],
        'special_notes': row[6]
    }

    # 特徴を取得
    cursor.execute("""
        SELECT feature
        FROM venue_features
        WHERE venue_code = ?
        ORDER BY id
    """, (venue_code,))

    features = [row[0] for row in cursor.fetchall()]
    info['features'] = features

    conn.close()
    return info


def analyze_venue_stats(venue_code=None, days_back=90):
    """
    会場の統計データを分析

    Args:
        venue_code: 会場コード（Noneの場合は全国）
        days_back: 何日分のデータを使用するか

    Returns:
        dict: 分析結果
    """
    conn = sqlite3.connect(DATABASE_PATH)

    stats = {}

    # 1. コース別勝率分析（正しい計算方法）
    # SQLインジェクション対策: パラメータ化クエリを使用
    if venue_code:
        query = """
            SELECT
                SUM(CASE WHEN rd.actual_course = 1 THEN 1 ELSE 0 END) as course1_total,
                SUM(CASE WHEN res.rank = 1 AND rd.actual_course = 1 THEN 1 ELSE 0 END) as course1_win,
                SUM(CASE WHEN rd.actual_course = 2 THEN 1 ELSE 0 END) as course2_total,
                SUM(CASE WHEN res.rank = 1 AND rd.actual_course = 2 THEN 1 ELSE 0 END) as course2_win,
                SUM(CASE WHEN rd.actual_course = 3 THEN 1 ELSE 0 END) as course3_total,
                SUM(CASE WHEN res.rank = 1 AND rd.actual_course = 3 THEN 1 ELSE 0 END) as course3_win,
                SUM(CASE WHEN rd.actual_course = 4 THEN 1 ELSE 0 END) as course4_total,
                SUM(CASE WHEN res.rank = 1 AND rd.actual_course = 4 THEN 1 ELSE 0 END) as course4_win,
                SUM(CASE WHEN rd.actual_course = 5 THEN 1 ELSE 0 END) as course5_total,
                SUM(CASE WHEN res.rank = 1 AND rd.actual_course = 5 THEN 1 ELSE 0 END) as course5_win,
                SUM(CASE WHEN rd.actual_course = 6 THEN 1 ELSE 0 END) as course6_total,
                SUM(CASE WHEN res.rank = 1 AND rd.actual_course = 6 THEN 1 ELSE 0 END) as course6_win,
                SUM(CASE WHEN rd.actual_course IN (1,2,3) THEN 1 ELSE 0 END) as inside_total,
                SUM(CASE WHEN res.rank = 1 AND rd.actual_course IN (1,2,3) THEN 1 ELSE 0 END) as inside_win,
                COUNT(DISTINCT r.id) as total_races
            FROM races r
            INNER JOIN race_details rd ON r.id = rd.race_id
            INNER JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
            WHERE r.race_date >= date('now', '-' || ? || ' days')
            AND r.venue_code = ?
        """
        query_params = (days_back, venue_code)
    else:
        query = """
            SELECT
                SUM(CASE WHEN rd.actual_course = 1 THEN 1 ELSE 0 END) as course1_total,
                SUM(CASE WHEN res.rank = 1 AND rd.actual_course = 1 THEN 1 ELSE 0 END) as course1_win,
                SUM(CASE WHEN rd.actual_course = 2 THEN 1 ELSE 0 END) as course2_total,
                SUM(CASE WHEN res.rank = 1 AND rd.actual_course = 2 THEN 1 ELSE 0 END) as course2_win,
                SUM(CASE WHEN rd.actual_course = 3 THEN 1 ELSE 0 END) as course3_total,
                SUM(CASE WHEN res.rank = 1 AND rd.actual_course = 3 THEN 1 ELSE 0 END) as course3_win,
                SUM(CASE WHEN rd.actual_course = 4 THEN 1 ELSE 0 END) as course4_total,
                SUM(CASE WHEN res.rank = 1 AND rd.actual_course = 4 THEN 1 ELSE 0 END) as course4_win,
                SUM(CASE WHEN rd.actual_course = 5 THEN 1 ELSE 0 END) as course5_total,
                SUM(CASE WHEN res.rank = 1 AND rd.actual_course = 5 THEN 1 ELSE 0 END) as course5_win,
                SUM(CASE WHEN rd.actual_course = 6 THEN 1 ELSE 0 END) as course6_total,
                SUM(CASE WHEN res.rank = 1 AND rd.actual_course = 6 THEN 1 ELSE 0 END) as course6_win,
                SUM(CASE WHEN rd.actual_course IN (1,2,3) THEN 1 ELSE 0 END) as inside_total,
                SUM(CASE WHEN res.rank = 1 AND rd.actual_course IN (1,2,3) THEN 1 ELSE 0 END) as inside_win,
                COUNT(DISTINCT r.id) as total_races
            FROM races r
            INNER JOIN race_details rd ON r.id = rd.race_id
            INNER JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
            WHERE r.race_date >= date('now', '-' || ? || ' days')
        """
        query_params = (days_back,)

    df = pd.read_sql_query(query, conn, params=query_params)

    if len(df) > 0 and df.iloc[0]['total_races'] > 0:
        row = df.iloc[0]
        stats['course_win_rates'] = {
            1: (row['course1_win'] / row['course1_total'] * 100) if row['course1_total'] > 0 else 0,
            2: (row['course2_win'] / row['course2_total'] * 100) if row['course2_total'] > 0 else 0,
            3: (row['course3_win'] / row['course3_total'] * 100) if row['course3_total'] > 0 else 0,
            4: (row['course4_win'] / row['course4_total'] * 100) if row['course4_total'] > 0 else 0,
            5: (row['course5_win'] / row['course5_total'] * 100) if row['course5_total'] > 0 else 0,
            6: (row['course6_win'] / row['course6_total'] * 100) if row['course6_total'] > 0 else 0,
        }
        stats['inside_win_rate'] = (row['inside_win'] / row['inside_total'] * 100) if row['inside_total'] > 0 else 0
        stats['total_races'] = int(row['total_races'])

    # 2. 決まり手分析
    if venue_code:
        query = """
            SELECT
                rd.actual_course,
                res.kimarite,
                COUNT(*) as count
            FROM races r
            JOIN race_details rd ON r.id = rd.race_id
            LEFT JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
            WHERE r.race_date >= date('now', '-' || ? || ' days')
              AND res.rank = 1
              AND res.kimarite IS NOT NULL
              AND rd.actual_course IS NOT NULL
              AND r.venue_code = ?
            GROUP BY rd.actual_course, res.kimarite
            ORDER BY rd.actual_course, count DESC
        """
        kimarite_params = (days_back, venue_code)
    else:
        query = """
            SELECT
                rd.actual_course,
                res.kimarite,
                COUNT(*) as count
            FROM races r
            JOIN race_details rd ON r.id = rd.race_id
            LEFT JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
            WHERE r.race_date >= date('now', '-' || ? || ' days')
              AND res.rank = 1
              AND res.kimarite IS NOT NULL
              AND rd.actual_course IS NOT NULL
            GROUP BY rd.actual_course, res.kimarite
            ORDER BY rd.actual_course, count DESC
        """
        kimarite_params = (days_back,)

    df_kimarite = pd.read_sql_query(query, conn, params=kimarite_params)

    # コース別の決まり手トップ3
    stats['kimarite_by_course'] = {}
    for course in range(1, 7):
        course_data = df_kimarite[df_kimarite['actual_course'] == course]
        if len(course_data) > 0:
            stats['kimarite_by_course'][course] = course_data.head(3).to_dict('records')

    # 3. 時間帯別分析
    if venue_code:
        query = """
            SELECT
                CASE
                    WHEN CAST(substr(r.race_time, 1, 2) AS INTEGER) < 12 THEN '午前'
                    WHEN CAST(substr(r.race_time, 1, 2) AS INTEGER) < 15 THEN '午後前半'
                    ELSE '午後後半'
                END as time_zone,
                AVG(CASE WHEN res.rank = 1 AND rd.actual_course = 1 THEN 1.0 ELSE 0.0 END) as course1_win,
                COUNT(*) as race_count
            FROM races r
            JOIN race_details rd ON r.id = rd.race_id
            LEFT JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
            WHERE r.race_date >= date('now', '-' || ? || ' days')
              AND r.race_time IS NOT NULL
              AND r.venue_code = ?
            GROUP BY time_zone
            HAVING race_count >= 20
            ORDER BY course1_win DESC
        """
        time_params = (days_back, venue_code)
    else:
        query = """
            SELECT
                CASE
                    WHEN CAST(substr(r.race_time, 1, 2) AS INTEGER) < 12 THEN '午前'
                    WHEN CAST(substr(r.race_time, 1, 2) AS INTEGER) < 15 THEN '午後前半'
                    ELSE '午後後半'
                END as time_zone,
                AVG(CASE WHEN res.rank = 1 AND rd.actual_course = 1 THEN 1.0 ELSE 0.0 END) as course1_win,
                COUNT(*) as race_count
            FROM races r
            JOIN race_details rd ON r.id = rd.race_id
            LEFT JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
            WHERE r.race_date >= date('now', '-' || ? || ' days')
              AND r.race_time IS NOT NULL
            GROUP BY time_zone
            HAVING race_count >= 20
            ORDER BY course1_win DESC
        """
        time_params = (days_back,)

    df_time = pd.read_sql_query(query, conn, params=time_params)
    if len(df_time) > 0:
        stats['time_analysis'] = df_time.to_dict('records')

    conn.close()
    return stats


def render_boaters_info(boaters_info):
    """ボーターズ場攻略情報を表示"""

    # 基本情報
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("水質", boaters_info['water_type'] or "不明")

    with col2:
        tendency = boaters_info['course_tendency'] or "標準"
        st.metric("コース傾向", tendency)

    with col3:
        tide_text = "影響あり" if boaters_info['tide_impact'] else "影響なし"
        st.metric("潮位影響", tide_text)

    # 特徴
    if boaters_info['features']:
        st.markdown("**主な特徴**")
        for feature in boaters_info['features']:
            st.markdown(f"- {feature}")

    # 決まり手傾向
    if boaters_info['kimarite_tendency']:
        with st.expander("決まり手傾向"):
            st.text(boaters_info['kimarite_tendency'])

    # 風傾向
    if boaters_info['wind_tendency']:
        with st.expander("風の影響"):
            st.text(boaters_info['wind_tendency'])

    # 特記事項
    if boaters_info['special_notes']:
        st.info(f"💡 {boaters_info['special_notes']}")


def verify_boaters_claims(boaters_info, stats):
    """
    ボーターズ情報をデータで検証

    Args:
        boaters_info: ボーターズ情報
        stats: データ分析結果

    Returns:
        list: 検証結果
    """
    verifications = []

    if not stats or 'course_win_rates' not in stats:
        return verifications

    course1_rate = stats['course_win_rates'].get(1, 0)
    course_tendency = boaters_info.get('course_tendency', '')

    # コース傾向の検証
    if course_tendency:
        if 'イン有利' in course_tendency or 'イン絶対' in course_tendency:
            if course1_rate >= 55:
                verifications.append({
                    'claim': f'コース傾向: {course_tendency}',
                    'verified': True,
                    'data': f'1コース勝率 {course1_rate:.1f}% (全国平均約53%)',
                    'conclusion': '✅ データでも確認: イン有利'
                })
            elif course1_rate >= 50:
                verifications.append({
                    'claim': f'コース傾向: {course_tendency}',
                    'verified': True,
                    'data': f'1コース勝率 {course1_rate:.1f}% (全国平均約53%)',
                    'conclusion': '⚠️ やや有利程度（想定より低い）'
                })
            else:
                verifications.append({
                    'claim': f'コース傾向: {course_tendency}',
                    'verified': False,
                    'data': f'1コース勝率 {course1_rate:.1f}% (全国平均約53%)',
                    'conclusion': '❌ データと不一致: インは弱い'
                })

        elif 'ダッシュ有利' in course_tendency or 'センター有利' in course_tendency:
            outer_rate = sum(stats['course_win_rates'].get(c, 0) for c in [3, 4, 5, 6])
            if outer_rate >= 50:
                verifications.append({
                    'claim': f'コース傾向: {course_tendency}',
                    'verified': True,
                    'data': f'3-6コース勝率合計 {outer_rate:.1f}%',
                    'conclusion': '✅ データでも確認: センター・アウト有利'
                })
            else:
                verifications.append({
                    'claim': f'コース傾向: {course_tendency}',
                    'verified': False,
                    'data': f'3-6コース勝率合計 {outer_rate:.1f}%',
                    'conclusion': '⚠️ データでは顕著ではない'
                })

    # 決まり手傾向の検証
    kimarite_tendency = boaters_info.get('kimarite_tendency', '')
    if kimarite_tendency and 'kimarite_by_course' in stats:
        # 1コースの決まり手を確認
        if 1 in stats['kimarite_by_course']:
            course1_kimarite = stats['kimarite_by_course'][1]
            if course1_kimarite:
                top_kimarite = course1_kimarite[0]['kimarite']
                total = sum(k['count'] for k in course1_kimarite)
                percentage = course1_kimarite[0]['count'] / total * 100 if total > 0 else 0

                # 逃げが多いと主張されている場合
                if '逃げ' in kimarite_tendency:
                    if top_kimarite == '逃げ' and percentage >= 80:
                        verifications.append({
                            'claim': '決まり手傾向: 逃げが多い',
                            'verified': True,
                            'data': f'1コース1着時: 逃げ {percentage:.1f}%',
                            'conclusion': '✅ データでも確認'
                        })

    return verifications


def render_venue_strategy_page():
    """場攻略ページのレンダリング - ボーターズ情報 + データ分析 + 検証"""
    st.header("🏟️ 場攻略情報")
    st.markdown("**ボーターズ情報 × データ分析 × 検証結果**")

    # 会場選択
    conn = sqlite3.connect(DATABASE_PATH)
    df_venues = pd.read_sql_query("SELECT code, name FROM venues ORDER BY code", conn)
    conn.close()

    # 各会場のみ（全国平均なし）
    venue_options = [f"{row['code']}: {row['name']}" for _, row in df_venues.iterrows()]

    selected_venue = st.selectbox(
        "会場を選択",
        venue_options,
        key="venue_strategy_selector"
    )

    # 分析期間
    col1, col2 = st.columns([3, 1])
    with col1:
        days_back = st.slider(
            "分析期間（過去N日間）",
            min_value=30,
            max_value=180,
            value=90,
            step=30,
            key="venue_strategy_days"
        )

    with col2:
        if st.button("🔄 分析実行", type="primary", use_container_width=True):
            st.rerun()

    # 会場コードを抽出
    venue_code = selected_venue.split(":")[0].strip()

    # ボーターズ情報取得
    boaters_info = get_venue_boaters_info(venue_code)

    # データ分析実行
    with st.spinner("データ分析中..."):
        stats = analyze_venue_stats(venue_code, days_back)

    if not stats or 'course_win_rates' not in stats:
        st.warning("データが不足しています。過去データを収集してください。")
        # ボーターズ情報だけでも表示
        if boaters_info:
            st.markdown("---")
            st.subheader("📚 ボーターズ場攻略情報")
            render_boaters_info(boaters_info)
        return

    # ボーターズ情報セクション
    if boaters_info:
        st.markdown("---")
        st.subheader("📚 ボーターズ場攻略情報")
        render_boaters_info(boaters_info)

    # データ分析結果
    st.markdown("---")

    # 基本情報
    st.subheader("📊 基本統計")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("分析対象レース数", f"{stats.get('total_races', 0):,}")

    with col2:
        course1_rate = stats['course_win_rates'].get(1, 0)
        trend = "🔥" if course1_rate > 55 else "⚠️" if course1_rate < 45 else "📊"
        st.metric(f"{trend} 1コース勝率", f"{course1_rate:.1f}%")

    with col3:
        inside_rate = stats.get('inside_win_rate', 0)
        st.metric("インコース(1-3)勝率", f"{inside_rate:.1f}%")

    # コース別勝率
    st.subheader("🎯 コース別勝率")

    course_data = []
    for course in range(1, 7):
        rate = stats['course_win_rates'].get(course, 0)
        course_data.append({
            'コース': f"{course}コース",
            '勝率': f"{rate:.1f}%",
            '勝率(数値)': rate
        })

    df_courses = pd.DataFrame(course_data)

    # 横棒グラフ
    st.bar_chart(df_courses.set_index('コース')['勝率(数値)'])

    # テーブル表示
    st.dataframe(
        df_courses[['コース', '勝率']],
        use_container_width=True,
        hide_index=True
    )

    # 決まり手分析
    if 'kimarite_by_course' in stats and stats['kimarite_by_course']:
        st.subheader("⚡ コース別決まり手")

        cols = st.columns(3)

        for idx, course in enumerate([1, 2, 3, 4, 5, 6]):
            col = cols[idx % 3]

            with col:
                st.markdown(f"**{course}コース**")

                if course in stats['kimarite_by_course']:
                    kimarite_list = stats['kimarite_by_course'][course]
                    total = sum(k['count'] for k in kimarite_list)

                    for k in kimarite_list[:3]:  # トップ3
                        percentage = k['count'] / total * 100 if total > 0 else 0
                        st.text(f"{k['kimarite']}: {percentage:.1f}%")
                else:
                    st.text("データなし")

    # 時間帯別分析
    if 'time_analysis' in stats and stats['time_analysis']:
        st.subheader("⏰ 時間帯別傾向")

        time_data = stats['time_analysis']

        if len(time_data) >= 2:
            best_time = time_data[0]
            worst_time = time_data[-1]
            diff = (best_time['course1_win'] - worst_time['course1_win']) * 100

            for t in time_data:
                col1, col2, col3 = st.columns([2, 2, 1])

                with col1:
                    st.text(t['time_zone'])

                with col2:
                    st.text(f"1コース勝率: {t['course1_win']*100:.1f}%")

                with col3:
                    st.text(f"({t['race_count']}R)")

            if diff > 5:
                st.info(f"💡 時間帯による差が大きい: {diff:.1f}ポイント")

    # ボーターズ情報検証
    if boaters_info:
        st.markdown("---")
        st.subheader("🔍 ボーターズ情報の検証")

        verifications = verify_boaters_claims(boaters_info, stats)

        if verifications:
            for v in verifications:
                with st.container():
                    col1, col2 = st.columns([1, 2])

                    with col1:
                        st.markdown(f"**{v['claim']}**")

                    with col2:
                        st.markdown(f"{v['conclusion']}")
                        st.caption(f"実データ: {v['data']}")

                    st.markdown("")
        else:
            st.info("データ量が不足しているため、検証できません")

    # 攻略ポイント（ボーターズ情報 + データ分析の総合）
    st.markdown("---")
    st.subheader("💡 総合攻略ポイント")

    recommendations = []

    course1_rate = stats['course_win_rates'].get(1, 0)

    # データ分析からの推奨
    if course1_rate > 55:
        recommendations.append("✅ 1コースが超強い場（固い展開を好む）")
    elif course1_rate > 50:
        recommendations.append("✅ 1コースが強い場（イン有利）")
    elif course1_rate < 45:
        recommendations.append("⚠️ 荒れる場（センター・アウトにもチャンス）")

    # アウト勝率
    outer_rate = sum(stats['course_win_rates'].get(c, 0) for c in [4, 5, 6])
    if outer_rate > 20:
        recommendations.append(f"💰 アウトコースも活躍（4-6コース合計 {outer_rate:.1f}%）")

    # 時間帯
    if 'time_analysis' in stats and len(stats.get('time_analysis', [])) >= 2:
        time_data = stats['time_analysis']
        best_time = time_data[0]
        worst_time = time_data[-1]
        diff = (best_time['course1_win'] - worst_time['course1_win']) * 100

        if diff > 5:
            recommendations.append(f"⏰ {best_time['time_zone']}が最もイン有利（+{diff:.1f}%）")

    # ボーターズ情報からの追加推奨
    if boaters_info:
        # 水質
        if boaters_info['water_type'] == '淡水':
            recommendations.append("🌊 淡水場（モーター性能・体重差が影響大）")
        elif boaters_info['water_type'] == '海水':
            recommendations.append("🌊 海水場（潮位・うねりに注意）")

        # 潮位影響
        if boaters_info['tide_impact']:
            recommendations.append("🌊 潮位の影響あり（満潮時・干潮時で傾向が変わる）")

        # 特記事項
        if boaters_info['special_notes']:
            recommendations.append(f"📝 {boaters_info['special_notes']}")

    if recommendations:
        for rec in recommendations:
            st.markdown(f"- {rec}")
    else:
        st.info("標準的な会場（特筆すべき傾向なし）")

    # データソース情報
    st.markdown("---")
    data_sources = [f"収集済みレースデータ（過去{days_back}日間）"]
    if boaters_info:
        data_sources.append("ボーターズ場攻略情報")

    st.caption(f"📊 データソース: {' + '.join(data_sources)}")
