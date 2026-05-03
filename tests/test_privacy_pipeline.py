import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
EXTRACT_SCRIPT = ROOT / "data-processing" / "extract_and_blur_frames.py"


try:
    import cv2  # type: ignore
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - handled by skip in setUpClass
    cv2 = None
    np = None


def load_extract_module():
    spec = importlib.util.spec_from_file_location("extract_and_blur_frames", EXTRACT_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakePetDetector:
    metadata = {
        "backend": "fake",
        "model": "unit-test",
        "confidence_threshold": 0.8,
    }

    def __init__(self, detected_indices):
        self.detected_indices = set(detected_indices)

    def detect(self, frame, source_frame_index=None):
        if source_frame_index not in self.detected_indices:
            return []
        return [
            {
                "box": [120, 90, 80, 60],
                "confidence": 0.93,
                "label": "dog",
            }
        ]


class PrivacyPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if cv2 is None or np is None:
            raise unittest.SkipTest("opencv-python and numpy are required for privacy tests.")
        cls.extract = load_extract_module()

    def make_args(self, video_path, output_dir, **overrides):
        values = {
            "video_path": str(video_path),
            "output_dir": str(output_dir),
            "frame_interval_seconds": 1.0,
            "max_frames": 30,
            "min_usable_frames": 3,
            "sampling_passes": 3,
            "detector_model": "unused.pt",
            "detection_confidence_threshold": 0.35,
            "pet_class_names": "cat,dog,bird,horse,sheep,cow",
            "box_padding_ratio": 0.0,
            "redaction_block_size": 61,
            "redaction_mode": "solid",
            "redaction_color": "0,0,0",
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def write_video(self, path, frame_count=18, fps=6):
        width, height = 320, 240
        writer = cv2.VideoWriter(
            str(path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (width, height),
        )
        for index in range(frame_count):
            frame = np.full((height, width, 3), 230, dtype=np.uint8)
            cv2.putText(
                frame,
                f"PRIVATE ROOM TEXT {index:02d}",
                (15, 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (10, 10, 10),
                2,
            )
            cv2.rectangle(frame, (120, 90), (200, 150), (20, 180, 80), -1)
            writer.write(frame)
        writer.release()

    def test_detector_frames_are_redacted_and_written_after_resampling(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video_path = tmp_path / "sample.mp4"
            output_dir = tmp_path / "processed"
            self.write_video(video_path)

            detector = FakePetDetector({2, 8, 14})
            args = self.make_args(video_path, output_dir)
            result = self.extract.process_video(args, detector=detector)

            self.assertEqual(result, 0)
            manifest = json.loads((output_dir / "frames_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "ok")
            self.assertEqual(manifest["usable_frame_count"], 3)
            self.assertEqual(manifest["sampling_passes_completed"], 2)
            self.assertEqual([frame["source_frame_index"] for frame in manifest["frames"]], [2, 8, 14])

            frame = manifest["frames"][0]
            self.assertEqual(frame["pet_box_method"], "detector")
            self.assertEqual(frame["privacy_status"], "protected")
            self.assertTrue(frame["share_allowed"])
            self.assertEqual(frame["pet_label"], "pet")
            self.assertEqual(frame["detector_pet_class"], "dog")
            self.assertAlmostEqual(frame["detector_pet_class_confidence"], 0.93)
            self.assertTrue(
                manifest["privacy_policy"]["detector_class_labels_are_localization_only"]
            )

            image = cv2.imread(frame["processed_frame_path"])
            self.assertIsNotNone(image)
            self.assertLess(float(image[25, 25].mean()), 8.0)
            self.assertGreater(float(image[110, 140].mean()), 30.0)

    def test_not_enough_detected_frames_rejects_and_removes_partials(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video_path = tmp_path / "sample.mp4"
            output_dir = tmp_path / "processed"
            self.write_video(video_path)

            detector = FakePetDetector({2})
            args = self.make_args(video_path, output_dir, min_usable_frames=2)
            result = self.extract.process_video(args, detector=detector)

            self.assertEqual(result, 0)
            manifest = json.loads((output_dir / "frames_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "rejected")
            self.assertEqual(manifest["reject_reason"], "not_enough_detected_pet_frames")
            self.assertEqual(manifest["partial_usable_frame_count"], 1)
            self.assertEqual(manifest["usable_frame_count"], 0)
            self.assertEqual(manifest["frames"], [])
            self.assertEqual(list(output_dir.glob("frame_*.jpg")), [])

    def test_no_detector_output_discards_every_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video_path = tmp_path / "sample.mp4"
            output_dir = tmp_path / "processed"
            self.write_video(video_path)

            detector = FakePetDetector(set())
            args = self.make_args(video_path, output_dir)
            result = self.extract.process_video(args, detector=detector)

            self.assertEqual(result, 0)
            manifest = json.loads((output_dir / "frames_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "rejected")
            self.assertEqual(manifest["discarded_frame_count"], 9)
            self.assertEqual(manifest["frames"], [])
            self.assertIn("Ask the user for a clearer pet video.", manifest["message"])


if __name__ == "__main__":
    unittest.main()
