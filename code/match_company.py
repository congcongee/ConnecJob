"""하이잡 기업명 ↔ 국민연금 가입 사업장 매칭.

입력 : data/processed/cover_letter_questions.csv (기업명·기업규모), data/processed/nps_workplace.csv
출력 : data/processed/company_nps.csv (utf-8-sig) - 하이잡 기업별 가입자수·추정평균월소득·입퇴사율

매칭 순서
1) 이름 정규화 : 전각→반각(NFKC), 회사형태 표기((주)·주식회사 등)·공백·기호 제거, 영문자 → 한글 읽기(SK → 에스케이)
2) 국민연금 사업장명은 뒤에 붙은 사업장 정보를 잘라 회사명만 남김 ('(주)대우건설 본사', '한화에어로스페이스(주)-장교동')
   같은 회사명의 사업장은 합산 (shortcut: 이름만 같은 다른 회사도 합쳐짐, 정확도가 필요하면 사업자등록번호 기준으로 교체)
3) 하이잡 기업명은 괄호 내용·'/' 뒤 계열사·'○○부문' 을 떼어 후보를 만들고, 정확히 같은 회사명 → 없으면 접두 일치
   (4글자 이상, 뒤에 '보험·사' 등만 남을 때, '삼성생명' → '삼성생명보험') 중 가입자수가 가장 많은 회사
"""
import re
import unicodedata
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data"
OUT_DIR = DATA_DIR / "processed"

LETTERS = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                   "에이 비 씨 디 이 에프 지 에이치 아이 제이 케이 엘 엠 엔 오 피 큐 알 에스 티 유 브이 더블유 엑스 와이 제트".split()))
CORP = r"\(주\)|주식회사|\(유\)|유한회사|\(재\)|재단법인|\(사\)|사단법인|\(합\)|합자회사"
PREFIX_MIN = 4  # 접두 일치는 정규화 후 4글자 이상만 (짧은 이름은 엉뚱한 회사와 겹침)
PREFIX_REST = re.compile(r"(해상보험|생명보험|보험|사|직장)")  # 접두 뒤에 남아도 같은 회사로 보는 말 (KBS → KBS비즈니스 같은 계열사 방지)


def norm(name):
    s = re.sub(CORP, "", unicodedata.normalize("NFKC", str(name)))
    s = re.sub(r"[\s\-·.,&'()/]", "", s)
    return re.sub(r"[A-Za-z]", lambda m: LETTERS[m.group().upper()], s)


def nps_base(name):
    """국민연금 사업장명 → 회사명 (회사형태 표기 제거 후 첫 공백·'-' 앞까지)"""
    s = re.sub(CORP, " ", unicodedata.normalize("NFKC", str(name))).strip()
    return norm(re.split(r"[\s\-]", s)[0])


def haijob_candidates(name):
    s = unicodedata.normalize("NFKC", str(name))
    s = re.sub(r"\(.*?\)", "", s)                     # 'CJ제일제당(BIO)' → 'CJ제일제당'
    s = re.sub(r"\s+\S*(부문|사업부)$", "", s)          # '삼성전자 DS부문' → '삼성전자'
    return list(dict.fromkeys(norm(p) for p in [s, *s.split("/")] if norm(p)))


def build_nps(nps):
    nps = nps[~nps["사업장명"].str.contains("/일용/", na=False)].copy()  # 건설현장 일용직 사업장 제외
    nps["회사명"] = nps["사업장명"].map(nps_base)
    agg = nps.sort_values("가입자수", ascending=False).groupby("회사명").agg(
        매칭사업장명=("사업장명", "first"), 사업장수=("사업장명", "size"), 시도=("시도", "first"),
        업종=("사업장업종코드명", "first"), 가입자수=("가입자수", "sum"), 당월고지금액=("당월고지금액", "sum"),
        신규취득자수=("신규취득자수", "sum"), 상실가입자수=("상실가입자수", "sum"))
    agg = agg.sort_values("가입자수", ascending=False)
    return agg


def match(name, agg):
    """→ (회사명, 매칭방식) 또는 (None, None)"""
    cands = haijob_candidates(name)
    for c in cands:
        if c in agg.index:
            return c, "정확"
    for c in cands:
        if len(c) >= PREFIX_MIN:
            hit = [i for i in agg.index if i.startswith(c) and PREFIX_REST.fullmatch(i[len(c):])]  # 가입자수 내림차순
            if len(hit):
                return hit[0], "접두"
    return None, None


def _selftest():
    assert norm("（주）아모레퍼시픽") == "아모레퍼시픽"
    assert norm("SK바이오사이언스") == "에스케이바이오사이언스"
    assert nps_base("(주)대우건설 본사") == "대우건설"
    assert nps_base("한화에어로스페이스(주)-장교동") == "한화에어로스페이스"
    assert nps_base("(주) 풍산 안강사업장") == "풍산"
    assert haijob_candidates("한화솔루션/케미칼") == ["한화솔루션케미칼", "한화솔루션", "케미칼"]
    assert haijob_candidates("삼성전자 DS부문") == ["삼성전자"]
    agg = pd.DataFrame({"가입자수": [5211, 2001, 313, 50]},
                       index=["삼성생명보험", "삼성생명서비스손해사정", "케이비에스비즈니스", "엘에스"])
    assert match("삼성생명", agg) == ("삼성생명보험", "접두")
    assert match("KBS", agg) == (None, None)  # 계열사(KBS비즈니스)로 잘못 연결하지 않음
    assert match("LS MnM", agg) == (None, None)  # 첫 단어(LS)만으로는 매칭하지 않음


if __name__ == "__main__":
    _selftest()
    agg = build_nps(pd.read_csv(OUT_DIR / "nps_workplace.csv", dtype={"사업자등록번호앞6자리": str}))
    co = pd.read_csv(OUT_DIR / "cover_letter_questions.csv")[["기업명", "기업규모"]].drop_duplicates("기업명")
    co[["회사명", "매칭방식"]] = co["기업명"].map(lambda n: match(n, agg)).tolist()

    df = co.merge(agg, left_on="회사명", right_index=True, how="left").drop(columns="회사명")
    df["추정평균월소득"] = (df["당월고지금액"] / df["가입자수"] / 0.095).round(-3)  # preprocess_files.NPS_RATE 와 같은 요율
    df["월입사율"] = (df["신규취득자수"] / df["가입자수"]).round(3)
    df["월퇴사율"] = (df["상실가입자수"] / df["가입자수"]).round(3)
    df = df.drop(columns=["당월고지금액"])
    df.to_csv(OUT_DIR / "company_nps.csv", index=False, encoding="utf-8-sig")

    hit = df["매칭방식"].notna()
    print(df.groupby("기업규모")["매칭방식"].apply(lambda s: f"{s.notna().sum()}/{len(s)}").to_dict(),
          df["매칭방식"].value_counts().to_dict())
    print("미매칭 :", df.loc[~hit, "기업명"].tolist())
