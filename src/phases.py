# src/phases.py

import json
from pathlib import Path
from dotenv import load_dotenv
from anthropic import Anthropic
from urllib.parse import urlparse
from config import REDACTION_LIST, EVIDENCE_DIR, BLOCKED_ACTION_KEYWORDS, ALLOWED_DOMAINS
from config import REDACTION_LIST, EVIDENCE_DIR
from helpers import (
    extract_form_fields,
    extract_visible_text,
    extract_interactive_elements,
    format_form_fields,
    format_interactive_elements,
    parse_claude_response,
    find_extract_value 
)

# Load .env file
load_dotenv()  # ADD THIS

# Initialize Anthropic client
client = Anthropic()

# ========== PROMPTS ==========

SYSTEM_PROMPT = """You are an automation agent that controls a web browser.

Your job is to complete tasks by interacting with web pages.

CRITICAL - DECISION LOGIC:
1. Look at the form fields
2. If an input field is EMPTY → type into it
3. If an input field ALREADY HAS A VALUE → do NOT type again, instead CLICK the Submit/Search button
4. Never type into a field that already has a value
5. Check "Already collected" below — if the page shows a piece of data you still need, EXTRACT it. Never extract something already listed as collected.
6. If everything you still need is on this page, extract it before clicking anywhere else.

ACTION TYPES:
- type: Enter text into an EMPTY input field only
- click: Click buttons, links, or perform actions
- navigate: Go to a URL
- extract: Pull a specific piece of data visible on the page (e.g. "balance", "member name") and record it
- escalate_to_human: If stuck, ask for help

SAFETY RULES:
- You may NOT withdraw, transfer, delete, or close accounts. These actions are blocked.
- If the goal requires a blocked action, respond with escalate_to_human instead of attempting it.

EXAMPLE SCENARIOS:
Scenario 1: Field is empty, Search button visible
  → Action: type the value into the field

Scenario 2: Field ALREADY HAS a value like '12345', Search button visible
  → Action: CLICK the Search button (do NOT type)

Scenario 3: On results page showing member details, need to proceed
  → Action: CLICK on "Check Balance" to proceed

Scenario 4: Page shows data you still need (check "Already collected" first)
  → Action: extract it (target = "balance" or "member name")

Always respond ONLY in JSON format:
{
  "reasoning": "Why this action",
  "action_type": "type|click|navigate|extract|escalate_to_human",
  "target": "Element name or data to extract",
  "value": "Text to type (only for type)"
}"""

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

Already collected: {already_collected}

