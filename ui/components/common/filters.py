"""
共通フィルターコンポーネント
"""
import streamlit as st
from datetime import datetime


def render_date_filter(key_prefix="global"):
    """日付フィルター"""
    st.subheader("📅 対象日")
    target_date = st.date_input(
        "日付を選択",
        datetime.now(),
        key=f"{key_prefix}_target_date"
    )
    return target_date


def render_venue_filter(key_prefix="global"):
    """競艇場フィルター"""
    st.subheader("🏟️ 競艇場")

    # セッションステートで選択状態を管理
    session_key = f'{key_prefix}_selected_venues'
    if session_key not in st.session_state:
        st.session_state[session_key] = set()

    # すべて選択/解除ボタン
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("すべて選択", key=f"{key_prefix}_select_all_btn", use_container_width=True):
            venue_list = [f'{i:02d}' for i in range(1, 25)]
            st.session_state[session_key] = set(venue_list)
            st.rerun()
    with col_btn2:
        if st.button("すべて解除", key=f"{key_prefix}_deselect_all_btn", use_container_width=True):
            st.session_state[session_key] = set()
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
            is_selected1 = code1 in st.session_state[session_key]
            button_type1 = "primary" if is_selected1 else "secondary"
            if st.button(f"{name1}", key=f"{key_prefix}_venue_btn_{code1}", type=button_type1, use_container_width=True):
                if is_selected1:
                    st.session_state[session_key].remove(code1)
                else:
                    st.session_state[session_key].add(code1)
                st.rerun()

        # 右列
        if i + 1 < len(venue_data):
            code2, name2 = venue_data[i + 1]
            with col2:
                is_selected2 = code2 in st.session_state[session_key]
                button_type2 = "primary" if is_selected2 else "secondary"
                if st.button(f"{name2}", key=f"{key_prefix}_venue_btn_{code2}", type=button_type2, use_container_width=True):
                    if is_selected2:
                        st.session_state[session_key].remove(code2)
                    else:
                        st.session_state[session_key].add(code2)
                    st.rerun()

    selected_venues = list(st.session_state[session_key])
    st.info(f"選択中: {len(selected_venues)}会場")

    return selected_venues


def render_sidebar_filters():
    """サイドバー用のグローバルフィルター"""
    with st.sidebar:
        st.header("🔍 フィルター設定")
        target_date = render_date_filter("sidebar")
        selected_venues = render_venue_filter("sidebar")

    return target_date, selected_venues
