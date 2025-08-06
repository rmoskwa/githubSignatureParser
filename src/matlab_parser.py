import re
import os
from typing import Dict, List, Optional, Tuple
from pathlib import Path

class MatlabFunctionParser:
    def __init__(self, pulseq_path: str = "/mnt/c/Users/Robert Moskwa/Documents/CodingWork/pulseqScratch/pulseq"):
        self.pulseq_path = Path(pulseq_path)
        self.matlab_path = self.pulseq_path / "matlab" / "+mr"
        
    def find_function_file(self, function_name: str) -> Optional[Path]:
        """Find the MATLAB file containing the specified function"""
        # Check in main +mr directory
        potential_file = self.matlab_path / f"{function_name}.m"
        if potential_file.exists():
            return potential_file
            
        # Check in @Sequence directory
        seq_file = self.matlab_path / "@Sequence" / f"{function_name}.m"
        if seq_file.exists():
            return seq_file
            
        # Check in subdirectories
        for subdir in self.matlab_path.iterdir():
            if subdir.is_dir():
                potential_file = subdir / f"{function_name}.m"
                if potential_file.exists():
                    return potential_file
                    
        return None
        
    def parse_file(self, file_path: Path) -> Dict:
        """Extract function signature, help text, and code body"""
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
        result = {
            'file_path': str(file_path),
            'signature': None,
            'help_text': None,
            'code_body': None,
            'input_parser_params': [],
            'varargin_params': [],
            'switch_params': []
        }
        
        # Extract function signature
        func_pattern = r'^\s*function\s+(\[.*?\]\s*=\s*)?(\w+)\s*\((.*?)\)'
        func_match = re.search(func_pattern, content, re.MULTILINE)
        
        if func_match:
            full_sig = func_match.group(0).strip()
            result['signature'] = full_sig
            result['function_name'] = func_match.group(2)
            result['parameters_str'] = func_match.group(3)
            
            # Extract help text (comments immediately after function declaration)
            help_start = func_match.end()
            help_lines = []
            lines = content[help_start:].split('\n')
            
            for line in lines:
                line = line.strip()
                if line.startswith('%'):
                    help_lines.append(line[1:].strip())
                elif line and not line.startswith('%'):
                    break
                    
            result['help_text'] = '\n'.join(help_lines)
            
            # Extract code body
            result['code_body'] = content[func_match.end():]
            
            # Extract inputParser parameters
            result['input_parser_params'] = self.extract_inputparser_params(content)
            
            # Extract varargin processing
            result['varargin_params'] = self.extract_varargin_params(content)
            
            # Extract switch/case parameters
            result['switch_params'] = self.extract_switch_params(content)
            
        return result
        
    def extract_inputparser_params(self, code: str) -> List[Dict]:
        """Extract parameters from inputParser patterns"""
        params = []
        
        # Pattern for addRequired
        required_pattern = r'p\.addRequired\s*\(\s*[\'"](\w+)[\'"](?:\s*,\s*([^)]+))?\)'
        for match in re.finditer(required_pattern, code):
            params.append({
                'name': match.group(1),
                'type': 'required',
                'validator': match.group(2) if match.group(2) else None
            })
            
        # Pattern for addOptional
        optional_pattern = r'p\.addOptional\s*\(\s*[\'"](\w+)[\'"](?:\s*,\s*([^,)]+))?(?:\s*,\s*([^)]+))?\)'
        for match in re.finditer(optional_pattern, code):
            params.append({
                'name': match.group(1),
                'type': 'optional',
                'default': match.group(2) if match.group(2) else None,
                'validator': match.group(3) if match.group(3) else None
            })
            
        # Pattern for addParameter (name-value pairs)
        param_pattern = r'p\.add(?:Parameter|ParamValue)\s*\(\s*[\'"](\w+)[\'"](?:\s*,\s*([^,)]+))?(?:\s*,\s*([^)]+))?\)'
        for match in re.finditer(param_pattern, code):
            param_name = match.group(1)
            # Skip if already added as required or optional
            if not any(p['name'] == param_name for p in params):
                params.append({
                    'name': param_name,
                    'type': 'parameter',
                    'default': match.group(2) if match.group(2) else None,
                    'validator': match.group(3) if match.group(3) else None
                })
                
        return params
        
    def extract_varargin_params(self, code: str) -> List[Dict]:
        """Extract parameters from varargin processing patterns"""
        params = []
        
        # Look for patterns like: varargin{i} == 'Duration'
        varargin_pattern = r'(?:strcmp\s*\()?varargin\{?\w*\}?\s*(?:==|,)\s*[\'"](\w+)[\'"]'
        
        for match in re.finditer(varargin_pattern, code):
            param_name = match.group(1)
            # Look for the value assignment nearby
            context_start = max(0, match.start() - 200)
            context_end = min(len(code), match.end() + 200)
            context = code[context_start:context_end]
            
            # Try to find default values or descriptions
            default_pattern = rf'{param_name}\s*=\s*([^;]+);'
            default_match = re.search(default_pattern, context)
            
            params.append({
                'name': param_name,
                'type': 'varargin',
                'default': default_match.group(1).strip() if default_match else None
            })
            
        # Remove duplicates
        seen = set()
        unique_params = []
        for param in params:
            if param['name'] not in seen:
                seen.add(param['name'])
                unique_params.append(param)
                
        return unique_params
        
    def extract_switch_params(self, code: str) -> List[Dict]:
        """Extract parameters from switch/case varargin patterns"""
        params = []
        
        # Look for switch statements on varargin
        switch_pattern = r'switch\s+(?:lower\s*\()?\s*varargin\{(\w+)\}'
        switch_matches = list(re.finditer(switch_pattern, code))
        
        for switch_match in switch_matches:
            # Find the corresponding case statements
            switch_start = switch_match.start()
            # Find the end of this switch block
            end_pattern = r'\bend\b'
            end_matches = list(re.finditer(end_pattern, code[switch_start:]))
            
            if end_matches:
                switch_end = switch_start + end_matches[0].end()
                switch_block = code[switch_start:switch_end]
                
                # Extract case statements
                case_pattern = r'case\s+[\'"](\w+)[\'"]'
                for case_match in re.finditer(case_pattern, switch_block):
                    param_name = case_match.group(1)
                    
                    # Try to find what happens with this parameter
                    case_start = case_match.end()
                    next_case = re.search(r'\bcase\b', switch_block[case_start:])
                    case_end = case_start + next_case.start() if next_case else len(switch_block)
                    case_body = switch_block[case_start:case_end]
                    
                    # Look for value assignment
                    value_pattern = rf'varargin\{{[\w+\s*\+\s*]*\d+\}}'
                    value_match = re.search(value_pattern, case_body)
                    
                    params.append({
                        'name': param_name,
                        'type': 'switch_case',
                        'expects_value': bool(value_match)
                    })
                    
        return params
        
    def get_function_summary(self, parsed_data: Dict) -> Dict:
        """Generate a summary of the parsed function"""
        summary = {
            'name': parsed_data.get('function_name', 'unknown'),
            'signature': parsed_data.get('signature', ''),
            'description': parsed_data.get('help_text', '').split('\n')[0] if parsed_data.get('help_text') else '',
            'parameter_count': {
                'input_parser': len(parsed_data.get('input_parser_params', [])),
                'varargin': len(parsed_data.get('varargin_params', [])),
                'switch_case': len(parsed_data.get('switch_params', []))
            },
            'all_parameters': self._merge_parameters(parsed_data)
        }
        return summary
        
    def _merge_parameters(self, parsed_data: Dict) -> List[str]:
        """Merge all found parameters into a unique list"""
        all_params = set()
        
        for param in parsed_data.get('input_parser_params', []):
            all_params.add(param['name'])
            
        for param in parsed_data.get('varargin_params', []):
            all_params.add(param['name'])
            
        for param in parsed_data.get('switch_params', []):
            all_params.add(param['name'])
            
        return sorted(list(all_params))