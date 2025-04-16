import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .AWS.aws_utils import is_receipt_data_available


class ReceiptConsumer(AsyncWebsocketConsumer):
   async def connect(self):
       self.user = self.scope["user"]
       if not self.user.is_authenticated:
           await self.close()
           return
      
       await self.accept()
       self.polling_task = None
  
   async def disconnect(self, close_code):
       # Cancel polling task if it exists
       if self.polling_task:
           self.polling_task.cancel()
  
   # Receive message from WebSocket
   async def receive(self, text_data):
       data = json.loads(text_data)
      
       if data.get('type') == 'start_polling':
           receipt_id = data.get('receipt_id')
           if receipt_id:
               # Cancel any existing polling task
               if self.polling_task:
                   self.polling_task.cancel()
              
               # Start a new polling task
               self.polling_task = asyncio.create_task(
                   self.poll_for_receipt_data(receipt_id)
               )
  
   async def poll_for_receipt_data(self, receipt_id):
       """Poll for receipt data availability and notify when ready."""
       try:
           # Poll every 3 seconds for up to 5 minutes
           for _ in range(100):  # 100 attempts * 3 seconds = 5 minutes
               print(f"Checking receipt data for {receipt_id}")
               is_available = await self.check_receipt_data(receipt_id)
              
               if is_available:
                   # Send success message to WebSocket
                   await self.send(text_data=json.dumps({
                       'type': 'data_available',
                       'receipt_id': receipt_id
                   }))
                   return
              
               # Wait before next check
               await asyncio.sleep(3)
          
           # If we reach here, data wasn't available after max attempts
           await self.send(text_data=json.dumps({
               'type': 'timeout',
               'receipt_id': receipt_id
           }))
       except asyncio.CancelledError:
           # Task was cancelled
           pass
  
   @database_sync_to_async
   def check_receipt_data(self, receipt_id):
       """Check if receipt data is available in DynamoDB."""
       user_id = str(self.user.id)
       return is_receipt_data_available(user_id, receipt_id)