@echo off
chcp 65001 > nul
rem ConnecJob 웹 실행 : conda 'llm' 환경 python 으로 Django 개발 서버를 켜고 브라우저를 엶 (키는 data/.env)
set PY=%USERPROFILE%\anaconda3\envs\llm\python.exe
if not exist "%PY%" set PY=python
cd /d "%~dp0web"
start "" http://127.0.0.1:8000
"%PY%" manage.py runserver
