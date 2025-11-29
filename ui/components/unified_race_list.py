"""
統合レース一覧画面
今日のレース推奨を一覧表示（的中率重視/期待値重視）
"""
import streamlit as st
import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional
import logging

from src.analysis.realtime_predictor import RealtimePredictor
from src.analysis.race_predictor import RacePredictor
from src.betting.bet_generator import BetGenerator
from src.betting.race_scorer import RaceScorer
from src.prediction.integrated_kimarite_predictor import IntegratedKimaritePredictor
from ui.components.common.widgets import render_confidence_badge

logger = logging.getLogger(__name__)


def render_unified_race_list():
    """統合レース一覧画面を表示"""
    st.header("🔮 レース予想一覧")

    # タブ作成：的中率重視 / 期待値重視
    tab1, tab2 = st.tabs(["🎯 的中率重視", "💰 期待値重視"])

    with tab1:
        _render_accuracy_focused()

    with tab2:
        _render_value_focused()


def _render_accuracy_focused():
    """的中率重視タブ - 保存済み予想から上位20レースを表示"""
    st.subheader("📊 信頼度の高いおすすめレース TOP20")
    st.caption("保存済みの予想データから、信頼度が高い上位20レースを表示します")

    # 日付選択
    target_date = st.date_input(
        "対象日",
        value=datetime.now().date(),
        key="accuracy_date"
    )

    # 保存済み予想データを取得
    try:
        import sqlite3
        from config.settings import DATABASE_PATH, VENUES

        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        target_date_str = target_date.strftime('%Y-%m-%d')

        # 会場名マッピング
        venue_name_map = {}
        for venue_id, venue_info in VENUES.items():
            venue_name_map[venue_info['code']] = venue_info['name']

        # レース情報と予想スコアを取得（信頼度順）
        # 信頼度優先: A>B>C>D でソートし、同じ信頼度なら最高スコア順
        cursor.execute("""
            SELECT
                r.id as race_id,
                r.venue_code,
                r.race_number,
                r.race_time,
                r.race_date,
                AVG(rp.total_score) as avg_score,
                MAX(rp.total_score) as max_score,
                MIN(CASE rp.confidence
                    WHEN 'A' THEN 1
                    WHEN 'B' THEN 2
                    WHEN 'C' THEN 3
                    WHEN 'D' THEN 4
                    ELSE 5
                END) as best_confidence_rank,
                GROUP_CONCAT(rp.pit_number || ':' || rp.rank_prediction || ':' || rp.total_score || ':' || rp.confidence, '|') as predictions_data
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id
            WHERE r.race_date = ?
            GROUP BY r.id
            ORDER BY best_confidence_rank ASC, max_score DESC
            LIMIT 20
        """, (target_date_str,))

        race_rows = cursor.fetchall()

        if not race_rows:
            st.warning(f"{target_date_str} のレース予想が見つかりませんでした")
            st.info("「データ準備」タブで「今日の予測を生成」を実行してください")
            conn.close()
            return

        st.success(f"📊 本日の上位20レースを表示中 ({len(race_rows)}件)")

        # レースカードデータを作成
        recommended_races = []

        for row in race_rows:
            race_id, venue_code, race_number, race_time, race_date, avg_score, max_score, best_confidence_rank, predictions_data = row

            # 予想データをパース
            predictions = []
            for pred_str in predictions_data.split('|'):
                parts = pred_str.split(':')
                if len(parts) == 4:
                    pit_number, rank_pred, score, confidence = parts
                    predictions.append({
                        'pit_number': int(pit_number),
                        'rank': int(rank_pred),
                        'score': float(score),
                        'confidence': confidence
                    })

            # 予想を順位でソート
            predictions.sort(key=lambda x: x['rank'])

            # 上位3艇を抽出
            top3 = predictions[:3]

            # 2段階戦略の買い目を生成
            if len(top3) >= 3:
                first = top3[0]['pit_number']
                second = top3[1]['pit_number']
                third = top3[2]['pit_number']

                # 3連単（5点）: 1着固定、2-3着流し
                trifecta_bets = [
                    f"{first}-{second}-{third}",
                    f"{first}-{third}-{second}",
                    f"{second}-{first}-{third}",
                    f"{second}-{third}-{first}",
                    f"{third}-{first}-{second}",
                ]

                # 3連複（1点）: BOX
                trio_bet = f"{first}={second}={third}"

                # メイン買い目（本命）
                main_bet = f"{first}-{second}-{third}"

                # 表示用テキスト
                bet_display = f"3連単{len(trifecta_bets)}点 + 3連複1点"
            else:
                trifecta_bets = []
                trio_bet = ""
                main_bet = '-'.join([str(p['pit_number']) for p in top3])
                bet_display = main_bet

            # 信頼度の計算: 上位3艇の信頼度レベルから算出
            # A=100%, B=80%, C=60%, D=40%, E=20%
            confidence_map = {'A': 100, 'B': 80, 'C': 60, 'D': 40, 'E': 20}
            top3_confidences = [confidence_map.get(p['confidence'], 50) for p in top3 if 'confidence' in p]

            if top3_confidences:
                # 上位3艇の信頼度の加重平均（1着重視）
                weights = [0.5, 0.3, 0.2]
                confidence = sum(c * w for c, w in zip(top3_confidences, weights[:len(top3_confidences)]))
            else:
                # フォールバック: スコアベース
                confidence = min(100, max(20, avg_score * 8))

            recommended_races.append({
                '会場': venue_name_map.get(venue_code, f'会場{venue_code}'),
                'レース': f"{race_number}R",
                '時刻': race_time or '未定',
                '本命': f"{top3[0]['pit_number']}号艇" if top3 else '-',
                '買い目': main_bet,
                '買い目表示': bet_display,
                '3連単': trifecta_bets,
                '3連複': trio_bet,
                '買い目詳細': [f"{p['pit_number']}号艇" for p in top3],
                '信頼度': confidence,
                '平均スコア': avg_score,
                'badge': render_confidence_badge(confidence),
                'race_id': race_id,
                'race_date': race_date,
                'venue_code': venue_code,
                'race_number': race_number,
                'predictions': predictions
            })

        conn.close()

        # レースカード表示
        _render_race_cards_v2(recommended_races)

        # 全レース一覧テーブル
        st.markdown("---")
        st.subheader("📋 全レース一覧")

        df_data = []
        for i, r in enumerate(recommended_races, 1):
            df_data.append({
                '順位': i,
                '会場': r['会場'],
                'レース': r['レース'],
                '時刻': r['時刻'],
                '買い目': r.get('買い目表示', r['買い目']),
                '3連単': ', '.join(r.get('3連単', [])[:3]) if r.get('3連単') else '-',
                '3連複': r.get('3連複', '-'),
                '信頼度': f"{r['信頼度']:.1f}%",
                'スコア': f"{r['平均スコア']:.2f}"
            })

        df = pd.DataFrame(df_data)
        st.dataframe(df, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"エラーが発生しました: {e}")
        import traceback
        st.code(traceback.format_exc())


