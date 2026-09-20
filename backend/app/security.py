"""배포용 접근 제어: 환경변수 APP_PASSWORD 가 있으면 모든 요청에 HTTP Basic 인증을 요구한다.

운영 모드(MARINE_ENV=production)에서 APP_PASSWORD 없이 뜨는 것은 기본적으로 막는다(문서 업로드·삭제·초기화·API 요금이
누구에게나 열리는 것을 방지). 의도적으로 열려면 MARINE_ALLOW_OPEN=1 을 명시해야 한다.
"""
import base64
import os
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse

PUBLIC_PATHS = {"/healthz"}      # 배포 플랫폼의 헬스 체크용(내용 없음)


class BasicAuth(BaseHTTPMiddleware):
    def __init__(self, app, user: str, password: str):
        super().__init__(app)
        self.user, self.password = user.encode(), password.encode()

    async def dispatch(self, request, call_next):
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)
        header = request.headers.get("authorization", "")
        if header.lower().startswith("basic "):
            try:
                u, _, p = base64.b64decode(header[6:]).partition(b":")
                if secrets.compare_digest(u, self.user) & secrets.compare_digest(p, self.password):
                    return await call_next(request)
            except Exception:
                pass
        return PlainTextResponse("인증이 필요합니다.", status_code=401, headers={"WWW-Authenticate": 'Basic realm="SpecBridge"'})


def install(app) -> None:
    password = os.environ.get("APP_PASSWORD", "")
    if password:
        app.add_middleware(BasicAuth, user=os.environ.get("APP_USER", "team"), password=password)
    elif os.environ.get("MARINE_ENV") == "production" and os.environ.get("MARINE_ALLOW_OPEN") != "1":
        raise RuntimeError("운영 모드에서는 APP_PASSWORD 를 설정해야 합니다(공개 접근을 의도하면 MARINE_ALLOW_OPEN=1).")
