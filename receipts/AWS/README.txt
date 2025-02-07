



New updates:
- Updated S3 so it accepts Django image object 
- Updated the view functions
- Added the function to update DynamoDB metadata 
- Made actual Unit tests for the aws_util, you can use those just by using 'python -m unittest receipts.AWS.test_aws_utils' 
- Moved aws_utils back to the AWS folder


DynamoDB info:
- A new receipt receives an "Uncategorised" category after upload, so the user should choose the correct one themselves. 

What dictionary to send to update_receipt_metadata:
    data = {
        "Vendor": str(vendor),
        "Total": str(total),
        "ReceiptDate": str(receipt_date),
        "Category": str(category)
    }

Example of what you can receive from get_user_receipts:
[
    {
        "UserID": "123",
        "ReceiptID": "receipt1.png",
        "S3Key": "receipts/123/receipt1.png",
        "Vendor": "Amazon",
        "Total": "49.99",
        "Date": "2025-02-05",
        "UploadDate": "2025-02-05T12:34:56.789Z",
        "Category": "Electronics"
    },
    {
        "UserID": "123",
        "ReceiptID": "receipt2.png",
        "S3Key": "receipts/123/receipt2.png",
        "Vendor": "Walmart",
        "Total": "20.50",
        "Date": "2025-02-03",
        "UploadDate": "2025-02-03T15:20:30.123Z",
        "Category": "Groceries"
    }
]




Proposed workflow for the pop up window after upload:

User uploads a picture, the view function calls upload_receipt_to_s3(image, user_id) 
and gets an object_key in return 
->
We call get_user_receipts(user_id) and look for the object with the new object_key 
(loop until its found, gets rid of wasted wait time)
-> 
When the object is found, display the current metadata in the pop up window 
-> 
When the user closes the window, call update_receipt_metadata(user_id, receipt_id, updated_data: dict)
to save new metadata 






Possible improvements for the future:
- Right now, if there is an error, Im just printing it in the terminal, but we could use 
Django logging instead, no clue how it works, but might be a good idea.











--------------------------------
Stuff from the meeting on Feb 5:
General questions:
- How are you handling user auntefication? Django built in? Are you using UserID as primary key, or some other value?
-- user id 

- How do we want to handle superusers? Store their info in DynamoDB? Or localy? We could save it as JSON in S3 
-- 

- Should a deleted receipt be kept for a certain amount of time?
-- just get rid of it  

- How do you want to receive DynamoDB metadata? Right now its a list of all records, with each record being a list itself.
-- 

- What data do we need from receipts? So far we only have: Vendor, Date and Total
-- add categories 

-  Should we store both upload date, and receipt date?
-- Add upload date

- Should we just merge all git branches into one? 
-- we will use receipts from now on 


Post meeting questions:
- should superusers aprove receipts?
- should an admin see all the receipts or do we need to assign team members 



To Do:
Me:
	1.	Modify upload_receipt_to_s3() to accept Django Image objects.
	2.	Update Lambda function to store upload date in DynamoDB.
	3.	Expand the DynamoDB schema to include categories.
	4.	Write a guide on using DynamoDB metadata.
	5.	Implement update_receipt_metadata() for editing receipt details.
    6.  Make actual unit tests for all the functions. 



- Figure out how to reload only the list of receipts, rather then the whole page after the user uploads a receipt 
- add a pop up window with receipt metadata after the upload 








