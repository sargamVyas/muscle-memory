# src/phases.py

import json
from pathlib import Path
from dotenv import load_dotenv
from anthropic import Anthropic
from config import REDACTION_LIST, EVIDENCE_DIR
from helpers import (
    extract_form_fields,
    extract_visible_text,
    extract_interactive_elements,
    format_form_fields,
    format_interactive_elements,
    parse_claude_response
)

# Load .env file
load_dotenv()  # ADD THIS

# Initialize Anthropic client
client = Anthropic()

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


def decide_action(goal: str, observation: dict) -> dict:
    """
    DECIDE phase: Ask Claude what to do next.
    
    Returns action dict like:
    {
        "action_type": "type|click|navigate|escalate_to_human",
        "target": "...",
        "value": "...",
        "reasoning": "..."
    }
    """
    
    try:
        # Format the user prompt with observation data
        form_fields_str = format_form_fields(observation['form_fields'])
        interactive_str = format_interactive_elements(observation['interactive_elements'])
        
        user_prompt = USER_PROMPT_TEMPLATE.format(
            goal=goal,
            url=observation['url'],
            page_title=observation['page_title'],
            form_fields=form_fields_str,
            visible_text=observation['visible_text'],
            interactive_elements=interactive_str
        )
        
        # Call Claude
        response = client.messages.create(
            model="claude-opus-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": user_prompt
                }
            ]
        )
        
        # Extract response text
        response_text = extract_response_text(response)
        
        # Parse JSON
        action = parse_claude_response(response_text)
        
        return action
        
    except Exception as e:
        print(f"Error in decide_action: {e}")
        return {
            "action_type": "escalate_to_human",
            "reason": f"Error calling Claude: {str(e)}"
        }



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
        
        # Handle each action type
        if action_type == 'type':
            return act_type(page, target, value)
        elif action_type == 'click':
            return act_click(page, target)
        elif action_type == 'navigate':
            return act_navigate(page, action.get('url', ''))
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
    1. Placeholder text matching
    2. Accessibility tree (role + name)
    3. CSS selector
    
    Returns (element, strategy_used) or (None, 'none')
    """
    
    # Strategy 1: Find by placeholder text
    try:
        inputs = page.query_selector_all('input')
        for input_elem in inputs:
            placeholder = input_elem.get_attribute('placeholder') or ''
            if target_description.lower() in placeholder.lower():
                return (input_elem, 'placeholder_text')
    except:
        pass
    
    # Strategy 2: Find by button text
    try:
        buttons = page.query_selector_all('button')
        for button in buttons:
            text = button.text_content().strip()
            if target_description.lower() in text.lower():
                return (button, 'button_text')
    except:
        pass
    
    # Strategy 3: Find by accessibility role + name
    try:
        # Try to find by accessibility tree
        # This is a simplified approach - looks for elements with matching accessible names
        all_elements = page.query_selector_all('*')
        for elem in all_elements:
            try:
                accessible_name = elem.get_attribute('aria-label') or elem.get_attribute('placeholder') or elem.text_content().strip()
                if target_description.lower() in accessible_name.lower():
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
    
    return (None, 'none')


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