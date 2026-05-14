


setup SSL

apt install nginx
apt install certbot python3-certbot-nginx
certbot --nginx -d yourdomain.com -d www.yourdomain.com

Create Env Variables

Create a hidden file in your project directory (e.g., .env) and restrict its permissions so only the service user can read it.

```bash
chmod 600 .env

EMAIL_USER=your-dedicated-account@gmail.com
RECEIVER_EMAIL_USER=your-destination-account@gmail.com
EMAIL_PASSWORD=your-16-character-app-password

COT_ADMIN_PASSWORD=your-password
```