def _render_value_focused():
    """期待値重視タブ - オッズと予測確率から期待値を計算"""
    st.subheader("💰 期待値重視のおすすめレース")
    st.caption("期待値 = 予測勝率 × オッズ。期待値 > 1.0 なら長期的にプラス収支が期待できる買い目")

    # 日付選択
    target_date = st.date_input(
        "対象日",
        value=datetime.now().date(),
        key="value_date"
    )

    # 期待値の説明
    with st.expander("📊 期待値とは？"):
        st.markdown("""
        **期待値（EV: Expected Value）の計算:**
        ```
        期待値 = 予測勝率 × オッズ
        ```

        - **期待値 > 1.0**: 長期的にプラス収支が期待できる
        - **期待値 = 1.0**: 収支トントン
        - **期待値 < 1.0**: 長期的にマイナス収支

        **例:**
        - 予測勝率30%、オッズ4.0倍 → 期待値 = 0.30 × 4.0 = **1.20** ✅
        - 予測勝率50%、オッズ1.5倍 → 期待値 = 0.50 × 1.5 = **0.75** ❌

        **重み設定（期待値重視モード）:**
        - コース: 25点（的中率重視は50点）→ コース過大評価を抑制
        - 選手: 35点（的中率重視は30点）
        - モーター: 20点（的中率重視は10点）
        - 決まり手: 15点（的中率重視は5点）
        """)

    # 期待値計算のためオッズデータを確認
    try:
        import sqlite3
        from config.settings import DATABASE_PATH, VENUES

        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        target_date_str = target_date.strftime('%Y-%m-%d')

        # オッズデータの有無を確認
        cursor.execute("""
            SELECT COUNT(*) FROM win_odds wo
            JOIN races r ON wo.race_id = r.id
            WHERE r.race_date = ?
        """, (target_date_str,))
        odds_count = cursor.fetchone()[0]

        # 会場名マッピング
        venue_name_map = {}
        for venue_id, venue_info in VENUES.items():
            venue_name_map[venue_info['code']] = venue_info['name']

        if odds_count == 0:
            # オッズデータがない場合
            st.warning("⚠️ オッズデータがありません")
            st.markdown("""
            **期待値計算にはオッズデータが必要です。**

            期待値 = 予測勝率 × オッズ

            オッズデータを取得するには：
            1. 「データ準備」タブで「オッズ取得」を実行
            2. または自動オッズ取得を有効化

            ---
            **暫定表示**: 期待値重視モードの予測スコアを表示します（オッズなし）
            """)

            # ボタン押下で予測を実行（遅延実行）
            if st.button("🔮 予測を生成", key="generate_value_predictions"):
                _render_value_predictions_without_odds(target_date_str, venue_name_map, cursor, conn)
            else:
                st.info("「予測を生成」ボタンを押すと、全レースの予測を生成します（時間がかかる場合があります）")
                conn.close()
        else:
            # オッズデータがある場合 - 期待値計算を実行
            st.success(f"✅ オッズデータ: {odds_count}件")

            # ボタン押下で予測を実行（遅延実行）
            if st.button("🔮 期待値計算を実行", key="generate_ev_predictions"):
                _render_value_predictions_with_odds(target_date_str, venue_name_map, cursor, conn)
            else:
                st.info("「期待値計算を実行」ボタンを押すと、全レースの期待値を計算します（時間がかかる場合があります）")
                conn.close()

    except Exception as e:
        st.error(f"エラーが発生しました: {e}")
        import traceback
        st.code(traceback.format_exc())


