import base64
import json
import hashlib
import os
import re
import secrets
import urllib.parse
import urllib.error
import urllib.request
import uuid
from pathlib import Path


REMOTE_ID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
IMAGE_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}
BRAND_IMAGE_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}
BRAND_LOGO_MAX_BYTES = 4 * 1024 * 1024


class PortalSyncError(RuntimeError):
    pass


class _PortalRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        redirected = super().redirect_request(
            request,
            file_pointer,
            code,
            message,
            headers,
            new_url,
        )
        if redirected:
            source = urllib.parse.urlsplit(request.full_url)
            target = urllib.parse.urlsplit(new_url)
            if (source.scheme, source.netloc) != (target.scheme, target.netloc):
                redirected.remove_header("Authorization")
                redirected.remove_header("Cookie")
        return redirected


def portal_settings():
    base_url = os.getenv("CLOUD_PORTAL_URL", "").strip().rstrip("/")
    token = os.getenv("CLOUD_PORTAL_SYNC_TOKEN", "")
    if not base_url or not token:
        raise PortalSyncError(
            "Configure CLOUD_PORTAL_URL and CLOUD_PORTAL_SYNC_TOKEN in .env before syncing."
        )
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme != "https" and parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise PortalSyncError("CLOUD_PORTAL_URL must use HTTPS.")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise PortalSyncError("CLOUD_PORTAL_URL must be a valid HTTPS portal URL.")
    if len(token) < 32:
        raise PortalSyncError("CLOUD_PORTAL_SYNC_TOKEN must contain at least 32 characters.")
    return base_url, token


def portal_request(path, method="GET", payload=None, binary=False):
    base_url, token = portal_settings()
    request_headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request_headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        headers=request_headers,
        method=method,
    )
    try:
        opener = urllib.request.build_opener(_PortalRedirectHandler())
        with opener.open(request, timeout=30) as response:
            content_type = response.headers.get_content_type()
            body = response.read()
    except urllib.error.HTTPError as error:
        response_text = error.read(2048).decode("utf-8", errors="replace")
        try:
            message = json.loads(response_text).get("error", "")
        except (ValueError, AttributeError):
            message = ""
        cloudflare_ray = error.headers.get("CF-Ray", "") if error.headers else ""
        context = f"Portal {method.upper()} {path} returned HTTP {error.code}"
        if cloudflare_ray:
            context += f" (Cloudflare Ray ID {cloudflare_ray})"
        if message:
            context += f": {message}"
        raise PortalSyncError(f"{context}.") from error
    except urllib.error.URLError as error:
        raise PortalSyncError(f"Could not reach the teacher portal: {error.reason}") from error
    except TimeoutError as error:
        raise PortalSyncError("The teacher portal request timed out.") from error

    if binary:
        return body, content_type
    try:
        response_payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PortalSyncError("The teacher portal returned an invalid JSON response.") from error
    if not isinstance(response_payload, dict):
        raise PortalSyncError("The teacher portal returned an unexpected response.")
    return response_payload


def sync_school_branding(settings, uploads_dir):
    school_name = str(settings.get("school_name", "")).strip()
    if not school_name or len(school_name) > 200:
        raise PortalSyncError("School name must contain 1–200 characters before it can be synced.")

    logo_name = str(settings.get("school_logo", "")).strip()
    payload = {
        "school_name": school_name,
        "logo_content_type": "",
        "logo_base64": "",
    }
    if logo_name:
        if Path(logo_name).name != logo_name:
            raise PortalSyncError("The configured school logo filename is invalid.")
        extension = Path(logo_name).suffix.lower().lstrip(".")
        content_type = BRAND_IMAGE_TYPES.get(extension)
        if not content_type:
            raise PortalSyncError("The school logo must be PNG, JPG, JPEG, or WEBP to sync.")
        logo_path = Path(uploads_dir) / logo_name
        try:
            logo_data = logo_path.read_bytes()
        except OSError as error:
            raise PortalSyncError(f"Could not read the configured school logo: {error}.") from error
        if not logo_data or len(logo_data) > BRAND_LOGO_MAX_BYTES:
            raise PortalSyncError("The school logo must be non-empty and no larger than 4 MB to sync.")
        payload.update({
            "logo_content_type": content_type,
            "logo_base64": base64.b64encode(logo_data).decode("ascii"),
        })

    response = portal_request("/api/sync/branding", method="POST", payload=payload)
    if response.get("ok") is not True:
        raise PortalSyncError("The teacher portal did not confirm the school branding update.")
    return school_name


