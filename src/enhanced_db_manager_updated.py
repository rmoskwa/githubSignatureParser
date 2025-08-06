import os
import json
from typing import Dict, List, Optional
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client
from src.embeddings import EmbeddingsGenerator

load_dotenv()

class EnhancedDatabaseManager:
    """Manage database updates for all function types with updated schema"""
    
    def __init__(self):
        url = os.getenv('SUPABASE_URL', 'https://mnbvsrsivuuuwbtkmumt.supabase.co')
        key = os.getenv('SUPABASE_KEY')
        
        if not key:
            raise ValueError("SUPABASE_KEY not found in environment variables")
        
        self.client: Client = create_client(url, key)
        self.embeddings_gen = EmbeddingsGenerator()
        self._next_id_cache = None  # Cache for next ID to avoid repeated queries
    
    def _get_next_id(self) -> int:
        """Get the next available ID for the api_reference table"""
        try:
            # If we have a cached next ID, use it and increment
            if self._next_id_cache is not None:
                next_id = self._next_id_cache
                self._next_id_cache += 1
                return next_id
            
            # Otherwise, query for the max ID
            result = self.client.table("api_reference").select("id").order("id", desc=True).limit(1).execute()
            
            if result.data and result.data[0]:
                max_id = result.data[0]["id"]
                self._next_id_cache = max_id + 1
            else:
                # Table is empty, start with ID 1
                self._next_id_cache = 1
            
            # Return the ID and increment cache for next use
            next_id = self._next_id_cache
            self._next_id_cache += 1
            return next_id
            
        except Exception as e:
            print(f"  Warning: Could not get next ID, using timestamp: {e}")
            # Fallback to timestamp-based ID if there's an issue
            import time
            return int(time.time() * 1000) % 2147483647  # Ensure it fits in an integer
    
    def update_file_functions(self, enhanced_data: Dict) -> Dict:
        """Update database with all functions from a file"""
        
        results = {
            'file': enhanced_data['file_info']['name'],
            'main': {'status': 'pending', 'name': None},
            'helpers': [],
            'internal': [],
            'errors': []
        }
        
        # Update main function
        if enhanced_data['main_function']:
            try:
                self.update_function(enhanced_data['main_function'])
                results['main'] = {
                    'status': 'success',
                    'name': enhanced_data['main_function']['name']
                }
                print(f"✓ Updated main function: {enhanced_data['main_function']['name']}")
            except Exception as e:
                results['errors'].append(f"Main function error: {str(e)}")
                results['main']['status'] = 'failed'
                print(f"✗ Failed to update main function: {e}")
        
        # Update helper functions
        for helper in enhanced_data.get('helper_functions', []):
            try:
                self.update_function(helper)
                results['helpers'].append({
                    'status': 'success',
                    'name': helper['name']
                })
                print(f"✓ Updated helper function: {helper['name']}")
            except Exception as e:
                results['errors'].append(f"Helper {helper['name']} error: {str(e)}")
                results['helpers'].append({
                    'status': 'failed',
                    'name': helper['name']
                })
                print(f"✗ Failed to update helper {helper['name']}: {e}")
        
        # Update internal functions (optional - only if public)
        for internal in enhanced_data.get('internal_functions', []):
            if internal.get('visibility') == 'public':
                try:
                    self.update_function(internal)
                    results['internal'].append({
                        'status': 'success',
                        'name': internal['name']
                    })
                    print(f"✓ Updated internal function: {internal['name']}")
                except Exception as e:
                    results['errors'].append(f"Internal {internal['name']} error: {str(e)}")
                    print(f"✗ Failed to update internal {internal['name']}: {e}")
        
        return results
    
    def update_function(self, function_data: Dict):
        """Update or insert a single function in api_reference table"""
        
        # Generate embedding
        embedding = self.embeddings_gen.generate_embedding(function_data)
        
        # Check if function uses nargin pattern - PRIORITIZE the parser's flag
        has_nargin = function_data.get('uses_nargin_pattern', False)
        
        # Additional check: look for nargin in the parameter sources
        if not has_nargin and function_data.get('parameters'):
            # Check if nargin_detection was used
            if function_data['parameters'].get('nargin_detection') is not None:
                has_nargin = True
            # Check if any parameter was detected via nargin_check
            for param in function_data['parameters'].get('optional', []):
                if param.get('source') == 'nargin_check':
                    has_nargin = True
                    break
        
        # Log nargin detection for debugging
        if has_nargin:
            print(f"  → {function_data['name']} uses nargin pattern")
        
        # Generate search terms for the function
        search_terms = [
            function_data.get("name", "unknown"),
            function_data.get("class_name") if function_data.get("class_name") else None,
            function_data.get("namespace") if function_data.get("namespace") else None
        ]
        # Remove None values and add description keywords
        search_terms = [term for term in search_terms if term is not None]
        if function_data.get("description"):
            # Add first few words of description as search terms
            desc_words = function_data["description"].split()[:5]
            search_terms.extend(desc_words)
        
        # Prepare the entry with all fields matching our database schema
        entry = {
            "name": function_data.get("name", "unknown"),
            "language": "matlab",
            "signature": function_data.get("signature"),
            "description": function_data.get("description", ""),
            "parameters": function_data.get("parameters", {}),  # Already in correct format
            "returns": function_data.get("returns", []),  # Already in correct format
            "source_id": "github.com/pulseq/pulseq",
            "pulseq_version": "1.5.0",
            "embedding": embedding,
            "function_type": function_data.get("function_type", "main"),
            "usage_examples": function_data.get("usage_examples", []),
            "related_functions": function_data.get("related_functions", []),
            "has_nargin_pattern": has_nargin,
            "last_updated": datetime.now().isoformat(),
            # New schema fields
            "class_name": function_data.get("class_name"),
            "is_class_method": function_data.get("is_class_method", False),
            "calling_pattern": function_data.get("calling_pattern"),
            "instance_variable": function_data.get("instance_variable"),
            "search_terms": search_terms
        }
        
        # Check if the function already exists
        try:
            existing = self.client.table("api_reference").select("id").eq(
                "name", entry["name"]
            ).eq(
                "language", entry["language"]
            ).execute()
            
            if existing.data:
                # Update existing entry
                result = self.client.table("api_reference").update(entry).eq(
                    "id", existing.data[0]["id"]
                ).execute()
                print(f"  Updated {entry['name']} in database")
            else:
                # Insert new entry - need to generate ID
                entry["id"] = self._get_next_id()
                result = self.client.table("api_reference").insert(entry).execute()
                print(f"  Inserted {entry['name']} into database with ID {entry['id']}")
                
        except Exception as e:
            print(f"  Error updating {entry['name']}: {e}")
            raise e
    
    def get_function(self, name: str, language: str = "matlab", version: str = "1.5.0") -> Optional[Dict]:
        """Retrieve a function from the database"""
        
        try:
            result = self.client.table("api_reference").select("*").eq(
                "name", name
            ).eq(
                "language", language
            ).eq(
                "pulseq_version", version
            ).execute()
            
            if result.data:
                # Data is already in correct format (JSONB columns)
                return result.data[0]
            
            return None
            
        except Exception as e:
            print(f"Error retrieving {name} from database: {e}")
            return None
    
    def list_functions_by_type(self, function_type: str = None, language: str = "matlab", version: str = "1.5.0") -> List[Dict]:
        """List functions, optionally filtered by type"""
        
        try:
            query = self.client.table("api_reference").select("name, description, function_type, has_nargin_pattern").eq(
                "language", language
            ).eq(
                "pulseq_version", version
            )
            
            if function_type:
                query = query.eq("function_type", function_type)
            
            result = query.execute()
            return result.data
            
        except Exception as e:
            print(f"Error listing functions: {e}")
            return []
    
    def clear_matlab_functions(self):
        """Clear all MATLAB functions from the database (use with caution!)"""
        try:
            result = self.client.table("api_reference").delete().eq(
                "language", "matlab"
            ).execute()
            print(f"Cleared {len(result.data) if result.data else 0} MATLAB functions from database")
            return result
        except Exception as e:
            print(f"Error clearing MATLAB functions: {e}")
            return None
