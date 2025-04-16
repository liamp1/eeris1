from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from .models import Receipt
from django.db.models import Sum
from django.conf import settings
from .AWS.aws_utils import (
    upload_receipt_to_s3,
    generate_presigned_url,
    get_user_receipts,
    delete_receipt,
    update_receipt_metadata,  # New function to update DynamoDB metadata
    get_all_receipts,
    get_receipts_by_status
)
import os
from django.contrib.auth.decorators import login_required
from django.core.files.uploadedfile import UploadedFile
from datetime import datetime
import csv
from io import StringIO
from django.http import HttpResponse
from django.shortcuts import redirect



@login_required
def manager_dashboard(request):
    if not request.user.is_manager:
        return redirect("view_receipts")

    selected_status = request.GET.get("status", "ALL").upper()

    if selected_status == "ALL":
        all_receipts = get_all_receipts()
    else:
        all_receipts = get_receipts_by_status(selected_status)


    # Filter if a specific status is selected
    if selected_status != "ALL":
        all_receipts = [
            r for r in all_receipts
            if r.get("ApprovalStatus", "PENDING").upper() == selected_status
        ]
    print("DEBUG: Selected status is", selected_status)


    # Sort to always show PENDING first, then APPROVED, then REJECTED
    def sort_key(receipt):
        status = receipt.get("ApprovalStatus", "PENDING").upper()
        order = {"PENDING": 0, "APPROVED": 1, "REJECTED": 2}
        return order.get(status, 3)

    all_receipts.sort(key=sort_key)

    for r in all_receipts:
        r["presigned_url"] = generate_presigned_url(r["UserID"], r["ReceiptID"])

    return render(request, "manager_dashboard.html", {
        "receipts": all_receipts,
        "selected_status": selected_status
    })






@login_required
def approve_reject_receipt(request, receipt_id):
    if not request.user.is_manager:
        return redirect("view_receipts")

    if request.method == "POST":
        action = request.POST.get("action")
        comment = request.POST.get("comment", "")
        user_id = request.POST.get("user_id")

        status = "APPROVED" if action == "approve" else "REJECTED"

        data = {"ApprovalStatus": status}
        if comment:
            data["ManagerComment"] = comment

        success = update_receipt_metadata(user_id, receipt_id, data)

        if success:
            return redirect("manager_dashboard")

    return redirect("manager_dashboard")


def filter_approved_receipts(receipts, category=None, start_date_str=None, end_date_str=None):
    def parse_date(d):
        try:
            return datetime.strptime(d, "%Y-%m-%d")
        except:
            return None

    start_date = parse_date(start_date_str) if start_date_str else None
    end_date = parse_date(end_date_str) if end_date_str else None

    approved_receipts = [r for r in receipts if r.get("ApprovalStatus", "").upper() == "APPROVED"]

    def receipt_in_date_range(receipt):
        receipt_date_str = receipt.get("Date") or receipt.get("ReceiptDate")
        receipt_date = parse_date(receipt_date_str)
        if not receipt_date:
            return False
        if start_date and receipt_date < start_date:
            return False
        if end_date and receipt_date > end_date:
            return False
        return True

    if start_date or end_date:
        approved_receipts = [r for r in approved_receipts if receipt_in_date_range(r)]

    if category:
        approved_receipts = [r for r in approved_receipts if r.get("Category", "").lower() == category.lower()]

    return approved_receipts



@login_required
def get_approved_expense_total(request):
    if not request.user.is_manager:
        return redirect("view_receipts")

    user_id = request.GET.get("user_id") or str(request.user.id)
    category = request.GET.get("category")
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")

    receipts = get_user_receipts(user_id)
    approved_receipts = filter_approved_receipts(receipts, category, start_date_str, end_date_str)

    total = 0.0
    for receipt in approved_receipts:
        try:
            total += float(receipt.get("TotalCost", 0))
        except (ValueError, TypeError) as e:
            print(f"Error parsing TotalCost: {e}")

    return JsonResponse({
        "total": round(total, 2),
        "approved_receipts": approved_receipts
    })



@login_required
def export_approved_expenses_csv(request):
    if not request.user.is_manager:
        return redirect("view_receipts")

    # Extract dates from query parameters
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")

    # Get only approved receipts from DynamoDB
    approved_receipts = get_receipts_by_status("APPROVED")

    # Filter based on provided date range (category & user_id removed)
    approved_receipts = filter_approved_receipts(
        approved_receipts, category=None, start_date_str=start_date_str, end_date_str=end_date_str
    )

    print(f"[DEBUG] Retrieved {len(approved_receipts)} approved receipts after date filtering")

    # Prepare CSV response
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="approved_expenses.csv"'

    writer = csv.writer(response)
    writer.writerow(["ReceiptID", "Date", "Category", "TotalCost", "ApprovalStatus"])

    total_cost = 0.0
    for receipt in approved_receipts:
        try:
            cost = float(receipt.get("TotalCost", 0))
            total_cost += cost
        except (ValueError, TypeError) as e:
            print(f"[DEBUG] Error parsing TotalCost: {e}")

        writer.writerow([
            receipt.get("ReceiptID", ""),
            receipt.get("Date") or receipt.get("ReceiptDate", ""),
            receipt.get("Category", ""),
            receipt.get("TotalCost", ""),
            receipt.get("ApprovalStatus", "")
        ])

    # Write total row at the bottom
    writer.writerow([])
    writer.writerow(["", "", "", "Total Cost:", f"{round(total_cost, 2)}"])

    return response








