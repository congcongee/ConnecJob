"""구인표준직무기술서 직무 ↔ NCS 능력단위 연결 (TF-IDF 글자 n-gram 유사도).

고용24 표준직무기술서 API는 키워드 일치 검색이라 문장으로는 결과가 거의 없어(2026.11.03 확인), 로컬에서 유사도로 연결.
입력 : processed/job_desc_standard.csv (직종·표준직무내용·표준직무능력내용), processed/ncs_units.csv
출력 : processed/job_ncs.csv (utf-8-sig) - 직무 한 줄당 유사도 상위 능력단위 (최대 TOP_K개)

- 직무 텍스트 : 표준직무내용(2번 넣어 가중) + 표준직무능력내용('~하기' 제거)
- NCS 텍스트  : 능력단위명(3번 가중) + 세분류명 + 능력단위정의
- MIN_SCORE 미만, 또는 1위 점수의 REL_SCORE 배 미만은 버림
shortcut: 글자 n-gram 유사도라 뜻은 같고 표현이 다른 직무는 놓침 (예 '한식위생관리'), 정확도가 필요하면 임베딩 모델로 교체
"""
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

OUT_DIR = Path(__file__).parent.parent / "data" / "processed"
TOP_K = 3
MIN_SCORE = 0.35
REL_SCORE = 0.8


def blank(s):
    return s.replace("정보없음", "").fillna("")


def job_text(j):
    return j["표준직무내용"] + " " + j["표준직무내용"] + " " + j["표준직무능력내용"].str.replace(",", " ").str.replace("하기", " ")


def ncs_text(u):
    return (u["능력단위명"] + " ") * 3 + blank(u["NCS세분류명"]) + " " + blank(u["능력단위정의"])


def link(jt, ut):
    """→ [(직무 행 번호, 능력단위 행 번호, 점수, 순위)]"""
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 3), sublinear_tf=True).fit(pd.concat([jt, ut]))
    sim = linear_kernel(vec.transform(jt), vec.transform(ut))
    out = []
    for i, row in enumerate(sim):
        top = np.argsort(-row)[:TOP_K]
        best = row[top[0]]
        out += [(i, t, round(float(row[t]), 3), r) for r, t in enumerate(top, 1)
                if row[t] >= MIN_SCORE and row[t] >= best * REL_SCORE]
    return out


def _selftest():
    ut = pd.Series(["외래원무관리 병원행정", "입퇴원원무관리 병원행정", "평면 총형 가공 밀링가공"])
    jt = pd.Series(["외래원무관리 외래원무관리 접수하기", "전혀 관계없는 글"])
    assert link(jt, ut) == [(0, 0, link(jt, ut)[0][2], 1)]  # 1위만 남고, 관계없는 직무는 연결 없음


if __name__ == "__main__":
    _selftest()
    j = pd.read_csv(OUT_DIR / "job_desc_standard.csv", dtype=str)
    u = pd.read_csv(OUT_DIR / "ncs_units.csv", dtype=str)
    pairs = pd.DataFrame(link(job_text(j), ncs_text(u)), columns=["j", "u", "유사도", "순위"])

    df = pd.concat([j.loc[pairs["j"], ["직종", "표준직무내용"]].reset_index(drop=True),
                    u.loc[pairs["u"], ["능력단위코드", "능력단위명", "NCS대분류명", "NCS세분류명"]].reset_index(drop=True),
                    pairs[["유사도", "순위"]]], axis=1)
    df = df.drop_duplicates()  # 원본에 직종·직무내용은 같고 다른 열만 다른 줄이 있어 같은 연결이 반복됨
    df.to_csv(OUT_DIR / "job_ncs.csv", index=False, encoding="utf-8-sig")

    linked = pairs["j"].nunique()
    per_occ = df.groupby("직종")["능력단위코드"].nunique()
    print(f"직무 {len(j)}줄 중 {linked}줄 연결 ({linked / len(j):.0%}) | 직종 {per_occ.size}/{j['직종'].nunique()}개,"
          f" 직종당 능력단위 중앙값 {per_occ.median():.0f}개 | {len(df)}행 → job_ncs.csv")
