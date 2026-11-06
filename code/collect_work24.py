"""고용24 Open API 수집 + 전처리.

API 키는 data/.env 에서 os.getenv 로 읽는다 (코드에 하드코딩 금지).
원본은 data/raw/work24_<이름>.csv, 전처리 결과는 data/processed/work24_<이름>.csv (utf-8-sig) 로 저장.
"""
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

DATA_DIR = Path(__file__).parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
OUT_DIR = DATA_DIR / "processed"
load_dotenv(DATA_DIR / ".env")

BASE = "https://www.work24.go.kr/cm/openApi/call/wk/"

# 이름: (환경변수, 엔드포인트, 추가 파라미터, 행 태그, 페이지 크기 or None)
APIS = {
    "sme":  ("WORK24_SME_KEY",  "callOpenApiSvcInfo216L01.do", {}, "smallGiant", 100),
    "occu": ("WORK24_OCCU_KEY", "callOpenApiSvcInfo212L01.do", {"target": "JOBCD"}, "jobList", None),
    "code": ("WORK24_CODE_KEY", "callOpenApiSvcInfo21L01.do", {"target": "CMCD", "dtlGb": 1}, None, None),
    # 채용정보: 현재 키로는 "개인회원은 사용할 수 없는 OPEN-API" 응답 → 기업회원 키 필요
    "job":  ("WORK24_JOB_KEY",  "callOpenApiSvcInfo210L01.do", {"callTp": "L"}, "wanted", 100),
}

# 직무정보(JSON, 검색형): 이름: (엔드포인트, 검색 파라미터명)
DUTY_APIS = {
    "duty_desc": ("callOpenApiSvcInfo215L01.do", "jobCont"),  # 표준직무기술서: 수행직무내용 → NCS 능력단위
    "duty_word": ("callOpenApiSvcInfo215L11.do", "word"),     # 직무데이터사전: 키워드 → NCS 능력단위
}
# 직무정보 검색어. 필요에 맞게 수정
DUTY_QUERIES = ["데이터 분석", "웹 개발", "회계", "마케팅", "인사관리", "간호", "영업", "디자인",
                "디지털 마케팅", "광고", "고객관계관리",
                "소프트웨어 개발", "데이터 엔지니어링", "인공지능", "정보보안", "클라우드",
                # 하이잡 자소서 직무분류 중 빠져 있던 직무
                "재무", "금융", "법무", "총무", "사무행정", "채용관리", "교육훈련운영",
                "경영기획", "서비스 기획", "상품기획", "홍보", "영업관리", "구매관리", "물류",
                "생산관리", "품질관리", "기계설계", "전기설계", "연구개발", "고객상담"]
DUTY_LIMIT = 20


def call(env, endpoint, params):
    key = os.getenv(env)
    if not key:
        raise RuntimeError(f"{env} 가 .env 에 없습니다")
    r = requests.get(BASE + endpoint, params={"authKey": key, "returnType": "XML", **params}, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "xml")  # 01_python ch14 2.3 XML 웹데이터 수집 방식
    err = soup.select_one("error")
    if err:
        raise RuntimeError(err.text.strip())
    return soup


def rows(soup, tag):
    return [{c.name: c.text.strip() for c in el.find_all(recursive=False)} for el in soup.select(tag)]


def child_text(el, tag):
    """바로 아래 자식 태그의 text (select_one 은 손자 태그까지 찾아서 oneDepth 안의 twoDepth 값이 섞임)"""
    c = el.find(tag, recursive=False)
    return c.text.strip() if c else None


def code_rows(soup):
    # 공통코드(지역)는 oneDepth > twoDepth 계층 → 평탄화
    out = []
    for one in soup.select("oneDepth"):
        out.append({"regionCd": child_text(one, "regionCd"), "regionNm": child_text(one, "regionNm"), "superCd": "-", "depth": 1})
        for two in one.select("twoDepth"):
            out.append({"regionCd": child_text(two, "regionCd"), "regionNm": child_text(two, "regionNm"),
                        "superCd": child_text(two, "superCd"), "depth": 2})
    return out


def collect(name):
    env, endpoint, params, tag, size = APIS[name]
    if tag is None:
        return pd.DataFrame(code_rows(call(env, endpoint, params)))
    if size is None:
        return pd.DataFrame(rows(call(env, endpoint, params), tag))
    data, page = [], 1
    while True:
        soup = call(env, endpoint, {**params, "startPage": page, "display": size})
        batch = rows(soup, tag)
        data += batch
        total = int(child_text(soup.find(), "total") or 0)
        if not batch or len(data) >= total:
            break
        page += 1
        time.sleep(0.2)  # 서버 부담 완화
    return pd.DataFrame(data)


