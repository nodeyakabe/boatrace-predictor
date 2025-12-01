"""
ワークフロー管理コンポーネント
データ準備の自動化とワンクリック実行
バックグラウンド処理専用版
"""
import streamlit as st
import subprocess
import logging
import os
import sys
import time
from datetime import datetime
from src.utils.job_manager import start_job, is_job_running, get_job_progress, cancel_job

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))

# ジョブ名定数
JOB_TODAY_PREDICTION = 'today_prediction'
JOB_TRAINING = 'training'


def render_workflow_manager():
    """データ準備ワークフローマネージャー"""
    st.header("🔧 データ準備ワークフロー")
    st.markdown("データ収集から学習までを自動化（バックグラウンド処理）")

    # ワンクリック実行ボタン
    st.markdown("### 🚀 クイックスタート")

    col1, col2 = st.columns(2)

    # ジョブ実行中かチェック
    today_running = is_job_running(JOB_TODAY_PREDICTION)
    training_running = is_job_running(JOB_TRAINING)

    with col1:
        if today_running:
            _render_running_job(JOB_TODAY_PREDICTION, "stop_today")
        else:
            if st.button("🎯 今日の予測を生成", type="primary", use_container_width=True):
                _run_background_job(JOB_TODAY_PREDICTION, 'background_today_prediction.py')

    with col2:
        if training_running:
            _render_running_job(JOB_TRAINING, "stop_training")
        else:
            if st.button("📚 過去データ学習", use_container_width=True):
                st.info("📚 過去データ学習機能は準備中です")

    # ジョブ実行中の場合、3秒後に自動リフレッシュ
    if today_running or training_running:
        time.sleep(3)
        st.rerun()

    st.markdown("---")

    # 個別ステップ実行（簡易版）
    st.markdown("### 📋 個別ステップ実行")

    with st.expander("Step 1: 本日データ取得"):
        st.info("「今日の予測を生成」ボタンで自動実行されます")

    with st.expander("Step 2: データ品質チェック"):
        if st.button("▶️ 実行", key="step2"):
            _check_data_quality()

    with st.expander("Step 3: 法則再解析"):
        if st.button("▶️ 実行", key="step3"):
            _reanalyze_rules()


def _render_running_job(job_name: str, stop_key: str):
    """実行中ジョブの表示"""
    progress = get_job_progress(job_name)
    pct = progress.get('progress', 0) if progress else 0
    msg = progress.get('message', '処理中...') if progress else '処理中...'
    step = progress.get('step', '') if progress else ''
    started_at = progress.get('started_at', '') if progress else ''

    # 経過時間を計算
    elapsed_str = ""
    if started_at:
        try:
            start_time = datetime.fromisoformat(started_at)
            elapsed = datetime.now() - start_time
            elapsed_sec = int(elapsed.total_seconds())
            elapsed_str = f" ({elapsed_sec // 60}分{elapsed_sec % 60}秒経過)"
        except:
            pass

    st.warning(f"🔄 実行中: {step} - {msg}{elapsed_str}")
    st.progress(pct / 100)

    if st.button("⏹️ 停止", key=stop_key):
        cancel_job(job_name)
        st.rerun()


def _run_background_job(job_name: str, script_name: str):
    """バックグラウンドジョブを開始"""
    script_path = os.path.join(PROJECT_ROOT, 'scripts', script_name)

    if not os.path.exists(script_path):
        st.error(f"スクリプトが見つかりません: {script_name}")
        return

    result = start_job(job_name, script_path)

    if result['success']:
        st.success(f"✅ {result['message']}")
        st.info("処理はバックグラウンドで実行されます。タブを移動しても処理は継続します。")
        st.rerun()
    else:
        st.error(result['message'])


def _check_data_quality():
    """データ品質チェック"""
    try:
        from src.analysis.data_coverage_checker import DataCoverageChecker
        from config.settings import DATABASE_PATH

        with st.spinner("データ品質をチェック中..."):
            checker = DataCoverageChecker(DATABASE_PATH)
            report = checker.get_coverage_report()

            overall_score = report["overall_score"]
            st.metric("データ充足率", f"{overall_score*100:.1f}%")

            if overall_score >= 0.8:
                st.success("✅ データは充実しています")
            elif overall_score >= 0.5:
                st.warning("⚠️ 一部データが不足しています")
            else:
                st.error("❌ データが大幅に不足しています")
    except Exception as e:
        st.error(f"チェックエラー: {e}")


def _reanalyze_rules():
    """法則を再解析"""
    try:
        with st.spinner("法則を再解析中..."):
            python_exe = sys.executable
            script_path = os.path.join(PROJECT_ROOT, 'reanalyze_all.py')

            result = subprocess.run(
                [python_exe, script_path],
                capture_output=True,
                text=True,
                timeout=900
            )

            if result.returncode == 0:
                st.success("✅ 法則の再解析が完了しました")
            else:
                st.warning("⚠️ 一部の法則解析に失敗しました")
    except Exception as e:
        st.error(f"再解析エラー: {e}")
