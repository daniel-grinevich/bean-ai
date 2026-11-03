import json
from pathlib import Path

from bean_ai_backend.main import app

# Snapshot of app.openapi() taken from `production` before the routers/schemas/services/agent split (J46).
# If you change the API on purpose, regenerate it:
#   uv run python -c "import json; from bean_ai_backend.main import app; \
#     print(json.dumps(app.openapi(), indent=2, sort_keys=True))" > tests/snapshots/openapi.json
SNAPSHOT = Path(__file__).parent / "snapshots" / "openapi.json"


def test_openapi_schema_is_unchanged() -> None:
    assert app.openapi() == json.loads(SNAPSHOT.read_text())
