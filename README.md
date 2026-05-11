# Po.La.R. Complete Dropbox Upload App

## Install locally on Mac

Open Terminal inside this folder and run:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
python3 app.py
```

Then open:

```text
http://localhost:5050
```

## Required `.env` values

```text
DROPBOX_ACCESS_TOKEN=your Dropbox token
DROPBOX_UPLOAD_FOLDER=/input
UPLOAD_PASSWORD=the password users will use
FLASK_SECRET_KEY=any long random string
MAX_UPLOAD_MB=2048
```
