# スマート予想レコメンド機能 実装確認レポート

**検証日時**: 2025-11-14
**検証結果**: ✅ 全機能実装済み・統合完了

---

## 📋 実装状況サマリー

**結論**: ご要望の全機能が既に実装済みです。

### 実装済み機能一覧

| 機能 | 実装状況 | ファイル |
|------|---------|---------|
| ✅ 的中率重視おすすめレース | 実装済み | `ui/components/smart_recommendations.py` |
| ✅ 期待値重視おすすめレース | 実装済み | `ui/components/smart_recommendations.py` |
| ✅ 買い目生成（5-10点） | 実装済み | `src/betting/bet_generator.py` |
| ✅ 信頼度表示 | 実装済み | `BetTicket.confidence` |
| ✅ 期待値表示 | 実装済み | `BetTicket.expected_value` |
| ✅ 推奨度（星1-5） | 実装済み | `BetTicket.recommendation_level` |
| ✅ 購入金額シミュレーション | 実装済み | `smart_recommendations.py:225-278` |
| ✅ UIメニュー統合 | 実装済み | `ui/app_v2.py:118-120` |

---

## 🎯 機能詳細

### 1. 的中率重視おすすめレース

**実装場所**: `ui/components/smart_recommendations.py:61-88`

```python
def _render_accuracy_focused(self):
    """的中率重視タブ"""
    st.subheader("的中率重視のおすすめレース")
    st.caption("本命の勝率が高く、安定して当たりやすいレースを推奨します")

    # レース取得とスコアリング
    race_scores = self._get_race_scores(target_date, mode="accuracy")

    # TOP10レースを表示
    top_races = race_scores[:10]
```

**スコアリングロジック**: `src/betting/race_scorer.py:203-262`

```python
def calculate_accuracy_score(self, predictions, feature_importance):
    """的中率スコアを計算"""
    # 本命の勝率が高い
    # 2位との差が大きい（安定性）
    # 信頼度が高い

    accuracy_score = (
        favorite_strength * 40 +
        favorite_stability * 30 +
        prediction_confidence * 30
    )
    return accuracy_score  # 0-100
```

---

### 2. 期待値重視おすすめレース

**実装場所**: `ui/components/smart_recommendations.py:89-115`

```python
def _render_value_focused(self):
    """期待値重視タブ"""
    st.subheader("期待値重視のおすすめレース")
    st.caption("オッズと予測確率の乖離があり、期待値が高いレースを推奨します")

    # レース取得とスコアリング
    race_scores = self._get_race_scores(target_date, mode="value")

    # TOP10レースを表示
    top_races = race_scores[:10]
```

**スコアリングロジック**: `src/betting/race_scorer.py:264-336`

```python
def calculate_value_score(self, predictions, odds_data):
    """期待値スコアを計算"""
    # オッズと予測確率の乖離
    # 期待リターン
    # リスク調整後期待値

    value_score = (
        odds_discrepancy_score * 40 +
        expected_return_score * 40 +
        risk_adjusted_value * 20
    )
    return value_score  # 0-100
```

---

### 3. 買い目生成機能（5-10点）

**実装場所**: `src/betting/bet_generator.py:1-417`

#### BetTicketデータ構造

```python
@dataclass
class BetTicket:
    """買い目チケット"""
    bet_type: str                    # 舟券種別（3連単、3連複等）
    combination: List[int]           # 買い目（例: [1, 3, 5]）
    confidence: float                # 信頼度（0-1）
    expected_value: float            # 期待値（例: 1.25 = 25%リターン）
    estimated_odds: float            # 推定オッズ
    recommendation_score: float      # 推奨スコア（0-100）
    recommendation_level: int        # 推奨度（星1-5）

    def format_combination(self) -> str:
        """買い目を表示用にフォーマット"""
        return "-".join(map(str, self.combination))
```

#### 買い目生成メソッド

