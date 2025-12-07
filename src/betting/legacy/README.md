# Legacy モジュール

このフォルダには旧バージョンのロジックを保管しています。

## ロールバック手順

ROIが115%未満に低下した場合、以下の手順で旧ロジックに戻せます：

### 方法1: config.py でバージョン切替

```python
# src/betting/config.py
LOGIC_VERSION = 'v1.0'  # 'v2.0' から変更
```

### 方法2: 個別機能のOFF

```python
# src/betting/config.py
FEATURES = {
    'use_edge_filter': False,      # Edge計算
    'use_exclusion_rules': False,  # 除外条件強化
    'use_venue_odds': False,       # 場タイプ別レンジ
    'use_dynamic_alloc': False,    # 動的配分
    'use_kelly': False,            # Kelly基準
}
```

## 保管ファイル

| ファイル | 内容 | バージョン |
|---------|------|-----------|
| bet_target_evaluator_v1.py | MODERATE戦略実装 | v1.0 |

## バージョン履歴

- v1.0: MODERATE戦略 (2025-12-07)
  - 年間ROI: 122.9%
  - 黒字月: 7/11ヶ月 (63.6%)
  - 条件: C/D × A1 × 20-60倍
