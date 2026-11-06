"""추천 공고 맞춤 자기소개서 초안 (RAG : 벡터DB 의 공고 본문 + 사용자 경험 + 자소서 문항 → LLM 생성).

07_LLM ch2(PromptTemplate + Pydantic + with_structured_output), ch9_06(검색한 문서를 프롬프트에 넣어 생성) 방식.
실행 환경 : conda 'llm' (recommend.py 와 같음)

  python cover_letter.py E01   → 평가셋 경험 E01 의 추천 1위 공고로 문항 초안 1개 생성 (확인용)

품질 규칙 (작업일지 4단계 품질 점검)
- 입력에 없는 경험·수치·회사 정보를 지어내지 않음 (프롬프트 규칙 + 쓴 경험 ID 가 입력에 있는지 검사)
- 문단마다 [E01] 처럼 출처 경험 ID 표시 → 화면에서 근거 확인
- 생성 → 검수 LLM 이 경험 원문과 대조해 근거 없는 표현을 찾음 → 있으면(또는 글자수 초과면) 한 번 다시 쓰기
  → 그래도 남은 표현은 '확인필요' 로 돌려줘 화면에서 사용자가 확인
  (2026.11.06 E05·E06·E19·E11 확인 : '배치→실시간', 없던 '협업·채널 운영' 이 검수에서 걸려 빠짐.
   경험 정보가 짧으면 초안도 짧게(300자대) 나옴 → 지어내지 않은 결과, 부족한 정보는 '보완할점' 으로 안내)
문항 : 같은 회사 문항이 하이잡 데이터(processed/cover_letter_questions.csv, 공개 저장소에 없음)에 있으면 그 문항, 없으면 DEFAULT_QUESTIONS
"""
import re
import sys

import pandas as pd
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from recommend import DATA_DIR, get_db, recommend

QUESTIONS_PATH = DATA_DIR / "processed" / "cover_letter_questions.csv"
DEFAULT_LIMIT = 800  # 하이잡 문항 글자수 중앙값
# 07_LLM ch9_06 모델. gpt-4o-mini 는 다시 써도 경험에 없는 협업·채널 운영을 지어내고, 검수에서는 사실대로 쓴 문장까지 문제로 잡음
LETTER_MODEL = "gpt-4.1-mini"
# 하이잡 문항 중 회사 이름이 없는 흔한 문장 (문항유형별)
DEFAULT_QUESTIONS = {
    "직무역량": "지원 직무와 관련된 경험 및 이를 통해 발휘한 역량을 작성해 주세요.",
    "지원동기·포부": "지원 동기와 입사 후 이루고 싶은 목표를 작성해 주세요.",
    "도전·문제해결": "자기의 경험 가운데 가장 어려웠던 일은 무엇인지, 그리고 어려움을 극복한 과정을 구체적으로 기술하십시오.",
    "협업·갈등": "타인의 협력을 이끌어 내거나 타인을 주도적으로 도와서 공동의 목표를 달성했던 경험을 서술해주세요.",
}
EXP_ID = re.compile(r"\[(E\d+)\]")


def norm_company(name):
    return re.sub(r"\(주\)|㈜|주식회사|\s", "", str(name))


def get_questions(company):
    """회사 문항 [{문항유형, 문항, 글자수}] (하이잡에 그 회사가 있으면), 없으면 기본 문항"""
    if QUESTIONS_PATH.exists():
        q = pd.read_csv(QUESTIONS_PATH, dtype={"글자수": "Int64"})
        q = q[q["기업명"].map(norm_company) == norm_company(company)].drop_duplicates("문항")
        if len(q):
            return [{"문항유형": r.문항유형, "문항": r.문항, "글자수": int(r.글자수) if pd.notna(r.글자수) and r.글자수 > 0 else DEFAULT_LIMIT}
                    for r in q.itertuples()]
    return [{"문항유형": t, "문항": text, "글자수": DEFAULT_LIMIT} for t, text in DEFAULT_QUESTIONS.items()]