# Divided the og function into two, for clarity
@login_required
def upload_receipt(request):

    print("DEBUG: upload_receipt view is being executed") # check if view runs
    user_id = str(request.user.id)

    if request.method == "POST":
        print("DEBUG: Received POST request")  # check if request is POST

        if "receipt_image" in request.FILES:
            print("DEBUG: File received")
            
            image: UploadedFile = request.FILES["receipt_image"]    # ensure image is passed as an UploadedFile object
    

            print(f"Uploading file {image.name} to S3 for user {user_id}")
            # Upload directly to S3, returns an object key of the new image
            object_key = upload_receipt_to_s3(image, user_id)

            if object_key:
                print(f"Upload successful: {object_key}")  # debugging success case
                return redirect("view_receipts")
            else:
                print("Upload failed!")  # debugging failure case
        else:
            print("DEBUG: no file found in request")
    
    return redirect("view_receipts")


@login_required
def view_receipts(request):
    user_id = str(request.user.id)
    selected_status = request.GET.get("status", "ALL")

    receipts = get_user_receipts(user_id)

    # Optional sorting by status order
    status_order = {"PENDING": 0, "APPROVED": 1, "REJECTED": 2}
    receipts.sort(key=lambda r: status_order.get(r.get("ApprovalStatus", "PENDING"), 3))

    # Apply filtering
    if selected_status != "ALL":
        receipts = [r for r in receipts if r.get("ApprovalStatus") == selected_status]

    for receipt in receipts:
        receipt["image_url"] = generate_presigned_url(user_id, receipt["ReceiptID"])

    # Extract unique categories from all receipts
    categories = []
    unique_categories = set()
    for receipt in receipts:
        category = receipt.get("Category")
        if category and category not in unique_categories:
            unique_categories.add(category)
            categories.append({"name": category})

    return render(request, "receipts/upload_receipt.html", {
        "receipts": receipts,
        "selected_status": selected_status,
        "categories": categories
    })



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


@login_required
def delete_receipt_view(request, receipt_id):
    if request.method == "POST":
        user_id = request.POST.get("user_id") or str(request.user.id)

        # Managers can delete any receipt
        if not request.user.is_manager and str(request.user.id) != user_id:
            return JsonResponse({"error": "Unauthorized"}, status=403)

        success = delete_receipt(user_id, receipt_id)

        if success:
            return redirect("manager_dashboard" if request.user.is_manager else "view_receipts")
        else:
            return JsonResponse({"error": "Failed to delete receipt"}, status=500)

    return JsonResponse({"error": "Invalid request"}, status=400)



def format_upload_date(iso_date):
    return datetime.fromisoformat(iso_date.replace("Z", "+00:00")).strftime("%B %d, %Y %I:%M %p")


@login_required
def get_receipt_details(request, receipt_id):
    receipts = get_all_receipts()  # Pulls all receipts (since manager needs full access)
    receipt_details = next((r for r in receipts if r["ReceiptID"] == receipt_id), None)

    if receipt_details:
        response_data = {
            "UserID": receipt_details["UserID"],
            "ReceiptID": receipt_details["ReceiptID"],
            "Vendor": receipt_details.get("Vendor", "N/A"),
            "TotalCost": receipt_details.get("TotalCost", "N/A"),
            "Date": receipt_details.get("Date", receipt_details.get("ReceiptDate", "N/A")),

            "UploadDate": format_upload_date(receipt_details.get("UploadDate", "N/A")),
            "Category": receipt_details.get("Category", "N/A"),
        }
        return JsonResponse(response_data, status=200)

    return JsonResponse({"error": "Receipt not found"}, status=404)


@login_required
def update_receipt_view(request, receipt_id):
    """Updates receipt metadata in DynamoDB correctly."""
    if request.method == "POST":
        user_id = str(request.user.id)

        # only send existing fields to prevent overwriting or creating new attributes
        data = {}
        if "Vendor" in request.POST:
            data["Vendor"] = request.POST.get("Vendor")
        if "TotalCost" in request.POST: 
            data["TotalCost"] = request.POST.get("TotalCost")
        if "Date" in request.POST:
            data["ReceiptDate"] = request.POST.get("Date")
        if "Category" in request.POST:
            data["Category"] = request.POST.get("Category")

        # call update_receipt_metadata with correct parameters
        success = update_receipt_metadata(user_id, receipt_id, data)  

        if success:
            return JsonResponse({"message": "Receipt updated successfully"}, status=200)
        return JsonResponse({"error": "Failed to update receipt"}, status=500)

    return JsonResponse({"error": "Invalid request"}, status=400)
