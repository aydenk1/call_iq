import json
import logging
import os
import time
from datetime import datetime, timezone
from multiprocessing import Event, Process
from pathlib import Path
from typing import Any, Optional

import requests
from sqlmodel import select
from requests.packages.urllib3.exceptions import \
    InsecureRequestWarning  # pyright: ignore[reportMissingImports]

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

from api.db import Database
from api.models import CallRecord, PipelineStatus


class UniFiAuthError(RuntimeError):
    pass



class UniFiOSClient:
    """
    UniFi OS session client:
      - POST /api/auth/login to get session cookie(s)
      - automatically retries once on 401/403 by re-login
    """

    def __init__(
            self, 
            base_url: str,
            username: str,
            password: str,
            timeout_s: int = 10
            ) -> None:
        self.base_url: str = base_url
        self.username: str = username
        self.password: str = password
        self.timeout_s: int = timeout_s

        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "unifi-talk-sync/1.0",
        })

        self.csrf_token: str = ""

    def _url(self, path: str) -> str:
        return self.base_url.rstrip("/") + "/" + path.lstrip("/")

    def login(self) -> None:
        """
        Establish UniFi OS session cookies.
        Captures CSRF token if present in response headers/cookies.
        """
        url = self._url("/api/auth/login")
        payload = {"username": self.username, "password": self.password}

        r = self.session.post(
            url,
            json=payload,
            verify=False,
            timeout=self.timeout_s,
        )

        if r.status_code != 200:
            raise UniFiAuthError(
                f"Login failed: HTTP {r.status_code}. "
                f"Check username/password and that this is the UniFi OS base URL."
            )
        self.csrf_token = r.headers.get("x-csrf-token", "")

    def _auth_headers(self) -> dict[str, str]:
        h: dict[str, str] = {}
        if self.csrf_token:
            h["X-Csrf-Token"] = self.csrf_token
        return h

    def request(
        self,
        method: str,
        path: str,
        params: Optional[dict[str, Any]] = None,
        json: Optional[dict[str, Any]] = None,
        data: Any = None,
        headers: Optional[dict[str, str]] = None,
        retry_on_unauthorized: bool = True,
    ) -> requests.Response:
        """
        Make an authenticated request.
        If we get 401/403, re-login once and retry.
        """
        url = self._url(path)

        merged_headers = {}
        merged_headers.update(self._auth_headers())
        if headers:
            merged_headers.update(headers)

        r = self.session.request(
            method.upper(),
            url,
            params=params,
            json=json,
            data=data,
            headers=merged_headers,
            verify=False,
            timeout=self.timeout_s,
        )

        if retry_on_unauthorized and r.status_code in (401, 403):
            # Re-login and retry once
            self.login()
            merged_headers = {}
            merged_headers.update(self._auth_headers())
            if headers:
                merged_headers.update(headers)

            r = self.session.request(
                method.upper(),
                url,
                params=params,
                json=json,
                data=data,
                headers=merged_headers,
                verify=False,
                timeout=self.timeout_s,
            )
        return r



