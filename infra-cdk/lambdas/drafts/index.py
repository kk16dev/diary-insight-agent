# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Drafts API Lambda Handler"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import boto3
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, CORSConfig
from aws_lambda_powertools.logging.correlation_paths import API_GATEWAY_REST
from aws_lambda_powertools.utilities.typing import LambdaContext
from botocore.exceptions import ClientError

# Environment variables
S3_BUCKET_NAME = os.environ["S3_BUCKET_NAME"]
CORS_ALLOWED_ORIGINS = os.environ.get("CORS_ALLOWED_ORIGINS", "*")

# Parse CORS origins - can be comma-separated list
cors_origins = [
    origin.strip() for origin in CORS_ALLOWED_ORIGINS.split(",") if origin.strip()
]
primary_origin = cors_origins[0] if cors_origins else "*"
extra_origins = cors_origins[1:] if len(cors_origins) > 1 else None

# Configure CORS
cors_config = CORSConfig(
    allow_origin=primary_origin,
    extra_origins=extra_origins,
    allow_headers=["Content-Type", "Authorization"],
    allow_credentials=True,
)

# Initialize S3 client
s3_client = boto3.client("s3")

tracer = Tracer()
logger = Logger()
app = APIGatewayRestResolver(cors=cors_config)


def get_draft_dates(date_from: Optional[str] = None, date_to: Optional[str] = None) -> List[str]:
    """
    Get list of draft dates from S3.

    Args:
        date_from: Start date filter (YYYY-MM-DD)
        date_to: End date filter (YYYY-MM-DD)

    Returns:
        List of date strings in YYYY-MM-DD format
    """
    try:
        response = s3_client.list_objects_v2(
            Bucket=S3_BUCKET_NAME,
            Prefix="draft/",
            Delimiter="/"
        )

        if "CommonPrefixes" not in response:
            return []

        dates = []
        for prefix in response["CommonPrefixes"]:
            # Extract date from "draft/YYYY-MM-DD/"
            date_str = prefix["Prefix"].replace("draft/", "").replace("/", "")

            if not date_str:
                continue

            # Apply date filters
            if date_from and date_str < date_from:
                continue
            if date_to and date_str > date_to:
                continue

            dates.append(date_str)

        return sorted(dates, reverse=True)  # Most recent first

    except ClientError as e:
        logger.error(f"S3 error listing drafts: {e}")
        raise


def get_draft_metadata(date: str) -> Optional[Dict[str, Any]]:
    """
    Get metadata for a specific draft.

    Args:
        date: Date string in YYYY-MM-DD format

    Returns:
        Metadata dictionary or None if not found
    """
    try:
        response = s3_client.get_object(
            Bucket=S3_BUCKET_NAME,
            Key=f"draft/{date}/metadata.json"
        )
        content = response["Body"].read().decode("utf-8")
        return json.loads(content)

    except s3_client.exceptions.NoSuchKey:
        return None
    except ClientError as e:
        logger.error(f"S3 error getting metadata for {date}: {e}")
        raise


def get_draft_file(date: str, filename: str) -> Optional[str]:
    """
    Get content of a draft file.

    Args:
        date: Date string in YYYY-MM-DD format
        filename: File name (e.g., "original.md", "references.md")

    Returns:
        File content or None if not found
    """
    try:
        response = s3_client.get_object(
            Bucket=S3_BUCKET_NAME,
            Key=f"draft/{date}/{filename}"
        )
        return response["Body"].read().decode("utf-8")

    except s3_client.exceptions.NoSuchKey:
        return None
    except ClientError as e:
        logger.error(f"S3 error getting {filename} for {date}: {e}")
        raise


@app.get("/drafts")
@tracer.capture_method
def list_drafts() -> Dict[str, Any]:
    """
    Handle GET /drafts endpoint.

    Query Parameters:
        date_from: Start date filter (YYYY-MM-DD)
        date_to: End date filter (YYYY-MM-DD)

    Returns:
        Response with list of drafts
    """
    try:
        # Get query parameters
        date_from = app.current_event.get_query_string_value("date_from")
        date_to = app.current_event.get_query_string_value("date_to")

        # Get draft dates
        dates = get_draft_dates(date_from, date_to)

        # Get metadata for each date
        drafts = []
        for date in dates:
            metadata = get_draft_metadata(date)
            if metadata:
                drafts.append({
                    "date": date,
                    "extracted_at": metadata.get("extracted_at"),
                    "status": metadata.get("extraction_status", "unknown")
                })

        return {"drafts": drafts}

    except ClientError as e:
        logger.error(f"Error listing drafts: {e}")
        return {"error": "Internal server error"}, 500

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {"error": "Internal server error"}, 500


@app.get("/drafts/<date>")
@tracer.capture_method
def get_draft_detail(date: str) -> Dict[str, Any]:
    """
    Handle GET /drafts/{date} endpoint.

    Args:
        date: Date string in YYYY-MM-DD format

    Returns:
        Response with draft details
    """
    try:
        # Validate date format
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return {"error": "Invalid date format. Use YYYY-MM-DD"}, 400

        # Get metadata (required)
        metadata = get_draft_metadata(date)
        if not metadata:
            return {"error": f"Draft not found for date {date}"}, 404

        # Get all draft files
        result = {
            "date": date,
            "metadata": metadata,
            "original": get_draft_file(date, "original.md") or "",
            "references": get_draft_file(date, "references.md") or "",
            "ideas": get_draft_file(date, "ideas.md") or "",
            "goals": get_draft_file(date, "goals.md") or "",
        }

        return result

    except ClientError as e:
        logger.error(f"Error getting draft detail for {date}: {e}")
        return {"error": "Internal server error"}, 500

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {"error": "Internal server error"}, 500


@logger.inject_lambda_context(correlation_id_path=API_GATEWAY_REST)
def handler(event: dict, context: LambdaContext) -> dict:
    """
    Lambda handler for drafts API.

    Args:
        event: API Gateway event
        context: Lambda context

    Returns:
        API Gateway response
    """
    return app.resolve(event, context)