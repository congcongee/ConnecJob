<img src=https://notion-emojis.s3-us-west-2.amazonaws.com/prod/svg-twitter/1f4bc.svg width="50">

# AI 취업 매칭 서비스 ConnecJob
> 경험을 적으면 맞는 채용공고를 근거와 함께 추천하고, 부족 역량 로드맵과 자기소개서 초안까지 만들어 주는 RAG 기반 AI 서비스 (KDT 2차 프로젝트 · 개인)

<img width="960" height="540" alt="슬라이드1" src="docs/ppt이미지/슬라이드1.JPG">

### 🌐 웹 서비스 바로가기
http://13.54.109.57:8000
(AWS EC2 탄력적 IP로 배포, 접속이 안 되면 아래 시연 영상 참고)

## 📑 목차
[배경 및 문제 정의](#-배경-및-문제-정의)<br>
[프로젝트 목표](#-프로젝트-목표)<br>
[프로젝트 소개](#-프로젝트-소개)<br>
[데이터 수집 및 분석](#-데이터-수집-및-분석)<br>
[모델 개발 및 성능 평가](#-모델-개발-및-성능-평가)<br>
[웹 서비스 구현](#-웹-서비스-구현)<br>
[프로젝트 결론](#-프로젝트-결론)<br>
[시연 영상](#-시연-영상)<br>
[활용 데이터](#-활용-데이터)<br>

## 🎯 배경 및 문제 정의

### 프로젝트 배경

- 채용공고는 여러 사이트에 흩어져 있고, 신입이 지원할 수 있는 공고를 직접 골라내기 어려움
- 키워드 검색은 표현이 다르면 맞는 공고를 놓치고, 왜 맞는지 근거를 알려 주지 않음
- 공고를 찾은 뒤에도 무엇이 부족한지, 자기소개서에 무엇을 써야 할지 따로 준비해야 함

### 핵심 질문

- 지원자의 경험만으로 맞는 공고를 근거와 함께 찾아 줄 수 있는가?
- 신입이 지원할 수 없는 경력 공고를 추천에서 걸러낼 수 있는가?
- 추천 결과에서 부족 역량과 자기소개서 초안까지 한 흐름으로 이어 줄 수 있는가?

## 🎯 프로젝트 목표

1. **채용 데이터 통합**
    - 공공 API·크롤링 등 15개 출처 공고를 수집·표준화해 통합 공고 60,100건 구축
    - 기술·자격증·직무묶음 사전으로 공고별 태그, 기업규모 판별
2. **RAG 기반 공고 추천**
    - 경험 임베딩 → 벡터DB 검색 → 규칙 기반 재순위 → LLM 재판정
    - 추천 이유를 공고 내용에 근거해 제시
3. **지원 준비 지원**
    - 부족 기술을 요구 비율 순으로 뽑아 학습 로드맵 제안
    - 실제 기업 자소서 문항으로 초안 생성, 검수 LLM이 근거 없는 표현 제거
4. **웹 서비스 구현·배포**
    - Django로 경험 입력 → 추천 → 로드맵 → 자소서 흐름 구현
    - AWS EC2에 배포

## 📌 프로젝트 소개
<img width="960" height="540" alt="슬라이드4" src="docs/ppt이미지/슬라이드4.JPG">
<img width="960" height="540" alt="슬라이드5" src="docs/ppt이미지/슬라이드5.JPG">
<img width="960" height="540" alt="슬라이드6" src="docs/ppt이미지/슬라이드6.JPG">
<img width="960" height="540" alt="슬라이드7" src="docs/ppt이미지/슬라이드7.JPG">
<img width="960" height="540" alt="슬라이드8" src="docs/ppt이미지/슬라이드8.JPG">
<img width="960" height="540" alt="슬라이드9" src="docs/ppt이미지/슬라이드9.JPG">
<img width="960" height="540" alt="슬라이드10" src="docs/ppt이미지/슬라이드10.JPG">
<img width="960" height="540" alt="슬라이드11" src="docs/ppt이미지/슬라이드11.JPG">

## 📝 데이터 수집 및 분석
<img width="960" height="540" alt="슬라이드13" src="docs/ppt이미지/슬라이드13.JPG">
<img width="960" height="540" alt="슬라이드14" src="docs/ppt이미지/슬라이드14.JPG">
<img width="960" height="540" alt="슬라이드15" src="docs/ppt이미지/슬라이드15.JPG">
<img width="960" height="540" alt="슬라이드16" src="docs/ppt이미지/슬라이드16.JPG">
<img width="960" height="540" alt="슬라이드17" src="docs/ppt이미지/슬라이드17.JPG">
<img width="960" height="540" alt="슬라이드18" src="docs/ppt이미지/슬라이드18.JPG">
<img width="960" height="540" alt="슬라이드19" src="docs/ppt이미지/슬라이드19.JPG">

## 🔍 모델 개발 및 성능 평가
<img width="960" height="540" alt="슬라이드21" src="docs/ppt이미지/슬라이드21.JPG">
<img width="960" height="540" alt="슬라이드22" src="docs/ppt이미지/슬라이드22.JPG">
<img width="960" height="540" alt="슬라이드23" src="docs/ppt이미지/슬라이드23.JPG">
<img width="960" height="540" alt="슬라이드24" src="docs/ppt이미지/슬라이드24.JPG">
<img width="960" height="540" alt="슬라이드25" src="docs/ppt이미지/슬라이드25.JPG">
<img width="960" height="540" alt="슬라이드26" src="docs/ppt이미지/슬라이드26.JPG">
<img width="960" height="540" alt="슬라이드27" src="docs/ppt이미지/슬라이드27.JPG">
<img width="960" height="540" alt="슬라이드28" src="docs/ppt이미지/슬라이드28.JPG">
<img width="960" height="540" alt="슬라이드29" src="docs/ppt이미지/슬라이드29.JPG">
<img width="960" height="540" alt="슬라이드30" src="docs/ppt이미지/슬라이드30.JPG">
<img width="960" height="540" alt="슬라이드31" src="docs/ppt이미지/슬라이드31.JPG">

## 💻 웹 서비스 구현
<img width="960" height="540" alt="슬라이드33" src="docs/ppt이미지/슬라이드33.JPG">
<img width="960" height="540" alt="슬라이드34" src="docs/ppt이미지/슬라이드34.JPG">
<img width="960" height="540" alt="슬라이드35" src="docs/ppt이미지/슬라이드35.JPG">
<img width="960" height="540" alt="슬라이드36" src="docs/ppt이미지/슬라이드36.JPG">
<img width="960" height="540" alt="슬라이드37" src="docs/ppt이미지/슬라이드37.JPG">
<img width="960" height="540" alt="슬라이드38" src="docs/ppt이미지/슬라이드38.JPG">
<img width="960" height="540" alt="슬라이드39" src="docs/ppt이미지/슬라이드39.JPG">
<img width="960" height="540" alt="슬라이드40" src="docs/ppt이미지/슬라이드40.JPG">
<img width="960" height="540" alt="슬라이드41" src="docs/ppt이미지/슬라이드41.JPG">
<img width="960" height="540" alt="슬라이드42" src="docs/ppt이미지/슬라이드42.JPG">

## 🚨 프로젝트 결론
<img width="960" height="540" alt="슬라이드44" src="docs/ppt이미지/슬라이드44.JPG">
<img width="960" height="540" alt="슬라이드45" src="docs/ppt이미지/슬라이드45.JPG">
<img width="960" height="540" alt="슬라이드46" src="docs/ppt이미지/슬라이드46.JPG">
<img width="960" height="540" alt="슬라이드47" src="docs/ppt이미지/슬라이드47.JPG">

## 🎬 시연 영상
[![ConnecJob 시연 영상](https://img.youtube.com/vi/rF4LaZISgIM/hqdefault.jpg)](https://www.youtube.com/watch?v=rF4LaZISgIM)

## 📚 활용 데이터

  - 서울시 일자리포털 채용정보 API, 나라일터(인사혁신처 공공채용정보), 잡알리오 공공기관 채용공시 API
  - 인크루트·잡다 채용공고, 하이잡 자기소개서 문항 (robots.txt·이용약관 확인 범위 내 수집)
  - 고용24 직무데이터사전·구인표준직무기술서, NCS 국가직무능력표준·국가자격 종목
  - 공정거래위원회 대기업집단, 외국인투자기업 정보, 국민연금 가입 사업장

##

- **프로젝트 기간**: 2026.10.26 ~ 2026.11.19 (4주)
- **개발 인원**: 1명 (기획·데이터·AI·웹·배포 전담)
- **주요 기술**:
   <div>
     <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white">
     <img src="https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white">
     <img src="https://img.shields.io/badge/scikit--learn-F7931E?style=for-the-badge&logo=scikit-learn&logoColor=white">
     <img src="https://img.shields.io/badge/Selenium-43B02A?style=for-the-badge&logo=selenium&logoColor=white">
   </div>
   <div>
     <img src="https://img.shields.io/badge/LangChain-1C3C3C?style=for-the-badge&logo=langchain&logoColor=white">
     <img src="https://img.shields.io/badge/OpenAI-412991?style=for-the-badge&logo=openai&logoColor=white">
     <img src="https://img.shields.io/badge/Chroma-FF6B35?style=for-the-badge&logoColor=white">
   </div>
   <div>
     <img src="https://img.shields.io/badge/Django-092E20?style=for-the-badge&logo=django&logoColor=white">
     <img src="https://img.shields.io/badge/Bootstrap-7952B3?style=for-the-badge&logo=bootstrap&logoColor=white">
     <img src="https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white">
     <img src="https://img.shields.io/badge/AWS%20EC2-FF9900?style=for-the-badge&logo=amazonec2&logoColor=white">
   </div>

## 📂 Project Structure
- `code/` : 수집·전처리·추천·자소서 소스 코드 (`eda_postings.ipynb` 탐색 분석)
- `data/` : 원본(`raw/`)·전처리(`processed/`) 데이터, 사전·평가 표, EDA 그림(`eda/`)
- `web/` : Django 웹 서비스 (`run_web.bat` 으로 실행)
- `html/` : 랜딩 페이지 최종 시안
- `docs/` : 발표 자료·원고(`ppt이미지/` README용 슬라이드), 화면 구조 설명, 작업일지

## 🌐 웹 서비스 실행 (Django)
필요한 것 : Windows, Python 3.10 (Anaconda 권장), OpenAI API 키

### 가장 쉬운 방법 : `run_web.bat` 더블클릭
처음 한 번만 아래를 자동으로 하고, 다음부터는 바로 서버가 켜짐
1. 패키지가 없으면 `pip install -r requirements.txt`
2. `data/.env` 가 없으면 `data/.env.example` 로 만들고 SECRET_KEY 를 자동으로 채운 뒤 메모장을 엶 → `OPENAI_API_KEY=` 뒤에 키를 넣고 저장
3. `web/db.sqlite3` 가 없으면 DB를 만들고 공고 6만 건을 불러옴 (1~2분)
4. 서버를 켜고 브라우저에서 http://127.0.0.1:8000 을 엶

conda `llm` 환경(`%USERPROFILE%\anaconda3\envs\llm`)이 있으면 그 python 을, 없으면 PATH 의 python 을 씀

### 직접 실행할 때
```bash
pip install -r requirements.txt
# data/.env.example 을 data/.env 로 복사하고 OPENAI_API_KEY, SECRET_KEY 입력
cd web
python manage.py migrate
python manage.py load_postings   # data/processed/postings.csv 공고 6만 건 → Posting 테이블
python manage.py runserver       # http://127.0.0.1:8000
python manage.py test matching   # 화면 흐름 테스트 (AI 호출은 가짜라 키 없이 돌아감)
```
- 추천용 벡터DB(`data/chroma`)는 이미 만들어 둔 것을 씀. 다시 만들려면 `python code/recommend.py build` (임베딩 비용 발생)
- `web/matching` : 경험 입력 → 추천·부족 역량·로드맵 → 자소서 초안·첨삭, 결과는 SQLite 에 저장
- 추천·자소서 로직은 `code/` 모듈(recommend, roadmap, cover_letter)을 그대로 불러씀
