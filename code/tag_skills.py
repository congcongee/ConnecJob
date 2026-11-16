"""공고·경험 본문 → 기술·자격증 표준 태그 (사전 매칭).

07_LLM/ch9_12(metadata 활용) 의 키워드 사전 분류(categorize_content) 방식 :
{표준명: [키워드...]} 사전에서 본문에 나오는 키워드를 찾고, 등장 횟수(count) 순으로 정렬한 표준명 리스트를 돌려준다.
사전 : data/tech_dictionary.csv, data/cert_dictionary.csv (표준명, 분류, 별칭 '|' 구분)

ch9_12 의 'keyword in content' 를 그대로 쓰면 생기는 오탐 두 가지를 막음
1) 긴 키워드부터 찾고, 찾은 부분은 본문에서 지움 → '자바스크립트' 안의 '자바'(Java), 'C++' 안의 'C' 가 다시 안 걸림
2) 영문 키워드는 앞뒤가 영문자·숫자가 아닐 때만 → 'CCTV' 의 C, 'SMTS' 의 TS 제외 ('C언어', 'C/C++' 은 인정)
"""
import re
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data"


def get_dictionary(path):
    """사전 CSV → [(키워드, 표준명)] 긴 키워드 순 (표준명 자신도 키워드)"""
    d = pd.read_csv(path)
    pairs = [(k, r.표준명) for r in d.itertuples() for k in [r.표준명, *str(r.별칭).split("|")] if k and k != "nan"]
    return sorted(pairs, key=lambda p: len(p[0]), reverse=True)


def pattern(keyword):
    if keyword.isascii():
        return re.compile(rf"(?<![A-Za-z0-9]){re.escape(keyword)}(?![A-Za-z0-9])")
    return re.compile(re.escape(keyword))


def compile_dictionary(path):
    return [(pattern(k), std) for k, std in get_dictionary(path)]


def find_tags(content, dictionary):
    """content 에 나오는 표준명 리스트 (등장 횟수 내림차순, 같으면 먼저 찾은 순)"""
    if not isinstance(content, str):
        return []
    scores = {}
    for pat, std in dictionary:
        content, count = pat.subn(" ", content)  # 찾은 키워드는 지워서 더 짧은 키워드가 다시 못 걸리게
        if count:
            scores[std] = scores.get(std, 0) + count
    return [std for std, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)]


TECH = compile_dictionary(DATA_DIR / "tech_dictionary.csv")
CERT = compile_dictionary(DATA_DIR / "cert_dictionary.csv")


def get_job_groups(path):
    """직무묶음 사전 CSV → {묶음: [(키워드 패턴, 가중치)]} (ch9_12 get_category 의 가중치 사전)"""
    d = pd.read_csv(path)
    return {g: [(pattern(k), w) for k, w in zip(part["키워드"], part["가중치"])] for g, part in d.groupby("직무묶음", sort=False)}


JOB_GROUPS = get_job_groups(DATA_DIR / "job_group_dictionary.csv")
MIN_GROUP_SCORE = 3  # 'AI' 한 번(1점) 같은 흔한 말만으로는 묶음을 붙이지 않음 (직무명 1개 = 3점)


def categorize_job(content, top_k=None):
    """content 의 직무묶음 리스트 (ch9_12 categorize_content 방식 : 등장 횟수 × 가중치 점수순, MIN_GROUP_SCORE 이상만)"""
    if not isinstance(content, str):
        return []
    scores = {}
    for group, weighted in JOB_GROUPS.items():
        score = sum(len(pat.findall(content)) * w for pat, w in weighted)
        if score >= MIN_GROUP_SCORE:
            scores[group] = score
    groups = [g for g, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)]
    return groups[:top_k] if top_k is not None else groups


# 공고 제목에 이 말이 있어야 본문 키워드로 직무묶음을 붙임 (2026.11.16)
# 본문만 보면 취업박람회·여러 부서 공채·생산직 본문의 'PLC'·'방화벽' 같은 말에 걸려 요양보호사·물류센터 공고까지 묶음이 붙었음
DEV_TITLE = re.compile(r"(?<!사업)개발|Developer|DevOps|엔지니어|Engineer|프로그래머|Programmer|소프트웨어|(?<![A-Za-z])SW(?![A-Za-z])|S/W"
                       r"|분석|Analyst|Analytics|Scientist|사이언티스트|정보\s?보안|사이버\s?보안|IT\s?보안|보안\s?(엔지니어|솔루션|관제|컨설|기술)"
                       r"|Security|포렌식|네트워크|서버|인프라|클라우드|Cloud|전산|(?<![A-Za-z])QA(?![A-Za-z])|테스트"
                       r"|아키텍|Architect|풀스[택텍]|Tech Lead|Data Platform|데이터 플랫폼|Java|자바"
                       r"|AI\s?(전문)?(인력|전문가|박사|연구|기술|Expert)", re.I)  # 'AI 디자이너·라벨러·콘텐츠' 는 안 걸리게 AI 단독은 뺌
MARKETING_TITLE = re.compile(r"마케터|마케팅|Marketer|Marketing|그로스|Growth|퍼포먼스|(?<![A-Za-z])CRM(?![A-Za-z])", re.I)
MARKETING_GROUPS = {"퍼포먼스·그로스 마케팅", "데이터 기반 마케팅"}


