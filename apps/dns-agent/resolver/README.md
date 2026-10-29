# 리졸버 설정

현재 완전한 dnsmasq 설정은 `dns_agent.policy.render_config()`에서 생성합니다.
사용자 정책에서 `conf-file`, `conf-dir`, 업스트림이나 리스너 설정을 주입할 수 없습니다.
`render`로 미리 확인한 뒤 격리 `run`으로 실행하세요. 이 폴더의 파일을 `/etc/dnsmasq.d`로 복사하지 않습니다.
`address=/domain/`은 해당 이름과 하위 이름을 다룹니다. 정확한 단일 이름 차단으로 표기하지 않습니다.
