from io import BytesIO
import time
import streamlit as st
import pandas as pd
import requests

from core.processor import (
    find_linkedin_column,
    clean_linkedin_urls
)


# ---------------------------------------------------------
# PAGE CONFIGURATION
# ---------------------------------------------------------

st.set_page_config(
    page_title="LeadPilot",
    page_icon="🎯",
    layout="wide"
)


# ---------------------------------------------------------
# HEADER
# ---------------------------------------------------------

st.title("🎯 LeadPilot")
st.caption("LinkedIn Lead Enrichment Platform")
st.divider()


# ---------------------------------------------------------
# SIDEBAR NAVIGATION
# ---------------------------------------------------------

st.sidebar.title("LeadPilot")
st.sidebar.caption("Contact Intelligence")

page = st.sidebar.radio(
    "Navigation",
    ["Dashboard", "Upload Leads", "Settings"]
)


# ---------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------

if page == "Dashboard":

    st.subheader("Dashboard Overview")

    col1, col2, col3, col4 = st.columns(4)

    total_leads = len(st.session_state.get("leadpilot_data", []))
    enriched_data = st.session_state.get("enriched_data")

    emails_found = 0
    phones_found = 0

    if isinstance(enriched_data, pd.DataFrame):
        if "work_email" in enriched_data.columns:
            emails_found = int(
                enriched_data["work_email"].fillna("").astype(str).str.strip().ne("").sum()
            )

        if "direct_phone" in enriched_data.columns:
            phones_found = int(
                enriched_data["direct_phone"].fillna("").astype(str).str.strip().ne("").sum()
            )

    col1.metric("Loaded Leads", total_leads)
    col2.metric("Emails Found", emails_found)
    col3.metric("Phone Numbers", phones_found)
    col4.metric("Credits Used", "Not tracked yet")

    st.info(
        "Upload your LinkedIn lead file to begin. "
        "Contact enrichment is a separate step and may consume provider credits."
    )


# ---------------------------------------------------------
# UPLOAD LEADS
# ---------------------------------------------------------
    
