#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""実行中のPythonプロセスをpsutilで表示"""
import sys
import io
import os

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)

import psutil

for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
    try:
        if proc.info['name'] == 'python.exe':
            pid = proc.info['pid']
            cmdline = proc.info['cmdline'] or []
            # Find script name
            script = ''
            args_extra = []
            found_script = False
            for part in cmdline:
                if found_script:
                    args_extra.append(part)
                elif part.endswith('.py'):
                    script = os.path.basename(part)
                    found_script = True
            args_str = ' '.join(args_extra)
            from datetime import datetime
            ct = datetime.fromtimestamp(proc.info['create_time']).strftime('%H:%M:%S')
            mem = proc.memory_info().rss / (1024 * 1024)
            print(f"PID={pid:>6}  started={ct}  mem={mem:>7.0f}MB  {script:45s} {args_str}")
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
