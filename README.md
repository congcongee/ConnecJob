# 🤖 ConnecJob Project

2번째 프로젝트(2nd Project)로 진행 중인 **ConnecJob** 입니다!

경험을 적으면 맞는 직무·채용공고를 근거와 함께 추천하고, 부족 역량 로드맵과 자소서 초안까지 만들어 주는 AI 취업 매칭 서비스

### 🎬 시연 영상
[![ConnecJob 시연 영상](https://img.youtube.com/vi/rF4LaZISgIM/hqdefault.jpg)](https://www.youtube.com/watch?v=rF4LaZISgIM)

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
