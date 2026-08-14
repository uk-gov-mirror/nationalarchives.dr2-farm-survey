{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "crossAccountBucketAccess",
      "Effect": "Allow",
      "Principal": {
        "AWS": [
          "${root_account}",
          "${research_account}"
        ]
      },
      "Action": [
        "s3:ListBucket"
      ],
      "Resource": "arn:aws:s3:::${source_jsons_bucket_name}"
    },
    {
      "Sid": "crossAccountObjectAccess",
      "Effect": "Allow",
      "Principal": {
        "AWS": [
          "${root_account}",
          "${research_account}"
        ]
      },
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::${source_jsons_bucket_name}/*"
    }
  ]
}
