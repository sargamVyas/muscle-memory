# src/mock_app.py
from flask import Flask, render_template, request
import json
import os

# Initialize Flask app
app = Flask(__name__, template_folder='../templates')

# Load members data
def load_members():
    with open('members.json') as f:
        return json.load(f)

members = load_members()

# ========== ROUTES ==========

@app.route('/login', methods=['GET'])
def login():
    """Show login page"""
    return render_template('login.html')

@app.route('/results', methods=['POST'])
def results():
    """Handle member search"""
    member_id = request.form.get('member_id')
    
    # Check if member exists
    if member_id not in members:
        return render_template('error.html', message=f"Member {member_id} not found")
    
    member = members[member_id]
    return render_template('results.html', member=member, member_id=member_id)

@app.route('/action', methods=['POST'])
def action():
    """Handle action (check balance or withdraw)"""
    member_id = request.form.get('member_id')
    action_type = request.form.get('action')
    
    if member_id not in members:
        return render_template('error.html', message=f"Member {member_id} not found")
    
    member = members[member_id]
    
    if action_type == 'check_balance':
        return render_template('action.html', 
            member=member, 
            action_type='check_balance',
            balance=member['balance']
        )
    
    return render_template('error.html', message="Invalid action")

# ========== START APP ==========

if __name__ == '__main__':
    print("Starting mock banking app on http://localhost:8000")
    app.run(debug=True, port=8000)