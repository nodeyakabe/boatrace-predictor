#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
バックグラウンド処理の進捗を確認
"""
import sys

output_file = r"C:\Users\User\AppData\Local\Temp\claude\c--Users-User-Desktop-BR-BoatRace-package-20251115-172032\tasks\ba3f6cc.output"

try:
    with open(output_file, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()

    # 警告以外の行を抽出
    important_lines = []
    for line in lines:
        if any(keyword in line for keyword in [
            '月次処理', '対象レース', '月次完了', '成功', 'エラー',
            'データロード', '予測生成', 'CSV', '統計', '完了',
            '新スコア効果確認', '出力:', '期間:'
        ]):
            if 'UserWarning' not in line and 'warnings.warn' not in line and 'sklearn' not in line:
                important_lines.append(line.strip())

    print(f"総行数: {len(lines)}行")
    print(f"重要メッセージ数: {len(important_lines)}件\n")

    if important_lines:
        print("最新の進捗:")
        print("-" * 80)
        for line in important_lines[-30:]:  # 最新30件
            print(line)
    else:
        print("まだ実質的な進捗メッセージがありません（処理開始直後の可能性）")
        print("\n最初の100行（警告含む）:")
        print("-" * 80)
        for line in lines[:100]:
            print(line.strip())

except FileNotFoundError:
    print("出力ファイルがまだ作成されていません")
except Exception as e:
    print(f"エラー: {e}")
