# Web Dashboard

웹 대시보드 (Vue 3 + Vite).

## 실행 방법

**반드시 이 디렉토리에서 실행해야 합니다.**

```bash
cd web
docker compose up -d
```

이 스택은 babycat 메인 스택과 독립적입니다. 별도 호스트에서 실행해도 됩니다. 백엔드(`app`·`api`·MediaMTX) 위치는 로그인 화면에서 입력하며, 연결에 성공하면 브라우저에 저장되어 다음 접속부터 자동 입력됩니다.

## 종료

```bash
cd web
docker compose down
```
