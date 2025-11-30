"""
統合レース一覧画面
今日のレース推奨を一覧表示（的中率重視/期待値重視）
"""
import streamlit as st
import pandas as pd
from datetime import datetime
from typing import List, Dict
import logging

from ui.components.common.widgets import render_confidence_badge

logger = logging.getLogger(__name__)


def render_unified_race_list():
    """統合レース一覧画面を表示"""

    # ヘッダーと直前情報取得ボタンを横並び
    col_header, col_btn = st.columns([3, 1])
    with col_header:
        st.header("🔮 レース予想一覧")
    with col_btn:
        st.write("")  # スペーサー
        if st.button("🔄 直前情報取得", type="secondary", use_container_width=True):
            st.session_state.show_beforeinfo_dialog = True

    # 直前情報取得ダイアログ
    if st.session_state.get('show_beforeinfo_dialog', False):
        _render_beforeinfo_dialog()

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
        # 初期予想と直前予想を別々に取得
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
                GROUP_CONCAT(rp.pit_number || ':' || rp.rank_prediction || ':' || rp.total_score || ':' || rp.confidence, '|') as predictions_data,
                COALESCE(rp.prediction_type, 'initial') as prediction_type
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id
            WHERE r.race_date = ?
            GROUP BY r.id, rp.prediction_type
            ORDER BY best_confidence_rank ASC, max_score DESC
        """, (target_date_str,))

        race_rows = cursor.fetchall()

        if not race_rows:
            st.warning(f"{target_date_str} のレース予想が見つかりませんでした")
            st.info("「データ準備」タブで「今日の予測を生成」を実行してください")
            conn.close()
            return

        st.success(f"📊 本日の予想データ: {len(race_rows)}件 (上位20件をカード表示、全件をテーブル表示)")

        # レースカードデータを作成
        recommended_races = []

        for row in race_rows:
            race_id, venue_code, race_number, race_time, race_date, avg_score, max_score, best_confidence_rank, predictions_data, prediction_type = row

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

            # 予想タイプのラベル
            type_label = '直前' if prediction_type == 'before' else '初期'

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
                'predictions': predictions,
                'prediction_type': prediction_type,
                'type_label': type_label
            })

        conn.close()

        # 信頼度の降順でソート
        recommended_races.sort(key=lambda x: x['信頼度'], reverse=True)

        # レースカード表示（上位20件のみ）
        st.subheader("🏆 おすすめレース TOP20")
        _render_race_cards_v2(recommended_races[:20])

        # 全レース一覧テーブル
        st.markdown("---")
        st.subheader(f"📋 全レース一覧 ({len(recommended_races)}件)")

        df_data = []
        for i, r in enumerate(recommended_races, 1):
            df_data.append({
                '順位': i,
                '種別': r.get('type_label', '初期'),
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
    """期待値重視タブ - 保存済み予想(value mode)から上位20レースを表示"""
    st.subheader("💰 期待値重視のおすすめレース TOP20")
    st.caption("保存済みの予想データ（期待値重視モード）から、スコア上位20レースを表示します")

    # 日付選択
    target_date = st.date_input(
        "対象日",
        value=datetime.now().date(),
        key="value_date"
    )

    # 期待値の説明
    with st.expander("📊 期待値重視モードとは？"):
        st.markdown("""
        **期待値重視モードの特徴:**
        - コース有利を過大評価せず、穴馬を狙う
        - モーター・選手の実力を重視

        **重み設定（期待値重視モード）:**
        - コース: 25点（的中率重視は50点）→ コース過大評価を抑制
        - 選手: 35点（的中率重視は30点）
        - モーター: 20点（的中率重視は10点）
        - 決まり手: 15点（的中率重視は5点）
        """)

    # 保存済み予想データを取得（的中率重視と同じロジック）
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

        # レース情報と予想スコアを取得
        # 期待値重視: モーター・選手スコアの合計が高い順（コースに依存しない実力重視）
        # 初期予想と直前予想を別行で取得
        cursor.execute("""
            SELECT
                r.id as race_id,
                r.venue_code,
                r.race_number,
                r.race_time,
                r.race_date,
                AVG(rp.total_score) as avg_score,
                MAX(rp.total_score) as max_score,
                MAX(COALESCE(rp.motor_score, 0) + COALESCE(rp.racer_score, 0)) as value_score,
                MIN(CASE rp.confidence
                    WHEN 'A' THEN 1
                    WHEN 'B' THEN 2
                    WHEN 'C' THEN 3
                    WHEN 'D' THEN 4
                    ELSE 5
                END) as best_confidence_rank,
                GROUP_CONCAT(rp.pit_number || ':' || rp.rank_prediction || ':' || rp.total_score || ':' || rp.confidence, '|') as predictions_data,
                COALESCE(rp.prediction_type, 'initial') as prediction_type
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id
            WHERE r.race_date = ?
            GROUP BY r.id, rp.prediction_type
            ORDER BY value_score DESC, max_score DESC
        """, (target_date_str,))

        race_rows = cursor.fetchall()

        if not race_rows:
            st.warning(f"{target_date_str} の予想データが見つかりませんでした")
            st.info("「データ準備」タブで「今日の予測を生成」を実行してください")
            conn.close()
            return

        st.success(f"📊 本日の予想データ: {len(race_rows)}件 (上位20件をカード表示、全件をテーブル表示)")

        # レースカードデータを作成（的中率重視と同じ形式）
        recommended_races = []

        for row in race_rows:
            race_id, venue_code, race_number, race_time, race_date, avg_score, max_score, value_score, best_confidence_rank, predictions_data, prediction_type = row

            # 予想タイプのラベル
            type_label = '直前' if prediction_type == 'before' else '初期'

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
            confidence_map = {'A': 100, 'B': 80, 'C': 60, 'D': 40, 'E': 20}
            top3_confidences = [confidence_map.get(p['confidence'], 50) for p in top3 if 'confidence' in p]

            if top3_confidences:
                weights = [0.5, 0.3, 0.2]
                confidence = sum(c * w for c, w in zip(top3_confidences, weights[:len(top3_confidences)]))
            else:
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
                'predictions': predictions,
                'prediction_type': prediction_type,
                'type_label': type_label
            })

        conn.close()

        # 信頼度の降順でソート
        recommended_races.sort(key=lambda x: x['信頼度'], reverse=True)

        # レースカード表示（上位20件のみ、期待値重視タブ用のkey_prefixを指定）
        st.subheader("🏆 おすすめレース TOP20")
        _render_race_cards_v2(recommended_races[:20], key_prefix="val")

        # 全レース一覧テーブル
        st.markdown("---")
        st.subheader(f"📋 全レース一覧 ({len(recommended_races)}件)")

        df_data = []
        for i, r in enumerate(recommended_races, 1):
            df_data.append({
                '順位': i,
                '種別': r.get('type_label', '初期'),
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


def _render_race_cards_v2(race_list: List[Dict], key_prefix: str = "acc"):
    """レースカードを表示（改善版）

    Args:
        race_list: レースデータのリスト
        key_prefix: ボタンキーのプレフィックス（タブ間で重複を避けるため）
    """

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
                # 種別バッジ（直前予想の場合は🔴を表示）
                type_label = race.get('type_label', '初期')
                type_badge = "🔴直前" if type_label == '直前' else "⚪初期"
                st.markdown(f"**{race['会場']} {race['レース']}** {type_badge}")
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
                if st.button("詳細 →", key=f"detail_{key_prefix}_{idx}", use_container_width=True):
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
                # 種別バッジ（直前予想の場合は🔴を表示）
                type_label = race.get('type_label', '初期')
                type_badge = "🔴直前" if type_label == '直前' else "⚪初期"
                st.markdown(f"**{race['会場']} {race['レース']}** {type_badge}")
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


def _render_beforeinfo_dialog():
    """直前情報取得ダイアログを表示"""
    import sqlite3
    from datetime import datetime
    from config.settings import DATABASE_PATH, VENUES

    st.markdown("---")
    st.subheader("🔄 直前情報取得")

    # サイドバーで選択された会場を取得
    sidebar_selected_venues = list(st.session_state.get('sidebar_selected_venues', set()))

    # 会場名マッピング
    venue_name_map = {}
    venue_code_map = {}  # 名前からコードへ
    for venue_id, venue_info in VENUES.items():
        venue_name_map[venue_info['code']] = venue_info['name']
        venue_code_map[venue_info['name']] = venue_info['code']

    # 本日のレースを取得
    today_str = datetime.now().strftime('%Y-%m-%d')
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # サイドバーで会場が選択されている場合はフィルタリング
    if sidebar_selected_venues:
        placeholders = ','.join('?' * len(sidebar_selected_venues))
        query = f"""
            SELECT r.id, r.venue_code, r.race_number, r.race_time,
                   CASE WHEN ed.exhibition_time IS NOT NULL THEN 1 ELSE 0 END as has_beforeinfo
            FROM races r
            LEFT JOIN exhibition_data ed ON r.id = ed.race_id AND ed.pit_number = 1
            WHERE r.race_date = ? AND r.venue_code IN ({placeholders})
            ORDER BY r.venue_code, r.race_number
        """
        cursor.execute(query, [today_str] + sidebar_selected_venues)
    else:
        cursor.execute("""
            SELECT r.id, r.venue_code, r.race_number, r.race_time,
                   CASE WHEN ed.exhibition_time IS NOT NULL THEN 1 ELSE 0 END as has_beforeinfo
            FROM races r
            LEFT JOIN exhibition_data ed ON r.id = ed.race_id AND ed.pit_number = 1
            WHERE r.race_date = ?
            ORDER BY r.venue_code, r.race_number
        """, (today_str,))

    races = cursor.fetchall()
    conn.close()

    # サイドバーでの選択状態を表示
    if sidebar_selected_venues:
        selected_venue_names = [venue_name_map.get(code, code) for code in sidebar_selected_venues]
        st.info(f"🏟️ 対象会場（サイドバー選択）: {', '.join(selected_venue_names)}")
    else:
        st.info("🏟️ 対象会場: 全場（サイドバーで会場を選択すると絞り込めます）")

    if not races:
        st.warning("本日のレースが見つかりません")
        if st.button("閉じる", key="close_beforeinfo_dialog"):
            st.session_state.show_beforeinfo_dialog = False
            st.rerun()
        return

    # 会場ごとにグループ化
    venues_with_races = {}
    for race_id, venue_code, race_number, race_time, has_beforeinfo in races:
        venue_name = venue_name_map.get(venue_code, f'会場{venue_code}')
        if venue_name not in venues_with_races:
            venues_with_races[venue_name] = []
        venues_with_races[venue_name].append({
            'race_id': race_id,
            'venue_code': venue_code,
            'race_number': race_number,
            'race_time': race_time,
            'has_beforeinfo': has_beforeinfo
        })

    # 取得モード選択
    col1, col2 = st.columns(2)
    with col1:
        fetch_mode = st.radio(
            "取得モード",
            ["全レース取得", "会場・レース指定"],
            key="beforeinfo_fetch_mode",
            horizontal=True
        )

    # オプション
    with col2:
        skip_fetched = st.checkbox("取得済みをスキップ", value=True, key="skip_fetched_beforeinfo")
        skip_not_started = st.checkbox("未公開をスキップ", value=True, key="skip_not_started_beforeinfo",
                                        help="まだ展示が始まっていないレースをスキップ")

    target_races = []

    if fetch_mode == "会場・レース指定":
        st.markdown("#### 対象レース選択")

        # 会場選択
        selected_venue = st.selectbox(
            "会場を選択",
            list(venues_with_races.keys()),
            key="beforeinfo_venue_select"
        )

        if selected_venue:
            venue_races = venues_with_races[selected_venue]

            # レース一覧表示
            race_options = []
            for race in venue_races:
                status = "✅" if race['has_beforeinfo'] else "⬜"
                time_str = race['race_time'] or '未定'
                race_options.append(f"{status} {race['race_number']}R ({time_str})")

            selected_races = st.multiselect(
                "レースを選択（複数可）",
                race_options,
                key="beforeinfo_race_select"
            )

            # 選択されたレースを抽出
            for race in venue_races:
                for selected in selected_races:
                    if f"{race['race_number']}R" in selected:
                        target_races.append({
                            'race_id': race['race_id'],
                            'venue_code': race['venue_code'],
                            'venue_name': selected_venue,
                            'race_number': race['race_number'],
                            'race_time': race['race_time'],
                            'has_beforeinfo': race['has_beforeinfo']
                        })
                        break

            st.caption(f"選択中: {len(target_races)}レース")

    else:
        # 全レース取得
        for venue_name, venue_races in venues_with_races.items():
            for race in venue_races:
                target_races.append({
                    'race_id': race['race_id'],
                    'venue_code': race['venue_code'],
                    'venue_name': venue_name,
                    'race_number': race['race_number'],
                    'race_time': race['race_time'],
                    'has_beforeinfo': race['has_beforeinfo']
                })

        # 統計表示
        total = len(target_races)
        fetched = sum(1 for r in target_races if r['has_beforeinfo'])
        st.info(f"全{total}レース（取得済み: {fetched}件）")

    # 実行ボタン
    col_exec, col_close = st.columns(2)
    with col_exec:
        if st.button("🔄 取得開始", type="primary", use_container_width=True):
            _fetch_and_update_beforeinfo(target_races, skip_fetched, skip_not_started)

    with col_close:
        if st.button("❌ 閉じる", use_container_width=True):
            st.session_state.show_beforeinfo_dialog = False
            st.rerun()

    st.markdown("---")


def _fetch_and_update_beforeinfo(target_races: List[Dict], skip_fetched: bool = True, skip_not_started: bool = True):
    """直前情報を取得して予想を更新"""
    from datetime import datetime
    from config.settings import VENUES

    try:
        today_ymd = datetime.now().strftime('%Y%m%d')
        now = datetime.now()

        # 会場名マッピング
        venue_name_map = {}
        for venue_id, venue_info in VENUES.items():
            venue_name_map[venue_info['code']] = venue_info['name']

        # フィルタリング
        races_to_fetch = []
        skipped_fetched = 0
        skipped_not_started = 0

        for race in target_races:
            # 取得済みスキップ
            if skip_fetched and race.get('has_beforeinfo'):
                skipped_fetched += 1
                continue

            # 未公開スキップ（レース時刻の30分前までは展示情報がない可能性）
            if skip_not_started and race.get('race_time'):
                try:
                    race_time = datetime.strptime(f"{now.strftime('%Y-%m-%d')} {race['race_time']}", "%Y-%m-%d %H:%M:%S")
                    # レース時刻の40分前より未来のレースはスキップ
                    if now < race_time.replace(hour=race_time.hour, minute=race_time.minute - 40 if race_time.minute >= 40 else race_time.minute + 20):
                        if race_time.minute < 40:
                            race_time = race_time.replace(hour=race_time.hour - 1)
                        skipped_not_started += 1
                        continue
                except:
                    pass

            races_to_fetch.append(race)

        if not races_to_fetch:
            st.warning("取得対象のレースがありません")
            if skipped_fetched > 0:
                st.info(f"取得済みスキップ: {skipped_fetched}件")
            if skipped_not_started > 0:
                st.info(f"未公開スキップ: {skipped_not_started}件")
            return

        # スキップ情報表示
        if skipped_fetched > 0 or skipped_not_started > 0:
            skip_msg = []
            if skipped_fetched > 0:
                skip_msg.append(f"取得済み: {skipped_fetched}件")
            if skipped_not_started > 0:
                skip_msg.append(f"未公開: {skipped_not_started}件")
            st.info(f"スキップ: {', '.join(skip_msg)}")

        # 進捗表示
        progress_bar = st.progress(0)
        status_text = st.empty()

        # BeforeInfoFetcher をインポート
        from src.scraper.beforeinfo_fetcher import BeforeInfoFetcher

        fetcher = BeforeInfoFetcher(delay=0.2)  # 高速化: 0.5→0.2秒

        total = len(races_to_fetch)
        success_count = 0
        error_count = 0
        no_data_count = 0
        fetched_data = []

        for idx, race in enumerate(races_to_fetch):
            venue_name = race.get('venue_name') or venue_name_map.get(race['venue_code'], f'会場{race["venue_code"]}')
            status_text.text(f"取得中: {venue_name} {race['race_number']}R ({idx + 1}/{total})")

            try:
                # 直前情報を取得
                beforeinfo = fetcher.fetch_beforeinfo(today_ymd, race['venue_code'], race['race_number'])

                if beforeinfo:
                    # 実際にデータがあるかチェック
                    racers = beforeinfo.get('racers', [])
                    has_actual_data = any(r.get('exhibition_time') for r in racers)

                    if has_actual_data:
                        fetched_data.append({
                            'race_id': race['race_id'],
                            'venue_code': race['venue_code'],
                            'venue_name': venue_name,
                            'race_number': race['race_number'],
                            'beforeinfo': beforeinfo
                        })
                        success_count += 1
                    else:
                        no_data_count += 1
                else:
                    error_count += 1

            except Exception as e:
                logger.error(f"直前情報取得エラー ({venue_name} {race['race_number']}R): {e}")
                error_count += 1

            # 進捗更新
            progress_bar.progress((idx + 1) / total)

        progress_bar.empty()
        status_text.empty()

        # 結果表示
        result_parts = []
        if success_count > 0:
            result_parts.append(f"成功: {success_count}件")
        if no_data_count > 0:
            result_parts.append(f"データなし: {no_data_count}件")
        if error_count > 0:
            result_parts.append(f"エラー: {error_count}件")

        if success_count > 0:
            st.success(f"✅ 直前情報取得完了 ({', '.join(result_parts)})")

            # DBに保存
            st.info("💾 直前情報をDBに保存中...")
            saved_count = _save_beforeinfo_to_db(fetched_data)
            if saved_count > 0:
                st.success(f"💾 {saved_count}件のデータをDBに保存しました")

            # 取得データのサマリーを表示
            with st.expander("📋 取得データの詳細", expanded=False):
                for data in fetched_data[:10]:  # 最初の10件のみ
                    st.markdown(f"**{data['venue_name']} {data['race_number']}R**")

                    weather = data['beforeinfo'].get('weather', {})
                    if any(weather.values()):
                        cols = st.columns(4)
                        cols[0].metric("気温", f"{weather.get('temperature', '-')}℃" if weather.get('temperature') else "-")
                        cols[1].metric("水温", f"{weather.get('water_temp', '-')}℃" if weather.get('water_temp') else "-")
                        cols[2].metric("風速", f"{weather.get('wind_speed', '-')}m" if weather.get('wind_speed') else "-")
                        cols[3].metric("波高", f"{weather.get('wave_height', '-')}cm" if weather.get('wave_height') else "-")

                    racers = data['beforeinfo'].get('racers', [])
                    if racers:
                        racer_data = []
                        for r in racers:
                            racer_data.append({
                                '枠': r.get('pit_number', '-'),
                                '展示タイム': r.get('exhibition_time', '-'),
                                'ST': r.get('start_timing', '-'),
                                'チルト': r.get('tilt', '-')
                            })
                        if racer_data:
                            st.dataframe(pd.DataFrame(racer_data), hide_index=True)

                    st.markdown("---")

                if len(fetched_data) > 10:
                    st.info(f"他 {len(fetched_data) - 10} レースのデータも取得済み")

            # 自動で予想更新を実行
            st.markdown("---")
            st.info("🔄 直前予想を更新中...")
            _update_predictions_with_beforeinfo(fetched_data)

        else:
            st.warning(f"直前情報を取得できませんでした ({', '.join(result_parts)})")

    except Exception as e:
        st.error(f"エラーが発生しました: {e}")
        import traceback
        st.code(traceback.format_exc())


def _update_predictions_with_beforeinfo(fetched_data: List[Dict]):
    """取得した直前情報で予想を更新（バッチ処理で高速化）"""
    import time

    try:
        from src.analysis.prediction_updater import PredictionUpdater
        from datetime import datetime

        # レースIDリストを作成
        race_ids = [data['race_id'] for data in fetched_data]
        total = len(race_ids)

        if total == 0:
            st.warning("更新対象のレースがありません")
            return

        start_time = time.time()
        st.info(f"📊 PredictionUpdater初期化中... (対象: {total}レース)")

        updater = PredictionUpdater()

        init_time = time.time() - start_time
        st.info(f"✅ 初期化完了 ({init_time:.1f}秒)")

        progress_bar = st.progress(0)
        status_text = st.empty()
        time_text = st.empty()

        # 進捗コールバック
        last_update_time = [time.time()]
        def update_progress(current, total_count):
            progress_bar.progress(current / total_count)
            now = time.time()
            elapsed = now - start_time
            per_race = elapsed / current if current > 0 else 0
            eta = per_race * (total_count - current)

            if current <= len(fetched_data):
                data = fetched_data[current - 1]
                status_text.text(f"更新中: {data['venue_name']} {data['race_number']}R ({current}/{total_count})")
                time_text.text(f"経過: {elapsed:.0f}秒 | 1レース: {per_race:.2f}秒 | 残り: {eta:.0f}秒")

        # 今日の日付
        target_date = datetime.now().strftime('%Y-%m-%d')

        # バッチ更新（日次データを一括ロードして高速化）
        load_start = time.time()
        st.info("📊 日次データを一括ロード中...")
        stats = updater.update_batch_before_predictions(
            race_ids=race_ids,
            target_date=target_date,
            progress_callback=update_progress
        )

        total_time = time.time() - start_time
        st.info(f"⏱️ 総処理時間: {total_time:.1f}秒 ({total_time/60:.1f}分)")

        progress_bar.empty()
        status_text.empty()

        updated_count = stats['updated']
        failed_count = stats['failed']

        if updated_count > 0:
            st.success(f"✅ 予想更新完了: {updated_count}件成功, {failed_count}件失敗")
            st.info("ページを更新すると最新の予想が表示されます")
            st.button("🔄 ページを更新", on_click=st.rerun)
        else:
            st.warning("予想を更新できませんでした")

    except Exception as e:
        st.error(f"予想更新エラー: {e}")
        import traceback
        st.code(traceback.format_exc())


def _save_beforeinfo_to_db(fetched_data: List[Dict]) -> int:
    """
    取得した直前情報をDBに保存

    Args:
        fetched_data: 取得した直前情報リスト
            [{
                'race_id': int,
                'venue_code': str,
                'venue_name': str,
                'race_number': int,
                'beforeinfo': {
                    'racers': [{
                        'pit_number': int,
                        'exhibition_time': float,
                        'start_timing': float,
                        'tilt': float,
                        'weight': float,
                        ...
                    }, ...],
                    'weather': {
                        'temperature': float,
                        'water_temp': float,
                        'wind_speed': int,
                        'wind_direction': str,
                        'wave_height': int,
                        'weather': str
                    }
                }
            }, ...]

    Returns:
        保存したレコード数
    """
    import sqlite3
    from config.settings import DATABASE_PATH
    from datetime import datetime

    saved_count = 0

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        # 現在時刻
        collected_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        for data in fetched_data:
            race_id = data['race_id']
            beforeinfo = data['beforeinfo']
            racers = beforeinfo.get('racers', [])
            weather = beforeinfo.get('weather', {})

            # 天候データを保存（race_conditions テーブル）
            if any(weather.values()):
                cursor.execute("""
                    SELECT id FROM race_conditions WHERE race_id = ?
                """, (race_id,))

                existing_weather = cursor.fetchone()

                if existing_weather:
                    cursor.execute("""
                        UPDATE race_conditions
                        SET weather = COALESCE(?, weather),
                            wind_speed = COALESCE(?, wind_speed),
                            wind_direction = COALESCE(?, wind_direction),
                            wave_height = COALESCE(?, wave_height),
                            temperature = COALESCE(?, temperature),
                            water_temperature = COALESCE(?, water_temperature),
                            collected_at = ?
                        WHERE race_id = ?
                    """, (
                        weather.get('weather'),
                        weather.get('wind_speed'),
                        weather.get('wind_direction'),
                        weather.get('wave_height'),
                        weather.get('temperature'),
                        weather.get('water_temp'),
                        collected_at,
                        race_id
                    ))
                else:
                    cursor.execute("""
                        INSERT INTO race_conditions
                        (race_id, weather, wind_speed, wind_direction, wave_height, temperature, water_temperature, collected_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        race_id,
                        weather.get('weather'),
                        weather.get('wind_speed'),
                        weather.get('wind_direction'),
                        weather.get('wave_height'),
                        weather.get('temperature'),
                        weather.get('water_temp'),
                        collected_at
                    ))

            for racer in racers:
                pit_number = racer.get('pit_number')
                if not pit_number:
                    continue

                exhibition_time = racer.get('exhibition_time')
                start_timing = racer.get('start_timing')
                tilt = racer.get('tilt')
                weight = racer.get('weight')

                # 既存レコードを確認
                cursor.execute("""
                    SELECT id FROM exhibition_data
                    WHERE race_id = ? AND pit_number = ?
                """, (race_id, pit_number))

                existing = cursor.fetchone()

                if existing:
                    # 更新
                    cursor.execute("""
                        UPDATE exhibition_data
                        SET exhibition_time = COALESCE(?, exhibition_time),
                            start_timing = COALESCE(?, start_timing),
                            weight_change = COALESCE(?, weight_change),
                            collected_at = ?
                        WHERE race_id = ? AND pit_number = ?
                    """, (
                        exhibition_time,
                        int(start_timing * 100) if start_timing else None,  # ST展示は0.15などの秒→15の整数
                        weight,
                        collected_at,
                        race_id,
                        pit_number
                    ))
                else:
                    # 新規挿入
                    cursor.execute("""
                        INSERT INTO exhibition_data
                        (race_id, pit_number, exhibition_time, start_timing, weight_change, collected_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        race_id,
                        pit_number,
                        exhibition_time,
                        int(start_timing * 100) if start_timing else None,
                        weight,
                        collected_at
                    ))

                saved_count += 1

        conn.commit()
        conn.close()
        logger.info(f"直前情報をDBに保存: {saved_count}件")

    except Exception as e:
        logger.error(f"直前情報のDB保存エラー: {e}")
        import traceback
        traceback.print_exc()

    return saved_count
