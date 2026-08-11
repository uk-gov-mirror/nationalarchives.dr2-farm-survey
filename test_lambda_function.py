import json
import os
import unittest
from sys import platform
from unittest.mock import patch, MagicMock

import lambda_function

db_name = "farm_survey_test.db"
image_magick_loc = "/opt/bin/convert" if platform == "linux" else "/usr/local/bin/magick"

required_records_fields = {
    "iaid": "5de561ca-1795-452b-bee6-710e6f1e7f50",
    "citableReference": "MAF 98/123/44/5",
    "parentId": "A7654321",
    "catalogueLevel": 8,
    "referencePart": "0",
    "heldBy": [
        {
            "xReferenceId": "A13530124",
            "xReferenceCode": "66",
            "xReferenceName": "The National Archives, Kew"
        }
    ],
}

sqs_s3_event = {
    "Records": [
        {
            "body": """{
                "Records": [
                  {
                    "s3": {
                      "bucket": {
                        "name": "my-bucket"
                      },
                      "object": {
                        "key": "test/image.json"
                      }
                    }
                  }
                ]
              }"""
        }
    ]
}


class BlobProperties:
    def __init__(self, name, container):
        self.name = name
        self.container = container


def call_args(mock: MagicMock, count=0):
    return mock.call_args_list[count].args


def call_kwarg(mock: MagicMock, param, count=0):
    return mock.call_args_list[count].kwargs[param]


blobs_in_container = [BlobProperties(f"file{n}.tif", "container1") for n in range(1, 5)]


class StorageStreamDownloader:
    def __init__(self, name):
        self.name = name


def name_to_kbs(name):
    return bytes(name, "utf-8") * 200


