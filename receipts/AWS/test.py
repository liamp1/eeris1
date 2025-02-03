import aws_utils
import time

object_name = "receipt2.png"
user_id = "whatever69"


# Test 1: Upload receipt to S3
uploaded_key = aws_utils.upload_receipt_to_s3(object_name, user_id)
if uploaded_key:
    print("Test 1 passed.")
else:
    print("Test 1 failed.")


# Test 2: Get presigned URL
presigned_url = aws_utils.generate_presigned_url(user_id, object_name)
if presigned_url:
    print(f"Test 2 passed.")
else:
    print("Test 2 failed.")

time.sleep(5)  # It takes a while

# Test 3: Get all receipts for a user
user_receipts = aws_utils.get_user_receipts(user_id)
if user_receipts:
    print("Test 3 passed.")
else:
    print("Test 3 failed.")

# Test 4: Delete receipts from S3 and DynamoDB
deleted_object = aws_utils.delete_receipt(user_id, object_name)
if deleted_object:
    print("Test 4 passed.")
else:
    print("Test 4 failed.")
