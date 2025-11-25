"""
購入履歴・分析UIコンポーネント

購入実績の記録、統計表示、グラフ表示、CSV エクスポート機能を提供。
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
from src.betting.bet_tracker import BetTracker


def render_bet_history_page():
    """
    購入履歴ページのレンダリング
    """
    st.title("購入履歴・分析")
    st.markdown("実際の購入結果を記録し、ROI、勝率、最大ドローダウンなどを分析します。")

    # BetTracker初期化
    if 'bet_tracker' not in st.session_state:
        st.session_state['bet_tracker'] = BetTracker()

    tracker = st.session_state['bet_tracker']

    # タブ構成
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 統計サマリー",
        "📝 購入履歴",
        "➕ 購入記録追加",
        "📤 データ管理"
    ])

    with tab1:
        render_statistics_tab(tracker)

    with tab2:
        render_history_tab(tracker)

    with tab3:
        render_add_bet_tab(tracker)

    with tab4:
        render_data_management_tab(tracker)


def render_statistics_tab(tracker: BetTracker):
    """
    統計サマリータブ
    """
    st.header("統計サマリー")

    # 期間フィルタ
    col_f1, col_f2, col_f3 = st.columns(3)

    with col_f1:
        period = st.selectbox(
            "表示期間",
            ["全期間", "過去1週間", "過去1ヶ月", "過去3ヶ月", "カスタム"],
            index=0
        )

    start_date = None
    end_date = None

    if period == "過去1週間":
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    elif period == "過去1ヶ月":
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    elif period == "過去3ヶ月":
        start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    elif period == "カスタム":
        with col_f2:
            start_date = st.date_input("開始日", key="bet_history_custom_start_date").strftime("%Y-%m-%d")
        with col_f3:
            end_date = st.date_input("終了日", key="bet_history_custom_end_date").strftime("%Y-%m-%d")

    # 統計情報取得
    stats = tracker.calculate_statistics(start_date=start_date, end_date=end_date)

    # メトリクス表示（4列）
    st.markdown("### 基本統計")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("総購入数", f"{stats['total_bets']}回")
        st.metric("総投資額", f"{stats['total_investment']:,}円")

    with col2:
        st.metric("総払戻額", f"{stats['total_payout']:,}円")
        st.metric("総利益", f"{stats['total_profit']:,}円",
                 delta=f"{stats['roi']:.1f}%" if stats['roi'] != 0 else None)

    with col3:
        st.metric("ROI（投資収益率）", f"{stats['roi']:.2f}%")
        st.metric("勝率", f"{stats['win_rate']:.2f}%")

    with col4:
        st.metric("回収率", f"{stats['recovery_rate']:.2f}%")
        st.metric("平均オッズ", f"{stats['avg_odds']:.2f}")

    # リスク指標
    st.markdown("### リスク指標")
    col5, col6, col7, col8 = st.columns(4)

    with col5:
        st.metric("平均利益/回", f"{stats['avg_profit_per_bet']:,.0f}円")

    with col6:
        st.metric("最大利益", f"{stats['max_profit']:,}円")

    with col7:
        st.metric("最大損失", f"{stats['max_loss']:,}円")

    with col8:
        st.metric("最大ドローダウン", f"{stats['max_drawdown']:,.0f}円")

    # グラフ表示
    if stats['total_bets'] > 0:
        st.markdown("### 資金推移")

        # 初期資金設定
        initial_fund = st.number_input(
            "初期資金（円）",
            min_value=10000,
            value=100000,
            step=10000
        )

        # 資金推移データ取得
        fund_df = tracker.get_fund_transition(
            start_date=start_date,
            end_date=end_date,
            initial_fund=initial_fund
        )

        if not fund_df.empty:
            # Plotlyで資金推移グラフ作成
            fig = go.Figure()

            fig.add_trace(go.Scatter(
                x=fund_df['date'],
                y=fund_df['fund_balance'],
                mode='lines+markers',
                name='資金残高',
                line=dict(color='#1f77b4', width=2),
                marker=dict(size=6)
            ))

            # 初期資金ライン
            fig.add_hline(
                y=initial_fund,
                line_dash="dash",
                line_color="gray",
                annotation_text="初期資金"
            )

            fig.update_layout(
                title="資金推移",
                xaxis_title="日付",
                yaxis_title="資金（円）",
                height=400,
                hovermode='x unified'
            )

            st.plotly_chart(fig, use_container_width=True)

            # 累積利益グラフ
            fig2 = go.Figure()

            fig2.add_trace(go.Scatter(
                x=fund_df['date'],
                y=fund_df['cumulative_profit'],
                mode='lines+markers',
                name='累積利益',
                fill='tozeroy',
                line=dict(color='#2ca02c', width=2),
                marker=dict(size=6)
            ))

            fig2.update_layout(
                title="累積利益推移",
                xaxis_title="日付",
                yaxis_title="累積利益（円）",
                height=400,
                hovermode='x unified'
            )

            st.plotly_chart(fig2, use_container_width=True)

        # 会場別統計
        st.markdown("### 会場別パフォーマンス")

        venue_stats = tracker.get_venue_statistics(start_date=start_date, end_date=end_date)

        if not venue_stats.empty:
            # 会場別ROIグラフ
            fig3 = px.bar(
                venue_stats.head(10),
                x='venue_name',
                y='roi',
                color='roi',
                color_continuous_scale='RdYlGn',
                title="会場別ROI（上位10会場）"
            )

            fig3.update_layout(height=400)
            st.plotly_chart(fig3, use_container_width=True)

            # 会場別統計テーブル
            display_cols = ['venue_name', 'total_bets', 'win_rate', 'roi', 'recovery_rate', 'avg_odds']
            st.dataframe(
                venue_stats[display_cols].style.format({
                    'win_rate': '{:.2f}%',
                    'roi': '{:.2f}%',
                    'recovery_rate': '{:.2f}%',
                    'avg_odds': '{:.2f}'
                }),
                use_container_width=True
            )
    else:
        st.info("購入実績データがありません。「購入記録追加」タブから記録を追加してください。")


def render_history_tab(tracker: BetTracker):
    """
    購入履歴タブ
    """
    st.header("購入履歴")

    # フィルタ設定
    col_f1, col_f2, col_f3 = st.columns(3)

    with col_f1:
        start_date_input = st.date_input("開始日", value=None, key="history_start_date")
        start_date = start_date_input.strftime("%Y-%m-%d") if start_date_input else None

    with col_f2:
        end_date_input = st.date_input("終了日", value=None, key="history_end_date")
        end_date = end_date_input.strftime("%Y-%m-%d") if end_date_input else None

    with col_f3:
        result_filter = st.selectbox(
            "結果フィルタ",
            ["全て", "結果確定済み", "未確定"],
            index=0
        )

    result_only = None
    if result_filter == "結果確定済み":
        result_only = True
    elif result_filter == "未確定":
        result_only = False

    # 購入履歴取得
    df = tracker.get_bet_history(
        start_date=start_date,
        end_date=end_date,
        result_only=result_only
    )

    if df.empty:
        st.info("購入履歴がありません。")
        return

    st.markdown(f"**総件数: {len(df)}件**")

    # 表示用にフォーマット
    display_df = df[[
        'id', 'bet_date', 'venue_name', 'race_number', 'combination',
        'bet_amount', 'odds', 'expected_value', 'result', 'payout', 'profit'
    ]].copy()

    display_df['result'] = display_df['result'].apply(
        lambda x: '的中' if x == 1 else ('不的中' if x == 0 else '未確定')
    )

    display_df.columns = [
        'ID', '日付', '会場', 'R', '組合せ', '賭金', 'オッズ',
        '期待値', '結果', '払戻', '利益'
    ]

    # スタイル適用
    def color_result(val):
        if val == '的中':
            return 'background-color: #d4edda'
        elif val == '不的中':
            return 'background-color: #f8d7da'
        else:
            return ''

    styled_df = display_df.style.applymap(color_result, subset=['結果'])

    st.dataframe(styled_df, use_container_width=True)

    # 結果更新セクション
    st.markdown("---")
    st.subheader("結果更新")

    col_u1, col_u2, col_u3, col_u4 = st.columns(4)

    with col_u1:
        bet_id_to_update = st.number_input("購入記録ID", min_value=1, step=1, key="update_bet_id")

    with col_u2:
        is_hit = st.selectbox("結果", ["的中", "不的中"], key="update_result")

    with col_u3:
        payout = st.number_input("払戻金額（円）", min_value=0, step=100, key="update_payout")

    with col_u4:
        st.write("")
        st.write("")
        if st.button("結果を更新", type="primary"):
            tracker.update_result(
                bet_id=int(bet_id_to_update),
                is_hit=(is_hit == "的中"),
                payout=int(payout)
            )
            st.success(f"ID={bet_id_to_update} の結果を更新しました")
            st.rerun()


def render_add_bet_tab(tracker: BetTracker):
    """
    購入記録追加タブ
    """
    st.header("購入記録追加")

    with st.form("add_bet_form"):
        st.markdown("### 購入情報")

        col1, col2, col3 = st.columns(3)

        with col1:
            bet_date = st.date_input("購入日", value=datetime.now())

        with col2:
            venue_code = st.text_input("会場コード（2桁）", value="01", max_chars=2)

        with col3:
            venue_name = st.text_input("会場名", value="")

        col4, col5 = st.columns(2)

        with col4:
            race_number = st.number_input("レース番号", min_value=1, max_value=12, value=1)

        with col5:
            combination = st.text_input("組み合わせ（例: 1-2-3）", value="")

        st.markdown("### 賭け情報")

        col6, col7 = st.columns(2)

        with col6:
            bet_amount = st.number_input("賭け金額（円）", min_value=100, value=1000, step=100)

        with col7:
            odds = st.number_input("オッズ", min_value=1.0, value=10.0, step=0.1)

        st.markdown("### 予測情報（オプション）")

        col8, col9, col10 = st.columns(3)

        with col8:
            predicted_prob = st.number_input("予測確率", min_value=0.0, max_value=1.0, value=0.0, step=0.01)

        with col9:
            expected_value = st.number_input("期待値", min_value=0.0, value=0.0, step=0.01)

        with col10:
            buy_score = st.number_input("購入スコア", min_value=0.0, max_value=1.0, value=0.0, step=0.01)

        notes = st.text_area("メモ（オプション）", value="")

        submitted = st.form_submit_button("購入記録を追加", type="primary")

        if submitted:
            if not combination:
                st.error("組み合わせを入力してください")
            else:
                bet_id = tracker.add_bet(
                    bet_date=bet_date.strftime("%Y-%m-%d"),
                    venue_code=venue_code,
                    venue_name=venue_name if venue_name else None,
                    race_number=race_number,
                    combination=combination,
                    bet_amount=bet_amount,
                    odds=odds,
                    predicted_prob=predicted_prob if predicted_prob > 0 else None,
                    expected_value=expected_value if expected_value > 0 else None,
                    buy_score=buy_score if buy_score > 0 else None,
                    notes=notes if notes else None
                )

                st.success(f"購入記録を追加しました（ID: {bet_id}）")


def render_data_management_tab(tracker: BetTracker):
    """
    データ管理タブ
    """
    st.header("データ管理")

    st.markdown("### CSV エクスポート")

    col1, col2 = st.columns(2)

    with col1:
        export_start_date_input = st.date_input("開始日", value=None, key="bet_history_export_start_date")
        export_start_date = export_start_date_input.strftime("%Y-%m-%d") if export_start_date_input else None

    with col2:
        export_end_date_input = st.date_input("終了日", value=None, key="bet_history_export_end_date")
        export_end_date = export_end_date_input.strftime("%Y-%m-%d") if export_end_date_input else None

    export_filename = st.text_input(
        "ファイル名",
        value=f"bet_history_{datetime.now().strftime('%Y%m%d')}.csv"
    )

    if st.button("CSV エクスポート", type="primary"):
        export_path = f"data/{export_filename}"

        try:
            tracker.export_to_csv(
                file_path=export_path,
                start_date=export_start_date,
                end_date=export_end_date
            )
            st.success(f"購入履歴を {export_path} にエクスポートしました")

            # ダウンロードボタン
            df = tracker.get_bet_history(start_date=export_start_date, end_date=export_end_date)
            csv = df.to_csv(index=False, encoding='utf-8-sig')

            st.download_button(
                label="ダウンロード",
                data=csv,
                file_name=export_filename,
                mime="text/csv"
            )

        except Exception as e:
            st.error(f"エクスポートエラー: {e}")

    st.markdown("---")
    st.markdown("### データ削除")

    st.warning("購入記録を削除すると元に戻せません。慎重に操作してください。")

    col_d1, col_d2 = st.columns([3, 1])

    with col_d1:
        delete_bet_id = st.number_input("削除する購入記録ID", min_value=1, step=1, key="delete_bet_id")

    with col_d2:
        st.write("")
        st.write("")
        if st.button("削除", type="secondary"):
            if st.session_state.get('confirm_delete'):
                tracker.delete_bet(int(delete_bet_id))
                st.success(f"ID={delete_bet_id} の購入記録を削除しました")
                st.session_state['confirm_delete'] = False
                st.rerun()
            else:
                st.session_state['confirm_delete'] = True
                st.warning("もう一度削除ボタンをクリックして確定してください")