def collect_duty(name):
    endpoint, qparam = DUTY_APIS[name]
    key = os.getenv("WORK24_DUTY_KEY")
    if not key:
        raise RuntimeError("WORK24_DUTY_KEY 가 .env 에 없습니다")
    data = []
    for q in DUTY_QUERIES:
        r = requests.get(BASE + endpoint, params={"authKey": key, "returnType": "JSON", qparam: q, "limit": DUTY_LIMIT}, timeout=30)
        r.raise_for_status()
        js = r.json()
        if "result" not in js:
            raise RuntimeError(js.get("message") or js)
        for unit_nm, unit in js["result"].items():
            row = {"query": q, "ablt_nm": unit_nm}  # 능력단위명은 dict key로만 옴
            # 리스트 필드(occp, hrd, req 등)는 능력단위와 중복이라 제외
            row.update({k: v for k, v in unit.items() if not isinstance(v, (list, dict))})
            data.append(row)
        time.sleep(0.2)
    return pd.DataFrame(data)


# 영문 API 필드명 → 한글 열이름 (rename)
RENAME = {
    # 강소기업
    "selYear": "선정연도", "sgBrandNm": "강소기업브랜드", "coNm": "기업명", "busiNo": "사업자번호",
    "reperNm": "대표자명", "superIndTpCd": "업종대분류코드", "superIndTpNm": "업종대분류",
    "indTpCd": "업종코드", "indTpNm": "업종명", "regionCd": "지역코드", "regionNm": "지역명",
    "coAddr": "회사주소", "coMainProd": "주요생산품", "alwaysWorkerCnt": "상시근로자수",
    "smlgntCoClcd": "강소기업구분코드",
    # 직업정보
    "jobClcd": "직업분류코드", "jobClcdNM": "직업분류명", "jobCd": "직업코드", "jobNm": "직업명",
    # 공통코드(지역)
    "superCd": "상위지역코드", "depth": "단계",
    # 직무정보
    "query": "검색어", "ablt_nm": "능력단위명", "ablt_def": "능력단위정의", "ablt_unit": "능력단위코드",
    "job_lrcl_cd": "NCS대분류코드", "job_lcfn": "NCS대분류명", "job_mlsf_cd": "NCS중분류코드",
    "job_mcn": "NCS중분류명", "job_scla_cd": "NCS소분류코드", "job_scfn": "NCS소분류명",
    "job_sdvn_cd": "NCS세분류코드", "job_sdvn": "NCS세분류명",
}


def preprocess(df):
    df = df.copy()
    # 0) 직무정보: 코드 필드가 "http://lod.work.go.kr/task/중분류/_0301" 형태 → 끝의 코드만, 링크 열 제거
    for c in [c for c in df.columns if c.endswith("_cd")]:
        df[c] = df[c].str.rsplit("_", n=1).str[-1]
    df = df.drop(columns=["centerURL", "centerLabel"], errors="ignore")
    # 1) 공백 제거, 빈 문자열 → 결측치 (replace)
    obj = df.select_dtypes("object").columns
    df[obj] = df[obj].apply(lambda s: s.str.strip()).replace("", np.nan)
    # 2) 모두 결측치인 열 drop, 중복행 제거 (dropna)
    df = df.dropna(axis=1, how="all").drop_duplicates()
    # 3) 숫자처럼 생긴 열만 숫자로 (코드 열은 앞자리 0 보존 위해 제외) (to_numeric)
    for c in df.columns:
        if c.lower().endswith(("cd", "no", "unit")):
            continue
        num = pd.to_numeric(df[c], errors="coerce")
        if num.notna().sum() == df[c].notna().sum() and df[c].notna().any():
            df[c] = num
    # 4) 결측치 대체 (fillna): 숫자 열은 그룹별 중위수(강소기업은 업종대분류별) → 남으면 전체 중위수, 문자 열은 '정보없음'
    num_cols = df.select_dtypes("number").columns
    if "superIndTpNm" in df.columns:
        df[num_cols] = df[num_cols].fillna(df.groupby("superIndTpNm")[num_cols].transform("median"))
    df[num_cols] = df[num_cols].fillna(df[num_cols].median())
    df = df.fillna("정보없음")
    # 5) 한글 열이름 (rename)
    df = df.rename(columns=RENAME)
    # 6) 지역명 "서울 구로구" → 시도 "서울" (map) : 서울시 채용정보 '근무지역'과 맞추기용
    if "지역명" in df.columns:
        df["시도"] = df["지역명"].map(lambda x: x.split()[0])
    return df.reset_index(drop=True)


if __name__ == "__main__":
    RAW_DIR.mkdir(exist_ok=True)
    OUT_DIR.mkdir(exist_ok=True)
    for name in [*APIS, *DUTY_APIS]:
        try:
            raw = collect(name) if name in APIS else collect_duty(name)
        except Exception as e:
            print(f"[{name}] 실패: {e}")
            continue
        raw.to_csv(RAW_DIR / f"work24_{name}.csv", index=False, encoding="utf-8-sig")
        df = preprocess(raw)
        out = OUT_DIR / f"work24_{name}.csv"
        df.to_csv(out, index=False, encoding="utf-8-sig")
        print(f"[{name}] 원본 {raw.shape} → 전처리 {df.shape} → {out.name} | 남은 결측치 {df.isna().sum().sum()}개")
