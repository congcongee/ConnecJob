"""경험 → 공고 추천 (벡터DB 검색 + 합격 가능성 재순위).

07_LLM/ch9_06(Chroma 저장·검색), ch9_12(Document + metadata) 방식.
실행 환경 : 수업용 conda 'llm' 환경 (langchain·chroma 설치됨), 키는 data/.env 의 OPENAI_API_KEY

  python recommend.py build   → processed/postings.csv 중 직무묶음이 있는 공고를 data/chroma 'postings' 에 저장
  python recommend.py eval    → 평가셋(eval_*.csv)으로 재현율@10 비교 + 대표 경험 5개 상위 5개 검토 파일

점수 (후보 = 유사도 상위 CANDIDATES 개)
  유사도 + 기술 충족률 × 0.1 + 직무묶음 일치 × 0.05   (평가셋 재현율@10 : 유사도만 0.74 → 0.79, 2026.11.06)
  - 기술 충족률 : 공고 기술태그 중 경험에 있는 비율 (공고에 태그가 없으면 0.5)
  - 마감일이 지난 공고는 제외
  - 경력 : 점수에 넣으면(-0.3) 유사도 폭(약 0~0.57)보다 커서 관련 공고가 묻힘 (재현율 0.48)
           → 점수 대신 '경력요구' 표시로 돌려주고, 화면에서 '신입 가능만' 필터로 거름
  - 범용 태그(GENERIC_TAGS)는 충족률에서 뺌 : 실제 공고 오탐 원인 1위 (재현율 0.78 → 0.76, 2026.11.06)
  - 최소 점수 컷은 안 씀 : 유사도 0.1 컷 재현율 0.59, 1위 대비 50% 컷 0.70 으로 정답이 더 많이 잘리고
    잘 맞던 경험(E15)이 잘리는 반면 안 맞던 경험(E11)은 그대로 10개 → 지금 점수로는 좋은/나쁜 공고가 안 갈림
  - 임베딩 글 = embed_text(본문) : 메타·양식 줄, 근무조건·전형·회사소개 섹션 제거. 제목만 남은(<100자) 공고는 -SHORT_PENALTY
    실제 공고 상위 10개 적합률 52% → 59%, 상위 5개 65% → 69% (2026.11.06, 기존 판정 재사용 + 새 공고 60건 추가 판정)
  - 직무묶음 14개로 세분화 + 임베디드·제어·보안·QA 추가 (DB 329 → 521건) : 상위 10개 72%, 상위 5개 80%, 평가셋 재현율 0.74
    '같은 묶음만 추천' 필터는 평가셋 재현율 0.11 (정답이 다른 묶음에도 많음) 이라 안 씀
  - LLM 재판정 (recommend(use_llm=True)) : 점수 상위 20개를 gpt-4o-mini 가 적합/부적합 + 이유로 판정, 적합만 최대 10개
    실제 공고 적합률 72% → 94% (125건 중 117건), 대신 경험당 평균 6.3개만 나옴 (맞는 공고가 적으면 적게)
    첫 프롬프트는 기술 스택·업종이 다르면 떨어뜨려 E01 이 2개만 나옴 → '직무 종류가 같으면 적합' 기준을 명시
"""
import re
import sys
import warnings
from datetime import date
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import BaseModel, Field

from tag_skills import TECH, categorize_job, find_tags

DATA_DIR = Path(__file__).parent.parent / "data"
CHROMA_DIR = str(DATA_DIR / "chroma")
load_dotenv(DATA_DIR / ".env")
CANDIDATES = 50
# 관련 없는 공고는 관련도가 0 아래로 나오는 게 정상인데 LangChain 이 결과마다 경고를 찍어서 끔
warnings.filterwarnings("ignore", message="Relevance scores must be between 0 and 1")
# 거의 모든 IT 공고에 나와 겹쳐도 적합 근거가 안 되는 태그 → 충족률·겹치는기술에서 뺌 (8명 판정 전원 지적)
GENERIC_TAGS = {"웹", "앱", "인공지능", "데이터베이스", "소프트웨어", "API", "백엔드", "프론트엔드", "빅데이터",
                "Python", "SQL", "MySQL", "Linux", "Excel", "Git"}
