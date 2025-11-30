"""
データ収集コンポーネント（統合版）

自動データ収集と手動データ収集を統合
- クイックアクション（今日/明日/今週）
- カスタム期間収集
- 補完データ取得（決まり手、詳細、天候、風向）
"""
import streamlit as st
import subprocess
import os
import sys
from datetime import datetime, timedelta
import sqlite3

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH


def render_data_collector():
    """データ収集UI（統合版）"""
    st.header("📥 データ収集")

    # タブで機能を分類
    tab1, tab2, tab3 = st.tabs(["🚀 クイック収集", "📅 期間指定収集", "🔧 補完データ取得"])

    with tab1:
        _render_quick_collection()

    with tab2:
        _render_custom_period_collection()

    with tab3:
        _render_supplement_data_collection()

    # 収集状況（共通）
    st.markdown("---")
    _show_collection_status()


def _render_quick_collection():
    """クイック収集タブ"""
    st.subheader("🚀 クイック収集")
    st.markdown("ワンクリックでデータを収集します")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("📅 今日のデータ", use_container_width=True, type="primary"):
            _collect_today_data()

    with col2:
        if st.button("📅 明日のデータ", use_container_width=True):
            _collect_tomorrow_data()

    with col3:
        if st.button("📅 今週のデータ", use_container_width=True):
            _collect_this_week_data()

    # オプション
    st.markdown("---")
    st.markdown("#### オプション")

    include_supplements = st.checkbox(
        "補完データも取得する（決まり手、詳細、天候、風向）",
        value=False,
        help="取得後に補完スクリプトを自動実行します（時間がかかります）"
    )

    if include_supplements:
        st.session_state['include_supplements'] = True
    else:
        st.session_state['include_supplements'] = False


def _render_custom_period_collection():
    """期間指定収集タブ"""
    st.subheader("📅 期間指定収集")

    # 最終保存日を取得
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(race_date) FROM races")
    result = cursor.fetchone()
    conn.close()

    if result and result[0]:
        last_saved_date = datetime.strptime(result[0], '%Y-%m-%d')
        default_start = last_saved_date + timedelta(days=1)
    else:
        last_saved_date = None
        default_start = datetime.now() - timedelta(days=7)

    # 最終保存日の表示
    if last_saved_date:
        st.info(f"📊 最終保存日: **{last_saved_date.strftime('%Y-%m-%d')}**")
    else:
        st.warning("📊 データベースにデータがありません")

    # 期間設定
    col1, col2 = st.columns(2)

    with col1:
        start_date = st.date_input(
            "開始日",
            default_start.date() if isinstance(default_start, datetime) else default_start,
            key="collector_start_date"
        )

    with col2:
        end_date = st.date_input(
            "終了日",
            datetime.now().date(),
            key="collector_end_date"
        )

    # 対象日数の計算
    if isinstance(start_date, datetime):
        start_date = start_date.date()
    if isinstance(end_date, datetime):
        end_date = end_date.date()

    target_days = (end_date - start_date).days + 1

    if target_days <= 0:
        st.success("✅ データは最新です！取得する必要はありません。")
        return

    # 会場選択
    st.markdown("#### 対象会場")
    venue_selection = st.radio(
        "会場選択",
        ["すべての会場（24会場）", "特定の会場を選択"],
        horizontal=True,
        label_visibility="collapsed"
    )

    selected_venues = None
    if venue_selection == "特定の会場を選択":
        from config.settings import VENUES
        venue_options = {f"{info['code']} - {info['name']}": info['code']
                        for venue_id, info in VENUES.items()}
        selected_names = st.multiselect(
            "会場を選択",
            list(venue_options.keys()),
            default=[]
        )
        selected_venues = [venue_options[name] for name in selected_names]

    # 補完データオプション
    st.markdown("#### 取得データ")

    col1, col2 = st.columns(2)
    with col1:
        get_basic = st.checkbox("レース基本情報・結果", value=True)
    with col2:
        get_supplements = st.checkbox("補完データ（決まり手、詳細、天候、風向）", value=True)

    # 確認表示
    venue_count = len(selected_venues) if selected_venues else 24
    st.warning(f"📊 取得対象: **{target_days}日分** × **{venue_count}会場**")

    # 実行ボタン
    if st.button("🚀 データ収集を開始", type="primary", use_container_width=True):
        _collect_custom_period_data(
            start_date,
            end_date,
            selected_venues,
            get_basic,
            get_supplements
        )