What should we do next? Respond ONLY with JSON."""


# ========== PHASE 1: OBSERVE ==========

def observe_page(page, step_number: int) -> dict:
    """
    OBSERVE phase: Capture current page state.
    
    Returns:
    {
        "url": "...",
        "page_title": "...",
        "form_fields": [...],
        "visible_text": "...",
        "interactive_elements": [...],
        "screenshot_path": "..."
    }
    """
    
    # Step 1: Take screenshot
    screenshot_path = f"{EVIDENCE_DIR}/step_{step_number:03d}_screenshot.png"
    page.screenshot(path=screenshot_path)
    
    # Step 2: Get page URL and title
    url = page.url
    page_title = page.title()
    
    # Step 3: Extract form fields
    form_fields = extract_form_fields(page)
    
    # Step 4: Get visible text
    visible_text = extract_visible_text(page)
    
    # Step 5: Get interactive elements
    interactive_elements = extract_interactive_elements(page)
    
    # Build observation object
    observation = {
        "url": url,
        "page_title": page_title,
        "form_fields": form_fields,
        "visible_text": visible_text,
        "interactive_elements": interactive_elements,
        "screenshot_path": screenshot_path
    }
    
    return observation


# ========== PHASE 2: DECIDE ==========

def extract_response_text(response) -> str:
    """
    Extract text from Claude's response.
    
    Claude can return multiple content types (TextBlock, ThinkingBlock, etc).
    We want the TextBlock with the actual answer.
    """
    for block in response.content:
        if hasattr(block, 'text'):
            return block.text
    
    raise ValueError("No text content in Claude response")


def decide_action(goal: str, observation: dict, extracted_data: dict = None) -> dict:
    """DECIDE phase: Ask Claude what to do next."""
    extracted_data = extracted_data or {}

    try:
        form_fields_str = format_form_fields(observation['form_fields'])
        interactive_str = format_interactive_elements(observation['interactive_elements'])

        collected_str = ", ".join(f"{k}={v}" for k, v in extracted_data.items()) or "nothing yet"

        extra_instruction = ""
        for field in observation['form_fields']:
            if field.get('type') == 'text' and field.get('value'):
                extra_instruction = "\n⚠️ CRITICAL: The input field ALREADY has a value. DO NOT TYPE. CLICK THE SEARCH BUTTON INSTEAD."
                break

        user_prompt = USER_PROMPT_TEMPLATE.format(
            goal=goal,
            url=observation['url'],
            page_title=observation['page_title'],
            form_fields=form_fields_str,
            visible_text=observation['visible_text'],
            interactive_elements=interactive_str,
            already_collected=collected_str
        ) + extra_instruction

        response = client.messages.create(
            model="claude-opus-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}]
        )

        response_text = extract_response_text(response)
        action = parse_claude_response(response_text)

        return action

    except Exception as e:
        print(f"Error in decide_action: {e}")
        return {
            "action_type": "escalate_to_human",
            "reason": f"Error calling Claude: {str(e)}"
        }
        
def check_guardrails(action_type: str, target: str = "", url: str = "") -> tuple:
    """
    Safety allowlist. Returns (allowed, reason).
    Enforced in code, not just in the prompt — the LLM can be told not to
    withdraw, but this is what actually stops it. Called by both discovery
    (act_on_page) and replay, so no path bypasses it.
    """
    if action_type == 'click':
        t = (target or '').lower()
        for kw in BLOCKED_ACTION_KEYWORDS:
            if kw in t:
                return (False, f"Blocked action: '{target}' matches '{kw}'")

    if action_type == 'navigate':
        host = urlparse(url or '').netloc
        if host not in ALLOWED_DOMAINS:
            return (False, f"Blocked navigation: '{host}' not in allowed domains")

    return (True, "allowed")

    # ========== PHASE 3: ACT ==========

def act_on_page(page, action: dict) -> dict:
    """
    ACT phase: Perform the action on the page.
    
    Takes Claude's decision and actually interacts with the page.
    
    Returns:
    {
        "action": "type|click|navigate",
        "target": "...",
        "success": true/false,
        "result": "...",
        "element_found": true/false,
        "strategy_used": "..."
    }
    """
    
    try:
        action_type = action.get('action_type')
        target = action.get('target')
        value = action.get('value', '')

        allowed, reason = check_guardrails(action_type, target, action.get('url', ''))
        if not allowed:
            return {
                "action": action_type,
                "target": target,
                "success": False,
                "result": reason,
                "element_found": False,
                "strategy_used": "none",
                "blocked": True
            }
        
        # Handle each action type
        if action_type == 'type':
            return act_type(page, target, value)
        elif action_type == 'click':
            return act_click(page, target)
        elif action_type == 'navigate':
            return act_navigate(page, action.get('url', ''))
        elif action_type == 'extract':
            return act_extract(page, target)
        else:
            return {
                "action": action_type,
                "target": target,
                "success": False,
                "result": f"Unknown action type: {action_type}",
                "element_found": False,
                "strategy_used": "none"
            }
    
    except Exception as e:
        return {
            "action": action.get('action_type'),
            "target": action.get('target'),
            "success": False,
            "result": f"Error performing action: {str(e)}",
            "element_found": False,
            "strategy_used": "error"
        }


def find_element(page, target_description: str) -> tuple:
    """
    Find element using multi-signal resolver.
    
    Tries in order:
    1. Placeholder text matching (flexible)
    2. Button text matching
    3. Accessibility tree (role + name)
    4. CSS selector
    
    Returns (element, strategy_used) or (None, 'none')
    """
    
    # Extract key words from target (remove common words)
    target_lower = target_description.lower()
    key_words = [w for w in target_lower.split() if w not in ['input', 'field', 'button', 'element', 'a']]
    
    # Strategy 1: Find by placeholder text (flexible matching)
    try:
        inputs = page.query_selector_all('input')
        for input_elem in inputs:
            placeholder = (input_elem.get_attribute('placeholder') or '').lower()
            
            # Check if any key word appears in placeholder
            for keyword in key_words:
                if keyword in placeholder:
                    return (input_elem, 'placeholder_text')
            
            # Also check exact match (case-insensitive)
            if placeholder and (target_lower in placeholder or placeholder in target_lower):
                return (input_elem, 'placeholder_text')
    except:
        pass
    
    # Strategy 2: Find by button text
    try:
        buttons = page.query_selector_all('button')
        for button in buttons:
            text = button.text_content().strip().lower()
            
            # Check if any key word appears in button text
            for keyword in key_words:
                if keyword in text:
                    return (button, 'button_text')
            
            if text and (target_lower in text or text in target_lower):
                return (button, 'button_text')
    except:
        pass
    
    # Strategy 3: Find by accessibility attributes
    try:
        all_elements = page.query_selector_all('*')
        for elem in all_elements:
            try:
                # Check aria-label
                aria_label = (elem.get_attribute('aria-label') or '').lower()
                if aria_label:
                    for keyword in key_words:
                        if keyword in aria_label:
                            return (elem, 'accessibility_label')
                
                # Check accessible name
                accessible_name = (elem.text_content().strip() or '').lower()
                if accessible_name:
                    for keyword in key_words:
                        if keyword in accessible_name:
                            return (elem, 'accessibility_name')
            except:
                pass
    except:
        pass
    
    # Strategy 4: Try as CSS selector
    try:
        if target_description.startswith('#') or target_description.startswith('.'):
            elem = page.query_selector(target_description)
            if elem:
                return (elem, 'css_selector')
    except:
        pass
    
    # Strategy 5: Find by visible text (last resort)
    try:
        all_inputs = page.query_selector_all('input, button, a')
        for elem in all_inputs:
            text = elem.text_content().strip().lower()
            placeholder = (elem.get_attribute('placeholder') or '').lower()
            combined = f"{text} {placeholder}".lower()
            
            if any(keyword in combined for keyword in key_words):
                return (elem, 'text_match')
    except:
        pass
    
    return (None, 'none')

def act_extract(page, target_description: str) -> dict:
    """Pull a labeled value (balance, name, etc.) from the page's visible text."""
    value = find_extract_value(page, target_description)

    if value:
        return {
            "action": "extract",
            "target": target_description,
            "success": True,
            "result": f"Extracted {target_description} = '{value}'",
            "element_found": True,
            "strategy_used": "regex_pattern",
            "extracted_value": value
        }

    return {
        "action": "extract",
        "target": target_description,
        "success": False,
        "result": f"Could not find '{target_description}' on page",
        "element_found": False,
        "strategy_used": "regex_pattern",
        "extracted_value": None
    }

