from typing import AsyncGenerator
from langchain_ollama import ChatOllama


class OllamaService:
    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url
        self.model = model
        self.client = ChatOllama(
            model=self.model,
            base_url=self.base_url,
            temperature=0,
        )

    async def generate(self, prompt: str) -> str:
        response = await self.client.ainvoke(prompt)
        return response.content

    async def stream(self, prompt: str) -> AsyncGenerator[str, None]:
        async for chunk in self.client.astream(prompt):
            if hasattr(chunk, "content") and chunk.content:
                yield chunk.content
