# Environment Configuration Instructions

## Angel One API Setup

The application is now configured to use `.env` files for Angel One credentials. Here's how to set it up:

### Step 1: Edit the .env File

Open the `.env` file in your project root directory and update the Angel One credentials:

```bash
# Angel One API Credentials
ANGEL_ONE_API_KEY=your_actual_api_key_here
ANGEL_ONE_CLIENT_CODE=your_actual_client_code_here
ANGEL_ONE_PASSWORD=your_actual_password_here
ANGEL_ONE_TOTP_SECRET=your_actual_totp_secret_here
```

### Step 2: Get Your Angel One Credentials

1. **Log in to your Angel One account**
2. **Go to Settings → API Settings**
3. **Generate API Key** and get your credentials:
   - **API Key**: Your unique API key
   - **Client Code**: Your Angel One client ID
   - **Password**: Your trading password
   - **TOTP Secret**: Your 2FA secret key (QR code value)

### Step 3: Replace Placeholder Values

Replace the placeholder values in the `.env` file:

- `your_actual_api_key_here` → Your real API key
- `your_actual_client_code_here` → Your real client code
- `your_actual_password_here` → Your real password
- `your_actual_totp_secret_here` → Your real TOTP secret

### Step 4: Save and Test

1. **Save the `.env` file**
2. **Start the application**: `python app.py`
3. **Check the console** for confirmation messages:
   - ✅ "Angel One API initialized from environment variables" (success)
   - ⚠️ "Angel One credentials not found in environment variables, using mock API" (check credentials)

## Security Notes

- **Never commit the `.env` file** to version control
- **Keep your credentials secure** and don't share them
- **The `.env` file is already in `.gitignore`** to prevent accidental commits

## Troubleshooting

### If you see "using mock API" message:
1. Check that your `.env` file exists in the project root
2. Verify the credential names are exactly as shown above
3. Make sure there are no extra spaces or quotes around the values
4. Restart the application after making changes

### If you get authentication errors:
1. Double-check your credentials are correct
2. Ensure your Angel One account is active
3. Verify the TOTP secret is correct
4. Check that your account has API access enabled

## Alternative Methods

If you prefer not to use the `.env` file, you can also:

1. **Set environment variables** directly in your system
2. **Use the web interface** at `/api/angel_one/configure` when the app is running

## File Structure

```
your-project/
├── .env                    # ← Your credentials go here
├── app.py                  # ← Loads credentials from .env
├── angel_one_api.py        # ← Uses the credentials
└── ...
```

The application will automatically load your Angel One credentials from the `.env` file when it starts up!
