{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "lambdas",
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "aws:SourceAccount": "${account_id}"
        }
      }
    },
    {
      "Sid": "rootUsers",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::${account_id}:root"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
