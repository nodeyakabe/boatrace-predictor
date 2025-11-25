"""
共通ウィジェットコンポーネント
"""
import streamlit as st
import sqlite3
from config.settings import DATABASE_PATH


@st.cache_data(ttl=300)  # 5分間キャッシュ
def get_database_stats():
    """データベース統計情報を取得（キャッシュ付き）"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM races")
        race_count = cursor.fetchone()[0]
        conn.close()
        return race_count
    except Exception as e:
        return None


def show_database_stats():
    """データベース統計情報を表示"""
    race_count = get_database_stats()
    if race_count is not None:
        st.metric("総レース数", f"{race_count:,}")
    else:
        st.error("DB接続エラー")


def show_progress_bar(progress, text="処理中..."):
    """プログレスバーを表示"""
    st.progress(progress, text=text)


def show_status_indicator(status, success_msg="完了", error_msg="エラー"):
    """ステータスインジケーターを表示"""
    if status == "success":
        st.success(success_msg)
    elif status == "error":
        st.error(error_msg)
    elif status == "warning":
        st.warning("警告")
    else:
        st.info("処理中...")


def render_venue_selector(label="競艇場を選択", key="venue_select"):
    """競艇場選択ドロップダウン"""
    venue_map = {
        '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島',
        '05': '多摩川', '06': '浜名湖', '07': '蒲郡', '08': '常滑',
        '09': '津', '10': '三国', '11': 'びわこ', '12': '住之江',
        '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島',
        '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
        '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
    }

    options = [f"{code} - {name}" for code, name in venue_map.items()]
    selected = st.selectbox(label, options, key=key)
    venue_code = selected.split(" - ")[0] if selected else None

    return venue_code, venue_map.get(venue_code, "")


def render_data_quality_badge(quality_score):
    """データ品質バッジを表示"""
    if quality_score >= 0.8:
        st.success(f"データ品質: 優良 ({quality_score*100:.1f}%)")
    elif quality_score >= 0.6:
        st.warning(f"データ品質: 普通 ({quality_score*100:.1f}%)")
    else:
        st.error(f"データ品質: 要改善 ({quality_score*100:.1f}%)")


def render_confidence_badge(confidence):
    """信頼度バッジを表示"""
    if confidence >= 80:
        return "🟢 高信頼度"
    elif confidence >= 60:
        return "🟡 中信頼度"
    else:
        return "🔴 低信頼度"