def act_type(page, target_description: str, value: str) -> dict:
    """Type text into an input field."""
    
    element, strategy = find_element(page, target_description)
    
    if not element:
        return {
            "action": "type",
            "target": target_description,
            "success": False,
            "result": "Could not find input field",
            "element_found": False,
            "strategy_used": strategy
        }
    
    try:
        # Fill the input (clears + types)
        element.fill(value)
        
        # Wait for page to respond (or timeout after 3 seconds)
        try:
            page.wait_for_load_state('networkidle', timeout=3000)
        except:
            # If page doesn't settle, that's okay - just continue
            pass
        
        return {
            "action": "type",
            "target": target_description,
            "success": True,
            "result": f"Typed '{value}' into field",
            "element_found": True,
            "strategy_used": strategy
        }
    
    except Exception as e:
        return {
            "action": "type",
            "target": target_description,
            "success": False,
            "result": f"Error typing: {str(e)}",
            "element_found": True,
            "strategy_used": strategy
        }


def act_click(page, target_description: str) -> dict:
    """Click a button or link."""
    
    element, strategy = find_element(page, target_description)
    
    if not element:
        return {
            "action": "click",
            "target": target_description,
            "success": False,
            "result": "Could not find element to click",
            "element_found": False,
            "strategy_used": strategy
        }
    
    try:
        # Click the element
        element.click()
        
        # Wait for page to respond (or timeout after 5 seconds)
        try:
            page.wait_for_load_state('networkidle', timeout=5000)
        except:
            # If page doesn't settle, that's okay
            pass
        
        return {
            "action": "click",
            "target": target_description,
            "success": True,
            "result": f"Clicked on {target_description}",
            "element_found": True,
            "strategy_used": strategy
        }
    
    except Exception as e:
        return {
            "action": "click",
            "target": target_description,
            "success": False,
            "result": f"Error clicking: {str(e)}",
            "element_found": True,
            "strategy_used": strategy
        }


