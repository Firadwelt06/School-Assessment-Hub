import json
import os
import re
import secrets
import urllib.parse
import urllib.error
import urllib.request
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
    remote_id = str(item.get("id", ""))
    if not REMOTE_ID_PATTERN.fullmatch(remote_id):
        raise PortalSyncError("The portal returned a question with an invalid identifier.")
    for field in ("subject", "topic", "stem", "option_a", "option_b", "option_c", "option_d"):
        if not isinstance(item.get(field), str) or not item[field].strip():
            raise PortalSyncError(f"The portal returned a question with an invalid {field} field.")
    if item.get("correct_option") not in {"A", "B", "C", "D"}:
        raise PortalSyncError("The portal returned a question with an invalid correct option.")
    if item.get("difficulty") not in {"easy", "medium", "hard"}:
        raise PortalSyncError("The portal returned a question with an invalid difficulty.")
    if item.get("image") not in {None, True, False}:
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

    return {"imported": imported, "decisions_synced": len(synced_ids), "conflicts": conflicts if decisions else []}
