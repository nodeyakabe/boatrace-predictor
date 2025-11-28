"""
統合レース詳細画面
AI予測結果、XAI説明、買い目推奨を統合表示
"""
import streamlit as st
import pandas as pd
from datetime import datetime
import traceback
from typing import Dict, List, Optional

from src.prediction.integrated_predictor import IntegratedPredictor
from src.analysis.race_predictor import RacePredictor
from src.betting.bet_generator import BetGenerator
from ui.components.common.widgets import render_confidence_badge
from ui.components.common.db_utils import safe_query_to_df


def render_unified_race_detail(race_date=None, venue_code=None, race_number=None, predictions=None):
    """統合レース詳細画面を表示

    Args:
        race_date: レース日（指定がなければ手動選択）
        venue_code: 会場コード（指定がなければ手動選択）
        race_number: レース番号（指定がなければ手動選択）
        predictions: 既存の予測結果（あればスキップ）
    """
    st.header("🎯 レース詳細分析")

    # レース選択または引数から取得
    if race_date and venue_code and race_number:
        # 引数から取得（一覧画面からの遷移）
        selected_race_date = race_date
        selected_venue_code = venue_code
        selected_race_number = race_number

        st.info(f"📍 選択レース: {venue_code} {race_number}R ({race_date})")

        # 戻るボタン
        if st.button("← 一覧に戻る"):
            # 一覧画面に戻る
            from ui.components.unified_race_list import clear_selected_race
            clear_selected_race()
            st.rerun()
    else:
        # 手動選択
        selected_race_date, selected_venue_code, selected_race_number = _render_race_selector()

    if not selected_race_date or not selected_venue_code or not selected_race_number:
        return

    # レースデータを取得
    race_date_str = selected_race_date if isinstance(selected_race_date, str) else selected_race_date.strftime('%Y-%m-%d')

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

    racers_df = safe_query_to_df(query, params=(race_date_str, selected_venue_code, selected_race_number))

    if racers_df is None or racers_df.empty:
        st.warning("該当するレースが見つかりません")
        st.info("データ準備タブでデータを取得してください")
        return

    race_id = racers_df['race_id'].iloc[0]
    race_grade = racers_df['race_grade'].iloc[0] if 'race_grade' in racers_df.columns else '一般'

    # タブ構成
    tab1, tab2, tab3 = st.tabs(["🎯 AI予測", "💰 買い目推奨", "🧠 詳細分析"])

    with tab1:
        _render_ai_prediction(race_id, race_date_str, selected_venue_code, selected_race_number,
                            racers_df, race_grade, predictions)

    with tab2:
        _render_bet_recommendations(race_id, race_date_str, selected_venue_code, selected_race_number)

    with tab3:
        _render_detailed_analysis(race_id, race_date_str, selected_venue_code, selected_race_number,
                                racers_df, race_grade)


def _render_race_selector():
    """レース選択UI"""
    st.subheader("📍 レース選択")

    col1, col2, col3 = st.columns(3)

    with col1:
        race_date = st.date_input(
            "レース日",
            value=datetime.now(),
            key="detail_race_date"
        )

    with col2:
        venues_df = safe_query_to_df("SELECT DISTINCT code as venue_code, name as venue_name FROM venues ORDER BY code")
        if venues_df is not None and not venues_df.empty:
            venue_options = {f"{row['venue_code']}: {row['venue_name']}": row['venue_code']
                           for _, row in venues_df.iterrows()}
            selected_venue_label = st.selectbox(
                "会場",
                options=list(venue_options.keys()),
                key="detail_venue"
            )
            venue_code = venue_options[selected_venue_label]
        else:
            st.warning("会場データが取得できません")
            return None, None, None

    with col3:
        race_number = st.number_input(
            "レース番号",
            min_value=1,
            max_value=12,
            value=1,
            key="detail_race_number"
        )

    return race_date, venue_code, race_number