def act_navigate(page, url: str) -> dict:
    """Navigate to a URL."""
    
    if not url:
        return {
            "action": "navigate",
            "target": url,
            "success": False,
            "result": "No URL provided",
            "element_found": False,
            "strategy_used": "none"
        }
    
    try:
        page.goto(url)
        
        # Wait for page to load
        try:
            page.wait_for_load_state('networkidle', timeout=5000)
        except:
            pass
        
        return {
            "action": "navigate",
            "target": url,
            "success": True,
            "result": f"Navigated to {url}",
            "element_found": True,
            "strategy_used": "goto"
        }
    
    except Exception as e:
        return {
            "action": "navigate",
            "target": url,
            "success": False,
            "result": f"Error navigating: {str(e)}",
            "element_found": False,
            "strategy_used": "none"
        }



# ========== PHASE 4: CHECKPOINT ==========

def checkpoint(page, previous_url: str, action: dict) -> dict:
    """
    CHECKPOINT phase: Verify the action actually worked.

    type: verified by reading the field back (typing never changes the URL,
          so URL-checking a type action is meaningless and was inflating error_count).
    click / navigate: verified by URL change.
    """

    try:
        import time
        current_url = page.url
        action_type = action.get('action_type')

        # --- TYPE: success = the value actually landed in the field ---
        if action_type == 'type':
            target = action.get('target', '')
            expected_value = action.get('value', '')

            element, _ = find_element(page, target)
            actual_value = None
            if element:
                try:
                    actual_value = element.input_value()
                except Exception:
                    actual_value = None

            if actual_value == expected_value:
                return {
                    "success": True,
                    "reason": "value_entered",
                    "current_url": current_url,
                    "previous_url": previous_url
                }
            else:
                return {
                    "success": False,
                    "reason": "value_not_entered",
                    "current_url": current_url,
                    "previous_url": previous_url
                }

        # --- CLICK: success = URL changed ---
        if action_type == 'click':
            time.sleep(1)
            if page.url != previous_url:
                return {
                    "success": True,
                    "reason": "url_changed",
                    "current_url": page.url,
                    "previous_url": previous_url
                }
            else:
                return {
                    "success": False,
                    "reason": "click_no_effect",
                    "current_url": page.url,
                    "previous_url": previous_url
                }

        # --- NAVIGATE: success = reached target URL ---
        if action_type == 'navigate':
            target_url = action.get('url')
            if page.url == target_url or (target_url and target_url in page.url):
                return {
                    "success": True,
                    "reason": "navigation_complete",
                    "current_url": page.url,
                    "previous_url": previous_url
                }
            else:
                return {
                    "success": False,
                    "reason": "navigation_failed",
                    "current_url": page.url,
                    "previous_url": previous_url
                }
            
        if action_type == 'extract':
            value = find_extract_value(page, action.get('target', ''))
            if value:
                return {
                    "success": True,
                    "reason": "value_extracted",
                    "current_url": current_url,
                    "previous_url": previous_url
                }
            else:
                return {
                    "success": False,
                    "reason": "value_not_found",
                    "current_url": current_url,
                    "previous_url": previous_url
                }

        return {
            "success": False,
            "reason": "unknown_action",
            "current_url": page.url,
            "previous_url": previous_url
        }

    except Exception as e:
        return {
            "success": False,
            "reason": f"checkpoint_error: {str(e)}",
            "current_url": page.url,
            "previous_url": previous_url
        }
# ========== PHASE 5: HANDLE ==========