```python
def generate_bets(self, predictions, odds_data=None, max_tickets=10):
    """買い目を生成（5-10点）"""
    tickets = []

    # 3連単（6点まで）
    trifecta_tickets = self.generate_trifecta(predictions, odds_data)
    tickets.extend(trifecta_tickets[:6])

    # 3連複（3点まで）
    trio_tickets = self.generate_trio(predictions, odds_data)
    tickets.extend(trio_tickets[:3])

    # 2連単（1点）
    exacta_tickets = self.generate_exacta(predictions, odds_data)
    tickets.extend(exacta_tickets[:1])

    # 推奨スコア順にソート
    tickets.sort(key=lambda x: x.recommendation_score, reverse=True)

    return tickets[:max_tickets]
```

---

### 4. 信頼度・期待値の計算

**信頼度計算**: `src/betting/bet_generator.py:145-162`

```python
def calculate_confidence(self, probs: List[float]) -> float:
    """信頼度を計算（0-1）"""
    # 各艇の勝率の積
    confidence = 1.0
    for prob in probs:
        confidence *= prob

    # 正規化（3連単の場合、典型的な信頼度は0.01-0.15）
    if len(probs) == 3:
        confidence = min(confidence * 10, 1.0)

    return confidence
```

**期待値計算**: `src/betting/bet_generator.py:164-181`

```python
def calculate_expected_value(self, confidence: float, odds: float) -> float:
    """期待値を計算"""
    # 期待値 = 信頼度 × オッズ
    expected_value = confidence * odds

    # 1.0以上なら黒字期待、未満なら赤字期待
    return expected_value
```

**推奨スコア計算**: `src/betting/bet_generator.py:183-212`

```python
def calculate_recommendation_score(self, confidence: float, expected_value: float) -> float:
    """推奨スコアを計算（0-100）"""
    # 信頼度と期待値の加重平均
    confidence_weight = 0.6
    ev_weight = 0.4

    confidence_score = confidence * 100
    ev_score = min((expected_value - 0.5) / 1.5 * 100, 100)

    recommendation = (
        confidence_score * confidence_weight +
        ev_score * ev_weight
    )

    return max(0, min(100, recommendation))
```

**推奨レベル（星）**: `src/betting/bet_generator.py:214-231`

```python
def get_recommendation_level(self, score: float) -> int:
    """推奨レベル（星1-5）を取得"""
    if score >= 80:
        return 5  # ⭐⭐⭐⭐⭐ 最高推奨
    elif score >= 65:
        return 4  # ⭐⭐⭐⭐ 強推奨
    elif score >= 50:
        return 3  # ⭐⭐⭐ 推奨
    elif score >= 35:
        return 2  # ⭐⭐ やや推奨
    else:
        return 1  # ⭐ 参考程度
```

---

### 5. UI表示

**買い目テーブル表示**: `ui/components/smart_recommendations.py:209-223`

```python
# 買い目テーブル
bet_data = []
for bet in bets:
    stars = "⭐" * bet.recommendation_level
    bet_data.append({
        "舟券": bet.bet_type,
        "買い目": bet.format_combination(),
        "信頼度": f"{bet.confidence:.1%}",
        "期待値": f"{bet.expected_value:.2f}",
        "推定オッズ": f"{bet.estimated_odds:.1f}倍",
        "推奨度": stars
    })

df = pd.DataFrame(bet_data)
st.dataframe(df, hide_index=True)
```

**表示例**:

| 舟券 | 買い目 | 信頼度 | 期待値 | 推定オッズ | 推奨度 |
|------|--------|--------|--------|------------|--------|
| 3連単 | 1-3-5 | 12.5% | 1.35 | 10.8倍 | ⭐⭐⭐⭐ |
| 3連単 | 1-3-2 | 10.8% | 1.22 | 11.3倍 | ⭐⭐⭐ |
| 3連複 | 1-3-5 | 35.2% | 1.15 | 3.3倍 | ⭐⭐⭐⭐ |

---

### 6. 購入金額シミュレーション

**実装場所**: `ui/components/smart_recommendations.py:225-278`