def _render_supplement_data_collection():
    """補完データ取得タブ"""
    st.subheader("🔧 補完データ取得")
    st.markdown("既存のレースデータに対して、不足している情報を補完します")

    # 知見の表示
    with st.expander("💡 補完データについて", expanded=False):
        st.markdown("""
        **補完可能なデータ:**
        - ✅ 決まり手データ（改善版スクレイピング）
        - ✅ レース詳細データv4（展示タイム、モーター・ボート情報）
        - ✅ 天候データ（気温・水温・波高）
        - ✅ 風向データ（風速・風向）

        **別途取得が必要:**
        - 🌊 潮位データ（RDMDB収集スクリプト）
        - 🎯 オリジナル展示データ（毎日手動実行）
        """)

    # タスク選択
    tasks = {
        "決まり手データ": {
            "description": "決まり手情報を補完（改善版）",
            "script": "補完_決まり手データ_改善版.py"
        },
        "レース詳細データv4": {
            "description": "展示タイム、モーター・ボート情報等",
            "script": "補完_レース詳細データ_改善版v4.py"
        },
        "天候データ": {
            "description": "気温・水温・波高",
            "script": "補完_天候データ_改善版.py"
        },
        "風向データ": {
            "description": "風速・風向",
            "script": "補完_風向データ_改善版.py"
        },
    }

    selected_tasks = []
    for task_name, task_info in tasks.items():
        if st.checkbox(task_name, value=True, help=task_info["description"]):
            selected_tasks.append((task_name, task_info))

    # 実行ボタン
    if st.button("🔄 補完データを取得", type="primary", use_container_width=True):
        if not selected_tasks:
            st.error("取得するデータを選択してください")
            return

        _run_supplement_scripts(selected_tasks)


def _collect_today_data():
    """今日のデータを収集"""
    st.info("📥 今日のデータを収集中...")

    try:
        from src.scraper.bulk_scraper import BulkScraper

        scraper = BulkScraper()
        schedule_scraper = scraper.schedule_scraper
        today_schedule = schedule_scraper.get_today_schedule()

        if not today_schedule:
            st.warning("本日開催のレースが見つかりませんでした")
            return

        progress_bar = st.progress(0)
        status_text = st.empty()

        total_venues = len(today_schedule)
        total_races = 0

        for i, (venue_code, race_date) in enumerate(today_schedule.items(), 1):
            status_text.text(f"会場 {venue_code} を収集中... ({i}/{total_venues})")

            result = scraper.fetch_multiple_venues(
                venue_codes=[venue_code],
                race_date=race_date,
                race_count=12
            )

            if venue_code in result:
                total_races += len(result[venue_code])

            progress_bar.progress(i / total_venues)

        st.success(f"✅ 完了！ {total_venues}会場 {total_races}レース取得しました")

        # 補完データも取得
        if st.session_state.get('include_supplements', False):
            _run_all_supplement_scripts()

    except Exception as e:
        st.error(f"❌ エラー: {e}")


def _collect_tomorrow_data():
    """明日のデータを収集"""
    st.info("📥 明日のデータを収集中...")

    try:
        from src.scraper.bulk_scraper import BulkScraper

        tomorrow = datetime.now() + timedelta(days=1)
        tomorrow_str = tomorrow.strftime("%Y-%m-%d")

        scraper = BulkScraper()

        total_races = 0
        successful_venues = []

        progress_bar = st.progress(0)
        status_text = st.empty()

        for i in range(1, 25):
            venue_code = f"{i:02d}"
            status_text.text(f"会場 {venue_code} を確認中... ({i}/24)")

            try:
                result = scraper.fetch_multiple_venues(
                    venue_codes=[venue_code],
                    race_date=tomorrow_str,
                    race_count=12
                )

                if venue_code in result and result[venue_code]:
                    total_races += len(result[venue_code])
                    successful_venues.append(venue_code)

            except Exception:
                pass

            progress_bar.progress(i / 24)

        if successful_venues:
            st.success(f"✅ 完了！ {len(successful_venues)}会場 {total_races}レース取得しました")
        else:
            st.warning("明日開催のレースが見つかりませんでした")

    except Exception as e:
        st.error(f"❌ エラー: {e}")


