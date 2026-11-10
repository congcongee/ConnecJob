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

from recommend import DATA_DIR, excerpt, get_db, recommend
from tag_skills import TECH, find_tags

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


def find_unsupported(experience, text):
    """검수 LLM : 경험 원문에 없는데 한 일처럼 쓴 표현 (초안·사용자 자소서 공통)"""
    checker = ChatOpenAI(model=LETTER_MODEL, temperature=0).with_structured_output(Checked)
    return checker.invoke(CHECK_PROMPT.invoke({"experience": experience, "draft": text})).근거없는표현


def text_length(draft):
    return len(EXP_ID.sub("", draft).replace("[공고]", "").strip())


def write_draft(exps, rec, question, limit=DEFAULT_LIMIT, db=None):
    """경험 + 추천 공고(recommend() 결과 1건) + 문항 → {초안, 보완할점, 글자수, 사용경험}"""
    db = db or get_db("postings")
    posting = db.get(ids=[rec["doc_id"]])["documents"][0]  # 임베딩한 글 (회사소개·양식 문구를 뺀 업무 중심 본문)
    llm = ChatOpenAI(model=LETTER_MODEL, temperature=0.3).with_structured_output(Draft)
    args = {"limit": limit, "question": question, "company": rec["기업명"], "title": rec["title"],
            "posting": excerpt(posting, 2500), "experience": experience_block(exps)}
    def check(text):
        return find_unsupported(args["experience"], text)

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


class Fix(BaseModel):
    원문: str = Field(description="고칠 문장 (사용자 자소서 원문 그대로 인용)")
    수정안: str = Field(description="고친 문장")
    이유: str = Field(description="왜 고치는지 한 문장 (공고 요구 역량 반영, 구체성, 근거 없는 표현 등)")


class Review(BaseModel):
    총평: str = Field(description="공고 요구 역량이 얼마나 드러나는지 2~3문장")
    수정제안: list[Fix] = Field(description="고칠 문장 최대 5개, 중요한 순")


REVIEW_PROMPT = PromptTemplate(
    template="""너는 신입·주니어 자기소개서 첨삭 컨설턴트다. [사용자 자소서]를 [채용공고]와 [문항]에 맞게 첨삭해라.
규칙
1. 수정안에는 [지원자 경험]에 있는 사실만 써라. 경험에 없는 경험·수치·협업을 새로 넣지 마라.
2. 공고 담당업무·자격요건과 이어지는데 자소서에서 빠졌거나 흐릿한 경험을 드러내도록 고쳐라.
3. 사용자 문체는 유지하고, 고칠 필요 없는 문장은 고르지 마라.
{hint}
[문항] {question} ({limit}자 이내)

[채용공고] {company} - {title}
{posting}

[지원자 경험]
{experience}

[사용자 자소서]
{letter}""",
    input_variables=["hint", "question", "limit", "company", "title", "posting", "experience", "letter"],
)


def letter_skills(rec, letter):
    """공고와 겹치는 내 기술(rec 겹치는기술) 중 자소서에 쓴 것 / 안 쓴 것"""
    have = [t for t in rec["겹치는기술"].split(";") if t]
    used = set(find_tags(letter, TECH))
    return [t for t in have if t in used], [t for t in have if t not in used]


