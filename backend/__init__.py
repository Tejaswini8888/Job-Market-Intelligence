"""FastAPI backend for the Job Market Intelligence platform.

The package only exists so the app can be started and tested as
``backend.app.main:app``. It holds nothing itself; the application module lives
in :mod:`backend.app` and stays importable from the project root thanks to
``pythonpath = .`` in ``pytest.ini``.
"""