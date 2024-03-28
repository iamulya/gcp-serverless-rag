import functions_framework
from google.cloud import firestore  # type: ignore
from google.cloud.firestore_v1.base_query import FieldFilter
from langchain.vectorstores.utils import DistanceStrategy
from langchain_community.vectorstores.bigquery_vector_search import BigQueryVectorSearch
from langchain_google_vertexai import VertexAIEmbeddings

PROJECT_ID = "YOUR_PROJECT"
LOCATION = "YOUR_LOCATION"
BATCH_SIZE = 5  # Currently the batch size is limited to five. See: https://cloud.google.com/vertex-ai/generative-ai/docs/embeddings/get-text-embeddings#get_text_embeddings_for_a_snippet_of_text

BIGQUERY_DATASET = "gemini_di"  # @param {type: "string"}
BIGQUERY_TABLE = "doc_and_vectors"  # @param {type: "string"}

db = firestore.Client()
embeddings = VertexAIEmbeddings(
    model_name="textembedding-gecko@003", project=PROJECT_ID, location=LOCATION
)

from google.cloud import bigquery

client = bigquery.Client(project=PROJECT_ID, location=LOCATION)
client.create_dataset(dataset=BIGQUERY_DATASET, exists_ok=True)

store = BigQueryVectorSearch(
    project_id=PROJECT_ID,
    dataset_name=BIGQUERY_DATASET,
    table_name=BIGQUERY_TABLE,
    location=LOCATION,
    embedding=embeddings,
    distance_strategy=DistanceStrategy.EUCLIDEAN_DISTANCE,
)


def batchify_list(original_list, group_size=BATCH_SIZE):
    """
    This function converts a list into a list of lists using list comprehension.

    Args:
        original_list: The original list to be converted.
        group_size: The maximum number of elements in each sublist.

    Returns:
        A list of lists, where each sublist has a maximum of 'group_size' elements.
    """
    return [
        original_list[i : i + group_size]
        for i in range(0, len(original_list), group_size)
    ]


@functions_framework.http
def indexer(request) -> tuple:

    # Get the collection name and file name
    request_json = request.get_json(silent=True)
    object = request_json["object"]
    filename = object.split("/")[-1]
    collection_name = object.split("/")[0]

    # Set the status of the file to "Indexing..."
    file_ref = db.collection(collection_name).document(filename)
    file_ref.update({"status": "Indexing..."})

    paragraph_ref = file_ref.collection("paragraphs")
    
    # Filter out any paragraphs that have already been indexed - we only want to index the ones that haven't been indexed yet in order to save unnecessary calls to the Vertex AI Embedding Model
    results = paragraph_ref.where(filter=FieldFilter("indexed", "==", False)).stream()
    
    # Get all the texts/paragraphs to index
    texts = [(result.to_dict()["text"], result.to_dict()["page"]) for result in results]
    print(f"Found {len(texts)} texts to index")

    # Batchify the texts to index - each batch will be indexed in a single request
    batchified_texts = batchify_list(texts)

    for batch in batchified_texts:
        metadatas = [{"source": filename, "page": t[1]} for t in batch]
        texts_to_embed = [t[0] for t in batch]
        store.add_texts(texts_to_embed, metadatas=metadatas)
        
        # Update the indexed status for each item in the batch
        for item in batch:
            print(f"Updating indexing status for: {item}")
            selected_ref = paragraph_ref.where(
                filter=FieldFilter("text", "==", item[0])
            ).stream()
            for doc_ref in selected_ref:
                # Set the indexed status to True
                doc_ref.reference.update({"indexed": True})

    results = list(
        paragraph_ref.where(filter=FieldFilter("indexed", "==", False)).stream()
    )

    if len(results) == 0:
        print("All texts have been indexed")
        db.collection(collection_name).document(filename).update({"status": "Indexed"})
    else:
        print(f"Still {len(results)} texts to index")

    return ("Indexing done!", 200)
