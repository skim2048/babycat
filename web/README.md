# Web Dashboard

웹 대시보드 (Vue 3 + Vite).

## 실행 방법

**반드시 이 디렉토리에서 실행해야 합니다.**

```bash
cd web
docker compose up -d
```

이 스택은 babycat 메인 스택과 독립적입니다. 별도 호스트에서 실행해도 되며, 백엔드(`app`·`api`·MediaMTX) 위치는 `.env`의 `VITE_BABYCAT_HOST`로 지정합니다(로그인 화면에서 런타임 변경도 가능).

## 종료

```bash
cd web
docker compose down
```