SHORT_PENALTY = 0.05
LLM_MODEL = "gpt-4o-mini"  # 07_LLM ch9_12 와 같은 모델
LLM_CANDIDATES = 20  # LLM 이 판정할 점수 상위 후보 수 (한 번 호출로 판정)
JUDGE_CHARS = 700  # 공고당 LLM 에 보여 줄 본문 길이 (8명 분석가도 본문 앞부분만 봄)
META_COLS = ["doc_id", "source", "title", "기업명", "기업규모", "시도", "경력", "마감일", "url", "기술태그", "직무묶음"]


def get_db(collection):
    return Chroma(collection_name=collection, embedding_function=OpenAIEmbeddings(model="text-embedding-3-large"),
                  persist_directory=CHROMA_DIR)


# 임베딩에서 뺄 것 (8명 판정 : 회사소개·양식 문구가 유사도를 흐림) - 반복 줄은 postings 에서 여러 회사에 똑같이 나온 줄
META_LINE = re.compile(r"^(직무|조건|급여조건|경력|최소학력|학력|근무지역|고용형태|접수방법|접수양식|전형단계): ")
TEMPLATE_LINE = re.compile(r"우리 회사에 대해|4줄 이내로 소개해주세요|우리 회사를 한 줄로 표현해주세요|허위사실이 있을 경우|자세히보기")
JOB_HEAD = re.compile(r"담당업무|주요 ?업무|업무 ?내용|하는 일|이런 일|자격 ?요건|지원 ?자격|우대 ?사항|이런 분|모집 ?부문|포지션")
SKIP_HEAD = re.compile(r"근무 ?조건|접수 ?방법|유의 ?사항|전형|제출 ?서류|복리 ?후생|혜택|채용 ?절차|회사 ?소개|기업 ?소개|이런 회사")


def embed_text(content):
    """공고 본문 → 임베딩할 글 : 메타·양식 줄을 빼고, 근무조건·전형·회사소개 섹션은 다음 업무 섹션 제목까지 건너뜀"""
    lines = [l for l in content.removeprefix("본문: ").replace("\n본문: ", "\n").split("\n")
             if not (META_LINE.match(l) or TEMPLATE_LINE.search(l))]
    keep, skipping = [], False
    for line in lines:
        if len(line) < 30 and JOB_HEAD.search(line):
            skipping = False
        elif len(line) < 30 and SKIP_HEAD.search(line):
            skipping = True
        if not skipping:
            keep.append(line)
    text = "\n".join(keep)
    # 업무 섹션 제목을 못 찾아 대부분 잘렸으면 섹션 건너뛰기 없이 (회사소개가 맨 앞이고 업무 제목이 없는 공고)
    return text if len(text) >= 100 else "\n".join(lines)


def to_documents(df):
    """데이터프레임 → Document 리스트 (ch9_12 : page_content + metadata)"""
    return [Document(page_content=embed_text(r["page_content"]), metadata={c: str(r[c]) for c in META_COLS}, id=r["doc_id"])
            for _, r in df.iterrows()]


def build(df, collection):
    db = get_db(collection)
    got = db.get()
    stored = dict(zip(got["ids"], got["documents"]))
    old = set(stored)
    # 새 공고 + 임베딩할 글이 바뀐 공고(embed_text 수정 등)는 지우고 다시 임베딩
    changed = df["doc_id"].isin(old) & (df["doc_id"].map(stored) != df["page_content"].map(embed_text))
    new = df[~df["doc_id"].isin(old) | changed]
    gone = (old - set(df["doc_id"])) | set(df.loc[changed, "doc_id"])
    if gone:  # 표에서 빠진 공고(교육생 모집글 등)는 DB 에서도 지움
        db.delete(ids=list(gone))
    if len(new):  # 이미 저장된 공고는 다시 임베딩하지 않음 (비용)
        db.add_documents(to_documents(new))
    print(f"[{collection}] 기존 {len(old)}건 - 삭제 {len(gone)}건 + 새로 저장 {len(new)}건")
    return db


def experience_text(exps):
    """경험 여러 개(dict 리스트) → 검색 문장"""
    return "\n".join(f"{e['제목']} {e['역할']} {e['기술스택'].replace(';', ', ')} {e['내용']}" for e in exps)


