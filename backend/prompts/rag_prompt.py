RAG_SYSTEM_PROMPT = """You are an AI assistant that answers questions using the provided documents.

Rules:

* Only use the provided context.
* If the answer is not present in the documents, say:
  "I could not find the answer in the provided documents."
* Be precise and concise.
* Cite the document section if possible.
"""

RAG_TEMPLATE = """SYSTEM:
{system_prompt}

CONTEXT:
{retrieved_chunks}

QUESTION:
{user_question}

ANSWER:
"""


def build_rag_prompt(retrieved_chunks: str, user_question: str) -> str:
    return RAG_TEMPLATE.format(
        system_prompt=RAG_SYSTEM_PROMPT,
        retrieved_chunks=retrieved_chunks,
        user_question=user_question,
    )
