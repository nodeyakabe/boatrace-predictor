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

        # レース情報と予想スコアを取得（上位20件）
        cursor.execute("""
            SELECT
                r.id as race_id,
                r.venue_code,
                r.race_number,
                r.race_time,
                r.race_date,
                AVG(rp.total_score) as avg_score,
                GROUP_CONCAT(rp.pit_number || ':' || rp.rank_prediction || ':' || rp.total_score || ':' || rp.confidence, '|') as predictions_data
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id
            WHERE r.race_date = ?
            GROUP BY r.id
            ORDER BY avg_score DESC
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
            race_id, venue_code, race_number, race_time, race_date, avg_score, predictions_data = row

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
    """期待値重視タブ - オッズベースの期待値計算"""
    st.subheader("💰 期待値重視のおすすめレース")
    st.caption("オッズと予測確率から期待値を計算し、高期待値レースを推奨します")

    # 日付選択
    target_date = st.date_input(
        "対象日",
        value=datetime.now().date(),
        key="value_date"
    )

    # 期待値閾値設定
    col1, col2 = st.columns(2)
    with col1:
        min_ev = st.slider(
            "最小期待値 (%)",
            min_value=-50,
            max_value=50,
            value=5,
            step=5,
            help="期待値がこの値以上のレースのみ表示"
        )
    with col2:
        min_confidence = st.slider(
            "最小信頼度 (%)",
            min_value=0,
            max_value=100,
            value=50,
            step=10,
            help="予測信頼度がこの値以上のレースのみ表示"
        )

    try:
        import sqlite3
        from config.settings import DATABASE_PATH, VENUES

        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        target_date_str = target_date.strftime('%Y-%m-%d')

        # オッズデータの有無を確認
        cursor.execute("""
            SELECT COUNT(*) FROM trifecta_odds
            WHERE race_id IN (
                SELECT id FROM races WHERE race_date = ?
            )
        """, (target_date_str,))
        odds_count = cursor.fetchone()[0]

        has_odds = odds_count > 0

        if not has_odds:
            st.warning("⚠️ オッズデータが未収集です")
            st.info("""
            **期待値計算にはオッズデータが必要です**

            オッズデータを収集するには:
            1. 「データ準備」タブ → 「オッズ自動取得」
            2. または、手動でオッズ収集スクリプトを実行

            現在は **推定オッズ** を使用して期待値を計算します。
            """)

        # 会場名マッピング
        venue_name_map = {}
        for venue_id, venue_info in VENUES.items():
            venue_name_map[venue_info['code']] = venue_info['name']

        # レース情報と予想スコアを取得
        cursor.execute("""
            SELECT
                r.id as race_id,
                r.venue_code,
                r.race_number,
                r.race_time,
                r.race_date,
                AVG(rp.total_score) as avg_score,
                GROUP_CONCAT(rp.pit_number || ':' || rp.rank_prediction || ':' || rp.total_score || ':' || rp.confidence, '|') as predictions_data
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id
            WHERE r.race_date = ?
            GROUP BY r.id
        """, (target_date_str,))

        race_rows = cursor.fetchall()

        if not race_rows:
            st.warning(f"{target_date_str} のレース予想が見つかりませんでした")
            st.info("「データ準備」タブで「今日の予測を生成」を実行してください")
            conn.close()
            return

        # 期待値計算
        value_races = []

        for row in race_rows:
            race_id, venue_code, race_number, race_time, race_date, avg_score, predictions_data = row

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

            # 上位3艇
            top3 = predictions[:3]
            if len(top3) < 3:
                continue

            # 信頼度の計算
            confidence_map = {'A': 100, 'B': 80, 'C': 60, 'D': 40, 'E': 20}
            top3_confidences = [confidence_map.get(p['confidence'], 50) for p in top3]
            weights = [0.5, 0.3, 0.2]
            confidence = sum(c * w for c, w in zip(top3_confidences, weights))

            # 信頼度フィルター
            if confidence < min_confidence:
                continue

            # オッズ取得または推定
            first = top3[0]['pit_number']
            second = top3[1]['pit_number']
            third = top3[2]['pit_number']
            combination = f"{first}-{second}-{third}"

            if has_odds:
                # 実際のオッズを取得
                cursor.execute("""
                    SELECT odds FROM trifecta_odds
                    WHERE race_id = ? AND combination = ?
                """, (race_id, combination))
                odds_row = cursor.fetchone()
                odds = odds_row[0] if odds_row else None
            else:
                odds = None

            # オッズ推定（データがない場合）
            if odds is None:
                # スコアベースの簡易推定
                # 1着確率を簡易計算（スコア正規化）
                total_score = sum(p['score'] for p in predictions)
                first_prob = top3[0]['score'] / total_score if total_score > 0 else 0.2

                # 3連単確率の推定（独立性を仮定）
                trifecta_prob = first_prob * 0.2 * 0.15  # 1着 × 2着 × 3着（簡易）

                # 控除率25%を考慮した推定オッズ
                if trifecta_prob > 0:
                    odds = (1 / trifecta_prob) * 0.75  # 控除率考慮
                else:
                    odds = 100.0

                odds_type = "推定"
            else:
                odds_type = "実測"

            # 期待値計算
            # 的中確率の推定（スコアベース）
            total_score = sum(p['score'] for p in predictions)
            win_prob = (top3[0]['score'] / total_score) if total_score > 0 else 0.1

            # 期待値 = 的中確率 × オッズ - 1
            expected_value = (win_prob * odds) - 1.0
            expected_value_pct = expected_value * 100

            # 期待値フィルター
            if expected_value_pct < min_ev:
                continue

            # ROI推定
            roi = expected_value_pct

            # Kelly基準による推奨賭け金率
            if odds > 1:
                kelly_fraction = max(0, (win_prob * odds - 1) / (odds - 1))
                kelly_pct = kelly_fraction * 100 * 0.25  # フラクショナルKelly (25%)
            else:
                kelly_pct = 0

            value_races.append({
                '会場': venue_name_map.get(venue_code, f'会場{venue_code}'),
                'レース': f"{race_number}R",
                '時刻': race_time or '未定',
                '本命': f"{first}号艇",
                '買い目': combination,
                'オッズ': odds,
                'オッズ種別': odds_type,
                '期待値': expected_value_pct,
                'ROI': roi,
                'Kelly': kelly_pct,
                '信頼度': confidence,
                '的中確率': win_prob * 100,
                'race_id': race_id,
                'race_date': race_date,
                'venue_code': venue_code,
                'race_number': race_number,
                'predictions': predictions
            })

        conn.close()

        # 期待値でソート
        value_races.sort(key=lambda x: x['期待値'], reverse=True)

        if not value_races:
            st.warning(f"期待値 {min_ev}% 以上のレースが見つかりませんでした")
            st.info("期待値の閾値を下げるか、信頼度の閾値を調整してください")
            return

        st.success(f"💰 期待値上位レース {len(value_races)}件を表示中")

        # サマリー統計
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            avg_ev = sum(r['期待値'] for r in value_races) / len(value_races)
            st.metric("平均期待値", f"{avg_ev:.1f}%")
        with col2:
            max_ev = max(r['期待値'] for r in value_races)
            st.metric("最大期待値", f"{max_ev:.1f}%")
        with col3:
            avg_odds = sum(r['オッズ'] for r in value_races) / len(value_races)
            st.metric("平均オッズ", f"{avg_odds:.1f}倍")
        with col4:
            real_odds_count = sum(1 for r in value_races if r['オッズ種別'] == '実測')
            st.metric("実測オッズ", f"{real_odds_count}/{len(value_races)}")

        # レースカード表示
        _render_value_race_cards(value_races)

        # 全レース一覧テーブル
        st.markdown("---")
        st.subheader("📋 全レース一覧")

        df_data = []
        for i, r in enumerate(value_races, 1):
            df_data.append({
                '順位': i,
                '会場': r['会場'],
                'レース': r['レース'],
                '時刻': r['時刻'],
                '買い目': r['買い目'],
                'オッズ': f"{r['オッズ']:.1f}倍 ({r['オッズ種別']})",
                '期待値': f"{r['期待値']:.1f}%",
                'Kelly': f"{r['Kelly']:.1f}%",
                '信頼度': f"{r['信頼度']:.1f}%",
                '的中確率': f"{r['的中確率']:.1f}%"
            })

        df = pd.DataFrame(df_data)
        st.dataframe(df, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"エラーが発生しました: {e}")
        import traceback
        st.code(traceback.format_exc())


def _render_value_race_cards(race_list: List[Dict]):
    """期待値重視レースカードを表示"""

    for idx, race in enumerate(race_list, 1):
        ev = race['期待値']

        # 期待値に応じた背景色
        if ev >= 20:
            border_color = "#ff6b6b"  # 赤（最高）
            bg_color = "#ffe0e0"
        elif ev >= 10:
            border_color = "#ffa500"  # オレンジ（高）
            bg_color = "#fff4e0"
        elif ev >= 5:
            border_color = "#4ecdc4"  # 青緑（中）
            bg_color = "#e0f4f4"
        else:
            border_color = "#95a5a6"  # グレー（低）
            bg_color = "#f0f0f0"

        # カードのスタイル
        with st.container():
            col1, col2, col3, col4, col5 = st.columns([0.5, 1.5, 2.5, 2.5, 1])

            with col1:
                st.markdown(f"### {idx}")

            with col2:
                st.markdown(f"**{race['会場']} {race['レース']}**")
                st.caption(f"⏰ {race['時刻']}")

            with col3:
                st.markdown(f"🎯 **買い目: {race['買い目']}**")
                st.caption(f"オッズ: {race['オッズ']:.1f}倍 ({race['オッズ種別']})")

            with col4:
                # 期待値とKelly情報
                st.markdown(f"💰 **期待値: {ev:+.1f}%**")
                st.caption(f"Kelly: {race['Kelly']:.1f}% | 信頼度: {race['信頼度']:.1f}%")

            with col5:
                # 詳細ボタン
                if st.button("詳細 →", key=f"value_detail_{idx}", use_container_width=True):
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
