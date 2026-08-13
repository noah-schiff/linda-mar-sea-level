"""One-time Earth Engine authentication for the `coastsat` conda environment.

Run this once -- it will open a browser window asking you to approve access
to your Google Earth Engine project. That approval gets stored as a reusable
token, so future scripts can call authenticate_and_initialize() and connect
silently without prompting again.

Usage (from the project root):
    C:\\Users\\schif\\Miniforge3\\envs\\coastsat\\python.exe scripts\\coastsat\\authenticate_gee.py
"""

import ee

PROJECT_ID = "linda-mar-coastsat"

if __name__ == "__main__":
    # NOTE: neither auth_mode='gcloud' NOR the default (auth_mode=None)
    # work as of Aug 2026 when gcloud is installed -- both delegate to
    # gcloud's own shared/generic OAuth client (the same client ID every
    # `gcloud auth application-default login` on every machine uses; see
    # ee/oauth.py's authenticate(): auth_mode=None only avoids the gcloud
    # branch if gcloud is NOT installed). Google has restricted that
    # shared client from requesting the Drive scope ee.Authenticate() asks
    # for by default -- result: "This app is blocked", unfixable via
    # test-user lists since you don't own that OAuth client. Confirmed via
    # direct Earth Engine REST API calls using gcloud's own token that the
    # project/API-enablement side was never the problem -- it's
    # specifically this shared-client scope block.
    #
    # Fix: explicitly force auth_mode='localhost', which skips the gcloud
    # branch entirely and uses Earth Engine's own dedicated, already
    # Google-verified OAuth client (a different, EE-specific CLIENT_ID in
    # ee/oauth.py) via a short-lived local webserver on localhost:8085.
    ee.Authenticate(auth_mode="localhost")
    ee.Initialize(project=PROJECT_ID)
    print(f"Earth Engine authenticated and initialized for project: {PROJECT_ID}")
