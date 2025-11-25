"""
データ品質監視コンポーネント
"""
import streamlit as st
import sqlite3
import pandas as pd
from config.settings import DATABASE_PATH
from src.analysis.data_coverage_checker import DataCoverageChecker


def render_data_quality_monitor():
    """データ品質監視ダッシュボード"""
    st.header("📊 データ品質監視")

    try:
        checker = DataCoverageChecker(DATABASE_PATH)

        with st.spinner("データを分析中..."):
            report = checker.get_coverage_report()

        # 全体スコア
        overall_score = report["overall_score"]

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("全体充足率", f"{overall_score*100:.1f}%")

        with col2:
            st.metric("総レース数", f"{report['total_races']:,}")

        with col3:
            status = "優良" if overall_score >= 0.8 else "要改善" if overall_score >= 0.5 else "不足"
            st.metric("状態", status)

        # プログレスバー
        progress_value = min(max(overall_score, 0.0), 1.0)
        st.progress(progress_value)

        if overall_score >= 0.8:
            st.success("✅ データは充実しています。機械学習の準備ができています。")
        elif overall_score >= 0.5:
            st.warning("⚠️ データは中程度です。いくつかの重要項目が不足しています。")
        else:
            st.error("❌ データが不足しています。追加のデータ収集が必要です。")

        st.markdown("---")

        # カテゴリ別詳細
        st.subheader("📋 カテゴリ別データ充足率")

        categories = report["categories"]
        category_data = []

        for cat_name, cat_data in categories.items():
            category_data.append({
                "カテゴリ": cat_name,
                "充足率": f"{cat_data['score']*100:.1f}%",
                "スコア": cat_data['score']
            })

        df_categories = pd.DataFrame(category_data)
        df_categories = df_categories.sort_values("スコア", ascending=False)

        # グラフ表示
        import plotly.graph_objects as go

        fig = go.Figure(data=[
            go.Bar(
                x=df_categories['カテゴリ'],
                y=df_categories['スコア'] * 100,
                marker_color=['green' if s >= 0.8 else 'orange' if s >= 0.5 else 'red'
                            for s in df_categories['スコア']]
            )
        ])

        fig.update_layout(
            title="カテゴリ別充足率",
            xaxis_title="カテゴリ",
            yaxis_title="充足率 (%)",
            yaxis_range=[0, 100]
        )

        st.plotly_chart(fig, use_container_width=True)

        # 詳細テーブル
        st.dataframe(
            df_categories[["カテゴリ", "充足率"]],
            use_container_width=True,
            hide_index=True
        )

        st.markdown("---")

        # 不足項目
        st.subheader("⚠️ 不足しているデータ項目")

        missing_items = checker.get_missing_items()

        if missing_items:
            missing_data = []
            for item in missing_items[:15]:
                importance_stars = "★" * item["importance"]
                missing_data.append({
                    "カテゴリ": item["category"],
                    "項目": item["name"],
                    "重要度": importance_stars,
                    "状態": item["status"],
                    "充足率": f"{item['coverage']*100:.1f}%",
                    "備考": item["note"]
                })

            df_missing = pd.DataFrame(missing_data)
            st.dataframe(df_missing, use_container_width=True, hide_index=True)

            # 優先対応項目
            st.markdown("### 🎯 優先対応が必要な項目")
            high_priority = [item for item in missing_items if item["importance"] >= 4]

            if high_priority:
                for item in high_priority[:5]:
                    st.warning(
                        f"**{item['name']}** (重要度: ★{item['importance']}) - "
                        f"{item['status']} - {item['note']}"
                    )
            else:
                st.info("重要度の高い不足項目はありません")

        else:
            st.success("✅ 全てのデータ項目が充足しています！")

        st.markdown("---")

        # データ統計
        st.subheader("📈 データ統計")

        render_data_statistics()

    except Exception as e:
        st.error(f"エラーが発生しました: {e}")
        import traceback
        st.code(traceback.format_exc())


def render_data_statistics():
    """データ統計情報を表示"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        col1, col2, col3 = st.columns(3)

        with col1:
            cursor.execute("SELECT COUNT(*) FROM races")
            total_races = cursor.fetchone()[0]
            st.metric("総レース数", f"{total_races:,}")

        with col2:
            cursor.execute("SELECT COUNT(*) FROM entries")
            total_entries = cursor.fetchone()[0]
            st.metric("総出走表数", f"{total_entries:,}")

        with col3:
            cursor.execute("SELECT COUNT(*) FROM results")
            total_results = cursor.fetchone()[0]
            st.metric("総結果数", f"{total_results:,}")

        # データ期間
        st.markdown("### 📅 データ期間")
        cursor.execute("SELECT MIN(race_date), MAX(race_date) FROM races")
        min_date, max_date = cursor.fetchone()

        if min_date and max_date:
            col1, col2 = st.columns(2)
            with col1:
                st.info(f"最古データ: {min_date}")
            with col2:
                st.info(f"最新データ: {max_date}")

        # 会場別レース数
        st.markdown("### 🏟️ 会場別レース数")
        query = """
            SELECT venue_code, COUNT(*) as race_count
            FROM races
            GROUP BY venue_code
            ORDER BY race_count DESC
        """
        df_venue = pd.read_sql_query(query, conn)

        if not df_venue.empty:
            import plotly.express as px

            fig = px.bar(
                df_venue,
                x='venue_code',
                y='race_count',
                title='会場別レース数'
            )
            st.plotly_chart(fig, use_container_width=True)

        conn.close()

    except Exception as e:
        st.error(f"統計情報取得エラー: {e}")


def check_data_anomalies():
    """データの異常値をチェック"""
    st.subheader("🔍 異常値検出")

    try:
        conn = sqlite3.connect(DATABASE_PATH)

        # 異常なレース時間
        query = """
            SELECT race_date, venue_code, race_number
            FROM races
            WHERE race_time NOT LIKE '__:__'
            LIMIT 10
        """
        df_anomalies = pd.read_sql_query(query, conn)

        if not df_anomalies.empty:
            st.warning(f"⚠️ 異常なレース時間: {len(df_anomalies)}件")
            st.dataframe(df_anomalies, use_container_width=True, hide_index=True)
        else:
            st.success("✅ レース時間データに異常なし")

        conn.close()

    except Exception as e:
        st.error(f"異常値チェックエラー: {e}")
