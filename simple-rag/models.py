"""Simple RAG model - that's all you need!"""
from beanis import Document, VectorField
from typing import List
from typing_extensions import Annotated


class KnowledgeBase(Document):
    """A document in our knowledge base"""
    text: str
    embedding: Annotated[List[float], VectorField(dimensions=1024)]

    class Settings:
        name = "knowledge"
