# 決まり手ベース予測システム - 実装ドキュメント

## 概要

競艇の決まり手（逃げ/差し/まくり等）に基づいた理論的な予測システム。
従来の単純なスコア順ではなく、レース展開シナリオを考慮して複数の買い目を確率ベースで生成します。

## 実装日
2025年11月14日

## システム構成

### 1. ファイル構成

```
src/prediction/
├── kimarite_constants.py              # 定数・マスタデータ定義
├── kimarite_probability_engine.py     # 決まり手確率計算エンジン
├── race_scenario_engine.py            # レース展開シナリオエンジン
├── probability_integrator.py          # 確率統合・買い目選定エンジン
└── integrated_kimarite_predictor.py   # 統合予測システム

ui/components/
└── unified_race_list.py               # UI統合（修正済み）

tests/
└── test_kimarite_prediction.py        # テストスクリプト
```

---

## 各モジュールの詳細

### 1. kimarite_constants.py

**役割**: 決まり手予測に必要な定数とマスタデータを定義

**主な定義内容**:

#### 1.1 決まり手の種類
```python
class Kimarite(IntEnum):
    NIGE = 1           # 逃げ
    SASHI = 2          # 差し
    MAKURI = 3         # まくり
    MAKURI_SASHI = 4   # まくり差し
    NUKI = 5           # 抜き
    MEGUMARE = 6       # 恵まれ
```

#### 1.2 コース別決まり手事前確率
各コースでどの決まり手が出やすいかの統計的確率

```python
COURSE_KIMARITE_PRIOR = {
    1: {Kimarite.NIGE: 0.950, ...},  # 1コースは95%逃げ
    2: {Kimarite.SASHI: 0.650, ...}, # 2コースは65%差し
    3: {Kimarite.MAKURI: 0.400, ...},# 3コースは40%まくり
    ...
}
```

#### 1.3 会場マスタデータ
- **水質情報** (`VENUE_WATER_QUALITY`): 淡水/海水/汽水
- **インコース有利度** (`VENUE_INNER_ADVANTAGE`): 1.0が標準、1.2なら1コース有利

#### 1.4 環境要因の処理
- **風向数値化** (`WIND_DIRECTION_DEGREES`): 方角→度数変換
- **風の影響計算** (`get_wind_effect()`): 追い風/向かい風/横風成分を算出
- **モーター出力タイプ推定** (`estimate_motor_output_type()`): 2連率から出足型/伸び型/バランス型を判定

---

### 2. kimarite_probability_engine.py

**役割**: ベイズ推定により各艇の決まり手確率を計算

**クラス**: `KimariteProbabilityEngine`

#### 主要メソッド

##### 2.1 `calculate_kimarite_probabilities(race_id)`
レースの全艇について決まり手確率を計算

**計算式**:
```
P(決まり手|条件) = P(条件|決まり手) × P(事前確率) / P(条件)
```

**考慮要素**:
1. **選手要因**: 決まり手実績、平均ST、勝率
2. **コース要因**: コース別基本確率、会場特性
3. **環境要因**: 風速、風向、波高、水温
4. **モーター要因**: 2連率、出力タイプ

**出力例**:
```python
{
    1: {Kimarite.NIGE: 0.965, Kimarite.SASHI: 0.01, ...},
    2: {Kimarite.SASHI: 0.60, Kimarite.MAKURI: 0.25, ...},
    ...
}
```

##### 2.2 尤度計算メソッド
各要因が決まり手に与える影響を計算

- `_st_likelihood()`: STタイミングの影響
  - ST ≤ 0.10 → 1コース逃げ/3-6コースまくりが有利
  - ST ≥ 0.20 → 差しが有利、逃げ・まくりが不利

- `_venue_likelihood()`: 会場特性の影響
  - インコース有利な会場 → 1コース逃げ確率UP

- `_wind_likelihood()`: 風の影響
  - 追い風3m/s以上 → 1コース逃げ不利、差し・まくり有利
  - 向かい風3m/s以上 → 1コース逃げ有利、まくり不利

- `_motor_likelihood()`: モーター性能の影響
  - 高性能×出足型 → 逃げ・差し有利
  - 高性能×伸び型 → まくり・まくり差し有利

##### 2.3 `calculate_win_probability(kimarite_probs)`
決まり手確率から各艇の1着確率を計算

---

### 3. race_scenario_engine.py

**役割**: 決まり手確率から考えられるレース展開シナリオを生成

**クラス**: `RaceScenarioEngine`

#### データ構造

```python
@dataclass
class RaceScenario:
    scenario_id: str           # "1_nige"
    scenario_name: str         # "1号艇逃げ成功"
    leading_boat: int          # 1
    kimarite: Kimarite         # Kimarite.NIGE
    probability: float         # 0.965
    finish_patterns: List[Tuple[Tuple[int, int, int], float]]
    # [(着順, 確率), ...]
    # [((1,2,3), 0.272), ((1,2,4), 0.204), ...]
```

#### 主要メソッド

##### 3.1 `calculate_race_scenarios(kimarite_probs)`
全ての可能なシナリオを生成し、確率順にソート