def _render_value_predictions_without_odds(target_date_str: str, venue_name_map: dict, cursor, conn):
    """オッズなしで期待値重視モードの予測を表示"""
    # 今日のレース一覧を取得
    cursor.execute("""
        SELECT id, venue_code, race_number, race_time, race_date
        FROM races
        WHERE race_date = ?
        ORDER BY race_time, venue_code, race_number
    """, (target_date_str,))

    race_rows = cursor.fetchall()

    if not race_rows:
        st.warning(f"{target_date_str} のレースデータが見つかりませんでした")
        conn.close()
        return

    # 期待値重視モードの予測を生成
    predictor = RacePredictor(mode='value')

    recommended_races = []

    progress_bar = st.progress(0)
    for i, row in enumerate(race_rows):
        race_id, venue_code, race_number, race_time, race_date = row

        try:
            predictions = predictor.predict_race(race_id)

            if not predictions:
                continue

            top3 = predictions[:3]

            if len(top3) >= 3:
                first = top3[0]['pit_number']
                second = top3[1]['pit_number']
                third = top3[2]['pit_number']
                main_bet = f"{first}-{second}-{third}"
            else:
                first = top3[0]['pit_number'] if top3 else 0
                main_bet = '-'.join([str(p['pit_number']) for p in top3])

            # 予測確率を計算（スコアから簡易変換）
            total_score = sum(p.get('total_score', p.get('score', 50)) for p in predictions)
            if total_score > 0:
                win_prob = top3[0].get('total_score', top3[0].get('score', 50)) / total_score
            else:
                win_prob = 0.0

            recommended_races.append({
                '会場': venue_name_map.get(venue_code, f'会場{venue_code}'),
                'レース': f"{race_number}R",
                '時刻': race_time or '未定',
                '本命': f"{first}号艇",
                '買い目': main_bet,
                '予測確率': win_prob,
                'スコア': top3[0].get('total_score', top3[0].get('score', 0)) if top3 else 0,
                'race_id': race_id,
                'race_date': race_date,
                'venue_code': venue_code,
                'race_number': race_number,
            })

        except Exception as e:
            logger.warning(f"レース {race_id} の予測でエラー: {e}")
            continue

        progress_bar.progress((i + 1) / len(race_rows))

    progress_bar.empty()
    conn.close()

    if not recommended_races:
        st.warning("予測可能なレースがありませんでした")
        return

    # スコア順にソート
    recommended_races.sort(key=lambda x: -x['スコア'])

    st.info(f"📊 {len(recommended_races)}レースを期待値重視モードで予測（オッズ未取得）")

    # テーブル表示
    df_data = []
    for i, r in enumerate(recommended_races[:30], 1):
        df_data.append({
            '順位': i,
            '会場': r['会場'],
            'レース': r['レース'],
            '時刻': r['時刻'],
            '本命': r['本命'],
            '買い目': r['買い目'],
            '予測確率': f"{r['予測確率']*100:.1f}%",
            'スコア': f"{r['スコア']:.1f}",
            '期待値': "オッズ必要"
        })

    df = pd.DataFrame(df_data)
    st.dataframe(df, use_container_width=True, hide_index=True)


