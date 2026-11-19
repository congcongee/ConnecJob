# 소개 페이지 Cloudflare Pages 배포 (무료, PC 꺼져도 계속 접속됨)

올리는 것 : `html/` 폴더 (`index.html` 한 파일, 글꼴·사진 내장, 시연 영상은 YouTube 임베드)
결과 주소 : `https://<프로젝트이름>.pages.dev`

## 처음 배포 (Direct Upload, 끌어다 놓기)
1. https://dash.cloudflare.com 가입·로그인 (무료)
2. 왼쪽 메뉴 **Workers & Pages** → **Create** → **Pages** 탭 → **Upload assets**
3. 프로젝트 이름 `connecjob` → **Create project**
   - 이름이 이미 쓰이고 있으면 다른 이름(예: `connecjob-portfolio`)을 쓰고, README 의 소개 페이지 주소도 같이 바꿈
4. `html` 폴더를 통째로 끌어다 놓기 → **Deploy site**
5. 나온 `https://connecjob.pages.dev` 접속해서 영상 재생 확인

## 페이지 고친 뒤 다시 올릴 때
같은 프로젝트 → **Create new deployment** → `html` 폴더 다시 끌어다 놓기
