"""
統合予測UIコンポーネント
Phase 1-3の新機能を統合した予測画面
"""
import streamlit as st
import pandas as pd
from datetime import datetime
import traceback

from src.prediction.integrated_predictor import IntegratedPredictor
from ui.components.common.db_utils import get_db_connection, safe_query_to_df


def render_integrated_prediction():
    """統合予測画面を表示"""
    st.header("🎯 AI予測（Phase 1-3統合版）")

    st.info("""
    **新機能搭載**:
    - ✨ Phase 1: 最適化特徴量とハイパーパラメータ調整
    - ✨ Phase 2: アンサンブル予測と時系列特徴量
    - ✨ Phase 3: リアルタイム更新とXAI説明
    """)

    # 予測器の初期化
    if 'integrated_predictor' not in st.session_state:
        with st.spinner("統合予測システムを初期化中..."):
            try:
                st.session_state.integrated_predictor = IntegratedPredictor()
                st.success("✅ 統合予測システム初期化完了")
            except Exception as e:
                st.error(f"初期化エラー: {e}")
                return

    predictor = st.session_state.integrated_predictor

    # レース選択
    st.subheader("📍 レース選択")

    col1, col2, col3 = st.columns(3)

    with col1:
        # 日付選択
        race_date = st.date_input(
            "レース日",
            value=datetime.now(),
            key="integrated_race_date"
        )

    with col2:
        # 会場選択
        venues_df = safe_query_to_df("SELECT DISTINCT code as venue_code, name as venue_name FROM venues ORDER BY code")
        if venues_df is not None and not venues_df.empty:
            venue_options = {f"{row['venue_code']}: {row['venue_name']}": row['venue_code']
                           for _, row in venues_df.iterrows()}
            selected_venue_label = st.selectbox(
                "会場",
                options=list(venue_options.keys()),
                key="integrated_venue"
            )
            venue_code = venue_options[selected_venue_label]
        else:
            st.warning("会場データが取得できません")
            return

    with col3:
        # レース選択
        race_number = st.number_input(
            "レース番号",
            min_value=1,
            max_value=12,
            value=1,
            key="integrated_race_number"
        )

    # レースデータ取得
    race_date_str = race_date.strftime('%Y-%m-%d')

    query = """
        SELECT
            r.id as race_id,
            r.venue_code,
            r.race_date,
            r.race_number,
            r.race_grade,
            e.pit_number,
            e.racer_number,
            e.racer_name,
            e.motor_number,
            e.boat_number
        FROM races r
        JOIN entries e ON r.id = e.race_id
        WHERE r.race_date = ?
          AND r.venue_code = ?
          AND r.race_number = ?
        ORDER BY e.pit_number
    """

    racers_df = safe_query_to_df(query, params=(race_date_str, venue_code, race_number))

    if racers_df is None or racers_df.empty:
        st.warning("該当するレースが見つかりません")
        return

    # レース情報表示
    race_id = racers_df['race_id'].iloc[0]
    race_grade = racers_df['race_grade'].iloc[0] if 'race_grade' in racers_df.columns else '一般'

    st.success(f"✅ レース取得: {venue_code} - {race_number}R ({race_grade})")

    # 直前情報入力（オプション）
    st.subheader("⚡ 直前情報（オプション）")

    use_latest_info = st.checkbox("直前情報を使用", value=False)

    latest_info_list = None
    if use_latest_info:
        st.caption("各選手の展示タイムとスタートタイミングを入力")
        latest_info_list = []

        cols = st.columns(3)
        for i, row in racers_df.iterrows():
            pit = row['pit_number']
            racer_name = row['racer_name']

            with cols[pit % 3]:
                st.markdown(f"**{pit}号艇: {racer_name}**")
                exhibition_time = st.number_input(
                    f"展示タイム",
                    min_value=6.0,
                    max_value=8.0,
                    value=6.8,
                    step=0.01,
                    key=f"ex_time_{pit}"
                )
                st_time = st.number_input(
                    f"ST",
                    min_value=-0.5,
                    max_value=0.5,
                    value=0.15,
                    step=0.01,
                    key=f"st_time_{pit}"
                )

                latest_info_list.append({
                    'exhibition_time': exhibition_time,
                    'st_time': st_time,
                    'actual_course': pit  # デフォルトは枠番通り
                })

    # 予測実行
    if st.button("🎯 AI予測を実行", type="primary"):
        with st.spinner("予測計算中..."):
            try:
                # 選手データを準備
                racers_data = []
                for _, row in racers_df.iterrows():
                    racers_data.append({
                        'racer_number': row['racer_number'],
                        'racer_name': row['racer_name'],
                        'pit_number': row['pit_number'],
                        'motor_number': row['motor_number'],
                        'race_grade': race_grade
                    })

                # 統合予測実行
                result = predictor.predict_race(
                    race_id=race_id,
                    venue_code=venue_code,
                    race_date=race_date_str,
                    racers_data=racers_data,
                    latest_info_list=latest_info_list
                )

                # 結果を保存
                st.session_state.prediction_result = result

            except Exception as e:
                st.error(f"予測エラー: {e}")
                st.code(traceback.format_exc())
                return

    # 結果表示
    if 'prediction_result' in st.session_state:
        result = st.session_state.prediction_result

        # 予測結果テーブル
        st.subheader("📊 予測結果")

        predictions_df = pd.DataFrame(result['predictions'])
        predictions_df = predictions_df.sort_values('probability', ascending=False)
        predictions_df['順位'] = range(1, len(predictions_df) + 1)
        predictions_df['勝率'] = predictions_df['probability'].apply(lambda x: f"{x*100:.2f}%")

        st.dataframe(
            predictions_df[['順位', 'pit_number', 'racer_name', '勝率']].rename(columns={
                'pit_number': '枠番',
                'racer_name': '選手名'
            }),
            use_container_width=True,
            hide_index=True
        )

        # レース分析
        if result.get('comparison'):
            st.subheader("🔍 レース分析")

            comp = result['comparison']

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("本命", f"{comp['highest_prob']['pit_number']}号艇")
                st.caption(f"{comp['highest_prob']['racer']}")
                st.caption(f"勝率: {comp['highest_prob']['probability']*100:.2f}%")

            with col2:
                st.metric("対抗", f"{comp['lowest_prob']['pit_number']}号艇")
                st.caption(f"{comp['lowest_prob']['racer']}")
                st.caption(f"勝率: {comp['lowest_prob']['probability']*100:.2f}%")

            with col3:
                st.metric("競争性", comp['competitiveness'])
                st.caption(f"確率差: {comp['probability_spread']*100:.2f}%")

        # 波乱分析
        if result.get('upset_analysis'):
            st.subheader("⚠️ 波乱分析")

            upset = result['upset_analysis']

            col1, col2 = st.columns(2)

            with col1:
                st.metric("波乱スコア", f"{upset['upset_score']*100:.1f}点")
                st.progress(upset['upset_score'])

            with col2:
                st.metric("リスクレベル", upset['risk_level'])
                st.info(f"💡 推奨: **{upset['recommendation']}**")

        # XAI説明
        if result.get('explanations'):
            st.subheader("🧠 AI予測の根拠（XAI）")

            for explanation in result['explanations']:
                with st.expander(f"{explanation['pit_number']}号艇: {explanation['racer_name']}"):
                    st.markdown(explanation['explanation_text'])

                    # 有利・不利要因を可視化
                    if explanation['explanation'].get('top_positive_factors'):
                        st.markdown("#### ✅ 有利な要因")
                        positive_df = pd.DataFrame(
                            explanation['explanation']['top_positive_factors'],
                            columns=['特徴量', '寄与度']
                        )
                        positive_df['寄与度'] = positive_df['寄与度'].apply(lambda x: f"+{x*100:.2f}%")
                        st.dataframe(positive_df, hide_index=True)

                    if explanation['explanation'].get('top_negative_factors'):
                        st.markdown("#### ❌ 不利な要因")
                        negative_df = pd.DataFrame(
                            explanation['explanation']['top_negative_factors'],
                            columns=['特徴量', '寄与度']
                        )
                        negative_df['寄与度'] = negative_df['寄与度'].apply(lambda x: f"{x*100:.2f}%")
                        st.dataframe(negative_df, hide_index=True)

        # 信頼区間
        if result.get('confidence_interval'):
            st.subheader("📈 予測信頼区間")

            ci = result['confidence_interval']
            st.write(f"信頼水準: {ci['confidence_level']*100:.0f}%")
            st.write(f"下限: {ci['lower_bound']*100:.2f}%")
            st.write(f"上限: {ci['upper_bound']*100:.2f}%")

        # 異常検出
        if result.get('anomaly_indices') and len(result['anomaly_indices']) > 0:
            st.warning(f"⚠️ 異常値検出: {len(result['anomaly_indices'])}件の異常が検出されました")
            st.caption("予測結果に異常な値が含まれています。慎重に判断してください。")


def render_feature_importance():
    """特徴量重要度を表示"""
    st.header("📊 特徴量重要度分析")

    if 'integrated_predictor' not in st.session_state:
        st.warning("先に予測を実行してください")
        return

    predictor = st.session_state.integrated_predictor

    with st.spinner("特徴量重要度を計算中..."):
        importance = predictor.get_feature_importance(top_n=30)

    if not importance:
        st.warning("特徴量重要度が取得できません")
        return

    # DataFrameに変換
    importance_df = pd.DataFrame([
        {'特徴量': k, '重要度': v}
        for k, v in importance.items()
    ])

    # 棒グラフ
    st.bar_chart(importance_df.set_index('特徴量')['重要度'])

    # テーブル
    st.dataframe(importance_df, use_container_width=True, hide_index=True)
