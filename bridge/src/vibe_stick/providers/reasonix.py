from __future__ import annotations

import ctypes
import http.cookiejar
import json
import ntpath
import os
import platform
import secrets
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vibe_stick.config.paths import APP_SUPPORT_DIR
from vibe_stick.protocol.state import AgentStatus
from vibe_stick.providers.base import ProviderObservation

DEFAULT_TIMEOUT_SECONDS = 2.0
STARTUP_TIMEOUT_SECONDS = 10.0
START_RETRY_SECONDS = 30.0


class ReasonixClient:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._opener: urllib.request.OpenerDirector | None = None
        self._authenticated_base_url = ""
        self._managed_process: subprocess.Popen[bytes] | None = None
        self._last_start_attempt = 0.0
        self._last_revision = ""
        self._last_changed_at: datetime | None = None
        self._project_root = Path.cwd()
        self._last_error = ""
        self._last_error_at = 0.0

    def observe(self, project_root: Path) -> ProviderObservation:
        self._project_root = project_root
        try:
            runtime_states = self._get_json("/runtime-states")
            status_payload = self._get_json("/status?runtime=1")
            pending_prompts = self._get_json("/pending-prompts")
        except (OSError, ValueError, urllib.error.URLError) as exc:
            self._report_error(exc)
            return _offline_observation(project_root)

        now = datetime.now(timezone.utc)
        revision = _runtime_revision(runtime_states)
        if revision != self._last_revision:
            self._last_revision = revision
            self._last_changed_at = now
        return observation_from_payloads(
            runtime_states,
            status_payload,
            pending_prompts,
            project_root=project_root,
            observed_at=self._last_changed_at or now,
        )

    def _get_json(self, path: str) -> Any:
        with self._lock:
            base_url, token = self._connection()
            if self._opener is None or self._authenticated_base_url != base_url:
                self._opener = urllib.request.build_opener(
                    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
                )
                self._authenticated_base_url = ""
                if token:
                    self._authenticate(base_url, token)
                self._authenticated_base_url = base_url

            request = urllib.request.Request(
                f"{base_url}{path}",
                headers={"Accept": "application/json"},
            )
            try:
                with self._opener.open(request, timeout=_timeout_seconds()) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code != 401 or not token:
                    raise
                self._authenticate(base_url, token)
                with self._opener.open(request, timeout=_timeout_seconds()) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.URLError:
                if (
                    not os.environ.get("VIBE_STICK_REASONIX_BASE_URL", "").strip()
                    and not self._managed_process_alive()
                ):
                    self._invalidate_managed_connection()
                raise

    def _authenticate(self, base_url: str, token: str) -> None:
        assert self._opener is not None
        body = json.dumps({"token": token}).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url}/auth/token",
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with self._opener.open(request, timeout=_timeout_seconds()):
            pass

    def _connection(self) -> tuple[str, str]:
        configured_url = os.environ.get("VIBE_STICK_REASONIX_BASE_URL", "").strip().rstrip("/")
        if configured_url:
            return configured_url, os.environ.get("VIBE_STICK_REASONIX_TOKEN", "").strip()

        reasonix_dir = APP_SUPPORT_DIR / "reasonix"
        port_path = reasonix_dir / "port"
        token_path = reasonix_dir / "token"
        connection = _read_managed_connection(port_path, token_path)
        if connection is not None:
            return connection

        if not _env_bool("VIBE_STICK_REASONIX_MANAGE_SERVE", default=False):
            raise OSError("Reasonix Serve is not configured")

        self._start_managed_serve(reasonix_dir)
        deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            connection = _read_managed_connection(port_path, token_path)
            if connection is not None:
                return connection
            if self._managed_process is not None and self._managed_process.poll() is not None:
                raise OSError("Reasonix Serve exited during startup")
            time.sleep(0.1)
        raise OSError("Timed out waiting for Reasonix Serve")

    def _start_managed_serve(self, reasonix_dir: Path) -> None:
        if self._managed_process_alive():
            raise OSError("Managed Reasonix Serve is already running")
        now = time.monotonic()
        if now - self._last_start_attempt < START_RETRY_SECONDS:
            raise OSError("Reasonix Serve startup is in retry backoff")
        self._last_start_attempt = now

        configured_command = os.environ.get("VIBE_STICK_REASONIX_COMMAND", "").strip()
        executable = configured_command or shutil.which("reasonix")
        if executable is None:
            raise OSError("reasonix is not available on PATH")
        if configured_command and not Path(configured_command).is_file():
            raise OSError(f"Configured Reasonix command does not exist: {configured_command}")

        reasonix_dir.mkdir(parents=True, exist_ok=True)
        port_path = reasonix_dir / "port"
        token_path = reasonix_dir / "token"
        pid_path = reasonix_dir / "pid"
        log_path = reasonix_dir / "serve.log"
        port_path.unlink(missing_ok=True)
        pid_path.unlink(missing_ok=True)
        token_path.write_text(secrets.token_hex(32), encoding="utf-8")

        args = [
            executable,
            "serve",
            "--addr",
            "127.0.0.1:0",
            "--port-file",
            str(port_path),
            "--auth",
            "token",
            "--token-file",
            str(token_path),
            "--pid-file",
            str(pid_path),
        ]
        suffix = Path(executable).suffix.lower()
        use_shell = platform.system() == "Windows" and suffix in {".cmd", ".bat"}
        if platform.system() == "Windows" and suffix == ".ps1":
            command: list[str] | str = [
                shutil.which("powershell.exe") or "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                executable,
                *args[1:],
            ]
        else:
            command = subprocess.list2cmdline(args) if use_shell else args

        creation_flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
        log = log_path.open("ab")
        try:
            self._managed_process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=creation_flags,
                shell=use_shell,
                cwd=str(self._project_root),
            )
        finally:
            log.close()

    def _invalidate_managed_connection(self) -> None:
        self._opener = None
        self._authenticated_base_url = ""
        reasonix_dir = APP_SUPPORT_DIR / "reasonix"
        for name in ("pid", "port", "token"):
            try:
                (reasonix_dir / name).unlink(missing_ok=True)
            except OSError:
                pass

    def _managed_process_alive(self) -> bool:
        if self._managed_process is not None:
            return self._managed_process.poll() is None
        pid_path = APP_SUPPORT_DIR / "reasonix" / "pid"
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return False
        return _pid_is_alive(pid)

    def _report_error(self, exc: Exception) -> None:
        message = f"{type(exc).__name__}: {exc}"
        now = time.monotonic()
        if message != self._last_error or now - self._last_error_at >= 30:
            print(f"reasonix observation failed: {message}", flush=True)
            self._last_error = message
            self._last_error_at = now