def posting_groups(title, content):
    """공고의 직무묶음 : 본문 점수로 고른 묶음 중 제목이 받쳐 주는 것만
    (제목에 그 묶음 키워드가 있거나, 제목에 그 계열 직무명 - 개발·엔지니어·분석·보안 … / 마케팅 계열은 마케터·그로스 … - 이 있을 때)"""
    title = title if isinstance(title, str) else ""
    if "박람회" in title:  # 취업박람회 공고는 여러 회사·직무를 한 글에 모아 둔 것이라 직무를 정할 수 없음
        return []
    keep = []
    for g in categorize_job(content):
        signal = MARKETING_TITLE if g in MARKETING_GROUPS else DEV_TITLE
        if signal.search(title) or any(pat.search(title) for pat, _ in JOB_GROUPS[g]):
            keep.append(g)
    return keep


def tag_columns(text, title=None):
    """본문 Series → 기술태그·자격증태그·직무묶음 열 ('Python;Django', 없으면 '정보없음', 직무묶음 없으면 '범위밖')
    title(공고 제목 Series)을 주면 직무묶음은 posting_groups 규칙으로"""
    join = lambda tags, empty="정보없음": ";".join(tags) if tags else empty
    groups = text.map(categorize_job) if title is None else pd.Series(map(posting_groups, title, text), index=text.index)
    return pd.DataFrame({"기술태그": text.map(lambda t: join(find_tags(t, TECH))),
                         "자격증태그": text.map(lambda t: join(find_tags(t, CERT))),
                         "직무묶음": groups.map(lambda g: join(g, "범위밖"))})


def _selftest():
    assert find_tags("자바스크립트와 React", TECH) == ["JavaScript", "React"]   # '자바' → Java 아님
    assert find_tags("C/C++ 및 C언어, CCTV 설치", TECH) == ["C", "C++"]        # CCTV 의 C 제외
    assert find_tags("MySQL, python, 파이썬", TECH) == ["Python", "MySQL"]   # 등장 횟수 순
    assert find_tags("FreeRTOS 기반, RTOS 경험", TECH) == ["FreeRTOS", "RTOS"]  # FreeRTOS 안의 RTOS 는 따로 안 셈
    assert find_tags("운전면허 2종보통 소지", CERT) == ["운전면허 2종보통"]      # '운전면허' 따로 안 걸림
    assert find_tags("정처기 우대", CERT) == ["정보처리기사"]
    assert find_tags(float("nan"), TECH) == []
    assert categorize_job("LLM 기반 챗봇 개발, PyTorch") == ["LLM·생성형AI 개발"]  # PyTorch(2점)만으론 ML 묶음 안 붙음
    assert categorize_job("일자리박람회 AI체험·AI취업지원·AI상담, 청소 업무") == []   # 흔한 말 AI 는 사전에 없음
    assert categorize_job("퍼포먼스 마케터 - 메타 광고 ROAS 관리") == ["퍼포먼스·그로스 마케팅"]
    assert categorize_job("Django REST API 웹 개발")[0] == "웹·백엔드 개발"  # 직무묶음 이름은 웹·벡터DB 와 같은 15개 체계
    plc = "PLC, MES 설비 운전, 사료 배합"
    assert categorize_job(plc) == ["제어·자동화"] and posting_groups("반려견 사료 배합 생산 사원모집", plc) == []  # 제목이 생산직
    assert posting_groups("자동제어 PLC기술자 신입", plc) == ["제어·자동화"]          # 제목에 묶음 키워드(PLC)
    assert posting_groups("[DRB] 사업개발 담당", "웹 개발 경험") == []                # '사업개발'은 개발 직무 아님
    assert posting_groups("경력직 JAVA 개발자 채용", "웹 개발 경험") == ["웹·백엔드 개발", "프론트엔드 개발"]
    assert posting_groups("브랜드 마케팅 사원", "퍼포먼스 마케팅, ROAS") == ["퍼포먼스·그로스 마케팅"]
    assert posting_groups("브랜드 마케팅 사원", "LLM 챗봇 콘텐츠") == []              # 마케팅 제목에 개발 묶음은 안 붙임
    assert posting_groups("[부평구 채용박람회] 정보보안 엔지니어", "정보보안, 방화벽") == []  # 박람회 모음 공고
    assert posting_groups("시설 보안요원 모집", "정보보안, 방화벽 관리") == []         # 경비 '보안'은 IT 보안 아님


if __name__ == "__main__":
    _selftest()
    # 확인 : 평가셋 경험의 '기술스택' 은 사람이 적은 정답 태그 → 같은 경험 '내용+기술스택' 에서 얼마나 찾는지
    e = pd.read_csv(DATA_DIR / "eval_exps.csv")
    want = e["기술스택"].str.split(";")
    got = (e["기술스택"].str.replace(";", ", ") + " " + e["내용"]).map(lambda t: find_tags(t, TECH) + find_tags(t, CERT))
    hit = [sum(find_tags(w, TECH) + find_tags(w, CERT) != [] for w in ws) for ws in want]
    print(f"경험 기술스택 {want.str.len().sum()}개 중 사전에 있어 태그된 것 {sum(hit)}개 ({sum(hit) / want.str.len().sum():.0%})")
    miss = sorted({w for ws in want for w in ws if not (find_tags(w, TECH) + find_tags(w, CERT))})
    print("사전에 없는 기술스택 :", miss)
    j = pd.read_csv(DATA_DIR / "eval_jobs.csv")
    t = tag_columns(j["채용제목"] + " " + j["직무내용"])
    print(f"평가셋 공고 {len(j)}개 중 기술태그 있음 {(t['기술태그'] != '정보없음').sum()}개, 자격증태그 있음 {(t['자격증태그'] != '정보없음').sum()}개")
    print(pd.concat([j[["job_id", "채용제목"]], t], axis=1).sample(6, random_state=0).to_string())
