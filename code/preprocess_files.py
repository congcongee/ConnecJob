"""파일 데이터 4종 전처리 (01_python ch11·ch13 방식).

data/raw/ 의 cp949 원본을 읽어 data/processed/ 에 utf-8-sig 로 저장.
- 서울시 일자리포털 채용정보            → processed/seoul_jobs.csv
- 고용형태공시대상기업_20251231          → processed/employment_disclosure.csv
- 구인표준직무기술서_20250901            → processed/job_desc_standard.csv
- 국민연금 가입 사업장 내역_20261023     → processed/nps_workplace.csv

전처리 순서 (ch13 사례연구 흐름)
1) 결측치 확인 (isna().sum())
2) 문자 정리 : 공백 정리, 콤마 제거(str.replace) 후 숫자 변환(pd.to_numeric(errors='coerce'))
3) 날짜 변환 (to_datetime)
4) 파생열 (str.extract / map / apply)
5) 결측치 대체 (fillna) : 문자는 '정보없음'
6) 불필요한 열 제거 (drop), 중복 제거 (drop_duplicates)
7) to_csv 저장
"""
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
OUT_DIR = DATA_DIR / "processed"


def clean_text(df):
    """문자열 열 : 연속 공백 → 한 칸, 앞뒤 공백 제거, 빈 문자열 → 결측치"""
    obj = df.select_dtypes("object").columns
    df[obj] = df[obj].apply(lambda s: s.str.replace(r"\s+", " ", regex=True).str.strip()).replace("", np.nan)
    return df


def preprocess_seoul_jobs(df):
    df = clean_text(df.copy())

    # 날짜 : '26-08-31' → 2026-08-31, 마감일자 '채용시까지 26-10-30' → 상시채용여부 + 마감일
    df["등록일자"] = pd.to_datetime(df["등록일자"], format="%y-%m-%d")
    df["상시채용여부"] = df["마감일자"].str.contains("채용시까지").map({True: "Y", False: "N"})
    df["마감일자"] = pd.to_datetime(df["마감일자"].str.extract(r"(\d{2}-\d{2}-\d{2})")[0], format="%y-%m-%d")

    # 임금조건 '연봉30,000,000원 이상 ~ 40,000,000원 이하, 면접 후 재조정 가능'
    #   → 임금형태(연봉/월급/시급/일급), 최소임금, 최대임금 (콤마 제거 후 숫자), 임금협의가능
    wage = df["임금조건"].str.extract(r"^(연봉|월급|시급|일급)\s*([\d,]+)원 이상(?: ~ ([\d,]+)원 이하)?")
    df["임금형태"] = wage[0]
    df["최소임금"] = pd.to_numeric(wage[1].str.replace(",", ""), errors="coerce")
    df["최대임금"] = pd.to_numeric(wage[2].str.replace(",", ""), errors="coerce")
    df["임금협의가능"] = df["임금조건"].str.contains("재조정").map({True: "Y", False: "N"})

    # 고용형태 '기간의 정함이 있는 근로계약3 개월/ ...' → 고용구분(정규/계약), 계약기간(개월)
    df["고용구분"] = df["고용형태"].map(lambda x: "계약" if "정함이 있는" in x else "정규", na_action="ignore")
    df["계약기간(개월)"] = pd.to_numeric(df["고용형태"].str.extract(r"근로계약(\d+) ?개월")[0], errors="coerce")

    # 모집직종 '응용 소프트웨어 개발자(133200)' → 코드는 직종코드 열에 있으므로 이름만
    df["모집직종"] = df["모집직종"].str.replace(r"\(\d+\)$", "", regex=True).str.strip()
    df["모집인원"] = pd.to_numeric(df["모집인원"], errors="coerce").astype("Int64")  # API 대량 수집분엔 빈 값이 있어 결측 허용 정수
    # 주소 앞 우편번호 '(08377) ' / '08377 ' 제거
    for c in ["회사주소", "근무예정지"]:
        df[c] = df[c].str.replace(r"^\(?\d{5}\)?\s*", "", regex=True)
    df["시도"] = df["근무지역"].map(lambda x: x.split()[0], na_action="ignore")

    # 값이 하나뿐인 열은 분석에 쓸모없어 제거 (연금4대보험 : 전부 동일)
    df = df.drop(columns=[c for c in df.columns if df[c].nunique(dropna=False) == 1])

    # 결측치 대체 : 문자 열만 '정보없음' (임금·계약기간·날짜 숫자 결측은 해당없음 의미라 그대로 둠)
    obj = df.select_dtypes("object").columns
    df[obj] = df[obj].fillna("정보없음")
    return df.drop_duplicates().reset_index(drop=True)


