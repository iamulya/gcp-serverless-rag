# [Serverless RAG on GCP](#1-serverless-rag)
- [Serverless RAG on GCP](#serverless-rag-on-gcp)
  - [1.1. Requisites](#11-requisites)
  - [1.2. Cloud Workflows](#12-cloud-workflows)
  - [1.3. Cloud Functions](#13-cloud-functions)
    - [1.3.1. Presigned URL](#131-presigned-url)
    - [1.3.2. Chunker](#132-chunker)
    - [1.3.3. Indexer](#133-indexer)
    - [1.3.4. Query](#134-query)

This repo contains example code for a serverless RAG implementation on Google Cloud. It doesn't deliver high quality results and **should only be used as a guiding tool** for your own serverless RAG application.

## 1.1. Requisites
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

This service account can now be used to run all the Cloud Functions and the workflow cited below. It, however, doesn't follow the least permission approach. 

For least permission approach, create a custom role with the following permissions and assign that to a service account. This however has not been properly tested and can result in permission issues!

- bigquery.datasets.create
- bigquery.datasets.get
- bigquery.jobs.create
- bigquery.tables.create
- bigquery.tables.get
- bigquery.tables.update
- bigquery.tables.updateData
- datastore.entities.create
- datastore.entities.get
- datastore.entities.list
- datastore.entities.update
- cloudfunctions.functions.invoke
- eventarc.events.receiveEvent
- run.routes.invoke
- documentai.processors.create
- documentai.processors.get
- documentai.processors.list
- documentai.processors.processBatch
- documentai.processors.update
- eventarc.events.receiveEvent
- logging.logEntries.create
- iam.serviceAccounts.signBlob
- storage.objects.create
- storage.objects.delete
- storage.objects.get
- storage.objects.list
- aiplatform.endpoints.predict
- workflows.executions.create

## 1.2. Cloud Workflows

[This workflow](workflow/workflow.yaml) is where everything is put together. While creating this workflow, you need to create an EventArc trigger for: 

**Event provider**: Cloud Storage

**Event type**: *google.cloud.storage.object.v1.finalized*

**Bucket**: $BUCKET_NAME

Now, this workflow will get triggered automatically when a file gets uploaded into a designated bucket using the Pre-signed URL Cloud Function. After this, the workflow calls the *Chunker* function, before *Indexer* kicks in. See below for the details of all these functions.

## 1.3. Cloud Functions

### 1.3.1. Presigned URL
This function creates a presigned URL for a file upload to a Cloud Storage Bucket. BUCKET_NAME must be provided as an environment variable to the function to represent the parent bucket where all files will be uploaded - this should be the same as the bucket you chose above for trigger. The function expects two parameters in the request body:
1. `object_name` - The name of the file to be uploaded
2. `collection_name` - The name of the folder inside the bucket where the file will be uploaded. This name should be unique to each user, so that each user has its own collection where their documents get uploaded.

When deploying this funciton, **please use the 1st gen runtime** since there seems to be a bug in the 2nd gen runtime that doesn't see the signBlob permissions correctly.

> [!NOTE]
> You'll need to provide your PROJECT_ID and LOCATION before deploying the following functions

### 1.3.2. Chunker
Parses the uploaded document and split it into chunks. Document AI will be used to parse the document and will be split at the paragraph level. All the document metadata will be saved in Firestore. OUTPUT_BUCKET_NAME must be provided as an environment variable to represent the parent bucket where Document AI will save its response. 

### 1.3.3. Indexer
Reads the data out of Firestore for a specific document, embeds the data in batches and stores the result into BigQuery Vector Store. It also accordingly updates the index status of all the chunks who embeddings have been successfully saved. This status can be polled by a frontend in order to know when a document is completely indexed and the query process can start. 

### 1.3.4. Query
Once the other functions have successfully run, you are ready to run the query. This function uses the “similarity search” retriever to retrieve the data similar to the query. That data is then sent along with the query to Gemini Pro on Vertex AI to generate an answer. 

```bash
curl -m 70 -X POST <Query_Function_URL> \
-H "Authorization: bearer $(gcloud auth print-identity-token)" \
-H "Content-Type: application/json" \
-d '{
  "query": "YOUR_QUERY",
}'
```