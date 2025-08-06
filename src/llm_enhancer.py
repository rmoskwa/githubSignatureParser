import os
import json
import google.generativeai as genai
from typing import Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()

class LLMParameterEnhancer:
    def __init__(self):
        genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
        self.model = genai.GenerativeModel('gemini-1.5-flash')
        
    def enhance_function(self, parsed_data: Dict) -> Dict:
        """Use Gemini to extract comprehensive parameter information"""
        
        # Build the prompt
        prompt = self._build_prompt(parsed_data)
        
        try:
            response = self.model.generate_content(prompt)
            
            # Extract JSON from response
            json_str = self._extract_json(response.text)
            
            if json_str:
                try:
                    result = json.loads(json_str)
                    # Add metadata
                    result['name'] = parsed_data.get('function_name', 'unknown')
                    result['signature'] = parsed_data.get('signature', '')
                    result['file_path'] = parsed_data.get('file_path', '')
                    return result
                except json.JSONDecodeError as e:
                    print(f"Warning: Invalid JSON from LLM: {e}")
                    return self._create_fallback_response(parsed_data)
            else:
                print(f"Warning: Could not extract JSON from LLM response")
                return self._create_fallback_response(parsed_data)
                
        except Exception as e:
            print(f"Error in LLM enhancement: {e}")
            return self._create_fallback_response(parsed_data)
            
    def _build_prompt(self, parsed_data: Dict) -> str:
        """Build the prompt for the LLM"""
        
        # Truncate code body if too long
        code_body = parsed_data.get('code_body', '') or ''
        if len(code_body) > 8000:
            code_body = code_body[:8000] + "\n... [truncated]"
            
        prompt = f"""Analyze this MATLAB Pulseq function and extract ALL parameters with precise details.

Function Signature: {parsed_data.get('signature', 'N/A')}

Help Text: {parsed_data.get('help_text', 'N/A')}

Detected InputParser Parameters: {json.dumps(parsed_data.get('input_parser_params', []), indent=2)}

Detected Varargin Parameters: {json.dumps(parsed_data.get('varargin_params', []), indent=2)}

Detected Switch/Case Parameters: {json.dumps(parsed_data.get('switch_params', []), indent=2)}

Code Body (first 8000 chars):
{code_body}

Extract and return JSON with this EXACT structure:
{{
    "description": "Clear one-line description of what this function does",
    "parameters": {{
        "required": [
            {{
                "name": "parameter_name",
                "type": "double|string|struct|cell|logical|char",
                "units": "seconds|Hz|Hz/m|radians|meters|none",
                "description": "Clear description of the parameter",
                "example": "pi/2 or 0.5e-3"
            }}
        ],
        "optional": [
            {{
                "name": "Duration",
                "type": "double",
                "units": "seconds",
                "default": "4e-3",
                "description": "RF pulse duration",
                "valid_values": "positive number",
                "example": "2e-3"
            }}
        ]
    }},
    "returns": [
        {{
            "name": "rf",
            "type": "struct",
            "description": "RF pulse structure",
            "fields": ["signal", "t", "freqOffset", "phaseOffset", "deadTime"]
        }}
    ],
    "common_errors": [
        "List any common mistakes users might make"
    ]
}}

CRITICAL RULES:
1. For mr.opts(): Do NOT include 'maxRF' - it doesn't exist in MATLAB version
2. For gradients: Units are ALWAYS Hz/m (not T/m, not mT/m)
3. Time units are ALWAYS seconds (not milliseconds, not us)
4. Angles are ALWAYS radians (not degrees) in function calls
5. Do NOT invent parameters like 'timeBwChannels' - only use what's actually in the code
6. Check for both addParameter() and varargin{{i}} patterns
7. For 'system' parameter: type is 'struct', it comes from mr.opts()
8. Look for parse(varargin{{:}}) to understand how parameters are processed
9. Default values should match exactly what's in the code
10. If a parameter accepts name-value pairs, it goes in 'optional' not 'required'

IMPORTANT: Return ONLY valid JSON, no extra text or markdown."""
        
        return prompt
        
    def _extract_json(self, text: str) -> Optional[str]:
        """Extract JSON from LLM response"""
        # Try to find JSON between curly braces
        import re
        
        # Remove markdown code blocks if present
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        
        # Find the first { and last }
        start = text.find('{')
        if start == -1:
            return None
            
        # Find matching closing brace
        brace_count = 0
        end = start
        for i in range(start, len(text)):
            if text[i] == '{':
                brace_count += 1
            elif text[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    end = i
                    break
                    
        if end > start:
            return text[start:end+1]
            
        return None
        
    def _create_fallback_response(self, parsed_data: Dict) -> Dict:
        """Create a fallback response using parsed data"""
        
        # Combine all detected parameters
        all_params = set()
        
        required = []
        optional = []
        
        # Process inputParser params
        for param in parsed_data.get('input_parser_params', []):
            param_dict = {
                'name': param['name'],
                'type': 'double',  # Default type
                'description': f"Parameter {param['name']}",
                'units': 'none'
            }
            
            if param['type'] == 'required':
                required.append(param_dict)
            else:
                if param.get('default'):
                    param_dict['default'] = str(param['default'])
                optional.append(param_dict)
                
        # Process varargin params
        for param in parsed_data.get('varargin_params', []):
            if param['name'] not in [p['name'] for p in required + optional]:
                optional.append({
                    'name': param['name'],
                    'type': 'double',
                    'description': f"Parameter {param['name']}",
                    'units': 'none',
                    'default': str(param.get('default', 'N/A'))
                })
                
        # Process switch/case params
        for param in parsed_data.get('switch_params', []):
            if param['name'] not in [p['name'] for p in required + optional]:
                optional.append({
                    'name': param['name'],
                    'type': 'double' if param.get('expects_value') else 'logical',
                    'description': f"Parameter {param['name']}",
                    'units': 'none'
                })
                
        return {
            'name': parsed_data.get('function_name', 'unknown'),
            'signature': parsed_data.get('signature', ''),
            'description': parsed_data.get('help_text', '').split('\n')[0] if parsed_data.get('help_text') else 'No description available',
            'parameters': {
                'required': required,
                'optional': optional
            },
            'returns': [],
            'common_errors': []
        }