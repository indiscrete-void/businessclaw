#!/usr/bin/env python3
"""
Merge two JSON files at the key level.
Arrays are not merged recursively – they are simply replaced by the second file's array.
Usage: python merge_json.py file1.json file2.json [output.json]
"""

import json
import sys
import argparse
from collections.abc import Mapping

def merge(a, b):
    """Recursively merge two JSON structures.
    
    - If both are dicts, merge keys recursively.
    - If either is an array (list), b completely replaces a (no merging).
    - For all other types, b replaces a.
    """
    if isinstance(a, Mapping) and isinstance(b, Mapping):
        # Merge dictionaries
        result = dict(a)
        for key, b_val in b.items():
            a_val = a.get(key)
            if key in a:
                result[key] = merge(a_val, b_val)
            else:
                result[key] = b_val
        return result
    else:
        # Non-dict: overwrite with b (including arrays)
        return b

def main():
    parser = argparse.ArgumentParser(
        description="Merge two JSON files (arrays are not merged, just overwritten)."
    )
    parser.add_argument("file1", help="First JSON file")
    parser.add_argument("file2", help="Second JSON file (overrides first)")
    parser.add_argument("output", nargs="?", help="Output file (default: stdout)")
    args = parser.parse_args()

    try:
        with open(args.file1, "r", encoding="utf-8") as f1:
            data1 = json.load(f1)
        with open(args.file2, "r", encoding="utf-8") as f2:
            data2 = json.load(f2)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}", file=sys.stderr)
        sys.exit(1)

    merged = merge(data1, data2)

    output_json = json.dumps(merged, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
    else:
        print(output_json)

if __name__ == "__main__":
    main()
