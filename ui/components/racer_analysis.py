"""
選手分析UIコンポーネント

選手一覧 → 選手詳細（クリックで遷移）
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import sqlite3
import sys
import os

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from src.analysis.racer_analyzer import RacerAnalyzer


def render_racer_analysis_page():
    """選手分析ページのメイン表示"""
    st.header("👤 選手データ分析")

    # セッション状態で選手選択を管理
    if 'selected_racer' not in st.session_state:
        st.session_state.selected_racer = None

    # 戻るボタン（選手詳細表示時）
    if st.session_state.selected_racer:
        if st.button("← 選手一覧に戻る", key="back_to_list"):
            st.session_state.selected_racer = None
            st.rerun()
        render_racer_detail_view(st.session_state.selected_racer)
    else:
        render_racer_list()


def render_racer_list():
    """選手一覧表示"""
    st.subheader("📋 選手一覧")

    # 検索フィルター
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        search_number = st.text_input("選手番号で検索", placeholder="例: 4444", key="racer_search_number")
    with col2:
        search_name = st.text_input("選手名で検索", placeholder="例: 山田", key="racer_search_name")
    with col3:
        days_back = st.selectbox("期間", [30, 90, 180, 365], index=2, format_func=lambda x: f"過去{x}日", key="racer_list_days")

    # 選手データ取得
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        # 最近のレースに出走した選手を取得
        query = """
            SELECT
                e.racer_number,
                MAX(e.racer_name) as racer_name,
                COUNT(*) as race_count,
                SUM(CASE WHEN r2.rank = '1' THEN 1 ELSE 0 END) as wins,
                AVG(CAST(r2.rank AS FLOAT)) as avg_rank
            FROM entries e
            JOIN races r ON e.race_id = r.id
            LEFT JOIN results r2 ON e.race_id = r2.race_id AND e.pit_number = r2.pit_number
            WHERE r.race_date >= date('now', ?)
              AND r2.rank IS NOT NULL
              AND CAST(r2.rank AS INTEGER) BETWEEN 1 AND 6
        """
        params = [f'-{days_back} days']

        if search_number:
            query += " AND CAST(e.racer_number AS TEXT) LIKE ?"
            params.append(f"%{search_number}%")
        if search_name:
            query += " AND e.racer_name LIKE ?"
            params.append(f"%{search_name}%")

        query += """
            GROUP BY e.racer_number
            HAVING race_count >= 5
            ORDER BY race_count DESC
            LIMIT 100
        """

        cursor.execute(query, params)
        racers = cursor.fetchall()
        conn.close()

        if not racers:
            st.info("該当する選手がいません。検索条件を変更してください。")
            return

        # 選手一覧を表示
        st.markdown(f"**{len(racers)}名の選手**（レース数5戦以上）")

        # カード形式で表示
        for i in range(0, len(racers), 3):
            cols = st.columns(3)
            for j, col in enumerate(cols):
                if i + j < len(racers):
                    racer = racers[i + j]
                    racer_number, racer_name, race_count, wins, avg_rank = racer
                    win_rate = (wins / race_count * 100) if race_count > 0 else 0

                    with col:
                        # クリック可能なカード
                        if st.button(
                            f"**{racer_name}** ({racer_number})\n{race_count}戦 {wins}勝 勝率{win_rate:.1f}%",
                            key=f"racer_{racer_number}",
                            use_container_width=True
                        ):
                            st.session_state.selected_racer = racer_number
                            st.rerun()

    except Exception as e:
        st.error(f"データ取得エラー: {e}")


def render_racer_detail_view(racer_number):
    """選手詳細ビュー"""
    analyzer = RacerAnalyzer(DATABASE_PATH)

    # データ期間選択
    days_back = st.slider(
        "分析期間（過去N日）",
        min_value=30,
        max_value=730,
        value=365,
        step=30,
        key="racer_detail_days"
    )

    # 全体成績取得
    with st.spinner("データ取得中..."):
        overall_stats = analyzer.get_racer_overall_stats(racer_number, days=days_back)
        venue_stats = analyzer.get_racer_all_venues_stats(racer_number, days=days_back)
        recent_trend = analyzer.get_racer_recent_trend(racer_number, recent_n=10)

    if overall_stats['total_races'] == 0:
        st.warning(f"選手番号 {racer_number} のデータが見つかりません。")
        return

    # 基本統計表示
    st.markdown(f"### 📋 選手番号: {racer_number}")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("総レース数", f"{overall_stats['total_races']}戦")

    with col2:
        st.metric("勝率", f"{overall_stats['win_rate']:.1%}")

    with col3:
        st.metric("2連対率", f"{overall_stats['place_rate_2']:.1%}")

    with col4:
        st.metric("平均着順", f"{overall_stats['avg_rank']:.2f}着")

    # 直近トレンド
    st.markdown("---")
    st.markdown("### 📈 直近トレンド（最近10戦）")

    trend_col1, trend_col2, trend_col3 = st.columns(3)

    with trend_col1:
        st.metric("直近勝率", f"{recent_trend['recent_win_rate']:.1%}")

    with trend_col2:
        st.metric("直近平均着順", f"{recent_trend['recent_avg_rank']:.2f}着")

    with trend_col3:
        trend_emoji = {
            'improving': '📈 調子上昇中',
            'stable': '➡️ 安定',
            'declining': '📉 調子下降気味'
        }
        st.metric("調子", trend_emoji.get(recent_trend['trend'], '❓ 不明'))

    # レーダーチャート
    st.markdown("---")
    st.markdown("### 🎯 選手能力レーダーチャート")

    categories = ['勝率', '2連対率', '3連対率', 'ST', '直近調子']
    win_rate_score = min(overall_stats['win_rate'] * 100 * 3, 100)
    place2_score = min(overall_stats['place_rate_2'] * 100 * 2, 100)
    place3_score = min(overall_stats['place_rate_3'] * 100 * 1.5, 100)

    avg_st = overall_stats.get('avg_st', 0.15)
    if avg_st and avg_st > 0:
        st_score = max(0, min(100, (0.20 - avg_st) * 500))
    else:
        st_score = 50

    recent_score = min(recent_trend['recent_win_rate'] * 100 * 3, 100)
    values = [win_rate_score, place2_score, place3_score, st_score, recent_score]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values,
        theta=categories,
        fill='toself',
        name=f'選手 {racer_number}'
    ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        showlegend=True,
        height=500
    )
    st.plotly_chart(fig, use_container_width=True)

    # 会場別成績
    st.markdown("---")
    st.markdown("### 🏟️ 会場別成績")

    if venue_stats:
        venue_df = pd.DataFrame(venue_stats)

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=venue_df['venue_name'],
            y=venue_df['win_rate'] * 100,
            text=[f"{rate:.1f}%" for rate in venue_df['win_rate'] * 100],
            textposition='auto',
            marker_color=['green' if rate > 0.20 else 'orange' if rate > 0.15 else 'lightcoral'
                         for rate in venue_df['win_rate']]
        ))

        fig.update_layout(
            title="会場別勝率",
            xaxis_title="会場",
            yaxis_title="勝率 (%)",
            height=400
        )

        st.plotly_chart(fig, use_container_width=True)

        display_df = venue_df.copy()
        display_df['win_rate'] = (display_df['win_rate'] * 100).round(1).astype(str) + '%'
        display_df['avg_rank'] = display_df['avg_rank'].round(2)
        display_df.columns = ['会場コード', '会場名', '総レース数', '勝利数', '勝率', '平均着順']

        st.dataframe(
            display_df[['会場名', '総レース数', '勝利数', '勝率', '平均着順']],
            use_container_width=True,
            height=400
        )
    else:
        st.info("会場別データがまだありません。")


if __name__ == "__main__":
    render_racer_analysis_page()
