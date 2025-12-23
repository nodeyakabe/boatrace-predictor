#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
知見インデックス検索ツール
==========================

過去の施策・失敗事例・落とし穴を検索し、重複作業を防止する。

使用例:
    python scripts/search_knowledge.py "オッズ"
    python scripts/search_knowledge.py "2着"
    python scripts/search_knowledge.py "検証が遅い"
"""

import json
import sys
import io
from pathlib import Path
from typing import List, Dict, Any

# Windows環境でのUnicode出力対応
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def load_knowledge_index() -> Dict[str, Any]:
    """知見インデックスを読み込み"""
    index_path = Path(__file__).parent.parent / "knowledge_index.json"

    if not index_path.exists():
        print(f"[ERROR] 知見インデックスが見つかりません: {index_path}")
        sys.exit(1)

    with open(index_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def search_experiments(index: Dict, keyword: str) -> List[Dict]:
    """施策を検索"""
    results = []
    keyword_lower = keyword.lower()

    for exp in index.get("experiments", []):
        # キーワード、名前、カテゴリで検索
        if (any(keyword_lower in kw.lower() for kw in exp.get("keywords", [])) or
            keyword_lower in exp.get("name", "").lower() or
            keyword_lower in exp.get("category", "").lower()):
            results.append({
                "type": "experiment",
                "data": exp
            })

    return results


def search_pitfalls(index: Dict, keyword: str) -> List[Dict]:
    """既知の落とし穴を検索"""
    results = []
    keyword_lower = keyword.lower()

    for pitfall in index.get("known_pitfalls", []):
        # 名前、症状、原因、解決策で検索
        if (keyword_lower in pitfall.get("name", "").lower() or
            keyword_lower in pitfall.get("symptom", "").lower() or
            keyword_lower in pitfall.get("root_cause", "").lower() or
            keyword_lower in pitfall.get("solution", "").lower()):
            results.append({
                "type": "pitfall",
                "data": pitfall
            })

    return results


def search_features(index: Dict, keyword: str) -> List[Dict]:
    """実装済み機能を検索"""
    results = []
    keyword_lower = keyword.lower()

    for feature in index.get("implemented_features", []):
        if (keyword_lower in feature.get("name", "").lower() or
            keyword_lower in feature.get("flag_name", "").lower()):
            results.append({
                "type": "feature",
                "data": feature
            })

    return results


def display_results(results: List[Dict], keyword: str):
    """検索結果を表示"""

    if not results:
        print(f"\n[INFO] '{keyword}' に関連する知見は見つかりませんでした。")
        print("\n✅ 新規施策として検討可能です。")
        print("\n【推奨アクション】")
        print("1. 類似の施策がないか、別のキーワードでも検索")
        print("2. 実装前にCLAUDE.mdの確認事項を実施")
        print("3. 検証後は必ず knowledge_index.json に登録")
        return

    print(f"\n{'='*80}")
    print(f"⚠️  '{keyword}' に関連する知見が {len(results)} 件見つかりました")
    print(f"{'='*80}\n")

    # 実験結果
    experiments = [r for r in results if r["type"] == "experiment"]
    if experiments:
        print("【過去の実験結果】\n")
        for r in experiments:
            exp = r["data"]
            result_icon = "❌" if exp["result"] == "rejected" else "✅"

            print(f"{result_icon} {exp['name']}")
            print(f"   ID: {exp['id']}")
            print(f"   カテゴリ: {exp['category']}")
            print(f"   実施日: {exp['date_tested']}")
            print(f"   結果: {exp['result']}")

            # 効果
            if "effect_2024" in exp:
                print(f"   効果（2024年）: {exp['effect_2024']}")
                print(f"   効果（2025年）: {exp.get('effect_2025', '未測定')}")
            elif "effect" in exp:
                print(f"   効果: {exp['effect']}")

            if exp.get("rejection_reason"):
                print(f"   不採用理由: {exp['rejection_reason']}")

            if exp.get("lesson"):
                print(f"   教訓: {exp['lesson']}")

            if exp.get("doc_reference"):
                print(f"   詳細: {exp['doc_reference']}")

            print()

    # 既知の落とし穴
    pitfalls = [r for r in results if r["type"] == "pitfall"]
    if pitfalls:
        print("【既知の落とし穴】\n")
        for r in pitfalls:
            p = r["data"]
            print(f"⚠️  {p['name']}")
            print(f"   症状: {p.get('symptom', 'N/A')}")
            print(f"   原因: {p.get('root_cause', 'N/A')}")
            print(f"   解決策: {p.get('solution', 'N/A')}")

            if p.get("performance_improvement"):
                print(f"   改善効果: {p['performance_improvement']}")

            if p.get("occurrence_count", 0) > 1:
                print(f"   ⚠️ 発生回数: {p['occurrence_count']}回（頻出問題）")

            if p.get("related_files"):
                print(f"   関連ファイル: {', '.join(p['related_files'][:2])}")

            print()

    # 実装済み機能
    features = [r for r in results if r["type"] == "feature"]
    if features:
        print("【実装済み機能】\n")
        for r in features:
            f = r["data"]
            status_icon = "🟢" if f["status"] == "enabled" else "🔴"

            print(f"{status_icon} {f['name']}")
            print(f"   フラグ名: {f['flag_name']}")
            print(f"   状態: {f['status']}")
            if f.get("effect"):
                print(f"   効果: {f['effect']}")
            print()

    # 推奨アクション
    print(f"{'='*80}")
    print("【推奨アクション】")
    print(f"{'='*80}\n")

    if any(exp["data"]["result"] == "rejected" for exp in experiments):
        print("⚠️  類似施策が過去に不採用となっています。\n")
        print("再検討する場合は、以下の点に注意してください：")
        for exp in experiments:
            if exp["data"]["result"] == "rejected":
                print(f"\n• {exp['data']['name']}")
                if exp['data'].get("rejection_reason"):
                    print(f"  - 不採用理由: {exp['data']['rejection_reason']}")
                if exp['data'].get("lesson"):
                    print(f"  - 教訓: {exp['data']['lesson']}")
    else:
        print("✅ 類似施策は採用済みまたは未実施です。")
        print("\n新規施策の場合は、以下を確認：")
        print("1. CLAUDE.mdのセッション開始時確認事項を実施")
        print("2. 検証テンプレート（scripts/templates/verification_template.py）を使用")
        print("3. 最低100レースで検証、2024年と2025年の両データで確認")


def main():
    """メイン処理"""

    if len(sys.argv) < 2:
        print("使用法: python scripts/search_knowledge.py <検索キーワード>")
        print("\n例:")
        print("  python scripts/search_knowledge.py オッズ")
        print("  python scripts/search_knowledge.py 2着")
        print("  python scripts/search_knowledge.py '検証が遅い'")
        sys.exit(1)

    keyword = sys.argv[1]

    # 知見インデックスを読み込み
    index = load_knowledge_index()

    # 検索実行
    results = []
    results.extend(search_experiments(index, keyword))
    results.extend(search_pitfalls(index, keyword))
    results.extend(search_features(index, keyword))

    # 結果表示
    display_results(results, keyword)


if __name__ == "__main__":
    main()
