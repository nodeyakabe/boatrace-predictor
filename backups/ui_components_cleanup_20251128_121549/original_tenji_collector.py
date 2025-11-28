"""
オリジナル展示データ収集UI
"""
import streamlit as st
import subprocess
import os
import sys


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))


def render_original_tenji_collector():
    """オリジナル展示収集UIのレンダリング"""
    st.subheader("🎯 オリジナル展示データ収集")

    st.markdown("""
    **オリジナル展示データとは？**
    - 直線タイム（chikusen_time）
    - 1周タイム（isshu_time）
    - 回り足タイム（mawariashi_time）

    **注意事項:**
    - オリジナル展示データは限られた期間のみ公開されています
    - 過去のデータは取得できないため、毎日実行して蓄積する必要があります
    """)

    # 収集対象日の選択
    st.markdown("---")
    st.markdown("**収集対象日を選択**")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("📅 昨日", key="collect_yesterday", use_container_width=True):
            run_collection(-1)

    with col2:
        if st.button("📅 今日", key="collect_today", use_container_width=True, type="primary"):
            run_collection(0)

    # カスタム日数オフセット
    with st.expander("🔧 カスタム設定", expanded=False):
        custom_offset = st.number_input(
            "日数オフセット（今日を0として、-1=昨日）",
            min_value=-7,
            max_value=0,
            value=0,
            key="custom_offset"
        )
        if st.button("実行", key="collect_custom"):
            run_collection(custom_offset)

    st.markdown("---")

    # 実行履歴（セッションステートに保存）
    if 'collection_history' in st.session_state and st.session_state.collection_history:
        st.subheader("📋 実行履歴")
        for entry in reversed(st.session_state.collection_history[-5:]):  # 最新5件
            st.text(entry)


def run_collection(days_offset):
    """オリジナル展示収集を実行"""
    if 'collection_history' not in st.session_state:
        st.session_state.collection_history = []

    with st.spinner(f"オリジナル展示データを収集中... (今日{days_offset:+d}日)"):
        try:
            script_path = os.path.join(PROJECT_ROOT, '収集_オリジナル展示_手動実行.py')
            python_exe = os.path.join(PROJECT_ROOT, 'venv', 'Scripts', 'python.exe')

            result = subprocess.run(
                [python_exe, script_path, str(days_offset)],
                capture_output=True,
                text=True,
                timeout=600,
                cwd=PROJECT_ROOT
            )

            if result.returncode == 0:
                # 成功件数を抽出
                output = result.stdout
                if "成功:" in output:
                    success_line = [line for line in output.split('\n') if '成功:' in line][0]
                    st.success(f"✅ 収集完了！ {success_line}")

                    # 履歴に追加
                    from datetime import datetime
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    st.session_state.collection_history.append(
                        f"{timestamp} | 今日{days_offset:+d}日 | {success_line}"
                    )
                else:
                    st.success("✅ 収集完了！")

                # 詳細を折りたたみで表示
                with st.expander("📄 詳細ログ"):
                    st.code(output)

                st.rerun()
            else:
                st.error(f"❌ 収集失敗")
                st.code(result.stderr)

        except subprocess.TimeoutExpired:
            st.error("❌ タイムアウト（10分経過）")
        except Exception as e:
            st.error(f"❌ エラー: {e}")