def preprocess_disclosure(df):
    df = clean_text(df.copy())
    num_cols = df.columns[3:14]  # 상시근로자총인원수 ~ 기간정함있는단기간여성근로자수
    df[num_cols] = df[num_cols].apply(lambda s: pd.to_numeric(s.str.replace(",", ""), errors="coerce")).astype("int")
    df["등록년도"] = df["등록년도"].astype("int")
    df["시도"] = df["지역명"].map(lambda x: x.split()[0])

    # 파생열 : 소속근로자수, 기간제비율, 소속외근로자수, 소속외비율
    df["소속근로자수"] = df[["기간정함없는남성근로자수", "기간정함없는여성근로자수",
                       "기간정함있는남성근로자수", "기간정함있는여성근로자수"]].sum(axis=1)
    df["기간제비율"] = (df["기간정함있는남성근로자수"] + df["기간정함있는여성근로자수"]) / df["소속근로자수"].replace(0, np.nan)
    df["소속외근로자수"] = df["소속외남성근로자수"] + df["소속외여성근로자수"]
    df["소속외비율"] = df["소속외근로자수"] / (df["소속근로자수"] + df["소속외근로자수"]).replace(0, np.nan)
    df[["기간제비율", "소속외비율"]] = df[["기간제비율", "소속외비율"]].round(3)
    return df.drop_duplicates().reset_index(drop=True)


def preprocess_job_desc(df):
    df = clean_text(df.copy())
    # 쉼표 구분 목록 : 쉼표 앞뒤 공백 통일 ('a , b' → 'a,b')
    for c in df.columns[2:]:
        df[c] = df[c].str.replace(r"\s*,\s*", ",", regex=True)
    df = df.fillna("정보없음")
    return df.drop_duplicates().reset_index(drop=True)  # 완전히 같은 행 1,169건 제거


def preprocess_nara(df):
    df = clean_text(df.copy())
    df["접수시작일"] = pd.to_datetime(df["접수시작일"])
    df["접수마감일"] = pd.to_datetime(df["접수마감일"])
    df["접수기간(일)"] = (df["접수마감일"] - df["접수시작일"]).dt.days + 1
    df["접수기간(일)"] = df["접수기간(일)"].where(df["접수기간(일)"] >= 1)  # 원본 47건은 마감일이 시작일보다 앞서 결측 처리
    df[["조회수", "선발예정인원"]] = df[["조회수", "선발예정인원"]].apply(pd.to_numeric, errors="coerce")
    df["출처URL"] = "https://www.gojobs.go.kr/apmView.do?empmnsn=" + df["일련번호"]
    obj = df.select_dtypes("object").columns
    df[obj] = df[obj].fillna("정보없음")
    return df.drop_duplicates("일련번호").reset_index(drop=True)


def read_html_xls(path):
    """'.xls' 로 받지만 실제로는 HTML 표 (pd.read_html 은 바깥 레이아웃 표까지 읽어 수 분 걸림)
    → BeautifulSoup 으로 표 안에 표가 없는 가장 안쪽 표만 읽음 (01_python ch14 select 방식)"""
    from bs4 import BeautifulSoup
    with open(path, encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "lxml")
    tab = max((t for t in soup.select("table") if not t.select("table")), key=lambda t: len(t.select("tr")))
    rows = [[td.text.strip() for td in tr.select("td, th")] for tr in tab.select("tr")]
    return pd.DataFrame(rows[1:], columns=rows[0], dtype=str)


def preprocess_fdi(df):
    df = clean_text(df.copy())
    df["외투기업최초등록일자"] = pd.to_datetime(df["외투기업최초등록일자"], format="%Y%m%d", errors="coerce")
    df["시도"] = df["주소"].map(lambda x: x.split()[0], na_action="ignore")
    df = df.drop(columns=["전화번호", "우편번호"])  # 개인기업은 대표 개인 연락처일 수 있어 제거
    obj = df.select_dtypes("object").columns
    df[obj] = df[obj].fillna("정보없음")
    return df.drop_duplicates().reset_index(drop=True)


NPS_RATE = 0.095  # 2026년 국민연금 보험료율 (고지금액 = 기준소득월액 × 요율)
NPS_MIN_MEMBERS = 30  # shortcut: 30인 미만 제외 (원본 115MB → 하이잡 기업 매칭 손실 약 2%), 소기업까지 필요하면 낮추기


