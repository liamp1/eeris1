import boto3
from datetime import datetime
from boto3.dynamodb.conditions import Key
import os
from dotenv import load_dotenv
import mimetypes
from typing import Optional
from django.core.files.uploadedfile import UploadedFile

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


def upload_receipt_to_s3(image: UploadedFile, user_id: str) -> Optional[str]:

    object_key: str = f"receipts/{user_id}/{image.name}"
    content_type: str = (
        image.content_type
        or mimetypes.guess_type(image.name)[0]
        or "application/octet-stream"
    )

    try:
        s3.upload_fileobj(
            image, BUCKET_NAME, object_key, ExtraArgs={"ContentType": content_type}
        )

        return object_key  # Return the S3 object key
    except Exception as e:
        print(f"Error uploading to S3: {e}")
        return None


def update_receipt_metadata(user_id: str, receipt_id: str, updated_data: dict) -> bool:
    try:
        update_expression = "SET " + ", ".join(
            f"{key} = :{key}" for key in updated_data
        )
        expression_values = {f":{key}": value for key, value in updated_data.items()}

        table.update_item(
            Key={"UserID": user_id, "ReceiptID": receipt_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values,
        )
        return True  # Returns true if updated succesfully
    except Exception as e:
        print(f"Error updating receipt metadata: {e}")
        return False


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
        # Ensure user_id is a string
        user_id = str(user_id)

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

def get_all_receipts():
    try:
        response = table.scan()
        items = response.get("Items", [])
        print(f"DEBUG: Retrieved {len(items)} receipts from DynamoDB")
        return items
    except Exception as e:
        print(f"Error fetching all receipts: {e}")
        return []

def get_receipts_by_status(status: str):
    try:
        response = table.query(
            IndexName="ApprovalStatusIndex",
            KeyConditionExpression=Key("ApprovalStatus").eq(status.upper())
        )
        print("DEBUG: Querying GSI for status:", status)

        return response.get("Items", [])
    except Exception as e:
        print(f"Error fetching receipts by status: {e}")
        return []

def is_receipt_data_available(user_id: str, receipt_id: str) -> bool:
   """
   Check if a receipt has been processed and its data is available in DynamoDB.
   Returns True only if the receipt exists AND has Textract data.
   """
   try:
       response = table.get_item(
           Key={"UserID": user_id, "ReceiptID": receipt_id}
       )
      
       # Check if the item exists and has Textract data (Vendor or TotalCost)
       if "Item" in response:
           item = response["Item"]
           return "Vendor" in item or "TotalCost" in item
      
       return False
   except Exception as e:
       print(f"Error checking receipt data: {e}")
       return False

