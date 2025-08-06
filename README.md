# MATLAB Function Parser

A comprehensive parser for extracting and documenting MATLAB functions from any repository, with automatic parameter detection including nargin-based optional parameters. Currently this parser does NOT have a recursive option.

## Features

- **Comprehensive Function Extraction**: Parses ALL functions in MATLAB files (main, helper, and internal)
- **Accurate Parameter Detection**: 
  - Preserves exact parameter names from function signatures
  - Detects both InputParser and nargin-based optional parameters
  - Supports multiple InputParser formats (`parser.addRequired` and `addRequired(parser, ...)`)
- **LLM Enhancement**: Uses Google Gemini to enhance function documentation
- **Database Integration**: Updates Supabase database with parsed function data
- **Vector Embeddings**: Generates embeddings for semantic search
- **Flexible File Filtering**: 
  - Optional inclusion of test files
  - Customizable skip patterns
  - Intelligent detection of non-function files

## Requirements

- Python 3.10+
- Google Gemini API key
- Supabase project with appropriate schema

## Installation

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Configure environment variables in `.env`:
   ```
   GEMINI_API_KEY=your_gemini_api_key
   SUPABASE_URL=your_supabase_url
   SUPABASE_KEY=your_supabase_anon_key
   
   # Optional: Set MATLAB functions path
   MATLAB_FUNCTIONS_PATH=/path/to/matlab/functions
   ```

## Usage

### Specifying MATLAB Functions Path

The script needs to know where your MATLAB files are located. You can specify this in two ways:

1. **Environment variable** (recommended):
   ```bash
   export MATLAB_FUNCTIONS_PATH=/path/to/matlab/functions
   python process_pulseq_api.py
   ```

2. **Command line argument**:
   ```bash
   python process_pulseq_api.py --path /path/to/matlab/functions
   ```

### Process All MATLAB Functions

```bash
python process_pulseq_api.py --path /path/to/your/matlab/files
```

### Command Line Options

- `--path PATH`: Specify path to directory containing MATLAB functions (required unless set via environment variable)
- `--dry-run`: Process without updating the database
- `--verify-only`: Only verify database contents without processing
- `--include-tests`: Include files starting with "test" (by default they are skipped)
- `--skip-patterns PATTERN [PATTERN ...]`: Additional filename patterns to skip

### Examples

```bash
# Process with specific path
python process_pulseq_api.py --path ~/repos/my-matlab-project/functions

# Process all functions using environment variable
export MATLAB_FUNCTIONS_PATH=~/projects/matlab/src
python process_pulseq_api.py

# Include test files that would normally be skipped
python process_pulseq_api.py --path ./matlab --include-tests

# Skip additional patterns
python process_pulseq_api.py --path ./matlab --skip-patterns temp_ backup_

# Test without database updates
python process_pulseq_api.py --path ./matlab --dry-run

# Verify database contents
python process_pulseq_api.py --verify-only
```

## Project Structure

```
├── process_pulseq_api.py       # Main processing script
├── src/
│   ├── comprehensive_parser.py  # MATLAB function parser with nargin detection
│   ├── enhanced_llm_processor.py # LLM enhancement for documentation
│   ├── enhanced_db_manager_updated.py # Database operations
│   └── embeddings.py           # Vector embedding generation
├── output/
│   └── full_processing/        # Processed function JSON files
├── requirements.txt            # Python dependencies
└── .env                       # Environment variables (create this)
```

## Key Components

### comprehensive_parser.py
- Extracts all functions from MATLAB files
- Detects nargin patterns for optional parameters
- Preserves exact parameter names from signatures
- Categorizes functions (main, helper, internal)

### enhanced_llm_processor.py
- Enhances function documentation using LLM
- Generates detailed parameter descriptions


