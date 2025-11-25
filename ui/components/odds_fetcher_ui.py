"""
オッズ取得UIコンポーネント
"""
import streamlit as st
from datetime import datetime

from src.scraper.auto_odds_fetcher import AutoOddsFetcher
from src.scraper.schedule_scraper import ScheduleScraper


def render_odds_fetcher():
    """オッズ自動取得UI"""
    st.header("📊 オッズ自動取得")
    st.markdown("本日のレースのオッズを自動的に取得してデータベースに保存します")

    st.markdown("---")

    # クイックスタート
    st.markdown("### 🚀 クイックスタート")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("📥 本日のオッズを一括取得", type="primary", use_container_width=True):
            fetch_all_odds_for_today()

    with col2:
        if st.button("🔍 オッズ取得状況を確認", use_container_width=True):
            check_odds_status()

    st.markdown("---")

    # 個別取得
    st.markdown("### 🎯 個別レースのオッズ取得")

    with st.form("manual_odds_fetch"):
        col1, col2, col3 = st.columns(3)

        with col1:
            venue_code = st.selectbox(
                "会場",
                options=['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12',
                        '13', '14', '15', '16', '17', '18', '19', '20', '21', '22', '23', '24'],
                format_func=lambda x: f"{x} - {get_venue_name(x)}"
            )

        with col2:
            race_date = st.date_input("レース日", value=datetime.now())

        with col3:
            race_number = st.number_input("レース番号", min_value=1, max_value=12, value=1)

        if st.form_submit_button("取得開始", use_container_width=True):
            fetch_single_race_odds(venue_code, race_date, race_number)

    st.markdown("---")

    # 説明
    st.markdown("### ℹ️ 使い方")
    st.info("""
    **本日のオッズを一括取得**
    - 本日開催される全てのレースのオッズを自動取得します
    - 3連単オッズと単勝オッズの両方を取得します
    - 処理には数分かかる場合があります

    **個別レースのオッズ取得**
    - 特定のレースのオッズのみを取得します
    - テストや再取得に便利です

    **注意事項**
    - オッズはレース開始前に公開されます
    - 公開前のレースは取得できません
    - サーバー負荷軽減のため、連続取得に遅延が入ります
    """)


def fetch_all_odds_for_today():
    """本日の全レースのオッズを取得"""
    st.info("🚀 本日のオッズ一括取得を開始します...")

    progress_bar = st.progress(0)
    status_text = st.empty()

    try:
        # スケジュール取得
        status_text.text("Step 1/2: 本日のスケジュールを取得中...")
        progress_bar.progress(0.1)

        schedule_scraper = ScheduleScraper()
        today_schedule = schedule_scraper.get_today_schedule()
        schedule_scraper.close()

        if not today_schedule:
            st.warning("本日開催のレースが見つかりませんでした")
            progress_bar.empty()
            status_text.empty()
            return

        st.info(f"📍 {len(today_schedule)}会場のオッズを取得します")
        progress_bar.progress(0.2)

        # オッズ取得開始
        status_text.text("Step 2/2: オッズを取得中...")

        fetcher = AutoOddsFetcher(delay=1.5)
        result = fetcher.fetch_odds_for_today(today_schedule)
        fetcher.close()

        progress_bar.progress(1.0)
        status_text.empty()
        progress_bar.empty()

        # 結果表示
        st.success(f"✅ オッズ取得完了!")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("総レース数", result['total_races'])
        with col2:
            st.metric("取得成功", result['success_count'])
        with col3:
            st.metric("取得失敗", result['failed_count'])

        # 詳細を展開可能な形式で表示
        with st.expander("📋 詳細結果を表示"):
            for detail in result['details']:
                venue_code = detail['venue_code']
                race_number = detail['race_number']
                race_result = detail['result']

                status_icon = "✅" if (race_result['trifecta_success'] or race_result['win_success']) else "❌"
                st.write(f"{status_icon} {get_venue_name(venue_code)} {race_number}R - {race_result['message']}")

    except Exception as e:
        st.error(f"❌ エラーが発生しました: {e}")
        import traceback
        st.code(traceback.format_exc())
    finally:
        progress_bar.empty()
        status_text.empty()