def _render_ai_prediction(race_id, race_date_str, venue_code, race_number, racers_df, race_grade, existing_predictions=None):
    """AI予測タブ"""
    st.subheader("🎯 AI予測結果")

    # 直前予想更新ボタン
    col_btn1, col_btn2 = st.columns([1, 3])
    with col_btn1:
        if st.button("🔄 直前予想を更新", help="展示データがあれば直前予想（before）を生成します"):
            from src.analysis.prediction_updater import PredictionUpdater
            updater = PredictionUpdater()

            with st.spinner("直前予想を生成中..."):
                success = updater.update_to_before_prediction(race_id, force=True)

            if success:
                st.success("✅ 直前予想を更新しました")
                st.rerun()
            else:
                st.error("❌ 直前予想の更新に失敗しました")

    # 既存の予測がある場合は使用、なければ生成
    if existing_predictions:
        predictions = existing_predictions
        st.success("✅ 予測済みデータを表示")
    else:
        # 基本予測を実行
        race_predictor = RacePredictor()

        with st.spinner("予測計算中..."):
            try:
                predictions = race_predictor.predict_race_by_key(
                    race_date_str, venue_code, race_number
                )
            except Exception as e:
                st.error(f"予測エラー: {e}")
                st.code(traceback.format_exc())
                return

    if not predictions or len(predictions) < 3:
        st.warning("予想データを生成できませんでした")
        return

    # TOP3予想を大きく表示
    st.markdown("### 🏆 予想結果 TOP3")

    top3 = predictions[:3]

    for i, pred in enumerate(top3, 1):
        with st.container():
            col1, col2, col3, col4 = st.columns([1, 2, 2, 2])

            with col1:
                medal = ["🥇", "🥈", "🥉"][i-1]
                st.markdown(f"## {medal}")

            with col2:
                st.markdown(f"**{pred['pit_number']}号艇**")
                racer_name = pred.get('racer_name', '選手名不明')
                st.markdown(f"{racer_name}")

            with col3:
                score = pred.get('total_score', pred.get('score', 0))
                st.metric("スコア", f"{score:.1f}")

            with col4:
                confidence_level = pred.get('confidence', 'C')
                badge = render_confidence_badge(confidence_level)
                st.markdown(f"**{badge}**")

            st.markdown("---")

    # 全艇の予想
    with st.expander("📊 全艇の予想スコア（詳細）", expanded=True):
        # 基本情報
        df = pd.DataFrame([{
            '順位': i+1,
            '艇番': p['pit_number'],
            '選手': p.get('racer_name', '選手名不明'),
            '合計': f"{p['total_score']:.1f}",
            'コース': f"{p.get('course_score', 0):.1f}",
            '選手': f"{p.get('racer_score', 0):.1f}",
            'モーター': f"{p.get('motor_score', 0):.1f}",
            '拡張': f"{p.get('extended_score', 0):.1f}",
        } for i, p in enumerate(predictions)])

        st.dataframe(df, use_container_width=True, hide_index=True)

        # 展示データ詳細
        st.markdown("#### 📊 展示ST・展示タイム順位")
        st.caption("※バックテスト結果: 展示ST/タイム追加で的中率 +1.23%（58.75%→59.98%）")

        exhibition_data = []
        for p in predictions:
            ext = p.get('extended_detail', {})
            exhibition = ext.get('exhibition', {})
            st_data = ext.get('start_timing', {})

            exhibition_data.append({
                '艇番': p['pit_number'],
                '選手': p.get('racer_name', '')[:6],
                '展示T順位': exhibition.get('rank', '-'),
                '展示T': f"{exhibition.get('exhibition_time', 0):.2f}" if exhibition.get('exhibition_time') else '-',
                '平均ST': f"{st_data.get('avg_st', 0):.2f}" if st_data.get('avg_st') else '-',
                'ST評価': st_data.get('category', '-'),
            })

        if exhibition_data:
            ex_df = pd.DataFrame(exhibition_data)
            st.dataframe(ex_df, use_container_width=True, hide_index=True)

    # 判断根拠（適用法則）
    st.markdown("---")
    st.markdown("### 🔍 判断根拠（適用法則）")

    try:
        race_predictor = RacePredictor()
        applied_rules = race_predictor.get_applied_rules_by_key(
            race_date_str, venue_code, race_number
        )

        if applied_rules:
            for i, rule in enumerate(applied_rules[:10], 1):
                effect_pct = rule['effect_value'] * 100

                # 法則タイプに応じたアイコン
                rule_type = rule.get('type', '競艇場法則')
                if rule_type == '競艇場法則':
                    icon = '🏟️'
                elif rule_type == '選手法則':
                    icon = '👤'
                else:
                    icon = '📌'

                st.write(f"{i}. {icon} {rule['description']} ({effect_pct:+.1f}%)")
        else:
            st.info("基本モデルのみで予想（法則未適用）")

    except Exception as e:
        st.warning(f"法則取得エラー: {e}")

    # 改善機能の効果を表示
    st.markdown("---")
    st.markdown("### ⚙️ 適用された改善機能")

    from ui.components.improvements_display import (
        render_improvement_badges,
        render_smoothing_details,
        render_first_place_lock_details
    )

    # 改善バッジを表示
    with st.expander("🔧 Laplace平滑化の効果", expanded=False):
        render_smoothing_details(predictions)

    with st.expander("🔒 1着固定ルールの判定", expanded=False):
        render_first_place_lock_details(predictions)

    # セッションに保存（他のタブで使用）
    st.session_state.current_predictions = predictions


