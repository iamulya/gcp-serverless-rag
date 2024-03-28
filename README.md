# Serverless RAG
This repo contains example code for a serverless RAG implementation. It doesn't deliver high quality results and should only be used as a guiding tool for your own RAG application.

## Requisites
Before moving forward, create a service account with the following roles:

- BigQuery Admin
- Cloud Datastore Owner
- Cloud Functions Admin
- Cloud Functions Invoker
- Cloud Run Admin
- Cloud Run Invoker
- Document AI Administrator
- Eventarc Event Receiver
- Logging Admin
- Service Account Token Creator
- Storage Admin
- Vertex AI User
- Workflows Admin

This service account can now be used to run all the Cloud Functions and the workflow cited below. It doesn't follow the least permission approach which is usually recommended. 

For least permission approach, create a custom role with the following permissions and assign that to a service account. This however has not been properly tested and can result in permission issues!

bigquery.datasets.create
bigquery.datasets.get
bigquery.jobs.create
bigquery.tables.create
bigquery.tables.get
bigquery.tables.update
bigquery.tables.updateData
datastore.entities.create
datastore.entities.get
datastore.entities.list
datastore.entities.update
cloudfunctions.functions.invoke
eventarc.events.receiveEvent
run.routes.invoke
documentai.processors.create
documentai.processors.get
documentai.processors.list
documentai.processors.processBatch
documentai.processors.update
eventarc.events.receiveEvent
logging.logEntries.create
iam.serviceAccounts.signBlob
storage.objects.create
storage.objects.delete
storage.objects.get
storage.objects.list
aiplatform.endpoints.predict
workflows.executions.create

## Cloud Functions

### Presigned URL
This function creates a presigned URL for a file upload to a Cloud Storage Bucket. The bucket name must be provided as an environment variable. The function expects two parameters in the request body:
1. `object_name` - The name of the file to be uploaded
2. `collection_name` - The name of the folder inside the bucket where the file will be uploaded. This name should be unique to each user, so that each user has its own collection where their documents get uploaded.

When deploying this funciton, please use the 1st gen runtime since there seems to be a bug in the 2nd gen runtime that doesn't see the signBlob permissions correctly.

### Chunker

