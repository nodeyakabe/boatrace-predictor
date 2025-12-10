# ハイブリッド予測システム 実装ガイド

**最終更新**: 2025-11-14
**対象**: 実験#001-#022の成果統合

---

## 📋 目次

1. [概要](#概要)
2. [クイックスタート](#クイックスタート)
3. [システム構成](#システム構成)
4. [API リファレンス](#apiリファレンス)
5. [使用例](#使用例)
6. [実戦運用](#実戦運用)
7. [トラブルシューティング](#トラブルシューティング)

---

## 概要

### システムの特徴

本システムは、22回の実験成果を統合した実戦的な予測システムです。

**主要機能**:
1. **ハイブリッド予測**: 会場ごとに最適なモデルを自動選択
2. **オッズ期待値戦略**: 3つの実戦戦略（保守的、バランス、穴狙い）
3. **リスク管理**: ケリー基準に基づく賭け金推奨
4. **複勝予測**: 高的中率（92.22%）の安定戦略

### 主要コンポーネント

```
BoatRace/
├── hybrid_predictor.py          # ハイブリッド予測システム
├── betting_strategy.py          # 賭け戦略システム
├── models/
│   ├── stage2_optimized.json    # 統合モデル（AUC 0.8496）
│   └── stage2_venue_*.json      # 会場別モデル（24会場）
└── EXPERIMENTS_FINAL_REPORT.md  # 全実験結果レポート
```

---

## クイックスタート

### 5分で始める

```python
# 1. 必要なモジュールをインポート
from hybrid_predictor import HybridPredictor
from betting_strategy import BettingRecommender, BettingStrategy
import pandas as pd
import numpy as np

# 2. ハイブリッド予測システムの初期化
predictor = HybridPredictor()
predictor.load_models()  # 統合モデルをロード

# 3. 賭け戦略システムの初期化（総資金10万円）
recommender = BettingRecommender(bankroll=100000)

# 4. 予測実行（会場07、35次元の特徴量データを用意）
# X = prepare_features(race_data)  # 実際のデータ準備関数
# result = predictor.predict_with_info(X, venue_code='07')

# 5. 賭け推奨取得
# odds = get_odds()  # オッズ取得
# recommendation = recommender.get_recommendation(
#     win_probability=result['probabilities'][0],
#     odds=odds[0],
#     pit_number=1
# )

print("✅ システム初期化完了！")
```

---

## システム構成

### 1. ハイブリッド予測システム (`hybrid_predictor.py`)

#### クラス: `HybridPredictor`

**目的**: 会場ごとに最適なモデルを自動選択して予測

**主要メソッド**:

```python
class HybridPredictor:
    def load_models(preload_all=False):
        """モデルをロード"""
        pass

    def get_best_model_for_venue(venue_code):
        """会場に応じた最適モデルを取得"""
        pass

    def predict(X, venue_code):
        """予測実行（確率を返す）"""
        pass

    def predict_with_info(X, venue_code):
        """詳細情報付きで予測実行"""
        pass

    def get_venue_info(venue_code):
        """会場情報を取得"""
        pass
```

#### 会場別モデル選択ルール

**会場特化モデル使用（9会場）**:
- 会場07: AUC 0.9341（+0.0845）⭐ 最優先
- 会場11: AUC 0.9173（+0.0677）⭐
- 会場18: AUC 0.8989（+0.0493）⭐
- 会場21: AUC 0.8746（+0.0250）
- 会場08: AUC 0.8715（+0.0219）
- 会場09: AUC 0.8679（+0.0183）
- 会場13: AUC 0.8570（+0.0074）
- 会場24: AUC 0.8604（+0.0108）
- 会場05: AUC 0.8512（+0.0016）

**統合モデル使用（15会場）**:
- その他の会場: AUC 0.8496

### 2. 賭け戦略システム (`betting_strategy.py`)

#### クラス: `BettingRecommender`

**目的**: オッズ期待値分析に基づく実戦的な賭け推奨

**3つの戦略**:

| 戦略 | 条件 | 的中率 | ROI | 対象レース/月 |
|------|------|--------|-----|--------------|
| **保守的** | 確率≥0.8 & EV>0 | 85.71% | 47.10% | 42 |
| **バランス** | EV≥+10% | 25.02% | 45.35% | 2,350 |
| **穴狙い** | 確率≥0.3 & EV≥+20% | 60.46% | 46.63% | 521 |

**主要メソッド**:

```python
class BettingRecommender:
    def __init__(bankroll=100000):
        """初期化"""
        pass

    def calculate_expected_value(win_probability, odds):
        """期待値計算"""
        pass

    def should_bet(win_probability, odds, strategy):
        """賭けるべきか判定"""
        pass

    def calculate_kelly_bet(win_probability, odds, fraction=0.25):
        """ケリー基準推奨額計算"""
        pass

    def get_recommendation(win_probability, odds, pit_number):
        """包括的な賭け推奨"""
        pass

    def analyze_race(probabilities, odds_list):
        """レース全体を分析"""
        pass
```

---

## API リファレンス

### HybridPredictor API

#### `__init__()`

```python
predictor = HybridPredictor()
```

初期化。モデルの辞書を準備。

#### `load_models(preload_all=False)`

```python
predictor.load_models(preload_all=False)
```

**引数**:
- `preload_all` (bool): Trueの場合、全モデルを事前ロード（メモリ使用大）

**戻り値**: None

**例**:
```python
# 統合モデルのみロード（推奨）
predictor.load_models()

# 全モデルを事前ロード
predictor.load_models(preload_all=True)
```

#### `predict_with_info(X, venue_code)`

```python
result = predictor.predict_with_info(X, venue_code='07')
```

**引数**:
- `X` (pd.DataFrame): 特徴量データ（35次元 × N艇）
- `venue_code` (str): 会場コード（'01'〜'24'）

**戻り値** (dict):
```python
{
    'probabilities': np.ndarray,      # 勝利確率配列
    'model_type': str,                # 'venue_07' or 'unified'
    'expected_auc': float,            # 期待AUC
    'venue_code': str,                # '07'
    'is_venue_specific': bool         # True/False
}
```

**例**:
```python
result = predictor.predict_with_info(X, venue_code='07')
print(f"使用モデル: {result['model_type']}")
print(f"期待AUC: {result['expected_auc']:.4f}")
print(f"1号艇勝利確率: {result['probabilities'][0]:.2%}")
```

#### `get_venue_info(venue_code)`

```python
info = predictor.get_venue_info('07')
```

**引数**:
- `venue_code` (str): 会場コード

**戻り値** (dict):
```python
{
    'venue_code': str,
    'auc': float,
    'delta': float,              # 統合モデルとの差
    'model': str,                # モデルファイルパス
    'recommendation': str,        # 推奨メッセージ
    'is_superior': bool          # 会場特化が優秀か
}
```

### BettingRecommender API

#### `__init__(bankroll=100000)`

```python
recommender = BettingRecommender(bankroll=100000)
```

**引数**:
- `bankroll` (float): 総資金（円）

#### `get_recommendation(win_probability, odds, pit_number, race_info=None)`

```python
rec = recommender.get_recommendation(
    win_probability=0.85,
    odds=1.5,
    pit_number=1
)
```

**引数**:
- `win_probability` (float): 勝利確率（0-1）
- `odds` (float): オッズ（倍率）
- `pit_number` (int): 艇番（1-6）
- `race_info` (dict, optional): レース情報

**戻り値** (dict):
```python
{
    'pit_number': int,
    'win_probability': float,
    'odds': float,
    'expected_value': float,          # 期待値
    'expected_value_pct': float,      # 期待値（%）
    'kelly_bet_amount': float,        # ケリー推奨額（円）
    'kelly_fraction': float,          # ケリー係数
    'max_bet_limit': float,           # 最大賭け金
    'recommendations': dict,          # 戦略別推奨
    'overall_recommendation': str,    # '賭け推奨' or '見送り'
    'confidence_level': str           # 信頼度レベル
}
```

#### `analyze_race(probabilities, odds_list, race_info=None)`

```python
df = recommender.analyze_race(
    probabilities=np.array([0.85, 0.45, 0.25, 0.15, 0.10, 0.05]),
    odds_list=np.array([1.5, 3.2, 5.8, 12.5, 18.0, 35.0])
)
```

**引数**:
- `probabilities` (np.ndarray): 各艇の勝利確率（6要素）
- `odds_list` (np.ndarray): 各艇のオッズ（6要素）
- `race_info` (dict, optional): レース情報

**戻り値**: pd.DataFrame（レース全体の分析結果）

---

## 使用例

### 例1: 基本的な予測と賭け推奨

```python
from hybrid_predictor import HybridPredictor
from betting_strategy import BettingRecommender
import pandas as pd
import numpy as np

# 初期化
predictor = HybridPredictor()
predictor.load_models()
recommender = BettingRecommender(bankroll=100000)

# 特徴量データ準備（実際にはDBから取得など）
# X = prepare_features_from_database(race_id)
# ここではダミーデータ
X = pd.DataFrame(np.random.randn(6, 35))  # 6艇 × 35特徴量

# 予測実行（会場07）
result = predictor.predict_with_info(X, venue_code='07')

print(f"会場07の予測:")
print(f"  使用モデル: {result['model_type']}")
print(f"  期待AUC: {result['expected_auc']:.4f}")
print(f"  予測確率:")
for i, prob in enumerate(result['probabilities'], 1):
    print(f"    {i}号艇: {prob:.2%}")

# オッズ取得（実際にはAPIから取得）
odds_list = np.array([1.5, 3.2, 5.8, 12.5, 18.0, 35.0])

# レース全体の分析
analysis = recommender.analyze_race(
    probabilities=result['probabilities'],
    odds_list=odds_list
)

print("\nレース分析:")
print(analysis)

# 1号艇の詳細推奨
rec = recommender.get_recommendation(
    win_probability=result['probabilities'][0],
    odds=odds_list[0],
    pit_number=1
)

print(f"\n1号艇の推奨:")
print(f"  期待値: {rec['expected_value_pct']:+.1f}%")
print(f"  ケリー推奨額: {rec['kelly_bet_amount']:.0f}円")
print(f"  総合推奨: {rec['overall_recommendation']}")
```

### 例2: 会場ごとの最適戦略

```python
# 会場情報を一覧表示
venues = ['07', '11', '18', '01', '14']

print("会場別最適モデル:")
for venue in venues:
    info = predictor.get_venue_info(venue)
    print(f"\n会場{venue}:")
    print(f"  {info['recommendation']}")
    print(f"  期待AUC: {info['auc']:.4f}")
    if info['is_superior']:
        print(f"  統合モデル比: {info['delta']:+.4f} （{info['delta']/0.8496*100:+.1f}%）")
```

### 例3: 戦略別シミュレーション

```python
from betting_strategy import BettingStrategy

# 3つの戦略で比較
strategies = [
    BettingStrategy.CONSERVATIVE,
    BettingStrategy.BALANCED,
    BettingStrategy.VALUE
]

win_probability = 0.65
odds = 2.5

print(f"勝利確率: {win_probability:.0%}, オッズ: {odds:.2f}")
print("\n戦略別推奨:")

for strategy in strategies:
    should_bet = recommender.should_bet(win_probability, odds, strategy)
    params = recommender.STRATEGY_PARAMS[strategy]

    print(f"\n{params['name']}:")
    print(f"  推奨: {'✅ ベット' if should_bet else '❌ 見送り'}")
    print(f"  期待的中率: {params['expected_hit_rate']:.2%}")
    print(f"  期待ROI: {params['expected_roi']:.2%}")
```

---

## 実戦運用

### ステップ1: システム初期化

```python
# main.py
from hybrid_predictor import HybridPredictor
from betting_strategy import BettingRecommender

# グローバルインスタンス
predictor = HybridPredictor()
predictor.load_models()

# 資金管理（必ず実際の資金額を設定）
recommender = BettingRecommender(bankroll=100000)

print("✅ システム初期化完了")
predictor.print_model_info()
recommender.print_strategy_info()
```

### ステップ2: データ取得と準備

```python
def prepare_race_features(race_data):
    """
    レースデータから特徴量を準備

    Args:
        race_data: レース生データ

    Returns:
        pd.DataFrame: 35次元の特徴量（6艇分）
    """
    # 実際の実装では、DBから取得したデータを処理
    # ここでは必要な35特徴量を準備
    features = pd.DataFrame({
        'actual_course': ...,
        'actual_course_1': ...,
        # ... 35特徴量すべて
        'wind_speed': ...
    })

    return features
```

### ステップ3: 予測と推奨

```python
def predict_and_recommend(race_id, venue_code):
    """
    予測と賭け推奨を一括実行

    Args:
        race_id: レースID
        venue_code: 会場コード

    Returns:
        dict: 予測と推奨の結果
    """
    # 1. データ取得
    race_data = get_race_data(race_id)
    X = prepare_race_features(race_data)

    # 2. 予測実行
    pred_result = predictor.predict_with_info(X, venue_code)

    # 3. オッズ取得（実際のAPI使用）
    odds_list = get_real_odds(race_id)

    # 4. レース分析
    analysis = recommender.analyze_race(
        probabilities=pred_result['probabilities'],
        odds_list=odds_list
    )

    return {
        'prediction': pred_result,
        'analysis': analysis,
        'race_id': race_id,
        'venue_code': venue_code
    }
```

### ステップ4: 実戦実行

```python
# 本日のレース一覧を取得
today_races = get_today_races()

recommendations = []

for race in today_races:
    # 予測と推奨
    result = predict_and_recommend(
        race_id=race['id'],
        venue_code=race['venue']
    )

    # バランス戦略でベット推奨があれば記録
    for idx, row in result['analysis'].iterrows():
        if row['バランス'] == '✅':
            recommendations.append({
                'race_id': race['id'],
                'pit': row['艇番'],
                'probability': row['勝利確率'],
                'odds': row['オッズ'],
                'kelly_bet': row['ケリー推奨額']
            })

# 推奨一覧を表示
print(f"\n本日のベット推奨: {len(recommendations)}件")
for rec in recommendations:
    print(f"  {rec['race_id']} - {rec['pit']}号艇: {rec['kelly_bet']}")
```

### 資金管理の重要性

```python
# 1日の最大損失額を設定
MAX_DAILY_LOSS = recommender.bankroll * 0.10  # 10%

# 連敗カウンター
consecutive_losses = 0
MAX_CONSECUTIVE_LOSSES = 5

def should_continue_betting(current_loss, consecutive_losses):
    """
    ベットを続けるべきか判定

    Args:
        current_loss: 本日の損失額
        consecutive_losses: 連敗数

    Returns:
        bool: True=継続、False=停止
    """
    if current_loss >= MAX_DAILY_LOSS:
        print("⚠️ 本日の最大損失額に達しました。ベット停止。")
        return False

    if consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
        print("⚠️ 連敗数が上限に達しました。ベット停止。")
        return False

    return True
```

---

## トラブルシューティング

### Q1: モデルファイルが見つからない

```
FileNotFoundError: 統合モデルが見つかりません
```

**解決方法**:
```bash
# モデルファイルの存在確認
ls models/stage2_optimized.json

# なければ再学習
python train_stage2_optimized.py
```

### Q2: 特徴量の次元が合わない

```
ValueError: Feature names mismatch
```

**解決方法**:
- 35次元すべての特徴量が揃っているか確認
- 特徴量の順序が正しいか確認（[EXPERIMENTS_FINAL_REPORT.md](EXPERIMENTS_FINAL_REPORT.md) 参照）
- `boat_third_rate`, `motor_third_rate` が含まれているか確認

### Q3: メモリ不足

```
MemoryError: Cannot allocate memory
```

**解決方法**:
```python
# 事前ロードしない（遅延ロード）
predictor.load_models(preload_all=False)  # 推奨

# 不要なモデルは削除
del predictor.models['01']  # 使わない会場
```

### Q4: 予測確率が異常

**症状**: すべての艇の確率が同じ、または極端な値

**解決方法**:
1. 特徴量の欠損値を確認
2. 特徴量のスケールを確認（異常な大きさの値）
3. モデルファイルの破損を確認（再学習）

### Q5: オッズAPIの統合

**現状**: 仮想オッズを使用

**実戦での対応**:
```python
def get_real_odds(race_id):
    """
    実際のオッズAPIから取得

    TODO: 実装が必要
    - BOATRACE公式API調査
    - またはスクレイピング（規約確認）
    """
    # 仮実装
    import requests
    # response = requests.get(f"https://api.boatrace.jp/odds/{race_id}")
    # return response.json()['odds']

    # 現状はダミー
    return np.array([1.5, 3.2, 5.8, 12.5, 18.0, 35.0])
```

---

## パフォーマンスチューニング

### メモリ使用量の最適化

```python
# 方法1: 遅延ロード（推奨）
predictor.load_models(preload_all=False)

# 方法2: 使用会場のみロード
predictor.load_models(preload_all=False)
for venue in ['07', '11', '18']:  # 頻繁に使う会場のみ
    predictor._load_venue_model(venue)
```

### 予測速度の最適化

```python
# バッチ予測（複数レース一括）
race_ids = ['20240601-07-12', '20240601-08-05', ...]
results = []

for race_id in race_ids:
    X = prepare_race_features(get_race_data(race_id))
    result = predictor.predict(X, venue_code=race_id.split('-')[1])
    results.append(result)
```

---

## 次のステップ

### 短期（1週間）
- [ ] 実オッズAPIの調査と統合
- [ ] Streamlit UIへの統合
- [ ] バックテスト拡張（6ヶ月）

### 中期（1ヶ月）
- [ ] リアルタイム予測システム
- [ ] 自動ベットシステム（慎重に）
- [ ] パフォーマンス監視ダッシュボード

### 長期（3ヶ月）
- [ ] 少額実証実験
- [ ] モデル再学習パイプライン
- [ ] データ収集自動化

---

## サポート

### ドキュメント
- [EXPERIMENTS_FINAL_REPORT.md](EXPERIMENTS_FINAL_REPORT.md): 全実験結果
- [QUICK_START.md](QUICK_START.md): クイックスタート
- [PROJECT_STATUS_AND_NEXT_STEPS.md](PROJECT_STATUS_AND_NEXT_STEPS.md): プロジェクト現状

### コード例
- `hybrid_predictor.py`: デモ実行 `python hybrid_predictor.py`
- `betting_strategy.py`: デモ実行 `python betting_strategy.py`

---

**最終更新**: 2025-11-14
**バージョン**: 1.0.0
