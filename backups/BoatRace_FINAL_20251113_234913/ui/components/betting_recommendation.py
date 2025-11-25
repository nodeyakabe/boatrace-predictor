"""
購入推奨UI

Kelly基準の投資戦略を使用した購入推奨を表示
"""

import streamlit as st
import pandas as pd
import numpy as np
from typing import Dict, List
import sys
import os


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

from src.betting.kelly_strategy import KellyBettingStrategy, ExpectedValueCalculator, BetRecommendation


def render_betting_recommendations(
    predictions: List[Dict],
    odds_data: Dict[str, float],
    buy_score: float = 1.0,
    bankroll: float = 10000
):
    """
    購入推奨を表示

    Args:
        predictions: 予測結果 [{'combination': '1-2-3', 'prob': 0.15}, ...]
        odds_data: オッズデータ {'1-2-3': 8.5, ...}
        buy_score: レース選別スコア（0〜1）
        bankroll: 資金
    """
    st.markdown("---")
    st.subheader("💰 Kelly基準 購入推奨")

    # レース選別スコア表示
    col1, col2, col3 = st.columns(3)

    with col1:
        score_color = "🟢" if buy_score > 0.7 else "🟡" if buy_score > 0.5 else "🔴"
        st.metric("レース選別スコア", f"{score_color} {buy_score:.0%}")

    with col2:
        if buy_score > 0.7:
            st.success("✅ 予想しやすいレース")
        elif buy_score > 0.5:
            st.warning("⚠️ 通常のレース")
        else:
            st.error("❌ 予想困難なレース")

    with col3:
        st.metric("資金", f"¥{bankroll:,}")

    st.markdown("---")

    # Kelly戦略設定
    with st.expander("⚙️ 投資戦略設定", expanded=False):
        col1, col2, col3 = st.columns(3)

        with col1:
            kelly_fraction = st.slider(
                "Kelly分数",
                min_value=0.1,
                max_value=0.5,
                value=0.25,
                step=0.05,
                help="リスク調整係数。0.25 = 1/4 Kelly（推奨）"
            )

        with col2:
            min_ev = st.slider(
                "最小期待値",
                min_value=0.0,
                max_value=0.20,
                value=0.05,
                step=0.01,
                format="%.0f%%",
                help="この値以上の期待値がある買い目のみ購入"
            )

        with col3:
            max_combinations = st.slider(
                "最大購入数",
                min_value=1,
                max_value=10,
                value=5,
                help="購入する買い目の最大数"
            )

    # Kelly戦略インスタンス
    strategy = KellyBettingStrategy(
        bankroll=bankroll,
        kelly_fraction=kelly_fraction,
        min_ev=min_ev
    )

    # 買い目選定
    recommendations = strategy.select_bets(
        predictions=predictions,
        odds_data=odds_data,
        buy_score=buy_score
    )

    if not recommendations:
        st.warning("⚠️ 期待値がプラスの買い目がありません。このレースは見送りを推奨します。")
        return

    # ポートフォリオ最適化
    optimized_recs = strategy.optimize_portfolio(recommendations, max_combinations=max_combinations)

    # 総賭け金
    total_bet = sum(rec.recommended_bet for rec in optimized_recs)

    # サマリー表示
    st.markdown("### 📊 購入サマリー")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("推奨購入数", f"{len(optimized_recs)}点")

    with col2:
        st.metric("総賭け金", f"¥{total_bet:,.0f}")

    with col3:
        avg_ev = np.mean([rec.expected_value for rec in optimized_recs])
        st.metric("平均期待値", f"{avg_ev:+.1%}")

    with col4:
        expected_return = sum(
            rec.pred_prob * rec.odds * rec.recommended_bet
            for rec in optimized_recs
        )
        expected_profit = expected_return - total_bet
        st.metric("期待利益", f"¥{expected_profit:+,.0f}")

    st.markdown("---")

    # 詳細な推奨リスト
    st.markdown("### 🎯 詳細な購入推奨")

    for idx, rec in enumerate(optimized_recs, 1):
        with st.container():
            # 信頼度による色分け
            if rec.confidence == "High":
                border_color = "#28a745"  # 緑
                confidence_emoji = "🟢"
            elif rec.confidence == "Medium":
                border_color = "#ffc107"  # 黄色
                confidence_emoji = "🟡"
            else:
                border_color = "#dc3545"  # 赤
                confidence_emoji = "🔴"

            st.markdown(f"""
            <div style="border-left: 4px solid {border_color}; padding-left: 10px; margin-bottom: 10px;">
            """, unsafe_allow_html=True)

            col1, col2, col3, col4, col5 = st.columns([1, 2, 2, 2, 2])

            with col1:
                st.markdown(f"### {idx}")

            with col2:
                st.markdown(f"**{rec.combination}**")
                st.caption(f"信頼度: {confidence_emoji} {rec.confidence}")

            with col3:
                st.metric("予測確率", f"{rec.pred_prob:.1%}")
                st.caption(f"オッズ: {rec.odds:.1f}倍")

            with col4:
                st.metric("期待値", f"{rec.expected_value:+.1%}")

                # エッジ計算
                calc = ExpectedValueCalculator()
                edge = calc.calculate_edge(rec.pred_prob, rec.odds)
                st.caption(f"エッジ: {edge:+.1f}%")

            with col5:
                st.metric("推奨購入額", f"¥{rec.recommended_bet:,.0f}")
                kelly_pct = rec.kelly_fraction * 100
                st.caption(f"Kelly: {kelly_pct:.1f}%")

            st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")

    # 期待値分析
    with st.expander("📈 詳細な期待値分析", expanded=False):
        st.markdown("#### 各買い目の詳細分析")

        calc = ExpectedValueCalculator()

        for rec in optimized_recs:
            st.markdown(f"**{rec.combination}**")

            col1, col2 = st.columns(2)

            with col1:
                # 損益分岐点オッズ
                breakeven_odds = calc.calculate_breakeven_odds(rec.pred_prob)
                st.write(f"損益分岐点オッズ: {breakeven_odds:.1f}倍")
                st.write(f"実際のオッズ: {rec.odds:.1f}倍")

                if rec.odds > breakeven_odds:
                    st.success(f"✅ オッズが{rec.odds - breakeven_odds:.1f}倍お得")
                else:
                    st.warning(f"⚠️ オッズが{breakeven_odds - rec.odds:.1f}倍不足")

            with col2:
                # ROI信頼区間
                lower_roi, upper_roi = calc.calculate_roi_range(
                    rec.pred_prob,
                    rec.odds,
                    rec.recommended_bet
                )

                st.write(f"期待ROI: {rec.expected_value * 100:.1f}%")
                st.write(f"95%信頼区間: {lower_roi:.1f}% 〜 {upper_roi:.1f}%")

            st.markdown("---")

    # シミュレーション
    with st.expander("🎮 結果シミュレーション", expanded=False):
        st.markdown("#### もし的中した場合...")

        for rec in optimized_recs:
            returns = rec.recommended_bet * rec.odds
            profit = returns - total_bet

            st.markdown(f"**{rec.combination} が的中した場合:**")
            st.write(f"- 払戻: ¥{returns:,.0f}")
            st.write(f"- 利益: ¥{profit:+,.0f}")
            st.write(f"- ROI: {profit / total_bet * 100:+.1f}%")
            st.markdown("---")

    # 購入ボタン
    st.markdown("---")
    col1, col2 = st.columns(2)

    with col1:
        if st.button("📋 購入リストをコピー", use_container_width=True):
            # 購入リストをテキスト形式で生成
            purchase_list = "【購入推奨リスト】\n"
            purchase_list += f"総賭け金: ¥{total_bet:,.0f}\n\n"

            for idx, rec in enumerate(optimized_recs, 1):
                purchase_list += f"{idx}. {rec.combination} ¥{rec.recommended_bet:,.0f}\n"
                purchase_list += f"   (期待値: {rec.expected_value:+.1%}, 信頼度: {rec.confidence})\n"

            st.code(purchase_list)
            st.success("✅ 上記テキストをコピーしてください")

    with col2:
        if st.button("⚠️ 購入見送り", use_container_width=True, type="secondary"):
            st.warning("このレースはスキップします")