class TestLambdaFunction(unittest.TestCase):

    @patch.dict(os.environ, {
        "AZURE_ACCOUNT_URL": "test_account_url",
        "AZURE_TENANT_ID": "test_tenant_id",
        "AZURE_CLIENT_ID": "test_client_id",
        "AZURE_FS_CONTAINER": "azure_container1"
    }, clear=True)
    @patch("lambda_function.ClientAssertionCredential")
    @patch("lambda_function.BlobServiceClient")
    def test_get_container_client_should_upload_file_bytes_to_correct_s3_bucket(self, blob_service_client,
                                                                                client_assertion_credential):
        client = MagicMock()
        client.get_container_client.return_value = "container_client_response"
        blob_service_client.return_value = client

        container_client = lambda_function.get_container_client()

        self.assertEqual("container_client_response", container_client)
        self.assertEqual("test_client_id", call_kwarg(client_assertion_credential, "client_id"))
        self.assertEqual("token_callback", call_kwarg(client_assertion_credential, "func").__name__)
        self.assertEqual("test_tenant_id", call_kwarg(client_assertion_credential, "tenant_id"))

        self.assertEqual("test_account_url", call_kwarg(blob_service_client, "account_url"))
        self.assertEqual("ClientAssertionCredential()",
                         call_kwarg(blob_service_client, "credential")._extract_mock_name())

    @patch.dict(os.environ, {"DEST_BUCKET": "bucket1", "DEST_BUCKET_FILES_PREFIX": "files_prefix",
                             "DEST_BUCKET_RECORDS_PREFIX": "records_prefix"}, clear=True)
    @patch("lambda_function.boto3")
    def test_upload_to_s3_should_upload_file_bytes_to_correct_s3_bucket(self, boto3):
        boto3.return_value = MagicMock()
        s3_client = MagicMock()
        boto3.client.return_value = s3_client

        client, upload_to_s3 = lambda_function.s3_setup()
        upload_to_s3(b"bytesToWrite", "file_name")

        self.assertEqual("s3", boto3.client.call_args.args[0])
        self.assertEqual(s3_client, client)
        self.assertEqual(b"bytesToWrite", s3_client.upload_fileobj.call_args.args[0].getvalue())
        self.assertEqual(("bucket1", "file_name"), s3_client.upload_fileobj.call_args.args[1:])

    def test_get_json_metadata_should_get_metadata_from_s3_and_return_it(self):
        s3_client = MagicMock()
        streaming_body = MagicMock()
        reader = MagicMock()
        streaming_body.read.return_value = reader
        reader.decode.return_value = """{"IAID": "123", "images": [{"file_name": "file.tif"}]}"""

        s3_client.get_object.return_value = {
            "Body": streaming_body
        }

        json_metadata = lambda_function.get_json_metadata(s3_client, "bucket1", "key1")

        self.assertEqual({"IAID": "123", "images": [{"file_name": "file.tif"}]}, json_metadata)
        self.assertEqual(1, streaming_body.read.call_count)
        self.assertEqual("utf-8", reader.decode.call_args.args[0])
        self.assertEqual({"Bucket": "bucket1", "Key": "key1"}, s3_client.get_object.call_args.kwargs)

    def test_validate_metadata_should_not_throw_any_exception_if_the_file_names_and_ids_are_unique(self):
        images_metadata = [
            {
                "format": "jpg",
                "name": "66/MAF/32/ed3744e6-9ff7-4bb3-9011-8b45356b6eb7.jpg",
                "originalName": "file1.tif"
            },
            {
                "format": "jpg",
                "name": "66/MAF/32/1a765470-ad91-4790-8706-11f78d30c6e1.jpg",
                "originalName": "file2.tif"
            },
            {
                "format": "jpg",
                "name": "66/MAF/32/6770380c-342b-455d-9f9e-aebd1574a242.jpg",
                "originalName": "file3.tif"
            },
            {
                "format": "jpg",
                "name": "66/MAF/32/d10ae551-2bed-4d5e-83c9-f6a04924de21.jpg",
                "originalName": "file4.tif"
            }
        ]

        lambda_function.validate_metadata(images_metadata)

    def test_validate_metadata_should_throw_an_exception_if_there_are_images_with_same_name_in_json(self):
        images_metadata = [
            {
                "format": "jpg",
                "name": "66/MAF/32/ed3744e6-9ff7-4bb3-9011-8b45356b6eb7.jpg",
                "originalName": "file1.tif"
            },
            {
                "format": "jpg",
                "name": "66/MAF/32/ed3744e6-9ff7-4bb3-9011-8b45356b6eb7.jpg",
                "originalName": "file2.tif"
            },
            {
                "format": "jpg",
                "name": "66/MAF/32/1a765470-ad91-4790-8706-11f78d30c6e1.jpg",
                "originalName": "file3.tif"
            },
            {
                "format": "jpg",
                "name": "66/MAF/32/1a765470-ad91-4790-8706-11f78d30c6e1.jpg",
                "originalName": "file4.tif"
            }
        ]

        with self.assertRaises(Exception) as context:
            lambda_function.validate_metadata(images_metadata)

        self.assertEqual(
            "These image names are duplicated in the replica's 'files' list: 66/MAF/32/ed3744e6-9ff7-4bb3-9011-8b45356b6eb7.jpg, "
            "66/MAF/32/1a765470-ad91-4790-8706-11f78d30c6e1.jpg",
            context.exception.args[0])

    def test_validate_metadata_should_throw_an_exception_if_there_are_images_with_same_originalName_in_json(self):
        images_metadata = [
            {
                "format": "jpg",
                "name": "66/MAF/32/ed3744e6-9ff7-4bb3-9011-8b45356b6eb7.jpg",
                "originalName": "file1.tif"
            },
            {
                "format": "jpg",
                "name": "66/MAF/32/1a765470-ad91-4790-8706-11f78d30c6e1.jpg",
                "originalName": "file1.tif"
            },
            {
                "format": "jpg",
                "name": "66/MAF/32/6770380c-342b-455d-9f9e-aebd1574a242.jpg",
                "originalName": "file2.tif"
            },
            {
                "format": "jpg",
                "name": "66/MAF/32/d10ae551-2bed-4d5e-83c9-f6a04924de21.jpg",
                "originalName": "file2.tif"
            }
        ]

        with self.assertRaises(Exception) as context:
            lambda_function.validate_metadata(images_metadata)

        self.assertEqual("There are images with the same 'originalName':" +
                         "\n1. 66/MAF/32/ed3744e6-9ff7-4bb3-9011-8b45356b6eb7.jpg, 66/MAF/32/1a765470-ad91-4790-8706-11f78d30c6e1.jpg" +
                         "\n2. 66/MAF/32/6770380c-342b-455d-9f9e-aebd1574a242.jpg, 66/MAF/32/d10ae551-2bed-4d5e-83c9-f6a04924de21.jpg",
                         context.exception.args[0])

    def test_get_azure_file_stream_should_get_blob_client_and_download_blob(self):
        container_client = MagicMock()
        blob_client = MagicMock()
        blob_client.download_blob.return_value = {"name": "file1", "container": "test"}
        container_client.get_blob_client.return_value = blob_client
        file_stream = lambda_function.get_azure_file_stream(container_client, "file1")
        self.assertEqual({"name": "file1", "container": "test"}, file_stream)
        self.assertEqual(1, container_client.get_blob_client.call_count)
        self.assertEqual("file1", container_client.get_blob_client.call_args[0][0])
        self.assertEqual(1, blob_client.download_blob.call_count)

    @patch("lambda_function.Popen")
    def test_convert_to_jpg_should_return_jpg_bytes(self, popen):
        process = MagicMock()
        popen.return_value = process
        process.communicate.return_value = (b"jpg_bytes", b"")
        process.returncode = 0
        tiff_stream = MagicMock()
        tiff_stream.read.return_value = b"tiff_stream"
        jpg_reduction = "40%"

        jpg_bytes = lambda_function.convert_to_jpg(jpg_reduction, tiff_stream)
        self.assertEqual(b"jpg_bytes", jpg_bytes)
        self.assertEqual([image_magick_loc, "tiff:-", "-resize", "40%", "jpg:-"], popen.call_args.args[0])
        self.assertEqual({"stdin": -1, "stdout": -1, "stderr": -1}, popen.call_args.kwargs)
        self.assertEqual({"input": b"tiff_stream"}, process.communicate.call_args.kwargs)
        self.assertEqual(1, tiff_stream.read.call_count)

    @patch("lambda_function.Popen")
    def test_convert_to_jpg_should_throw_error_if_return_code_is_not_0(self, popen):
        process = MagicMock()
        popen.return_value = process
        process.communicate.return_value = (b"jpg_bytes", b"Conversion Error")
        process.returncode = 1
        tiff_stream = MagicMock()
        tiff_stream.read.return_value = b"tiff_stream"

        with self.assertRaises(RuntimeError) as context:
            lambda_function.convert_to_jpg("40%", tiff_stream)

        self.assertEqual("Conversion from TIFF to JPG failed: Conversion Error", context.exception.args[0])
        self.assertEqual([image_magick_loc, "tiff:-", "-resize", "40%", "jpg:-"], popen.call_args.args[0])
        self.assertEqual({"stdin": -1, "stdout": -1, "stderr": -1}, popen.call_args.kwargs)
        self.assertEqual({"input": b"tiff_stream"}, process.communicate.call_args.kwargs)
        self.assertEqual(1, tiff_stream.read.call_count)

    @patch.dict(os.environ, {"IMAGE_MAGICK_LOC": "loc"}, clear=True)
    @patch("lambda_function.boto3")
    def test_token_callback_should_call_the_correct_sts_endpoint(self, boto3):
        boto3.return_value = MagicMock()
        sts_client = MagicMock()
        sts_client.get_web_identity_token.return_value = {"WebIdentityToken": "test_token"}
        boto3.client.return_value = sts_client

        web_identity_token = lambda_function.token_callback()

        self.assertEqual("test_token", web_identity_token)
        self.assertEqual("sts", boto3.client.call_args.args[0])

        self.assertEqual({
            "Audience": ["api://AzureADTokenExchange"],
            "DurationSeconds": 300,
            "SigningAlgorithm": "RS256"
        }, sts_client.get_web_identity_token.call_args.kwargs)

    @patch.dict(os.environ, {"DEST_BUCKET_FILES_PREFIX": "files_prefix", "DEST_BUCKET_RECORDS_PREFIX":
        "records_prefix"}, clear=True)
    @patch("lambda_function.token_callback")
    @patch("lambda_function.get_container_client")
    @patch("lambda_function.s3_setup")
    @patch("lambda_function.get_json_metadata")
    @patch("lambda_function.validate_metadata")
    def test_lambda_handler_should_throw_an_error_if_update_scope_provided_does_not_exist(self, validate_metadata,
                                                                                          get_json_metadata, s3_setup,
                                                                                          get_container_client,
                                                                                          token_callback):
        token_callback.return_value = "token_callback"
        get_container_client.return_value = "container_client_response"

        get_json_metadata.return_value = {
            "record": required_records_fields | {"replicaId": "23333d87-99c3-4d46-9972-2c583ccfca72"},
            "replica": {
                "files": [
                    {
                        "format": "jpg",
                        "name": "66/MAF/32/ed3744e6-9ff7-4bb3-9011-8b45356b6eb7.jpg",
                        "originalName": "file1.tif"
                    },
                    {
                        "format": "jpg",
                        "name": "66/MAF/32/1a765470-ad91-4790-8706-11f78d30c6e1.jpg",
                        "originalName": "file2.tif"
                    },
                    {
                        "format": "jpg",
                        "name": "66/MAF/32/8d383366-dca5-4390-b466-746eca5f72c5.jpg",
                        "originalName": "file3.tif"
                    },
                    {
                        "format": "jpg",
                        "name": "66/MAF/32/4ba95a7e-8dda-406a-b5af-77bc4e113a16.jpg",
                        "originalName": "file4.tif"
                    }
                ],
                "replicaId": "23333d87-99c3-4d46-9972-2c583ccfca72"
            },
            "updateScope": "NonExistentUpdateScope"
        }

        s3_client = MagicMock()
        upload_to_s3 = MagicMock()
        s3_setup.return_value = (s3_client, upload_to_s3)

        with self.assertRaises(Exception) as context:
            lambda_function.lambda_handler(sqs_s3_event, None)

        self.assertEqual(
            "updateScope 'NonExistentUpdateScope' is not RecordAndReplica nor RecordOnly",
            context.exception.args[0]
        )

        self.assertEqual(1, s3_setup.call_count)
        self.assertEqual(1, get_container_client.call_count)
        self.assertEqual((s3_client, "my-bucket", "test/image.json"), get_json_metadata.call_args.args)
        self.assertEqual(
            ([
                 {"format": "jpg", "name": "66/MAF/32/ed3744e6-9ff7-4bb3-9011-8b45356b6eb7.jpg",
                  "originalName": "file1.tif"},
                 {"format": "jpg", "name": "66/MAF/32/1a765470-ad91-4790-8706-11f78d30c6e1.jpg",
                  "originalName": "file2.tif"},
                 {"format": "jpg", "name": "66/MAF/32/8d383366-dca5-4390-b466-746eca5f72c5.jpg",
                  "originalName": "file3.tif"},
                 {"format": "jpg", "name": "66/MAF/32/4ba95a7e-8dda-406a-b5af-77bc4e113a16.jpg",
                  "originalName": "file4.tif"}
             ],),
            validate_metadata.call_args_list[0].args
        )

    def lambda_handler_test_good_path(self, series, series_no, expected_reduction, convert_to_jpg,
                                      get_azure_file_stream, validate_metadata, get_json_metadata,
                                      s3_setup, get_container_client, token_callback):
        token_callback.return_value = "token_callback"
        get_container_client.return_value = "container_client_response"

        get_json_metadata.return_value = {
            "record": required_records_fields | {"citableReference": f"{series}/123/44/5", "replicaId":
                "23333d87-99c3-4d46-9972-2c583ccfca72"},
            "replica": {
                "files": [
                    {
                        "format": "jpg",
                        "name": f"66/MAF/{series_no}/ed3744e6-9ff7-4bb3-9011-8b45356b6eb7.jpg",
                        "originalName": "file1.tif"
                    },
                    {
                        "format": "jpg",
                        "name": f"66/MAF/{series_no}/1a765470-ad91-4790-8706-11f78d30c6e1.jpg",
                        "originalName": "file2.tif"
                    },
                    {
                        "format": "jpg",
                        "name": f"66/MAF/{series_no}/8d383366-dca5-4390-b466-746eca5f72c5.jpg",
                        "originalName": "file3.tif"
                    },
                    {
                        "format": "jpg",
                        "name": f"66/MAF/{series_no}/4ba95a7e-8dda-406a-b5af-77bc4e113a16.jpg",
                        "originalName": "file4.tif"
                    }
                ],
                "replicaId": "23333d87-99c3-4d46-9972-2c583ccfca72"
            },
            "updateScope": "RecordAndReplica"
        }

        s3_client = MagicMock()
        upload_to_s3 = MagicMock()
        s3_setup.return_value = (s3_client, upload_to_s3)
        get_azure_file_stream.side_effect = [StorageStreamDownloader(f"{blob.name} bytes") for blob in
                                             blobs_in_container]

        convert_to_jpg.side_effect = [name_to_kbs(blob.name) for blob in blobs_in_container]

        lambda_function.lambda_handler(sqs_s3_event, None)

        self.assertEqual(1, s3_setup.call_count)
        self.assertEqual(1, get_container_client.call_count)
        self.assertEqual((s3_client, "my-bucket", "test/image.json"), get_json_metadata.call_args.args)
        self.assertEqual(
            ([
                 {"format": "jpg", "name": f"66/MAF/{series_no}/ed3744e6-9ff7-4bb3-9011-8b45356b6eb7.jpg",
                  "originalName": "file1.tif"},
                 {"format": "jpg", "name": f"66/MAF/{series_no}/1a765470-ad91-4790-8706-11f78d30c6e1.jpg",
                  "originalName": "file2.tif"},
                 {"format": "jpg", "name": f"66/MAF/{series_no}/8d383366-dca5-4390-b466-746eca5f72c5.jpg",
                  "originalName": "file3.tif"},
                 {"format": "jpg", "name": f"66/MAF/{series_no}/4ba95a7e-8dda-406a-b5af-77bc4e113a16.jpg",
                  "originalName": "file4.tif"}
             ],),
            validate_metadata.call_args_list[0].args
        )
        self.assertEqual(("container_client_response", "folder1/folder1_1/file1.tif"),
                         get_azure_file_stream.call_args_list[0].args)
        self.assertEqual(("container_client_response", "folder1/folder1_1/file2.tif"),
                         get_azure_file_stream.call_args_list[1].args)
        self.assertEqual(("container_client_response", "folder1/folder1_1/file3.tif"),
                         get_azure_file_stream.call_args_list[2].args)
        self.assertEqual(("container_client_response", "folder1/folder1_1/file4.tif"),
                         get_azure_file_stream.call_args_list[3].args)

        for n in range(0, 4):
            jpg_reduction, tiff_stream = call_args(convert_to_jpg, n)
            self.assertEqual(expected_reduction, jpg_reduction)
            self.assertEqual(f"file{n + 1}.tif bytes", tiff_stream.name)

        self.assertEqual(5, upload_to_s3.call_count)
        upload_calls = upload_to_s3.call_args_list
        s3_prefix = "files_prefix/5de561ca-1795-452b-bee6-710e6f1e7f50"
        self.assertEqual((name_to_kbs(blobs_in_container[0].name),
                          f"{s3_prefix}/ed3744e6-9ff7-4bb3-9011-8b45356b6eb7.jpg"), upload_calls[0].args)
        self.assertEqual((name_to_kbs(blobs_in_container[1].name),
                          f"{s3_prefix}/1a765470-ad91-4790-8706-11f78d30c6e1.jpg"), upload_calls[1].args)
        self.assertEqual((name_to_kbs(blobs_in_container[2].name),
                          f"{s3_prefix}/8d383366-dca5-4390-b466-746eca5f72c5.jpg"), upload_calls[2].args)
        self.assertEqual((name_to_kbs(blobs_in_container[3].name),
                          f"{s3_prefix}/4ba95a7e-8dda-406a-b5af-77bc4e113a16.jpg"), upload_calls[3].args)
        expected_metadata = {
            "record": required_records_fields | {"citableReference": f"{series}/123/44/5", "replicaId":
                "23333d87-99c3-4d46-9972-2c583ccfca72"},
            "replica": {
                "files": [
                    {"format": "jpg", "name": f"66/MAF/{series_no}/ed3744e6-9ff7-4bb3-9011-8b45356b6eb7.jpg",
                     "originalName": "file1.tif",
                     "checkSum": "6c319749b5a62079e4bbe7b49f333d79622e33899077b34397df613df5f96198", "size": 2},
                    {"format": "jpg", "name": f"66/MAF/{series_no}/1a765470-ad91-4790-8706-11f78d30c6e1.jpg",
                     "originalName": "file2.tif",
                     "checkSum": "95ca985f19c27633a48f52ec37fefd6c6998584698caa2e105ab761898a5496a", "size": 2},
                    {"format": "jpg", "name": f"66/MAF/{series_no}/8d383366-dca5-4390-b466-746eca5f72c5.jpg",
                     "originalName": "file3.tif",
                     "checkSum": "e3dd291076cc2b1e5860b386aefd60ab36abbc92c9a76ce79bc128ccc1b8561e", "size": 2},
                    {"format": "jpg", "name": f"66/MAF/{series_no}/4ba95a7e-8dda-406a-b5af-77bc4e113a16.jpg",
                     "originalName": "file4.tif",
                     "checkSum": "95f6f71ab879aecaa17545ec4b96bc77adad5a52901ba91fb66c6a0e99c7469f", "size": 2}
                ],
                "replicaId": "23333d87-99c3-4d46-9972-2c583ccfca72",
                "totalSize": 8
            },
            "updateScope": "RecordAndReplica"
        }
        self.assertEqual(
            (json.dumps(expected_metadata).encode("utf-8"),
             "records_prefix/5de561ca-1795-452b-bee6-710e6f1e7f50.json"),
            upload_calls[4].args
        )

    @patch.dict(os.environ, {"DEST_BUCKET_FILES_PREFIX": "files_prefix", "DEST_BUCKET_RECORDS_PREFIX":
        "records_prefix"}, clear=True)
    @patch("lambda_function.db_name", new=db_name)
    @patch("lambda_function.token_callback")
    @patch("lambda_function.get_container_client")
    @patch("lambda_function.s3_setup")
    @patch("lambda_function.get_json_metadata")
    @patch("lambda_function.validate_metadata")
    @patch("lambda_function.get_azure_file_stream")
    @patch("lambda_function.convert_to_jpg")
    def test_lambda_handler_should_reduce_percentage_to_40_if_not_maf73_and_upload_files_and_metadata_to_correct_s3_bucket(
        self, convert_to_jpg, get_azure_file_stream, validate_metadata, get_json_metadata, s3_setup,
        get_container_client, token_callback):
        series_no = 32
        series = f"MAF {series_no}"

        expected_reduction = "40%"
        self.lambda_handler_test_good_path(series, series_no, expected_reduction, convert_to_jpg, get_azure_file_stream,
                                           validate_metadata,
                                           get_json_metadata, s3_setup, get_container_client, token_callback)

    @patch.dict(os.environ, {"DEST_BUCKET_FILES_PREFIX": "files_prefix", "DEST_BUCKET_RECORDS_PREFIX":
        "records_prefix"}, clear=True)
    @patch("lambda_function.db_name", new=db_name)
    @patch("lambda_function.token_callback")
    @patch("lambda_function.get_container_client")
    @patch("lambda_function.s3_setup")
    @patch("lambda_function.get_json_metadata")
    @patch("lambda_function.validate_metadata")
    @patch("lambda_function.get_azure_file_stream")
    @patch("lambda_function.convert_to_jpg")
    def test_lambda_handler_should_reduce_percentage_to_60_if_maf73_and_upload_files_and_metadata_to_correct_s3_bucket(
        self, convert_to_jpg, get_azure_file_stream, validate_metadata, get_json_metadata, s3_setup,
        get_container_client, token_callback):
        series_no = 73
        series = f"MAF {series_no}"

        expected_reduction = "60%"
        self.lambda_handler_test_good_path(series, series_no, expected_reduction, convert_to_jpg, get_azure_file_stream,
                                           validate_metadata,
                                           get_json_metadata, s3_setup, get_container_client, token_callback)

    @patch.dict(os.environ,
                {"DEST_BUCKET_FILES_PREFIX": "files_prefix", "DEST_BUCKET_RECORDS_PREFIX": "records_prefix"},
                clear=True)
    @patch("lambda_function.db_name", new=db_name)
    @patch("lambda_function.token_callback")
    @patch("lambda_function.get_container_client")
    @patch("lambda_function.s3_setup")
    @patch("lambda_function.get_json_metadata")
    @patch("lambda_function.validate_metadata")
    @patch("lambda_function.get_azure_file_stream")
    @patch("lambda_function.convert_to_jpg")
    def test_lambda_handler_should_skip_uploading_file_if_it_is_not_in_azure(self, convert_to_jpg,
                                                                             get_azure_file_stream,
                                                                             validate_metadata, get_json_metadata,
                                                                             s3_setup, get_container_client,
                                                                             token_callback):
        token_callback.return_value = "token_callback"
        get_container_client.return_value = "container_client"
        get_json_metadata.return_value = {
            "record": required_records_fields | {"replicaId": "23333d87-99c3-4d46-9972-2c583ccfca72"},
            "replica": {
                "files": [
                    {
                        "format": "jpg",
                        "name": "66/MAF/32/ed3744e6-9ff7-4bb3-9011-8b45356b6eb7.jpg",
                        "originalName": "file1.tif"
                    },
                    {
                        "format": "jpg",
                        "name": "66/MAF/32/1a765470-ad91-4790-8706-11f78d30c6e1.jpg",
                        "originalName": "file5.tif"
                    }
                ]
            },
            "updateScope": "RecordAndReplica"
        }

        validate_metadata.return_value = None
        s3_client = MagicMock()
        upload_to_s3 = MagicMock()
        s3_setup.return_value = (s3_client, upload_to_s3)
        get_azure_file_stream.side_effect = [StorageStreamDownloader(f"{blob.name} bytes") for blob in
                                             blobs_in_container]

        convert_to_jpg.side_effect = [name_to_kbs(blob.name) for blob in blobs_in_container]

        with self.assertRaises(Exception) as context:
            lambda_function.lambda_handler(sqs_s3_event, None)

        self.assertEqual(
            "1 file(s) in the JSON were not found in Azure for IAID 5de561ca-1795-452b-bee6-710e6f1e7f50. "
            "These are the originalNames: 'file5.tif'",
            context.exception.args[0])

        self.assertEqual(1, s3_setup.call_count)
        self.assertEqual(1, get_container_client.call_count)
        self.assertEqual((s3_client, "my-bucket", "test/image.json"), get_json_metadata.call_args.args)
        self.assertEqual(
            ([{"format": "jpg", "name": "66/MAF/32/ed3744e6-9ff7-4bb3-9011-8b45356b6eb7.jpg",
               "originalName": "file1.tif"},
              {"format": "jpg", "name": "66/MAF/32/1a765470-ad91-4790-8706-11f78d30c6e1.jpg",
               "originalName": "file5.tif"}
              ],),
            validate_metadata.call_args_list[0].args
        )
        self.assertEqual([], get_azure_file_stream.call_args_list)
        self.assertEqual([], convert_to_jpg.call_args_list)

        self.assertEqual(0, upload_to_s3.call_count)

    @patch.dict(os.environ, {"DEST_BUCKET_FILES_PREFIX": "files_prefix", "DEST_BUCKET_RECORDS_PREFIX":
        "records_prefix"}, clear=True)
    @patch("lambda_function.token_callback")
    @patch("lambda_function.get_container_client")
    @patch("lambda_function.s3_setup")
    @patch("lambda_function.get_json_metadata")
    @patch("lambda_function.validate_metadata")
    def test_lambda_handler_should_only_upload_metadata_if_update_scope_is_record_only(self, validate_metadata,
                                                                                       get_json_metadata, s3_setup,
                                                                                       get_container_client,
                                                                                       token_callback):
        token_callback.return_value = "token_callback"
        get_container_client.return_value = "container_client_response"

        get_json_metadata.return_value = {
            "record": required_records_fields | {"replicaId": "23333d87-99c3-4d46-9972-2c583ccfca72"},
            "replica": {
                "files": [
                    {
                        "format": "jpg",
                        "name": "66/MAF/32/ed3744e6-9ff7-4bb3-9011-8b45356b6eb7.jpg",
                        "originalName": "file1.tif",
                        "size": 25
                    },
                    {
                        "format": "jpg",
                        "name": "66/MAF/32/1a765470-ad91-4790-8706-11f78d30c6e1.jpg",
                        "originalName": "file2.tif",
                        "size": 25
                    },
                    {
                        "format": "jpg",
                        "name": "66/MAF/32/8d383366-dca5-4390-b466-746eca5f72c5.jpg",
                        "originalName": "file3.tif",
                        "size": 25
                    },
                    {
                        "format": "jpg",
                        "name": "66/MAF/32/4ba95a7e-8dda-406a-b5af-77bc4e113a16.jpg",
                        "originalName": "file4.tif",
                        "size": 25
                    }
                ],
                "replicaId": "23333d87-99c3-4d46-9972-2c583ccfca72",
                "totalSize": 100
            },
            "updateScope": "RecordOnly"
        }

        s3_client = MagicMock()
        upload_to_s3 = MagicMock()
        s3_setup.return_value = (s3_client, upload_to_s3)

        lambda_function.lambda_handler(sqs_s3_event, None)

        self.assertEqual(1, s3_setup.call_count)
        self.assertEqual(1, get_container_client.call_count)
        self.assertEqual((s3_client, "my-bucket", "test/image.json"), get_json_metadata.call_args.args)
        self.assertEqual(
            ([
                 {"format": "jpg", "name": "66/MAF/32/ed3744e6-9ff7-4bb3-9011-8b45356b6eb7.jpg",
                  "originalName": "file1.tif", "size": 25},
                 {"format": "jpg", "name": "66/MAF/32/1a765470-ad91-4790-8706-11f78d30c6e1.jpg",
                  "originalName": "file2.tif", "size": 25},
                 {"format": "jpg", "name": "66/MAF/32/8d383366-dca5-4390-b466-746eca5f72c5.jpg",
                  "originalName": "file3.tif", "size": 25},
                 {"format": "jpg", "name": "66/MAF/32/4ba95a7e-8dda-406a-b5af-77bc4e113a16.jpg",
                  "originalName": "file4.tif", "size": 25}
             ],),
            validate_metadata.call_args_list[0].args
        )

        self.assertEqual(1, upload_to_s3.call_count)
        upload_calls = upload_to_s3.call_args_list

        expected_metadata = {
            "record": required_records_fields | {"replicaId": "23333d87-99c3-4d46-9972-2c583ccfca72"},
            "replica": {
                "files": [
                    {"format": "jpg", "name": "66/MAF/32/ed3744e6-9ff7-4bb3-9011-8b45356b6eb7.jpg",
                     "originalName": "file1.tif", "size": 25},
                    {"format": "jpg", "name": "66/MAF/32/1a765470-ad91-4790-8706-11f78d30c6e1.jpg",
                     "originalName": "file2.tif", "size": 25},
                    {"format": "jpg", "name": "66/MAF/32/8d383366-dca5-4390-b466-746eca5f72c5.jpg",
                     "originalName": "file3.tif", "size": 25},
                    {"format": "jpg", "name": "66/MAF/32/4ba95a7e-8dda-406a-b5af-77bc4e113a16.jpg",
                     "originalName": "file4.tif", "size": 25}
                ],
                "replicaId": "23333d87-99c3-4d46-9972-2c583ccfca72",
                "totalSize": 100
            },
            "updateScope": "RecordOnly"
        }
        self.assertEqual(
            (json.dumps(expected_metadata).encode("utf-8"),
             "records_prefix/5de561ca-1795-452b-bee6-710e6f1e7f50.json"),
            upload_calls[0].args
        )

    @patch.dict(os.environ, {"DEST_BUCKET_FILES_PREFIX": "files_prefix", "DEST_BUCKET_RECORDS_PREFIX":
        "records_prefix"}, clear=True)
    @patch("lambda_function.token_callback")
    @patch("lambda_function.get_container_client")
    @patch("lambda_function.s3_setup")
    @patch("lambda_function.get_json_metadata")
    @patch("lambda_function.validate_metadata")
    def test_lambda_handler_should_throw_an_error_if_metadata_json_does_not_match_schema(self, validate_metadata,
                                                                                         get_json_metadata, s3_setup,
                                                                                         get_container_client,
                                                                                         token_callback):
        token_callback.return_value = "token_callback"
        get_container_client.return_value = "container_client_response"

        get_json_metadata.return_value = {
            "record": {
                **required_records_fields | {"replicaId": "23333d87-99c3-4d46-9972-2c583ccfca72"},
                "iaid": 1111,
                "replicaId": "23333d87-99c3-4d46-9972-2c583ccfca72"
            },
            "replica": {
                "files": [
                    {
                        "format": "jpg",
                        "name": "66/MAF/32/ed3744e6-9ff7-4bb3-9011-8b45356b6eb7.jpg",
                        "originalName": "file1.tif",
                        "size": 25
                    }
                ],
                "replicaId": "23333d87-99c3-4d46-9972-2c583ccfca72",
                "totalSize": 25
            },
            "updateScope": "RecordOnly"
        }

        s3_client = MagicMock()
        upload_to_s3 = MagicMock()
        s3_setup.return_value = (s3_client, upload_to_s3)

        with self.assertRaises(Exception) as context:
            lambda_function.lambda_handler(sqs_s3_event, None)

        self.assertEqual(
            "\nJSON validation returned an error for file 'test/image.json' at path: record/iaid:\n  - 1111 is " +
            "not of type 'string'",
            context.exception.args[0]
        )


if __name__ == '__main__':
    unittest.main()
