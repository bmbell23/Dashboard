# Dashboard Scan Feature

## Overview
The dashboard now includes library scan buttons for Jellyfin and Audiobookshelf, allowing you to trigger library scans directly from the dashboard.

## Changes Made

### 1. Removed Services
The following services have been removed from the dashboard:
- **Kavita** - Book/Comic server
- **Navidrome** - Music streaming server
- **Beets** - Music library manager

### 2. Added Scan Functionality
Added scan buttons to:
- **Jellyfin** - Scans all Jellyfin libraries
- **Audiobookshelf** - Scans all Audiobookshelf libraries

## Setup Instructions

### Prerequisites
You need to obtain API keys/tokens for the services you want to scan:

#### Jellyfin API Key
1. Log into your Jellyfin web interface (http://100.69.184.113:8096)
2. Go to **Dashboard** → **API Keys**
3. Click **+** to create a new API key
4. Give it a name (e.g., "Dashboard Scan")
5. Copy the generated API key

#### Audiobookshelf API Token
1. Log into your Audiobookshelf web interface (http://100.69.184.113:13378)
2. Click the **Settings** gear icon (top right)
3. Go to **Users**
4. Click on your user account
5. Copy the **API Token** shown

### Configuration

1. Navigate to the dashboard directory:
   ```bash
   cd /home/brandon/projects/Dashboard
   ```

2. Create a `.env` file from the example:
   ```bash
   cp .env.example .env
   ```

3. Edit the `.env` file and add your API keys:
   ```bash
   nano .env
   ```
   
   Add your keys:
   ```
   JELLYFIN_API_KEY=your_actual_jellyfin_api_key_here
   AUDIOBOOKSHELF_API_TOKEN=your_actual_audiobookshelf_token_here
   ```

4. Update the compose.yml to use the .env file (it's already configured to read from environment variables)

5. Rebuild and restart the dashboard:
   ```bash
   docker compose down
   docker compose build
   docker compose up -d
   ```

## Usage

Once configured, you'll see a green **Scan** button on the Jellyfin and Audiobookshelf service cards. Click the button to trigger a library scan.

The scan will:
- **Jellyfin**: Scan all libraries for new media
- **Audiobookshelf**: Scan all libraries for new audiobooks and podcasts

You'll see a toast notification indicating whether the scan started successfully or if there was an error.

## Troubleshooting

### "API key not set" error
- Make sure you've created the `.env` file with the correct API keys
- Restart the dashboard container after adding the keys
- Check the dashboard logs: `docker logs dashboard`

### "Failed to trigger scan" error
- Verify the API key/token is correct
- Make sure Jellyfin/Audiobookshelf is running
- Check that the URLs in `app.py` match your setup (default: http://100.69.184.113:8096 for Jellyfin, http://100.69.184.113:13378 for Audiobookshelf)

### Scan button doesn't appear
- Clear your browser cache
- Hard refresh the page (Ctrl+Shift+R or Cmd+Shift+R)

## Technical Details

### Backend Changes
- Added `requests` library to `requirements.txt`
- Added `/api/scan/jellyfin` endpoint that calls Jellyfin's `/Library/Refresh` API
- Added `/api/scan/audiobookshelf` endpoint that:
  1. Gets all libraries from Audiobookshelf
  2. Triggers a scan for each library via `/api/libraries/{id}/scan`

### Frontend Changes
- Added scan button to Jellyfin and Audiobookshelf service cards
- Added `scanJellyfin()` and `scanAudiobookshelf()` JavaScript functions
- Added CSS styling for the scan button (green color scheme)

## Files Modified
- `app.py` - Added scan endpoints and removed old services
- `static/index.html` - Added scan buttons and JavaScript functions, removed old service cards
- `requirements.txt` - Added requests library
- `compose.yml` - Added environment variables for API keys
- `.env.example` - Created example environment file

