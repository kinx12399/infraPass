# InfraPass

인프라·보안 자격증 탐색, 취득 가이드와 수험 커뮤니티. KINX 운영 표시는 푸터·소개에 배치하고 IXcloud는 실습 가이드에서 연결합니다.

## 구성

| 계층 | 구성 | 주소 |
|---|---|---|
| 공개 진입점 | HTTPS 종료 퍼블릭 LB | 1.201.170.59 |
| WEB | Nginx, 정적 HTML/CSS/JavaScript | 192.168.21.8 / 192.168.21.5 |
| 내부 LB | HTTP 8080 → WAS 8080 | 192.168.22.19 |
| WAS | Python FastAPI + Uvicorn 2 workers | 192.168.22.6 / 192.168.22.9 |
| DB 접속 | MySQL 8.x, SQLAlchemy, PyMySQL | **192.168.23.7:3306 (VIP)** |
| DB 노드 | DRBD Active-Standby (사용자 별도 구성) | 192.168.23.5 / 192.168.23.6 |

Node 빌드 없이 Nginx가 `web/`를 제공합니다. API는 같은 도메인의 `/api/`로 호출하며 CORS 개방 없이 Origin을 검사합니다. 세션·글·관심 자격증은 MySQL에 저장하여 WAS 사이에 공유합니다.

## 구현된 기능

- 106개 초기 자격증 카탈로그, 이름·약칭 검색, 분야·국내외 필터
- 자격증 개요, 대상, 취득 과정, 시험, 학습, 유지·갱신, 후기·질문 탭
- 회원가입·로그인·로그아웃, Argon2 비밀번호 해시, HttpOnly 세션 쿠키
- 관심 자격증 저장, 나의 학습 페이지
- 후기·질문·공부 기록·스터디 게시물, 후기 추가 항목, 댓글, 페이지 추가 조회
- 정보 수정 제보, 관리자 정보 편집·제보 처리, 변경 전 정보 감사 기록
- 검수된 일정 표시, 직무 로드맵, IXcloud 실습 가이드 3개
- Nginx 설정, systemd 서비스, Git pull 기반 수동 배포 스크립트

카탈로그는 초기 편집 데이터입니다. 106개 전체의 시험별 상세 검수가 완료된 것은 아닙니다. 미확인 비용·일정은 만들어 넣지 않았으며 검수 상태를 표시합니다. 가짜 합격 후기·회원 수·일정도 없습니다. 초기 데이터의 출처는 대화에서 조사한 시행기관 공식 목록이며, 시험별 심층 검수와 링크 재확인이 필요합니다.

## 로컬 개발 (Python 3.12 이상)

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
$env:DATABASE_URL = 'sqlite:///./infrapass.db'
$env:APP_ORIGIN = 'http://127.0.0.1:8000'
$env:COOKIE_SECURE = 'false'
.\.venv\Scripts\python -m app.manage init
.\.venv\Scripts\python -m app.manage seed
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

브라우저에서 `http://127.0.0.1:8000`을 엽니다. SQLite는 로컬 개발·테스트 전용입니다. 운영에서는 DATABASE_URL을 설정하지 않고 DB_HOST 등의 MySQL 설정을 사용하세요.

```bash
python -m pytest -q
```

테스트는 인증, Origin 검사, WAS 간 세션 공유, 권한, 관심 목록 격리, 중복 제출, 댓글과 관리자 검수를 확인합니다. 실제 MySQL·DRBD 장애 전환은 VM에서 별도로 확인해야 합니다.

## VM 최초 배포

Git 원격 저장소 생성·push는 사용자가 진행합니다. 아래 `<REPO_URL>`을 실제 주소로 바꾸세요. 모든 VM에서 경로는 `/opt/infrapass`로 통일합니다. 배포 계정이 체크아웃을 소유하며 앱 서비스 사용자는 소스를 읽기만 합니다.

### WEB 두 대

```bash
sudo apt update
sudo apt install -y nginx git curl
sudo install -d -o "$USER" -g "$USER" /opt/infrapass
git clone <REPO_URL> /opt/infrapass
cd /opt/infrapass
sudo install -d /var/www/infrapass
sudo install -m 0644 web/index.html web/app.js web/styles.css /var/www/infrapass/
sudo install -m 0644 deploy/nginx.conf /etc/nginx/sites-available/infrapass
sudo ln -sfn /etc/nginx/sites-available/infrapass /etc/nginx/sites-enabled/infrapass
```

Ubuntu 기본 사이트가 활성화되어 있으면 해당 링크만 비활성화해 `default_server` 중복을 해소합니다. 다른 서비스 설정은 제거하지 마세요. 이후:

```bash
sudo nginx -t
sudo systemctl reload nginx
curl --fail http://127.0.0.1/healthz
```

퍼블릭 LB: HTTPS 443 → WEB HTTP 80, 헬스 체크 `/healthz`. HTTP 80 공개 접속은 LB에서 HTTPS로 리다이렉트합니다. 예시 Nginx 설정은 **LB의 TLS 종료**를 전제로 합니다. WEB까지 HTTPS가 필요하면 Nginx 인증서와 LB 백엔드 프로토콜을 함께 변경해야 합니다.

