import os
import re
from typing import Optional, Sequence

import functions_framework
from google.api_core.client_options import ClientOptions
from google.api_core.exceptions import (FailedPrecondition,
                                        InternalServerError, RetryError)
from google.cloud import documentai, firestore, storage  # type: ignore

PROJECT_ID = "YOUR_PROJECT"
LOCATION = "YOUR_LOCATION"
PROCESSOR_DISPLAY_NAME = "document_ai_ocr_processor"
PROCESSOR_TYPE = "OCR_PROCESSOR"

db = firestore.Client()

def batch_process_documents(
    project_id: str,
    location: str,
    processor_id: str,
    gcs_output_uri: str,
    processor_version_id: Optional[str] = None,
    gcs_input_uri: Optional[str] = None,
    input_mime_type: str = "application/pdf",
    gcs_input_prefix: Optional[str] = None,
    field_mask: Optional[str] = None,
    timeout: int = 400,
) -> None:
    """
    Batch processes the documents from Cloud Storage using a Document AI Processor.
    """
    # You must set the `api_endpoint` if you use a location other than "us".
    opts = ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")

    client = documentai.DocumentProcessorServiceClient(client_options=opts)

    if gcs_input_uri:
        # Specify specific GCS URIs to process individual documents
        gcs_document = documentai.GcsDocument(
            gcs_uri=gcs_input_uri, mime_type=input_mime_type
        )
        # Load GCS Input URI into a List of document files
        gcs_documents = documentai.GcsDocuments(documents=[gcs_document])
        input_config = documentai.BatchDocumentsInputConfig(gcs_documents=gcs_documents)
    else:
        # Specify a GCS URI Prefix to process an entire directory
        gcs_prefix = documentai.GcsPrefix(gcs_uri_prefix=gcs_input_prefix)
        input_config = documentai.BatchDocumentsInputConfig(gcs_prefix=gcs_prefix)

    # Cloud Storage URI for the Output Directory
    gcs_output_config = documentai.DocumentOutputConfig.GcsOutputConfig(
        gcs_uri=gcs_output_uri
    )

    # Where to write results
    output_config = documentai.DocumentOutputConfig(gcs_output_config=gcs_output_config)

    if processor_version_id:
        # The full resource name of the processor version, e.g.:
        # projects/{project_id}/locations/{location}/processors/{processor_id}/processorVersions/{processor_version_id}
        name = client.processor_version_path(
            project_id, location, processor_id, processor_version_id
        )
    else:
        # The full resource name of the processor, e.g.:
        # projects/{project_id}/locations/{location}/processors/{processor_id}
        name = client.processor_path(project_id, location, processor_id)

    request = documentai.BatchProcessRequest(
        name=name,
        input_documents=input_config,
        document_output_config=output_config,
    )

    # BatchProcess returns a Long Running Operation (LRO)
    operation = client.batch_process_documents(request)

    # Continually polls the operation until it is complete.
    # This could take some time for larger files
    # Format: projects/{project_id}/locations/{location}/operations/{operation_id}
    try:
        print(f"Waiting for operation {operation.operation.name} to complete...")
        operation.result(timeout=timeout)
    # Catch exception when operation doesn't finish before timeout
    except (RetryError, InternalServerError) as e:
        print(e.message)

    # NOTE: Can also use callbacks for asynchronous processing
    #
    # def my_callback(future):
    #   result = future.result()
    #
    # operation.add_done_callback(my_callback)

    # Once the operation is complete,
    # get output document information from operation metadata
    metadata = documentai.BatchProcessMetadata(operation.metadata)

    if metadata.state != documentai.BatchProcessMetadata.State.SUCCEEDED:
        raise ValueError(f"Batch Process Failed: {metadata.state_message}")

    storage_client = storage.Client()

    print("Output files:")
    # One process per Input Document
    for process in list(metadata.individual_process_statuses):
        # output_gcs_destination format: gs://BUCKET/PREFIX/OPERATION_NUMBER/INPUT_FILE_NUMBER/
        # The Cloud Storage API requires the bucket name and URI prefix separately
        matches = re.match(r"gs://(.*?)/(.*)", process.output_gcs_destination)
        if not matches:
            print(
                "Could not parse output GCS destination:",
                process.output_gcs_destination,
            )
            continue

        output_bucket, output_prefix = matches.groups()

        # Get List of Document Objects from the Output Bucket
        output_blobs = storage_client.list_blobs(output_bucket, prefix=output_prefix)

        # Document AI may output multiple JSON files per source file
        for blob in output_blobs:
            # Document AI should only output JSON files to GCS
            if blob.content_type != "application/json":
                print(
                    f"Skipping non-supported file: {blob.name} - Mimetype: {blob.content_type}"
                )
                continue

            # Download JSON File as bytes object and convert to Document Object
            print(f"Fetching {blob.name}")
            document = documentai.Document.from_json(
                blob.download_as_bytes(), ignore_unknown_fields=True
            )

            # For a full list of Document object attributes, please reference this page:
            # https://cloud.google.com/python/docs/reference/documentai/latest/google.cloud.documentai_v1.types.Document

            return document


