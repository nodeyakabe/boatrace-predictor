"""
自動データ収集コンポーネント
"""
import streamlit as st
from datetime import datetime, timedelta
from src.scraper.bulk_scraper import BulkScraper


def render_auto_data_collector():
    """自動データ収集UI"""
    st.header("📥 自動データ収集")

    st.markdown("""
    このツールは、指定した期間のデータを自動的に収集します。
    - 出走表
    - 展示タイム
    - オッズ
    - レース結果
    """)

    # クイックアクション
    st.markdown("### 🚀 クイックアクション")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("📅 今日のデータ", use_container_width=True, type="primary"):
            collect_today_data()

    with col2:
        if st.button("📅 明日のデータ", use_container_width=True):
            collect_tomorrow_data()

    with col3:
        if st.button("📅 今週のデータ", use_container_width=True):
            collect_this_week_data()

    st.markdown("---")

    # カスタム期間収集
    st.markdown("### ⚙️ カスタム期間収集")

    col1, col2 = st.columns(2)

    with col1:
        start_date = st.date_input(
            "開始日",
            datetime.now() - timedelta(days=7),
            key="auto_collector_start_date"
        )

    with col2:
        end_date = st.date_input(
            "終了日",
            datetime.now(),
            key="auto_collector_end_date"
        )

    # 会場選択
    venue_selection = st.radio(
        "対象会場",
        ["すべての会場", "特定の会場を選択"],
        horizontal=True
    )

    selected_venues = None
    if venue_selection == "特定の会場を選択":
        venue_options = [f"{i:02d}" for i in range(1, 25)]
        selected_venues = st.multiselect(
            "会場を選択",
            venue_options,
            default=["01", "12", "24"]
        )

    if st.button("🔄 データ収集を開始", type="primary"):
        collect_custom_period_data(start_date, end_date, selected_venues)

    st.markdown("---")

    # 収集状況モニター
    st.markdown("### 📊 収集状況")
    show_collection_status()


def collect_today_data():
    """今日のデータを収集"""
    st.info("📥 今日のデータを収集中...")

    try:
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

    except Exception as e:
        st.error(f"❌ エラー: {e}")


def collect_tomorrow_data():
    """明日のデータを収集"""
    st.info("📥 明日のデータを収集中...")

    try:
        tomorrow = datetime.now() + timedelta(days=1)
        tomorrow_str = tomorrow.strftime("%Y-%m-%d")

        scraper = BulkScraper()

        # 明日開催の会場を推測（全会場試行）
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
            st.success(
                f"✅ 完了！ {len(successful_venues)}会場 {total_races}レース取得しました"
            )
        else:
            st.warning("明日開催のレースが見つかりませんでした")

    except Exception as e:
        st.error(f"❌ エラー: {e}")


def collect_this_week_data():
    """今週のデータを収集"""
    st.info("📥 今週のデータを収集中...")

    today = datetime.now()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    collect_custom_period_data(
        start_of_week.date(),
        end_of_week.date(),
        None
    )


def collect_custom_period_data(start_date, end_date, venue_codes):
    """カスタム期間のデータを収集"""
    st.info(f"📥 {start_date} から {end_date} のデータを収集中...")

    try:
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

        progress_bar = st.progress(0)
        status_text = st.empty()

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

        st.success(f"✅ 完了！ {total_races}レース取得しました")

    except Exception as e:
        st.error(f"❌ エラー: {e}")


def show_collection_status():
    """収集状況を表示"""
    try:
        import sqlite3
        from config.settings import DATABASE_PATH

        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        # 最新データの日付
        cursor.execute("SELECT MAX(race_date) FROM races")
        latest_date = cursor.fetchone()[0]

        # 本日のレース数
        today = datetime.now().strftime("%Y-%m-%d")
        cursor.execute(
            "SELECT COUNT(*) FROM races WHERE race_date = ?",
            (today,)
        )
        today_count = cursor.fetchone()[0]

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("最新データ日付", latest_date if latest_date else "N/A")

        with col2:
            st.metric("本日のレース数", today_count)

        with col3:
            cursor.execute("SELECT COUNT(*) FROM races")
            total = cursor.fetchone()[0]
            st.metric("総レース数", f"{total:,}")

        conn.close()

    except Exception as e:
        st.error(f"ステータス取得エラー: {e}")
