"""Entry point: ``PYTHONPATH=src python3 -m seance`` (or ``python3 src/seance``) from the repository root."""
import os
import sys

if not __package__:  # started as ``python3 src/seance``: make the package importable
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from seance.cli import main  # noqa: E402

sys.exit(main())
