from pathlib import Path
import os
import sys
import unittest


ROOT = Path(__file__).resolve().parents[3]
for path in [
    ROOT / "services" / "f5tts-service",
    ROOT / "local-tts-service-kit" / "src",
    ROOT / "local-tts-protocol" / "src",
]:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


class F5TTSServiceCheckpointSelectionTest(unittest.TestCase):
    def test_prefers_official_base_checkpoint_over_local_finetune_ckpts(self):
        os.environ.pop("F5_CKPT_FILE", None)

        from app import handler

        ckpt_file = Path(handler.find_local_ckpt_file())

        self.assertEqual("F5TTS_Base", handler.MODEL_NAME)
        self.assertIn("models--SWivid--F5-TTS", str(ckpt_file))
        self.assertEqual("model_1200000.safetensors", ckpt_file.name)


if __name__ == "__main__":
    unittest.main()
