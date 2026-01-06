import json
from typing import List, Dict

data = []
uncertainties = []
MAX = 3 # loop-protection
"""Most questions need only 1-2 loops (detect gap → repair → verify)"""

def load():
    global data
    with open("knowledge.json") as f:
        data = json.load(f)

def save():
    with open("knowledge.json", "w") as f:
        json.dump(data, f, indent=2)

def retrieve(query):
    words = query.lower().split()
    results = []
    for doc in data:
        score = 0
        text = (doc['title'] + ' ' + doc['content']).lower()
        for w in words:
            if w in text:
                score += 1
        if score > 0:
            results.append({'doc': doc, 'score': score})
    results.sort(key=lambda x: x['score'], reverse=True)
    return [r['doc'] for r in results[:3]]

def search_kb(query):
    docs = retrieve(query)
    if not docs:
        return "No docs"
    output = "Found:\n"
    for doc in docs:
        output += f"ID: {doc['id']}, Title: {doc['title']}\n{doc['content']}\n"
        if 'inferred' in doc:
            output += f"Inferred: {json.dumps(doc['inferred'])}\n"
        output += "\n"
    return output

def log_uncertainty(reason):
    uncertainties.append({'reason': reason, 'n': len(uncertainties)})
    return f"Logged: {reason}"

def update_kb(doc_id, new_content):
    for doc in data:
        if doc['id'] == doc_id:
            if 'inferred' not in doc:
                doc['inferred'] = {}
            for k, v in new_content.items():
                doc['inferred'][k] = v
            save()
            return f"Updated {doc_id}"
    return "Not found"

def llm(msgs):
    last = msgs[-1]['content']
    
    if 'produce a draft' in last.lower():
        lines = last.split('\n')
        query = ""
        for line in lines:
            if line.lower().startswith('question:'):
                query = line.lower()
                break
        
        if 'parental' in query or 'maternity' in query:
            doc = next((d for d in data if d.get('id') == '3'), None)
            if doc and 'inferred' in doc:
                return {'content': 'Maternity leave available. We assume 12 weeks duration based on typical policies.'}
            return {'content': 'Maternity leave available but details missing.'}
        
        elif 'sick' in query:
            doc = next((d for d in data if d.get('id') == '2'), None)
            if doc and 'inferred' in doc:
                return {'content': 'Sick leave needs manager approval. We assume 10 days per year.'}
            return {'content': 'Sick leave needs manager approval. No limit specified.'}
        
        elif 'vacation' in query or 'carry' in query:
            doc = next((d for d in data if d.get('id') == '1'), None)
            if doc and 'inferred' in doc:
                if 'carry' in query:
                    return {'content': 'Vacation days expire end of calendar year, cannot carry over.'}
                elif 'manager' in query or 'approval' in query:
                    return {'content': 'Vacation policy doesnt mention manager approval.'}
                return {'content': '20 days paid vacation per year. Unused days expire end of calendar year.'}
            else:
                if 'carry' in query:
                    return {'content': 'Policy says days expire but timing unclear, carryover unknown.'}
                elif 'manager' in query or 'approval' in query:
                    return {'content': 'Vacation policy doesnt mention manager approval.'}
                return {'content': '20 days paid vacation per year. Days expire but timing unclear.'}
        
        return {'content': 'No policy found.'}
    
    elif 'self-check' in last.lower():
        lines = last.split('\n')
        answer = ""
        for line in lines:
            if line.lower().startswith('answer:'):
                answer = line.lower()
                break
        
        if 'vacation' in answer and 'unclear' in answer:
            return {'tool_calls': [
                {'function': {'name': 'log_uncertainty', 'arguments': '{"reason": "Timing not specified"}'}},
                {'function': {'name': 'update_kb', 'arguments': '{"doc_id": "1", "new_content": {"unused_days": {"status": "expire", "assumption": "Expiration at end of calendar year unless specified", "confidence": 0.35, "source": "agent_inferred"}}}'}}
            ]}
        elif 'sick' in answer and 'no limit' in answer:
            return {'tool_calls': [
                {'function': {'name': 'log_uncertainty', 'arguments': '{"reason": "Duration not specified"}'}},
                {'function': {'name': 'update_kb', 'arguments': '{"doc_id": "2", "new_content": {"annual_limit": {"days": 10, "assumption": "Typical allowance absent policy", "confidence": 0.3, "source": "agent_inferred"}}}'}}
            ]}
        elif ('parental' in answer or 'maternity' in answer) and 'missing' in answer:
            return {'tool_calls': [
                {'function': {'name': 'log_uncertainty', 'arguments': '{"reason": "Duration not documented"}'}},
                {'function': {'name': 'update_kb', 'arguments': '{"doc_id": "3", "new_content": {"duration": {"weeks": 12, "assumption": "Standard duration when not specified", "confidence": 0.25, "source": "agent_inferred"}}}'}}
            ]}
        elif 'carryover' in answer and 'unknown' in answer:
            return {'tool_calls': [
                {'function': {'name': 'log_uncertainty', 'arguments': '{"reason": "Carryover unclear"}'}},
                {'function': {'name': 'update_kb', 'arguments': '{"doc_id": "1", "new_content": {"unused_days": {"status": "expire", "assumption": "Expiration at end of calendar year unless specified", "confidence": 0.35, "source": "agent_inferred"}}}'}}
            ]}
        return {'content': 'YES'}
    
    return {'content': 'OK'}

def run_tool(name, args):
    parsed = json.loads(args) if isinstance(args, str) else args
    if name == 'search_kb':
        return search_kb(parsed['query'])
    elif name == 'log_uncertainty':
        return log_uncertainty(parsed['reason'])
    elif name == 'update_kb':
        return update_kb(parsed['doc_id'], parsed['new_content'])
    return "Unknown"

def answer(question):
    load()
    global uncertainties
    uncertainties = []
    
    loops = 0
    draft = ""
    
    while loops < MAX:
        loops += 1
        
        msgs = [{'role': 'system', 'content': 'You are a self-healing agent.'}]
        
        context = search_kb(question)
        
        msgs.append({'role': 'user', 'content': f'Context:\n{context}\n\nQuestion: {question}\n\nProduce a draft answer.'})
        resp = llm(msgs)
        draft = resp.get('content', '')
        msgs.append({'role': 'assistant', 'content': draft})
        
        msgs.append({'role': 'user', 'content': f'Self-check: Is this answer fully supported by KB with no missing facts?\nAnswer: {draft}\n\nIf NO, call tools. If YES, respond YES.'})
        check = llm(msgs)
        
        if 'tool_calls' in check:
            for tc in check['tool_calls']:
                fn = tc['function']
                result = run_tool(fn['name'], fn['arguments'])
            load()
        elif check.get('content', '').strip().upper().startswith('YES'):
            return draft
    
    return draft

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        q = ' '.join(sys.argv[1:])
    else:
        load()
        q = input("Enter your question: ")
    
    print("\nProcessing...\n")
    result = answer(q)
    print("Answer:", result)
    
    if uncertainties:
        print(f"\n[Uncertainties detected: {len(uncertainties)} ]")
