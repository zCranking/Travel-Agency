"""Unit tests must not depend on developer credentials or touch the network.

`api/.env` carries a real Duffel token for live testing. Without this, importing
`agent.tools` builds a RealDuffelClient and any test exercising the booking path
would make real Duffel API calls — slow, flaky, and creating real test orders.
Environment variables take precedence over `.env` in pydantic-settings, so
blanking the token here forces MockDuffelClient across the whole suite.

Tests that exercise RealDuffelClient construct it explicitly with a fake token
and mock httpx, so they are unaffected.
"""
import os

os.environ["DUFFEL_ACCESS_TOKEN"] = ""
