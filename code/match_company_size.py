"""공고 기업명 → 기업규모 태그 (대기업집단 / 외국계 / 중견(근사) / 중소·기타).

입력 : processed/ftc_companies.csv (공정위 대규모기업집단 소속회사), processed/fdi_companies.csv (외국인투자기업),
       processed/nps_workplace.csv (국민연금 가입자수)
       공고 기업명 : 하이잡(cover_letter_questions), 서울시 API(seoul_jobs_api), 인크루트·잡다(private_*)
출력 : processed/company_size.csv (utf-8-sig) - 출처·기업명별 태그와 근거(기업집단명·대표투자국가·가입자수)

판별 순서 (먼저 걸리는 것)
1) 대기업집단 : 공정위 소속회사명과 일치 (회사명 매칭은 match_company.match : 정확 → 4글자 이상 접두)
   기업집단명('현대백화점', '현대백화점그룹')과 일치해도 대기업집단
2) 외국계     : 외국인투자기업(법인기업) 중 '한국○○'·'○○코리아'·영문명 KOREA 인 현지법인명과 일치
3) 중견(근사) : 국민연금 가입자수 300명 이상 (shortcut: 공식 중견기업 목록이 없어 고용 규모로 근사, 목록을 구하면 교체)
4) 중소·기타  : 위에 모두 해당 없음 (매칭 실패 포함)
하이잡에는 사이트가 붙인 기업규모가 있어 태그 정확도를 같이 출력 (공공기관 제외)
"""
from pathlib import Path

import pandas as pd

from match_company import build_nps, match, norm

OUT_DIR = Path(__file__).parent.parent / "data" / "processed"
MID_MIN_MEMBERS = 300


def name_index(df, name_col, order_col):
    """정규화한 회사명을 index 로, order_col 내림차순 (접두 매칭에서 큰 회사 우선)"""
    df = df.assign(_n=df[name_col].map(norm)).sort_values(order_col, ascending=False)
    return df.drop_duplicates("_n").set_index("_n")


def load_postings():
    srcs = [
        ("하이잡", "cover_letter_questions.csv", "기업명"),
        ("서울시", "seoul_jobs_api.csv", "기업명"),
        ("인크루트", "private_incruit.csv", "기업명"),
        ("잡다", "private_jobda.csv", "기업명"),
    ]
    out = []
    for src, f, col in srcs:
        if not (OUT_DIR / f).exists():  # gitignore 대상이라 저장소만 받은 경우 없을 수 있음
            print(f"  [건너뜀] {f} 없음")
            continue
        d = pd.read_csv(OUT_DIR / f, usecols=lambda c: c in (col, "기업규모")).rename(columns={col: "기업명"})
        out.append(d.drop_duplicates("기업명").assign(출처=src))
    return pd.concat(out, ignore_index=True)


def tag(name, refs):
    for label, (agg, info) in refs.items():
        hit, how = match(name, agg)
        if hit is not None and (label != "중견(근사)" or agg.loc[hit, "가입자수"] >= MID_MIN_MEMBERS):
            return label, how, agg.loc[hit, info]
    return "중소·기타", None, None


if __name__ == "__main__":
    ftc = pd.read_csv(OUT_DIR / "ftc_companies.csv")
    # '현대백화점그룹' 처럼 그룹명으로 올린 공고도 잡도록 기업집단명(괄호 설명 제거)을 회사명처럼 추가
    groups = ftc.groupby("기업집단명", as_index=False)["자산총액"].sum()
    groups["회사명"] = groups["기업집단명"].str.replace(r"\(.*?\)", "", regex=True)
    ftc = name_index(pd.concat([ftc, groups, groups.assign(회사명=groups["회사명"] + "그룹")]), "회사명", "자산총액")
    fdi = pd.read_csv(OUT_DIR / "fdi_companies.csv")
    # 외국인투자기업은 외국 지분이 조금만 있어도 등록됨 (안랩·컴투스) → '한국○○'·'○○코리아'·영문명 KOREA 인 현지법인만 외국계로
    local = fdi["회사명(한글)"].str.contains(r"^(?:\(주\)|주식회사)?\s*한국|코리아") | fdi["회사명(영문)"].str.contains("KOREA", case=False)
    fdi = name_index(fdi[(fdi["업체유형"] == "법인기업") & local], "회사명(한글)", "외투기업최초등록일자")
    nps = build_nps(pd.read_csv(OUT_DIR / "nps_workplace.csv", dtype={"사업자등록번호앞6자리": str}))
    refs = {
        "대기업집단": (ftc, "기업집단명"),
        "외국계": (fdi, "대표투자국가"),
        "중견(근사)": (nps, "가입자수"),
    }

    assert tag("현대백화점그룹", refs)[0] == "대기업집단"   # 그룹명 공고
    assert tag("램리서치코리아", refs)[0] == "외국계"
    assert tag("안랩", refs)[0] != "외국계"                # 외국 지분만 있는 국내 기업

    df = load_postings()
    df[["기업규모태그", "매칭방식", "근거"]] = [tag(n, refs) for n in df["기업명"]]
    df = df[["출처", "기업명", "기업규모태그", "근거", "매칭방식", "기업규모"]].rename(columns={"기업규모": "하이잡기업규모"})
    df.fillna("정보없음").to_csv(OUT_DIR / "company_size.csv", index=False, encoding="utf-8-sig")

    print(pd.crosstab(df["출처"], df["기업규모태그"]))
    h = df[(df["출처"] == "하이잡") & (df["하이잡기업규모"] != "공공기관")]
    want = h["하이잡기업규모"].map({"대기업": "대기업집단", "외국계": "외국계", "중소/중견": "중견·중소"})
    got = h["기업규모태그"].replace({"중견(근사)": "중견·중소", "중소·기타": "중견·중소"})
    print(f"하이잡 기준 일치율 {(want == got).mean():.1%} ({len(h)}곳)")
    print(pd.crosstab(want, got))
