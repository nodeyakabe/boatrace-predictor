"""
グローバル進捗表示コンポーネント

ヘッダー部分にバックグラウンドジョブの進捗を常時表示
タブ移動しても進捗が見える
"""
import streamlit as st
from datetime import datetime
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

from src.utils.job_manager import get_all_jobs, cancel_job, is_job_running

# ジョブ名と表示名のマッピング
JOB_LABELS = {
    'today_prediction': '今日の予測生成',
    'data_collection': 'データ収集',
    'tenji_collection': 'オリジナル展示収集',
    'missing_data_fetch': '不足データ取得',
    'training': 'モデル学習',
    'odds_fetch': 'オッズ取得',
}


def render_global_progress():
    """
    グローバル進捗バーをヘッダー部分に表示

    全ページで共通で呼び出す
    """
    jobs = get_all_jobs()
    running_jobs = {k: v for k, v in jobs.items() if v.get('is_running')}

    if not running_jobs:
        return

    # 進捗バー表示エリア
    with st.container():
        st.markdown("""
        <style>
        .global-progress {
            background-color: #1e3a5f;
            border-radius: 8px;
            padding: 10px 15px;
            margin-bottom: 15px;
        }
        .global-progress-title {
            color: #fff;
            font-weight: bold;
            margin-bottom: 5px;
        }
        </style>
        """, unsafe_allow_html=True)

        for job_name, progress in running_jobs.items():
            label = JOB_LABELS.get(job_name, job_name)
            status = progress.get('status', 'running')
            pct = progress.get('progress', 0)
            message = progress.get('message', '処理中...')
            step = progress.get('step', '')

            # ヘッダーに固定表示
            col1, col2, col3 = st.columns([5, 1, 1])

            with col1:
                if step:
                    st.info(f"🔄 **{label}** - {step}: {message}")
                else:
                    st.info(f"🔄 **{label}**: {message}")

                if pct > 0:
                    st.progress(pct / 100)

            with col2:
                # 経過時間表示
                started_at = progress.get('started_at')
                if started_at:
                    try:
                        start_time = datetime.fromisoformat(started_at)
                        elapsed = (datetime.now() - start_time).total_seconds()
                        if elapsed < 60:
                            st.caption(f"⏱️ {int(elapsed)}秒")
                        else:
                            st.caption(f"⏱️ {int(elapsed // 60)}分{int(elapsed % 60)}秒")
                    except:
                        pass

            with col3:
                if st.button("❌ 停止", key=f"cancel_{job_name}"):
                    cancel_job(job_name)
                    st.rerun()

        st.markdown("---")


def get_running_jobs_summary():
    """実行中ジョブのサマリーを取得"""
    jobs = get_all_jobs()
    running_jobs = {k: v for k, v in jobs.items() if v.get('is_running')}

    if not running_jobs:
        return None

    summary = []
    for job_name, progress in running_jobs.items():
        label = JOB_LABELS.get(job_name, job_name)
        pct = progress.get('progress', 0)
        summary.append(f"{label}: {pct}%")

    return " | ".join(summary)


def show_job_complete_notification():
    """
    直近で完了したジョブの通知を表示
    """
    jobs = get_all_jobs()

    for job_name, progress in jobs.items():
        status = progress.get('status', '')
        completed_at = progress.get('completed_at')

        if status == 'completed' and completed_at:
            try:
                complete_time = datetime.fromisoformat(completed_at)
                elapsed = (datetime.now() - complete_time).total_seconds()

                # 30秒以内に完了したジョブを通知
                if elapsed < 30:
                    label = JOB_LABELS.get(job_name, job_name)
                    message = progress.get('message', '完了しました')
                    st.success(f"✅ **{label}**: {message}")
            except:
                pass

        elif status == 'failed' and completed_at:
            try:
                complete_time = datetime.fromisoformat(completed_at)
                elapsed = (datetime.now() - complete_time).total_seconds()

                if elapsed < 30:
                    label = JOB_LABELS.get(job_name, job_name)
                    message = progress.get('message', 'エラーが発生しました')
                    st.error(f"❌ **{label}**: {message}")
            except:
                pass
