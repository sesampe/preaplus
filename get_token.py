from google_auth_oauthlib.flow import InstalledAppFlow

# Scopes: acceso a Google Drive (lectura y escritura de archivos creados por la app)
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

def main():
    # Usa el JSON que descargaste de Google Cloud
    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
    creds = flow.run_local_server(port=0)

    print("Access Token:", creds.token)
    print("Refresh Token:", creds.refresh_token)
    print("Client ID:", creds.client_id)
    print("Client Secret:", creds.client_secret)

if __name__ == "__main__":
    main()
