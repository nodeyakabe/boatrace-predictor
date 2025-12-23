# 買い目システム改善 作業計画書 v2

**作成日**: 2025年12月7日
**更新日**: 2025年12月7日
**目標**: 期待値（EV）ベースの戦略エンジンへの段階的改善

---

## 0. 最重要方針：デグレ防止

### ⚠️ 現状の成績は高水準 - これを下回らないこと

| 指標 | 現状値 | 最低ライン |
|------|--------|-----------|
| 年間収支 | +92,020円 | +80,000円以上 |
| ROI | 122.9% | 115%以上 |
| 黒字月 | 7/11月 (63.6%) | 6/11月以上 |

### 改善の鉄則

```
1. A/Bテスト方式
   - 新旧ロジックを並行運用
   - 同一レースで両方の判定を記録
   - 1週間分の比較後に判断

2. 段階的導入
   - 1つの改善ポイントずつ適用
   - 効果検証してから次へ
   - 複数同時適用は禁止

3. 即時ロールバック
   - ROIが現状-5%以下 → 即座に元に戻す
   - バグ発見 → 即座に元に戻す
   - config.py の1行変更で切替可能にする

4. バージョン管理
   - 全ての買い目に logic_version を付与
   - v1.0: 現行MODERATE戦略（ベースライン）
   - v2.x: 各改善の適用版
```

---

## 1. 現状分析と改善マッピング

### 1.1 現状の強み（維持すべきもの）

| 要素 | 内容 | 備考 |
|------|------|------|
| 信頼度フィルター | C/Dのみ採用 | A/Bは不安定で除外済み |
| 級別フィルター | A1のみ採用 | A2以下は赤字 |
| オッズレンジ | 20-60倍 | 低オッズは期待値マイナス |
| 1点買い | 追加点は効率悪化 | 検証済み |

### 1.2 改善案との対応

| 改善ポイント | 現状 | 改善内容 | リスク |
|--------------|------|----------|--------|
| ① 状況別オッズレンジ | 固定20-60倍 | 場タイプ別に動的変更 | 中：過学習の恐れ |
| ② 簡易Kelly導入 | 100円固定 | 0.25Kelly × キャップ | 高：資金変動リスク |
| ③ Edge計算導入 | なし | 市場乖離度を数値化 | 低：追加情報のみ |
| ④ 動的資金配分 | 固定比率 | 3連単/2連単を日次調整 | 中：判断基準が曖昧 |
| ⑤ 買わない条件明文化 | 部分的 | 除外ルールを追加 | 低：保守的な変更 |

---

## 2. 改善の優先順位と実装順序

### 2.1 優先順位（リスク昇順）

```
【Phase A】低リスク改善（まず実施）
  ├─ ⑤ 買わない条件の明文化
  └─ ③ Edge計算の導入

【Phase B】中リスク改善（効果検証後）
  ├─ ① 状況別オッズレンジ
  └─ ④ 動的資金配分

【Phase C】高リスク改善（慎重に検討）
  └─ ② 簡易Kelly導入
```

### 2.2 各フェーズの判定基準

| フェーズ | 成功条件 | 失敗条件 | 期間 |
|----------|----------|----------|------|
| Phase A | ROI維持 or 向上 | ROI 5%以上低下 | 1週間 |
| Phase B | ROI 3%以上向上 | ROI低下 | 2週間 |
| Phase C | ROI 5%以上向上 | ROI低下 or DD増加 | 1ヶ月 |

---

## 3. 詳細設計

### 3.1 Phase A: 低リスク改善

#### ⑤ 買わない条件の明文化

```python
# filter_engine.py

class FilterEngine:
    """レース選別エンジン（除外ルール強化版）"""

    # 除外条件リスト
    EXCLUSION_RULES = [
        # 既存条件
        {'name': 'confidence', 'check': lambda r: r['confidence'] not in ['C', 'D']},
        {'name': 'c1_rank', 'check': lambda r: r['c1_rank'] not in ['A1']},
        {'name': 'odds_range', 'check': lambda r: not (20 <= r.get('odds', 0) <= 60)},

        # 新規追加条件
        {'name': 'wind_gap', 'check': lambda r: abs(r.get('wind_forecast', 0) - r.get('wind_actual', 0)) > 3},
        {'name': 'low_entry_conf', 'check': lambda r: r.get('entry_confidence', 1.0) < 0.6},
        {'name': 'no_edge', 'check': lambda r: abs(r.get('model_rank', 1) - r.get('odds_rank', 1)) < 2},
    ]

    def is_target_race(self, race_data: dict) -> tuple[bool, str]:
        """
        購入対象レースか判定

        Returns:
            (対象フラグ, 除外理由)
        """
        for rule in self.EXCLUSION_RULES:
            if rule['check'](race_data):
                return False, rule['name']
        return True, None
```

**検証方法**:
1. 既存条件のみでバックテスト → ベースラインROI確認
2. 新規条件を1つずつ追加 → ROI変化を記録
3. ROI向上する条件のみ採用