def download_submission_image(remote_id, uploads_dir):
    if not REMOTE_ID_PATTERN.fullmatch(remote_id):
        raise PortalSyncError("The portal returned an invalid question identifier.")
    image_data, content_type = portal_request(
        f"/api/sync/submissions/{remote_id}/image",
        binary=True,
    )
    extension = IMAGE_TYPES.get(content_type)
    if not extension:
        raise PortalSyncError("The portal returned an unsupported image type.")
    if not image_data or len(image_data) > 5 * 1024 * 1024:
        raise PortalSyncError("A question image was empty or exceeded the 5 MB limit.")

    filename = f"question-{secrets.token_hex(16)}.{extension}"
    Path(uploads_dir).mkdir(parents=True, exist_ok=True)
    image_path = Path(uploads_dir) / filename
    image_path.write_bytes(image_data)
    return filename


def _validate_submission(item):
    if not isinstance(item, dict):
        raise PortalSyncError("The portal returned a malformed question submission.")
    remote_id = item.get("id")
    if not isinstance(remote_id, str) or not REMOTE_ID_PATTERN.fullmatch(remote_id):
        raise PortalSyncError("The portal returned a question with an invalid identifier.")
    for field in (
        "teacher_name", "teacher_username", "subject", "topic", "stem",
        "option_a", "option_b", "option_c", "option_d", "submitted_at",
    ):
        if not isinstance(item.get(field), str) or not item[field].strip():
            raise PortalSyncError(f"The portal returned a question with an invalid {field} field.")
    for field in ("class_name", "explanation", "standard"):
        if field in item and not isinstance(item[field], str):
            raise PortalSyncError(f"The portal returned a question with an invalid {field} field.")
    if not isinstance(item.get("correct_option"), str) or item["correct_option"] not in {"A", "B", "C", "D"}:
        raise PortalSyncError("The portal returned a question with an invalid correct option.")
    if not isinstance(item.get("difficulty"), str) or item["difficulty"] not in {"easy", "medium", "hard"}:
        raise PortalSyncError("The portal returned a question with an invalid difficulty.")
    if item.get("image") is not None and not isinstance(item["image"], bool):
        raise PortalSyncError("The portal returned an invalid image indicator.")


def pull_pending_submissions():
    submissions = []
    cursor = ""
    while True:
        query = urllib.parse.urlencode({"cursor": cursor}) if cursor else ""
        response = portal_request(f"/api/sync/pending{f'?{query}' if query else ''}")
        batch = response.get("submissions")
        next_cursor = response.get("next_cursor", "")
        if not isinstance(batch, list) or not isinstance(next_cursor, str):
            raise PortalSyncError("The portal returned an invalid pending-submissions list.")
        for item in batch:
            _validate_submission(item)
            submissions.append(item)
        if not next_cursor:
            return submissions
        if next_cursor == cursor or (batch and next_cursor != batch[-1].get("id")):
            raise PortalSyncError("The portal returned an invalid pagination cursor.")
        cursor = next_cursor


def pull_reviewed_submissions():
    submissions = []
    cursor = ""
    while True:
        query = urllib.parse.urlencode({"cursor": cursor}) if cursor else ""
        response = portal_request(f"/api/sync/reviewed{f'?{query}' if query else ''}")
        batch = response.get("submissions")
        next_cursor = response.get("next_cursor", "")
        if not isinstance(batch, list) or not isinstance(next_cursor, str):
            raise PortalSyncError("The portal returned an invalid reviewed-submissions list.")
        for item in batch:
            _validate_submission(item)
            if not isinstance(item.get("status"), str) or item["status"] not in {"approved", "rejected"}:
                raise PortalSyncError("The portal returned a review without a valid decision.")
            if not isinstance(item.get("feedback", ""), str):
                raise PortalSyncError("The portal returned invalid review feedback.")
            submissions.append(item)
        if not next_cursor:
            return submissions
        if next_cursor == cursor or (batch and next_cursor != batch[-1].get("id")):
            raise PortalSyncError("The portal returned an invalid reviewed-submissions cursor.")
        cursor = next_cursor


