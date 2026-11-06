"""출처별 채용공고 → 통합 공고 표 (RAG 지식베이스용).

출처마다 다른 열을 공통 열로 맞춰 concat·merge 하고 (01_python ch11 6절 병합과 연결),
07_LLM/ch9_12(metadata 활용) 의 백업 CSV 형식대로 page_content(본문) + metadata 열로 저장한다.

입력 : processed/seoul_jobs_api.csv, alio_recruit.csv, nara_recruit.csv, private_incruit.csv, private_jobda.csv,
       job_ncs.csv (서울시 모집직종 → NCS 대분류), company_size.csv (기업규모 태그)
출력 : processed/postings.csv (utf-8-sig) - 열 : doc_id, source, title, 기업명, category, 기업규모, 시도, 경력, 마감일, url,
       기술태그, 자격증태그 (tag_skills.py 사전 매칭, ';' 구분), page_content

공통 기준
- category : NCS 대분류명 (구분자 '·' 로 통일, ALIO 의 '보건.의료' → '보건·의료'), 검색 시 filter 에 사용
- 경력 : 신입 / 경력 / 관계없음 (신입·경력 둘 다면 관계없음)
- 기업규모 : 공공기관(ALIO·나라일터) 또는 company_size.csv 의 태그
- 문자 결측치는 '정보없음', 마감일은 날짜형 (상시채용·형식 불명은 결측)
"""
from pathlib import Path

import numpy as np
import pandas as pd

from tag_skills import tag_columns

OUT_DIR = Path(__file__).parent.parent / "data" / "processed"
COLS = ["doc_id", "source", "title", "기업명", "category", "기업규모", "시도", "경력", "마감일", "url", "page_content"]
YEAR = 2026  # 인크루트·잡다 마감일은 '11.29' 처럼 연도 없이 옴 (2026.11 수집)


def join_text(df, cols):
    """여러 열을 '열이름: 값' 줄로 합친 본문 ('정보없음'·결측은 건너뜀)"""
    def one(row):
        return "\n".join(f"{c}: {row[c]}" for c in cols if pd.notna(row[c]) and row[c] != "정보없음")
    return df.apply(one, axis=1)


def career(text):
    text = str(text)
    if "신입" in text and "경력" in text or "관계없음" in text:
        return "관계없음"
    return "신입" if "신입" in text else "경력" if "경력" in text else "정보없음"


def month_day(s):
    """'~11.15 (일)', '11.29(월) 마감 D-24' → 2026-11-15, '채용시' 등은 결측"""
    md = s.str.extract(r"(\d{1,2})\.(\d{1,2})")
    return pd.to_datetime(YEAR * 10000 + pd.to_numeric(md[0]) * 100 + pd.to_numeric(md[1]), format="%Y%m%d", errors="coerce")


def from_seoul():
    s = pd.read_csv(OUT_DIR / "seoul_jobs_api.csv", dtype=str)
    j = pd.read_csv(OUT_DIR / "job_ncs.csv")
    # 직종별 1순위 연결의 NCS 대분류 중 가장 많은 것 (groupby + value_counts)
    ncs = j[j["순위"] == 1].groupby("직종")["NCS대분류명"].agg(lambda x: x.value_counts().index[0])
    return pd.DataFrame({
        "doc_id": "seoul_" + s.index.astype(str), "source": "서울시", "title": s["채용제목"], "기업명": s["기업명"],
        "category": s["모집직종"].map(ncs), "시도": s["시도"], "경력": s["경력"].map(career),
        "마감일": pd.to_datetime(s["마감일자"], errors="coerce"), "url": np.nan,
        "page_content": join_text(s, ["채용제목", "모집직종", "직무내용", "경력", "최소학력", "전공", "자격면허", "컴퓨터활용능력", "우대조건", "근무지역"]),
    })


def from_alio():
    a = pd.read_csv(OUT_DIR / "alio_recruit.csv", dtype=str)
    return pd.DataFrame({
        "doc_id": "alio_" + a["채용공시일련번호"], "source": "ALIO", "title": a["채용공고제목"], "기업명": a["기관명"],
        "category": a["NCS분류"].str.replace(".", "·", regex=False), "기업규모": "공공기관", "시도": a["근무지역"],
        "경력": a["채용구분"].map(career), "마감일": pd.to_datetime(a["공고종료일"], errors="coerce"), "url": a["출처URL"],
        "page_content": join_text(a, ["채용공고제목", "NCS분류", "채용구분", "고용유형", "학력조건", "지원자격", "우대조건", "우대내용", "전형절차"]),
    })


