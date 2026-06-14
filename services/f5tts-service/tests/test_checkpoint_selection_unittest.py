from pathlib import Path
import importlib
import os
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
for path in [
    ROOT / "services" / "f5tts-service",
    ROOT / "bobogen-service-kit" / "src",
    ROOT / "bobogen-protocol" / "src",
]:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


class F5TTSServiceCheckpointSelectionTest(unittest.TestCase):
    def test_prefers_official_base_checkpoint_over_local_finetune_ckpts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_dir = Path(temp_dir) / "repo"
            official_ckpt = (
                repo_dir
                / "huggingface"
                / "hub"
                / "models--SWivid--F5-TTS"
                / "snapshots"
                / "snapshot-a"
                / "F5TTS_Base"
                / "model_1200000.safetensors"
            )
            finetune_ckpt = repo_dir / "ckpts" / "model_last.pt"
            official_ckpt.parent.mkdir(parents=True)
            finetune_ckpt.parent.mkdir(parents=True)
            official_ckpt.write_bytes(b"official")
            finetune_ckpt.write_bytes(b"finetune")

            os.environ.pop("F5_CKPT_FILE", None)
            os.environ["F5TTS_REPO_DIR"] = str(repo_dir)
            sys.modules.pop("app.handler", None)
            if "app" in sys.modules and hasattr(sys.modules["app"], "handler"):
                delattr(sys.modules["app"], "handler")

            try:
                handler = importlib.import_module("app.handler")
                ckpt_file = Path(handler.find_local_ckpt_file())
            finally:
                os.environ.pop("F5TTS_REPO_DIR", None)
                sys.modules.pop("app.handler", None)
                if "app" in sys.modules and hasattr(sys.modules["app"], "handler"):
                    delattr(sys.modules["app"], "handler")

            self.assertEqual("F5TTS_Base", handler.MODEL_NAME)
            self.assertIn("models--SWivid--F5-TTS", str(ckpt_file))
            self.assertEqual("model_1200000.safetensors", ckpt_file.name)


if __name__ == "__main__":
    unittest.main()
