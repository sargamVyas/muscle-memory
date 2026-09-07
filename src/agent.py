# src/agent.py

import os
import json
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright
from anthropic import Anthropic
from config import REDACTION_LIST, EVIDENCE_DIR

# Initialize Anthropic client
client = Anthropic()

# Create evidence directory if it doesn't exist
Path(EVIDENCE_DIR).mkdir(exist_ok=True)

# ========== HELPER FUNCTIONS ==========

def redact_value(field_name: str, value: str) -> str:
    """
    Redact sensitive values based on field name.
    
    If field name is in REDACTION_LIST, return [REDACTED]
    Otherwise return the value as-is
    """
    field_name_lower = field_name.lower()
    
    for redacted_field in REDACTION_LIST:
        if redacted_field.lower() in field_name_lower:
            return "[REDACTED]"
    
    return value

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

def extract_form_fields(page) -> list:
    """
    Extract all form fields from the page.
    
    Returns list of dicts with: label, type, value (if visible)
    """
    form_fields = []
    
    try:
        # Get all inputs
        inputs = page.query_selector_all('input')
        for input_elem in inputs:
            field_type = input_elem.get_attribute('type') or 'text'
            placeholder = input_elem.get_attribute('placeholder') or ''
            value = input_elem.input_value() if field_type != 'password' else ''
            
            # Redact if needed
            value = redact_value(placeholder or field_type, value)
            
            form_fields.append({
                "type": field_type,
                "placeholder": placeholder,
                "value": value
            })
        
        # Get all buttons
        buttons = page.query_selector_all('button')
        for button in buttons:
            text = button.text_content().strip()
            button_type = button.get_attribute('type') or 'button'
            
            form_fields.append({
                "type": "button",
                "text": text,
                "button_type": button_type
            })
    
    except Exception as e:
        print(f"Error extracting form fields: {e}")
    
    return form_fields

def extract_visible_text(page) -> str:
    """
    Extract visible text from the page.
    
    Gets headings, labels, paragraphs, and button text.
    """
    try:
        # Get body text content
        body = page.query_selector('body')
        if body:
            text = body.text_content()
            # Clean up whitespace
            text = ' '.join(text.split())
            # Limit to first 500 chars (don't overwhelm Claude)
            return text[:500]
    except Exception as e:
        print(f"Error extracting visible text: {e}")
    
    return ""

def extract_interactive_elements(page) -> list:
    """
    Extract clickable/interactive elements.
    
    Returns list of buttons, links, and form inputs.
    """
    elements = []
    
    try:
        # Get all buttons
        buttons = page.query_selector_all('button')
        for button in buttons:
            text = button.text_content().strip()
            elements.append({
                "type": "button",
                "text": text,
                "selector": get_selector(button)
            })
        
        # Get all links
        links = page.query_selector_all('a')
        for link in links:
            text = link.text_content().strip()
            elements.append({
                "type": "link",
                "text": text,
                "href": link.get_attribute('href'),
                "selector": get_selector(link)
            })
        
        # Get all inputs
        inputs = page.query_selector_all('input')
        for input_elem in inputs:
            placeholder = input_elem.get_attribute('placeholder') or ''
            elements.append({
                "type": "input",
                "placeholder": placeholder,
                "selector": get_selector(input_elem)
            })
    
    except Exception as e:
        print(f"Error extracting interactive elements: {e}")
    
    return elements

def get_selector(element) -> str:
    """Get a CSS selector for an element."""
    try:
        # Try to get ID first
        elem_id = element.get_attribute('id')
        if elem_id:
            return f"#{elem_id}"
        
        # Try to get other selectors
        # This is simplified; Playwright doesn't have a built-in selector generator
        tag = element.evaluate("el => el.tagName.toLowerCase()")
        return tag
    except:
        return "unknown"

# ========== TEST ==========

if __name__ == "__main__":
    # Start mock app (make sure it's running on port 8000)
    # Then test OBSERVE
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto("http://localhost:8000/login")
        
        observation = observe_page(page, 1)
        
        print("Observation:")
        print(json.dumps(observation, indent=2))
        
        browser.close()