"""
競艇予想システム - Streamlit UIアプリケーション
"""

import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import sys
import os

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.settings import DATABASE_PATH, VENUES
from src.analysis.realtime_predictor import RealtimePredictor
from src.analysis.race_predictor import RacePredictor
from src.analysis.statistics_calculator import StatisticsCalculator
from src.analysis.data_quality import DataQualityMonitor
from src.analysis.backtest import Backtester
from src.analysis.pattern_analyzer import PatternAnalyzer
from src.analysis.data_coverage_checker import DataCoverageChecker
from src.analysis.feature_calculator import FeatureCalculator
from src.ml.dataset_builder import DatasetBuilder
from src.ml.model_trainer import ModelTrainer
from src.ml.shap_explainer import SHAPExplainer
from src.utils.result_manager import ResultManager
from src.scraper.bulk_scraper import BulkScraper
from src.database.views import initialize_views
from ui.components.bet_history import render_bet_history_page
from ui.components.backtest import render_backtest_page
from ui.components.betting_recommendation import render_betting_recommendations
from ui.components.model_training import render_model_training_page
from ui.components.racer_analysis import render_racer_analysis_page
from ui.components.venue_analysis import render_venue_analysis_page
from ui.components.venue_strategy import analyze_venue_stats, get_venue_boaters_info
from ui.components.original_tenji_collector import render_original_tenji_collector
from ui.components.bulk_data_collector import render_bulk_data_collector
from ui.components.data_export import render_data_export_page, render_past_races_summary
from ui.components.hybrid_prediction import render_hybrid_prediction_page


