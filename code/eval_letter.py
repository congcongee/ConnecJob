"""자소서 초안 검수 효과 측정 (cover_letter.write_draft 의 생성 → 검수 → 다시 쓰기 단계 전후 비교).
평가셋 경험 N개마다 점수 1위 공고(LLM 재판정 없이)에 '직무역량' 기본 문항(800자)으로 초안을 만들고 센다.
- 검수 전 : 첫 초안에서 검수 LLM 이 찾은 '경험에 없는 표현' 수 (write_draft 의 고친표현)
- 제거 : 그 표현이 다시 쓴 최종 초안에 그대로 남았는지 (공백 빼고 포함 여부)
- 새 지적 : 다시 쓴 초안을 검수했을 때 새로 잡힌 표현 수 (확인필요, 화면에 '확인 필요'로 표시)
  → 지적 수만 세면 안 됨 : 검수 LLM 이 매번 다른 문장을 잡고, 경험에 있는 내용('30% 단축')도 잡는 과잉 검출이 있음 (2026.11.13)
- 글자수 준수, 근거 경험 ID 가 입력 경험 안에만 있는지
  python eval_letter.py        → 표 출력 + data/eval_letter.csv (LLM 호출 약 경험당 3~4번)
한계 : 검수 전후를 같은 검수 LLM 이 판정 (사람 판정 아님)
"""
import sys

import pandas as pd

from cover_letter import DEFAULT_LIMIT, DEFAULT_QUESTIONS, write_draft
from recommend import DATA_DIR, get_db, recommend

N = 10


def squash(text):
    return "".join(str(text).split())

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N
    e = pd.read_csv(DATA_DIR / "eval_exps.csv", dtype=str).fillna("")
    db = get_db("postings")
    rows = []
    for exp in e.to_dict("records")[:n]:
        rec = recommend([exp], db, k=1, newbie_only=True)[0]
        try:
            out = write_draft([exp], rec, DEFAULT_QUESTIONS["직무역량"], DEFAULT_LIMIT, db)
        except ValueError as err:  # 입력에 없는 경험 ID 를 근거로 씀 = 지어낸 근거 → 화면에서는 버리고 다시 시도하게 함
            rows.append({"exp_id": exp["exp_id"], "공고": rec["title"][:30], "지어낸근거ID": str(err)})
            continue
        final = squash(out["초안"])
        rows.append({"exp_id": exp["exp_id"], "공고": rec["title"][:30], "검수전_근거없는표현": len(out["고친표현"]),
                     "최종초안에_남은지적": sum(squash(f) in final for f in out["고친표현"]),
                     "새지적_확인필요": len(out["확인필요"]), "지적내용": " / ".join(out["고친표현"]),
                     "확인필요내용": " / ".join(out["확인필요"]), "글자수": out["글자수"], "글자수준수": out["글자수"] <= out["제한"],
                     "근거ID정상": set(out["사용경험"]) <= {exp["exp_id"]}, "지어낸근거ID": ""})
        print(rows[-1])
    r = pd.DataFrame(rows)
    r.to_csv(DATA_DIR / "eval_letter.csv", index=False, encoding="utf-8-sig")
    ok = r[r["지어낸근거ID"] == ""]
    print(f"\n초안 {len(r)}개 (지어낸 근거 ID 로 버린 것 {len(r) - len(ok)}개)")
    before, left = ok["검수전_근거없는표현"].sum(), ok["최종초안에_남은지적"].sum()
    print(f"근거 없는 표현 : 검수 전 {before}개 (초안 {(ok['검수전_근거없는표현'] > 0).sum()}개에서) → 최종 초안에 남은 것 {left}개"
          f" (제거율 {1 - left / before:.0%}) | 다시 쓴 초안의 새 지적 {ok['새지적_확인필요'].sum()}개 → 화면 '확인 필요'")
    print(f"글자수 준수 {ok['글자수준수'].mean():.0%} · 평균 {ok['글자수'].mean():.0f}자 · 근거 ID 정상 {ok['근거ID정상'].mean():.0%}")
