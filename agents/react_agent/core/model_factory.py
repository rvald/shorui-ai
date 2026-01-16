"""
Model factory for creating LLM instances across different providers.
Supports OpenAI, Anthropic, and Ollama with consistent interface.
"""

from typing import Optional, Literal
from langchain_openai import ChatOpenAI

from loguru import logger

ModelType = Literal["openai"]

class ModelFactory:
    """
    Factory for creating LLM instances with consistent configuration.
    
    Supports multiple providers:
    - OpenAI (GPT-4, GPT-3.5, etc.)
    """

    @staticmethod
    def create_model(
        model_name: str,
        model_type: ModelType = "openai",
        temperature: Optional[float] = None,
        **kwargs
    ):
        """
        Create an LLM instance based on the specified type.
        
        Args:
            model_name: Specific model name
            model_type: Type of model ("openai")
            temperature: Temperature for generation (0-1). If None, uses DEFAULT_TEMPERATURE from config
            **kwargs: Additional provider-specific parameters
            
        Returns:
            Configured chat model instance
            
        Raises:
            ValueError: If model_type is not supported or required config is missing
            
        Examples:
            >>> # OpenAI model
            >>> model = ModelFactory.create_model("gpt-4o-mini")
        """
        # Use config default temperature if not explicitly provided
        temperature = temperature if temperature is not None else 0.0
        
        logger.info(f"Creating model - type: {model_type}, name: {model_name}, temp: {temperature}")
        
        if model_type == "openai":
            return ModelFactory._create_openai_model(model_name, temperature, **kwargs)
        
        else:
            raise ValueError(
                f"Unsupported model_type: {model_type}. "
                f"Must be one of: 'openai'"
            )
    
    @staticmethod
    def _create_openai_model(
        model_name: str,
        temperature: float,
        **kwargs
    ) -> ChatOpenAI:
        """
        Create OpenAI chat model.
        
        Args:
            model_name: Model name (e.g., "gpt-4o-mini", "gpt-4", "gpt-3.5-turbo")
            temperature: Temperature for generation
            **kwargs: Additional OpenAI-specific parameters
            
        Returns:
            ChatOpenAI instance
        """
        import os
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OpenAI API key required. Set OPENAI_API_KEY in .env file.")
        
        model = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            api_key=api_key,
            **kwargs
        )
        
        logger.info(f"OpenAI model created - model: {model_name}, temperature: {temperature}")
        return model