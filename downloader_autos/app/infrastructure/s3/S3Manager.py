import boto3
from pathlib import Path
from botocore.exceptions import BotoCoreError, ClientError

from app.domain.interfaces.IS3Manager import IS3Manager

class S3Manager(IS3Manager):
    def __init__(
        self,
        awsAccessKey: str,
        awsSecretKey: str,
        bucketNft: str,
        prefixNft: str,
    ):
        self.s3 = boto3.client(
            "s3",
            aws_access_key_id=awsAccessKey,
            aws_secret_access_key=awsSecretKey
        )
        self.bucketName = bucketNft
        self.prefix = prefixNft.rstrip("/") if prefixNft else ""

    async def uploadFile(self, filePath: Path) -> bool:
        try:
            fileName = Path(filePath).name
            s3Key = f"{self.prefix}/{fileName}" if self.prefix else fileName

            self.s3.upload_file(str(filePath), self.bucketName, s3Key)
            return True

        except (BotoCoreError, ClientError) as e:
            raise RuntimeError(f"Error subiendo archivo {filePath} a S3: {e}")