def observe_reasonix(project_root: Path) -> ProviderObservation:
    return _CLIENT.observe(project_root)


def observation_from_payloads(
    runtime_states: Any,
    status_payload: Any,
    pending_prompts: Any,
    *,
    project_root: Path,
    observed_at: datetime,
) -> ProviderObservation:
    session = _current_runtime_session(runtime_states)
    runtime = session.get("state") if isinstance(session.get("state"), dict) else {}
    status_data = status_payload if isinstance(status_payload, dict) else {}
    prompt_list = pending_prompts if isinstance(pending_prompts, list) else []
    turn_status = str(runtime.get("turnStatus") or "")
    phase = str(runtime.get("phase") or "")
    turn_id = str(runtime.get("turnId") or "")
    activity = str(runtime.get("activity") or "")
    pending_prompt = bool(prompt_list) or bool(runtime.get("pendingPrompt")) or turn_status == "waiting_user"

    status = AgentStatus.UNKNOWN
    alert_type = "NONE"
    alert_message = ""
    alert_event_id = ""
    if pending_prompt:
        status = AgentStatus.APPROVAL
        alert_type = "APPROVAL"
        alert_message = _pending_prompt_message(prompt_list) or "Reasonix is waiting for approval or input"
        alert_event_id = _event_id("approval", turn_id, runtime)
    elif turn_status in {"failed", "protocol_failed"}:
        status = AgentStatus.ERROR
        alert_type = "ERROR"
        alert_message = activity or "Reasonix task failed"
        alert_event_id = _event_id("error", turn_id, runtime)
    elif turn_status == "interrupted":
        status = AgentStatus.ERROR
        alert_type = "ERROR"
        alert_message = activity or "Reasonix task was interrupted"
        alert_event_id = _event_id("interrupted", turn_id, runtime)
    elif turn_status == "completed":
        status = AgentStatus.DONE
        alert_type = "DONE"
        alert_message = activity or "Reasonix task completed"
        alert_event_id = _event_id("done", turn_id, runtime)
    elif (
        bool(runtime.get("running"))
        or turn_status in {"queued", "in_progress", "cancelling"}
        or phase in {"executing", "finishing"}
    ):
        status = AgentStatus.RUNNING
    elif phase == "closed":
        status = AgentStatus.OFFLINE
    else:
        status = AgentStatus.IDLE

    return ProviderObservation(
        provider_id="reasonix",
        display_name="Reasonix",
        online=status != AgentStatus.OFFLINE,
        status=status,
        project=_project_name(status_data, project_root),
        quota_5h_remaining=None,
        quota_7d_remaining=None,
        quota_updated_at="",
        quota_stale=False,
        alert_type=alert_type,
        alert_message=alert_message,
        alert_event_id=alert_event_id,
        latest_event_timestamp=observed_at,
    )


