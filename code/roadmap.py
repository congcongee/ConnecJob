"""부족 역량 → 준비 로드맵 (작업일지 4단계 5단계 : '관심 직무 공고 중 요구 비율' 기준 우선순위).

실행 환경 : conda 'llm' (recommend.py 와 같음)

  python roadmap.py E01        → 평가셋 경험 E01 의 로드맵 (요구 비율표 + LLM 학습·미니 프로젝트 제안)
  python roadmap.py E01 --nollm → 요구 비율표만 (API 호출 없음)

우선순위
- 관심 직무 = 경험에서 찾은 직무묶음 (없으면 추천 공고들의 직무묶음, 화면에서 고르면 groups 로 넘김)
- 대상 공고 = processed/postings.csv 중 그 직무묶음이고 마감 안 지난 공고
- 요구 비율 = 대상 공고 중 그 기술(자격증) 태그가 있는 비율, 내 경험에 이미 있는 건 뺌
- '웹·앱·백엔드' 같은 직무영역 태그는 배울 기술이 아니라서 뺌 (Python·SQL·Git 처럼 구체적인 건 남김)
- 운전면허는 IT 공고에도 현장 방문 조건으로 붙어 나와서 자격증 순위에서 뺌
"""
import sys
from collections import Counter
from datetime import date

import pandas as pd
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from recommend import DATA_DIR, GENERIC_TAGS, LLM_MODEL, experience_text
from tag_skills import CERT, TECH, categorize_job, find_tags

VAGUE_TAGS = GENERIC_TAGS - {"Python", "SQL", "MySQL", "Linux", "Excel", "Git"}
TOP = 5  # 로드맵에 올릴 부족 기술 수


def tag_set(cell):
    return set(str(cell).split(";")) - {"정보없음", "nan", ""}


def load_postings(today=None):
    p = pd.read_csv(DATA_DIR / "processed" / "postings.csv", dtype=str).fillna("")
    today = today or date.today().isoformat()
    return p[(p["직무묶음"] != "범위밖") & ~((p["마감일"] != "") & (p["마감일"].str[:10] < today))]


def ranked(target, col, mine, skip):
    """대상 공고 중 태그별 요구 비율 [(태그, 비율, 공고수)] (내 태그·skip 태그 제외, 비율 높은 순)"""
    count = Counter(t for cell in target[col] for t in tag_set(cell) - mine if not skip(t))
    return [(t, round(n / len(target), 3), n) for t, n in count.most_common()]


def roadmap(exps, recs=None, groups=None, postings=None, top=TOP):
    """경험 (+ 추천 결과) → {직무묶음, 대상공고수, 부족기술 [{기술, 요구비율, 공고수, 추천공고부족}], 추천자격증 [...]}"""
    text = experience_text(exps)
    my_tech, my_cert = set(find_tags(text, TECH)), set(find_tags(text, CERT))
    groups = set(groups or categorize_job(text) or [g for r in recs or [] for g in tag_set(r["직무묶음"])])
    postings = load_postings() if postings is None else postings
    target = postings[postings["직무묶음"].map(lambda g: bool(tag_set(g) & groups))]
    rec_lack = Counter(t for r in recs or [] for t in tag_set(r["부족기술"]))
    if not len(target):
        return {"직무묶음": sorted(groups), "대상공고수": 0, "부족기술": [], "추천자격증": []}
    tech = [{"기술": t, "요구비율": ratio, "공고수": n, "추천공고부족": rec_lack[t]}
            for t, ratio, n in ranked(target, "기술태그", my_tech, lambda t: t in VAGUE_TAGS)]
    # 같은 요구 비율이면 내 추천 공고에서 더 많이 빠진 기술 먼저
    tech.sort(key=lambda d: (d["요구비율"], d["추천공고부족"]), reverse=True)
    cert = [{"자격증": t, "요구비율": ratio, "공고수": n}
            for t, ratio, n in ranked(target, "자격증태그", my_cert, lambda t: t.startswith("운전면허"))]
    return {"직무묶음": sorted(groups), "대상공고수": len(target), "부족기술": tech[:top], "추천자격증": cert[:3]}


