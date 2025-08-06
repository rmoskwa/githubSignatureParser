import os
import google.generativeai as genai
from typing import Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()

class EmbeddingsGenerator:
    def __init__(self):
        genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
        
    def generate_embedding(self, function_data: Dict) -> List[float]:
        """Generate embedding for a function using Google's embedding model"""
        
        # Create a comprehensive text representation of the function
        text = self._create_text_representation(function_data)
        
        try:
            # Use the embedding model
            result = genai.embed_content(
                model="models/embedding-001",
                content=text,
                task_type="retrieval_document",
                title=function_data.get('name', 'function')
            )
            
            return result['embedding']
            
        except Exception as e:
            print(f"Error generating embedding for {function_data.get('name', 'unknown')}: {e}")
            # Return a zero vector as fallback
            return [0.0] * 768  # Standard embedding size
            
    def _create_text_representation(self, function_data: Dict) -> str:
        """Create a text representation of the function for embedding"""
        
        parts = []
        
        # Add function name and signature
        parts.append(f"Function: {function_data.get('name', 'unknown')}")
        parts.append(f"Signature: {function_data.get('signature', '')}")
        
        # Add description
        parts.append(f"Description: {function_data.get('description', '')}")
        
        # Add parameter information
        params = function_data.get('parameters', {})
        
        if params.get('required'):
            required_names = [p['name'] for p in params['required']]
            parts.append(f"Required parameters: {', '.join(required_names)}")
            
        if params.get('optional'):
            optional_info = []
            for p in params['optional']:
                info = f"{p['name']}"
                if p.get('units') and p['units'] != 'none':
                    info += f" ({p['units']})"
                if p.get('default'):
                    info += f" default={p['default']}"
                optional_info.append(info)
            parts.append(f"Optional parameters: {', '.join(optional_info)}")
            
        # Add return information
        returns = function_data.get('returns', [])
        if returns:
            return_info = [f"{r['name']} ({r['type']})" for r in returns]
            parts.append(f"Returns: {', '.join(return_info)}")
            
        # Add common errors if any
        errors = function_data.get('common_errors', [])
        if errors:
            parts.append(f"Common errors: {'; '.join(errors)}")
            
        # Combine all parts
        text = " | ".join(parts)
        
        # Limit text length to avoid token limits
        if len(text) > 5000:
            text = text[:5000]
            
        return text
        
    def batch_generate_embeddings(self, functions: List[Dict]) -> List[Dict]:
        """Generate embeddings for multiple functions"""
        
        for func_data in functions:
            embedding = self.generate_embedding(func_data)
            func_data['embedding'] = embedding
            
        return functions
        
    def similarity_search(self, query: str, functions: List[Dict], top_k: int = 5) -> List[Dict]:
        """Find similar functions based on embedding similarity"""
        
        # Generate embedding for query
        try:
            query_embedding = genai.embed_content(
                model="models/embedding-001",
                content=query,
                task_type="retrieval_query"
            )['embedding']
        except Exception as e:
            print(f"Error generating query embedding: {e}")
            return []
            
        # Calculate similarities
        similarities = []
        for func in functions:
            if 'embedding' in func and func['embedding']:
                similarity = self._cosine_similarity(query_embedding, func['embedding'])
                similarities.append((func, similarity))
                
        # Sort by similarity and return top k
        similarities.sort(key=lambda x: x[1], reverse=True)
        return [func for func, _ in similarities[:top_k]]
        
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        
        if len(vec1) != len(vec2):
            return 0.0
            
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
            
        return dot_product / (norm1 * norm2)