{
  "Statement": [
    {
      "Sid": "listBucketAndGetObject",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket",
        "s3:GetObject"
      ],
      "Resource": [
        "arn:aws:s3:::${source_jsons_bucket_name}",
        "arn:aws:s3:::${source_jsons_bucket_name}/*"
      ]
    }
  ],
  "Version": "2012-10-17"
}