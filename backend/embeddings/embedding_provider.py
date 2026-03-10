from langchain_ollama import OllamaEmbeddings


class EmbeddingProvider:
    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url
        self.model = model

    def get_embeddings(self) -> OllamaEmbeddings:
        return OllamaEmbeddings(
            model=self.model,
            base_url=self.base_url,
        )