def create_processor(
    project_id: str, location: str, processor_display_name: str, processor_type: str
) -> None:
    """
    Creates the Document AI Processor.
    """
    # You must set the api_endpoint if you use a location other than 'us'.
    print(f"Checking for existing processor: {processor_display_name}")
    opts = ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")

    client = documentai.DocumentProcessorServiceClient(client_options=opts)

     # The full resource name of the location
    # e.g.: projects/project_id/locations/location
    parent = client.common_location_path(project_id, location)
    
    # Make GetProcessor request
    processor_list = client.list_processors(parent=parent)
    for processor in processor_list:
        if processor.display_name == processor_display_name:        
            print(f"Processor already exists: {processor.name}")
            return processor
    
    print("Processor does not exist, creating...")

    # Create a processor
    processor = client.create_processor(
        parent=parent,
        processor=documentai.Processor(
            display_name=processor_display_name, type_=processor_type
        ),
    )

    # Print the processor information
    print(f"Processor Name: {processor.name}")
    print(f"Processor Display Name: {processor.display_name}")
    print(f"Processor Type: {processor.type_}")
    
    return processor


def enable_processor(project_id: str, location: str, processor_id: str) -> None:
    """
    Enables the Document AI Processor.
    """
    # You must set the api_endpoint if you use a location other than 'us'.
    opts = ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")

    client = documentai.DocumentProcessorServiceClient(client_options=opts)

    # The full resource name of the location
    # e.g.: projects/project_id/locations/location/processors/processor_id
    processor_name = client.processor_path(project_id, location, processor_id)
    request = documentai.EnableProcessorRequest(name=processor_name)

    # Make EnableProcessor request
    try:
        operation = client.enable_processor(request=request)

        # Print operation name
        print(operation.operation.name)
        # Wait for operation to complete
        operation.result()
    # Cannot enable a processor that is already enabled
    except FailedPrecondition as e:
        print(e.message)


def disable_processor(project_id: str, location: str, processor_id: str) -> None:
    """
    Disables the Document AI Processor.
    """
    # You must set the api_endpoint if you use a location other than 'us'.
    opts = ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")

    client = documentai.DocumentProcessorServiceClient(client_options=opts)

    # The full resource name of the processor
    # e.g.: projects/project_id/locations/location/processors/processor_id
    processor_name = client.processor_path(project_id, location, processor_id)
    request = documentai.DisableProcessorRequest(name=processor_name)

    # Make DisableProcessor request
    try:
        operation = client.disable_processor(request=request)

        # Print operation name
        print(operation.operation.name)
        # Wait for operation to complete
        operation.result()
    # Cannot disable a processor that is already disabled
    except FailedPrecondition as e:
        print(e.message)

