import requests
import json
import logging
from app import app

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ChatGPT API endpoint and key (replace with your actual key)
CHATGPT_API_URL = "https://api.openai.com/v1/chat/completions"
CHATGPT_API_KEY = "sk-proj-1LoJN3t9NkVVqncjWMmkT3BlbkFJ7CsrLNhBNVVWd2toB0qI"

def analyze_code_changes(file_path, file_content):
    prompt = f"Analyze the following code changes in {file_path}:\n\n{file_content}\n\nWrite a newsletter as if you're a product manager displaying the new updates that were just added to the code."
    
    headers = {
        "Authorization": f"Bearer {CHATGPT_API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "gpt-3.5-turbo",
        "messages": [{"role": "user", "content": prompt}]
    }
    
    try:
        response = requests.post(CHATGPT_API_URL, headers=headers, json=data)
        response.raise_for_status()
        
        analysis = response.json()['choices'][0]['message']['content']
        logger.info(f"AI Analysis for {file_path}:\n{analysis}")
        
        return analysis
    except Exception as e:
        logger.error(f"Error in AI analysis: {str(e)}")
        return None

# Modify the webhook function in app.py to call this function
def process_webhook_payload(payload):
    if 'ref' in payload and payload['ref'] == 'refs/heads/main':
        repo = payload['repository']['full_name']
        commits = payload['commits']
        
        for commit in commits:
            for file_path in commit['modified']:
                file_url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
                headers = {'Authorization': f"token {app.config.get('GITHUB_ACCESS_TOKEN')}"}
                response = requests.get(file_url, headers=headers)
                
                if response.status_code == 200:
                    file_content = base64.b64decode(response.json()['content']).decode('utf-8')
                    analysis = analyze_code_changes(file_path, file_content)
                    if analysis:
                        logger.info(f"AI analysis completed for {file_path}")
                else:
                    logger.error(f"Failed to fetch content of {file_path}: {response.status_code}")