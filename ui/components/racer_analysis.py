"""
選手分析UIコンポーネント

選手の詳細データを可視化
- レーダーチャート: 選手能力の多角的評価
- 会場別成績ヒートマップ
- 直近トレンド分析
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
from src.analysis.racer_analyzer import RacerAnalyzer


def render_racer_analysis_page():
    """選手分析ページのメイン表示"""
    st.header("👤 選手データ分析")

    tab1, tab2 = st.tabs([
        "🎯 選手詳細分析",
        "📊 選手比較"
    ])

    with tab1:
        render_racer_detail_analysis()

    with tab2:
        render_racer_comparison()


def render_racer_detail_analysis():
    """選手詳細分析タブ"""
    st.subheader("🎯 選手詳細分析")

    analyzer = RacerAnalyzer(DATABASE_PATH)

    # 選手番号入力
    racer_number = st.number_input(
        "選手登録番号を入力",
        min_value=1000,
        max_value=9999,
        value=4444,
        step=1,
        key="racer_detail_number"
    )

    # データ期間選択
    days_back = st.slider(
        "分析期間（過去N日）",
        min_value=30,
        max_value=730,
        value=365,
        step=30,
        key="racer_analysis_days"
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
        # トレンド表示
        trend_emoji = {
            'improving': '📈 調子上昇中',
            'stable': '➡️ 安定',
            'declining': '📉 調子下降気味'
        }
        st.metric("調子", trend_emoji.get(recent_trend['trend'], '❓ 不明'))

    # レーダーチャート（選手能力）
    st.markdown("---")
    st.markdown("### 🎯 選手能力レーダーチャート")

    # レーダーチャート用データ作成
    categories = ['勝率', '2連対率', '3連対率', 'ST', '直近調子']

    # 各項目を0-100にスケーリング
    win_rate_score = min(overall_stats['win_rate'] * 100 * 3, 100)  # 33%で100点
    place2_score = min(overall_stats['place_rate_2'] * 100 * 2, 100)  # 50%で100点
    place3_score = min(overall_stats['place_rate_3'] * 100 * 1.5, 100)  # 66%で100点

    # ST スコア（0.15秒を基準に、速いほど高得点）
    avg_st = overall_stats.get('avg_st', 0.15)
    if avg_st and avg_st > 0:
        st_score = max(0, min(100, (0.20 - avg_st) * 500))  # 0.10で100点、0.20で0点
    else:
        st_score = 50  # デフォルト

    # 直近調子スコア
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
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100]
            )
        ),
        showlegend=True,
        height=500
    )

    st.plotly_chart(fig, use_container_width=True)

    # 会場別成績
    st.markdown("---")
    st.markdown("### 🏟️ 会場別成績")

    if venue_stats:
        venue_df = pd.DataFrame(venue_stats)

        # 会場別勝率棒グラフ
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

        # 会場別成績テーブル
        st.markdown("#### 📋 詳細データ")

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


def render_racer_comparison():
    """選手比較タブ"""
    st.subheader("📊 選手比較")

    analyzer = RacerAnalyzer(DATABASE_PATH)

    st.markdown("複数の選手を比較します。")

    # 選手番号入力（最大4人）
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        racer1 = st.number_input("選手1", min_value=1000, max_value=9999, value=4444, key="racer_comp_1")

    with col2:
        racer2 = st.number_input("選手2", min_value=1000, max_value=9999, value=4445, key="racer_comp_2")

    with col3:
        racer3 = st.number_input("選手3（任意）", min_value=0, max_value=9999, value=0, key="racer_comp_3")

    with col4:
        racer4 = st.number_input("選手4（任意）", min_value=0, max_value=9999, value=0, key="racer_comp_4")

    racers = [r for r in [racer1, racer2, racer3, racer4] if r > 0]

    if len(racers) < 2:
        st.warning("比較するには少なくとも2人の選手番号を入力してください。")
        return

    # データ取得
    days_back = st.slider(
        "分析期間（過去N日）",
        min_value=30,
        max_value=730,
        value=180,
        step=30,
        key="racer_comp_days"
    )

    comparison_data = []

    with st.spinner("データ取得中..."):
        for racer_num in racers:
            stats = analyzer.get_racer_overall_stats(racer_num, days=days_back)
            if stats['total_races'] > 0:
                comparison_data.append({
                    'racer_number': racer_num,
                    'total_races': stats['total_races'],
                    'win_rate': stats['win_rate'],
                    'place_rate_2': stats['place_rate_2'],
                    'place_rate_3': stats['place_rate_3'],
                    'avg_rank': stats['avg_rank'],
                    'avg_st': stats.get('avg_st', 0)
                })

    if not comparison_data:
        st.error("データが取得できませんでした。")
        return

    # レーダーチャート（複数選手）
    st.markdown("### 🎯 能力比較レーダーチャート")

    fig = go.Figure()

    categories = ['勝率', '2連対率', '3連対率', 'ST', '平均着順']

    for data in comparison_data:
        win_rate_score = min(data['win_rate'] * 100 * 3, 100)
        place2_score = min(data['place_rate_2'] * 100 * 2, 100)
        place3_score = min(data['place_rate_3'] * 100 * 1.5, 100)

        avg_st = data.get('avg_st', 0.15)
        if avg_st and avg_st > 0:
            st_score = max(0, min(100, (0.20 - avg_st) * 500))
        else:
            st_score = 50

        # 平均着順スコア（1着で100点、6着で0点）
        rank_score = max(0, 100 - (data['avg_rank'] - 1) * 20)

        values = [win_rate_score, place2_score, place3_score, st_score, rank_score]

        fig.add_trace(go.Scatterpolar(
            r=values,
            theta=categories,
            fill='toself',
            name=f'選手 {data["racer_number"]}'
        ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100]
            )
        ),
        showlegend=True,
        height=600
    )

    st.plotly_chart(fig, use_container_width=True)

    # 比較テーブル
    st.markdown("### 📋 詳細比較")

    comp_df = pd.DataFrame(comparison_data)
    comp_df['win_rate'] = (comp_df['win_rate'] * 100).round(1).astype(str) + '%'
    comp_df['place_rate_2'] = (comp_df['place_rate_2'] * 100).round(1).astype(str) + '%'
    comp_df['place_rate_3'] = (comp_df['place_rate_3'] * 100).round(1).astype(str) + '%'
    comp_df['avg_rank'] = comp_df['avg_rank'].round(2)
    comp_df['avg_st'] = comp_df['avg_st'].round(3)

    comp_df.columns = ['選手番号', '総レース数', '勝率', '2連対率', '3連対率', '平均着順', '平均ST']

    st.dataframe(comp_df, use_container_width=True)


if __name__ == "__main__":
    # Streamlit単体実行用（デバッグ）
    render_racer_analysis_page()