def from_nara():
    n = pd.read_csv(OUT_DIR / "nara_recruit.csv", dtype=str)
    return pd.DataFrame({
        "doc_id": "nara_" + n["일련번호"], "source": "나라일터", "title": n["제목"], "기업명": n["선발기관명"],
        "기업규모": "공공기관", "마감일": pd.to_datetime(n["접수마감일"], errors="coerce"), "url": n["출처URL"],
        "page_content": join_text(n, ["제목", "기관구분", "채용정보구분", "선발예정직급"]),  # 원본에 공고 본문 없음
    })


def from_private(name, source):
    p = OUT_DIR / f"private_{name}.csv"
    if not p.exists():  # gitignore 대상이라 저장소만 받은 경우 없을 수 있음
        print(f"  [건너뜀] {p.name} 없음 → code/collect_private_jobs.py 로 만들기")
        return pd.DataFrame(columns=COLS)
    d = pd.read_csv(p, dtype=str)
    if name == "incruit":
        sido, car, text_cols = d["근무지역"], d["경력"], ["제목", "직무", "조건", "급여조건", "본문"]
    else:
        sido, car, text_cols = d["지역"], d["요약"], ["제목", "요약", "태그", "본문"]
    return pd.DataFrame({
        "doc_id": f"{name}_" + d["공고ID"], "source": source, "title": d["제목"], "기업명": d["기업명"],
        "시도": sido.str.split().str[0], "경력": car.map(career), "마감일": month_day(d["마감"]), "url": d["출처URL"],
        "page_content": join_text(d, text_cols),
    })


def _selftest():
    assert [career(x) for x in ["신입", "경력 1년↑", "신입+경력", "관계없음", "-"]] == ["신입", "경력", "관계없음", "관계없음", "정보없음"]
    got = month_day(pd.Series(["~11.15 (일)", "11.29(월) 마감 D-24", "채용시"]))
    assert got.iloc[0] == pd.Timestamp("2026-11-15") and got.iloc[1] == pd.Timestamp("2026-11-29") and pd.isna(got.iloc[2])
    t = join_text(pd.DataFrame({"a": ["x"], "b": ["정보없음"], "c": [np.nan]}), ["a", "b", "c"])
    assert t.iloc[0] == "a: x"


if __name__ == "__main__":
    _selftest()
    df = pd.concat([from_seoul(), from_alio(), from_nara(),
                    from_private("incruit", "인크루트"), from_private("jobda", "잡다")], ignore_index=True)[COLS]

    # 기업규모 : 공공기관이 아닌 출처는 company_size.csv 태그를 (출처, 기업명) 으로 merge
    size = pd.read_csv(OUT_DIR / "company_size.csv")[["출처", "기업명", "기업규모태그"]]
    df = df.merge(size, left_on=["source", "기업명"], right_on=["출처", "기업명"], how="left")
    df["기업규모"] = df["기업규모"].fillna(df["기업규모태그"])
    df = df.drop(columns=["출처", "기업규모태그"])
    df = pd.concat([df.drop(columns="page_content"), tag_columns(df["page_content"]), df["page_content"]], axis=1)

    str_cols = df.columns.drop("마감일")
    df[str_cols] = df[str_cols].fillna("정보없음")
    df = df.drop_duplicates(subset="doc_id")
    # 국비·부트캠프 교육생 모집글은 채용이 아니라 제외 (인크루트 고용형태 '교육생(연수생)', 8명 판정에서 1위 오탐 원인)
    trainee = df["page_content"].str.contains("교육생(연수생)", regex=False)
    print(f"교육생 모집글 제외 {trainee.sum()}건")
    df = df[~trainee]
    assert df["doc_id"].is_unique and (df["page_content"] != "").all()
    df.to_csv(OUT_DIR / "postings.csv", index=False, encoding="utf-8-sig")

    print(f"통합 공고 {df.shape} → postings.csv")
    print(pd.crosstab(df["source"], df["기업규모"]))
    print("category 있음 :", df.groupby("source")["category"].apply(lambda s: f"{(s != '정보없음').mean():.0%}").to_dict())
    print("기술태그 있음 :", df.groupby("source")["기술태그"].apply(lambda s: f"{(s != '정보없음').mean():.0%}").to_dict())
    print("자격증태그 있음 :", df.groupby("source")["자격증태그"].apply(lambda s: f"{(s != '정보없음').mean():.0%}").to_dict())
    print("많이 나온 기술 :", df["기술태그"].str.split(";").explode().value_counts().drop("정보없음", errors="ignore").head(12).to_dict())
    print("본문 길이 중앙값 :",df.groupby("source")["page_content"].apply(lambda s: int(s.str.len().median())).to_dict())
