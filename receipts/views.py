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
    get_receipts_by_status,
    is_receipt_data_available,
)
import os
from django.contrib.auth.decorators import login_required
from django.core.files.uploadedfile import UploadedFile
from datetime import datetime, timedelta
import csv
from io import StringIO
from django.http import HttpResponse
from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth import get_user_model

ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/jpg"]
User = get_user_model()

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

    # Create a mapping of user IDs to user names
    user_map = {}
    for user in User.objects.all():
        name = f"{user.first_name} {user.last_name}".strip()
        user_map[str(user.id)] = name if name else user.username

    # Add user names to receipts
    for receipt in all_receipts:
        receipt["presigned_url"] = generate_presigned_url(receipt["UserID"], receipt["ReceiptID"])
        receipt["UserName"] = user_map.get(receipt["UserID"], receipt["UserID"])  # Add this line
    

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
    print("DEBUG: upload_receipt view is being executed")
    user_id = str(request.user.id)

    if request.method == "POST":
        print("DEBUG: Received POST request")

        if "receipt_image" in request.FILES:
            image: UploadedFile = request.FILES["receipt_image"]
            print("DEBUG: File received")

            # Validate file content type
            if image.content_type not in ALLOWED_IMAGE_TYPES:
                print(f"Rejected upload: invalid content type {image.content_type}")
                return JsonResponse({"error": "Invalid file type."}, status=400)

            print(f"Uploading file {image.name} to S3 for user {user_id}")
            object_key = upload_receipt_to_s3(image, user_id)

            if object_key:
                print(f"Upload successful: {object_key}")
                return redirect("view_receipts")
            else:
                print("Upload failed!")
                return JsonResponse({"error": "Failed to upload file."}, status=500)
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
    
    # Define categories with subcategories flag
    predefined_categories = [
        {"name": "Travel", "has_subcategories": True},
        {"name": "Office Supplies", "has_subcategories": True},
        {"name": "Meals", "has_subcategories": True},
        {"name": "Transportation", "has_subcategories": True},
        {"name": "Software", "has_subcategories": True},
        {"name": "Utilities", "has_subcategories": False},
        {"name": "Advertising", "has_subcategories": False},
        {"name": "Other", "has_subcategories": False}
    ]
    
    # Extract any additional unique categories from receipts
    unique_categories = set(cat["name"] for cat in predefined_categories)
    for receipt in receipts:
        category = receipt.get("Category", "")
        # Extract main category if in format "Category / Subcategory"
        if " / " in category:
            main_category = category.split(" / ")[0]
            if main_category and main_category not in unique_categories:
                unique_categories.add(main_category)
                predefined_categories.append({"name": main_category, "has_subcategories": False})
        elif category and category not in unique_categories:
            unique_categories.add(category)
            predefined_categories.append({"name": category, "has_subcategories": False})

    return render(request, "receipts/upload_receipt.html", {
        "receipts": receipts,
        "selected_status": selected_status,
        "categories": predefined_categories
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
            "Subcategory": receipt_details.get("Subcategory", "N/A"),
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
        if "Subcategory" in request.POST:
            data["Subcategory"] = request.POST.get("Subcategory")

        # call update_receipt_metadata with correct parameters
        success = update_receipt_metadata(user_id, receipt_id, data)  

        if success:
            return JsonResponse({"message": "Receipt updated successfully"}, status=200)
        return JsonResponse({"error": "Failed to update receipt"}, status=500)

    return JsonResponse({"error": "Invalid request"}, status=400)

@login_required
def check_receipt_data(request, receipt_id):
   """Check if receipt data is available in DynamoDB."""
   user_id = str(request.user.id)
  
   # Use the new function to check if data is available
   is_data_available = is_receipt_data_available(user_id, receipt_id)
  
   print(f"DEBUG: Receipt {receipt_id} data available: {is_data_available}")
  
   return JsonResponse({"dataAvailable": is_data_available})


@login_required
def reports_view(request):
    if not request.user.is_manager:
        return redirect('view_receipts')

     # Get all receipts
    all_receipts = get_all_receipts()
    from datetime import date
    
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date") or date.today().strftime("%Y-%m-%d")

    def parse_date(d):
        try:
            return datetime.strptime(d, "%Y-%m-%d")
        except:
            return None

    start_date = parse_date(start_date_str)
    end_date = parse_date(end_date_str)

    # Make end_date inclusive
    if end_date:
        end_date += timedelta(days=1)


    if start_date or end_date:
        def receipt_in_range(receipt):
            receipt_date_str = receipt.get("Date") or receipt.get("ReceiptDate")
            receipt_date = parse_date(receipt_date_str)
            if not receipt_date:
                return False
            if start_date and receipt_date < start_date:
                return False
            if end_date and receipt_date > end_date:
                return False
            return True

        all_receipts = [r for r in all_receipts if receipt_in_range(r)]

    
    # Initialize counters
    total_expense = 0
    approved_expense = 0
    pending_expense = 0
    rejected_expense = 0
    receipt_count = len(all_receipts)
    
    # For debugging - track receipts by status
    status_counts = {"APPROVED": 0, "PENDING": 0, "REJECTED": 0, "UNKNOWN": 0}
    status_amounts = {"APPROVED": 0, "PENDING": 0, "REJECTED": 0, "UNKNOWN": 0}
    
    # For category breakdown and monthly trends
    categories = {}
    monthly_expenses = {}
    users_spending = {}
    vendors = {}

    # Create a mapping of user_id to full name or username
    user_map = {}
    for user in User.objects.all():
        name = f"{user.first_name} {user.last_name}".strip()
        user_map[str(user.id)] = name if name else user.username
    

    for i, receipt in enumerate(all_receipts[:5]):
        print(f"Receipt {i+1}: {receipt.get('ReceiptID')}, Status: '{receipt.get('ApprovalStatus', '')}', Amount: {receipt.get('TotalCost', 0)}")
    
    # Process each receipt
    for receipt in all_receipts:
        status = receipt.get("ApprovalStatus", "").upper() or "PENDING"
        total_cost = receipt.get("TotalCost", "N/A")
        
        # Update status counts
        if status == "APPROVED":
            status_counts["APPROVED"] += 1
        elif status == "REJECTED":
            status_counts["REJECTED"] += 1
        elif status == "PENDING":
            status_counts["PENDING"] += 1
        else:
            status_counts["UNKNOWN"] += 1
        
        # Handle amount calculation
        if total_cost == "N/A":
            # Treat N/A values as zero
            amount = 0
        else:
            # Try to convert to float
            try:
                amount = float(total_cost)
            except (ValueError, TypeError):
                amount = 0
        
        # Update total expenses
        total_expense += amount
        
        # Update status amounts
        if status == "APPROVED":
            approved_expense += amount
            status_amounts["APPROVED"] += amount
        elif status == "REJECTED":
            rejected_expense += amount
            status_amounts["REJECTED"] += amount
        elif status == "PENDING":
            pending_expense += amount
            status_amounts["PENDING"] += amount
        else:
            status_amounts["UNKNOWN"] += amount
            pending_expense += amount  # Group unknown with pending
        
        # Update category breakdown
        category = receipt.get("Category", "Uncategorized")
        if category in categories:
            categories[category] += amount
        else:
            categories[category] = amount
            
        # Update monthly trends
        date_str = receipt.get("Date") or receipt.get("ReceiptDate")
        if date_str:
            try:
                date = datetime.strptime(date_str, "%Y-%m-%d")
                month_key = date.strftime("%Y-%m")
                month_name = date.strftime("%b %Y")
                
                if month_key in monthly_expenses:
                    monthly_expenses[month_key]["amount"] += amount
                else:
                    monthly_expenses[month_key] = {
                        "name": month_name,
                        "amount": amount
                    }
            except ValueError:
                pass
        
        # Update user spending
        user_id = receipt.get("UserID", "Unknown")
        user_name = user_map.get(str(user_id), f"User {user_id}")  # 🔥 Correct name now

        # Use user_name as the key instead of user_id
        if user_name in users_spending:
            users_spending[user_name]["total"] += amount
            users_spending[user_name]["count"] += 1
        else:
            users_spending[user_name] = {
                "user_id": user_id,
                "total": amount,
                "count": 1,
                "approved": 0,
                "pending": 0,
                "rejected": 0
            }

        # Update user spending by status
        if status == "APPROVED":
            users_spending[user_name]["approved"] += amount
        elif status == "REJECTED":
            users_spending[user_name]["rejected"] += amount
        elif status == "PENDING":
            users_spending[user_name]["pending"] += amount

            
        # Update vendors
        vendor = receipt.get("Vendor", "Unknown")
        if vendor in vendors:
            vendors[vendor] += 1
        else:
            vendors[vendor] = 1
    
   
    # Calculate average expense
    approved_count = status_counts["APPROVED"]
    avg_expense = approved_expense / approved_count if approved_count > 0 else 0
    
    # Find most common vendor
    most_common_vendor = max(vendors.items(), key=lambda x: x[1])[0] if vendors else "None"
    
    # Sort monthly expenses by date
    sorted_monthly = sorted(monthly_expenses.items(), key=lambda x: x[0])
    monthly_data = [item[1] for item in sorted_monthly]
    
    # Sort categories by amount
    category_data = [{"name": k, "amount": v} for k, v in categories.items()]
    category_data.sort(key=lambda x: x["amount"], reverse=True)
    
    # Sort users by total spending
    top_spenders = []
    for user_name, data in users_spending.items():
        top_spenders.append({
            "name": user_name,
            "user_id": data["user_id"],
            "total": data["total"],
            "count": data["count"],
            "approved": data["approved"],
            "pending": data["pending"],
            "rejected": data["rejected"]
        })
    
    top_spenders.sort(key=lambda x: x["total"], reverse=True)
    top_spenders = top_spenders[:5]  # Limit to top 5
    
    # Create status data for chart
    status_data = [
        {"name": "Approved", "amount": approved_expense},
        {"name": "Pending", "amount": pending_expense},
        {"name": "Rejected", "amount": rejected_expense}
    ]
    
    # Get recent activity (latest 5 receipts)
    recent_receipts = sorted(
        all_receipts, 
        key=lambda x: x.get("UploadDate", ""), 
        reverse=True
    )[:5]
    
    # Format the recent receipts for display
    formatted_recent = []
    for r in recent_receipts:
        date_str = r.get("Date") or r.get("ReceiptDate", "N/A")
        try:
            date = datetime.strptime(date_str, "%Y-%m-%d")
            formatted_date = date.strftime("%b %d, %Y")
        except (ValueError, TypeError):
            formatted_date = date_str
            
        # Get status with explicit normalization
        raw_status = r.get("ApprovalStatus", "")
        status = raw_status.upper() if raw_status else "PENDING"
            
        user_id = r.get("UserID", "N/A")
        user_name = user_map.get(str(user_id), f"User {user_id}")

        formatted_recent.append({
            "date": formatted_date,
            "user_name": user_name,
            "vendor": r.get("Vendor", "N/A"),
            "amount": r.get("TotalCost", "0.00"),
            "status": status
        })
    
    import json
    
    context = {
        "start_date": start_date_str,
        "end_date": end_date_str,
        "today": date.today().strftime("%Y-%m-%d"),
        "total_expense": round(total_expense, 2),
        "approved_expense": round(approved_expense, 2),
        "pending_expense": round(pending_expense, 2),
        "rejected_expense": round(rejected_expense, 2),
        "avg_expense": round(avg_expense, 2),
        "receipt_count": receipt_count,
        "most_common_vendor": most_common_vendor,
        "category_data": json.dumps(category_data),
        "monthly_data": json.dumps(monthly_data),
        "status_data": json.dumps(status_data),
        "top_spenders": json.dumps(top_spenders),
        "recent_activity": formatted_recent
    }
    
    return render(request, 'receipts/reports.html', context)