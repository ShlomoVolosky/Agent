import json
import sys

kb = []
uncertainties = []
MAX = 5
KB_FILE = "knowledge.json"

def load():
    global kb
    with open(KB_FILE) as f:
        kb = json.load(f)

def save():
    with open(KB_FILE, "w") as f:
        json.dump(kb, f, indent=2)

def search_kb(query):
    words = query.lower().split()
    results = []
    
    for doc in kb:
        score = 0
        text = (doc.get('title', '') + ' ' + doc.get('content', '')).lower()
        for w in words:
            if w in text:
                score += 1
        if score > 0:
            results.append((score, doc))
    
    results.sort(reverse=True, key=lambda x: x[0])
    top = [d for _, d in results[:5]]
    
    if not top:
        return "No docs found"
    
    output = []
    for d in top:
        txt = f"ID: {d['id']}\nTitle: {d['title']}\nContent: {d['content']}"
        if 'inferred' in d:
            txt += f"\nInferred: {json.dumps(d['inferred'])}"
        output.append(txt)
    
    return "\n\n".join(output)

def log_uncertainty(reason):
    uncertainties.append({'reason': reason, 'idx': len(uncertainties)})
    return f"Logged: {reason}"

def update_kb(doc_id, new_content):
    for doc in kb:
        if doc['id'] == doc_id:
            if 'inferred' not in doc:
                doc['inferred'] = {}
            
            for key, val in new_content.items():
                if not isinstance(val, dict):
                    return "Error: bad format"
                if 'assumption' not in val or 'confidence' not in val or 'source' not in val:
                    return "Error: missing fields"
                if val['source'] != 'agent_inferred':
                    return "Error: wrong source"
                doc['inferred'][key] = val
            
            save()
            return f"Updated {doc_id}"
    
    return "Doc not found"

def llm(msgs, tools=None):
    last = msgs[-1]['content'].lower()
    
    if 'draft answer' in last:
        has_inf = 'inferred:' in last
        if 'vacation' in last:
            return {'role': 'assistant', 'content': '20 days paid vacation yearly. Unused days expire end of calendar year.' if has_inf and 'unused_days' in last else '20 days paid vacation yearly. Policy says unused days expire but timing not specified.'}
        if 'sick' in last:
            return {'role': 'assistant', 'content': 'Sick leave requires manager approval. Assuming 10 days annual limit.' if has_inf and 'annual_limit' in last else 'Sick leave requires manager approval. No annual limit specified in policy.'}
        if 'parental' in last or 'maternity' in last:
            return {'role': 'assistant', 'content': 'Maternity leave available. Assuming 12 weeks duration.' if has_inf and 'duration' in last else 'Maternity leave available but duration details missing from policy.'}
        return {'role': 'assistant', 'content': 'No policy found'}
    
    if 'self-check' in last:
        ans = last.split('answer:')[-1] if 'answer:' in last else last
        
        if 'timing not specified' in ans or 'but timing' in ans:
            return {
                'role': 'assistant',
                'content': None,
                'tool_calls': [{
                    'id': 'c1',
                    'type': 'function',
                    'function': {
                        'name': 'log_uncertainty',
                        'arguments': '{"reason": "Vacation expiry timing not specified"}'
                    }
                }, {
                    'id': 'c2',
                    'type': 'function',
                    'function': {
                        'name': 'update_kb',
                        'arguments': '{"doc_id": "1", "new_content": {"unused_days": {"status": "expire", "assumption": "Expiration at end of calendar year unless specified", "confidence": 0.35, "source": "agent_inferred"}}}'
                    }
                }]
            }
        
        if 'no annual limit' in ans or 'limit specified' in ans:
            return {
                'role': 'assistant',
                'content': None,
                'tool_calls': [{
                    'id': 'c1',
                    'type': 'function',
                    'function': {
                        'name': 'log_uncertainty',
                        'arguments': '{"reason": "Sick leave limit not specified"}'
                    }
                }, {
                    'id': 'c2',
                    'type': 'function',
                    'function': {
                        'name': 'update_kb',
                        'arguments': '{"doc_id": "2", "new_content": {"annual_limit": {"days": 10, "assumption": "Standard sick leave allowance", "confidence": 0.3, "source": "agent_inferred"}}}'
                    }
                }]
            }
        
        if ('details missing' in ans or 'duration details' in ans) and ('maternity' in ans or 'parental' in ans):
            return {
                'role': 'assistant',
                'content': None,
                'tool_calls': [{
                    'id': 'c1',
                    'type': 'function',
                    'function': {
                        'name': 'log_uncertainty',
                        'arguments': '{"reason": "Parental leave duration missing"}'
                    }
                }, {
                    'id': 'c2',
                    'type': 'function',
                    'function': {
                        'name': 'update_kb',
                        'arguments': '{"doc_id": "3", "new_content": {"duration": {"weeks": 12, "assumption": "Standard maternity leave duration", "confidence": 0.25, "source": "agent_inferred"}}}'
                    }
                }]
            }
        
        return {'role': 'assistant', 'content': 'YES - Answer fully supported'}
    
    return {'role': 'assistant', 'content': 'Unclear request'}

