import datetime
import os

import functions_framework
from google.cloud import storage


@functions_framework.http
def generate_signed_url(
    request,
    headers=None,
):
    """
    Generates a v4 signed URL for uploading a blob using HTTP PUT.
    """
    request_json = request.get_json(silent=True)

    object_name = f'{request_json["collection_name"]}/{request_json["object_name"]}'
    bucket_name = os.environ.get("BUCKET_NAME")

    # For more information about CORS and CORS preflight requests, see:
    # https://developer.mozilla.org/en-US/docs/Glossary/Preflight_request

    # Set CORS headers for the preflight request
    if request.method == "OPTIONS":
        # Allows GET requests from any origin with the Content-Type
        # header and caches preflight response for an 3600s
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "PUT",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Max-Age": "3600",
        }

        return ("", 204, headers)

    # Set CORS headers for the main request
    headers = {"Access-Control-Allow-Origin": "*"}

    import google.auth

    credentials, _ = google.auth.default()

    # Perform a refresh request to get the access token of the current credentials (Else, it's None)
    from google.auth.transport import requests

    r = requests.Request()
    credentials.refresh(r)

    service_account_email = credentials.service_account_email

    # Get your IDTokenCredentials
    from google.auth import compute_engine

    signing_credentials = compute_engine.IDTokenCredentials(
        r, "", service_account_email=service_account_email
    )

    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(object_name)

    url = blob.generate_signed_url(
        version="v4",
        # This URL is valid for 15 minutes
        expiration=datetime.timedelta(minutes=15),
        # Allow PUT requests using this URL.
        method="PUT",
        content_type="application/octet-stream",
        credentials=signing_credentials,
    )

    print("Generated PUT signed URL:")
    print(url)
    print("You can use this URL with any user agent, for example:")
    print(
        "curl -X PUT -H 'Content-Type: application/octet-stream' "
        "--upload-file my-file '{}'".format(url)
    )
    return url