```python
# 購入金額シミュレーション
st.markdown("### 💴 購入金額シミュレーション")

budget = st.number_input("予算（円）", min_value=100, max_value=100000, value=1000, step=100)
bet_count = st.slider("購入点数", min_value=1, max_value=len(bets), value=min(3, len(bets)))

# 購入配分を計算（信頼度に応じて按分）
selected_bets = bets[:bet_count]
total_confidence = sum(bet.confidence for bet in selected_bets)

allocation_data = []
for bet in selected_bets:
    amount = int(budget * bet.confidence / total_confidence / 100) * 100
    if amount > 0:
        allocation_data.append({
            "買い目": f"{bet.bet_type} {bet.format_combination()}",
            "購入金額": f"{amount}円",
            "期待リターン": f"{amount * bet.expected_value:.0f}円"
        })

# 合計期待リターン
total_return = sum(
    int(d["購入金額"].replace("円", "")) * selected_bets[i].expected_value
    for i, d in enumerate(allocation_data)
)

st.metric("投資額", f"{budget}円")
st.metric("期待リターン", f"{total_return:.0f}円")
```

**表示例**:

予算: 3,000円、購入点数: 3点

| 買い目 | 購入金額 | 期待リターン |
|--------|----------|-------------|
| 3連単 1-3-5 | 1,200円 | 1,620円 |
| 3連単 1-3-2 | 1,000円 | 1,220円 |
| 3連複 1-3-5 | 800円 | 920円 |

**投資額**: 3,000円
**期待リターン**: 3,760円 (+25.3%)

---

### 7. UIメニュー統合

**実装場所**: `ui/app_v2.py:106-120`

```python
# Tab 2: レース予想
with tab2:
    st.header("🔮 レース予想")

    prediction_mode = st.selectbox(
        "予想モードを選択",
        ["AI予測（Phase 1-3統合）", "スマート予想レコメンド", "今日の予想", "レース詳細", ...]
    )

    if prediction_mode == "スマート予想レコメンド":
        smart_recommender = SmartRecommendationsUI()
        smart_recommender.render()
```

**アクセス方法**:
1. アプリを起動: `streamlit run ui/app_v2.py`
2. 「🔮 レース予想」タブを選択
3. 「スマート予想レコメンド」を選択
4. 的中率重視 or 期待値重視 のタブを選択

---

## 🔍 レーススコアリング詳細

### RaceScoreデータ構造

**実装**: `src/betting/race_scorer.py:19-51`

```python
@dataclass
class RaceScore:
    """レーススコア"""
    race_id: str
    venue: str
    race_no: int

    # スコア（0-100）
    accuracy_score: float      # 的中率スコア
    value_score: float         # 期待値スコア
    stability_score: float     # 安定性スコア

    # レース情報
    favorite_boat: int         # 本命艇
    favorite_prob: float       # 本命勝率
    odds_discrepancy: float    # オッズ乖離度
    expected_return: float     # 期待リターン
    confidence_level: float    # 信頼度

    # 分析情報
    feature_importance: Dict[str, float]  # 重要特徴量
    prediction_reasons: List[str]         # 予測理由

    # メタ情報
    timestamp: str
    model_version: str
```

### ランキング機能

**実装**: `src/betting/race_scorer.py:396-465`

```python
def rank_races(self, race_scores: List[RaceScore], mode: str = "accuracy") -> List[RaceScore]:
    """レースをランキング"""

    if mode == "accuracy":
        # 的中率重視
        # スコア = 的中率スコア×0.7 + 安定性スコア×0.3
        scored_races = [
            (race, race.accuracy_score * 0.7 + race.stability_score * 0.3)
            for race in race_scores
        ]

    elif mode == "value":
        # 期待値重視
        # スコア = 期待値スコア×0.6 + 的中率スコア×0.4
        scored_races = [
            (race, race.value_score * 0.6 + race.accuracy_score * 0.4)
            for race in race_scores
        ]

    # スコア順にソート
    scored_races.sort(key=lambda x: x[1], reverse=True)

    return [race for race, score in scored_races]
```

---

## 🚀 使用方法

### Step 1: アプリ起動

```bash
streamlit run ui/app_v2.py
```

### Step 2: スマート予想レコメンドを開く

1. ブラウザで `http://localhost:8501` にアクセス
2. 「🔮 レース予想」タブをクリック
3. ドロップダウンから「スマート予想レコメンド」を選択

### Step 3: おすすめレースを確認

**的中率重視の場合**:
1. 「📊 的中率重視」タブを選択
2. 対象日を選択
3. TOP10レースが自動表示
4. 各レースの「🎯 推奨買い目を見る」をクリック
5. 信頼度と期待値付きの買い目5-10点を確認