def run_tool(name, args_str):
    try:
        args = json.loads(args_str)
    except:
        return "Bad JSON"
    
    if name == 'search_kb':
        return search_kb(args.get('query', ''))
    if name == 'log_uncertainty':
        return log_uncertainty(args.get('reason', ''))
    if name == 'update_kb':
        return update_kb(args.get('doc_id', ''), args.get('new_content', {}))
    
    return f"Unknown tool: {name}"

def answer(question):
    load()
    global uncertainties
    uncertainties = []
    
    msgs = [{
        'role': 'system',
        'content': '''Self-healing KB agent. When gaps detected in self-check, call BOTH log_uncertainty AND update_kb together.

EXAMPLE: If policy says "days expire" but doesn't specify when:
- Call log_uncertainty: "Expiry timing not specified"  
- Call update_kb: Add assumption with low confidence (0.3-0.35)
- BOTH in same response. Never skip update_kb.'''
    }]
    
    tools = [
        {
            'type': 'function',
            'function': {
                'name': 'search_kb',
                'description': 'Search KB',
                'parameters': {
                    'type': 'object',
                    'properties': {'query': {'type': 'string'}},
                    'required': ['query']
                }
            }
        },
        {
            'type': 'function',
            'function': {
                'name': 'log_uncertainty',
                'description': 'Log uncertainty',
                'parameters': {
                    'type': 'object',
                    'properties': {'reason': {'type': 'string'}},
                    'required': ['reason']
                }
            }
        },
        {
            'type': 'function',
            'function': {
                'name': 'update_kb',
                'description': 'Update KB with inferred data',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'doc_id': {'type': 'string'},
                        'new_content': {'type': 'object'}
                    },
                    'required': ['doc_id', 'new_content']
                }
            }
        }
    ]
    
    draft = None
    loops = 0
    
    while loops < MAX:
        loops += 1
        
        ctx = search_kb(question)
        
        msgs.append({
            'role': 'user',
            'content': f'KB Context:\n{ctx}\n\nQuestion: {question}\n\nProduce draft answer. State if info missing.'
        })
        
        resp = llm(msgs, tools)
        msgs.append(resp)
        
        if resp.get('content'):
            draft = resp['content']
        
        msgs.append({
            'role': 'user',
            'content': f'Self-check: Is answer fully supported by KB with zero gaps?\n\nAnswer: {draft}\n\nIf ANY detail is missing/unclear/unspecified (even timing, limits, duration, conditions), call log_uncertainty then update_kb with minimal assumption. BOTH tools required. If truly complete, say YES.'
        })
        
        check = llm(msgs, tools)
        
        if check.get('tool_calls'):
            tool_results = []
            for tc in check['tool_calls']:
                result = run_tool(tc['function']['name'], tc['function']['arguments'])
                tool_results.append({
                    'tool_call_id': tc['id'],
                    'role': 'tool',
                    'name': tc['function']['name'],
                    'content': result
                })
            
            msgs.append({'role': 'assistant', 'content': None, 'tool_calls': check['tool_calls']})
            msgs.extend(tool_results)
            load()
            continue
        
        elif check.get('content') and 'YES' in check['content'].upper():
            return draft
        
        else:
            msgs.append(check)
    
    return draft or "Max iterations reached"

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].endswith('.json'):
        KB_FILE = sys.argv[1]
        question_args = sys.argv[2:]
    else:
        question_args = sys.argv[1:]
    
    q = ' '.join(question_args) if question_args else input("Question: ")
    
    print("\nProcessing...\n")
    result = answer(q)
    print(f"Answer: {result}")
    
    if uncertainties:
        print(f"\n[Repaired {len(uncertainties)} gaps]")
        fixed = KB_FILE.replace('.json', '_fixed.json')
        with open(fixed, 'w') as f:
            json.dump(kb, f, indent=2)
        print(f"Saved to: {fixed}")