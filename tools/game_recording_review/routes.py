import os
import secrets
from collections import OrderedDict
from threading import Lock

from flask import Blueprint, jsonify, render_template, request, send_from_directory


game_recording_review_bp = Blueprint(
    "game_recording_review",
    __name__,
    template_folder="../../templates/game_recording_review",
)

VIDEO_EXTENSIONS = {".mp4"}
COVER_EXTENSIONS = (".jpeg", ".jpg", ".png", ".webp")
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | set(COVER_EXTENSIONS)
MAX_SCAN_SESSIONS = 32

_scan_roots = OrderedDict()
_scan_roots_lock = Lock()


def validate_root(root_path):
    if not isinstance(root_path, str) or not root_path.strip():
        return None, "请输入录屏根目录"

    normalized_root = os.path.realpath(os.path.expanduser(root_path.strip()))
    if not os.path.isdir(normalized_root):
        return None, f"路径不存在或不是目录：{normalized_root}"

    return normalized_root, None


def _record_error(errors, path, error):
    errors.append(f"{path}：{getattr(error, 'strerror', None) or str(error)}")


def _directory_entries(path, errors):
    try:
        with os.scandir(path) as entries:
            return sorted(entries, key=lambda entry: entry.name.lower())
    except OSError as error:
        _record_error(errors, path, error)
        return None


def scan_recordings(root_path):
    """Scan root/game_id/random_directory without following symbolic links."""
    root_path, validation_error = validate_root(root_path)
    if validation_error:
        raise ValueError(validation_error)

    errors = []
    games = []
    empty_directories = []
    directory_count = 0

    for game_entry in _directory_entries(root_path, errors) or ():
        try:
            if not game_entry.is_dir(follow_symlinks=False):
                continue
        except OSError as error:
            _record_error(errors, game_entry.path, error)
            continue

        recordings = []
        game_directory_count = 0

        for random_entry in _directory_entries(game_entry.path, errors) or ():
            try:
                if not random_entry.is_dir(follow_symlinks=False):
                    continue
            except OSError as error:
                _record_error(errors, random_entry.path, error)
                continue

            directory_count += 1
            game_directory_count += 1
            entries = _directory_entries(random_entry.path, errors)
            directory_path = os.path.join(game_entry.name, random_entry.name)

            if entries is None:
                continue

            if not entries:
                empty_directories.append(
                    {
                        "game_id": game_entry.name,
                        "directory_id": random_entry.name,
                        "path": directory_path,
                    }
                )
                continue

            covers = {}
            videos = []
            for media_entry in entries:
                try:
                    if not media_entry.is_file(follow_symlinks=False):
                        continue
                except OSError as error:
                    _record_error(errors, media_entry.path, error)
                    continue

                stem, extension = os.path.splitext(media_entry.name)
                extension = extension.lower()
                if extension in COVER_EXTENSIONS:
                    covers.setdefault(stem.lower(), {})[extension] = media_entry.name
                elif extension in VIDEO_EXTENSIONS:
                    videos.append(media_entry)

            for video_entry in videos:
                try:
                    stat = video_entry.stat(follow_symlinks=False)
                except OSError as error:
                    _record_error(errors, video_entry.path, error)
                    continue

                stem = os.path.splitext(video_entry.name)[0]
                matching_covers = covers.get(stem.lower(), {})
                cover_name = next(
                    (matching_covers[extension] for extension in COVER_EXTENSIONS if extension in matching_covers),
                    None,
                )
                recordings.append(
                    {
                        "game_id": game_entry.name,
                        "directory_id": random_entry.name,
                        "directory_path": directory_path,
                        "name": video_entry.name,
                        "path": os.path.join(directory_path, video_entry.name),
                        "cover_path": os.path.join(directory_path, cover_name) if cover_name else None,
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                        "mtime_ns": stat.st_mtime_ns,
                    }
                )

        recordings.sort(key=lambda item: (-item["mtime"], item["name"].lower()))
        games.append(
            {
                "game_id": game_entry.name,
                "directory_count": game_directory_count,
                "recordings": recordings,
            }
        )

    return {
        "root": root_path,
        "summary": {
            "game_count": len(games),
            "directory_count": directory_count,
            "recording_count": sum(len(game["recordings"]) for game in games),
            "empty_directory_count": len(empty_directories),
        },
        "games": games,
        "empty_directories": empty_directories,
        "errors": errors,
    }


def _remember_root(root_path):
    scan_id = secrets.token_urlsafe(18)
    with _scan_roots_lock:
        _scan_roots[scan_id] = root_path
        _scan_roots.move_to_end(scan_id)
        while len(_scan_roots) > MAX_SCAN_SESSIONS:
            _scan_roots.popitem(last=False)
    return scan_id


def _get_scan_root(scan_id):
    if not isinstance(scan_id, str):
        return None
    with _scan_roots_lock:
        root_path = _scan_roots.get(scan_id)
        if root_path:
            _scan_roots.move_to_end(scan_id)
        return root_path


def _resolve_relative_path(root_path, relative_path, expected_parts, extensions=None):
    if not isinstance(relative_path, str):
        raise ValueError("路径参数无效")

    parts = relative_path.replace("\\", "/").split("/")
    if len(parts) not in expected_parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("路径参数无效")

    root_path = os.path.realpath(root_path)
    normalized_relative_path = os.path.join(*parts)
    unresolved_path = os.path.join(root_path, normalized_relative_path)
    resolved_path = os.path.realpath(unresolved_path)
    if os.path.commonpath([root_path, resolved_path]) != root_path:
        raise ValueError("路径超出录屏根目录")
    if os.path.islink(unresolved_path):
        raise ValueError("不支持符号链接")
    if extensions and os.path.splitext(resolved_path)[1].lower() not in extensions:
        raise ValueError("文件类型不受支持")

    return resolved_path, normalized_relative_path


