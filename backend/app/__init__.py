"""FastAPI application package.

Three small modules, one job each:

* :mod:`backend.app.schemas` - every request and response shape, so the API
  contract is visible in one file and validated by Pydantic at the edge.
* :mod:`backend.app.services` - plain functions that fetch data (through
  ``src.data.queries``), run the rule-based Skill Gap Analyzer, and run the
  ML role recommender. No HTTP details live here.
* :mod:`backend.app.main` - the FastAPI app: the routes are thin wrappers over
  the services, with CORS and exception handlers.
"""