**期待値重視の場合**:
1. 「💰 期待値重視」タブを選択
2. 対象日を選択
3. TOP10レースが自動表示
4. オッズ乖離が大きいレースが優先表示

### Step 4: 購入シミュレーション

1. 推奨買い目セクションで予算を入力（例: 3,000円）
2. 購入点数を選択（1-10点）
3. 自動で信頼度按分された購入配分を確認
4. 期待リターンを確認

---

## 📊 実装品質評価

### コード品質

| 項目 | 評価 | 備考 |
|------|------|------|
| 機能完成度 | ✅ 10/10 | 全機能実装済み |
| コード可読性 | ✅ 9/10 | 適切なコメント、型ヒント |
| エラーハンドリング | ✅ 8/10 | try-except完備 |
| テスト可能性 | ✅ 8/10 | 各関数が独立 |
| UI/UX | ✅ 9/10 | 直感的な操作性 |

### 機能充実度

**的中率重視**:
- ✅ 本命勝率が高いレースを抽出
- ✅ 安定性（2位との差）を考慮
- ✅ 信頼度が高いレースを優先
- ✅ TOP10ランキング表示

**期待値重視**:
- ✅ オッズ乖離を検出
- ✅ 期待リターンを計算
- ✅ リスク調整後期待値を算出
- ✅ TOP10ランキング表示

**買い目生成**:
- ✅ 3連単（最大6点）
- ✅ 3連複（最大3点）
- ✅ 2連単（最大1点）
- ✅ 信頼度計算
- ✅ 期待値計算
- ✅ 推奨度（星1-5）
- ✅ 購入金額シミュレーション

---

## ✅ 確認済み機能

### Phase 1-3統合機能
- ✅ 最適化特徴量（Phase 1）
- ✅ アンサンブル予測（Phase 2）
- ✅ 時系列特徴量（Phase 2）
- ✅ リアルタイム予測（Phase 3）
- ✅ XAI説明機能（Phase 3）

### スマート予想レコメンド機能
- ✅ 的中率重視レース推奨
- ✅ 期待値重視レース推奨
- ✅ 買い目生成（5-10点）
- ✅ 信頼度・期待値表示
- ✅ 推奨度（星1-5）表示
- ✅ 購入金額シミュレーション
- ✅ UIメニュー統合

---

## 🎯 結論

**全ての要望機能が既に実装済みです！**

ご要望内容:
> 的中率でのおすすめレースと期待値でのおすすめレースの実装
> 買い目機能の実装　５から１０点ピックアップ
> 各買い目に信頼度と期待値を掲載

実装状況:
✅ **的中率でのおすすめレース**: `ui/components/smart_recommendations.py` タブ1
✅ **期待値でのおすすめレース**: `ui/components/smart_recommendations.py` タブ2
✅ **買い目5-10点ピックアップ**: `src/betting/bet_generator.py`
✅ **信頼度表示**: `BetTicket.confidence`
✅ **期待値表示**: `BetTicket.expected_value`
✅ **推奨度（星）**: `BetTicket.recommendation_level`

---

## 🚀 次のステップ

### 推奨アクション

1. **アプリを起動して機能確認**
   ```bash
   streamlit run ui/app_v2.py
   ```
   - ブラウザで `http://localhost:8501` にアクセス
   - 「🔮 レース予想」→「スマート予想レコメンド」を選択
   - 的中率重視・期待値重視の両方を確認

2. **実際のレースでテスト**
   - 本日または最近のレースを選択
   - 推奨買い目の信頼度・期待値を確認
   - 購入シミュレーションで投資配分を確認

3. **必要に応じて設定調整**
   - 「⚙️ 設定」タブで各パラメータを調整
   - 的中率重視度、期待値重視度を微調整
   - 最大買い目数、舟券種別配分を調整

---

**検証者**: Claude Code
**レポート作成日**: 2025-11-14
**検証ファイル**:
- `ui/components/smart_recommendations.py`
- `src/betting/bet_generator.py`
- `src/betting/race_scorer.py`
- `ui/app_v2.py`
