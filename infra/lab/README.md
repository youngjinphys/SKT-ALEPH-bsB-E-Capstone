# 격리 시험 환경

`apps/dns-agent/tests/test_integration.py`는 일반 사용자로 실제 dnsmasq 두 개를 loopback 고포트에 띄웁니다.
통제 업스트림은 합성 `.test` 이름에 정상 A/AAAA를 제공하고, 검사 대상 에이전트의 적용 전후를 독립 `dig`로 비교합니다.
인터넷의 실제 피싱 사이트나 운영 DNS 설정을 사용하지 않습니다.

```sh
REQUIRE_DNSMASQ=1 PYTHONPATH=apps/dns-agent/src \
  python3 -m unittest discover -s apps/dns-agent/tests -v
```

Linux, Python 3.11 이상, 일반 사용자, `dnsmasq-base`·`dnsutils` 설치가 필요합니다.
설치된 바이너리가 없으면 일반 실행은 skip, 위 명령은 실패합니다. VM 이미지와 운영 네트워크 배포는 제공하지 않습니다.
