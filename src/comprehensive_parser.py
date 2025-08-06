import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import logging

class ComprehensiveMatlabParser:
    """
    Extracts ALL functions from MATLAB files with proper categorization
    Now includes nargin-based optional parameter detection
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(level=logging.INFO)
    
    def detect_namespace_from_path(self, file_path: str) -> Optional[str]:
        """
        Extract MATLAB namespace from file path.
        
        Examples:
        - "C:/pulseq/matlab/+mr/makeTrapezoid.m" -> "mr"
        - "C:/pulseq/matlab/+mr/+aux/+quat/multiply.m" -> "mr.aux.quat"
        """
        path_parts = file_path.replace('\\', '/').split('/')
        namespace_parts = []
        
        for part in path_parts:
            if part.startswith('+'):
                # It's a package folder - remove the +
                namespace_parts.append(part[1:])
            elif part.startswith('@'):
                # It's a class folder - stop here as classes are handled separately
                break
        
        if namespace_parts:
            return '.'.join(namespace_parts)
        return None
    
    def detect_class_info_from_path(self, file_path: str) -> Dict[str, Optional[str]]:
        """
        Detect if this is a class method and extract class information.
        
        Returns:
        {
            'class_name': str or None,
            'is_class_method': bool,
            'instance_variable': str or None
        }
        """
        path_parts = file_path.replace('\\', '/').split('/')
        
        for i, part in enumerate(path_parts):
            if part.startswith('@'):
                class_name = part[1:]  # Remove @
                
                # Check if this is the class constructor file
                filename = Path(file_path).stem
                if filename == class_name:
                    # This is the constructor
                    return {
                        'class_name': class_name,
                        'is_class_method': False,  # Constructor is not an instance method
                        'is_constructor': True,
                        'instance_variable': class_name.lower()[:3]  # e.g., 'seq' for Sequence
                    }
                else:
                    # This is a class method
                    return {
                        'class_name': class_name,
                        'is_class_method': True,
                        'is_constructor': False,
                        'instance_variable': class_name.lower()[:3]  # e.g., 'seq' for Sequence
                    }
        
        return {
            'class_name': None,
            'is_class_method': False,
            'is_constructor': False,
            'instance_variable': None
        }
    
    def detect_classdef(self, content: str) -> Optional[Dict[str, Any]]:
        """
        Detect if this is a classdef file and extract class information.
        
        Returns:
        {
            'is_classdef': bool,
            'class_name': str,
            'parent_class': str or None,
            'properties': {...},
            'methods_blocks': [...],  # List of (start_pos, end_pos) for methods blocks
            'classdef_end': int  # Position where classdef ends
        }
        """
        import re
        
        # Check for classdef statement
        classdef_pattern = r'^\s*classdef\s+(?:\([^)]+\)\s+)?(\w+)(?:\s*<\s*(\w+))?'
        classdef_match = re.search(classdef_pattern, content, re.MULTILINE)
        
        if not classdef_match:
            return None
        
        class_name = classdef_match.group(1)
        parent_class = classdef_match.group(2) if classdef_match.group(2) else None
        
        # Find all methods blocks
        methods_blocks = []
        methods_pattern = r'^\s*methods\b.*?$'
        end_pattern = r'^\s*end\b'
        
        # Track nested blocks to find correct 'end' statements
        lines = content.split('\n')
        in_methods = False
        methods_start = None
        block_depth = 0
        classdef_end_line = None
        
        # Track all block depths
        main_blocks = 0  # Count of main blocks (classdef, methods, properties)
        
        for i, line in enumerate(lines):
            # Skip comment-only lines
            stripped = line.strip()
            if stripped.startswith('%') or not stripped:
                continue
            
            # Check for main block starts
            if re.match(r'^\s*classdef\b', line):
                main_blocks = 1  # Start tracking from classdef
            elif re.match(r'^\s*(properties|methods|events|enumeration)\b', line):
                if main_blocks > 0:
                    main_blocks += 1
                    
                    # Check for methods block specifically
                    if re.match(methods_pattern, line):
                        if not in_methods:
                            in_methods = True
                            methods_start = i
                            block_depth = 1
            elif in_methods:
                # Track nested blocks within methods
                if re.match(r'^\s*(function|if|for|while|switch|try|parfor)\b', line):
                    block_depth += 1
                elif re.match(end_pattern, line):
                    block_depth -= 1
                    if block_depth == 0:
                        # End of methods block
                        methods_blocks.append((methods_start, i))
                        in_methods = False
                        main_blocks -= 1
            elif re.match(end_pattern, line):
                # This could be ending a main block
                if main_blocks > 0:
                    main_blocks -= 1
                    if main_blocks == 0:
                        # This is the end of the classdef
                        classdef_end_line = i
                        break
        
        # Extract properties
        properties = self._extract_class_properties(content)
        
        return {
            'is_classdef': True,
            'class_name': class_name,
            'parent_class': parent_class,
            'properties': properties,
            'methods_blocks': methods_blocks,
            'classdef_end_line': classdef_end_line
        }
    
    def _extract_class_properties(self, content: str) -> Dict:
        """Extract properties from a classdef file."""
        properties = {'public': {}, 'private': {}, 'protected': {}}
        
        # Find properties blocks
        properties_pattern = r'^\s*properties\s*(?:\(([^)]+)\))?\s*$'
        prop_pattern = r'^\s*(\w+)(?:\s*=\s*([^;%]+))?.*?(?:%\s*(.*))?$'
        
        lines = content.split('\n')
        in_properties = False
        current_access = 'public'
        
        for i, line in enumerate(lines):
            # Check for properties block
            props_match = re.match(properties_pattern, line)
            if props_match:
                in_properties = True
                # Determine access level
                if props_match.group(1):
                    access_str = props_match.group(1).lower()
                    if 'private' in access_str:
                        current_access = 'private'
                    elif 'protected' in access_str:
                        current_access = 'protected'
                    else:
                        current_access = 'public'
                else:
                    current_access = 'public'
                continue
            
            if in_properties:
                if re.match(r'^\s*end\b', line):
                    in_properties = False
                    continue
                
                # Extract property
                prop_match = re.match(prop_pattern, line)
                if prop_match and prop_match.group(1):
                    prop_name = prop_match.group(1)
                    prop_default = prop_match.group(2).strip() if prop_match.group(2) else None
                    prop_comment = prop_match.group(3).strip() if prop_match.group(3) else ''
                    
                    properties[current_access][prop_name] = {
                        'default': prop_default,
                        'description': prop_comment
                    }
        
        return properties
    
    def _parse_classdef_file(self, file_path: Path, content: str, namespace: Optional[str], 
                           class_info: Dict, classdef_info: Dict) -> Dict:
        """Parse a MATLAB classdef file."""
        import re
        
        lines = content.split('\n')
        result = {
            'file_info': {
                'path': str(file_path),
                'name': file_path.name,
                'expected_main': file_path.stem,
                'namespace': namespace,
                'class_info': class_info,
                'is_classdef': True
            },
            'main_function': None,  # Will be the class itself
            'helper_functions': [],  # Methods within the class
            'internal_functions': []  # Functions after classdef end
        }
        
        # Create the class entry
        class_entry = {
            'name': classdef_info['class_name'],
            'function_type': 'class',
            'signature': f"classdef {classdef_info['class_name']}" + 
                        (f" < {classdef_info['parent_class']}" if classdef_info['parent_class'] else ""),
            'parent_file': file_path.name,
            'help_text': self._extract_classdef_help(content),
            'function_body': content[:5000],  # First 5000 chars of the class file
            'parameters': {'required': [], 'optional': []},  # Will be filled from constructor
            'returns': [],
            'visibility': 'public',
            'line_number': 1,
            'uses_nargin_pattern': False,
            'namespace': namespace,
            'class_name': classdef_info['class_name'],
            'is_class_method': False,
            'is_constructor': False,  # The class itself is not the constructor
            'instance_variable': classdef_info['class_name'].lower()[:3],
            'calling_pattern': f"{classdef_info['class_name'].lower()[:3]} = {namespace}.{classdef_info['class_name']}(...)" if namespace else f"{classdef_info['class_name'].lower()[:3]} = {classdef_info['class_name']}(...)",
            'class_metadata': {
                'properties': classdef_info['properties'],
                'parent_class': classdef_info['parent_class'],
                'methods': []  # Will be populated
            }
        }
        
        # Find functions within methods blocks (these are class methods)
        class_methods = []
        for start_line, end_line in classdef_info['methods_blocks']:
            methods_content = '\n'.join(lines[start_line:end_line+1])
            methods_functions = self._find_all_functions(methods_content, allow_indented=True)
            
            # Filter out nested functions by checking indentation levels
            # Class methods should be at the first indentation level within the methods block
            top_level_functions = []
            for func_def in methods_functions:
                # Get the line where this function is defined
                func_line = methods_content.split('\n')[func_def['line_num']]
                # Count leading spaces/tabs
                indent_level = len(func_line) - len(func_line.lstrip())
                
                # Check if this is likely a nested function
                # Nested functions typically have more indentation than class methods
                # Class methods in a methods block usually have 8-12 spaces of indentation
                # Nested functions would have 16+ spaces
                is_nested = False
                
                # More robust check: see if this function is inside another function
                # by checking if there's a function definition before it that hasn't ended
                lines_before = methods_content[:func_def['start_pos']].split('\n')
                function_depth = 0
                for line in lines_before:
                    if re.match(r'^\s*function\s+', line):
                        function_depth += 1
                    # Count 'end' statements that close functions
                    elif re.match(r'^\s*end\s*(?:%.*)?$', line):
                        # This could be closing a function, if/for block, etc.
                        # Simple heuristic: assume it closes a function if we're inside one
                        if function_depth > 0:
                            function_depth -= 1
                
                # If function_depth > 0, this function is nested inside another
                if function_depth > 0:
                    is_nested = True
                    
                if not is_nested:
                    top_level_functions.append(func_def)
            
            for func_def in top_level_functions:
                    
                # Adjust line numbers relative to file start
                func_def['line_num'] += start_line
                func_def['start_pos'] += sum(len(line) + 1 for line in lines[:start_line])
                
                func_data = self._extract_function_details(
                    content, func_def, classdef_info['class_name'], file_path.name, namespace, class_info
                )
                
                # Check if this is the constructor
                if func_data['name'] == classdef_info['class_name']:
                    # This is the constructor
                    func_data['is_constructor'] = True
                    func_data['is_class_method'] = False
                    func_data['function_type'] = 'constructor'
                    # Use constructor parameters for the class entry
                    class_entry['parameters'] = func_data.get('parameters', {'required': [], 'optional': []})
                else:
                    # Regular class method
                    func_data['is_class_method'] = True
                    func_data['class_name'] = classdef_info['class_name']
                    func_data['instance_variable'] = classdef_info['class_name'].lower()[:3]
                    func_data['calling_pattern'] = f"{func_data['instance_variable']}.{func_data['name']}(...)"
                    func_data['function_type'] = 'method'
                
                class_methods.append(func_data)
                class_entry['class_metadata']['methods'].append(func_data['name'])
        
        # Find functions after classdef end (these are internal helper functions)
        helper_functions = []
        if classdef_info['classdef_end_line'] is not None:
            after_class_content = '\n'.join(lines[classdef_info['classdef_end_line']+1:])
            helper_funcs = self._find_all_functions(after_class_content)
            
            for func_def in helper_funcs:
                # Adjust positions
                func_def['line_num'] += classdef_info['classdef_end_line'] + 1
                func_def['start_pos'] += sum(len(line) + 1 for line in lines[:classdef_info['classdef_end_line']+1])
                
                func_data = self._extract_function_details(
                    content, func_def, None, file_path.name, namespace, 
                    {'class_name': None, 'is_class_method': False, 'is_constructor': False, 'instance_variable': None}
                )
                
                # These are internal helper functions, NOT class methods
                func_data['function_type'] = 'internal'
                func_data['class_name'] = None
                func_data['is_class_method'] = False
                func_data['calling_pattern'] = None  # Not meant to be called directly
                
                helper_functions.append(func_data)
        
        # Organize results
        result['main_function'] = class_entry
        result['helper_functions'] = class_methods  # Class methods
        result['internal_functions'] = helper_functions  # Functions outside class
        
        return result
    
    def _extract_classdef_help(self, content: str) -> str:
        """Extract help text from classdef file."""
        lines = content.split('\n')
        help_lines = []
        
        # Look for comments immediately after classdef line
        in_help = False
        for i, line in enumerate(lines):
            if i == 0:
                continue
            if line.strip().startswith('%'):
                in_help = True
                help_lines.append(line.strip()[1:].strip())
            elif in_help and not line.strip().startswith('%'):
                break
        
        return '\n'.join(help_lines)
    
    def generate_calling_pattern(self, function_name: str, namespace: Optional[str], class_info: Dict) -> str:
        """
        Generate the correct calling pattern for a function.
        
        Examples:
        - Regular function: "mr.makeTrapezoid(...)"
        - Class method: "seq.write(...)"
        - Constructor: "seq = mr.Sequence(...)"
        - Nested namespace: "mr.aux.quat.multiply(...)"
        """
        if class_info['is_constructor']:
            # Constructor pattern: seq = mr.Sequence(...)
            instance_var = class_info['instance_variable'] or 'obj'
            if namespace:
                return f"{instance_var} = {namespace}.{class_info['class_name']}(...)"
            else:
                return f"{instance_var} = {class_info['class_name']}(...)"
        
        elif class_info['is_class_method']:
            # Class method pattern: seq.methodName(...)
            instance_var = class_info['instance_variable'] or 'obj'
            return f"{instance_var}.{function_name}(...)"
        
        else:
            # Regular function pattern: mr.functionName(...)
            if namespace:
                return f"{namespace}.{function_name}(...)"
            else:
                return f"{function_name}(...)"
        
    def parse_file_comprehensive(self, file_path: str) -> Dict:
        """
        Parse a MATLAB file and extract ALL functions with categorization
        
        Returns:
            {
                'file_info': {...},
                'main_function': {...},
                'helper_functions': [...],
                'internal_functions': [...]
            }
        """
        file_path = Path(file_path)
        expected_main_name = file_path.stem  # e.g., 'makeTrapezoid'
        
        # Detect namespace and class information from path
        namespace = self.detect_namespace_from_path(str(file_path))
        class_info = self.detect_class_info_from_path(str(file_path))
        
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Check if this is a classdef file
        classdef_info = self.detect_classdef(content)
        
        if classdef_info:
            # This is a class definition file
            return self._parse_classdef_file(file_path, content, namespace, class_info, classdef_info)
        
        # Regular function file - Find all function definitions
        functions = self._find_all_functions(content)
        
        result = {
            'file_info': {
                'path': str(file_path),
                'name': file_path.name,
                'expected_main': expected_main_name,
                'namespace': namespace,
                'class_info': class_info
            },
            'main_function': None,
            'helper_functions': [],
            'internal_functions': []
        }
        
        for func_def in functions:
            func_data = self._extract_function_details(
                content, 
                func_def, 
                expected_main_name,
                file_path.name,
                namespace,
                class_info
            )
            
            # Categorize function
            if func_data['name'] == expected_main_name:
                result['main_function'] = func_data
                func_data['function_type'] = 'main'
            elif func_data['visibility'] == 'private':
                result['internal_functions'].append(func_data)
                func_data['function_type'] = 'internal'
            else:
                result['helper_functions'].append(func_data)
                func_data['function_type'] = 'helper'
        
        # Validate we found the main function
        if not result['main_function']:
            self.logger.warning(f"Could not find main function '{expected_main_name}' in {file_path}")
            # Try to use first function as main
            if functions:
                result['main_function'] = self._extract_function_details(
                    content, functions[0], expected_main_name, file_path.name, namespace, class_info
                )
                result['main_function']['function_type'] = 'main'
                result['main_function']['extraction_warning'] = 'Used first function as main'
        
        return result
    
    def _find_all_functions(self, content: str, allow_indented: bool = False) -> List[Dict]:
        """Find all function definitions in the content"""
        functions = []
        
        # Pattern to match function definitions
        # Captures: output args, function name, input args
        if allow_indented:
            pattern = r'^\s*function\s+(?:(\[[^\]]+\]|\w+)\s*=\s*)?(\w+)\s*\(([^)]*)\)'
        else:
            pattern = r'^function\s+(?:(\[[^\]]+\]|\w+)\s*=\s*)?(\w+)\s*\(([^)]*)\)'
        
        for match in re.finditer(pattern, content, re.MULTILINE):
            functions.append({
                'match': match,
                'name': match.group(2),
                'full_signature': match.group(0),
                'outputs': match.group(1),
                'inputs': match.group(3),
                'start_pos': match.start(),
                'line_num': content[:match.start()].count('\n') + 1
            })
        
        return functions
    
    def _extract_function_details(self, content: str, func_def: Dict, 
                                 expected_main: str, parent_file: str,
                                 namespace: Optional[str], class_info: Dict) -> Dict:
        """Extract complete details for a single function"""
        
        # Find the end of this function (start of next function or end of file)
        next_func_pattern = r'^function\s+'
        remaining_content = content[func_def['start_pos']:]
        next_match = re.search(next_func_pattern, remaining_content[len(func_def['full_signature']):], re.MULTILINE)
        
        if next_match:
            func_end_pos = func_def['start_pos'] + len(func_def['full_signature']) + next_match.start()
        else:
            func_end_pos = len(content)
        
        function_body = content[func_def['start_pos']:func_end_pos]
        
        # Extract help text
        help_text = self._extract_help_text(function_body)
        
        # Extract inputParser block
        parser_block = self._extract_inputparser_block(function_body)
        
        # Parse parameters with FIXED logic including nargin detection
        parameters = self._parse_parameters(
            func_def['full_signature'],
            func_def['inputs'],
            parser_block,
            function_body
        )
        
        # Parse return values
        returns = self._parse_returns(func_def['outputs'], help_text)
        
        # Determine visibility
        visibility = self._determine_visibility(func_def['name'], help_text, expected_main)
        
        # Check if nargin pattern was used for optional parameters
        uses_nargin_pattern = False
        if parameters.get('nargin_detection') is not None:
            uses_nargin_pattern = True
        # Also check if any optional parameter was detected via nargin
        for opt_param in parameters.get('optional', []):
            if opt_param.get('source') == 'nargin_check':
                uses_nargin_pattern = True
                break
        
        # Generate calling pattern
        calling_pattern = self.generate_calling_pattern(func_def['name'], namespace, class_info)
        
        return {
            'name': func_def['name'],
            'signature': func_def['full_signature'],
            'parent_file': parent_file,
            'help_text': help_text,
            'function_body': function_body[:5000],  # First 5000 chars for LLM
            'parameters': parameters,
            'returns': returns,
            'visibility': visibility,
            'line_number': func_def['line_num'],
            'uses_nargin_pattern': uses_nargin_pattern,
            # New fields for database schema
            'namespace': namespace,
            'class_name': class_info.get('class_name'),
            'is_class_method': class_info.get('is_class_method', False),
            'is_constructor': class_info.get('is_constructor', False),
            'instance_variable': class_info.get('instance_variable'),
            'calling_pattern': calling_pattern
        }
    
    def _extract_help_text(self, function_body: str) -> str:
        """Extract the help comment block after function definition"""
        lines = function_body.split('\n')
        help_lines = []
        in_help = False
        
        for line in lines[1:]:  # Skip function definition line
            stripped = line.strip()
            if stripped.startswith('%'):
                in_help = True
                help_lines.append(stripped[1:].strip())
            elif in_help and not stripped.startswith('%'):
                break  # End of help block
        
        return '\n'.join(help_lines)
    
    def _extract_inputparser_block(self, function_body: str) -> str:
        """Extract the inputParser block from function body"""
        # Look for parser initialization
        parser_start = re.search(r'p(?:arser)?\s*=\s*inputParser', function_body, re.IGNORECASE)
        if not parser_start:
            return ""
        
        # Find the parse() call
        parse_end = re.search(r'parse\s*\(\s*p(?:arser)?[^)]*\)', function_body[parser_start.start():], re.IGNORECASE)
        if not parse_end:
            # Sometimes parse is called later, look for last addParameter
            last_add = None
            for match in re.finditer(r'p(?:arser)?\.add(?:Required|Optional|Parameter|ParamValue)[^;]+;', 
                                    function_body[parser_start.start():], re.IGNORECASE):
                last_add = match
            if last_add:
                return function_body[parser_start.start():parser_start.start() + last_add.end()]
            return ""
        
        return function_body[parser_start.start():parser_start.start() + parse_end.end()]
    
    def _detect_nargin_pattern(self, function_body: str, total_params: int) -> Optional[int]:
        """
        Detect nargin checks to determine how many parameters are required.
        Returns the number of required parameters, or None if no pattern found.
        """
        # Remove comments to avoid false positives
        content_no_comments = re.sub(r'%.*$', '', function_body, flags=re.MULTILINE)
        
        # Pattern 1: if nargin < N (parameters from N onwards are optional)
        pattern1 = r'if\s+nargin\s*<\s*(\d+)'
        matches1 = re.findall(pattern1, content_no_comments)
        
        # Pattern 2: if nargin > N (parameters after N are optional, so first N are required)
        pattern2 = r'if\s+nargin\s*>\s*(\d+)'
        matches2 = re.findall(pattern2, content_no_comments)
        
        # Pattern 3: nargin >= N (parameters from N onwards are optional)
        pattern3 = r'if\s+nargin\s*>=\s*(\d+)'
        matches3 = re.findall(pattern3, content_no_comments)
        
        # Pattern 4: nargin <= N (up to N parameters are required)
        pattern4 = r'if\s+nargin\s*<=\s*(\d+)'
        matches4 = re.findall(pattern4, content_no_comments)
        
        # Determine minimum required parameters
        min_required = None
        
        # Process patterns to find the minimum required count
        for match in matches1:
            n = int(match)
            # if nargin < 2 means first parameter is required (index 0)
            if min_required is None or n - 1 < min_required:
                min_required = n - 1
        
        for match in matches2:
            n = int(match)
            # if nargin > 2 means first 2 are required
            if min_required is None or n < min_required:
                min_required = n
        
        for match in matches3:
            n = int(match)
            # if nargin >= 3 means first 2 are required
            if min_required is None or n - 1 < min_required:
                min_required = n - 1
        
        # Special case: if nargin < 1 is just error checking, not optional params
        if min_required == 0 and matches1 and all(int(m) == 1 for m in matches1):
            # This is just checking that at least one param was provided
            return None
        
        # Only return if we found meaningful patterns
        if min_required is not None and min_required < total_params:
            return max(0, min_required)  # Ensure non-negative
        
        return None
    
    def _parse_parameters(self, signature: str, inputs_str: str, 
                         parser_block: str, function_body: str) -> Dict:
        """
        Parse all parameters from signature, inputParser, and nargin patterns
        ENHANCED: Now detects nargin-based optional parameters
        """
        
        params = {
            'required': [],
            'optional': [],
            'inputparser_mapping': {},  # Track mapping between signature and InputParser names
            'nargin_detection': None  # Track if nargin was used for detection
        }
        
        # Step 1: Parse positional parameters from signature - THESE ARE THE TRUTH
        signature_params = []
        if inputs_str:
            input_list = [p.strip() for p in inputs_str.split(',')]
            
            for i, param in enumerate(input_list):
                if param == 'varargin':
                    break  # Everything after varargin is handled separately
                elif param and param != '~':
                    signature_params.append(param)
        
        # Step 2: Check if InputParser is used
        if parser_block:
            # InputParser takes precedence - use existing logic
            # Map InputParser names to signature names for required params
            inputparser_required = []
            
            # Extract addRequired - support both formats:
            # 1. parser.addRequired('param', ...)
            # 2. addRequired(parser, 'param', ...)
            
            # Format 1: parser.addRequired or p.addRequired
            for match in re.finditer(r"p(?:arser)?\.addRequired\s*\(\s*['\"](\w+)['\"]", parser_block, re.IGNORECASE):
                inputparser_name = match.group(1)
                inputparser_required.append(inputparser_name)
            
            # Format 2: addRequired(parser, 'param', ...)
            for match in re.finditer(r"addRequired\s*\(\s*\w+\s*,\s*['\"](\w+)['\"]", parser_block, re.IGNORECASE):
                inputparser_name = match.group(1)
                if inputparser_name not in inputparser_required:  # Avoid duplicates
                    inputparser_required.append(inputparser_name)
            
            # Build required params list
            for i, sig_param in enumerate(signature_params):
                if i < len(inputparser_required):
                    # This param is marked as required in InputParser
                    params['required'].append({
                        'name': sig_param,  # USE SIGNATURE NAME
                        'position': i,
                        'source': 'signature'
                    })
                    
                    ip_name = inputparser_required[i]
                    if ip_name != sig_param:
                        # There's a mismatch - note it but use signature name
                        params['inputparser_mapping'][sig_param] = ip_name
                        self.logger.info(f"Parameter name mismatch: signature='{sig_param}' vs InputParser='{ip_name}'")
                else:
                    # This param is not in addRequired
                    # Check if there's a nargin check indicating it's required
                    nargin_check = re.search(rf'if\s+nargin\s*<\s*{i+1}.*?error', function_body[:1000], re.IGNORECASE | re.DOTALL)
                    
                    if nargin_check:
                        # There's an error check for this parameter - it's required
                        params['required'].append({
                            'name': sig_param,
                            'position': i,
                            'source': 'signature_with_nargin_check'
                        })
                    elif 'varargin' in inputs_str and i == len(signature_params) - 1:
                        # Last param before varargin and no nargin error check - might be optional
                        pass
                    else:
                        # Default: assume required if not explicitly optional
                        params['required'].append({
                            'name': sig_param,
                            'position': i,
                            'source': 'signature'
                        })
            
            # Handle special case: InputParser has more required params than signature
            # (e.g., makeArbitraryGrad where 'waveform' is required but passed through varargin)
            if len(inputparser_required) > len(signature_params) and 'varargin' in inputs_str:
                for j in range(len(signature_params), len(inputparser_required)):
                    params['required'].append({
                        'name': inputparser_required[j],
                        'position': j,
                        'source': 'inputParser.addRequired'
                    })
            
            # Extract optional parameters - support both formats
            # Format 1: parser.addOptional
            for match in re.finditer(
                r"p(?:arser)?\.addOptional\s*\(\s*['\"](\w+)['\"]\s*,\s*([^,)]+)", 
                parser_block, re.IGNORECASE
            ):
                params['optional'].append({
                    'name': match.group(1),
                    'default': match.group(2).strip(),
                    'source': 'inputParser.addOptional'
                })
            
            # Format 2: addOptional(parser, 'param', default)
            for match in re.finditer(
                r"addOptional\s*\(\s*\w+\s*,\s*['\"](\w+)['\"]\s*,\s*([^,)]+)",
                parser_block, re.IGNORECASE
            ):
                param_name = match.group(1)
                if not any(p['name'] == param_name for p in params['optional']):
                    params['optional'].append({
                        'name': param_name,
                        'default': match.group(2).strip(),
                        'source': 'inputParser.addOptional'
                    })
            
            # Extract addParameter/addParamValue - support both formats
            # Format 1: parser.addParameter
            for match in re.finditer(
                r"p(?:arser)?\.add(?:Parameter|ParamValue)\s*\(\s*['\"](\w+)['\"]\s*,\s*([^,)]+)",
                parser_block, re.IGNORECASE
            ):
                param_name = match.group(1)
                # Avoid duplicates
                if not any(p['name'] == param_name for p in params['optional']):
                    params['optional'].append({
                        'name': param_name,
                        'default': match.group(2).strip(),
                        'source': 'inputParser.addParameter'
                    })
            
            # Format 2: addParameter(parser, 'param', default) or addParamValue(parser, 'param', default)
            for match in re.finditer(
                r"add(?:Parameter|ParamValue)\s*\(\s*\w+\s*,\s*['\"](\w+)['\"]\s*,\s*([^,)]+)",
                parser_block, re.IGNORECASE
            ):
                param_name = match.group(1)
                if not any(p['name'] == param_name for p in params['optional']):
                    params['optional'].append({
                        'name': param_name,
                        'default': match.group(2).strip(),
                        'source': 'inputParser.addParameter'
                    })
        
        # Step 3: No InputParser - check for nargin patterns
        elif len(signature_params) > 0:
            # Detect nargin-based optional parameters
            nargin_required_count = self._detect_nargin_pattern(function_body, len(signature_params))
            
            if nargin_required_count is not None:
                # Use nargin detection to classify parameters
                params['nargin_detection'] = nargin_required_count
                
                for i, param in enumerate(signature_params):
                    if i < nargin_required_count:
                        params['required'].append({
                            'name': param,
                            'position': i,
                            'source': 'signature'
                        })
                    else:
                        # Extract default value if possible
                        default_value = self._extract_default_value(function_body, param, i + 1)
                        params['optional'].append({
                            'name': param,
                            'default': default_value,
                            'source': 'nargin_check',
                            'position': i
                        })
                
                self.logger.info(f"Detected nargin pattern: {nargin_required_count} required out of {len(signature_params)}")
            else:
                # No nargin pattern found - assume all required (existing behavior)
                for i, param in enumerate(signature_params):
                    params['required'].append({
                        'name': param,
                        'position': i,
                        'source': 'signature'
                    })
        
        # Step 4: Check for direct varargin processing (if no InputParser and varargin exists)
        if not parser_block and 'varargin' in inputs_str:
            # Look for switch/case or if/else patterns for varargin
            switch_pattern = r"case\s+['\"](\w+)['\"]"
            for match in re.finditer(switch_pattern, function_body):
                param_name = match.group(1)
                if not any(p['name'] == param_name for p in params['optional']):
                    params['optional'].append({
                        'name': param_name,
                        'default': 'N/A',
                        'source': 'varargin_case'
                    })
        
        return params
    
    def _extract_default_value(self, function_body: str, param_name: str, param_position: int) -> str:
        """
        Try to extract the default value for a parameter from nargin checks
        """
        # Look for patterns like:
        # if nargin < 2
        #     param = default_value;
        # end
        
        # Remove comments
        content_no_comments = re.sub(r'%.*$', '', function_body, flags=re.MULTILINE)
        
        # Pattern for default assignment after nargin check
        pattern = rf'if\s+nargin\s*<\s*{param_position}\s*\n.*?{re.escape(param_name)}\s*=\s*([^;]+);'
        match = re.search(pattern, content_no_comments, re.IGNORECASE | re.DOTALL)
        
        if match:
            return match.group(1).strip()
        
        # Try another pattern: if nargin < N, param = value
        pattern2 = rf'if\s+nargin\s*<\s*{param_position}.*?{re.escape(param_name)}\s*=\s*([^;]+);'
        match2 = re.search(pattern2, content_no_comments, re.IGNORECASE | re.DOTALL)
        
        if match2:
            return match2.group(1).strip()
        
        return 'N/A'
    
    def _parse_returns(self, outputs_str: str, help_text: str) -> List[Dict]:
        """Parse return values from function signature"""
        if not outputs_str:
            return []
        
        returns = []
        
        # Remove brackets if present
        outputs_str = outputs_str.strip()
        if outputs_str.startswith('[') and outputs_str.endswith(']'):
            outputs_str = outputs_str[1:-1]
        
        # Split by comma
        output_names = [o.strip() for o in outputs_str.split(',') if o.strip()]
        
        for name in output_names:
            returns.append({
                'name': name,
                'description': f'Output {name}'
            })
        
        return returns
    
    def _determine_visibility(self, func_name: str, help_text: str, expected_main: str) -> str:
        """Determine function visibility"""
        if func_name == expected_main:
            return 'public'
        
        # Check if marked as private in comments
        if 'private' in help_text.lower() or 'internal' in help_text.lower():
            return 'private'
        
        # Functions starting with underscore are typically private
        if func_name.startswith('_'):
            return 'private'
        
        return 'public'