def _collect_this_week_data():
    """今週のデータを収集"""
    st.info("📥 今週のデータを収集中...")

    today = datetime.now()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    _collect_custom_period_data(
        start_of_week.date(),
        end_of_week.date(),
        None,
        True,
        st.session_state.get('include_supplements', False)
    )


def _collect_custom_period_data(start_date, end_date, venue_codes, get_basic, get_supplements):
    """カスタム期間のデータを収集"""
    st.info(f"📥 {start_date} から {end_date} のデータを収集中...")

    progress_bar = st.progress(0)
    status_text = st.empty()
    log_placeholder = st.empty()
    logs = []

    def add_log(message):
        logs.append(f"{datetime.now().strftime('%H:%M:%S')} - {message}")
        log_placeholder.text_area("実行ログ", "\n".join(logs[-20:]), height=200)

    try:
        if get_basic:
            from src.scraper.bulk_scraper import BulkScraper
            scraper = BulkScraper()

            # 日付リストを生成
            date_range = []
            current_date = start_date
            while current_date <= end_date:
                date_range.append(current_date.strftime("%Y-%m-%d"))
                current_date += timedelta(days=1)

            # 会場リスト
            if not venue_codes:
                venue_codes = [f"{i:02d}" for i in range(1, 25)]

            total_tasks = len(date_range) * len(venue_codes)
            completed_tasks = 0
            total_races = 0

            add_log(f"期間: {start_date} ～ {end_date}")
            add_log(f"対象: {len(venue_codes)}会場 × {len(date_range)}日")

            for date_str in date_range:
                for venue_code in venue_codes:
                    status_text.text(
                        f"{date_str} - 会場 {venue_code} を収集中... "
                        f"({completed_tasks}/{total_tasks})"
                    )

                    try:
                        result = scraper.fetch_multiple_venues(
                            venue_codes=[venue_code],
                            race_date=date_str,
                            race_count=12
                        )

                        if venue_code in result:
                            total_races += len(result[venue_code])

                    except Exception:
                        pass

                    completed_tasks += 1
                    progress_bar.progress(completed_tasks / total_tasks)

            add_log(f"✅ レース基本情報: {total_races}レース取得完了")

        # 補完データ取得
        if get_supplements:
            add_log("補完データの取得を開始...")
            _run_all_supplement_scripts(add_log, status_text)

        status_text.text("✅ すべての処理が完了しました！")
        add_log("🎉 データ取得完了！")

        # 取得データの確認
        _show_period_data_summary(start_date, end_date)

        st.success("✅ データ取得が完了しました！")

    except Exception as e:
        st.error(f"❌ エラー: {e}")
        add_log(f"❌ 致命的エラー: {str(e)}")


def _run_supplement_scripts(selected_tasks):
    """補完スクリプトを実行"""
    progress_bar = st.progress(0)
    status_text = st.empty()
    log_placeholder = st.empty()
    logs = []

    def add_log(message):
        logs.append(f"{datetime.now().strftime('%H:%M:%S')} - {message}")
        log_placeholder.text_area("実行ログ", "\n".join(logs[-20:]), height=200)

    total_tasks = len(selected_tasks)
    completed = 0

    for task_name, task_info in selected_tasks:
        status_text.text(f"{task_name}を処理中...")
        add_log(f"{task_name}の処理を開始")

        try:
            python_exe = sys.executable
            script_path = os.path.join(PROJECT_ROOT, task_info["script"])

            if not os.path.exists(script_path):
                add_log(f"⚠️ {task_name}: スクリプトが見つかりません")
                completed += 1
                progress_bar.progress(completed / total_tasks)
                continue

            result = subprocess.run(
                [python_exe, script_path],
                capture_output=True,
                text=True,
                cwd=PROJECT_ROOT,
                timeout=600,
                encoding='utf-8'
            )

            if result.returncode == 0:
                add_log(f"✅ {task_name}: 完了")
            else:
                add_log(f"⚠️ {task_name}: 警告あり")
                if result.stderr:
                    add_log(f"   詳細: {result.stderr[:200]}")

        except subprocess.TimeoutExpired:
            add_log(f"⏱️ {task_name}: タイムアウト（10分経過）")
        except Exception as e:
            add_log(f"❌ {task_name}: エラー - {str(e)[:100]}")

        completed += 1
        progress_bar.progress(completed / total_tasks)

    status_text.text("✅ 補完データ取得完了！")
    st.success("✅ 補完データの取得が完了しました！")


