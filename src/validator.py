import re
import os
from pathlib import Path
from typing import Dict, List, Optional, Set

class FunctionValidator:
    def __init__(self, pulseq_path: str = "/mnt/c/Users/Robert Moskwa/Documents/CodingWork/pulseqScratch/pulseq"):
        self.pulseq_path = Path(pulseq_path)
        self.demo_path = self.pulseq_path / "matlab" / "demoSeq"
        self.demo_recon_path = self.pulseq_path / "matlab" / "demoRecon"
        
    def validate_against_demos(self, function_name: str, parameters: Dict) -> List[str]:
        """Check if extracted parameters match usage in demo sequences"""
        
        issues = []
        
        # Find all demo files
        demo_files = list(self.demo_path.glob("*.m")) + list(self.demo_recon_path.glob("*.m"))
        
        # Extract parameter names from our data
        our_params = self._extract_parameter_names(parameters)
        
        # Find actual usage in demos
        actual_usage = self._find_function_usage(function_name, demo_files)
        
        if actual_usage:
            # Compare parameters
            used_params = actual_usage['parameters']
            
            # Check for parameters used in demos but not in our extraction
            missing_params = used_params - our_params
            if missing_params:
                issues.append(f"Parameters used in demos but not extracted: {', '.join(missing_params)}")
                
            # Check for hallucinated parameters (in our extraction but never used)
            if len(actual_usage['calls']) > 5:  # Only check if we have enough examples
                hallucinated = our_params - used_params
                # Filter out common system parameters that might not always be used
                hallucinated = hallucinated - {'system', 'use', 'delay'}
                if hallucinated:
                    issues.append(f"Possible hallucinated parameters: {', '.join(hallucinated)}")
                    
        return issues
        
    def _extract_parameter_names(self, parameters: Dict) -> Set[str]:
        """Extract all parameter names from our parameter data"""
        
        param_names = set()
        
        params_dict = parameters.get('parameters', parameters)
        
        if isinstance(params_dict, dict):
            for param_list in params_dict.get('required', []):
                if isinstance(param_list, dict):
                    param_names.add(param_list.get('name', ''))
                    
            for param_list in params_dict.get('optional', []):
                if isinstance(param_list, dict):
                    param_names.add(param_list.get('name', ''))
                    
        return param_names
        
    def _find_function_usage(self, function_name: str, demo_files: List[Path]) -> Optional[Dict]:
        """Find how a function is actually used in demo files"""
        
        all_calls = []
        all_parameters = set()
        
        # Pattern to match function calls
        # Handle both mr.functionName and just functionName
        patterns = [
            rf'mr\.{function_name}\s*\(',
            rf'\b{function_name}\s*\('
        ]
        
        for demo_file in demo_files:
            try:
                with open(demo_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    
                for pattern in patterns:
                    for match in re.finditer(pattern, content):
                        # Extract the full function call
                        call_text = self._extract_function_call(content, match.start())
                        if call_text:
                            all_calls.append({
                                'file': demo_file.name,
                                'call': call_text
                            })
                            
                            # Extract parameter names from this call
                            params = self._extract_parameters_from_call(call_text)
                            all_parameters.update(params)
                            
            except Exception as e:
                print(f"Error reading {demo_file}: {e}")
                
        if all_calls:
            return {
                'calls': all_calls,
                'parameters': all_parameters
            }
            
        return None
        
    def _extract_function_call(self, content: str, start_pos: int) -> Optional[str]:
        """Extract the complete function call starting from a position"""
        
        # Find the matching closing parenthesis
        paren_count = 0
        in_string = False
        string_char = None
        i = start_pos
        
        while i < len(content):
            char = content[i]
            
            if not in_string:
                if char in ['"', "'"]:
                    in_string = True
                    string_char = char
                elif char == '(':
                    paren_count += 1
                elif char == ')':
                    paren_count -= 1
                    if paren_count == 0:
                        return content[start_pos:i+1]
            else:
                if char == string_char and (i == 0 or content[i-1] != '\\'):
                    in_string = False
                    
            i += 1
            
        return None
        
    def _extract_parameters_from_call(self, call_text: str) -> Set[str]:
        """Extract parameter names from a function call"""
        
        parameters = set()
        
        # Look for name-value pairs (e.g., 'Duration', 4e-3)
        # Pattern: 'paramName' followed by comma and value
        pattern = r"['\"](\w+)['\"](?:\s*,\s*[^,\)]+)"
        
        for match in re.finditer(pattern, call_text):
            param_name = match.group(1)
            # Filter out common non-parameter strings
            if param_name not in ['excitation', 'refocusing', 'inversion', 'saturation']:
                parameters.add(param_name)
                
        return parameters
        
    def validate_parameter_values(self, function_data: Dict) -> List[str]:
        """Validate parameter values and types"""
        
        issues = []
        params = function_data.get('parameters', {})
        
        # Check for common issues
        for param_list in params.get('optional', []) + params.get('required', []):
            if isinstance(param_list, dict):
                name = param_list.get('name', '')
                units = param_list.get('units', '')
                
                # Check gradient units
                if 'grad' in name.lower() or name in ['maxGrad', 'amplitude']:
                    if units not in ['Hz/m', 'none']:
                        issues.append(f"{name}: Gradient units should be Hz/m, not {units}")
                        
                # Check time units
                if any(time_word in name.lower() for time_word in ['duration', 'time', 'delay']):
                    if units not in ['seconds', 'none']:
                        issues.append(f"{name}: Time units should be seconds, not {units}")
                        
                # Check angle units
                if 'flip' in name.lower() or 'angle' in name.lower():
                    if units not in ['radians', 'none']:
                        issues.append(f"{name}: Angle units should be radians, not {units}")
                        
                # Check for hallucinated parameters
                if name == 'timeBwChannels':
                    issues.append("'timeBwChannels' is not a real parameter - should be 'timeBwProduct'")
                    
                if name == 'maxRF' and function_data.get('name') == 'opts':
                    issues.append("'maxRF' does not exist in MATLAB version of mr.opts()")
                    
        return issues
        
    def generate_validation_report(self, function_data: Dict) -> Dict:
        """Generate a comprehensive validation report"""
        
        report = {
            'function_name': function_data.get('name', 'unknown'),
            'demo_validation': [],
            'value_validation': [],
            'warnings': [],
            'status': 'valid'
        }
        
        # Validate against demos
        demo_issues = self.validate_against_demos(
            function_data.get('name', ''),
            function_data
        )
        report['demo_validation'] = demo_issues
        
        # Validate parameter values
        value_issues = self.validate_parameter_values(function_data)
        report['value_validation'] = value_issues
        
        # Generate warnings
        if demo_issues or value_issues:
            report['status'] = 'needs_review'
            
        # Check for critical issues
        critical_keywords = ['hallucinated', 'maxRF', 'timeBwChannels']
        for issue in demo_issues + value_issues:
            if any(keyword in issue for keyword in critical_keywords):
                report['status'] = 'critical'
                break
                
        return report