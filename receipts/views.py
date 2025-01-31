from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from .models import Receipt
import boto3
from django.conf import settings

# Create your views here.

def home(request):
    return render(request, "home.html")

def upload_receipt(request):
    if request.method == 'POST' and request.FILES.get('receipt_image'):
        image = request.FILES['receipt_image']
        receipt_name = image.name  # Get the original filename

        receipt = Receipt(image=image, receipt_name=receipt_name)
        receipt.save()  # Automatically uploads to AWS S3

        return redirect('upload_receipt')  # Prevent duplicate submissions on refresh

    receipts = Receipt.objects.all()
    return render(request, 'receipts/upload_receipt.html', {'receipts': receipts})

def delete_receipt(request, receipt_id):
    if request.method == "POST":
        receipt = get_object_or_404(Receipt, id=receipt_id)

        # Delete from AWS S3
        s3 = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
        )

        try:
            s3.delete_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=receipt.image.name)
        except Exception as e:
            return JsonResponse({"error": f"S3 delete failed: {str(e)}"}, status=500)

        # Delete from database
        receipt.delete()
        return JsonResponse({"message": "Receipt deleted successfully"}, status=200)

    return JsonResponse({"error": "Invalid request"}, status=400)