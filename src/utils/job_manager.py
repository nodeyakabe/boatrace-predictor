"""
バックグラウンドジョブ管理システム

- ロックファイルによる重複実行防止
- 進捗状況のファイル記録
- PIDチェックによる異常終了検出
"""
import os
import json
import subprocess
import sys
from datetime import datetime
from typing import Optional, Dict, Any
import psutil


# ジョブディレクトリ
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
JOBS_DIR = os.path.join(PROJECT_ROOT, 'temp', 'jobs')


def _ensure_jobs_dir():
    """ジョブディレクトリを作成"""
    os.makedirs(JOBS_DIR, exist_ok=True)


def _get_lock_path(job_name: str) -> str:
    """ロックファイルのパスを取得"""
    return os.path.join(JOBS_DIR, f'{job_name}.lock')


def _get_progress_path(job_name: str) -> str:
    """進捗ファイルのパスを取得"""
    return os.path.join(JOBS_DIR, f'{job_name}.json')


def is_process_running(pid: int) -> bool:
    """プロセスが実行中か確認"""
    try:
        process = psutil.Process(pid)
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def is_job_running(job_name: str) -> bool:
    """ジョブが実行中か確認"""
    _ensure_jobs_dir()
    lock_path = _get_lock_path(job_name)

    if not os.path.exists(lock_path):
        return False

    # ロックファイルからPIDを読み取り
    try:
        with open(lock_path, 'r', encoding='utf-8') as f:
            lock_data = json.load(f)

        pid = lock_data.get('pid')
        if pid and is_process_running(pid):
            return True
        else:
            # プロセスが終了しているならロックを解除
            cleanup_job(job_name)
            return False
    except Exception:
        # 読み取りエラー時はロック解除
        cleanup_job(job_name)
        return False


def start_job(job_name: str, script_path: str, args: list = None) -> Dict[str, Any]:
    """
    バックグラウンドジョブを開始

    Returns:
        {'success': bool, 'message': str, 'pid': int or None}
    """
    _ensure_jobs_dir()

    # 既に実行中か確認
    if is_job_running(job_name):
        return {
            'success': False,
            'message': f'ジョブ「{job_name}」は既に実行中です',
            'pid': None
        }

    # スクリプトの存在確認
    if not os.path.exists(script_path):
        return {
            'success': False,
            'message': f'スクリプトが見つかりません: {script_path}',
            'pid': None
        }

    try:
        # サブプロセスを起動（デタッチモード）
        cmd = [sys.executable, script_path]
        if args:
            cmd.extend([str(a) for a in args])

        # Windowsの場合はCREATE_NEW_PROCESS_GROUPを使用
        if sys.platform == 'win32':
            process = subprocess.Popen(
                cmd,
                cwd=PROJECT_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            )
        else:
            process = subprocess.Popen(
                cmd,
                cwd=PROJECT_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True
            )

        pid = process.pid

        # ロックファイルを作成
        lock_path = _get_lock_path(job_name)
        lock_data = {
            'pid': pid,
            'job_name': job_name,
            'script': script_path,
            'args': args,
            'started_at': datetime.now().isoformat()
        }

        with open(lock_path, 'w', encoding='utf-8') as f:
            json.dump(lock_data, f, ensure_ascii=False, indent=2)

        # 初期進捗ファイルを作成
        update_job_progress(job_name, {
            'status': 'running',
            'progress': 0,
            'message': '処理を開始しました',
            'started_at': datetime.now().isoformat()
        })

        return {
            'success': True,
            'message': f'ジョブを開始しました (PID: {pid})',
            'pid': pid
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'ジョブ開始エラー: {str(e)}',
            'pid': None
        }


def update_job_progress(job_name: str, progress_data: Dict[str, Any]):
    """ジョブの進捗を更新"""
    _ensure_jobs_dir()
    progress_path = _get_progress_path(job_name)

    # 既存の進捗を読み込み
    existing = {}
    if os.path.exists(progress_path):
        try:
            with open(progress_path, 'r', encoding='utf-8') as f:
                existing = json.load(f)
        except Exception:
            pass

    # 更新
    existing.update(progress_data)
    existing['updated_at'] = datetime.now().isoformat()

    with open(progress_path, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)


def get_job_progress(job_name: str) -> Optional[Dict[str, Any]]:
    """ジョブの進捗を取得"""
    _ensure_jobs_dir()
    progress_path = _get_progress_path(job_name)

    if not os.path.exists(progress_path):
        return None

    try:
        with open(progress_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def cleanup_job(job_name: str):
    """ジョブのロックファイルを削除"""
    _ensure_jobs_dir()
    lock_path = _get_lock_path(job_name)

    if os.path.exists(lock_path):
        try:
            os.remove(lock_path)
        except Exception:
            pass


def complete_job(job_name: str, success: bool = True, message: str = ''):
    """ジョブを完了としてマーク"""
    update_job_progress(job_name, {
        'status': 'completed' if success else 'failed',
        'progress': 100 if success else -1,
        'message': message or ('完了しました' if success else 'エラーが発生しました'),
        'completed_at': datetime.now().isoformat()
    })
    cleanup_job(job_name)


def cancel_job(job_name: str) -> bool:
    """ジョブをキャンセル"""
    _ensure_jobs_dir()
    lock_path = _get_lock_path(job_name)

    if not os.path.exists(lock_path):
        return False

    try:
        with open(lock_path, 'r', encoding='utf-8') as f:
            lock_data = json.load(f)

        pid = lock_data.get('pid')
        if pid:
            try:
                process = psutil.Process(pid)
                process.terminate()
                process.wait(timeout=5)
            except Exception:
                pass

        update_job_progress(job_name, {
            'status': 'cancelled',
            'message': 'キャンセルされました',
            'cancelled_at': datetime.now().isoformat()
        })
        cleanup_job(job_name)
        return True

    except Exception:
        cleanup_job(job_name)
        return False


def get_all_jobs() -> Dict[str, Dict[str, Any]]:
    """すべてのジョブ状況を取得"""
    _ensure_jobs_dir()
    jobs = {}

    for filename in os.listdir(JOBS_DIR):
        if filename.endswith('.json'):
            job_name = filename[:-5]  # .jsonを除去
            progress = get_job_progress(job_name)
            if progress:
                progress['is_running'] = is_job_running(job_name)
                jobs[job_name] = progress

    return jobs
