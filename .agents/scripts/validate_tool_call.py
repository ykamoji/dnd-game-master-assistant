import sys
import json
import re

def main():
    try:
        # Read the payload from standard input
        input_data = sys.stdin.read()
        if not input_data.strip():
            sys.exit(0)

        payload = json.loads(input_data)

        # We only care about run_command tools in this hook
        tool_name = payload.get("tool")
        if tool_name and tool_name != "run_command":
            sys.exit(0)

        # Extract the command line argument
        args = payload.get("args", {})
        command = args.get("CommandLine", "")
        if not command:
            sys.exit(0)

        # Define destructive command patterns
        destructive_patterns = [
            r"rm\s+-r[fF]?\s+/",
            r"rm\s+-r[fF]?\s+/\*",
            r"rm\s+-r[fF]?\s+\.",
            r"rm\s+-r[fF]?\s+\*"
        ]

        # Check against patterns
        for pattern in destructive_patterns:
            if re.search(pattern, command):
                print(f"Error: Destructive command detected! Execution blocked by hook (matched pattern '{pattern}').", file=sys.stderr)
                sys.exit(1)

        # If command is safe, allow execution
        sys.exit(0)

    except json.JSONDecodeError:
        # If stdin is not valid JSON, fallback to allow or block (allowing to prevent breaking everything)
        sys.exit(0)
    except Exception as e:
        print(f"Hook Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
