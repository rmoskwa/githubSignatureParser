import os
import json
import google.generativeai as genai
from typing import Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()

class EnhancedLLMProcessor:
    """Process all functions with proper context"""
    
    def __init__(self):
        genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
        self.model = genai.GenerativeModel('gemini-1.5-flash')
    
    def enhance_all_functions(self, parsed_file_data: Dict) -> Dict:
        """Enhance all functions from a file with LLM"""
        
        enhanced_result = {
            'file_info': parsed_file_data['file_info'],
            'main_function': None,
            'helper_functions': [],
            'internal_functions': []
        }
        
        # Process main function with highest priority
        if parsed_file_data['main_function']:
            enhanced_result['main_function'] = self.enhance_function(
                parsed_file_data['main_function'],
                function_type='main',
                related_functions=self._get_related_function_names(parsed_file_data)
            )
        
        # Process helper functions
        for helper in parsed_file_data['helper_functions']:
            enhanced = self.enhance_function(
                helper,
                function_type='helper',
                parent_function=parsed_file_data['main_function']['name'] if parsed_file_data['main_function'] else None
            )
            enhanced_result['helper_functions'].append(enhanced)
        
        # Process internal functions (lighter processing)
        for internal in parsed_file_data['internal_functions']:
            enhanced = self.enhance_function(
                internal,
                function_type='internal',
                minimal=True  # Don't spend too much LLM time on internal functions
            )
            enhanced_result['internal_functions'].append(enhanced)
        
        return enhanced_result
    
    def _get_related_function_names(self, parsed_file_data: Dict) -> List[str]:
        """Get names of related functions in the same file"""
        names = []
        for helper in parsed_file_data.get('helper_functions', []):
            names.append(helper['name'])
        return names
    
    def enhance_function(self, func_data: Dict, function_type: str = 'main', 
                        parent_function: str = None, related_functions: List[str] = None,
                        minimal: bool = False) -> Dict:
        """Enhance a single function with detailed parameter information"""
        
        if minimal:
            # For internal functions, just clean up what we have
            return self._minimal_enhancement(func_data)
        
        # Build context-aware prompt
        prompt = f"""Analyze this MATLAB Pulseq function and provide detailed parameter information.
        
FUNCTION DETAILS:
- Name: {func_data['name']}
- Type: {function_type} function
- Parent File: {func_data['parent_file']}
- Signature: {func_data['signature']}
{f"- Parent Function: {parent_function}" if parent_function else ""}
{f"- Related Functions: {', '.join(related_functions)}" if related_functions else ""}

EXTRACTED PARAMETERS (PRESERVE THESE EXACT NAMES):
{json.dumps(func_data['parameters'], indent=2)}

HELP TEXT:
{func_data['help_text'][:1000] if func_data['help_text'] else 'No help text available'}

FUNCTION BODY (excerpt):
{func_data['function_body'][:3000] if func_data['function_body'] else 'No body available'}

CRITICAL CONTEXT FOR '{func_data['name']}':
{"- This is the MAIN function that users will call directly" if function_type == 'main' else ""}
{"- This is a HELPER function that provides utility calculations" if function_type == 'helper' else ""}

Provide a JSON response with:
{{
    "name": "{func_data['name']}",
    "function_type": "{function_type}",
    "description": "Clear, comprehensive description of what this function does",
    "parameters": {{
        "required": [
            {{
                "name": "exact_param_name",
                "type": "double|string|struct|char|cell",
                "units": "seconds|Hz|Hz/m|radians|meters|none|1/m",
                "description": "What this parameter controls",
                "example": "pi/2 or 'x' or mr.opts()"
            }}
        ],
        "optional": [
            {{
                "name": "exact_param_name",
                "type": "double|string|struct|char|cell",
                "units": "seconds|Hz|Hz/m|radians|meters|none|1/m",
                "default": "exact_default_value",
                "description": "What this parameter controls",
                "valid_values": "any constraints",
                "example": "0.004 or 'excitation'"
            }}
        ]
    }},
    "returns": [
        {{
            "name": "return_variable_name",
            "type": "struct|double|cell",
            "description": "What this returns"
        }}
    ],
    "usage_examples": [
        "Example function call with typical parameters"
    ],
    "related_functions": [
        "Other functions commonly used with this one"
    ]
}}

CRITICAL INSTRUCTIONS:
1. **PRESERVE EXACT PARAMETER NAMES**: The parameter names in EXTRACTED PARAMETERS are from the function signature. DO NOT change them!
   - If a required parameter is named 'flip' in the extracted parameters, use 'flip' NOT 'flipAngle'
   - If a required parameter is named 'num' in the extracted parameters, use 'num' NOT 'numSamples'
   - The extracted names are the TRUTH - preserve them exactly as given
2. You can enhance descriptions, types, units, examples, etc., but NEVER change the parameter names

SPECIFIC RULES FOR PULSEQ FUNCTIONS:
1. If this is 'makeTrapezoid': 'channel' must be first required parameter (type: char, values: 'x', 'y', or 'z')
2. If this is 'opts': Only system parameters like maxGrad, maxSlew, gradRasterTime, etc. No 'maxRF' in MATLAB version
3. If this is 'calcShortestParamsForArea': This calculates gradient timing parameters for a trapezoid gradient
4. Gradients use Hz/m (NOT T/m or mT/m)
5. Time uses seconds (NOT milliseconds or microseconds)
6. Angles use radians in code (even if degrees in comments)
7. Area units are typically 1/m for gradient areas
8. If this is 'sinc': It's a helper that implements the sinc function if not available

IMPORTANT: Return ONLY valid JSON, no extra text or markdown."""
        
        try:
            response = self.model.generate_content(prompt)
            
            # Extract JSON from response
            json_str = self._extract_json(response.text)
            
            if json_str:
                try:
                    enhanced = json.loads(json_str)
                except json.JSONDecodeError as e:
                    print(f"Warning: Invalid JSON for {func_data['name']}: {e}")
                    return self._create_fallback_response(func_data, function_type)
            else:
                print(f"Warning: Could not extract JSON for {func_data['name']}")
                return self._create_fallback_response(func_data, function_type)
            
            # Merge with original data
            enhanced['signature'] = func_data['signature']
            enhanced['parent_file'] = func_data['parent_file']
            enhanced['visibility'] = func_data['visibility']
            enhanced['line_number'] = func_data['line_number']
            # Preserve 'class' function_type if already set, otherwise use the passed in type
            if func_data.get('function_type') == 'class':
                enhanced['function_type'] = 'class'
            else:
                enhanced['function_type'] = function_type
            # PRESERVE the nargin flag!
            enhanced['uses_nargin_pattern'] = func_data.get('uses_nargin_pattern', False)
            # PRESERVE the new class-related fields!
            enhanced['namespace'] = func_data.get('namespace')
            enhanced['class_name'] = func_data.get('class_name')
            enhanced['is_class_method'] = func_data.get('is_class_method', False)
            enhanced['is_constructor'] = func_data.get('is_constructor', False)
            enhanced['instance_variable'] = func_data.get('instance_variable')
            enhanced['calling_pattern'] = func_data.get('calling_pattern')
            # Preserve class_metadata for class entries
            if func_data.get('class_metadata'):
                enhanced['class_metadata'] = func_data.get('class_metadata')
            
            return enhanced
            
        except Exception as e:
            print(f"Error enhancing {func_data['name']}: {e}")
            return self._create_fallback_response(func_data, function_type)
    
    def _minimal_enhancement(self, func_data: Dict) -> Dict:
        """Minimal enhancement for internal functions"""
        
        params_required = []
        params_optional = []
        
        for param in func_data.get('parameters', {}).get('required', []):
            params_required.append({
                'name': param['name'],
                'type': 'double',
                'description': f"Parameter {param['name']}",
                'units': 'none'
            })
        
        for param in func_data.get('parameters', {}).get('optional', []):
            params_optional.append({
                'name': param['name'],
                'type': 'double',
                'description': f"Parameter {param['name']}",
                'units': 'none',
                'default': param.get('default', 'N/A')
            })
        
        result = {
            'name': func_data['name'],
            'function_type': func_data.get('function_type', 'internal'),  # Preserve original type
            'signature': func_data['signature'],
            'parent_file': func_data['parent_file'],
            'visibility': func_data['visibility'],
            'line_number': func_data['line_number'],
            'uses_nargin_pattern': func_data.get('uses_nargin_pattern', False),  # PRESERVE the flag
            'description': func_data.get('help_text', '').split('\n')[0] if func_data.get('help_text') else 'Internal function',
            'parameters': {
                'required': params_required,
                'optional': params_optional
            },
            'returns': func_data.get('returns', []),
            # PRESERVE the new class-related fields!
            'namespace': func_data.get('namespace'),
            'class_name': func_data.get('class_name'),
            'is_class_method': func_data.get('is_class_method', False),
            'is_constructor': func_data.get('is_constructor', False),
            'instance_variable': func_data.get('instance_variable'),
            'calling_pattern': func_data.get('calling_pattern')
        }
        
        # Preserve class_metadata if present
        if func_data.get('class_metadata'):
            result['class_metadata'] = func_data.get('class_metadata')
        
        return result
    
    def _extract_json(self, text: str) -> Optional[str]:
        """Extract JSON from LLM response"""
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
    
    def _create_fallback_response(self, func_data: Dict, function_type: str) -> Dict:
        """Create a fallback response using parsed data"""
        
        # Convert parsed parameters to proper format
        params_required = []
        params_optional = []
        
        for param in func_data.get('parameters', {}).get('required', []):
            params_required.append({
                'name': param['name'],
                'type': 'double',
                'description': f"Parameter {param['name']}",
                'units': 'none'
            })
        
        for param in func_data.get('parameters', {}).get('optional', []):
            params_optional.append({
                'name': param['name'],
                'type': 'double',
                'description': f"Parameter {param['name']}",
                'units': 'none',
                'default': param.get('default', 'N/A')
            })
        
        result = {
            'name': func_data['name'],
            'function_type': func_data.get('function_type', function_type),  # Preserve original type if set
            'signature': func_data['signature'],
            'parent_file': func_data['parent_file'],
            'visibility': func_data['visibility'],
            'line_number': func_data['line_number'],
            'uses_nargin_pattern': func_data.get('uses_nargin_pattern', False),  # PRESERVE the flag
            'description': func_data.get('help_text', '').split('\n')[0] if func_data.get('help_text') else f'{function_type.capitalize()} function',
            'parameters': {
                'required': params_required,
                'optional': params_optional
            },
            'returns': func_data.get('returns', []),
            'usage_examples': [],
            'related_functions': [],
            # PRESERVE the new class-related fields!
            'namespace': func_data.get('namespace'),
            'class_name': func_data.get('class_name'),
            'is_class_method': func_data.get('is_class_method', False),
            'is_constructor': func_data.get('is_constructor', False),
            'instance_variable': func_data.get('instance_variable'),
            'calling_pattern': func_data.get('calling_pattern')
        }
        
        # Preserve class_metadata if present
        if func_data.get('class_metadata'):
            result['class_metadata'] = func_data.get('class_metadata')
        
        return result