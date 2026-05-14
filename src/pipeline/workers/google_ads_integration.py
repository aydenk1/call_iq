from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import date
import json
from typing import Any

from google.ads.googleads.client import GoogleAdsClient
from google.auth.transport.requests import Request
from google.oauth2 import service_account


GOOGLE_ADS_SCOPE = "https://www.googleapis.com/auth/adwords"


@dataclass(slots=True)
class GoogleAdsCallRecord:
    campaign_id: int
    campaign_name: str
    ad_group_id: int
    ad_group_name: str
    caller_area_code: str | None
    call_duration_seconds: int | None
    call_start_date_time: str | None
    call_status: str | None


class GoogleAdsIntegration:
    """Thin helper around Google Ads API to fetch call data by campaign."""

    def __init__(
        self,
        developer_token: str,
        service_account_json_b64: str,
        customer_id: str,
        login_customer_id: str | None = None,
        campaign_ids: list[str] | None = None,
        api_version: str | None = None,
        use_proto_plus: bool = True,
    ) -> None:
        service_account_info = self._decode_service_account_json(service_account_json_b64)
        credentials = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=[GOOGLE_ADS_SCOPE],
        )
        credentials.refresh(Request())

        self.customer_id = customer_id.replace("-", "")
        self.client = GoogleAdsClient(
            credentials=credentials,
            developer_token=developer_token,
            login_customer_id=login_customer_id,
            version=api_version,
            use_proto_plus=use_proto_plus,
        )
        self.campaign_ids = campaign_ids or []

    @staticmethod
    def _decode_service_account_json(service_account_json_b64: str) -> dict[str, Any]:
        try:
            decoded = base64.b64decode("".join(service_account_json_b64.split()), validate=True)
        except binascii.Error as exc:
            raise ValueError("GOOGLE_ADS_SERVICE_ACCOUNT_JSON_B64 is not valid base64.") from exc

        try:
            service_account_info = json.loads(decoded.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("GOOGLE_ADS_SERVICE_ACCOUNT_JSON_B64 must decode to a JSON object.") from exc

        if not isinstance(service_account_info, dict):
            raise ValueError("GOOGLE_ADS_SERVICE_ACCOUNT_JSON_B64 must decode to a JSON object.")
        return service_account_info

    def fetch_calls_for_date_range(
        self,
        start_date: date,
        end_date: date,
        campaign_ids: list[str] | None = None,
        limit: int = 1000,
    ) -> list[GoogleAdsCallRecord]:
        service = self.client.get_service("GoogleAdsService")

        ids = campaign_ids if campaign_ids is not None else self.campaign_ids
        campaign_filter = ""
        if ids:
            normalized_ids = [str(campaign_id).replace("-", "").strip() for campaign_id in ids]
            invalid_ids = [campaign_id for campaign_id in normalized_ids if not campaign_id.isdigit()]
            if invalid_ids:
                raise ValueError(f"Google Ads campaign IDs must be numeric: {invalid_ids}")
            safe_ids = ", ".join(normalized_ids)
            campaign_filter = f"AND campaign.id IN ({safe_ids})"

        query = f"""
            SELECT
              campaign.id,
              campaign.name,
              ad_group.id,
              ad_group.name,
              call_view.caller_area_code,
              call_view.call_duration_seconds,
              call_view.start_call_date_time,
              call_view.call_status
            FROM call_view
            WHERE segments.date BETWEEN '{start_date.isoformat()}' AND '{end_date.isoformat()}'
              {campaign_filter}
            ORDER BY call_view.start_call_date_time DESC
            LIMIT {int(limit)}
        """

        response = service.search(customer_id=self.customer_id, query=query)

        calls: list[GoogleAdsCallRecord] = []
        for row in response:
            calls.append(
                GoogleAdsCallRecord(
                    campaign_id=row.campaign.id,
                    campaign_name=row.campaign.name,
                    ad_group_id=row.ad_group.id,
                    ad_group_name=row.ad_group.name,
                    caller_area_code=row.call_view.caller_area_code,
                    call_duration_seconds=row.call_view.call_duration_seconds,
                    call_start_date_time=row.call_view.start_call_date_time,
                    call_status=row.call_view.call_status.name if row.call_view.call_status else None,
                )
            )
        return calls
    
    
