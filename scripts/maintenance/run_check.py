#!/usr/bin/env python
# -*- coding: utf-8 -*-
import subprocess
import sys

result = subprocess.run([sys.executable, 'check_nov_dec_simple.py'],
                       capture_output=True, text=True, timeout=30)
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr, file=sys.stderr)
print("Return code:", result.returncode)
