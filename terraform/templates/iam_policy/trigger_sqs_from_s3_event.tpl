{
  "Statement": [
    {
      "Sid": "AllowS3ToPublishMessages",
      "Effect": "Allow",
      "Principal": {
        "Service": "s3.amazonaws.com"
      },
      "Action": "sqs:SendMessage",
      "Resource": "${queue_arn}",
      "Condition": {
        "ArnEquals": {
          "aws:SourceArn": "${bucket_arn}"
        }
      }
    }
  ],
  "Version": "2012-10-17"
}