def _render_bet_recommendations(race_id, race_date_str, venue_code, race_number):
    """買い目推奨タブ"""
    st.subheader("💰 推奨買い目")

    # 予測結果を取得
    predictions = st.session_state.get('current_predictions')

    if not predictions or len(predictions) < 3:
        st.warning("先にAI予測タブで予測を実行してください")
        return

    top3 = predictions[:3]

    # 基本的な推奨買い目
    st.markdown("### 🎯 基本の推奨買い目")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("#### 3連単")
        buy_3tan = f"{top3[0]['pit_number']}-{top3[1]['pit_number']}-{top3[2]['pit_number']}"
        st.info(f"**{buy_3tan}**")
        st.caption("1着固定の推奨")

    with col2:
        st.markdown("#### 2連単")
        buy_2tan = f"{top3[0]['pit_number']}-{top3[1]['pit_number']}"
        st.info(f"**{buy_2tan}**")
        st.caption("1-2着の推奨")

    with col3:
        st.markdown("#### 単勝")
        buy_win = f"{top3[0]['pit_number']}号艇"
        st.info(f"**{buy_win}**")
        st.caption("1着の推奨")

    # 期待値分析セクション
    st.markdown("---")
    _render_expected_value_analysis(predictions, race_id, venue_code, race_date_str, race_number)

    # 詳細な買い目（フォーメーション）
    st.markdown("---")
    st.markdown("### 📋 フォーメーション買い目")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 3連単（1着固定）")
        first = top3[0]['pit_number']
        second_third = [top3[1]['pit_number'], top3[2]['pit_number']]

        formations = []
        for second in second_third:
            for third in second_third:
                if second != third:
                    formations.append(f"{first}-{second}-{third}")

        for formation in formations:
            st.write(f"• {formation}")

        st.caption(f"合計: {len(formations)}点")

    with col2:
        st.markdown("#### 3連複（ボックス）")
        box_numbers = [top3[0]['pit_number'], top3[1]['pit_number'], top3[2]['pit_number']]
        st.write(f"• {'-'.join(map(str, box_numbers))}")
        st.caption("3艇ボックス: 1点")

    # 購入金額シミュレーション
    st.markdown("---")
    st.markdown("### 💴 購入シミュレーション")

    col1, col2, col3 = st.columns(3)

    with col1:
        budget = st.number_input(
            "予算（円）",
            min_value=100,
            max_value=100000,
            value=1000,
            step=100,
            key="bet_budget"
        )

    with col2:
        bet_type = st.selectbox(
            "舟券種類",
            options=["3連単", "3連複", "2連単", "2連複", "単勝"],
            key="bet_type"
        )

    with col3:
        points = st.number_input(
            "購入点数",
            min_value=1,
            max_value=20,
            value=2 if bet_type == "3連単" else 1,
            key="bet_points"
        )

    # 1点あたりの金額
    per_point = int(budget / points / 100) * 100

    if per_point > 0:
        st.success(f"✅ 1点あたり: {per_point}円 × {points}点 = {per_point * points}円")
    else:
        st.warning("予算が少なすぎます")