elif page == "Upload Leads":
    st.subheader("Upload Multiple Leads")

    uploaded_file = st.file_uploader(
        "Upload CSV or Excel file",
        type=["csv", "xlsx"]
    )

    if uploaded_file is not None:
        try:
            if uploaded_file.name.lower().endswith(".xlsx"):
                df = pd.read_excel(uploaded_file)
            else:
                df = pd.read_csv(uploaded_file)

            column = find_linkedin_column(df)

            if column is None:
                st.error("LinkedIn profile URL column not detected.")
                st.write("Available columns:", list(df.columns))

            else:
                cleaned, stats = clean_linkedin_urls(df, column)

                st.success("File successfully processed!")

                c1, c2, c3 = st.columns(3)
                c1.metric("Valid Unique Profiles", stats["valid"])
                c2.metric("Duplicates", stats["duplicates"])
                c3.metric("Invalid Records", stats["invalid"])

                st.subheader("Lead Preview")
                st.dataframe(cleaned, use_container_width=True)

                st.session_state["leadpilot_data"] = cleaned
                st.session_state["linkedin_column"] = column

                st.download_button(
                    "Download Cleaned CSV",
                    data=cleaned.to_csv(
                        index=False
                    ).encode("utf-8-sig"),
                    file_name="leadpilot_cleaned.csv",
                    mime="text/csv"
                )

        except Exception as error:
            st.error(f"File processing error: {error}")

    # Bulk enrichment section
    leads = st.session_state.get("leadpilot_data")

    if isinstance(leads, pd.DataFrame) and not leads.empty:

        st.divider()
        st.subheader("Bulk Email Enrichment")

        st.info(
            "Phone enrichment is disabled. "
            "Only email enrichment will be requested."
        )

        batch_size = st.selectbox(
            "Number of profiles for this test",
            [5, 10, 20, 25, 50],
            index=0
        )

        total_leads = len(leads)

        st.write(f"Total unique profiles available: {total_leads}")
        st.write(f"Profiles selected for this test: {min(batch_size, total_leads)}")

        st.warning(
            "Your Prospeo Free plan has a limit of 50 submitted "
            "enrichment records per day. Start with 5 profiles."
        )

        confirm_bulk = st.checkbox(
            "I authorize Prospeo to process the selected profiles. "
            "A successful email match may consume 1 credit per record."
        )

        if st.button(
            "Start Bulk Email Enrichment",
            disabled=not confirm_bulk
        ):

            try:
                from providers.prospeo import ProspeoProvider

                prospeo = ProspeoProvider()

                # Check current account balance first
                account = prospeo.check_account()

                remaining = account.get(
                    "response", {}
                ).get("remaining_credits")

                if remaining is None:
                    st.error("Could not confirm available Prospeo credits.")
                    st.json(account)

                elif remaining <= 0:
                    st.error("No Prospeo credits remaining.")

                else:
                    selected = leads.head(
                        min(batch_size, total_leads)
                    )

                    linkedin_urls = (
                        selected[column]
                        .astype(str)
                        .tolist()
                    )

                    st.write(
                        f"Submitting {len(linkedin_urls)} profiles."
                    )

                    with st.spinner(
                        "Prospeo is processing your profiles..."
                    ):
                        response = prospeo.enrich_many(
                            linkedin_urls
                        )

                    if response.get("error") is True:
                        st.error("Prospeo bulk request failed.")
                        st.json(response)

                    else:
                        matched = response.get("matched", [])

                        matched_by_id = {
                            str(item.get("identifier")): item
                            for item in matched
                        }

                        output_rows = []

                        for index, url in enumerate(linkedin_urls):
                            item = matched_by_id.get(str(index))

                            if item:
                                formatted = prospeo.format_result(
                                    item,
                                    url
                                )
                                formatted["match_status"] = "MATCHED"

                            else:
                                formatted = {
                                    "linkedin_url": url,
                                    "full_name": None,
                                    "job_title": None,
                                    "company": None,
                                    "company_website": None,
                                    "company_domain": None,
                                    "work_email": None,
                                    "email_status": "UNAVAILABLE",
                                    "direct_phone": None,
                                    "phone_status": "NOT_REQUESTED",
                                    "phone_provider": "Prospeo",
                                    "provider": "Prospeo",
                                    "match_status": (
                                        "INVALID"
                                        if str(index) in [
                                            str(x) for x in
                                            response.get(
                                                "invalid_datapoints", []
                                            )
                                        ]
                                        else "NOT_MATCHED"
                                    )
                                }

                            output_rows.append(formatted)

                        result_df = pd.DataFrame(output_rows)

                        st.session_state["enriched_data"] = result_df

                        st.success(
                            f"Bulk processing completed: "
                            f"{len(matched)} matched out of "
                            f"{len(linkedin_urls)} submitted."
                        )

                        st.write(
                            "Prospeo reported credit cost:",
                            response.get("total_cost", "Not provided")
                        )

                        st.subheader("Bulk Enrichment Results")

                        st.dataframe(
                            result_df,
                            use_container_width=True,
                            hide_index=True
                        )

                        excel_buffer = BytesIO()

                        with pd.ExcelWriter(
                            excel_buffer,
                            engine="openpyxl"
                        ) as writer:

                            result_df.to_excel(
                                writer,
                                index=False,
                                sheet_name="Enriched Leads"
                            )

                            worksheet = writer.sheets[
                                "Enriched Leads"
                            ]

                            worksheet.freeze_panes = "A2"
                            worksheet.auto_filter.ref = (
                                worksheet.dimensions
                            )

                            for cells in worksheet.columns:
                                max_length = max(
                                    len(str(cell.value or ""))
                                    for cell in cells
                                )
                                worksheet.column_dimensions[
                                    cells[0].column_letter
                                ].width = min(max_length + 3, 40)

                        st.download_button(
                            "Download Bulk Results (.xlsx)",
                            data=excel_buffer.getvalue(),
                            file_name="LeadPilot_Bulk_Enriched.xlsx",
                            mime=(
                                "application/vnd.openxmlformats-officedocument."
                                "spreadsheetml.sheet"
                            )
                        )

            
            except requests.HTTPError as error:
                st.error("Prospeo API rate or request limit reached.")

                if error.response is not None:
                    st.write(
                        "HTTP status:",
                        error.response.status_code
                    )

                    try:
                        st.json(error.response.json())
                    except ValueError:
                        st.code(error.response.text[:3000])

                    # Show Prospeo rate-limit information
                    headers = error.response.headers

                    rate_info = {
                        "Daily requests remaining":
                            headers.get("x-daily-request-left"),
                        "Minute requests remaining":
                            headers.get("x-minute-request-left"),
                        "Daily reset seconds":
                            headers.get("x-daily-reset-seconds"),
                        "Minute reset seconds":
                            headers.get("x-minute-reset-seconds")
                    }

                    st.subheader("API Rate Limit Details")
                    st.json(rate_info)

                    st.warning(
                        "Do not retry until the rate limit "
                        "has been checked."
                    )
                else:
                    st.code(str(error))




# ---------------------------------------------------------
# SETTINGS AND APOLLO API
# ---------------------------------------------------------

