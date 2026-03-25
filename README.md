# Swim Workout Writer

Private mobile-friendly web app for uploading Apple Workouts swim screenshots, reviewing parsed workout fields, and writing them to a MySQL-compatible database.

## Features
- Single-user login
- Screenshot upload from mobile
- OCR extraction using `tesseract`
- Review/edit flow before saving
- Persistent stroke mappings such as `Kickboard -> Freestyle`
- Immediate writes after confirmation

## Local setup
1. Copy `.env.example` to `.env` and set credentials.
2. Install dependencies: `pip install -r requirements.txt`
3. Run the app: `python app.py`
4. Open `http://127.0.0.1:8000`

Default local storage uses SQLite. Point `DATABASE_URL` at MySQL in production, for example:

```bash
DATABASE_URL=mysql+pymysql://user:password@host:3306/database_name
```

## Docker
```bash
docker compose up --build
```

## Notes
- Unknown stroke labels can be mapped permanently from the review screen.
- Uploaded screenshots are stored in `uploads/`.
- The app creates the single admin account on first boot from `ADMIN_USERNAME` and `ADMIN_PASSWORD`.
