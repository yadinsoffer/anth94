from flask import Flask, redirect, request, render_template_string, session, url_for
from flask_sqlalchemy import SQLAlchemy
import os
import requests
import logging
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import json

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///site.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Set up logging
logging.basicConfig(level=logging.DEBUG)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    github_username = db.Column(db.String(80), unique=True, nullable=False)
    access_token = db.Column(db.String(120), nullable=False)

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
    github_client_id = os.environ.get('GITHUB_CLIENT_ID')
    return redirect(f'https://github.com/login/oauth/authorize?client_id={github_client_id}&scope=repo,user')

@app.route('/callback')
def callback():
    app.logger.debug("Callback route accessed")
    session_code = request.args.get('code')
    github_client_id = os.environ.get('GITHUB_CLIENT_ID')
    github_client_secret = os.environ.get('GITHUB_CLIENT_SECRET')

    app.logger.debug(f"Received code: {session_code}")
    app.logger.debug(f"Client ID: {github_client_id}")
    app.logger.debug(f"Client Secret: {github_client_secret[:5]}...")  # Log only first 5 chars of secret

    if not session_code:
        app.logger.error("No code received from GitHub")
        return render_template_string("<html><body><h1>Error: No code received from GitHub</h1></body></html>")

    if not github_client_id or not github_client_secret:
        app.logger.error("Missing GitHub client ID or secret")
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

        # Get user info
        user_response = requests.get('https://api.github.com/user', headers={'Authorization': f'token {access_token}'})
        user_data = user_response.json()
        github_username = user_data['login']

        # Store or update user in database
        user = User.query.filter_by(github_username=github_username).first()
        if user:
            user.access_token = access_token
        else:
            user = User(github_username=github_username, access_token=access_token)
            db.session.add(user)
        db.session.commit()

        session['github_username'] = github_username
        
        app.logger.info(f"Successfully obtained access token for user: {github_username}")
        return redirect(url_for('list_repos'))
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

@app.route('/list_repos')
def list_repos():
    github_username = session.get('github_username')
    if not github_username:
        return render_template_string("<html><body><h1>Error: Not logged in. Please log in again.</h1></body></html>")

    user = User.query.filter_by(github_username=github_username).first()
    if not user:
        return render_template_string("<html><body><h1>Error: User not found. Please log in again.</h1></body></html>")

    try:
        # Fetch user's repositories
        repos_url = 'https://api.github.com/user/repos'
        headers = {'Authorization': f'token {user.access_token}'}
        repos_response = requests.get(repos_url, headers=headers)
        repos_response.raise_for_status()
        repos = repos_response.json()

        repo_list = [f'<li><input type="checkbox" name="repos" value="{repo["full_name"]}"> {repo["full_name"]}</li>' for repo in repos]
        
        return render_template_string(f"""
        <html>
        <body>
            <h1>Select repositories to set up webhooks:</h1>
            <form action="/setup_webhooks" method="post">
                <ul>
                    {"".join(repo_list)}
                </ul>
                <input type="submit" value="Set up webhooks">
            </form>
            <br>
            <a href="/check_token">Check Token Scopes</a>
        </body>
        </html>
        """)
    except Exception as e:
        error_message = f"Error fetching repositories: {str(e)}"
        app.logger.error(error_message)
        return render_template_string(f"<html><body><h1>{error_message}</h1></body></html>")