def fetch_single_race_odds(venue_code: str, race_date, race_number: int):
    """個別レースのオッズを取得"""
    import sqlite3
    from config.settings import DATABASE_PATH

    st.info(f"📥 オッズ取得中: {get_venue_name(venue_code)} {race_date.strftime('%Y-%m-%d')} {race_number}R")

    try:
        # race_idを取得
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id
            FROM races
            WHERE venue_code = ? AND race_date = ? AND race_number = ?
        """, (venue_code, race_date.strftime('%Y-%m-%d'), race_number))

        row = cursor.fetchone()
        conn.close()

        if not row:
            st.error("❌ 指定されたレースが見つかりません。先にレースデータを取得してください。")
            return

        race_id = row[0]

        # オッズ取得
        with st.spinner("オッズを取得中..."):
            fetcher = AutoOddsFetcher()
            result = fetcher.fetch_odds_for_race(
                race_id,
                venue_code,
                race_date.strftime('%Y%m%d'),
                race_number
            )
            fetcher.close()

        # 結果表示
        if result['trifecta_success'] or result['win_success']:
            st.success(result['message'])

            col1, col2 = st.columns(2)
            with col1:
                if result['trifecta_success']:
                    st.metric("3連単オッズ", f"{result['trifecta_count']}通り")
                else:
                    st.metric("3連単オッズ", "取得失敗")

            with col2:
                if result['win_success']:
                    st.metric("単勝オッズ", "6艇")
                else:
                    st.metric("単勝オッズ", "取得失敗")
        else:
            st.error(result['message'])

    except Exception as e:
        st.error(f"❌ エラー: {e}")
        import traceback
        st.code(traceback.format_exc())


def check_odds_status():
    """オッズ取得状況を確認"""
    import sqlite3
    from config.settings import DATABASE_PATH

    st.info("🔍 オッズ取得状況を確認中...")

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        # 今日のレース数
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute("""
            SELECT COUNT(*)
            FROM races
            WHERE race_date = ?
        """, (today,))
        total_races = cursor.fetchone()[0]

        # オッズ取得済みレース数（3連単）
        cursor.execute("""
            SELECT COUNT(DISTINCT race_id)
            FROM trifecta_odds t
            JOIN races r ON t.race_id = r.id
            WHERE r.race_date = ?
        """, (today,))
        trifecta_fetched = cursor.fetchone()[0]

        # オッズ取得済みレース数（単勝）
        cursor.execute("""
            SELECT COUNT(DISTINCT race_id)
            FROM win_odds w
            JOIN races r ON w.race_id = r.id
            WHERE r.race_date = ?
        """, (today,))
        win_fetched = cursor.fetchone()[0]

        conn.close()

        # 結果表示
        st.success("✅ 状況確認完了")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("本日のレース数", total_races)
        with col2:
            st.metric("3連単取得済み", f"{trifecta_fetched} / {total_races}")
        with col3:
            st.metric("単勝取得済み", f"{win_fetched} / {total_races}")

        # 進捗率
        if total_races > 0:
            trifecta_rate = (trifecta_fetched / total_races) * 100
            win_rate = (win_fetched / total_races) * 100

            st.markdown("### 📊 取得進捗")
            st.progress(trifecta_rate / 100, text=f"3連単: {trifecta_rate:.1f}%")
            st.progress(win_rate / 100, text=f"単勝: {win_rate:.1f}%")

    except Exception as e:
        st.error(f"❌ エラー: {e}")


def get_venue_name(code: str) -> str:
    """会場コードから会場名を取得"""
    venue_map = {
        '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島',
        '05': '多摩川', '06': '浜名湖', '07': '蒲郡', '08': '常滑',
        '09': '津', '10': '三国', '11': 'びわこ', '12': '住之江',
        '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島',
        '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
        '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
    }
    return venue_map.get(code, f"会場{code}")
