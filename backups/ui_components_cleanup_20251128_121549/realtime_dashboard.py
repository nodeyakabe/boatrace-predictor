"""
リアルタイム予想ダッシュボード
"""
import streamlit as st
import pandas as pd
from datetime import datetime
from src.analysis.realtime_predictor import RealtimePredictor
from src.analysis.race_predictor import RacePredictor
from ui.components.common.widgets import render_confidence_badge


def render_realtime_dashboard():
    """リアルタイム予想ダッシュボードを表示"""
    st.header("🔮 リアルタイム予想ダッシュボード")

    try:
        realtime_predictor = RealtimePredictor()
        race_predictor = RacePredictor()

        # 本日のレース一覧を取得
        today_races = realtime_predictor.get_today_races()

        if not today_races:
            st.warning("本日開催予定のレースが見つかりませんでした")
            st.info("データ準備タブでデータを取得してください")
            return

        st.success(f"本日開催: {len(today_races)}レース")

        # おすすめレースを抽出
        recommended_races = []

        st.info(f"予想を読み込み中... ({len(today_races)}レース)")
        progress_bar = st.progress(0)

        from src.database.data_manager import DataManager
        data_manager = DataManager()

        for idx, race_info in enumerate(today_races):
            try:
                race_id = race_info['race_id']
                venue_code = race_info['venue_code']
                race_number = race_info['race_number']

                # 進捗更新
                progress_bar.progress((idx + 1) / len(today_races))

                # 保存された予想を取得
                predictions = data_manager.get_race_predictions(race_id)

                if predictions and len(predictions) >= 3:
                    top3 = predictions[:3]
                    confidence = min(top3[0].get('total_score', top3[0].get('score', 50)), 100.0)

                    if confidence >= 55:  # 閾値を下げて表示数を増やす
                        recommended_races.append({
                            '会場': race_info.get('venue_name', ''),
                            'レース': f"{race_number}R",
                            '時刻': race_info.get('race_time', ''),
                            '1着': f"{top3[0]['pit_number']}号艇",
                            '2着': f"{top3[1]['pit_number']}号艇",
                            '3着': f"{top3[2]['pit_number']}号艇",
                            '信頼度': confidence,
                            'badge': render_confidence_badge(confidence),
                            'race_date': race_info['date'],
                            'venue_code': venue_code,
                            'race_number': race_number
                        })
            except Exception as e:
                # エラーログを出力（デバッグ用）
                import logging
                logging.warning(f"予想取得エラー (race_id={race_id}): {e}")
                continue

        progress_bar.empty()  # プログレスバーを削除

        if recommended_races:
            # 信頼度でソート
            recommended_races.sort(key=lambda x: x['信頼度'], reverse=True)

            st.subheader(f"🌟 本日の注目レース ({len(recommended_races)}件)")

            # 上位5件をハイライト表示
            st.markdown("### 🏆 最も推奨するレース TOP5")
            for i, race in enumerate(recommended_races[:5], 1):
                with st.container():
                    col1, col2, col3, col4 = st.columns([2, 2, 3, 2])
                    with col1:
                        st.markdown(f"**{i}. {race['会場']} {race['レース']}**")
                    with col2:
                        st.markdown(f"⏰ {race['時刻']}")
                    with col3:
                        st.markdown(f"🎯 {race['1着']}-{race['2着']}-{race['3着']}")
                    with col4:
                        st.markdown(f"{race['badge']} {race['信頼度']:.1f}%")
                    st.markdown("---")

            # 全レース一覧（エクスパンダー）
            with st.expander(f"📋 全{len(recommended_races)}件の予想を表示"):
                df = pd.DataFrame([{
                    '順位': i+1,
                    '会場': r['会場'],
                    'レース': r['レース'],
                    '時刻': r['時刻'],
                    '買い目': f"{r['1着']}-{r['2着']}-{r['3着']}",
                    '信頼度': f"{r['信頼度']:.1f}%"
                } for i, r in enumerate(recommended_races)])
                st.dataframe(df, use_container_width=True, hide_index=True)

        else:
            st.info("現時点で推奨できるレースはありません")

    except Exception as e:
        st.error(f"エラーが発生しました: {e}")
        import traceback
        st.code(traceback.format_exc())


def render_race_detail_viewer(race_date, venue_code, race_number):
    """レース詳細ビューア"""
    st.subheader(f"📊 レース詳細: {venue_code} - {race_number}R")

    try:
        from src.database.data_manager import DataManager
        import sqlite3
        from config.settings import DATABASE_PATH
        from src.utils.date_utils import to_iso_format

        data_manager = DataManager()

        # race_idを取得
        race_date_formatted = to_iso_format(race_date)
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id FROM races
            WHERE venue_code = ? AND race_date = ? AND race_number = ?
        """, (venue_code, race_date_formatted, race_number))
        race_row = cursor.fetchone()
        conn.close()

        if not race_row:
            st.warning("レースが見つかりませんでした")
            return

        race_id = race_row[0]

        # 保存された予想を取得
        predictions = data_manager.get_race_predictions(race_id)

        if predictions:
            # 予想表示
            st.markdown("### 🎯 予想結果")
            for i, pred in enumerate(predictions[:3], 1):
                col1, col2, col3 = st.columns([1, 3, 2])
                with col1:
                    st.metric(f"{i}着", f"{pred['pit_number']}号艇")
                with col2:
                    st.write(f"**{pred.get('racer_name', 'N/A')}**")
                with col3:
                    st.write(f"スコア: {pred.get('total_score', pred.get('score', 50)):.1f}")

            # 適用法則を表示
            st.markdown("---")
            st.markdown("### 🔍 判断根拠")

            if predictions[0].get('applied_rules'):
                rules_list = predictions[0]['applied_rules'].split(',')
                for i, rule in enumerate(rules_list[:5], 1):
                    st.write(f"{i}. {rule}")
            else:
                st.write("基本モデルのみで予想")

        else:
            st.warning("予想データがありません。「データ準備」タブで予想を生成してください")

    except Exception as e:
        st.error(f"エラー: {e}")