def _run_all_supplement_scripts(add_log=None, status_text=None):
    """すべての補完スクリプトを実行"""
    tasks = [
        ("決まり手データ", "補完_決まり手データ_改善版.py"),
        ("レース詳細データv4", "補完_レース詳細データ_改善版v4.py"),
        ("天候データ", "補完_天候データ_改善版.py"),
        ("風向データ", "補完_風向データ_改善版.py"),
    ]

    if add_log is None:
        add_log = lambda x: None
    if status_text is None:
        status_text = st.empty()

    for task_name, script_name in tasks:
        status_text.text(f"{task_name}を処理中...")
        add_log(f"{task_name}の処理を開始")

        try:
            python_exe = sys.executable
            script_path = os.path.join(PROJECT_ROOT, script_name)

            if not os.path.exists(script_path):
                add_log(f"⚠️ {task_name}: スクリプトが見つかりません")
                continue

            result = subprocess.run(
                [python_exe, script_path],
                capture_output=True,
                text=True,
                cwd=PROJECT_ROOT,
                timeout=600,
                encoding='utf-8'
            )

            if result.returncode == 0:
                add_log(f"✅ {task_name}: 完了")
            else:
                add_log(f"⚠️ {task_name}: 警告あり")

        except subprocess.TimeoutExpired:
            add_log(f"⏱️ {task_name}: タイムアウト")
        except Exception as e:
            add_log(f"❌ {task_name}: エラー - {str(e)[:100]}")


def _show_collection_status():
    """収集状況を表示"""
    st.markdown("### 📊 データ収集状況")

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        # 最新データの日付
        cursor.execute("SELECT MAX(race_date) FROM races")
        latest_date = cursor.fetchone()[0]

        # 本日のレース数
        today = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("SELECT COUNT(*) FROM races WHERE race_date = ?", (today,))
        today_count = cursor.fetchone()[0]

        # 総レース数
        cursor.execute("SELECT COUNT(*) FROM races")
        total = cursor.fetchone()[0]

        # 結果データ数
        cursor.execute("SELECT COUNT(*) FROM results")
        results_count = cursor.fetchone()[0]

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("最新データ日付", latest_date if latest_date else "N/A")

        with col2:
            st.metric("本日のレース数", today_count)

        with col3:
            st.metric("総レース数", f"{total:,}")

        with col4:
            st.metric("結果データ数", f"{results_count:,}")

        conn.close()

    except Exception as e:
        st.error(f"ステータス取得エラー: {e}")


def _show_period_data_summary(start_date, end_date):
    """期間データのサマリーを表示"""
    st.subheader("📊 取得データ確認")

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        start_str = start_date.strftime('%Y-%m-%d') if hasattr(start_date, 'strftime') else str(start_date)
        end_str = end_date.strftime('%Y-%m-%d') if hasattr(end_date, 'strftime') else str(end_date)

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            cursor.execute("""
                SELECT COUNT(*) FROM races
                WHERE race_date BETWEEN ? AND ?
            """, (start_str, end_str))
            race_count = cursor.fetchone()[0]
            st.metric("レース数", f"{race_count:,}")

        with col2:
            cursor.execute("""
                SELECT COUNT(*) FROM results r
                JOIN races ra ON r.race_id = ra.id
                WHERE ra.race_date BETWEEN ? AND ?
            """, (start_str, end_str))
            result_count = cursor.fetchone()[0]
            st.metric("結果データ", f"{result_count:,}")

        with col3:
            cursor.execute("""
                SELECT COUNT(*) FROM race_details rd
                JOIN races ra ON rd.race_id = ra.id
                WHERE ra.race_date BETWEEN ? AND ?
            """, (start_str, end_str))
            detail_count = cursor.fetchone()[0]
            st.metric("レース詳細", f"{detail_count:,}")

        with col4:
            cursor.execute("""
                SELECT COUNT(*) FROM results r
                JOIN races ra ON r.race_id = ra.id
                WHERE ra.race_date BETWEEN ? AND ? AND r.kimarite IS NOT NULL
            """, (start_str, end_str))
            kimarite_count = cursor.fetchone()[0]
            if result_count > 0:
                ratio = kimarite_count / result_count * 100
                st.metric("決まり手", f"{ratio:.1f}%")
            else:
                st.metric("決まり手", "0%")

        conn.close()

    except Exception as e:
        st.error(f"データ確認エラー: {e}")
