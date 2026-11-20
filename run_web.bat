@echo off
chcp 65001 > nul
rem ConnecJob 웹 실행 : 처음이면 data/.env 만들기 + DB 만들기 + 공고 불러오기, 그다음 서버를 켜고 브라우저를 엶
set PY=%USERPROFILE%\anaconda3\envs\llm\python.exe
if not exist "%PY%" set PY=python
rem 공유 폴더(\서버\...)에서 더블클릭해도 되게 : cd /d 는 UNC 경로를 못 씀, pushd 는 임시 드라이브로 연결
pushd "%~dp0"

"%PY%" -c "import django, langchain_chroma, langchain_openai" 2>nul
if errorlevel 1 (
  echo [1/3] 필요한 패키지를 설치합니다...
  "%PY%" -m pip install -r requirements.txt || goto :fail
)

if not exist "data\.env" (
  echo [2/3] data\.env 를 만듭니다. 메모장이 열리면 OPENAI_API_KEY= 뒤에 키를 넣고 저장한 뒤 닫아 주세요.
  "%PY%" -c "from django.core.management.utils import get_random_secret_key as g; t=open(r'data\.env.example',encoding='utf-8').read().replace('SECRET_KEY=\n','SECRET_KEY='+g()+'\n',1); open(r'data\.env','w',encoding='utf-8').write(t)" || goto :fail
  notepad "data\.env"
)

cd web
if not exist "db.sqlite3" (
  echo [3/3] DB를 만들고 공고 6만 건을 불러옵니다. 1~2분 걸립니다...
  "%PY%" manage.py migrate || goto :fail
  "%PY%" manage.py load_postings || goto :fail
)

start "" http://127.0.0.1:8000
rem 로컬 개발용 : DEBUG 를 켜야 runserver 가 CSS 를 서빙함 (settings.py 기본값은 False)
set DEBUG=True
"%PY%" manage.py runserver
goto :eof

:fail
echo 실행 중 오류가 났습니다. 위 메시지를 확인해 주세요.
pause
