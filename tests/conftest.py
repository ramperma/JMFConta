"""Conftest: añade src/ al sys.path para que `import jmfconta` funcione."""
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