def _render_value_predictions_with_odds(target_date_str: str, venue_name_map: dict, cursor, conn):
    """オッズありで期待値計算を実行"""
    # レースとオッズを取得
    cursor.execute("""
        SELECT r.id, r.venue_code, r.race_number, r.race_time, r.race_date,
               wo.pit_number, wo.odds
        FROM races r
        JOIN win_odds wo ON r.id = wo.race_id
        WHERE r.race_date = ?
        ORDER BY r.race_time, r.venue_code, r.race_number, wo.pit_number
    """, (target_date_str,))

    rows = cursor.fetchall()

    if not rows:
        st.warning("オッズデータの取得に失敗しました")
        conn.close()
        return

    # レースごとにオッズをグループ化
    race_odds = {}
    for row in rows:
        race_id, venue_code, race_number, race_time, race_date, pit_number, odds = row
        if race_id not in race_odds:
            race_odds[race_id] = {
                'venue_code': venue_code,
                'race_number': race_number,
                'race_time': race_time,
                'race_date': race_date,
                'odds': {}
            }
        race_odds[race_id]['odds'][pit_number] = odds

    conn.close()

    # 期待値重視モードで予測
    predictor = RacePredictor(mode='value')

    ev_bets = []  # 期待値 > 1.0 の買い目

    progress_bar = st.progress(0)
    race_ids = list(race_odds.keys())

    for i, race_id in enumerate(race_ids):
        race_info = race_odds[race_id]
        odds_dict = race_info['odds']

        try:
            predictions = predictor.predict_race(race_id)

            if not predictions:
                continue

            # 予測確率を計算（スコアをsoftmaxで確率に変換）
            import math
            scores = [p.get('total_score', p.get('score', 50)) for p in predictions]
            max_score = max(scores)
            exp_scores = [math.exp((s - max_score) / 10) for s in scores]  # 温度10
            sum_exp = sum(exp_scores)
            probs = {p['pit_number']: exp_scores[i] / sum_exp for i, p in enumerate(predictions)}

            # 各艇の期待値を計算
            for pit_number, prob in probs.items():
                if pit_number in odds_dict:
                    odds = odds_dict[pit_number]
                    if odds and odds > 0:
                        expected_value = prob * odds

                        if expected_value > 1.0:  # 期待値プラスの買い目
                            ev_bets.append({
                                '会場': venue_name_map.get(race_info['venue_code'], f"会場{race_info['venue_code']}"),
                                'レース': f"{race_info['race_number']}R",
                                '時刻': race_info['race_time'] or '未定',
                                '艇番': f"{pit_number}号艇",
                                '予測確率': prob,
                                'オッズ': odds,
                                '期待値': expected_value,
                                'race_id': race_id,
                                'race_date': race_info['race_date'],
                                'venue_code': race_info['venue_code'],
                                'race_number': race_info['race_number'],
                            })

        except Exception as e:
            logger.warning(f"レース {race_id} の期待値計算でエラー: {e}")
            continue

        progress_bar.progress((i + 1) / len(race_ids))

    progress_bar.empty()

    if not ev_bets:
        st.warning("期待値 > 1.0 の買い目が見つかりませんでした")
        st.info("予測確率とオッズの乖離が小さいか、オッズが妥当な水準です")
        return

    # 期待値順にソート
    ev_bets.sort(key=lambda x: -x['期待値'])

    st.success(f"🎯 期待値 > 1.0 の買い目: {len(ev_bets)}件")

    # 上位の期待値買い目を表示
    st.markdown("### 💰 期待値プラスの推奨買い目 TOP20")

    df_data = []
    for i, bet in enumerate(ev_bets[:20], 1):
        ev = bet['期待値']
        ev_badge = "🔥🔥" if ev >= 1.5 else "🔥" if ev >= 1.2 else "✅"
        df_data.append({
            '順位': i,
            '会場': bet['会場'],
            'レース': bet['レース'],
            '時刻': bet['時刻'],
            '買い目': bet['艇番'],
            '予測確率': f"{bet['予測確率']*100:.1f}%",
            'オッズ': f"{bet['オッズ']:.1f}倍",
            '期待値': f"{ev:.2f} {ev_badge}",
        })

    df = pd.DataFrame(df_data)
    st.dataframe(df, use_container_width=True, hide_index=True)


