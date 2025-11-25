"""
データ排出機能 - 外部解析用のデータエクスポート
"""
import streamlit as st
import sqlite3
import pandas as pd
import io
from datetime import datetime
import os
import sys


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH


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
