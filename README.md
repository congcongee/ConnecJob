# 🤖 ConnecJob Project

2번째 프로젝트(2nd Project)로 진행 중인 **ConnecJob** 입니다!

## 🛠 Tech Stack
- **Language:** Python
- **Tools:** Git, GitHub

## 📂 Project Structure
- `code/` : 수집·전처리·추천·자소서 소스 코드 (`eda_postings.ipynb` 탐색 분석)
- `data/` : 원본(`raw/`)·전처리(`processed/`) 데이터, 사전·평가 표, EDA 그림(`eda/`)
- `web/` : Django 웹 서비스 (`run_web.bat` 으로 실행)
- `html/` : 랜딩 페이지 최종 시안
- `docs/` : 발표 자료·원고, 화면 구조 설명, 작업일지

## 🌐 웹 서비스 실행 (Django)
conda `llm` 환경 (langchain·chroma·django 5.2), 키는 `data/.env.example` 을 `data/.env` 로 복사해 `OPENAI_API_KEY` 입력

Windows 에서는 `run_web.bat` 을 더블클릭하면 서버가 켜지고 브라우저가 열림
```bash
cd web
python manage.py migrate
python manage.py load_postings   # data/processed/postings.csv 공고 6만 건 → Posting 테이블 (공고 표를 다시 만들면 다시 실행)
python manage.py runserver   # http://localhost:8000
python manage.py test matching   # 화면 흐름 테스트 (AI 호출은 가짜)
```
- `web/matching` : 경험 입력 → 추천·부족 역량·로드맵 → 자소서 초안·첨삭, 결과는 SQLite 에 저장
- 추천·자소서 로직은 `code/` 모듈(recommend, roadmap, cover_letter)을 그대로 불러씀
