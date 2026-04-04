# AWS prerequisites (EC2 + S3)

Checklist to apply in the AWS console (or IaC) before or during deployment. The app uses an **IAM instance profile** on EC2 (preferred) instead of long-lived access keys on disk.

## S3 bucket

1. Create a bucket in your chosen region (match `S3_REGION` in `.env`).
2. **Block Public Access**: keep all four settings ON (bucket stays private).
3. **Versioning**: optional; enable if you need object recovery.
4. **CORS**: not required for the default flow (browser hits your API; API returns redirects to presigned S3 URLs).

Object layout (app default): `{S3_PREFIX}{job_id}/voiceover.mp3`, `.../output.mp4`, `.../script.json`, plus optional slide/title assets under the same prefix.

## IAM instance profile for EC2

1. Create an **IAM role** trusted by **EC2**.
2. Attach an inline or managed policy allowing **only** this bucket and prefix, for example (replace placeholders):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ObjectRW",
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::YOUR_BUCKET_NAME/jobs/*"
    },
    {
      "Sid": "ListPrefix",
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::YOUR_BUCKET_NAME",
      "Condition": {
        "StringLike": {
          "s3:prefix": ["jobs/*"]
        }
      }
    }
  ]
}
```

Adjust `jobs/*` if you change `S3_PREFIX` (e.g. `prod/jobs/*`).

3. **Attach the role** to your EC2 instance as an **instance profile**.
4. Do **not** put `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` on the server unless you have no instance profile; the SDK uses the role automatically.

## Security group

| Direction | Port   | Source        | Notes                          |
|-----------|--------|---------------|--------------------------------|
| Inbound   | 22     | Your IP / VPN | SSH; avoid `0.0.0.0/0`         |
| Inbound   | 80     | `0.0.0.0/0`   | HTTP (Certbot, redirect HTTPS) |
| Inbound   | 443    | `0.0.0.0/0`   | HTTPS via nginx                |
| Outbound  | 443    | `0.0.0.0/0`   | OpenAI, ElevenLabs, Google, S3 |

## EC2 sizing (starting point)

- **Instance**: `t3.medium` or larger (video mux + Python).
- **EBS**: 30–50 GiB root (or separate volume for `ARTIFACT_ROOT` if you expect large temp jobs).

## After the instance is running

- Set `.env` on the server: `DATABASE_URL`, `S3_BUCKET`, `S3_REGION`, `S3_PREFIX=jobs/` (optional), `MEDIA_PRESIGN_EXPIRES_SECONDS`.
- Run **Alembic** migrations against PostgreSQL (see [DEPLOY_EC2.md](DEPLOY_EC2.md)).