class UnifiCallAPI(Process):
    def __init__(
            self,
            unifi_client: UniFiOSClient,
            page_size: int,
            output_dir: Path
        ):
        super().__init__()
        self.unifi_client: UniFiOSClient = unifi_client
        self.page_size: int = page_size
        self.output_dir: Path = output_dir

        self.call_url = "/proxy/talk/api/call_log"
        self.sleep_same_request_s = .1
        self.sleep_between_request_s = 60
        self._stop_event = Event()
        self._db = None

    def get_data(self, most_recent_call: datetime | None) -> dict[str, dict[str, Any]]:
        """ Pulls all call logs from Unifi router and early exits if 
            incoming data is older than most_recent call
        """
        data = []
        params = {
            "page": 0,
            "items_per_page": self.page_size,
            "sort_key": "time",
            "sort_order": "desc",
        }
        
        while True:
            r = self.unifi_client.request("GET", self.call_url, params=params)
            r.raise_for_status() # If your TOKEN/CSRF expires, you'll usually see 401/403 here.
            payload = r.json()    
            data.extend(payload["records"])
            
            # Return if no records are left or last call seen is older than most_recent_call
            if not len(payload["records"]):
                return self.process_data(data)
            
            if most_recent_call is not None:
                oldest_record = self._parse_call_time(payload["records"][-1]["time"])
                if oldest_record < most_recent_call:
                    return self.process_data(data)
            
            params["page"] += 1
            time.sleep(self.sleep_same_request_s)

    def process_data(self, data: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        call_records = {}
        for call_record in data:
            uuid = call_record.pop("uuid")
            call_records[uuid] = call_record
        return call_records
    
    def stop(self, timeout: float = 60.0, terminate_timeout: float = 10.0) -> None:
        self._stop_event.set()
        if os.getpid() == self.pid or self.pid is None:
            return
        self.join(timeout=timeout)
        if self.is_alive():
            self.terminate()
            self.join(timeout=terminate_timeout)

    def run_file(self) -> dict:
        """ Old run method for storing pulled info in json on disk """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        data = self.get_data(None)

        for uuid in data:
            output_path = self.output_dir / f'{uuid}.json'
            output_path.write_text(json.dumps(data[uuid], indent=2), encoding="utf-8")

        print(f"Wrote {len(data)} transcripts to {self.output_dir}")
        return data
    
    def update_db(self, data: dict[str, Any]) -> None:
        if self._db is None:
            self._db = Database()

        with self._db.session() as session:
            call_records: list[CallRecord] = []

            for call_uuid in data:
                call = session.get(CallRecord, call_uuid)
                created_at = self._parse_call_time(data[call_uuid].pop("time"))
                duration_sec = data[call_uuid].pop("duration")
                if duration_sec is None:
                    logging.warning(
                        "Call %s missing duration; marking FAILED with duration_sec=0",
                        call_uuid,
                    )
                    duration_sec = 0
                    status = PipelineStatus.FAILED
                else:
                    status = PipelineStatus.QUEUED
                if call is None:
                    call = CallRecord(
                        id=call_uuid,
                        created_at=created_at,
                        duration_sec=duration_sec,
                        summary="",
                        status=status,
                        raw_call_log=data[call_uuid]
                    )
                    call_records.append(call)
            
            if call_records:
                session.add_all(call_records)
            session.commit()
        logging.info(f"{self.name} Updated the DB with {len(call_records)} calls.")
        
    @property
    def most_recent_call(self) -> datetime | None:
        if self._db is None:
            self._db = Database()
        with self._db.session() as session:
            statement = select(CallRecord.created_at).order_by(CallRecord.created_at.desc()).limit(1)
            return session.exec(statement).first()

    def run_db(self) -> None:
        while not self._stop_event.is_set():
            most_recent_call = self.most_recent_call
            data = self.get_data(most_recent_call)

            if len(data):
                most_recent_call_id = next(iter(data))
                old_call_time = "None" if most_recent_call is None else most_recent_call.strftime("%b %d, %Y %I:%M %p")
                most_recent_call = self._parse_call_time(data[most_recent_call_id]["time"])
                logging.info(f"{self.name} Most recent call updated from {old_call_time} -> {most_recent_call.strftime('%b %d, %Y %I:%M %p')}")

            self.update_db(data)
            self._stop_event.wait(self.sleep_between_request_s)

    def run(self) -> None:
        self.run_db()

    @staticmethod
    def _parse_call_time(value: Any) -> datetime:
        iso_value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(iso_value)



if __name__ == "__main__":
    # Provide secrets via env vars instead of hardcoding.
    logging.basicConfig(level=logging.INFO)
    UNIFI_USERNAME = os.getenv("UNIFI_USERNAME")
    UNIFI_PASSWORD = os.getenv("UNIFI_PASSWORD")
    if not UNIFI_USERNAME or not UNIFI_PASSWORD:
        raise SystemExit(
            "Missing UNIFI_USERNAME or UNIFI_PASSWORD environment variables."
        )

    client = UniFiOSClient(
        base_url="https://192.168.1.1",
        username=UNIFI_USERNAME,
        password=UNIFI_PASSWORD,
        )
    client.login()

    api = UnifiCallAPI(
        unifi_client=client,
        output_dir=Path(__file__).resolve().parent.parent / "data" / "unifi_call_logs",
        page_size=25,
    )
    Database().create_db_and_tables()
    api.run()

    
