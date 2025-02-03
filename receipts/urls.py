from django.urls import path
from .views import upload_receipt, delete_receipt_view

urlpatterns = [
    path("upload/", upload_receipt, name="upload_receipt"),
    path("delete/<str:receipt_id>/", delete_receipt_view, name="delete_receipt"),
]