def score(sim, meta, my_tags, my_groups, today):
    job_tags = set(meta["기술태그"].split(";")) - {"정보없음"} - GENERIC_TAGS
    have = job_tags & my_tags
    coverage = len(have) / len(job_tags) if job_tags else 0.5
    group = bool(set(meta["직무묶음"].split(";")) & my_groups)
    expired = meta["마감일"] not in ("", "nan", "NaT") and meta["마감일"][:10] < today
    total = sim + 0.1 * coverage + 0.05 * group
    return (None if expired else total), sorted(have), sorted(job_tags - my_tags)


class Verdict(BaseModel):
    번호: int = Field(description="공고 번호")
    적합: bool = Field(description="이 경험을 가진 지원자가 지원할 만한 직무면 true")
    이유: str = Field(description="경험의 어떤 점이 공고의 어떤 업무와 맞는지(또는 안 맞는지) 한 문장")


class Verdicts(BaseModel):
    판정: list[Verdict]


# 8명 분석가 판정 기준을 그대로 옮김 : 직무가 맞는지만 보고, 경력 연차는 화면의 '경력요구' 표시로 따로 보여 줌
JUDGE_PROMPT = PromptTemplate(
    template="""너는 취업 컨설턴트다. 아래 지원자 경험과 채용공고들을 비교해 공고마다 적합 여부를 판정해라.
적합 : 공고의 실제 담당업무가 경험과 같은 직무 종류다 (예: 백엔드 개발, 풀스택 개발, 데이터 분석, 펌웨어 개발, 퍼포먼스 마케팅).
       언어·프레임워크가 달라도(Django 와 Spring 등), 회사 업종이 달라도(의료·제조·금융 등) 직무 종류가 같으면 적합이다.
부적합 : 직무 종류 자체가 다르다. 겹치는 단어(웹, AI, 데이터, 앱, CRM 등)만 있고 실제 업무가 다른 경우
         (예: 개발 경험인데 영업·현장직·강사·디자인·운영, 앱 CRM 캠페인 경험인데 매장 VIP 고객 응대)도 부적합이다.
경력 연차 요구는 판정에 넣지 마라.

[지원자 경험]
{experience}

[채용공고]
{jobs}""",
    input_variables=["experience", "jobs"],
)


def judge(text, recs, contents):
    """LLM 재판정 (07_LLM ch2 with_structured_output) → 번호별 (적합, 이유)"""
    jobs = "\n\n".join(f"[{i}] {r['title']}\n{c[:JUDGE_CHARS]}" for i, (r, c) in enumerate(zip(recs, contents)))
    llm = ChatOpenAI(model=LLM_MODEL, temperature=0).with_structured_output(Verdicts)
    res = llm.invoke(JUDGE_PROMPT.invoke({"experience": text, "jobs": jobs}))
    return {v.번호: (v.적합, v.이유) for v in res.판정}


def recommend(exps, db, k=10, rerank=True, today=None, use_llm=False):
    """경험 리스트 → 추천 [{doc_id, title, 기업명, 점수, 유사도, 겹치는기술, 부족기술, ...}] (점수순 k개)
    use_llm : 점수 상위 LLM_CANDIDATES 개를 LLM 이 판정해 적합한 것만 (k 개보다 적을 수 있음, '이유' 열 추가)"""
    text = experience_text(exps)
    my_tags = set(find_tags(text, TECH))
    my_groups = set(categorize_job(text))
    newbie = not any(e["유형"] == "경력" for e in exps)
    today = today or date.today().isoformat()
    out = []
    for doc, sim in db.similarity_search_with_relevance_scores(text, k=CANDIDATES):
        total, have, lack = score(sim, doc.metadata, my_tags, my_groups, today)
        if total is None:
            continue
        if len(doc.page_content) < 100:  # 본문이 이미지라 제목만 남은 공고 : 어느 경험과도 중간 유사도가 나와 상위에 끼어듦
            total -= SHORT_PENALTY
        out.append(({**doc.metadata, "점수": round(total if rerank else sim, 3), "유사도": round(sim, 3),
                     "겹치는기술": ";".join(have), "부족기술": ";".join(lack),
                     "경력요구": newbie and doc.metadata["경력"] == "경력"}, doc.page_content))
    out.sort(key=lambda rc: rc[0]["점수"], reverse=True)
    if not use_llm:
        return [r for r, _ in out[:k]]
    top = out[:LLM_CANDIDATES]
    verdicts = judge(text, [r for r, _ in top], [c for _, c in top])
    return [{**r, "이유": verdicts[i][1]} for i, (r, _) in enumerate(top) if verdicts.get(i, (False,))[0]][:k]


