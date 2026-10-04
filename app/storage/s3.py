class S3Storage:
    def __init__(self, endpoint, bucket, key, secret, region="auto"):
        try:
            import boto3
        except ImportError as e:
            raise RuntimeError("S3/R2 storage requires boto3. Install requirements-full.txt") from e
        self.bucket = bucket
        self.s3 = boto3.client("s3", endpoint_url=endpoint, aws_access_key_id=key, aws_secret_access_key=secret, region_name=region)
