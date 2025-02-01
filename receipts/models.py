from django.db import models

# Create your models here.

class Receipt(models.Model):
    image = models.ImageField(upload_to="receipts/")
    receipt_name = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.image and not self.receipt_name:
            self.receipt_name = self.image.name.split("/")[-1]  # extract filename from path
        super().save(*args, **kwargs)
        
    def image_url(self):
        return self.image.url  # AWS S3 URL