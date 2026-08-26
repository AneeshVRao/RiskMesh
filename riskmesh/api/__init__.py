"""Read-only HTTP layer over the frozen Tier 0/Tier 1 artifacts.

The data path (artifacts, bands, payloads, audit) is stdlib-only and testable
without a web server. Only `routes.py` and `main.py` import FastAPI.
"""