def _render_race_cards_v2(race_list: List[Dict]):
    """レースカードを表示（改善版）"""

    for idx, race in enumerate(race_list, 1):
        confidence = race['信頼度']

        # スコアに応じた背景色
        if confidence >= 80:
            border_color = "#ff6b6b"  # 赤（最高）
            bg_color = "#ffe0e0"
        elif confidence >= 70:
            border_color = "#ffa500"  # オレンジ（高）
            bg_color = "#fff4e0"
        elif confidence >= 60:
            border_color = "#4ecdc4"  # 青緑（中）
            bg_color = "#e0f4f4"
        else:
            border_color = "#95a5a6"  # グレー（低）
            bg_color = "#f0f0f0"

        # カードのスタイル
        with st.container():
            col1, col2, col3, col4, col5 = st.columns([0.5, 2, 2.5, 2, 1])

            with col1:
                st.markdown(f"### {idx}")

            with col2:
                st.markdown(f"**{race['会場']} {race['レース']}**")
                st.caption(f"⏰ {race['時刻']}")

            with col3:
                # 複数買い目を表示
                st.markdown(f"🎯 **買い目: {race['買い目表示']}**")
                # 3連単と3連複を表示
                if race.get('3連単'):
                    trifecta_str = ', '.join(race['3連単'][:3])
                    if len(race['3連単']) > 3:
                        trifecta_str += f" 他{len(race['3連単'])-3}点"
                    st.caption(f"3連単: {trifecta_str}")
                if race.get('3連複'):
                    st.caption(f"3連複: {race['3連複']}")

            with col4:
                st.markdown(f"**{race['badge']}**")
                st.caption(f"信頼度: {confidence:.1f}% | スコア: {race['平均スコア']:.2f}")

            with col5:
                # 詳細ボタン
                if st.button("詳細 →", key=f"detail_v2_{idx}", use_container_width=True):
                    # セッションステートに選択レース情報を保存
                    st.session_state.selected_race = {
                        'race_date': race['race_date'],
                        'venue_code': race['venue_code'],
                        'race_number': race['race_number'],
                        'predictions': race.get('predictions')
                    }
                    st.session_state.show_detail = True
                    st.rerun()

            st.markdown("---")