def layout_to_text(layout: documentai.Document.Page.Layout, text: str) -> str:
    """
    Document AI identifies text in different parts of the document by their
    offsets in the entirety of the document"s text. This function converts
    offsets to a string.
    """
    # If a text segment spans several lines, it will
    # be stored in different text segments.
    return "".join(
        text[int(segment.start_index) : int(segment.end_index)]
        for segment in layout.text_anchor.text_segments
    )
    
def extract_paragraphs(
    page_number: int, paragraphs: Sequence[documentai.Document.Page.Paragraph], text: str, doc_ref
) -> None:
    """
    Print all paragraphs from the page and writes them into Firestore.
    """
    for idx, paragraph in enumerate(paragraphs):
        paragraph_text = layout_to_text(paragraph.layout, text)
        print(f"Paragraph text: {paragraph_text}")  
        
        # Create a paragraph id
        paragraph_id = str(page_number) + "." + str(idx)
        
        # Update the document with paragraph data and set the indexed status to false
        doc_ref.collection("paragraphs").document(paragraph_id).set({"text": paragraph_text, "indexed": False, "page": page_number})
        
def extract_blocks(
    page_number: int, blocks: Sequence[documentai.Document.Page.Block], text: str, doc_ref
) -> None:
    """
    Extract all blocks from the page and writes them into Firestore.
    """
    for idx, block in enumerate(blocks):
        paragraph_text = layout_to_text(block.layout, text)
        print(f"Paragraph text: {paragraph_text}")  
        
        # Create a paragraph id
        paragraph_id = str(page_number) + "." + str(idx)
        
        # Update the document with block data and set the indexed status to false
        doc_ref.collection("blocks").document(paragraph_id).set({"text": paragraph_text, "indexed": False, "page": page_number})

# Triggered by the workflow
@functions_framework.http
def chunker(request) -> tuple:
    """
    Given a Cloud Storage object, parse the object using Document AI and put all the relevant metadata into Firestore.
    """
    # Get the bucket name and file name from the request
    request_json = request.get_json(silent=True)
    object = request_json['object']
    bucket = request_json['bucket']
    print(f"bucket: {bucket}, object: {object}")
    
    blob_uri = f"gs://{bucket}/{object}"

    output_bucket = os.environ.get("OUTPUT_BUCKET_NAME")
    output_uri = f"gs://{output_bucket}/"
    
    # Create a Document AI processor
    processor = create_processor(
        project_id = PROJECT_ID, location = LOCATION, processor_display_name = PROCESSOR_DISPLAY_NAME, processor_type = PROCESSOR_TYPE
    )
    
    processor_id = processor.name.split("/")[-1]
    
    # To save costs, we disable the processor at the end of this function, hence enable it
    print("Enabling processor")
    enable_processor(project_id = PROJECT_ID, location = LOCATION, processor_id = processor_id)
    
    print("Processing document")
    document = batch_process_documents(
        project_id = PROJECT_ID,
        location = LOCATION,
        processor_id = processor_id, 
        gcs_output_uri = output_uri,
        gcs_input_uri = blob_uri
    )
        
    text = document.text
    print(f"Full document text: {text}\n")
    
    filename = object.split("/")[-1]
    collection_name = object.split("/")[0]
    
    #Create a file reference in Firestore
    doc_ref = db.collection(collection_name).document(filename)
    
    languages = ""
    
    print(f"There are {len(document.pages)} page(s) in this document.\n")

    for page in document.pages:
        print(f"Page {page.page_number}:")
        
        # Get all detected langauges
        for lang in page.detected_languages:
            if lang.language_code not in languages and lang.confidence > 0.8:
                languages += lang.language_code + ","
        
        # Extract metadata and write it to Firestore
        extract_paragraphs(page.page_number, page.paragraphs, text, doc_ref)
        #extract_blocks(page.page_number, page.blocks, text, doc_ref)
        
    languages = languages[:-1]
    data = {"text": text, "status": "Processing...", "languages": languages}
    doc_ref.set(data)
    
    # Disable the processor to reduce the costs
    disable_processor(project_id = PROJECT_ID, location = LOCATION, processor_id = processor_id)
    
    return ('Document processed successfully', 200)
