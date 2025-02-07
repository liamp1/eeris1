from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from .models import Receipt
from django.conf import settings
from .AWS.aws_utils import (
    upload_receipt_to_s3,
    generate_presigned_url,
    get_user_receipts,
    delete_receipt,
    update_receipt_metadata,  # New function to update DynamoDB metadata
)
import os
from django.contrib.auth.decorators import login_required


# Divided the og function into two, for clarity
@login_required
def upload_receipt(request):
    if request.method == "POST" and request.FILES.get("receipt_image"):
        image = request.FILES["receipt_image"]
        user_id = str(request.user.id)

        # Upload directly to S3, returns an object key of the new image
        object_key = upload_receipt_to_s3(image, user_id)

        return redirect("view_receipts")  # Redirect to a separate view function


@login_required
def view_receipts(request):
    user_id = str(request.user.id)
    receipts = get_user_receipts(user_id)

    for receipt in receipts:
        receipt["image_url"] = generate_presigned_url(user_id, receipt["ReceiptID"])

    return render(request, "receipts/upload_receipt.html", {"receipts": receipts})


# the old function, just in case you need it
@login_required
def upload_receipt_old(request):
    if request.method == "POST" and request.FILES.get("receipt_image"):
        image = request.FILES["receipt_image"]
        user_id = request.user.id  # Get the authenticated user's ID
        file_path = os.path.join(settings.MEDIA_ROOT, image.name)

        # Save the file temporarily
        with open(file_path, "wb") as f:
            for chunk in image.chunks():
                f.write(chunk)

        # Upload to S3
        object_key = upload_receipt_to_s3(file_path, user_id)

        # Remove local temporary file
        os.remove(file_path)

        if object_key:
            # Save to Django DB
            receipt = Receipt(image=object_key, receipt_name=image.name)
            receipt.save()

        return redirect("upload_receipt")

    # Lambda takes a while (from lik 2 to 5s) to process the image, so we have to think of a way to seemlesly wait after upload.

    # Retrieve user receipts from DynamoDB
    user_id = request.user.id
    receipts = get_user_receipts(user_id)

    # Generate pre-signed URLs for each receipt
    for receipt in receipts:
        receipt["image_url"] = generate_presigned_url(user_id, receipt["ReceiptID"])

    return render(request, "receipts/upload_receipt.html", {"receipts": receipts})


def delete_receipt_view(request, receipt_id):
    if request.method == "POST":
        user_id = request.user.id  # Ensure authenticated user
        success = delete_receipt(user_id, receipt_id)

        if success:
            return JsonResponse({"message": "Receipt deleted successfully"}, status=200)
        else:
            return JsonResponse({"error": "Error deleting receipt"}, status=500)

    return JsonResponse({"error": "Invalid request"}, status=400)
