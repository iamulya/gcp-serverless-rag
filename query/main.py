import functions_framework
import jsonpickle
from langchain.chains.qa_with_sources.retrieval import RetrievalQAWithSourcesChain
from langchain.prompts import PromptTemplate
from langchain.vectorstores.utils import DistanceStrategy
from langchain_community.vectorstores.bigquery_vector_search import BigQueryVectorSearch
from langchain_google_vertexai import ChatVertexAI, VertexAIEmbeddings

from langchain.globals import set_debug, set_verbose

# Enable debug logging
set_debug(True)
set_verbose(True)

PROJECT_ID = "YOUR_PROJECT"
LOCATION = "YOUR_LOCATION"
BIGQUERY_DATASET = "gemini_di"  # @param {type: "string"}
BIGQUERY_TABLE = "doc_and_vectors"  # @param {type: "string"}

embeddings = VertexAIEmbeddings(
    model_name="textembedding-gecko@003", project=PROJECT_ID, location=LOCATION
)

store = BigQueryVectorSearch(
    project_id=PROJECT_ID,
    dataset_name=BIGQUERY_DATASET,
    table_name=BIGQUERY_TABLE,
    location=LOCATION,
    embedding=embeddings,
    distance_strategy=DistanceStrategy.EUCLIDEAN_DISTANCE,
)

chat_llm = ChatVertexAI(model_name="gemini-pro", project=PROJECT_ID, location=LOCATION)

custom_prompt_template = """You are a chatbot used for answering questions based on provided context. Use the following pieces of context to answer the question at the end. 

{context}

Question: {question}
Helpful Answer:"""

di_prompt = PromptTemplate(
    template=custom_prompt_template, input_variables=["context", "question"]
)

@functions_framework.http
def query(request) -> tuple:

    # Get the bucket name and file name from the request
    request_json = request.get_json(silent=True)
    query_text = request_json["query"]

    retriever = store.as_retriever(search_kwargs={"k": 1}, return_source_documents=True)

    chatbot = RetrievalQAWithSourcesChain.from_chain_type(
        llm=chat_llm,
        chain_type="map_reduce",
        retriever=retriever,
        return_source_documents=True,
    )
    chatbot.combine_documents_chain.llm_chain.prompt = di_prompt

    try:
        answer = chatbot({"question": query_text})
    except Exception as err:
        answer = (
            f"Sorry, an error occured while procuring the answer. Error: {str(err)}"
        )

    # TODO - Find a better way to convert to json
    json_string = jsonpickle.encode(answer)
    print(f"Query reply - {json_string}")

    return (json_string, 200)