def _offline_observation(project_root: Path) -> ProviderObservation:
    return ProviderObservation(
        provider_id="reasonix",
        display_name="Reasonix",
        online=False,
        status=AgentStatus.OFFLINE,
        project=_project_name({}, project_root),
        quota_5h_remaining=None,
        quota_7d_remaining=None,
        quota_updated_at="",
        quota_stale=False,
        alert_type="NONE",
        alert_message="",
        alert_event_id="",
        latest_event_timestamp=None,
    )


def _current_runtime_session(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    sessions = payload.get("sessions")
    if not isinstance(sessions, list):
        return {}
    for session in sessions:
        if isinstance(session, dict) and session.get("current") is True:
            return session
    for session in sessions:
        if isinstance(session, dict):
            return session
    return {}


def _runtime_revision(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    session = _current_runtime_session(payload)
    state = session.get("state") if isinstance(session.get("state"), dict) else {}
    return ":".join(
        str(value or "")
        for value in (
            payload.get("epoch"),
            payload.get("revision"),
            state.get("runtimeEpoch"),
            state.get("revision"),
            state.get("turnId"),
            state.get("turnStatus"),
        )
    )


def _pending_prompt_message(prompts: list[Any]) -> str:
    for prompt in prompts:
        if not isinstance(prompt, dict):
            continue
        approval = prompt.get("approval")
        if isinstance(approval, dict):
            subject = str(approval.get("subject") or approval.get("tool") or "")
            if subject:
                return f"Reasonix approval required: {subject}"
        if prompt.get("kind") == "ask_request" or prompt.get("promptKind") == "ask":
            return "Reasonix is waiting for an answer"
    return ""


def _event_id(prefix: str, turn_id: str, runtime: dict[str, Any]) -> str:
    identity = turn_id or str(runtime.get("turnEventSeq") or runtime.get("revision") or "current")
    safe_identity = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in identity)
    return f"evt_reasonix_{safe_identity}_{prefix}"


def _project_name(status_payload: dict[str, Any], project_root: Path) -> str:
    configured = os.environ.get("VIBE_STICK_PROJECT_NAME", "").strip()
    if configured:
        return configured
    project_name = project_root.name
    if project_name:
        return project_name
    cwd = str(status_payload.get("cwd") or "").strip()
    if cwd:
        return ntpath.basename(cwd.rstrip("\\/")) or Path(cwd).name or cwd
    return "reasonix"


def _read_managed_connection(port_path: Path, token_path: Path) -> tuple[str, str] | None:
    try:
        raw_port = port_path.read_text(encoding="utf-8").strip()
        port = int(raw_port.rsplit(":", 1)[-1])
        token = token_path.read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return None
    if not 1 <= port <= 65535 or not token:
        return None
    return f"http://127.0.0.1:{port}", token


def _timeout_seconds() -> float:
    raw = os.environ.get("VIBE_STICK_REASONIX_TIMEOUT_SECONDS", "").strip()
    try:
        value = float(raw) if raw else DEFAULT_TIMEOUT_SECONDS
    except ValueError:
        value = DEFAULT_TIMEOUT_SECONDS
    return max(0.5, min(10.0, value))


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if platform.system() == "Windows":
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False
    return True


_CLIENT = ReasonixClient()
