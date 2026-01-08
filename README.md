# Self-Healing Knowledge Agent

A self-repairing knowledge base agent that detects gaps in policy documentation and fills them with minimal, low-confidence assumptions.

## Setup

1. Rename `.env.example` to `.env`
2. Add your OpenAI API key to the `.env` file:
   ```
   OPENAI_API_KEY=your_api_key_here
   ```

## How to Use

### agent.py - Main Agent

**Basic usage:**
```bash
python agent.py "What happens to unused vacation days?"
```

**With custom KB file:**
```bash
python agent.py company_policies.json "What happens to unused vacation days?"
```

**Interactive mode:**
```bash
python agent.py
# or with custom KB
python agent.py company_policies.json
```

**How it works:**
- If first argument ends with `.json` → uses it as KB file
- Otherwise uses default `knowledge.json`
- Remaining arguments = your question
- When the agent detects knowledge gaps, it uses `update_kb` to repair the knowledge base
- Updates are saved to a new file: `knowledge_fixed.json` (original KB remains unchanged)

### test_interactive.py - Real LLM Testing

This script replaces the stub LLM with real OpenAI GPT-4 API calls to demonstrate the agent with actual language model reasoning.

**Manual approval mode (ask before each KB update):**
```bash
python test_interactive.py no
```

**Auto-approve mode (approve all updates automatically):**
```bash
python test_interactive.py yes
```

**What it does:**
- Replaces the stub with real OpenAI GPT-4 API calls
- Runs 3 test questions
- Shows KB updates before applying them
- Requires `OPENAI_API_KEY` in `.env` file

**Note:** The test questions are hardcoded and can be modified in line 127 of `test_interactive.py`

## Test Questions

1. What happens to unused vacation days?
2. How many sick leave days do I get?
3. What is the parental leave policy?
4. Can I carry over vacation days to next year?
5. Do I need manager approval for vacation?