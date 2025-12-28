import json
import os
import time
from pathlib import Path
from typing import Any

import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning # pyright: ignore[reportMissingImports]



class UnifiCallAPI:
    def __init__(
            self,
            base_url: str,
            token_cookie: str,
            csrf_token: str,
            page_size: int,
            output_dir: Path
        ):

        self.base_url: str = base_url
        self.token_cookie: str = token_cookie
        self.csrf_token: str = csrf_token
        self.page_size: int = page_size
        self.output_dir: Path = output_dir
        self.url = f"{base_url.rstrip('/')}/proxy/talk/api/call_log"
        self.sleep_s = .5
    
    def get_session(self) -> requests.Session:
        requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)
        session = requests.Session()
        session.verify = False  # same as curl --insecure
        session.headers.update(
            {
                "accept": "*/*",
                "content-type": "application/json",
                "x-csrf-token": self.csrf_token,
                "cookie": self.token_cookie,
                "user-agent": "Mozilla/5.0",
            }
        )
        return session

    def get_data(self) -> dict:
        data = []
        session = self.get_session()
        params = {
            "page": 0,
            "items_per_page": self.page_size,
            "sort_key": "time",
            "sort_order": "desc",
        }
        
        while True:
            r = session.get(self.url, params=params, timeout=30)
            r.raise_for_status() # If your TOKEN/CSRF expires, you'll usually see 401/403 here.
            payload = r.json()

            if not len(payload["records"]):
                return self.process_data(data)
            params["page"] += 1
            data.extend(payload["records"])
            time.sleep(self.sleep_s)

    def process_data(self, data: list) -> dict:
        call_records = {}
        for call_record in data:
            uuid = call_record.pop("uuid")
            call_records[uuid] = call_record
        return call_records

    def run(self) -> dict:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        data = self.get_data()

        for uuid in data:
            output_path = self.output_dir / f'{uuid}.json'
            output_path.write_text(json.dumps(data[uuid], indent=2), encoding="utf-8")

        print(f"Wrote {len(data)} transcripts to {output_path}")
        return data



if __name__ == "__main__":
    # Provide secrets via env vars instead of hardcoding.
    COOKIE = os.getenv("UNIFI_TOKEN_COOKIE")
    CSRF = os.getenv("UNIFI_CSRF_TOKEN")
    if not COOKIE or not CSRF:
        raise SystemExit(
            "Missing UNIFI_TOKEN_COOKIE or UNIFI_CSRF_TOKEN environment variables."
        )
    api = UnifiCallAPI(
        base_url="https://192.168.1.1",
        token_cookie=COOKIE,
        csrf_token=CSRF,
        output_dir=Path(__file__).resolve().parent.parent / "data" / "unifi_call_logs",
        page_size=25,
    )

    api.run()

    
