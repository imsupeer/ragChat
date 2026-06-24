QUERY_REWRITE_TEMPLATE = """You rewrite follow-up questions into standalone search queries for document retrieval.

Rules:
- Use conversation history only to resolve references such as "it", "that", "they", or "the same thing".
- Do not add facts that are not implied by the follow-up question and history.
- Output a single standalone retrieval query with no explanation or quotes.
- If the follow-up is already standalone, repeat it unchanged.

Conversation history:
{history}

Follow-up question:
{question}

Standalone retrieval query:"""


def build_query_rewrite_prompt(question: str, history_text: str) -> str:
    return QUERY_REWRITE_TEMPLATE.format(
        history=history_text or "(no prior turns)",
        question=question.strip(),
    )
