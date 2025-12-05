"""
BEFORE_SAFEスコアラーの単体テスト
"""

from src.analysis.before_safe_scorer import BeforeSafeScorer


def test_entry_score():
    """進入コーススコアのテスト"""
    scorer = BeforeSafeScorer()

    # 1コース奪取（3号艇が1コース）
    exhibition_courses = {1: 4, 2: 5, 3: 1, 4: 2, 5: 3, 6: 6}
    score = scorer._calc_entry_score(3, exhibition_courses)
    print(f"1コース奪取（3号→1コース）: {score}点")
    assert score == 12.0, f"Expected 12.0, got {score}"

    # 枠なり
    exhibition_courses = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6}
    score = scorer._calc_entry_score(3, exhibition_courses)
    print(f"枠なり（3号→3コース）: {score}点")
    assert score == 0.0, f"Expected 0.0, got {score}"

    # 外に追いやられる
    exhibition_courses = {1: 1, 2: 6, 3: 3, 4: 4, 5: 5, 6: 2}
    score = scorer._calc_entry_score(2, exhibition_courses)
    print(f"深く追いやられる（2号→6コース）: {score}点")
    assert score == -10.0, f"Expected -10.0, got {score}"

    print("[OK] 進入コーススコアテスト成功")


def test_parts_weight_score():
    """部品交換・体重スコアのテスト"""
    scorer = BeforeSafeScorer()

    # ピストン交換
    beforeinfo_data = {
        'parts_exchange': {
            1: {'piston': True, 'ring': False},
            2: {'P': True}
        },
        'weight_adjustments': {}
    }
    parts, weight = scorer._calc_parts_weight_score(1, beforeinfo_data)
    print(f"ピストン交換: parts={parts}点, weight={weight}点")
    assert parts == -12.0, f"Expected -12.0, got {parts}"

    # シリンダー交換
    beforeinfo_data = {
        'parts_exchange': {
            3: {'cylinder': True}
        },
        'weight_adjustments': {}
    }
    parts, weight = scorer._calc_parts_weight_score(3, beforeinfo_data)
    print(f"シリンダー交換: parts={parts}点")
    assert parts == -18.0, f"Expected -18.0, got {parts}"

    # 体重+3kg
    beforeinfo_data = {
        'parts_exchange': {},
        'weight_adjustments': {
            4: 3.0
        }
    }
    parts, weight = scorer._calc_parts_weight_score(4, beforeinfo_data)
    print(f"体重+3kg: weight={weight}点")
    assert weight == -3.0, f"Expected -3.0, got {weight}"

    print("[OK] 部品交換・体重スコアテスト成功")


def test_calculate_before_safe_score():
    """統合スコア計算のテスト"""
    scorer = BeforeSafeScorer(db_path='data/boatrace.db')

    # テスト用データ
    beforeinfo_data = {
        'is_published': True,
        'exhibition_courses': {1: 1, 2: 1, 3: 3, 4: 4, 5: 5, 6: 6},  # 2号が1コース奪取
        'parts_exchange': {
            2: {'piston': True}  # 2号がピストン交換
        },
        'weight_adjustments': {
            2: 2.0  # 2号が+2kg
        }
    }

    result = scorer.calculate_before_safe_score(132764, 2, beforeinfo_data)

    print(f"\n統合スコア計算結果:")
    print(f"  total_score: {result['total_score']}")
    print(f"  entry_score: {result['entry_score']}")
    print(f"  parts_score: {result['parts_score']}")
    print(f"  weight_score: {result['weight_score']}")
    print(f"  confidence: {result['confidence']}")
    print(f"  data_completeness: {result['data_completeness']}")

    # 期待値計算: entry=12.0, parts=-12.0, weight=-2.0
    # total = 0.6 * 12.0 + 0.4 * (-12.0 + -2.0) = 7.2 + 0.4 * (-14.0) = 7.2 - 5.6 = 1.6
    expected_total = 0.6 * 12.0 + 0.4 * (-12.0 + -2.0)
    print(f"\n期待値: {expected_total}")
    assert abs(result['total_score'] - expected_total) < 0.01, f"Expected {expected_total}, got {result['total_score']}"

    print("[OK] 統合スコア計算テスト成功")


def test_real_race():
    """実際のレースデータでのテスト"""
    scorer = BeforeSafeScorer(db_path='data/boatrace.db')

    # 実レースでテスト
    result = scorer.calculate_before_safe_score(132764, 1)

    print(f"\n実レーステスト（race_id=132764, pit=1）:")
    print(f"  total_score: {result['total_score']}")
    print(f"  entry_score: {result['entry_score']}")
    print(f"  data_completeness: {result['data_completeness']}")

    # データが取得できていることを確認
    assert result['data_completeness'] > 0, "Data should be loaded"

    print("[OK] 実レーステスト成功")


if __name__ == "__main__":
    print("=" * 80)
    print("BEFORE_SAFEスコアラー 単体テスト")
    print("=" * 80)
    print()

    try:
        test_entry_score()
        print()
        test_parts_weight_score()
        print()
        test_calculate_before_safe_score()
        print()
        test_real_race()
        print()
        print("=" * 80)
        print("全テスト成功")
        print("=" * 80)
    except AssertionError as e:
        print()
        print("=" * 80)
        print(f"テスト失敗: {e}")
        print("=" * 80)
        raise