@app.route('/setup_webhooks', methods=['POST'])
def setup_webhooks():
    github_username = session.get('github_username')
    if not github_username:
        return render_template_string("<html><body><h1>Error: Not logged in. Please log in again.</h1></body></html>")

    user = User.query.filter_by(github_username=github_username).first()
    if not user:
        return render_template_string("<html><body><h1>Error: User not found. Please log in again.</h1></body></html>")

    selected_repos = request.form.getlist('repos')
    
    try:
        headers = {'Authorization': f'token {user.access_token}', 'Accept': 'application/vnd.github.v3+json'}
        webhook_url = f"https://{request.host}/webhook"
        
        setup_results = []
        for repo in selected_repos:
            # Check if user has admin rights to the repo
            repo_url = f"https://api.github.com/repos/{repo}"
            repo_response = requests.get(repo_url, headers=headers)
            repo_data = repo_response.json()
            
            app.logger.debug(f"Repo data for {repo}: {json.dumps(repo_data)}")
            
            if not repo_data.get('permissions', {}).get('admin', False):
                setup_results.append(f"Skipped {repo}: You don't have admin rights to this repository")
                continue

            webhook_data = {
                'name': 'web',
                'active': True,
                'events': ['push'],
                'config': {
                    'url': webhook_url,
                    'content_type': 'json'
                }
            }
            webhook_url = f"https://api.github.com/repos/{repo}/hooks"
            webhook_response = requests.post(webhook_url, headers=headers, json=webhook_data)
            
            app.logger.debug(f"Webhook response for {repo}: {webhook_response.status_code} - {webhook_response.text}")
            
            if webhook_response.status_code != 201:
                setup_results.append(f"Failed to set up webhook for {repo}: {webhook_response.text}")
            else:
                setup_results.append(f"Successfully set up webhook for {repo}")

        return render_template_string(f"""
        <html>
        <body>
            <h1>Webhook Setup Results:</h1>
            <ul>
                {"".join(f"<li>{result}</li>" for result in setup_results)}
            </ul>
            <a href="/check_token">Check Token Scopes</a>
        </body>
        </html>
        """)
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
        
        # Find the access token for the pusher
        user = User.query.filter_by(github_username=pusher).first()
        if not user:
            app.logger.error(f"No access token found for user: {pusher}")
            return '', 200

        headers = {'Authorization': f'token {user.access_token}'}
        
        for commit in commits:
            commit_sha = commit['id']
            app.logger.info(f"Processing commit: {commit_sha}")
            app.logger.info(f"Commit message: {commit['message']}")
            
            # Fetch the commit details
            commit_url = f"https://api.github.com/repos/{repo}/commits/{commit_sha}"
            commit_response = requests.get(commit_url, headers=headers)
            
            if commit_response.status_code == 200:
                commit_data = commit_response.json()
                for file in commit_data['files']:
                    filename = file['filename']
                    status = file['status']
                    
                    app.logger.info(f"File: {filename}, Status: {status}")
                    
                    if status == 'modified':
                        # Log the patch (changes) for the file
                        if 'patch' in file:
                            app.logger.info(f"Changes in {filename}:")
                            app.logger.info(file['patch'])
                    elif status == 'added':
                        app.logger.info(f"New file added: {filename}")
                    elif status == 'removed':
                        app.logger.info(f"File removed: {filename}")
            else:
                app.logger.error(f"Failed to fetch commit details: {commit_response.status_code} - {commit_response.text}")

    return '', 200

@app.route('/check_token')
def check_token():
    github_username = session.get('github_username')
    if not github_username:
        return "No user logged in. Please log in again."

    user = User.query.filter_by(github_username=github_username).first()
    if not user:
        return "User not found in database. Please log in again."

    headers = {'Authorization': f'token {user.access_token}'}
    r = requests.get('https://api.github.com/user', headers=headers)
    
    if r.status_code == 200:
        scopes = r.headers.get('X-OAuth-Scopes', '').split(', ')
        user_data = r.json()
        return f"""
        <h1>Token Information</h1>
        <p>Token scopes: {', '.join(scopes) if scopes else 'No scopes'}</p>
        <p>User: {user_data.get('login')}</p>
        <p>Name: {user_data.get('name')}</p>
        <a href="/">Back to Home</a>
        """
    else:
        return f"Error checking token: {r.status_code} - {r.text}"

@app.before_first_request
def create_tables():
    db.create_all()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)