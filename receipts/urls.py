from django.urls import path
from .views import upload_receipt, delete_receipt_view, view_receipts, get_receipt_details, update_receipt_view, manager_dashboard, approve_reject_receipt, get_approved_expense_total, export_approved_expenses_csv, reports_view
from . import views
urlpatterns = [
    path("upload/", upload_receipt, name="upload_receipt"),
    path("delete/<str:receipt_id>/", delete_receipt_view, name="delete_receipt"),
    path("view/", view_receipts, name="view_receipts"),
    path("details/<str:receipt_id>/", get_receipt_details, name="get_receipt_details"), 
    path("update/<str:receipt_id>/", update_receipt_view, name="update_receipt"),
    path("manager/", manager_dashboard, name="manager_dashboard"),  # ✅ This line is needed
    path("manager/action/<str:receipt_id>/", approve_reject_receipt, name="approve_reject_receipt"),
    path("get_approved_expense_total/", get_approved_expense_total, name="get_approved_expense_total"),
    path("export_csv/", export_approved_expenses_csv, name="export_csv"),
    path('api/check-receipt-data/<str:receipt_id>/', views.check_receipt_data, name='check_receipt_data'),

    path('reports/', reports_view, name='reports'),
]