def _render_race_cards(race_list: List[Dict], mode: str = "accuracy"):
    """レースカードを表示（旧版）"""

    for idx, race in enumerate(race_list, 1):
        confidence = race['信頼度']

        # スコアに応じた背景色
        if confidence >= 80:
            border_color = "#ff6b6b"  # 赤（最高）
            bg_color = "#ffe0e0"
        elif confidence >= 70:
            border_color = "#ffa500"  # オレンジ（高）
            bg_color = "#fff4e0"
        elif confidence >= 60:
            border_color = "#4ecdc4"  # 青緑（中）
            bg_color = "#e0f4f4"
        else:
            border_color = "#95a5a6"  # グレー（低）
            bg_color = "#f0f0f0"

        # カードのスタイル
        card_style = f"""
        <style>
        .race-card-{idx} {{
            border: 2px solid {border_color};
            border-radius: 10px;
            padding: 15px;
            margin: 10px 0;
            background-color: {bg_color};
        }}
        </style>
        """
        st.markdown(card_style, unsafe_allow_html=True)

        # カード内容
        with st.container():
            st.markdown(f'<div class="race-card-{idx}">', unsafe_allow_html=True)

            # ヘッダー行
            col1, col2, col3, col4, col5 = st.columns([1, 2, 2, 2, 1])

            with col1:
                st.markdown(f"### #{idx}")

            with col2:
                st.markdown(f"**{race['会場']} {race['レース']}**")
                st.caption(f"⏰ {race['時刻']}")

            with col3:
                # 複数買い目を表示
                if '買い目リスト' in race:
                    bet_list = race['買い目リスト']
                    main_bet = bet_list[0] if bet_list else ''
                    st.markdown(f"🎯 **本命: {main_bet}**")
                    if len(bet_list) > 1:
                        st.caption(f"他{len(bet_list)-1}点: {', '.join(bet_list[1:3])}")
                else:
                    st.markdown(f"🎯 **{race.get('1着', '')}-{race.get('2着', '')}-{race.get('3着', '')}**")

            with col4:
                st.markdown(f"**{race['badge']}**")
                st.caption(f"信頼度: {confidence:.1f}%")

            with col5:
                # 詳細ボタン
                if st.button("詳細", key=f"detail_{idx}"):
                    # セッションステートに選択レース情報を保存
                    st.session_state.selected_race = {
                        'race_date': race['race_date'],
                        'venue_code': race['venue_code'],
                        'race_number': race['race_number'],
                        'predictions': race.get('predictions')
                    }
                    st.session_state.show_detail = True
                    st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)
            st.markdown("---")


def check_and_show_detail():
    """詳細画面を表示するかチェック"""
    if st.session_state.get('show_detail', False):
        return True
    return False


def get_selected_race():
    """選択されたレース情報を取得"""
    return st.session_state.get('selected_race', None)


def clear_selected_race():
    """選択レース情報をクリア"""
    if 'show_detail' in st.session_state:
        st.session_state.show_detail = False
    if 'selected_race' in st.session_state:
        del st.session_state.selected_race
