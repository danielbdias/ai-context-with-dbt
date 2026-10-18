"""HTTP routes: the single page, the form handler and the health check."""

from pathlib import Path

from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from web import csrf
from web.auth import hash_ip, is_rate_limited, verify_password
from web.db import check_database, record_attempt, save_submission
from web.logs import log_event
from web.settings import Settings
from web.ua import parse_user_agent
from web.validation import clean_message

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

REJECTION_STATUS = {
    "csrf": 403,
    "rate_limited": 429,
    "invalid_input": 400,
    "bad_password": 401,
}
REJECTION_TEXT = {
    "csrf": "Your form expired. Please try again.",
    "rate_limited": "Too many failed attempts. Please wait and try again.",
    "invalid_input": "The message must be between 1 and {max} characters.",
    "bad_password": "Wrong password.",
}


def render_page(
    request: Request,
    *,
    status_code: int = 200,
    ok: bool = False,
    error: str | None = None,
    message: str = "",
) -> Response:
    """Render the page, reusing a valid CSRF cookie or issuing a new one."""
    settings: Settings = request.app.state.settings
    secret = settings.csrf_secret.get_secret_value()
    cookie = request.cookies.get(csrf.CSRF_COOKIE)
    reusable = bool(cookie and csrf.is_signed(cookie, secret))
    token = cookie if cookie and reusable else csrf.issue_token(secret)
    response = templates.TemplateResponse(
        request,
        "index.html",
        {
            "csrf_token": token,
            "ok": ok,
            "error": error,
            "message": message,
            "max_length": settings.message_max_length,
        },
        status_code=status_code,
    )
    if not reusable:
        response.set_cookie(csrf.CSRF_COOKIE, token, httponly=True, samesite="strict")
    return response


@router.get("/healthz")
def healthz(request: Request) -> JSONResponse:
    """Report liveness and whether the database answers."""
    if check_database(request.app.state.pool):
        return JSONResponse({"status": "ok"})
    return JSONResponse({"status": "unavailable"}, status_code=503)


@router.get("/")
def index(request: Request) -> Response:
    """Show the form; `?ok=1` shows the success flash after a redirect."""
    return render_page(request, ok=request.query_params.get("ok") == "1")


def find_rejection(
    request: Request, ip_hash: str, form_token: str, password: str, cleaned: str | None
) -> str | None:
    """Return the first failing check as an auth_attempts reason, if any."""
    settings: Settings = request.app.state.settings
    secret = settings.csrf_secret.get_secret_value()
    if not csrf.is_valid(request.cookies.get(csrf.CSRF_COOKIE), form_token, secret):
        return "csrf"
    with request.app.state.pool.connection() as conn:
        if is_rate_limited(conn, ip_hash, settings):
            return "rate_limited"
    if cleaned is None:
        return "invalid_input"
    if not verify_password(password, settings.app_password.get_secret_value()):
        return "bad_password"
    return None


def reject(request: Request, ip_hash: str, reason: str, message: str) -> Response:
    """Audit a failed attempt and render the page with its error."""
    with request.app.state.pool.connection() as conn:
        record_attempt(conn, ip_hash, reason)
    log_event("rejected", request_id=request.state.request_id, reason=reason)
    max_length = request.app.state.settings.message_max_length
    return render_page(
        request,
        status_code=REJECTION_STATUS[reason],
        error=REJECTION_TEXT[reason].format(max=max_length),
        message=message,
    )


def accept(request: Request, ip_hash: str, cleaned: str) -> Response:
    """Store the submission and redirect (Post/Redirect/Get)."""
    settings: Settings = request.app.state.settings
    user_agent = request.headers.get("user-agent", "")[: settings.user_agent_max_length]
    language = request.headers.get("accept-language")
    with request.app.state.pool.connection() as conn:
        submission_id = save_submission(
            conn,
            message=cleaned,
            client=parse_user_agent(user_agent),
            user_agent=user_agent,
            accept_language=language[: settings.accept_language_max_length]
            if language
            else None,
            ip_hash=ip_hash,
        )
    log_event(
        "submission_saved",
        request_id=request.state.request_id,
        submission_id=submission_id,
    )
    return RedirectResponse("/?ok=1", status_code=303)


@router.post("/")
def submit(
    request: Request,
    password: str = Form(""),
    message: str = Form(""),
    csrf_token: str = Form(""),
) -> Response:
    """Validate the form and store a submission or audit the rejection."""
    settings: Settings = request.app.state.settings
    host = request.client.host if request.client else None
    ip_hash = hash_ip(host, settings.ip_salt.get_secret_value())
    cleaned = clean_message(message, settings.message_max_length)
    reason = find_rejection(request, ip_hash, csrf_token, password, cleaned)
    if reason or cleaned is None:
        return reject(request, ip_hash, reason or "invalid_input", message)
    return accept(request, ip_hash, cleaned)
