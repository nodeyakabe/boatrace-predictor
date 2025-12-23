# 参考サイト詳細解析資料

## 目次
1. [kyoteibiyori 詳細分析](#kyoteibiyori)
2. [BOATERS 詳細分析](#boaters)
3. [両サイトの比較](#comparison)
4. [実装への応用](#implementation)

---

## <a name="kyoteibiyori"></a>1. kyoteibiyori 詳細分析

### サイト情報
- **URL**: https://kyoteibiyori.com/
- **コンセプト**: データドリブンな競艇予想支援プラットフォーム
- **ターゲット**: 条件検索でレースを絞り込みたいユーザー

### 主要機能

#### 1.1 超展開データ（最大の特徴）
**概要**:
- 選手の1マークでの攻め方を数値化
- 従来の単純な確率分析を超えた戦術レベルの分析

**実装への示唆**:
- 展示タイムだけでなく、過去のレース展開パターンを分析
- 選手の「攻める傾向」「守る傾向」をスコア化
- 1マークでの位置取り予測モデル

**データ要件**:
```python
# 必要なデータ
- 過去のスタート順位
- 1マークでの順位変動
- 差し・捲りの成功率
- コース別の戦術選択傾向
```

#### 1.2 条件検索機能

**ガチガチレース検索**:
```
入力条件:
- 1号艇の逃げ率（例: 70%以上）
- 2号艇の逃し率（例: 60%以上）

検索ロジック:
1. 全レースから1号艇の全国勝率・当地勝率を取得
2. 1号艇の「逃げ率」を計算（コース別1着率）
3. 2号艇の「逃し率」を計算（1号艇を1着で通す率）
4. 条件に合致するレースを抽出

出力:
- 該当レース一覧
- 推奨買い目（1-2-3, 1-2-4など）
- 信頼度スコア
```

**穴狙いレース検索**:
```
入力条件:
- 1号艇の逃げ率上限（例: 50%未満）
- 2-6号艇の差し・捲り率（例: 30%以上）

検索ロジック:
1. 1号艇の逃げ率が低いレースを抽出
2. 外枠艇の攻撃力（差し率・捲り率）を計算
3. モーター2連率の高い艇を評価
4. 荒れる可能性の高いレースを抽出

出力:
- 穴候補レース一覧
- 注目艇と予想配当範囲
```

#### 1.3 アラート機能

**まくりアラート**:
```
判定条件:
- 展示タイムが外枠艇の方が早い（0.3秒以上の差）
- かつ、平均STが良い（0.15秒以内）
- かつ、モーター2連率が高い（35%以上）

→ まくりが決まる可能性が高い

実装例:
def check_makuri_alert(exhibition_times, avg_st, motor_rates):
    outer_lanes = [4, 5, 6]  # 外枠
    inner_lanes = [1, 2, 3]  # 内枠

    outer_fastest = min([exhibition_times[i] for i in outer_lanes])
    inner_fastest = min([exhibition_times[i] for i in inner_lanes])

    if (outer_fastest + 0.3 < inner_fastest and
        avg_st[outer_lanes] < 0.15 and
        motor_rates[outer_lanes] > 0.35):
        return True, "まくり警戒"
    return False, None
```

**前づけアラート**:
```
判定条件:
- 進入予想コースと枠番が大きく異なる
- 内側に2艇以上が前づけしようとしている

→ スタート展開が荒れる可能性

実装例:
def check_maezuke_alert(pit_numbers, expected_courses):
    maezuke_count = 0
    for pit, course in zip(pit_numbers, expected_courses):
        if pit - course >= 2:  # 2枠以上内側に入る
            maezuke_count += 1

    if maezuke_count >= 2:
        return True, "前づけ警戒：展開が荒れる可能性"
    return False, None
```

**チルト跳アラート**:
```
判定条件:
- チルト角度が極端（-0.5以下 or +3.0以上）
- かつ、モーター2連率が高い

→ 有利な選手の可能性

実装例:
def check_tilt_alert(tilt_angles, motor_rates):
    alerts = []
    for i, (tilt, rate) in enumerate(zip(tilt_angles, motor_rates)):
        if (tilt <= -0.5 or tilt >= 3.0) and rate > 0.35:
            alerts.append(f"{i+1}号艇: チルト{tilt}° / モーター{rate*100:.1f}%")

    if alerts:
        return True, alerts
    return False, None
```

#### 1.4 場状況分析

**固い場ランキング**:
```sql
-- 計算方法
SELECT
    venue_code,
    AVG(CASE WHEN pit_number = 1 AND rank = 1 THEN 1 ELSE 0 END) as escape_rate,
    AVG(trifecta_odds) as avg_payout
FROM results r
JOIN races ra ON r.race_id = ra.id
WHERE race_date >= date('now', '-3 months')
GROUP BY venue_code
ORDER BY escape_rate DESC, avg_payout ASC
```

**荒れている場ランキング**:
```sql
-- 計算方法
SELECT
    venue_code,
    AVG(CASE WHEN pit_number = 1 AND rank = 1 THEN 1 ELSE 0 END) as escape_rate,
    AVG(CASE WHEN trifecta_odds >= 10000 THEN 1 ELSE 0 END) as upset_rate
FROM results r
JOIN races ra ON r.race_id = ra.id
WHERE race_date >= date('now', '-3 months')
GROUP BY venue_code
ORDER BY escape_rate ASC, upset_rate DESC
```

**イン逃率ランキング**:
```sql
-- 1-3号艇の1着率合計
SELECT
    venue_code,
    AVG(CASE WHEN pit_number IN (1,2,3) AND rank = 1 THEN 1 ELSE 0 END) as inside_win_rate
FROM results r
JOIN races ra ON r.race_id = ra.id
WHERE race_date >= date('now', '-3 months')
GROUP BY venue_code
ORDER BY inside_win_rate DESC
```

**万舟率ランキング**:
```sql
-- 配当10,000円以上の出現率
SELECT
    venue_code,
    AVG(CASE WHEN trifecta_odds >= 10000 THEN 1 ELSE 0 END) * 100 as high_payout_rate
FROM results r
JOIN races ra ON r.race_id = ra.id
WHERE race_date >= date('now', '-3 months')
GROUP BY venue_code
ORDER BY high_payout_rate DESC
```

### 学ぶべきポイント

1. **データの可視化**:
   - ランキング形式で分かりやすく表示
   - 色分けで直感的に理解できる

2. **条件の柔軟性**:
   - ユーザーが閾値を調整できる
   - 検索結果を即座に更新

3. **戦術レベルの分析**:
   - 単なる統計だけでなく、レース展開を予測
   - 「攻め方」という抽象概念の数値化

---

## <a name="boaters"></a>2. BOATERS 詳細分析

### サイト情報
- **URL**: https://boaters-boatrace.com/
- **コンセプト**: AI予想とその実績を完全公開する透明性重視のプラットフォーム
- **ターゲット**: AI予想を参考にしたいユーザー、実績を重視するユーザー

### 主要機能

#### 2.1 複数AI予想モデル

**4つのモデル**:

| モデル名 | 狙い | 的中率目標 | 回収率目標 | 推奨ユーザー |
|---------|------|----------|----------|------------|
| Hit | 的中重視 | 35-40% | 0.8-0.9倍 | 初心者 |
| HighOdds | 高配当狙い | 15-20% | 1.2-1.5倍 | 上級者 |
| Profitable | 収益性重視 | 25-30% | 1.0-1.2倍 | 中級者 |
| NewBalance | バランス型 | 30-35% | 0.9-1.1倍 | 万人向け |

**Hit型の実装イメージ**:
```python
def hit_model_prediction(race_data):
    """
    的中重視型予想

    ロジック:
    1. 1号艇の逃げ率が高い（60%以上）→ 1軸
    2. 2-3号艇の連対率が高い → 相手候補
    3. 低オッズでも安定した組み合わせを推奨
    """
    score = {}

    # 1号艇が強い場合
    if race_data['pit_1']['escape_rate'] >= 0.6:
        score['1-2-3'] = 0.9  # 高確率
        score['1-2-4'] = 0.85
        score['1-3-4'] = 0.8
    else:
        # 1号艇が弱い場合は2-3号艇軸
        if race_data['pit_2']['win_rate'] >= 0.3:
            score['2-1-3'] = 0.75
            score['2-3-1'] = 0.7

    # スコア順にソート
    return sorted(score.items(), key=lambda x: x[1], reverse=True)[:3]
```

**HighOdds型の実装イメージ**:
```python
def high_odds_model_prediction(race_data, odds_data):
    """
    高配当狙い型予想

    ロジック:
    1. 1号艇の逃げ率が低い（50%未満）レースを選択
    2. 差し・捲りが得意な選手を高評価
    3. オッズ50倍以上の組み合わせを推奨
    """
    candidates = []

    # 1号艇が弱いレースのみ対象
    if race_data['pit_1']['escape_rate'] < 0.5:
        # 外枠で強い選手を探す
        for pit in [4, 5, 6]:
            if (race_data[f'pit_{pit}']['attack_rate'] > 0.3 and
                race_data[f'pit_{pit}']['motor_rate'] > 0.35):

                # 穴候補として登録
                combinations = generate_high_odds_combinations(pit)
                for comb in combinations:
                    if odds_data[comb] >= 50:
                        candidates.append((comb, odds_data[comb]))

    # オッズが高い順に返す
    return sorted(candidates, key=lambda x: x[1], reverse=True)[:5]
```

**Profitable型の実装イメージ**:
```python
def profitable_model_prediction(race_data, odds_data):
    """
    収益性重視型予想

    ロジック:
    1. 期待値 = 予想的中率 × オッズ
    2. 期待値が1.0を超える買い目のみ推奨
    3. リスクとリターンのバランスを重視
    """
    expected_values = {}

    for combination, odds in odds_data.items():
        # 組み合わせの的中確率を計算
        win_probability = calculate_win_probability(combination, race_data)

        # 期待値計算
        expected_value = win_probability * odds

        # 期待値が1.0以上の買い目のみ
        if expected_value >= 1.0:
            expected_values[combination] = {
                'odds': odds,
                'probability': win_probability,
                'expected_value': expected_value
            }

    # 期待値が高い順に返す
    return sorted(expected_values.items(),
                  key=lambda x: x[1]['expected_value'],
                  reverse=True)[:3]
```

**NewBalance型の実装イメージ**:
```python
def new_balance_model_prediction(race_data, odds_data):
    """
    バランス型予想

    ロジック:
    1. レース状況を判定（堅い/荒れそう）
    2. 堅いレース → Hit型寄りの予想
    3. 荒れそうなレース → HighOdds型寄りの予想
    """
    # レースの堅さを判定
    is_solid = race_data['pit_1']['escape_rate'] >= 0.65

    if is_solid:
        # 堅いレース：的中重視
        return hit_model_prediction(race_data)
    else:
        # 荒れそうなレース：期待値重視
        candidates = profitable_model_prediction(race_data, odds_data)

        # 期待値上位 + オッズ適度な買い目を混ぜる
        result = candidates[:2]  # 期待値上位2つ

        # オッズ20-50倍の穴目を1つ追加
        for comb, data in candidates[2:]:
            if 20 <= data['odds'] <= 50:
                result.append((comb, data))
                break

        return result
```

#### 2.2 実績追跡システム

**月間成績の例（NewBalance型）**:
```
月間成績（2024年10月）
- 総予想数: 620レース
- 的中数: 222レース
- 的中率: 35.8%
- 総投資額: 620,000円（1レース1,000円）
- 総払戻額: 551,800円
- 回収率: 89.0%
- 収支: -68,200円
```

**実装への示唆**:
```python
class PerformanceTracker:
    def __init__(self, db_path):
        self.db = Database(db_path)

    def record_prediction_result(self, prediction_data, result_data):
        """
        予想結果を記録

        Args:
            prediction_data: {
                'date': '2024-10-30',
                'model': 'new_balance',
                'venue': '03',
                'race_number': 10,
                'predicted_combination': '1-2-3',
                'odds': 12.5,
                'bet_amount': 1000
            }
            result_data: {
                'actual_combination': '1-2-3',
                'payout': 1250
            }
        """
        is_hit = (prediction_data['predicted_combination'] ==
                  result_data['actual_combination'])

        return_amount = result_data['payout'] if is_hit else 0
        return_rate = return_amount / prediction_data['bet_amount']

        # DB保存
        self.db.execute("""
            INSERT INTO prediction_results
            (date, model, venue, race_number, predicted_combination,
             is_hit, bet_amount, return_amount, return_rate)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (prediction_data['date'], prediction_data['model'],
              prediction_data['venue'], prediction_data['race_number'],
              prediction_data['predicted_combination'], is_hit,
              prediction_data['bet_amount'], return_amount, return_rate))

    def generate_monthly_report(self, year, month, model=None):
        """
        月次レポート生成

        Returns:
            {
                'total_predictions': 620,
                'total_hits': 222,
                'hit_rate': 0.358,
                'total_bet': 620000,
                'total_return': 551800,
                'return_rate': 0.890,
                'profit': -68200
            }
        """
        query = """
            SELECT
                COUNT(*) as total_predictions,
                SUM(CASE WHEN is_hit THEN 1 ELSE 0 END) as total_hits,
                SUM(bet_amount) as total_bet,
                SUM(return_amount) as total_return
            FROM prediction_results
            WHERE strftime('%Y', date) = ?
              AND strftime('%m', date) = ?
        """

        params = [str(year), f"{month:02d}"]

        if model:
            query += " AND model = ?"
            params.append(model)

        result = self.db.fetch_one(query, params)

        return {
            'total_predictions': result['total_predictions'],
            'total_hits': result['total_hits'],
            'hit_rate': result['total_hits'] / result['total_predictions'],
            'total_bet': result['total_bet'],
            'total_return': result['total_return'],
            'return_rate': result['total_return'] / result['total_bet'],
            'profit': result['total_return'] - result['total_bet']
        }
```

#### 2.3 初日レース対応

**概要**:
- 節の初日は情報が少ないため予想が難しい
- 初日対応モデルでは前節のデータを重視

**実装イメージ**:
```python
def is_first_day_race(race_date, venue_code):
    """
    初日レースかどうかを判定

    ロジック:
    - 前日に同じ会場でレースがなければ初日
    """
    prev_day = race_date - timedelta(days=1)
    prev_races = get_races_by_date_and_venue(prev_day, venue_code)
    return len(prev_races) == 0

def first_day_adjusted_prediction(race_data, is_first_day):
    """
    初日レース対応予想

    初日の場合:
    - 全国勝率を重視（当地成績は参考程度）
    - モーター成績は前節のデータを使用
    - 選手のSTを重視（展示は参考程度）
    """
    if is_first_day:
        # 全国勝率の重み増加
        race_data['weight_national_rate'] = 0.7
        race_data['weight_local_rate'] = 0.3

        # 前節モーターデータを使用
        race_data['use_previous_motor_data'] = True
    else:
        # 通常時は当地成績を重視
        race_data['weight_national_rate'] = 0.4
        race_data['weight_local_rate'] = 0.6

    return race_data
```

#### 2.4 一番人気のみ抽出

**概要**:
- 各予想タイプの「最も自信がある買い目」のみを出力
- 的中率は下がるが、回収率が向上する可能性

**実装イメージ**:
```python
def extract_top_pick(predictions):
    """
    一番人気（最も自信のある買い目）のみ抽出

    Args:
        predictions: [
            ('1-2-3', {'score': 0.9, 'odds': 5.2}),
            ('1-2-4', {'score': 0.85, 'odds': 8.1}),
            ('1-3-4', {'score': 0.8, 'odds': 12.3})
        ]

    Returns:
        ('1-2-3', {'score': 0.9, 'odds': 5.2})
    """
    return predictions[0] if predictions else None

# 使用例
all_predictions = new_balance_model_prediction(race_data, odds_data)
top_pick = extract_top_pick(all_predictions)

print(f"本命買い目: {top_pick[0]} / オッズ: {top_pick[1]['odds']}倍")
```

### 学ぶべきポイント

1. **透明性の徹底**:
   - 全ての予想結果を記録・公開
   - 的中率・回収率をリアルタイム表示
   - ユーザーの信頼獲得

2. **複数モデルの提供**:
   - ユーザーの好みに応じた選択肢
   - 的中重視 vs 収益重視 vs バランス型
   - 各モデルの特性を明確化

3. **実績データの活用**:
   - 過去のパフォーマンスからモデル改善
   - ユーザーが自分で判断できる情報提供

---

## <a name="comparison"></a>3. 両サイトの比較

### 強み・弱みの比較表

| 項目 | kyoteibiyori | BOATERS |
|------|--------------|---------|
| **データ深度** | ◎ 超展開データが独自性高い | ○ 一般的な統計データ |
| **検索機能** | ◎ 柔軟な条件検索 | △ 特化した検索機能なし |
| **予想精度** | ○ 条件検索ベース | ◎ AI学習ベース |
| **透明性** | △ 実績データ非公開 | ◎ 全実績を完全公開 |
| **ユーザビリティ** | ○ データが多く初心者には難解 | ◎ シンプルで分かりやすい |
| **アラート機能** | ◎ 3つの専門アラート | × なし |
| **モデルの多様性** | △ 1つの検索ロジック | ◎ 4つの異なるモデル |

### 利用シーン別の使い分け

**kyoteibiyori が優れているシーン**:
- 特定条件のレースを探したい時
- 展開を予測したい時（前づけ、まくり）
- 場所の特性を知りたい時

**BOATERS が優れているシーン**:
- AI予想を参考にしたい時
- 実績データで信頼性を確認したい時
- 複数の戦略を試したい時

---

## <a name="implementation"></a>4. 実装への応用

### 統合システムの設計思想

両サイトの長所を組み合わせた「ハイブリッド予想システム」:

```
[データ収集層]
    ↓
[基礎統計層] ← kyoteibiyori方式
- コース別1着率
- 場所別特性
- 超展開データ（攻め方分析）
    ↓
[条件検索層] ← kyoteibiyori方式
- ガチガチレース検索
- 穴狙いレース検索
- アラート判定
    ↓
[AI予想層] ← BOATERS方式
- Hit型
- HighOdds型
- Profitable型
- NewBalance型
    ↓
[実績追跡層] ← BOATERS方式
- 予想結果の記録
- パフォーマンス分析
- モデル改善
    ↓
[UI/出力層]
- Streamlitダッシュボード
- レポート生成
```

### 実装優先順位（再確認）

#### Week 1: 基盤構築
1. 基礎統計計算（コース別勝率、選手成績）
2. 展示タイムデータ取得
3. データベース拡張（展示データテーブル追加）

#### Week 2: kyoteibiyori風機能
4. ガチガチレース検索
5. 穴狙いレース検索
6. 場所別分析（固い場/荒れる場ランキング）

#### Week 3: BOATERS風機能
7. Hit型AI予想
8. HighOdds型AI予想
9. Profitable型AI予想
10. NewBalance型AI予想

#### Week 4: 実績追跡・UI
11. 予想結果記録システム
12. パフォーマンストラッキング
13. Streamlit UIの拡張
14. レポート自動生成

### 差別化ポイント

両サイトにない独自機能のアイデア:

1. **リアルタイムオッズ変動追跡**:
   - オッズの急変を検知
   - 「金が動いている」買い目を検出

2. **ユーザーカスタム予想**:
   - 重視する要素を自分で設定
   - パーソナライズされた予想生成

3. **バックテスト機能**:
   - 過去データで戦略の有効性を検証
   - 「もしこの戦略で1年間買っていたら」をシミュレーション

4. **SNS連携**:
   - 予想の共有
   - 他ユーザーの成績を参考

5. **LINE Bot対応**:
   - レース直前に予想通知
   - アラート発動時に通知

---

## まとめ

### kyoteibiyori の本質
- **データ × 条件検索** = ユーザーが主体的にレースを選ぶ
- 「攻め方」という戦術レベルの分析が独自性

### BOATERS の本質
- **AI × 透明性** = 信頼できる予想システム
- 複数モデル提供で幅広いニーズに対応

### 我々のシステムの目指す姿
- **データ × AI × 透明性 × カスタマイズ性**
- kyoteibiyori の深いデータ分析
- BOATERS の複数予想モデルと実績追跡
- 独自の差別化機能（リアルタイム追跡、バックテスト）

→ **最強のボートレース予想システム**

---

## 参考資料

- kyoteibiyori: https://kyoteibiyori.com/
- BOATERS: https://boaters-boatrace.com/
- 作成日: 2025-10-30
- 作成者: Claude (AI Assistant)