**処理フロー**:
1. 各艇×各決まり手の組み合わせでシナリオ生成
2. 確率が低すぎる（< 1%）シナリオは除外
3. 累積確率95%まで返す

##### 3.2 `_calculate_second_place_probs()`
1着が決まった後の2着確率を計算

**決まり手ごとの傾向**:
- **1逃げ成功** → 2着: 2コース40%, 3コース25%, 4コース20%
- **2差し成功** → 2着: 1コース45%, 3コース25%
- **まくり成功** → 2着: 1コース35%, 内側の艇30%

##### 3.3 `_calculate_third_place_probs()`
1-2着が決まった後の3着確率を計算

**パターン例**:
- **1-2** → 3着: 3コース40%, 4コース30%
- **1-3** → 3着: 2コース40%, 4コース30%

---

### 4. probability_integrator.py

**役割**: シナリオから2連単・3連単確率を統合し、最適買い目を選定

**クラス**: `ProbabilityIntegrator`

#### データ構造

```python
@dataclass
class BetRecommendation:
    combination: Tuple[int, int, int]  # (1, 2, 3)
    probability: float                  # 0.263
    scenario: str                       # "1号艇逃げ成功"
    confidence: str                     # "Very High"
    rank: int                           # 1
```

#### 主要メソッド

##### 4.1 `calculate_trifecta_probabilities(scenarios)`
全シナリオを統合して3連単確率を計算

**計算式**:
```
P(1-2-3) = Σ [P(シナリオi) × P(1-2-3|シナリオi)]
```

**出力例**:
```python
{
    (1, 2, 3): 0.263,
    (1, 2, 4): 0.197,
    (1, 3, 2): 0.164,
    ...
}
```

##### 4.2 `select_optimal_bets()`
最適な買い目を選定

**選定戦略**:
- **probability**: 確率が2%以上の買い目を選定
- **coverage**: 累積確率70%まで選定

**買い目数の決定**:
- 最小: 3点（min_bets）
- 最大: 6点（max_bets）
- 確率が低すぎる場合は途中で打ち切り

##### 4.3 信頼度判定
```python
probability >= 0.20  → "Very High"
probability >= 0.10  → "High"
probability >= 0.05  → "Medium"
probability >= 0.02  → "Low"
```

---

### 5. integrated_kimarite_predictor.py

**役割**: 3つのエンジンを統合し、API的なインターフェースを提供

**クラス**: `IntegratedKimaritePredictor`

#### 主要メソッド

##### 5.1 `predict_race(race_id, min_bets=3, max_bets=6)`
レースの総合予測を実行

**処理フロー**:
```
1. 決まり手確率を計算 (KimariteProbabilityEngine)
   ↓
2. 展開シナリオを生成 (RaceScenarioEngine)
   ↓
3. 買い目を選定 (ProbabilityIntegrator)
   ↓
4. 統計情報を計算
```

**返り値**:
```python
{
    'bets': [BetRecommendation, ...],      # 買い目リスト
    'scenarios': [RaceScenario, ...],       # シナリオリスト
    'kimarite_probs': {...},                # 決まり手確率
    'statistics': {                         # 統計情報
        'total_bets': 6,
        'total_probability': 0.965,
        'main_favorite': 1,
        ...
    }
}
```

##### 5.2 `predict_race_by_key(race_date, venue_code, race_number)`
レースキーから予測実行（race_idを内部で取得）

##### 5.3 `format_prediction_for_ui(prediction)`
予測結果をUI表示用にフォーマット

---

## UI統合（unified_race_list.py）

### 修正箇所

#### 1. インポート追加
```python
from src.prediction.integrated_kimarite_predictor import IntegratedKimaritePredictor
```

#### 2. 予測エンジンの初期化
```python
kimarite_predictor = IntegratedKimaritePredictor()
```

#### 3. 予想生成部分の変更
**変更前**:
```python
predictions = race_predictor.predict_race_by_key(...)
top3 = predictions[:3]
# 1つの買い目のみ: "1-2-3"
```

**変更後**:
```python
kimarite_result = kimarite_predictor.predict_race_by_key(
    race_date, venue_code, race_number,
    min_bets=3, max_bets=6
)
bets = kimarite_result['bets']
# 複数買い目を取得: ["1-2-3", "1-2-4", "1-3-2", ...]
```

#### 4. レースカード表示の変更
**変更前**:
```python
st.markdown(f"🎯 **{race['1着']}-{race['2着']}-{race['3着']}**")
```

**変更後**:
```python
bet_list = race['買い目リスト']
st.markdown(f"🎯 **本命: {bet_list[0]}**")
st.caption(f"他{len(bet_list)-1}点: {', '.join(bet_list[1:3])}")
```

---

## 使用例

### 1. コマンドラインテスト
```python
from src.prediction.integrated_kimarite_predictor import IntegratedKimaritePredictor

predictor = IntegratedKimaritePredictor()
result = predictor.predict_race(race_id=445, min_bets=3, max_bets=6)

# 結果表示
for bet in result['bets']:
    print(f"{bet.rank}. {bet.combination} - {bet.probability*100:.1f}%")
```

