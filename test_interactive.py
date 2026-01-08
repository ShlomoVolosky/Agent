import os 
import json
import sys
from agent import search_kb, log_uncertainty, update_kb, load, kb, uncertainties

def load_env_file(path=".env"):
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value)

load_env_file()

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

AUTO_APPROVE = False

def llm_real(msgs, tools=None):
    try:
        from openai import OpenAI
    except ImportError:
        print("Error: openai package not installed")
        return {'role': 'assistant', 'content': 'API package missing'}
    
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=msgs,
            tools=tools if tools else None,
            tool_choice="auto" if tools else None
        )
        
        message = response.choices[0].message
        
        if message.tool_calls:
            approved_calls = []
            
            for tc in message.tool_calls:
                if tc.function.name == 'update_kb':
                    args = json.loads(tc.function.arguments)
                    print(f"\n[LLM wants to update KB]")
                    print(f"Doc ID: {args.get('doc_id')}")
                    print(f"New content: {json.dumps(args.get('new_content'), indent=2)}")
                    
                    if AUTO_APPROVE:
                        print("✓ Auto-approved")
                        approved = True
                    else:
                        approve = input("\nApprove this KB update? (y/n): ").strip().lower()
                        approved = approve == 'y'
                    
                    if approved:
                        approved_calls.append({
                            'id': tc.id,
                            'type': tc.type,
                            'function': {
                                'name': tc.function.name,
                                'arguments': tc.function.arguments
                            }
                        })
                    else:
                        print("✗ Update rejected")
                else:
                    approved_calls.append({
                        'id': tc.id,
                        'type': tc.type,
                        'function': {
                            'name': tc.function.name,
                            'arguments': tc.function.arguments
                        }
                    })
            
            if approved_calls:
                return {
                    'role': 'assistant',
                    'content': message.content,
                    'tool_calls': approved_calls
                }
            else:
                return {
                    'role': 'assistant',
                    'content': 'KB update rejected.'
                }
        else:
            return {
                'role': 'assistant',
                'content': message.content
            }
    
    except Exception as e:
        print(f"API Error: {e}")
        return {'role': 'assistant', 'content': f'Error: {str(e)}'}

def test_with_approval():
    global AUTO_APPROVE
    
    if OPENAI_API_KEY == "your-openai-api-key-here":
        print("Error: Set OPENAI_API_KEY in this file")
        return
    
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()
        if mode == 'yes':
            AUTO_APPROVE = True
            print("Mode: AUTO-APPROVE all KB updates\n")
        elif mode == 'no':
            AUTO_APPROVE = False
            print("Mode: MANUAL APPROVAL required for each update\n")
        else:
            print(f"Unknown mode: {mode}")
            print("Usage: python test_interactive.py [yes|no]")
            print("  yes - auto-approve all updates")
            print("  no  - ask for approval each time (default)")
            return
    else:
        print("Mode: MANUAL APPROVAL required for each update")
        print("(Use 'python test_interactive.py yes' to auto-approve)\n")
    
    import agent
    agent.llm = llm_real
    
    questions = [
        "What happens to unused vacation days?",
        "How many sick leave days do I get?",
        "What is the parental leave policy?"
    ]
    
    for q in questions:
        print(f"\n{'='*60}")
        print(f"Question: {q}")
        print('='*60)
        
        try:
            result = agent.answer(q)
            print(f"\n✓ Answer: {result}")
            
            if agent.uncertainties:
                print(f"\nUncertainties logged: {len(agent.uncertainties)}")
        
        except Exception as e:
            print(f"Error: {e}")
    
    print("\n\nFinal KB State:")
    load()
    has_changes = False
    for doc in kb:
        if 'inferred' in doc:
            has_changes = True
            print(f"\n{doc['title']}:")
            print(json.dumps(doc['inferred'], indent=2))
    
    if not has_changes:
        print("(No changes - KB was not updated)")
    else:
        fixed = "knowledge_fixed.json"
        with open(fixed, 'w') as f:
            json.dump(kb, f, indent=2)
        print(f"\n✓ Saved repaired KB to: {fixed}")

if __name__ == "__main__":
    test_with_approval()