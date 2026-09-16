# IXcloud 를 이용한 3Tier 아키텍처

인프라·보안 자격증 탐색과 수험 커뮤니티를 위한 **IXcloud 기반 3-Tier 고가용성 서비스**입니다.
http://1.201.170.59/

**Cloud & Network**

![IXcloud · Cloud](https://img.shields.io/badge/IXcloud-Cloud-FF5A1F?style=flat-square)
![Load Balancer · Public / Private](https://img.shields.io/badge/Load_Balancer-Public_%2F_Private-0078D4?style=flat-square)
![Bastion Host · SSH](https://img.shields.io/badge/Bastion_Host-SSH-475569?style=flat-square)

**Web & Application**

![NGINX · Web](https://img.shields.io/badge/NGINX-Web-009639?style=flat-square&logo=nginx&logoColor=white)
![Python · Backend](https://img.shields.io/badge/Python-Backend-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI · API](https://img.shields.io/badge/FastAPI-API-009688?style=flat-square&logo=fastapi&logoColor=white)
![Uvicorn · ASGI](https://img.shields.io/badge/Uvicorn-ASGI-4051B5?style=flat-square)
![MySQL · Database](https://img.shields.io/badge/MySQL-Database-4479A1?style=flat-square&logo=mysql&logoColor=white)

**High Availability & Operations**

![Pacemaker · HA](https://img.shields.io/badge/Pacemaker-HA-2E7D32?style=flat-square)
![DRBD · Replication](https://img.shields.io/badge/DRBD-Replication-00A4A6?style=flat-square)
![Corosync · Cluster](https://img.shields.io/badge/Corosync-Cluster-6F42C1?style=flat-square)
![QDevice · Quorum](https://img.shields.io/badge/QDevice-Quorum-00897B?style=flat-square)
![QNetd · Arbitrator](https://img.shields.io/badge/QNetd-Arbitrator-00796B?style=flat-square)
![pcs · Management](https://img.shields.io/badge/pcs-Management-546E7A?style=flat-square)
![systemd · Service](https://img.shields.io/badge/systemd-Service-455A64?style=flat-square&logo=systemd&logoColor=white)

---

## 인프라 구축 및 필수 제출 내용

IXcloud에 Web / WAS / DB를 분리한 3-Tier 아키텍처를 구축했습니다. Web과 WAS는 각각 2대와 로드밸런서로 구성하고, DB는 **Pacemaker + Corosync + DRBD 기반 Active-Standby**로 구성했습니다. 관리망에는 Bastion Host와 QNetd 서버를 배치하고, DB 두 노드의 QDevice가 외부 정족수 중재에 참여합니다.

**현재 실습 환경에서는 IXcloud 컨트롤 플레인에 접근할 수 없어 STONITH/fencing을 적용하지 않았습니다.** QDevice 기반 정족수 중재까지 구성했으며, 클라우드 제어 권한을 확보한 후 펜싱을 연동하는 작업은 향후 진행하겠습니다.

### 1. 전체 아키텍처와 통신 경로

![InfraPass 3-Tier 및 DB 고가용성 아키텍처](docs/images/infrapass-architecture-qdevice.png)

외부 사용자의 서비스 요청은 다음 경로로 처리합니다.

```text
Internet → 퍼블릭 LB:443 (HTTPS 종료) → Web-01 / Web-02:80
  ├─ 정적 콘텐츠: Nginx에서 응답
  └─ /api/ 요청 → 프라이빗 LB:8080 → WAS-01 / WAS-02:8080
                                      → DB VIP 192.168.23.7:3306
                                      → 활성 DB의 MySQL

DB-01 ↔ DB-02                  : DRBD 복제 및 Corosync 클러스터 통신
DB-01 / DB-02의 QDevice → QNetd : TCP/5403, 외부 정족수 중재
관리자 → Bastion Host → 각 VM  : TCP/22, 관리용 SSH
```

도식의 HTTPS 443은 외부 접속 구간입니다. [Nginx 설정](deploy/nginx.conf)에서 Web은 HTTP 80으로 수신하고, API 요청을 내부 LB의 HTTP 8080으로 전달합니다. 정적 페이지 요청은 WAS와 DB를 경유하지 않습니다.

#### 서버와 접속 주소

| 계층 | 구성 | 주소 |
|---|---|---|
| 공개 진입점 | HTTPS 종료 퍼블릭 LB | 1.201.170.59 |
| WEB | Nginx, 정적 HTML/CSS/JavaScript | 192.168.21.8 / 192.168.21.5 |
| 내부 LB | HTTP 8080 → WAS 8080 | 192.168.22.19 |
| WAS | Python FastAPI + Uvicorn 2 workers | 192.168.22.6 / 192.168.22.9 |
| DB 접속 | MySQL 8.x, SQLAlchemy, PyMySQL | **192.168.23.7:3306 (VIP)** |
| DB 노드 | DRBD Active-Standby | 192.168.23.5 / 192.168.23.6 |
| 관리 접속 | Bastion Host | 192.168.20.7 |
| 정족수 중재 | vm-fence-assign, corosync-qnetd | 관리망에 배치 |

Node 빌드 없이 Nginx가 `web/`를 제공합니다. API는 같은 도메인의 `/api/`로 호출하며 CORS 개방 없이 Origin을 검사합니다. 세션·글·관심 자격증은 MySQL에 저장하여 WAS 사이에 공유합니다.

### 2. 서브넷 설계와 보안 근거

| 구분 | CIDR | 배치 대상 | 설계 근거 |
|---|---|---|---|
| 관리망 | `192.168.20.0/24` | Bastion Host, QNetd | 사용자 서비스와 관리 접속을 분리하고, DB 노드 외부에 정족수 중재 서버 배치 |
| Web Tier | `192.168.21.0/24` | Web-01, Web-02 | 외부 요청을 받는 프런트 계층을 업무·데이터 계층과 분리 |
| WAS Tier | `192.168.22.0/24` | 내부 LB `192.168.22.19`, WAS 2대 | Web의 API 요청만 내부 LB를 거쳐 처리하고 외부 직접 접근 차단 |
| DB Tier | `192.168.23.0/24` | DB 2대, VIP `192.168.23.7` | MySQL 접속을 WAS로 제한하고 복제·클러스터 통신 범위를 DB망으로 제한 |

서로 겹치지 않는 사설 `/24` 대역을 사용해 계층을 명확히 식별하고 서버 증설과 보안그룹 관리를 단순화했습니다. 관리망을 포함한 총 4개 서브넷으로, Web / WAS / DB 각각 독립 서브넷이라는 필수 조건을 충족합니다. 서브넷 분리만으로 접근이 차단되는 것은 아니므로 보안그룹과 라우팅 정책을 함께 적용합니다.

외부 공개 진입점은 퍼블릭 LB이며, Web VM의 공인 IP 직접 접속을 서비스 경로로 사용하지 않습니다. WAS와 DB는 사설 주소를 이용합니다. DB의 TCP/3306은 WAS에만 허용하며, DB 간 복제·클러스터 통신 및 Bastion의 SSH는 서비스 접속과 구분한 운영 예외입니다.

관리자는 허용된 관리자 공인 IP에서 Bastion으로 접속한 뒤 각 VM의 사설 IP로 SSH 접속합니다. 개별 VM의 SSH를 인터넷에 개방하지 않고 접속 경로를 집중하여 관리 범위와 로그 확인 지점을 줄입니다. SSH 키 인증과 접속 로그 수집·보관 정책은 운영 설정으로 관리합니다.

### 3. 사용한 인프라 도구와 역할

| 도구·구성요소 | 배치 | 역할 |
|---|---|---|
| IXcloud 네트워크·서브넷·보안그룹 | 전체 | 계층별 네트워크 분리와 출발지·목적지·포트 단위 접근 제어 |
| 퍼블릭 Load Balancer | 외부 진입점 | HTTPS 종료, Web 2대로 요청 분산, 헬스 체크 기반 장애 Web 제외 |
| Nginx | Web 2대 | 정적 콘텐츠 제공, `/api/`를 내부 LB로 프록시, `/healthz` 제공 |
| 프라이빗 Load Balancer | WAS망 | Web의 API 요청을 WAS 2대로 분산, 준비 상태 검사로 장애 WAS 제외 |
| FastAPI + Uvicorn | WAS 2대 | 업무 API 처리, VM당 2 workers, DB 기반 세션 공유 |
| systemd | WAS 및 각 인프라 서비스 호스트 | 서비스 기동·재시작 및 로그 조회. WAS는 `infrapass.service`로 관리 |
| MySQL | DB의 활성 노드 | 회원·세션·게시물·관심 목록 저장, VIP를 통한 단일 접속점 제공 |
| DRBD | DB 2대 | DB 데이터가 저장된 블록 장치를 노드 간 복제하는 스토리지 계층 |
| Corosync | DB 2대 | 노드 간 통신, 클러스터 멤버십 및 votequorum을 통한 정족수 판단 |
| Pacemaker | DB 2대 | DRBD 역할, 파일시스템, MySQL, VIP 리소스의 배치·감시·장애 복구를 조정 |
| pcs / pcsd | 클러스터 관리 대상 | Pacemaker·Corosync 구성 및 상태 관리. pcsd 관리 통신은 TCP/2224 |
| corosync-qdevice | DB 각 노드 | QNetd의 중재 결과를 Corosync 정족수 판단에 반영하는 클라이언트 |
| corosync-qnetd | 관리망의 vm-fence-assign | DB 노드 외부에서 정족수 중재를 수행하는 서버, TCP/5403 수신 |
| DB VIP | 현재 활성 DB 노드 | 장애 전환 후에도 WAS가 동일한 DB 주소로 재접속하도록 지원 |
| Bastion Host + SSH | 관리망 | 관리자의 내부 VM 접속을 중계 |

#### 3.1 Pacemaker — 리소스 배치와 복구 관리

Pacemaker는 클러스터에서 **어떤 서비스를 어느 노드에서 실행할지 결정하는 리소스 관리자**입니다. Corosync가 제공하는 노드 상태와 리소스 감시 결과를 바탕으로 서비스 시작·중지·재시작·이동을 조정합니다. 각 서비스는 Resource Agent를 통해 관리하며, 에이전트의 `start`, `stop`, `monitor` 같은 동작을 호출합니다. DRBD처럼 역할이 있는 리소스에는 승격·강등 동작도 사용합니다. [Pacemaker 리소스 문서](https://clusterlabs.org/projects/pacemaker/doc/3.0/Pacemaker_Explained/html/resources.html)

이 구성에서 관리할 대상은 DRBD 역할, DB 파일시스템, MySQL, DB VIP입니다. 데이터가 준비되기 전에 MySQL이 기동하거나 VIP만 다른 노드로 이동하지 않도록 다음 제약을 함께 사용합니다.

- **순서 제약(Ordering):** DRBD Primary 승격 → 파일시스템 마운트 → MySQL 시작 → VIP 활성화 순서로 의존관계를 정의합니다.
- **동일 노드 배치 제약(Colocation):** MySQL과 VIP를 쓰기 가능한 DRBD 및 파일시스템이 있는 노드에 배치합니다.
- **감시·복구 정책:** 리소스 상태를 주기적으로 확인하고, 실패 시 재시작 또는 다른 노드로의 이동을 판단합니다. 감시 주기·실패 임계값·타임아웃은 실제 설정에 따릅니다.

Pacemaker 자체가 DB 데이터를 복제하지는 않습니다. 데이터 복제는 DRBD가 담당하고, Pacemaker는 복제 장치와 서비스를 올바른 순서로 운용합니다. 현재는 펜싱이 미적용되어 응답하지 않는 기존 활성 노드를 강제로 격리하는 단계가 빠져 있습니다.

#### 3.2 Corosync — 노드 통신, 멤버십, 정족수

Corosync는 DB 노드 사이의 클러스터 통신을 담당합니다. 노드가 클러스터에 참가하거나 이탈했는지 파악하는 **멤버십 정보**를 제공하고, `votequorum`은 현재 연결된 구성원이 서비스를 계속할 수 있는 정족수를 갖추었는지 판단합니다. Pacemaker는 이 정보를 리소스 운영 정책에 반영합니다.

DB 두 대만 각각 1표를 가지면 통신 단절 시 어느 쪽을 유지해야 할지 판단하기 어렵습니다. 이 설계는 QDevice의 중재표를 더해 **총 3표 중 2표**를 정족수로 사용합니다. Corosync가 연결 단절을 감지했다고 해서 상대 노드의 전원이나 MySQL이 실제로 중지되었다는 뜻은 아닙니다. 정족수 상실 시 리소스를 어떻게 처리하는지는 Pacemaker 정책과 함께 확인해야 합니다.

제출 화면에는 DB망 내부 UDP/5404·5405가 허용되어 있습니다. 이는 등록된 규칙이며, 실제 필요한 포트는 설치 버전과 Corosync transport 설정에 따라 대조합니다. Corosync의 투표와 DRBD 자체의 데이터 접근·정족수 기능은 별도 계층의 기능입니다. [Corosync votequorum 매뉴얼](https://github.com/corosync/corosync/blob/main/man/votequorum.5)

#### 3.3 DRBD — DB 저장 장치의 블록 복제

DRBD는 두 서버의 저장 장치를 네트워크로 연결하여 **블록 장치에 발생하는 쓰기를 상대 노드에 복제**합니다. MySQL은 활성 노드의 파일시스템에 데이터를 기록하고, 그 아래에 있는 DRBD가 변경 블록을 복제합니다. 따라서 이 구성은 MySQL의 SQL 문이나 binlog를 전달하는 DB 자체 복제와 구분됩니다.

단일 Primary 구조에서 Primary는 쓰기 가능한 장치를 제공하고, Secondary는 복제 데이터를 유지합니다. 정상 상태에서는 활성 DB 노드에서만 파일시스템을 마운트하고 MySQL을 실행합니다. 장애 인계 시에는 데이터 상태를 확인한 후 대기 노드를 Primary로 승격하고 서비스를 시작합니다.

복제 프로토콜은 쓰기 완료를 응답하는 시점을 결정합니다. 예를 들어 **Protocol C는 양쪽 디스크의 쓰기 완료를 확인하는 동기 복제 방식**입니다. 다만 현재 저장소에 실제 DRBD 설정이 없으므로 Protocol C 적용이나 데이터 손실 0을 단정하지 않습니다. 복제 프로토콜, 연결 상태, 양쪽 디스크의 최신 여부, 재동기화 완료 여부를 함께 확인해야 합니다.

DRBD는 데이터 삭제나 손상도 복제할 수 있으므로 백업을 대체하지 않습니다. 노드 간 연결이 끊긴 상태에서 양쪽에 서로 다른 쓰기가 발생하면 데이터가 갈라지는 split-brain 문제가 생길 수 있습니다. 현재 펜싱 미적용 범위를 고려하여 단일 쓰기 노드 확인을 전제로 운용합니다. [DRBD 사용자 가이드](https://linbit.com/drbd-user-guide/drbd-guide-9_0-en/)

#### 3.4 QDevice — DB 노드에서 동작하는 중재 클라이언트

`corosync-qdevice`는 **각 DB 노드에 설치되는 클라이언트 데몬**입니다. 외부 QNetd 서버와 통신하여 받은 판단을 Corosync의 정족수 계산에 반영합니다. 두 DB에 클라이언트를 각각 설치하더라도 도식의 중재표는 클러스터 전체 기준 1표이며, 클라이언트 수만큼 독립적인 중재표가 생기는 구조는 아닙니다.

DB 간 통신이 단절되어 클러스터가 나뉘면 QNetd와의 연결, 멤버십, 설정된 알고리즘 등에 따라 중재 결과가 달라집니다. 제출된 양쪽 DB와 QNetd 상태 출력에서 실제 알고리즘은 **Fifty-Fifty split (`ffsplit`)**, tie-breaker는 **가장 낮은 Node ID**로 확인했습니다. QDevice가 표를 제공하는 상태와 단순히 QNetd에 연결된 상태도 구분해서 확인합니다. [QDevice 공식 매뉴얼](https://github.com/corosync/corosync-qdevice/blob/main/man/corosync-qdevice.8)

QDevice는 MySQL을 기동하거나 VIP를 이동하지 않고, 상대 DB의 전원을 끄지도 않습니다. 투표 결과를 사용하는 주체는 Corosync와 Pacemaker이며, 실제 노드 격리는 별도 펜싱의 역할입니다.

#### 3.5 QNetd — 관리망의 외부 중재 서버

`corosync-qnetd`는 관리망의 `vm-fence-assign`에서 동작하는 **외부 중재 서버**입니다. DB의 QDevice 클라이언트가 QNetd의 TCP/5403으로 접속하고, QNetd는 클러스터 상태와 중재 알고리즘에 따라 판단을 제공합니다. DB 노드 외부에 배치하여 DB 두 노드만으로 결정을 내려야 하는 상황을 보완합니다.

QNetd는 DB 데이터를 보관하는 세 번째 복제 노드가 아니며, 이 호스트에서는 펜싱을 수행하지 않습니다. 서버 이름에 `fence`가 포함되어 있어도 현재 역할은 QNetd입니다. DB 두 대가 서로 연결된 상태에서 QNetd만 중단되면 도식상 DB 2표로 정족수를 유지할 수 있지만, 추가 DB 장애에 대비한 중재 기능은 잃게 됩니다. [QNetd 공식 매뉴얼](https://github.com/corosync/corosync-qdevice/blob/main/man/corosync-qnetd.8)

#### 3.6 pcs / pcsd — 클러스터 구성과 상태 관리

`pcs`는 Pacemaker·Corosync의 리소스, 제약, 클러스터 속성과 상태를 관리하는 명령행 도구입니다. `pcsd`는 노드 인증과 구성 관리 통신을 지원하는 데몬이며, 제출 화면에는 TCP/2224가 등록되어 있습니다. `pcs status`로 노드와 리소스 상태를 확인하고, 실제 구성 출력으로 리소스 배치·순서 제약을 대조합니다.

이 관리 통신은 DRBD 복제 트래픽이나 Corosync의 노드 간 통신과 목적이 다릅니다. pcsd 접근은 클러스터를 관리하는 출발지로 제한합니다. pcs는 설정을 관리하는 도구이며, 실행 중 리소스의 배치·복구 판단은 Pacemaker가 수행합니다. [pcs 프로젝트 문서](https://github.com/ClusterLabs/pcs)

#### 3.7 DB VIP와 systemd — 접속 주소와 프로세스 관리

**DB VIP `192.168.23.7`**은 WAS가 사용하는 고정 접속 주소입니다. 활성 DB가 바뀌면 VIP도 서비스를 인계받은 노드에 배치하여 애플리케이션 설정 변경을 줄입니다. VIP 이동이 기존 TCP 연결과 진행 중 트랜잭션까지 이전하는 것은 아니므로, WAS의 재연결과 요청 재시도가 필요합니다.

**systemd**는 각 VM의 서비스 프로세스를 관리합니다. WAS에서는 Uvicorn 기동·재시작과 로그 조회에 사용합니다. DB에서는 Pacemaker가 관리하는 MySQL·파일시스템을 별도 자동 기동 경로와 충돌시키지 않도록 관리 주체를 일치시켜야 합니다. 노드 한 대 내부의 프로세스 재시작과 여러 노드 사이의 서비스 인계는 각각 systemd와 클러스터 관리 계층의 역할입니다.

**현재 적용 범위:** Pacemaker 리소스 관리 + Corosync 멤버십·정족수 + DRBD 복제 + QDevice/QNetd 외부 중재. **향후 적용 범위:** IXcloud 컨트롤 플레인 접근 권한 확보 후 STONITH/fencing 연동. 정족수 중재만으로 응답하지 않는 노드의 쓰기 중단까지 보장하지는 않습니다. [Pacemaker 펜싱 문서](https://clusterlabs.org/projects/pacemaker/doc/3.0/Pacemaker_Explained/html/fencing.html)

### 4. 계층별 이중화 및 장애 전환 설계

#### Web: 퍼블릭 LB + Nginx 2대

퍼블릭 LB가 Web 두 대로 트래픽을 분산합니다. 두 Web에는 동일한 정적 파일과 Nginx 설정을 배포하며, LB는 HTTP 80의 `/healthz`를 검사합니다. 한 Web이 중단되면 헬스 체크 실패 판정 후 해당 서버를 풀에서 제외하고 정상 서버로 새 요청을 전달합니다.

#### WAS: 프라이빗 LB + 애플리케이션 2대

Web은 `192.168.22.19:8080`의 내부 LB로 API 요청을 전달합니다. 내부 LB는 WAS 두 대의 `/api/health/ready`를 검사하여 정상 인스턴스로만 요청을 전달합니다. 이 엔드포인트는 `SELECT 1`로 DB 연결까지 확인합니다. 세션을 MySQL에 저장하므로 다른 WAS가 다음 요청을 처리해도 동일한 로그인 상태를 조회할 수 있습니다.

#### DB: DRBD + Pacemaker + Corosync + QDevice

초기 구성은 DB-01을 Active, DB-02를 Standby로 둔 단일 활성 구조입니다. 페일오버 후에는 역할이 바뀔 수 있으며, 이번 시험 종료 시에는 DB-02가 Primary, DB-01이 Secondary를 유지했습니다. 활성 노드에서만 DB 파일시스템과 MySQL을 사용하고, WAS는 노드별 IP 대신 `192.168.23.7:3306`으로 접속합니다. DRBD는 블록 단위 복제이며 MySQL binlog 기반 복제와는 구분합니다. DRBD 버전·복제 프로토콜·디스크 및 마운트 경로는 실제 설정 파일을 기준으로 기록해야 합니다. [DRBD 사용자 가이드](https://linbit.com/drbd-user-guide/drbd-guide-9_0-en/)

1. Corosync와 Pacemaker가 노드 또는 리소스 장애를 감지합니다. 리소스 장애는 설정된 복구 정책에 따라 재시작 또는 다른 노드로의 이동 대상이 됩니다.
2. 정족수·복제 데이터 상태와 기존 활성 노드의 쓰기 중단을 확인합니다. 기존 노드의 상태를 확인할 수 없는 경우 자동 격리를 보장할 수 없으므로, 강제 승격에 앞서 운영자 확인이 필요합니다. 이 격리 단계를 자동화하는 펜싱은 향후 적용합니다.
3. 서비스 인계가 가능한 DB 노드의 DRBD를 Primary로 승격합니다.
4. 해당 노드에서 DB 파일시스템을 마운트하고 MySQL을 시작합니다.
5. 같은 노드에서 VIP를 활성화하여 WAS의 새 연결을 받습니다. DRBD Primary·파일시스템·MySQL·VIP를 같은 노드에 두는 배치 제약과 시작 순서 제약이 필요합니다.
6. WAS가 동일 VIP로 재접속하고 readiness가 회복되면 내부 LB가 정상 요청 처리를 재개합니다.

애플리케이션은 `pool_pre_ping`으로 끊어진 DB 연결을 감지하지만 진행 중 트랜잭션의 복구까지 보장하지는 않습니다. DB 연결 오류를 처리할 때는 503을 반환하며, 게시물 등록은 동일 사용자·요청 ID의 중복 생성을 방지합니다. 장애 후 같은 요청 ID로 재시도하여 응답 유실에 대응합니다.

복귀한 기존 노드는 데이터 상태와 재동기화를 확인한 뒤 Standby로 편입합니다. 자동 원복 여부는 리소스 선호도·유지 정책에 따르며, 두 노드에서 DB를 동시에 쓰기 가능 상태로 만들지 않습니다. 클라우드 네트워크에서 VIP 이동을 허용하는 포트 보안·주소 허용 설정도 인계 시험으로 확인합니다.

도식은 **DB 2표 + QDevice 1표 = 총 3표, 정족수 2표**를 기준으로 합니다. DB 한 대와 QNetd가 정상 통신하면 생존 DB 1표와 중재표 1표로 서비스 지속을 판단할 수 있습니다. DB 간 통신이 분리되었을 때 어느 쪽에 중재표를 줄지는 QDevice 알고리즘과 연결 상태에 따릅니다. QNetd만 중단되고 DB 두 대가 정상 통신하면 DB 2표로 정족수를 유지할 수 있지만, 추가로 DB 한 대까지 잃으면 이 설계 기준의 정족수를 충족하지 못합니다. 실제 투표 설정과 상태는 `corosync-quorumtool -s`로 확인합니다. [Red Hat 정족수 장치 구성 문서](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/8/html/configuring_and_managing_high_availability_clusters/assembly_configuring-quorum-devices-configuring-and-managing-high-availability-clusters)

QNetd는 DB 데이터를 저장하거나 복제하는 세 번째 DB 노드가 아닙니다. QDevice 클라이언트에서 QNetd 서버의 TCP/5403으로 연결합니다. [Corosync QDevice 공식 매뉴얼](https://github.com/corosync/corosync-qdevice/blob/main/man/corosync-qdevice.8)

### 5. 보안그룹별 정책표

#### 5.1 Web — `sg-assignment-web`

**서비스 대상:** Web-01 / Web-02 · **서브넷:** `192.168.21.0/24` · **역할:** 정적 콘텐츠 제공 및 내부 LB로 API 전달

| 출발지(Source) | 목적지(Dest.) | 포트/프로토콜 | 방향(In/Out) | 허용 사유 |
|---|---|---|---|---|
| `192.168.21.0/24` | Web 그룹 VM | TCP/80 | In | 퍼블릭 LB 전달 트래픽 수신, 화면 설명 `public lb` |
| Bastion `192.168.20.7/32` | Web 그룹 VM | TCP/22 | In | 관리용 SSH |
| Web 그룹 VM | `169.254.169.254/32` | TCP/80 | Out | 클라우드 메타데이터 접근 |
| Web 그룹 VM | `0.0.0.0/0` | ALL | Out | IPv4 전체 송신 허용 |
| Web 그룹 VM | `::/0` | ALL | Out | IPv6 전체 송신 허용 |

**설계 의도:** 외부 사용자는 퍼블릭 LB의 HTTPS 443으로 접속하고, TLS 종료 후 Web의 HTTP 80으로 요청이 전달됩니다. LB의 VIP 서브넷 ID는 Web 서브넷과 일치하며, 현재 Web:80은 해당 사설 대역 `192.168.21.0/24`에서 오는 연결만 허용합니다.

#### 5.2 WAS — `sg-assignment-was`

**서비스 대상:** WAS-01 / WAS-02 · **서브넷:** `192.168.22.0/24` · **역할:** 내부 LB의 API 요청 처리 및 DB 접근

| 출발지(Source) | 목적지(Dest.) | 포트/프로토콜 | 방향(In/Out) | 허용 사유 |
|---|---|---|---|---|
| `192.168.22.0/24` | WAS 그룹 VM | TCP/8080 | In | API 수신, 화면 설명 `from web` |
| Bastion `192.168.20.7/32` | WAS 그룹 VM | TCP/22 | In | 관리용 SSH |
| WAS 그룹 VM | `169.254.169.254/32` | TCP/80 | Out | 클라우드 메타데이터 접근 |
| WAS 그룹 VM | `0.0.0.0/0` | ALL | Out | IPv4 전체 송신 허용 |
| WAS 그룹 VM | `::/0` | ALL | Out | IPv6 전체 송신 허용 |

**설계 의도:** 서비스 요청은 Web → 내부 LB → WAS로 전달합니다.

#### 5.3 DB — `sg-assignment-db`

**서비스 대상:** DB-01 / DB-02 · **서브넷:** `192.168.23.0/24` · **역할:** MySQL 서비스, DRBD 복제, 클러스터 통신

| 출발지(Source) | 목적지(Dest.) | 포트/프로토콜 | 방향(In/Out) | 허용 사유 |
|---|---|---|---|---|
| WAS망 `192.168.22.0/24` | DB 그룹 VM | TCP/3306 | In | WAS의 MySQL 접속 |
| DB망 `192.168.23.0/24` | DB 그룹 VM | TCP/7789 | In | DRBD 복제용 후보 포트, 화면 설명은 `mysql` |
| DB망 `192.168.23.0/24` | DB 그룹 VM | UDP/5404 | In | Corosync 클러스터 통신 |
| DB망 `192.168.23.0/24` | DB 그룹 VM | UDP/5405 | In | Corosync 클러스터 통신 |
| DB망 `192.168.23.0/24` | DB 그룹 VM | TCP/2224 | In | pcsd 클러스터 관리 |
| Bastion `192.168.20.7/32` | DB 그룹 VM | TCP/22 | In | 관리용 SSH |
| DB 그룹 VM | `169.254.169.254/32` | TCP/80 | Out | 클라우드 메타데이터 접근 |
| DB 그룹 VM | `0.0.0.0/0` | ALL | Out | IPv4 전체 송신 허용 |
| DB 그룹 VM | `::/0` | ALL | Out | IPv6 전체 송신 허용 |

**설계 의도:** MySQL의 서비스 수신은 WAS로 제한하고, 외부 및 Web에서의 직접 DB 접속은 허용하지 않습니다.

#### 5.4 관리망 — `sg-assignment-management`

**설계상 대상:** Bastion Host / QNetd · **서브넷:** `192.168.20.0/24` · **역할:** 관리자 접속 중계 및 외부 정족수 중재

| 출발지(Source) | 목적지(Dest.) | 포트/프로토콜 | 방향(In/Out) | 허용 사유 |
|---|---|---|---|---|
| 관리자 공인 IP `1.201.194.31/32` | 관리 그룹 VM | TCP/22 | In | 허용된 관리자의 SSH 접속 |
| Bastion `192.168.20.7/32` | 관리 그룹 VM | TCP/22 | In | 관리망 내부 SSH 접속 |
| DB망 `192.168.23.0/24` | 관리 그룹 VM | TCP/5403 | In | DB QDevice → QNetd 중재 연결 |
| DB망 `192.168.23.0/24` | 관리 그룹 VM | TCP/2224 | In | pcsd 인증·구성 관리 |
| 관리 그룹 VM | `169.254.169.254/32` | TCP/80 | Out | 클라우드 메타데이터 접근 |
| 관리 그룹 VM | `0.0.0.0/0` | ALL | Out | IPv4 전체 송신 허용 |
| 관리 그룹 VM | `::/0` | ALL | Out | IPv6 전체 송신 허용 |

**설계 의도:** 외부 관리자는 Bastion을 경유하여 내부 VM에 접근합니다. 관리 그룹이 Bastion과 QNetd에 함께 연결된다면 공인 IP의 SSH 허용이 어느 VM에 적용되는지 확인하고, 외부 SSH 진입은 Bastion으로 한정합니다. TCP/5403은 DB QDevice의 중재 요청을 받는 QNetd에 필요한 규칙입니다.

### 6. 장애 시나리오와 검증 방법

#### 6.1 보안그룹 변경 후 정상 상태 확인

**확인 시점:** DB 출력 기준 2026-09-14 16:11:33~16:11:38 (서버 표시 시각). DB-01·DB-02와 QNetd 서버의 명령 출력으로 아래 상태를 확인했습니다.

| 확인 항목 | 실제 결과 | 확인 근거 |
|---|---|---|
| 클러스터 | `mysql-ha`, db01·db02 모두 Online | 양쪽 `pcs status --full` |
| Pacemaker | Current DC `db02`, 표시 버전 `3.0.1-3.0.1` | 클러스터 요약 |
| DRBD 리소스 | `drbd_mysql-clone`: db01 Promoted, db02 Unpromoted | Pacemaker 리소스 목록 |
| DRBD 복제 상태 | 리소스 `mysql`: db01 Primary / db02 Secondary, 양쪽 디스크 UpToDate, 복제 Established | 양쪽 `drbdadm status` |
| 파일시스템 | `mysql_fs` (`ocf:heartbeat:Filesystem`) Started db01 | Pacemaker 리소스 목록 |
| MySQL | `mysql_service` (`systemd:mysql`) Started db01 | Pacemaker 리소스 목록 |
| VIP | `mysql_vip` (`ocf:heartbeat:IPaddr2`) Started db01, `192.168.23.7/24`은 db01에만 존재 | 리소스 목록 및 양쪽 `ip -brief address` |
| 정족수 | Expected votes 3, Total votes 3, Quorum 2, Quorate Yes | 양쪽 `corosync-quorumtool -s` |
| QDevice | 양쪽 Connected, QNetd `192.168.20.20:5403` | 양쪽 `corosync-qdevice-tool -s` |
| 중재 알고리즘 | Fifty-Fifty split, 가장 낮은 Node ID 기준 tie-breaker | DB·QNetd 상태 출력 |
| QNetd 서버 | `vm-fence-assign`, 서비스 active, TCP `*:5403` LISTEN | `systemctl is-active`, `ss -lntp` |
| QNetd 클라이언트 | db01 `192.168.23.5`, db02 `192.168.23.6` 모두 연결, Vote는 각각 `ACK (ACK)`, `No change (ACK)` | `corosync-qnetd-tool -l` |


#### 6.2 페일오버 테스트 결과

Web의 Nginx 중단, WAS의 `infrapass` 서비스 중단, DB 노드 중단·복구 및 QNetd 서비스 중단·복구를 수행한 결과입니다. **Web은 약 4~5초 내 생존 노드로 전환됐고, DB Primary 장애 시 자동 인계에 성공했습니다.** DB 장애 중 반복 호출한 `/api/health/ready`에서는 HTTP 오류가 관측되지 않았으며, 요청 1건의 응답이 최대 약 13.36초 지연됐습니다.

| 구분 | 테스트 내용 | 결과 | 주요 관찰 |
|---|---|---|---|
| Web | Web2 Nginx 중단 | PASS | Web2 로컬 `/healthz` 접속 실패, Web1에서 외부 요청 정상 처리 및 쓰기 요청 HTTP 201 |
| Web | Web1 Nginx 중단 | PASS | 일시적 HTTP 503 발생 후 약 4~5초 내 Web2로 전환 |
| WAS | WAS 서비스 중단 및 LB 전환 | PASS | 프라이빗 LB가 생존 WAS로 요청 전달, API 정상 유지 |
| DB | Secondary `db02` 중단 | PASS | Primary `db01` 유지, MySQL·VIP 이동 없이 서비스 지속 |
| DB | Secondary `db02` 복구 | PASS | Secondary 재가입, DRBD `Established`, 양쪽 `UpToDate`, 총 3표 복원 |
| DB | Primary `db01` 중단 | PASS | `db02` 자동 Primary 승격, 파일시스템·MySQL·VIP 모두 db02로 이동 |
| DB | Primary 장애 중 readiness 호출 | PASS | HTTP 오류 미관측, 최대 `13.357665초` 응답 지연 1회 후 HTTP 200 |
| DB | 기존 Primary `db01` 복구 | PASS | db01이 Secondary로 재가입, db02 Primary 유지, 복제·정족수 정상 복구 |
| QNetd | QNetd 서비스 중단 | PASS | QDevice 연결 실패 상태에서도 DB 2표로 정족수 유지, 서비스 영향 및 리소스 이동 없음 |
| QNetd | QNetd 복구 | PASS | QDevice 재연결 및 총 3표 복원 |

**Web — 장애 확인 및 전환 시간**

Web2의 Nginx 중단 후 `systemctl`에서 `inactive (dead)`, 로컬 `/healthz`에서 `connection refused`를 확인했습니다. 이 상태에서 Web1이 `/`, `/api/certificates`, `/api/me`, `/api/bookmarks` 요청을 정상 처리했고, 쓰기 요청도 HTTP 201로 성공했습니다.

Web1 중단 시험에서 기록한 시각과 응답은 다음과 같습니다.

| 시각 | 관측 내용 |
|---|---|
| 11:07:53 | Web1 Nginx 중단 |
| 11:07:54 | HTTP 503, 해당 요청 응답 지연 약 3.01초 |
| 11:07:58 | HTTP 200 복구 |

장애 발생부터 정상 응답 복구까지의 관측 기준으로 퍼블릭 LB의 생존 Web 전환에 **약 4~5초의 사용자 영향**이 있었습니다.

**WAS — 생존 애플리케이션으로 요청 전달**

WAS의 `infrapass` 서비스를 중단한 후 프라이빗 LB가 다른 WAS로 트래픽을 전환하고 API 요청을 계속 처리하는 것을 확인했습니다. `/api/health/live`는 애플리케이션 프로세스 상태를, `/api/health/ready`는 DB 연결을 포함한 준비 상태를 확인합니다. 이번 결과에는 WAS 전환 소요 시간의 정량 측정값은 포함하지 않았습니다.

**DB Secondary — 활성 노드 유지 및 복제 복구**

시험 전에는 `db01 = Primary`, `db02 = Secondary`였고, DRBD는 `Established`, 양쪽 디스크는 `UpToDate`였습니다. db02를 중단하자 db02는 `OFFLINE`이 됐지만 db01은 `Online / Promoted`를 유지했고, `mysql_fs`·`mysql_service`·`mysql_vip` 모두 db01에서 계속 실행됐습니다. 불필요한 Primary 전환 없이 서비스가 지속됐습니다.

db02 복구 후에는 Secondary로 재가입했으며, DRBD `Established`·양쪽 `UpToDate`, `Total votes = 3`, `Quorate = Yes`로 정상 복귀했습니다.

**DB Primary — 자동 승격 및 서비스 영향**

기존 Primary인 db01 종료 후 Pacemaker에서 db01의 `OFFLINE` 상태와 다음 리소스 인계를 확인했습니다.

```text
db01: OFFLINE
db02:
  DRBD          Promoted (Primary)
  mysql_fs      Started
  mysql_service Started
  mysql_vip     Started

인계 순서: DRBD 승격 → 파일시스템 마운트 → MySQL 시작 → VIP 활성화
```

`/api/health/ready` 반복 호출 로그에서는 HTTP 503을 포함한 HTTP 오류가 관측되지 않았습니다. 전환 시점의 요청 1건은 **13.357665초 후 HTTP 200**으로 완료됐고, 이후 응답은 다시 수십 ms 이하 수준으로 정상화됐습니다. 이 수치는 관측된 최대 요청 응답 시간이며, 전체 DB 리소스 전환 시간을 별도로 측정한 값은 아닙니다.

**기존 Primary 복구 — 자동 원복 없이 Secondary 재가입**

db01 재기동 후에도 db02가 Primary를 유지했고, db01은 Secondary로 재가입했습니다. DRBD는 양쪽 `UpToDate`, 복제 연결은 `Established`로 복구됐습니다. 정족수는 `Expected votes = 3`, `Total votes = 3`, `Quorum = 2`, `Quorate = Yes`였습니다. 기존 Primary로 강제 failback하지 않고 현재 정상 Primary를 유지하는 동작을 확인했습니다.

**QNetd — 중재표 상실 중 정족수 유지 및 복구**

QNetd 중단 시 두 DB의 `QNetd State`는 `Connect failed`였고, 투표 상태는 다음과 같았습니다.

```text
db01 vote   = 1
db02 vote   = 1
QDevice vote = 0
Total votes = 2
Quorum      = 2
Quorate     = Yes
```

db02의 Primary 역할과 `mysql_fs`·`mysql_service`·`mysql_vip` 위치가 그대로 유지됐고 서비스 영향은 없었습니다. QNetd 복구 후에는 QDevice가 재연결되며 총 3표가 복원됐습니다. DB 두 노드가 서로 통신 가능한 조건에서 QNetd 단독 장애에도 정족수를 유지하는 것을 확인했습니다.

**검증 범위:** 위 PASS는 각 시험에서 보고된 관측 결과를 기준으로 합니다. DB Primary 장애 중 HTTP 오류 미발생은 readiness 호출 로그 범위의 결과이며, 전체 업무 API·진행 중 트랜잭션의 무손실을 검증한 결과는 아닙니다. Bastion 중단, DB 간 네트워크 분리 및 복합 장애 시험 결과는 이번 기록에 포함되지 않습니다.

### 7. 향후 인프라 개선 계획

#### STONITH/fencing 연동

현재 실습 계정에서는 **IXcloud 컨트롤 플레인에 접근할 수 없어 VM 전원 제어를 이용한 펜싱을 적용하지 않았습니다.** QDevice/QNetd는 정족수를 중재하지만 장애 노드의 전원을 끄거나 쓰기 접근을 강제로 차단하지 않습니다. 따라서 현재 구성을 네트워크 단절까지 안전하게 자동 복구하는 펜싱 완료 구성으로 보지 않습니다.

#### 운영 보완

- **백업·복구 검증:** DRBD 복제와 별도로 MySQL 백업, 복원 절차, 데이터 보존 및 복구 시간을 확인합니다.

---

InfraPass는 Web·WAS·DB와 관리망을 분리하고, 계층별 접근 제어와 이중화 경로를 갖춘 3-Tier 인프라로 구축했습니다. 페일오버 시험에서 Web·WAS의 LB 자동 전환, DB Secondary 장애 시 Primary 유지, Primary 장애 시 db02 자동 승격과 리소스 인계를 확인했습니다. Web 전환 시 약 4~5초의 영향이 있었고, DB Primary 장애 중 readiness 호출에서는 HTTP 오류 없이 최대 약 13.36초의 응답 지연이 관측됐습니다. DB 복구 후에는 기존 Primary가 Secondary로 재가입했으며, QNetd 단독 장애에서도 DB 2표로 정족수와 서비스를 유지했습니다.

현재 환경의 제약으로 적용하지 못한 펜싱은 향후 클라우드 제어 권한 확보 후 보완하고, 백업·복구 검증을 통해 데이터 보호를 강화할 계획입니다. 구축 상태와 시험 결과, 남은 개선 항목을 함께 관리하여 장애 상황에서도 동작을 설명하고 복구할 수 있는 운영 환경으로 발전시키겠습니다.