---

#### ③ Edge計算の導入

```python
# ev_calculator.py

class EVCalculator:
    """期待値計算エンジン（Edge対応版）"""

    def calc_edge(self, model_prob: float, market_prob: float) -> float:
        """
        市場とのズレ（Edge）を計算

        Edge = (モデル確率 / 市場確率) - 1
        正の値 = 市場が過小評価している（買い）
        負の値 = 市場が過大評価している（見送り）
        """
        if market_prob <= 0:
            return 0
        return (model_prob / market_prob) - 1

    def market_prob_from_odds(self, odds: float) -> float:
        """オッズから市場の想定確率を逆算"""
        if odds <= 0:
            return 0
        # 控除率25%を考慮
        return 0.75 / odds

    def calc_ev_with_edge(self, confidence: str, odds: float) -> dict:
        """EV + Edgeを計算"""
        model_prob = self.CONFIDENCE_HIT_RATES.get(confidence, {}).get('trifecta', 0.01)
        market_prob = self.market_prob_from_odds(odds)
        edge = self.calc_edge(model_prob, market_prob)
        ev = model_prob * odds

        return {
            'ev': ev,
            'edge': edge,
            'model_prob': model_prob,
            'market_prob': market_prob,
            'is_value_bet': edge > 0 and ev >= 1.0,
        }
```

**検証方法**:
1. 過去データでEdge値を算出
2. Edge > 0 のみ購入した場合のROIを検証
3. 最適なEdge閾値を探索

---

### 3.2 Phase B: 中リスク改善

#### ① 状況別オッズレンジ

```python
# config.py

# 場タイプ別オッズレンジ
VENUE_TYPE_ODDS_RANGES = {
    'high_in': {  # イン強場: 徳山, 大村, 下関等
        'venues': [18, 24, 19, 21, 20],
        'odds_range': (12, 35),
        'description': '1コース勝率60%以上',
    },
    'sashi': {  # 差し場: 平和島, 戸田, 江戸川等
        'venues': [4, 2, 3, 6],
        'odds_range': (25, 80),
        'description': '1コース勝率50%以下',
    },
    'rough': {  # 荒れ水面: 児島, 宮島等
        'venues': [17, 22],
        'odds_range': (40, 150),
        'description': '波乱傾向',
    },
    'nighter': {  # ナイター: 蒲郡, 住之江等
        'venues': [7, 12],
        'odds_range': (20, 70),
        'description': 'ナイター開催',
    },
    'default': {  # その他
        'venues': [],
        'odds_range': (20, 60),
        'description': '標準',
    },
}

def get_odds_range(venue_code: int) -> tuple:
    """会場コードから最適オッズレンジを取得"""
    for vtype, config in VENUE_TYPE_ODDS_RANGES.items():
        if venue_code in config['venues']:
            return config['odds_range']
    return VENUE_TYPE_ODDS_RANGES['default']['odds_range']
```

**検証方法**:
1. 各場タイプ別にバックテスト実施
2. 場タイプごとの最適レンジを確認
3. 全体ROIが現状を上回るか検証
4. **上回らなければ採用しない**

---

#### ④ 動的資金配分（3連単/2連単）

```python
# bet_selector.py

class DynamicAllocator:
    """動的資金配分"""

    # 基本配分
    BASE_RATIO = {'trifecta': 0.7, 'exacta': 0.3}

    def calc_allocation(self, race_context: dict) -> dict:
        """
        レースコンテキストから配分を決定

        Args:
            race_context: {
                'confidence': 'D',
                'edge': 0.15,
                'is_upset_likely': False,
            }
        """
        # Edge高い日: 3連単に寄せる
        if race_context.get('edge', 0) > 0.2:
            return {'trifecta': 0.9, 'exacta': 0.1}

        # 荒れそうな日: 2連単に寄せる
        if race_context.get('is_upset_likely', False):
            return {'trifecta': 0.5, 'exacta': 0.5}

        # 通常
        return self.BASE_RATIO
```

**検証方法**:
1. 固定配分（70/30）でのROIを確認
2. 動的配分でのROIを確認
3. 差異が+3%以上なら採用

---

### 3.3 Phase C: 高リスク改善

#### ② 簡易Kelly導入

```python
# kelly_calculator.py

class SimpleKelly:
    """簡易Kelly基準（0.25Kelly + キャップ）"""

    FRACTION = 0.25  # フルKellyの1/4
    MAX_BET_RATIO = 0.05  # 資金の5%上限
    MIN_EDGE = 0.05  # Edge 5%未満は賭けない

    def calc_bet_amount(self, bankroll: int, edge: float, odds: float) -> int:
        """
        賭け金を計算

        Kelly公式: f* = (bp - q) / b
        b = オッズ - 1
        p = 勝率
        q = 1 - p
        """
        if edge < self.MIN_EDGE:
            return 0

        # 勝率を推定
        p = 0.75 / odds + edge  # 市場確率 + Edge
        q = 1 - p
        b = odds - 1

        if b <= 0:
            return 0

        # Kelly計算
        kelly_fraction = (b * p - q) / b
        if kelly_fraction <= 0:
            return 0

        # 0.25 Kelly + キャップ
        bet_ratio = min(kelly_fraction * self.FRACTION, self.MAX_BET_RATIO)
        bet_amount = int(bankroll * bet_ratio)

        # 100円単位に丸め
        return max(100, (bet_amount // 100) * 100)
```

