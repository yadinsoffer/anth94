from flask import Flask, redirect, request, render_template_string, session, url_for
import os
import requests
import logging
import json
import requests
import json
import base64
import requests

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or os.urandom(24)

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
    github_client_id = os.environ.get('GITHUB_CLIENT_ID')
    return redirect(f'https://github.com/login/oauth/authorize?client_id={github_client_id}&scope=repo,user')

@app.route('/callback')
def callback():
    session_code = request.args.get('code')
    github_client_id = os.environ.get('GITHUB_CLIENT_ID')
    github_client_secret = os.environ.get('GITHUB_CLIENT_SECRET')

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

        r.raise_for_status()

        access_token = r.json()['access_token']
        session['access_token'] = access_token
        app.config['GITHUB_ACCESS_TOKEN'] = access_token  # Set the token in app config

        app.logger.info(f"Access token set in app config: {access_token[:10]}...")  # Log first 10 chars for verification

        # Get user info
        user_response = requests.get('https://api.github.com/user', headers={'Authorization': f'token {access_token}'})
        user_data = user_response.json()
        session['github_username'] = user_data['login']
        
        app.logger.info(f"Successfully obtained access token for user: {session['github_username']}")
        return redirect(url_for('list_repos'))
    except Exception as e:
        error_message = f"Error during GitHub OAuth flow: {str(e)}"
        app.logger.error(error_message)
        return render_template_string(f"<html><body><h1>{error_message}</h1></body></html>")

@app.route('/list_repos')
def list_repos():
    access_token = session.get('access_token')
    if not access_token:
        return render_template_string("<html><body><h1>Error: No access token found. Please log in again.</h1></body></html>")

    try:
        # Fetch user's repositories
        repos_url = 'https://api.github.com/user/repos'
        headers = {'Authorization': f'token {access_token}'}
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
            <br>
            <a href="/repo_contents">View Repository Contents</a>
        </body>
        </html>
        """)
    except Exception as e:
        error_message = f"Error fetching repositories: {str(e)}"
        app.logger.error(error_message)
        return render_template_string(f"<html><body><h1>{error_message}</h1></body></html>")

@app.route('/setup_webhooks', methods=['POST'])
def setup_webhooks():
    access_token = session.get('access_token')
    if not access_token:
        return render_template_string("<html><body><h1>Error: No access token found. Please log in again.</h1></body></html>")

    selected_repos = request.form.getlist('repos')
    
    try:
        headers = {'Authorization': f'token {access_token}', 'Accept': 'application/vnd.github.v3+json'}
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
    
    access_token = app.config.get('GITHUB_ACCESS_TOKEN')
    if not access_token:
        app.logger.error("No access token found in app config")
        app.logger.info(f"App config keys: {app.config.keys()}")  # Log all keys in app config
        return '', 200

    # Rest of the webhook function remains the same
    ...

    if 'ref' in payload:
        if payload['ref'] == 'refs/heads/main':  # or whichever branch you're interested in
            repo = payload['repository']['full_name']
            commits = payload['commits']
            
            for commit in commits:
                commit_sha = commit['id']
                app.logger.info(f"Processing commit: {commit_sha}")
                app.logger.info(f"Commit message: {commit['message']}")
                app.logger.info(f"Added files: {', '.join(commit['added'])}")
                app.logger.info(f"Removed files: {', '.join(commit['removed'])}")
                app.logger.info(f"Modified files: {', '.join(commit['modified'])}")
                
                # Fetch content of modified files
                for file_path in commit['modified']:
                    file_url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
                    headers = {'Authorization': f'token {access_token}'}
                    response = requests.get(file_url, headers=headers)
                    if response.status_code == 200:
                        file_content = base64.b64decode(response.json()['content']).decode('utf-8')
                        app.logger.info(f"Content of {file_path}:\n{file_content}")
                    else:
                        app.logger.error(f"Failed to fetch content of {file_path}: {response.status_code}")

    return '', 200

@app.route('/check_token')
def check_token():
    token = app.config.get('GITHUB_ACCESS_TOKEN')
    if token:
        return f"Access token is set in app config: {token[:10]}...", 200
    else:
        return "No access token found in app config", 404

    headers = {'Authorization': f'token {access_token}'}
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