def reset_portal_teacher_password(username, password):
    return portal_request(
        "/api/sync/teachers/reset-password",
        method="POST",
        payload={"username": username, "password": password},
    )


def set_portal_teacher_active(username, active):
    return portal_request(
        "/api/sync/teachers/set-active",
        method="POST",
        payload={"username": username, "active": active},
    )


def set_portal_admin(username, full_name, password):
    return portal_request(
        "/api/sync/admin/set-password",
        method="POST",
        payload={"username": username, "full_name": full_name, "password": password},
    )


def set_portal_teacher_password_hash(username, full_name, password_hash, active=True):
    account = {
        "username": username,
        "full_name": full_name,
        "password_hash": password_hash,
        "active": bool(active),
    }
    if not _valid_teacher_account(account):
        raise PortalSyncError("The teacher account data is invalid.")
    portal_request("/api/sync/teachers/upsert", method="POST", payload=account)
    return {"ok": True}


def teacher_account_fingerprint(account):
    material = "\0".join(
        (
            account["username"],
            account["full_name"],
            account["password_hash"],
            "1" if account["active"] else "0",
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _valid_teacher_account(account):
    valid_scopes = lambda name: (
        account.get(name) is None
        or (
            isinstance(account[name], list)
            and len(account[name]) <= 100
            and all(isinstance(value, str) and 1 <= len(value) <= 120 for value in account[name])
        )
    )
    return (
        isinstance(account, dict)
        and isinstance(account.get("username"), str)
        and re.fullmatch(r"[a-z0-9._-]{3,64}", account["username"]) is not None
        and isinstance(account.get("full_name"), str)
        and 2 <= len(account["full_name"]) <= 100
        and isinstance(account.get("password_hash"), str)
        and (
            re.fullmatch(r"[a-fA-F0-9]{32}\$[a-fA-F0-9]{64}", account["password_hash"])
            or re.fullmatch(
                r"pbkdf2\$100000\$[a-fA-F0-9]{32}\$[a-fA-F0-9]{64}",
                account["password_hash"],
            )
        )
        and isinstance(account.get("active"), bool)
        and valid_scopes("subjects")
        and valid_scopes("classes")
    )


def get_portal_teacher_directory():
    response = portal_request("/api/sync/teachers")
    accounts = response.get("teachers")
    if not isinstance(accounts, list) or any(not _valid_teacher_account(item) for item in accounts):
        raise PortalSyncError("The portal returned an invalid teacher account directory.")
    return [
        {
            "username": account["username"],
            "full_name": account["full_name"],
            "active": account["active"],
            "created_at": account.get("created_at", ""),
        }
        for account in accounts
    ]


def get_portal_admin_directory():
    response = portal_request("/api/sync/admins")
    accounts = response.get("admins")
    if (
        not isinstance(accounts, list)
        or any(
            not isinstance(account, dict)
            or not isinstance(account.get("username"), str)
            or re.fullmatch(r"[a-z0-9._-]{3,64}", account["username"]) is None
            or not isinstance(account.get("full_name"), str)
            or not 2 <= len(account["full_name"]) <= 100
            or not isinstance(account.get("active"), bool)
            for account in accounts
        )
    ):
        raise PortalSyncError("The portal returned an invalid administrator account directory.")
    return [
        {
            "username": account["username"],
            "full_name": account["full_name"],
            "active": account["active"],
        }
        for account in accounts
    ]


def _database_rows(database_engine, database_factory, sql, params=()):
    connection = database_factory()
    try:
        if database_engine == "mysql":
            with connection.cursor() as cursor:
                cursor.execute(sql.replace("?", "%s"), params)
                return cursor.fetchall()
        return connection.execute(sql, params).fetchall()
    finally:
        connection.close()


def _database_write(database_engine, database_factory, sql, params=()):
    connection = database_factory()
    try:
        if database_engine == "mysql":
            with connection.cursor() as cursor:
                cursor.execute(sql.replace("?", "%s"), params)
        else:
            connection.execute(sql, params)
        connection.commit()
    finally:
        connection.close()


def sync_exam_results(database_engine, database_factory):
    source_rows = _database_rows(
        database_engine,
        database_factory,
        "SELECT value FROM settings WHERE `key` = ?",
        ("portal_sync_source_id",),
    )
    if source_rows:
        source_id = source_rows[0]["value"]
    else:
        source_id = str(uuid.uuid4())
        if database_engine == "mysql":
            insert_sql = """INSERT INTO settings (`key`, value) VALUES (?, ?)
            ON DUPLICATE KEY UPDATE value = value"""
        else:
            insert_sql = "INSERT OR IGNORE INTO settings (`key`, value) VALUES (?, ?)"
        _database_write(database_engine, database_factory, insert_sql, ("portal_sync_source_id", source_id))
        source_rows = _database_rows(
            database_engine,
            database_factory,
            "SELECT value FROM settings WHERE `key` = ?",
            ("portal_sync_source_id",),
        )
        source_id = source_rows[0]["value"]

    try:
        source_id = str(uuid.UUID(source_id))
    except (ValueError, TypeError, AttributeError) as error:
        raise PortalSyncError("The local portal sync identifier is invalid.") from error

    rows = _database_rows(
        database_engine,
        database_factory,
        """SELECT a.id AS attempt_id, u.full_name AS student_name, u.username AS student_username,
        u.class_name, e.title, e.subject, e.exam_type, a.score, a.total, a.submitted_at
        FROM attempts a
        JOIN users u ON u.id = a.student_id
        JOIN exams e ON e.id = a.exam_id
        WHERE u.role = 'student' AND a.submitted_at != ''
        ORDER BY a.submitted_at, a.id""",
    )
    results = [
        {
            "id": f"{source_id}:{row['attempt_id']}",
            "student_name": row["student_name"],
            "student_username": row["student_username"],
            "class_name": row["class_name"],
            "title": row["title"],
            "subject": row["subject"],
            "exam_type": row["exam_type"],
            "score": float(row["score"]),
            "total": int(row["total"]),
            "submitted_at": row["submitted_at"],
        }
        for row in rows
    ]

    for offset in range(0, len(results), 100):
        batch = results[offset:offset + 100]
        response = portal_request(
            "/api/sync/results",
            method="POST",
            payload={"source_id": source_id, "results": batch},
        )
        if response.get("ok") is not True or response.get("upserted") != len(batch):
            raise PortalSyncError("The teacher portal did not confirm the exam result sync.")

    current_ids = {result["id"] for result in results}
    synced_ids = {
        row["result_id"]
        for row in _database_rows(
            database_engine,
            database_factory,
            "SELECT result_id FROM portal_result_sync_state",
        )
    }
    removed_ids = sorted(synced_ids - current_ids)
    for offset in range(0, len(removed_ids), 100):
        batch = removed_ids[offset:offset + 100]
        response = portal_request(
            "/api/sync/results/delete",
            method="POST",
            payload={"source_id": source_id, "ids": batch},
        )
        if response.get("ok") is not True or response.get("deleted") != len(batch):
            raise PortalSyncError("The teacher portal did not confirm removal of deleted exam results.")

    _replace_result_sync_state(database_engine, database_factory, sorted(current_ids))
    return {"synced": len(results), "deleted": len(removed_ids)}


def _replace_result_sync_state(database_engine, database_factory, result_ids):
    connection = database_factory()
    try:
        if database_engine == "mysql":
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM portal_result_sync_state")
                if result_ids:
                    cursor.executemany(
                        "INSERT INTO portal_result_sync_state(result_id) VALUES (%s)",
                        [(result_id,) for result_id in result_ids],
                    )
        else:
            connection.execute("DELETE FROM portal_result_sync_state")
            if result_ids:
                connection.executemany(
                    "INSERT INTO portal_result_sync_state(result_id) VALUES (?)",
                    [(result_id,) for result_id in result_ids],
                )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _save_sync_baseline(database_engine, database_factory, username, fingerprint):
    if database_engine == "mysql":
        sql = """INSERT INTO teacher_sync_state(username, synced_fingerprint) VALUES (?, ?)
        ON DUPLICATE KEY UPDATE synced_fingerprint = VALUES(synced_fingerprint)"""
    else:
        sql = """INSERT OR REPLACE INTO teacher_sync_state(username, synced_fingerprint)
        VALUES (?, ?)"""
    _database_write(database_engine, database_factory, sql, (username, fingerprint))
    _database_write(
        database_engine,
        database_factory,
        "DELETE FROM teacher_sync_conflicts WHERE username = ?",
        (username,),
    )


def _record_sync_conflict(database_engine, database_factory, username):
    now = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    if database_engine == "mysql":
        sql = """INSERT INTO teacher_sync_conflicts(username, detected_at) VALUES (?, ?)
        ON DUPLICATE KEY UPDATE detected_at = VALUES(detected_at)"""
    else:
        sql = """INSERT OR REPLACE INTO teacher_sync_conflicts(username, detected_at)
        VALUES (?, ?)"""
    _database_write(database_engine, database_factory, sql, (username, now))


def sync_teacher_accounts(database_engine, database_factory):
    response = portal_request("/api/sync/teachers")
    accounts = response.get("teachers")
    if not isinstance(accounts, list) or any(not _valid_teacher_account(item) for item in accounts):
        raise PortalSyncError("The portal returned an invalid teacher account directory.")
    remote_accounts = {account["username"]: account for account in accounts}
    local_accounts = {}
    assignments = {}
    for row in _database_rows(
        database_engine,
        database_factory,
        "SELECT teacher_id, class_name FROM teacher_class_assignments ORDER BY class_name",
    ):
        assignments.setdefault(row["teacher_id"], []).append(row["class_name"])
    for row in _database_rows(
        database_engine,
        database_factory,
        "SELECT id, username, full_name, password_hash, active, subjects FROM users WHERE role = 'teacher'",
    ):
        local_accounts[row["username"]] = {
            "username": row["username"],
            "full_name": row["full_name"],
            "password_hash": row["password_hash"],
            "active": bool(row["active"]),
            "subjects": sorted({value.strip() for value in (row["subjects"] or "").split(",") if value.strip()}),
            "classes": sorted(set(assignments.get(row["id"], []))),
        }
    baselines = {
        row["username"]: row["synced_fingerprint"]
        for row in _database_rows(
            database_engine,
            database_factory,
            "SELECT username, synced_fingerprint FROM teacher_sync_state",
        )
    }
    imported = pushed = 0
    conflicts = []
    for username in sorted(set(local_accounts) | set(remote_accounts)):
        local = local_accounts.get(username)
        remote = remote_accounts.get(username)
        baseline = baselines.get(username)
        if local is None:
            try:
                _database_write(
                    database_engine,
                    database_factory,
                    """INSERT INTO users(username, full_name, password_hash, role, class_name, subjects, active, created_at)
                    VALUES (?, ?, ?, 'teacher', '', '', ?, ?)""",
                    (
                        remote["username"], remote["full_name"], remote["password_hash"],
                        int(remote["active"]), remote["created_at"] if isinstance(remote.get("created_at"), str)
                        else __import__("datetime").datetime.now().isoformat(timespec="seconds"),
                    ),
                )
            except Exception as error:
                if "unique" not in str(error).lower() and "duplicate" not in str(error).lower():
                    raise
                _record_sync_conflict(database_engine, database_factory, username)
                conflicts.append(username)
                continue
            imported += 1
            _save_sync_baseline(database_engine, database_factory, username, teacher_account_fingerprint(remote))
            continue
        if remote is None:
            portal_request("/api/sync/teachers/upsert", method="POST", payload=local)
            pushed += 1
            _save_sync_baseline(database_engine, database_factory, username, teacher_account_fingerprint(local))
            continue
        local_fingerprint = teacher_account_fingerprint(local)
        remote_fingerprint = teacher_account_fingerprint(remote)
        account_pushed = False
        if local_fingerprint == remote_fingerprint:
            _save_sync_baseline(database_engine, database_factory, username, local_fingerprint)
        elif baseline is None:
            _record_sync_conflict(database_engine, database_factory, username)
            conflicts.append(username)
        else:
            local_changed = local_fingerprint != baseline
            remote_changed = remote_fingerprint != baseline
            if local_changed and not remote_changed:
                portal_request("/api/sync/teachers/upsert", method="POST", payload=local)
                pushed += 1
                account_pushed = True
                _save_sync_baseline(database_engine, database_factory, username, local_fingerprint)
            elif remote_changed and not local_changed:
                _database_write(
                    database_engine,
                    database_factory,
                    """UPDATE users SET full_name = ?, password_hash = ?, active = ?
                    WHERE username = ? AND role = 'teacher'""",
                    (remote["full_name"], remote["password_hash"], int(remote["active"]), username),
                )
                local.update({
                    "full_name": remote["full_name"],
                    "password_hash": remote["password_hash"],
                    "active": remote["active"],
                })
                imported += 1
                _save_sync_baseline(database_engine, database_factory, username, remote_fingerprint)
            else:
                _record_sync_conflict(database_engine, database_factory, username)
                conflicts.append(username)
        if (
            not account_pushed
            and (remote.get("subjects", []) != local["subjects"] or remote.get("classes", []) != local["classes"])
        ):
            portal_request(
                "/api/sync/teachers/scopes",
                method="POST",
                payload={
                    "username": username,
                    "subjects": local["subjects"],
                    "classes": local["classes"],
                },
            )
            pushed += 1
    return {"imported": imported, "pushed": pushed, "conflicts": conflicts}


def resolve_teacher_account_conflict(database_engine, database_factory, username, authority):
    if authority not in {"local", "portal"}:
        raise PortalSyncError("Choose either the local account or the portal account.")
    local_rows = _database_rows(
        database_engine,
        database_factory,
        "SELECT username, full_name, password_hash, active FROM users WHERE username = ? AND role = 'teacher'",
        (username,),
    )
    local = local_rows[0] if local_rows else None
    response = portal_request("/api/sync/teachers")
    accounts = response.get("teachers")
    if not isinstance(accounts, list) or any(not _valid_teacher_account(item) for item in accounts):
        raise PortalSyncError("The portal returned an invalid teacher account directory.")
    remote = next((item for item in accounts if item["username"] == username), None)
    if authority == "local":
        if not local:
            raise PortalSyncError("The local teacher account no longer exists; choose the portal account or recreate the teacher locally.")
        chosen = {
            "username": local["username"],
            "full_name": local["full_name"],
            "password_hash": local["password_hash"],
            "active": bool(local["active"]),
        }
        portal_request("/api/sync/teachers/upsert", method="POST", payload=chosen)
    else:
        if not remote:
            raise PortalSyncError("The portal teacher account no longer exists.")
        if local:
            _database_write(
                database_engine,
                database_factory,
                "UPDATE users SET full_name = ?, password_hash = ?, active = ? WHERE username = ? AND role = 'teacher'",
                (remote["full_name"], remote["password_hash"], int(remote["active"]), username),
            )
        else:
            _database_write(
                database_engine,
                database_factory,
                """INSERT INTO users(username, full_name, password_hash, role, class_name, subjects, active, created_at)
                VALUES (?, ?, ?, 'teacher', '', '', ?, ?)""",
                (remote["username"], remote["full_name"], remote["password_hash"], int(remote["active"]),
                 __import__("datetime").datetime.now().isoformat(timespec="seconds")),
            )
        chosen = remote
    _save_sync_baseline(database_engine, database_factory, username, teacher_account_fingerprint(chosen))


def _apply_online_review_decisions(database_engine, database_factory, uploads_dir):
    reviewed = pull_reviewed_submissions()
    if not reviewed:
        return {"applied": 0, "conflicts": 0}
    applied = conflicts = 0
    admin_rows = _database_rows(database_engine, database_factory, "SELECT id FROM users WHERE role = 'admin' LIMIT 1")
    admin_id = admin_rows[0]["id"] if admin_rows else None
    for item in reviewed:
        connection = database_factory()
        image_path = ""
        existing = None
        try:
            if database_engine == "mysql":
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT status, image_path FROM question_submissions WHERE remote_id = %s",
                        (item["id"],),
                    )
                    existing = cursor.fetchone()
            else:
                existing = connection.execute(
                    "SELECT status, image_path FROM question_submissions WHERE remote_id = ?",
                    (item["id"],),
                ).fetchone()
            if existing and existing["status"] not in {"pending", item["status"]}:
                conflicts += 1
                continue
            if existing and existing["status"] == item["status"]:
                if database_engine == "mysql":
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "UPDATE question_submissions SET decision_synced = 1 WHERE remote_id = %s",
                            (item["id"],),
                        )
                else:
                    connection.execute(
                        "UPDATE question_submissions SET decision_synced = 1 WHERE remote_id = ?",
                        (item["id"],),
                    )
                connection.commit()
                continue

            image_path = (
                existing["image_path"]
                if existing
                else download_submission_image(item["id"], uploads_dir)
                if item.get("image")
                else ""
            )
            if database_engine == "mysql":
                connection.begin()
            else:
                connection.execute("BEGIN IMMEDIATE")
            if existing:
                sql = """UPDATE question_submissions SET status = ?, feedback = ?, reviewed_at = ?,
                decision_synced = 1 WHERE remote_id = ? AND status = 'pending'"""
                params = (item["status"], item.get("feedback", ""), item.get("decided_at", ""), item["id"])
                if database_engine == "mysql":
                    with connection.cursor() as cursor:
                        cursor.execute(sql.replace("?", "%s"), params)
                else:
                    connection.execute(sql, params)
            else:
                sql = """INSERT INTO question_submissions
                (remote_id, teacher_name, teacher_username, subject, topic, class_name, image_path,
                 stem, option_a, option_b, option_c, option_d, correct_option, difficulty,
                 explanation, standard, status, feedback, submitted_at, reviewed_at, decision_synced)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)"""
                params = (
                    item["id"], item["teacher_name"], item["teacher_username"], item["subject"],
                    item["topic"], item.get("class_name", ""), image_path, item["stem"],
                    item["option_a"], item["option_b"], item["option_c"], item["option_d"],
                    item["correct_option"], item["difficulty"], item.get("explanation", ""),
                    item.get("standard", ""), item["status"], item.get("feedback", ""),
                    item["submitted_at"], item.get("decided_at", ""),
                )
                if database_engine == "mysql":
                    with connection.cursor() as cursor:
                        cursor.execute(sql.replace("?", "%s"), params)
                else:
                    connection.execute(sql, params)

            if item["status"] == "approved":
                if database_engine == "mysql":
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT subject, stem FROM questions WHERE subject = %s",
                            (item["subject"],),
                        )
                        existing_questions = cursor.fetchall()
                else:
                    existing_questions = connection.execute(
                        "SELECT subject, stem FROM questions WHERE subject = ?",
                        (item["subject"],),
                    ).fetchall()
                key = " ".join(item["stem"].casefold().split())
                duplicate = any(
                    " ".join(row["stem"].casefold().split()) == key
                    for row in existing_questions
                )
                if not duplicate:
                    sql = """INSERT INTO questions
                    (subject, topic, class_name, image_path, stem, option_a, option_b, option_c, option_d,
                     correct_option, difficulty, explanation, standard, created_by, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
                    params = (
                        item["subject"], item["topic"], item.get("class_name", ""), image_path,
                        item["stem"], item["option_a"], item["option_b"], item["option_c"],
                        item["option_d"], item["correct_option"], item["difficulty"],
                        item.get("explanation", ""), item.get("standard", ""), admin_id,
                        item.get("decided_at") or item["submitted_at"],
                    )
                    if database_engine == "mysql":
                        with connection.cursor() as cursor:
                            cursor.execute(sql.replace("?", "%s"), params)
                    else:
                        connection.execute(sql, params)
            connection.commit()
            applied += 1
        except Exception:
            connection.rollback()
            if image_path and not existing:
                (Path(uploads_dir) / image_path).unlink(missing_ok=True)
            raise
        finally:
            connection.close()
    return {"applied": applied, "conflicts": conflicts}


def sync_question_submissions(database_engine, database_factory, uploads_dir):
    pending = pull_pending_submissions()
    imported = 0
    for item in pending:
        image_path = ""
        if database_engine == "mysql":
            connection = database_factory()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT 1 FROM question_submissions WHERE remote_id = %s",
                        (item["id"],),
                    )
                    exists = cursor.fetchone()
                if exists:
                    continue
                image_path = (
                    download_submission_image(item["id"], uploads_dir)
                    if item.get("image")
                    else ""
                )
                with connection.cursor() as cursor:
                    cursor.execute(
                        """INSERT IGNORE INTO question_submissions
                        (remote_id, teacher_name, teacher_username, subject, topic, class_name,
                        image_path, stem, option_a, option_b, option_c, option_d, correct_option,
                        difficulty, explanation, standard, status, feedback, submitted_at,
                        decision_synced)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        'pending', '', %s, 0)""",
                        (
                            item["id"], item["teacher_name"], item["teacher_username"],
                            item["subject"], item["topic"], item.get("class_name", ""),
                            image_path, item["stem"], item["option_a"], item["option_b"],
                            item["option_c"], item["option_d"], item["correct_option"],
                            item["difficulty"], item.get("explanation", ""),
                            item.get("standard", ""), item["submitted_at"],
                        ),
                    )
                    inserted = cursor.rowcount
                connection.commit()
                imported += int(inserted > 0)
            except Exception:
                connection.rollback()
                if image_path:
                    (Path(uploads_dir) / image_path).unlink(missing_ok=True)
                raise
            finally:
                connection.close()
        else:
            connection = database_factory()
            try:
                if connection.execute(
                    "SELECT 1 FROM question_submissions WHERE remote_id = ?", (item["id"],)
                ).fetchone():
                    continue
                image_path = (
                    download_submission_image(item["id"], uploads_dir)
                    if item.get("image")
                    else ""
                )
                cursor = connection.execute(
                    """INSERT OR IGNORE INTO question_submissions
                    (remote_id, teacher_name, teacher_username, subject, topic, class_name,
                    image_path, stem, option_a, option_b, option_c, option_d, correct_option,
                    difficulty, explanation, standard, status, feedback, submitted_at,
                    decision_synced)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', '', ?, 0)""",
                    (
                        item["id"], item["teacher_name"], item["teacher_username"],
                        item["subject"], item["topic"], item.get("class_name", ""),
                        image_path, item["stem"], item["option_a"], item["option_b"],
                        item["option_c"], item["option_d"], item["correct_option"],
                        item["difficulty"], item.get("explanation", ""),
                        item.get("standard", ""), item["submitted_at"],
                    ),
                )
                connection.commit()
                imported += int(cursor.rowcount > 0)
            except Exception:
                connection.rollback()
                if image_path:
                    (Path(uploads_dir) / image_path).unlink(missing_ok=True)
                raise
            finally:
                connection.close()

    online_reviews = _apply_online_review_decisions(
        database_engine, database_factory, uploads_dir
    )

    connection = database_factory()
    try:
        if database_engine == "mysql":
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT remote_id, status, feedback FROM question_submissions
                    WHERE status IN ('approved', 'rejected') AND decision_synced = 0
                    ORDER BY id LIMIT 100"""
                )
                decisions = cursor.fetchall()
        else:
            decisions = connection.execute(
                """SELECT remote_id, status, feedback FROM question_submissions
                WHERE status IN ('approved', 'rejected') AND decision_synced = 0
                ORDER BY id LIMIT 100"""
            ).fetchall()
    finally:
        connection.close()

    synced_ids = []
    if decisions:
        decision_response = portal_request(
            "/api/sync/decisions",
            method="POST",
            payload={
                "decisions": [
                    {"id": row["remote_id"], "status": row["status"], "feedback": row["feedback"]}
                    for row in decisions
                ]
            },
        )
        synced_ids = decision_response.get("synced_ids")
        conflicts = decision_response.get("conflicts")
        if not isinstance(synced_ids, list) or not isinstance(conflicts, list):
            raise PortalSyncError("The portal returned an invalid decision-sync response.")
        allowed_ids = {row["remote_id"] for row in decisions}
        if any(not isinstance(remote_id, str) or remote_id not in allowed_ids for remote_id in synced_ids):
            raise PortalSyncError("The portal acknowledged a decision that was not sent.")
        if synced_ids:
            connection = database_factory()
            try:
                placeholders = ",".join("?" for _ in synced_ids)
                if database_engine == "mysql":
                    with connection.cursor() as cursor:
                        cursor.execute(
                            f"""UPDATE question_submissions SET decision_synced = 1
                            WHERE remote_id IN ({','.join(['%s'] * len(synced_ids))})""",
                            tuple(synced_ids),
                        )
                else:
                    connection.execute(
                        f"""UPDATE question_submissions SET decision_synced = 1
                        WHERE remote_id IN ({placeholders})""",
                        tuple(synced_ids),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    return {
        "imported": imported,
        "decisions_synced": len(synced_ids),
        "conflicts": conflicts if decisions else [],
        "online_reviews_applied": online_reviews["applied"],
        "online_review_conflicts": online_reviews["conflicts"],
    }
