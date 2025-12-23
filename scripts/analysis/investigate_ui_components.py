#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
UIコンポーネント調査スクリプト

ui/componentsフォルダ内のファイルを調査し、使用状況と重複を確認
"""
import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import glob
import re
from pathlib import Path
from typing import Dict, List, Set


def get_ui_components():
    """UIコンポーネント一覧を取得"""
    ui_path = Path('ui/components')

    # commonフォルダを除く
    components = []
    for py_file in ui_path.glob('*.py'):
        if py_file.name != '__init__.py':
            components.append(py_file)

    return sorted(components)


def analyze_component(filepath: Path) -> Dict:
    """コンポーネントファイルを分析"""
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    # 行数
    lines = content.split('\n')
    total_lines = len(lines)
    code_lines = len([l for l in lines if l.strip() and not l.strip().startswith('#')])

    # 関数定義を検索
    functions = re.findall(r'^def\s+(\w+)\s*\(', content, re.MULTILINE)

    # Streamlit関数の使用
    st_calls = len(re.findall(r'\bst\.', content))

    # インポート文
    imports = re.findall(r'^(?:from|import)\s+(.+)', content, re.MULTILINE)

    return {
        'filepath': filepath,
        'filename': filepath.name,
        'total_lines': total_lines,
        'code_lines': code_lines,
        'functions': functions,
        'function_count': len(functions),
        'st_calls': st_calls,
        'imports': imports,
    }


def find_usage_in_main(component_name: str) -> List[str]:
    """main.pyでの使用箇所を検索"""
    main_file = Path('main.py')

    if not main_file.exists():
        return []

    with open(main_file, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    # インポート文を検索
    import_pattern = rf'from\s+ui\.components\.{component_name[:-3]}\s+import'
    imports = re.findall(import_pattern, content)

    # 関数呼び出しを検索（推定）
    module_name = component_name[:-3]
    usage_lines = []

    for i, line in enumerate(content.split('\n'), 1):
        if module_name in line or any(word in line for word in ['render_', 'show_', 'display_']):
            usage_lines.append(f"L{i}: {line.strip()[:60]}")

    return usage_lines[:5]  # 最初の5件のみ


def find_references(component_name: str) -> int:
    """プロジェクト全体での参照回数を検索"""
    module_name = component_name[:-3]

    count = 0
    for pattern in ['**/*.py']:
        for filepath in glob.glob(pattern, recursive=True):
            if 'venv' in filepath or '__pycache__' in filepath:
                continue

            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    count += content.count(module_name)
            except:
                pass

    return count


def categorize_components(components_info: List[Dict]) -> Dict[str, List[str]]:
    """コンポーネントをカテゴリ分け"""
    categories = {
        'data_prep': [],
        'prediction': [],
        'analysis': [],
        'training': [],
        'monitoring': [],
        'betting': [],
        'other': []
    }

    for info in components_info:
        name = info['filename'].lower()

        if any(word in name for word in ['data', 'scraper', 'fetch', 'collect']):
            categories['data_prep'].append(info['filename'])
        elif any(word in name for word in ['predict', 'forecast']):
            categories['prediction'].append(info['filename'])
        elif any(word in name for word in ['analysis', 'analyzer', 'backtest']):
            categories['analysis'].append(info['filename'])
        elif any(word in name for word in ['train', 'model', 'learning']):
            categories['training'].append(info['filename'])
        elif any(word in name for word in ['monitor', 'dashboard', 'quality']):
            categories['monitoring'].append(info['filename'])
        elif any(word in name for word in ['bet', 'betting', 'recommendation']):
            categories['betting'].append(info['filename'])
        else:
            categories['other'].append(info['filename'])

    return categories


def main():
    print("="*70)
    print("UIコンポーネント調査")
    print("="*70)

    components = get_ui_components()
    print(f"\n総コンポーネント数: {len(components)}ファイル\n")

    # 各コンポーネントを分析
    components_info = []
    for comp in components:
        info = analyze_component(comp)
        components_info.append(info)

    # カテゴリ分け
    categories = categorize_components(components_info)

    print("\n【カテゴリ別分類】")
    for cat_name, files in categories.items():
        if files:
            print(f"\n{cat_name.upper()} ({len(files)}件):")
            for f in files:
                print(f"  - {f}")

    # 詳細情報
    print("\n" + "="*70)
    print("【詳細情報】")
    print("="*70)

    for info in sorted(components_info, key=lambda x: x['code_lines'], reverse=True):
        print(f"\n📄 {info['filename']}")
        print(f"   コード行数: {info['code_lines']:,}行 (総行数: {info['total_lines']:,})")
        print(f"   関数数: {info['function_count']}個")
        print(f"   Streamlit呼び出し: {info['st_calls']}回")

        # main.pyでの使用
        usage = find_usage_in_main(info['filename'])
        if usage:
            print(f"   main.py使用: あり")
        else:
            print(f"   main.py使用: なし")

        # 主要な関数
        if info['functions']:
            print(f"   主要関数: {', '.join(info['functions'][:3])}")
            if len(info['functions']) > 3:
                print(f"              ... 他 {len(info['functions']) - 3}個")

    # サマリー
    print("\n" + "="*70)
    print("【サマリー】")
    print("="*70)

    total_code_lines = sum(info['code_lines'] for info in components_info)
    print(f"\n総コード行数: {total_code_lines:,}行")
    print(f"平均コード行数: {total_code_lines // len(components_info):,}行/ファイル")

    # 大きいファイル TOP5
    print("\n【大きいファイル TOP5】")
    for i, info in enumerate(sorted(components_info, key=lambda x: x['code_lines'], reverse=True)[:5], 1):
        print(f"  {i}. {info['filename']:40s} {info['code_lines']:,}行")

    # 小さいファイル（使用されていない可能性）
    print("\n【小さいファイル（100行未満）】")
    small_files = [info for info in components_info if info['code_lines'] < 100]
    for info in sorted(small_files, key=lambda x: x['code_lines']):
        print(f"  - {info['filename']:40s} {info['code_lines']:,}行")

    print("\n" + "="*70)
    print("調査完了")
    print("="*70)


if __name__ == "__main__":
    main()
