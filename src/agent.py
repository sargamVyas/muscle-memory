# src/agent.py

import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from anthropic import Anthropic
from config import EVIDENCE_DIR
from phases import observe_page, decide_action
from helpers import parse_claude_response

# Initialize Anthropic client
client = Anthropic()

# Create evidence directory if it doesn't exist
Path(EVIDENCE_DIR).mkdir(exist_ok=True)

# ========== PROMPTS ==========

SYSTEM_PROMPT = """You are an automation agent that controls a web browser.

Your job is to complete tasks by interacting with web pages.

You can perform these actions:
1. type - Type text into an input field
2. click - Click a button, link, or interactive element
3. navigate - Navigate to a URL
4. escalate_to_human - If you're stuck and can't proceed safely

IMPORTANT: Only interact with elements that are visible on the page.
If you can't find an element or don't know what to do, respond with escalate_to_human.

Always respond in JSON format like this:
{
  "reasoning": "Why you chose this action",
  "action_type": "type|click|navigate|escalate_to_human",
  "target": "Element name or description",
  "value": "Value to type (only for type action)",
  "reason_for_escalation": "Why escalating (only for escalate_to_human)"
}

Do NOT include any text outside the JSON. Only JSON."""

USER_PROMPT_TEMPLATE = """Goal: {goal}

Current page state:
URL: {url}
Page title: {page_title}

Form fields available:
{form_fields}

Visible text on page:
{visible_text}

Interactive elements:
{interactive_elements}

What should we do next? Respond ONLY with JSON."""


# ========== MAIN AGENT LOOP ==========

def agent_loop(goal: str, member_id: str, max_steps: int = 20):
    """
    Main agent loop: orchestrates all 7 phases.
    
    Args:
        goal: What we're trying to accomplish
        member_id: Member ID to use in interactions
        max_steps: Maximum iterations before giving up
    
    Returns:
        Dictionary with success status and events
    """
    
    events = []
    step_count = 0
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto("http://localhost:8000/login")
        
        while step_count < max_steps:
            print(f"\n{'='*60}")
            print(f"Step {step_count + 1}")
            print(f"{'='*60}")
            
            # PHASE 1: OBSERVE
            print("PHASE 1: OBSERVE")
            observation = observe_page(page, step_count + 1)
            events.append({"phase": "observe", "step": step_count + 1, "observation": observation})
            print(f"  URL: {observation['url']}")
            print(f"  Page: {observation['page_title']}")
            
            # PHASE 2: DECIDE
            print("PHASE 2: DECIDE")
            action = decide_action(goal, observation)
            events.append({"phase": "decide", "step": step_count + 1, "action": action})
            print(f"  Action: {action.get('action_type')}")
            print(f"  Target: {action.get('target', 'N/A')}")
            print(f"  Reasoning: {action.get('reasoning', 'N/A')}")
            
            # Check if Claude wants to escalate
            if action.get('action_type') == 'escalate_to_human':
                print("\n⚠️  ESCALATING TO HUMAN")
                print(f"  Reason: {action.get('reason_for_escalation', action.get('reason', 'Unknown'))}")
                events.append({"phase": "escalate", "step": step_count + 1, "reason": action.get('reason')})
                browser.close()
                return {"success": False, "reason": "escalated_to_human", "events": events}

            
            print("PHASE 3: ACT")
            from phases import act_on_page
            result = act_on_page(page, action)
            events.append({"phase": "act", "step": step_count + 1, "result": result})
            print(f"  Success: {result['success']}")
            print(f"  Result: {result['result']}")
            print(f"  Strategy: {result['strategy_used']}")
            
            # TODO: Add Phase 4 (CHECKPOINT), Phase 5 (HANDLE), Phase 6 (STOP), Phase 7 (RECORD)
            step_count += 1
        
        browser.close()
    
    return {"success": False, "reason": "max_steps_reached", "events": events}


# ========== TEST ==========

if __name__ == "__main__":
    # Start mock app first: python src/mock_app.py
    # Then run this
    
    print("Starting agent loop...")
    print("Goal: Check balance for member 12345")
    
    result = agent_loop(
        goal="Check balance for member 12345",
        member_id="12345"
    )
    
    print("\n" + "="*60)
    print("AGENT LOOP FINISHED")
    print("="*60)
    print(f"Success: {result['success']}")
    print(f"Reason: {result.get('reason', 'N/A')}")
    print(f"Total steps: {len(result['events'])}")