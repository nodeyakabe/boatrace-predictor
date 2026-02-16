"""config/bet_conditions.py に優先度を追加する一括修正スクリプト

Phase 0: 条件優先度の明示化
"""
import re

def main():
    file_path = 'config/bet_conditions.py'

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 各条件の 'id' フィールドを見つけて、その直後に 'priority' を挿入
    # パターン: 'id': 'XXX',\n        'name':

    # 条件IDとその優先度のマッピング
    condition_priorities = [
        ('A_A1_10_12', 1),
        ('B_50_100', 2),
        ('B_30_50_B1', 3),
        ('B_10_30_bias', 4),
        ('C_20_30_B1', 5),
        ('C_Naruto_A2', 6),
        ('C_Karatsu_B1', 7),
        ('C_Kojima_B1', 8),
        ('D_40_50_B1', 9),
        ('D_course5', 10),
    ]

    for cond_id, priority in condition_priorities:
        # パターン: 'id': 'A_A1_10_12',\n        'name':
        # 置換: 'id': 'A_A1_10_12',\n        'priority': 1,\n        'name':
        pattern = rf"('id': '{cond_id}',)\n(\s+)('name':)"
        replacement = rf"\1\n\2'priority': {priority},\n\2\3"
        content = re.sub(pattern, replacement, content)

    # STANDARD_BET_CONDITIONS の前のコメントを更新
    content = content.replace(
        '# 11条件の定義（2026-02-13現在）',
        '# 10条件の定義（2026-02-16更新：優先度追加）'
    )

    # コメントブロックを追加
    comment_insertion_point = "STANDARD_BET_CONDITIONS = ["
    priority_comment = """
# ============================================================
# 重複レース時の優先度
# ============================================================
# 重複レースの場合、優先度の高い条件（小さい数値）を優先
# 例: 同じレースがD×40-50×B1(priority=9)とD×5コース(priority=10)に
#     該当する場合、D×40-50×B1が優先される

"""

    content = content.replace(
        comment_insertion_point,
        priority_comment + comment_insertion_point
    )

    # バージョン情報を更新
    content = content.replace(
        'CONDITION_VERSION = "v2.1.0"',
        'CONDITION_VERSION = "v2.2.0"'
    )
    content = content.replace(
        'LAST_UPDATED = "2026-02-13"',
        'LAST_UPDATED = "2026-02-16"'
    )
    content = content.replace(
        'Version: v2.1.0',
        'Version: v2.2.0'
    )
    content = content.replace(
        'Last Updated: 2026-02-13',
        'Last Updated: 2026-02-16'
    )

    # ファイルを書き込み
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print("[OK] Priority added successfully")
    print("\nAdded priorities:")
    for cond_id, priority in condition_priorities:
        print(f"  {priority}. {cond_id}")
    print("\nUpdates:")
    print("  - Version: v2.1.0 -> v2.2.0")
    print("  - Date: 2026-02-13 -> 2026-02-16")
    print("  - Priority comment block added")

if __name__ == '__main__':
    main()
