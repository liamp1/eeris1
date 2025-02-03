import boto3
from datetime import datetime
from boto3.dynamodb.conditions import Key
import os
from dotenv import load_dotenv
import mimetypes

# Credentials for AWS
load_dotenv()

# Initialize AWS Clients
s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION"),
)
dynamodb = boto3.resource(
    "dynamodb",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION"),
)

BUCKET_NAME = "eeris-1-s3"
TABLE_NAME = "eeris-1-dynamodb"
table = dynamodb.Table(TABLE_NAME)


def upload_receipt_to_s3(file_path, user_id):
    object_key = f"receipts/{user_id}/{os.path.basename(file_path)}"
    content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"

    try:
        # Open file in binary mode
        with open(file_path, "rb") as file:
            s3.upload_fileobj(
                file, BUCKET_NAME, object_key, ExtraArgs={"ContentType": content_type}
            )

        # print(f"Uploaded {file_path} to {BUCKET_NAME}/{object_key}")
        return object_key

    except Exception as e:
        print(f"Error uploading to S3: {e}")
        return None


# Used to get the URL to a receipt (single one)
def generate_presigned_url(user_id, object_name, expiration=3600):

    try:
        object_key = f"receipts/{user_id}/{object_name}"

        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": BUCKET_NAME, "Key": object_key},
            ExpiresIn=expiration,
        )

        return url

    except Exception as e:
        print(f"Error generating pre-signed URL: {e}")
        return None


# Returns a list of user receipts
def get_user_receipts(user_id):

    try:

        response = table.query(KeyConditionExpression=Key("UserID").eq(user_id))

        receipts = response.get("Items", [])

        return receipts

    except Exception as e:
        print(f"Error getting receipts: {e}")
        return []


def delete_receipt(user_id, object_name):
    s3_deleted = delete_receipt_from_s3(user_id, object_name)
    db_deleted = delete_receipt_from_dynamodb(user_id, object_name)

    return s3_deleted and db_deleted


def delete_receipt_from_s3(user_id, object_name):
    try:
        object_key = f"receipts/{user_id}/{object_name}"

        s3.delete_object(Bucket=BUCKET_NAME, Key=object_key)

        return True

    except Exception as e:
        print(f"Error deleting {object_key} from S3: {e}")
        return False


def delete_receipt_from_dynamodb(user_id, object_name):

    try:
        table.delete_item(Key={"UserID": user_id, "ReceiptID": object_name})
        return True
    except Exception as e:
        print(f"Error deleting {object_name} from DynamoDB: {e}")
        return False
