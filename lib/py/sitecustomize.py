"""라이브러리 파이프라인 python3이 시작할 때 TLS 검증을 macOS 시스템 신뢰 저장소로 돌린다.

lib/python_env.sh 가 이 폴더를 PYTHONPATH에 넣어서, 파이프라인 스크립트가 띄우는
모든 python3 프로세스에 적용된다.

certifi 번들만 쓰는 OpenSSL은 서버가 중간 인증서를 빼먹으면(KISA 등 일부 공공기관)
'unable to get local issuer certificate'로 실패한다. 시스템 신뢰 저장소는 브라우저처럼
빠진 중간 인증서를 채워 검증한다. truststore가 없으면 아무것도 하지 않는다.
"""
try:
    import truststore
except ImportError:
    pass
else:
    truststore.inject_into_ssl()
