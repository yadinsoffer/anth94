from flask import Flask, redirect, request, render_template_string, session
import os
from dotenv import load_dotenv
import requests
import logging
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Set up logging
logging.basicConfig(level=logging.DEBUG)

@app.route('/')
def home():
    return render_template_string('''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Anti - GitHub Login</title>
        <style>
            body { font-family: Arial, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
            .login-button { padding: 10px 20px; font-size: 16px; background-color: #24292e; color: white; border: none; border-radius: 5px; cursor: pointer; }
        </style>
    </head>
    <body>
        <button class="login-button" onclick="window.location.href='/login'">Login with GitHub</button>
    </body>
    </html>
    ''')

@app.route('/login')
def login():
    github_client_id = os.getenv('GITHUB_CLIENT_ID')
    return redirect(f'https://github.com/login/oauth/authorize?client_id={github_client_id}&scope=repo')

@app.route('/callback')
def callback():
    app.logger.debug("Callback route accessed")
    session_code = request.args.get('code')
    github_client_id = os.getenv('GITHUB_CLIENT_ID')
    github_client_secret = os.getenv('GITHUB_CLIENT_SECRET')

    app.logger.debug(f"Received code: {session_code}")
    app.logger.debug(f"Client ID: {github_client_id}")
    app.logger.debug(f"Client Secret: {github_client_secret[:5]}...")  # Log only first 5 chars of secret

    if not session_code:
        return render_template_string("<html><body><h1>Error: No code received from GitHub</h1></body></html>")

    if not github_client_id or not github_client_secret:
        return render_template_string("<html><body><h1>Error: Missing GitHub client ID or secret</h1></body></html>")

    try:
        r = requests.post('https://github.com/login/oauth/access_token', data={
            'client_id': github_client_id,
            'client_secret': github_client_secret,
            'code': session_code
        }, headers={'Accept': 'application/json'})

        app.logger.debug(f"GitHub API response: {r.text}")

        r.raise_for_status()  # Raise an exception for bad responses

        access_token = r.json()['access_token']
        session['access_token'] = access_token
        success_message = f"Logged in successfully! Access token: {access_token[:10]}..."
        app.logger.debug(success_message)
        return render_template_string(f"<html><body><h1>{success_message}</h1></body></html>")
    except requests.exceptions.RequestException as e:
        error_message = f"Error during GitHub API request: {str(e)}"
        app.logger.error(error_message)
        return render_template_string(f"<html><body><h1>{error_message}</h1></body></html>")
    except KeyError:
        error_message = f"Failed to get access token from GitHub response: {r.text}"
        app.logger.error(error_message)
        return render_template_string(f"<html><body><h1>{error_message}</h1></body></html>")
    except Exception as e:
        error_message = f"Unexpected error: {str(e)}"
        app.logger.error(error_message)
        return render_template_string(f"<html><body><h1>{error_message}</h1></body></html>")

@app.route('/webhook', methods=['POST'])
def webhook():
    payload = request.json
    if payload['ref'] == 'refs/heads/main':  # or whichever branch you're interested in
        repo = payload['repository']['full_name']
        pusher = payload['pusher']['name']
        commits = payload['commits']
        
        message = Mail(
            from_email='yadinupstage@gmail.com',
            to_emails='yadinupstage@gmail.com',
            subject=f'New push to {repo}',
            html_content=f'<p>New push to {repo} by {pusher}</p>' +
                         '<ul>' +
                         ''.join([f'<li>{commit["message"]}</li>' for commit in commits]) +
                         '</ul>'
        )
        try:
            sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
            response = sg.send(message)
            print(response.status_code)
        except Exception as e:
            print(str(e))
    
    return '', 200

if __name__ == '__main__':
    print("Starting Flask server on http://localhost:8000")
    app.run(debug=True, host='0.0.0.0', port=8000, use_reloader=False)