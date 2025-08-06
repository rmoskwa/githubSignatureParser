import os
import json
from typing import Dict, List, Optional
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

class SupabaseManager:
    def __init__(self):
        url = os.getenv('SUPABASE_URL', 'https://mnbvsrsivuuuwbtkmumt.supabase.co')
        key = os.getenv('SUPABASE_KEY')
        
        if not key:
            raise ValueError("SUPABASE_KEY not found in environment variables")
            
        self.client: Client = create_client(url, key)
        
    def update_function(self, function_data: Dict) -> bool:
        """Update or insert function in api_reference table"""
        
        try:
            # Prepare the entry (without common_errors since it doesn't exist in the schema)
            entry = {
                "name": function_data.get("name", "unknown"),
                "language": "matlab",
                "signature": function_data.get("signature", ""),
                "description": function_data.get("description", ""),
                "parameters": json.dumps(function_data.get("parameters", {})),
                "returns": json.dumps(function_data.get("returns", [])),
                "source_id": "pulseq_matlab",
                "pulseq_version": "1.5.0"
            }
            
            # Add embedding if available
            if "embedding" in function_data:
                entry["embedding"] = function_data["embedding"]
                
            # Check if the function already exists
            existing = self.client.table("api_reference").select("id").eq(
                "name", entry["name"]
            ).eq(
                "language", entry["language"]
            ).eq(
                "pulseq_version", entry["pulseq_version"]
            ).execute()
            
            if existing.data:
                # Update existing entry
                result = self.client.table("api_reference").update(entry).eq(
                    "id", existing.data[0]["id"]
                ).execute()
                print(f"Updated {entry['name']} in database")
            else:
                # Insert new entry
                result = self.client.table("api_reference").insert(entry).execute()
                print(f"Inserted {entry['name']} into database")
                
            return True
            
        except Exception as e:
            print(f"Error updating database for {function_data.get('name', 'unknown')}: {e}")
            return False
            
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
                # Parse JSON fields
                data = result.data[0]
                if isinstance(data.get("parameters"), str):
                    data["parameters"] = json.loads(data["parameters"])
                if isinstance(data.get("returns"), str):
                    data["returns"] = json.loads(data["returns"])
                if isinstance(data.get("common_errors"), str):
                    data["common_errors"] = json.loads(data["common_errors"])
                return data
                
            return None
            
        except Exception as e:
            print(f"Error retrieving {name} from database: {e}")
            return None
            
    def list_functions(self, language: str = "matlab", version: str = "1.5.0") -> List[Dict]:
        """List all functions in the database"""
        
        try:
            result = self.client.table("api_reference").select("name, description").eq(
                "language", language
            ).eq(
                "pulseq_version", version
            ).execute()
            
            return result.data
            
        except Exception as e:
            print(f"Error listing functions: {e}")
            return []
            
    def delete_function(self, name: str, language: str = "matlab", version: str = "1.5.0") -> bool:
        """Delete a function from the database"""
        
        try:
            result = self.client.table("api_reference").delete().eq(
                "name", name
            ).eq(
                "language", language
            ).eq(
                "pulseq_version", version
            ).execute()
            
            print(f"Deleted {name} from database")
            return True
            
        except Exception as e:
            print(f"Error deleting {name}: {e}")
            return False
            
    def bulk_update(self, functions: List[Dict]) -> Dict:
        """Update multiple functions at once"""
        
        results = {
            'successful': [],
            'failed': []
        }
        
        for func_data in functions:
            if self.update_function(func_data):
                results['successful'].append(func_data.get('name', 'unknown'))
            else:
                results['failed'].append(func_data.get('name', 'unknown'))
                
        return results