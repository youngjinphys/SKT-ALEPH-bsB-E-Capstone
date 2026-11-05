# Policy Sync 수신·적용과 복구

[대시보드 정책 게시 가이드](remote-policy-deployment.md)에서 초안·독립 서명·HTTPS 게시 절차를 확인하세요. 신규 노드 설치 명령은 `scripts/deploy/install-dns-server.sh --help`에서 확인하며 기본 실행은 미리보기입니다. 기존 설치를 덮어쓰지 않습니다.

`aleph-policy-fetch`는 비특권 계정으로 고정 HTTPS 피드를 가져오고 Ed25519 서명·장치 ID·시각을 확인합니다. `aleph-policy-apply`는 네트워크에 접속하지 않고 root 권한으로 다시 검증한 뒤 기존 DNS 게시 경로를 실행합니다. 단순 root 서비스 활성 상태는 적용 증명이 아닙니다.

적용 상태는 `/var/lib/aleph-policy-apply`와 `/var/lib/aleph-policy-fetch`에 있습니다. 복구 전 현재 정책, inbox, applied 상태, pending journal을 비공개 위치에 복사하고 해시와 서비스 설정을 기록하세요. 키나 정책 본문을 공개 이슈·CI 아티팩트에 올리지 마세요.

- 동일 시퀀스 재실행은 실제 DNS attestation을 통과해야 `already-applied`가 됩니다.
- 중단된 작업의 pending journal은 자동 조정을 위한 증거입니다. 삭제하거나 watermark를 낮춰 우회하지 마세요.
- 새로 게시할 때는 현재 시퀀스보다 크고 발급 시각도 더 늦은 정책을 사용합니다. 만료된 근거는 새 수집·검토가 필요합니다.
- 긴급 로컬 정책 변경 시 fetch/apply 타이머가 다시 덮어쓸 수 있습니다. 현재 설치와 영향 범위를 검토한 후 승인된 복구 절차에서 타이머를 제어하세요.
- 차단 철회는 명시적으로 승인된 새 전체 교체 정책으로 수행합니다. 빈 정책 게시나 임의 TTL 연장으로 오류를 숨기지 마세요.

현재 코드 무결성·서비스 경로·신뢰키·journal을 확인한 뒤 기존 명령을 재실행하고 UDP/TCP 응답과 정책 해시를 검증합니다. 자세한 DNS 설치·업그레이드는 [infra/edge/README.md](../infra/edge/README.md)를 따릅니다.
