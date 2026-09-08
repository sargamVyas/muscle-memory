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

# ========== MAIN AGENT LOOP ==========

def agent_loop(goal: str, member_id: str, max_steps: int = 20):
    """
    Main agent loop: orchestrates all 7 phases.
    """
    
    from phases import (
        observe_page, decide_action, act_on_page, 
        checkpoint, handle_result, should_stop,
        record_event, save_events_to_file
    )
    
    events = []
    step_count = 0
    error_count = 0
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto("http://localhost:8000/login")
        
        while step_count < max_steps:
            print(f"\n{'='*60}")
            print(f"Step {step_count + 1}")
            print(f"{'='*60}")
            
            previous_url = page.url
            
            # PHASE 1: OBSERVE
            print("PHASE 1: OBSERVE")
            observation = observe_page(page, step_count + 1)
            event = record_event("observe", observation)
            events.append(event)
            print(f"  URL: {observation['url']}")
            
            # PHASE 2: DECIDE
            print("PHASE 2: DECIDE")
            action = decide_action(goal, observation)
            event = record_event("decide", action)
            events.append(event)
            print(f"  Action: {action.get('action_type')}")
            
            # Check if escalating
            if action.get('action_type') == 'escalate_to_human':
                print("\n⚠️  ESCALATING TO HUMAN")
                event = record_event("escalate", {"reason": action.get('reason')})
                events.append(event)
                save_events_to_file(events)
                browser.close()
                return {"success": False, "reason": "escalated_to_human", "events": events}

            # Printing to see what cl;asause is seeing after login
            print("\n[DEBUG] Claude saw:")
            print(f"  Form fields: {observation['form_fields']}")
            print(f"  Interactive elements: {observation['interactive_elements']}")
            print(f"  Claude decision: {action.get('action_type')} on '{action.get('target')}'")
            
            # PHASE 3: ACT
            print("PHASE 3: ACT")
            act_result = act_on_page(page, action)
            event = record_event("act", act_result)
            events.append(event)
            print(f"  Success: {act_result['success']}")
            print(f"  Result: {act_result['result']}")
            
            # PHASE 4: CHECKPOINT
            print("PHASE 4: CHECKPOINT")
            checkpoint_result = checkpoint(page, previous_url, action)
            event = record_event("checkpoint", checkpoint_result)
            events.append(event)
            print(f"  Success: {checkpoint_result['success']}")
            print(f"  Reason: {checkpoint_result['reason']}")
            
            # PHASE 5: HANDLE
            print("PHASE 5: HANDLE")
            handle_result_dict = handle_result(page, action, act_result, checkpoint_result, error_count)
            event = record_event("handle", handle_result_dict)
            events.append(event)
            print(f"  Action: {handle_result_dict['action']}")
            print(f"  Error count: {handle_result_dict['error_count']}")
            
            error_count = handle_result_dict['error_count']
            
            # If handle says escalate
            if handle_result_dict['action'] == 'escalate_to_human':
                print("\n⚠️  ESCALATING TO HUMAN (from HANDLE)")
                save_events_to_file(events)
                browser.close()
                return {"success": False, "reason": "escalated_to_human", "events": events}
            
            # If handle says retry, restart loop
            if handle_result_dict['action'] == 'retry':
                print("  Retrying action...")
                step_count += 1
                continue
            
            # PHASE 6: STOP
            print("PHASE 6: STOP")
            stop_result = should_stop(page, goal, step_count, error_count, max_steps)
            event = record_event("stop", stop_result)
            events.append(event)
            print(f"  Should stop: {stop_result['should_stop']}")
            print(f"  Reason: {stop_result['reason']}")
            
            if stop_result['should_stop']:
                print("\n✅ GOAL ACHIEVED OR STOPPING CONDITIONS MET")
                
                # PHASE 7: RECORD
                print("PHASE 7: RECORD")
                artifact_path = save_events_to_file(events)
                
                browser.close()
                return {
                    "success": stop_result['reason'] == 'goal_achieved',
                    "reason": stop_result['reason'],
                    "events": events,
                    "artifact_path": artifact_path
                }
            
            step_count += 1
        
        # Max steps reached
        print("\n❌ MAX STEPS REACHED")
        save_events_to_file(events)
        browser.close()
        return {
            "success": False,
            "reason": "max_steps_reached",
            "events": events
        }

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