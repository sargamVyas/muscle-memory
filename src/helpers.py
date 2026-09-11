# src/helpers.py
import re
import json
from config import REDACTION_LIST


EXTRACT_PATTERNS = {
    "balance": r'balance[:\s]*\$?\s*([\d,]+\.?\d*)',
    "name": r'name[:\s]+([A-Za-z][A-Za-z\s]*?)(?:\n|$|\.|\s{2,})',
}


def find_extract_value(page, target_description: str):
    """Look up a labeled value (balance, name, etc.) in the page's visible text."""
    target_key = target_description.lower().strip()
    pattern = next((rgx for key, rgx in EXTRACT_PATTERNS.items() if key in target_key), None)
    if not pattern:
        return None
    try:
        visible = page.query_selector('body').text_content()
        match = re.search(pattern, visible, re.IGNORECASE)
        return match.group(1).strip() if match else None
    except Exception:
        return None


def redact_text(text: str) -> str:
    """
    Mask values that follow a sensitive label in free text, keeping the label
    so the LLM knows the field exists without ever seeing the value.
    'Balance: $1500.0' → 'Balance: [REDACTED]'
    """
    for kw in REDACTION_LIST:
        label = kw.replace('_', r'[ _]?')   # 'member_id' also matches 'Member ID'
        text = re.sub(rf'(\b{label}\b\s*[:\-]\s*)\S+', r'\1[REDACTED]', text, flags=re.IGNORECASE)
    return text


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


def extract_form_fields(page) -> list:
    """Extract all form fields from the page."""
    form_fields = []
    
    try:
        # Get all inputs
        inputs = page.query_selector_all('input')
        for input_elem in inputs:
            field_type = input_elem.get_attribute('type') or 'text'
            placeholder = input_elem.get_attribute('placeholder') or ''
            value = input_elem.input_value() if field_type != 'password' else ''
            value = redact_value(placeholder or field_type, value)
            
            form_fields.append({
                "type": field_type,
                "placeholder": placeholder,
                "value": value
            })
        
        # Get all buttons (PRIORITIZE)
        buttons = page.query_selector_all('button')
        for button in buttons:
            text = button.text_content().strip()
            button_type = button.get_attribute('type') or 'button'
            
            form_fields.append({
                "type": "button",
                "text": text,
                "button_type": button_type,
                "visible": True  # Add this to make it clear
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
            text = redact_text(text)
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

        # Non-semantic clickables (divs/spans with onclick) — hostile pages use these instead of buttons
        clickables = page.query_selector_all('[onclick]:not(button):not(a)')
        for el in clickables:
            text = el.text_content().strip()
            elements.append({
                "type": "clickable",
                "text": text,
                "selector": get_selector(el)
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
        tag = element.evaluate("el => el.tagName.toLowerCase()")
        return tag
    except:
        return "unknown"


def format_form_fields(form_fields: list) -> str:
    """Format form fields for Claude's context."""
    if not form_fields:
        return "No form fields found"
    
    lines = []
    for i, field in enumerate(form_fields, 1):
        if field['type'] == 'button':
            lines.append(f"  {i}. Button: '{field['text']}'")
        elif field['type'] == 'input':
            lines.append(f"  {i}. Input: placeholder='{field.get('placeholder', '')}', value='{field.get('value', '')}'")
    
    return "\n".join(lines)


def format_interactive_elements(elements: list) -> str:
    """Format interactive elements for Claude's context."""
    if not elements:
        return "No interactive elements found"
    
    lines = []
    for i, elem in enumerate(elements, 1):
        if elem['type'] == 'button':
            lines.append(f"  {i}. Button: '{elem['text']}'")
        elif elem['type'] == 'link':
            lines.append(f"  {i}. Link: '{elem['text']}' (href: {elem.get('href', '#')})")
        elif elem['type'] == 'input':
            lines.append(f"  {i}. Input field: '{elem.get('placeholder', 'No placeholder')}'")
        elif elem['type'] == 'clickable':
            lines.append(f"  {i}. Clickable: '{elem['text']}'")
    return "\n".join(lines)


def parse_claude_response(response_text: str) -> dict:
    """
    Parse Claude's JSON response.
    
    Handles cases where Claude wraps JSON in markdown code blocks.
    """
    try:
        # Remove markdown code blocks if present
        clean_text = response_text.strip()
        if clean_text.startswith('```json'):
            clean_text = clean_text[7:]  # Remove ```json
        if clean_text.startswith('```'):
            clean_text = clean_text[3:]  # Remove ```
        if clean_text.endswith('```'):
            clean_text = clean_text[:-3]  # Remove trailing ```
        
        clean_text = clean_text.strip()
        
        # Parse JSON
        action = json.loads(clean_text)
        
        # Validate required fields
        if 'action_type' not in action:
            return {
                "action_type": "escalate_to_human",
                "reason": "Claude response missing action_type field"
            }
        
        return action
        
    except json.JSONDecodeError as e:
        print(f"Invalid JSON from Claude: {response_text}")
        return {
            "action_type": "escalate_to_human",
            "reason": "Claude returned invalid JSON",
            "claude_response": response_text
        }
    except Exception as e:
        print(f"Error parsing Claude response: {e}")
        return {
            "action_type": "escalate_to_human",
            "reason": f"Error parsing response: {str(e)}"
        }