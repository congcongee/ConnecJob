"""NCS 능력단위 전체(한국산업인력공단 파일) + 고용24 직무데이터사전 API로 정의·분류명 보강.

원본
- raw/한국산업인력공단_국가직무능력표준 정보_20251231.csv (cp949) : 능력단위 13,442개 (분류번호·명칭·수준·훈련시간)
- raw/한국산업인력공단_NCS능력단위별_자격종목조회_20251231.csv (cp949) : 능력단위 ↔ 과정평가형 자격종목
- raw/work24_duty_ncs.csv : 능력단위명을 검색어로 고용24 직무데이터사전(callOpenApiSvcInfo215L11) 호출 결과.
  한 번 호출에 관련 능력단위가 여러 개 오므로 이미 받은 능력단위는 검색을 건너뜀. 중간 저장 → 다시 실행하면 이어서 수집.
전처리 결과 (utf-8-sig)
- processed/ncs_units.csv : 능력단위별 대·중·소·세분류 코드/이름, 수준, 훈련시간, 정의
- processed/ncs_cert.csv  : 능력단위코드 ↔ 자격종목 (보완점 단계의 관련 자격증)
"""
import os
import re
import time

import pandas as pd
import requests

from collect_work24 import BASE, DUTY_APIS, OUT_DIR, RAW_DIR, preprocess

NCS_FILE = RAW_DIR / "한국산업인력공단_국가직무능력표준 정보_20251231.csv"
CERT_FILE = RAW_DIR / "한국산업인력공단_NCS능력단위별_자격종목조회_20251231.csv"
CACHE = RAW_DIR / "work24_duty_ncs.csv"
SAVE_EVERY = 300


def fetch(word, key):
    endpoint, qparam = DUTY_APIS["duty_word"]
    q = re.sub(r"\s+", " ", re.sub(r"\(.*?\)|[^\w\s]", " ", word)).strip()  # 괄호·쉼표가 있으면 API가 HTML 오류 페이지를 돌려줌
    for attempt in range(3):
        try:
            r = requests.get(BASE + endpoint, params={"authKey": key, "returnType": "JSON", qparam: q, "limit": 100},
                             timeout=30)
            r.raise_for_status()
            js = r.json()
            break
        except (requests.RequestException, ValueError):
            time.sleep(2 ** attempt)
    else:
        print(f"  {word} 3회 실패 → 결과 없음으로 기록")
        return []
    if "result" not in js:
        return []  # 검색 결과 없음
    return [{"query": word, "ablt_nm": nm, **{k: v for k, v in u.items() if not isinstance(v, (list, dict))}}
            for nm, u in js["result"].items()]


def collect_definitions(ncs):
    key = os.getenv("WORK24_DUTY_KEY")
    if not key:
        raise RuntimeError("WORK24_DUTY_KEY 가 .env 에 없습니다")
    rows = pd.read_csv(CACHE, dtype=str).to_dict("records") if CACHE.exists() else []
    got = {str(r["ablt_unit"]).rsplit("_", 1)[-1] for r in rows}  # 이미 받은 능력단위코드
    done = {r["query"] for r in rows}
    todo = ncs[~ncs["능력단위코드"].isin(got) & ~ncs["명칭"].isin(done)]
    print(f"검색 대상 {len(todo)}개 (이미 받은 능력단위 {len(got)}개)")
    for i, (code, name) in enumerate(zip(todo["능력단위코드"], todo["명칭"]), 1):
        if code in got:
            continue  # 앞선 검색 결과에 이미 포함
        new = fetch(name, key) or [{"query": name, "ablt_nm": None, "ablt_unit": None}]  # 결과 없음도 기록해 재검색 방지
        rows += new
        got |= {str(r["ablt_unit"]).rsplit("_", 1)[-1] for r in new}
        if i % SAVE_EVERY == 0:
            pd.DataFrame(rows).to_csv(CACHE, index=False, encoding="utf-8-sig")
            print(f"  {i}/{len(todo)} 검색, 확보 {len(got & set(ncs['능력단위코드']))}/{len(ncs)}")
        time.sleep(0.1)
    raw = pd.DataFrame(rows)
    raw.to_csv(CACHE, index=False, encoding="utf-8-sig")
    return raw


