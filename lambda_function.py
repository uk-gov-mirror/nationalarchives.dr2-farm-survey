import hashlib
import io
import json
import math
import os
import sqlite3
from collections import Counter
from contextlib import closing
from itertools import groupby
from subprocess import Popen, PIPE
from sys import platform

import boto3
from azure.identity import ClientAssertionCredential
from azure.storage.blob import StorageStreamDownloader, ContainerClient, BlobServiceClient
from validate_farm_survey_jsons import validate_json, load_json

type StreamDownloader = StorageStreamDownloader[bytes] | StorageStreamDownloader[str]
name_key = "name"
original_name_key = "originalName"
files_key = "files"
update_scopes = {"RecordAndReplica", "RecordOnly"}
db_name = "farm-survey.db"

if os.environ.get("RUNNING_IN_DOCKER") == "True":
    image_magick_loc = "convert"
else:
    image_magick_loc = "/opt/bin/convert" if platform == "linux" else "/usr/local/bin/magick"

new_file_extension = "jpg"


def token_callback():
    sts_client = boto3.client("sts")
    response = sts_client.get_web_identity_token(
        Audience=["api://AzureADTokenExchange"],
        DurationSeconds=300,
        SigningAlgorithm="RS256",
    )

    return response["WebIdentityToken"]


def get_container_client():
    account_url = os.environ["AZURE_ACCOUNT_URL"]
    tenant_id = os.environ["AZURE_TENANT_ID"]
    client_id = os.environ["AZURE_CLIENT_ID"]
    azure_fs_container = os.environ["AZURE_FS_CONTAINER"]

    credential = ClientAssertionCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        func=token_callback,
    )

    blob_service_client = BlobServiceClient(account_url=account_url, credential=credential)

    return blob_service_client.get_container_client(azure_fs_container)


def s3_setup():
    s3_client = boto3.client("s3")
    dest_bucket = os.environ["DEST_BUCKET"]

    def upload_to_s3(bytes_to_write, file_name):
        body = io.BytesIO(bytes_to_write)
        s3_client.upload_fileobj(body, dest_bucket, file_name)

    return s3_client, upload_to_s3


def get_json_metadata(s3_client, source_bucket, key):
    response = s3_client.get_object(Bucket=source_bucket, Key=key)
    json_metadata = json.loads(response["Body"].read().decode("utf-8"))
    return json_metadata


def validate_metadata(all_image_metadata: list[dict[str, str]]):
    metadata_grouped_by_orig_name = {name: list(metadata) for name, metadata in
                                     groupby(all_image_metadata, lambda m: m[original_name_key])}

    metadata_grouped_by_name = Counter(metadata[name_key] for metadata in all_image_metadata)

    duplicate_names = [name for name, count in metadata_grouped_by_name.items() if count > 1]

    if len(duplicate_names) > 0:
        names = ", ".join(duplicate_names)
        raise Exception(f"These image {name_key}s are duplicated in the replica's 'files' list: {names}")

    names_of_files_with_same_orig_name = [
        ", ".join([image[name_key] for image in images_with_same_orig_name])
        for _, images_with_same_orig_name in metadata_grouped_by_orig_name.items() if
        len(images_with_same_orig_name) > 1
    ]
    if len(names_of_files_with_same_orig_name) > 0:
        names = [f"{n}. {names}" for n, names in enumerate(names_of_files_with_same_orig_name, 1)]
        raise Exception(f"""There are images with the same '{original_name_key}':\n{"\n".join(names)}""")


def get_azure_file_stream(container_client: ContainerClient, blob_path: str) -> StreamDownloader:
    blob_client = container_client.get_blob_client(blob_path)
    return blob_client.download_blob()


