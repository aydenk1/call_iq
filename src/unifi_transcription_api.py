import json
import os
import time
from pathlib import Path
from typing import Any

import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning # pyright: ignore[reportMissingImports]


def dump_all_transcripts(
    base_url: str,
    token_cookie: str,
    csrf_token: str,
    out_path: Path = Path("unifi_talk_transcripts_all.json"),
    size: int = 25,
    sort_by: str = "call_time",
    sort_direction: str = "DESC",
    start_page: int = 0,
    sleep_s: float = 0.15,   # tiny pause to be nice to the box
) -> None:
    """
    Fetches every page from /proxy/talk/api/transcript and saves each transcript under the call UUID.

    Stops when a page returns no items.
    """
    # Silence warning from verify=False (curl --insecure)
    requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning) # pyright: ignore[reportAttributeAccessIssue]

    session = requests.Session()
    session.verify = False  # same as curl --insecure
    session.headers.update(
        {
            "accept": "*/*",
            "content-type": "application/json",
            "x-csrf-token": csrf_token,
            "cookie": token_cookie,
            "user-agent": "Mozilla/5.0",
        }
    )

    url = f"{base_url.rstrip('/')}/proxy/talk/api/transcript"

    all_items: list[dict[str, Any]] = []
    raw_pages: list[dict[str, Any]] = []

    page = start_page
    while True:
        params = {
            "page": page,
            "size": size,
            "sortBy": sort_by,
            "sortDirection": sort_direction,
        }

        r = session.get(url, params=params, timeout=30)
        # If your TOKEN/CSRF expires, you'll usually see 401/403 here.
        r.raise_for_status()

        payload = r.json()
        raw_pages.append(payload)

        # UniFi endpoints often return a list in one of these keys.
        # We check common possibilities and fall back gracefully.
        items = None
        for key in ("data", "results", "items", "transcripts"):
            if isinstance(payload.get(key), list):
                items = payload[key]
                break

        # Sometimes the whole payload is the list
        if items is None and isinstance(payload, list):
            items = payload

        if not items:
            # No items => we've reached the end
            break

        all_items.extend(items)
        page += 1

        if sleep_s:
            time.sleep(sleep_s)

    out = {
        "meta": {
            "base_url": base_url,
            "endpoint": "/proxy/talk/api/transcript",
            "start_page": start_page,
            "pages_fetched": page - start_page,
            "page_size": size,
            "sort_by": sort_by,
            "sort_direction": sort_direction,
            "total_items": len(all_items),
        },
        "items": all_items,
        # Keep raw pages too in case you want fields not present in items.
        # If you want a smaller file, delete this line.
        "pages_raw": raw_pages,
    }
    out_path.mkdir(parents=True, exist_ok=True)
    for transcript in out["items"]:
        transcript_path = out_path / f'{transcript["context"]["call_uuid"]}.json'
        transcript_path.write_text(json.dumps(transcript, indent=2), encoding="utf-8")
    
    print(f"Wrote {len(out["items"])} transcripts to {out_path}")
    #out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return


if __name__ == "__main__":
    # Provide secrets via env vars instead of hardcoding.
    COOKIE = os.getenv("UNIFI_TOKEN_COOKIE")
    CSRF = os.getenv("UNIFI_CSRF_TOKEN")
    if not COOKIE or not CSRF:
        raise SystemExit(
            "Missing UNIFI_TOKEN_COOKIE or UNIFI_CSRF_TOKEN environment variables."
        )

    dump_all_transcripts(
        base_url="https://192.168.1.1",
        token_cookie=COOKIE,
        csrf_token=CSRF,
        out_path=Path(__file__).resolve().parent.parent / "data" / "unifi_transcripts",
        size=25,
    )

    
