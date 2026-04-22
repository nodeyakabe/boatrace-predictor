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
from src.prediction.predictor_helpers import create_standard_predictor
from src.betting.bet_generator import BetGenerator
from src.betting.bet_target_evaluator import BetTargetEvaluator, BetTarget, BetStatus
from src.betting.multi_bet_generator import MultiBetPattern
from ui.components.common.widgets import render_confidence_badge
from ui.components.common.db_utils import safe_query_to_df
from config.settings import DATABASE_PATH


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

    # タブ構成（総合タブを最初に配置）
    tab0, tab1, tab2, tab3 = st.tabs(["📊 総合", "🎯 AI予測", "💰 買い目推奨", "🧠 詳細分析"])

    with tab0:
        _render_bet_target_summary(race_id, race_date_str, selected_venue_code, selected_race_number,
                                   racers_df, race_grade, predictions)

    with tab1:
        _render_ai_prediction(race_id, race_date_str, selected_venue_code, selected_race_number,
                            racers_df, race_grade, predictions)

    with tab2:
        _render_bet_recommendations(race_id, race_date_str, selected_venue_code, selected_race_number)

    with tab3:
        _render_detailed_analysis(race_id, race_date_str, selected_venue_code, selected_race_number,
                                racers_df, race_grade)


def _render_bet_target_summary(race_id, race_date_str, venue_code, race_number, racers_df, race_grade, existing_predictions=None):
    """総合タブ: 購入対象判定の表示"""
    st.subheader("📊 購入対象判定")

    # 1コース選手の情報を取得
    c1_entry = racers_df[racers_df['pit_number'] == 1].iloc[0] if len(racers_df[racers_df['pit_number'] == 1]) > 0 else None

    # 1コース選手の級別を取得
    c1_rank_query = """
        SELECT racer_rank FROM entries
        WHERE race_id = ? AND pit_number = 1
    """
    c1_rank_df = safe_query_to_df(c1_rank_query, params=(int(race_id),))
    c1_rank = c1_rank_df['racer_rank'].iloc[0] if c1_rank_df is not None and not c1_rank_df.empty else 'B1'

    # advance予測を取得（信頼度・top3取得 & advance/before一致フィルタ用）
    advance_query = """
        SELECT pit_number, rank_prediction, confidence, total_score
        FROM race_predictions
        WHERE race_id = ? AND prediction_type = 'advance'
        ORDER BY rank_prediction
    """
    advance_df = safe_query_to_df(advance_query, params=(int(race_id),))

    if advance_df is None or advance_df.empty:
        st.warning("予測データがありません。AI予測タブで予測を実行してください。")
        return

    advance_pits = advance_df['pit_number'].tolist()
    advance_top3 = advance_pits[:3] if len(advance_pits) >= 3 else None

    # before予測を取得（直前情報あり時はこちらが評価対象）
    before_query = """
        SELECT pit_number, rank_prediction, confidence, total_score
        FROM race_predictions
        WHERE race_id = ? AND prediction_type = 'before'
        ORDER BY rank_prediction
    """
    before_df = safe_query_to_df(before_query, params=(int(race_id),))
    has_beforeinfo = before_df is not None and not before_df.empty

    # 評価に使う予測を決定（before優先）
    eval_df = before_df if has_beforeinfo else advance_df
    confidence = eval_df['confidence'].iloc[0] if 'confidence' in eval_df.columns else 'D'
    eval_pits = eval_df['pit_number'].tolist()
    if len(eval_pits) < 3:
        st.warning("予測データが不足しています（3位以上の予測が必要）。")
        return

    top3_pits = eval_pits[:3]
    full_prediction = eval_pits[:6]
    # 6位まで補填
    for i in range(1, 7):
        if i not in full_prediction:
            full_prediction.append(i)

    old_combo = f"{top3_pits[0]}-{top3_pits[1]}-{top3_pits[2]}"

    # オッズを取得（fetched_atも取得して鮮度確認用）
    odds_query = """
        SELECT combination, odds, MAX(fetched_at) as fetched_at FROM trifecta_odds
        WHERE race_id = ?
        GROUP BY combination, odds
    """
    odds_df = safe_query_to_df(odds_query, params=(int(race_id),))
    odds_data = {row['combination']: row['odds'] for _, row in odds_df.iterrows()} if odds_df is not None and not odds_df.empty else {}

    # オッズ取得時刻を確認（最新のfetched_atを使用）
    odds_fetched_at = None
    if odds_df is not None and not odds_df.empty and 'fetched_at' in odds_df.columns:
        fetched_vals = odds_df['fetched_at'].dropna()
        if not fetched_vals.empty:
            odds_fetched_at = fetched_vals.max()

    old_odds = odds_data.get(old_combo, 0)

    # エントリー情報を取得（evaluate_race用）
    entries_query = """
        SELECT pit_number, racer_rank FROM entries WHERE race_id = ?
    """
    entries_df = safe_query_to_df(entries_query, params=(int(race_id),))
    entries_list = (
        [{'pit_number': r['pit_number'], 'racer_rank': r['racer_rank']}
         for _, r in entries_df.iterrows()]
        if entries_df is not None and not entries_df.empty else []
    )

    # 購入対象判定（evaluate_race: config/bet_conditions.py の全条件・advance_top3を使用）
    evaluator = BetTargetEvaluator(
        use_multi_bet=True,
        multi_bet_pattern=MultiBetPattern.PATTERN_H,
        enable_venue_wind_filter=True,
        enable_venue_course_adjustment=True,
        db_path=DATABASE_PATH
    )
    race_data_for_eval = {
        'venue_code': int(venue_code),
        'entries': entries_list,
        'race_date': race_date_str,
        'race_number': int(race_number),
        'id': int(race_id),
    }
    predictions_for_eval = {
        'confidence': confidence,
        'old_prediction': top3_pits,
        'new_prediction': top3_pits,
        'full_prediction': full_prediction,
    }
    # before予測がある場合のみadvance_top3を渡してフィルタを有効化
    adv_top3_param = advance_top3 if has_beforeinfo else None
    bet_target = evaluator.evaluate_race(
        race_data=race_data_for_eval,
        predictions=predictions_for_eval,
        odds_data=odds_data if odds_data else None,
        has_beforeinfo=has_beforeinfo,
        advance_top3=adv_top3_param,
    )

    # 詳細表示用に旧変数名を維持
    new_combo = old_combo
    new_odds = old_odds

    # 判定結果の表示
    st.markdown("### 判定結果")

    col1, col2 = st.columns([1, 2])

    with col1:
        # ステータスに応じたアイコンと色
        if bet_target.status == BetStatus.TARGET_ADVANCE:
            st.success("🟢 **対象（事前）**")
        elif bet_target.status == BetStatus.TARGET_CONFIRMED:
            st.success("🟢 **対象（確定）**")
        elif bet_target.status == BetStatus.CANDIDATE:
            st.warning("🟡 **候補**")
        else:
            st.info("⚪ **対象外**")

    with col2:
        st.markdown(f"**理由**: {bet_target.reason}")

    # 判定の詳細根拠を追加
    with st.expander("📋 判定根拠の詳細", expanded=False):
        st.markdown("### 参照した条件")

        # 方式の説明
        st.info("""
        **予測方式について:**
        - **advance（事前）予測**: レース前日までの情報（選手成績、モーター性能など）で予測
        - **before（直前）予測**: 展示タイム・STタイミングなど直前情報を加えて予測
        - **advance/before一致フィルタ**: 両予測のtop3が一致する場合のみ購入対象（一部条件に適用）
        """)

        # advance/before一致フィルタの状態を表示
        if has_beforeinfo and advance_top3 is not None:
            adv_str = '-'.join(map(str, advance_top3))
            bef_str = '-'.join(map(str, top3_pits))
            match_ok = adv_str == bef_str
            match_label = f"✅ 一致（{adv_str}）" if match_ok else f"⚠️ 不一致（advance: {adv_str} / before: {bef_str}）"
        else:
            match_label = "—（beforeなし・パススルー）"

        # オッズ取得時刻の警告
        odds_freshness_note = ""
        if odds_fetched_at:
            try:
                from datetime import datetime as _dt
                fetched_dt = _dt.fromisoformat(str(odds_fetched_at))
                minutes_ago = (_dt.now() - fetched_dt).total_seconds() / 60
                if minutes_ago > 30:
                    odds_freshness_note = f" ⚠️ **{int(minutes_ago)}分前のデータ（要更新）**"
                else:
                    odds_freshness_note = f" （{int(minutes_ago)}分前取得）"
            except Exception:
                pass

        st.markdown(f"""
        **検証項目:**
        - 信頼度: **{confidence}**
        - 1コース級別: **{c1_rank}**
        - 評価予測（{'before' if has_beforeinfo else 'advance'}）: **{old_combo}** → オッズ **{old_odds:.1f}倍**{odds_freshness_note}
        - advance/before一致: **{match_label}**
        - 直前情報: **{'取得済み（before予測で評価）' if has_beforeinfo else '未取得（advance予測で評価）'}**
        """)

        # 適用された法則を表示
        st.markdown("---")
        st.markdown("### 📜 適用された法則")

        try:
            import os
            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'boatrace.db')
            race_predictor = create_standard_predictor(db_path=db_path)
            applied_rules = race_predictor.get_applied_rules_by_key(
                race_date_str, venue_code, race_number
            )

            if applied_rules:
                st.markdown("""
                以下の法則は過去のレースデータから統計的に有意な勝率向上パターンとして抽出されたものです。
                各法則には「的中率」「適用条件」が設定され、条件を満たす場合にスコアが加算されます。
                """)

                for rule in applied_rules:
                    rule_type_icon = "🏟️" if rule['type'] == 'venue' else "👤"
                    effect_pct = rule.get('effect', 0) * 100

                    with st.container():
                        st.markdown(f"""
                        {rule_type_icon} **{rule['name']}**
                        - 種別: {rule['type']}
                        - 効果: +{effect_pct:.1f}%
                        - 説明: {rule.get('description', '統計的有意パターン')}
                        """)
            else:
                st.info("このレースに適用された特別な法則はありません（基本予測のみ）")

        except Exception as e:
            st.warning(f"適用法則の取得に失敗しました: {e}")

        st.markdown("---")
        st.markdown("### 購入条件との照合結果")

        # 条件別の判定詳細
        if bet_target.status in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
            st.success(f"""
            ✅ 購入条件を満たしました

            - 適用条件: **{bet_target.reason}**
            - 期待オッズ範囲: **{bet_target.odds_range}**
            - 実際のオッズ: **{bet_target.odds:.1f}倍**
            - 期待回収率: **{bet_target.expected_roi:.1f}%**
            """)
        elif bet_target.status == BetStatus.CANDIDATE:
            st.warning(f"""
            ⏳ 条件付きで購入候補

            - 条件: **{bet_target.reason}**
            - 必要オッズ範囲: **{bet_target.odds_range}**
            - 現在のオッズ: **{bet_target.odds:.1f}倍** (条件の80%以上)

            直前情報を取得後、以下が満たされれば購入対象に昇格:
            - 直前予測が事前予測を維持
            - オッズが条件範囲内に変動
            """)
        else:
            st.info(f"""
            ⚪ 購入条件を満たしませんでした

            - 理由: **{bet_target.reason}**

            以下のいずれかの理由で除外されました:
            - 信頼度が低い（E以下）
            - オッズが条件範囲外
            - 1コース級別が条件外（B2以下）
            - 会場×風速除外条件に該当
            """)

    # 詳細情報
    st.markdown("---")
    st.markdown("### 詳細情報")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**レース情報**")
        st.write(f"- 信頼度: **{confidence}**")
        st.write(f"- 1コース級別: **{c1_rank}**")
        st.write(f"- 直前情報: {'取得済み' if has_beforeinfo else '未取得'}")

    with col2:
        st.markdown("**予測買い目**")
        st.write(f"- 事前予測: **{old_combo}**")
        st.write(f"- 直前予測: **{new_combo}**")
        st.write(f"- 採用方式: **{bet_target.method}**")

    with col3:
        st.markdown("**オッズ情報**")
        st.write(f"- 事前予測買い目: **{old_odds:.1f}倍**" if old_odds else "- 事前予測買い目: 未取得")
        st.write(f"- 直前予測買い目: **{new_odds:.1f}倍**" if new_odds else "- 直前予測買い目: 未取得")
        st.write(f"- 条件オッズ範囲: **{bet_target.odds_range}**")

    # 購入対象の場合の推奨
    if bet_target.status in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
        st.markdown("---")
        st.markdown("### 💰 購入推奨")

        st.success(f"""
        **買い目**: {bet_target.combination}

        - 推奨賭け金: **{bet_target.bet_amount}円**
        - 期待回収率: **{bet_target.expected_roi:.1f}%**
        - オッズ: **{bet_target.odds:.1f}倍**
        """)

    elif bet_target.status == BetStatus.CANDIDATE:
        st.markdown("---")
        st.markdown("### ⏳ 直前情報待ち")

        st.warning(f"""
        **候補買い目**: {bet_target.combination}

        直前情報を取得後、オッズが **{bet_target.odds_range}** の範囲内であれば購入対象になります。

        → 「AI予測」タブの「直前予想を更新」ボタンで直前情報を取得してください。
        """)

    # レース結果を取得（終了レースの場合）
    result_query = """
        SELECT pit_number, rank
        FROM results
        WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
        ORDER BY rank
    """
    result_df = safe_query_to_df(result_query, params=(int(race_id),))

    if result_df is not None and len(result_df) >= 3:
        # レース終了
        st.markdown("---")
        st.markdown("### 🏁 レース結果")

        actual_1st = result_df[result_df['rank'] == 1]['pit_number'].iloc[0]
        actual_2nd = result_df[result_df['rank'] == 2]['pit_number'].iloc[0]
        actual_3rd = result_df[result_df['rank'] == 3]['pit_number'].iloc[0]
        actual_combo = f"{actual_1st}-{actual_2nd}-{actual_3rd}"

        # 払戻金を取得
        payout_query = """
            SELECT bet_type, combination, amount
            FROM payouts
            WHERE race_id = ?
        """
        payout_df = safe_query_to_df(payout_query, params=(int(race_id),))

        col_r1, col_r2 = st.columns([1, 2])

        with col_r1:
            st.markdown(f"**確定着順**: 🥇{actual_1st} - 🥈{actual_2nd} - 🥉{actual_3rd}")

            # 的中判定
            if bet_target.status in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
                if bet_target.combination == actual_combo:
                    st.success("🎉 **的中！**")
                else:
                    st.error("❌ **不的中**")

        with col_r2:
            if payout_df is not None and not payout_df.empty:
                st.markdown("**払戻金**")
                payout_data = []
                for _, row in payout_df.iterrows():
                    bet_type_name = {
                        'trifecta': '3連単',
                        'trio': '3連複',
                        'exacta': '2連単',
                        'quinella': '2連複',
                        'win': '単勝',
                        'place': '複勝'
                    }.get(row['bet_type'], row['bet_type'])

                    payout_data.append({
                        '券種': bet_type_name,
                        '組み合わせ': row['combination'] if row['combination'] else '-',
                        '払戻': f"¥{int(row['amount']):,}"
                    })

                st.dataframe(pd.DataFrame(payout_data), use_container_width=True, hide_index=True)

                # 3連単の払戻金を表示
                trifecta_payout = payout_df[payout_df['bet_type'] == 'trifecta']
                if not trifecta_payout.empty:
                    trifecta_amount = int(trifecta_payout['amount'].iloc[0])
                    st.info(f"3連単 **{actual_combo}** → **¥{trifecta_amount:,}**")

        # 収支計算（購入対象だった場合）
        if bet_target.status in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
            st.markdown("---")
            st.markdown("### 💹 収支")

            if bet_target.combination == actual_combo:
                # 的中時
                trifecta_payout = payout_df[payout_df['bet_type'] == 'trifecta']
                if not trifecta_payout.empty:
                    payout_amount = int(trifecta_payout['amount'].iloc[0])
                    # 100円あたりの払戻金なので、賭け金に応じて計算
                    returns = int(payout_amount * bet_target.bet_amount / 100)
                    profit = returns - bet_target.bet_amount
                    roi = returns / bet_target.bet_amount * 100

                    col_s1, col_s2, col_s3 = st.columns(3)
                    with col_s1:
                        st.metric("投資額", f"¥{bet_target.bet_amount:,}")
                    with col_s2:
                        st.metric("払戻額", f"¥{returns:,}")
                    with col_s3:
                        st.metric("収支", f"¥{profit:+,}", delta=f"{roi:.1f}%")
            else:
                # 不的中時
                col_s1, col_s2, col_s3 = st.columns(3)
                with col_s1:
                    st.metric("投資額", f"¥{bet_target.bet_amount:,}")
                with col_s2:
                    st.metric("払戻額", "¥0")
                with col_s3:
                    st.metric("収支", f"¥{-bet_target.bet_amount:,}", delta="-100%")

    # 購入条件の説明
    with st.expander("📖 購入条件の詳細", expanded=False):
        st.markdown("""
        ### 最終運用戦略（Opus分析確定版）

        | 信頼度 | 方式 | オッズ範囲 | 追加条件 | 期待回収率 | 賭け金 |
        |--------|------|------------|----------|------------|--------|
        | **C** | 従来 | 30-60倍 | 1コースA1級 | **127.2%** | 500円 |
        | **C** | 従来 | 50倍+ | 1コースA級 | **121.0%** | 500円 |
        | **D** | 新方式 | 30倍+ | 1コースA級 | **209.1%** | 300円 |
        | **D** | 新方式 | 20倍+ | 1コースA級 | **178.9%** | 300円 |

        ### 購入見送り条件

        - 信頼度A・B: サンプル不足で統計的に不安定
        - 1コースB級以下: 回収率が低い
        - オッズ20倍未満: 期待値不足
        """)


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
        race_predictor = create_standard_predictor()

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

    # 選手名をracers_dfから補完（predictionに選手名がない場合）
    racer_name_map = {row['pit_number']: row['racer_name'] for _, row in racers_df.iterrows()}
    for pred in predictions:
        if not pred.get('racer_name') or pred.get('racer_name') == '選手名不明':
            pred['racer_name'] = racer_name_map.get(pred['pit_number'], '選手名不明')

    # 予想結果（6人全員をテーブル表示）
    st.markdown("### 🏆 予想結果")

    # テーブル形式でコンパクトに表示
    prediction_data = []
    for i, pred in enumerate(predictions, 1):
        medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}位"
        score = pred.get('total_score', pred.get('score', 0))
        confidence_level = pred.get('confidence', 'C')

        # パターン情報を取得
        pattern_multiplier = pred.get('pattern_multiplier', 1.0)
        matched_patterns = pred.get('matched_patterns', [])
        has_negative = pred.get('has_negative_pattern', False)

        # パターンボーナス表示
        if pattern_multiplier > 1.0:
            pattern_display = f"×{pattern_multiplier:.3f} 🔥"
        elif has_negative:
            pattern_display = "⚠️ 注意"
        else:
            pattern_display = "-"

        prediction_data.append({
            '順位': medal,
            '艇番': f"{pred['pit_number']}号艇",
            '選手名': pred.get('racer_name', '選手名不明'),
            'スコア': f"{score:.1f}",
            'パターン': pattern_display,
            '信頼度': render_confidence_badge(confidence_level)
        })

    pred_df = pd.DataFrame(prediction_data)
    st.dataframe(pred_df, use_container_width=True, hide_index=True)

    # パターンボーナス詳細（Phase 3: パターン情報表示）
    with st.expander("🔥 BEFOREパターンボーナス詳細", expanded=False):
        st.markdown("**BEFOREパターンシステム**: 展示タイム × STタイミング × 予測順位の組み合わせで有利パターンを検出")
        st.markdown("")

        pattern_details = []
        for i, pred in enumerate(predictions, 1):
            pit_number = pred['pit_number']
            pattern_multiplier = pred.get('pattern_multiplier', 1.0)
            matched_patterns = pred.get('matched_patterns', [])
            has_negative = pred.get('has_negative_pattern', False)
            negative_patterns = pred.get('negative_patterns', [])

            # パターン情報を整形
            if pattern_multiplier > 1.0:
                # ポジティブパターン
                pattern_str = f"🔥 {matched_patterns[0] if matched_patterns else 'unknown'}"
                effect_str = f"+{(pattern_multiplier - 1.0) * 100:.1f}%"
            elif has_negative:
                # ネガティブパターン
                pattern_str = f"⚠️ {', '.join(negative_patterns) if negative_patterns else '要注意'}"
                effect_str = f"{(pattern_multiplier - 1.0) * 100:.1f}%"
            else:
                pattern_str = "-"
                effect_str = "-"

            pattern_details.append({
                '艇番': pit_number,
                '選手': pred.get('racer_name', '選手名不明')[:6],
                'パターン': pattern_str,
                '効果': effect_str,
                '倍率': f"×{pattern_multiplier:.3f}" if pattern_multiplier != 1.0 else "-"
            })

        pattern_df = pd.DataFrame(pattern_details)
        st.dataframe(pattern_df, use_container_width=True, hide_index=True)

        # パターン適用状況のサマリー
        positive_count = sum(1 for pred in predictions if pred.get('pattern_multiplier', 1.0) > 1.0)
        negative_count = sum(1 for pred in predictions if pred.get('has_negative_pattern', False))

        st.markdown(f"""
        **適用状況**:
        - ポジティブパターン検出: {positive_count}艇
        - ネガティブパターン検出: {negative_count}艇
        - パターン未適用: {len(predictions) - positive_count - negative_count}艇
        """)

    # 展示データ詳細（DBから取得）
    with st.expander("📊 展示ST・展示タイム詳細", expanded=False):
        # DBから展示データを取得（entriesからavg_stも取得）
        exhibition_query = """
            SELECT
                rd.pit_number,
                e.racer_name,
                rd.exhibition_time,
                e.avg_st,
                rd.tilt_angle
            FROM race_details rd
            JOIN entries e ON rd.race_id = e.race_id AND rd.pit_number = e.pit_number
            WHERE rd.race_id = ?
            ORDER BY rd.pit_number
        """
        # race_idを確実に整数に変換
        race_id_int = int(race_id) if race_id else None
        ex_df = safe_query_to_df(exhibition_query, params=(race_id_int,))

        if ex_df is not None and not ex_df.empty:
            # 展示タイムで順位付け（小さいほうが良い）
            ex_df['展示T順位'] = ex_df['exhibition_time'].rank(method='min').fillna(0).astype(int).replace(0, '-')

            # 表示用に整形
            display_data = []
            for _, row in ex_df.iterrows():
                display_data.append({
                    '艇番': int(row['pit_number']),
                    '選手': row['racer_name'][:6] if row['racer_name'] else '-',
                    '展示T順位': row['展示T順位'] if pd.notna(row['exhibition_time']) else '-',
                    '展示T': f"{row['exhibition_time']:.2f}" if pd.notna(row['exhibition_time']) else '-',
                    '平均ST': f"{row['avg_st']:.2f}" if pd.notna(row['avg_st']) else '-',
                    'チルト': f"{row['tilt_angle']:.1f}" if pd.notna(row['tilt_angle']) else '-',
                })

            st.dataframe(pd.DataFrame(display_data), use_container_width=True, hide_index=True)
        else:
            st.info("展示データはまだ取得されていません")

    # 参照データの詳細を追加
    st.markdown("---")
    st.markdown("### 📊 予測で参照したデータ")

    with st.expander("📋 参照データ詳細", expanded=True):
        st.markdown("""
        AI予測システムは以下のデータを総合的に分析して予測を生成しています:
        """)

        # 選手データ
        st.markdown("#### 👤 選手データ")
        entry_query = """
            SELECT
                e.pit_number,
                e.racer_name,
                e.racer_rank,
                e.nationwide_win_rate,
                e.nationwide_second_rate,
                e.local_win_rate,
                e.local_second_rate,
                e.motor_second_rate,
                e.boat_second_rate,
                e.avg_st
            FROM entries e
            WHERE e.race_id = ?
            ORDER BY e.pit_number
        """
        entry_df = safe_query_to_df(entry_query, params=(int(race_id),))

        if entry_df is not None and not entry_df.empty:
            display_entry = entry_df.copy()
            display_entry.columns = ['艇番', '選手名', '級別', '全国勝率', '全国2連率', '当地勝率', '当地2連率', 'モーター2連率', 'ボート2連率', '平均ST']
            st.dataframe(display_entry, use_container_width=True, hide_index=True)

            st.caption("※ 勝率・2連率は選手の実力を、モーター・ボート2連率は機材の性能を表します")
        else:
            st.warning("選手データが取得できませんでした")

        # レース条件データ
        st.markdown("#### 🌊 レース条件データ")
        condition_query = """
            SELECT
                weather,
                wind_direction,
                wind_speed,
                wave_height,
                water_temperature,
                air_temperature
            FROM race_conditions
            WHERE race_id = ?
        """
        condition_df = safe_query_to_df(condition_query, params=(int(race_id),))

        if condition_df is not None and not condition_df.empty:
            cond = condition_df.iloc[0]
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("天候", cond['weather'] if pd.notna(cond['weather']) else "不明")
                st.metric("風向", cond['wind_direction'] if pd.notna(cond['wind_direction']) else "不明")

            with col2:
                st.metric("風速", f"{cond['wind_speed']:.1f}m" if pd.notna(cond['wind_speed']) else "不明")
                st.metric("波高", f"{cond['wave_height']:.1f}cm" if pd.notna(cond['wave_height']) else "不明")

            with col3:
                st.metric("水温", f"{cond['water_temperature']:.1f}℃" if pd.notna(cond['water_temperature']) else "不明")
                st.metric("気温", f"{cond['air_temperature']:.1f}℃" if pd.notna(cond['air_temperature']) else "不明")

            st.caption("※ 風速・風向は予測精度に大きく影響します。特に風速5m以上の場合はレース展開が変わりやすくなります")
        else:
            st.info("レース条件データが取得できませんでした")

        # 展示データ（直前情報）
        if has_beforeinfo:
            st.markdown("#### 🏁 展示データ（直前情報）")
            exhibition_query = """
                SELECT
                    rd.pit_number,
                    e.racer_name,
                    rd.exhibition_time,
                    rd.tilt_angle
                FROM race_details rd
                JOIN entries e ON rd.race_id = e.race_id AND rd.pit_number = e.pit_number
                WHERE rd.race_id = ?
                ORDER BY rd.pit_number
            """
            ex_df = safe_query_to_df(exhibition_query, params=(int(race_id),))

            if ex_df is not None and not ex_df.empty:
                # 展示タイム順位を計算
                ex_df['展示T順位'] = ex_df['exhibition_time'].rank(method='min').fillna(0).astype(int)

                display_ex = []
                for _, row in ex_df.iterrows():
                    display_ex.append({
                        '艇番': int(row['pit_number']),
                        '選手': row['racer_name'][:6],
                        '展示T': f"{row['exhibition_time']:.2f}" if pd.notna(row['exhibition_time']) else '-',
                        '展示T順位': f"{int(row['展示T順位'])}位" if row['展示T順位'] > 0 else '-',
                        'チルト': f"{row['tilt_angle']:.1f}°" if pd.notna(row['tilt_angle']) else '-'
                    })

                st.dataframe(pd.DataFrame(display_ex), use_container_width=True, hide_index=True)
                st.caption("※ 展示タイムはモーター性能とスタート力の指標です。上位選手が有利になる傾向があります")

        # 会場特性データ
        st.markdown("#### 🏟️ 会場特性")
        venue_query = """
            SELECT name, place, is_seawater FROM venues WHERE code = ?
        """
        venue_df = safe_query_to_df(venue_query, params=(selected_venue_code,))

        if venue_df is not None and not venue_df.empty:
            venue_info = venue_df.iloc[0]
            col1, col2 = st.columns(2)

            with col1:
                st.write(f"**会場名**: {venue_info['name']}")
                st.write(f"**所在地**: {venue_info['place']}")

            with col2:
                water_type = "海水" if venue_info['is_seawater'] == 1 else "淡水"
                st.write(f"**水質**: {water_type}")
                st.write(f"**会場コード**: {selected_venue_code}")

            st.caption("※ 海水/淡水、インコース有利度などの会場特性が予測に影響します")

    # 判断根拠（適用法則）
    st.markdown("---")
    st.markdown("### 🔍 判断根拠（適用法則）")

    with st.expander("📜 適用された法則一覧", expanded=True):
        st.markdown("""
        以下の法則は過去のレースデータから統計的に有意な勝率向上パターンとして抽出されたものです。
        各法則には「的中率」「適用条件」が設定され、条件を満たす場合にスコアが加算されます。
        """)

        try:
            import os
            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'boatrace.db')
            race_predictor = create_standard_predictor(db_path=db_path)
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

                st.markdown("""
                ---
                **法則の読み方:**
                - **%値**: その法則がスコアに与える影響度（プラスが大きいほど有利）
                - **🏟️**: 会場特有の傾向（例: 風向×コース）
                - **👤**: 選手の特性に基づく法則（例: A1級×1コース）
                """)
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

    # =====================================================
    # 階層的確率モデルによる三連単予測（NEW）
    # =====================================================
    st.markdown("### 🎯 AI三連単予測（階層的確率モデル）")

    # 階層的モデルで予測
    try:
        from src.prediction.hierarchical_predictor import HierarchicalPredictor
        import os

        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'boatrace.db')
        hierarchical_predictor = HierarchicalPredictor(db_path)
        hierarchical_predictor.load_models()

        if hierarchical_predictor._model_loaded:
            # 予測実行
            h_result = hierarchical_predictor.predict_race(race_id)

            if 'error' not in h_result:
                # 上位10件の三連単を表示
                top_trifecta = h_result.get('top_combinations', [])[:10]

                if top_trifecta:
                    st.success("✅ 学習済み条件付きモデルによる予測")

                    # 確率分布の可視化
                    trifecta_data = []
                    for i, (combo, prob) in enumerate(top_trifecta, 1):
                        rank_emoji = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}位"
                        trifecta_data.append({
                            '順位': rank_emoji,
                            '三連単': combo,
                            '確率': f"{prob * 100:.2f}%",
                            '確率値': prob
                        })

                    trifecta_df = pd.DataFrame(trifecta_data)

                    # テーブル表示
                    st.dataframe(
                        trifecta_df[['順位', '三連単', '確率']],
                        use_container_width=True,
                        hide_index=True
                    )

                    # 各艇の1着/2着/3着確率
                    st.markdown("#### 📊 各艇の順位別確率")
                    rank_probs = h_result.get('rank_probs', {})
                    if rank_probs:
                        rank_data = []
                        for pit in range(1, 7):
                            if pit in rank_probs:
                                rank_data.append({
                                    '艇番': f"{pit}号艇",
                                    '1着確率': f"{rank_probs[pit].get(1, 0) * 100:.1f}%",
                                    '2着確率': f"{rank_probs[pit].get(2, 0) * 100:.1f}%",
                                    '3着確率': f"{rank_probs[pit].get(3, 0) * 100:.1f}%",
                                })
                        st.dataframe(pd.DataFrame(rank_data), use_container_width=True, hide_index=True)

                    # 推奨買い目（上位5点）
                    st.markdown("#### 🎯 推奨買い目（確率上位5点）")
                    for i, (combo, prob) in enumerate(top_trifecta[:5], 1):
                        if i == 1:
                            st.info(f"**① {combo}** ({prob*100:.2f}%) ← 本命")
                        else:
                            st.write(f"{'②③④⑤'[i-2]} {combo} ({prob*100:.2f}%)")

                    # =====================================================
                    # 三連複予測（三連単確率から計算）
                    # =====================================================
                    st.markdown("---")
                    st.markdown("### 🎲 AI三連複予測")

                    from src.prediction.trifecta_calculator import calculate_trio_from_trifecta, get_top_trio
                    trifecta_probs = h_result.get('trifecta_probs', {})

                    if trifecta_probs:
                        top_trio = get_top_trio(trifecta_probs, top_n=10)

                        trio_data = []
                        for idx_t, (combo, prob) in enumerate(top_trio, 1):
                            rank_emoji = ["🥇", "🥈", "🥉"][idx_t-1] if idx_t <= 3 else f"{idx_t}位"
                            trio_data.append({
                                '順位': rank_emoji,
                                '三連複': combo,
                                '確率': f"{prob * 100:.2f}%",
                            })

                        st.dataframe(
                            pd.DataFrame(trio_data),
                            use_container_width=True,
                            hide_index=True
                        )

                        st.caption("※ 三連複は三連単の確率を順不同で合計して計算")


                    # =====================================================
                    # 2連単/2連複予測
                    # =====================================================
                    st.markdown("---")
                    st.markdown("### 🎰 AI 2連単/2連複予測")

                    from src.prediction.trifecta_calculator import (
                        calculate_exacta_from_trifecta, get_top_exacta,
                        calculate_quinella_from_trifecta, get_top_quinella
                    )

                    col_ex, col_qu = st.columns(2)

                    with col_ex:
                        st.markdown("**2連単 TOP10**")
                        top_exacta = get_top_exacta(trifecta_probs, top_n=10)
                        exacta_data = []
                        for idx_e, (combo, prob) in enumerate(top_exacta, 1):
                            rank_emoji = ["🥇", "🥈", "🥉"][idx_e-1] if idx_e <= 3 else f"{idx_e}位"
                            exacta_data.append({
                                '順位': rank_emoji,
                                '2連単': combo,
                                '確率': f"{prob * 100:.2f}%",
                            })
                        st.dataframe(pd.DataFrame(exacta_data), use_container_width=True, hide_index=True)

                    with col_qu:
                        st.markdown("**2連複 TOP10**")
                        top_quinella = get_top_quinella(trifecta_probs, top_n=10)
                        quinella_data = []
                        for idx_q, (combo, prob) in enumerate(top_quinella, 1):
                            rank_emoji = ["🥇", "🥈", "🥉"][idx_q-1] if idx_q <= 3 else f"{idx_q}位"
                            quinella_data.append({
                                '順位': rank_emoji,
                                '2連複': combo,
                                '確率': f"{prob * 100:.2f}%",
                            })
                        st.dataframe(pd.DataFrame(quinella_data), use_container_width=True, hide_index=True)

                    # =====================================================
                    # 期待値分析（階層的モデルの確率を使用）
                    # =====================================================
                    st.markdown("---")
                    st.markdown("### 📈 期待値分析（階層的モデル）")

                    use_ev_analysis = st.checkbox("オッズを入力して期待値計算", value=False, key="hierarchical_ev_checkbox")

                    if use_ev_analysis and trifecta_probs:
                        st.caption("オッズを入力すると、階層的モデルの予測確率に基づいて期待値を計算します")

                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown("**三連単オッズ**")
                            trifecta_odds = {}
                            for idx_o, (combo, prob) in enumerate(top_trifecta[:5]):
                                odds = st.number_input(
                                    f"{combo}",
                                    min_value=1.0,
                                    max_value=9999.0,
                                    value=round(1.0 / max(prob, 0.001) * 0.75, 1),
                                    step=0.1,
                                    key=f"h_odds_tan_{idx_o}"
                                )
                                trifecta_odds[combo] = odds

                        with col2:
                            st.markdown("**三連複オッズ**")
                            trio_odds = {}
                            for idx_o, (combo, prob) in enumerate(top_trio[:5]):
                                odds = st.number_input(
                                    f"{combo}",
                                    min_value=1.0,
                                    max_value=9999.0,
                                    value=round(1.0 / max(prob, 0.001) * 0.75, 1),
                                    step=0.1,
                                    key=f"h_odds_fuku_{idx_o}"
                                )
                                trio_odds[combo] = odds

                        # 期待値計算
                        st.markdown("#### 📊 期待値計算結果")

                        ev_results = []
                        for combo, odds in trifecta_odds.items():
                            prob = trifecta_probs.get(combo, 0)
                            ev = prob * odds - 1
                            ev_results.append({
                                '種別': '三連単',
                                '買い目': combo,
                                '確率': f"{prob*100:.2f}%",
                                'オッズ': odds,
                                '期待値': f"{ev*100:+.1f}%",
                                'ev_value': ev
                            })

                        trio_probs_dict = calculate_trio_from_trifecta(trifecta_probs)
                        for combo, odds in trio_odds.items():
                            prob = trio_probs_dict.get(combo, 0)
                            ev = prob * odds - 1
                            ev_results.append({
                                '種別': '三連複',
                                '買い目': combo,
                                '確率': f"{prob*100:.2f}%",
                                'オッズ': odds,
                                '期待値': f"{ev*100:+.1f}%",
                                'ev_value': ev
                            })

                        ev_df = pd.DataFrame(ev_results)
                        ev_df = ev_df.sort_values('ev_value', ascending=False)

                        st.dataframe(
                            ev_df[['種別', '買い目', '確率', 'オッズ', '期待値']],
                            use_container_width=True,
                            hide_index=True
                        )

                        # プラス期待値の買い目
                        positive_ev = ev_df[ev_df['ev_value'] > 0]
                        if len(positive_ev) > 0:
                            st.success(f"✅ 期待値プラスの買い目: {len(positive_ev)}点")
                            for _, row in positive_ev.iterrows():
                                st.write(f"  **{row['種別']} {row['買い目']}** - 期待値: {row['期待値']}")
                        else:
                            st.warning("⚠️ 期待値プラスの買い目がありません。オッズ妙味が低い可能性があります。")


                else:
                    st.warning("三連単予測を生成できませんでした")
            else:
                error_msg = h_result.get('error', '')
                if 'レースデータ取得失敗' in error_msg:
                    st.info("💡 直前情報（展示タイム等）が未取得のため、階層的モデルは使用できません。下記の従来予測をご参照ください。")
                else:
                    st.warning(f"予測エラー: {error_msg}")
                _render_traditional_bets(predictions, key_prefix="fallback")
        else:
            st.info("💡 階層的モデルが読み込まれていません。従来の予測を使用します。")
            _render_traditional_bets(predictions, key_prefix="no_model")

    except Exception as e:
        st.warning(f"階層的モデルエラー: {e}")
        _render_traditional_bets(predictions, key_prefix="error")

    st.markdown("---")

    # =====================================================
    # 従来の買い目（比較用）- 階層的モデル成功時のみexpander表示
    # =====================================================
    with st.expander("📋 従来の買い目（スコア順）", expanded=False):
        _render_traditional_bets(predictions, key_prefix="expander")