def preprocess_nps(df):
    df = clean_text(df.copy())
    df.columns = [c.split(" 1 ")[0] for c in df.columns]  # '사업장가입상태코드 1 등록 2 탈퇴' → '사업장가입상태코드'
    num_cols = ["가입자수", "당월고지금액", "신규취득자수", "상실가입자수"]
    df[num_cols] = df[num_cols].apply(pd.to_numeric, errors="coerce")
    df = df[(df["사업장가입상태코드"] == "1") & (df["가입자수"] >= NPS_MIN_MEMBERS)].copy()  # 탈퇴 사업장 제외
    df["적용일자"] = pd.to_datetime(df["적용일자"], errors="coerce")

    # 파생열 : 시도, 시군구, 사업장형태, 추정평균월소득(상한액 적용이라 고소득 기업은 과소추정), 월 입사율·퇴사율
    addr = df["사업장도로명상세주소"].fillna(df["사업장지번상세주소"]).fillna("정보없음")
    df["시도"] = addr.map(lambda x: x.split()[0])
    df["시군구"] = addr.map(lambda x: " ".join(x.split()[:2]))
    df["사업장형태"] = df["사업장형태구분코드"].map({"1": "법인", "2": "개인"})
    df["추정평균월소득"] = (df["당월고지금액"] / df["가입자수"] / NPS_RATE).round(-3)
    df["월입사율"] = (df["신규취득자수"] / df["가입자수"]).round(3)
    df["월퇴사율"] = (df["상실가입자수"] / df["가입자수"]).round(3)

    # 불필요한 열 제거 : 주소코드·우편번호, 코드열(이름열로 대체), 등록 사업장만 남겨 의미 없는 탈퇴일자
    df = df.drop(columns=["우편번호", "사업장지번상세주소", "고객법정동주소코드", "고객행정동주소코드",
                          "법정동주소광역시도코드", "법정동주소광역시시군구코드", "법정동주소광역시시군구읍면동코드",
                          "사업장가입상태코드", "사업장형태구분코드", "탈퇴일자"])
    df = df.rename(columns={"사업자등록번호": "사업자등록번호앞6자리"})
    obj = df.select_dtypes("object").columns
    df[obj] = df[obj].fillna("정보없음")
    return df.drop_duplicates().reset_index(drop=True)


JOBS = {
    "서울시 일자리포털 채용정보.csv": ("seoul_jobs.csv", preprocess_seoul_jobs),
    "한국고용정보원_고용형태공시대상기업_20251231.csv": ("employment_disclosure.csv", preprocess_disclosure),
    "한국고용정보원_구인표준직무기술서_20250901.csv": ("job_desc_standard.csv", preprocess_job_desc),
    "국민연금 가입 사업장 내역_20261023.csv": ("nps_workplace.csv", preprocess_nps),
    "인사혁신처_공공채용정보_20251231.csv": ("nara_recruit.csv", preprocess_nara),
    "산업통상부_외국인투자기업정보.xls": ("fdi_companies.csv", preprocess_fdi),
}
UTF8_SOURCES = {"인사혁신처_공공채용정보_20251231.csv"}  # 나머지 원본은 cp949


if __name__ == "__main__":
    OUT_DIR.mkdir(exist_ok=True)
    for src, (out, func) in JOBS.items():
        if src.endswith(".xls"):
            raw = read_html_xls(RAW_DIR / src)
        else:
            raw = pd.read_csv(RAW_DIR / src, encoding="utf-8-sig" if src in UTF8_SOURCES else "cp949", dtype=str)
        na = raw.isna().sum()
        print(f"== {src}\n   원본 결측치 : {na[na > 0].to_dict()}")
        df = func(raw)
        df.to_csv(OUT_DIR / out, index=False, encoding="utf-8-sig")
        print(f"   원본 {raw.shape} → 전처리 {df.shape} → {out} | 남은 결측치 {df.isna().sum()[lambda s: s > 0].to_dict()}")

    # 간단 검증
    s = pd.read_csv(OUT_DIR / "seoul_jobs.csv")
    assert s["최소임금"].notna().sum() >= len(s) * 0.9, "임금 파싱 실패 행이 많음"
    assert (s["최대임금"].dropna() >= s.loc[s["최대임금"].notna(), "최소임금"]).all()
    assert not pd.read_csv(OUT_DIR / "job_desc_standard.csv").duplicated().any()
    n = pd.read_csv(OUT_DIR / "nps_workplace.csv")
    assert (n["가입자수"] >= NPS_MIN_MEMBERS).all() and n["추정평균월소득"].between(0, 7_000_000).all()
    g = pd.read_csv(OUT_DIR / "nara_recruit.csv")
    assert g["일련번호"].is_unique and (g["접수기간(일)"].dropna() >= 1).all()
    f = pd.read_csv(OUT_DIR / "fdi_companies.csv")
    assert len(f) > 20000 and f["회사명(한글)"].ne("정보없음").all()