class Draft(BaseModel):
    초안: str = Field(description="자기소개서 답변. 문단마다 끝에 근거 경험 ID 를 [E01] 처럼 붙임")
    보완할점: str = Field(description="초안을 더 좋게 하려면 사용자가 직접 채워야 할 정보 (예: 본인 역할 비중, 구체적 수치)")


DRAFT_PROMPT = PromptTemplate(
    template="""너는 신입·주니어 취업 준비생의 자기소개서를 돕는 컨설턴트다.
아래 [채용공고]의 담당업무·자격요건에 맞춰 [지원자 경험]만 사용해 [문항]의 답변 초안을 써라.

규칙
1. [지원자 경험]에 없는 경험, 수치, 기술, 수상, 회사 정보는 절대 지어내지 마라. 모르는 내용은 쓰지 말고 '보완할점'에 적어라.
   경험에 적힌 결과를 다른 효과로 부풀리지도 마라 (예: '처리 시간 30% 단축'을 '서버 성능 개선·안정성 확보'로 바꾸지 말 것).
   공고의 요구사항(실시간 처리, 협업, 대용량 등)을 지원자가 이미 해 본 것처럼 쓰지 마라. 공고 내용은 '앞으로 하고 싶은 일'로만 써라.
2. 문단마다 끝에 그 문단의 근거가 된 경험 ID 를 [E01] 처럼 붙여라. 지원 동기처럼 경험이 아닌 문단은 [공고] 를 붙여라.
3. 공고의 담당업무 중 경험과 이어지는 업무를 구체적으로 언급해라.
4. 공백 포함 {limit}자 이내 (ID 표시 제외), 첫 문장은 핵심을 담은 한 줄 요약으로 시작해라.

[문항]
{question}

[채용공고] {company} - {title}
{posting}

[지원자 경험]
{experience}""",
    input_variables=["limit", "question", "company", "title", "posting", "experience"],
)


class Checked(BaseModel):
    근거없는표현: list[str] = Field(description="경험에 없는데 지원자가 한 일처럼 쓴 표현 (초안 원문 그대로 인용), 없으면 빈 리스트")


# 생성 규칙만으로는 공고 요구사항이 경험처럼 섞여 들어감 (E05 배치 → '실시간 파이프라인 경험') → 따로 대조
# 검수 LLM 에게 고쳐 쓰기까지 시키면 [E01] 표시를 지우고 새 거짓('서버 개발자와 협업')을 만들어서 찾기만 시킴
CHECK_PROMPT = PromptTemplate(
    template="""아래 [자기소개서 초안]의 각 문단을 [지원자 경험] 원문과 한 문장씩 대조해라.
경험 원문에 없는 행동·기술·성과·성격·협업을 지원자가 이미 한 것처럼 쓴 표현을 모두 찾아 원문 그대로 인용해라
(예: 배치 작업을 '실시간'으로, 혼자 한 일을 '협업'으로, 없던 채널 운영을 '다양한 채널 운영 경험'으로).
'~하고 싶다', '~에 기여하겠다' 같은 앞으로의 다짐과, 경험 원문을 바꿔 말한 표현은 문제 아니다.

[지원자 경험]
{experience}

[자기소개서 초안]
{draft}""",
    input_variables=["experience", "draft"],
)


def experience_block(exps):
    """경험 → 'E01 | 프로젝트 | 제목 | 역할 | 기술 | 내용 | 성과' 줄 (출처 ID 표시용)"""
    cols = ["유형", "제목", "기간", "역할", "기술스택", "내용", "성과"]
    return "\n".join(f"[{e['exp_id']}] " + " | ".join(f"{c}: {e[c]}" for c in cols if pd.notna(e.get(c)) and e.get(c))
                     for e in exps)


def text_length(draft):
    return len(EXP_ID.sub("", draft).replace("[공고]", "").strip())


