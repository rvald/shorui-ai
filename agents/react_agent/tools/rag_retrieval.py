"""
Regulations retrieval tool using RAG (Retrieval Augmented Generation)

This tool queries HIPAA regulations and returns AI-generated answers
grounded in the retrieved document context.
"""
from langchain_core.tools import tool
from typing import Optional
from ..infrastructure.clients import RAGClient
from loguru import logger


class RegulationsRetrieval:
    """
    RAG tool for HIPAA regulation queries.
    
    Uses the /rag/query endpoint to:
    1. Search for relevant regulation documents
    2. Generate an AI answer grounded in those documents
    
    Example:
        tool = RegulationsRetrieval()
        answer = tool.forward(query="What is the HIPAA Privacy Rule?")
    """
    
    name = "regulations_retrieval"
    description = (
        "Query HIPAA regulations and get an AI-generated answer. "
        "Use this to find information from HIPAA Privacy Rule, Security Rule, "
        "de-identification requirements, and other compliance topics."
    )
    inputs = {
        "query": {
            "type": "string",
            "description": "The question about HIPAA regulations to answer"
        }
    }
    output_type = "string"
    
    def __init__(self, rag_client: Optional[RAGClient] = None):
        """
        Initialize the regulations retrieval tool.
        
        Args:
            rag_client: Optional RAGClient instance. Creates default if not provided.
        """
        self.rag_client = rag_client or RAGClient()
    
    def forward(
        self,
        query: str,
        project_id: str = "hipaa_regulations"
    ) -> str:
        """
        Query regulations and get an AI-generated answer.
        
        Args:
            query: The question to answer about HIPAA regulations
            project_id: Project identifier (default: "default")
            
        Returns:
            AI-generated answer grounded in regulation documents
        """
        try:
            # Use query() for full RAG (retrieval + generation)
            result = self.rag_client.query(
                query=query,
                project_id=project_id,
                k=5,
            )
            
            answer = result.get("answer", "")
            if not answer:
                return (
                    "NO_RELEVANT_DOCUMENTS_FOUND: The regulations database did not return results for this query. "
                    "You MUST tell the user: 'I could not find specific guidance on this topic in the indexed regulations. "
                    "Please ensure HIPAA regulation documents have been indexed, or try rephrasing your question.' "
                    "DO NOT provide information from your training data. DO NOT make up CFR citations or regulation text."
                )
            
            return answer
            
        except Exception as e:
            logger.error(f"RAG query error: {str(e)}")
            return (
                f"RETRIEVAL_ERROR: Failed to query the regulations database: {e}. "
                "You MUST tell the user there was an error and you cannot answer without the regulations data. "
                "DO NOT provide information from your training data."
            )


@tool
def search_regulations(query: str) -> str:
    """
    Query HIPAA regulations and get an AI-generated answer.
    
    Use this tool to find information about:
    - HIPAA Privacy Rule requirements
    - HIPAA Security Rule requirements  
    - De-identification methods (Safe Harbor, Expert Determination)
    - Patient rights and authorizations
    - Breach notification requirements
    - And other HIPAA compliance topics
    
    Args:
        query: The question about HIPAA regulations to answer
        
    Returns:
        AI-generated answer grounded in HIPAA regulation documents
    """
    try: 
        # Instantiate directly for now - in future we can inject this
        retriever = RegulationsRetrieval()
        answer = retriever.forward(query)
        
        if not answer:
            return f"I couldn't find relevant regulations for: {query}"
        
        return answer
    except Exception as e:
        logger.error(f"RAG tool error for '{query[:100]}...': {str(e)}")
        return (
            "RETRIEVAL_ERROR: An error occurred while searching regulations. "
            "You MUST tell the user there was an error and you cannot provide compliance guidance without the regulations database. "
            "DO NOT use training data to answer. Suggest the user try again or contact support."
        )