def convert_to_jpg(jpg_reduction, tiff_stream: StreamDownloader) -> bytes:
    process: Popen[bytes] = Popen(
        [image_magick_loc, "tiff:-", "-resize", jpg_reduction, f"{new_file_extension}:-"], stdin=PIPE, stdout=PIPE,
        stderr=PIPE
    )
    jpg_bytes, err = process.communicate(input=tiff_stream.read())

    if process.returncode != 0:
        raise RuntimeError(f"Conversion from TIFF to JPG failed: {err.decode()}")
    return jpg_bytes


def lambda_handler(event, context):
    s3_client, upload_to_s3 = s3_setup()
    container_client = get_container_client()

    files_prefix = os.environ["DEST_BUCKET_FILES_PREFIX"]
    metadata_prefix = os.environ["DEST_BUCKET_RECORDS_PREFIX"]

    json_schema_data = load_json("json_schema_for_metadata_jsons.json")

    for event_record in event["Records"]:
        s3_records = json.loads(event_record["body"])["Records"]
        for s3_record in s3_records:
            s3_event_info: dict = s3_record["s3"]
            source_bucket = s3_event_info["bucket"]["name"]
            s3_object = s3_event_info["object"]
            key = s3_object["key"]

            json_metadata = get_json_metadata(s3_client, source_bucket, key)

            record = json_metadata["record"]
            replica = json_metadata["replica"]
            all_image_metadata = replica[files_key]
            iaid = record["iaid"]

            jpg_reduction = "60%" if record["citableReference"].startswith("MAF 73") else "40%"

            validate_metadata(all_image_metadata)
            print(f"Number of images belonging to IAID {iaid} in JSON:", len(all_image_metadata))

            update_scope = json_metadata["updateScope"]
            assert update_scope in update_scopes, (f"updateScope '{update_scope}' is not "
                                                   f"{" nor ".join(sorted(update_scopes))}")
            if update_scope == "RecordAndReplica":
                file_names_not_in_azure = []
                all_image_metadata_by_path = {}
                db_uri = f"file:{db_name}?mode=ro&immutable=1"
                with closing(sqlite3.connect(db_uri, uri=True)) as connection:
                    with connection:
                        for image_metadata in all_image_metadata:
                            original_name = image_metadata[original_name_key]

                            blob_cursor = connection.cursor()
                            blob_cursor.execute(
                                f"SELECT filePath FROM 'farm_survey_paths' WHERE {original_name_key} = ?;",
                                (original_name,)
                            )
                            blob_info = blob_cursor.fetchone()

                            if not blob_info:
                                file_names_not_in_azure.append(original_name)
                            else:
                                blob_path = blob_info[0]
                                all_image_metadata_by_path[blob_path] = image_metadata

                if len(file_names_not_in_azure) > 0:
                    raise Exception(
                        f"{len(file_names_not_in_azure)} file(s) in the JSON were not found in Azure for IAID"
                        f" {iaid}. These are the originalNames: '{", ".join(file_names_not_in_azure)}'"
                    )

                images_metadata = []
                for blob_path, image_metadata in all_image_metadata_by_path.items():
                    name = image_metadata[name_key].split("/")[-1]

                    tiff_blob_stream: StreamDownloader = get_azure_file_stream(container_client, blob_path)
                    jpg_bytes = convert_to_jpg(jpg_reduction, tiff_blob_stream)
                    upload_to_s3(jpg_bytes, f"{files_prefix}/{iaid}/{name}")

                    file_size_kb = math.ceil(len(jpg_bytes) / 1000)

                    images_metadata.append(
                        image_metadata | {"checkSum": hashlib.sha256(jpg_bytes).hexdigest(), "size": file_size_kb}
                    )

                replica[files_key] = images_metadata
                replica["totalSize"] = sum(image_metadata["size"] for image_metadata in images_metadata)

            error_message = validate_json(key, json_metadata, json_schema_data)
            if error_message:
                raise Exception(error_message)
            metadata_bytes = json.dumps(json_metadata).encode("utf-8")
            upload_to_s3(metadata_bytes, f"{metadata_prefix}/{iaid}.json")
