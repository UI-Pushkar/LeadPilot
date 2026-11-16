
import re
import pandas as pd
from urllib.parse import urlsplit, urlunsplit


# 1. Validate LinkedIn profile URLs
def is_linkedin_url(value):

    if pd.isna(value):
        return False

    value = str(value).strip()

    pattern = (
        r"^https?://([a-z]{2,3}\.)?"
        r"linkedin\.com/in/[^/?#]+/?$"
    )

    return bool(
        re.match(pattern, value, re.IGNORECASE)
    )


# 2. Detect LinkedIn URL column
def find_linkedin_column(df):

    for column in df.columns:

        name = str(column).strip().lower()

        if (
            "linkedin" in name
            or "profile_url" in name
            or "profile url" in name
        ):
            return column

    # Handle URL accidentally used as Excel header
    for column in df.columns:

        if is_linkedin_url(column):
            return column

    return None


# 3. Normalize LinkedIn URLs
def normalize_linkedin_url(value):

    parts = urlsplit(str(value).strip())

    path = parts.path.rstrip("/").lower()

    return urlunsplit((
        "https",
        "www.linkedin.com",
        path,
        "",
        ""
    ))


# 4. Clean, validate and remove duplicates
def clean_linkedin_urls(df, column):

    df = df.copy()

    # Recover URL used as Excel column heading
    if is_linkedin_url(column):

        header_url = str(column).strip()

        df = pd.concat(
            [
                pd.DataFrame([{column: header_url}]),
                df
            ],
            ignore_index=True
        )

    # Clean whitespace
    df[column] = (
        df[column]
        .astype("string")
        .str.strip()
    )

    # Validate records
    valid_mask = df[column].apply(is_linkedin_url)

    valid = df[valid_mask].copy()

    invalid_count = int((~valid_mask).sum())

    # Normalize URLs for accurate duplicate detection
    valid["_normalized_url"] = (
        valid[column].apply(normalize_linkedin_url)
    )

    # Count duplicates
    before_deduplication = len(valid)

    valid = valid.drop_duplicates(
        subset=["_normalized_url"],
        keep="first"
    )

    duplicate_count = (
        before_deduplication - len(valid)
    )

    # Remove internal helper column
    valid = valid.drop(
        columns=["_normalized_url"]
    )

    # Statistics
    stats = {
        "valid": len(valid),
        "duplicates": duplicate_count,
        "invalid": invalid_count,
        "total": len(df)
    }

    return valid.reset_index(drop=True), stats