def _render_detailed_analysis(race_id, race_date_str, venue_code, race_number, racers_df, race_grade):
    """詳細分析タブ（XAI等）"""
    st.subheader("🧠 詳細分析（XAI）")

    st.info("""
    **統合予測システム（Phase 1-3）**:
    - Phase 1: 最適化特徴量とハイパーパラメータ調整
    - Phase 2: アンサンブル予測と時系列特徴量
    - Phase 3: リアルタイム更新とXAI説明
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

    # 直前情報入力（オプション）
    use_latest_info = st.checkbox("直前情報を使用", value=False, key="use_latest_xai")

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
                    key=f"xai_ex_time_{pit}"
                )
                st_time = st.number_input(
                    f"ST",
                    min_value=-0.5,
                    max_value=0.5,
                    value=0.15,
                    step=0.01,
                    key=f"xai_st_time_{pit}"
                )

                latest_info_list.append({
                    'exhibition_time': exhibition_time,
                    'st_time': st_time,
                    'actual_course': pit
                })

    # 予測実行
    if st.button("🧠 詳細AI予測を実行（XAI付き）", type="primary"):
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
                st.session_state.xai_prediction_result = result

            except Exception as e:
                st.error(f"予測エラー: {e}")
                st.code(traceback.format_exc())
                return

    # 結果表示
    if 'xai_prediction_result' in st.session_state:
        result = st.session_state.xai_prediction_result

        # 予測結果テーブル
        st.markdown("---")
        st.markdown("### 📊 予測結果")

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
            st.markdown("---")
            st.markdown("### 🔍 レース分析")

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
            st.markdown("---")
            st.markdown("### ⚠️ 波乱分析")

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
            st.markdown("---")
            st.markdown("### 🧠 AI予測の根拠（XAI）")

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


def _render_expected_value_analysis(predictions, race_id, venue_code, race_date_str, race_number):
    """期待値ベースの分析と購入推奨"""
    st.markdown("### 📈 期待値分析（Kelly基準）")

    # オッズ入力
    st.markdown("#### オッズ入力（任意）")
    st.caption("オッズを入力すると期待値を計算します。未入力の場合は推定オッズを使用します。")

    top3 = predictions[:3]

    # 3連単の組み合わせを生成
    combinations_3tan = []
    first = top3[0]['pit_number']
    for second in [top3[1]['pit_number'], top3[2]['pit_number']]:
        for third in [top3[1]['pit_number'], top3[2]['pit_number']]:
            if second != third:
                combinations_3tan.append(f"{first}-{second}-{third}")

    # オッズ入力UI
    use_manual_odds = st.checkbox("オッズを手動入力", value=False, key="manual_odds_checkbox")

    odds_data = {}
    if use_manual_odds:
        cols = st.columns(len(combinations_3tan))
        for i, combo in enumerate(combinations_3tan):
            with cols[i]:
                odds = st.number_input(
                    f"{combo}",
                    min_value=1.0,
                    max_value=9999.0,
                    value=10.0,
                    step=0.1,
                    key=f"odds_{combo}"
                )
                odds_data[combo] = odds
    else:
        # 推定オッズ（スコアに基づいて逆算）
        st.info("💡 スコアに基づく推定オッズを使用中")
        total_score = sum(p['total_score'] for p in predictions)

        for combo in combinations_3tan:
            # 簡易的な推定（実際のオッズは異なる）
            parts = combo.split('-')
            first_score = next(p['total_score'] for p in predictions if p['pit_number'] == int(parts[0]))
            second_score = next(p['total_score'] for p in predictions if p['pit_number'] == int(parts[1]))
            third_score = next(p['total_score'] for p in predictions if p['pit_number'] == int(parts[2]))

            # スコアから確率を推定し、オッズに変換
            combo_score = first_score * 0.5 + second_score * 0.3 + third_score * 0.2
            estimated_prob = combo_score / total_score * 0.3  # 3連単なので確率は低い
            estimated_prob = max(0.01, min(0.30, estimated_prob))
            estimated_odds = 1.0 / estimated_prob * 0.75  # 控除率を考慮
            odds_data[combo] = round(estimated_odds, 1)

    # 期待値計算
    st.markdown("---")
    st.markdown("#### 📊 期待値計算結果")

    from src.betting.kelly_strategy import KellyBettingStrategy, ExpectedValueCalculator

    # 予測確率を計算（スコアからsoftmaxで変換）
    import numpy as np

    scores = np.array([p['total_score'] for p in predictions])
    temperature = 15.0
    exp_scores = np.exp(scores / temperature)
    base_probs = exp_scores / np.sum(exp_scores)

    # 各組み合わせの確率を計算
    pred_list = []
    for combo in combinations_3tan:
        parts = combo.split('-')
        first_idx = next(i for i, p in enumerate(predictions) if p['pit_number'] == int(parts[0]))
        second_idx = next(i for i, p in enumerate(predictions) if p['pit_number'] == int(parts[1]))
        third_idx = next(i for i, p in enumerate(predictions) if p['pit_number'] == int(parts[2]))

        # 3連単の確率 = 1着確率 × (2着確率 / 残り) × (3着確率 / 残り)
        p1 = base_probs[first_idx]
        remaining_after_1 = 1 - p1
        p2 = base_probs[second_idx] / remaining_after_1 if remaining_after_1 > 0 else 0
        remaining_after_2 = remaining_after_1 - base_probs[second_idx]
        p3 = base_probs[third_idx] / remaining_after_2 if remaining_after_2 > 0 else 0

        combo_prob = p1 * p2 * p3
        combo_prob = max(0.001, min(0.5, combo_prob))  # 範囲制限

        pred_list.append({
            'combination': combo,
            'prob': combo_prob
        })

    # Kelly戦略で分析
    budget = st.number_input(
        "資金（円）",
        min_value=1000,
        max_value=100000,
        value=10000,
        step=1000,
        key="ev_budget"
    )

    strategy = KellyBettingStrategy(
        bankroll=budget,
        kelly_fraction=0.25,
        min_ev=0.00  # すべて表示
    )

    # 期待値分析結果を表示
    results = []
    calc = ExpectedValueCalculator()

    for pred in pred_list:
        combo = pred['combination']
        prob = pred['prob']
        odds = odds_data.get(combo, 10.0)

        ev = strategy.calculate_expected_value(prob, odds)
        kelly_f, bet_amount = strategy.calculate_kelly_bet(prob, odds)
        breakeven_odds = calc.calculate_breakeven_odds(prob)
        edge = calc.calculate_edge(prob, odds)

        results.append({
            '買い目': combo,
            '予測確率': f"{prob*100:.2f}%",
            'オッズ': f"{odds:.1f}倍",
            '期待値': ev,
            '損益分岐': f"{breakeven_odds:.1f}倍",
            'エッジ': edge,
            '推奨': '◎' if ev > 0.10 else '○' if ev > 0 else '△' if ev > -0.10 else '×'
        })

    results_df = pd.DataFrame(results)

    # 期待値でソート
    results_df = results_df.sort_values('期待値', ascending=False)

    # 表示用に整形
    display_df = results_df.copy()
    display_df['期待値'] = display_df['期待値'].apply(lambda x: f"{x*100:+.1f}%")
    display_df['エッジ'] = display_df['エッジ'].apply(lambda x: f"{x:+.1f}%")

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # 推奨サマリー
    positive_ev = results_df[results_df['期待値'].apply(lambda x: x if isinstance(x, float) else float(x.replace('%', '').replace('+', '')) / 100) > 0]

    if len(positive_ev) > 0:
        st.success(f"✅ 期待値プラスの買い目: {len(positive_ev)}点")

        st.markdown("#### 💡 推奨買い目")
        for _, row in display_df.iterrows():
            if row['推奨'] in ['◎', '○']:
                st.write(f"**{row['買い目']}** - 期待値: {row['期待値']}, オッズ: {row['オッズ']}")
    else:
        st.warning("⚠️ 期待値プラスの買い目がありません。見送りを検討してください。")

    # Kelly基準による購入額
    with st.expander("📐 Kelly基準による購入額計算", expanded=False):
        st.markdown("""
        **Kelly基準とは:**
        - 長期的に資金を最大化するための賭け金配分理論
        - 期待値がプラスの買い目に対してのみ適用
        - 1/4 Kelly（推奨）でリスクを抑制
        """)

        for pred in pred_list:
            combo = pred['combination']
            prob = pred['prob']
            odds = odds_data.get(combo, 10.0)

            ev = strategy.calculate_expected_value(prob, odds)
            if ev > 0:
                kelly_f, bet_amount = strategy.calculate_kelly_bet(prob, odds)
                st.write(f"**{combo}**: 推奨購入額 ¥{bet_amount:,.0f} (Kelly分数: {kelly_f*100:.1f}%)")
