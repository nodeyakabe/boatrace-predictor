"""
予想ビューアコンポーネント
"""
import streamlit as st
import pandas as pd
from src.analysis.race_predictor import RacePredictor
from ui.components.common.widgets import render_confidence_badge

# 予測説明モジュール
try:
    from src.ml.prediction_explainer import PredictionExplainer
    HAS_EXPLAINER = True
except ImportError:
    HAS_EXPLAINER = False

# 複数パターン予測モジュール
try:
    from src.prediction.multi_pattern_predictor import MultiPatternPredictor
    HAS_MULTI_PATTERN = True
except ImportError:
    HAS_MULTI_PATTERN = False

# 2段階買い目生成モジュール
try:
    from src.prediction.betting_strategy import BettingStrategyEngine
    HAS_BETTING_STRATEGY = True
except ImportError:
    HAS_BETTING_STRATEGY = False


def render_prediction_viewer(race_date, venue_code, race_number):
    """予想詳細ビューア"""
    st.subheader(f"🎯 予想詳細")

    try:
        race_predictor = RacePredictor()

        # 予想生成
        predictions = race_predictor.predict_race_by_key(
            race_date, venue_code, race_number
        )

        if not predictions or len(predictions) < 3:
            st.warning("予想データを生成できませんでした")
            return

        # トップ3予想
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
                    score = pred.get('total_score', pred.get('score', 50))
                    st.metric("スコア", f"{score:.1f}")

                with col4:
                    confidence = pred.get('total_score', pred.get('score', 50))
                    badge = render_confidence_badge(confidence)
                    st.markdown(f"**{badge}**")

                st.markdown("---")

        # 全艇の予想
        with st.expander("📊 全艇の予想スコア"):
            df = pd.DataFrame([{
                '艇番': p['pit_number'],
                '選手': p.get('racer_name', '選手名不明'),
                'スコア': f"{p.get('total_score', p.get('score', 50)):.2f}",
                '順位': i+1
            } for i, p in enumerate(predictions)])

            st.dataframe(df, use_container_width=True, hide_index=True)

        # 詳細な予測根拠（PredictionExplainer使用）
        if HAS_EXPLAINER:
            with st.expander("🔬 各艇の詳細分析", expanded=False):
                try:
                    explainer = PredictionExplainer("data/boatrace.db")

                    # 選択した艇の詳細
                    selected_pit = st.selectbox(
                        "詳細を見る艇番",
                        options=[p['pit_number'] for p in predictions],
                        format_func=lambda x: f"{x}号艇 - {next((p.get('racer_name', '選手名不明') for p in predictions if p['pit_number'] == x), '不明')}"
                    )

                    # 選択した艇の予測データを作成
                    selected_pred = next((p for p in predictions if p['pit_number'] == selected_pit), None)

                    if selected_pred:
                        # モデル予測確率を正規化スコアから推定
                        model_prob = selected_pred.get('total_score', selected_pred.get('score', 50)) / 100

                        # 予測データを構築
                        pred_data = {
                            'venue_code': venue_code,
                            'pit_number': selected_pit,
                            'racer_name': selected_pred.get('racer_name', '不明'),
                            'racer_rank': selected_pred.get('racer_rank', ''),
                            'nation_win_rate': selected_pred.get('win_rate', 0),
                            'local_win_rate': selected_pred.get('local_win_rate', 0),
                            'motor_2ren_rate': selected_pred.get('motor_second_rate', 0),
                            'boat_2ren_rate': selected_pred.get('boat_second_rate', 0),
                        }

                        # 説明生成
                        explanation = explainer.explain_prediction(pred_data, model_prob)

                        # 表示
                        st.markdown(f"#### {selected_pit}号艇 {pred_data['racer_name']}")

                        # 確率表示
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("モデル予測", f"{explanation['model_probability']:.1f}%")
                        with col2:
                            adj = explanation['total_adjustment']
                            st.metric("調整値", f"{adj:+.1f}%")
                        with col3:
                            st.metric("最終予測", f"{explanation['adjusted_probability']:.1f}%")

                        # 要因リスト
                        st.markdown("##### 予測要因")
                        for factor in explanation.get('factors', []):
                            sentiment = factor.get('sentiment', 'neutral')
                            if sentiment == 'positive':
                                icon = "✅"
                            elif sentiment == 'negative':
                                icon = "⚠️"
                            else:
                                icon = "ℹ️"

                            adj = factor.get('adjustment', 0)
                            if adj != 0:
                                adj_str = f" ({adj*100:+.1f}%)"
                            else:
                                adj_str = ""

                            st.write(f"{icon} **{factor['category']}**: {factor['description']}{adj_str}")

                        # 評価サマリー
                        st.info(f"**総合評価**: {explanation.get('summary', '')}")

                except Exception as e:
                    st.warning(f"詳細分析エラー: {e}")

        # 適用法則
        st.markdown("---")
        st.markdown("### 🔍 判断根拠（適用法則）")

        try:
            applied_rules = race_predictor.get_applied_rules_by_key(
                race_date, venue_code, race_number
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

        # 推奨買い目（2段階構造）
        st.markdown("---")
        st.markdown("### 💰 推奨買い目")

        if HAS_BETTING_STRATEGY:
            try:
                betting_engine = BettingStrategyEngine("data/boatrace.db")

                # 確率閾値選択
                min_prob = st.slider(
                    "最低確率閾値",
                    min_value=0.5,
                    max_value=5.0,
                    value=1.0,
                    step=0.5,
                    format="%.1f%%"
                ) / 100

                # タブで3連単と3連複を切り替え
                tab1, tab2 = st.tabs(["3連単", "3連複"])

                with tab1:
                    # 3連単パターン生成
                    trifecta_patterns = betting_engine.generate_betting_patterns(
                        predictions,
                        min_probability=min_prob,
                        max_patterns=15
                    )

                    if trifecta_patterns:
                        # カテゴリ別に表示
                        categories = {}
                        for p in trifecta_patterns:
                            if p.category not in categories:
                                categories[p.category] = []
                            categories[p.category].append(p)

                        for category in ["本命", "対抗", "抑え", "穴"]:
                            if category not in categories:
                                continue

                            st.markdown(f"**【{category}】**")
                            for p in categories[category]:
                                tri = f"{p.trifecta[0]}-{p.trifecta[1]}-{p.trifecta[2]}"

                                col1, col2 = st.columns([3, 1])
                                with col1:
                                    st.markdown(
                                        f"{p.confidence} **{tri}**",
                                    )
                                with col2:
                                    st.write(f"{p.probability*100:.1f}%")

                                # 根拠を展開パネルで表示
                                with st.expander("根拠", expanded=False):
                                    for reason in p.reasons:
                                        st.write(f"• {reason}")

                        # 合計点数と確率
                        total_prob = sum(p.probability for p in trifecta_patterns)
                        st.info(f"**合計 {len(trifecta_patterns)}点** (的中確率: {total_prob*100:.1f}%)")

                    else:
                        st.warning("買い目を生成できませんでした")

                with tab2:
                    # 3連複パターン生成
                    trio_patterns = betting_engine.generate_trifecta_combinations(
                        predictions,
                        min_probability=min_prob
                    )

                    if trio_patterns:
                        for p in trio_patterns[:10]:
                            tri = f"{p.trifecta[0]}-{p.trifecta[1]}-{p.trifecta[2]}"

                            col1, col2 = st.columns([3, 1])
                            with col1:
                                st.markdown(f"{p.confidence} **{tri}**")
                            with col2:
                                st.write(f"{p.probability*100:.1f}%")

                        # 合計
                        total_prob = sum(p.probability for p in trio_patterns[:10])
                        st.info(f"**合計 {min(10, len(trio_patterns))}点** (的中確率: {total_prob*100:.1f}%)")

                    else:
                        st.warning("3連複を生成できませんでした")

            except Exception as e:
                st.warning(f"買い目生成エラー: {e}")
                import traceback
                st.code(traceback.format_exc())
        else:
            # フォールバック：従来の簡易表示
            buy_recommendation = f"{top3[0]['pit_number']}-{top3[1]['pit_number']}-{top3[2]['pit_number']}"
            st.info(f"**本命 3連単**: {buy_recommendation}")

            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**2連単**: {top3[0]['pit_number']}-{top3[1]['pit_number']}")
            with col2:
                st.write(f"**単勝**: {top3[0]['pit_number']}号艇")

    except Exception as e:
        st.error(f"エラー: {e}")
        import traceback
        st.code(traceback.format_exc())


def render_multiple_predictions(race_list):
    """複数レースの予想を一覧表示"""
    st.subheader("📋 複数レース予想一覧")

    try:
        race_predictor = RacePredictor()
        predictions_summary = []

        for race in race_list:
            race_date = race['date']
            venue_code = race['venue_code']
            race_number = race['race_number']

            try:
                predictions = race_predictor.predict_race_by_key(
                    race_date, venue_code, race_number
                )

                if predictions and len(predictions) >= 3:
                    top3 = predictions[:3]
                    confidence = top3[0].get('total_score', top3[0].get('score', 50))

                    predictions_summary.append({
                        '会場': race.get('venue_name', venue_code),
                        'レース': f"{race_number}R",
                        '時刻': race.get('race_time', '-'),
                        '1着': f"{top3[0]['pit_number']}号艇",
                        '2着': f"{top3[1]['pit_number']}号艇",
                        '3着': f"{top3[2]['pit_number']}号艇",
                        '信頼度': f"{confidence:.1f}%",
                        'スコア': confidence
                    })
            except Exception:
                continue

        if predictions_summary:
            # スコアでソート
            predictions_summary.sort(key=lambda x: x['スコア'], reverse=True)

            # データフレーム表示
            df = pd.DataFrame([{k: v for k, v in p.items() if k != 'スコア'}
                             for p in predictions_summary])
            st.dataframe(df, use_container_width=True, hide_index=True)

            st.success(f"✅ {len(predictions_summary)}レースの予想を生成しました")
        else:
            st.warning("予想を生成できたレースがありません")

    except Exception as e:
        st.error(f"エラー: {e}")