def render_past_performance(bet_history: pd.DataFrame):
    """
    過去の購入実績を表示

    Args:
        bet_history: 購入履歴データ
    """
    st.markdown("---")
    st.subheader("📊 過去の購入実績")

    if bet_history.empty:
        st.info("まだ購入実績がありません")
        return

    # 統計サマリー
    from src.betting.kelly_strategy import KellyBettingStrategy

    strategy = KellyBettingStrategy()
    risk_metrics = strategy.calculate_risk_metrics(bet_history)

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("総購入回数", f"{risk_metrics['total_bets']}回")

    with col2:
        st.metric("勝率", f"{risk_metrics['win_rate']:.1%}")

    with col3:
        st.metric("平均ROI", f"{risk_metrics['avg_roi']:+.1f}%")

    with col4:
        st.metric("総利益", f"¥{risk_metrics['total_profit']:+,.0f}")

    # 資金推移グラフ
    st.markdown("#### 資金推移")

    import plotly.graph_objects as go

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=bet_history['date'],
        y=bet_history['bankroll'],
        mode='lines+markers',
        name='資金',
        line=dict(color='#2196F3', width=2)
    ))

    fig.update_layout(
        title="資金推移",
        xaxis_title="日付",
        yaxis_title="資金（円）",
        hovermode='x unified'
    )

    st.plotly_chart(fig, use_container_width=True)

    # リスク指標
    st.markdown("#### リスク指標")

    col1, col2 = st.columns(2)

    with col1:
        st.metric("最大ドローダウン", f"{risk_metrics['max_drawdown']:.1%}")

    with col2:
        st.metric("シャープレシオ", f"{risk_metrics['sharpe_ratio']:.2f}")

    # 詳細履歴
    with st.expander("📋 詳細履歴", expanded=False):
        st.dataframe(bet_history, use_container_width=True)
