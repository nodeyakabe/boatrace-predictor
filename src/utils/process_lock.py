#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
プロセスロック管理

複数のデータ収集・投入プロセスが同時実行されないようにロックを管理します。
"""
import os
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOCK_DIR = PROJECT_ROOT / 'data' / 'locks'
LOCK_DIR.mkdir(parents=True, exist_ok=True)


class ProcessLock:
    """プロセスロッククラス"""

    def __init__(self, lock_name: str, timeout: int = 3600):
        """
        Args:
            lock_name: ロックの名前（例: 'data_collection', 'db_insert'）
            timeout: ロックのタイムアウト（秒）
        """
        self.lock_name = lock_name
        self.lock_file = LOCK_DIR / f'{lock_name}.lock'
        self.timeout = timeout
        self.acquired = False

    def acquire(self, force: bool = False) -> bool:
        """
        ロックを取得

        Args:
            force: 強制的にロックを取得（既存ロックを削除）

        Returns:
            ロック取得成功時True

        Raises:
            RuntimeError: ロック取得失敗時
        """
        # 既存ロックのチェック
        if self.lock_file.exists():
            if force:
                print(f"[WARNING] 既存ロックを強制削除します: {self.lock_file}")
                self.lock_file.unlink()
            else:
                # ロックファイルの内容を読み込み
                lock_info = self._read_lock_info()
                if lock_info:
                    pid = lock_info.get('pid')
                    timestamp = lock_info.get('timestamp')
                    elapsed = time.time() - float(lock_info.get('start_time', 0))

                    # タイムアウトチェック
                    if elapsed > self.timeout:
                        print(f"[WARNING] ロックがタイムアウトしました（{elapsed/60:.1f}分）。削除します。")
                        self.lock_file.unlink()
                    else:
                        error_msg = (
                            f"別のプロセスが実行中です:\n"
                            f"  ロック名: {self.lock_name}\n"
                            f"  プロセスID: {pid}\n"
                            f"  開始時刻: {timestamp}\n"
                            f"  経過時間: {elapsed/60:.1f}分\n"
                            f"\n"
                            f"対処方法:\n"
                            f"1. 実行中のプロセスが完了するまで待つ\n"
                            f"2. プロセスを手動で停止: taskkill /PID {pid} /F\n"
                            f"3. 強制的にロックを削除: --force オプション\n"
                        )
                        raise RuntimeError(error_msg)

        # ロックファイル作成
        self._write_lock_info()
        self.acquired = True
        print(f"[INFO] ロック取得: {self.lock_name} (PID: {os.getpid()})")
        return True

    def release(self):
        """ロックを解放"""
        if self.acquired and self.lock_file.exists():
            self.lock_file.unlink()
            self.acquired = False
            print(f"[INFO] ロック解放: {self.lock_name}")

    def _write_lock_info(self):
        """ロックファイルに情報を書き込み"""
        lock_info = {
            'pid': os.getpid(),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'start_time': time.time(),
            'lock_name': self.lock_name
        }

        with open(self.lock_file, 'w') as f:
            for key, value in lock_info.items():
                f.write(f"{key}={value}\n")

    def _read_lock_info(self) -> Optional[dict]:
        """ロックファイルから情報を読み込み"""
        if not self.lock_file.exists():
            return None

        lock_info = {}
        try:
            with open(self.lock_file, 'r') as f:
                for line in f:
                    if '=' in line:
                        key, value = line.strip().split('=', 1)
                        lock_info[key] = value
        except Exception as e:
            print(f"[WARNING] ロックファイル読み込みエラー: {e}")
            return None

        return lock_info

    def __enter__(self):
        """with文のサポート"""
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """with文のサポート"""
        self.release()


def check_running_processes(lock_name: str = None) -> list:
    """
    実行中のプロセスをチェック

    Args:
        lock_name: 特定のロック名でフィルタ（Noneの場合は全て）

    Returns:
        実行中のプロセス情報のリスト
    """
    running = []

    # ロックディレクトリ内の全ロックファイルをチェック
    for lock_file in LOCK_DIR.glob('*.lock'):
        if lock_name and lock_file.stem != lock_name:
            continue

        lock = ProcessLock(lock_file.stem)
        lock_info = lock._read_lock_info()

        if lock_info:
            running.append({
                'lock_name': lock_info.get('lock_name', lock_file.stem),
                'pid': lock_info.get('pid'),
                'timestamp': lock_info.get('timestamp'),
                'elapsed': time.time() - float(lock_info.get('start_time', 0))
            })

    return running


def cleanup_stale_locks(timeout: int = 3600):
    """
    古いロックファイルをクリーンアップ

    Args:
        timeout: この秒数以上経過したロックを削除
    """
    for lock_file in LOCK_DIR.glob('*.lock'):
        lock = ProcessLock(lock_file.stem)
        lock_info = lock._read_lock_info()

        if lock_info:
            elapsed = time.time() - float(lock_info.get('start_time', 0))
            if elapsed > timeout:
                print(f"[INFO] 古いロックを削除: {lock_file.name} ({elapsed/60:.1f}分経過)")
                lock_file.unlink()


if __name__ == '__main__':
    # テスト用
    print("=== プロセスロックテスト ===")

    # 実行中プロセスの確認
    running = check_running_processes()
    if running:
        print("\n実行中のプロセス:")
        for proc in running:
            print(f"  - {proc['lock_name']}: PID {proc['pid']}, {proc['elapsed']/60:.1f}分経過")
    else:
        print("\n実行中のプロセスはありません")

    # ロックのテスト
    print("\nロック取得テスト...")
    with ProcessLock('test_lock') as lock:
        print("ロック取得成功")
        time.sleep(2)
        print("処理実行中...")

    print("ロック解放完了")