def handle_result(page, action: dict, act_result: dict, checkpoint_result: dict, error_count: int) -> dict:
    """
    HANDLE phase: Recover from errors or continue.
    
    Returns:
    {
        "should_continue": true/false,
        "action": "continue|retry|escalate_to_human",
        "error_count": 0/1/2...,
        "reason": "..."
    }
    """

        # Guardrail violations are never retried — escalate immediately
    if act_result.get('blocked'):
        return {
            "should_continue": False,
            "action": "escalate_to_human",
            "error_count": error_count + 1,
            "reason": f"Guardrail: {act_result['result']}"
        }
    
    # If action succeeded AND checkpoint passed
    if act_result['success'] and checkpoint_result['success']:
        return {
            "should_continue": True,
            "action": "continue",
            "error_count": 0,
            "reason": "Action succeeded, checkpoint passed"
        }
    
    # If action failed but element was found
    if not act_result['success'] and act_result['element_found']:
        return {
            "should_continue": False,
            "action": "escalate_to_human",
            "error_count": error_count + 1,
            "reason": f"Action failed: {act_result['result']}"
        }
    
    # If element not found, try retry
    if not act_result['element_found']:
        if error_count < 2:  # Max 2 retries
            return {
                "should_continue": True,
                "action": "retry",
                "error_count": error_count + 1,
                "reason": "Element not found, retrying with different strategy"
            }
        else:
            return {
                "should_continue": False,
                "action": "escalate_to_human",
                "error_count": error_count + 1,
                "reason": "Element not found after 2 retries"
            }
    
    # Checkpoint failed (URL didn't change)
    if not checkpoint_result['success']:
        if error_count < 2:
            return {
                "should_continue": True,
                "action": "retry",
                "error_count": error_count + 1,
                "reason": f"Action didn't have expected effect: {checkpoint_result['reason']}"
            }
        else:
            return {
                "should_continue": False,
                "action": "escalate_to_human",
                "error_count": error_count + 1,
                "reason": "Action failed checkpoint after retries"
            }
    
    # Default: escalate
    return {
        "should_continue": False,
        "action": "escalate_to_human",
        "error_count": error_count + 1,
        "reason": "Unexpected state"
    }


# ========== PHASE 6: STOP ==========

def should_stop(page, goal: str, step_count: int, error_count: int, max_steps: int = 20, extracted_data: dict = None) -> dict:
    """
    STOP phase: Check if loop should exit.

    Returns:
    {
        "should_stop": true/false,
        "reason": "goal_achieved|max_steps|error_limit|stuck_on_login|continue",
        "details": "..."
    }
    """
    extracted_data = extracted_data or {}

    try:
        current_url = page.url

        # Check 1: Goal achieved — only once the value has actually been
        # extracted, not just because the word "balance" is somewhere on the page.
        if "check balance" in goal.lower():
            have_balance = bool(extracted_data.get("balance"))
            wants_name = "name" in goal.lower()
            have_name = bool(extracted_data.get("member_name"))

            if have_balance and (have_name or not wants_name):
                return {
                    "should_stop": True,
                    "reason": "goal_achieved",
                    "details": f"Extracted: {extracted_data}"
                }

        # Check 2: Max steps reached
        if step_count >= max_steps:
            return {
                "should_stop": True,
                "reason": "max_steps",
                "details": f"Reached max steps: {step_count}"
            }

        # Check 3: Error limit reached
        if error_count >= 3:
            return {
                "should_stop": True,
                "reason": "error_limit",
                "details": f"Error count: {error_count}"
            }

        # Check 4: Still on login page after too many steps (stuck)
        if "login" in current_url and step_count > 5:
            return {
                "should_stop": True,
                "reason": "stuck_on_login",
                "details": "Still on login page after 5 steps"
            }

        # Default: continue
        return {
            "should_stop": False,
            "reason": "continue",
            "details": f"Step {step_count}, errors: {error_count}"
        }

    except Exception as e:
        return {
            "should_stop": False,
            "reason": "continue",
            "details": f"Error checking stop condition: {str(e)}"
        }

# ========== PHASE 7: RECORD ==========

import datetime

def record_event(event_type: str, data: dict) -> dict:
    """
    Create an event record with timestamp.
    
    Returns:
    {
        "timestamp": "2025-01-16T10:30:45.123Z",
        "type": "observe|decide|act|checkpoint|handle|stop",
        "data": {...}
    }
    """
    
    return {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "type": event_type,
        "data": data
    }


def save_events_to_file(events: list, filename: str = None) -> str:
    """
    Save all events to JSON file in evidence folder.
    
    Returns: filepath
    """
    
    if not filename:
        timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"discovery_run_{timestamp}.json"
    
    filepath = f"{EVIDENCE_DIR}/{filename}"
    
    try:
        with open(filepath, 'w') as f:
            json.dump({
                "started_at": events[0]['timestamp'] if events else None,
                "ended_at": events[-1]['timestamp'] if events else None,
                "total_events": len(events),
                "events": events
            }, f, indent=2)
        
        print(f"✅ Events saved to {filepath}")
        return filepath
    
    except Exception as e:
        print(f"❌ Error saving events: {e}")
        return None