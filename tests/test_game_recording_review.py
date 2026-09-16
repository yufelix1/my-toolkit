import json
import os
import tempfile
import unittest

from flask import Flask

from tools.game_recording_review.routes import (
    FAVORITES_FILENAME,
    delete_empty_recording_directories,
    delete_recording,
    game_recording_review_bp,
    scan_recordings,
    set_recording_favorite,
)


class GameRecordingReviewTestCase(unittest.TestCase):
    def create_recording_tree(self, root):
        random_dir = os.path.join(root, "18284674457949499456", "648524933912092428")
        os.makedirs(random_dir)
        video_path = os.path.join(random_dir, "53d3feac60d0ee1c194e0fe220339e3e.mp4")
        cover_path = os.path.join(random_dir, "53d3feac60d0ee1c194e0fe220339e3e.jpeg")
        second_video = os.path.join(random_dir, "second.mp4")
        for path, content in (
            (video_path, b"video-one"),
            (cover_path, b"cover"),
            (second_video, b"video-two"),
        ):
            with open(path, "wb") as file:
                file.write(content)

        empty_dir = os.path.join(root, "18284674457949499456", "empty-directory")
        os.mkdir(empty_dir)
        orphan_dir = os.path.join(root, "18284674457949499456", "cover-only")
        os.mkdir(orphan_dir)
        with open(os.path.join(orphan_dir, "orphan.jpeg"), "wb") as file:
            file.write(b"orphan")
        return video_path, cover_path, second_video, empty_dir, orphan_dir

    def test_scan_groups_multiple_videos_and_finds_only_truly_empty_directories(self):
        with tempfile.TemporaryDirectory() as root:
            self.create_recording_tree(root)

            result = scan_recordings(root)

            self.assertEqual(result["summary"]["game_count"], 1)
            self.assertEqual(result["summary"]["directory_count"], 3)
            self.assertEqual(result["summary"]["recording_count"], 2)
            self.assertEqual(result["summary"]["empty_directory_count"], 1)
            recordings = result["games"][0]["recordings"]
            covered = next(item for item in recordings if item["name"].startswith("53d3"))
            self.assertTrue(covered["cover_path"].endswith(".jpeg"))
            self.assertFalse(covered["favorite"])
            self.assertIsNone(covered["favorited_at"])
            self.assertEqual(result["empty_directories"][0]["directory_id"], "empty-directory")
            self.assertEqual(result["errors"], [])

    def test_favorite_persists_in_root_metadata_and_scan_result(self):
        with tempfile.TemporaryDirectory() as root:
            video_path, _, _, _, _ = self.create_recording_tree(root)
            relative_path = os.path.relpath(video_path, root)

            favorite = set_recording_favorite(root, relative_path, True)

            self.assertTrue(favorite["favorite"])
            self.assertTrue(favorite["favorited_at"].endswith("Z"))
            metadata_path = os.path.join(root, FAVORITES_FILENAME)
            with open(metadata_path, encoding="utf-8") as metadata_file:
                metadata = json.load(metadata_file)
            favorite_key = relative_path.replace(os.sep, "/")
            self.assertIn(favorite_key, metadata["favorites"])

            scanned = scan_recordings(root)
            recording = next(
                item
                for game in scanned["games"]
                for item in game["recordings"]
                if item["path"] == relative_path
            )
            self.assertTrue(recording["favorite"])
            self.assertEqual(recording["favorited_at"], favorite["favorited_at"])
            self.assertEqual(scanned["summary"]["game_count"], 1)

            unfavorite = set_recording_favorite(root, relative_path, False)
            self.assertFalse(unfavorite["favorite"])
            self.assertIsNone(unfavorite["favorited_at"])
            recording = next(
                item
                for game in scan_recordings(root)["games"]
                for item in game["recordings"]
                if item["path"] == relative_path
            )
            self.assertFalse(recording["favorite"])

    def test_scan_reports_malformed_favorite_metadata_without_hiding_recordings(self):
        with tempfile.TemporaryDirectory() as root:
            self.create_recording_tree(root)
            with open(os.path.join(root, FAVORITES_FILENAME), "w", encoding="utf-8") as metadata_file:
                metadata_file.write("not json")

            result = scan_recordings(root)

            self.assertEqual(result["summary"]["recording_count"], 2)
            self.assertEqual(len(result["errors"]), 1)
            self.assertIn(FAVORITES_FILENAME, result["errors"][0])
            self.assertTrue(
                all(
                    not recording["favorite"]
                    for game in result["games"]
                    for recording in game["recordings"]
                )
            )

    def test_delete_recording_removes_its_cover_and_preserves_other_video(self):
        with tempfile.TemporaryDirectory() as root:
            video_path, cover_path, second_video, _, _ = self.create_recording_tree(root)
            stat = os.stat(video_path)
            relative_path = os.path.relpath(video_path, root)

            deleted = delete_recording(root, relative_path, stat.st_size, stat.st_mtime_ns)

            self.assertEqual(len(deleted), 2)
            self.assertFalse(os.path.exists(video_path))
            self.assertFalse(os.path.exists(cover_path))
            self.assertTrue(os.path.isfile(second_video))

    def test_delete_recording_removes_its_favorite_metadata(self):
        with tempfile.TemporaryDirectory() as root:
            video_path, _, _, _, _ = self.create_recording_tree(root)
            stat = os.stat(video_path)
            relative_path = os.path.relpath(video_path, root)
            set_recording_favorite(root, relative_path, True)

            delete_recording(root, relative_path, stat.st_size, stat.st_mtime_ns)

            with open(os.path.join(root, FAVORITES_FILENAME), encoding="utf-8") as metadata_file:
                metadata = json.load(metadata_file)
            self.assertNotIn(relative_path.replace(os.sep, "/"), metadata["favorites"])

    def test_delete_recording_rejects_a_file_changed_after_scan(self):
        with tempfile.TemporaryDirectory() as root:
            video_path, _, _, _, _ = self.create_recording_tree(root)
            stat = os.stat(video_path)
            with open(video_path, "ab") as file:
                file.write(b"changed")

            with self.assertRaisesRegex(RuntimeError, "重新扫描"):
                delete_recording(
                    root,
                    os.path.relpath(video_path, root),
                    stat.st_size,
                    stat.st_mtime_ns,
                )

            self.assertTrue(os.path.isfile(video_path))

    def test_api_deletes_recording_with_browser_safe_mtime(self):
        with tempfile.TemporaryDirectory() as root:
            video_path, cover_path, second_video, _, _ = self.create_recording_tree(root)
            app = Flask(__name__)
            app.register_blueprint(
                game_recording_review_bp,
                url_prefix="/tools/game-recording-review",
            )
            client = app.test_client()

            scan_response = client.post(
                "/tools/game-recording-review/api/scan",
                json={"path": root},
            )
            scan_data = scan_response.get_json()
            recording = next(
                item
                for game in scan_data["games"]
                for item in game["recordings"]
                if item["name"].startswith("53d3")
            )
            self.assertIsInstance(recording["mtime_ns"], str)

            delete_response = client.delete(
                "/tools/game-recording-review/api/recording",
                json={
                    "scan_id": scan_data["scan_id"],
                    "path": recording["path"],
                    "size": recording["size"],
                    "mtime_ns": recording["mtime_ns"],
                },
            )

            self.assertEqual(delete_response.status_code, 200)
            self.assertFalse(os.path.exists(video_path))
            self.assertFalse(os.path.exists(cover_path))
            self.assertTrue(os.path.isfile(second_video))

    def test_favorite_api_updates_and_survives_a_new_scan(self):
        with tempfile.TemporaryDirectory() as root:
            video_path, _, _, _, _ = self.create_recording_tree(root)
            app = Flask(__name__)
            app.register_blueprint(
                game_recording_review_bp,
                url_prefix="/tools/game-recording-review",
            )
            client = app.test_client()

            scan_data = client.post(
                "/tools/game-recording-review/api/scan",
                json={"path": root},
            ).get_json()
            relative_path = os.path.relpath(video_path, root)

            favorite_response = client.patch(
                "/tools/game-recording-review/api/recording/favorite",
                json={
                    "scan_id": scan_data["scan_id"],
                    "path": relative_path,
                    "favorite": True,
                },
            )

            self.assertEqual(favorite_response.status_code, 200)
            self.assertTrue(favorite_response.get_json()["favorite"])
            rescanned = client.post(
                "/tools/game-recording-review/api/scan",
                json={"path": root},
            ).get_json()
            recording = next(
                item
                for game in rescanned["games"]
                for item in game["recordings"]
                if item["path"] == relative_path
            )
            self.assertTrue(recording["favorite"])

    def test_favorite_api_rejects_invalid_state_and_path_traversal(self):
        with tempfile.TemporaryDirectory() as root:
            self.create_recording_tree(root)
            app = Flask(__name__)
            app.register_blueprint(game_recording_review_bp, url_prefix="/tools/game-recording-review")
            client = app.test_client()
            scan_id = client.post(
                "/tools/game-recording-review/api/scan",
                json={"path": root},
            ).get_json()["scan_id"]

            invalid_state = client.patch(
                "/tools/game-recording-review/api/recording/favorite",
                json={
                    "scan_id": scan_id,
                    "path": "game/directory/video.mp4",
                    "favorite": "yes",
                },
            )
            traversal = client.patch(
                "/tools/game-recording-review/api/recording/favorite",
                json={
                    "scan_id": scan_id,
                    "path": "../../outside.mp4",
                    "favorite": True,
                },
            )

            self.assertEqual(invalid_state.status_code, 400)
            self.assertEqual(traversal.status_code, 400)

    def test_empty_cleanup_preserves_nonempty_directories_and_game_directory(self):
        with tempfile.TemporaryDirectory() as root:
            _, _, _, empty_dir, orphan_dir = self.create_recording_tree(root)

            deleted, errors = delete_empty_recording_directories(root)

            self.assertEqual(errors, [])
            self.assertEqual(deleted, [os.path.relpath(empty_dir, root)])
            self.assertFalse(os.path.exists(empty_dir))
            self.assertTrue(os.path.isdir(orphan_dir))
            self.assertTrue(os.path.isdir(os.path.dirname(orphan_dir)))

    def test_api_serves_media_and_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as root:
            video_path, _, _, _, _ = self.create_recording_tree(root)
            app = Flask(__name__)
            app.register_blueprint(game_recording_review_bp, url_prefix="/tools/game-recording-review")
            client = app.test_client()

            scan_response = client.post(
                "/tools/game-recording-review/api/scan",
                json={"path": root},
            )
            self.assertEqual(scan_response.status_code, 200)
            scan_id = scan_response.get_json()["scan_id"]
            relative_path = os.path.relpath(video_path, root)

            media_response = client.get(
                f"/tools/game-recording-review/media/{scan_id}/{relative_path}"
            )
            self.assertEqual(media_response.status_code, 200)
            self.assertEqual(media_response.data, b"video-one")
            media_response.close()

            traversal_response = client.delete(
                "/tools/game-recording-review/api/recording",
                json={
                    "scan_id": scan_id,
                    "path": "../../outside.mp4",
                    "size": 0,
                    "mtime_ns": 0,
                },
            )
            self.assertEqual(traversal_response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
