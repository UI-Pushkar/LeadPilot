
import os
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.apollo.io/api/v1"


class ApolloProvider:

    def __init__(self):

        self.api_key = os.getenv("APOLLO_API_KEY", "").strip()

        if not self.api_key:
            raise ValueError("Apollo API key missing in .env")

        self.headers = {
            "X-Api-Key": self.api_key,
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "accept": "application/json"
        }

    def check_connection(self):

        response = requests.get(
            f"{BASE_URL}/auth/health",
            headers=self.headers,
            timeout=20
        )

        response.raise_for_status()
        return response.json()

    def enrich_one(self, linkedin_url):

        if not linkedin_url.startswith("https://www.linkedin.com/in/"):
            raise ValueError("Please provide a valid LinkedIn profile URL")

        endpoint = f"{BASE_URL}/people/match"

        params = {
            "linkedin_url": linkedin_url,
            "reveal_personal_emails": "false",
            "reveal_phone_number": "false"
        }

        response = requests.post(
            endpoint,
            headers=self.headers,
            params=params,
            timeout=30
        )

        response.raise_for_status()

        return response.json()
