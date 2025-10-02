# MATLAB Function Parser

A comprehensive parser for extracting and documenting MATLAB functions from any repository, with automatic parameter detection including nargin-based optional parameters. This only applies to repositories on the local system, e.g. cloning a Github repo. Currently this parser does NOT have a recursive option.
This repo was created for personal use to scrape data from Pulseq scripts.

## Requirements

- Python 3.10+
- LLM API key
- Database (current repo uses Supabase). 

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


