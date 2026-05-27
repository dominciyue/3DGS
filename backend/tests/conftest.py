"""Test config: force mock mode with zero delay before any app import."""
import os
import tempfile

os.environ["PIPELINE_MOCK"] = "1"
os.environ["MOCK_STAGE_DELAY"] = "0"
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="3dgs_test_"))
# Ensure no real LLM is attempted during tests.
os.environ.pop("ANTHROPIC_API_KEY", None)
