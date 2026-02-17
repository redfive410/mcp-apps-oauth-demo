# Auth Server

## Deployment

Before deploying, make sure the secret exists in Secret Manager:

```bash
echo -n "your-actual-password" | gcloud secrets create demo-password --data-file=-
```

Then deploy:

```bash
./deploy.sh
```
