from django.urls import path
from . import views

urlpatterns = [
    path('upload/', views.upload_receipt, name='upload_receipt'),
    path('delete/<int:receipt_id>/', views.delete_receipt, name='delete_receipt'), 
]