def _selftest():
    meta = {"기술태그": "Python;Django;AWS", "직무묶음": "백엔드 개발", "경력": "경력", "마감일": "2026-12-31"}
    total, have, lack = score(0.5, meta, {"Python", "Django"}, {"백엔드 개발"}, "2026-11-06")
    assert have == ["Django"] and lack == ["AWS"]  # 범용 태그 Python 은 안 셈
    assert abs(total - (0.5 + 0.1 * 1 / 2 + 0.05)) < 1e-9
    assert score(0.5, {**meta, "마감일": "2026-11-01"}, set(), set(), "2026-11-06")[0] is None  # 마감 지남
    body = "제목: 백엔드 개발자\n직무: 웹개발자\n본문: 우리 회사에 대해\n[담당업무]\n" + "Django API 개발 " * 8 + "\n근무조건\n주 5일\n[우대사항]\nAWS"
    assert embed_text(body) == "제목: 백엔드 개발자\n[담당업무]\n" + "Django API 개발 " * 8 + "\n[우대사항]\nAWS"
    assert embed_text("회사소개\n우리는 좋은 회사") == "회사소개\n우리는 좋은 회사"  # 다 잘리면 원문 유지


def evaluate():
    e = pd.read_csv(DATA_DIR / "eval_exps.csv", dtype=str)
    j = pd.read_csv(DATA_DIR / "eval_jobs.csv", dtype=str)
    a = pd.read_csv(DATA_DIR / "eval_answers.csv", dtype=str)
    text = j["채용제목"] + "\n" + j["모집직종"] + "\n" + j["직무내용"]
    jobs = pd.DataFrame({"doc_id": j["job_id"], "source": "평가셋", "title": j["채용제목"], "기업명": j["기업명"],
                         "기업규모": "정보없음", "시도": "정보없음", "경력": j["경력"], "마감일": "", "url": "",
                         "기술태그": text.map(lambda t: ";".join(find_tags(t, TECH)) or "정보없음"),
                         "직무묶음": text.map(lambda t: ";".join(categorize_job(t)) or "범위밖"), "page_content": text})
    db = build(jobs, "eval_jobs")
    answers = dict(zip(a["exp_id"], a["relevant_job_ids"].str.split(";")))
    rows, review = [], []
    for exp in e.to_dict("records"):
        want = set(answers[exp["exp_id"]])
        res = {m: recommend([exp], db, k=10, rerank=m == "재순위") for m in ["유사도만", "재순위"]}
        rows.append({"exp_id": exp["exp_id"], "제목": exp["제목"], "정답수": len(want),
                     **{m: len(want & {r["doc_id"] for r in res[m]}) / min(len(want), 10) for m in res}})
        if exp["exp_id"] in ("E01", "E05", "E06", "E07", "E17"):
            review += [{"exp_id": exp["exp_id"], "경험": exp["제목"], "순위": i, "job_id": r["doc_id"], "공고제목": r["title"],
                        "점수": r["점수"], "겹치는기술": r["겹치는기술"], "부족기술": r["부족기술"], "경력요구": r["경력요구"],
                        "정답여부": "정답" if r["doc_id"] in want else "", "판정(O/X)": "", "메모": ""}
                       for i, r in enumerate(res["재순위"][:5], 1)]
    r = pd.DataFrame(rows)
    print(r.round(2).to_string(index=False))
    print(f"평균 재현율@10 : 유사도만 {r['유사도만'].mean():.2f} / 재순위 {r['재순위'].mean():.2f}")
    pd.DataFrame(review).to_csv(DATA_DIR / "eval_top5_review.csv", index=False, encoding="utf-8-sig")
    print("검토 파일 → data/eval_top5_review.csv (25행)")


if __name__ == "__main__":
    _selftest()
    mode = sys.argv[1] if len(sys.argv) > 1 else "eval"
    if mode == "build":
        p = pd.read_csv(DATA_DIR / "processed" / "postings.csv", dtype=str).fillna("")
        build(p[p["직무묶음"] != "범위밖"], "postings")
    else:
        evaluate()