def delete_recording(root_path, relative_path, expected_size, expected_mtime_ns):
    video_path, normalized_relative_path = _resolve_relative_path(
        root_path,
        relative_path,
        expected_parts={3},
        extensions=VIDEO_EXTENSIONS,
    )
    if not os.path.isfile(video_path):
        raise FileNotFoundError("录屏文件不存在，请重新扫描")

    try:
        expected_size = int(expected_size)
        expected_mtime_ns = int(expected_mtime_ns)
    except (TypeError, ValueError) as error:
        raise ValueError("录屏校验信息无效") from error

    stat = os.stat(video_path, follow_symlinks=False)
    if stat.st_size != expected_size or stat.st_mtime_ns != expected_mtime_ns:
        raise RuntimeError("录屏文件在扫描后发生变化，请重新扫描")

    os.remove(video_path)
    deleted = [normalized_relative_path]
    video_stem = os.path.splitext(os.path.basename(video_path))[0].lower()

    for entry in os.scandir(os.path.dirname(video_path)):
        stem, extension = os.path.splitext(entry.name)
        try:
            is_regular_file = entry.is_file(follow_symlinks=False)
        except OSError:
            is_regular_file = False
        if is_regular_file and stem.lower() == video_stem and extension.lower() in COVER_EXTENSIONS:
            os.remove(entry.path)
            deleted.append(os.path.join(os.path.dirname(normalized_relative_path), entry.name))

    return deleted


def find_empty_recording_directories(root_path):
    root_path, validation_error = validate_root(root_path)
    if validation_error:
        raise ValueError(validation_error)

    errors = []
    empty_directories = []
    for game_entry in _directory_entries(root_path, errors) or ():
        try:
            if not game_entry.is_dir(follow_symlinks=False):
                continue
        except OSError as error:
            _record_error(errors, game_entry.path, error)
            continue

        for random_entry in _directory_entries(game_entry.path, errors) or ():
            try:
                if not random_entry.is_dir(follow_symlinks=False):
                    continue
                entries = _directory_entries(random_entry.path, errors)
                if entries == []:
                    empty_directories.append(os.path.join(game_entry.name, random_entry.name))
            except OSError as error:
                _record_error(errors, random_entry.path, error)

    return empty_directories, errors


def delete_empty_recording_directories(root_path, relative_path=None):
    if relative_path is None:
        candidates, errors = find_empty_recording_directories(root_path)
    else:
        candidates, errors = [relative_path], []

    deleted = []
    for candidate in candidates:
        try:
            directory_path, normalized_relative_path = _resolve_relative_path(
                root_path,
                candidate,
                expected_parts={2},
            )
            os.rmdir(directory_path)
            deleted.append(normalized_relative_path)
        except (OSError, ValueError) as error:
            error_path = candidate if isinstance(candidate, str) else root_path
            _record_error(errors, error_path, error)

    return deleted, errors


def _json_error(message, status_code):
    return jsonify({"success": False, "message": message}), status_code


@game_recording_review_bp.route("/")
def index():
    return render_template("game_recording_review/index.html")


@game_recording_review_bp.route("/api/scan", methods=["POST"])
def api_scan():
    data = request.get_json(silent=True) or {}
    root_path, validation_error = validate_root(data.get("path"))
    if validation_error:
        return _json_error(validation_error, 400)

    result = scan_recordings(root_path)
    result["scan_id"] = _remember_root(root_path)
    result["success"] = not result["errors"]
    return jsonify(result)


@game_recording_review_bp.route("/media/<scan_id>/<path:relative_path>")
def media(scan_id, relative_path):
    root_path = _get_scan_root(scan_id)
    if not root_path:
        return _json_error("扫描已失效，请重新扫描", 404)

    try:
        media_path, normalized_relative_path = _resolve_relative_path(
            root_path,
            relative_path,
            expected_parts={3},
            extensions=MEDIA_EXTENSIONS,
        )
    except ValueError as error:
        return _json_error(str(error), 400)

    if not os.path.isfile(media_path):
        return _json_error("媒体文件不存在", 404)
    return send_from_directory(root_path, normalized_relative_path, conditional=True)


@game_recording_review_bp.route("/api/recording", methods=["DELETE"])
def api_delete_recording():
    data = request.get_json(silent=True) or {}
    root_path = _get_scan_root(data.get("scan_id"))
    if not root_path:
        return _json_error("扫描已失效，请重新扫描", 404)

    try:
        deleted = delete_recording(
            root_path,
            data.get("path"),
            data.get("size"),
            data.get("mtime_ns"),
        )
    except ValueError as error:
        return _json_error(str(error), 400)
    except FileNotFoundError as error:
        return _json_error(str(error), 404)
    except RuntimeError as error:
        return _json_error(str(error), 409)
    except OSError as error:
        return _json_error(error.strerror or str(error), 409)

    return jsonify({"success": True, "deleted": deleted})


@game_recording_review_bp.route("/api/empty-directories", methods=["DELETE"])
def api_delete_empty_directories():
    data = request.get_json(silent=True) or {}
    root_path = _get_scan_root(data.get("scan_id"))
    if not root_path:
        return _json_error("扫描已失效，请重新扫描", 404)

    deleted, errors = delete_empty_recording_directories(root_path, data.get("path"))
    return jsonify(
        {
            "success": not errors,
            "deleted": deleted,
            "errors": errors,
            "message": f"已删除 {len(deleted)} 个空目录",
        }
    )
