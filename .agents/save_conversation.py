import sys
import json
import os

def parse_transcript(transcript_path):
    turns = []
    current_turn = None
    
    if not os.path.exists(transcript_path):
        return turns

    with open(transcript_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                step = json.loads(line)
            except Exception:
                continue
            
            step_type = step.get("type")
            source = step.get("source")
            content = step.get("content", "")
            
            # Start of a new turn when USER_INPUT is seen
            if step_type == "USER_INPUT" or (source == "USER_EXPLICIT" and step_type == "USER_INPUT"):
                if current_turn:
                    turns.append(current_turn)
                current_turn = {
                    "Input": content,
                    "Tools Used": [],
                    "Output": ""
                }
            elif current_turn:
                # Check for tool calls in PLANNER_RESPONSE
                if step_type == "PLANNER_RESPONSE" and "tool_calls" in step:
                    tool_calls = step["tool_calls"]
                    if tool_calls:
                        for tc in tool_calls:
                            current_turn["Tools Used"].append({
                                "tool": tc.get("name"),
                                "arguments": tc.get("args"),
                                "result": None
                            })
                # Check for tool results
                elif source == "MODEL" and step_type not in ("PLANNER_RESPONSE", "CONVERSATION_HISTORY", "KNOWLEDGE_ARTIFACTS"):
                    # Find the last tool call without a result and associate it
                    assigned = False
                    for tool_use in reversed(current_turn["Tools Used"]):
                        if tool_use["result"] is None:
                            tool_use["result"] = content
                            assigned = True
                            break
                    if not assigned:
                        current_turn["Tools Used"].append({
                            "tool": step_type,
                            "arguments": None,
                            "result": content
                        })
                # Check for final model output
                elif source == "MODEL" and step_type == "PLANNER_RESPONSE" and content:
                    current_turn["Output"] = content

    if current_turn:
        turns.append(current_turn)
        
    return turns

def main():
    # 1. Antigravity pipes the event payload to stdin
    try:
        input_data = sys.stdin.read()
        
        # DEBUG: Log the input data
        output_dir = os.path.join(os.getcwd(), "agent_logs")
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, "debug_payload.json"), "w") as f:
            f.write(input_data)
            
        payload = json.loads(input_data)
    except Exception as e:
        with open(os.path.join(output_dir, "debug_error.log"), "w") as f:
            f.write(str(e))
        # Failsafe: always return empty JSON so the IDE doesn't hang
        print("{}")
        return

    # Extract metadata provided by Antigravity
    transcript_path = payload.get("transcriptPath")
    conversation_id = payload.get("conversationId")
    
    if not conversation_id and "id" in payload:
        conversation_id = payload.get("id")
    if not conversation_id:
        conversation_id = "unknown_session"

    if not transcript_path and conversation_id != "unknown_session":
        app_data_dir = os.path.expanduser("~/.gemini/antigravity-ide")
        transcript_path = os.path.join(app_data_dir, "brain", conversation_id, ".system_generated", "logs", "transcript.jsonl")

    # 2. Parse and save the structured conversation
    if transcript_path:
        output_dir = os.path.join(os.getcwd(), "agent_logs")
        os.makedirs(output_dir, exist_ok=True)
        
        destination = os.path.join(output_dir, f"{conversation_id}_structured.json")
        
        try:
            structured_data = parse_transcript(transcript_path)
            with open(destination, 'w', encoding='utf-8') as out_f:
                json.dump(structured_data, out_f, indent=2, ensure_ascii=False)
        except Exception as e:
            # You can log this to a local debug file if needed
            debug_log = os.path.join(output_dir, "error.log")
            with open(debug_log, 'a', encoding='utf-8') as err_f:
                err_f.write(f"Error parsing transcript: {str(e)}\n")

    # 3. Contract requirement: Must return JSON to stdout
    print(json.dumps({}))

if __name__ == "__main__":
    main()

