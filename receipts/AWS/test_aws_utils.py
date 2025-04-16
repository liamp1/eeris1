# Run using:

# python -m unittest receipts.AWS.test_aws_utils


import io
import unittest
from unittest.mock import patch

from receipts.AWS.aws_utils import (
    BUCKET_NAME,
    upload_receipt_to_s3,
    update_receipt_metadata,
    generate_presigned_url,
    get_user_receipts,
    delete_receipt,
    delete_receipt_from_s3,
    delete_receipt_from_dynamodb,
)


class DummyUploadedFile(io.BytesIO):
    def __init__(self, name, content_type, content=b"test"):
        super().__init__(content)
        self.name = name
        self.content_type = content_type


class TestReceiptsFunctions(unittest.TestCase):
    def setUp(self):
        self.print_patch = patch("builtins.print")
        self.mock_print = self.print_patch.start()

    def tearDown(self):
        self.print_patch.stop()

    @patch("receipts.AWS.aws_utils.s3")
    def test_upload_receipt_to_s3_success(self, mock_s3):
        dummy_file = DummyUploadedFile("test.jpg", "image/jpeg")
        user_id = "user123"
        expected_key = f"receipts/{user_id}/{dummy_file.name}"

        result = upload_receipt_to_s3(dummy_file, user_id)

        mock_s3.upload_fileobj.assert_called_once_with(
            dummy_file,
            BUCKET_NAME,
            expected_key,
            ExtraArgs={"ContentType": dummy_file.content_type},
        )
        self.assertEqual(result, expected_key)

    @patch("receipts.AWS.aws_utils.s3")
    def test_upload_receipt_to_s3_failure(self, mock_s3):
        dummy_file = DummyUploadedFile("test.jpg", "image/jpeg")
        user_id = "user123"
        mock_s3.upload_fileobj.side_effect = Exception("S3 error")

        result = upload_receipt_to_s3(dummy_file, user_id)
        self.assertIsNone(result)

    @patch("receipts.AWS.aws_utils.table")
    def test_update_receipt_metadata_success(self, mock_table):
        user_id = "user123"
        receipt_id = "receipt456"
        updated_data = {"amount": 100, "status": "paid"}
        expected_expr = "SET amount = :amount, status = :status"
        expected_values = {":amount": 100, ":status": "paid"}

        result = update_receipt_metadata(user_id, receipt_id, updated_data)

        mock_table.update_item.assert_called_once_with(
            Key={"UserID": user_id, "ReceiptID": receipt_id},
            UpdateExpression=expected_expr,
            ExpressionAttributeValues=expected_values,
        )
        self.assertTrue(result)

    @patch("receipts.AWS.aws_utils.table")
    def test_update_receipt_metadata_failure(self, mock_table):
        user_id = "user123"
        receipt_id = "receipt456"
        updated_data = {"amount": 100}
        mock_table.update_item.side_effect = Exception("DB error")

        result = update_receipt_metadata(user_id, receipt_id, updated_data)
        self.assertFalse(result)

    @patch("receipts.AWS.aws_utils.s3")
    def test_generate_presigned_url_success(self, mock_s3):
        user_id = "user123"
        object_name = "test.jpg"
        expiration = 600
        fake_url = "https://example.com/test.jpg"
        mock_s3.generate_presigned_url.return_value = fake_url

        result = generate_presigned_url(user_id, object_name, expiration)

        expected_key = f"receipts/{user_id}/{object_name}"
        mock_s3.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": BUCKET_NAME, "Key": expected_key},
            ExpiresIn=expiration,
        )
        self.assertEqual(result, fake_url)

    @patch("receipts.AWS.aws_utils.s3")
    def test_generate_presigned_url_failure(self, mock_s3):
        user_id = "user123"
        object_name = "test.jpg"
        mock_s3.generate_presigned_url.side_effect = Exception("S3 error")

        result = generate_presigned_url(user_id, object_name)
        self.assertIsNone(result)

    @patch("receipts.AWS.aws_utils.table")
    def test_get_user_receipts_success(self, mock_table):
        user_id = "user123"
        receipts_list = [{"ReceiptID": "r1"}, {"ReceiptID": "r2"}]
        mock_table.query.return_value = {"Items": receipts_list}

        result = get_user_receipts(user_id)
        mock_table.query.assert_called_once()
        self.assertEqual(result, receipts_list)

    @patch("receipts.AWS.aws_utils.table")
    def test_get_user_receipts_failure(self, mock_table):
        user_id = "user123"
        mock_table.query.side_effect = Exception("DB error")

        result = get_user_receipts(user_id)
        self.assertEqual(result, [])

    @patch("receipts.AWS.aws_utils.delete_receipt_from_dynamodb")
    @patch("receipts.AWS.aws_utils.delete_receipt_from_s3")
    def test_delete_receipt_success(self, mock_delete_s3, mock_delete_dynamodb):
        user_id = "user123"
        object_name = "test.jpg"
        mock_delete_s3.return_value = True
        mock_delete_dynamodb.return_value = True

        result = delete_receipt(user_id, object_name)
        mock_delete_s3.assert_called_once_with(user_id, object_name)
        mock_delete_dynamodb.assert_called_once_with(user_id, object_name)
        self.assertTrue(result)

    @patch("receipts.AWS.aws_utils.delete_receipt_from_dynamodb")
    @patch("receipts.AWS.aws_utils.delete_receipt_from_s3")
    def test_delete_receipt_failure(self, mock_delete_s3, mock_delete_dynamodb):
        user_id = "user123"
        object_name = "test.jpg"
        mock_delete_s3.return_value = False  # Simulate failure in S3 deletion
        mock_delete_dynamodb.return_value = True

        result = delete_receipt(user_id, object_name)
        self.assertFalse(result)

    @patch("receipts.AWS.aws_utils.s3")
    def test_delete_receipt_from_s3_success(self, mock_s3):
        user_id = "user123"
        object_name = "test.jpg"
        expected_key = f"receipts/{user_id}/{object_name}"

        result = delete_receipt_from_s3(user_id, object_name)
        mock_s3.delete_object.assert_called_once_with(
            Bucket=BUCKET_NAME, Key=expected_key
        )
        self.assertTrue(result)

    @patch("receipts.AWS.aws_utils.s3")
    def test_delete_receipt_from_s3_failure(self, mock_s3):
        user_id = "user123"
        object_name = "test.jpg"
        mock_s3.delete_object.side_effect = Exception("S3 error")

        result = delete_receipt_from_s3(user_id, object_name)
        self.assertFalse(result)

    @patch("receipts.AWS.aws_utils.table")
    def test_delete_receipt_from_dynamodb_success(self, mock_table):
        user_id = "user123"
        object_name = "test.jpg"

        result = delete_receipt_from_dynamodb(user_id, object_name)
        mock_table.delete_item.assert_called_once_with(
            Key={"UserID": user_id, "ReceiptID": object_name}
        )
        self.assertTrue(result)

    @patch("receipts.AWS.aws_utils.table")
    def test_delete_receipt_from_dynamodb_failure(self, mock_table):
        user_id = "user123"
        object_name = "test.jpg"
        mock_table.delete_item.side_effect = Exception("DB error")

        result = delete_receipt_from_dynamodb(user_id, object_name)
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