def review_letter(exps, rec, question, letter, limit=DEFAULT_LIMIT, db=None):
    """사용자가 쓴 자소서 첨삭 → {총평, 수정제안, 반영기술, 빠진기술, 근거없는표현, 글자수, 제한}"""
    db = db or get_db("postings")
    posting = db.get(ids=[rec["doc_id"]])["documents"][0]
    used, missing = letter_skills(rec, letter)
    experience = experience_block(exps)
    # 첫 시험(E01)에서 사용자가 쓴 '팀원 10명과 협업' 을 수정안이 그대로 살림 → 검수 결과를 먼저 알려 주고 빼게 함
    flags = find_unsupported(experience, letter)
    hint = f"4. 경험에도 공고에도 있는데 자소서에 안 쓴 기술 : {', '.join(missing)} → 넣을 수 있으면 넣어라.\n" if missing else ""
    if flags:
        hint += f"5. 다음 표현은 경험 원문에 없다. 이 문장은 반드시 고르고, 수정안에서 그 내용을 빼라 : {' / '.join(flags)}\n"
    llm = ChatOpenAI(model=LETTER_MODEL, temperature=0).with_structured_output(Review)
    res = llm.invoke(REVIEW_PROMPT.invoke({"hint": hint, "question": question, "limit": limit, "company": rec["기업명"],
                                           "title": rec["title"], "posting": excerpt(posting, 2500), "experience": experience,
                                           "letter": letter}))
    fixes = [f.model_dump() for f in res.수정제안]
    # 수정안도 한 번 대조 : 그래도 남은 근거 없는 표현은 '확인필요' 로 화면에 표시
    left = find_unsupported(experience, "\n".join(f["수정안"] for f in fixes)) if fixes else []
    for f in fixes:
        f["확인필요"] = [x for x in left if x in f["수정안"]]
    return {"총평": res.총평, "수정제안": fixes, "반영기술": used, "빠진기술": missing,
            "근거없는표현": flags, "글자수": len(letter.strip()), "제한": limit}


def _selftest():
    assert letter_skills({"겹치는기술": "Django;Docker"}, "Django 로 예약 서비스를 만들었습니다") == (["Django"], ["Docker"])
    assert letter_skills({"겹치는기술": ""}, "아무 글") == ([], [])
    assert text_length("요약입니다.[E01] 지원합니다.[공고]") == len("요약입니다. 지원합니다.")
    assert norm_company("(주)이노션") == norm_company("이노션 ") == "이노션"
    assert len(get_questions("세상에없는회사123")) == len(DEFAULT_QUESTIONS)
    block = experience_block([{"exp_id": "E01", "유형": "프로젝트", "제목": "예약 웹", "성과": float("nan")}])
    assert block == "[E01] 유형: 프로젝트 | 제목: 예약 웹"


if __name__ == "__main__":
    _selftest()
    e = pd.read_csv(DATA_DIR / "eval_exps.csv", dtype=str).set_index("exp_id", drop=False)
    exps = [e.loc[x].to_dict() for x in ([a for a in sys.argv[1:] if not a.startswith("--")] or ["E01"])]
    db = get_db("postings")
    rec = recommend(exps, db, k=1, use_llm=True)[0]
    q = get_questions(rec["기업명"])[0]
    print(f"공고 : {rec['기업명']} - {rec['title']}\n추천 이유 : {rec['이유']}\n문항({q['문항유형']}, {q['글자수']}자) : {q['문항']}\n")
    if "--review" in sys.argv:  # python cover_letter.py E01 --review → 일부러 근거 없는 문장을 넣은 예시 자소서 첨삭
        letter = (f"저는 {exps[0]['제목']} 경험이 있습니다. {exps[0]['내용']}. "
                  "팀원 10명과 협업하며 대용량 트래픽을 처리했고, 이 경험을 살려 귀사에 기여하고 싶습니다.")
        out = review_letter(exps, rec, q["문항"], letter, q["글자수"], db)
        print(f"[예시 자소서]\n{letter}\n\n총평 : {out['총평']}\n반영 기술 {out['반영기술']} | 빠진 기술 {out['빠진기술']}")
        for f in out["수정제안"]:
            print(f"- {f['원문']}\n  → {f['수정안']}\n  ({f['이유']})")
        print("근거 없는 표현 :", out["근거없는표현"])
        sys.exit()
    out = write_draft(exps, rec, q["문항"], q["글자수"], db)
    print(out["초안"], f"\n\n글자수 {out['글자수']}/{out['제한']} | 사용 경험 {out['사용경험']}\n보완할 점 : {out['보완할점']}")
    print("검수에서 고친 표현 :", out["고친표현"])
    print("다시 써도 남은 확인 필요 표현 :", out["확인필요"])
