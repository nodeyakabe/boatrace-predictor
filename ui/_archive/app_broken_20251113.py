"""
競艇予想システム - Streamlit UIアプリケーション
"""

import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import sys
import os
import subprocess
import threading

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH, VENUES
from src.analysis.realtime_predictor import RealtimePredictor
from src.analysis.race_predictor import RacePredictor
from src.prediction.stage2_predictor import Stage2Predictor
from src.analysis.statistics_calculator import StatisticsCalculator
from src.analysis.data_quality import DataQualityMonitor
from src.analysis.backtest import Backtester
from src.analysis.pattern_analyzer import PatternAnalyzer
from src.analysis.rule_validator import RuleValidator
from src.analysis.data_coverage_checker import DataCoverageChecker
from src.analysis.feature_calculator import FeatureCalculator
from src.ml.dataset_builder import DatasetBuilder
from src.ml.model_trainer import ModelTrainer
# from src.ml.shap_explainer import SHAPExplainer  # shapライブラリ未インストールのためコメントアウト
from src.utils.result_manager import ResultManager
from src.scraper.bulk_scraper import BulkScraper
from src.database.views import initialize_views
from ui.components.bet_history import render_bet_history_page


def main():
    st.set_page_config(
        page_title="コンドル",
        page_icon="🚤",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # データベースビューを初期化（起動時に一度だけ実行）
    try:
        initialize_views(DATABASE_PATH)
    except Exception as e:
        st.warning(f"ビュー初期化エラー: {e}")

    st.title("🚤 コンドル")

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

        # レース情報取得セクション
        with st.expander("📥 レース情報取得", expanded=False):
            st.subheader("データ収集")

            # 最終保存日を取得
            try:
                conn = sqlite3.connect(DATABASE_PATH)
                cursor = conn.cursor()
                cursor.execute('SELECT MAX(race_date) FROM races')
                last_date_result = cursor.fetchone()
                conn.close()

                if last_date_result and last_date_result[0]:
                    last_date = datetime.strptime(last_date_result[0], '%Y-%m-%d')
                    next_date = last_date + timedelta(days=1)
                else:
                    last_date = datetime.now() - timedelta(days=7)
                    next_date = last_date + timedelta(days=1)

                st.info(f"最終保存日: {last_date.strftime('%Y-%m-%d')}")
            except Exception as e:
                st.error(f"最終保存日取得エラー: {e}")
                next_date = datetime.now() - timedelta(days=7)

            # 日付範囲選択
            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input(
                    "開始日",
                    value=next_date,
                    max_value=datetime.now(),
                    key="fetch_start_date"
                )
            with col2:
                end_date = st.date_input(
                    "終了日",
                    value=datetime.now(),
                    max_value=datetime.now(),
                    key="fetch_end_date"
                )

            # オプション
            workers = st.slider("並列ワーカー数", min_value=1, max_value=10, value=3, key="fetch_workers")

            col1, col2 = st.columns(2)
            with col1:
                skip_tenji = st.checkbox("オリジナル展示スキップ", value=False, key="skip_tenji")
            with col2:
                skip_tide = st.checkbox("潮位データスキップ", value=False, key="skip_tide")

            # 取得ボタン
            if st.button("🚀 レース情報取得", type="primary", use_container_width=True):
                start_str = start_date.strftime('%Y-%m-%d')
                end_str = end_date.strftime('%Y-%m-%d')

                # コマンド構築
                cmd = [
                    sys.executable,
                    os.path.join(PROJECT_ROOT, 'fetch_all_data_comprehensive.py'),
                    '--start', start_str,
                    '--end', end_str,
                    '--workers', str(workers)
                ]

                if skip_tenji:
                    cmd.append('--skip-original-tenji')
                if skip_tide:
                    cmd.append('--skip-tide')

                # 実行
                with st.spinner(f'データ取得中... ({start_str} ～ {end_str})'):
                    try:
                        result = subprocess.run(
                            cmd,
                            capture_output=True,
                            text=True,
                            timeout=3600,
                            cwd=PROJECT_ROOT,
                            encoding='utf-8',
                            errors='replace'
                        )

                        if result.returncode == 0:
                            st.success("データ取得完了！")
                            with st.expander("実行ログ"):
                                st.text(result.stdout)
                        else:
                            st.error("データ取得エラー")
                            with st.expander("エラー詳細"):
                                st.text(result.stderr)
                    except subprocess.TimeoutExpired:
                        st.error("データ取得がタイムアウトしました（1時間）")
                    except Exception as e:
                        st.error(f"エラー: {e}")

            # 取得データ一覧
            with st.expander("取得データ詳細"):
                st.markdown("""
                **公式サイトから取得（HTTP）**:
                - レース結果（着順・タイム・決まり手）
                - 展示タイム・チルト角・部品交換
                - STタイム・進入コース
                - 天気データ
                - 払戻金

                **Seleniumで取得（ブラウザ自動化）**:
                - オリジナル展示データ（直線・一周・回り足）
                - 潮位データ（満潮・干潮、海水場のみ）
                """)

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

    # タブ定義（整理版：検証・データ管理系を設定タブにまとめた）
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
        "🏠 ホーム",
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
                                [os.path.join(PROJECT_ROOT, 'venv', 'Scripts', 'python.exe'), os.path.join(PROJECT_ROOT, 'analyze_venue_patterns.py')],
                                capture_output=True,
                                text=True,
                                timeout=300,
                                cwd=PROJECT_ROOT
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
                                [os.path.join(PROJECT_ROOT, 'venv', 'Scripts', 'python.exe'), os.path.join(PROJECT_ROOT, 'register_top_racer_rules.py')],
                                capture_output=True,
                                text=True,
                                timeout=600,
                                cwd=PROJECT_ROOT
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
                            [os.path.join(PROJECT_ROOT, 'venv', 'Scripts', 'python.exe'), os.path.join(PROJECT_ROOT, 'reanalyze_all.py')],
                            capture_output=True,
                            text=True,
                            timeout=900,
                            cwd=PROJECT_ROOT
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

    # Tab 2: リアルタイム予想
    with tab2:
        st.header("🔮 リアルタイム予想")
        st.markdown("本日・これから開催されるレースの予想を表示します")

        try:
            realtime_predictor = RealtimePredictor()
            race_predictor = RacePredictor()

            today_races = realtime_predictor.get_today_races()

            if not today_races:
                st.warning("本日開催予定のレースが見つかりませんでした")
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

                # 直前情報取得ボタン
                st.markdown("---")
                col_btn1, col_btn2 = st.columns(2)

                with col_btn1:
                    fetch_beforeinfo_btn = st.button("📊 直前情報を取得", use_container_width=True, type="secondary")

                with col_btn2:
                    show_prediction_btn = st.button("🔮 予想を表示", use_container_width=True, type="primary")

                # 直前情報取得処理
                if fetch_beforeinfo_btn:
                    selected_race = next(r for r in venue_races if r['race_number'] == selected_race_num)

                    with st.spinner("直前情報を取得中..."):
                        from src.scraper.beforeinfo_fetcher import BeforeInfoFetcher

                        fetcher = BeforeInfoFetcher()
                        beforeinfo = fetcher.fetch_beforeinfo(
                            selected_race['date'].replace('-', ''),
                            selected_race['venue_code'],
                            selected_race['race_number']
                        )

                        if beforeinfo:
                            st.success("✅ 直前情報取得完了！")

                            # 水面気象情報を表示
                            st.markdown("### 🌊 水面気象情報")
                            weather = beforeinfo['weather']

                            col_w1, col_w2, col_w3, col_w4 = st.columns(4)
                            with col_w1:
                                st.metric("天候", weather.get('weather', '不明'))
                            with col_w2:
                                temp = weather.get('temperature')
                                st.metric("気温", f"{temp}℃" if temp else "不明")
                            with col_w3:
                                wind = weather.get('wind_speed')
                                st.metric("風速", f"{wind}m" if wind else "不明")
                            with col_w4:
                                wave = weather.get('wave_height')
                                st.metric("波高", f"{wave}cm" if wave else "不明")

                            # 選手情報を表示
                            st.markdown("### 👤 選手直前情報")

                            if beforeinfo['racers']:
                                racers_df = pd.DataFrame(beforeinfo['racers'])

                                # 表示用に整形
                                display_cols = []
                                if 'pit_number' in racers_df.columns:
                                    display_cols.append('pit_number')
                                if 'racer_name' in racers_df.columns:
                                    display_cols.append('racer_name')
                                if 'weight' in racers_df.columns:
                                    display_cols.append('weight')
                                if 'exhibition_time' in racers_df.columns:
                                    display_cols.append('exhibition_time')
                                if 'start_timing' in racers_df.columns:
                                    display_cols.append('start_timing')
                                if 'tilt' in racers_df.columns:
                                    display_cols.append('tilt')
                                if 'course' in racers_df.columns:
                                    display_cols.append('course')

                                if display_cols:
                                    display_df = racers_df[display_cols].copy()
                                    display_df.columns = ['枠', '選手名', '体重(kg)', '展示タイム', 'ST', 'チルト', 'コース']
                                    st.dataframe(display_df, use_container_width=True)
                                else:
                                    st.info("選手情報の取得に失敗しました（HTML構造が変更された可能性があります）")
                            else:
                                st.warning("選手情報が取得できませんでした")

                            # セッションステートに保存
                            st.session_state['beforeinfo'] = beforeinfo
                        else:
                            st.error("❌ 直前情報の取得に失敗しました")

                # 選択されたレースの予想を表示
                if show_prediction_btn or True:  # 常に自動表示
                    selected_race = next(r for r in venue_races if r['race_number'] == selected_race_num)
                    race_id = f"{selected_race['date']}_{selected_race['venue_code']}_{selected_race['race_number']:02d}"

                    with st.spinner("予想を生成中..."):
                        # Stage2モデルを試行、失敗時はルールベースにフォールバック
                        use_stage2 = False
                        stage2_predictor = None

                        try:
                            stage2_predictor = Stage2Predictor(db_path=DATABASE_PATH)
                            if stage2_predictor.model_loaded:
                                use_stage2 = True
                                st.info("🤖 Stage2モデル（機械学習）を使用")
                            else:
                                st.warning("⚠️ Stage2モデル未学習 - ルールベース予測を使用")
                        except Exception as e:
                            st.warning(f"⚠️ Stage2モデルエラー - ルールベースにフォールバック: {str(e)[:50]}")

                        # Stage2モデルで予測
                        if use_stage2 and stage2_predictor:
                            try:
                                # トップ3を取得
                                top3_stage2 = stage2_predictor.predict_top3(
                                    selected_race['date'],
                                    selected_race['venue_code'],
                                    selected_race['race_number']
                                )

                                # 三連単の組み合わせ確率を取得
                                bet_predictions = stage2_predictor.calculate_sanrentan_probabilities(
                                    selected_race['date'],
                                    selected_race['venue_code'],
                                    selected_race['race_number'],
                                    top_n=10
                                )

                                if top3_stage2 and bet_predictions:
                                    st.success("✅ Stage2予想完了！")

                                    # 上位3艇の予想を表示
                                    col1, col2, col3 = st.columns(3)

                                    with col1:
                                        boat = top3_stage2[0]
                                        st.metric("🥇 1着予想",
                                                 f"{boat['pit_number']}号艇 {boat['racer_name']}",
                                                 delta=f"{boat['prob_1st']:.1%}")
                                    with col2:
                                        if len(top3_stage2) > 1:
                                            boat = top3_stage2[1]
                                            st.metric("🥈 2着予想",
                                                     f"{boat['pit_number']}号艇 {boat['racer_name']}",
                                                     delta=f"{boat['prob_1st']:.1%}")
                                        else:
                                            st.metric("🥈 2着予想", '-')
                                    with col3:
                                        if len(top3_stage2) > 2:
                                            boat = top3_stage2[2]
                                            st.metric("🥉 3着予想",
                                                     f"{boat['pit_number']}号艇 {boat['racer_name']}",
                                                     delta=f"{boat['prob_1st']:.1%}")
                                        else:
                                            st.metric("🥉 3着予想", '-')

                                    st.markdown("---")

                                    # 信頼度（1着確率ベース）
                                    confidence = top3_stage2[0]['prob_1st'] * 100
                                    st.metric("信頼度（1着確率）", f"{confidence:.1f}%")
                                    st.progress(min(confidence / 100, 1.0))

                                    # 買い目表示
                                    st.markdown("### 💰 推奨買い目")
                                    recommended_bet = f"{top3_stage2[0]['pit_number']}-{top3_stage2[1]['pit_number']}-{top3_stage2[2]['pit_number']}"
                                    st.info(f"三連単: {recommended_bet}")

                                    # Kelly基準での購入推奨を表示
                                    from ui.components.betting_recommendation import render_betting_recommendations

                                else:
                                    # Stage2予測失敗時はルールベースにフォールバック
                                    use_stage2 = False
                                    st.warning("⚠️ Stage2予測データ不足 - ルールベースを使用")

                            except Exception as e:
                                st.error(f"❌ Stage2予測エラー: {str(e)[:100]}")
                                use_stage2 = False

                        # ルールベース予測（フォールバック）
                        if not use_stage2:
                            predictions_list = race_predictor.predict_race_by_key(
                                selected_race['date'],
                                selected_race['venue_code'],
                                selected_race['race_number']
                            )

                            if predictions_list:
                                st.success("予想完了！（ルールベース）")

                                # 上位3艇の予想を表示
                                top3 = predictions_list[:3]

                                col1, col2, col3 = st.columns(3)

                                with col1:
                                    st.metric("🥇 1着予想", f"{top3[0]['pit_number']}号艇 {top3[0]['racer_name']}")
                                with col2:
                                    st.metric("🥈 2着予想", f"{top3[1]['pit_number']}号艇 {top3[1]['racer_name']}" if len(top3) > 1 else '-')
                                with col3:
                                    st.metric("🥉 3着予想", f"{top3[2]['pit_number']}号艇 {top3[2]['racer_name']}" if len(top3) > 2 else '-')

                                st.markdown("---")

                                # 信頼度（total_scoreベース）
                                confidence = min(top3[0]['total_score'], 100.0)
                                st.metric("信頼度", f"{confidence:.1f}%")
                                st.progress(confidence / 100)

                                # 買い目表示（自動表示）
                                st.markdown("### 💰 推奨買い目")
                                recommended_bet = f"{top3[0]['pit_number']}-{top3[1]['pit_number']}-{top3[2]['pit_number']}"
                                st.info(f"三連単: {recommended_bet}")

                                # Kelly基準での購入推奨を表示
                                from ui.components.betting_recommendation import render_betting_recommendations

                                # 三連単の予測確率を計算（上位10組み合わせ）
                                bet_predictions = []
                                for i in range(min(len(predictions_list), 6)):
                                    for j in range(min(len(predictions_list), 6)):
                                        if j == i:
                                            continue
                                        for k in range(min(len(predictions_list), 6)):
                                            if k == i or k == j:
                                                continue

                                            # 組み合わせ確率を計算（簡易版：各艇のスコアの積）
                                            combined_prob = (
                                                predictions_list[i]['total_score'] / 100 * 0.6 *
                                                predictions_list[j]['total_score'] / 100 * 0.3 *
                                                predictions_list[k]['total_score'] / 100 * 0.1
                                            )

                                            combination = f"{predictions_list[i]['pit_number']}-{predictions_list[j]['pit_number']}-{predictions_list[k]['pit_number']}"

                                            bet_predictions.append({
                                                'combination': combination,
                                                'prob': combined_prob
                                            })

                                # 確率で並べ替え
                                bet_predictions.sort(key=lambda x: x['prob'], reverse=True)

                                # 確率を正規化（合計を1に調整）
                                total_prob = sum(p['prob'] for p in bet_predictions[:10])
                                if total_prob > 0:
                                    for p in bet_predictions[:10]:
                                        p['prob'] = p['prob'] / total_prob

                        # ここから共通処理（オッズ取得・Kelly基準）
                        if (use_stage2 and bet_predictions) or (not use_stage2 and 'bet_predictions' in locals()):
                            # オッズデータ取得（リアルAPI or モック）
                            try:
                                from src.scraper.odds_fetcher import OddsFetcher, generate_mock_odds

                                fetcher = OddsFetcher()
                                race_date_str = selected_race['date'].replace('-', '')

                                # 上位10組み合わせのオッズを取得
                                combinations = [p['combination'] for p in bet_predictions[:10]]
                                odds_data = fetcher.fetch_odds_for_combinations(
                                    race_date_str,
                                    selected_race['venue_code'],
                                    selected_race['race_number'],
                                    combinations
                                )

                                if not odds_data or len(odds_data) == 0:
                                    # APIエラー時はモック生成
                                    odds_data = generate_mock_odds(bet_predictions[:10])
                                    st.warning("⚠️ オッズAPIエラー: モックオッズを使用")
                                else:
                                    st.success(f"✅ リアルタイムオッズを取得: {len(odds_data)}件")

                            except Exception as e:
                                # フォールバック: モックオッズ
                                from src.scraper.odds_fetcher import generate_mock_odds
                                odds_data = generate_mock_odds(bet_predictions[:10])
                                st.info(f"📊 モックオッズを使用（API未実装）")

                            # レース選別スコア（Stage1モデル or 信頼度ベース）
                            try:
                                from src.ml.race_selector import RaceSelector
                                import os
                                model_path = os.path.join(PROJECT_ROOT, 'models', 'race_selector.json')

                                if os.path.exists(model_path):
                                    # Stage1モデルで予測
                                    race_selector = RaceSelector()
                                    race_selector.load_model('race_selector.json')
                                    buy_score = race_selector.predict_by_key(
                                        selected_race['date'],
                                        selected_race['venue_code'],
                                        selected_race['race_number']
                                    )
                                    st.info(f"🤖 Stage1モデル使用: レース選別スコア = {buy_score:.1%}")
                                else:
                                    # 信頼度ベース（フォールバック）
                                    buy_score = confidence / 100.0
                                    st.info(f"📊 信頼度ベース: レース選別スコア = {buy_score:.1%} （Stage1モデル未学習）")
                            except Exception as e:
                                # エラー時は信頼度ベース
                                buy_score = confidence / 100.0
                                st.warning(f"⚠️ Stage1モデルエラー（信頼度ベース使用）: {str(e)[:50]}")

                            # 資金設定
                            bankroll = st.number_input(
                                "資金（円）",
                                min_value=1000,
                                max_value=100000,
                                value=10000,
                                step=1000,
                                key='bankroll_input'
                            )

                            # Kelly基準の購入推奨を表示
                            render_betting_recommendations(
                                predictions=bet_predictions[:10],
                                odds_data=odds_data,
                                buy_score=buy_score,
                                bankroll=bankroll
                            )

                            # 詳細情報
                            with st.expander("予想詳細（全艇）"):
                                for idx, boat in enumerate(predictions_list, 1):
                                    st.markdown(f"**{idx}位予想: {boat['pit_number']}号艇 {boat['racer_name']}**")
                                    st.write(f"- スコア: {boat['total_score']:.1f}")
                                    st.write(f"- 基本スコア: {boat['base_score']:.1f}")
                                    st.write(f"- ルール補正: {boat['rule_adjustment']:.1f}")
                                    st.markdown("---")
                        else:
                            st.warning("予想データを生成できませんでした")

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
            import traceback
            st.code(traceback.format_exc())

    # Tab 3: 購入履歴
    with tab3:
        render_bet_history_page()

    # Tab 4: 場攻略 (old tab4 content)
    with tab4:
        # 表示モード選択を削除し、全ての機能を統合
        st.header("🏟️ 場攻略")
        st.markdown("各競艇場のデータと傾向を分析 - コース別勝率、決まり手、場の特性を完全解析")

        # 再解析ボタン
        st.markdown("---")
        col1, col2 = st.columns([3, 1])
        with col1:
            st.info("💡 データが増えたら再解析を実行して法則を更新できます")
        with col2:
            if st.button("🔄 競艇場法則を再解析", key="reanalyze_venues"):
                with st.spinner("競艇場パターンを再解析中..."):
                    import subprocess
                    try:
                        result = subprocess.run(
                            [os.path.join(PROJECT_ROOT, 'venv', 'Scripts', 'python.exe'), os.path.join(PROJECT_ROOT, 'analyze_venue_patterns.py')],
                            capture_output=True,
                            text=True,
                            timeout=300,
                            cwd=PROJECT_ROOT
                        )
                        if result.returncode == 0:
                            st.success("✅ 競艇場法則の再解析が完了しました！")
                            st.rerun()
                        else:
                            st.error(f"❌ 再解析に失敗しました: {result.stderr[:200]}")
                    except subprocess.TimeoutExpired:
                        st.error("⏱️ タイムアウト: 再解析に5分以上かかりました")
                    except Exception as e:
                        st.error(f"❌ エラー: {e}")
        st.markdown("---")

        try:
            stats_calc = StatisticsCalculator()

            # 集計期間を選択
            days = st.slider("集計期間（日数）", 30, 365, 90, key="stats_days")

            # サイドバーで選択された競艇場を使用
            # 競艇場コードから名前へのマッピング
            venue_code_to_name = {
                '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島',
                '05': '多摩川', '06': '浜名湖', '07': '蒲郡', '08': '常滑',
                '09': '津', '10': '三国', '11': 'びわこ', '12': '住之江',
                '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島',
                '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
                '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
            }

            # 選択された競艇場を取得（複数選択の場合は最初の1つを使用）
            if len(filter_selected_venues) > 0:
                selected_venue_code = filter_selected_venues[0]
                selected_venue_display = f"{venue_code_to_name.get(selected_venue_code, '不明')}({selected_venue_code})"
            else:
                selected_venue_code = None
                selected_venue_display = "全国"

            st.info(f"📍 分析対象: {selected_venue_display} （サイドバーで競艇場を選択してください）")
            st.markdown("---")

            # コース別勝率
            st.subheader(f"📍 {selected_venue_display} - コース別勝率")

            course_stats = stats_calc.calculate_course_stats(venue_code=selected_venue_code, days=days)

            if course_stats:
                # データフレーム用に整形
                stats_list = []
                for course, stats in course_stats.items():
                    stats_list.append({
                        'コース': f"{course}コース",
                        '総レース数': f"{stats['total_races']:,}",
                        '1着率': f"{stats['win_rate']*100:.1f}%",
                        '2着率': f"{stats['place_rate_2']*100:.1f}%",
                        '3着率': f"{stats['place_rate_3']*100:.1f}%"
                    })

                df_course = pd.DataFrame(stats_list)
                st.table(df_course)

                # 1号艇逃げ率を表示
                escape_rate = stats_calc.calculate_escape_rate(venue_code=selected_venue_code, days=days)
                st.metric("🚤 1号艇逃げ率", f"{escape_rate*100:.1f}%")
            else:
                st.info("統計データがありません")
            # 競艇場特性（競艇場選択時のみ）
            if selected_venue_code:
                st.markdown("---")
                st.subheader(f"🏟️ {selected_venue_display} - 場の特性")
                venue_chars = stats_calc.calculate_venue_characteristics(selected_venue_code, days=days)
                col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("1号艇逃げ率", f"{venue_chars['escape_rate']*100:.1f}%")
            with col2:
                st.metric("イン勝率(1-3C)", f"{venue_chars['inside_win_rate']*100:.1f}%")
            with col3:
                st.metric("平均配当", f"¥{venue_chars['avg_payout']:.0f}")
            with col4:
                st.metric("万舟率", f"{venue_chars['high_payout_rate']*100:.2f}%")
            # 固い場か荒れる場かの判定
            if venue_chars['escape_rate'] > 0.6:
                st.success("⭐ この場は「固い場」です（1号艇の勝率が高い）")
            elif venue_chars['high_payout_rate'] > 0.03:
                st.warning("🌊 この場は「荒れる場」です（高配当が出やすい）")
            else:
                st.info("📊 この場は標準的な傾向です")
            # 傾向の言語化
                st.markdown("---")
                st.subheader(f"💬 {selected_venue_display} - 傾向分析（AI言語化）")
            try:
                pattern_analyzer = PatternAnalyzer()
                venue_summary = pattern_analyzer.get_venue_summary_text(selected_venue_code, days=days)
                st.text_area("分析結果", venue_summary, height=300, key="venue_pattern_text")
        
            except Exception as e:
                st.warning(f"傾向分析でエラーが発生しました: {e}")
            # 時間帯別分析
            if selected_venue_code:
                st.markdown("---")
                st.subheader(f"⏰ {selected_venue_display} - 時間帯別分析")

                try:
                    # 時間帯別の1号艇勝率を取得
                    query_time = """
                        SELECT
                            CASE
                                WHEN CAST(substr(r.race_time, 1, 2) AS INTEGER) < 12 THEN '午前'
                                WHEN CAST(substr(r.race_time, 1, 2) AS INTEGER) < 15 THEN '午後前半'
                                ELSE '午後後半'
                            END as time_zone,
                            COUNT(*) as total_races,
                            AVG(CASE WHEN res.rank = 1 AND rd.actual_course = 1 THEN 1.0 ELSE 0.0 END) as course1_win_rate,
                            AVG(CASE WHEN res.rank = 1 THEN 1.0 ELSE 0.0 END) as overall_win_rate
                        FROM races r
                        JOIN race_details rd ON r.id = rd.race_id
                        LEFT JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
                        WHERE r.venue_code = ?
                          AND r.race_date >= date('now', ? || ' days')
                          AND r.race_time IS NOT NULL
                        GROUP BY time_zone
                        ORDER BY time_zone
                    """
                    conn_time = sqlite3.connect(DATABASE_PATH)
                    df_time = pd.read_sql_query(query_time, conn_time, params=[selected_venue_code, -days])
                    conn_time.close()

                    if not df_time.empty:
                        df_time['時間帯'] = df_time['time_zone']
                        df_time['レース数'] = df_time['total_races']
                        df_time['1コース勝率'] = (df_time['course1_win_rate'] * 100).round(1).astype(str) + '%'
                        df_time_display = df_time[['時間帯', 'レース数', '1コース勝率']]
                        st.table(df_time_display)

                        # 時間帯による傾向分析
                        max_time = df_time.loc[df_time['course1_win_rate'].idxmax(), 'time_zone']
                        min_time = df_time.loc[df_time['course1_win_rate'].idxmin(), 'time_zone']
                        st.info(f"💡 **{max_time}**が最も1コース有利（{selected_venue_display}）")
                    else:
                        st.info("時間帯別データが不足しています")
                except Exception as e:
                    st.warning(f"時間帯別分析でエラーが発生しました: {e}")
            # 季節別分析
            if selected_venue_code:
                st.markdown("---")
                st.subheader(f"🌸 {selected_venue_display} - 季節別分析")

                try:
                query_season = """
                SELECT
                CASE
                WHEN CAST(substr(r.race_date, 6, 2) AS INTEGER) IN (3, 4, 5) THEN '春'
                WHEN CAST(substr(r.race_date, 6, 2) AS INTEGER) IN (6, 7, 8) THEN '夏'
                WHEN CAST(substr(r.race_date, 6, 2) AS INTEGER) IN (9, 10, 11) THEN '秋'
                ELSE '冬'
                END as season,
                COUNT(*) as total_races,
                AVG(CASE WHEN res.rank = 1 AND rd.actual_course = 1 THEN 1.0 ELSE 0.0 END) as course1_win_rate,
                AVG(CASE WHEN res.rank = 1 AND rd.actual_course <= 3 THEN 1.0 ELSE 0.0 END) as inside_win_rate
                FROM races r
                JOIN race_details rd ON r.id = rd.race_id
                LEFT JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
                WHERE r.venue_code = ?
                AND r.race_date >= date('now', ? || ' days')
                GROUP BY season
                ORDER BY
                CASE season
                WHEN '春' THEN 1
                WHEN '夏' THEN 2
                WHEN '秋' THEN 3
                ELSE 4
                END
                """
                conn_season = sqlite3.connect(DATABASE_PATH)
                df_season = pd.read_sql_query(query_season, conn_season, params=[selected_venue_code, -days])
                conn_season.close()
            if not df_season.empty:
                df_season['季節'] = df_season['season']
                df_season['レース数'] = df_season['total_races']
                df_season['1コース勝率'] = (df_season['course1_win_rate'] * 100).round(1).astype(str) + '%'
                df_season['インコース勝率'] = (df_season['inside_win_rate'] * 100).round(1).astype(str) + '%'
                df_season_display = df_season[['季節', 'レース数', '1コース勝率', 'インコース勝率']]
                st.table(df_season_display)
            # 季節による傾向分析
                max_season = df_season.loc[df_season['course1_win_rate'].idxmax(), 'season']
                min_season = df_season.loc[df_season['course1_win_rate'].idxmin(), 'season']
                st.info(f"💡 **{max_season}**が最も1コース有利、**{min_season}**が最も荒れやすい（{selected_venue_display}）")
            else:
                st.info("季節別データが不足しています")
            except Exception as e:
                st.warning(f"季節別分析でエラーが発生しました: {e}")
            # 全24場比較データ
            if not selected_venue_code:
                st.markdown("---")
                st.subheader("🏆 全国24場 - 勝率ランキング")
                try:
                    query_all_venues = """
                    SELECT
                    r.venue_code,
                    COUNT(*) as total_races,
                    AVG(CASE WHEN res.rank = 1 AND rd.actual_course = 1 THEN 1.0 ELSE 0.0 END) as course1_win_rate,
                    AVG(CASE WHEN res.rank = 1 AND rd.actual_course <= 3 THEN 1.0 ELSE 0.0 END) as inside_win_rate
                    FROM races r
                    JOIN race_details rd ON r.id = rd.race_id
                    LEFT JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
                    WHERE r.race_date >= date('now', ? || ' days')
                    GROUP BY r.venue_code
                    HAVING total_races >= 50
                    ORDER BY course1_win_rate DESC
                    """
                    conn_all = sqlite3.connect(DATABASE_PATH)
                    df_all_venues = pd.read_sql_query(query_all_venues, conn_all, params=[-days])
                    conn_all.close()
                    if not df_all_venues.empty:
                        df_all_venues['競艇場'] = df_all_venues['venue_code'].apply(
                        lambda x: f"{venue_code_to_name.get(x, '不明')}({x})"
                        )
                        df_all_venues['レース数'] = df_all_venues['total_races']
                        df_all_venues['1コース勝率'] = (df_all_venues['course1_win_rate'] * 100).round(1).astype(str) + '%'
                        df_all_venues['インコース勝率'] = (df_all_venues['inside_win_rate'] * 100).round(1).astype(str) + '%'
                        df_all_display = df_all_venues[['競艇場', 'レース数', '1コース勝率', 'インコース勝率']]
                        # TOP10とBOTTOM5を表示
                        st.markdown("**1コース勝率が高い場（固い場）TOP10**")
                        st.table(df_all_display.head(10))
                        st.markdown("**1コース勝率が低い場（荒れる場）BOTTOM5**")
                        st.table(df_all_display.tail(5))
                    else:
                        st.info("全国比較データが不足しています")
                except Exception as e:
                    st.warning(st.warning(f"全国比較分析でエラーが発生しました: {e}")
            # 決まり手分析
                st.markdown("---")
                st.subheader(f"🎯 {selected_venue_display} - 決まり手分析")
            try:
                kimarite_dist = stats_calc.calculate_kimarite_distribution(venue_code=selected_venue_code, days=days)
            if kimarite_dist:
            # 決まり手の分布を表示
                kimarite_list = []
            for kimarite, data in kimarite_dist.items():
                kimarite_list.append({
                '決まり手': kimarite,
                '回数': f"{data['count']:,}",
                '割合': f"{data['rate']*100:.1f}%"
                })
                df_kimarite = pd.DataFrame(kimarite_list)
                st.table(df_kimarite)
            # バーチャートで視覚化
                chart_data = pd.DataFrame({
                '決まり手': [k for k in kimarite_dist.keys()],
                '割合': [v['rate']*100 for v in kimarite_dist.values()]
                })
                st.bar_chart(chart_data.set_index('決まり手'))
            else:
                st.info("決まり手データがありません")
            except Exception as e:
                st.warning(f"決まり手分析でエラーが発生しました: {e}")
            # コース別決まり手確率
                st.markdown("---")
                st.subheader(f"📊 {selected_venue_display} - コース別決まり手確率")
            try:
                course_kimarite = stats_calc.calculate_course_kimarite_stats(venue_code=selected_venue_code, days=days)
            if course_kimarite:
            # コース別決まり手確率を表で表示
            # Noneキーを除外
                course_kimarite = {k: v for k, v in course_kimarite.items() if k is not None}

            # 全決まり手のリストを取得
                all_kimarite = set()
            for course_data in course_kimarite.values():
                all_kimarite.update(course_data.keys())

            # データフレーム用に整形
                course_kimarite_list = []
            for course in sorted(course_kimarite.keys()):
                row_data = {'コース': f"{course}コース"}
            for kimarite in all_kimarite:
                prob = course_kimarite[course].get(kimarite, 0.0)
                row_data[kimarite] = f"{prob*100:.1f}%"
                course_kimarite_list.append(row_data)
                df_course_kimarite = pd.DataFrame(course_kimarite_list)
                st.table(df_course_kimarite)
            # 特徴的な傾向を抽出
                st.markdown("**特徴的な傾向:**")
            # 1コースの逃げ率
            if 1 in course_kimarite and '逃げ' in course_kimarite[1]:
                nige_rate = course_kimarite[1]['逃げ']
                st.write(f"- 1コース: 逃げ確率 **{nige_rate*100:.1f}%**")
            # 2-4コースのまくり率
            for course in [2, 3, 4]:
            if course in course_kimarite and 'まくり' in course_kimarite[course]:
                makuri_rate = course_kimarite[course]['まくり']
            if makuri_rate > 0.15:  # 15%以上なら表示
                st.write(f"- {course}コース: まくり確率 **{makuri_rate*100:.1f}%**")
            # 2-5コースの差し率
            for course in [2, 3, 4, 5]:
            if course in course_kimarite and '差し' in course_kimarite[course]:
                sashi_rate = course_kimarite[course]['差し']
            if sashi_rate > 0.20:  # 20%以上なら表示
                st.write(f"- {course}コース: 差し確率 **{sashi_rate*100:.1f}%**")
            else:
                st.info("コース別決まり手データがありません")
            except Exception as e:
                st.warning(f"コース別決まり手分析でエラーが発生しました: {e}")
            # 登録されている法則の表示と管理
                st.markdown("---")
                st.subheader(f"📜 {selected_venue_display} - 登録法則")
            # 法則の表示
                conn_rules = sqlite3.connect(DATABASE_PATH)
            # 該当する法則を取得（全国共通 + 選択された場専用）
            if selected_venue_code:
                query_rules = """
                SELECT id, venue_code, rule_type, condition_type, target_pit,
                effect_type, effect_value, description, is_active
                FROM venue_rules
                WHERE (venue_code IS NULL OR venue_code = ?)
                AND is_active = 1
                ORDER BY
                CASE WHEN venue_code IS NULL THEN 1 ELSE 0 END,
                id
                """
                df_rules = pd.read_sql_query(query_rules, conn_rules, params=[selected_venue_code])
            else:
                query_rules = """
                SELECT id, venue_code, rule_type, condition_type, target_pit,
                effect_type, effect_value, description, is_active
                FROM venue_rules
                WHERE venue_code IS NULL AND is_active = 1
                ORDER BY id
                """
                df_rules = pd.read_sql_query(query_rules, conn_rules)
            if not df_rules.empty:
                st.markdown(f"**適用可能な法則: {len(df_rules)}件**")
            # 法則をカテゴリ別に表示
                venue_specific_rules = df_rules[df_rules['venue_code'].notna()]
                general_rules = df_rules[df_rules['venue_code'].isna()]
            if not venue_specific_rules.empty:
                st.markdown(f"##### 🏟️ {selected_venue_display}専用法則")
            for idx, rule in venue_specific_rules.iterrows():
                effect_sign = "+" if rule['effect_value'] > 0 else ""
                effect_pct = rule['effect_value'] * 100
            # 法則の種類に応じたアイコン
                icon = {
                'tidal': '🌊',
                'water': '💧',
                'wind': '💨',
                'season': '🌸',
                'time': '⏰',
                'kimarite': '🎯'
                }.get(rule['rule_type'], '📌')
                col1, col2 = st.columns([5, 1])
            with col1:
                st.info(f"{icon} **{rule['description']}**")
            with col2:
            if st.button("❌", key=f"del_rule_{rule['id']}"):
                c_del = conn_rules.cursor()
                c_del.execute("UPDATE venue_rules SET is_active = 0 WHERE id = ?", (rule['id'],))
                conn_rules.commit()
                st.rerun()
            if not general_rules.empty:
                st.markdown("##### 🌐 全国共通法則")
            for idx, rule in general_rules.iterrows():
                effect_sign = "+" if rule['effect_value'] > 0 else ""
                effect_pct = rule['effect_value'] * 100
                icon = {
                'general': '📊',
                'kimarite': '🎯',
                'time': '⏰'
                }.get(rule['rule_type'], '📌')
                col1, col2 = st.columns([5, 1])
            with col1:
                st.info(f"{icon} **{rule['description']}**")
            with col2:
            if st.button("❌", key=f"del_rule_{rule['id']}"):
                c_del = conn_rules.cursor()
                c_del.execute("UPDATE venue_rules SET is_active = 0 WHERE id = ?", (rule['id'],))
                conn_rules.commit()
                st.rerun()
            else:
                st.info("登録されている法則がありません")
            # 新規法則の追加
                st.markdown("---")
                st.subheader("➕ 新規法則の登録")
            with st.expander("新しい法則を追加"):
                col1, col2 = st.columns(2)
            with col1:
                new_rule_type = st.selectbox(
                "法則の種類",
                ["general", "tidal", "water", "wind", "season", "time", "kimarite"],
                format_func=lambda x: {
                'general': '全般',
                'tidal': '潮汐（干潮・満潮）',
                'water': '水面状況',
                'wind': '風向・風速',
                'season': '季節',
                'time': '時間帯',
                'kimarite': '決まり手'
                }.get(x, x),
                key="new_rule_type"
                )
                new_condition = st.text_input("条件（例: 干潮、強風、夏季）", key="new_condition")
                new_target_pit = st.selectbox(
                "対象艇番",
                [1, 2, 3, 4, 5, 6],
                key="new_target_pit"
                )
            with col2:
                new_effect_type = st.selectbox(
                "効果の種類",
                ["win_rate_boost", "win_rate_penalty", "place2_rate_boost", "place3_rate_boost"],
                format_func=lambda x: {
                'win_rate_boost': '勝率UP',
                'win_rate_penalty': '勝率DOWN',
                'place2_rate_boost': '2連対率UP',
                'place3_rate_boost': '3連対率UP'
                }.get(x, x),
                key="new_effect_type"
                )
                new_effect_value = st.slider(
                "効果の大きさ（%）",
                -20, 20, 5,
                key="new_effect_value"
                )
                new_venue_specific = st.checkbox(
                f"{selected_venue_display}専用法則として登録",
                value=bool(selected_venue_code),
                key="new_venue_specific"
                )
                new_description = st.text_area(
                "法則の説明",
                placeholder=f"例: {selected_venue_display}：干潮時は2号艇の1着率+10%",
                key="new_description"
                )
            if st.button("📝 法則を登録", key="add_rule_btn"):
            if new_description.strip():
                c_add = conn_rules.cursor()
                venue_for_rule = selected_venue_code if new_venue_specific and selected_venue_code else None
                c_add.execute("""
                INSERT INTO venue_rules
                (venue_code, rule_type, condition_type, target_pit, effect_type, effect_value, description)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                venue_for_rule,
                new_rule_type,
                new_condition if new_condition.strip() else None,
                new_target_pit,
                new_effect_type,
                new_effect_value / 100.0,
                new_description.strip()
                ))
                conn_rules.commit()
                st.success("✅ 法則を登録しました！")
                st.rerun()
            else:
                st.error("法則の説明を入力してください")
                conn_rules.close()
            except Exception as e:
                st.error(f"エラー: {e}")
                import traceback
                st.code(traceback.format_exc())

            # Tab 5: 選手 (old tab5 content)
            with tab5:
            # 表示モード選択
                racer_display_mode = st.radio(
                "表示モード",
                ["選手分析（新）", "選手情報"],
                horizontal=True,
                key="racer_display_mode"
                )

            if racer_display_mode == "選手分析（新）":
            # 新しい選手分析UI（レーダーチャート等）
                from ui.components.racer_analysis import render_racer_analysis_page
                render_racer_analysis_page()

            else:
                st.header("👤 選手情報")

            # 再解析ボタン
                st.markdown("---")
                col1, col2 = st.columns([3, 1])
            with col1:
                st.info("💡 データが増えたら再解析を実行して選手法則を更新できます")
            with col2:
            if st.button("🔄 選手法則を再解析", key="reanalyze_racers"):
            with st.spinner("トップ選手法則を再解析中..."):
                import subprocess
            try:
                result = subprocess.run(
                [os.path.join(PROJECT_ROOT, 'venv', 'Scripts', 'python.exe'), os.path.join(PROJECT_ROOT, 'register_top_racer_rules.py')],
                capture_output=True,
                text=True,
                timeout=600,
                cwd=PROJECT_ROOT
                )
            if result.returncode == 0:
                st.success("✅ 選手法則の再解析が完了しました！")
                st.rerun()
            else:
                st.error(f"❌ 再解析に失敗しました: {result.stderr[:200]}")
            except subprocess.TimeoutExpired:
                st.error("⏱️ タイムアウト: 再解析に10分以上かかりました")
            except Exception as e:
                st.error(f"❌ エラー: {e}")
                st.markdown("---")

            # 場所を選択
                venue_code_to_name = {
                '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島',
                '05': '多摩川', '06': '浜名湖', '07': '蒲郡', '08': '常滑',
                '09': '津', '10': '三国', '11': 'びわこ', '12': '住之江',
                '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島',
                '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
                '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
                }

            if len(filter_selected_venues) > 0:
                selected_venue_code = filter_selected_venues[0]
                selected_venue_display = f"{venue_code_to_name.get(selected_venue_code, '不明')}({selected_venue_code})"
            else:
                selected_venue_code = None
                selected_venue_display = "全国"

            # セッションステートで選手選択を管理
            if 'selected_racer_detail' not in st.session_state:
            st.session_state.selected_racer_detail = None

            try:
            conn = sqlite3.connect(DATABASE_PATH)

            # 選択された競艇場の選手一覧を取得
            if selected_venue_code:
                query = """
                    SELECT DISTINCT
                        e.racer_number,
                        e.racer_name,
                        COUNT(DISTINCT r.id) as race_count,
                        AVG(CASE WHEN res.rank = 1 THEN 1.0 ELSE 0.0 END) as win_rate,
                        AVG(CASE WHEN res.rank <= 2 THEN 1.0 ELSE 0.0 END) as place_rate_2,
                        AVG(CASE WHEN res.rank <= 3 THEN 1.0 ELSE 0.0 END) as place_rate_3
                    FROM entries e
                    JOIN races r ON e.race_id = r.id
                    LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
                    WHERE r.venue_code = ?
                      AND r.race_date >= date('now', '-180 days')
                    GROUP BY e.racer_number, e.racer_name
                    HAVING race_count >= 3
                    ORDER BY win_rate DESC
                    LIMIT 100
                """
                df_racers = pd.read_sql_query(query, conn, params=[selected_venue_code])
            else:
                query = """
                    SELECT DISTINCT
                        e.racer_number,
                        e.racer_name,
                        COUNT(DISTINCT r.id) as race_count,
                        AVG(CASE WHEN res.rank = 1 THEN 1.0 ELSE 0.0 END) as win_rate,
                        AVG(CASE WHEN res.rank <= 2 THEN 1.0 ELSE 0.0 END) as place_rate_2,
                        AVG(CASE WHEN res.rank <= 3 THEN 1.0 ELSE 0.0 END) as place_rate_3
                    FROM entries e
                    JOIN races r ON e.race_id = r.id
                    LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
                    WHERE r.race_date >= date('now', '-180 days')
                    GROUP BY e.racer_number, e.racer_name
                    HAVING race_count >= 5
                    ORDER BY win_rate DESC
                    LIMIT 200
                """
                df_racers = pd.read_sql_query(query, conn)

            if not df_racers.empty:
                # 詳細表示中かどうかで表示を切り替え
                if st.session_state.selected_racer_detail is None:
                    # 一覧表示モード
                    st.subheader(f"📍 {selected_venue_display} - 選手一覧")
                    st.info(f"過去180日間のデータ ({len(df_racers)}名)")

                    # 検索ボックス
                    search_query = st.text_input("🔍 選手名で検索", "", key="racer_search")

                    if search_query:
                        df_filtered = df_racers[df_racers['racer_name'].str.contains(search_query, na=False)]
                    else:
                        df_filtered = df_racers

                    st.markdown(f"**表示中: {len(df_filtered)}名**")

                    # 選手名のリンク表示（5列）
                    cols_per_row = 5
                    for i in range(0, len(df_filtered), cols_per_row):
                        cols = st.columns(cols_per_row)
                        for j, col in enumerate(cols):
                            idx = i + j
                            if idx < len(df_filtered):
                                racer = df_filtered.iloc[idx]
                                with col:
                                    if st.button(
                                        f"{racer['racer_name']}\n({racer['win_rate']*100:.1f}%)",
                                        key=f"racer_btn_{racer['racer_number']}",
                                        use_container_width=True
                                    ):
                                        st.session_state.selected_racer_detail = racer['racer_number']
                                        st.rerun()

                else:
                    # 詳細表示モード
                    selected_racer = st.session_state.selected_racer_detail

                    # 戻るボタン
                    if st.button("← 一覧に戻る", key="back_to_list"):
                        st.session_state.selected_racer_detail = None
                        st.rerun()

                    st.markdown("---")

                    # 選手の詳細成績を取得
                    conn = sqlite3.connect(DATABASE_PATH)

                    # 基本情報
                    racer_info = df_racers[df_racers['racer_number'] == selected_racer].iloc[0]
                    st.markdown(f"### {racer_info['racer_name']} (登録番号: {selected_racer})")

                    # 全選手中のランキングを計算
                    rank_win = (df_racers['win_rate'] > racer_info['win_rate']).sum() + 1
                    rank_2rate = (df_racers['place_rate_2'] > racer_info['place_rate_2']).sum() + 1
                    rank_3rate = (df_racers['place_rate_3'] > racer_info['place_rate_3']).sum() + 1
                    total_racers = len(df_racers)

                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("出走数", f"{int(racer_info['race_count'])}回")
                    with col2:
                        st.metric("勝率", f"{racer_info['win_rate']*100:.1f}%",
                                 delta=f"{rank_win}/{total_racers}位")
                    with col3:
                        st.metric("2連対率", f"{racer_info['place_rate_2']*100:.1f}%",
                                 delta=f"{rank_2rate}/{total_racers}位")
                    with col4:
                        st.metric("3連対率", f"{racer_info['place_rate_3']*100:.1f}%",
                                 delta=f"{rank_3rate}/{total_racers}位")

                    # 最近の調子分析（直近10走）
                    st.markdown("---")
                    st.markdown("#### 📈 最近の調子")

                    query_recent_trend = """
                        SELECT
                            CAST(res.rank AS INTEGER) as rank,
                            r.race_date
                        FROM entries e
                        JOIN races r ON e.race_id = r.id
                        LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
                        WHERE e.racer_number = ?
                          AND res.rank IS NOT NULL
                        ORDER BY r.race_date DESC, r.race_number DESC
                        LIMIT 10
                    """
                    df_recent_trend = pd.read_sql_query(query_recent_trend, conn, params=[selected_racer])

                    if not df_recent_trend.empty and len(df_recent_trend) >= 5:
                        # 念のため数値型に変換
                        df_recent_trend['rank'] = pd.to_numeric(df_recent_trend['rank'], errors='coerce')
                        recent_wins = (df_recent_trend['rank'] == 1).sum()
                        recent_top2 = (df_recent_trend['rank'] <= 2).sum()
                        recent_top3 = (df_recent_trend['rank'] <= 3).sum()

                        col1, col2, col3 = st.columns(3)
                        with col1:
                            win_pct = recent_wins / len(df_recent_trend) * 100
                            st.metric("直近10走 1着率", f"{win_pct:.1f}%",
                                     delta=f"{recent_wins}回")
                        with col2:
                            top2_pct = recent_top2 / len(df_recent_trend) * 100
                            st.metric("直近10走 2連対率", f"{top2_pct:.1f}%",
                                     delta=f"{recent_top2}回")
                        with col3:
                            top3_pct = recent_top3 / len(df_recent_trend) * 100
                            st.metric("直近10走 3連対率", f"{top3_pct:.1f}%",
                                     delta=f"{recent_top3}回")

                        # 調子の評価
                        if win_pct > racer_info['win_rate'] * 100 * 1.2:
                            st.success("🔥 最近絶好調！通常より1着率が高い")
                        elif win_pct < racer_info['win_rate'] * 100 * 0.8:
                            st.warning("⚠️ 最近不調気味。通常より1着率が低い")
                        else:
                            st.info("📊 安定した成績を維持")
                    else:
                        st.info("データ不足（10走未満）")

                    # コース別成績（詳細版）
                    st.markdown("---")
                    st.markdown("#### 🎯 コース別成績")
                    query_course = """
                        SELECT
                            rd.actual_course as course,
                            COUNT(*) as races,
                            SUM(CASE WHEN res.rank = 1 THEN 1 ELSE 0 END) as first,
                            SUM(CASE WHEN res.rank = 2 THEN 1 ELSE 0 END) as second,
                            SUM(CASE WHEN res.rank = 3 THEN 1 ELSE 0 END) as third,
                            AVG(CASE WHEN res.rank = 1 THEN 1.0 ELSE 0.0 END) as win_rate,
                            AVG(CASE WHEN res.rank <= 2 THEN 1.0 ELSE 0.0 END) as place_rate_2,
                            AVG(CASE WHEN res.rank <= 3 THEN 1.0 ELSE 0.0 END) as place_rate_3
                        FROM entries e
                        JOIN races r ON e.race_id = r.id
                        JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
                        LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
                        WHERE e.racer_number = ?
                          AND r.race_date >= date('now', '-180 days')
                        GROUP BY rd.actual_course
                        ORDER BY rd.actual_course
                    """
                    df_course = pd.read_sql_query(query_course, conn, params=[selected_racer])

                    if not df_course.empty:
                        # NaN値を含む行を除外
                        df_course = df_course.dropna(subset=['course'])

                        # コース別成績を視覚的に表示
                        for idx, row in df_course.iterrows():
                            course_num = int(row['course'])
                            col1, col2, col3, col4, col5, col6 = st.columns([1, 1, 1, 1, 1, 2])

                            with col1:
                                st.markdown(f"**{course_num}コース**")
                            with col2:
                                st.text(f"{int(row['races'])}走")
                            with col3:
                                st.text(f"1着: {int(row['first'])}回")
                            with col4:
                                st.text(f"2着: {int(row['second'])}回")
                            with col5:
                                st.text(f"3着: {int(row['third'])}回")
                            with col6:
                                # バーで視覚化
                                win_pct = row['win_rate'] * 100 if pd.notna(row['win_rate']) else 0
                                st.progress(min(win_pct / 100, 1.0))
                                place_rate = row['place_rate_2'] * 100 if pd.notna(row['place_rate_2']) else 0
                                st.caption(f"1着率: {win_pct:.1f}% / 2連対: {place_rate:.1f}%")

                        # 得意コース・苦手コースの分析
                        if len(df_course) > 0:
                            best_course = df_course.loc[df_course['win_rate'].idxmax()]
                            worst_course = df_course.loc[df_course['win_rate'].idxmin()]

                            col1, col2 = st.columns(2)
                            with col1:
                                st.success(f"得意コース: **{int(best_course['course'])}コース** ({best_course['win_rate']*100:.1f}%)")
                            with col2:
                                st.warning(f"苦手コース: **{int(worst_course['course'])}コース** ({worst_course['win_rate']*100:.1f}%)")
                        else:
                            st.info("コース別成績データがありません")

                    # 決まり手分布
                    st.markdown("#### 決まり手の分布")
                    query_kimarite = """
                        SELECT
                            res.kimarite,
                            COUNT(*) as count
                        FROM entries e
                        JOIN races r ON e.race_id = r.id
                        LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
                        WHERE e.racer_number = ?
                          AND r.race_date >= date('now', '-180 days')
                          AND res.rank = 1
                          AND res.kimarite IS NOT NULL
                        GROUP BY res.kimarite
                        ORDER BY count DESC
                    """
                    df_kimarite = pd.read_sql_query(query_kimarite, conn, params=[selected_racer])

                    if not df_kimarite.empty:
                        total_wins = df_kimarite['count'].sum()
                        df_kimarite['割合'] = (df_kimarite['count'] / total_wins * 100).round(1).astype(str) + '%'
                        df_kimarite['回数'] = df_kimarite['count'].astype(str) + '回'
                        df_kimarite_display = df_kimarite[['kimarite', '回数', '割合']]
                        df_kimarite_display.columns = ['決まり手', '回数', '割合']
                        st.table(df_kimarite_display)

                        # 得意技を表示
                        if len(df_kimarite) > 0:
                            best_kimarite = df_kimarite.iloc[0]['kimarite']
                            best_rate = df_kimarite.iloc[0]['count'] / total_wins * 100
                            st.success(f"🎯 得意技: **{best_kimarite}** ({best_rate:.1f}%)")
                    else:
                        st.info("決まり手データがありません")

                    # 競艇場別成績
                    st.markdown("#### 競艇場別成績")
                    query_venue_stats = """
                        SELECT
                            r.venue_code,
                            COUNT(*) as races,
                            AVG(CASE WHEN res.rank = 1 THEN 1.0 ELSE 0.0 END) as win_rate,
                            AVG(CASE WHEN res.rank <= 2 THEN 1.0 ELSE 0.0 END) as place_rate_2,
                            AVG(CASE WHEN res.rank <= 3 THEN 1.0 ELSE 0.0 END) as place_rate_3
                        FROM entries e
                        JOIN races r ON e.race_id = r.id
                        LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
                        WHERE e.racer_number = ?
                          AND r.race_date >= date('now', '-180 days')
                        GROUP BY r.venue_code
                        HAVING races >= 3
                        ORDER BY win_rate DESC
                        LIMIT 10
                    """
                    df_venue_stats = pd.read_sql_query(query_venue_stats, conn, params=[selected_racer])

                    if not df_venue_stats.empty:
                        df_venue_stats['競艇場'] = df_venue_stats['venue_code'].map(venue_code_to_name)
                        df_venue_stats['勝率'] = (df_venue_stats['win_rate'] * 100).round(1).astype(str) + '%'
                        df_venue_stats['2連対率'] = (df_venue_stats['place_rate_2'] * 100).round(1).astype(str) + '%'
                        df_venue_stats['3連対率'] = (df_venue_stats['place_rate_3'] * 100).round(1).astype(str) + '%'
                        df_venue_display = df_venue_stats[['競艇場', 'races', '勝率', '2連対率', '3連対率']]
                        df_venue_display.columns = ['競艇場', 'レース数', '勝率', '2連対率', '3連対率']
                        st.table(df_venue_display)

                        # 得意場を表示
                        if len(df_venue_stats) > 0:
                            best_venue = df_venue_stats.iloc[0]['競艇場']
                            best_venue_rate = df_venue_stats.iloc[0]['win_rate'] * 100
                            st.success(f"🏟️ 得意場: **{best_venue}** (勝率{best_venue_rate:.1f}%)")
                    else:
                        st.info("競艇場別データが不足しています")

                    # STタイミング分析
                    st.markdown("---")
                    st.markdown("#### ⏱️ STタイミング分析")
                    query_st = """
                        SELECT
                            AVG(rd.st_time) as avg_st,
                            MIN(rd.st_time) as min_st,
                            MAX(rd.st_time) as max_st,
                            COUNT(*) as st_count
                        FROM entries e
                        JOIN races r ON e.race_id = r.id
                        JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
                        WHERE e.racer_number = ?
                          AND r.race_date >= date('now', '-180 days')
                          AND rd.st_time IS NOT NULL
                    """
                    df_st = pd.read_sql_query(query_st, conn, params=[selected_racer])

                    if not df_st.empty and df_st.iloc[0]['st_count'] > 0:
                        avg_st = df_st.iloc[0]['avg_st']
                        min_st = df_st.iloc[0]['min_st']
                        max_st = df_st.iloc[0]['max_st']
                        st_count = df_st.iloc[0]['st_count']

                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("平均ST", f"{avg_st:.2f}秒")
                        with col2:
                            st.metric("最速ST", f"{min_st:.2f}秒")
                        with col3:
                            st.metric("最遅ST", f"{max_st:.2f}秒")
                        with col4:
                            st.metric("データ数", f"{st_count}回")

                        # STの評価
                        if avg_st < 0.16:
                            st.success("⚡ スタートタイミングが非常に速い選手です（予想で有利）")
                        elif avg_st < 0.17:
                            st.info("✨ スタートタイミングが良い選手です")
                        else:
                            st.warning("🐢 スタートタイミングは平均的です")
                    else:
                        st.info(f"STデータがありません（データ数: {df_st.iloc[0]['st_count'] if not df_st.empty else 0}件）")

                    # 時間帯別成績
                    st.markdown("---")
                    st.markdown("#### 🕐 時間帯別成績")
                    query_time_stats = """
                        SELECT
                            CASE
                                WHEN CAST(substr(r.race_time, 1, 2) AS INTEGER) < 12 THEN '午前'
                                WHEN CAST(substr(r.race_time, 1, 2) AS INTEGER) < 15 THEN '午後前半'
                                ELSE '午後後半'
                            END as time_zone,
                            COUNT(*) as races,
                            AVG(CASE WHEN res.rank = 1 THEN 1.0 ELSE 0.0 END) as win_rate,
                            AVG(CASE WHEN res.rank <= 2 THEN 1.0 ELSE 0.0 END) as place_rate_2,
                            AVG(CASE WHEN res.rank <= 3 THEN 1.0 ELSE 0.0 END) as place_rate_3
                        FROM entries e
                        JOIN races r ON e.race_id = r.id
                        LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
                        WHERE e.racer_number = ?
                          AND r.race_date >= date('now', '-180 days')
                          AND r.race_time IS NOT NULL
                        GROUP BY time_zone
                        HAVING races >= 5
                        ORDER BY win_rate DESC
                    """
                    df_time_stats = pd.read_sql_query(query_time_stats, conn, params=[selected_racer])

                    if not df_time_stats.empty:
                        for idx, row in df_time_stats.iterrows():
                            col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
                            with col1:
                                st.markdown(f"**{row['time_zone']}**")
                            with col2:
                                st.text(f"{int(row['races'])}走")
                            with col3:
                                st.text(f"1着率: {row['win_rate']*100:.1f}%")
                            with col4:
                                st.text(f"2連対: {row['place_rate_2']*100:.1f}%")

                        # 得意時間帯の表示
                        best_time = df_time_stats.iloc[0]
                        st.info(f"💡 得意時間帯: **{best_time['time_zone']}** (1着率 {best_time['win_rate']*100:.1f}%)")
                    else:
                        st.info("時間帯別データが不足しています")

                    # モーター・ボート成績
                    st.markdown("---")
                    st.markdown("#### 🚤 使用モーター・ボート成績")
                    query_motor_boat = """
                        SELECT
                            e.motor_number,
                            e.boat_number,
                            COUNT(*) as races,
                            AVG(CASE WHEN res.rank = 1 THEN 1.0 ELSE 0.0 END) as win_rate,
                            AVG(CASE WHEN res.rank <= 2 THEN 1.0 ELSE 0.0 END) as place_rate_2,
                            r.venue_code,
                            MAX(r.race_date) as last_use_date
                        FROM entries e
                        JOIN races r ON e.race_id = r.id
                        LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
                        WHERE e.racer_number = ?
                          AND r.race_date >= date('now', '-180 days')
                          AND e.motor_number IS NOT NULL
                        GROUP BY e.motor_number, e.boat_number, r.venue_code
                        HAVING races >= 3
                        ORDER BY last_use_date DESC
                        LIMIT 10
                    """
                    df_motor_boat = pd.read_sql_query(query_motor_boat, conn, params=[selected_racer])

                    if not df_motor_boat.empty:
                        st.markdown("**最近使用した主なモーター・ボート**")
                        for idx, row in df_motor_boat.iterrows():
                            venue_name = venue_code_to_name.get(row['venue_code'], '不明')
                            col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 2])
                            with col1:
                                st.text(f"{venue_name}")
                            with col2:
                                st.text(f"M{int(row['motor_number'])} / B{int(row['boat_number'])}")
                            with col3:
                                st.text(f"{int(row['races'])}走")
                            with col4:
                                st.text(f"1着率: {row['win_rate']*100:.1f}%")
                            with col5:
                                st.text(f"2連対: {row['place_rate_2']*100:.1f}%")
                    else:
                        st.info("モーター・ボートデータが不足しています")

                    # 天候別成績
                    st.markdown("---")
                    st.markdown("#### ☀️ 天候別成績")
                    query_weather = """
                        SELECT
                            w.weather_condition as weather,
                            COUNT(*) as races,
                            AVG(CASE WHEN res.rank = 1 THEN 1.0 ELSE 0.0 END) as win_rate,
                            AVG(CASE WHEN res.rank <= 2 THEN 1.0 ELSE 0.0 END) as place_rate_2
                        FROM entries e
                        JOIN races r ON e.race_id = r.id
                        LEFT JOIN weather w ON r.venue_code = w.venue_code AND r.race_date = w.weather_date
                        LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
                        WHERE e.racer_number = ?
                          AND r.race_date >= date('now', '-180 days')
                          AND w.weather_condition IS NOT NULL
                          AND w.weather_condition != ''
                        GROUP BY w.weather_condition
                        HAVING races >= 3
                        ORDER BY win_rate DESC
                    """
                    df_weather = pd.read_sql_query(query_weather, conn, params=[selected_racer])

                    if not df_weather.empty:
                        for idx, row in df_weather.iterrows():
                            col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
                            with col1:
                                weather_icon = {"晴": "☀️", "曇": "☁️", "雨": "🌧️", "雪": "❄️"}.get(row['weather'], "🌤️")
                                st.markdown(f"**{weather_icon} {row['weather']}**")
                            with col2:
                                st.text(f"{int(row['races'])}走")
                            with col3:
                                st.text(f"1着率: {row['win_rate']*100:.1f}%")
                            with col4:
                                st.text(f"2連対: {row['place_rate_2']*100:.1f}%")

                        # 得意天候の分析
                        best_weather = df_weather.iloc[0]
                        worst_weather = df_weather.iloc[-1]
                        diff = (best_weather['win_rate'] - worst_weather['win_rate']) * 100
                        if diff > 10:
                            st.warning(f"⚠️ 天候による差が大きい: {best_weather['weather']}が得意 (+{diff:.1f}%)")
                        else:
                            st.info("📊 天候による成績差は小さい")
                    else:
                        st.info("天候別データが不足しています")

                    # 展示タイム順位別成績
                    st.markdown("---")
                    st.markdown("#### 🏁 展示タイム順位別成績")
                    query_tenji = """
                        SELECT
                            CASE
                                WHEN rd.tenji_time_rank = 1 THEN '1位'
                                WHEN rd.tenji_time_rank IN (2, 3) THEN '2-3位'
                                WHEN rd.tenji_time_rank IN (4, 5, 6) THEN '4-6位'
                                ELSE 'データなし'
                            END as tenji_rank_group,
                            COUNT(*) as races,
                            AVG(CASE WHEN res.rank = 1 THEN 1.0 ELSE 0.0 END) as win_rate,
                            AVG(CASE WHEN res.rank <= 2 THEN 1.0 ELSE 0.0 END) as place_rate_2
                        FROM entries e
                        JOIN races r ON e.race_id = r.id
                        JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
                        LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
                        WHERE e.racer_number = ?
                          AND r.race_date >= date('now', '-180 days')
                          AND rd.tenji_time_rank IS NOT NULL
                        GROUP BY tenji_rank_group
                        HAVING races >= 3
                        ORDER BY
                            CASE tenji_rank_group
                                WHEN '1位' THEN 1
                                WHEN '2-3位' THEN 2
                                WHEN '4-6位' THEN 3
                                ELSE 4
                            END
                    """
                    df_tenji = pd.read_sql_query(query_tenji, conn, params=[selected_racer])

                    if not df_tenji.empty:
                        for idx, row in df_tenji.iterrows():
                            col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
                            with col1:
                                st.markdown(f"**展示 {row['tenji_rank_group']}**")
                            with col2:
                                st.text(f"{int(row['races'])}走")
                            with col3:
                                st.text(f"1着率: {row['win_rate']*100:.1f}%")
                            with col4:
                                st.text(f"2連対: {row['place_rate_2']*100:.1f}%")

                        # 展示タイムと本番成績の相関分析
                        if len(df_tenji) >= 2:
                            top_win_rate = df_tenji[df_tenji['tenji_rank_group'] == '1位']['win_rate'].values
                            if len(top_win_rate) > 0:
                                if top_win_rate[0] > racer_info['win_rate'] * 1.3:
                                    st.success("🔥 展示タイムが良い時は本番も強い！展示を重視すべき選手")
                                elif top_win_rate[0] < racer_info['win_rate'] * 0.7:
                                    st.warning("⚠️ 展示が良くても本番で崩れやすい。展示だけで判断は危険")
                                else:
                                    st.info("📊 展示タイムと本番成績は標準的な相関")
                    else:
                        st.info("展示タイム順位データが不足しています")

                    # 進入コース変更率（枠なり進入率）
                    st.markdown("---")
                    st.markdown("#### 🔀 進入コース変更傾向")
                    query_course_change = """
                        SELECT
                            e.pit_number,
                            rd.actual_course,
                            COUNT(*) as count
                        FROM entries e
                        JOIN races r ON e.race_id = r.id
                        JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
                        WHERE e.racer_number = ?
                          AND r.race_date >= date('now', '-180 days')
                          AND rd.actual_course IS NOT NULL
                        GROUP BY e.pit_number, rd.actual_course
                        HAVING count >= 2
                        ORDER BY e.pit_number, count DESC
                    """
                    df_course_change = pd.read_sql_query(query_course_change, conn, params=[selected_racer])

                    if not df_course_change.empty:
                        # 枠番ごとの進入傾向
                        pit_numbers = sorted(df_course_change['pit_number'].unique())
                        for pit in pit_numbers:
                            pit_data = df_course_change[df_course_change['pit_number'] == pit]
                            total_races = pit_data['count'].sum()
                            most_common = pit_data.iloc[0]
                            枠なり率 = most_common['count'] / total_races * 100

                            col1, col2, col3 = st.columns([2, 3, 3])
                            with col1:
                                st.markdown(f"**{int(pit)}号艇**")
                            with col2:
                                st.text(f"最多進入: {int(most_common['actual_course'])}コース")
                            with col3:
                                if most_common['actual_course'] == pit:
                                    st.text(f"枠なり率: {枠なり率:.1f}%")
                                else:
                                    st.text(f"コース取り率: {枠なり率:.1f}% → {int(most_common['actual_course'])}C")

                        # 全体的な枠なり率
                        total_pit_races = df_course_change.groupby('pit_number')['count'].sum()
                        枠なり_count = df_course_change[df_course_change['pit_number'] == df_course_change['actual_course']]['count'].sum()
                        total_count = df_course_change['count'].sum()
                        overall_枠なり率 = 枠なり_count / total_count * 100 if total_count > 0 else 0

                        if overall_枠なり率 > 85:
                            st.success(f"✅ 枠なり率: {overall_枠なり率:.1f}% - 枠なりで進入する選手（予想しやすい）")
                        elif overall_枠なり率 < 60:
                            st.warning(f"⚠️ 枠なり率: {overall_枠なり率:.1f}% - コース取りをする選手（進入予想重要）")
                        else:
                            st.info(f"📊 枠なり率: {overall_枠なり率:.1f}% - 標準的")
                    else:
                        st.info("進入コース変更データが不足しています")

                    # 月別成績推移
                    st.markdown("---")
                    st.markdown("#### 📊 月別成績推移（直近6ヶ月）")
                    query_monthly = """
                        SELECT
                            strftime('%Y-%m', r.race_date) as month,
                            COUNT(*) as races,
                            AVG(CASE WHEN res.rank = 1 THEN 1.0 ELSE 0.0 END) as win_rate,
                            AVG(CASE WHEN res.rank <= 2 THEN 1.0 ELSE 0.0 END) as place_rate_2
                        FROM entries e
                        JOIN races r ON e.race_id = r.id
                        LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
                        WHERE e.racer_number = ?
                          AND r.race_date >= date('now', '-180 days')
                        GROUP BY month
                        ORDER BY month
                    """
                    df_monthly = pd.read_sql_query(query_monthly, conn, params=[selected_racer])

                    if not df_monthly.empty and len(df_monthly) >= 3:
                        # 折れ線グラフ用にデータ整形
                        df_monthly['month'] = pd.to_datetime(df_monthly['month'])
                        df_monthly['勝率'] = df_monthly['win_rate'] * 100
                        df_monthly['2連対率'] = df_monthly['place_rate_2'] * 100

                        # Streamlitの折れ線グラフ
                        st.line_chart(df_monthly.set_index('month')[['勝率', '2連対率']])

                        # トレンド分析
                        recent_3months = df_monthly.tail(3)['win_rate'].mean()
                        older_3months = df_monthly.head(3)['win_rate'].mean() if len(df_monthly) >= 6 else df_monthly.head(len(df_monthly)-3)['win_rate'].mean()

                        if recent_3months > older_3months * 1.2:
                            st.success("📈 上昇傾向！最近調子を上げている")
                        elif recent_3months < older_3months * 0.8:
                            st.warning("📉 下降傾向。最近調子が落ちている")
                        else:
                            st.info("→ 安定した成績を維持")
                    else:
                        st.info("月別推移データが不足しています")

                    # 最近のレース結果
                    st.markdown("---")
                    st.markdown("#### 📋 最近のレース結果（直近10レース）")
                    query_recent = """
                        SELECT
                            r.race_date,
                            r.venue_code,
                            r.race_number,
                            e.pit_number,
                            rd.actual_course,
                            res.rank,
                            res.kimarite
                        FROM entries e
                        JOIN races r ON e.race_id = r.id
                        LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
                        LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
                        WHERE e.racer_number = ?
                        ORDER BY r.race_date DESC, r.race_number DESC
                        LIMIT 10
                    """
                    df_recent = pd.read_sql_query(query_recent, conn, params=[selected_racer])

                    if not df_recent.empty:
                        df_recent['競艇場'] = df_recent['venue_code'].map(venue_code_to_name)
                        df_recent_display = df_recent[['race_date', '競艇場', 'race_number', 'pit_number', 'actual_course', 'rank', 'kimarite']]
                        df_recent_display.columns = ['日付', '競艇場', 'R', '艇番', 'コース', '着順', '決まり手']

                        # 着順に応じて色分け
                        def highlight_rank(row):
                            if row['着順'] == '1':
                                return ['background-color: #FFD700'] * len(row)  # 金色
                            elif row['着順'] == '2':
                                return ['background-color: #C0C0C0'] * len(row)  # 銀色
                            elif row['着順'] == '3':
                                return ['background-color: #CD7F32'] * len(row)  # 銅色
                            else:
                                return [''] * len(row)

                        st.table(df_recent_display)

                    conn.close()
            else:
                st.info("選手データがありません")

        except Exception as e:
            st.error(f"エラー: {e}")
            import traceback
            st.code(traceback.format_exc())


    # Tab 6: モデル学習 (old tab11 content)
    with tab6:
        from ui.components.model_training import render_model_training_page
        render_model_training_page()

        # 旧実装は残しておく（コメントアウト）
        """
        st.header("🤖 モデル学習ダッシュボード")
        st.markdown("XGBoost + SHAP による機械学習モデルの学習と評価")

        try:
            # セッション状態の初期化
            if 'ml_dataset' not in st.session_state:
                st.session_state.ml_dataset = None
            if 'ml_model' not in st.session_state:
                st.session_state.ml_model = None
            if 'ml_trainer' not in st.session_state:
                st.session_state.ml_trainer = None

            builder = DatasetBuilder(db_path=DATABASE_PATH)

            # ステップ1: データセット準備
            st.subheader("📊 ステップ1: データセット準備")

            col1, col2, col3 = st.columns(3)
            with col1:
                train_start = st.date_input(
                    "訓練開始日",
                    value=datetime.now() - timedelta(days=365),
                    key="ml_train_start"
                )
            with col2:
                train_end = st.date_input(
                    "訓練終了日",
                    value=datetime.now() - timedelta(days=90),
                    key="ml_train_end"
                )
            with col3:
                test_end = st.date_input(
                    "テスト終了日",
                    value=datetime.now(),
                    key="ml_test_end"
                )

            st.info("モデル学習機能は実装中です")

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
            import traceback
            st.code(traceback.format_exc())
        """

    # Tab 7: バックテスト (old tab15 content)
    with tab7:
        from ui.components.backtest import render_backtest_page
        render_backtest_page()

    # Tab 8: 設定・データ管理 (consolidating old tabs 3,6,7,8,9,10,12,13,14)
    with tab8:
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
                "法則検証",
                "データ排出",
                "過去レース統計"
            ]
        )

        if setting_page == "過去データ取得":
            # Old tab3 content
            st.markdown("---")
            st.subheader("📥 過去データ取得")
            # 改善版一括データ収集UI
            from ui.components.bulk_data_collector import render_bulk_data_collector
            render_bulk_data_collector(filter_target_date, filter_selected_venues)

            # オリジナル展示データ収集
            st.markdown("---")
            from ui.components.original_tenji_collector import render_original_tenji_collector
            render_original_tenji_collector()

        elif setting_page == "システム設定":
            # Old tab6 content
            st.markdown("---")
            st.subheader("⚙️ システム設定")
            st.text(f"データベースパス: {DATABASE_PATH}")

            st.subheader("競艇場一覧")
            venues_list = list(VENUES.items())
            for venue_id, venue_info in venues_list[:5]:
                st.text(f"{venue_info['code']}: {venue_info['name']}")

        elif setting_page == "レース結果管理":
            # Old tab7 content
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
            # Old tab8 content - Data Quality & Coverage Check
            st.markdown("---")
            st.subheader("📋 データ充足率・品質チェック")

            # データ充足率チェック
            st.markdown("#### データ充足率")
            if st.button("🔍 充足率チェック実行", key="run_coverage_check"):
                with st.spinner("データ充足率を確認中..."):
                    try:
                        checker = DataCoverageChecker(DATABASE_PATH)
                        coverage_report = checker.check_coverage()

                        # 全体サマリー
                        st.markdown("**全体サマリー**")
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("総レース数", f"{coverage_report.get('total_races', 0):,}")
                        with col2:
                            complete = coverage_report.get('complete_races', 0)
                            st.metric("完全データレース", f"{complete:,}")
                        with col3:
                            ratio = coverage_report.get('coverage_ratio', 0) * 100
                            st.metric("充足率", f"{ratio:.1f}%")

                        # 会場別詳細
                        if 'venue_coverage' in coverage_report:
                            st.markdown("**会場別充足率**")
                            venue_df = pd.DataFrame(coverage_report['venue_coverage'])
                            if not venue_df.empty:
                                st.dataframe(venue_df, use_container_width=True)

                    except Exception as e:
                        st.error(f"エラー: {e}")
                        import traceback
                        st.code(traceback.format_exc())

            st.markdown("---")

            # データ品質チェック
            st.markdown("#### データ品質モニター")
            if st.button("🔍 品質チェック実行", key="run_quality_check"):
                with st.spinner("データ品質を確認中..."):
                    try:
                        monitor = DataQualityMonitor(DATABASE_PATH)
                        quality_report = monitor.check_all()

                        # 品質スコア
                        st.markdown("**品質スコア**")
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            completeness = quality_report.get('completeness_score', 0) * 100
                            st.metric("完全性", f"{completeness:.1f}%")
                        with col2:
                            consistency = quality_report.get('consistency_score', 0) * 100
                            st.metric("一貫性", f"{consistency:.1f}%")
                        with col3:
                            accuracy = quality_report.get('accuracy_score', 0) * 100
                            st.metric("正確性", f"{accuracy:.1f}%")

                        # 問題検出
                        if 'issues' in quality_report and quality_report['issues']:
                            st.markdown("**検出された問題**")
                            for issue in quality_report['issues']:
                                severity = issue.get('severity', 'info')
                                msg = issue.get('message', '')
                                if severity == 'error':
                                    st.error(f"❌ {msg}")
                                elif severity == 'warning':
                                    st.warning(f"⚠️ {msg}")
                                else:
                                    st.info(f"ℹ️ {msg}")
                        else:
                            st.success("✅ 問題は検出されませんでした")

                    except Exception as e:
                        st.error(f"エラー: {e}")
                        import traceback
                        st.code(traceback.format_exc())

            st.markdown("---")

            # データバリデーション
            st.markdown("#### データバリデーション")
            validation_target = st.selectbox(
                "検証対象",
                ["レースデータ", "選手データ", "結果データ", "展示データ"],
                key="validation_target"
            )

            if st.button("🔍 バリデーション実行", key="run_validation"):
                with st.spinner(f"{validation_target}を検証中..."):
                    try:
                        from src.utils.data_validator import DataValidator
                        validator = DataValidator(DATABASE_PATH)

                        if validation_target == "レースデータ":
                            errors = validator.validate_races()
                        elif validation_target == "選手データ":
                            errors = validator.validate_racers()
                        elif validation_target == "結果データ":
                            errors = validator.validate_results()
                        else:
                            errors = validator.validate_tenji()

                        if errors:
                            st.warning(f"⚠️ {len(errors)}件の問題が見つかりました")
                            error_df = pd.DataFrame(errors)
                            st.dataframe(error_df, use_container_width=True)
                        else:
                            st.success("✅ データは正常です")

                    except Exception as e:
                        st.error(f"エラー: {e}")
                        import traceback
                        st.code(traceback.format_exc())

        elif setting_page == "特徴量計算":
            # Feature Engineering
            st.markdown("---")
            st.subheader("🧮 特徴量エンジニアリング")

            from src.ml.feature_calculator import FeatureCalculator
            import plotly.graph_objects as go

            calculator = FeatureCalculator(DATABASE_PATH)

            # 会場選択
            st.markdown("#### 会場選択")
            use_sidebar = st.checkbox("サイドバーで選択した会場を使用", value=True)

            if use_sidebar and 'selected_venue' in st.session_state and st.session_state['selected_venue']:
                selected_venue_code = st.session_state['selected_venue']['code']
                selected_venue_name = st.session_state['selected_venue']['name']
                st.info(f"選択中の会場: {selected_venue_name} ({selected_venue_code})")
            else:
                venues = calculator.get_all_venues()
                venue_options = {f"{v['name']} ({v['code']})": v['code'] for v in venues}
                selected_display = st.selectbox("会場を選択", list(venue_options.keys()))
                selected_venue_code = venue_options[selected_display]

            # 集計期間
            days = st.slider("集計期間（日数）", min_value=30, max_value=365, value=180, step=30)

            st.markdown("---")

            # 特徴量サマリー
            st.markdown("### 📊 特徴量サマリー")

            col1, col2, col3, col4 = st.columns(4)

            # モーター統計
            motor_stats = calculator.calculate_motor_stats(selected_venue_code, days)
            col1.metric("モーター数", f"{motor_stats['motor_count']}台")

            # ボート統計
            boat_stats = calculator.calculate_boat_stats(selected_venue_code, days)
            col2.metric("ボート数", f"{boat_stats['boat_count']}艇")

            # 逃げ率
            escape_rate = calculator.calculate_escape_rate(selected_venue_code, days)
            col3.metric("1コース逃げ率", f"{escape_rate['escape_rate']:.1f}%")

            # 進入固定率
            fixed_entry_rate = calculator.calculate_fixed_entry_rate(selected_venue_code, days)
            col4.metric("進入固定率", f"{fixed_entry_rate['fixed_rate']:.1f}%")

            st.markdown("---")

            # モーター性能詳細
            st.markdown("### 🔧 モーター性能")

            if motor_stats['motors']:
                motor_list = []
                for motor in motor_stats['motors']:
                    motor_list.append({
                        'モーター番号': motor['motor_number'],
                        '勝率': f"{motor['win_rate']:.2f}",
                        '2連率': f"{motor['place_rate_2']:.2f}%",
                        '3連率': f"{motor['place_rate_3']:.2f}%",
                        '使用回数': motor['use_count']
                    })

                df_motor = pd.DataFrame(motor_list)

                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("#### 🏆 TOP5 モーター")
                    st.table(df_motor.head(5))

                with col2:
                    st.markdown("#### ⚠️ WORST5 モーター")
                    st.table(df_motor.tail(5))
            else:
                st.info("モーターデータがありません")

            st.markdown("---")

            # ボート性能詳細
            st.markdown("### 🚤 ボート性能")

            if boat_stats['boats']:
                boat_list = []
                for boat in boat_stats['boats']:
                    boat_list.append({
                        'ボート番号': boat['boat_number'],
                        '勝率': f"{boat['win_rate']:.2f}",
                        '2連率': f"{boat['place_rate_2']:.2f}%",
                        '3連率': f"{boat['place_rate_3']:.2f}%",
                        '使用回数': boat['use_count']
                    })

                df_boat = pd.DataFrame(boat_list)

                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("#### 🏆 TOP5 ボート")
                    st.table(df_boat.head(5))

                with col2:
                    st.markdown("#### ⚠️ WORST5 ボート")
                    st.table(df_boat.tail(5))
            else:
                st.info("ボートデータがありません")

            st.markdown("---")

            # 選手コース別成績
            st.markdown("### 👤 選手コース別成績")

            racer_number = st.number_input("選手登録番号", min_value=1000, max_value=9999, value=4444, step=1)

            if st.button("選手データを取得"):
                course_stats = calculator.calculate_racer_course_stats(racer_number, days)

                if course_stats['courses']:
                    st.markdown(f"**対象期間:** 過去{days}日間")

                    # グラフ表示
                    courses = []
                    win_rates = []
                    place_rates = []
                    use_counts = []

                    for course in course_stats['courses']:
                        courses.append(f"{course['course']}コース")
                        win_rates.append(course['win_rate'])
                        place_rates.append(course['place_rate_2'])
                        use_counts.append(course['use_count'])

                    fig = go.Figure()
                    fig.add_trace(go.Bar(
                        name='勝率',
                        x=courses,
                        y=win_rates,
                        marker_color='gold'
                    ))
                    fig.add_trace(go.Bar(
                        name='2連率',
                        x=courses,
                        y=place_rates,
                        marker_color='silver'
                    ))

                    fig.update_layout(
                        title='コース別成績',
                        xaxis_title='コース',
                        yaxis_title='率（%）',
                        barmode='group',
                        height=400
                    )

                    st.plotly_chart(fig, use_container_width=True)

                    # 表形式でも表示
                    course_table = []
                    for i, course in enumerate(course_stats['courses']):
                        course_table.append({
                            'コース': course['course'],
                            '勝率': f"{course['win_rate']:.1f}%",
                            '2連率': f"{course['place_rate_2']:.1f}%",
                            '3連率': f"{course['place_rate_3']:.1f}%",
                            '使用回数': use_counts[i]
                        })

                    df_course = pd.DataFrame(course_table)
                    st.table(df_course)
                else:
                    st.warning("選手データが見つかりませんでした")

            st.markdown("---")

            # 進入パターン分析
            st.markdown("### 🔄 進入パターン分析")

            entry_patterns = calculator.analyze_entry_patterns(selected_venue_code, days)

            if entry_patterns['patterns']:
                st.markdown(f"**対象期間:** 過去{days}日間 / **会場:** {selected_venue_name}")

                pattern_list = []
                for pattern in entry_patterns['patterns']:
                    pattern_list.append({
                        '進入パターン': pattern['pattern'],
                        '出現回数': pattern['count'],
                        '出現率': f"{pattern['rate']:.1f}%"
                    })

                df_pattern = pd.DataFrame(pattern_list)
                st.table(df_pattern.head(10))
            else:
                st.info("進入パターンデータがありません")

        elif setting_page == "MLデータ出力":
            # ML Data Export
            st.markdown("---")
            st.subheader("📤 機械学習用データ出力")

            from src.ml.dataset_builder import DatasetBuilder

            builder = DatasetBuilder(DATABASE_PATH)

            st.markdown("#### データセット設定")

            # 期間選択
            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input(
                    "開始日",
                    value=pd.Timestamp.now() - pd.Timedelta(days=365)
                )
            with col2:
                end_date = st.date_input(
                    "終了日",
                    value=pd.Timestamp.now()
                )

            # 会場選択
            st.markdown("#### 会場選択")
            venue_selection = st.radio(
                "会場選択方法",
                ["全会場", "サイドバーの会場", "カスタム選択"],
                horizontal=True
            )

            selected_venues = []

            if venue_selection == "全会場":
                selected_venues = None
                st.info("全24会場のデータを出力します")

            elif venue_selection == "サイドバーの会場":
                if 'selected_venue' in st.session_state and st.session_state['selected_venue']:
                    selected_venue_code = st.session_state['selected_venue']['code']
                    selected_venue_name = st.session_state['selected_venue']['name']
                    selected_venues = [selected_venue_code]
                    st.info(f"選択中の会場: {selected_venue_name} ({selected_venue_code})")
                else:
                    st.warning("サイドバーで会場を選択してください")

            else:  # カスタム選択
                venues = builder.get_all_venues()
                venue_options = {f"{v['name']} ({v['code']})": v['code'] for v in venues}
                selected_displays = st.multiselect(
                    "会場を選択（複数可）",
                    list(venue_options.keys())
                )
                selected_venues = [venue_options[d] for d in selected_displays]

                if selected_venues:
                    st.info(f"{len(selected_venues)}会場を選択中")

            st.markdown("---")

            # データセット生成
            st.markdown("### 📊 データセット生成")

            if st.button("データセットを生成", type="primary"):
                with st.spinner("データセットを生成中..."):
                    try:
                        # 生データ取得
                        df_raw = builder.build_training_dataset(
                            start_date=start_date.strftime("%Y-%m-%d"),
                            end_date=end_date.strftime("%Y-%m-%d"),
                            venue_codes=selected_venues
                        )

                        if df_raw is None or df_raw.empty:
                            st.error("データが見つかりませんでした")
                        else:
                            # 派生特徴量を追加
                            df_processed = builder.add_derived_features(df_raw)

                            # セッションステートに保存
                            st.session_state['ml_dataset'] = df_processed
                            st.session_state['ml_dataset_raw'] = df_raw

                            st.success(f"データセット生成完了: {len(df_processed)}件")

                            # 特徴量サマリー
                            st.markdown("#### 📊 データセットサマリー")

                            col1, col2, col3, col4 = st.columns(4)
                            col1.metric("総レコード数", f"{len(df_processed):,}件")
                            col2.metric("特徴量数", f"{len(df_processed.columns)}個")

                            # 1着の数
                            if 'rank' in df_processed.columns:
                                win_count = (df_processed['rank'] == 1).sum()
                                col3.metric("1着数", f"{win_count:,}件")
                                col4.metric("1着率", f"{win_count / len(df_processed) * 100:.1f}%")

                            # データプレビュー
                            st.markdown("#### 🔍 データプレビュー（先頭10件）")
                            st.dataframe(df_processed.head(10), use_container_width=True)

                    except Exception as e:
                        st.error(f"エラーが発生しました: {e}")
                        import traceback
                        st.code(traceback.format_exc())

            st.markdown("---")

            # データセットのエクスポート
            if 'ml_dataset' in st.session_state and st.session_state['ml_dataset'] is not None:
                st.markdown("### 💾 データセットのエクスポート")

                df = st.session_state['ml_dataset']

                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("#### CSV形式")
                    filename_csv = st.text_input("ファイル名（CSV）", value="dataset.csv")

                    if st.button("CSVでエクスポート"):
                        output_path = f"data/exports/{filename_csv}"
                        builder.export_to_csv(df, output_path)
                        st.success(f"エクスポート完了: {output_path}")

                        # ダウンロードボタン
                        with open(output_path, 'rb') as f:
                            st.download_button(
                                label="CSVをダウンロード",
                                data=f,
                                file_name=filename_csv,
                                mime="text/csv"
                            )

                with col2:
                    st.markdown("#### JSON形式")
                    filename_json = st.text_input("ファイル名（JSON）", value="dataset.json")

                    if st.button("JSONでエクスポート"):
                        output_path = f"data/exports/{filename_json}"
                        builder.export_to_json(df, output_path)
                        st.success(f"エクスポート完了: {output_path}")

                        # ダウンロードボタン
                        with open(output_path, 'rb') as f:
                            st.download_button(
                                label="JSONをダウンロード",
                                data=f,
                                file_name=filename_json,
                                mime="application/json"
                            )

                st.markdown("---")

                # XGBoost用データ準備
                st.markdown("### 🤖 XGBoost用データ準備")

                if st.button("XGBoost形式で準備"):
                    with st.spinner("XGBoost用データを準備中..."):
                        try:
                            X, y, feature_names = builder.prepare_xgboost_data(df)

                            st.session_state['xgb_X'] = X
                            st.session_state['xgb_y'] = y
                            st.session_state['xgb_feature_names'] = feature_names

                            st.success("XGBoost用データ準備完了")

                            col1, col2 = st.columns(2)
                            col1.metric("特徴量行列サイズ", f"{X.shape[0]} x {X.shape[1]}")
                            col2.metric("正解ラベル数", f"{len(y)}")

                            # 特徴量リスト表示
                            with st.expander("特徴量リスト"):
                                for i, name in enumerate(feature_names, 1):
                                    st.text(f"{i}. {name}")

                        except Exception as e:
                            st.error(f"エラー: {e}")
                            import traceback
                            st.code(traceback.format_exc())

                st.markdown("---")

                # 時系列分割
                st.markdown("### 📅 時系列データ分割")

                split_ratio = st.slider("訓練データ比率", min_value=0.5, max_value=0.9, value=0.8, step=0.05)

                if st.button("時系列分割を実行"):
                    with st.spinner("データを分割中..."):
                        try:
                            if 'race_date' not in df.columns:
                                st.error("race_date列が見つかりません")
                            else:
                                # 日付でソート
                                df_sorted = df.sort_values('race_date')

                                # 分割点
                                split_idx = int(len(df_sorted) * split_ratio)

                                df_train = df_sorted.iloc[:split_idx]
                                df_test = df_sorted.iloc[split_idx:]

                                st.session_state['ml_train'] = df_train
                                st.session_state['ml_test'] = df_test

                                st.success("時系列分割完了")

                                col1, col2 = st.columns(2)
                                col1.metric("訓練データ", f"{len(df_train):,}件")
                                col2.metric("テストデータ", f"{len(df_test):,}件")

                                # 期間表示
                                train_start = df_train['race_date'].min()
                                train_end = df_train['race_date'].max()
                                test_start = df_test['race_date'].min()
                                test_end = df_test['race_date'].max()

                                st.info(f"訓練期間: {train_start} 〜 {train_end}")
                                st.info(f"テスト期間: {test_start} 〜 {test_end}")

                        except Exception as e:
                            st.error(f"エラー: {e}")
                            import traceback
                            st.code(traceback.format_exc())

        elif setting_page == "法則検証":
            # Rule Validation
            st.markdown("---")
            st.subheader("🔬 法則検証")

            from src.analysis.rule_validator import RuleValidator

            validator = RuleValidator(DATABASE_PATH)

            st.markdown("""
            このページでは、競艇の「法則」や「セオリー」を統計的に検証できます。
            実際のデータに基づいて、法則の信頼性を評価します。
            """)

            st.markdown("---")

            # 会場法則の検証
            st.markdown("### 🏟️ 会場法則の検証")

            venue_rules = validator.get_all_venue_rules()

            if venue_rules:
                rule_options = {f"{r['id']}. {r['title']}": r['id'] for r in venue_rules}
                selected_rule_display = st.selectbox(
                    "検証する法則を選択",
                    list(rule_options.keys())
                )
                selected_rule_id = rule_options[selected_rule_display]

                # 選択された法則の詳細表示
                selected_rule = next(r for r in venue_rules if r['id'] == selected_rule_id)

                st.info(f"**法則:** {selected_rule['description']}")

                col1, col2 = st.columns(2)
                with col1:
                    st.text(f"対象会場: {selected_rule['venue_name']}")
                with col2:
                    st.text(f"条件: {selected_rule['condition']}")

                if st.button("🔬 検証実行", type="primary"):
                    with st.spinner("法則を検証中..."):
                        try:
                            result = validator.validate_venue_rule(selected_rule_id)

                            if result:
                                st.markdown("#### 📊 検証結果")

                                # メトリクス表示
                                col1, col2, col3, col4 = st.columns(4)
                                col1.metric("サンプル数", f"{result['sample_size']}件")
                                col2.metric("的中率", f"{result['hit_rate']:.1f}%")
                                col3.metric("期待的中率", f"{result['expected_rate']:.1f}%")

                                improvement = result['hit_rate'] - result['expected_rate']
                                col4.metric("改善", f"{improvement:+.2f}%")

                                # 統計的有意性
                                st.markdown("#### 📈 統計的有意性")
                                col1, col2 = st.columns(2)

                                with col1:
                                    st.metric("p値", f"{result['p_value']:.4f}")
                                    if result['p_value'] < 0.05:
                                        st.success("✅ 統計的に有意（p < 0.05）")
                                    elif result['p_value'] < 0.10:
                                        st.warning("⚠️ やや有意（p < 0.10）")
                                    else:
                                        st.error("❌ 有意差なし（p >= 0.10）")

                                with col2:
                                    confidence_score = result['confidence_score']
                                    st.metric("信頼度スコア", f"{confidence_score}/100")
                                    st.progress(confidence_score / 100)

                                # 解釈
                                st.markdown("#### 💡 解釈")

                                if confidence_score >= 80:
                                    st.success("⭐⭐⭐ 非常に信頼できる法則です")
                                elif confidence_score >= 60:
                                    st.info("⭐⭐ 信頼できる法則です")
                                elif confidence_score >= 40:
                                    st.warning("⭐ やや信頼できる法則です")
                                else:
                                    st.error("❌ 信頼性が低い法則です")

                                # 詳細データ
                                with st.expander("詳細データを表示"):
                                    st.json(result)

                        except Exception as e:
                            st.error(f"エラーが発生しました: {e}")
                            import traceback
                            st.code(traceback.format_exc())

            else:
                st.warning("会場法則が登録されていません")

            st.markdown("---")

            # 選手法則の検証
            st.markdown("### 👤 選手法則の検証")

            racer_rules = validator.get_all_racer_rules()

            if racer_rules:
                rule_options_racer = {f"{r['id']}. {r['title']}": r['id'] for r in racer_rules}
                selected_racer_rule_display = st.selectbox(
                    "検証する選手法則を選択",
                    list(rule_options_racer.keys())
                )
                selected_racer_rule_id = rule_options_racer[selected_racer_rule_display]

                # 選択された法則の詳細表示
                selected_racer_rule = next(r for r in racer_rules if r['id'] == selected_racer_rule_id)

                st.info(f"**法則:** {selected_racer_rule['description']}")
                st.text(f"条件: {selected_racer_rule['condition']}")

                if st.button("🔬 選手法則を検証", type="primary"):
                    with st.spinner("選手法則を検証中..."):
                        try:
                            result = validator.validate_racer_rule(selected_racer_rule_id)

                            if result:
                                st.markdown("#### 📊 検証結果")

                                # メトリクス表示
                                col1, col2, col3, col4 = st.columns(4)
                                col1.metric("サンプル数", f"{result['sample_size']}件")
                                col2.metric("的中率", f"{result['hit_rate']:.1f}%")
                                col3.metric("期待的中率", f"{result['expected_rate']:.1f}%")

                                improvement = result['hit_rate'] - result['expected_rate']
                                col4.metric("改善", f"{improvement:+.2f}%")

                                # 統計的有意性
                                st.markdown("#### 📈 統計的有意性")
                                col1, col2 = st.columns(2)

                                with col1:
                                    st.metric("p値", f"{result['p_value']:.4f}")
                                    if result['p_value'] < 0.05:
                                        st.success("✅ 統計的に有意（p < 0.05）")
                                    elif result['p_value'] < 0.10:
                                        st.warning("⚠️ やや有意（p < 0.10）")
                                    else:
                                        st.error("❌ 有意差なし（p >= 0.10）")

                                with col2:
                                    confidence_score = result['confidence_score']
                                    st.metric("信頼度スコア", f"{confidence_score}/100")
                                    st.progress(confidence_score / 100)

                                # 詳細データ
                                with st.expander("詳細データを表示"):
                                    st.json(result)

                        except Exception as e:
                            st.error(f"エラーが発生しました: {e}")
                            import traceback
                            st.code(traceback.format_exc())

            else:
                st.warning("選手法則が登録されていません")

            st.markdown("---")

            # 一括検証
            st.markdown("### 🔄 一括検証")

            if st.button("全ての法則を一括検証"):
                with st.spinner("全ての法則を検証中..."):
                    try:
                        results = []

                        # 会場法則を検証
                        for rule in venue_rules:
                            result = validator.validate_venue_rule(rule['id'])
                            if result:
                                results.append({
                                    'タイプ': '会場',
                                    '法則': rule['title'],
                                    'サンプル数': result['sample_size'],
                                    '的中率': f"{result['hit_rate']:.1f}%",
                                    '期待的中率': f"{result['expected_rate']:.1f}%",
                                    '改善': f"{result['hit_rate'] - result['expected_rate']:+.2f}%",
                                    'p値': f"{result['p_value']:.4f}",
                                    '信頼度': result['confidence_score']
                                })

                        # 選手法則を検証
                        for rule in racer_rules:
                            result = validator.validate_racer_rule(rule['id'])
                            if result:
                                results.append({
                                    'タイプ': '選手',
                                    '法則': rule['title'],
                                    'サンプル数': result['sample_size'],
                                    '的中率': f"{result['hit_rate']:.1f}%",
                                    '期待的中率': f"{result['expected_rate']:.1f}%",
                                    '改善': f"{result['hit_rate'] - result['expected_rate']:+.2f}%",
                                    'p値': f"{result['p_value']:.4f}",
                                    '信頼度': result['confidence_score']
                                })

                        if results:
                            df_results = pd.DataFrame(results)
                            df_results = df_results.sort_values('信頼度', ascending=False)

                            st.success(f"{len(results)}件の法則を検証しました")
                            st.dataframe(df_results, use_container_width=True)

                            # CSVダウンロード
                            csv = df_results.to_csv(index=False, encoding='utf-8-sig')
                            st.download_button(
                                label="結果をCSVでダウンロード",
                                data=csv,
                                file_name="rule_validation_results.csv",
                                mime="text/csv"
                            )

                        else:
                            st.warning("検証可能な法則がありませんでした")

                    except Exception as e:
                        st.error(f"エラーが発生しました: {e}")
                        import traceback
                        st.code(traceback.format_exc())

        elif setting_page == "データ排出":
            # Old tab13 content
            st.markdown("---")
            from ui.components.data_export import render_data_export_page
            render_data_export_page()

        elif setting_page == "過去レース統計":
            # Old tab14 content
            st.markdown("---")
            from ui.components.data_export import render_past_races_summary
            render_past_races_summary()


if __name__ == "__main__":
    main()