def main():
    st.set_page_config(
        page_title="競艇予想システム",
        page_icon="🚤",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # データベースビューを初期化（起動時に一度だけ実行）
    try:
        initialize_views(DATABASE_PATH)
    except Exception as e:
        st.warning(f"ビュー初期化エラー: {e}")

    st.title("🚤 競艇予想システム")

    # サイドバー
    with st.sidebar:
        st.header("メニュー")
        st.info("データベース: " + DATABASE_PATH)

        # データベース統計
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM races")
            race_count = cursor.fetchone()[0]
            st.metric("総レース数", f"{race_count:,}")
            conn.close()
        except Exception as e:
            st.error(f"DB接続エラー: {e}")

        st.markdown("---")

        # グローバルフィルター
        st.header("🔍 フィルター設定")

        # 日付選択（カレンダー形式）
        st.subheader("📅 対象日")
        filter_target_date = st.date_input("日付を選択", datetime.now(), key="global_target_date")

        # 競艇場選択（ボタン形式）
        st.subheader("🏟️ 競艇場")

        # セッションステートで選択状態を管理
        if 'selected_venues' not in st.session_state:
            st.session_state.selected_venues = set()

        # すべて選択/解除ボタン
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("すべて選択", key="select_all_btn", use_container_width=True):
                venue_list = [
                    '01', '02', '03', '04', '05', '06', '07', '08',
                    '09', '10', '11', '12', '13', '14', '15', '16',
                    '17', '18', '19', '20', '21', '22', '23', '24'
                ]
                st.session_state.selected_venues = set(venue_list)
                st.rerun()
        with col_btn2:
            if st.button("すべて解除", key="deselect_all_btn", use_container_width=True):
                st.session_state.selected_venues = set()
                st.rerun()

        # 競艇場ボタン（2列レイアウト）
        venue_data = [
            ('01', '桐生'), ('02', '戸田'), ('03', '江戸川'), ('04', '平和島'),
            ('05', '多摩川'), ('06', '浜名湖'), ('07', '蒲郡'), ('08', '常滑'),
            ('09', '津'), ('10', '三国'), ('11', 'びわこ'), ('12', '住之江'),
            ('13', '尼崎'), ('14', '鳴門'), ('15', '丸亀'), ('16', '児島'),
            ('17', '宮島'), ('18', '徳山'), ('19', '下関'), ('20', '若松'),
            ('21', '芦屋'), ('22', '福岡'), ('23', '唐津'), ('24', '大村')
        ]

        for i in range(0, len(venue_data), 2):
            col1, col2 = st.columns(2)

            # 左列
            code1, name1 = venue_data[i]
            with col1:
                is_selected1 = code1 in st.session_state.selected_venues
                button_type1 = "primary" if is_selected1 else "secondary"
                if st.button(f"{name1}", key=f"venue_btn_{code1}", type=button_type1, use_container_width=True):
                    if is_selected1:
                        st.session_state.selected_venues.remove(code1)
                    else:
                        st.session_state.selected_venues.add(code1)
                    st.rerun()

            # 右列
            if i + 1 < len(venue_data):
                code2, name2 = venue_data[i + 1]
                with col2:
                    is_selected2 = code2 in st.session_state.selected_venues
                    button_type2 = "primary" if is_selected2 else "secondary"
                    if st.button(f"{name2}", key=f"venue_btn_{code2}", type=button_type2, use_container_width=True):
                        if is_selected2:
                            st.session_state.selected_venues.remove(code2)
                        else:
                            st.session_state.selected_venues.add(code2)
                        st.rerun()

        filter_selected_venues = list(st.session_state.selected_venues)
        st.info(f"選択中: {len(filter_selected_venues)}会場")

    # タブ定義（整理版：管理系機能をTab8に集約、ハイブリッド予測を追加）
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
        "🏠 ホーム",
        "🎯 ハイブリッド予測",
        "🔮 リアルタイム予想",
        "💰 購入履歴",
        "🏟️ 場攻略",
        "👤 選手",
        "🤖 モデル学習",
        "🧪 バックテスト",
        "⚙️ 設定・データ管理"
    ])

    # Tab 1: ホーム - 本日のおすすめレース一覧
    with tab1:
        st.header("🏠 本日のおすすめレース")
        st.markdown("### 今日の注目レースと買い目を一覧表示")

        # 本日のデータ取得ボタン
        with st.expander("📥 本日のレースデータ取得", expanded=False):
            st.markdown("**本日開催のレースデータをDBに取り込みます**")
            st.info("出走表・展示タイム・オッズなどを取得して予想の精度を向上させます")

            if st.button("🔄 本日のデータを取得", type="primary", key="home_fetch_today_data"):
                with st.spinner("本日のレースデータを取得中..."):
                    try:
                        today_date = datetime.now().strftime("%Y-%m-%d")

                        # BulkScraperを使用して本日のデータを取得
                        scraper = BulkScraper()

                        # 本日開催の会場を取得
                        if not hasattr(scraper, 'schedule_scraper'):
                            st.error("❌ BulkScraperにschedule_scraperが存在しません")
                            st.info("💡 src/scraper/bulk_scraper.py の __init__ メソッドを確認してください")
                        else:
                            schedule_scraper = scraper.schedule_scraper
                            today_schedule = schedule_scraper.get_today_schedule()

                            if today_schedule:
                                st.info(f"本日開催: {len(today_schedule)}会場")

                                # 各会場のデータを取得
                                total_races = 0
                                for venue_code, race_date in today_schedule.items():
                                    result = scraper.fetch_multiple_venues(
                                        venue_codes=[venue_code],
                                        race_date=race_date,
                                        race_count=12
                                    )
                                    if venue_code in result:
                                        total_races += len(result[venue_code])

                                st.success(f"✅ 本日のデータ取得完了！ {total_races}レース取得しました")
                                st.rerun()
                            else:
                                st.warning("本日開催のレースが見つかりませんでした")
                    except Exception as e:
                        st.error(f"❌ データ取得エラー: {e}")
                        import traceback
                        st.code(traceback.format_exc())

        # 全体再解析ボタン
        with st.expander("🔄 データ更新・再解析", expanded=False):
            st.markdown("データが増えたら再解析を実行して予想精度を向上させます")

            col1, col2 = st.columns(2)
            with col1:
                if st.button("🏟️ 競艇場法則を再解析", key="home_reanalyze_venues"):
                    with st.spinner("競艇場パターンを再解析中..."):
                        import subprocess
                        try:
                            result = subprocess.run(
                                ['venv/Scripts/python.exe', 'analyze_venue_patterns.py'],
                                capture_output=True,
                                text=True,
                                timeout=300
                            )
                            if result.returncode == 0:
                                st.success("✅ 競艇場法則の再解析が完了しました！")
                                st.rerun()
                            else:
                                st.error(f"❌ 再解析に失敗: {result.stderr[:200]}")
                        except Exception as e:
                            st.error(f"❌ エラー: {e}")

            with col2:
                if st.button("👤 選手法則を再解析", key="home_reanalyze_racers"):
                    with st.spinner("トップ選手法則を再解析中..."):
                        import subprocess
                        try:
                            result = subprocess.run(
                                ['venv/Scripts/python.exe', 'register_top_racer_rules.py'],
                                capture_output=True,
                                text=True,
                                timeout=600
                            )
                            if result.returncode == 0:
                                st.success("✅ 選手法則の再解析が完了しました！")
                                st.rerun()
                            else:
                                st.error(f"❌ 再解析に失敗: {result.stderr[:200]}")
                        except Exception as e:
                            st.error(f"❌ エラー: {e}")

            st.markdown("---")
            if st.button("🔄 全ての法則を一括再解析", key="home_reanalyze_all", type="primary"):
                with st.spinner("全ての法則を再解析中... 数分かかります"):
                    import subprocess
                    try:
                        result = subprocess.run(
                            ['venv/Scripts/python.exe', 'reanalyze_all.py'],
                            capture_output=True,
                            text=True,
                            timeout=900
                        )
                        if result.returncode == 0:
                            st.success("✅ 全ての法則の再解析が完了しました！")
                            # 結果の要約を表示
                            output_lines = result.stdout.split('\n')
                            summary_start = False
                            for line in output_lines:
                                if '再解析完了サマリー' in line:
                                    summary_start = True
                                if summary_start and line.strip():
                                    st.text(line)
                            st.rerun()
                        else:
                            st.error(f"❌ 再解析に失敗: {result.stderr[:200]}")
                    except Exception as e:
                        st.error(f"❌ エラー: {e}")

        # 現在の予想条件を表示
        with st.expander("🔧 現在の予想条件", expanded=False):
            conn_rules = sqlite3.connect(DATABASE_PATH)

            # 有効な法則を取得
            query_active_rules = """
                SELECT rule_type, COUNT(*) as count
                FROM venue_rules
                WHERE is_active = 1
                GROUP BY rule_type
                ORDER BY count DESC
            """
            df_active_rules = pd.read_sql_query(query_active_rules, conn_rules)

            if not df_active_rules.empty:
                st.markdown("**📜 適用中の法則**")

                rule_type_names = {
                    'general': '全般',
                    'tidal': '潮汐',
                    'water': '水面',
                    'wind': '風',
                    'season': '季節',
                    'time': '時間帯',
                    'kimarite': '決まり手'
                }

                cols = st.columns(len(df_active_rules))
                for idx, (_, rule) in enumerate(df_active_rules.iterrows()):
                    with cols[idx]:
                        rule_name = rule_type_names.get(rule['rule_type'], rule['rule_type'])
                        st.metric(f"{rule_name}", f"{rule['count']}件")

                # 全法則の一覧表示（有効/無効切り替え可能）
                st.markdown("---")
                st.markdown("**🎛️ 法則の有効/無効を切り替え**")

                query_all_rules = """
                    SELECT id, venue_code, description, is_active
                    FROM venue_rules
                    ORDER BY is_active DESC, id
                """
                df_all_rules = pd.read_sql_query(query_all_rules, conn_rules)

                for idx, rule in df_all_rules.iterrows():
                    col1, col2, col3 = st.columns([1, 6, 2])

                    with col1:
                        current_state = bool(rule['is_active'])
                        new_state = st.checkbox(
                            "有効" if current_state else "無効",
                            value=current_state,
                            key=f"rule_toggle_{rule['id']}",
                            label_visibility="collapsed"
                        )

                        # 状態が変わったら更新
                        if new_state != current_state:
                            c_update = conn_rules.cursor()
                            c_update.execute(
                                "UPDATE venue_rules SET is_active = ? WHERE id = ?",
                                (1 if new_state else 0, rule['id'])
                            )
                            conn_rules.commit()
                            st.rerun()

                    with col2:
                        venue_tag = f"[{rule['venue_code']}] " if rule['venue_code'] else "[全国] "
                        opacity = "1.0" if rule['is_active'] else "0.4"
                        st.markdown(
                            f"<span style='opacity:{opacity}'>{venue_tag}{rule['description']}</span>",
                            unsafe_allow_html=True
                        )

                    with col3:
                        if rule['is_active']:
                            st.markdown("🟢 適用中")
                        else:
                            st.markdown("⚫ 無効")

            else:
                st.info("登録されている法則がありません")

            conn_rules.close()

            st.markdown("---")
            st.markdown("**📊 基本予想モデル**")
            st.write("• XGBoost機械学習モデル")
            st.write("• 過去180日間のデータで学習")
            st.write("• 1号艇の基本勝率: 48.65% (データから抽出)")

        try:
            realtime_predictor = RealtimePredictor()
            race_predictor = RacePredictor()

            # 本日のレース一覧を取得
            today_races = realtime_predictor.get_today_races()

            if not today_races:
                st.warning("本日開催予定のレースが見つかりませんでした")
            else:
                st.success(f"本日開催: {len(today_races)}レース")

                # おすすめレースを抽出（信頼度が高い順）
                recommended_races = []

                for race_info in today_races[:20]:  # 最初の20レースをチェック
                    try:
                        # レースキー情報
                        race_date = race_info['date']
                        venue_code = race_info['venue_code']
                        race_number = race_info['race_number']
                        race_id_str = f"{race_date}_{venue_code}_{race_number:02d}"

                        # 予想を生成（新しいメソッドを使用）
                        predictions = race_predictor.predict_race_by_key(
                            race_date,
                            venue_code,
                            race_number
                        )

                        if predictions and len(predictions) > 0:
                            # トップ3を取得
                            top3 = predictions[:3]

                            # 信頼度：1位の total_score を基準に計算（簡易版）
                            # total_score が高いほど信頼度が高い
                            confidence = min(top3[0]['total_score'], 100.0)

                            if confidence >= 60:
                                recommended_races.append({
                                    '会場': race_info.get('venue_name', ''),
                                    'レース': f"{race_number}R",
                                    '時刻': race_info.get('race_time', ''),
                                    '1着予想': f"{top3[0]['pit_number']}号艇 {top3[0]['racer_name']}",
                                    '2着予想': f"{top3[1]['pit_number']}号艇 {top3[1]['racer_name']}" if len(top3) > 1 else '',
                                    '3着予想': f"{top3[2]['pit_number']}号艇 {top3[2]['racer_name']}" if len(top3) > 2 else '',
                                    '信頼度': f"{confidence:.1f}%",
                                    '推奨買い目': f"{top3[0]['pit_number']}-{top3[1]['pit_number']}-{top3[2]['pit_number']}",
                                    'race_date': race_date,
                                    'venue_code': venue_code,
                                    'race_number': race_number,
                                    'race_id': race_id_str  # 互換性のため残す
                                })
                    except Exception as e:
                        continue

                if recommended_races:
                    st.subheader(f"🌟 本日の注目レース ({len(recommended_races)}件)")

                    # データフレーム表示
                    df = pd.DataFrame(recommended_races)

                    # race_idを除外して表示
                    display_df = df.drop('race_id', axis=1)

                    st.table(
                        display_df)

                    # 個別レース詳細
                    st.markdown("---")
                    st.subheader("📋 レース詳細")

                    for idx, race in enumerate(recommended_races[:5]):  # 上位5レースの詳細表示
                        with st.expander(f"{race['会場']} {race['レース']} - {race['時刻']} (信頼度: {race['信頼度']})"):
                            col1, col2 = st.columns(2)

                            with col1:
                                st.markdown("**🎯 予想**")
                                st.write(f"🥇 1着: {race['1着予想']}")
                                st.write(f"🥈 2着: {race['2着予想']}")
                                st.write(f"🥉 3着: {race['3着予想']}")

                            with col2:
                                st.markdown("**💰 買い目**")
                                st.write(race['推奨買い目'])
                                st.metric("信頼度", race['信頼度'])

                            # このレースに適用されている法則を表示
                            st.markdown("---")
                            st.markdown("**🔍 このレースの判断根拠**")

                            # 法則エンジンから適用法則を取得
                            try:
                                applied_rules = race_predictor.get_applied_rules_by_key(
                                    race['race_date'],
                                    race['venue_code'],
                                    race['race_number']
                                )

                                if applied_rules:
                                    st.markdown("**適用法則:**")
                                    for i, rule in enumerate(applied_rules[:5], 1):
                                        effect_sign = "+" if rule['effect_value'] > 0 else ""
                                        effect_pct = rule['effect_value'] * 100

                                        # 法則タイプに応じたアイコン
                                        rule_type = rule.get('type', '競艇場法則')
                                        if rule_type == '競艇場法則':
                                            icon = '🏟️'
                                        elif rule_type == '選手法則':
                                            icon = '👤'
                                        else:
                                            icon = '📌'

                                        st.write(f"{i}. {icon} {rule['description']} ({effect_sign}{effect_pct:+.1f}%)")
                                else:
                                    st.write("基本モデルのみで予想（法則未適用）")
                            except Exception as e:
                                st.write(f"法則取得エラー: {e}")

                            st.markdown("**予想の特徴:**")
                            confidence_val = float(race['信頼度'].replace('%', ''))
                            if confidence_val >= 80:
                                st.success("✅ 高信頼度: モデルが強く推奨しています")
                            elif confidence_val >= 70:
                                st.info("ℹ️ 中信頼度: 比較的堅実な予想です")
                            else:
                                st.warning("⚠️ 標準信頼度: 慎重に検討してください")
                else:
                    st.info("現時点で信頼度60%以上のおすすめレースはありません")

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
            import traceback
            st.code(traceback.format_exc())

    # Tab 2: ハイブリッド予測（実験#001-#022統合）
    with tab2:
        render_hybrid_prediction_page()

    # Tab 3: リアルタイム予想
    with tab3:
        st.header("🔮 リアルタイム予想")
        st.markdown("本日・これから開催されるレースの予想を表示します")

        # 本日のデータ取得ボタン
        with st.expander("📥 本日のレースデータ取得", expanded=False):
            st.markdown("**本日開催のレースデータをDBに取り込みます**")
            st.info("出走表・展示タイム・オッズなどを取得して予想の精度を向上させます")

            if st.button("🔄 本日のデータを取得", type="primary", key="fetch_today_data"):
                with st.spinner("本日のレースデータを取得中..."):
                    import subprocess
                    try:
                        today_date = datetime.now().strftime("%Y-%m-%d")

                        # BulkScraperを使用して本日のデータを取得
                        scraper = BulkScraper()

                        # 本日開催の会場を取得
                        schedule_scraper = scraper.schedule_scraper
                        today_schedule = schedule_scraper.get_today_schedule()

                        if today_schedule:
                            st.info(f"本日開催: {len(today_schedule)}会場")

                            # 各会場のデータを取得
                            total_races = 0
                            for venue_code, race_date in today_schedule.items():
                                result = scraper.fetch_multiple_venues(
                                    venue_codes=[venue_code],
                                    race_date=race_date,
                                    race_count=12
                                )
                                if venue_code in result:
                                    total_races += len(result[venue_code])

                            st.success(f"✅ 本日のデータ取得完了！ {total_races}レース取得しました")
                            st.rerun()
                        else:
                            st.warning("本日開催のレースが見つかりませんでした")
                    except Exception as e:
                        st.error(f"❌ データ取得エラー: {e}")

        st.markdown("---")

        try:
            realtime_predictor = RealtimePredictor()
            race_predictor = RacePredictor()

            today_races = realtime_predictor.get_today_races()

            if not today_races:
                st.warning("本日開催予定のレースが見つかりませんでした")
                st.info("👆 上の「本日のレースデータ取得」ボタンでデータを取得してください")
            else:
                # 会場選択
                venue_options = list(set([r['venue_name'] for r in today_races]))
                selected_venue = st.selectbox("会場を選択", ["すべて"] + venue_options)

                # フィルタリング
                if selected_venue != "すべて":
                    filtered_races = [r for r in today_races if r['venue_name'] == selected_venue]
                else:
                    filtered_races = today_races

                # レース一覧表示
                st.subheader(f"開催レース一覧 ({len(filtered_races)}レース)")

                race_list = []
                for race in filtered_races:
                    race_list.append({
                        '会場': race['venue_name'],
                        'レース': f"{race['race_number']}R",
                        '日付': race['date'],
                        'ステータス': race.get('status', '未確定')
                    })

                df_races = pd.DataFrame(race_list)
                st.table(df_races)

                # レース選択
                st.markdown("---")
                st.subheader("レース選択して予想を表示")

                col1, col2 = st.columns(2)
                with col1:
                    selected_venue_detail = st.selectbox("会場", venue_options, key='venue_detail')
                with col2:
                    venue_races = [r for r in today_races if r['venue_name'] == selected_venue_detail]
                    race_numbers = [r['race_number'] for r in venue_races]
                    selected_race_num = st.selectbox("レース番号", race_numbers)

                # 選択されたレースの予想を自動表示
                if st.button("予想を表示") or True:  # 常に自動表示
                    selected_race = next(r for r in venue_races if r['race_number'] == selected_race_num)
                    race_id = f"{selected_race['date']}_{selected_race['venue_code']}_{selected_race['race_number']:02d}"

                    with st.spinner("予想を生成中..."):
                        prediction = race_predictor.predict_race(race_id)

                        if prediction:
                            st.success("予想完了！")

                            # 買い目を自動表示
                            col1, col2, col3 = st.columns(3)

                            with col1:
                                st.metric("🥇 1着予想", prediction.get('winner', '-'))
                            with col2:
                                st.metric("🥈 2着予想", prediction.get('second', '-'))
                            with col3:
                                st.metric("🥉 3着予想", prediction.get('third', '-'))

                            st.markdown("---")

                            # 信頼度
                            confidence = prediction.get('confidence', 0)
                            st.metric("信頼度", f"{confidence:.1f}%")
                            st.progress(confidence / 100)

                            # 買い目表示（自動表示）
                            st.markdown("### 💰 推奨買い目")
                            st.info(prediction.get('recommended_bet', '買い目情報なし'))

                            # Kelly基準購入推奨（オプション表示）
                            if st.checkbox("💰 Kelly基準で購入推奨を計算", value=False, key="show_kelly"):
                                st.markdown("---")
                                st.markdown("### 📊 Kelly基準 購入推奨")

                                try:
                                    # 予測確率を取得（ダミーデータ - 実際はpredictionから取得）
                                    predictions = [
                                        {'combination': '1-2-3', 'prob': 0.15},
                                        {'combination': '1-3-2', 'prob': 0.12},
                                        {'combination': '2-1-3', 'prob': 0.10}
                                    ]

                                    # オッズデータ（ダミー - 実際はAPIから取得）
                                    odds_data = {
                                        '1-2-3': 8.5,
                                        '1-3-2': 12.3,
                                        '2-1-3': 15.7
                                    }

                                    # 購入推奨を表示
                                    render_betting_recommendations(
                                        predictions=predictions,
                                        odds_data=odds_data,
                                        buy_score=confidence / 100,
                                        bankroll=10000
                                    )
                                except Exception as kelly_error:
                                    st.warning(f"Kelly基準計算エラー: {kelly_error}")

                            # 詳細情報
                            with st.expander("予想詳細"):
                                st.json(prediction)
                        else:
                            st.warning("予想データを生成できませんでした")

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
            import traceback
            st.code(traceback.format_exc())

    # Tab 4: 購入履歴
    with tab4:
        render_bet_history_page()

    # Tab 5: 場攻略
    with tab5:
        render_venue_analysis_page()

    # Tab 6: 選手分析
    with tab6:
        render_racer_analysis_page()

    # Tab 7: モデル学習
    with tab7:
        render_model_training_page()

    # Tab 8: バックテスト
    with tab8:
        render_backtest_page()

    # Tab 9: 設定・データ管理
    with tab9:
        st.header("⚙️ 設定・データ管理")

        setting_page = st.selectbox(
            "カテゴリを選択",
            [
                "過去データ取得",
                "システム設定",
                "レース結果管理",
                "データ充足率チェック",
                "特徴量計算",
                "MLデータ出力",
                "データ排出",
                "過去レース統計"
            ]
        )

        if setting_page == "過去データ取得":
            # Old tab4 content
            st.markdown("---")
            st.subheader("📥 過去データ取得")
            # 改善版一括データ収集UI
            render_bulk_data_collector(filter_target_date, filter_selected_venues)

            # オリジナル展示データ収集
            st.markdown("---")
            render_original_tenji_collector()

        elif setting_page == "システム設定":
            # Old tab7 content
            st.markdown("---")
            st.subheader("⚙️ システム設定")
            st.text(f"データベースパス: {DATABASE_PATH}")

            st.subheader("競艇場一覧")
            venues_list = list(VENUES.items())
            for venue_id, venue_info in venues_list[:5]:
                st.text(f"{venue_info['code']}: {venue_info['name']}")

        elif setting_page == "レース結果管理":
            # Old tab8 content
            st.markdown("---")
            st.subheader("📝 レース結果管理")

            try:
                result_mgr = ResultManager()
                st.subheader("最近の結果")

                conn = sqlite3.connect(DATABASE_PATH)
                df = pd.read_sql_query("""
                    SELECT
                        r.race_date,
                        r.venue_code,
                        r.race_number,
                        MAX(CASE WHEN res.rank = 1 THEN res.pit_number END) as first_place,
                        MAX(CASE WHEN res.rank = 2 THEN res.pit_number END) as second_place,
                        MAX(CASE WHEN res.rank = 3 THEN res.pit_number END) as third_place
                    FROM races r
                    LEFT JOIN results res ON r.id = res.race_id
                    WHERE res.rank <= 3
                    GROUP BY r.id, r.race_date, r.venue_code, r.race_number
                    ORDER BY r.race_date DESC, r.race_number DESC
                    LIMIT 20
                """, conn)
                conn.close()

                if not df.empty:
                    st.table(df)
                else:
                    st.info("結果データがありません")

            except Exception as e:
                st.error(f"エラー: {e}")

        elif setting_page == "データ充足率チェック":
            # Old tab9 content
            st.markdown("---")
            st.subheader("📋 データ充足率チェック")
            st.markdown("### 機械学習に必要なデータの取得状況を確認")

            try:
                checker = DataCoverageChecker(DATABASE_PATH)

                # レポート生成
                with st.spinner("データを分析中..."):
                    report = checker.get_coverage_report()

                # 全体スコア表示
                overall_score = report["overall_score"]
                st.metric("全体データ充足率", f"{overall_score*100:.1f}%")

                # プログレスバー (0.0～1.0の範囲に制限)
                progress_value = min(max(overall_score, 0.0), 1.0)
                st.progress(progress_value)

                if overall_score >= 0.8:
                    st.success("データは充実しています。機械学習の準備ができています。")
                elif overall_score >= 0.5:
                    st.warning("データは中程度です。いくつかの重要項目が不足しています。")
                else:
                    st.error("データが不足しています。追加のデータ収集が必要です。")

                st.markdown("---")

                # カテゴリ別詳細
                st.subheader("📊 カテゴリ別データ充足率")

                # カテゴリごとのスコアを表示
                categories = report["categories"]
                category_scores = []
                for cat_name, cat_data in categories.items():
                    category_scores.append({
                        "カテゴリ": cat_name,
                        "充足率": f"{cat_data['score']*100:.1f}%",
                        "スコア": cat_data['score']
                    })

                df_categories = pd.DataFrame(category_scores)
                df_categories = df_categories.sort_values("スコア", ascending=False)
                st.table(
                    df_categories[["カテゴリ", "充足率"]])

                st.markdown("---")

                # 各カテゴリの詳細をエクスパンダーで表示
                st.subheader("📋 詳細データ項目")

                for cat_name, cat_data in categories.items():
                    with st.expander(f"{cat_name} (充足率: {cat_data['score']*100:.1f}%)"):
                        items_list = []
                        for item in cat_data["items"]:
                            importance_stars = "★" * item["importance"]
                            items_list.append({
                                "項目": item["name"],
                                "重要度": importance_stars,
                                "状態": item["status"],
                                "充足率": f"{item['coverage']*100:.1f}%",
                                "備考": item.get("note", "")
                            })

                        df_items = pd.DataFrame(items_list)
                        st.table(df_items)

                st.markdown("---")

                # 不足項目リスト
                st.subheader("⚠️ 不足しているデータ項目（重要度順）")

                missing_items = checker.get_missing_items()

                if missing_items:
                    missing_list = []
                    for item in missing_items[:15]:  # 上位15件
                        importance_stars = "★" * item["importance"]
                        missing_list.append({
                            "カテゴリ": item["category"],
                            "項目": item["name"],
                            "重要度": importance_stars,
                            "状態": item["status"],
                            "充足率": f"{item['coverage']*100:.1f}%",
                            "備考": item["note"]
                        })

                    df_missing = pd.DataFrame(missing_list)
                    st.table(df_missing)

                    # 優先対応項目
                    st.markdown("### 🎯 優先対応が必要な項目")
                    high_priority = [item for item in missing_items if item["importance"] >= 4]

                    if high_priority:
                        for item in high_priority[:5]:
                            st.warning(f"**{item['name']}** (★{item['importance']}) - {item['status']} - {item['note']}")
                    else:
                        st.info("重要度の高い不足項目はありません")

                else:
                    st.success("全てのデータ項目が充足しています！")

                st.markdown("---")

                # 統計情報
                st.subheader("📈 データ統計")

                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric("総レース数", f"{report['total_races']:,}")

                with col2:
                    conn = sqlite3.connect(DATABASE_PATH)
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM entries")
                    total_entries = cursor.fetchone()[0]
                    conn.close()
                    st.metric("総出走表数", f"{total_entries:,}")

                with col3:
                    conn = sqlite3.connect(DATABASE_PATH)
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM results")
                    total_results = cursor.fetchone()[0]
                    conn.close()
                    st.metric("総結果数", f"{total_results:,}")

                # データ期間
                st.markdown("### 📅 データ期間")
                conn = sqlite3.connect(DATABASE_PATH)
                cursor = conn.cursor()
                cursor.execute("SELECT MIN(race_date), MAX(race_date) FROM races")
                min_date, max_date = cursor.fetchone()
                conn.close()

                if min_date and max_date:
                    col1, col2 = st.columns(2)
                    with col1:
                        st.info(f"最古データ: {min_date}")
                    with col2:
                        st.info(f"最新データ: {max_date}")

            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
                import traceback
                st.code(traceback.format_exc())

        elif setting_page == "特徴量計算":
            # Old tab10 content
            st.markdown("---")
            st.subheader("🧮 特徴量エンジニアリング")
            st.markdown("### 機械学習用の特徴量を計算・確認")

            try:
                calculator = FeatureCalculator(DATABASE_PATH)

                # 競艇場コードから名前へのマッピング
                venue_code_to_name = {
                    '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島',
                    '05': '多摩川', '06': '浜名湖', '07': '蒲郡', '08': '常滑',
                    '09': '津', '10': '三国', '11': 'びわこ', '12': '住之江',
                    '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島',
                    '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
                    '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
                }

                # 競艇場選択
                if len(filter_selected_venues) > 0:
                    selected_venue_code = filter_selected_venues[0]
                    selected_venue_display = f"{venue_code_to_name.get(selected_venue_code, '不明')}({selected_venue_code})"
                else:
                    selected_venue_code = '01'  # デフォルト
                    selected_venue_display = f"{venue_code_to_name.get(selected_venue_code, '不明')}({selected_venue_code})"

                st.info(f"📍 対象: {selected_venue_display} （サイドバーで変更可能）")

                # 集計期間
                days = st.slider("集計期間（日数）", 30, 365, 180, key="feature_days")

                st.markdown("---")

                # 特徴量サマリー
                st.subheader("📊 特徴量サマリー")

                with st.spinner("特徴量を計算中..."):
                    summary = calculator.export_features_summary(selected_venue_code, days)

                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    st.metric("モーター数", f"{summary['motor_count']}")
                with col2:
                    st.metric("ボート数", f"{summary['boat_count']}")
                with col3:
                    st.metric("1号艇逃げ率", f"{summary['escape_rate']*100:.1f}%")
                with col4:
                    st.metric("進入固定率", f"{summary['fixed_entry_rate']*100:.1f}%")

                col1, col2 = st.columns(2)
                with col1:
                    st.metric("モーター平均2連対率", f"{summary['avg_motor_place_rate_2']*100:.1f}%")
                with col2:
                    st.metric("ボート平均2連対率", f"{summary['avg_boat_place_rate_2']*100:.1f}%")

                st.markdown("---")

                # モーター連対率
                st.subheader("⚙️ モーター連対率")

                motor_stats = calculator.calculate_motor_stats(selected_venue_code, days)

                if motor_stats:
                    motor_list = []
                    for motor_no, stats in motor_stats.items():
                        motor_list.append({
                            "モーター番号": motor_no,
                            "レース数": stats["total_races"],
                            "勝率": f"{stats['win_rate']*100:.1f}%",
                            "2連対率": f"{stats['place_rate_2']*100:.1f}%",
                            "3連対率": f"{stats['place_rate_3']*100:.1f}%"
                        })

                    df_motor = pd.DataFrame(motor_list)
                    # 2連対率でソート
                    df_motor["sort_key"] = df_motor["2連対率"].str.rstrip('%').astype(float)
                    df_motor = df_motor.sort_values("sort_key", ascending=False).drop("sort_key", axis=1)

                    st.table(df_motor)

                    # TOP5とWORST5
                    st.markdown("#### 🏆 TOP5モーター")
                    top5 = df_motor.head(5)
                    st.table(top5)

                    st.markdown("#### ⚠️ WORST5モーター")
                    worst5 = df_motor.tail(5)
                    st.table(worst5)
                else:
                    st.info("モーターデータがありません")

                st.markdown("---")

                # ボート連対率
                st.subheader("🚤 ボート連対率")

                boat_stats = calculator.calculate_boat_stats(selected_venue_code, days)

                if boat_stats:
                    boat_list = []
                    for boat_no, stats in boat_stats.items():
                        boat_list.append({
                            "ボート番号": boat_no,
                            "レース数": stats["total_races"],
                            "勝率": f"{stats['win_rate']*100:.1f}%",
                            "2連対率": f"{stats['place_rate_2']*100:.1f}%",
                            "3連対率": f"{stats['place_rate_3']*100:.1f}%"
                        })

                    df_boat = pd.DataFrame(boat_list)
                    # 2連対率でソート
                    df_boat["sort_key"] = df_boat["2連対率"].str.rstrip('%').astype(float)
                    df_boat = df_boat.sort_values("sort_key", ascending=False).drop("sort_key", axis=1)

                    st.table(df_boat)
                else:
                    st.info("ボートデータがありません")

                st.markdown("---")

                # 選手コース別成績
                st.subheader("👤 選手コース別成績")

                # 選手選択
                conn = sqlite3.connect(DATABASE_PATH)
                query_racers = """
                    SELECT DISTINCT
                        e.racer_number,
                        e.racer_name,
                        COUNT(DISTINCT r.id) as race_count
                    FROM entries e
                    JOIN races r ON e.race_id = r.id
                    WHERE r.venue_code = ?
                      AND r.race_date >= date('now', '-180 days')
                    GROUP BY e.racer_number, e.racer_name
                    HAVING race_count >= 5
                    ORDER BY race_count DESC
                    LIMIT 50
                """
                df_racers = pd.read_sql_query(query_racers, conn, params=[selected_venue_code])
                conn.close()

                if not df_racers.empty:
                    selected_racer_idx = st.selectbox(
                        "選手を選択",
                        options=range(len(df_racers)),
                        format_func=lambda i: f"{df_racers.iloc[i]['racer_name']} ({df_racers.iloc[i]['racer_number']}) - {df_racers.iloc[i]['race_count']}レース"
                    )

                    selected_racer_number = df_racers.iloc[selected_racer_idx]['racer_number']
                    selected_racer_name = df_racers.iloc[selected_racer_idx]['racer_name']

                    st.markdown(f"**選手**: {selected_racer_name} ({selected_racer_number})")

                    course_stats = calculator.calculate_racer_course_stats(selected_racer_number, days)

                    if course_stats:
                        course_list = []
                        for course, stats in sorted(course_stats.items()):
                            course_list.append({
                                "コース": f"{course}コース",
                                "レース数": stats["total_races"],
                                "勝率": f"{stats['win_rate']*100:.1f}%",
                                "2連対率": f"{stats['place_rate_2']*100:.1f}%",
                                "3連対率": f"{stats['place_rate_3']*100:.1f}%"
                            })

                        df_course = pd.DataFrame(course_list)
                        st.table(df_course)

                        # グラフ表示
                        import plotly.graph_objects as go

                        courses = [f"{c}C" for c in sorted(course_stats.keys())]
                        win_rates = [course_stats[c]["win_rate"]*100 for c in sorted(course_stats.keys())]
                        place2_rates = [course_stats[c]["place_rate_2"]*100 for c in sorted(course_stats.keys())]

                        fig = go.Figure()
                        fig.add_trace(go.Bar(name='勝率', x=courses, y=win_rates))
                        fig.add_trace(go.Bar(name='2連対率', x=courses, y=place2_rates))

                        fig.update_layout(
                            title=f"{selected_racer_name} - コース別成績",
                            xaxis_title="コース",
                            yaxis_title="確率 (%)",
                            barmode='group'
                        )

                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("コース別成績データがありません")
                else:
                    st.info("選手データがありません")

                st.markdown("---")

                # 進入パターン分析
                st.subheader("🔄 進入パターン分析")

                entry_pattern = calculator.calculate_course_entry_pattern(selected_venue_code, days)

                col1, col2 = st.columns(2)

                with col1:
                    st.metric("総レース数", f"{entry_pattern['total_races']:,}")
                    st.metric("進入固定レース数", f"{entry_pattern['fixed_entry_races']:,}")

                with col2:
                    st.metric("進入固定率", f"{entry_pattern['fixed_entry_rate']*100:.1f}%")
                    st.metric("進入変動率", f"{entry_pattern['irregular_entry_rate']*100:.1f}%")

                # 進入固定率の評価
                if entry_pattern['fixed_entry_rate'] > 0.9:
                    st.success("この競艇場は進入が非常に固定的です（枠番=コース）")
                elif entry_pattern['fixed_entry_rate'] > 0.7:
                    st.info("この競艇場は進入がやや固定的です")
                else:
                    st.warning("この競艇場は進入変動が多いです（スリット駆け引きに注意）")

            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
                import traceback
                st.code(traceback.format_exc())

        elif setting_page == "MLデータ出力":
            # Old tab11 content
            st.markdown("---")
            st.subheader("📤 データ出力")

            # サブタブで機能を分割
            subtab1, subtab2 = st.tabs(["🤖 ML用データ出力", "📊 汎用データエクスポート"])

            with subtab1:
                st.subheader("機械学習用データ出力")
                st.markdown("XGBoost + SHAP用のデータセットを生成・エクスポート")

                try:
                    builder = DatasetBuilder(DATABASE_PATH)
                    st.info("機械学習用の特徴量データセットを生成し、CSV/JSON形式でエクスポートできます")

                    # データ期間選択
                    col1, col2 = st.columns(2)
                    with col1:
                        start_date = st.date_input("開始日", value=datetime.now() - timedelta(days=180), key="ml_start_date")
                    with col2:
                        end_date = st.date_input("終了日", value=datetime.now(), key="ml_end_date")

                    if st.button("データセット生成", type="primary"):
                        with st.spinner("データセット生成中..."):
                            X, y = builder.build_dataset(
                                start_date=start_date.strftime("%Y-%m-%d"),
                                end_date=end_date.strftime("%Y-%m-%d")
                            )
                            if X is not None:
                                st.success(f"データセット生成完了: {len(X)}件")
                                st.dataframe(X.head(10))
                except Exception as e:
                    st.error(f"エラー: {e}")

            with subtab2:
                render_data_export_page()

        elif setting_page == "データ排出":
            # Data export page
            st.markdown("---")
            render_data_export_page()

        elif setting_page == "過去レース統計":
            # Past races summary
            st.markdown("---")
            render_past_races_summary()


if __name__ == "__main__":
    main()
