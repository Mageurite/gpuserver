"""
RAG (Retrieval-Augmented Generation) Module

This module provides knowledge base retrieval functionality for the GPU Server.
Supports both real RAG retrieval (with Milvus) and Mock mode for testing.
"""

from .rag_engine import RAGEngine, get_rag_engine

__all__ = ["RAGEngine", "get_rag_engine"]
