from flask import Flask, redirect, request, render_template_string, session, url_for
import os
import requests
import logging
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import json

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Set up logging
logging.basicConfig(level=logging.DEBUG)

# ... (keep the existing routes for '/' and '/login')

@app.route('/callback')
def callback():
    # ... (keep existing code)
    try:
        # ... (keep existing code)
        return redirect(url_for('setup_webhooks'))
    except Exception as e:
        error_message = f"Unexpected error in callback: {str(e)}"
        app.logger.error(error_message)
        return render_template_string(f"<html><body><h1>{error_message}</h1></body></html>")

@app.route('/setup_webhooks')
def setup_webhooks():
    access_token = session.get('access_token')
    if not access_token:
        app.logger.error("No access token found in session")
        return "Please log in first", 401

    try:
        # Fetch user's repositories
        repos_url = 'https://api.github.com/user/repos'
        headers = {'Authorization': f'token {access_token}'}
        repos_response = requests.get(repos_url, headers=headers)
        repos_response.raise_for_status()
        repos = repos_response.json()

        app.logger.info(f"Fetched {len(repos)} repositories")

        webhook_url = f"https://{request.host}/webhook"
        
        for repo in repos:
            # Set up webhook for each repository
            webhook_data = {
                'name': 'web',
                'active': True,
                'events': ['push'],
                'config': {
                    'url': webhook_url,
                    'content_type': 'json'
                }
            }
            webhook_url = f"https://api.github.com/repos/{repo['full_name']}/hooks"
            webhook_response = requests.post(webhook_url, headers=headers, data=json.dumps(webhook_data))
            
            if webhook_response.status_code != 201:
                app.logger.error(f"Failed to set up webhook for {repo['full_name']}: {webhook_response.text}")
            else:
                app.logger.info(f"Successfully set up webhook for {repo['full_name']}")

        return render_template_string("<html><body><h1>Webhooks set up successfully!</h1></body></html>")
    except Exception as e:
        error_message = f"Error setting up webhooks: {str(e)}"
        app.logger.error(error_message)
        return render_template_string(f"<html><body><h1>{error_message}</h1></body></html>")

@app.route('/webhook', methods=['POST'])
def webhook():
    payload = request.json
    app.logger.info(f"Received webhook: {json.dumps(payload)}")
    if payload['ref'] == 'refs/heads/main':  # or whichever branch you're interested in
        repo = payload['repository']['full_name']
        pusher = payload['pusher']['name']
        commits = payload['commits']
        
        message = Mail(
            from_email=os.environ.get('FROM_EMAIL', 'your-app@example.com'),
            to_emails=os.environ.get('TO_EMAIL', 'your-email@example.com'),
            subject=f'New push to {repo}',
            html_content=f'<p>New push to {repo} by {pusher}</p>' +
                         '<ul>' +
                         ''.join([f'<li>{commit["message"]}</li>' for commit in commits]) +
                         '</ul>'
        )
        try:
            sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
            response = sg.send(message)
            app.logger.info(f"Email sent, status code: {response.status_code}")
        except Exception as e:
            app.logger.error(f"Failed to send email: {str(e)}")
    
    return '', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)