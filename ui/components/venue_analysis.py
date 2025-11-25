"""
会場分析UIコンポーネント

会場別の統計データを可視化
- ヒートマップ: 全会場のコース別勝率比較
- 会場特性サマリー
- 季節別パフォーマンス
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import sys
import os

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from src.analysis.venue_analyzer import VenueAnalyzer
from src.database.venue_data import VenueDataManager
from src.scraper.official_venue_scraper import OfficialVenueScraper


def fetch_venue_data_ui():
    """UIから会場データを取得する関数"""
    with st.spinner("公式サイトから会場データを取得中... (約1分かかります)"):
        try:
            # スクレイパー初期化
            scraper = OfficialVenueScraper(timeout=30)
            manager = VenueDataManager(DATABASE_PATH)

            # 全会場データ取得
            all_data = scraper.fetch_all_venues(delay=2.0)

            if all_data:
                # データベースに保存
                success_count = manager.save_all_venues(all_data)

                st.success(f"[OK] 会場データ取得完了: {len(all_data)}/24 会場取得、{success_count}件保存")

                # TOP5会場を表示
                sorted_venues = sorted(
                    all_data.values(),
                    key=lambda x: x.get('course_1_win_rate', 0),
                    reverse=True
                )

                st.markdown("**1コース勝率 TOP5**")
                for i, venue in enumerate(sorted_venues[:5], 1):
                    st.text(f"  {i}. {venue['venue_name']:8s} - {venue['course_1_win_rate']:.1f}%")

                # クリーンアップ
                scraper.close()

                # ページをリロードしてデータを反映
                st.rerun()
            else:
                st.error("[ERROR] データ取得に失敗しました")
                scraper.close()

        except Exception as e:
            st.error(f"[ERROR] エラーが発生しました: {e}")
            import traceback
            st.code(traceback.format_exc())


def render_venue_analysis_page():
    """会場分析ページのメイン表示"""
    st.header("🏟️ 会場データ分析")

    # タブ分割
    tab1, tab2, tab3 = st.tabs([
        "📊 全会場比較",
        "🎯 会場詳細分析",
        "🗺️ 会場マスタデータ"
    ])

    with tab1:
        render_all_venues_comparison()

    with tab2:
        render_venue_detail_analysis()

    with tab3:
        render_venue_master_data()


def render_all_venues_comparison():
    """全会場比較タブ"""
    st.subheader("📊 全会場のコース別勝率比較")

    analyzer = VenueAnalyzer(DATABASE_PATH)
    manager = VenueDataManager(DATABASE_PATH)

    # データ期間選択
    days_back = st.slider(
        "データ期間（過去N日）",
        min_value=30,
        max_value=365,
        value=90,
        step=30,
        key="venue_comparison_days"
    )

    # ヒートマップ作成
    with st.spinner("データ取得中..."):
        comparison_df = analyzer.get_venue_comparison(days_back=days_back)

    if comparison_df.empty:
        st.warning("データが不足しています。まずレース結果を収集してください。")
        return

    # ヒートマップ用データ整形
    heatmap_data = comparison_df.set_index('venue_name')[[
        'course_1_rate', 'course_2_rate', 'course_3_rate',
        'course_4_rate', 'course_5_rate', 'course_6_rate'
    ]]

    # カラム名を変更
    heatmap_data.columns = ['1コース', '2コース', '3コース', '4コース', '5コース', '6コース']

    # Plotlyヒートマップ作成
    fig = go.Figure(data=go.Heatmap(
        z=heatmap_data.values,
        x=heatmap_data.columns,
        y=heatmap_data.index,
        colorscale='RdYlGn',
        text=heatmap_data.values,
        texttemplate='%{text:.1f}%',
        textfont={"size": 10},
        colorbar=dict(title="勝率 (%)")
    ))

    fig.update_layout(
        title=f"全24会場のコース別1着率ヒートマップ（過去{days_back}日）",
        xaxis_title="コース",
        yaxis_title="会場",
        height=800,
        width=900
    )

    st.plotly_chart(fig, use_container_width=True)

    # TOP5 / BOTTOM5 表示
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 🏆 1コース勝率 TOP5")
        top5 = comparison_df.nlargest(5, 'course_1_rate')[['venue_name', 'course_1_rate']]
        for idx, row in top5.iterrows():
            st.metric(
                label=row['venue_name'],
                value=f"{row['course_1_rate']:.1f}%"
            )

    with col2:
        st.markdown("### 📉 1コース勝率 BOTTOM5")
        bottom5 = comparison_df.nsmallest(5, 'course_1_rate')[['venue_name', 'course_1_rate']]
        for idx, row in bottom5.iterrows():
            st.metric(
                label=row['venue_name'],
                value=f"{row['course_1_rate']:.1f}%"
            )


def render_venue_detail_analysis():
    """会場詳細分析タブ"""
    st.subheader("🎯 会場詳細分析")

    analyzer = VenueAnalyzer(DATABASE_PATH)
    manager = VenueDataManager(DATABASE_PATH)

    # 会場選択
    all_venues = manager.get_all_venues()
    if not all_venues:
        st.warning("会場データが登録されていません。")
        st.info("公式サイトから会場データを取得してください。")

        if st.button("🚀 今すぐ会場データを取得", type="primary", key="fetch_venue_data_detail"):
            fetch_venue_data_ui()

        st.markdown("---")
        st.markdown("**または、ターミナルから手動で実行:**")
        st.code("python fetch_venue_data.py")
        return

    venue_names = {v['venue_code']: v['venue_name'] for v in all_venues}
    selected_venue_name = st.selectbox(
        "会場を選択",
        options=list(venue_names.values()),
        key="venue_detail_select"
    )

    # 選択された会場コードを取得
    selected_venue_code = next(code for code, name in venue_names.items() if name == selected_venue_name)

    # 会場特性分析
    with st.spinner("分析中..."):
        characteristics = analyzer.analyze_venue_characteristics(selected_venue_code)
        venue_info = manager.get_venue_data(selected_venue_code)

    if not characteristics:
        st.error("分析データが取得できませんでした。")
        return

    # 会場基本情報
    st.markdown(f"## {characteristics['venue_name']} ボートレース場")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("水質", venue_info.get('water_type', '不明'))

    with col2:
        st.metric("干満差", venue_info.get('tidal_range', '不明'))

    with col3:
        st.metric("モーター", venue_info.get('motor_type', '不明'))

    with col4:
        st.metric("レコード", venue_info.get('record_time', '不明'))

    # 会場特性サマリー
    st.markdown("---")
    st.markdown("### 📋 会場特性")

    summary_col1, summary_col2 = st.columns(2)

    with summary_col1:
        st.markdown(f"**インコース有利**: {'✅ はい' if characteristics['is_inner_advantage'] else '❌ いいえ'}")
        st.markdown(f"**1コース支配度**: {characteristics['course_1_dominance']}")
        st.markdown(f"**1コース勝率**: {characteristics['course_1_win_rate']:.1f}%")

    with summary_col2:
        st.markdown(f"**決まり手多様性**: {characteristics['kimarite_diversity']:.2f}")
        st.markdown(f"**季節変動**: {characteristics['seasonal_variation']}")
        st.markdown(f"**レコード保持者**: {venue_info.get('record_holder', '不明')}")

    st.info(f"💡 {characteristics['characteristics_summary']}")

    # コース別勝率グラフ
    st.markdown("---")
    st.markdown("### 📊 コース別1着率")

    course_stats = analyzer.get_venue_course_stats(selected_venue_code, days_back=90)

    if not course_stats.empty:
        fig = go.Figure()

        fig.add_trace(go.Bar(
            x=[f"{i}コース" for i in range(1, 7)],
            y=[
                venue_info.get('course_1_win_rate', 0),
                venue_info.get('course_2_win_rate', 0),
                venue_info.get('course_3_win_rate', 0),
                venue_info.get('course_4_win_rate', 0),
                venue_info.get('course_5_win_rate', 0),
                venue_info.get('course_6_win_rate', 0)
            ],
            name="公式データ（最近3ヶ月平均）",
            marker_color='lightblue'
        ))

        # 実績データがあれば追加
        if not course_stats.empty:
            actual_rates = []
            for i in range(1, 7):
                course_data = course_stats[course_stats['course'] == i]
                if not course_data.empty:
                    actual_rates.append(course_data.iloc[0]['win_rate'])
                else:
                    actual_rates.append(0)

            fig.add_trace(go.Bar(
                x=[f"{i}コース" for i in range(1, 7)],
                y=actual_rates,
                name="実績データ（過去90日）",
                marker_color='orange'
            ))

        fig.update_layout(
            title="コース別1着率比較",
            xaxis_title="コース",
            yaxis_title="1着率 (%)",
            barmode='group',
            height=400
        )

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("実績データがまだありません。")

    # 決まり手パターン
    st.markdown("---")
    st.markdown("### 🎯 決まり手パターン（1コース）")

    kimarite = analyzer.get_venue_kimarite_pattern(selected_venue_code, days_back=90)

    if kimarite and '1' in kimarite:
        kimarite_1 = kimarite['1']

        # 円グラフ
        fig = go.Figure(data=[go.Pie(
            labels=list(kimarite_1.keys()),
            values=list(kimarite_1.values()),
            hole=0.3
        )])

        fig.update_layout(
            title="1コースの決まり手分布",
            height=400
        )

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("決まり手データがまだありません。")


def render_venue_master_data():
    """会場マスタデータタブ"""
    st.subheader("🗺️ 会場マスタデータ")

    manager = VenueDataManager(DATABASE_PATH)

    # データ件数表示
    count = manager.count_venues()
    st.metric("登録会場数", f"{count} / 24")

    if count == 0:
        st.warning("会場データが登録されていません。")
        st.info("公式サイトから会場データを取得してください。")

        if st.button("🚀 今すぐ会場データを取得", type="primary", key="fetch_venue_data_master"):
            fetch_venue_data_ui()

        st.markdown("---")
        st.markdown("**または、ターミナルから手動で実行:**")
        st.code("python fetch_venue_data.py")
        return

    # 全会場データ取得
    all_venues = manager.get_all_venues()

    # データフレーム作成
    df = pd.DataFrame(all_venues)

    # 表示カラム選択
    display_columns = [
        'venue_code', 'venue_name', 'water_type', 'tidal_range', 'motor_type',
        'course_1_win_rate', 'course_2_win_rate', 'course_3_win_rate',
        'record_time', 'record_holder', 'updated_at'
    ]

    display_df = df[display_columns].copy()

    # カラム名を日本語化
    display_df.columns = [
        '会場コード', '会場名', '水質', '干満差', 'モーター',
        '1コース勝率', '2コース勝率', '3コース勝率',
        'レコード', '記録保持者', '更新日時'
    ]

    # データテーブル表示
    st.dataframe(
        display_df,
        use_container_width=True,
        height=600
    )

    # CSV エクスポート
    csv = display_df.to_csv(index=False, encoding='utf-8-sig')
    st.download_button(
        label="📥 CSVダウンロード",
        data=csv,
        file_name="venue_master_data.csv",
        mime="text/csv"
    )

    # データ更新ボタン
    st.markdown("---")
    st.markdown("### 🔄 データ更新")

    if st.button("🚀 公式サイトから全会場データを再取得", type="primary", key="fetch_venue_data_refresh"):
        fetch_venue_data_ui()


if __name__ == "__main__":
    # Streamlit単体実行用（デバッグ）
    render_venue_analysis_page()