def preprocess_units(ncs, duty):
    df = ncs.rename(columns={"명칭": "능력단위명", "분류번호": "능력단위분류번호"})
    for col, n in [("NCS대분류코드", 2), ("NCS중분류코드", 4), ("NCS소분류코드", 6), ("NCS세분류코드", 8)]:
        df[col] = df["능력단위코드"].str[:n]
    df["버전"] = df["능력단위분류번호"].str.split("_").str[-1]
    df[["수준", "훈련시간"]] = df[["수준", "훈련시간"]].apply(pd.to_numeric, errors="coerce")

    duty = preprocess(duty.dropna(subset=["ablt_unit"]))
    defs = duty.drop_duplicates("능력단위코드").set_index("능력단위코드")["능력단위정의"]
    # 개정으로 코드가 바뀐 능력단위는 이름(공백 제거)으로 한 번 더 연결
    key = lambda s: s.str.replace(r"\s+", "", regex=True)
    by_name = duty.assign(k=key(duty["능력단위명"])).drop_duplicates("k").set_index("k")["능력단위정의"]
    df["능력단위정의"] = df["능력단위코드"].map(defs).fillna(key(df["능력단위명"]).map(by_name)).fillna("정보없음")
    # 분류명 : 고용24 결과에 나온 코드별 이름을 모든 능력단위에 퍼뜨림 (같은 세분류 능력단위 하나만 걸려도 이름 확보)
    for lv in ["대", "중", "소", "세"]:
        names = duty.drop_duplicates(f"NCS{lv}분류코드").set_index(f"NCS{lv}분류코드")[f"NCS{lv}분류명"]
        df[f"NCS{lv}분류명"] = df[f"NCS{lv}분류코드"].map(names).fillna("정보없음")
    cols = ["능력단위코드", "능력단위명", "능력단위정의", "수준", "훈련시간", "버전", "능력단위분류번호"]
    lv_cols = [f"NCS{lv}분류{x}" for lv in ["대", "중", "소", "세"] for x in ["코드", "명"]]
    return df[cols[:2] + lv_cols + cols[2:]].drop_duplicates("능력단위코드").reset_index(drop=True)


def preprocess_cert(cert):
    df = cert.copy()
    df["능력단위코드"] = df["능력단위코드"].str.split("_").str[0]
    num = ["최소훈련시간", "훈련기준시간합계", "필수능력단위기준시간", "선택능력단위기준시간", "직무기초능력기준시간"]
    df[num] = df[num].apply(pd.to_numeric, errors="coerce")
    df = df.drop(columns=["능력단위유형코드", "기준버전"])
    return df.drop_duplicates().reset_index(drop=True)


if __name__ == "__main__":
    ncs = pd.read_csv(NCS_FILE, encoding="cp949", dtype=str)
    ncs["능력단위코드"] = ncs["분류번호"].str.split("_").str[0]  # '0101010101_17v2' → 버전 뗀 10자리 (고용24 코드와 같은 형식)
    assert ncs["능력단위코드"].str.fullmatch(r"\d{10}").all() and not ncs["능력단위코드"].duplicated().any()

    duty = collect_definitions(ncs)
    units = preprocess_units(ncs, duty)
    units.to_csv(OUT_DIR / "ncs_units.csv", index=False, encoding="utf-8-sig")
    cert = preprocess_cert(pd.read_csv(CERT_FILE, encoding="cp949", dtype=str))
    cert.to_csv(OUT_DIR / "ncs_cert.csv", index=False, encoding="utf-8-sig")

    has = lambda c: (units[c] != "정보없음").sum()
    print(f"능력단위 {len(units)}개 | 정의 {has('능력단위정의')}개 | 세분류명 {has('NCS세분류명')}개"
          f" (세분류 {units['NCS세분류코드'].nunique()}개) | 자격 매핑 {cert.shape} → ncs_units.csv, ncs_cert.csv")
    assert len(units) == len(ncs) and cert["능력단위코드"].str.fullmatch(r"\d{10}").all()
