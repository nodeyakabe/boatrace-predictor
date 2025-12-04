"""前走成績スコアラーのテスト"""
import sys
sys.path.append('.')

from src.scoring.prev_race_scorer import PrevRaceScorer

scorer = PrevRaceScorer()

print("=== 前走成績スコアラー テスト ===")

test_race_id = 133159

for pit in range(1, 7):
    result = scorer.calculate_prev_race_score(test_race_id, pit)
    score = result.get('prev_race_score', 0)
    rank = result.get('prev_rank', '?')
    course = result.get('prev_course', '?')
    st = result.get('prev_st', '?')
    print(f"艇{pit}: 前走{rank}着（{course}コース、ST={st}）→ スコア={score:.1f}点")