elif page == "Settings":

    st.subheader("Application Settings")

    st.write("Primary provider: Apollo")
    st.write("Fallback providers: Not enabled")
    st.write("Phone enrichment: Disabled by default")
    st.write("Bulk processing: Not enabled")

    st.divider()

    st.subheader("Apollo API Connection")

    st.info(
        "Test Apollo API authentication without performing contact enrichment."
    )

    if st.button("Test Apollo Connection"):

        try:
            from providers.apollo import ApolloProvider

            with st.spinner("Checking Apollo connection..."):
                apollo = ApolloProvider()
                result = apollo.check_connection()

            st.success("Apollo API authentication successful!")
            st.json(result)

        except Exception as error:
            st.error("Apollo connection failed.")
            st.code(str(error))

    st.divider()

    st.subheader("Test Single Contact Enrichment")

    st.warning(
        "An enrichment request may consume Apollo credits. "
        "Check your account's available credits and API permissions first. "
        "Phone reveal is not requested by this test."
    )

    test_url = st.text_input(
        "LinkedIn Profile URL",
        placeholder="https://www.linkedin.com/in/example/"
    )

    confirm_test = st.checkbox(
        "I understand that this API request may consume credits."
    )

    if st.button(
        "Test Single Enrichment",
        disabled=(not confirm_test or not test_url.strip())
    ):

        try:
            from providers.apollo import ApolloProvider

            with st.spinner("Sending one contact for enrichment..."):
                apollo = ApolloProvider()
                result = apollo.enrich_one(test_url.strip())

            st.success("Apollo returned a response.")
            st.json(result)

        except requests.HTTPError as error:
            if error.response is not None:
                try:
                    error_data = error.response.json()
                except ValueError:
                    error_data = {}

                if error_data.get("error_code") == "NO_MATCH":
                    st.warning(
                        "No matching contact found. "
                        "This is not necessarily an API connection failure."
                    )
                    st.json(error_data)
                else:
                    st.error("Prospeo API request failed.")
                    st.write("HTTP status:", error.response.status_code)
                    st.code(error.response.text[:3000])
            else:
                st.error(str(error))

        except Exception as error:
            st.error("Enrichment error.")
            st.code(str(error))



    st.divider()
    st.subheader("Prospeo API Connection")


    st.divider()
    st.subheader("Test Single Contact with Prospeo")

    st.info(
        "This test requests a verified work email only. "
        "Mobile enrichment is disabled."
    )

    prospeo_url = st.text_input(
        "LinkedIn Profile URL for Prospeo",
        placeholder="https://www.linkedin.com/in/real-profile/"
    )

    confirm_prospeo = st.checkbox(
        "I authorize one Prospeo email enrichment request. "
        "I understand that a verified match may use 1 credit."
    )

   
    if st.button(
        "Test Prospeo Email Enrichment",
        disabled=(not confirm_prospeo or not prospeo_url.strip())
    ):
        try:
            from providers.prospeo import ProspeoProvider
            from io import BytesIO

            with st.spinner("Checking this LinkedIn profile..."):
                prospeo = ProspeoProvider()
                result = prospeo.enrich_one(prospeo_url.strip())

            if result.get("error") is True:
                st.warning("No matching contact found.")
                st.json(result)

            else:
                st.success("Prospeo enrichment request completed!")

                formatted = prospeo.format_result(
                    result,
                    prospeo_url.strip()
                )

                result_df = pd.DataFrame([formatted])

                st.subheader("Enriched Contact Details")

                st.dataframe(
                    result_df,
                    use_container_width=True,
                    hide_index=True
                )

                
                # Create proper Excel workbook
                excel_buffer = BytesIO()

                with pd.ExcelWriter(
                    excel_buffer,
                    engine="openpyxl"
                ) as writer:

                    result_df.to_excel(
                        writer,
                        index=False,
                        sheet_name="Enriched Leads"
                    )

                    worksheet = writer.sheets["Enriched Leads"]

                    # Adjust column widths
                    for column_cells in worksheet.columns:
                        max_length = max(
                            len(str(cell.value or ""))
                            for cell in column_cells
                        )
                        worksheet.column_dimensions[
                            column_cells[0].column_letter
                        ].width = min(max_length + 3, 40)

                    # Add Excel filters
                    worksheet.auto_filter.ref = worksheet.dimensions

                    # Freeze header row
                    worksheet.freeze_panes = "A2"

                st.download_button(
                    label="Download Excel (.xlsx)",
                    data=excel_buffer.getvalue(),
                    file_name="LeadPilot_Enriched_Leads.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )


        except requests.HTTPError as error:
            st.error("Prospeo API request failed.")

            if error.response is not None:
                st.write("HTTP status:", error.response.status_code)
                st.code(error.response.text[:3000])
            else:
                st.code(str(error))

        except Exception as error:
            st.error("Enrichment error.")
            st.code(str(error))



    if st.button("Check Prospeo Account & Credits"):
        try:
            from providers.prospeo import ProspeoProvider

            with st.spinner("Checking Prospeo account..."):
                prospeo = ProspeoProvider()
                result = prospeo.check_account()

            st.success("Prospeo API connection successful!")
            st.json(result)

        except Exception as error:
            st.error("Prospeo connection failed.")
            st.code(str(error))

# ---------------------------------------------------------
# FOOTER
# ---------------------------------------------------------

st.divider()
st.caption("LeadPilot | Version 0.2.0")
