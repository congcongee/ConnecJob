# ConnecJob AWS EC2 + Cloudflare 터널 배포 (수업 방식 : `C:\ai\lecNote\12_배포`)

결과 : `https://<랜덤단어>.trycloudflare.com` (https 공개 주소, 포트폴리오 링크용). 수업 방식의 `http://<탄력적IP>:8000` 도 그대로 됨. 꺾쇠 `< >` 는 본인 값으로 바꿈.

EC2 가 장고 서버를 돌리고, Cloudflare 터널(cloudflared)은 그 서버에 https 주소만 붙여 줌 (무료, Cloudflare 가입 불필요)

수업 예제와 다른 점 4가지
1. `.env` 위치가 루트가 아니라 **`data/.env`**
2. `db.sqlite3`(111MB)·`data/chroma`(벡터DB)·`data/processed/postings.csv` 는 GitHub에 없음 → **로컬에서 scp로 올림**
3. chromadb·pandas 때문에 메모리가 1GB면 부족할 수 있음 → **t3.small** 권장 (t3.micro면 아래 6-1 스왑 추가)
4. ⑭ 에서 runserver 와 함께 **cloudflared 터널**도 screen 으로 띄움 (6-2)

## 1. 로컬 (이미 반영됨)
- `settings.py` : `WhiteNoiseMiddleware` 추가, `STATIC_ROOT = BASE_DIR / "staticfiles"`, DEBUG·ALLOWED_HOSTS·SECRET_KEY 는 `data/.env` 에서 읽음
- `requirements.txt` 에 `whitenoise` 추가, `.gitignore` 에 `.venv/`, `web/staticfiles/` 추가
- GitHub push
```powershell
cd C:\ai\lecNote\09_Project\personal_project
git push   # 배포 준비 커밋은 이미 push 됨
```

## 2~4. EC2 콘솔 (수업 문서 그대로)
- 리전 서울, OS **Ubuntu**, 유형 **t3.small**, 키 페어 `connecjob-key.pem` → `C:\Users\<사용자명>\.ssh\` 에 저장
- 보안 그룹 인바운드 : 22(SSH), 80(HTTP), **8000(사용자 지정 TCP, 0.0.0.0/0)**
- 스토리지 20GB 이상 (패키지 + DB + 벡터DB)
- 탄력적 IP 할당 → 인스턴스에 연결

## 5. 키 권한 + 데이터 올리기 + SSH 접속 (로컬 PowerShell)
```powershell
icacls "$env:USERPROFILE\.ssh\connecjob-key.pem" /inheritance:r
icacls "$env:USERPROFILE\.ssh\connecjob-key.pem" /grant:r "${env:USERNAME}:R"
```
먼저 서버에 접속해 6단계 ⑦(클론)까지 한 뒤, 로컬에서 GitHub에 없는 파일을 올림
```powershell
cd C:\ai\lecNote\09_Project\personal_project
$K="$env:USERPROFILE\.ssh\connecjob-key.pem"; $S="ubuntu@<탄력적IP>:/home/ubuntu/myproject"
scp -i $K data/.env "$S/data/.env"
scp -i $K data/processed/postings.csv "$S/data/processed/"
scp -i $K -r data/chroma "$S/data/"
scp -i $K data/processed/cover_letter_questions.csv "$S/data/processed/"   # 있으면 (없어도 기본 문항으로 동작)
```
접속
```powershell
ssh -i "$env:USERPROFILE\.ssh\connecjob-key.pem" ubuntu@<탄력적IP>
```

## 6. EC2 서버 (Ubuntu)
```bash
# ① 업데이트  ② Python 3.10 저장소  ③④ 3.10 설치
sudo apt update && sudo apt upgrade -y
sudo apt install software-properties-common -y
sudo add-apt-repository ppa:deadsnakes/ppa -y && sudo apt update
sudo apt install python3.10 python3.10-venv python3.10-dev -y
# ⑤ 필수 소프트웨어
sudo apt install build-essential git nginx screen -y
# ⑥⑦ 폴더 만들고 클론
cd /home/ubuntu && mkdir myproject && cd myproject
git clone https://github.com/congcongee/ConnecJob.git .
# → 여기서 5단계의 scp 실행
# ⑧ 가상환경
python3.10 -m venv .venv
source .venv/bin/activate
# ⑨ 의존성
pip install --upgrade pip
pip install -r requirements.txt
```
⑩ `data/.env` 수정 (`nano data/.env`, 저장 Ctrl+O 엔터, 종료 Ctrl+X). scp로 올린 로컬 값에 아래 두 줄 추가
```
DEBUG=False
ALLOWED_HOSTS=<탄력적IP>,.trycloudflare.com,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://*.trycloudflare.com
```
`CSRF_TRUSTED_ORIGINS` 가 없으면 https 주소에서 로그인·경험 입력(POST)이 403 으로 막힘
`OPENAI_API_KEY`, `SECRET_KEY` 가 채워져 있는지 `cat data/.env` 로 확인

⑫ DB 만들기 + static 모으기 (공고 6만 건, 1~2분)
```bash
cd web
python manage.py migrate
python manage.py load_postings
python manage.py collectstatic --noinput
python manage.py createsuperuser   # 관리자 필요하면
```
⑬ 테스트 : `python manage.py runserver 0.0.0.0:8000` → 브라우저에서 `http://<탄력적IP>:8000` 확인 → Ctrl+C

⑭ SSH 닫아도 계속 실행
```bash
screen -S django
source /home/ubuntu/myproject/.venv/bin/activate
cd /home/ubuntu/myproject/web && python manage.py runserver 0.0.0.0:8000
# Ctrl+A, D 로 빠져나옴. 다시 볼 때 : screen -r django
```

### 6-2. Cloudflare 터널 (https 공개 주소)
```bash
# 설치 (t3 는 x86 → amd64)
curl -L -o cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb && cloudflared --version
# ⑭ 의 django screen 이 떠 있는 상태에서, 터널도 screen 으로
screen -S tunnel
cloudflared tunnel --url http://localhost:8000
# 출력의 https://xxxx.trycloudflare.com 이 공개 주소 → README 에 적음
# Ctrl+A, D 로 빠져나옴. 주소 다시 볼 때 : screen -r tunnel
```
- 무료 터널은 cloudflared 를 다시 켜면(인스턴스 재부팅 포함) **주소가 바뀜** → README 링크도 새 주소로 고침
- 터널로만 접속할 거면 보안 그룹의 8000 은 닫아도 됨 (터널은 서버에서 바깥으로 나가는 연결이라 인바운드 불필요)

### 6-1. t3.micro(1GB)일 때만 : 스왑 2GB 추가 (pip 설치·추천 중 메모리 부족으로 죽는 것 방지)
```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### 코드 고친 뒤 다시 올릴 때
```bash
cd /home/ubuntu/myproject && git pull
source .venv/bin/activate && pip install -r requirements.txt
cd web && python manage.py migrate && python manage.py collectstatic --noinput
screen -r django   # Ctrl+C 후 runserver 다시 실행 (터널은 그대로 두면 주소 유지)
```

## 7. 실습 끝나면 과금 방지
인스턴스 종료 → 탄력적 IP 릴리스 → 보안 그룹 삭제 → 웹에서 키 페어 삭제 → 로컬 `.pem` 삭제
