"""
データ排出機能 - 外部解析用のデータエクスポート
"""
import streamlit as st
import sqlite3
import pandas as pd
import io
from datetime import datetime, timedelta
import os
import sys


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

# 決まり手の名称マッピング
KIMARITE_NAMES = {
    1: "逃げ",
    2: "差し",
    3: "まくり",
    4: "まくり差し",
    5: "抜き",
    6: "恵まれ"
}


def render_data_export_page():
    """データ排出ページのレンダリング"""
    st.header("📊 データ排出")
    st.markdown("収集したレースデータを外部解析用にエクスポート")

    conn = sqlite3.connect(DATABASE_PATH)

    # エクスポート条件設定
    st.subheader("🔧 エクスポート条件")

    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input(
            "開始日",
            value=datetime(2024, 1, 1),
            key="data_export_start_date"
        )
    with col2:
        end_date = st.date_input(
            "終了日",
            value=datetime.now(),
            key="data_export_end_date"
        )

    # データテーブル選択
    st.subheader("📋 エクスポートするテーブル")

    export_options = {
        "レース基本情報 (races)": "races",
        "レース詳細 (race_details)": "race_details",
        "結果 (results)": "results",
        "選手情報 (racers)": "racers",
        "天候データ (weather)": "weather",
        "潮位データ (tide)": "tide",
        "会場情報 (venues)": "venues"
    }

    selected_tables = st.multiselect(
        "エクスポートするテーブルを選択",
        options=list(export_options.keys()),
        default=["レース基本情報 (races)", "レース詳細 (race_details)", "結果 (results)"]
    )

    if not selected_tables:
        st.warning("エクスポートするテーブルを選択してください")
        conn.close()
        return

    # プレビュー表示
    st.subheader("🔍 データプレビュー")

    for table_label in selected_tables:
        table_name = export_options[table_label]

        with st.expander(f"{table_label} - サンプル"):
            try:
                # レースデータの場合は日付でフィルター
                if table_name in ['races', 'race_details', 'results', 'weather']:
                    if table_name == 'races':
                        query = f"""
                            SELECT * FROM {table_name}
                            WHERE race_date BETWEEN ? AND ?
                            LIMIT 100
                        """
                    elif table_name in ['race_details', 'results']:
                        query = f"""
                            SELECT t.* FROM {table_name} t
                            JOIN races r ON t.race_id = r.id
                            WHERE r.race_date BETWEEN ? AND ?
                            LIMIT 100
                        """
                    elif table_name == 'weather':
                        query = f"""
                            SELECT * FROM {table_name}
                            WHERE weather_date BETWEEN ? AND ?
                            LIMIT 100
                        """
                    df = pd.read_sql_query(query, conn, params=(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')))
                else:
                    # 会場、選手、潮位は全データ
                    df = pd.read_sql_query(f"SELECT * FROM {table_name} LIMIT 100", conn)

                st.dataframe(df, use_container_width=True)
                st.caption(f"表示: 最初の{len(df)}行（実際のエクスポートでは全データ）")
            except Exception as e:
                st.error(f"エラー: {e}")

    # エクスポート実行
    st.subheader("📤 エクスポート実行")

    col1, col2 = st.columns(2)

    with col1:
        export_format = st.radio(
            "フォーマット",
            ["CSV", "Excel", "JSON"],
            horizontal=True
        )

    with col2:
        if st.button("📥 エクスポート実行", type="primary", use_container_width=True):
            with st.spinner("エクスポート中..."):
                try:
                    # 各テーブルをエクスポート
                    export_data = {}

                    for table_label in selected_tables:
                        table_name = export_options[table_label]

                        # フルデータ取得
                        if table_name in ['races', 'race_details', 'results', 'weather']:
                            if table_name == 'races':
                                query = f"""
                                    SELECT * FROM {table_name}
                                    WHERE race_date BETWEEN ? AND ?
                                """
                            elif table_name in ['race_details', 'results']:
                                query = f"""
                                    SELECT t.* FROM {table_name} t
                                    JOIN races r ON t.race_id = r.id
                                    WHERE r.race_date BETWEEN ? AND ?
                                """
                            elif table_name == 'weather':
                                query = f"""
                                    SELECT * FROM {table_name}
                                    WHERE weather_date BETWEEN ? AND ?
                                """
                            df = pd.read_sql_query(query, conn, params=(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')))
                        else:
                            df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)

                        export_data[table_name] = df

                    # フォーマットに応じてエクスポート
                    if export_format == "CSV":
                        # 複数CSVをZIPでまとめる
                        import zipfile
                        zip_buffer = io.BytesIO()
                        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                            for table_name, df in export_data.items():
                                csv_buffer = io.StringIO()
                                df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
                                zip_file.writestr(f"{table_name}.csv", csv_buffer.getvalue())

                        zip_buffer.seek(0)
                        st.download_button(
                            label="💾 CSVファイルをダウンロード (ZIP)",
                            data=zip_buffer,
                            file_name=f"boatrace_data_{start_date}_{end_date}.zip",
                            mime="application/zip"
                        )

                    elif export_format == "Excel":
                        # Excelファイル（複数シート）
                        excel_buffer = io.BytesIO()
                        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                            for table_name, df in export_data.items():
                                df.to_excel(writer, sheet_name=table_name[:31], index=False)  # シート名は31文字まで

                        excel_buffer.seek(0)
                        st.download_button(
                            label="💾 Excelファイルをダウンロード",
                            data=excel_buffer,
                            file_name=f"boatrace_data_{start_date}_{end_date}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )

                    elif export_format == "JSON":
                        # JSON形式
                        json_data = {table_name: df.to_dict(orient='records') for table_name, df in export_data.items()}
                        import json
                        json_str = json.dumps(json_data, ensure_ascii=False, indent=2)

                        st.download_button(
                            label="💾 JSONファイルをダウンロード",
                            data=json_str,
                            file_name=f"boatrace_data_{start_date}_{end_date}.json",
                            mime="application/json"
                        )

                    st.success(f"✅ エクスポート完了！ ({len(export_data)}テーブル)")

                    # 統計表示
                    total_rows = sum(len(df) for df in export_data.values())
                    st.info(f"総レコード数: {total_rows:,}行")

                except Exception as e:
                    st.error(f"❌ エクスポート失敗: {e}")

    conn.close()


def render_ai_analysis_export():
    """AI解析用統合CSVエクスポート機能"""
    st.header("🤖 AI解析用データエクスポート")
    st.markdown("法則性発見のために、全データを統合した1つのCSVファイルを生成します")

    conn = sqlite3.connect(DATABASE_PATH)

    # データ期間の取得
    cursor = conn.cursor()
    cursor.execute("SELECT MIN(race_date), MAX(race_date) FROM races")
    min_date_str, max_date_str = cursor.fetchone()

    if not min_date_str or not max_date_str:
        st.warning("データベースにレースデータが存在しません")
        conn.close()
        return

    # 日付フォーマットを自動判定
    if '-' in min_date_str:
        # YYYY-MM-DD形式
        min_date = datetime.strptime(min_date_str, '%Y-%m-%d').date()
        max_date = datetime.strptime(max_date_str, '%Y-%m-%d').date()
        date_format = '%Y-%m-%d'
    else:
        # YYYYMMDD形式
        min_date = datetime.strptime(min_date_str, '%Y%m%d').date()
        max_date = datetime.strptime(max_date_str, '%Y%m%d').date()
        date_format = '%Y%m%d'

    st.info(f"📅 保有データ期間: {min_date} ~ {max_date}")

    # 期間選択
    st.subheader("📆 エクスポート期間")

    col1, col2 = st.columns(2)

    with col1:
        period_preset = st.selectbox(
            "期間プリセット",
            ["カスタム", "最新1ヶ月", "最新2ヶ月", "最新3ヶ月", "最新6ヶ月", "最新1年", "最新2年", "全期間"],
            index=2,  # デフォルトは「最新2ヶ月」
            key="ai_export_preset"
        )

    # プリセットに応じて日付を計算
    if period_preset == "最新1ヶ月":
        start_date = max_date - timedelta(days=30)
        end_date = max_date
    elif period_preset == "最新2ヶ月":
        start_date = max_date - timedelta(days=60)
        end_date = max_date
    elif period_preset == "最新3ヶ月":
        start_date = max_date - timedelta(days=90)
        end_date = max_date
    elif period_preset == "最新6ヶ月":
        start_date = max_date - timedelta(days=180)
        end_date = max_date
    elif period_preset == "最新1年":
        start_date = max_date - timedelta(days=365)
        end_date = max_date
    elif period_preset == "最新2年":
        start_date = max_date - timedelta(days=730)
        end_date = max_date
    elif period_preset == "全期間":
        start_date = min_date
        end_date = max_date
    else:  # カスタム
        start_date = min_date
        end_date = max_date

    with col2:
        if period_preset == "カスタム":
            col2_1, col2_2 = st.columns(2)
            with col2_1:
                start_date = st.date_input(
                    "開始日",
                    value=start_date,
                    min_value=min_date,
                    max_value=max_date,
                    key="ai_export_start"
                )
            with col2_2:
                end_date = st.date_input(
                    "終了日",
                    value=end_date,
                    min_value=min_date,
                    max_value=max_date,
                    key="ai_export_end"
                )
        else:
            st.info(f"期間: {start_date} ~ {end_date}")

    # データサイズの推定
    st.subheader("📊 データサイズ推定")

    start_date_str = start_date.strftime(date_format)
    end_date_str = end_date.strftime(date_format)

    # レコード数の取得
    query_count = """
        SELECT COUNT(*)
        FROM races r
        JOIN entries e ON r.id = e.race_id
        WHERE r.race_date BETWEEN ? AND ?
    """
    cursor.execute(query_count, (start_date_str, end_date_str))
    total_records = cursor.fetchone()[0]

    # CSVサイズの推定（1レコード約500バイトと仮定）
    estimated_size_bytes = total_records * 500
    estimated_size_mb = estimated_size_bytes / (1024 * 1024)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("推定レコード数", f"{total_records:,}行")
    with col2:
        st.metric("推定ファイルサイズ", f"{estimated_size_mb:.2f} MB")
    with col3:
        if estimated_size_mb > 10:
            st.error("⚠️ 10MBを超えています")
        else:
            st.success("✅ 10MB以内")

    if estimated_size_mb > 10:
        st.warning(f"⚠️ ファイルサイズが{estimated_size_mb:.2f}MBと大きいです。期間を短縮することをお勧めします。")

    # 含まれるデータ項目の説明
    with st.expander("📋 含まれるデータ項目", expanded=False):
        st.markdown("""
        **レース基本情報:**
        - レースID、開催日、会場コード、会場名、レース番号、発走時刻

        **選手情報:**
        - ピット番号、選手登録番号、選手名、級別、全国勝率、全国2連対率

        **機材情報:**
        - モーター番号、モーター2連対率、ボート番号、展示タイム、チルト角

        **レース詳細:**
        - 実進入コース、スタートタイミング(ST)

        **環境情報:**
        - 気温、天候、風速、風向、波高、水温

        **結果情報:**
        - 着順、決まり手(番号)、決まり手(名称)、オッズ
        """)

    # エクスポート実行
    st.subheader("📤 エクスポート実行")

    if st.button("🤖 AI解析用CSVをエクスポート", type="primary", use_container_width=True):
        if total_records == 0:
            st.error("指定期間にデータが存在しません")
            conn.close()
            return

        with st.spinner(f"データを統合中... ({total_records:,}レコード)"):
            try:
                # 統合クエリの実行
                query = """
                    SELECT
                        r.id as race_id,
                        r.race_date,
                        r.venue_code,
                        v.name as venue_name,
                        r.race_number,
                        r.race_time,

                        e.pit_number,
                        e.racer_number,
                        e.racer_name,
                        e.racer_rank as racer_class,
                        e.win_rate,
                        e.second_rate,

                        e.motor_number,
                        e.motor_second_rate as motor_2tan_rate,
                        e.boat_number,
                        rd.exhibition_time,
                        rd.actual_course,
                        rd.st_time,
                        rd.tilt_angle,

                        w.temperature,
                        w.weather_condition,
                        w.wind_speed,
                        w.wind_direction,
                        w.wave_height,
                        w.water_temperature,

                        res.rank,
                        res.winning_technique as kimarite,
                        res.trifecta_odds as odds

                    FROM races r
                    LEFT JOIN venues v ON r.venue_code = v.code
                    LEFT JOIN entries e ON r.id = e.race_id
                    LEFT JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
                    LEFT JOIN weather w ON r.venue_code = w.venue_code AND r.race_date = w.weather_date
                    LEFT JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number

                    WHERE r.race_date BETWEEN ? AND ?
                    ORDER BY r.race_date, r.venue_code, r.race_number, e.pit_number
                """

                df = pd.read_sql_query(query, conn, params=(start_date_str, end_date_str))

                # 決まり手の名称を追加
                df['kimarite_name'] = df['kimarite'].map(KIMARITE_NAMES)

                # 列の順序を整理
                columns_order = [
                    'race_id', 'race_date', 'venue_code', 'venue_name', 'race_number', 'race_time',
                    'pit_number', 'racer_number', 'racer_name', 'racer_class', 'win_rate', 'second_rate',
                    'motor_number', 'motor_2tan_rate', 'boat_number', 'exhibition_time', 'actual_course', 'st_time', 'tilt_angle',
                    'temperature', 'weather_condition', 'wind_speed', 'wind_direction', 'wave_height', 'water_temperature',
                    'rank', 'kimarite', 'kimarite_name', 'odds'
                ]
                df = df[columns_order]

                # CSVに変換
                csv_buffer = io.StringIO()
                df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
                csv_data = csv_buffer.getvalue()

                # 実際のサイズを計算
                actual_size_mb = len(csv_data.encode('utf-8')) / (1024 * 1024)

                st.success(f"✅ エクスポート完了！ ({len(df):,}行, {actual_size_mb:.2f} MB)")

                # ダウンロードボタン
                filename_start = start_date.strftime('%Y%m%d')
                filename_end = end_date.strftime('%Y%m%d')
                st.download_button(
                    label="💾 CSVファイルをダウンロード",
                    data=csv_data,
                    file_name=f"boatrace_ai_analysis_{filename_start}_{filename_end}.csv",
                    mime="text/csv"
                )

                # プレビュー表示
                st.subheader("🔍 データプレビュー（最初の100行）")
                st.dataframe(df.head(100), use_container_width=True)

                # 統計情報
                st.subheader("📈 統計情報")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    unique_races = df['race_id'].nunique()
                    st.metric("ユニークレース数", f"{unique_races:,}")
                with col2:
                    unique_venues = df['venue_code'].nunique()
                    st.metric("会場数", f"{unique_venues}")
                with col3:
                    unique_racers = df['racer_number'].nunique()
                    st.metric("選手数", f"{unique_racers:,}")
                with col4:
                    results_count = df['rank'].notna().sum()
                    st.metric("結果データ", f"{results_count:,}")

            except Exception as e:
                st.error(f"❌ エクスポート失敗: {e}")
                import traceback
                st.code(traceback.format_exc())

    conn.close()


def render_past_races_summary():
    """過去レースまとめページ"""
    st.header("📊 過去レースデータまとめ")

    conn = sqlite3.connect(DATABASE_PATH)

    # 統計情報
    st.subheader("📈 データ統計")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM races")
        race_count = cursor.fetchone()[0]
        st.metric("総レース数", f"{race_count:,}")

    with col2:
        cursor.execute("SELECT COUNT(DISTINCT race_date) FROM races")
        date_count = cursor.fetchone()[0]
        st.metric("収集日数", f"{date_count:,}日")

    with col3:
        cursor.execute("SELECT COUNT(DISTINCT racer_number) FROM entries WHERE racer_number IS NOT NULL")
        racer_count = cursor.fetchone()[0]
        st.metric("選手数", f"{racer_count:,}")

    with col4:
        cursor.execute("SELECT COUNT(*) FROM results WHERE rank = 1")
        result_count = cursor.fetchone()[0]
        st.metric("結果データ", f"{result_count:,}")

    # 期間情報
    st.subheader("📅 データ期間")
    cursor.execute("SELECT MIN(race_date), MAX(race_date) FROM races")
    min_date, max_date = cursor.fetchone()

    if min_date and max_date:
        col1, col2 = st.columns(2)
        with col1:
            st.info(f"最古: {min_date}")
        with col2:
            st.info(f"最新: {max_date}")

    # 会場別データ数
    st.subheader("🏟️ 会場別レース数")
    query = """
        SELECT v.name, COUNT(r.id) as race_count
        FROM venues v
        LEFT JOIN races r ON v.code = r.venue_code
        GROUP BY v.code, v.name
        ORDER BY race_count DESC
    """
    df_venues = pd.read_sql_query(query, conn)
    st.dataframe(df_venues, use_container_width=True)

    # オリジナル展示データの充足率
    st.subheader("🎯 オリジナル展示データ充足率")
    query = """
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN chikusen_time IS NOT NULL THEN 1 END) as with_chikusen,
            COUNT(CASE WHEN isshu_time IS NOT NULL THEN 1 END) as with_isshu,
            COUNT(CASE WHEN mawariashi_time IS NOT NULL THEN 1 END) as with_mawariashi
        FROM race_details
    """
    cursor.execute(query)
    total, chikusen, isshu, mawariashi = cursor.fetchone()

    if total > 0:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("直線タイム", f"{chikusen/total*100:.1f}%", f"{chikusen:,}/{total:,}")
        with col2:
            st.metric("1周タイム", f"{isshu/total*100:.1f}%", f"{isshu:,}/{total:,}")
        with col3:
            st.metric("回り足タイム", f"{mawariashi/total*100:.1f}%", f"{mawariashi:,}/{total:,}")

    conn.close()
