
import os
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.prospeo.io"


def get_secret(key):
    """Read from Streamlit Cloud Secrets or local environment."""
    try:
        import streamlit as st
        value = st.secrets.get(key, "")
        if value:
            return str(value).strip()
    except Exception:
        pass

    return os.getenv(key, "").strip()


class ProspeoProvider:

    def __init__(self):
        self.api_key = get_secret("PROSPEO_API_KEY")

        if not self.api_key:
            raise ValueError("Prospeo API key missing in Streamlit Secrets or .env")

        self.headers = {
            "X-KEY": self.api_key,
            "Content-Type": "application/json"
        }

    def check_account(self):
        response = requests.get(
            f"{BASE_URL}/account-information",
            headers=self.headers,
            timeout=20
        )
        response.raise_for_status()
        return response.json()

    def enrich_one(self, linkedin_url):
        linkedin_url = linkedin_url.strip()

        if "linkedin.com/in/" not in linkedin_url.lower():
            raise ValueError("Please enter a valid LinkedIn profile URL.")

        payload = {
            "only_verified_email": False,
            "enrich_mobile": False,
            "data": {
                "linkedin_url": linkedin_url
            }
        }

        response = requests.post(
            f"{BASE_URL}/enrich-person",
            headers=self.headers,
            json=payload,
            timeout=30
        )

        response.raise_for_status()
        return response.json()

    def enrich_many(self, linkedin_urls):
        records = []

        for index, url in enumerate(linkedin_urls):
            records.append({
                "identifier": str(index),
                "linkedin_url": str(url).strip()
            })

        if not records:
            return {"error": False, "matched": []}

        if len(records) > 50:
            raise ValueError("Maximum 50 profiles per bulk request.")

        payload = {
            "only_verified_email": False,
            "enrich_mobile": False,
            "data": records
        }

        response = requests.post(
            f"{BASE_URL}/bulk-enrich-person",
            headers=self.headers,
            json=payload,
            timeout=90
        )

        response.raise_for_status()
        return response.json()

    def format_result(self, result, linkedin_url):
        person = result.get("person") or {}
        company = result.get("company") or {}
        email = person.get("email") or {}

        return {
            "linkedin_url": linkedin_url,
            "full_name": person.get("full_name"),
            "job_title": person.get("current_job_title"),
            "company": company.get("name"),
            "company_website": company.get("website"),
            "company_domain": company.get("domain"),
            "work_email": email.get("email"),
            "email_status": email.get("status", "UNAVAILABLE"),
            "direct_phone": None,
            "phone_status": "NOT_REQUESTED",
            "phone_provider": "Prospeo",
            "provider": "Prospeo"
        }