**出力例**:
```
1. (1, 2, 3) - 26.3%
2. (1, 2, 4) - 19.7%
3. (1, 3, 2) - 16.4%
4. (1, 3, 4) - 12.3%
5. (1, 4, 2) - 10.9%
6. (1, 4, 3) - 10.9%

累積的中率: 96.5%
本命: 1号艇
```

### 2. UI経由での使用
```python
# StreamlitアプリでUIから使用
streamlit run test_unified_ui.py
```

1. 「的中率重視」タブを選択
2. 日付と最低信頼度を設定
3. 自動的に本日のおすすめレースを複数買い目付きで表示

---

## データ要件

### 必須データ（DB）
- ✅ **決まり手データ** (`results.winning_technique`): 120,859件
- ✅ **STデータ** (`race_details.st_time`, `entries.avg_st`)
- ✅ **天候データ** (`weather.wind_speed`, `wind_direction`, `wave_height`)
- ✅ **モーター性能** (`entries.motor_second_rate`)

### マスタデータ（コード定義）
- ✅ **コース別決まり手確率** (`COURSE_KIMARITE_PRIOR`)
- ✅ **会場水質** (`VENUE_WATER_QUALITY`)
- ✅ **会場特性** (`VENUE_INNER_ADVANTAGE`)

---

## パラメータチューニング

### 1. 買い目数の調整
```python
# 保守的（3-4点）
predictor.predict_race(race_id, min_bets=3, max_bets=4)

# 標準（3-6点）※デフォルト
predictor.predict_race(race_id, min_bets=3, max_bets=6)

# 広範囲（3-10点）
predictor.predict_race(race_id, min_bets=3, max_bets=10)
```

### 2. 買い目選定戦略
```python
# 確率重視（2%以上の買い目のみ）
select_optimal_bets(scenarios, strategy='probability')

# カバレッジ重視（累積70%まで）
select_optimal_bets(scenarios, strategy='coverage')
```

### 3. シナリオの最小確率閾値
```python
# デフォルト: 1%以上のシナリオを生成
calculate_race_scenarios(kimarite_probs, min_probability=0.01)

# より厳格: 5%以上のシナリオのみ
calculate_race_scenarios(kimarite_probs, min_probability=0.05)
```

---

## 今後の改善案

### Phase 1: 精度向上
1. **過去データでのバックテスト**
   - 決まり手確率の精度検証
   - 的中率・回収率の測定

2. **パラメータ最適化**
   - ベイズ推定の重み調整
   - 尤度計算の係数チューニング

### Phase 2: 機能拡張
1. **オッズ連動**
   - リアルタイムオッズ取得
   - 期待値計算による買い目選定

2. **進入予想との連携**
   - 実際のコース取りを予測
   - `actual_course`の事前予測

### Phase 3: UI改善
1. **詳細画面の拡充**
   - シナリオ別の着順パターン表示
   - 決まり手確率の可視化

2. **カスタマイズ機能**
   - ユーザーごとの買い目戦略設定
   - 信頼度フィルタの保存

---

## トラブルシューティング

### エラー: "Race not found"
**原因**: 指定したレースがDBに存在しない
**対処**: race_date, venue_code, race_numberを確認

### エラー: "No bets generated"
**原因**: 信頼度が低く、買い目が生成されなかった
**対処**: `min_confidence`を下げる、または`min_bets`を減らす

### 予測が遅い
**原因**: 決まり手履歴の取得に時間がかかる
**対処**: キャッシュが効くまで待つ（2回目以降は高速化）

---

## まとめ

### 実現したこと
✅ 決まり手（逃げ/差し/まくり）ベースの理論的予測
✅ ベイズ推定による確率計算
✅ 複数展開シナリオの生成
✅ 3-6点の買い目を確率順に選定
✅ UIへの統合と複数買い目表示

### 期待される効果
- **的中率向上**: 1点買い15% → 3-6点買い40-60%
- **リスク分散**: 複数買い目で安定性向上
- **透明性**: 各買い目の確率とシナリオを明示

### 設計の優位性
1. **理論的根拠**: ベイズ推定による科学的アプローチ
2. **柔軟性**: パラメータ調整で戦略変更可能
3. **拡張性**: オッズ連動など将来の機能追加が容易

---

## リファレンス

### 主要クラス一覧
- `KimariteProbabilityEngine`: 決まり手確率計算
- `RaceScenarioEngine`: シナリオ生成
- `ProbabilityIntegrator`: 確率統合・買い目選定
- `IntegratedKimaritePredictor`: 統合API

### 主要データ構造
- `Kimarite`: 決まり手の列挙型
- `RaceScenario`: レース展開シナリオ
- `BetRecommendation`: 買い目推奨
- `KimariteFactors`: 決まり手確率の影響要因

### テストコマンド
```bash
# 単体テスト
python test_kimarite_prediction.py

# UI起動
streamlit run test_unified_ui.py
```

---

**作成者**: Claude (Anthropic)
**作成日**: 2025年11月14日
**バージョン**: 1.0