def _render_traditional_bets(predictions, key_prefix: str = "main"):
    """従来のスコアベース買い目

    Args:
        predictions: 予測データ
        key_prefix: Streamlitウィジェットのキープレフィックス（重複防止用）
    """
    top3 = predictions[:3]

    first = top3[0]['pit_number']
    second = top3[1]['pit_number']
    third = top3[2]['pit_number']

    # 5点の買い目
    trifecta_bets = [
        f"{first}-{second}-{third}",
        f"{first}-{third}-{second}",
        f"{second}-{first}-{third}",
        f"{second}-{third}-{first}",
        f"{third}-{first}-{second}",
    ]

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 3連単 5点")
        for i, bet in enumerate(trifecta_bets, 1):
            if i == 1:
                st.info(f"**① {bet}** ← 本命")
            else:
                st.write(f"② {bet}" if i == 2 else f"③ {bet}" if i == 3 else f"④ {bet}" if i == 4 else f"⑤ {bet}")

    with col2:
        st.markdown("#### 3連複（BOX）")
        trio_bet = f"{first}={second}={third}"
        st.info(f"**{trio_bet}**")
        st.caption("3艇ボックス: 1点")

        st.markdown("#### 2連単")
        st.write(f"• {first}-{second}")
        st.write(f"• {first}-{third}")

    st.success(f"📊 合計: 3連単5点 + 3連複1点 = **6点**")

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
            key=f"bet_budget_{key_prefix}"
        )

    with col2:
        bet_type = st.selectbox(
            "舟券種類",
            options=["3連単", "3連複", "2連単", "2連複", "単勝"],
            key=f"bet_type_{key_prefix}"
        )

    with col3:
        points = st.number_input(
            "購入点数",
            min_value=1,
            max_value=20,
            value=2 if bet_type == "3連単" else 1,
            key=f"bet_points_{key_prefix}"
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
    **このタブの機能**:
    - 展示タイム・スタートタイミングを**手動入力**して詳細予測
    - AI予測の根拠（有利・不利な要因）を可視化
    - 各選手の強み・弱みを定量的に分析
    - ※「AI予測」タブの直前予想更新ボタンとは別機能です
    """)

    st.markdown("---")
    st.markdown("### 📚 XAI（説明可能AI）とは")

    with st.expander("ℹ️ XAIの説明", expanded=False):
        st.markdown("""
        **XAI（Explainable AI）** は、AIの予測結果を人間が理解できる形で説明する技術です。

        **このシステムでは以下を可視化します:**

        1. **SHAP値分析**
           - 各特徴量（選手の成績、モーター性能など）が予測にどれだけ貢献したか
           - プラス要因（有利な要素）とマイナス要因（不利な要素）を分離表示

        2. **特徴量の重要度**
           - どのデータ（全国勝率、モーター2連率、展示タイムなど）が予測に影響したか
           - 上位の重要特徴量を抽出して表示

        3. **予測の確信度**
           - AIがどれだけ確信を持って予測したか
           - 不確実性が高い場合は警告を表示

        **活用方法:**
        - 本命選手の強み・弱みを確認
        - 穴馬の有利要因を発見
        - 予測の信頼性を判断
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

            st.markdown("""
            各選手の予測根拠を詳細に分析します。**有利な要因**と**不利な要因**を定量的に表示し、
            なぜその予測になったのかを明確にします。
            """)

            # 予測順にソート（確率が高い順）
            sorted_explanations = sorted(
                result['explanations'],
                key=lambda x: predictions_df[predictions_df['pit_number'] == x['pit_number']]['probability'].iloc[0] if len(predictions_df[predictions_df['pit_number'] == x['pit_number']]) > 0 else 0,
                reverse=True
            )

            for idx, explanation in enumerate(sorted_explanations, 1):
                pit = explanation['pit_number']
                racer = explanation['racer_name']

                # 予測確率を取得
                pred_prob = predictions_df[predictions_df['pit_number'] == pit]['probability'].iloc[0] if len(predictions_df[predictions_df['pit_number'] == pit]) > 0 else 0

                # 順位アイコン
                rank_icon = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣"][idx - 1]

                with st.expander(f"{rank_icon} {pit}号艇: {racer} （予測勝率: {pred_prob*100:.2f}%）", expanded=(idx <= 3)):
                    st.markdown(f"#### 総合評価")
                    st.markdown(explanation['explanation_text'])

                    col1, col2 = st.columns(2)

                    # 有利・不利要因を可視化
                    with col1:
                        if explanation['explanation'].get('top_positive_factors'):
                            st.markdown("#### ✅ 有利な要因")
                            positive_df = pd.DataFrame(
                                explanation['explanation']['top_positive_factors'],
                                columns=['特徴量', '寄与度']
                            )
                            positive_df['寄与度'] = positive_df['寄与度'].apply(lambda x: f"+{x*100:.2f}%")
                            st.dataframe(positive_df, hide_index=True, use_container_width=True)

                            # 最も影響の大きい要因を強調
                            if len(explanation['explanation']['top_positive_factors']) > 0:
                                top_factor = explanation['explanation']['top_positive_factors'][0]
                                st.success(f"💡 **最大の強み**: {top_factor[0]}")
                        else:
                            st.info("有利な要因が検出されませんでした")

                    with col2:
                        if explanation['explanation'].get('top_negative_factors'):
                            st.markdown("#### ❌ 不利な要因")
                            negative_df = pd.DataFrame(
                                explanation['explanation']['top_negative_factors'],
                                columns=['特徴量', '寄与度']
                            )
                            negative_df['寄与度'] = negative_df['寄与度'].apply(lambda x: f"{x*100:.2f}%")
                            st.dataframe(negative_df, hide_index=True, use_container_width=True)

                            # 最も影響の大きい弱点を強調
                            if len(explanation['explanation']['top_negative_factors']) > 0:
                                top_factor = explanation['explanation']['top_negative_factors'][0]
                                st.warning(f"⚠️ **最大の弱み**: {top_factor[0]}")
                        else:
                            st.info("不利な要因が検出されませんでした")

                    # 要因の解説を追加
                    st.markdown("---")
                    st.markdown("#### 📊 要因の解説")

                    with st.expander("各特徴量の意味", expanded=False):
                        st.markdown("""
                        | 特徴量 | 説明 | 影響度 |
                        |--------|------|--------|
                        | 全国勝率 | 選手の全国での勝利実績 | ⭐⭐⭐ |
                        | 全国2連率 | 全国での2着以内率 | ⭐⭐⭐ |
                        | モーター2連率 | モーターの性能指標 | ⭐⭐⭐ |
                        | 当地勝率 | この会場での勝利実績 | ⭐⭐ |
                        | 当地2連率 | この会場での2着以内率 | ⭐⭐ |
                        | 展示タイム | 展示航走のタイム | ⭐⭐ |
                        | 平均ST | スタートタイミング平均 | ⭐⭐ |
                        | ボート2連率 | ボートの性能指標 | ⭐ |

                        **評価基準:**
                        - ⭐⭐⭐: 予測に大きく影響
                        - ⭐⭐: 中程度の影響
                        - ⭐: 補助的な影響
                        """)

            # 全体のサマリー
            st.markdown("---")
            st.markdown("### 📈 予測サマリー")

            summary_col1, summary_col2, summary_col3 = st.columns(3)

            with summary_col1:
                top_racer = sorted_explanations[0]
                st.metric(
                    "本命",
                    f"{top_racer['pit_number']}号艇",
                    f"{top_racer['racer_name']}"
                )

            with summary_col2:
                # 有利要因の平均数
                avg_positive = sum(len(e['explanation'].get('top_positive_factors', [])) for e in result['explanations']) / len(result['explanations'])
                st.metric("平均有利要因数", f"{avg_positive:.1f}個")

            with summary_col3:
                # 不利要因の平均数
                avg_negative = sum(len(e['explanation'].get('top_negative_factors', [])) for e in result['explanations']) / len(result['explanations'])
                st.metric("平均不利要因数", f"{avg_negative:.1f}個")


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
        total_score = sum(p.get('total_score', p.get('score', 50)) for p in predictions)

        for combo in combinations_3tan:
            # 簡易的な推定（実際のオッズは異なる）
            parts = combo.split('-')
            first_score = next(p.get('total_score', p.get('score', 50)) for p in predictions if p['pit_number'] == int(parts[0]))
            second_score = next(p.get('total_score', p.get('score', 50)) for p in predictions if p['pit_number'] == int(parts[1]))
            third_score = next(p.get('total_score', p.get('score', 50)) for p in predictions if p['pit_number'] == int(parts[2]))

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

    scores = np.array([p.get('total_score', p.get('score', 50)) for p in predictions])
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
