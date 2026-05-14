from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from google.ads.googleads.client import GoogleAdsClient


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
        client_id: str,
        client_secret: str,
        refresh_token: str,
        customer_id: str,
        login_customer_id: str | None = None,
    ) -> None:
        config: dict[str, Any] = {
            "developer_token": developer_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "use_proto_plus": True,
        }
        if login_customer_id:
            config["login_customer_id"] = login_customer_id

        self.customer_id = customer_id.replace("-", "")
        self.client = GoogleAdsClient.load_from_dict(config)

    def fetch_calls_for_date_range(
        self,
        start_date: date,
        end_date: date,
        campaign_ids: list[str] | None = None,
        limit: int = 1000,
    ) -> list[GoogleAdsCallRecord]:
        service = self.client.get_service("GoogleAdsService")

        campaign_filter = ""
        if campaign_ids:
            safe_ids = ", ".join(campaign_ids)
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
    
    
