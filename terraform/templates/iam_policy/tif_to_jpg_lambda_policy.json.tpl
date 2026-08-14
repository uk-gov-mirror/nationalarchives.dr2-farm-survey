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
    },
    {
      "Sid": "writeAccess",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject"
      ],
      "Resource": [
        "arn:aws:s3:::${dest_bucket}/${files_prefix}/*",
        "arn:aws:s3:::${dest_bucket}/${records_prefix}/*",
        "arn:aws:s3:eu-west-2:${dest_account_id}:accesspoint/farm-survey/object/${files_prefix}/*",
        "arn:aws:s3:eu-west-2:${dest_account_id}:accesspoint/farm-survey/object/${records_prefix}/*"
      ]
    },
    {
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes"
      ],
      "Effect": "Allow",
      "Resource": ["arn:aws:sqs:eu-west-2:${account_id}:${queue_name}"],
      "Sid": "receiveDeleteMessage"
    },
    {
      "Sid": "getWebIdentityToken",
      "Effect": "Allow",
      "Action": "sts:GetWebIdentityToken",
      "Resource": "arn:aws:sts::${account_id}:self",
      "Condition": {
        "ForAllValues:StringEquals": {
          "sts:IdentityTokenAudience": "api://AzureADTokenExchange"
        }
      }
    },
    {
      "Action": [
        "logs:PutLogEvents",
        "logs:CreateLogStream",
        "logs:CreateLogGroup"
      ],
      "Effect": "Allow",
      "Resource": [
        "arn:aws:logs:eu-west-2:${account_id}:log-group:/aws/lambda/${lambda_name}:*:*",
        "arn:aws:logs:eu-west-2:${account_id}:log-group:/aws/lambda/${lambda_name}:*"
      ],
      "Sid": "writeLogs"
    }
  ],
  "Version": "2012-10-17"
}