def write_draft(exps, rec, question, limit=DEFAULT_LIMIT, db=None):
    """경험 + 추천 공고(recommend() 결과 1건) + 문항 → {초안, 보완할점, 글자수, 사용경험}"""
    db = db or get_db("postings")
    posting = db.get(ids=[rec["doc_id"]])["documents"][0]  # 임베딩한 글 (회사소개·양식 문구를 뺀 업무 중심 본문)
    llm = ChatOpenAI(model=LETTER_MODEL, temperature=0.3).with_structured_output(Draft)
    args = {"limit": limit, "question": question, "company": rec["기업명"], "title": rec["title"],
            "posting": posting[:2500], "experience": experience_block(exps)}
    checker = ChatOpenAI(model=LETTER_MODEL, temperature=0).with_structured_output(Checked)

    def check(text):
        return checker.invoke(CHECK_PROMPT.invoke({"experience": args["experience"], "draft": text})).근거없는표현

    draft = llm.invoke(DRAFT_PROMPT.invoke(args))
    flags, fixed = check(draft.초안), []
    notes = []
    if text_length(draft.초안) > limit:
        notes.append(f"이전 초안이 {text_length(draft.초안)}자라서 너무 깁니다. {int(limit * 0.9)}자 안팎으로 줄여라.")
    if flags:
        notes.append("이전 초안의 다음 표현은 경험에 없는 내용이라 빼거나 경험 원문의 사실로 바꿔라 : " + " / ".join(flags))
    if notes:  # 한 번만 다시 쓰기 (생성 단계가 [E01] 표시·글자수를 지키며 고침)
        args["question"] = question + "\n(" + " ".join(notes) + ")"
        draft = llm.invoke(DRAFT_PROMPT.invoke(args))
        fixed, flags = flags, check(draft.초안)
    used = sorted(set(EXP_ID.findall(draft.초안)))
    unknown = set(used) - {e["exp_id"] for e in exps}
    if unknown:  # 입력에 없는 경험 ID = 지어낸 근거
        raise ValueError(f"입력에 없는 경험 ID 사용 : {unknown}")
    return {"초안": draft.초안, "보완할점": draft.보완할점, "고친표현": fixed, "확인필요": flags,
            "글자수": text_length(draft.초안), "제한": limit, "사용경험": used}


def _selftest():
    assert text_length("요약입니다.[E01] 지원합니다.[공고]") == len("요약입니다. 지원합니다.")
    assert norm_company("(주)이노션") == norm_company("이노션 ") == "이노션"
    assert len(get_questions("세상에없는회사123")) == len(DEFAULT_QUESTIONS)
    block = experience_block([{"exp_id": "E01", "유형": "프로젝트", "제목": "예약 웹", "성과": float("nan")}])
    assert block == "[E01] 유형: 프로젝트 | 제목: 예약 웹"


if __name__ == "__main__":
    _selftest()
    e = pd.read_csv(DATA_DIR / "eval_exps.csv", dtype=str).set_index("exp_id", drop=False)
    exps = [e.loc[x].to_dict() for x in (sys.argv[1:] or ["E01"])]
    db = get_db("postings")
    rec = recommend(exps, db, k=1, use_llm=True)[0]
    q = get_questions(rec["기업명"])[0]
    print(f"공고 : {rec['기업명']} - {rec['title']}\n추천 이유 : {rec['이유']}\n문항({q['문항유형']}, {q['글자수']}자) : {q['문항']}\n")
    out = write_draft(exps, rec, q["문항"], q["글자수"], db)
    print(out["초안"], f"\n\n글자수 {out['글자수']}/{out['제한']} | 사용 경험 {out['사용경험']}\n보완할 점 : {out['보완할점']}")
    print("검수에서 고친 표현 :", out["고친표현"])
    print("다시 써도 남은 확인 필요 표현 :", out["확인필요"])