class Step(BaseModel):
    기술: str = Field(description="부족 기술 이름 (입력 그대로)")
    학습방법: str = Field(description="무엇부터 어떻게 공부할지 한두 문장 (공식 문서·튜토리얼 수준, 없는 강의 이름 금지)")
    미니프로젝트: str = Field(description="지원자의 기존 경험을 확장해 이 기술을 써 볼 1~2주짜리 작은 프로젝트 한 문장")


class Plan(BaseModel):
    단계: list[Step]


PLAN_PROMPT = PromptTemplate(
    template="""너는 신입 개발·데이터·마케팅 직무 취업 준비를 돕는 멘토다.
[부족 기술]을 위에서부터 우선순위대로, 기술마다 학습 방법과 미니 프로젝트를 제안해라.
규칙
1. 미니 프로젝트는 [지원자 경험]에 있는 프로젝트·기술을 이어서 확장하는 형태로 제안해라.
2. 실제로 있는지 모르는 강의명·책 제목·URL 은 쓰지 마라. '공식 문서의 튜토리얼' 처럼 일반적으로 써라.
3. 기술 순서와 이름은 바꾸지 마라.

[관심 직무] {groups}
[부족 기술] (관심 직무 공고 중 요구 비율)
{lacks}

[지원자 경험]
{experience}""",
    input_variables=["groups", "lacks", "experience"],
)


def study_plan(exps, plan):
    """roadmap() 결과의 부족기술 → 기술별 학습방법·미니프로젝트 (LLM 한 번 호출)"""
    if not plan["부족기술"]:
        return []
    lacks = "\n".join(f"- {d['기술']} ({d['요구비율']:.0%})" for d in plan["부족기술"])
    llm = ChatOpenAI(model=LLM_MODEL, temperature=0.3).with_structured_output(Plan)
    res = llm.invoke(PLAN_PROMPT.invoke({"groups": ", ".join(plan["직무묶음"]), "lacks": lacks,
                                         "experience": experience_text(exps)}))
    return [s.model_dump() for s in res.단계]


def _selftest():
    p = pd.DataFrame({"직무묶음": ["백엔드 개발", "백엔드 개발", "백엔드 개발;데이터 엔지니어", "디자인"],
                      "기술태그": ["Django;AWS;웹", "Spring;AWS", "AWS;Docker", "Figma"],
                      "자격증태그": ["정보처리기사", "운전면허", "정보없음", "정보없음"], "마감일": ""})
    exps = [{"제목": "예약 웹", "역할": "백엔드 개발", "기술스택": "Python;Django", "내용": "Django API 개발"}]
    recs = [{"직무묶음": "백엔드 개발", "부족기술": "Docker"}]
    out = roadmap(exps, recs, postings=p)
    assert out["대상공고수"] == 3 and "백엔드 개발" in out["직무묶음"]
    # AWS 3/3 1위, Docker·Spring 1/3 동률이면 추천 공고에서 빠진 Docker 먼저, 내 기술 Django·직무영역 '웹' 은 빠짐
    assert [d["기술"] for d in out["부족기술"]] == ["AWS", "Docker", "Spring"]
    assert out["부족기술"][0]["요구비율"] == 1.0
    assert [d["자격증"] for d in out["추천자격증"]] == ["정보처리기사"]  # 운전면허 제외
    assert roadmap(exps, postings=p, groups=["없는묶음"])["대상공고수"] == 0


if __name__ == "__main__":
    _selftest()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    e = pd.read_csv(DATA_DIR / "eval_exps.csv", dtype=str).set_index("exp_id", drop=False)
    exps = [e.loc[x].to_dict() for x in (args or ["E01"])]
    plan = roadmap(exps)
    print(f"관심 직무 {plan['직무묶음']} | 대상 공고 {plan['대상공고수']}건")
    for d in plan["부족기술"]:
        print(f"  {d['기술']:<12} {d['요구비율']:>5.0%} ({d['공고수']}건)")
    print("추천 자격증 :", [f"{c['자격증']} {c['요구비율']:.0%}" for c in plan["추천자격증"]])
    if "--nollm" not in sys.argv:
        for s in study_plan(exps, plan):
            print(f"\n[{s['기술']}] {s['학습방법']}\n  미니 프로젝트 : {s['미니프로젝트']}")
