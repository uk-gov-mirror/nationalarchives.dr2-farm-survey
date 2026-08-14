# National Farm Survey Terraform

Infrastructure as Code for the National Farm Survey


## Local development

### Install Terraform locally

See: https://learn.hashicorp.com/terraform/getting-started/install.html

### Install AWS CLI Locally

See: https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-install.html

### Install Terraform Plugins on IntelliJ

HCL Language Support: https://plugins.jetbrains.com/plugin/7808-hashicorp-terraform--hcl-language-support

## Running Terraform Project Locally

**NOTE: Running Terraform locally should only be used to check the Terraform plan. Updating the DR2 environments should only ever be done through GitHub Actions**


1. (In the `terraform` directory) clone DR2 Configurations: https://github.
   com/nationalarchives/da-terraform-configurations

2. Initialise Terraform (if not done so previously):

   ```
   [location of project] $ terraform init
   ```

3. To ensure the modules are up-to-date, run
   ```
   [location of project] $ terraform get -update
   ```
4. To ensure that the terraform configuration is up-to-date, run
   ```
   [location of project] $ cd da-terraform-configurations
   [location of project/da-terraform-configurations] $ git pull
   [location of project/da-terraform-configurations] $ cd ..
   ```

5. Make your terraform changes

6. (Optional) To quickly validate the changes you made, run
   ```
   [location of project] $ terraform validate
   ```

7. Run Terraform to view changes that will be made to the DR2 environment AWS resources
    1. Make sure your credentials (for the environment that you are interested in) are valid/still valid first (the AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY and AWS_SESSION_TOKEN)
    2. If you have the AWS CLI installed:
        1. run `aws sso login --profile [account name where credentials are] && export AWS_PROFILE=[account name where credentials are]`

    3. Set the requisite variables in the `terraform.tfvars` file
    4. Run
      ```
      [location of project] $ terraform plan
      ```

8. Run `terraform fmt --recursive` to properly format your Terraform changes before pushing to a branch.

### Troubleshooting:

If you receive an error, try running `terraform get -update` (if it hasn't been run already)

## Further Information

* Terraform website: https://www.terraform.io/
* Terraform basic tutorial: https://learn.hashicorp.com/terraform/getting-started/build