### WAS 두 대

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-dev build-essential git curl
sudo useradd --system --no-create-home --shell /usr/sbin/nologin infrapass
sudo install -d -o "$USER" -g "$USER" /opt/infrapass
git clone <REPO_URL> /opt/infrapass
cd /opt/infrapass
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
sudo install -m 0600 .env.example /etc/infrapass.env
sudoedit /etc/infrapass.env
```

`DB_PASSWORD`, 실제 HTTPS `APP_ORIGIN`을 설정합니다. 두 WAS 모두 동일한 DB를 사용합니다. 운영은 `COOKIE_SECURE=true`, `DATABASE_URL` 미설정. 도메인이 아직 없다면 HTTPS LB 접속 주소를 사용하되 인증서가 일치해야 합니다.

DB 관리자에게 `infrapass` 데이터베이스(utf8mb4)를 만들고 WAS 두 IP 각각에 필요한 계정을 발급받습니다. 런타임 권한은 해당 DB의 SELECT/INSERT/UPDATE/DELETE로 제한합니다. 최초 테이블 생성은 DDL 권한을 가진 별도 계정으로 **WAS 한 대에서만** 실행합니다:

```bash
# 이 셸에 DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD를 안전하게 설정한 뒤:
.venv/bin/python -m app.manage init
.venv/bin/python -m app.manage seed
```

설정 파일을 로드해 실행하려면 root 셸에서 `set -a; source /etc/infrapass.env; set +a`를 사용합니다. env 값에 특수문자가 있으면 셸에서 안전하게 작은따옴표로 감싸세요. 비밀번호는 명령 인수·Git·로그에 남기지 마세요. 스키마 생성 후 런타임 계정으로 복귀합니다.

```bash
sudo install -m 0644 deploy/infrapass.service /etc/systemd/system/infrapass.service
sudo systemctl daemon-reload
sudo systemctl enable --now infrapass
curl --fail http://127.0.0.1:8080/api/health/ready
```

내부 LB: HTTP 8080 → WAS 8080, 헬스 체크 `/api/health/ready`. 보안 그룹은 WEB → 내부 LB, 내부 LB → WAS:8080, WAS → DB VIP:3306과 운영자 SSH 경로만 허용합니다. 프록시 헤더는 앱 인증에 사용하지 않습니다. 실제 클라이언트 IP 기반 속도 제한은 신뢰할 LB 주소만 `set_real_ip_from`에 등록한 뒤 활성화합니다. 현재 Nginx 로그인 제한은 LB IP 단위로 적용될 수 있습니다.

### 관리자 지정

일반 회원가입 후, DB 설정이 로드된 WAS 셸에서 실행합니다. 공개 관리자 생성 API는 없습니다.

```bash
.venv/bin/python -m app.manage admin --email operator@example.com
```

## 이후 배포: Git pull

1. 사용자가 검증된 코드를 원격 저장소에 push합니다.
2. WAS 한 대를 내부 LB에서 제외하고 `bash deploy/update.sh was`를 실행합니다.
3. 헬스 체크와 로그인·조회가 정상인지 확인한 뒤 LB에 복귀합니다.
4. 나머지 WAS에도 반복합니다.
5. WEB도 한 대씩 LB에서 제외하고 `bash deploy/update.sh web` 후 복귀합니다.

스크립트는 `git pull --ff-only`만 사용하며 로컬 변경이 있으면 중단합니다. 자동 reset·자동 DB 마이그레이션·자동 롤백은 하지 않습니다. 업데이트 실패 시 노드를 LB에 복귀시키지 말고 원인을 해결하거나 검증된 커밋을 명시적으로 재배포하세요. 웹 자산은 요청 단위의 원자 배포가 아니므로 반드시 노드를 LB에서 제외한 뒤 갱신합니다.

Nginx/systemd 설정 자체의 변경은 diff 검토 후 최초 설치 명령으로 별도 반영합니다. DB 스키마 변경은 향후 버전별 마이그레이션을 추가하고 한 번만 실행합니다. `init`은 초기 테이블 생성용이며 스키마 업그레이드 도구가 아닙니다. `seed`는 기존 관리자 편집 내용을 덮어쓰지 않습니다.

## DB HA와 운영 검증

- 앱은 VIP로만 접속합니다. `pool_pre_ping`은 끊어진 연결을 교체하지만 진행 중 트랜잭션 복구를 보장하지 않습니다.
- 연결 장애에는 503을 반환합니다. 글 등록 요청 ID를 재사용하면 응답 유실 후에도 같은 사용자의 글이 중복 생성되지 않습니다. 클라이언트는 실패한 폼을 닫지 않고 다시 제출해야 같은 ID를 유지합니다.
- DRBD·Pacemaker·펜싱·VIP 이동은 이 저장소에서 설정하지 않습니다. MySQL 프로세스·파일시스템·VIP의 안전한 단일 활성화는 DB 클러스터에서 보장해야 합니다.
- 장애 테스트: 저장 완료된 글 확인 → 활성 DB 중단 → 503 동작 확인 → VIP 전환 → 기존 로그인·글·관심 목록 유지 및 새 글 작성 확인.
- `journalctl -u infrapass`와 Nginx 로그로 배포 상태를 확인합니다. MySQL 백업·복구는 DRBD와 별도로 구성합니다.

## 공개 운영 전 남은 항목

- 실제 도메인/TLS, MySQL 계정·스키마, LB 포트·헬스 체크를 연결
- 시험별 정보·공식 링크 검수와 일정 입력 (초기 등록과 검수 완료는 다름)
- 정식 개인정보처리방침의 연락처·보유기간·삭제 절차 확정
- 이메일 확인·비밀번호 재설정·계정 삭제, 게시물 신고·운영자 숨김 기능은 후속 운영 기능
- 이메일 알림·목표일 설정·수료 인증 검증·파일 업로드는 아직 미구현
- 외부 Google Fonts를 불러옵니다. 외부 폰트 사용이 불필요하면 CSS 첫 줄을 제거해 시스템 폰트로 운영 가능

## 기술 참고

- https://fastapi.tiangolo.com/deployment/server-workers/
- https://docs.sqlalchemy.org/en/20/core/pooling.html
- https://nginx.org/en/docs/http/ngx_http_proxy_module.html
