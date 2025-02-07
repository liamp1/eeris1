from django.urls import path
from .views import upload_receipt, delete_receipt_view, view_receipts, get_receipt_details, update_receipt_view

urlpatterns = [
    path("upload/", upload_receipt, name="upload_receipt"),
    path("delete/<str:receipt_id>/", delete_receipt_view, name="delete_receipt"),
    path("view/", view_receipts, name="view_receipts"),
    path("details/<str:receipt_id>/", get_receipt_details, name="get_receipt_details"), 
    path("update/<str:receipt_id>/", update_receipt_view, name="update_receipt"),
]