**検証方法**:
1. 過去1年分のシミュレーション
2. 資金曲線の推移を確認
3. 最大ドローダウンを確認
4. 現状の固定100円と比較
5. **ドローダウンが大きければ採用しない**

---

## 4. 新アーキテクチャ

```
src/betting/
├── __init__.py
├── strategy_engine.py      # 全体制御
├── ev_calculator.py        # 期待値 + Edge計算
├── filter_engine.py        # 除外条件（強化版）
├── bet_selector.py         # 買い目選択 + 動的配分
├── kelly_calculator.py     # 簡易Kelly（Phase C）
├── bet_logger.py           # ログ管理
├── config.py               # 設定一元化（場タイプ別等）
│
├── legacy/                 # 旧ロジック保管（必須）
│   ├── bet_target_evaluator_v1.py
│   └── README.md           # ロールバック手順
│
└── tests/                  # テスト
    ├── test_ev_calculator.py
    ├── test_filter_engine.py
    └── test_backtest.py
```

---

## 5. ロールバック設計

### 5.1 切替スイッチ

```python
# config.py

# ロジックバージョン切替
LOGIC_VERSION = 'v2.0'  # 'v1.0' に変更で旧ロジックに戻る

# 個別機能のON/OFF
FEATURES = {
    'use_edge_filter': True,      # Edge計算（③）
    'use_exclusion_rules': True,  # 除外条件強化（⑤）
    'use_venue_odds': False,      # 場タイプ別レンジ（①）
    'use_dynamic_alloc': False,   # 動的配分（④）
    'use_kelly': False,           # Kelly基準（②）
}
```

### 5.2 ロールバック手順

```bash
# 1. config.py を編集
LOGIC_VERSION = 'v1.0'

# または個別機能をOFF
FEATURES['use_edge_filter'] = False

# 2. 再起動
# アプリケーションを再起動すれば即座に反映
```

---

## 6. スケジュール

### Phase A: 低リスク改善（Week 1）

| 日 | タスク | 成果物 | 判定 |
|----|--------|--------|------|
| Day 1 | 旧ロジックをlegacyに保管 | legacy/フォルダ | - |
| Day 2 | filter_engine.py（除外条件） | 除外ルール実装 | - |
| Day 3 | ev_calculator.py（Edge計算） | Edge関数 | - |
| Day 4 | バックテスト（⑤除外条件） | ROI比較 | ROI維持? |
| Day 5 | バックテスト（③Edge） | ROI比較 | ROI維持? |
| Day 6-7 | 並行運用開始 | ログ収集 | - |

### Phase B: 中リスク改善（Week 2-3）

| 日 | タスク | 成果物 | 判定 |
|----|--------|--------|------|
| Day 8-9 | config.py（場タイプ別） | 設定ファイル | - |
| Day 10-11 | バックテスト（①場タイプ） | ROI比較 | +3%以上? |
| Day 12-13 | bet_selector.py（動的配分） | 配分ロジック | - |
| Day 14 | バックテスト（④動的配分） | ROI比較 | +3%以上? |

### Phase C: 高リスク改善（Week 4）

| 日 | タスク | 成果物 | 判定 |
|----|--------|--------|------|
| Day 15-16 | kelly_calculator.py | Kelly実装 | - |
| Day 17-20 | シミュレーション | 資金曲線 | DD許容範囲? |
| Day 21 | 最終判断 | 採用/不採用 | - |

---

## 7. 成功基準

### 各フェーズの判定

| フェーズ | 成功 | 失敗（ロールバック） |
|----------|------|---------------------|
| Phase A | ROI 120%以上維持 | ROI 115%未満 |
| Phase B | ROI 125%以上達成 | ROI 120%未満 |
| Phase C | ROI 130%以上 + DD 50%以下 | それ以外 |

### 最終目標

| 指標 | 現状 | 目標 | 最低ライン |
|------|------|------|-----------|
| 年間ROI | 122.9% | 135% | 115% |
| 黒字月 | 63.6% | 75% | 55% |
| 月間的中 | 2.9件 | 5件 | 2件 |
| 最大DD | 不明 | 30%以下 | 50%以下 |

---

## 8. 参考資料

- [betting_strategy_complete_analysis.md](betting_strategy_complete_analysis.md) - 過去の検証結果
- [改善案_20251207.txt](../改善点/改善案_20251207.txt) - 元の改善案

---

*作成者: Claude Code*
*最終更新: 2025年12月7日*
